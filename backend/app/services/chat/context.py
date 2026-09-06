from app.core.enums import MessageRole
from app.models.conversation import Message
from app.providers.base import NormalizedMessage


def normalize_messages(
    messages: list[Message],
    *,
    thread_summary: str | None = None,
    memory_context: str | None = None,
) -> list[NormalizedMessage]:
    normalized: list[NormalizedMessage] = []

    # Build system context block if summary or memories exist
    system_sections: list[str] = []
    if thread_summary and thread_summary.strip():
        system_sections.append(f"[Conversation History Summary]\n{thread_summary.strip()}")
    if memory_context and memory_context.strip():
        system_sections.append(memory_context.strip())

    if system_sections:
        combined_system = "\n\n".join(system_sections)
        normalized.append(NormalizedMessage(role=MessageRole.SYSTEM, content=combined_system))

    # Append normalized conversation messages
    for message in messages:
        if message.content and message.content.strip():
            normalized.append(NormalizedMessage(role=message.role, content=message.content))

    return normalized
