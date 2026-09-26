"""Tool Call Orchestrator for TARK AI. Bounded multi-step tool execution loop."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
import re
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
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
    github_username: Optional[str] = None,
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
        "- When answering questions about latest events, news, or current facts, ALWAYS execute `web_search` or `search_news`.",
        "- Strictly use the verified publication dates, URLs, and source titles returned in the tool response. Do not invent or synthesize past/stale dates.",
        "",
        "## TOOL CALLING INSTRUCTIONS",
        "1. LIVE WEB SEARCH & REAL-TIME FACT GROUNDING (TAVILY):",
        "   - You have access to real-time live web search powered by Tavily AI via `web_search`.",
        "   - When the user asks you to search, or asks about current facts, latest news, recent models/software releases (e.g. OpenAI models, Claude, Gemini, Apple, etc.):",
        "     * You MUST ALWAYS invoke `<tool_call>{\"name\": \"web_search\", \"arguments\": {\"query\": \"<concise search query>\"}}</tool_call>` as your immediate response.",
        "     * Use clean, keyword-focused queries (e.g. 'latest OpenAI model released official announcement', not raw conversational sentences).",
        "   - CRITICAL ZERO-LEAKAGE RULE: When invoking a tool, your entire response MUST be ONLY the `<tool_call>...</tool_call>` block without conversational fluff.",
        "   - SYNTHESIS & FACT VERIFICATION (CHATGPT STYLE):",
        "     * Deliver clear, direct, and concise answers immediately from the search findings.",
        "     * Summarize the latest releases and facts in clean bullet points or a short table with markdown source links: `[Source Name](URL)`.",
        "     * DO NOT engage in meta-commentary, self-deprecating apologies about earlier turns, or repetitive disclaimers. Answer directly like ChatGPT.",
        "   - NEVER claim that you do not have internet access or live web access — you DO have access via `web_search`.",
        "",
        "2. OTHER TOOLS & CALCULATIONS:",
        "   - When you need calculations, weather, financial prices, or workspace memories/documents, ALWAYS call the appropriate tool.",
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
        user_mention = f" (Authenticated GitHub Account: @{github_username})" if github_username else ""
        lines.extend([
            "4. GITHUB MCP & REPOSITORY INTEGRATION (REAL REPOSITORIES & ACTIONS):",
            f"   - GitHub IS connected for this user{user_mention}.",
            "   - You have access to tools for repositories, files, issues, pull requests, commits, branches, and GitHub Actions.",
            "   - LISTING USER REPOSITORIES:",
            "     * When the user asks 'What are my repositories?', 'Show my repos', 'List my repositories', 'What repos do I have on GitHub?', or asks in Hindi/Hinglish (e.g. 'mere repos kya hai', 'mere repo dikhao', 'mere repositories'):",
            "       You MUST ALWAYS invoke `<tool_call>{\"name\": \"github_list_user_repositories\", \"arguments\": {}}</tool_call>` as your immediate action.",
            "     * DO NOT call `github_get_repository` with generic words like 'repositories' or 'repos'.",
            "     * DO NOT ask the user for their username or token, because their GitHub account is ALREADY connected!",
            "   - FILE READING & CREATING/UPDATING FILES ON GITHUB:",
            "     * When the user asks to read, inspect, or show a file (e.g. 'Show README.md of iot-bin', 'Read package.json in smarrtbin'):",
            "       Invoke `<tool_call>{\"name\": \"github_get_file_contents\", \"arguments\": {\"repo\": \"<repo_name>\", \"path\": \"<file_path>\"}}</tool_call>`.",
            "     * When the user asks to update, edit, modify, add lines to, or create a file in a GitHub repo (e.g. 'Update README.md of iot-bin', 'Add line to README', 'Commit and push changes', 'Push update', 'repo me README create/update karo'):",
            "       You MUST invoke `github_create_or_update_file` directly! DO NOT call `web_search` and DO NOT just provide text instructions on how to use git terminal.",
            "       Step 1: Execute `<tool_call>{\"name\": \"github_create_or_update_file\", \"arguments\": {\"repo\": \"<repo_name>\", \"path\": \"<file_path>\", \"content\": \"<new_or_updated_content>\", \"message\": \"<commit_message>\"}}</tool_call>`. (Leave confirmed=false).",
            "       Step 2: When the tool returns `requires_confirmation`, summarize the proposed changes clearly to the user and ask for their confirmation.",
            "       Step 3: When the user confirms (e.g. 'yes', 'do it', 'you only commit and do', 'push it', 'proceed'), execute `<tool_call>{\"name\": \"github_create_or_update_file\", \"arguments\": {\"repo\": \"<repo_name>\", \"path\": \"<file_path>\", \"content\": \"<new_or_updated_content>\", \"message\": \"<commit_message>\", \"confirmed\": true}}</tool_call>`.",
            "     * NEVER claim you cannot push, commit, or update files on GitHub — you DO have full write and commit access via `github_create_or_update_file`!",
            "   - STRICT ROUTING BOUNDARY (ZERO FALSE INVOCATIONS):",
            "     * ONLY call GitHub tools when the user specifically requests interactions with a real GitHub repository, issue, PR, commit, branch, or workflow.",
            "     * STRICT PROHIBITION: You are STRICTLY FORBIDDEN from calling GitHub tools for general programming questions, writing code snippets, explaining algorithms, or debugging code. Answer those directly in the chat with markdown code blocks!",
            "     * NEVER call `github_search_repositories` unless the user explicitly asks to search/find repositories on GitHub.",
            "   - REPOSITORY INSPECTION:",
            "     * When the user asks to analyze, explain, or inspect a repository structure (e.g. 'Analyze my iot-bin repo', 'What files are in pallets/flask?'):",
            "       Invoke `<tool_call>{\"name\": \"github_get_file_contents\", \"arguments\": {\"repo\": \"<repo_name>\", \"path\": \"\"}}</tool_call>`.",
            "   - CRITICAL SAFETY CONFIRMATION ON WRITE/DESTRUCTIVE ACTIONS:",
            "     * All write operations (`github_create_or_update_file`, `github_delete_file`, `github_create_issue`, `github_add_issue_comment`, `github_create_pull_request`, `github_merge_pull_request`, `github_create_branch`, `github_dispatch_workflow`, `github_create_repository`) REQUIRE explicit user confirmation.",
            "     * When you execute a write tool without 'confirmed': true, the tool will return a `requires_confirmation` response.",
            "     * When you receive `requires_confirmation`, summarize the proposed changes to the user and ASK for their explicit approval. Stop calling tools in that turn.",
            "     * ONLY when the user explicitly approves in a subsequent message, re-execute the tool with 'confirmed': true.",
            "   - ZERO-HALLUCINATION & ANTI-LOOP RULE:",
            "     * Never guess repository contents, file SHA, branches, or issue numbers without querying GitHub.",
            "     * If a repository or file is not found (404), STOP calling tools immediately and inform the user. Do NOT retry or make repeated calls in a loop.",
        ])
    else:
        lines.extend([
            "4. GITHUB MCP STATUS:",
            "   - GitHub is NOT connected for this user.",
            "   - If the user asks to perform GitHub operations on repositories, issues, PRs, or code files, inform them: 'GitHub is not connected. You can configure your GITHUB_PERSONAL_ACCESS_TOKEN in .env or connect under Settings -> Personal -> Connections.'",
        ])

    lines.extend([
        "## KNOWLEDGE & CONTEXT HIERARCHY (STRICT DETERMINISTIC PRECEDENCE)",
        "1. CURRENT CONVERSATION HISTORY (Highest Priority):",
        "   - The messages above in this active thread represent the ground truth for this conversation.",
        "   - If the user mentioned a fact earlier in this chat session (such as what they ate, their plans, location, name, schedule details, thoughts, or statements):",
        "     * YOU MUST ALWAYS ANSWER DIRECTLY from the conversation history.",
        "     * STRICT PROHIBITION: You are STRICTLY FORBIDDEN from calling `search_user_memory` or `search_knowledge_base` when the information is already present in this conversation thread.",
        "     * Example: If user previously said 'I ate mango today' and now asks 'What did I eat?', reply directly 'You ate a mango today!' with ZERO tool calls.",
        "     * Example: If user previously said 'My exam is on Monday' and asks 'When is my exam?', reply directly 'Your exam is on Monday.' with ZERO tool calls.",
        "",
        "2. USER DECLARATIONS vs MEMORY QUERIES (ZERO FALSE SEARCHES):",
        "   - When the user tells you about themselves, their role, status, or preferences (e.g. 'I am a third year CS student', 'I live in Delhi', 'My goal is to learn Rust'):",
        "     * THIS IS A DECLARATION / INTRODUCTION, NOT A DATABASE SEARCH QUERY.",
        "     * STRICT PROHIBITION: You are STRICTLY FORBIDDEN from calling `search_user_memory` or `search_knowledge_base` to 'look up' what the user just declared!",
        "     * Acknowledge warmly and converse directly (e.g. 'Got it! As a 3rd-year CSE student, I can assist you with DSA, system design, web dev, and project building. What are you working on today?').",
        "   - ONLY invoke `search_user_memory` when the user asks a retrospective recall question about previously saved information (e.g. 'What is my saved address?', 'What did I save earlier?') and the information is NOT in the current thread.",
        "",
        "3. LONG-TERM USER MEMORY (`search_user_memory`):",
        "   - ONLY call `search_user_memory` if the user is explicitly asking about facts saved from past sessions or if the fact is completely missing from this active thread.",
        "   - If `search_user_memory` returns no items or empty count, NEVER contradict yourself by saying you found it. Trust the empty result.",
        "",
        "4. ASSISTANT IDENTITY & RUNTIME MODEL INFO:",
        "   - You are TARK AI (TA513), a smart luxury personal AI assistant.",
        "   - When asked 'What is your model?', 'What model are you using?', 'What is your model name?', 'Who are you?', answer directly that you are TARK AI (TA513) powered by modern high-performance AI models without calling `search_knowledge_base`, `search_user_memory`, or document retrieval tools.",
        "",
        "5. STRICT TOOL CALL SYNTAX & ZERO LEAKAGE:",
        "   - When you need to call a tool, your ENTIRE output MUST be ONLY the `<tool_call>{\"name\": \"...\", \"arguments\": {...}}</tool_call>` block.",
        "   - NEVER write conversational commentary or introductory questions before or after the `<tool_call>` block in the same turn.",
        "",
        "## OUTPUT FORMATTING GUIDELINES",
        "- Present search results, news, calendar agendas, and GitHub repository/code data cleanly using crisp headings, concise bullet points, and clickable markdown links where applicable.",
        "- Avoid gigantic, awkwardly wide raw tables that clip horizontal screens unless explicitly requested by the user.",
        "- Keep responses clean, elegant, friendly, and easy to read.",
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
    if "input" in params and isinstance(params["input"], dict):
        nested = params.pop("input")
        params = {**nested, **params}

    return params


KNOWN_CORE_TOOLS = {
    "calculator", "web_search", "read_url", "get_weather", "convert_currency", "search_news",
    "get_stock_price", "get_crypto_price", "search_knowledge_base", "search_user_memory",
    "search_conversation_history", "get_calendar_events", "check_calendar_availability",
    "create_calendar_event", "delete_calendar_event", "create_task", "list_tasks",
    "update_task", "complete_task", "delete_task", "create_reminder", "list_reminders", "plan_day",
}


def is_valid_tool_name(name: Any, registry: Optional[ToolRegistry] = None) -> bool:
    """Validate that candidate tool name is an actual registered tool or valid alias, not conversational text."""
    if not name or not isinstance(name, str):
        return False
    name = name.strip()
    if not re.match(r"^[a-zA-Z0-9_\-]{2,64}$", name):
        return False
    lower_name = name.lower()
    if lower_name in KNOWN_CORE_TOOLS or lower_name.startswith("github_"):
        return True
    try:
        from app.tools.registry import TOOL_NAME_ALIASES, get_tool_registry
        canonical = TOOL_NAME_ALIASES.get(lower_name, lower_name)
        if canonical in KNOWN_CORE_TOOLS:
            return True
        reg = registry or get_tool_registry()
        if reg.has_tool(canonical) or canonical.startswith("github_"):
            return True
    except Exception:
        pass
    return False


def parse_tool_calls(text: str) -> List[Tuple[str, Dict[str, Any]]]:
    """Extract tool calls from model output supporting standard JSON, Qwen ChatML, XML, Codeblock, and NL intent formats."""
    calls: List[Tuple[str, Dict[str, Any]]] = []

    # 1. Qwen format: <tool_call> <function=web_search> {"query": ...} </tool_call>
    qwen_fn_matches = re.findall(
        r"<tool_call>\s*<function=([a-zA-Z0-9_\-]+)>\s*([\s\S]*?)(?:</function>)?\s*</tool_call>",
        text,
        re.IGNORECASE,
    )
    for fn_name, raw_content in qwen_fn_matches:
        fn_name = fn_name.strip()
        if not is_valid_tool_name(fn_name):
            continue
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
            if is_valid_tool_name(fn_name):
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
                if is_valid_tool_name(name):
                    params = parsed.get("parameters") or parsed.get("params") or parsed.get("arguments") or parsed.get("input")
                    if params is None:
                        params = {k: v for k, v in parsed.items() if k not in ("name", "tool", "function")}
                    params = _clean_tool_params(params)
                    if name and not any(c[0] == name for c in calls):
                        calls.append((name, params))
            except Exception as err:
                logger.debug("Failed parsing tool_call JSON: %s (%s)", block, err)

    if calls:
        return calls

    # 3. <function_call> ... </function_call>
    fc_blocks = re.findall(r"<function_call>\s*([\s\S]*?)\s*</function_call>", text, re.IGNORECASE)
    for block in fc_blocks:
        json_match = re.search(r"({[\s\S]*})", block)
        if json_match:
            try:
                parsed = json.loads(json_match.group(1))
                name = parsed.get("name") or parsed.get("tool") or parsed.get("function")
                if is_valid_tool_name(name):
                    params = parsed.get("parameters") or parsed.get("params") or parsed.get("arguments") or {}
                    params = _clean_tool_params(params)
                    if name and not any(c[0] == name for c in calls):
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
            if is_valid_tool_name(name):
                params = parsed.get("parameters") or parsed.get("params") or parsed.get("arguments")
                if params is None:
                    params = {k: v for k, v in parsed.items() if k not in ("name", "tool", "function")}
                params = _clean_tool_params(params)
                if name and not any(c[0] == name for c in calls):
                    calls.append((name, params))
        except Exception as err:
            logger.debug("Failed parsing codeblock tool call: %s (%s)", raw_json, err)

    if calls:
        return calls

    # 5. Bare JSON objects without tags: {"name": "web_search", "arguments": ...}
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
                                if is_valid_tool_name(name):
                                    params = parsed.get("parameters") or parsed.get("params") or parsed.get("arguments") or {}
                                    if isinstance(params, dict):
                                        params = _clean_tool_params(params)
                                        if name and not any(c[0] == name for c in calls):
                                            calls.append((name, params))
                        except Exception:
                            pass
                        break

    if calls:
        return calls

    # 6. Natural Language Search Intent Rescue:
    # When models talk in 3rd person or output natural intent instead of tags
    # e.g. "The user is asking about an AI model named 'Astra'... I need to search the live web to find out what AI model 'Astra' is."
    nl_match = re.search(
        r"(?:i\s+(?:need\s+to|should|must|will)\s+search(?:\s+(?:the\s+)?(?:live\s+)?web|\s+online)?\s+(?:to\s+find\s+out|for)?|let\s+me\s+search(?:\s+(?:the\s+)?(?:live\s+)?web|\s+online)?\s+for)\s+([^\.\n]+)",
        text,
        re.IGNORECASE,
    )
    if nl_match:
        raw_target = nl_match.group(1).strip().strip("'\"`")
        target = re.sub(r"^(?:what|who|which)\s+", "", raw_target, flags=re.IGNORECASE)
        target = re.sub(r"\s+is\s*$", "", target, flags=re.IGNORECASE).strip()
        target = target.strip("'\"` ")
        if target and len(target) >= 2:
            logger.info("Rescued natural language web search intent from model output: %r", target)
            calls.append(("web_search", {"query": target}))

    return calls


def strip_think_markup(text: str, strip_whitespace: bool = False) -> str:
    """Remove <think>...</think> reasoning blocks, markdown thinking headers, and internal reasoning from output."""
    cleaned = re.sub(r"<think>[\s\S]*?(?:</think>|\Z)", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"(?i)(?:Here'?s a thinking process:?|Thinking Process:?|Thought Process:?)[\s\S]*?(?=(?:\n\n(?:\*{0,2}[A-Z0-9#\-`]))|\Z)",
        "",
        cleaned,
    )
    # Suppress third-person scratchpad leakage (e.g. "The user is asking about an AI model...")
    cleaned = re.sub(
        r"(?i)(?:The user is asking|The user wants to|I need to search the (?:live )?web|I will search the (?:live )?web)[\s\S]*?(?=(?:\n\n)|\Z)",
        "",
        cleaned,
    )
    return cleaned.strip() if strip_whitespace else cleaned


def strip_tool_call_markup(text: str, strip_whitespace: bool = False) -> str:
    """Remove all tool call markup, XML tags, bare tool JSONs, and thinking tags so only clean response remains."""
    cleaned = re.sub(r"(?:Tool call:\s*)?`*<tool_call>[\s\S]*?</tool_call>`*", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"(?:Tool call:\s*)?`*<tool_call>[\s\S]*?(?:</tool_call>|(?=<tool_call>)|\Z)`*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(?:Tool call:\s*)?`*<function_call>[\s\S]*?</function_call>`*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(?:Tool call:\s*)?`*<function_call>[\s\S]*?(?:</function_call>|(?=<function_call>)|\Z)`*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(?:Tool call:\s*)?`*<function=[^>]+>[\s\S]*?(?:</function>|(?=<function=)|\Z)`*", "", cleaned, flags=re.IGNORECASE)
    cleaned = JSON_CODEBLOCK_TOOL_REGEX.sub("", cleaned)
    cleaned = strip_think_markup(cleaned, strip_whitespace=strip_whitespace)

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
    cleaned = re.sub(r"(?:\bTool call:\s*)+$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\s*(?:Tool call:\s*)+", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip() if strip_whitespace else cleaned



# ── Conversational intent classifier ──────────────────────────────────────────
# Patterns that indicate the user just wants a direct conversational reply with
# no external data fetching needed.  Keep this list conservative so we never
# accidentally skip tools the user really needs.
import re as _re

_CONVERSATIONAL_PATTERNS = _re.compile(
    r"^\s*(?:"
    r"hi+[!?\s]*"
    r"|hello+[!?\s]*"
    r"|hey+[!?\s]*"
    r"|howdy[!?\s]*"
    r"|good\s+(?:morning|afternoon|evening|night)[!?\s]*"
    r"|thanks?(?:\s+you)?[!?\s]*"
    r"|thank\s+you[!?\s]*"
    r"|what\s+(?:can|do)\s+you\s+do[?!\s]*"
    r"|what\s+are\s+your\s+(?:capabilities|features|skills)[?!\s]*"
    r"|who\s+are\s+you[?!\s]*"
    r"|what\s+are\s+you[?!\s]*"
    r"|what(?:'s| is)\s+(?:your\s+)?(?:name|model)[?!\s]*"
    r"|how\s+are\s+you[?!\s]*"
    r"|are\s+you\s+(?:there|ready|ok|alive)[?!\s]*"
    r"|help[!?\s]*"
    r"|(?:can|could)\s+you\s+help\s+(?:me)?[?!\s]*"
    r"|what\s+(?:can|could)\s+i\s+(?:ask|do)[?!\s]*"
    r")\s*$",
    _re.IGNORECASE,
)


def is_conversational_query(content: str) -> bool:
    """Return True when the user message is clearly a greeting or capability
    question that needs no external tool calls at all.

    Keeps the check conservative: a false-negative (missing a conversational
    message) only means the tool loop runs unnecessarily; a false-positive
    (skipping tools that were needed) would break real requests.
    """
    stripped = content.strip()
    # Reject immediately if the message contains URL, code, or is long
    if len(stripped) > 120:
        return False
    if any(ch in stripped for ch in ("```", "http", "github.com", "@")):
        return False
    return bool(_CONVERSATIONAL_PATTERNS.match(stripped))


_PRONOUN_PATTERN = _re.compile(
    r"\b(he|she|it|they|his|her|its|their|him|them|ye|yeh|wo|woh|iska|iske|iski|unka|inke)\b",
    _re.IGNORECASE,
)

KNOWN_TECH_ENTITIES = {
    "astra", "project astra", "sora", "o1", "o1-mini", "o3", "o3-mini", "o4",
    "gpt-4o", "gpt-4.5", "gpt-5", "claude", "gemini", "deepseek", "perplexity",
    "midjourney", "flux", "runway", "elevenlabs", "cursor", "windsurf", "devin",
    "grok", "llama", "mistral", "qwen", "chatgpt", "copilot"
}

_SEARCH_SUFFIX_PATTERN = _re.compile(
    r"\s+(?:search\s+latest|search\s+now|search\s+online|search\s+karo|search\s+kro|khojo|google\s+karo|search\s+karke\s+batao|search\s+pe|online\s+search|find\s+online|on\s+the\s+web|search)\s*$",
    _re.IGNORECASE,
)

_SEARCH_PREFIX_PATTERN = _re.compile(
    r"^(?:please\s+)?(?:web\s+)?(?:search\s+(?:the\s+web\s+for|the\s+internet\s+for|online\s+for|for|about|pe)?|google\s+(?:for|about)?|look\s+up\s+(?:for|about)?|find\s+(?:out\s+about)?)\s*",
    _re.IGNORECASE,
)


def extract_primary_subject_from_history(messages: Optional[List[NormalizedMessage]]) -> str:
    """Extract the primary named entity or subject from recent conversation messages."""
    if not messages:
        return ""

    for msg in reversed(messages[-6:]):
        content = (msg.content or "").strip()
        if not content:
            continue

        # 1. Hindi/Hinglish entity inquiry e.g. "astra kya tha fir", "sora kya hai"
        m_hi = _re.search(
            r"\b([A-Za-z0-9\.\-_]{2,30})\s+(?:kya\s+tha(?:\s+fir)?|kya\s+hai|kiske\s+liye\s+hai|kab\s+aaya|kab\s+release|kab\s+launch|kisne\s+banaya|ke\s+baare\s+me)\b",
            content,
            _re.IGNORECASE,
        )
        if m_hi:
            subj = m_hi.group(1).strip()
            if subj.lower() not in {"ye", "yeh", "wo", "woh", "kya", "batao", "this", "that"}:
                return subj

        # 2. User questions like "who is <Subject>" or "tell me about <Subject>"
        m = _re.search(
            r"\b(?:who\s+is|what\s+is|tell\s+me\s+about|know\s+about)\s+([A-Za-z0-9\s\.\-]{2,40})",
            content,
            _re.IGNORECASE,
        )
        if m:
            subj = m.group(1).strip()
            subj = _re.sub(r"[\?\.\,\!\;]+$", "", subj).strip()
            subj = _re.sub(r"^(?:the|a|an)\s+", "", subj, flags=_re.IGNORECASE).strip()
            if subj and len(subj) > 2 and subj.lower() not in {"this", "that", "it", "he", "she"}:
                return subj

        # 3. Known tech entities in content
        for entity in KNOWN_TECH_ENTITIES:
            if _re.search(r"\b" + _re.escape(entity) + r"\b", content, _re.IGNORECASE):
                return entity.title()

        # 4. Quoted terms
        m_q = _re.search(r"['\"]([A-Za-z0-9\s\.\-_]{2,30})['\"]", content)
        if m_q:
            return m_q.group(1).strip()

        # 5. Assistant message opening, e.g. "Virat Kohli is an Indian..."
        if msg.role == MessageRole.ASSISTANT:
            m_cap = _re.search(r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", content)
            if m_cap:
                return m_cap.group(1).strip()

        # 6. Capitalized proper nouns
        proper_nouns = _re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b", content)
        for pn in proper_nouns:
            if len(pn) > 2 and pn.lower() not in {"google calendar", "google news", "tark ai", "duckduckgo", "united states", "the", "what", "when", "how", "here", "there"}:
                return pn.strip()

    return ""


def contextualize_search_query(
    raw_query: str,
    messages: Optional[List[NormalizedMessage]] = None,
) -> str:
    """Clean search directives and resolve pronouns from conversation history."""
    query = raw_query.strip()
    if not query:
        return ""

    # 1. Strip leading and trailing search meta-commands
    query = _SEARCH_PREFIX_PATTERN.sub("", query).strip()
    query = _SEARCH_SUFFIX_PATTERN.sub("", query).strip()

    # Strip Hinglish inspection and critique directives (e.g. "hng se dekh", "dhang se dekh", "bhai dekh")
    hinglish_prefixes = [
        r"^\s*(?:bhai\s+)?(?:please\s+)?(?:dhang|dhng|hng|ache|acche|sahi|theek|dobara|fir\s+se)\s+se\s+dekh(?:iye|o)?\s*",
        r"^\s*(?:bhai\s+)?(?:dekh|dekho|check\s+karo|check\s+kr|khojo|dhundho)\s*",
        r"^\s*(?:ye|yeh)\s+",
    ]
    for hp in hinglish_prefixes:
        query = _re.sub(hp, "", query, flags=_re.IGNORECASE).strip()

    # Normalize common tech terms & drop conversational Hinglish filler
    query = _re.sub(r"\bopen\s+ai\b", "OpenAI", query, flags=_re.IGNORECASE)
    query = _re.sub(r"\bdevloper\b", "developer", query, flags=_re.IGNORECASE)
    query = _re.sub(r"\b(?:kiska\s+hai|kiske\s+liye\s+hai|ke\s+baare\s+me)\b", " ", query, flags=_re.IGNORECASE)
    query = _re.sub(r"\b(?:hai|tha|thi|h)\b", " ", query, flags=_re.IGNORECASE)
    query = _re.sub(r"\b(?:bhai|yaar|please)\b", " ", query, flags=_re.IGNORECASE)
    query = " ".join(query.split()).strip()

    # Strip question filler like "what are", "what is", "can you tell me"
    query = _re.sub(
        r"^(?:what\s+are\s+|what\s+is\s+|can\s+you\s+tell\s+me\s+|tell\s+me\s+|how\s+many\s+)",
        "",
        query,
        flags=_re.IGNORECASE,
    ).strip()
    query = _re.sub(
        r"\s+(?:kya\s+tha(?:\s+fir)?|kya\s+hai|kiske\s+liye\s+hai|kab\s+aaya|kab\s+release|kab\s+launch|kisne\s+banaya|ke\s+baare\s+me|batao|bata)\s*$",
        "",
        query,
        flags=_re.IGNORECASE,
    ).strip()
    query = query.rstrip("?").strip()

    # 2. Check if query contains pronouns or is a dependent fragment
    has_pronouns = bool(_PRONOUN_PATTERN.search(query))
    is_fragment = (
        len(query.split()) <= 4
        and any(
            w in query.lower()
            for w in [
                "model", "ai", "tool", "app", "price", "founder", "features", "release", "details",
                "centuries", "runs", "stats", "age", "height", "wife",
                "records", "ceo", "net worth", "score", "matches", "family", "born"
            ]
        )
    )

    if (has_pronouns or is_fragment) and messages:
        subject = extract_primary_subject_from_history(messages)
        if subject:
            if has_pronouns:
                query = _PRONOUN_PATTERN.sub(subject, query)
                query = _re.sub(r"\bhai\b", "", query, flags=_re.IGNORECASE).strip()
                if "model" in query.lower() and "ai" not in query.lower():
                    query = f"{query} AI"
            elif is_fragment:
                query = f"{subject} {query}"

    # If query is a single known entity without qualifiers (e.g. "astra"), qualify it
    q_lower = query.lower()
    if q_lower in {"astra", "project astra"}:
        query = "Google Project Astra AI model"
    elif q_lower in KNOWN_TECH_ENTITIES and "model" not in q_lower and "ai" not in q_lower:
        query = f"{query} AI model"

    return query.strip() or raw_query.strip()


def detect_github_intent(
    content: str,
    messages: Optional[List[NormalizedMessage]] = None,
) -> bool:
    """Accurately identify if the user's query requires GitHub tool interactions.

    Returns False for general coding questions, algorithms, conceptual git questions,
    and conversational chit-chat to prevent unnecessary tool pollution and infinite loops.
    """
    stripped = content.strip()
    if not stripped:
        return False

    lower = stripped.lower()

    # 1. Quick exclusion for greetings and conversational chit-chat
    if is_conversational_query(stripped):
        return False

    # 2. Strong exclusion for general code generation, algorithms, and debugging
    general_coding_patterns = [
        r"^(?:please\s+)?write\s+(?:a\s+|some\s+)?(?:python|javascript|typescript|c\+\+|java|rust|go|react|html|css|sql|bash|code|script|function|program|class)\b",
        r"^(?:please\s+)?how\s+to\s+(?:code|implement|build|use|write)\b",
        r"^(?:please\s+)?create\s+(?:a\s+)?(?:component|function|class|script|program)\b",
        r"^(?:please\s+)?implement\s+(?:a\s+|an\s+)?(?:algorithm|function|class|method)\b",
        r"^(?:please\s+)?(?:explain|what\s+is|how\s+does)\s+(?:git\s+rebase|git\s+merge|git\s+commit|git\s+push|git\s+pull|git\s+branch)\b",
        r"^(?:please\s+)?solve\s+(?:this\s+)?(?:leetcode|problem|equation|bug|issue\s+in\s+my\s+code)\b",
        r"^(?:please\s+)?debug\s+(?:this|my\s+code)\b",
    ]
    is_general_coding = any(_re.search(pat, lower) for pat in general_coding_patterns)
    if is_general_coding and not any(k in lower for k in ("github", "github.com", "gh repo")):
        return False

    # 3. Direct GitHub intent indicators
    if any(k in lower for k in ("github", "github.com", "gh repo")):
        return True

    # Hindi / Hinglish intent indicators
    hinglish_github_indicators = [
        "mera repo", "mere repo", "meri repo", "mera repos", "mere repos", "meri repos",
        "meri repository", "mere repositories", "mera repository", "mere repository",
        "repo dikhao", "repos dikhao", "repos batao", "repo batao",
        "repos list", "repo list", "github pe", "github par",
        "commit karo", "push karo", "repo me update", "file update karo",
    ]
    if any(k in lower for k in hinglish_github_indicators):
        return True

    # Shorthand repository references like "owner/repo" combined with repo actions
    has_owner_repo = bool(_re.search(r"\b[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+\b", stripped))
    repo_actions = [
        "repo", "repository", "issue", "issues", "pr", "prs", "pull request",
        "pull requests", "commit", "commits", "branch", "branches", "workflow", "workflows",
        "readme", "clone", "update", "push", "write", "modify",
    ]
    if has_owner_repo and any(act in lower for act in repo_actions):
        return True

    # Flexible regex patterns for repository actions and queries
    repo_action_regexes = [
        r"\b(?:create|open|add|file|list|get|show|close|update|edit|write|push|modify|commit|delete|remove)\s+(?:an?\s+)?(?:issue|pr|pull\s+request|branch|commit|workflow|file|readme|line)\b",
        r"\b(?:update|edit|modify|create|write)\s+(?:the\s+)?(?:readme|file|code)\b",
        r"\b(?:push|commit)\s+(?:the\s+)?(?:changes?|code|update|file|commits?)\b",
        r"\b(?:commit|push)\s+(?:and\s+)?(?:do|update|push)\b",
        r"\b(?:merge|close)\s+(?:the\s+|this\s+)?(?:pr|pull\s+request)\b",
        r"\b(?:repo|repository)\s+[A-Za-z0-9_.\-]+\b",
        r"\b[A-Za-z0-9_.\-]+\s+(?:repo|repository)\b",
        r"\b(?:what|show|list|get|display|view|fetch)\s+(?:are\s+)?(?:all\s+)?(?:the\s+)?(?:my\s+)?repos(?:itories)?\b",
        r"\b(?:my\s+repos?|my\s+repositories|search\s+repos?|search\s+repositories|list\s+repos?|list\s+repositories|create\s+repo|create\s+repository)\b",
        r"\b(?:dispatch|trigger|run)\s+(?:a\s+|the\s+)?(?:workflow|action|actions|ci)\b",
        r"\b(?:workflow\s+runs?|workflow\s+status|github\s+actions?)\b",
        r"\b(?:files?\s+in\s+(?:the\s+)?repo|repo\s+files?|repo\s+structure|repository\s+structure)\b",
        r"\b[\w\-.]+\.(?:json|md|py|js|ts|html|yml|yaml|env|toml|txt)\s+(?:of|in|from)\s+[A-Za-z0-9_.\-]+\b",
        r"\b(?:show|view|get|read|open|cat)\s+[\w\-.]+\.(?:json|md|py|js|ts|html|yml|yaml|env|toml)\b",
        r"\b(?:commits?\s+(?:on|in)|branches?\s+(?:in|of))\b",
    ]
    if any(_re.search(pat, lower) for pat in repo_action_regexes):
        return True

    # 4. Multi-turn context check: Follow-up questions referencing recent GitHub interaction
    if messages:
        recent_has_github = False
        for msg in reversed(messages[-6:]):
            c = (msg.content or "").lower()
            if any(marker in c for marker in [
                "github", "github.com", "tool=\"github_", "name\": \"github_",
                "repo", "repository", "commit", "push", "branch", "pr", "pull request", "issue", "iot-bin", "readme"
            ]):
                recent_has_github = True
                break

        if recent_has_github:
            follow_up_tokens = [
                "issues", "issue", "prs", "pr", "pull request", "pull requests",
                "commits", "commit", "branches", "branch", "workflows", "files",
                "readme", "structure", "merge", "open one", "create one", "details",
                "update", "edit", "write", "push", "change", "modify", "save", "add",
                "yes", "ha", "haan", "sure", "proceed", "confirm", "approve", "do it",
                "kardo", "commit and do", "push and update", "from here", "please do", "only commit",
            ]
            if any(tok in lower for tok in follow_up_tokens) or len(stripped.split()) <= 5:
                return True

    return False


def detect_web_search_intent(
    content: str,
    web_search_flag: bool = False,
    messages: Optional[List[NormalizedMessage]] = None,
) -> Tuple[bool, str]:
    """Detect if a query requires or explicitly requests live web search.
    
    Returns (should_search: bool, clean_search_query: str).
    """
    stripped = content.strip()
    if not stripped:
        return False, ""

    # 1. Explicit Web Search button enabled or [Web Search Enabled] tag
    if web_search_flag or "[web search enabled]" in stripped.lower():
        clean = _re.sub(
            r"\[web search enabled\](?:\s*please\s+search\s+the\s+web\s+for\s+(?:the\s+)?latest\s+information\s+about:?)?",
            "",
            stripped,
            flags=_re.IGNORECASE,
        ).strip()
        cleaned_query = contextualize_search_query(clean or stripped, messages)
        return True, cleaned_query or clean or stripped

    # 2. Explicit search commands (English and Hinglish)
    explicit_patterns = [
        r"^(?:please\s+)?(?:web\s+)?search\s+(?:the\s+web\s+for|the\s+internet\s+for|online\s+for|for|about|tavily\s+for)?\s+(.+)$",
        r"^(?:please\s+)?(?:google|tavily|bing|ddg)\s+(?:search\s+)?(?:for\s+|about\s+)?(.+)$",
        r"^(?:please\s+)?look\s+up\s+(?:on\s+(?:the\s+)?web\s+)?(.+?)(?:\s+on\s+(?:the\s+)?web|\s+online)?$",
        r"^(?:please\s+)?find\s+(?:online|on\s+the\s+web)\s+(.+)$",
        r"^(?:search\s+karo|search\s+kro|khojo|google\s+karo|web\s+pe\s+search\s+karo|internet\s+pe\s+search\s+karo)\s+(.+)$",
        r"^(.+?)\s+(?:search\s+karo|search\s+kro|khojo|search\s+karke\s+batao|google\s+karo|web\s+pe\s+search\s+karo|search\s+latest|latest\s+search|search\s+online|online\s+search)$",
    ]

    for pat in explicit_patterns:
        m = _re.match(pat, stripped, flags=_re.IGNORECASE)
        if m:
            q = m.group(1).strip()
            q = _re.sub(r"^(?:about|for|regarding)\s+", "", q, flags=_re.IGNORECASE).strip()
            if q:
                cleaned_query = contextualize_search_query(q, messages)
                return True, cleaned_query or q

    # 3. Guardrails: Exclude queries clearly meant for internal tools, GitHub operations, coding, math, or greetings
    lower = stripped.lower()
    if is_conversational_query(stripped):
        return False, ""
    if detect_github_intent(stripped, messages=messages):
        return False, ""
    if any(lower.startswith(p) for p in [
        "write code", "write a python", "write a script", "create a function",
        "def ", "class ", "how to code", "solve ", "calculate ", "plot ", "implement "
    ]):
        return False, ""
    if any(p in lower for p in [
        "my schedule", "my calendar", "add task", "create task", "my tasks",
        "what did i eat", "remind me", "check calendar"
    ]):
        return False, ""

    # 4. Implicit intent - Real-world freshness, live facts, and recent developments
    freshness_indicators = [
        r"\b(latest|recent|today'?s?|yesterday'?s?|breaking|now|this\s+week|this\s+month|new\s+release|update|updates|announcement|2025|2026)\b",
        r"\b(who\s+is\s+(?:the\s+)?(?:current|new|present)\b|who\s+won\b|current\s+(?:price|status|ceo|prime\s+minister|president)|stock\s+price|crypto\s+price|weather\s+in|match\s+score|election\s+result|release\s+date\s+of)\b",
        r"\b(astra|project\s+astra|sora|o1|o1-mini|o3|o3-mini|o4|gpt-4o|gpt-4\.5|gpt-5|claude\s*3(?:\.5|\.7)?|gemini\s*(?:1\.5|2|2\.5|3)?|deepseek(?:\s*v3|\s*r1)?|qwen\s*2\.5|llama\s*3\.[123]|rtx\s*50\d0|starship\s*flight|artemis|perplexity|midjourney|elevenlabs|cursor|windsurf|devin|grok)\b",
    ]

    for pat in freshness_indicators:
        if _re.search(pat, lower):
            cleaned_query = contextualize_search_query(stripped, messages)
            return True, cleaned_query or stripped

    # 5. Hindi/Hinglish entity inquiry patterns (e.g. "astra kya tha fir", "sora kya hai", "o3 ke baare me")
    hinglish_inquiry_patterns = [
        r"\b([a-zA-Z0-9_\-\.]{2,30})\s+(?:kya\s+tha(?:\s+fir)?|kya\s+hai|kiske\s+liye\s+hai|kab\s+aaya|kab\s+release|kab\s+launch|kisne\s+banaya|ke\s+baare\s+me|batao|bata)\b",
        r"\b(?:kya\s+tha|kya\s+hai|batao|bata)\s+([a-zA-Z0-9_\-\.]{2,30})\b",
    ]
    for pat in hinglish_inquiry_patterns:
        m = _re.search(pat, stripped, flags=_re.IGNORECASE)
        if m:
            entity = m.group(1).strip()
            if entity.lower() not in {"ye", "yeh", "wo", "woh", "kya", "this", "that", "it", "code", "file", "repo", "task"}:
                cleaned_query = contextualize_search_query(stripped, messages)
                return True, cleaned_query or f"{entity} AI model overview"

    # 6. Multi-turn follow-ups & pronoun clarifications (e.g. "ye model hai", "details batao", "who made it")
    follow_up_tokens = [
        "model hai", "ye model", "ai model", "tool hai", "app hai", "who made",
        "when was", "details batao", "kab aaya", "kiska hai", "kis company",
    ]
    is_follow_up = any(tok in lower for tok in follow_up_tokens) or (
        len(stripped.split()) <= 4 and bool(_PRONOUN_PATTERN.search(lower))
    )
    if is_follow_up and messages:
        subject = extract_primary_subject_from_history(messages)
        if subject:
            cleaned_query = contextualize_search_query(stripped, messages)
            return True, cleaned_query or f"{subject} AI model"

    # 7. Hindi/Hinglish search directives & entity release verification triggers
    hinglish_search_triggers = [
        r"\b(?:dhang|dhng|hng|ache|acche|sahi|theek|dobara|fir\s+se)\s+se\s+dekh\b",
        r"\b(?:dekh\s+ye|check\s+karo|check\s+kr|dhundho|khojo)\b",
        r"\b(?:open\s*ai|openai|anthropic|google|meta|microsoft|deepseek|apple)\b.*\b(?:release|released|launch|launched|developer|model|api|announced)\b",
        r"\b(?:release|released|launch|launched)\s+(?:in|on)\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)\b",
        r"\b(?:galat\s+hai|wrong\s+hai|glt\s+pe\s+glt|glt\s+result|galt\s+result|ye\s+nahi\s+hai)\b",
    ]
    for pat in hinglish_search_triggers:
        if _re.search(pat, lower):
            cleaned_query = contextualize_search_query(stripped, messages)
            return True, cleaned_query or stripped

    return False, ""


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
        web_search: bool = False,
    ) -> AsyncIterator[str]:
        """
        Execute iterative tool calling loop:
        1. Resolve authenticated user's integration status (e.g. Google Calendar).
        2. Filter allowed tools and inject tailored instructions into system prompt.
        3. Stream response from model.
        4. If tool call is requested, execute tool, emit tool SSE events, append result to context.
        5. Repeat until model produces final answer or max iterations reached.
        """
        last_user_content = ""
        for msg in reversed(messages):
            if msg.role == MessageRole.USER:
                last_user_content = msg.content or ""
                break

        # Check for web search intent (button enabled, explicit search command, or live fact query)
        should_web_search, search_query = detect_web_search_intent(
            last_user_content,
            web_search_flag=web_search,
            messages=messages,
        )

        # Fast-path for pure conversational messages (only if web search was not triggered)
        if not should_web_search and is_conversational_query(last_user_content):
            logger.info("ToolLoop fast-path: conversational query detected, skipping tool infrastructure")
            latest_sel = None
            async for selection, event in self.router.stream(
                messages=messages,
                mode=mode,
                provider=provider,
                model=model,
            ):
                if latest_sel is None:
                    latest_sel = selection
                    yield message_start(selection.provider_name, selection.model, mode, selection.fallback_used)
                if await is_disconnected():
                    return
                if event.delta:
                    yield text_delta(event.delta)
            return

        # Direct Web Search execution path when intent / button / command was detected
        if should_web_search and search_query:
            logger.info("ToolLoop proactive web search triggered for: %r", search_query[:60])
            tools_catalog = [t for t in self.registry.get_catalog() if t.get("name") == "web_search"]
            if tools_catalog:
                yield tool_available(tools_catalog)

            yield tool_started("web_search", {"query": search_query})

            search_result: ToolResult = await self.executor.execute(
                tool_name="web_search",
                arguments={"query": search_query},
                context=context,
            )

            yield tool_result_event(
                tool_name="web_search",
                success=search_result.success,
                data=search_result.data,
                source=search_result.source or "tavily",
            )

            if not search_result.success:
                yield tool_error_event("web_search", search_result.error or "Search execution failed")

            tool_resp_str = (
                f'<tool_response tool="web_search" status="{"success" if search_result.success else "error"}">\n'
                f'{json.dumps(search_result.data, default=str)}\n'
                f'</tool_response>'
            )

            synthesis_directive = (
                "\n\n[STRICT SYNTHESIS DIRECTIVE - WEB SEARCH]:\n"
                "- Answer the user's question directly, clearly, and comprehensively using the search results.\n"
                "- Provide an accurate, well-structured answer in clean markdown with key details, release dates, and facts highlighted.\n"
                "- Cite verified sources using clickable markdown links in the format [Source Title](URL).\n"
                "- FACTUAL ACCURACY ON OPENAI & AI MODELS:\n"
                "  * Clarify verified releases: OpenAI o1 series (o1-preview, o1-mini released on September 12, 2024 for developers and ChatGPT Plus/Team users; first reasoning models), GPT-4o (May 2024), OpenAI DevDay developer conferences (held in September/October with Realtime API, prompt caching, vision fine-tuning), Whisper (September 2022), and ChatGPT (November 2022).\n"
                "  * If search snippets mention speculative future predictions or simulated timelines (such as 'Sol/Terra tiers', 'GPT-5.6', or fan trackers), distinguish them clearly from verified official releases.\n"
                "  * Note that Project Astra is Google DeepMind's real-time multimodal AI assistant, NOT an OpenAI model.\n"
                "- NO INTERNAL DEBATES OR APOLOGY ESSAYS: Answer directly, objectively, and politely like ChatGPT without arguing about earlier turns or apologizing.\n"
                "- CRITICAL: Never refuse to answer with statements like 'I was unable to find any information' or merely provide external links when the question is about well-known public figures, tech releases, historical events, or established facts.\n"
                "- Do NOT output any `<tool_call>` tags, JSON tool objects, or XML tool markup.\n"
                "- Keep the tone helpful, objective, crisp, and well-structured."
            )

            cur_messages = list(messages)
            # Clean any [Web Search Enabled] prefix in user messages
            for idx in range(len(cur_messages) - 1, -1, -1):
                if cur_messages[idx].role == MessageRole.USER:
                    cleaned_u = _re.sub(
                        r"\[web search enabled\](?:\s*please\s+search\s+the\s+web\s+for\s+(?:the\s+)?latest\s+information\s+about:?)?",
                        "",
                        cur_messages[idx].content,
                        flags=_re.IGNORECASE,
                    ).strip()
                    if cleaned_u:
                        cur_messages[idx] = NormalizedMessage(role=MessageRole.USER, content=cleaned_u)
                    break

            cur_messages.append(
                NormalizedMessage(
                    role=MessageRole.USER,
                    content=f"{tool_resp_str}{synthesis_directive}",
                )
            )

            latest_sel = None
            async for selection, event in self.router.stream(
                messages=cur_messages,
                mode=mode,
                provider=provider,
                model=model,
            ):
                if latest_sel is None:
                    latest_sel = selection
                    yield message_start(selection.provider_name, selection.model, mode, selection.fallback_used)
                if await is_disconnected():
                    return
                if event.delta:
                    yield text_delta(event.delta)
            return

        # Determine user integration status for personal tools (e.g. Google Calendar)
        has_calendar = False
        can_write_calendar = False
        if context.session is not None and context.user_id is not None:
            try:
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
        github_username = None
        try:
            from app.services.integrations.github import get_github_service
            gh_service = get_github_service()
            gh_token = await gh_service.get_token_for_user(user_id=context.user_id, session=context.session)
            if gh_token:
                has_github = True
                status = await gh_service.get_status(user_id=context.user_id, session=context.session)
                github_username = status.get("account_login")
        except Exception as gh_err:
            logger.warning("Failed checking GitHub status in tool loop: %s", gh_err)

        # Check if current turn or thread context requires GitHub tools
        is_github_relevant = detect_github_intent(last_user_content, messages=messages)

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
        if not has_github or not is_github_relevant:
            allowed_tools = [t for t in allowed_tools if t not in github_tool_names]
        elif is_github_relevant and not web_search and not any(w in last_user_content.lower() for w in ["search the web", "google", "live search"]):
            # When performing dedicated GitHub operations, exclude web search tools to focus the model on GitHub MCP
            allowed_tools = [t for t in allowed_tools if t not in {"web_search", "search_news"}]

        # Safe diagnostic logging (Never logs tokens or credentials)
        user_prefix = str(context.user_id)[:8] + "..." if context.user_id else "anonymous"
        logger.info(
            "ToolLoop initialized: user=%s, model=%s, has_calendar=%s, has_github=%s, gh_user=%s, tools_count=%d",
            user_prefix,
            model or "default",
            has_calendar,
            has_github,
            github_username,
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
            github_username=github_username,
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
        executed_tool_calls: set[tuple[str, str]] = set()
        github_calls_count = 0

        # Pre-compute tool name tuple once — used inside the inner streaming loop.
        # Previously recomputed on every token delta (O(n_tools) per chunk).
        _dynamic_tool_names = tuple(t.name for t in self.registry.list_tools())
        _tool_indicators = (
            "<tool_call",
            "<function",
            "<function_call",
            "Tool call:",
            "Tool call",
            "Tool Call:",
            "`<tool_call",
            "```json",
            '{"name"',
            '{"tool"',
            '{"function"',
            '{"arguments"',
            '{"parameters"',
            *_dynamic_tool_names,
        )

        while iteration < max_iterations:
            iteration += 1
            iteration_output: List[str] = []
            stream_buffer = ""
            in_think_block = False
            is_tool_call_detected = False
            streamed_any = False

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

                        # If tool call has already been detected, don't stream anything to user
                        if is_tool_call_detected:
                            continue

                        stream_buffer += event.delta

                        while stream_buffer:
                            # 1. Handle <think>...</think> blocks
                            if in_think_block:
                                if "</think>" in stream_buffer:
                                    _, _, after_think = stream_buffer.partition("</think>")
                                    stream_buffer = after_think
                                    in_think_block = False
                                    continue
                                else:
                                    # Whole buffer is within think block; swallow it
                                    stream_buffer = ""
                                    break
                            else:
                                if "<think>" in stream_buffer:
                                    before_think, _, after_think = stream_buffer.partition("<think>")
                                    in_think_block = True
                                    stream_buffer = after_think
                                    if before_think:
                                        yield text_delta(before_think)
                                        streamed_any = True
                                    continue

                                # 2. Check for partial <think> tag at tail of stream_buffer
                                has_partial_think = any(
                                    stream_buffer.endswith("<think>"[:i])
                                    for i in range(1, len("<think>"))
                                )
                                if has_partial_think and len(stream_buffer) <= len("<think>"):
                                    break

                                # 3. Check for tool call markers anywhere in stream_buffer
                                tool_call_pattern = re.search(
                                    r"(?i)(?:Tool call:\s*)?`*<(?:tool_call|function_call|function)\b|```(?:json)?\s*\{\s*\"(?:tool|name|function)\"|(?:\bTool call:\s*)",
                                    stream_buffer,
                                )
                                if tool_call_pattern:
                                    # Safely yield any clean text that appeared BEFORE the tool call
                                    pre_text = stream_buffer[:tool_call_pattern.start()]
                                    clean_pre = strip_tool_call_markup(pre_text, strip_whitespace=False)
                                    if clean_pre:
                                        yield text_delta(clean_pre)
                                        streamed_any = True
                                    is_tool_call_detected = True
                                    stream_buffer = ""
                                    break

                                stripped_buf = stream_buffer.lstrip()
                                is_tool_start = any(stripped_buf.startswith(ind) for ind in _tool_indicators) or bool(
                                    re.search(r'["\']?(?:name|tool|function)["\']?\s*:', stripped_buf)
                                )
                                is_potential_tool = any(
                                    ind.startswith(stripped_buf) or stripped_buf.startswith(ind)
                                    for ind in _tool_indicators
                                )

                                if is_tool_start:
                                    is_tool_call_detected = True
                                    stream_buffer = ""
                                    break
                                elif is_potential_tool and len(stripped_buf) < 20 and "\n" not in stripped_buf:
                                    # Wait for more tokens to be certain whether it is a tool call
                                    break

                                # 4. Suppress untagged markdown thinking process or 3rd-person scratchpads (e.g. "The user is asking...", "I need to search...")
                                if re.match(r"^\s*(?:Here'?s a thinking process:?|Thinking Process:?|Thought Process:?|The user is asking|The user wants to|I need to search|I should search|Let me search|I will search|In order to answer)", stream_buffer, re.IGNORECASE):
                                    if "\n\n" in stream_buffer:
                                        _, _, stream_buffer = stream_buffer.partition("\n\n")
                                        continue
                                    else:
                                        break

                                # 5. Safe to emit text! Check if buffer ends with a potential <think> prefix to hold back
                                hold_len = 0
                                for i in range(1, len("<think>")):
                                    if stream_buffer.endswith("<think>"[:i]):
                                        hold_len = i
                                        break

                                if hold_len > 0:
                                    to_yield = stream_buffer[:-hold_len]
                                    stream_buffer = stream_buffer[-hold_len:]
                                else:
                                    to_yield = stream_buffer
                                    stream_buffer = ""

                                if to_yield:
                                    yield text_delta(to_yield)
                                    streamed_any = True

            except Exception as stream_err:
                logger.warning("Stream error in tool loop iteration %d: %s", iteration, stream_err)
                yield text_delta(f"I encountered an issue: {stream_err}. Please try again.")
                return

            # Flush any remaining buffer if not in think block or tool call
            if stream_buffer and not in_think_block and not is_tool_call_detected:
                clean_tail = strip_tool_call_markup(stream_buffer, strip_whitespace=False)
                if clean_tail:
                    yield text_delta(clean_tail)
                    streamed_any = True

            raw_text = "".join(iteration_output)

            # If the model returned nothing at all, bail out gracefully
            if not raw_text.strip():
                logger.warning("Tool loop iteration %d: model returned empty output, stopping.", iteration)
                yield text_delta("I wasn't able to generate a response. Please try again.")
                return

            tool_calls = parse_tool_calls(raw_text)

            if not tool_calls:
                # No tool call needed -> final answer reached
                if not streamed_any:
                    clean_text = strip_tool_call_markup(raw_text, strip_whitespace=True)
                    if clean_text:
                        yield text_delta(clean_text)
                    else:
                        logger.warning("Tool loop iteration %d: model produced unparsable tool markup with no plain text; providing safe fallback.", iteration)
                return

            # Tool calls detected! Execute each tool sequentially with loop & duplicate protection
            tool_responses: List[str] = []
            break_after_this_turn = False

            for tool_name, tool_params in tool_calls:
                if await is_disconnected():
                    return

                # Duplicate tool call detection (Loop Breaker)
                canonical_param_str = json.dumps(tool_params, sort_keys=True, default=str)
                call_sig = (tool_name, canonical_param_str)
                if call_sig in executed_tool_calls:
                    logger.warning("ToolLoop: Duplicate tool call prevented: %s", tool_name)
                    break_after_this_turn = True
                    tool_responses.append(
                        f'<tool_response tool="{tool_name}" status="error">\nError: Duplicate tool call. This exact tool call was already executed this turn. Stop calling tools and provide your final answer to the user.\n</tool_response>'
                    )
                    continue
                executed_tool_calls.add(call_sig)

                if tool_name.startswith("github_"):
                    github_calls_count += 1
                    if github_calls_count >= 2:
                        break_after_this_turn = True

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
                    # If this write tool requires user confirmation, stop loop immediately
                    if isinstance(result.data, dict) and result.data.get("status") == "requires_confirmation":
                        break_after_this_turn = True
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
                    # Check for terminal errors where repeating is futile
                    err_lower = str(result.error or "").lower()
                    if any(term in err_lower for term in [
                        "not connected",
                        "authentication required",
                        "authentication failed",
                        "bad credentials",
                        "rate limit exceeded",
                        "permission denied",
                        "resource not found",
                        "could not be retrieved",
                        "must be provided",
                        "not found",
                    ]):
                        break_after_this_turn = True

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
                "- Ground your response in the factual data returned in the tool response above. If the tool is web_search or news and results are limited, supplement with accurate knowledge to directly answer the user's question rather than refusing.\n"
                "- If listing items (repositories, tasks, calendar events, search results, issues, PRs): Format cleanly with bullet points, names, status, and concise details.\n"
                "- If requires_confirmation is present: Clearly summarize the proposed write action and ask the user for explicit confirmation before proceeding.\n"
                "- If a tool returned an error (such as repository not found or not connected): Explain the issue clearly and politely with helpful advice (e.g. check spelling or connect under Settings)."
            )

            current_messages.append(
                NormalizedMessage(
                    role=MessageRole.USER,
                    content="\n\n".join(tool_responses) + synthesis_directive,
                )
            )

            # If a terminal error or safety confirmation was triggered, break immediately to final synthesis!
            if break_after_this_turn:
                logger.info("ToolLoop break_after_this_turn triggered. Emitting final synthesis directly.")
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
                        yield text_delta(event.delta)
                return

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
