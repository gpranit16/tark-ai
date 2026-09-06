# ROADMAP.md — TARK AI Implementation Roadmap

## Completed Phases

### Phase 1: Backend Foundation ✅
- FastAPI application setup with Alembic database migrations.
- SQLAlchemy async models for Users, Projects, Threads, and Messages.
- Dockerized PostgreSQL + pgvector container configuration.
- REST endpoints for Thread and Message CRUD operations.
- Backend test suite with 15 passing integration tests.

### Phase 2: AI Chat Backend ✅
- Unified provider interface (`BaseProvider`) supporting Groq, Gemini, and Mistral.
- Model router supporting dynamic fallback mechanisms and mode-based selection (`fast`, `normal`, `reasoning`).
- Streaming response generation over Server-Sent Events (SSE).
- Message token usage and latency telemetry tracking.

### Phase 3: Frontend AI Workspace UI ✅
- Charcoal & Champagne visual design system built with Vite, React, and Tailwind CSS.
- Responsive sidebar navigation for threads and feature routes.
- Real-time Markdown rendering with code highlighting (`rehype-highlight`, `remark-gfm`).
- Optimistic user message dispatch and live SSE stream rendering.

### Phase 4: File Upload & Storage ✅
- Storage provider abstraction (`LocalStorageProvider` & `B2StorageProvider`).
- Multi-format file validation, upload, ownership scoping, and CRUD endpoints.
- Message composer drag-and-drop file attachment interface.

### Phase 5: Document Ingestion & Structure Extraction ✅
- Multi-format document parsers for PDF, DOCX, PPTX, TXT, MD, CSV, XLSX.
- Scanned document detection and OCR extraction using Tesseract.
- Structured document schema preservation (pages, blocks, tables, images).

### Phase 6: Embeddings + pgvector + Retrieval / RAG Foundation ✅
- Structure-aware document chunking (`DocumentChunker`) with metadata preservation.
- Dense 1024-dimensional local embeddings via `BAAI/bge-m3`.
- PostgreSQL `document_chunks` table with pgvector HNSW and GIN full-text search indexes.
- Idempotent embedding ingestion pipeline with retry capability.
- Multi-strategy retrieval (Dense Vector Similarity, PostgreSQL Full-Text Keyword Search, Weighted Hybrid Search).
- ContextBuilder with deduplication, token constraints, and source citations.
- Frontend ContextPanel knowledge search tester.

---

### Phase 7: Hybrid RAG & Corrective Retrieval Engine (CRAG) ✅
- Reciprocal Rank Fusion (RRF) and BGE-reranker-v2 integration.
- Document grounding confidence grading, dynamic query rewriting loops, and CRAG fallback.
- Citation tracking down to page number, document filename, and chunk ID in assistant streaming responses.

### Phase 8: Memory System ✅
- Two-layer memory architecture (short-term thread context and summarization + selective long-term personalization).
- `Memory` schema with categories, confidence, importance, provenance metadata, and project scoping.
- Deduplication and conflict resolution preserving previous values in history.
- `MemoryRetriever` relevance search and prompt context injection bounded by `MEMORY_TOP_K`.
- Incremental `ThreadSummaryService` for long conversations exceeding `THREAD_SUMMARY_THRESHOLD`.
- Temporary chat mode with incognito privacy controls.
- REST API endpoints for memory CRUD, search, and candidate extraction.
- Frontend Memory management dashboard and Temporary Chat toggle UI.

### Phase 9: Tool Calling & Tool Infrastructure ✅
- Provider-agnostic tool calling abstraction (`BaseTool`, `ToolPermission`, `ToolResult`, `ToolExecutionContext`).
- Central `ToolRegistry` with dynamic catalog discovery, schemas, and `ToolExecutor` guardrails (permissions, timeouts, SSRF shield, AST parsing).
- 11 zero-cost built-in tools:
  - `calculator`: AST-evaluated safe math engine with percentage & scientific calculations (no `eval()`).
  - `web_search`: Live search results via DuckDuckGo without API keys.
  - `read_url`: SSRF-shielded web reader with RFC1918 / cloud metadata blocking.
  - `get_weather`: Open-Meteo free geocoding and 3-day forecast.
  - `convert_currency`: Frankfurter / European Central Bank fiat currency conversion.
  - `search_news`: DuckDuckGo / Google News RSS headline search.
  - `get_stock_price`: Public Yahoo Finance equity quotes and market metrics.
  - `get_crypto_price`: CoinGecko public API crypto quotes and market data.
  - `search_knowledge_base`: User-isolated hybrid RAG search across workspace documents.
  - `search_user_memory`: Scoped long-term memory retrieval.
  - `search_conversation_history`: Historical threads and messages search.
- Multi-step bounded tool execution loop (`ToolCallOrchestrator`) integrated into SSE streaming (`tool_available`, `tool_started`, `tool_result`, `tool_error`).
- REST endpoints (`GET /api/v1/tools`, `POST /api/v1/tools/execute`).
- Frontend Tools dashboard (`/tools`) with catalog filtering and interactive sandbox tester workbench.

