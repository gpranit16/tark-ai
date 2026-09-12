from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = Field(default="development", alias="APP_ENV")
    database_url: str = Field(alias="DATABASE_URL")
    cors_origins: str | None = Field(default=None, alias="CORS_ORIGINS")

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        if isinstance(v, str):
            if v.startswith("postgres://"):
                return v.replace("postgres://", "postgresql+asyncpg://", 1)
            elif v.startswith("postgresql://") and not v.startswith("postgresql+"):
                return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v
    postgres_db: str = Field(default="tarkai", alias="POSTGRES_DB")
    postgres_user: str = Field(default="tarkai", alias="POSTGRES_USER")
    postgres_password: str = Field(default="change-me", alias="POSTGRES_PASSWORD")
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    mistral_api_key: str | None = Field(default=None, alias="MISTRAL_API_KEY")
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    nvidia_api_key: str | None = Field(default=None, alias="NVIDIA_API_KEY")
    nvidia_base_url: str = Field(default="https://integrate.api.nvidia.com/v1", alias="NVIDIA_BASE_URL")
    nvidia_model: str = Field(default="meta/llama-3.2-11b-vision-instruct", alias="NVIDIA_MODEL")
    tavily_api_key: str | None = Field(default=None, alias="TAVILY_API_KEY")
    default_provider: str = Field(default="groq", alias="DEFAULT_PROVIDER")
    fast_provider: str = Field(default="groq", alias="FAST_PROVIDER")
    fast_model: str = Field(default="qwen/qwen3.6-27b", alias="FAST_MODEL")
    normal_provider: str = Field(default="groq", alias="NORMAL_PROVIDER")
    normal_model: str = Field(default="qwen/qwen3.8-27b", alias="NORMAL_MODEL")
    reasoning_provider: str = Field(default="groq", alias="REASONING_PROVIDER")
    reasoning_model: str = Field(default="openai/gpt-oss-120b", alias="REASONING_MODEL")
    rag_provider: str | None = Field(default=None, alias="RAG_PROVIDER")
    rag_model: str | None = Field(default=None, alias="RAG_MODEL")
    deep_research_provider: str | None = Field(default=None, alias="DEEP_RESEARCH_PROVIDER")
    deep_research_model: str | None = Field(default=None, alias="DEEP_RESEARCH_MODEL")
    coding_provider: str = Field(default="groq", alias="CODING_PROVIDER")
    coding_model: str = Field(default="qwen/qwen3.8-27b", alias="CODING_MODEL")
    coding_max_context_tokens: int = Field(default=8000, alias="CODING_MAX_CONTEXT_TOKENS")
    coding_max_files: int = Field(default=10, alias="CODING_MAX_FILES")
    coding_max_file_size: int = Field(default=500000, alias="CODING_MAX_FILE_SIZE")
    coding_temperature: float = Field(default=0.2, alias="CODING_TEMPERATURE")
    auto_fallback: bool = Field(default=True, alias="AUTO_FALLBACK")
    provider_timeout_seconds: float = Field(default=60.0, alias="PROVIDER_TIMEOUT_SECONDS")
    max_context_messages: int = Field(default=50, alias="MAX_CONTEXT_MESSAGES")

    storage_provider: str = Field(default="local", alias="STORAGE_PROVIDER")
    b2_endpoint: str | None = Field(default=None, alias="B2_ENDPOINT")
    b2_key_id: str | None = Field(default=None, alias="B2_KEY_ID")
    b2_application_key: str | None = Field(default=None, alias="B2_APPLICATION_KEY")
    b2_bucket_name: str | None = Field(default=None, alias="B2_BUCKET_NAME")
    max_upload_size_bytes: int = Field(default=52428800, alias="MAX_UPLOAD_SIZE_BYTES")  # 50MB

    # JWT Authentication Settings
    jwt_secret_key: str = Field(default="tark-ai-luxury-secret-key-change-in-production-2026", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=1440, alias="ACCESS_TOKEN_EXPIRE_MINUTES")  # 24 hours
    refresh_token_expire_days: int = Field(default=30, alias="REFRESH_TOKEN_EXPIRE_DAYS")

    # Resend Transactional Email Settings
    resend_api_key: str | None = Field(default=None, alias="RESEND_API_KEY")
    resend_from_email: str = Field(default="onboarding@resend.dev", alias="RESEND_FROM_EMAIL")
    resend_from_name: str = Field(default="TARK AI", alias="RESEND_FROM_NAME")
    frontend_url: str = Field(default="http://localhost:5173", alias="FRONTEND_URL")
    password_reset_token_expire_minutes: int = Field(default=60, alias="PASSWORD_RESET_TOKEN_EXPIRE_MINUTES")
    email_verification_token_expire_hours: int = Field(default=24, alias="EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS")

    # Phase 6 Embedding & Retrieval Settings
    embedding_provider: str = Field(default="bge", alias="EMBEDDING_PROVIDER")
    embedding_model: str = Field(default="BAAI/bge-m3", alias="EMBEDDING_MODEL")
    embedding_dimension: int = Field(default=1024, alias="EMBEDDING_DIMENSION")
    chunk_size: int = Field(default=500, alias="CHUNK_SIZE")
    chunk_overlap: int = Field(default=60, alias="CHUNK_OVERLAP")
    default_top_k: int = Field(default=5, alias="DEFAULT_TOP_K")
    max_context_tokens: int = Field(default=4000, alias="MAX_CONTEXT_TOKENS")
    vector_search_weight: float = Field(default=0.7, alias="VECTOR_SEARCH_WEIGHT")
    keyword_search_weight: float = Field(default=0.3, alias="KEYWORD_SEARCH_WEIGHT")

    # Phase 7 Reranking, Grading & CRAG Settings
    reranker_model: str = Field(default="BAAI/bge-reranker-v2-m3", alias="RERANKER_MODEL")
    reranker_top_k: int = Field(default=5, alias="RERANKER_TOP_K")
    retrieval_top_k: int = Field(default=8, alias="RETRIEVAL_TOP_K")
    grading_threshold: float = Field(default=0.35, alias="GRADING_THRESHOLD")
    crag_max_retries: int = Field(default=1, alias="CRAG_MAX_RETRIES")
    rag_context_max_tokens: int = Field(default=6000, alias="RAG_CONTEXT_MAX_TOKENS")
    min_grounding_confidence: float = Field(default=0.30, alias="MIN_GROUNDING_CONFIDENCE")

    # CRAG Latency Optimization Settings
    rag_top_k: int = Field(default=8, alias="RAG_TOP_K")
    rag_rerank_top_k: int = Field(default=5, alias="RAG_RERANK_TOP_K")
    rag_confidence_threshold: float = Field(default=0.65, alias="RAG_CONFIDENCE_THRESHOLD")
    rag_max_retries: int = Field(default=1, alias="RAG_MAX_RETRIES")
    rag_enable_llm_grader: bool = Field(default=False, alias="RAG_ENABLE_LLM_GRADER")
    rag_retrieval_timeout: float = Field(default=3.0, alias="RAG_RETRIEVAL_TIMEOUT")
    rag_reranker_timeout: float = Field(default=8.0, alias="RAG_RERANKER_TIMEOUT")
    rag_grader_timeout: float = Field(default=3.0, alias="RAG_GRADER_TIMEOUT")
    rag_rewrite_timeout: float = Field(default=3.0, alias="RAG_REWRITE_TIMEOUT")
    rag_max_output_tokens: int = Field(default=500, alias="RAG_MAX_OUTPUT_TOKENS")
    rag_grader_max_output_tokens: int = Field(default=150, alias="RAG_GRADER_MAX_OUTPUT_TOKENS")
    rag_rewrite_max_output_tokens: int = Field(default=100, alias="RAG_REWRITE_MAX_OUTPUT_TOKENS")
    rag_debug_logging: bool = Field(default=False, alias="RAG_DEBUG_LOGGING")

    # Phase 8 Memory System Settings
    memory_enabled: bool = Field(default=True, alias="MEMORY_ENABLED")
    memory_min_confidence: float = Field(default=0.70, alias="MEMORY_MIN_CONFIDENCE")
    memory_min_importance: float = Field(default=0.60, alias="MEMORY_MIN_IMPORTANCE")
    memory_top_k: int = Field(default=5, alias="MEMORY_TOP_K")
    thread_summary_threshold: int = Field(default=10, alias="THREAD_SUMMARY_THRESHOLD")
    temporary_chat_memory_enabled: bool = Field(default=False, alias="TEMPORARY_CHAT_MEMORY_ENABLED")

    # Phase 9 Tool Calling & Tool Infrastructure Settings
    tool_calling_enabled: bool = Field(default=True, alias="TOOL_CALLING_ENABLED")
    max_tool_calls: int = Field(default=5, alias="MAX_TOOL_CALLS")
    tool_timeout_seconds: float = Field(default=10.0, alias="TOOL_TIMEOUT_SECONDS")
    max_tool_output_size: int = Field(default=15000, alias="MAX_TOOL_OUTPUT_SIZE")
    web_search_provider: str = Field(default="duckduckgo", alias="WEB_SEARCH_PROVIDER")
    news_provider: str = Field(default="duckduckgo", alias="NEWS_PROVIDER")
    weather_provider: str = Field(default="openmeteo", alias="WEATHER_PROVIDER")
    currency_provider: str = Field(default="frankfurter", alias="CURRENCY_PROVIDER")
    finance_provider: str = Field(default="yahoo", alias="FINANCE_PROVIDER")
    crypto_provider: str = Field(default="coingecko", alias="CRYPTO_PROVIDER")

    # Phase 10 Deep Research + LangGraph Settings
    deep_research_enabled: bool = Field(default=True, alias="DEEP_RESEARCH_ENABLED")
    max_research_tasks: int = Field(default=8, alias="MAX_RESEARCH_TASKS")
    max_parallel_research_tasks: int = Field(default=3, alias="MAX_PARALLEL_RESEARCH_TASKS")
    max_research_retries: int = Field(default=1, alias="MAX_RESEARCH_RETRIES")
    research_task_timeout_seconds: float = Field(default=30.0, alias="RESEARCH_TASK_TIMEOUT_SECONDS")
    max_sources_per_task: int = Field(default=5, alias="MAX_SOURCES_PER_TASK")
    max_total_sources: int = Field(default=20, alias="MAX_TOTAL_SOURCES")
    max_research_context_tokens: int = Field(default=12000, alias="MAX_RESEARCH_CONTEXT_TOKENS")
    research_planner_model: str | None = Field(default=None, alias="RESEARCH_PLANNER_MODEL")
    research_worker_model: str | None = Field(default=None, alias="RESEARCH_WORKER_MODEL")
    research_synthesizer_model: str | None = Field(default=None, alias="RESEARCH_SYNTHESIZER_MODEL")

    # Voice Mode Settings
    voice_stt_provider: str = Field(default="browser", alias="VOICE_STT_PROVIDER")
    voice_tts_provider: str = Field(default="browser", alias="VOICE_TTS_PROVIDER")

    # Google OAuth & Calendar Integration Settings
    google_client_id: str | None = Field(default=None, alias="GOOGLE_CLIENT_ID")
    google_client_secret: str | None = Field(default=None, alias="GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str = Field(
        default="http://localhost:8001/api/v1/integrations/google/calendar/callback",
        alias="GOOGLE_REDIRECT_URI",
    )

    # GitHub MCP & API Integration Settings
    github_personal_access_token: str | None = Field(default=None, alias="GITHUB_PERSONAL_ACCESS_TOKEN")


    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
