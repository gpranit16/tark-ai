# DECISIONS.md — TARK AI Architecture Decision Records (ADR)

## ADR-001: PostgreSQL Port Mapping Strategy
- **Context**: Local environment contains multiple PostgreSQL instances. Docker container `tarkai-postgres` maps host port `5433` to container port `5432`.
- **Decision**: Backend database URL configuration strictly connects to `127.0.0.1:5433` in development mode to target the project's dedicated container without host port collisions.

## ADR-002: Model Routing & Fallback Design
- **Context**: Users can toggle between `fast`, `normal`, and `reasoning` execution modes.
- **Decision**: Model selection maps to designated default providers (Groq by default) with automatic fallback handlers configured in `ModelRouter` to prevent chat failure during provider outages.

## ADR-003: Hierarchical Message Structure
- **Context**: Future support required for message editing, regeneration, and thread branching.
- **Decision**: The `messages` database table includes a self-referencing `parent_message_id` foreign key.

## ADR-004: Storage Provider Abstraction
- **Context**: Development requires zero-dependency local filesystem storage while production targets Backblaze B2 object storage.
- **Decision**: Storage operations will be encapsulated behind a unified `StorageProvider` interface (`local` vs `b2`).

## ADR-005: Local BGE-M3 Dense Embedding Provider
- **Context**: RAG retrieval requires high-quality, multilingual, zero-API-cost dense embeddings without hardcoded dimension constraints or vendor lock-in.
- **Decision**: Adopt `BAAI/bge-m3` as the default local embedding model running via `sentence-transformers`, generating normalized 1024-dimensional dense vectors with configurable parameters in `Settings`.

## ADR-006: Dual-Index Strategy for PostgreSQL pgvector
- **Context**: Efficient vector similarity search requires approximate nearest neighbor indexing while keyword search requires lexical inverted index support on the same table.
- **Decision**: The `document_chunks` table implements an HNSW index (`USING hnsw (embedding vector_cosine_ops)`) for vector cosine distance and a GIN index (`USING gin (to_tsvector('english', content))`) for full-text search.

## ADR-007: Modular Retrieval and Context Synthesis Layer
- **Context**: Need flexible search strategies (dense vector, sparse keyword, weighted hybrid) and LLM-agnostic context assembly with citation tracking before introducing complex rerankers or CRAG.
- **Decision**: Decouple `VectorRetriever`, `KeywordRetriever`, `HybridRetriever`, and `ContextBuilder` into distinct modular services, isolating the ranking calculation to enable simple drop-in addition of Reciprocal Rank Fusion (RRF) in Phase 7.

## ADR-008: Two-Layer Memory Architecture & Deduplication Strategy
- **Context**: Need personalized responses that preserve user preferences and project-specific facts across sessions without bloating the prompt context or polluting long-term memory with conversational fluff or document chunks.
- **Decision**: Implement a two-layer memory model:
  1. **Short-Term Memory**: Sliding window context + incremental thread summarization (`ThreadSummaryService`) stored directly on the `threads` table when message count exceeds `THREAD_SUMMARY_THRESHOLD`.
  2. **Long-Term Memory**: Structured `memories` table storing typed categories (`preference`, `fact`, `goal`, `skill`, `interest`, `project_context`, `other`), confidence/importance scores, and project scoping.
  - Candidate extraction runs via `MemoryExtractor` filtering fluff and document queries.
  - Deduplication and conflict resolution in `MemoryService` updates existing active records on key match, bumping confidence or recording provenance history in `metadata["history"]` when preferences change.
  - Temporary chat mode strictly suppresses memory extraction and long-term persistence.

## ADR-009: Tool Execution Architecture, Zero-Key Default Providers & Sandboxing
- **Context**: Autonomous tool execution requires a model-agnostic, secure, and extensible architecture that prevents remote code execution, prompt injection, infinite execution loops, and Server-Side Request Forgery (SSRF) without exposing third-party API keys to the frontend or requiring paid services.
- **Decision**:
  1. **Provider-Agnostic Core (`BaseTool`, `ToolRegistry`, `ToolExecutor`)**: Standardized input schema, normalized `ToolResult`, and permissions (`SAFE`, `NETWORK`, `USER_DATA`, `SYSTEM`).
  2. **Security Sandboxing**:
     - `SafeMathEvaluator`: Parses expressions using Python `ast` syntax tree validation. Disallows imports, `eval()`, code execution statements, arbitrary variables, and enforces upper power bounds.
     - `SSRFValidator`: Rejects loopback (`127.0.0.1`, `localhost`), RFC 1918 private subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), link-local/cloud metadata (`169.254.169.254`), and internal TLDs (`.local`, `.internal`).
  3. **Zero-Key Default Providers**:
     - Web Search: DuckDuckGo HTML Lite scraping.
     - Weather: Open-Meteo geocoding and forecast API.
     - Currency: Frankfurter / ECB exchange rates.
     - Equities / Cryptos: Yahoo Finance quote endpoints and CoinGecko public APIs.
  4. **Bounded Multi-Step Orchestration**: `ToolCallOrchestrator` caps executions at `MAX_TOOL_CALLS=5`, streams tool status events over SSE (`tool_available`, `tool_started`, `tool_result`, `tool_error`), and synthesizes final answers seamlessly across any LLM.

