# PROJECT_CONTEXT.md — TARK AI Project Status & Implementation Details

## Overview
TARK AI is an enterprise-grade, multi-provider AI workspace supporting persistent thread management, dynamic LLM routing, real-time SSE streaming, file storage, multi-format document parsing, OCR, and dense/sparse/hybrid vector retrieval via PostgreSQL `pgvector` and BGE-M3 embeddings.

---

## Technical Stack
- **Frontend**: React (Vite, JS, React Router v6), Tailwind CSS, TanStack Query, Zustand, Lucide Icons, Markdown parsing (`react-markdown`, `remark-gfm`, `rehype-highlight`).
- **Backend**: FastAPI (Python 3.12+), SQLAlchemy 2.0 (Async), Alembic, Pydantic v2, PyPDF, python-docx, python-pptx, openpyxl, pytesseract, Pillow, sentence-transformers.
- **Database**: PostgreSQL 16 + `pgvector` extension running in Docker (`tarkai-postgres`) mapped to `127.0.0.1:5433`.
- **Embeddings**: Local `BAAI/bge-m3` (1024-dimensional dense vectors, normalized).
- **AI Infrastructure**: Unified provider abstraction (`BaseProvider`) supporting Groq, Gemini, and Mistral. Configurable fallback & mode routing (`fast`, `normal`, `reasoning`).

---

## Active Configuration & Ports
- **Backend Server**: `http://127.0.0.1:8001`
- **Frontend Server**: `http://localhost:5173`
- **Database Host/Port**: `127.0.0.1:5433` (Database name: `tarkai`, User: `tarkai`)
- **Default Seed Dev User ID**: `00000000-0000-0000-0000-000000000001`

---

## Implemented Architecture

### 1. Database Schema
- `User` (`app/models/conversation.py`): Base user identity table.
- `Project` (`app/models/conversation.py`): Project workspaces belonging to users (`user_id`).
- `Thread` (`app/models/conversation.py`): Conversation threads associated with users and optional projects.
- `Message` (`app/models/conversation.py`): Chat messages supporting roles (`user`, `assistant`, `system`), metadata tracking, and parent-child tree hierarchy (`parent_message_id`).
- `File` (`app/models/file.py`): Stored file metadata, storage keys, MIME validation, and status tracking.
- `ParsedDocument` (`app/models/document.py`): Extracted structured document content (pages, blocks, tables, images) and OCR status.
- `DocumentChunk` (`app/models/chunk.py`): Chunked document texts with 1024-d BGE-M3 embeddings, page numbers, metadata JSONB, HNSW vector index, GIN full-text search index, and cascading foreign keys.

### 2. Document Processing & Ingestion Pipeline
- `DocumentChunker` (`app/services/chunking/document_chunker.py`): Structure-preserving chunker with sliding window overlap and block metadata preservation.
- `LocalBGEEmbeddingProvider` (`app/services/embeddings/bge.py`): Local dense embeddings using `BAAI/bge-m3` (1024 dimensions, cosine normalized).
- `EmbeddingIngestionService` (`app/services/embeddings/ingestion.py`): Idempotent file embedding and chunk persistence pipeline with retry capabilities.

### 3. Multi-Strategy Retrieval & Context Building
- `VectorRetriever` (`app/services/retrieval/vector.py`): Dense cosine distance similarity search using pgvector.
- `KeywordRetriever` (`app/services/retrieval/keyword.py`): Native PostgreSQL full-text search using `to_tsvector`, `plainto_tsquery`, and `ts_rank` with ILIKE fallback.
- `HybridRetriever` (`app/services/retrieval/hybrid.py`): Weighted hybrid search merging dense semantic and sparse lexical matches.
- `ContextBuilder` (`app/services/retrieval/context_builder.py`): LLM-ready context synthesis with deduplication, token capping, and structured source citations.

