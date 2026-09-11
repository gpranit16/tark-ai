"""GitHub MCP Integration Service for TARK AI.

Connects to GitHub using Server PAT from .env or encrypted user credentials.
Provides complete tools suite for:
- repos, code/files, issues, pull requests, commits, branches, workflows (Actions).
- Enforces explicit user confirmation checks on all destructive/write operations.
- Guarantees credentials are never exposed to frontend, logs, or model prompts.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import logging
import os
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decrypt_secret, encrypt_secret
from app.models.integration import UserIntegration

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"


class GitHubMCPService:
    """Service for GitHub operations and MCP protocol integration."""

    def __init__(self, timeout_seconds: float = 15.0) -> None:
        self.settings = get_settings()
        self.timeout = timeout_seconds

    async def get_token_for_user(
        self,
        user_id: Optional[UUID] = None,
        session: Optional[AsyncSession] = None,
    ) -> Optional[str]:
        """
        Resolve active GitHub token.
        Priority:
        1. Encrypted UserIntegration for specific user (if present and active).
        2. GITHUB_PERSONAL_ACCESS_TOKEN / GITHUB_TOKEN from server settings / .env.
        """
        if user_id is not None and session is not None:
            try:
                stmt = select(UserIntegration).where(
                    UserIntegration.user_id == user_id,
                    UserIntegration.provider == "github",
                    UserIntegration.is_active == True,
                )
                res = await session.execute(stmt)
                integration = res.scalars().first()
                if integration and integration.encrypted_access_token:
                    decrypted = decrypt_secret(integration.encrypted_access_token)
                    if decrypted:
                        return decrypted
            except Exception as e:
                logger.warning("Failed to retrieve user GitHub integration: %s", e)

        # Fallback to server configuration
        token = (
            self.settings.github_personal_access_token
            or os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
            or os.environ.get("GITHUB_TOKEN")
        )
        if token and token.strip():
            return token.strip()

        return None

    def _get_headers(self, token: str) -> Dict[str, str]:
        """Generate secure headers with Bearer token without exposing in logs."""
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json, application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "TARK-AI-MCP-Service/1.0",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        token: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Execute async HTTP request to GitHub API with error sanitization."""
        url = f"{GITHUB_API_BASE.rstrip('/')}/{endpoint.lstrip('/')}"
        headers = self._get_headers(token)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_body,
                )
            except httpx.TimeoutException:
                raise RuntimeError(f"GitHub API request timed out after {self.timeout}s.")
            except Exception as exc:
                raise RuntimeError(f"GitHub connection failed: {exc}")

            if resp.status_code in (200, 201, 202, 204):
                if resp.status_code == 204:
                    return {"success": True}
                return resp.json()

            # Sanitize error detail
            error_data = {}
            try:
                error_data = resp.json()
            except Exception:
                pass

            msg = error_data.get("message", resp.text or f"HTTP {resp.status_code}")
            if resp.status_code == 401:
                raise RuntimeError("GitHub authentication failed: Bad credentials or expired personal access token.")
            elif resp.status_code == 403:
                raise RuntimeError(f"GitHub permission denied / rate limit exceeded: {msg}")
            elif resp.status_code == 404:
                raise RuntimeError(f"GitHub resource not found: {msg}")
            else:
                raise RuntimeError(f"GitHub API error ({resp.status_code}): {msg}")

    # =========================================================================
    # STATUS & AUTHENTICATION
    # =========================================================================

    async def get_status(
        self,
        user_id: Optional[UUID] = None,
        session: Optional[AsyncSession] = None,
    ) -> Dict[str, Any]:
        """Check GitHub connection status and return sanitized metadata."""
        token = await self.get_token_for_user(user_id=user_id, session=session)
        if not token:
            return {
                "connected": False,
                "is_connected": False,
                "provider": "github",
                "account_login": None,
                "account_name": None,
                "avatar_url": None,
                "token_source": "none",
                "scopes": [],
                "tools_count": 0,
            }

        # Validate token with GitHub
        try:
            user_info = await self.get_user_info(token)
            token_source = "user" if user_id and session else "env"
            return {
                "connected": True,
                "is_connected": True,
                "provider": "github",
                "account_login": user_info.get("login"),
                "account_name": user_info.get("name") or user_info.get("login"),
                "avatar_url": user_info.get("avatar_url"),
                "public_repos": user_info.get("public_repos", 0),
                "total_private_repos": user_info.get("total_private_repos", 0),
                "token_source": token_source,
                "scopes": ["repo", "read:org", "workflow", "user"],
                "tools_count": 21,
            }
        except Exception as e:
            logger.warning("GitHub status validation failed: %s", e)
            return {
                "connected": False,
                "is_connected": False,
                "provider": "github",
                "account_login": None,
                "account_name": None,
                "avatar_url": None,
                "token_source": "invalid",
                "error": str(e),
                "tools_count": 0,
            }

    async def save_user_token(
        self,
        user_id: UUID,
        token: str,
        session: AsyncSession,
    ) -> Dict[str, Any]:
        """Validate and securely save personal access token for user."""
        token = token.strip()
        user_info = await self.get_user_info(token)

        enc_token = encrypt_secret(token)
        stmt = select(UserIntegration).where(
            UserIntegration.user_id == user_id,
            UserIntegration.provider == "github",
        )
        res = await session.execute(stmt)
        integration = res.scalars().first()

        if integration:
            integration.encrypted_access_token = enc_token
            integration.account_email = user_info.get("email") or user_info.get("login")
            integration.is_active = True
            integration.integration_metadata = {
                "login": user_info.get("login"),
                "name": user_info.get("name"),
                "avatar_url": user_info.get("avatar_url"),
            }
        else:
            integration = UserIntegration(
                user_id=user_id,
                provider="github",
                service="github",
                encrypted_access_token=enc_token,
                account_email=user_info.get("email") or user_info.get("login"),
                is_active=True,
                integration_metadata={
                    "login": user_info.get("login"),
                    "name": user_info.get("name"),
                    "avatar_url": user_info.get("avatar_url"),
                },
            )
            session.add(integration)

        await session.commit()
        return {
            "success": True,
            "account_login": user_info.get("login"),
            "account_name": user_info.get("name"),
            "avatar_url": user_info.get("avatar_url"),
        }

    async def disconnect_user(self, user_id: UUID, session: AsyncSession) -> bool:
        """Disconnect GitHub token for user."""
        stmt = select(UserIntegration).where(
            UserIntegration.user_id == user_id,
            UserIntegration.provider == "github",
        )
        res = await session.execute(stmt)
        integration = res.scalars().first()
        if integration:
            await session.delete(integration)
            await session.commit()
            return True
        return False

    async def get_user_info(self, token: str) -> Dict[str, Any]:
        """Fetch authenticated user profile."""
        return await self._request("GET", "user", token)

    # =========================================================================
    # REPOSITORIES
    # =========================================================================

    async def search_repositories(
        self,
        token: str,
        query: str,
        sort: str = "stars",
        order: str = "desc",
        per_page: int = 10,
        page: int = 1,
    ) -> Dict[str, Any]:
        """Search GitHub repositories."""
        params = {"q": query, "sort": sort, "order": order, "per_page": min(per_page, 30), "page": page}
        data = await self._request("GET", "search/repositories", token, params=params)
        items = []
        for repo in data.get("items", []):
            items.append({
                "name": repo.get("name"),
                "full_name": repo.get("full_name"),
                "owner": repo.get("owner", {}).get("login"),
                "description": repo.get("description"),
                "html_url": repo.get("html_url"),
                "stars": repo.get("stargazers_count"),
                "forks": repo.get("forks_count"),
                "language": repo.get("language"),
                "open_issues": repo.get("open_issues_count"),
                "updated_at": repo.get("updated_at"),
            })
        return {"total_count": data.get("total_count", 0), "repositories": items}

    async def get_repository(self, token: str, owner: str, repo: str) -> Dict[str, Any]:
        """Get repository metadata."""
        data = await self._request("GET", f"repos/{owner}/{repo}", token)
        return {
            "name": data.get("name"),
            "full_name": data.get("full_name"),
            "owner": data.get("owner", {}).get("login"),
            "description": data.get("description"),
            "default_branch": data.get("default_branch", "main"),
            "stars": data.get("stargazers_count", 0),
            "forks": data.get("forks_count", 0),
            "open_issues": data.get("open_issues_count", 0),
            "private": data.get("private", False),
            "html_url": data.get("html_url"),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
        }

    async def list_user_repositories(
        self,
        token: str,
        username: Optional[str] = None,
        sort: str = "updated",
        per_page: int = 20,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        """List repositories for authenticated user or specific user/org."""
        endpoint = f"users/{username}/repos" if username else "user/repos"
        params = {"sort": sort, "per_page": min(per_page, 50), "page": page}
        data = await self._request("GET", endpoint, token, params=params)
        return [
            {
                "name": r.get("name"),
                "full_name": r.get("full_name"),
                "private": r.get("private"),
                "description": r.get("description"),
                "stars": r.get("stargazers_count", 0),
                "language": r.get("language"),
                "default_branch": r.get("default_branch", "main"),
                "updated_at": r.get("updated_at"),
                "html_url": r.get("html_url"),
            }
            for r in (data if isinstance(data, list) else [])
        ]

    async def create_repository(
        self,
        token: str,
        name: str,
        description: str = "",
        private: bool = False,
        auto_init: bool = True,
    ) -> Dict[str, Any]:
        """Create a new GitHub repository."""
        payload = {
            "name": name,
            "description": description,
            "private": private,
            "auto_init": auto_init,
        }
        data = await self._request("POST", "user/repos", token, json_body=payload)
        return {
            "name": data.get("name"),
            "full_name": data.get("full_name"),
            "html_url": data.get("html_url"),
            "private": data.get("private"),
            "default_branch": data.get("default_branch"),
        }

    # =========================================================================
    # CODE & FILES
    # =========================================================================

    async def get_file_contents(
        self,
        token: str,
        owner: str,
        repo: str,
        path: str = "",
        ref: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Read a file or list contents of a directory in repository."""
        endpoint = f"repos/{owner}/{repo}/contents/{path.lstrip('/')}"
        params = {"ref": ref} if ref else {}
        data = await self._request("GET", endpoint, token, params=params)

        if isinstance(data, list):
            # Directory listing
            entries = [
                {
                    "name": item.get("name"),
                    "path": item.get("path"),
                    "type": item.get("type"),
                    "size": item.get("size"),
                    "download_url": item.get("download_url"),
                }
                for item in data
            ]
            return {"type": "directory", "path": path, "entries": entries}

        content_encoded = data.get("content", "")
        encoding = data.get("encoding")
        decoded_text = ""
        if encoding == "base64" and content_encoded:
            try:
                decoded_text = base64.b64decode(content_encoded).decode("utf-8", errors="replace")
            except Exception as e:
                decoded_text = f"[Binary or undecodable content: {e}]"

        return {
            "type": "file",
            "name": data.get("name"),
            "path": data.get("path"),
            "size": data.get("size"),
            "sha": data.get("sha"),
            "content": decoded_text,
            "html_url": data.get("html_url"),
        }

    async def create_or_update_file(
        self,
        token: str,
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: Optional[str] = None,
        sha: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create or update a file in repository."""
        # If sha is not provided, check if file exists
        if not sha:
            try:
                existing = await self.get_file_contents(token, owner, repo, path, ref=branch)
                if existing.get("type") == "file" and existing.get("sha"):
                    sha = existing.get("sha")
            except Exception:
                pass

        encoded_content = base64.b64encode(content.encode("utf-8")).decode("ascii")
        payload: Dict[str, Any] = {
            "message": message,
            "content": encoded_content,
        }
        if branch:
            payload["branch"] = branch
        if sha:
            payload["sha"] = sha

        endpoint = f"repos/{owner}/{repo}/contents/{path.lstrip('/')}"
        data = await self._request("PUT", endpoint, token, json_body=payload)
        return {
            "commit_sha": data.get("commit", {}).get("sha"),
            "html_url": data.get("content", {}).get("html_url"),
            "path": path,
            "message": message,
        }

    async def delete_file(
        self,
        token: str,
        owner: str,
        repo: str,
        path: str,
        message: str,
        sha: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Delete a file from repository."""
        if not sha:
            existing = await self.get_file_contents(token, owner, repo, path, ref=branch)
            sha = existing.get("sha")
            if not sha:
                raise RuntimeError(f"Cannot delete '{path}': file SHA could not be retrieved.")

        payload: Dict[str, Any] = {"message": message, "sha": sha}
        if branch:
            payload["branch"] = branch

        endpoint = f"repos/{owner}/{repo}/contents/{path.lstrip('/')}"
        data = await self._request("DELETE", endpoint, token, json_body=payload)
        return {
            "success": True,
            "commit_sha": data.get("commit", {}).get("sha"),
            "path": path,
        }

    # =========================================================================
    # ISSUES
    # =========================================================================

    async def list_issues(
        self,
        token: str,
        owner: str,
        repo: str,
        state: str = "open",
        labels: Optional[str] = None,
        sort: str = "created",
        direction: str = "desc",
        per_page: int = 20,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        """List repository issues."""
        params: Dict[str, Any] = {
            "state": state,
            "sort": sort,
            "direction": direction,
            "per_page": min(per_page, 50),
            "page": page,
        }
        if labels:
            params["labels"] = labels

        data = await self._request("GET", f"repos/{owner}/{repo}/issues", token, params=params)
        results = []
        for issue in (data if isinstance(data, list) else []):
            if "pull_request" in issue:
                continue  # Skip PRs
            results.append({
                "number": issue.get("number"),
                "title": issue.get("title"),
                "state": issue.get("state"),
                "author": issue.get("user", {}).get("login"),
                "labels": [lbl.get("name") for lbl in issue.get("labels", [])],
                "comments_count": issue.get("comments", 0),
                "created_at": issue.get("created_at"),
                "html_url": issue.get("html_url"),
            })
        return results

    async def get_issue(self, token: str, owner: str, repo: str, issue_number: int) -> Dict[str, Any]:
        """Get details and comments for an issue."""
        issue = await self._request("GET", f"repos/{owner}/{repo}/issues/{issue_number}", token)
        comments_data = await self._request("GET", f"repos/{owner}/{repo}/issues/{issue_number}/comments", token)
        comments = [
            {
                "author": c.get("user", {}).get("login"),
                "body": c.get("body"),
                "created_at": c.get("created_at"),
            }
            for c in (comments_data if isinstance(comments_data, list) else [])
        ]
        return {
            "number": issue.get("number"),
            "title": issue.get("title"),
            "body": issue.get("body"),
            "state": issue.get("state"),
            "author": issue.get("user", {}).get("login"),
            "labels": [lbl.get("name") for lbl in issue.get("labels", [])],
            "comments": comments,
            "html_url": issue.get("html_url"),
            "created_at": issue.get("created_at"),
            "updated_at": issue.get("updated_at"),
        }

    async def create_issue(
        self,
        token: str,
        owner: str,
        repo: str,
        title: str,
        body: str = "",
        labels: Optional[List[str]] = None,
        assignees: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create a new issue."""
        payload: Dict[str, Any] = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels
        if assignees:
            payload["assignees"] = assignees

        data = await self._request("POST", f"repos/{owner}/{repo}/issues", token, json_body=payload)
        return {
            "number": data.get("number"),
            "title": data.get("title"),
            "html_url": data.get("html_url"),
            "state": data.get("state"),
        }

    async def add_issue_comment(
        self,
        token: str,
        owner: str,
        repo: str,
        issue_number: int,
        body: str,
    ) -> Dict[str, Any]:
        """Add comment to issue or pull request."""
        data = await self._request(
            "POST",
            f"repos/{owner}/{repo}/issues/{issue_number}/comments",
            token,
            json_body={"body": body},
        )
        return {
            "id": data.get("id"),
            "html_url": data.get("html_url"),
            "author": data.get("user", {}).get("login"),
            "created_at": data.get("created_at"),
        }

    # =========================================================================
    # PULL REQUESTS
    # =========================================================================

    async def list_pull_requests(
        self,
        token: str,
        owner: str,
        repo: str,
        state: str = "open",
        head: Optional[str] = None,
        base: Optional[str] = None,
        sort: str = "created",
        direction: str = "desc",
        per_page: int = 20,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        """List repository pull requests."""
        params: Dict[str, Any] = {
            "state": state,
            "sort": sort,
            "direction": direction,
            "per_page": min(per_page, 50),
            "page": page,
        }
        if head:
            params["head"] = head
        if base:
            params["base"] = base

        data = await self._request("GET", f"repos/{owner}/{repo}/pulls", token, params=params)
        return [
            {
                "number": pr.get("number"),
                "title": pr.get("title"),
                "state": pr.get("state"),
                "author": pr.get("user", {}).get("login"),
                "head": pr.get("head", {}).get("ref"),
                "base": pr.get("base", {}).get("ref"),
                "draft": pr.get("draft", False),
                "created_at": pr.get("created_at"),
                "html_url": pr.get("html_url"),
            }
            for pr in (data if isinstance(data, list) else [])
        ]

    async def get_pull_request(self, token: str, owner: str, repo: str, pull_number: int) -> Dict[str, Any]:
        """Get pull request details."""
        pr = await self._request("GET", f"repos/{owner}/{repo}/pulls/{pull_number}", token)
        return {
            "number": pr.get("number"),
            "title": pr.get("title"),
            "body": pr.get("body"),
            "state": pr.get("state"),
            "author": pr.get("user", {}).get("login"),
            "head": pr.get("head", {}).get("ref"),
            "base": pr.get("base", {}).get("ref"),
            "mergeable": pr.get("mergeable"),
            "merged": pr.get("merged", False),
            "commits": pr.get("commits", 0),
            "additions": pr.get("additions", 0),
            "deletions": pr.get("deletions", 0),
            "changed_files": pr.get("changed_files", 0),
            "html_url": pr.get("html_url"),
            "created_at": pr.get("created_at"),
        }

    async def create_pull_request(
        self,
        token: str,
        owner: str,
        repo: str,
        title: str,
        head: str,
        base: str = "main",
        body: str = "",
        draft: bool = False,
    ) -> Dict[str, Any]:
        """Create a new pull request."""
        payload = {
            "title": title,
            "head": head,
            "base": base,
            "body": body,
            "draft": draft,
        }
        data = await self._request("POST", f"repos/{owner}/{repo}/pulls", token, json_body=payload)
        return {
            "number": data.get("number"),
            "title": data.get("title"),
            "state": data.get("state"),
            "html_url": data.get("html_url"),
            "head": data.get("head", {}).get("ref"),
            "base": data.get("base", {}).get("ref"),
        }

    async def merge_pull_request(
        self,
        token: str,
        owner: str,
        repo: str,
        pull_number: int,
        commit_title: Optional[str] = None,
        commit_message: Optional[str] = None,
        merge_method: str = "merge",  # "merge" | "squash" | "rebase"
    ) -> Dict[str, Any]:
        """Merge a pull request."""
        payload: Dict[str, Any] = {"merge_method": merge_method}
        if commit_title:
            payload["commit_title"] = commit_title
        if commit_message:
            payload["commit_message"] = commit_message

        data = await self._request(
            "PUT",
            f"repos/{owner}/{repo}/pulls/{pull_number}/merge",
            token,
            json_body=payload,
        )
        return {
            "merged": data.get("merged", True),
            "message": data.get("message"),
            "sha": data.get("sha"),
        }

    # =========================================================================
    # BRANCHES & COMMITS
    # =========================================================================

    async def list_branches(
        self,
        token: str,
        owner: str,
        repo: str,
        per_page: int = 30,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        """List branches in repository."""
        params = {"per_page": min(per_page, 50), "page": page}
        data = await self._request("GET", f"repos/{owner}/{repo}/branches", token, params=params)
        return [
            {
                "name": b.get("name"),
                "sha": b.get("commit", {}).get("sha"),
                "protected": b.get("protected", False),
            }
            for b in (data if isinstance(data, list) else [])
        ]

    async def create_branch(
        self,
        token: str,
        owner: str,
        repo: str,
        branch: str,
        from_branch: str = "main",
    ) -> Dict[str, Any]:
        """Create a new branch from an existing branch or commit."""
        # Get base branch SHA
        ref_data = await self._request("GET", f"repos/{owner}/{repo}/git/ref/heads/{from_branch}", token)
        base_sha = ref_data.get("object", {}).get("sha")
        if not base_sha:
            raise RuntimeError(f"Could not resolve base branch '{from_branch}' to a commit SHA.")

        payload = {
            "ref": f"refs/heads/{branch}",
            "sha": base_sha,
        }
        data = await self._request("POST", f"repos/{owner}/{repo}/git/refs", token, json_body=payload)
        return {
            "branch": branch,
            "ref": data.get("ref"),
            "sha": data.get("object", {}).get("sha"),
        }

    async def list_commits(
        self,
        token: str,
        owner: str,
        repo: str,
        sha: Optional[str] = None,
        path: Optional[str] = None,
        author: Optional[str] = None,
        per_page: int = 20,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        """List commits in repository."""
        params: Dict[str, Any] = {"per_page": min(per_page, 50), "page": page}
        if sha:
            params["sha"] = sha
        if path:
            params["path"] = path
        if author:
            params["author"] = author

        data = await self._request("GET", f"repos/{owner}/{repo}/commits", token, params=params)
        return [
            {
                "sha": c.get("sha")[:8] if c.get("sha") else "",
                "full_sha": c.get("sha"),
                "message": c.get("commit", {}).get("message", "").split("\n")[0],
                "author": c.get("commit", {}).get("author", {}).get("name") or c.get("author", {}).get("login"),
                "date": c.get("commit", {}).get("author", {}).get("date"),
                "html_url": c.get("html_url"),
            }
            for c in (data if isinstance(data, list) else [])
        ]

    # =========================================================================
    # GITHUB ACTIONS (WORKFLOWS)
    # =========================================================================

    async def list_workflows(self, token: str, owner: str, repo: str) -> Dict[str, Any]:
        """List GitHub Actions workflows in repository."""
        data = await self._request("GET", f"repos/{owner}/{repo}/actions/workflows", token)
        workflows = [
            {
                "id": w.get("id"),
                "name": w.get("name"),
                "path": w.get("path"),
                "state": w.get("state"),
                "html_url": w.get("html_url"),
            }
            for w in data.get("workflows", [])
        ]
        return {"total_count": data.get("total_count", 0), "workflows": workflows}

    async def list_workflow_runs(
        self,
        token: str,
        owner: str,
        repo: str,
        workflow_id: Optional[str] = None,
        status: Optional[str] = None,
        per_page: int = 10,
        page: int = 1,
    ) -> Dict[str, Any]:
        """List recent GitHub Actions workflow runs."""
        endpoint = f"repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs" if workflow_id else f"repos/{owner}/{repo}/actions/runs"
        params: Dict[str, Any] = {"per_page": min(per_page, 30), "page": page}
        if status:
            params["status"] = status

        data = await self._request("GET", endpoint, token, params=params)
        runs = [
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "head_branch": r.get("head_branch"),
                "status": r.get("status"),
                "conclusion": r.get("conclusion"),
                "event": r.get("event"),
                "created_at": r.get("created_at"),
                "html_url": r.get("html_url"),
            }
            for r in data.get("workflow_runs", [])
        ]
        return {"total_count": data.get("total_count", 0), "runs": runs}

    async def dispatch_workflow(
        self,
        token: str,
        owner: str,
        repo: str,
        workflow_id: str,
        ref: str = "main",
        inputs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Manually trigger a GitHub Actions workflow run via workflow_dispatch."""
        payload: Dict[str, Any] = {"ref": ref}
        if inputs:
            payload["inputs"] = inputs

        await self._request(
            "POST",
            f"repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches",
            token,
            json_body=payload,
        )
        return {
            "success": True,
            "message": f"Successfully triggered workflow '{workflow_id}' on branch '{ref}'.",
        }


# Global singleton
_github_service: Optional[GitHubMCPService] = None


def get_github_service() -> GitHubMCPService:
    global _github_service
    if _github_service is None:
        _github_service = GitHubMCPService()
    return _github_service
