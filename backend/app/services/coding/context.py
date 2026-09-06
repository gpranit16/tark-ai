"""CodeContextBuilder for Phase 12 Coding Mode & Code Workspace.

Assembles focused, file-aware code context respecting workspace boundaries,
project instructions, memory, and RAG knowledge.
"""
from __future__ import annotations

import os
import re
from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import MessageRole
from app.models.conversation import Message, Project
from app.models.file import File
from app.providers.base import NormalizedMessage
from app.services.coding.system_prompt import build_coding_system_prompt
from app.storage.factory import get_storage_provider


EXTENSION_LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "jsx",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".html": "html",
    ".css": "css",
    ".json": "json",
    ".sql": "sql",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".xml": "xml",
    ".java": "java",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".go": "go",
    ".rs": "rust",
    ".php": "php",
    ".sh": "bash",
    ".bash": "bash",
    ".toml": "toml",
    ".ini": "ini",
    ".graphql": "graphql",
    ".md": "markdown",
    ".txt": "text",
}


def detect_language(filename: str) -> str:
    """Detect programming language from filename extension."""
    ext = os.path.splitext(filename)[1].lower()
    return EXTENSION_LANGUAGE_MAP.get(ext, "text")


def extract_code_symbols(content: str, language: str) -> list[str]:
    """Extract key symbols (classes, functions, routes, imports) for quick structural awareness."""
    symbols: list[str] = []
    lines = content.splitlines()

    for line in lines[:300]:  # scan top lines for fast inspection
        stripped = line.strip()
        if language == "python":
            if stripped.startswith("import ") or stripped.startswith("from "):
                symbols.append(stripped)
            elif stripped.startswith("def ") or stripped.startswith("async def "):
                match = re.match(r"(?:async\s+)?def\s+([a-zA-Z0-9_]+)", stripped)
                if match:
                    symbols.append(f"def {match.group(1)}()")
            elif stripped.startswith("class "):
                match = re.match(r"class\s+([a-zA-Z0-9_]+)", stripped)
                if match:
                    symbols.append(f"class {match.group(1)}")
            elif stripped.startswith("@"):
                symbols.append(stripped)
        elif language in ("javascript", "typescript", "jsx", "tsx"):
            if stripped.startswith("import ") or stripped.startswith("export "):
                symbols.append(stripped)
            elif stripped.startswith("function ") or "=>" in stripped:
                match = re.match(r"(?:export\s+)?(?:default\s+)?function\s+([a-zA-Z0-9_]+)", stripped)
                if match:
                    symbols.append(f"function {match.group(1)}()")
            elif stripped.startswith("class "):
                match = re.match(r"class\s+([a-zA-Z0-9_]+)", stripped)
                if match:
                    symbols.append(f"class {match.group(1)}")

    return symbols[:15]


