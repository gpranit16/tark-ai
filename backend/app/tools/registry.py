from typing import Any

from app.tools.base import BaseTool


TOOL_ALIASES: dict[str, str] = {
    "search": "web_search",
    "websearch": "web_search",
    "search_web": "web_search",
    "google_search": "web_search",
    "bing_search": "web_search",
    "internet_search": "web_search",
    "news": "news_search",
    "search_news": "news_search",
    "get_news": "news_search",
    "get_weather": "weather",
    "weather_search": "weather",
    "calculate": "calculator",
    "calc": "calculator",
    "math": "calculator",
    "stock": "stock_price",
    "get_stock": "stock_price",
    "get_stock_price": "stock_price",
    "crypto": "crypto_price",
    "get_crypto": "crypto_price",
    "get_crypto_price": "crypto_price",
    "currency": "currency_conversion",
    "convert_currency": "currency_conversion",
    "fetch_url": "url_reader",
    "read_url": "url_reader",
    "web_reader": "url_reader",
    "memory": "memory_search",
    "search_memories": "memory_search",
    "knowledge": "knowledge_search",
    "search_knowledge": "knowledge_search",
    "conversation": "conversation_search",
    "chat_search": "conversation_search",
    "calendar": "get_calendar_events",
    "calendar_events": "get_calendar_events",
    "get_calendar": "get_calendar_events",
    "get_events": "get_calendar_events",
    "list_events": "get_calendar_events",
    "google_calendar": "get_calendar_events",
    "check_availability": "check_calendar_availability",
    "calendar_availability": "check_calendar_availability",
    "free_busy": "check_calendar_availability",
    "check_free_busy": "check_calendar_availability",
    "create_event": "create_calendar_event",
    "create_calendar_event": "create_calendar_event",
    "schedule_event": "create_calendar_event",
    "add_event": "create_calendar_event",
    "delete_event": "delete_calendar_event",
    "delete_calendar_event": "delete_calendar_event",
    "remove_event": "delete_calendar_event",
    "remove_calendar_event": "delete_calendar_event",
    "cancel_event": "delete_calendar_event",
    "cancel_calendar_event": "delete_calendar_event",
    "add_task": "create_task",
    "new_task": "create_task",
    "get_tasks": "list_tasks",
    "show_tasks": "list_tasks",
    "tasks": "list_tasks",
    "edit_task": "update_task",
    "modify_task": "update_task",
    "done_task": "complete_task",
    "finish_task": "complete_task",
    "mark_task_completed": "complete_task",
    "remove_task": "delete_task",
    "remind_me": "create_reminder",
    "add_reminder": "create_reminder",
    "schedule_reminder": "create_reminder",
    "get_reminders": "list_reminders",
    "show_reminders": "list_reminders",
    "plan_my_day": "plan_day",
    "daily_plan": "plan_day",
    "schedule_day": "plan_day",
    # GitHub MCP Aliases
    "github_search": "github_search_repositories",
    "search_github": "github_search_repositories",
    "search_repos": "github_search_repositories",
    "search_repositories": "github_search_repositories",
    "get_repo": "github_get_repository",
    "get_repository": "github_get_repository",
    "github_repo": "github_get_repository",
    "list_repos": "github_list_user_repositories",
    "list_repositories": "github_list_user_repositories",
    "get_file": "github_get_file_contents",
    "read_file": "github_get_file_contents",
    "get_file_contents": "github_get_file_contents",
    "create_file": "github_create_or_update_file",
    "update_file": "github_create_or_update_file",
    "write_file": "github_create_or_update_file",
    "delete_file": "github_delete_file",
    "list_issues": "github_list_issues",
    "get_issue": "github_get_issue",
    "create_issue": "github_create_issue",
    "add_issue_comment": "github_add_issue_comment",
    "comment_issue": "github_add_issue_comment",
    "list_prs": "github_list_pull_requests",
    "list_pull_requests": "github_list_pull_requests",
    "get_pr": "github_get_pull_request",
    "get_pull_request": "github_get_pull_request",
    "create_pr": "github_create_pull_request",
    "create_pull_request": "github_create_pull_request",
    "merge_pr": "github_merge_pull_request",
    "merge_pull_request": "github_merge_pull_request",
    "list_branches": "github_list_branches",
    "create_branch": "github_create_branch",
    "list_commits": "github_list_commits",
    "list_workflows": "github_list_workflows",
    "list_workflow_runs": "github_list_workflow_runs",
    "dispatch_workflow": "github_dispatch_workflow",
    "trigger_workflow": "github_dispatch_workflow",
}


