"""Unit & Integration tests for GitHub MCP toolchain in TARK AI."""
from __future__ import annotations

import json
from typing import Any, Dict
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.integrations.github import GitHubMCPService, get_github_service
from app.tools.base import ToolExecutionContext, ToolResult
from app.tools.builtins.github_tools import (
    GitHubCreateBranchTool,
    GitHubCreateIssueTool,
    GitHubCreateOrUpdateFileTool,
    GitHubCreatePullRequestTool,
    GitHubCreateRepositoryTool,
    GitHubDeleteFileTool,
    GitHubDispatchWorkflowTool,
    GitHubGetFileContentsTool,
    GitHubGetRepositoryTool,
    GitHubListCommitsTool,
    GitHubListIssuesTool,
    GitHubListPullRequestsTool,
    GitHubListWorkflowsTool,
    GitHubMergePullRequestTool,
    GitHubSearchRepositoriesTool,
    get_github_tools,
)
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry, get_tool_registry


@pytest.fixture
def mock_context() -> ToolExecutionContext:
    return ToolExecutionContext(
        user_id=uuid4(),
        project_id=None,
        thread_id=None,
        session=None,
    )


# =============================================================================
# 1. TOOL DISCOVERY & REGISTRATION
# =============================================================================

def test_github_tools_discovery_and_registry():
    """Verify all 21 GitHub MCP tools are discovered and registered in ToolRegistry."""
    registry = get_tool_registry()
    tools = get_github_tools()
    assert len(tools) == 21

    expected_tool_names = [
        "github_search_repositories",
        "github_get_repository",
        "github_list_user_repositories",
        "github_create_repository",
        "github_get_file_contents",
        "github_create_or_update_file",
        "github_delete_file",
        "github_list_issues",
        "github_get_issue",
        "github_create_issue",
        "github_add_issue_comment",
        "github_list_pull_requests",
        "github_get_pull_request",
        "github_create_pull_request",
        "github_merge_pull_request",
        "github_list_branches",
        "github_create_branch",
        "github_list_commits",
        "github_list_workflows",
        "github_list_workflow_runs",
        "github_dispatch_workflow",
    ]

    for name in expected_tool_names:
        tool = registry.get(name)
        assert tool is not None, f"Tool '{name}' was not found in registry"
        schema = tool.get_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == name
        assert "description" in schema["function"]
        assert "parameters" in schema["function"]


def test_github_tool_aliases():
    """Verify common natural language aliases map to canonical GitHub tools."""
    registry = get_tool_registry()
    assert registry.get("search_github").name == "github_search_repositories"
    assert registry.get("get_repo").name == "github_get_repository"
    assert registry.get("read_file").name == "github_get_file_contents"
    assert registry.get("create_issue").name == "github_create_issue"
    assert registry.get("create_pr").name == "github_create_pull_request"
    assert registry.get("merge_pr").name == "github_merge_pull_request"
    assert registry.get("dispatch_workflow").name == "github_dispatch_workflow"


# =============================================================================
# 2. WRITE CONFIRMATION SAFETY GUARDS
# =============================================================================

@pytest.mark.asyncio
async def test_write_action_requires_confirmation_when_unconfirmed(mock_context: ToolExecutionContext):
    """Destructive/write tools MUST return requires_confirmation if confirmed is not True."""
    with patch.object(GitHubMCPService, "get_token_for_user", return_value="ghp_test_token_123"):
        # 1. Create issue
        create_issue_tool = GitHubCreateIssueTool()
        res = await create_issue_tool.execute(
            {"owner": "octocat", "repo": "Hello-World", "title": "Test Issue", "body": "Details"},
            mock_context,
        )
        assert res.success is True
        assert res.data["status"] == "requires_confirmation"
        assert "⚠️ [SAFETY CONFIRMATION REQUIRED]" in res.data["message"]

        # 2. Create/update file
        create_file_tool = GitHubCreateOrUpdateFileTool()
        res_file = await create_file_tool.execute(
            {"owner": "octocat", "repo": "Hello-World", "path": "src/main.py", "content": "print('hello')", "message": "Add main"},
            mock_context,
        )
        assert res_file.success is True
        assert res_file.data["status"] == "requires_confirmation"

        # 3. Create PR
        create_pr_tool = GitHubCreatePullRequestTool()
        res_pr = await create_pr_tool.execute(
            {"owner": "octocat", "repo": "Hello-World", "title": "New Feature", "head": "feat"},
            mock_context,
        )
        assert res_pr.success is True
        assert res_pr.data["status"] == "requires_confirmation"

        # 4. Dispatch workflow
        dispatch_tool = GitHubDispatchWorkflowTool()
        res_dispatch = await dispatch_tool.execute(
            {"owner": "octocat", "repo": "Hello-World", "workflow_id": "ci.yml"},
            mock_context,
        )
        assert res_dispatch.success is True
        assert res_dispatch.data["status"] == "requires_confirmation"


