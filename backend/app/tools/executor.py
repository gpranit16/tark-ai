import asyncio
import re
import time
from typing import Any

from app.core.config import get_settings
from app.tools.base import BaseTool, ToolExecutionContext, ToolPermission, ToolResult
from app.tools.registry import ToolRegistry, get_tool_registry


class ToolExecutor:
    """Safely executes registered tools with permission enforcement, timeouts, and output sanitization."""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or get_tool_registry()
        self.settings = get_settings()

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolResult:
        start_time = time.perf_counter()

        tool = self.registry.get(tool_name)
        if tool is None:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Tool '{tool_name}' not found in registry",
                source="system",
                metadata={"latency_ms": int((time.perf_counter() - start_time) * 1000)},
            )

        # 1. Validate permissions
        perm_error = self._check_permissions(tool, context)
        if perm_error:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Permission denied: {perm_error}",
                source="security",
                metadata={"latency_ms": int((time.perf_counter() - start_time) * 1000)},
            )

        # 2. Validate arguments against schema
        arg_error = self._validate_arguments(tool, arguments)
        if arg_error:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Invalid arguments: {arg_error}",
                source="validation",
                metadata={"latency_ms": int((time.perf_counter() - start_time) * 1000)},
            )

        # 3. Execute with timeout
        timeout = self.settings.tool_timeout_seconds
        try:
            result = await asyncio.wait_for(
                tool.execute(arguments, context),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Tool execution timed out after {timeout}s",
                source="timeout",
                metadata={"latency_ms": int((time.perf_counter() - start_time) * 1000)},
            )
        except Exception as exc:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Tool execution error: {str(exc)}",
                source="exception",
                metadata={"latency_ms": int((time.perf_counter() - start_time) * 1000)},
            )

        # 4. Cap output size & sanitize
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        result.metadata["latency_ms"] = latency_ms

        if result.success and result.data:
            result.data = self._sanitize_and_cap(result.data)

        return result

    def _check_permissions(self, tool: BaseTool, context: ToolExecutionContext) -> str | None:
        """Verify context satisfies the tool's required permissions."""
        perms = tool.get_permissions_list() if hasattr(tool, "get_permissions_list") else [p.value for p in getattr(tool, "permissions", [])]
        if "user_data" in perms:
            if not context.user_id:
                return "User context (user_id) is required for user-scoped data access"
        return None

    def _validate_arguments(self, tool: BaseTool, arguments: dict[str, Any]) -> str | None:
        """Verify required fields specified in the tool schema."""
        if not isinstance(arguments, dict):
            return "Arguments must be a JSON object / dictionary"
        schema = tool.get_parameters_schema() if hasattr(tool, "get_parameters_schema") else getattr(tool, "parameters", {})
        required_fields = schema.get("required", [])
        for req in required_fields:
            if req not in arguments or arguments[req] is None:
                return f"Missing required argument: '{req}'"
        return None

    def _sanitize_and_cap(self, data: Any) -> Any:
        """Sanitize prompt injection markers and enforce response size limits."""
        max_size = self.settings.max_tool_output_size

        if isinstance(data, str):
            sanitized = self._sanitize_text(data)
            if len(sanitized) > max_size:
                return sanitized[:max_size] + "\n...[Output truncated due to size limit]"
            return sanitized
        elif isinstance(data, list):
            return [self._sanitize_and_cap(item) for item in data]
        elif isinstance(data, dict):
            return {k: self._sanitize_and_cap(v) for k, v in data.items()}
        return data

    def _sanitize_text(self, text: str) -> str:
        """Neutralize malicious injection instructions in external web data."""
        # Replace dangerous prompt hijacking phrases from external websites
        patterns = [
            (r"(?i)ignore\s+(all\s+)?previous\s+instructions", "[Filtered prompt override]"),
            (r"(?i)system\s+prompt\s+override", "[Filtered prompt override]"),
            (r"(?i)you\s+are\s+now\s+in\s+developer\s+mode", "[Filtered mode switch]"),
        ]
        sanitized = text
        for pat, rep in patterns:
            sanitized = re.sub(pat, rep, sanitized)
        return sanitized
