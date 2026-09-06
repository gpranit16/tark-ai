"""Tool Call Orchestrator for TARK AI. Bounded multi-step tool execution loop."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import re
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import ConversationMode, MessageRole
from app.providers.base import NormalizedMessage, ProviderError, ProviderStreamEvent, UsageMetadata
from app.services.chat.router import ModelRouter, ProviderSelection
from app.services.chat.sse import (
    message_start,
    text_delta,
    tool_available,
    tool_error_event,
    tool_result_event,
    tool_started,
)
from app.tools.base import ToolExecutionContext, ToolResult
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry, get_tool_registry

logger = logging.getLogger(__name__)

# Regex pattern for tool calls in model output
TOOL_CALL_REGEX = re.compile(
    r"<tool_call>\s*({[\s\S]*?})\s*</tool_call>",
    re.IGNORECASE,
)
JSON_CODEBLOCK_TOOL_REGEX = re.compile(
    r"```(?:json)?\s*(\{\s*\"(?:tool|name|function)\"[\s\S]*?\})\s*```",
    re.IGNORECASE,
)


def format_tools_system_prompt(registry: ToolRegistry, allowed_tools: Optional[List[str]] = None) -> str:
    """Format tools definition for the system prompt."""
    tools = registry.list_tools()
    if allowed_tools:
        tools = [t for t in tools if t.name in allowed_tools]

    if not tools:
        return ""

    lines = [
        "## AVAILABLE TOOLS",
        "You have access to the following secure tools to retrieve external information or perform specialized calculations:",
        "",
    ]

    for tool in tools:
        info = tool.get_info()
        schema = tool.get_schema()
        lines.append(f"### `{tool.name}`")
        lines.append(f"**Description**: {tool.description}")
        lines.append(f"**Parameters (JSON Schema)**: `{json.dumps(schema.get('parameters', {}))}`")
        lines.append("")

    current_date_str = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")
    lines.extend([
        f"## TEMPORAL CONTEXT & FRESHNESS",
        f"- Current Date: {current_date_str} (Year: 2026).",
        f"- When answering questions about latest events, news, or current facts, ALWAYS execute `search_news` or `web_search`.",
        f"- Strictly use the verified publication dates, URLs, and source titles returned in the tool response. Do not invent or synthesize past/stale dates.",
        "",
        "## TOOL CALLING INSTRUCTIONS",
        "1. When you need external facts, recent news, calculations, weather, financial prices, or workspace memories/documents, ALWAYS call the appropriate tool.",
        "2. To invoke a tool, output a single `<tool_call>` block containing a valid JSON object with `name` and `arguments` (or `parameters`).",
        "Example:",
        "<tool_call>",
        '{"name": "calculator", "arguments": {"expression": "250 * 1.18"}}',
        "</tool_call>",
        "",
        "3. You will receive the tool result in a `<tool_response>` block. Use that data to formulate a comprehensive, helpful, and accurate response.",
        "4. If NO tool is required, answer the user query directly without using any `<tool_call>` tags.",
        "",
        "## OUTPUT FORMATTING GUIDELINES",
        "- Present search results, news, and complex data cleanly using crisp headings, concise bullet points, and clickable markdown source links.",
        "- Avoid gigantic, awkwardly wide raw tables that clip horizontal screens unless explicitly requested by the user.",
        "- Keep responses clean, elegant, and easy to read.",
        "",
    ])

    return "\n".join(lines)


def parse_tool_calls(text: str) -> List[Tuple[str, Dict[str, Any]]]:
    """Extract tool calls from model output."""
    calls: List[Tuple[str, Dict[str, Any]]] = []

    # 1. Search for <tool_call>...</tool_call>
    matches = TOOL_CALL_REGEX.findall(text)
    for raw_json in matches:
        try:
            parsed = json.loads(raw_json)
            name = parsed.get("name") or parsed.get("tool") or parsed.get("function")
            params = parsed.get("parameters") or parsed.get("params") or parsed.get("arguments") or {}
            if isinstance(params, str):
                params = json.loads(params)
            if name and isinstance(params, dict):
                calls.append((name, params))
        except Exception as err:
            logger.debug("Failed parsing tool call block: %s (%s)", raw_json, err)

    if calls:
        return calls

    # 2. Search for ```json {"tool": ...} ``` codeblocks
    cb_matches = JSON_CODEBLOCK_TOOL_REGEX.findall(text)
    for raw_json in cb_matches:
        try:
            parsed = json.loads(raw_json)
            name = parsed.get("name") or parsed.get("tool") or parsed.get("function")
            params = parsed.get("parameters") or parsed.get("params") or parsed.get("arguments") or {}
            if isinstance(params, str):
                params = json.loads(params)
            if name and isinstance(params, dict):
                calls.append((name, params))
        except Exception as err:
            logger.debug("Failed parsing codeblock tool call: %s (%s)", raw_json, err)

    return calls


def strip_think_markup(text: str) -> str:
    """Remove <think>...</think> reasoning blocks from output."""
    return re.sub(r"<think>[\s\S]*?</think>", "", text).strip()


def strip_tool_call_markup(text: str) -> str:
    """Remove tool call markup and thinking tags so only clean response remains."""
    cleaned = TOOL_CALL_REGEX.sub("", text)
    cleaned = JSON_CODEBLOCK_TOOL_REGEX.sub("", cleaned)
    cleaned = strip_think_markup(cleaned)
    return cleaned.strip()


class ToolCallOrchestrator:
    """Manages the model -> tool -> result -> final answer execution loop."""

    def __init__(
        self,
        router: ModelRouter,
        registry: Optional[ToolRegistry] = None,
        executor: Optional[ToolExecutor] = None,
    ) -> None:
        self.router = router
        self.registry = registry or get_tool_registry()
        self.executor = executor or ToolExecutor(self.registry)
        self.settings = get_settings()

    async def run_tool_loop(
        self,
        *,
        messages: List[NormalizedMessage],
        mode: ConversationMode,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        context: ToolExecutionContext,
        is_disconnected,
    ) -> AsyncIterator[str]:
        """
        Execute iterative tool calling loop:
        1. Inject tool definitions into system prompt.
        2. Stream response from model.
        3. If tool call is requested, execute tool, emit tool SSE events, append result to context.
        4. Repeat until model produces final answer or max iterations reached.
        """
        # Emit available tools event
        tools_catalog = self.registry.get_catalog()
        yield tool_available(tools_catalog)

        # Inject tool system prompt
        tools_prompt = format_tools_system_prompt(self.registry)
        current_messages = list(messages)

        # Prepend or append tools prompt to system message
        if tools_prompt:
            has_system = False
            for idx, msg in enumerate(current_messages):
                if msg.role == MessageRole.SYSTEM:
                    current_messages[idx] = NormalizedMessage(
                        role=MessageRole.SYSTEM,
                        content=f"{msg.content}\n\n{tools_prompt}",
                    )
                    has_system = True
                    break
            if not has_system:
                current_messages.insert(0, NormalizedMessage(role=MessageRole.SYSTEM, content=tools_prompt))

        max_iterations = min(self.settings.max_tool_calls, 5)
        iteration = 0
        latest_selection: Optional[ProviderSelection] = None

        while iteration < max_iterations:
            iteration += 1
            iteration_output: List[str] = []
            has_tool_call = False

            try:
                async for selection, event in self.router.stream(
                    messages=current_messages,
                    mode=mode,
                    provider=provider,
                    model=model,
                ):
                    if latest_selection is None or latest_selection.provider_name != selection.provider_name:
                        latest_selection = selection
                        yield message_start(selection.provider_name, selection.model, mode, selection.fallback_used)

                    if await is_disconnected():
                        return

                    if event.delta:
                        iteration_output.append(event.delta)
            except Exception as stream_err:
                logger.warning("Stream error in tool loop iteration %d: %s", iteration, stream_err)
                # Yield the error as a text response so the user sees something
                yield text_delta(f"I encountered an issue: {stream_err}. Please try again.")
                return

            raw_text = "".join(iteration_output)

            # If the model returned nothing at all, bail out gracefully
            if not raw_text.strip():
                logger.warning("Tool loop iteration %d: model returned empty output, stopping.", iteration)
                yield text_delta("I wasn't able to generate a response. Please try again.")
                return

            tool_calls = parse_tool_calls(raw_text)

            if not tool_calls:
                # No tool call needed -> Stream natural final answer text to client
                clean_text = strip_tool_call_markup(raw_text) or raw_text
                # Yield in chunks for smooth SSE experience
                chunk_size = 32
                for i in range(0, len(clean_text), chunk_size):
                    if await is_disconnected():
                        return
                    yield text_delta(clean_text[i : i + chunk_size])
                return

            # Tool calls detected! Execute each tool sequentially
            tool_responses: List[str] = []
            for tool_name, tool_params in tool_calls:
                if await is_disconnected():
                    return

                # Emit tool started SSE
                yield tool_started(tool_name, tool_params)

                # Execute securely
                result: ToolResult = await self.executor.execute(
                    tool_name=tool_name,
                    arguments=tool_params,
                    context=context,
                )

                if result.success:
                    yield tool_result_event(
                        tool_name=tool_name,
                        success=True,
                        data=result.data,
                        source=result.source,
                    )
                    tool_responses.append(
                        f'<tool_response tool="{tool_name}" status="success">\n{json.dumps(result.data, default=str)}\n</tool_response>'
                    )
                else:
                    yield tool_result_event(
                        tool_name=tool_name,
                        success=False,
                        data=None,
                        error=result.error,
                        source=result.source,
                    )
                    yield tool_error_event(tool_name, result.error or "Execution failed")
                    tool_responses.append(
                        f'<tool_response tool="{tool_name}" status="error">\nError: {result.error}\n</tool_response>'
                    )

            # Append model's tool call and the environment's response to message history.
            # IMPORTANT: Strip ALL tool-call markup from the assistant entry because Gemini
            # rejects <tool_call> XML in an assistant/model turn and returns:
            #   "model output must contain either output text or tool calls, cannot both be empty"
            # After stripping, fall back to a neutral placeholder to guarantee non-empty content.
            clean_assistant_content = strip_tool_call_markup(raw_text).strip()
            if not clean_assistant_content:
                clean_assistant_content = "[Calling tool]"
            current_messages.append(
                NormalizedMessage(
                    role=MessageRole.ASSISTANT,
                    content=clean_assistant_content,
                )
            )
            current_messages.append(
                NormalizedMessage(
                    role=MessageRole.USER,
                    content="\n\n".join(tool_responses) + "\n\nPlease continue your response based on the above tool results.",
                )
            )

        # If iteration limit reached, ask model for a final synthesis
        final_messages = list(current_messages) + [
            NormalizedMessage(
                role=MessageRole.SYSTEM,
                content="Maximum tool calls reached. Provide your final concise answer to the user now without any additional tool calls.",
            )
        ]

        async for selection, event in self.router.stream(
            messages=final_messages,
            mode=mode,
            provider=provider,
            model=model,
        ):
            if await is_disconnected():
                return
            if event.delta:
                yield text_delta(event.delta)
