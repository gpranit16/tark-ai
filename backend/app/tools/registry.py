from typing import Any

from app.tools.base import BaseTool


class ToolRegistry:
    """Central registry of all available tools for model discovery and execution."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance."""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """Unregister a tool by name."""
        self._tools.pop(name, None)

    def get(self, name: str) -> BaseTool | None:
        """Lookup a tool by name."""
        return self._tools.get(name)

    def has_tool(self, name: str) -> bool:
        """Check if a tool exists in registry."""
        return name in self._tools

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
    """Populate default registry with all 11 built-in tools."""
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