# =============================================================================
# 3. READ OPERATIONS & CONFIRMED EXECUTION
# =============================================================================

@pytest.mark.asyncio
async def test_read_operations_execute_immediately(mock_context: ToolExecutionContext):
    """Read tools (search, get repo, get file, list issues) execute without confirmation prompt."""
    with patch.object(GitHubMCPService, "get_token_for_user", return_value="ghp_test_token_123"):
        with patch.object(GitHubMCPService, "search_repositories", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = {
                "total_count": 1,
                "repositories": [{"name": "Hello-World", "full_name": "octocat/Hello-World", "stars": 2000}],
            }
            tool = GitHubSearchRepositoriesTool()
            res = await tool.execute({"query": "Hello-World"}, mock_context)
            assert res.success is True
            assert res.data["total_count"] == 1
            assert res.data["repositories"][0]["name"] == "Hello-World"
            mock_search.assert_awaited_once()


@pytest.mark.asyncio
async def test_write_operation_executes_when_confirmed(mock_context: ToolExecutionContext):
    """When confirmed=True is supplied after user approval, the write operation executes on GitHub."""
    with patch.object(GitHubMCPService, "get_token_for_user", return_value="ghp_test_token_123"):
        with patch.object(GitHubMCPService, "create_issue", new_callable=AsyncMock) as mock_create_issue:
            mock_create_issue.return_value = {
                "number": 42,
                "title": "Confirmed Bugfix",
                "html_url": "https://github.com/octocat/Hello-World/issues/42",
                "state": "open",
            }
            tool = GitHubCreateIssueTool()
            res = await tool.execute(
                {
                    "owner": "octocat",
                    "repo": "Hello-World",
                    "title": "Confirmed Bugfix",
                    "body": "Fixed regression",
                    "confirmed": True,
                },
                mock_context,
            )
            assert res.success is True
            assert res.data["number"] == 42
            assert res.data["state"] == "open"
            mock_create_issue.assert_awaited_once()


# =============================================================================
# 4. CREDENTIAL PRIVACY & ERROR HANDLING
# =============================================================================

@pytest.mark.asyncio
async def test_token_privacy_and_error_handling(mock_context: ToolExecutionContext):
    """Verify tokens are never leaked in error messages when GitHub is disconnected or errors occur."""
    with patch.object(GitHubMCPService, "get_token_for_user", return_value=None):
        tool = GitHubGetRepositoryTool()
        res = await tool.execute({"owner": "octocat", "repo": "Hello-World"}, mock_context)
        assert res.success is False
        assert "GitHub is not connected" in res.error
        assert "ghp_" not in str(res.error)


@pytest.mark.asyncio
async def test_github_executor_integration(mock_context: ToolExecutionContext):
    """Verify ToolExecutor handles GitHub tools with permission enforcement."""
    executor = ToolExecutor()
    with patch.object(GitHubMCPService, "get_token_for_user", return_value="ghp_test_token_123"):
        with patch.object(GitHubMCPService, "get_repository", new_callable=AsyncMock) as mock_get_repo:
            mock_get_repo.return_value = {
                "name": "Hello-World",
                "full_name": "octocat/Hello-World",
                "default_branch": "main",
                "stars": 1500,
            }
            res = await executor.execute(
                tool_name="github_get_repository",
                arguments={"owner": "octocat", "repo": "Hello-World"},
                context=mock_context,
            )
            assert res.success is True
            assert res.data["full_name"] == "octocat/Hello-World"
            assert "latency_ms" in res.metadata