## ADR-010: LangGraph Multi-Agent Architecture for Deep Research
- **Context**: Deep research requires complex multi-step reasoning, query decomposition, parallel execution across disparate data sources (web, internal workspace documents, financial data), iterative verification against hallucination, and citation-backed synthesis without blocking or duplicating thread state.
- **Decision**:
  1. **StateGraph Framework**: Build an asynchronous graph using LangGraph `StateGraph` operating on typed `ResearchState` with operator-additive reducers for evidence and task result aggregation.
  2. **Specialized Agents**:
     - `PlannerAgent`: Deconstructs research queries into focused parallel tasks.
     - `WebAgent`: Executes parallel web searches and extracts page content via SSRF-shielded HTTP readers.
     - `DocumentAgent`: Searches workspace document chunks using vector retrieval.
     - `FinanceAgent`: Fetches and analyzes equities and cryptocurrency metrics.
     - `VerifierAgent`: Computes evidence sufficiency, detects information gaps and conflicting claims.
     - `RefinerAgent`: Generates targeted follow-up queries when verification indicates missing aspects (bounded by max retries).
     - `SynthesizerAgent`: Produces comprehensive Markdown reports with structured citation indices.
  3. **In-Thread Seamless Integration**: Research executes within the user's active chat thread without spawning disjoint threads, storing metadata in `research_sessions` while streaming rich progress steps over SSE.

## ADR-011: Project Workspaces and Deterministic Precedence Context Assembly
- **Context**: Workspaces require encapsulating custom instructions, isolated memories, attached files, threads, and research history with zero data leakage across projects or users, while maintaining consistent LLM behavior regardless of provider.
- **Decision**:
  1. **Enhanced Project Entity**: Extend `Project` with `custom_instructions`, `avatar`, `is_archived`, and `project_metadata`. Link `files.project_id` and `research_sessions.project_id`.
  2. **Deterministic Context Precedence**: Context builder (`ProjectContextBuilder`) injects blocks strictly in descending priority:
     `System Identity -> Developer Safety -> Global Config -> Project Custom Instructions -> Relevant Memories -> RAG / Research Context -> Thread Summary -> Recent Turn History`.
  3. **Multi-Tenant / Cross-Project Isolation**: Memory queries and RAG retrieval always enforce `WHERE user_id = :uid AND (project_id = :pid OR project_id IS NULL)` so project-specific facts never contaminate unrelated projects.

## ADR-012: Coding Mode, File-Aware Context & Execution Safety Guardrails
- **Context**: Coding tasks (generation, debugging, refactoring, code review, test generation) require multi-file code awareness, structural symbol parsing, standardized diff output, and bounded token usage without risking server-side remote code execution or file corruption.
- **Decision**:
  1. **Single ModelRouter Integration**: Coding Mode reuses the unified `ModelRouter` and configurable providers (`CODING_PROVIDER`, `CODING_MODEL`) rather than a parallel LLM framework.
  2. **Bounded Code Context Builder (`CodeContextBuilder`)**: Ingests attached and project files with language detection, lightweight symbol extraction (classes, functions, routes), and hard constraints (`CODING_MAX_FILES`, `CODING_MAX_FILE_SIZE`, `CODING_MAX_CONTEXT_TOKENS`).
  3. **Execution Safety & Honesty Guardrail**: The system prompt explicitly forbids claiming that code was executed or applied to disk unless verified tool execution occurred. Code modifications are presented as suggested diffs / patches.
  4. **Granular SSE Stream Protocol**: Emits `coding_started`, `coding_file`, `coding_context_ready`, `coding_generation`, and `coding_complete` events alongside token deltas for real-time frontend observability.