### 4. AI Router & Provider Services (`app/providers/`, `app/services/chat/`)
- `BaseProvider`: Abstract base class enforcing async generator streaming interface (`stream_chat`).
- `GroqProvider`, `GeminiProvider`, `MistralProvider`: Concrete implementations normalized to `ProviderStreamEvent`.
- `ModelRouter`: Dynamically resolves provider and model according to mode/override settings with automatic fallback.
- `ChatService`: Manages context windowing, message persistence, stream emission via SSE, and error handling.

### 5. Memory System & Context Summarization (`app/services/memory/`)
- `Memory` (`app/models/memory.py`): Long-term memory table storing category, key, value, confidence, importance, project_id, metadata JSONB, source, and is_active flag.
- `MemoryExtractor` (`app/services/memory/extractor.py`): Intelligent candidate extractor identifying user preferences, facts, goals, skills, interests, and project context while rejecting fluff and RAG document queries.
- `MemoryRepository` & `MemoryService` (`app/services/memory/`): CRUD, semantic/key-based deduplication, provenance history preservation, and conflict resolution.
- `MemoryRetriever` (`app/services/memory/retriever.py`): Relevance-based scoring and formatted context injection bounded by `MEMORY_TOP_K`.
- `ThreadSummaryService` (`app/services/memory/summarizer.py`): Incremental short-term thread summarization triggered when conversation exceeds `THREAD_SUMMARY_THRESHOLD`.
- Temporary Chat Privacy: Zero memory extractions or writes when temporary chat mode is active.

### 6. Tool Calling & Tool Infrastructure (`app/tools/`, `app/services/chat/tool_loop.py`)
- `BaseTool` (`app/tools/base.py`): Abstract base class defining tool metadata, input schema validation, execution context (`user_id`, `project_id`, `thread_id`, `session`), and security permissions (`SAFE`, `NETWORK`, `USER_DATA`, `SYSTEM`).
- `ToolRegistry` (`app/tools/registry.py`): Central tool discovery registry with dynamic catalog and OpenAI-compatible function schema generation.
- `ToolExecutor` (`app/tools/executor.py`): Isolated tool runner with schema validation, permission checks, `asyncio.wait_for` timeout enforcement (10s), output truncation, and sanitization.
- `ToolCallOrchestrator` (`app/services/chat/tool_loop.py`): Multi-step bounded execution loop with regex/JSON extraction, iterative reasoning, and real-time SSE tool events (`tool_available`, `tool_started`, `tool_result`, `tool_error`).
- 11 Zero-Cost Built-in Tools:
  - `calculator` (`app/tools/builtins/calculator.py`): Safe AST-based math evaluator with percentages & trigonometry (no `eval()`).
  - `web_search` (`app/tools/builtins/web_search.py`): DuckDuckGo HTML Lite live web search.
  - `read_url` (`app/tools/builtins/url_reader.py`): SSRF-shielded web content extractor.
  - `get_weather` (`app/tools/builtins/weather.py`): Open-Meteo geocoding and 3-day forecast.
  - `convert_currency` (`app/tools/builtins/currency.py`): Frankfurter / ECB live exchange rates.
  - `search_news` (`app/tools/builtins/news.py`): DuckDuckGo / Google News RSS current events.
  - `get_stock_price` (`app/tools/builtins/finance.py`): Yahoo Finance real-time equity quotes.
  - `get_crypto_price` (`app/tools/builtins/crypto.py`): CoinGecko public API crypto quotes.
  - `search_knowledge_base` (`app/tools/builtins/knowledge_search.py`): Scoped hybrid retrieval tool.
  - `search_user_memory` (`app/tools/builtins/memory_search.py`): Scoped user long-term memory query tool.
  - `search_conversation_history` (`app/tools/builtins/conversation_search.py`): Past threads & messages search tool.
- Frontend Tools Workbench (`frontend/src/pages/ToolsPage.jsx`): Interactive playground with catalog cards, permission badges, sample input auto-fill, and live execution tester console.


