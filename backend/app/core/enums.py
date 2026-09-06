from enum import StrEnum


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ConversationMode(StrEnum):
    FAST = "fast"
    NORMAL = "normal"
    REASONING = "reasoning"
    RAG = "rag"
    DEEP_RESEARCH = "deep_research"
    CODING = "coding"


class GenerationStatus(StrEnum):
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class MemoryCategory(StrEnum):
    PREFERENCE = "preference"
    FACT = "fact"
    GOAL = "goal"
    SKILL = "skill"
    INTEREST = "interest"
    PROJECT_CONTEXT = "project_context"
    OTHER = "other"
