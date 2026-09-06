"""ProjectContextBuilder for Phase 11 Workspace Context Assembly.

Enforces deterministic precedence:
1. System instructions
2. Developer safety / system policies
3. Global configuration
4. Project custom instructions
5. Relevant Memory (Project memory + Global user memory)
6. RAG / Research context
7. Thread summary
8. Recent messages & user query
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from app.core.enums import MessageRole
from app.models.conversation import Message, Project
from app.providers.base import NormalizedMessage


class ProjectContextBuilder:
    """Builds model prompt context with strict workspace isolation and deterministic precedence."""

    def __init__(
        self,
        *,
        system_prompt: Optional[str] = None,
        project: Optional[Project] = None,
        memory_context: Optional[str] = None,
        rag_context: Optional[str] = None,
        thread_summary: Optional[str] = None,
        max_context_tokens: int = 4000,
    ) -> None:
        self.system_prompt = system_prompt
        self.project = project
        self.memory_context = memory_context
        self.rag_context = rag_context
        self.thread_summary = thread_summary
        self.max_context_tokens = max_context_tokens

    def build_system_content(self) -> str:
        """Assemble system prompt blocks following strict precedence."""
        blocks: List[str] = []

        # 1. Base system prompt
        if self.system_prompt and self.system_prompt.strip():
            blocks.append(self.system_prompt.strip())

        # 2. Project Custom Instructions
        if self.project and self.project.custom_instructions and self.project.custom_instructions.strip():
            project_header = f"## PROJECT WORKSPACE: {self.project.name.upper()}"
            if self.project.description:
                project_header += f"\nDescription: {self.project.description}"
            blocks.append(
                f"{project_header}\n\n"
                f"### Custom Project Instructions:\n"
                f"{self.project.custom_instructions.strip()}"
            )

        # 3. Relevant Memories (Project Memory + Global User Memory)
        if self.memory_context and self.memory_context.strip():
            blocks.append(self.memory_context.strip())

        # 4. RAG / Research Document Context
        if self.rag_context and self.rag_context.strip():
            blocks.append(self.rag_context.strip())

        # 5. Conversation History Summary (Older messages)
        if self.thread_summary and self.thread_summary.strip():
            blocks.append(f"[Conversation History Summary]\n{self.thread_summary.strip()}")

        return "\n\n".join(blocks)

    def assemble(
        self,
        messages: List[Message],
    ) -> List[NormalizedMessage]:
        """Assemble complete NormalizedMessage list for model router."""
        normalized: List[NormalizedMessage] = []

        system_content = self.build_system_content()
        if system_content.strip():
            normalized.append(
                NormalizedMessage(
                    role=MessageRole.SYSTEM,
                    content=system_content.strip(),
                )
            )

        # Append normalized conversation turns
        for message in messages:
            if message.content and message.content.strip():
                normalized.append(
                    NormalizedMessage(
                        role=message.role,
                        content=message.content,
                    )
                )

        return normalized
