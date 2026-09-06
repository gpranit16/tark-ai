"""FileScopeResolver — resolves document and attachment scope for RAG and CRAG.

Implements strict hierarchy:
1. Explicit Request File IDs (current message attachments)
2. Explicit Filename Mentions in query (e.g., "Pan.pdf", "according to Pan.pdf")
3. Deictic References ("this document", "this PDF", "the attached file") -> thread history
4. Project Scope
5. Global User Knowledge

Enforces strict user ownership isolation: never resolves to a file belonging to another user.
"""
import logging
import os
import re
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Message
from app.models.file import File

logger = logging.getLogger(__name__)

_DEICTIC_PATTERNS = [
    r"\bthis\s+(?:document|pdf|file|attachment|report|paper|upload)\b",
    r"\bthe\s+(?:attached|uploaded)\s+(?:document|pdf|file|attachment|report|paper)\b",
    r"\bin\s+this\s+doc\b",
    r"\bfrom\s+this\s+doc\b",
    r"\bthis\s+doc\b",
    r"\bthe\s+document\b",
    r"\bthe\s+file\b",
    r"\bthe\s+pdf\b",
]

_DEICTIC_REGEX = re.compile("|".join(_DEICTIC_PATTERNS), re.IGNORECASE)


@dataclass
class ResolvedScope:
    """Resolved file and context scope for retrieval and CRAG."""

    file_ids: list[UUID] | None = None
    filenames: list[str] = field(default_factory=list)
    source: str = "global"  # "explicit_attachments" | "explicit_filename" | "thread_history" | "project_scope" | "global"
    is_document_scoped: bool = False
    refusal_hint: str | None = None


