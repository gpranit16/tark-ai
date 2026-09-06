"""Tools API router for listing and manual execution of tools."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.tools.base import ToolExecutionContext, ToolPermission, ToolResult
from app.tools.executor import ToolExecutor
from app.tools.registry import get_tool_registry

logger = logging.getLogger(__name__)

DEFAULT_DEV_USER_ID = UUID("00000000-0000-0000-0000-000000000001")

router = APIRouter(prefix="/tools", tags=["tools"])


class ToolExecuteRequest(BaseModel):
    tool_name: str = Field(..., description="Name of the tool to execute.")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Input arguments matching tool schema.")
    parameters: Optional[Dict[str, Any]] = Field(default=None, description="Alias for arguments.")
    user_id: UUID = Field(default=DEFAULT_DEV_USER_ID, description="User ID context for scoped tools.")
    project_id: Optional[UUID] = Field(default=None, description="Optional project ID context.")
    thread_id: Optional[UUID] = Field(default=None, description="Optional thread ID context.")


class ToolInfoResponse(BaseModel):
    name: str
    description: str
    permission: str
    input_schema: Dict[str, Any]


class ToolListResponse(BaseModel):
    tools: List[ToolInfoResponse]
    count: int


@router.get("", response_model=ToolListResponse)
async def list_tools() -> ToolListResponse:
    """List all registered tools with their schemas and permissions."""
    registry = get_tool_registry()
    catalog = registry.get_catalog()
    return ToolListResponse(
        tools=[
            ToolInfoResponse(
                name=t["name"],
                description=t["description"],
                permission=t["permission"],
                input_schema=t["input_schema"],
            )
            for t in catalog
        ],
        count=len(catalog),
    )


@router.post("/execute", response_model=ToolResult)
async def execute_tool(
    request: ToolExecuteRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ToolResult:
    """Manually execute a registered tool (e.g. from developer console / test playground)."""
    registry = get_tool_registry()
    if not registry.has_tool(request.tool_name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{request.tool_name}' not found in registry.",
        )

    executor = ToolExecutor(registry)
    context = ToolExecutionContext(
        user_id=request.user_id,
        project_id=request.project_id,
        thread_id=request.thread_id,
        session=session,
    )

    args = request.arguments if request.arguments else (request.parameters or {})

    result = await executor.execute(
        tool_name=request.tool_name,
        arguments=args,
        context=context,
    )

    return result
