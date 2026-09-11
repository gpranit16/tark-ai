"""Tool Call Orchestrator for TARK AI. Bounded multi-step tool execution loop."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


def format_tools_system_prompt(
    registry: ToolRegistry,
    allowed_tools: Optional[List[str]] = None,
    has_calendar: bool = False,
    has_github: bool = False,
) -> str:
    """Format tools definition for the system prompt with context-aware tool guidance."""
    tools = registry.list_tools()
    if allowed_tools is not None:
        tools = [t for t in tools if t.name in allowed_tools]

    if not tools:
        if not has_calendar:
            return (
                "## GOOGLE CALENDAR STATUS\n"
                "- Google Calendar is NOT connected for this user.\n"
                "- If the user asks about their schedule, calendar, upcoming meetings, or availability, "
                "clearly explain that Google Calendar is not connected and they can connect it under Settings -> Personal -> Connections.\n"
            )
        return ""

    lines = [
        "## AVAILABLE TOOLS",
        "You have access to the following secure tools to retrieve external information, manage personal schedule, or perform specialized calculations:",
        "",
    ]

    for tool in tools:
        schema = tool.get_schema()
        lines.append(f"### `{tool.name}`")
        lines.append(f"**Description**: {tool.description}")
        lines.append(f"**Parameters (JSON Schema)**: `{json.dumps(schema.get('parameters', {}))}`")
        lines.append("")

    now_utc = datetime.now(timezone.utc)
    local_tz = timezone(timedelta(hours=5, minutes=30))
    now_local = datetime.now(local_tz)
    current_date_str = now_local.strftime("%A, %B %d, %Y")
    current_time_str = now_local.strftime("%I:%M %p")
    tomorrow_date_str = (now_local + timedelta(days=1)).strftime("%A, %B %d, %Y")

    lines.extend([
        "## TEMPORAL CONTEXT & FRESHNESS",
        f"- Current Local Date (Today): {current_date_str} (Time: {current_time_str}, Timezone: Asia/Kolkata +05:30).",
        f"- Tomorrow's Date: {tomorrow_date_str}.",
        f"- Current UTC Time: {now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}.",
        "- When answering questions about latest events, news, or current facts, ALWAYS execute `search_news` or `web_search`.",
        "- Strictly use the verified publication dates, URLs, and source titles returned in the tool response. Do not invent or synthesize past/stale dates.",
        "",
        "## TOOL CALLING INSTRUCTIONS",
        "1. When you need external facts, recent news, calculations, weather, financial prices, or workspace memories/documents, ALWAYS call the appropriate tool.",
    ])

    if has_calendar:
        lines.extend([
            "2. PERSONAL CALENDAR & SCHEDULE INTEGRATION (STRICT GROUNDING):",
            "   - Google Calendar IS connected for this user.",
            "   - CRITICAL ZERO-HALLUCINATION RULE: You do NOT know the user's schedule internally. You are STRICTLY FORBIDDEN from guessing or fabricating sample events (such as 'Team Standup', '1:1 with Manager', 'Design Sync', etc.).",
            "   - When the user asks 'What do I have tomorrow?', 'What is my schedule today?', 'What do I have on my calendar this week?', or asks about their meetings/agenda:",
            "     * You MUST ALWAYS invoke `<tool_call>{\"name\": \"get_calendar_events\", \"arguments\": {\"time_frame\": \"...\"}}</tool_call>` as your immediate action.",
            "   - When the user asks 'Am I free at 5 PM?' or queries availability:",
            "     * You MUST ALWAYS invoke `<tool_call>{\"name\": \"check_calendar_availability\", \"arguments\": {\"target_date\": \"...\", \"start_time\": \"...\"}}</tool_call>`.",
            "   - When the user asks to schedule, create, set up, or add a meeting or calendar event (e.g. 'Schedule a meeting called Client Demo tomorrow from 1 PM to 2 PM', 'Add a calendar event tomorrow at 3 PM'):",
            "     * You MUST ALWAYS invoke `<tool_call>{\"name\": \"create_calendar_event\", \"arguments\": {\"title\": \"Client Demo\", \"start_time\": \"tomorrow at 1 PM\", \"end_time\": \"tomorrow at 2 PM\"}}</tool_call>` as your immediate response.",
            "     * HARD CONSTRAINT: You are STRICTLY FORBIDDEN from outputting confirmation text (such as 'The meeting has been scheduled on your Google Calendar...') without first executing `<tool_call>{\"name\": \"create_calendar_event\", ...}</tool_call>`. Only after receiving the successful tool response can you formulate your final confirmation message.",
            "   - When the user asks to remove, delete, or cancel an event (e.g. 'remove test event', 'delete Client Demo meeting'):",
            "     * You MUST ALWAYS invoke `<tool_call>{\"name\": \"delete_calendar_event\", \"arguments\": {\"title\": \"test event\"}}</tool_call>`.",
            "     * NEVER claim you don't have a tool to delete calendar events when Google Calendar is connected.",
            "   - If `get_calendar_events` returns 0 events (`\"event_count\": 0` or `\"events\": []`), you MUST state clearly: 'You have no events scheduled for [period].' Do NOT provide example or placeholder meetings.",
            "   - NEVER claim that you do not have access to their calendar when Google Calendar is connected.",
        ])
    else:
        lines.extend([
            "2. PERSONAL CALENDAR STATUS:",
            "   - Google Calendar is NOT connected for this user.",
            "   - If the user asks about their calendar, schedule, agenda, or availability, inform them: 'Google Calendar is not connected. You can connect it under Settings -> Personal -> Connections.'",
            "   - DO NOT fabricate or invent any schedule or events.",
        ])

    lines.extend([
        "3. TASKS, REMINDERS & DAILY PLANNING (TARK PERSONAL OS):",
        "   - The user has an integrated Tasks & Reminders manager on TARK AI.",
        "   - When the user asks to add/create a task (e.g. 'Add a task to finish project by Friday', 'Create task: study DBMS for 90 minutes'):",
        "     * You MUST ALWAYS invoke `<tool_call>{\"name\": \"create_task\", \"arguments\": {\"title\": \"...\", \"due_date\": \"...\", \"estimated_duration\": 90}}</tool_call>`.",
        "   - When the user asks 'What are my tasks?', 'Show my pending tasks', 'What is due today?', 'What did I finish this week?':",
        "     * You MUST ALWAYS invoke `<tool_call>{\"name\": \"list_tasks\", \"arguments\": {\"time_frame\": \"...\"}}</tool_call>`.",
        "   - When the user asks to complete or mark done a task (e.g. 'Mark grocery as complete'):",
        "     * You MUST ALWAYS invoke `<tool_call>{\"name\": \"complete_task\", \"arguments\": {\"title\": \"grocery\"}}</tool_call>`.",
        "   - When the user asks to delete or remove a task:",
        "     * You MUST ALWAYS invoke `<tool_call>{\"name\": \"delete_task\", \"arguments\": {\"title\": \"...\"}}</tool_call>`.",
        "   - When the user asks for a reminder (e.g. 'Remind me in 2 minutes to test TARK reminder', 'Remind me tomorrow at 8 PM to pay electricity bill'):",
        "     * You MUST ALWAYS invoke `<tool_call>{\"name\": \"create_reminder\", \"arguments\": {\"title\": \"...\", \"reminder_time\": \"in 2 minutes\"}}</tool_call>`.",
        "     * Pass the user's natural timing directly (such as 'in 2 minutes', 'in 30 mins', 'tomorrow at 8 PM') to `reminder_time`. Do NOT guess or calculate stale past ISO timestamps.",
        "   - When the user asks 'Plan my day' or 'Plan tomorrow around my calendar':",
        "     * You MUST ALWAYS invoke `<tool_call>{\"name\": \"plan_day\", \"arguments\": {\"target_date\": \"today\"}}</tool_call>`.",
        "   - NEVER pretend to create tasks or reminders without invoking the respective tool first.",
    ])

    if has_github:
        lines.extend([
            "4. GITHUB MCP & REPOSITORY INTEGRATION (REAL REPOSITORIES & ACTIONS):",
            "   - GitHub IS connected for this user.",
            "   - You have tools to search repos, read files/code, inspect issues, pull requests, commits, branches, and GitHub Actions.",
            "   - When the user asks to analyze, explain, or inspect a repository structure or what a project does (e.g. 'Analyze my iot-bin repo', 'What does this project do?'):",
            "     * You MUST ALWAYS invoke `<tool_call>{\"name\": \"github_get_file_contents\", \"arguments\": {\"repo\": \"<repo_name>\", \"path\": \"\"}}</tool_call>` as your immediate action to fetch directory tree and files.",
            "   - When the user asks to search repositories, inspect repos, read code/files, check issues/PRs/commits, or check GitHub workflows:",
            "     * You MUST ALWAYS invoke the respective GitHub tool (e.g. `github_search_repositories`, `github_get_file_contents`, `github_list_issues`, `github_list_pull_requests`, `github_list_commits`, `github_list_branches`, `github_list_workflows`).",
            "   - CRITICAL SAFETY CONFIRMATION ON WRITE/DESTRUCTIVE ACTIONS:",
            "     * All write operations (`github_create_or_update_file`, `github_delete_file`, `github_create_issue`, `github_add_issue_comment`, `github_create_pull_request`, `github_merge_pull_request`, `github_create_branch`, `github_dispatch_workflow`, `github_create_repository`) REQUIRE explicit user confirmation.",
            "     * When you execute a write tool without 'confirmed': true, the tool will return a `requires_confirmation` response.",
            "     * When you receive `requires_confirmation`, summarize the proposed changes to the user and ASK for their explicit approval.",
            "     * ONLY when the user explicitly approves, re-execute the tool with 'confirmed': true.",
            "   - ZERO-HALLUCINATION RULE: Never guess repository contents, file SHA, branches, or issue numbers without querying GitHub.",
        ])
    else:
        lines.extend([
            "4. GITHUB MCP STATUS:",
            "   - GitHub is NOT connected for this user.",
            "   - If the user asks about GitHub repositories, issues, PRs, or code files, inform them: 'GitHub is not connected. You can configure your GITHUB_PERSONAL_ACCESS_TOKEN in .env or connect under Settings -> Personal -> Connections.'",
        ])

    lines.extend([
        "5. To invoke a tool, output ONLY a single `<tool_call>` block containing a valid JSON object with `name` and `arguments` (or `parameters`).",
        "Do NOT include introductory conversational text (such as 'Let me fetch...', 'Sure, checking...') before or after the `<tool_call>` block.",
        "Example:",
        "<tool_call>",
        '{"name": "web_search", "arguments": {"query": "latest developments in AI"}}',
        "</tool_call>",
        "",
        "6. You will receive the tool result in a `<tool_response>` block. Use that data to formulate a comprehensive, helpful, and accurate response.",
        "7. If NO tool is required (or for standard document QA / conversational questions), answer the user query directly without using any `<tool_call>` tags.",
        "",
        "## OUTPUT FORMATTING GUIDELINES",
        "- Present search results, news, calendar agendas, and GitHub repository/code data cleanly using crisp headings, concise bullet points, and clickable markdown links where applicable.",
        "- Avoid gigantic, awkwardly wide raw tables that clip horizontal screens unless explicitly requested by the user.",
        "- Keep responses clean, elegant, and easy to read.",
        "",
    ])

    return "\n".join(lines)


def _clean_tool_params(params: Any) -> Dict[str, Any]:
    """Unwrap nested parameter dicts that some models like NVIDIA/Qwen wrap inside 'parameters' or 'arguments'."""
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except Exception:
            return {"query": params}
    if not isinstance(params, dict):
        return {}

    depth = 0
    while depth < 5:
        depth += 1
        if len(params) == 1:
            key = next(iter(params.keys()))
            if key in ("parameters", "arguments", "params", "properties", "input") and isinstance(params[key], dict):
                params = params[key]
                continue
        break

    if "parameters" in params and isinstance(params["parameters"], dict):
        nested = params.pop("parameters")
        params = {**nested, **params}
    if "arguments" in params and isinstance(params["arguments"], dict):
        nested = params.pop("arguments")
        params = {**nested, **params}

    return params


def parse_tool_calls(text: str) -> List[Tuple[str, Dict[str, Any]]]:
    """Extract tool calls from model output supporting standard JSON, Qwen ChatML, XML, and Codeblock formats."""
    calls: List[Tuple[str, Dict[str, Any]]] = []

    # 1. Qwen format: <tool_call> <function=web_search> {"query": ...} </tool_call>
    qwen_fn_matches = re.findall(
        r"<tool_call>\s*<function=([a-zA-Z0-9_\-]+)>\s*([\s\S]*?)(?:</function>)?\s*</tool_call>",
        text,
        re.IGNORECASE,
    )
    for fn_name, raw_content in qwen_fn_matches:
        fn_name = fn_name.strip()
        raw_content = raw_content.strip()
        json_match = re.search(r"({[\s\S]*})", raw_content)
        if json_match:
            try:
                params = json.loads(json_match.group(1))
                if isinstance(params, dict):
                    params = _clean_tool_params(params)
                    calls.append((fn_name, params))
                    continue
            except Exception as err:
                logger.debug("Failed parsing Qwen JSON params: %s (%s)", raw_content, err)

        param_tags = re.findall(r"<parameter=([a-zA-Z0-9_\-]+)>\s*([\s\S]*?)\s*</parameter>", raw_content, re.IGNORECASE)
        if param_tags:
            params = {k.strip(): v.strip() for k, v in param_tags}
            calls.append((fn_name, params))
            continue

        if raw_content:
            calls.append((fn_name, {"query": raw_content}))

    if calls:
        return calls

    # 2. General <tool_call> ... (</tool_call>|<tool_call>|$) blocks
    tc_blocks = re.findall(r"<tool_call>\s*([\s\S]*?)(?:</tool_call>|(?=<tool_call>)|\Z)", text, re.IGNORECASE)
    for block in tc_blocks:
        block = block.strip()
        if not block:
            continue
        # Sub-check for <function=name>
        fn_match = re.search(r"<function=([a-zA-Z0-9_\-]+)>\s*([\s\S]*)", block, re.IGNORECASE)
        if fn_match:
            fn_name = fn_match.group(1).strip()
            rest = fn_match.group(2).strip()
            rest = re.sub(r"</function>$", "", rest, flags=re.IGNORECASE).strip()
            json_match = re.search(r"({[\s\S]*})", rest)
            if json_match:
                try:
                    params = json.loads(json_match.group(1))
                    if isinstance(params, dict):
                        params = _clean_tool_params(params)
                        calls.append((fn_name, params))
                        continue
                except Exception:
                    pass

        json_match = re.search(r"({[\s\S]*})", block)
        if json_match:
            try:
                parsed = json.loads(json_match.group(1))
                name = parsed.get("name") or parsed.get("tool") or parsed.get("function")
                params = parsed.get("parameters") or parsed.get("params") or parsed.get("arguments")
                if params is None:
                    params = {k: v for k, v in parsed.items() if k not in ("name", "tool", "function")}
                params = _clean_tool_params(params)
                if name and not any(c[0] == name for c in calls):
                    calls.append((name, params))
            except Exception as err:
                logger.debug("Failed parsing tool_call JSON: %s (%s)", block, err)

    # 3. Bare JSON tool call fallback (e.g. Nemotron outputting {"name": "...", "arguments": ...})
    if not calls:
        start_indices = [i for i, ch in enumerate(text) if ch == "{"]
        for start in start_indices:
            if start >= len(text) or text[start] != "{":
                continue
            depth = 0
            in_str = False
            escape = False
            for end in range(start, len(text)):
                ch = text[end]
                if escape:
                    escape = False
                    continue
                if ch == "\\":
                    escape = True
                    continue
                if ch == '"':
                    in_str = not in_str
                    continue
                if not in_str:
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            candidate = text[start : end + 1]
                            try:
                                parsed = json.loads(candidate)
                                if isinstance(parsed, dict) and (parsed.get("name") or parsed.get("tool") or parsed.get("function")):
                                    name = parsed.get("name") or parsed.get("tool") or parsed.get("function")
                                    params = parsed.get("parameters") or parsed.get("params") or parsed.get("arguments") or {}
                                    if isinstance(params, dict):
                                        params = _clean_tool_params(params)
                                        if name and not any(c[0] == name for c in calls):
                                            calls.append((name, params))
                            except Exception:
                                pass
                            break

    return calls


    # 3. <function_call> ... </function_call>
    fc_blocks = re.findall(r"<function_call>\s*([\s\S]*?)\s*</function_call>", text, re.IGNORECASE)
    for block in fc_blocks:
        json_match = re.search(r"({[\s\S]*})", block)
        if json_match:
            try:
                parsed = json.loads(json_match.group(1))
                name = parsed.get("name") or parsed.get("tool") or parsed.get("function")
                params = parsed.get("parameters") or parsed.get("params") or parsed.get("arguments") or {}
                params = _clean_tool_params(params)
                if name:
                    calls.append((name, params))
            except Exception:
                pass

    if calls:
        return calls

    # 4. JSON codeblocks ```json ... ```
    cb_matches = JSON_CODEBLOCK_TOOL_REGEX.findall(text)
    for raw_json in cb_matches:
        try:
            parsed = json.loads(raw_json)
            name = parsed.get("name") or parsed.get("tool") or parsed.get("function")
            params = parsed.get("parameters") or parsed.get("params") or parsed.get("arguments")
            if params is None:
                params = {k: v for k, v in parsed.items() if k not in ("name", "tool", "function")}
            params = _clean_tool_params(params)
            if name:
                calls.append((name, params))
        except Exception as err:
            logger.debug("Failed parsing codeblock tool call: %s (%s)", raw_json, err)

    if calls:
        return calls

    # 5. Bare JSON objects without tags: {"name": "search_news", "arguments": ...}
    start_indices = [i for i, ch in enumerate(text) if ch == "{"]
    for start in start_indices:
        depth = 0
        in_str = False
        escape = False
        for end in range(start, len(text)):
            ch = text[end]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if not in_str:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = text[start : end + 1]
                        try:
                            parsed = json.loads(candidate)
                            if isinstance(parsed, dict):
                                name = parsed.get("name") or parsed.get("tool") or parsed.get("function")
                                if name and isinstance(name, str):
                                    params = parsed.get("parameters") or parsed.get("params") or parsed.get("arguments")
                                    if params is None:
                                        params = {k: v for k, v in parsed.items() if k not in ("name", "tool", "function")}
                                    params = _clean_tool_params(params)
                                    calls.append((name, params))
                        except Exception:
                            pass
                        break

    return calls


def strip_think_markup(text: str) -> str:
    """Remove <think>...</think> reasoning blocks, markdown thinking headers, and internal reasoning from output."""
    cleaned = re.sub(r"<think>[\s\S]*?(?:</think>|\Z)", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"(?i)(?:Here'?s a thinking process:?|Thinking Process:?|Thought Process:?)[\s\S]*?(?=(?:\n\n(?:\*{0,2}[A-Z0-9#\-`]))|\Z)",
        "",
        cleaned,
    )
    return cleaned.strip()


def strip_tool_call_markup(text: str) -> str:
    """Remove all tool call markup, XML tags, bare tool JSONs, and thinking tags so only clean response remains."""
    cleaned = re.sub(r"<tool_call>[\s\S]*?(?:</tool_call>|(?=<tool_call>)|\Z)", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"<function_call>[\s\S]*?(?:</function_call>|(?=<function_call>)|\Z)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<function=[^>]+>[\s\S]*?(?:</function>|(?=<function=)|\Z)", "", cleaned, flags=re.IGNORECASE)
    cleaned = JSON_CODEBLOCK_TOOL_REGEX.sub("", cleaned)
    cleaned = strip_think_markup(cleaned)

    # Strip any bare tool call JSON blocks with balanced braces
    start_indices = [i for i, ch in enumerate(cleaned) if ch == "{"]
    for start in reversed(start_indices):
        if start >= len(cleaned) or cleaned[start] != "{":
            continue
        depth = 0
        in_str = False
        escape = False
        for end in range(start, len(cleaned)):
            ch = cleaned[end]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if not in_str:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = cleaned[start : end + 1]
                        try:
                            parsed = json.loads(candidate)
                            if isinstance(parsed, dict) and (parsed.get("name") or parsed.get("tool") or parsed.get("function")):
                                cleaned = cleaned[:start] + cleaned[end + 1 :]
                        except Exception:
                            pass
                        break

    cleaned = re.sub(r"</?(?:tool_call|function_call|function|parameter)[^>]*>", "", cleaned, flags=re.IGNORECASE)
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
        1. Resolve authenticated user's integration status (e.g. Google Calendar).
        2. Filter allowed tools and inject tailored instructions into system prompt.
        3. Stream response from model.
        4. If tool call is requested, execute tool, emit tool SSE events, append result to context.
        5. Repeat until model produces final answer or max iterations reached.
        """
        # Determine user integration status for personal tools (e.g. Google Calendar)
        has_calendar = False
        can_write_calendar = False
        if context.session is not None and context.user_id is not None:
            try:
                from sqlalchemy import select
                from app.models.integration import UserIntegration

                stmt = select(UserIntegration).where(
                    UserIntegration.user_id == context.user_id,
                    UserIntegration.provider == "google",
                    UserIntegration.service == "calendar",
                    UserIntegration.is_active == True,
                )
                res = await context.session.execute(stmt)
                integration = res.scalars().first()
                if integration is not None:
                    has_calendar = True
                    can_write_calendar = bool(
                        integration.scopes
                        and any("calendar.events" in str(s) for s in integration.scopes)
                    )

            except Exception as integ_err:
                logger.warning("Failed to query user integrations in tool loop: %s", integ_err)

        # Determine GitHub MCP integration status
        has_github = False
        try:
            from app.services.integrations.github import get_github_service
            gh_service = get_github_service()
            gh_token = await gh_service.get_token_for_user(user_id=context.user_id, session=context.session)
            if gh_token:
                has_github = True
        except Exception as gh_err:
            logger.warning("Failed checking GitHub status in tool loop: %s", gh_err)

        # Build allowed tools list
        all_registered = [t.name for t in self.registry.list_tools()]
        calendar_tool_names = {
            "get_calendar_events",
            "check_calendar_availability",
            "create_calendar_event",
            "delete_calendar_event",
        }
        github_tool_names = {t for t in all_registered if t.startswith("github_")}

        allowed_tools = list(all_registered)
        if not has_calendar:
            allowed_tools = [t for t in allowed_tools if t not in calendar_tool_names]
        if not has_github:
            allowed_tools = [t for t in allowed_tools if t not in github_tool_names]

        # Safe diagnostic logging (Never logs tokens or credentials)
        user_prefix = str(context.user_id)[:8] + "..." if context.user_id else "anonymous"
        logger.info(
            "ToolLoop initialized: user=%s, model=%s, has_calendar=%s, has_github=%s, tools_count=%d",
            user_prefix,
            model or "default",
            has_calendar,
            has_github,
            len(allowed_tools),
        )

        # Emit available tools event filtered for this user
        tools_catalog = [t for t in self.registry.get_catalog() if t.get("name") in allowed_tools]
        yield tool_available(tools_catalog)

        # Inject tool system prompt
        tools_prompt = format_tools_system_prompt(
            self.registry,
            allowed_tools=allowed_tools,
            has_calendar=has_calendar,
            has_github=has_github,
        )
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
                # No tool call needed -> final answer reached
                clean_text = strip_tool_call_markup(raw_text) or raw_text
                if clean_text:
                    yield text_delta(clean_text)
                return

            # Tool calls detected! Execute each tool sequentially
            tool_responses: List[str] = []
            for tool_name, tool_params in tool_calls:
                if await is_disconnected():
                    return

                logger.info(
                    "ToolLoop executing tool: %s (params: %s)",
                    tool_name,
                    list(tool_params.keys()) if isinstance(tool_params, dict) else "unknown",
                )

                # Emit tool started SSE
                yield tool_started(tool_name, tool_params)

                # Execute securely
                result: ToolResult = await self.executor.execute(
                    tool_name=tool_name,
                    arguments=tool_params,
                    context=context,
                )

                if result.success:
                    logger.info("ToolLoop tool %s succeeded", tool_name)
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
                    logger.warning("ToolLoop tool %s failed: %s", tool_name, result.error)
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

            # Append model's raw tool call output to dialogue history
            current_messages.append(
                NormalizedMessage(
                    role=MessageRole.ASSISTANT,
                    content=raw_text.strip(),
                )
            )

            # Strip heavy tools schema from system message for subsequent synthesis passes
            # to save ~3500 tokens, staying well below Groq TPM rate limits for ultra-fast generation
            if current_messages and current_messages[0].role == MessageRole.SYSTEM:
                sys_content = current_messages[0].content
                if "## AVAILABLE TOOLS" in sys_content:
                    clean_sys = sys_content.split("## AVAILABLE TOOLS")[0].strip()
                    if not clean_sys:
                        clean_sys = "You are TARK AI. Synthesize the final concise and direct response based on the tool results provided below."
                    current_messages[0] = NormalizedMessage(role=MessageRole.SYSTEM, content=clean_sys)

            synthesis_directive = (
                "\n\n[STRICT SYNTHESIS DIRECTIVE]:\n"
                "- Provide your final response in clean, user-friendly markdown.\n"
                "- Do NOT output any `<tool_call>` tags, JSON tool objects, or XML tool markup.\n"
                "- Base your response ONLY on the factual data returned in the tool response above.\n"
                "- If listing items (repositories, tasks, calendar events, search results, issues, PRs): Format cleanly with bullet points, names, status, and concise details.\n"
                "- If event_count or item count is 0 or empty: State clearly that there are no items found.\n"
                "- If requires_confirmation is present: Clearly summarize the proposed write action and ask the user for explicit confirmation before proceeding."
            )

            current_messages.append(
                NormalizedMessage(
                    role=MessageRole.USER,
                    content="\n\n".join(tool_responses) + synthesis_directive,
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