class FileScopeResolver:
    """Resolves and validates document scopes with strict user isolation."""

    async def resolve_scope(
        self,
        session: AsyncSession,
        user_id: UUID,
        query: str,
        explicit_file_ids: list[UUID] | None = None,
        project_id: UUID | None = None,
        thread_id: UUID | None = None,
    ) -> ResolvedScope:
        """Resolve document scope following the strict priority hierarchy."""
        # ── 1. Priority 1: Current-turn explicit attachments ──────────────────
        if explicit_file_ids:
            stmt = select(File).where(
                File.id.in_(explicit_file_ids),
                File.user_id == user_id,
            )
            res = await session.execute(stmt)
            owned_files = list(res.scalars().all())

            if owned_files:
                valid_ids = [f.id for f in owned_files]
                filenames = [f.original_filename for f in owned_files]
                logger.info(
                    "[ScopeResolver] Priority 1: Explicit attachments resolved: %s (ids=%s)",
                    filenames,
                    valid_ids,
                )
                return ResolvedScope(
                    file_ids=valid_ids,
                    filenames=filenames,
                    source="explicit_attachments",
                    is_document_scoped=True,
                    refusal_hint=", ".join(filenames),
                )
            else:
                logger.warning(
                    "[ScopeResolver] Priority 1: None of explicit_file_ids %s owned by user %s",
                    explicit_file_ids,
                    user_id,
                )
                return ResolvedScope(
                    file_ids=[],
                    filenames=[],
                    source="explicit_attachments",
                    is_document_scoped=True,
                    refusal_hint="the specified file",
                )

        # Fetch all user-accessible files (scoped by project if provided)
        file_query = select(File).where(File.user_id == user_id)
        if project_id is not None:
            file_query = file_query.where(
                (File.project_id == project_id) | (File.project_id.is_(None))
            )
        file_res = await session.execute(file_query)
        user_files = list(file_res.scalars().all())

        if not user_files:
            # User has no uploaded files
            return ResolvedScope(
                file_ids=None,
                filenames=[],
                source="project_scope" if project_id else "global",
                is_document_scoped=False,
            )

        query_clean = query.strip()
        query_lower = query_clean.lower()

        # ── 2. Priority 2: Explicit filename mentions in query ────────────────
        matched_files: list[File] = []
        for f in user_files:
            fname = f.original_filename.strip()
            fname_lower = fname.lower()
            base_name, _ext = os.path.splitext(fname)
            base_name_lower = base_name.lower().strip()

            # Exact or word-boundary match of full filename (e.g., "Pan.pdf" or "pan.pdf")
            pattern_full = r"(?i)(?:\b|_)" + re.escape(fname_lower) + r"(?:\b|_)"
            if re.search(pattern_full, query_lower):
                matched_files.append(f)
                continue

            # If base name is sufficiently specific (>= 3 chars) and not a generic word
            if (
                len(base_name_lower) >= 3
                and base_name_lower not in {"the", "doc", "pdf", "file", "test", "data", "text"}
            ):
                pattern_base = r"(?i)(?:\b|_)" + re.escape(base_name_lower) + r"(?:\b|_)"
                if re.search(pattern_base, query_lower):
                    matched_files.append(f)

        if matched_files:
            # Deduplicate by file id
            seen_ids = set()
            unique_matches = []
            for f in matched_files:
                if f.id not in seen_ids:
                    seen_ids.add(f.id)
                    unique_matches.append(f)

            valid_ids = [f.id for f in unique_matches]
            filenames = [f.original_filename for f in unique_matches]
            logger.info(
                "[ScopeResolver] Priority 2: Explicit filename matched in query: %s (ids=%s)",
                filenames,
                valid_ids,
            )
            return ResolvedScope(
                file_ids=valid_ids,
                filenames=filenames,
                source="explicit_filename",
                is_document_scoped=True,
                refusal_hint=", ".join(filenames),
            )

        # ── 3. Priority 3: Deictic reference ("this document", "this pdf") ───
        if _DEICTIC_REGEX.search(query_lower):
            # Check thread history for recent attachments
            if thread_id is not None:
                msg_stmt = (
                    select(Message)
                    .where(
                        Message.thread_id == thread_id,
                        Message.attachments.isnot(None),
                    )
                    .order_by(Message.created_at.desc())
                    .limit(10)
                )
                msg_res = await session.execute(msg_stmt)
                recent_msgs = list(msg_res.scalars().all())

                for msg in recent_msgs:
                    if not msg.attachments:
                        continue
                    # Extract attachment file_ids
                    att_file_ids: list[UUID] = []
                    for att in msg.attachments:
                        fid_str = att.get("file_id") if isinstance(att, dict) else None
                        if fid_str:
                            try:
                                att_file_ids.append(UUID(str(fid_str)))
                            except (ValueError, TypeError):
                                pass

                    if att_file_ids:
                        # Verify ownership
                        val_stmt = select(File).where(
                            File.id.in_(att_file_ids),
                            File.user_id == user_id,
                        )
                        val_res = await session.execute(val_stmt)
                        thread_files = list(val_res.scalars().all())
                        if thread_files:
                            valid_ids = [f.id for f in thread_files]
                            filenames = [f.original_filename for f in thread_files]
                            logger.info(
                                "[ScopeResolver] Priority 3: Deictic reference resolved from thread history: %s (ids=%s)",
                                filenames,
                                valid_ids,
                            )
                            return ResolvedScope(
                                file_ids=valid_ids,
                                filenames=filenames,
                                source="thread_history",
                                is_document_scoped=True,
                                refusal_hint=", ".join(filenames),
                            )

            # If user has only 1 uploaded file total in the knowledge base, resolve to that file
            if len(user_files) == 1:
                single_file = user_files[0]
                logger.info(
                    "[ScopeResolver] Priority 3: Deictic reference resolved to single user file: %s (id=%s)",
                    single_file.original_filename,
                    single_file.id,
                )
                return ResolvedScope(
                    file_ids=[single_file.id],
                    filenames=[single_file.original_filename],
                    source="thread_history",
                    is_document_scoped=True,
                    refusal_hint=single_file.original_filename,
                )

        # ── 4 & 5. Priority 4/5: Project or Global Scope ──────────────────────
        return ResolvedScope(
            file_ids=None,
            filenames=[],
            source="project_scope" if project_id else "global",
            is_document_scoped=False,
        )
