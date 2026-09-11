"""GitHub MCP Builtin Tools for TARK AI.

Provides provider-compatible tool definitions for:
- Repository discovery & inspection
- File read & write
- Issue management
- Pull request workflows
- Branch & commit navigation
- GitHub Actions triggers
Enforces explicit user confirmation on all write/destructive operations.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from app.services.integrations.github import get_github_service
from app.tools.base import BaseTool, ToolExecutionContext, ToolPermission, ToolResult


async def _get_token_or_error(context: ToolExecutionContext) -> tuple[Optional[str], Optional[ToolResult], str]:
    """Helper to resolve GitHub token securely or return error result."""
    service = get_github_service()
    token = await service.get_token_for_user(user_id=context.user_id, session=context.session)
    if not token:
        return None, ToolResult(
            tool_name="github",
            success=False,
            error="GitHub is not connected. Please configure GITHUB_PERSONAL_ACCESS_TOKEN in backend .env or connect under Settings -> Personal -> Connections.",
            source="github_mcp",
        ), ""
    return token, None, ""


def _check_write_confirmation(
    tool_name: str,
    summary: str,
    arguments: Dict[str, Any],
) -> Optional[ToolResult]:
    """Safety check: Pauses write actions unless explicitly confirmed by user."""
    if not arguments.get("confirmed", False):
        return ToolResult(
            tool_name=tool_name,
            success=True,
            data={
                "status": "requires_confirmation",
                "action": tool_name,
                "summary": summary,
                "proposed_parameters": {k: v for k, v in arguments.items() if k != "confirmed"},
                "message": (
                    "⚠️ [SAFETY CONFIRMATION REQUIRED]: This action will perform a LIVE WRITE operation on GitHub. "
                    "You MUST ask the user for explicit confirmation before executing this change. "
                    "When the user approves, re-execute this tool with 'confirmed': true."
                ),
            },
            source="github_mcp_safety",
        )
    return None


async def _resolve_owner_and_repo(
    arguments: Dict[str, Any],
    token: str,
) -> tuple[str, str]:
    """Helper to extract owner and repo safely, supporting 'owner/repo' strings or auto-resolving authenticated user login."""
    owner = str(arguments.get("owner") or "").strip()
    repo = str(arguments.get("repo") or "").strip()

    if "/" in repo:
        parts = repo.split("/", 1)
        owner = parts[0].strip()
        repo = parts[1].strip()
    elif "/" in owner:
        parts = owner.split("/", 1)
        owner = parts[0].strip()
        repo = parts[1].strip()

    if not owner and token:
        try:
            service = get_github_service()
            user_info = await service.get_user_info(token)
            owner = user_info.get("login", "")
        except Exception:
            pass

    return owner, repo


# =============================================================================
# 1. REPOSITORIES
# =============================================================================

class GitHubSearchRepositoriesTool(BaseTool):
    name = "github_search_repositories"
    description = "Search public and private GitHub repositories by keyword, topic, or language."
    category = "github"
    permissions = [ToolPermission.NETWORK]
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query (e.g. 'react language:typescript', 'tark-ai')"},
            "sort": {"type": "string", "enum": ["stars", "forks", "updated", "help-wanted-issues"], "default": "stars"},
            "order": {"type": "string", "enum": ["desc", "asc"], "default": "desc"},
            "per_page": {"type": "integer", "default": 10, "description": "Number of results to return (max 30)"},
        },
        "required": ["query"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        token, err_res, _ = await _get_token_or_error(context)
        if err_res:
            return err_res

        service = get_github_service()
        try:
            res = await service.search_repositories(
                token=token,
                query=arguments["query"],
                sort=arguments.get("sort", "stars"),
                order=arguments.get("order", "desc"),
                per_page=arguments.get("per_page", 10),
            )
            return ToolResult(tool_name=self.name, success=True, data=res, source="github_mcp")
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc), source="github_mcp")


class GitHubGetRepositoryTool(BaseTool):
    name = "github_get_repository"
    description = "Get detailed information about a specific GitHub repository including metadata and root directory structure."
    category = "github"
    permissions = [ToolPermission.NETWORK]
    parameters = {
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "Repository owner / organization (e.g. 'torvalds', 'octocat'). Optional if authenticated."},
            "repo": {"type": "string", "description": "Repository name (e.g. 'linux', 'iot-bin', or 'owner/repo')"},
        },
        "required": ["repo"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        token, err_res, _ = await _get_token_or_error(context)
        if err_res:
            return err_res

        service = get_github_service()
        owner, repo = await _resolve_owner_and_repo(arguments, token)
        if not owner or not repo:
            return ToolResult(tool_name=self.name, success=False, error="Both repository name and owner must be provided.", source="github_mcp")
        try:
            res = await service.get_repository(token=token, owner=owner, repo=repo)
            try:
                root_data = await service.get_file_contents(token=token, owner=owner, repo=repo, path="")
                if root_data.get("type") == "directory":
                    res["root_files_and_folders"] = [
                        f"{e.get('name')} ({e.get('type')})" for e in root_data.get("entries", [])[:25]
                    ]
            except Exception:
                pass
            return ToolResult(tool_name=self.name, success=True, data=res, source="github_mcp")
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc), source="github_mcp")


class GitHubListUserRepositoriesTool(BaseTool):
    name = "github_list_user_repositories"
    description = "List repositories owned by the authenticated user or a specific GitHub username."
    category = "github"
    permissions = [ToolPermission.NETWORK]
    parameters = {
        "type": "object",
        "properties": {
            "username": {"type": "string", "description": "Optional GitHub username. If omitted, lists authenticated user's repositories."},
            "sort": {"type": "string", "enum": ["updated", "created", "pushed", "full_name"], "default": "updated"},
            "per_page": {"type": "integer", "default": 6, "description": "Number of repositories to return (default: 6)"},
        },
    }

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        token, err_res, _ = await _get_token_or_error(context)
        if err_res:
            return err_res

        service = get_github_service()
        try:
            res = await service.list_user_repositories(
                token=token,
                username=arguments.get("username"),
                sort=arguments.get("sort", "updated"),
                per_page=arguments.get("per_page", 6),
            )
            return ToolResult(tool_name=self.name, success=True, data={"repositories": res, "count": len(res)}, source="github_mcp")
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc), source="github_mcp")


class GitHubCreateRepositoryTool(BaseTool):
    name = "github_create_repository"
    description = "Create a new repository under the authenticated user's account. Requires user confirmation."
    category = "github"
    permissions = [ToolPermission.NETWORK, ToolPermission.USER_DATA]
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Name of the new repository"},
            "description": {"type": "string", "description": "Short description of the repository"},
            "private": {"type": "boolean", "default": False, "description": "Whether the repository should be private"},
            "auto_init": {"type": "boolean", "default": True, "description": "Initialize with an empty README"},
            "confirmed": {"type": "boolean", "default": False, "description": "Must be true to execute the repository creation."},
        },
        "required": ["name"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        token, err_res, _ = await _get_token_or_error(context)
        if err_res:
            return err_res

        conf_res = _check_write_confirmation(
            self.name,
            f"Create {'private' if arguments.get('private') else 'public'} repository '{arguments['name']}' on GitHub",
            arguments,
        )
        if conf_res:
            return conf_res

        service = get_github_service()
        try:
            res = await service.create_repository(
                token=token,
                name=arguments["name"],
                description=arguments.get("description", ""),
                private=arguments.get("private", False),
                auto_init=arguments.get("auto_init", True),
            )
            return ToolResult(tool_name=self.name, success=True, data=res, source="github_mcp")
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc), source="github_mcp")


# =============================================================================
# 2. CODE & FILES
# =============================================================================

class GitHubGetFileContentsTool(BaseTool):
    name = "github_get_file_contents"
    description = "Get the contents of a file or directory tree in a GitHub repository at a specific path and branch."
    category = "github"
    permissions = [ToolPermission.NETWORK]
    parameters = {
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "Repository owner (optional if authenticated)"},
            "repo": {"type": "string", "description": "Repository name (e.g. 'DSA-Leetcode_Notes', or 'owner/repo')"},
            "path": {"type": "string", "default": "", "description": "Path to file or directory (e.g. 'src/index.ts', 'README.md', '')"},
            "ref": {"type": "string", "description": "Optional branch, tag, or commit SHA. Defaults to default branch."},
        },
        "required": ["repo"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        token, err_res, _ = await _get_token_or_error(context)
        if err_res:
            return err_res

        service = get_github_service()
        owner, repo = await _resolve_owner_and_repo(arguments, token)
        if not owner or not repo:
            return ToolResult(tool_name=self.name, success=False, error="Both repository name and owner must be provided.", source="github_mcp")
        try:
            res = await service.get_file_contents(
                token=token,
                owner=owner,
                repo=repo,
                path=arguments.get("path", ""),
                ref=arguments.get("ref"),
            )
            return ToolResult(tool_name=self.name, success=True, data=res, source="github_mcp")
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc), source="github_mcp")


class GitHubCreateOrUpdateFileTool(BaseTool):
    name = "github_create_or_update_file"
    description = "Create a new file or update an existing file in a GitHub repository. Requires user confirmation."
    category = "github"
    permissions = [ToolPermission.NETWORK, ToolPermission.USER_DATA]
    parameters = {
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "Repository owner (optional if authenticated)"},
            "repo": {"type": "string", "description": "Repository name"},
            "path": {"type": "string", "description": "File path in repository (e.g. 'src/utils.py', 'docs/README.md')"},
            "content": {"type": "string", "description": "The exact text content to write to the file"},
            "message": {"type": "string", "description": "Commit message describing the change"},
            "branch": {"type": "string", "description": "Target branch name. Defaults to repository's default branch."},
            "sha": {"type": "string", "description": "Optional SHA of the file if updating existing file."},
            "confirmed": {"type": "boolean", "default": False, "description": "Must be true to apply the commit to GitHub."},
        },
        "required": ["repo", "path", "content", "message"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        token, err_res, _ = await _get_token_or_error(context)
        if err_res:
            return err_res

        service = get_github_service()
        owner, repo = await _resolve_owner_and_repo(arguments, token)
        if not owner or not repo:
            return ToolResult(tool_name=self.name, success=False, error="Both repository name and owner must be provided.", source="github_mcp")

        conf_res = _check_write_confirmation(
            self.name,
            f"Commit and write file '{arguments['path']}' in {owner}/{repo} (Branch: {arguments.get('branch', 'default')})",
            arguments,
        )
        if conf_res:
            return conf_res

        try:
            res = await service.create_or_update_file(
                token=token,
                owner=owner,
                repo=repo,
                path=arguments["path"],
                content=arguments["content"],
                message=arguments["message"],
                branch=arguments.get("branch"),
                sha=arguments.get("sha"),
            )
            return ToolResult(tool_name=self.name, success=True, data=res, source="github_mcp")
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc), source="github_mcp")


class GitHubDeleteFileTool(BaseTool):
    name = "github_delete_file"
    description = "Delete a file from a GitHub repository. Requires user confirmation."
    category = "github"
    permissions = [ToolPermission.NETWORK, ToolPermission.USER_DATA]
    parameters = {
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "Repository owner (optional if authenticated)"},
            "repo": {"type": "string", "description": "Repository name"},
            "path": {"type": "string", "description": "File path to delete"},
            "message": {"type": "string", "description": "Commit message for deletion"},
            "branch": {"type": "string", "description": "Target branch"},
            "sha": {"type": "string", "description": "Optional file SHA"},
            "confirmed": {"type": "boolean", "default": False, "description": "Must be true to execute file deletion."},
        },
        "required": ["repo", "path", "message"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        token, err_res, _ = await _get_token_or_error(context)
        if err_res:
            return err_res

        service = get_github_service()
        owner, repo = await _resolve_owner_and_repo(arguments, token)
        if not owner or not repo:
            return ToolResult(tool_name=self.name, success=False, error="Both repository name and owner must be provided.", source="github_mcp")

        conf_res = _check_write_confirmation(
            self.name,
            f"Delete file '{arguments['path']}' from {owner}/{repo}",
            arguments,
        )
        if conf_res:
            return conf_res

        try:
            res = await service.delete_file(
                token=token,
                owner=owner,
                repo=repo,
                path=arguments["path"],
                message=arguments["message"],
                sha=arguments.get("sha"),
                branch=arguments.get("branch"),
            )
            return ToolResult(tool_name=self.name, success=True, data=res, source="github_mcp")
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc), source="github_mcp")


# =============================================================================
# 3. ISSUES
# =============================================================================

class GitHubListIssuesTool(BaseTool):
    name = "github_list_issues"
    description = "List issues in a GitHub repository with filters for state (open/closed) and labels."
    category = "github"
    permissions = [ToolPermission.NETWORK]
    parameters = {
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "Repository owner (optional if authenticated)"},
            "repo": {"type": "string", "description": "Repository name"},
            "state": {"type": "string", "enum": ["open", "closed", "all"], "default": "open"},
            "labels": {"type": "string", "description": "Optional comma-separated label names (e.g. 'bug,ui')"},
            "per_page": {"type": "integer", "default": 20},
        },
        "required": ["repo"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        token, err_res, _ = await _get_token_or_error(context)
        if err_res:
            return err_res

        service = get_github_service()
        owner, repo = await _resolve_owner_and_repo(arguments, token)
        if not owner or not repo:
            return ToolResult(tool_name=self.name, success=False, error="Both repository name and owner must be provided.", source="github_mcp")
        try:
            res = await service.list_issues(
                token=token,
                owner=owner,
                repo=repo,
                state=arguments.get("state", "open"),
                labels=arguments.get("labels"),
                per_page=arguments.get("per_page", 20),
            )
            return ToolResult(tool_name=self.name, success=True, data={"issues": res, "count": len(res)}, source="github_mcp")
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc), source="github_mcp")


class GitHubGetIssueTool(BaseTool):
    name = "github_get_issue"
    description = "Get full details and conversation comments for a specific GitHub issue."
    category = "github"
    permissions = [ToolPermission.NETWORK]
    parameters = {
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "Repository owner (optional if authenticated)"},
            "repo": {"type": "string", "description": "Repository name"},
            "issue_number": {"type": "integer", "description": "Issue number (e.g. 42)"},
        },
        "required": ["repo", "issue_number"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        token, err_res, _ = await _get_token_or_error(context)
        if err_res:
            return err_res

        service = get_github_service()
        owner, repo = await _resolve_owner_and_repo(arguments, token)
        if not owner or not repo:
            return ToolResult(tool_name=self.name, success=False, error="Both repository name and owner must be provided.", source="github_mcp")
        try:
            res = await service.get_issue(
                token=token,
                owner=owner,
                repo=repo,
                issue_number=int(arguments["issue_number"]),
            )
            return ToolResult(tool_name=self.name, success=True, data=res, source="github_mcp")
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc), source="github_mcp")


class GitHubCreateIssueTool(BaseTool):
    name = "github_create_issue"
    description = "Create a new issue in a GitHub repository. Requires user confirmation."
    category = "github"
    permissions = [ToolPermission.NETWORK, ToolPermission.USER_DATA]
    parameters = {
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "Repository owner (optional if authenticated)"},
            "repo": {"type": "string", "description": "Repository name"},
            "title": {"type": "string", "description": "Issue title"},
            "body": {"type": "string", "description": "Detailed markdown body of the issue"},
            "labels": {"type": "array", "items": {"type": "string"}, "description": "Optional label names"},
            "assignees": {"type": "array", "items": {"type": "string"}, "description": "Optional usernames to assign"},
            "confirmed": {"type": "boolean", "default": False, "description": "Must be true to create the issue."},
        },
        "required": ["repo", "title"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        token, err_res, _ = await _get_token_or_error(context)
        if err_res:
            return err_res

        service = get_github_service()
        owner, repo = await _resolve_owner_and_repo(arguments, token)
        if not owner or not repo:
            return ToolResult(tool_name=self.name, success=False, error="Both repository name and owner must be provided.", source="github_mcp")

        conf_res = _check_write_confirmation(
            self.name,
            f"Create issue '{arguments['title']}' in {owner}/{repo}",
            arguments,
        )
        if conf_res:
            return conf_res

        try:
            res = await service.create_issue(
                token=token,
                owner=owner,
                repo=repo,
                title=arguments["title"],
                body=arguments.get("body", ""),
                labels=arguments.get("labels"),
                assignees=arguments.get("assignees"),
            )
            return ToolResult(tool_name=self.name, success=True, data=res, source="github_mcp")
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc), source="github_mcp")


class GitHubAddIssueCommentTool(BaseTool):
    name = "github_add_issue_comment"
    description = "Add a comment to a GitHub issue or pull request. Requires user confirmation."
    category = "github"
    permissions = [ToolPermission.NETWORK, ToolPermission.USER_DATA]
    parameters = {
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "Repository owner (optional if authenticated)"},
            "repo": {"type": "string", "description": "Repository name"},
            "issue_number": {"type": "integer", "description": "Issue or PR number"},
            "body": {"type": "string", "description": "Markdown comment text"},
            "confirmed": {"type": "boolean", "default": False, "description": "Must be true to post comment."},
        },
        "required": ["repo", "issue_number", "body"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        token, err_res, _ = await _get_token_or_error(context)
        if err_res:
            return err_res

        service = get_github_service()
        owner, repo = await _resolve_owner_and_repo(arguments, token)
        if not owner or not repo:
            return ToolResult(tool_name=self.name, success=False, error="Both repository name and owner must be provided.", source="github_mcp")

        conf_res = _check_write_confirmation(
            self.name,
            f"Post comment on issue #{arguments['issue_number']} in {owner}/{repo}",
            arguments,
        )
        if conf_res:
            return conf_res

        try:
            res = await service.add_issue_comment(
                token=token,
                owner=owner,
                repo=repo,
                issue_number=int(arguments["issue_number"]),
                body=arguments["body"],
            )
            return ToolResult(tool_name=self.name, success=True, data=res, source="github_mcp")
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc), source="github_mcp")


# =============================================================================
# 4. PULL REQUESTS
# =============================================================================

class GitHubListPullRequestsTool(BaseTool):
    name = "github_list_pull_requests"
    description = "List pull requests in a GitHub repository."
    category = "github"
    permissions = [ToolPermission.NETWORK]
    parameters = {
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "Repository owner (optional if authenticated)"},
            "repo": {"type": "string", "description": "Repository name"},
            "state": {"type": "string", "enum": ["open", "closed", "all"], "default": "open"},
            "head": {"type": "string", "description": "Filter by head branch (e.g. 'user:feature-branch')"},
            "base": {"type": "string", "description": "Filter by base branch (e.g. 'main')"},
            "per_page": {"type": "integer", "default": 20},
        },
        "required": ["repo"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        token, err_res, _ = await _get_token_or_error(context)
        if err_res:
            return err_res

        service = get_github_service()
        owner, repo = await _resolve_owner_and_repo(arguments, token)
        if not owner or not repo:
            return ToolResult(tool_name=self.name, success=False, error="Both repository name and owner must be provided.", source="github_mcp")
        try:
            res = await service.list_pull_requests(
                token=token,
                owner=owner,
                repo=repo,
                state=arguments.get("state", "open"),
                head=arguments.get("head"),
                base=arguments.get("base"),
                per_page=arguments.get("per_page", 20),
            )
            return ToolResult(tool_name=self.name, success=True, data={"pull_requests": res, "count": len(res)}, source="github_mcp")
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc), source="github_mcp")


class GitHubGetPullRequestTool(BaseTool):
    name = "github_get_pull_request"
    description = "Get detailed information about a specific pull request including changed files, additions, and merge status."
    category = "github"
    permissions = [ToolPermission.NETWORK]
    parameters = {
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "Repository owner (optional if authenticated)"},
            "repo": {"type": "string", "description": "Repository name"},
            "pull_number": {"type": "integer", "description": "Pull request number"},
        },
        "required": ["repo", "pull_number"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        token, err_res, _ = await _get_token_or_error(context)
        if err_res:
            return err_res

        service = get_github_service()
        owner, repo = await _resolve_owner_and_repo(arguments, token)
        if not owner or not repo:
            return ToolResult(tool_name=self.name, success=False, error="Both repository name and owner must be provided.", source="github_mcp")
        try:
            res = await service.get_pull_request(
                token=token,
                owner=owner,
                repo=repo,
                pull_number=int(arguments["pull_number"]),
            )
            return ToolResult(tool_name=self.name, success=True, data=res, source="github_mcp")
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc), source="github_mcp")


class GitHubCreatePullRequestTool(BaseTool):
    name = "github_create_pull_request"
    description = "Create a new pull request in a GitHub repository. Requires user confirmation."
    category = "github"
    permissions = [ToolPermission.NETWORK, ToolPermission.USER_DATA]
    parameters = {
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "Repository owner (optional if authenticated)"},
            "repo": {"type": "string", "description": "Repository name"},
            "title": {"type": "string", "description": "Pull request title"},
            "head": {"type": "string", "description": "The branch where changes are implemented (e.g. 'feature-auth')"},
            "base": {"type": "string", "default": "main", "description": "The target branch to merge into (e.g. 'main', 'master')"},
            "body": {"type": "string", "description": "Pull request description / overview of changes"},
            "draft": {"type": "boolean", "default": False, "description": "Whether to create as draft PR"},
            "confirmed": {"type": "boolean", "default": False, "description": "Must be true to open the pull request."},
        },
        "required": ["repo", "title", "head"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        token, err_res, _ = await _get_token_or_error(context)
        if err_res:
            return err_res

        service = get_github_service()
        owner, repo = await _resolve_owner_and_repo(arguments, token)
        if not owner or not repo:
            return ToolResult(tool_name=self.name, success=False, error="Both repository name and owner must be provided.", source="github_mcp")

        conf_res = _check_write_confirmation(
            self.name,
            f"Create pull request '{arguments['title']}' ({arguments['head']} -> {arguments.get('base', 'main')}) in {owner}/{repo}",
            arguments,
        )
        if conf_res:
            return conf_res

        try:
            res = await service.create_pull_request(
                token=token,
                owner=owner,
                repo=repo,
                title=arguments["title"],
                head=arguments["head"],
                base=arguments.get("base", "main"),
                body=arguments.get("body", ""),
                draft=arguments.get("draft", False),
            )
            return ToolResult(tool_name=self.name, success=True, data=res, source="github_mcp")
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc), source="github_mcp")


class GitHubMergePullRequestTool(BaseTool):
    name = "github_merge_pull_request"
    description = "Merge a pull request into base branch. Requires user confirmation."
    category = "github"
    permissions = [ToolPermission.NETWORK, ToolPermission.USER_DATA]
    parameters = {
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "Repository owner (optional if authenticated)"},
            "repo": {"type": "string", "description": "Repository name"},
            "pull_number": {"type": "integer", "description": "Pull request number"},
            "commit_title": {"type": "string", "description": "Optional title for merge commit"},
            "commit_message": {"type": "string", "description": "Optional commit message"},
            "merge_method": {"type": "string", "enum": ["merge", "squash", "rebase"], "default": "merge"},
            "confirmed": {"type": "boolean", "default": False, "description": "Must be true to merge the pull request."},
        },
        "required": ["repo", "pull_number"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        token, err_res, _ = await _get_token_or_error(context)
        if err_res:
            return err_res

        service = get_github_service()
        owner, repo = await _resolve_owner_and_repo(arguments, token)
        if not owner or not repo:
            return ToolResult(tool_name=self.name, success=False, error="Both repository name and owner must be provided.", source="github_mcp")

        conf_res = _check_write_confirmation(
            self.name,
            f"Merge pull request #{arguments['pull_number']} into {owner}/{repo} (Method: {arguments.get('merge_method', 'merge')})",
            arguments,
        )
        if conf_res:
            return conf_res

        try:
            res = await service.merge_pull_request(
                token=token,
                owner=owner,
                repo=repo,
                pull_number=int(arguments["pull_number"]),
                commit_title=arguments.get("commit_title"),
                commit_message=arguments.get("commit_message"),
                merge_method=arguments.get("merge_method", "merge"),
            )
            return ToolResult(tool_name=self.name, success=True, data=res, source="github_mcp")
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc), source="github_mcp")


# =============================================================================
# 5. BRANCHES & COMMITS
# =============================================================================

class GitHubListBranchesTool(BaseTool):
    name = "github_list_branches"
    description = "List branches in a GitHub repository."
    category = "github"
    permissions = [ToolPermission.NETWORK]
    parameters = {
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "Repository owner (optional if authenticated)"},
            "repo": {"type": "string", "description": "Repository name"},
            "per_page": {"type": "integer", "default": 30},
        },
        "required": ["repo"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        token, err_res, _ = await _get_token_or_error(context)
        if err_res:
            return err_res

        service = get_github_service()
        owner, repo = await _resolve_owner_and_repo(arguments, token)
        if not owner or not repo:
            return ToolResult(tool_name=self.name, success=False, error="Both repository name and owner must be provided.", source="github_mcp")
        try:
            res = await service.list_branches(
                token=token,
                owner=owner,
                repo=repo,
                per_page=arguments.get("per_page", 30),
            )
            return ToolResult(tool_name=self.name, success=True, data={"branches": res, "count": len(res)}, source="github_mcp")
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc), source="github_mcp")


class GitHubCreateBranchTool(BaseTool):
    name = "github_create_branch"
    description = "Create a new branch in a repository. Requires user confirmation."
    category = "github"
    permissions = [ToolPermission.NETWORK, ToolPermission.USER_DATA]
    parameters = {
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "Repository owner (optional if authenticated)"},
            "repo": {"type": "string", "description": "Repository name"},
            "branch": {"type": "string", "description": "Name of the new branch"},
            "from_branch": {"type": "string", "default": "main", "description": "Base branch to branch off from (e.g. 'main')"},
            "confirmed": {"type": "boolean", "default": False, "description": "Must be true to create the branch."},
        },
        "required": ["repo", "branch"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        token, err_res, _ = await _get_token_or_error(context)
        if err_res:
            return err_res

        service = get_github_service()
        owner, repo = await _resolve_owner_and_repo(arguments, token)
        if not owner or not repo:
            return ToolResult(tool_name=self.name, success=False, error="Both repository name and owner must be provided.", source="github_mcp")

        conf_res = _check_write_confirmation(
            self.name,
            f"Create branch '{arguments['branch']}' from '{arguments.get('from_branch', 'main')}' in {owner}/{repo}",
            arguments,
        )
        if conf_res:
            return conf_res

        try:
            res = await service.create_branch(
                token=token,
                owner=owner,
                repo=repo,
                branch=arguments["branch"],
                from_branch=arguments.get("from_branch", "main"),
            )
            return ToolResult(tool_name=self.name, success=True, data=res, source="github_mcp")
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc), source="github_mcp")


class GitHubListCommitsTool(BaseTool):
    name = "github_list_commits"
    description = "List recent commits in a repository with author, message, and date."
    category = "github"
    permissions = [ToolPermission.NETWORK]
    parameters = {
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "Repository owner (optional if authenticated)"},
            "repo": {"type": "string", "description": "Repository name"},
            "sha": {"type": "string", "description": "Branch name or commit SHA to start listing from"},
            "path": {"type": "string", "description": "Only commits containing this file path"},
            "author": {"type": "string", "description": "GitHub username or email address of author"},
            "per_page": {"type": "integer", "default": 20},
        },
        "required": ["repo"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        token, err_res, _ = await _get_token_or_error(context)
        if err_res:
            return err_res

        service = get_github_service()
        owner, repo = await _resolve_owner_and_repo(arguments, token)
        if not owner or not repo:
            return ToolResult(tool_name=self.name, success=False, error="Both repository name and owner must be provided.", source="github_mcp")
        try:
            res = await service.list_commits(
                token=token,
                owner=owner,
                repo=repo,
                sha=arguments.get("sha"),
                path=arguments.get("path"),
                author=arguments.get("author"),
                per_page=arguments.get("per_page", 20),
            )
            return ToolResult(tool_name=self.name, success=True, data={"commits": res, "count": len(res)}, source="github_mcp")
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc), source="github_mcp")


# =============================================================================
# 6. GITHUB ACTIONS (WORKFLOWS)
# =============================================================================

class GitHubListWorkflowsTool(BaseTool):
    name = "github_list_workflows"
    description = "List GitHub Actions workflows defined in a repository."
    category = "github"
    permissions = [ToolPermission.NETWORK]
    parameters = {
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "Repository owner (optional if authenticated)"},
            "repo": {"type": "string", "description": "Repository name"},
        },
        "required": ["repo"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        token, err_res, _ = await _get_token_or_error(context)
        if err_res:
            return err_res

        service = get_github_service()
        owner, repo = await _resolve_owner_and_repo(arguments, token)
        if not owner or not repo:
            return ToolResult(tool_name=self.name, success=False, error="Both repository name and owner must be provided.", source="github_mcp")
        try:
            res = await service.list_workflows(token=token, owner=owner, repo=repo)
            return ToolResult(tool_name=self.name, success=True, data=res, source="github_mcp")
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc), source="github_mcp")


class GitHubListWorkflowRunsTool(BaseTool):
    name = "github_list_workflow_runs"
    description = "List recent GitHub Actions workflow runs and their conclusion status (success/failure)."
    category = "github"
    permissions = [ToolPermission.NETWORK]
    parameters = {
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "Repository owner (optional if authenticated)"},
            "repo": {"type": "string", "description": "Repository name"},
            "workflow_id": {"type": "string", "description": "Optional workflow ID or filename (e.g. 'ci.yml')"},
            "status": {"type": "string", "enum": ["completed", "in_progress", "queued"], "description": "Filter by status"},
            "per_page": {"type": "integer", "default": 10},
        },
        "required": ["repo"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        token, err_res, _ = await _get_token_or_error(context)
        if err_res:
            return err_res

        service = get_github_service()
        owner, repo = await _resolve_owner_and_repo(arguments, token)
        if not owner or not repo:
            return ToolResult(tool_name=self.name, success=False, error="Both repository name and owner must be provided.", source="github_mcp")
        try:
            res = await service.list_workflow_runs(
                token=token,
                owner=owner,
                repo=repo,
                workflow_id=arguments.get("workflow_id"),
                status=arguments.get("status"),
                per_page=arguments.get("per_page", 10),
            )
            return ToolResult(tool_name=self.name, success=True, data=res, source="github_mcp")
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc), source="github_mcp")


class GitHubDispatchWorkflowTool(BaseTool):
    name = "github_dispatch_workflow"
    description = "Manually trigger a GitHub Actions workflow run via workflow_dispatch event. Requires user confirmation."
    category = "github"
    permissions = [ToolPermission.NETWORK, ToolPermission.USER_DATA]
    parameters = {
        "type": "object",
        "properties": {
            "owner": {"type": "string", "description": "Repository owner (optional if authenticated)"},
            "repo": {"type": "string", "description": "Repository name"},
            "workflow_id": {"type": "string", "description": "Workflow ID or workflow file name (e.g. 'deploy.yml', '123456')"},
            "ref": {"type": "string", "default": "main", "description": "Git branch or tag to run workflow against"},
            "inputs": {"type": "object", "description": "Optional key-value input parameters for the workflow"},
            "confirmed": {"type": "boolean", "default": False, "description": "Must be true to trigger the workflow execution."},
        },
        "required": ["repo", "workflow_id"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        token, err_res, _ = await _get_token_or_error(context)
        if err_res:
            return err_res

        service = get_github_service()
        owner, repo = await _resolve_owner_and_repo(arguments, token)
        if not owner or not repo:
            return ToolResult(tool_name=self.name, success=False, error="Both repository name and owner must be provided.", source="github_mcp")

        conf_res = _check_write_confirmation(
            self.name,
            f"Trigger GitHub Action workflow '{arguments['workflow_id']}' on branch '{arguments.get('ref', 'main')}' in {owner}/{repo}",
            arguments,
        )
        if conf_res:
            return conf_res

        try:
            res = await service.dispatch_workflow(
                token=token,
                owner=owner,
                repo=repo,
                workflow_id=arguments["workflow_id"],
                ref=arguments.get("ref", "main"),
                inputs=arguments.get("inputs"),
            )
            return ToolResult(tool_name=self.name, success=True, data=res, source="github_mcp")
        except Exception as exc:
            return ToolResult(tool_name=self.name, success=False, error=str(exc), source="github_mcp")


def get_github_tools() -> List[BaseTool]:
    """Dynamically construct and return list of all GitHub MCP tools."""
    return [
        GitHubSearchRepositoriesTool(),
        GitHubGetRepositoryTool(),
        GitHubListUserRepositoriesTool(),
        GitHubCreateRepositoryTool(),
        GitHubGetFileContentsTool(),
        GitHubCreateOrUpdateFileTool(),
        GitHubDeleteFileTool(),
        GitHubListIssuesTool(),
        GitHubGetIssueTool(),
        GitHubCreateIssueTool(),
        GitHubAddIssueCommentTool(),
        GitHubListPullRequestsTool(),
        GitHubGetPullRequestTool(),
        GitHubCreatePullRequestTool(),
        GitHubMergePullRequestTool(),
        GitHubListBranchesTool(),
        GitHubCreateBranchTool(),
        GitHubListCommitsTool(),
        GitHubListWorkflowsTool(),
        GitHubListWorkflowRunsTool(),
        GitHubDispatchWorkflowTool(),
    ]