### Phase 10: Deep Research + LangGraph Multi-Agent System ✅
- Multi-agent autonomous research system built with LangGraph `StateGraph`.
- In-thread execution reusing existing thread/messages/database/provider architecture.
- Specialized agents and workflow nodes:
  - `ResearchManager`: Session orchestration, persistence, and cancellation registry.
  - `PlannerAgent`: Query decomposition into structured sub-tasks with agent type assignment (`web`, `document`, `finance`).
  - `WebAgent`: Parallel web search queries + top URL fetching with DuckDuckGo.
  - `DocumentAgent`: Workspace document chunk vector similarity retrieval.
  - `FinanceAgent`: Stock / crypto price and financial metric analysis.
  - `VerifierAgent`: Evidence validation, claim support verification, and gap detection.
  - `RefinerAgent`: Adaptive task re-planning for missing or conflicting information.
  - `SynthesizerAgent`: Structured comprehensive Markdown synthesis with numbered citations.
- 15 granular SSE event stream indicators (`research_started`, `research_plan_created`, `research_task_started`, `research_evidence_collected`, `research_verification_complete`, `research_complete`, etc.).
- `ResearchSession` database table and Alembic migration `20260904_0009_add_research_sessions.py`.
- REST endpoints (`POST /api/v1/research/stream`, `POST /api/v1/research/{id}/cancel`, `GET /api/v1/research/{id}`, `GET /api/v1/research/`).
- Frontend components: `ResearchProgress` (accordion progress bar with live event logs), `ResearchCitations` (rich source badge links), and composer mode selector activation.

---

### Phase 11: Projects + Advanced Workspace Context ✅
- Enhanced `Project` workspace model with `custom_instructions`, `avatar`, `is_archived`, `project_metadata`, and foreign key relations.
- Project Files: Direct file attachment, scoping, detachment, and RAG document ingestion pipeline linking.
- Project Threads: Thread association, filtering, workspace switching, and standalone thread reassignment.
- Project Memory: Scoped long-term memory isolation (zero cross-project leakage), strictly querying project-specific and user-global facts.
- Project Research History: Deep Research sessions permanently linked and queried by `project_id`.
- `ProjectContextBuilder`: Deterministic context assembly enforcing strict precedence (System -> Safety -> Global Config -> Project Custom Instructions -> Relevant Memories -> RAG/Research Context -> Thread Summary -> Recent Messages).
- Alembic database migration `20260904_0010_enhance_projects_and_workspace.py`.
- REST API router (`/api/v1/projects`) with full CRUD, archive/restore, file link/unlink, thread link/unlink, memory, and research endpoints.
- Frontend Workspace UI:
  - Projects dashboard (`/projects` & `/projects/:projectId`) with tabbed management (Instructions, Files, Threads, Memory, Research).
  - Sidebar workspace switcher with active project indicator and project-scoped thread filtering.
  - Chat header active project pill and automatic project tagging on new conversations.

---

### Phase 12: Coding Mode + Code Workspace ✅
- Dedicated `Coding Mode` leveraging unified `ModelRouter` and configurable providers (`CODING_PROVIDER`, `CODING_MODEL`, `CODING_MAX_CONTEXT_TOKENS`, `CODING_MAX_FILES`, `CODING_MAX_FILE_SIZE`, `CODING_TEMPERATURE`).
- `CodeContextBuilder` with multi-file workspace awareness, language detection, symbol extraction, token budgeting, and strict multi-tenant scoping.
- Dedicated `CODING_SYSTEM_PROMPT` enforcing correctness, runnable code, minimal changes, no execution claims without tool execution, root-cause debugging, structured code review with severity levels, and standardized diff output.
- Full code file support across all major languages (`.py`, `.js`, `.jsx`, `.ts`, `.tsx`, `.html`, `.css`, `.json`, `.sql`, `.yaml`, `.xml`, `.java`, `.cpp`, `.c`, `.go`, `.rs`, `.php`, etc.).
- 6 Granular SSE Stream Events (`coding_started`, `coding_file`, `coding_context_ready`, `coding_generation`, `coding_complete`, `coding_error`).
- REST API endpoint (`POST /api/v1/coding/query`) and in-thread chat dispatch (`/api/v1/threads/{id}/chat`).
- Frontend Coding UI:
  - Mode selector integration with active coding indicator pill.
  - Enhanced `CodeBlock` component with language tags, copy button with state feedback, file path header labels, unified diff line highlighting (+/-), and collapsible sections.
  - `CodingProgress` status accordion rendering loaded files and patch generation progress.
- 24 comprehensive unit and E2E test cases passing.

---

## Upcoming Phases

### Phase 13: Security, Observability, Telemetry & Guardrails
### Phase 14: Production Hardening, Packaging & Deployment

