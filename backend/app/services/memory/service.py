from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import MemoryCategory
from app.models.memory import Memory
from app.schemas.memory import (
    MemoryCandidate,
    MemoryCreate,
    MemoryListResponse,
    MemoryRead,
    MemorySearchRequest,
    MemoryUpdate,
)
from app.services.errors import not_found
from app.services.memory.repository import MemoryRepository


class MemoryService:
    """Manages long-term user and project memories with deduplication and conflict resolution."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = MemoryRepository(session)
        self.settings = get_settings()

    async def create_memory(self, user_id: UUID, payload: MemoryCreate) -> MemoryRead:
        memory = await self.repository.create(user_id, payload)
        return MemoryRead.model_validate(memory)

    async def get_memory(self, memory_id: UUID, user_id: UUID) -> MemoryRead:
        memory = await self.repository.get_by_id(memory_id, user_id=user_id)
        if memory is None:
            raise not_found("Memory not found")
        return MemoryRead.model_validate(memory)

    async def list_memories(
        self,
        user_id: UUID,
        *,
        project_id: UUID | None = None,
        include_global: bool = True,
        category: MemoryCategory | None = None,
        is_active: bool | None = None,
        search_query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> MemoryListResponse:
        items = await self.repository.list_for_user(
            user_id,
            project_id=project_id,
            include_global=include_global,
            category=category,
            is_active=is_active,
            search_query=search_query,
            limit=limit,
            offset=offset,
        )
        total = await self.repository.count_for_user(
            user_id,
            project_id=project_id,
            include_global=include_global,
            category=category,
            is_active=is_active,
            search_query=search_query,
        )
        return MemoryListResponse(
            items=[MemoryRead.model_validate(m) for m in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def update_memory(self, memory_id: UUID, user_id: UUID, payload: MemoryUpdate) -> MemoryRead:
        memory = await self.repository.get_by_id(memory_id, user_id=user_id)
        if memory is None:
            raise not_found("Memory not found")
        updated = await self.repository.update(memory, payload)
        return MemoryRead.model_validate(updated)

    async def delete_memory(self, memory_id: UUID, user_id: UUID) -> None:
        memory = await self.repository.get_by_id(memory_id, user_id=user_id)
        if memory is None:
            raise not_found("Memory not found")
        await self.repository.delete(memory)

    async def deactivate_memory(self, memory_id: UUID, user_id: UUID) -> MemoryRead:
        return await self.update_memory(memory_id, user_id, MemoryUpdate(is_active=False))

    async def search_memories(self, user_id: UUID, payload: MemorySearchRequest) -> list[MemoryRead]:
        items = await self.repository.list_for_user(
            user_id,
            project_id=payload.project_id,
            include_global=True,
            category=payload.category,
            is_active=True,
            search_query=payload.query,
            limit=payload.top_k,
            offset=0,
        )
        return [MemoryRead.model_validate(m) for m in items]

    async def process_and_store_candidates(
        self,
        user_id: UUID,
        candidates: list[MemoryCandidate],
        project_id: UUID | None = None,
        source: str = "conversation",
    ) -> list[Memory]:
        """Deduplicate, resolve conflicts, and persist extracted memory candidates."""
        stored: list[Memory] = []
        now = datetime.now(timezone.utc)

        for candidate in candidates:
            # Check threshold constraints
            if (
                candidate.confidence < self.settings.memory_min_confidence
                or candidate.importance < self.settings.memory_min_importance
            ):
                continue

            # Check if an active memory with the same key exists
            existing = await self.repository.get_active_by_key(
                user_id=user_id,
                key=candidate.key,
                project_id=project_id,
            )

            if existing is not None:
                # Deduplication check: Is the value essentially the same?
                if existing.value.strip().lower() == candidate.value.strip().lower():
                    # Same fact/preference repeated in similar words -> Update metadata & timestamp, no duplicate
                    existing.updated_at = now
                    existing.last_accessed_at = now
                    if candidate.confidence > existing.confidence:
                        existing.confidence = candidate.confidence
                    if candidate.importance > existing.importance:
                        existing.importance = candidate.importance
                    await self.session.commit()
                    await self.session.refresh(existing)
                    stored.append(existing)
                else:
                    # Conflict / update handling: User changed preference or updated fact
                    # e.g. "Prefers Python" -> "Prefers JavaScript"
                    meta = dict(existing.metadata_ or {})
                    history = list(meta.get("history", []))
                    history.append({
                        "previous_value": existing.value,
                        "updated_at": existing.updated_at.isoformat() if existing.updated_at else now.isoformat(),
                        "previous_source": existing.source,
                    })
                    meta["history"] = history

                    existing.value = candidate.value
                    existing.confidence = candidate.confidence
                    existing.importance = candidate.importance
                    existing.source = source
                    existing.metadata_ = meta
                    existing.updated_at = now
                    existing.last_accessed_at = now

                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(existing, "metadata_")

                    await self.session.commit()
                    await self.session.refresh(existing)
                    stored.append(existing)
            else:
                # New memory creation
                new_mem = await self.repository.create(
                    user_id=user_id,
                    payload=MemoryCreate(
                        category=candidate.category,
                        key=candidate.key,
                        value=candidate.value,
                        project_id=project_id,
                        source=source,
                        confidence=candidate.confidence,
                        importance=candidate.importance,
                        metadata={"created_from": candidate.reasoning} if candidate.reasoning else {},
                    ),
                )
                stored.append(new_mem)

        return stored

    async def delete_all_memories(self, user_id: UUID, project_id: UUID | None = None) -> int:
        """Delete all memories for a user (and optionally project)."""
        return await self.repository.delete_all_for_user(user_id, project_id=project_id)

    async def forget_matching_memory(
        self,
        user_id: UUID,
        subject: str | None = None,
        project_id: UUID | None = None,
    ) -> Memory | None:
        """Find and delete/deactivate a memory matching the subject query."""
        if not subject or not subject.strip():
            # If no subject specified, fetch the most recently updated memory
            all_mems = await self.repository.list_for_user(
                user_id=user_id,
                project_id=project_id,
                include_global=True,
                is_active=True,
                limit=1,
            )
            if all_mems:
                mem = all_mems[0]
                await self.repository.delete(mem)
                return mem
            return None

        # Clean subject string
        clean_subj = subject.strip().lower()
        # Look for direct keyword matches
        matches = await self.repository.find_by_keywords(user_id, clean_subj, project_id=project_id)
        if matches:
            target = matches[0]
            await self.repository.delete(target)
            return target

        # Check by key directly if user said e.g. "my name" or "concise answers"
        key_aliases = {
            "name": ["name", "user_role"],
            "concise": ["response_style"],
            "short": ["response_style"],
            "style": ["response_style", "explanation_style"],
            "python": ["preferred_programming_language"],
            "javascript": ["preferred_programming_language"],
            "language": ["preferred_programming_language"],
            "interview": ["interview_preparation", "user_goal"],
            "goal": ["user_goal", "interview_preparation"],
            "project": ["project_stack", "backend_framework", "frontend_framework", "project_name"],
        }
        for alias, keys in key_aliases.items():
            if alias in clean_subj:
                for k in keys:
                    active = await self.repository.get_active_by_key(user_id, k, project_id=project_id)
                    if not active and project_id:
                        active = await self.repository.get_active_by_key(user_id, k, project_id=None)
                    if active:
                        await self.repository.delete(active)
                        return active

        # Fallback to search list
        all_active = await self.repository.list_for_user(user_id, project_id=project_id, include_global=True, is_active=True, limit=50)
        for mem in all_active:
            if any(w in mem.value.lower() or w in mem.key.lower() for w in clean_subj.split() if len(w) > 2):
                await self.repository.delete(mem)
                return mem

        return None

    async def format_user_memory_dossier(self, user_id: UUID, project_id: UUID | None = None) -> str:
        """Format active memories into a clear structured Markdown presentation."""
        memories = await self.repository.list_for_user(
            user_id=user_id,
            project_id=project_id,
            include_global=True,
            is_active=True,
            limit=100,
        )
        if not memories:
            return "I don't have any active memories saved about you yet. As we chat, I'll automatically remember important preferences, goals, and facts, or you can ask me to remember specific details anytime!"

        grouped: dict[str, list[Memory]] = {
            "Personal & Identity": [],
            "Preferences": [],
            "Goals & Focus": [],
            "Skills & Learning": [],
            "Project & Technical Context": [],
            "Other": [],
        }

        for mem in memories:
            if mem.category == MemoryCategory.FACT:
                grouped["Personal & Identity"].append(mem)
            elif mem.category == MemoryCategory.PREFERENCE:
                grouped["Preferences"].append(mem)
            elif mem.category == MemoryCategory.GOAL:
                grouped["Goals & Focus"].append(mem)
            elif mem.category == MemoryCategory.SKILL or mem.category == MemoryCategory.INTEREST:
                grouped["Skills & Learning"].append(mem)
            elif mem.category == MemoryCategory.PROJECT_CONTEXT:
                grouped["Project & Technical Context"].append(mem)
            else:
                grouped["Other"].append(mem)

        lines = ["Here is what I remember about you:"]
        for section, items in grouped.items():
            if items:
                lines.append(f"\n### {section}")
                for item in items:
                    scope = f" *({item.project.name if item.project else 'Project'})*" if item.project_id else ""
                    lines.append(f"- **{item.value}**{scope}")

        lines.append("\n*You can ask me to update, remember, or forget any of these details anytime.*")
        return "\n".join(lines)

    async def handle_explicit_memory_command(
        self,
        user_id: UUID,
        command: "ExplicitMemoryCommand",
        project_id: UUID | None = None,
        recent_messages: list | None = None,
        source: str = "conversation",
    ) -> tuple[str, str | None, dict | None]:
        """Execute explicit memory command and return (assistant_response, sse_event_type, sse_payload)."""
        from app.services.memory.extractor import ExplicitIntent

        if command.intent == ExplicitIntent.QUERY:
            dossier = await self.format_user_memory_dossier(user_id, project_id=project_id)
            return dossier, None, None

        if command.intent == ExplicitIntent.FORGET_ALL:
            count = await self.delete_all_memories(user_id, project_id=project_id)
            response = f"I have forgotten everything I knew about you. All personal memories ({count} items) have been cleared."
            return response, "memory_forgotten", {"key": "all", "value": f"Cleared {count} memories"}

        if command.intent == ExplicitIntent.FORGET:
            target = await self.forget_matching_memory(user_id, subject=command.target_subject, project_id=project_id)
            if target:
                response = f"I've forgotten that memory: **{target.value}**."
                return response, "memory_forgotten", {"key": target.key, "value": target.value}
            else:
                subject_desc = f" for '{command.target_subject}'" if command.target_subject else ""
                response = f"I couldn't find a matching active memory{subject_desc} to forget."
                return response, None, None

        if command.intent == ExplicitIntent.REMEMBER:
            candidate = command.extracted_candidate
            if not candidate and recent_messages:
                # Attempt extraction from immediate recent user message
                from app.services.memory.extractor import MemoryExtractor
                extractor = MemoryExtractor()
                for msg in reversed(recent_messages):
                    content = getattr(msg, "content", "") if not isinstance(msg, dict) else msg.get("content", "")
                    if content and content != command.raw_query:
                        ext = extractor.extract(content)
                        if ext.candidates:
                            candidate = ext.candidates[0]
                            break

            if candidate:
                stored = await self.process_and_store_candidates(
                    user_id=user_id,
                    candidates=[candidate],
                    project_id=project_id,
                    source=source,
                )
                if stored:
                    item = stored[0]
                    response = f"I've saved that to memory: **{item.value}**."
                    return response, "memory_saved", {
                        "key": item.key,
                        "value": item.value,
                        "category": item.category.value,
                        "explicit": True,
                    }

            # Fallback if no specific candidate could be structured
            fallback_val = command.target_subject or command.raw_query
            new_mem = await self.repository.create(
                user_id=user_id,
                payload=MemoryCreate(
                    category=MemoryCategory.FACT,
                    key="user_note",
                    value=fallback_val,
                    project_id=project_id,
                    source=source,
                    confidence=1.0,
                    importance=0.9,
                ),
            )
            response = f"I've saved that to memory: **{new_mem.value}**."
            return response, "memory_saved", {
                "key": new_mem.key,
                "value": new_mem.value,
                "category": new_mem.category.value,
                "explicit": True,
            }

        return "Memory command processed.", None, None