class CodeContextBuilder:
    """Builds a rich, bounded code context from attached files and project resources."""

    def __init__(
        self,
        *,
        project: Optional[Project] = None,
        memory_context: Optional[str] = None,
        rag_context: Optional[str] = None,
        thread_summary: Optional[str] = None,
        max_context_tokens: int | None = None,
        max_files: int | None = None,
        max_file_size: int | None = None,
    ) -> None:
        settings = get_settings()
        self.project = project
        self.memory_context = memory_context
        self.rag_context = rag_context
        self.thread_summary = thread_summary
        self.max_context_tokens = max_context_tokens or settings.coding_max_context_tokens
        self.max_files = max_files or settings.coding_max_files
        self.max_file_size = max_file_size or settings.coding_max_file_size
        self.loaded_files: list[dict[str, Any]] = []

    async def load_code_files(
        self,
        session: AsyncSession,
        user_id: UUID,
        file_ids: Optional[List[UUID]] = None,
        project_id: Optional[UUID] = None,
    ) -> list[dict[str, Any]]:
        """Load code files scoped to user and project without exceeding constraints."""
        files_to_load: list[File] = []
        storage = get_storage_provider()

        if file_ids:
            stmt = (
                select(File)
                .where(File.id.in_(file_ids), File.user_id == user_id)
                .limit(self.max_files)
            )
            result = await session.execute(stmt)
            files_to_load = list(result.scalars().all())
        elif project_id:
            stmt = (
                select(File)
                .where(File.project_id == project_id, File.user_id == user_id, File.status == "active")
                .order_by(File.created_at.desc())
                .limit(self.max_files)
            )
            result = await session.execute(stmt)
            files_to_load = list(result.scalars().all())

        loaded: list[dict[str, Any]] = []
        for f in files_to_load:
            try:
                storage = get_storage_provider(f.storage_provider)
                content_data = await storage.download(f.storage_key)
                if hasattr(content_data, "read"):
                    raw_bytes = content_data.read(self.max_file_size + 1)
                elif isinstance(content_data, bytes):
                    raw_bytes = content_data[: self.max_file_size + 1]
                else:
                    raw_bytes = bytes(content_data)[: self.max_file_size + 1]

                truncated = len(raw_bytes) > self.max_file_size
                if truncated:
                    raw_bytes = raw_bytes[: self.max_file_size]

                try:
                    text_content = raw_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    text_content = raw_bytes.decode("latin-1", errors="replace")

                lang = detect_language(f.original_filename)
                symbols = extract_code_symbols(text_content, lang)

                loaded.append({
                    "id": str(f.id),
                    "filename": f.original_filename,
                    "path": f.storage_key,
                    "language": lang,
                    "size_bytes": len(raw_bytes),
                    "truncated": truncated,
                    "symbols": symbols,
                    "content": text_content,
                })
            except Exception as e:
                # Gracefully record unreadable file
                loaded.append({
                    "id": str(f.id),
                    "filename": f.original_filename,
                    "language": "unknown",
                    "error": str(e),
                    "content": f"[Could not read file {f.original_filename}: {str(e)}]",
                })

        self.loaded_files = loaded
        return loaded

    def format_codebase_context(self) -> str:
        """Format loaded code files into standard prompt sections."""
        if not self.loaded_files:
            return ""

        sections: list[str] = ["### WORKSPACE CODE FILES:"]
        for file_info in self.loaded_files:
            fname = file_info.get("filename", "unknown")
            lang = file_info.get("language", "text")
            content = file_info.get("content", "")
            symbols = file_info.get("symbols", [])
            truncated = file_info.get("truncated", False)

            header = f"#### File: `{fname}` (Language: `{lang}`)"
            if symbols:
                header += f"\nKey symbols: {', '.join(symbols[:8])}"

            code_block = f"```{lang}:{fname}\n{content}\n```"
            if truncated:
                code_block += f"\n[Note: Content of `{fname}` was truncated to max file size limit]"

            sections.append(f"{header}\n{code_block}")

        return "\n\n".join(sections)

    def assemble(
        self,
        messages: List[Message],
        user_query: Optional[str] = None,
    ) -> List[NormalizedMessage]:
        """Assemble NormalizedMessage list following strict precedence and token budget."""
        normalized: List[NormalizedMessage] = []

        # 1. Coding System Prompt (with custom project instructions)
        custom_instructions = self.project.custom_instructions if self.project else None
        system_content = build_coding_system_prompt(custom_instructions)

        # 2. Project Memory
        if self.memory_context and self.memory_context.strip():
            system_content += f"\n\n### RELEVANT PROJECT & USER MEMORIES:\n{self.memory_context.strip()}"

        # 3. RAG Documentation / Knowledge
        if self.rag_context and self.rag_context.strip():
            system_content += f"\n\n### RELEVANT DOCUMENTATION & SPECIFICATIONS:\n{self.rag_context.strip()}"

        # 4. Codebase Files
        code_context = self.format_codebase_context()
        if code_context:
            system_content += f"\n\n{code_context}"

        # 5. Thread Summary
        if self.thread_summary and self.thread_summary.strip():
            system_content += f"\n\n[Conversation Summary]\n{self.thread_summary.strip()}"

        normalized.append(
            NormalizedMessage(
                role=MessageRole.SYSTEM,
                content=system_content.strip(),
            )
        )

        # 6. Append historical messages
        for message in messages:
            if message.content and message.content.strip():
                normalized.append(
                    NormalizedMessage(
                        role=message.role,
                        content=message.content,
                    )
                )

        return normalized
