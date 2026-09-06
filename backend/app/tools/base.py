from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession


class ToolPermission(StrEnum):
    SAFE = "safe"
    NETWORK = "network"
    USER_DATA = "user_data"
    SYSTEM = "system"


class ToolResult(BaseModel):
    tool_name: str
    success: bool
    data: Any = None
    error: str | None = None
    source: str = "builtin"
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass
class ToolExecutionContext:
    user_id: UUID
    project_id: UUID | None = None
    thread_id: UUID | None = None
    session: AsyncSession | None = None


class BaseTool(ABC):
    name: str
    description: str
    parameters: dict[str, Any] = {}
    input_schema: Any = None
    permissions: list[ToolPermission] = [ToolPermission.SAFE]
    permission: ToolPermission | None = None
    category: str = "general"

    @abstractmethod
    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        """Execute the tool with given arguments and security context."""
        raise NotImplementedError

    def get_parameters_schema(self) -> dict[str, Any]:
        """Return JSON Schema for input parameters."""
        if hasattr(self, "input_schema") and self.input_schema is not None:
            if hasattr(self.input_schema, "model_json_schema"):
                return self.input_schema.model_json_schema()
            elif isinstance(self.input_schema, dict):
                return self.input_schema
        if hasattr(self, "parameters") and self.parameters:
            return self.parameters
        return {"type": "object", "properties": {}}

    def get_permissions_list(self) -> list[str]:
        """Return list of permission strings."""
        perms = []
        if hasattr(self, "permissions") and self.permissions:
            perms.extend([p.value if hasattr(p, "value") else str(p) for p in self.permissions])
        if hasattr(self, "permission") and self.permission:
            p_val = self.permission.value if hasattr(self.permission, "value") else str(self.permission)
            if p_val not in perms:
                perms.append(p_val)
        return perms or ["safe"]

    def get_schema(self) -> dict[str, Any]:
        """Return OpenAI / provider-compatible tool definition schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.get_parameters_schema(),
            },
        }

    def get_info(self) -> dict[str, Any]:
        """Return information dictionary for tool catalog APIs and UIs."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.get_parameters_schema(),
            "input_schema": self.get_parameters_schema(),
            "permission": self.get_permissions_list()[0] if self.get_permissions_list() else "safe",
            "permissions": self.get_permissions_list(),
            "category": getattr(self, "category", "general"),
        }

