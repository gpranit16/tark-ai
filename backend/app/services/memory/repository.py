from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import MemoryCategory
from app.models.memory import Memory
from app.schemas.memory import MemoryCreate, MemoryUpdate


class MemoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, user_id: UUID, payload: MemoryCreate) -> Memory:
        memory = Memory(
            user_id=user_id,
            project_id=payload.project_id,
            category=payload.category,
            key=payload.key,
            value=payload.value,
            source=payload.source or "manual",
            confidence=payload.confidence if payload.confidence is not None else 1.0,
            importance=payload.importance if payload.importance is not None else 0.7,
            metadata_=payload.metadata or {},
            is_active=True,
        )
        self.session.add(memory)
        await self.session.commit()
        await self.session.refresh(memory)
        return memory

    async def get_by_id(self, memory_id: UUID, user_id: UUID | None = None) -> Memory | None:
        stmt: Select[tuple[Memory]] = select(Memory).where(Memory.id == memory_id)
        if user_id is not None:
            stmt = stmt.where(Memory.user_id == user_id)
        result = await self.session.scalars(stmt)
        return result.first()

    async def get_active_by_key(
        self,
        user_id: UUID,
        key: str,
        project_id: UUID | None = None,
    ) -> Memory | None:
        stmt: Select[tuple[Memory]] = select(Memory).where(
            Memory.user_id == user_id,
            Memory.key == key,
            Memory.is_active == True,  # noqa: E712
        )
        if project_id is not None:
            stmt = stmt.where(Memory.project_id == project_id)
        else:
            stmt = stmt.where(Memory.project_id.is_(None))
        result = await self.session.scalars(stmt)
        return result.first()

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        project_id: UUID | None = None,
        include_global: bool = False,
        category: MemoryCategory | None = None,
        is_active: bool | None = None,
        search_query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Memory]:
        stmt = self._build_query(
            user_id=user_id,
            project_id=project_id,
            include_global=include_global,
            category=category,
            is_active=is_active,
            search_query=search_query,
        )
        stmt = stmt.order_by(Memory.updated_at.desc(), Memory.created_at.desc())
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def count_for_user(
        self,
        user_id: UUID,
        *,
        project_id: UUID | None = None,
        include_global: bool = False,
        category: MemoryCategory | None = None,
        is_active: bool | None = None,
        search_query: str | None = None,
    ) -> int:
        stmt = select(func.count(Memory.id)).where(Memory.user_id == user_id)
        if is_active is not None:
            stmt = stmt.where(Memory.is_active == is_active)
        if category is not None:
            stmt = stmt.where(Memory.category == category)
        if project_id is not None:
            if include_global:
                stmt = stmt.where(or_(Memory.project_id == project_id, Memory.project_id.is_(None)))
            else:
                stmt = stmt.where(Memory.project_id == project_id)
        elif not include_global and project_id is None:
            # If project_id is None and include_global not specified, filter to global
            pass

        if search_query:
            pattern = f"%{search_query}%"
            stmt = stmt.where(or_(Memory.key.ilike(pattern), Memory.value.ilike(pattern)))

        result = await self.session.scalar(stmt)
        return result or 0

    def _build_query(
        self,
        user_id: UUID,
        project_id: UUID | None = None,
        include_global: bool = False,
        category: MemoryCategory | None = None,
        is_active: bool | None = None,
        search_query: str | None = None,
    ) -> Select[tuple[Memory]]:
        stmt: Select[tuple[Memory]] = select(Memory).where(Memory.user_id == user_id)

        if is_active is not None:
            stmt = stmt.where(Memory.is_active == is_active)

        if category is not None:
            stmt = stmt.where(Memory.category == category)

        if project_id is not None:
            if include_global:
                stmt = stmt.where(or_(Memory.project_id == project_id, Memory.project_id.is_(None)))
            else:
                stmt = stmt.where(Memory.project_id == project_id)
        elif not include_global:
            # Global only
            pass

        if search_query:
            pattern = f"%{search_query}%"
            stmt = stmt.where(or_(Memory.key.ilike(pattern), Memory.value.ilike(pattern)))

        return stmt

    async def update(self, memory: Memory, payload: MemoryUpdate) -> Memory:
        updates = payload.model_dump(exclude_unset=True)
        for field, value in updates.items():
            if field == "metadata":
                memory.metadata_ = value
            elif hasattr(memory, field):
                setattr(memory, field, value)
        await self.session.commit()
        await self.session.refresh(memory)
        return memory

    async def delete(self, memory: Memory) -> None:
        await self.session.delete(memory)
        await self.session.commit()

    async def delete_all_for_user(self, user_id: UUID, project_id: UUID | None = None) -> int:
        stmt = select(Memory).where(Memory.user_id == user_id)
        if project_id is not None:
            stmt = stmt.where(Memory.project_id == project_id)
        records = list((await self.session.scalars(stmt)).all())
        count = len(records)
        for mem in records:
            await self.session.delete(mem)
        await self.session.commit()
        return count

    async def find_by_keywords(
        self,
        user_id: UUID,
        query: str,
        project_id: UUID | None = None,
    ) -> list[Memory]:
        """Find active memories matching keywords in key, value, or category."""
        clean_words = [w.lower() for w in query.split() if len(w) > 2]
        if not clean_words:
            return []
        
        stmt = select(Memory).where(
            Memory.user_id == user_id,
            Memory.is_active == True,  # noqa: E712
        )
        if project_id is not None:
            stmt = stmt.where(or_(Memory.project_id == project_id, Memory.project_id.is_(None)))

        records = list((await self.session.scalars(stmt)).all())
        scored: list[tuple[int, Memory]] = []
        for mem in records:
            mem_text = f"{mem.key} {mem.value} {mem.category.value}".lower()
            overlap = sum(1 for w in clean_words if w in mem_text)
            if overlap > 0:
                scored.append((overlap, mem))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored]

    async def touch_last_accessed(self, memory_ids: list[UUID]) -> None:
        if not memory_ids:
            return
        stmt = (
            select(Memory)
            .where(Memory.id.in_(memory_ids))
        )
        records = await self.session.scalars(stmt)
        now = datetime.now(timezone.utc)
        for mem in records:
            mem.last_accessed_at = now
        await self.session.commit()

