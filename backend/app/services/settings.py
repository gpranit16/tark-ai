from datetime import datetime, timezone
import math
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.enums import ConversationMode
from app.models.conversation import Message, Project, Thread, User
from app.models.file import File
from app.models.memory import Memory
from app.models.settings import UserSettings
from app.schemas.settings import (
    ModelModeMapping,
    ProviderHealthInfo,
    SettingsEnvelope,
    StorageInfo,
    ToolSettingInfo,
    UserAccountStats,
    UserSettingsRead,
    UserSettingsUpdate,
)
from app.services.errors import not_found
from app.tools.registry import get_tool_registry

DEFAULT_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


def _format_bytes(bytes_count: int) -> str:
    if bytes_count <= 0:
        return "0 KB"
    if bytes_count < 1024:
        return f"{bytes_count} B"
    elif bytes_count < 1024 * 1024:
        return f"{bytes_count / 1024:.1f} KB"
    elif bytes_count < 1024 * 1024 * 1024:
        return f"{bytes_count / (1024 * 1024):.2f} MB"
    else:
        return f"{bytes_count / (1024 * 1024 * 1024):.2f} GB"


class SettingsService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def get_or_create_user_settings(self, session: AsyncSession, user_id: UUID) -> UserSettings:
        # Ensure user exists in users table
        user = await session.get(User, user_id)
        if user is None:
            user = User(id=user_id)
            session.add(user)
            await session.flush()

        stmt = select(UserSettings).where(UserSettings.user_id == user_id)
        result = await session.scalars(stmt)
        user_settings = result.first()

        if user_settings is None:
            user_settings = UserSettings(
                user_id=user_id,
                display_name="Developer",
                theme="dark",
                language="en",
                default_mode=ConversationMode.NORMAL,
                chat_density="comfortable",
                animations_enabled=True,
                enter_to_send=True,
                streaming_enabled=True,
                show_timestamps=True,
                auto_scroll=True,
                compact_messages=False,
                show_citations=True,
                show_attachment_previews=True,
                smart_memory_enabled=True,
                explicit_memory_enabled=True,
                default_retrieval_mode="hybrid",
                rag_enabled=True,
                document_context_scope="project",
                tool_preferences={},
                crag_debug_mode=False,
                show_crag_pipeline=False,
                detailed_streaming_events=False,
            )
            session.add(user_settings)
            await session.commit()
            await session.refresh(user_settings)

        return user_settings

    async def update_user_settings(
        self, session: AsyncSession, user_id: UUID, payload: UserSettingsUpdate
    ) -> UserSettings:
        user_settings = await self.get_or_create_user_settings(session, user_id)

        update_dict = payload.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            if key == "tool_preferences" and isinstance(value, dict):
                current_prefs = dict(user_settings.tool_preferences or {})
                current_prefs.update(value)
                user_settings.tool_preferences = current_prefs
            else:
                setattr(user_settings, key, value)

        user_settings.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(user_settings)
        return user_settings

    async def reset_user_settings(self, session: AsyncSession, user_id: UUID) -> UserSettings:
        user_settings = await self.get_or_create_user_settings(session, user_id)

        user_settings.display_name = "Developer"
        user_settings.theme = "dark"
        user_settings.language = "en"
        user_settings.default_mode = ConversationMode.NORMAL
        user_settings.chat_density = "comfortable"
        user_settings.animations_enabled = True
        user_settings.enter_to_send = True
        user_settings.streaming_enabled = True
        user_settings.show_timestamps = True
        user_settings.auto_scroll = True
        user_settings.compact_messages = False
        user_settings.show_citations = True
        user_settings.show_attachment_previews = True
        user_settings.smart_memory_enabled = True
        user_settings.explicit_memory_enabled = True
        user_settings.default_retrieval_mode = "hybrid"
        user_settings.rag_enabled = True
        user_settings.document_context_scope = "project"
        user_settings.tool_preferences = {}
        user_settings.crag_debug_mode = False
        user_settings.show_crag_pipeline = False
        user_settings.detailed_streaming_events = False
        user_settings.updated_at = datetime.now(timezone.utc)

        await session.commit()
        await session.refresh(user_settings)
        return user_settings

    async def get_settings_envelope(self, session: AsyncSession, user_id: UUID) -> SettingsEnvelope:
        user_settings = await self.get_or_create_user_settings(session, user_id)

        # 1. Models mapping
        modes_config: list[ModelModeMapping] = [
            ModelModeMapping(
                mode="fast",
                display_name="Fast",
                provider=self.settings.fast_provider,
                model=self.settings.fast_model,
                is_default=(user_settings.default_mode == ConversationMode.FAST),
            ),
            ModelModeMapping(
                mode="normal",
                display_name="Normal",
                provider=self.settings.normal_provider,
                model=self.settings.normal_model,
                is_default=(user_settings.default_mode == ConversationMode.NORMAL),
            ),
            ModelModeMapping(
                mode="reasoning",
                display_name="Reasoning",
                provider=self.settings.reasoning_provider,
                model=self.settings.reasoning_model,
                is_default=(user_settings.default_mode == ConversationMode.REASONING),
            ),
            ModelModeMapping(
                mode="coding",
                display_name="Coding",
                provider=self.settings.coding_provider,
                model=self.settings.coding_model,
                is_default=(user_settings.default_mode == ConversationMode.CODING),
            ),
            ModelModeMapping(
                mode="rag",
                display_name="RAG",
                provider=self.settings.rag_provider or self.settings.normal_provider,
                model=self.settings.rag_model or self.settings.normal_model,
                is_default=(user_settings.default_mode == ConversationMode.RAG),
            ),
            ModelModeMapping(
                mode="deep_research",
                display_name="Deep Research",
                provider=self.settings.deep_research_provider or self.settings.normal_provider,
                model=self.settings.deep_research_model or self.settings.normal_model,
                is_default=(user_settings.default_mode == ConversationMode.DEEP_RESEARCH),
            ),
        ]

        # 2. Providers health info (Safe - zero secrets)
        providers_info: list[ProviderHealthInfo] = [
            ProviderHealthInfo(
                provider="groq",
                display_name="Groq",
                status="available" if bool(self.settings.groq_api_key) else "configured",
                default_model=self.settings.normal_model,
            ),
            ProviderHealthInfo(
                provider="gemini",
                display_name="Google Gemini",
                status="available" if bool(self.settings.gemini_api_key) else "not_configured",
                default_model="gemini-2.5-flash",
            ),
            ProviderHealthInfo(
                provider="mistral",
                display_name="Mistral AI",
                status="available" if bool(self.settings.mistral_api_key) else "not_configured",
                default_model="mistral-medium-latest",
            ),
        ]

        # 3. Storage info
        doc_count_stmt = select(func.count(File.id)).where(File.user_id == user_id)
        doc_count = await session.scalar(doc_count_stmt) or 0

        storage_bytes_stmt = select(func.coalesce(func.sum(File.size_bytes), 0)).where(File.user_id == user_id)
        storage_bytes = await session.scalar(storage_bytes_stmt) or 0

        storage_info = StorageInfo(
            provider=self.settings.storage_provider.upper(),
            status="Connected",
            documents_count=doc_count,
            storage_used_bytes=storage_bytes,
            storage_used_formatted=_format_bytes(storage_bytes),
            max_upload_size_bytes=self.settings.max_upload_size_bytes,
            bucket_name=self.settings.b2_bucket_name if self.settings.storage_provider == "b2" else None,
        )

        # 4. Account stats
        user_db = await session.get(User, user_id)
        proj_count = await session.scalar(select(func.count(Project.id)).where(Project.user_id == user_id)) or 0
        thread_count = await session.scalar(select(func.count(Thread.id)).where(Thread.user_id == user_id)) or 0
        mem_count = await session.scalar(select(func.count(Memory.id)).where(Memory.user_id == user_id)) or 0

        account_stats = UserAccountStats(
            user_id=user_id,
            display_name=user_settings.display_name,
            created_at=user_db.created_at if user_db else None,
            projects_count=proj_count,
            threads_count=thread_count,
            memories_count=mem_count,
            files_count=doc_count,
        )

        # 5. Tools setting info
        registry = get_tool_registry()
        catalog = registry.get_catalog()
        tool_prefs = user_settings.tool_preferences or {}

        tools_list: list[ToolSettingInfo] = []
        for t in catalog:
            name = t["name"]
            is_enabled = tool_prefs.get(name, True)
            display_name = name.replace("_", " ").title()
            tools_list.append(
                ToolSettingInfo(
                    name=name,
                    display_name=display_name,
                    description=t["description"],
                    category=t.get("category", "General"),
                    permission=t.get("permission", "SAFE"),
                    enabled=is_enabled,
                )
            )

        return SettingsEnvelope(
            settings=UserSettingsRead.model_validate(user_settings),
            modes=modes_config,
            providers=providers_info,
            storage=storage_info,
            account=account_stats,
            tools=tools_list,
        )


settings_service = SettingsService()