class ToolRegistry:
    """Central registry of all available tools for model discovery and execution."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance."""
        self._tools[tool.name.lower()] = tool

    def unregister(self, name: str) -> None:
        """Unregister a tool by name."""
        self._tools.pop(name.lower(), None)

    def get(self, name: str) -> BaseTool | None:
        """Lookup a tool by name or alias."""
        clean_name = (name or "").strip().lower()
        tool = self._tools.get(clean_name)
        if tool is not None:
            return tool
        canonical = TOOL_ALIASES.get(clean_name)
        if canonical:
            return self._tools.get(canonical)
        return None

    def has_tool(self, name: str) -> bool:
        """Check if a tool exists in registry."""
        return self.get(name) is not None

    def list_tools(self) -> list[BaseTool]:
        """Return list of all registered tools."""
        return list(self._tools.values())

    def get_schemas(self) -> list[dict[str, Any]]:
        """Return provider-compatible function definitions for all registered tools."""
        return [tool.get_schema() for tool in self._tools.values()]

    def get_catalog(self) -> list[dict[str, Any]]:
        """Return detailed info on all registered tools for the UI and APIs."""
        return [tool.get_info() for tool in self._tools.values()]


# Global default tool registry
_global_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
        _register_builtin_tools(_global_registry)
    return _global_registry


def _register_builtin_tools(registry: ToolRegistry) -> None:
    """Populate default registry with all built-in and GitHub MCP tools."""
    from app.tools.builtins.calculator import CalculatorTool
    from app.tools.builtins.web_search import WebSearchTool
    from app.tools.builtins.url_reader import URLReaderTool
    from app.tools.builtins.weather import WeatherTool
    from app.tools.builtins.currency import CurrencyConversionTool
    from app.tools.builtins.news import NewsSearchTool
    from app.tools.builtins.finance import StockPriceTool
    from app.tools.builtins.crypto import CryptoPriceTool
    from app.tools.builtins.knowledge_search import KnowledgeSearchTool
    from app.tools.builtins.memory_search import MemorySearchTool
    from app.tools.builtins.conversation_search import ConversationSearchTool
    from app.tools.builtins.calendar import (
        GetCalendarEventsTool,
        CheckCalendarAvailabilityTool,
        CreateCalendarEventTool,
        DeleteCalendarEventTool,
    )
    from app.tools.builtins.task_tools import (
        CreateTaskTool,
        ListTasksTool,
        UpdateTaskTool,
        CompleteTaskTool,
        DeleteTaskTool,
        CreateReminderTool,
        ListRemindersTool,
        PlanDayTool,
    )
    from app.tools.builtins.github_tools import get_github_tools

    registry.register(CalculatorTool())
    registry.register(WebSearchTool())
    registry.register(URLReaderTool())
    registry.register(WeatherTool())
    registry.register(CurrencyConversionTool())
    registry.register(NewsSearchTool())
    registry.register(StockPriceTool())
    registry.register(CryptoPriceTool())
    registry.register(KnowledgeSearchTool())
    registry.register(MemorySearchTool())
    registry.register(ConversationSearchTool())
    registry.register(GetCalendarEventsTool())
    registry.register(CheckCalendarAvailabilityTool())
    registry.register(CreateCalendarEventTool())
    registry.register(DeleteCalendarEventTool())
    registry.register(CreateTaskTool())
    registry.register(ListTasksTool())
    registry.register(UpdateTaskTool())
    registry.register(CompleteTaskTool())
    registry.register(DeleteTaskTool())
    registry.register(CreateReminderTool())
    registry.register(ListRemindersTool())
    registry.register(PlanDayTool())

    # Dynamically register all GitHub MCP tools
    for gh_tool in get_github_tools():
        registry.register(gh_tool)