### 7. Deep Research & LangGraph Multi-Agent System (`app/services/research/`)
- `ResearchSession` (`app/models/research.py`): Tracks Deep Research executions, query, plan, tasks, duration, confidence, and source metadata.
- `StateGraph` Workflow (`app/services/research/graph.py`): Typed `ResearchState` orchestrating query decomposition, parallel execution across agents, evidence aggregation, claim verification, adaptive refinement, and final report synthesis.
- Multi-Agent Nodes (`app/services/research/nodes/`):
  - `PlannerAgent`: Deconstructs user prompt into discrete research sub-tasks.
  - `WebAgent`: Executes parallel search and URL content fetching via DuckDuckGo.
  - `DocumentAgent`: Searches workspace document chunks via vector similarity.
  - `FinanceAgent`: Analyzes equity and cryptocurrency ticker metrics.
  - `VerifierAgent`: Checks evidence sufficiency, detects unsupported claims, and flags contradictory information.
  - `RefinerAgent`: Automatically reformulates queries for detected gaps.
  - `SynthesizerAgent`: Generates structured comprehensive Markdown with numbered source citations.
- 15 Deep Research SSE Event Helpers (`app/services/research/sse.py`).
- Frontend Deep Research UI (`frontend/src/components/chat/ResearchProgress.jsx`, `ResearchCitations.jsx`, `ChatRoute.jsx`).

### 8. Coding Mode & Code Workspace (`app/services/coding/`)
- `CodeContextBuilder` (`app/services/coding/context.py`): Assembles focused code context with multi-file awareness, symbol extraction, language detection, and strict token bounding.
- `CodingService` (`app/services/coding/service.py`): In-thread coding chat and standalone query execution with diff extraction and SSE streaming.
- `CODING_SYSTEM_PROMPT` (`app/services/coding/system_prompt.py`): Enforces correctness, runnable code, minimal edits, no execution hallucination, root-cause debugging, structured code review, and standardized diffs.
- Code File Support: Full ingestion and parsing support for `.py`, `.js`, `.jsx`, `.ts`, `.tsx`, `.html`, `.css`, `.json`, `.sql`, `.yaml`, `.xml`, `.java`, `.cpp`, `.c`, `.go`, `.rs`, `.php`, etc.
- 6 Coding SSE Event Helpers (`app/services/chat/sse.py`): `coding_started`, `coding_file`, `coding_context_ready`, `coding_generation`, `coding_complete`, `coding_error`.
- REST API: `POST /api/v1/coding/query` and seamless `mode: "coding"` dispatch in `/api/v1/threads/{id}/chat`.
- Frontend Coding UI (`frontend/src/components/chat/CodeBlock.jsx`, `CodingProgress.jsx`, `ChatRoute.jsx`): Rich code blocks with language pills, copy button, file path headers, diff line styling (+/-), collapsible views, and live workspace progress indicators.

### 9. Frontend Application Structure (`frontend/src/`)
- `App.jsx`: Global router setup with TanStack Query Provider and routes.
- `components/layout/Layout.jsx`: Main UI layout containing collapsible sidebar, main chat window, and context drawer.
- `components/context/ContextPanel.jsx`: Knowledge & semantic retrieval tester supporting Hybrid/Vector/Keyword search modes with match scoring and source citations.
- `pages/ChatRoute.jsx`: Primary chat interface with Markdown rendering, file attachment dropzone, Temporary Chat toggle, Coding mode selector, Deep Research mode selector, live progress accordions, and citations.
- `pages/ProjectsPage.jsx` & `ProjectDetailPage.jsx`: Project workspace management.
- `pages/MemoryPage.jsx`: Memory management center.
- `pages/ToolsPage.jsx`: Interactive tool playground.

---

## Verification Status
- **Backend Tests**: 24/24 Phase 12 coding tests passing (`pytest tests/test_coding.py -v`).
- **Frontend Build**: Verified production build clean (`npm run build`).
- **Health Check Endpoint**: `/health` returning `200 OK`.

