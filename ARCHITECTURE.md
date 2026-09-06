# ARCHITECTURE.md — TARK AI System Architecture

## System Overview

```
 +-----------------------------------------------------------------------+
 |                            React Frontend                             |
 |    (Vite, Tailwind CSS, TanStack Query, Zustand, React Markdown)      |
 +-----------------------------------+-----------------------------------+
                                     |
                          HTTP / SSE (Port 8001)
                                     v
 +-----------------------------------------------------------------------+
 |                           FastAPI Backend                             |
 |                                                                       |
 |   +---------------------------------------------------------------+   |
 |   |                      API Router (/api/v1)                     |   |
 |   |   /threads | /messages | /files | /documents | /retrieval     |   |
 |   |   /memory  | /rag      | /tools                               |   |
 |   +-------------------------------+-------------------------------+   |
 |                                   |                                   |
 |   +-------------------------------+-------------------------------+   |
 |   |                   Tool Infrastructure Layer                   |   |
 |   |   ToolRegistry | ToolExecutor | ToolCallOrchestrator          |   |
 |   |   SafeMathEvaluator | SSRFValidator | 11 Built-in Tools       |   |
 |   +-------------------------------+-------------------------------+   |
 |                                   |                                   |
 |   +-------------------------------+-------------------------------+   |
 |   |                   Memory & Context Engine                     |   |
 |   |   MemoryExtractor | MemoryRetriever | MemoryService           |   |
 |   |   ThreadSummaryService | MemoryRepository                     |   |
 |   +-------------------------------+-------------------------------+   |
 |                                   |                                   |
 |   +-------------------------------+-------------------------------+   |
 |   |                   Retrieval & Ingestion Layer                 |   |
 |   |   VectorRetriever | KeywordRetriever | HybridRetriever        |   |
 |   |   DocumentChunker | LocalBGEProvider | ContextBuilder         |   |
 |   +-------------------------------+-------------------------------+   |
 |                                   |                                   |
 |   +-------------------------------+-------------------------------+   |
 |   |                         Chat Service                          |   |
 |   |     Context Normalization | SSE Dispatcher | Message Sync     |   |
 |   +-------------------------------+-------------------------------+   |
 |                                   |                                   |
 |   +-------------------------------+-------------------------------+   |
 |   |                         Model Router                          |   |
 |   |          Mode Selection & Fallback Logic Resolution           |   |
 |   +---------------+---------------+---------------+---------------+   |
 |                   |               |               |                   |
 |                   v               v               v                   |
 |           +---------------+---------------+---------------+           |
 |           | Groq Provider | GeminiProvider|MistralProvider|           |
 |           +---------------+---------------+---------------+           |
 +-----------------------------------+-----------------------------------+
                                     |
                               Async SQLAlchemy
                                     v
 +-----------------------------------------------------------------------+
 |                     PostgreSQL 16 + pgvector DB                       |
 |                         (Docker Port 5433)                            |
 |                                                                       |
 |   - memories (User & Project Long-Term Personalization)               |
 |   - files                                                             |
 |   - parsed_documents                                                  |
 |   - document_chunks (HNSW Vector Index + GIN Full-Text Index)         |
 |   - users / projects / threads (with Summary) / messages              |
 +-----------------------------------------------------------------------+
```

---

## Data Models & Schema Design

### Entity Relationships
- **User**: Root record (`id` UUID).
- **Project**: Belongs to `User`. Workspace container for threads, files, chunks, and memories.
- **Thread**: Belongs to `User` and optional `Project`. Stores conversation history, short-term thread summary, and temporary chat flags.
- **Message**: Belongs to `Thread`. Supports parent-child tree hierarchy (`parent_message_id`).
- **Memory**: Belongs to `User` and optional `Project`. Stores categories (`preference`, `fact`, `goal`, `skill`, `interest`, `project_context`, `other`), keys, values, confidence, importance, provenance metadata, and active state.
- **File**: Belongs to `User` and optional `Project`. Stores uploaded raw files.
- **ParsedDocument**: Belongs to `File` and `User`. Stores structured pages, blocks, tables, and OCR metadata.
- **DocumentChunk**: Belongs to `File`, `User`, `Project`, and `ParsedDocument`. Stores chunked text content, page numbers, metadata JSONB, and 1024-dimensional BGE-M3 embeddings.
- **ResearchSession**: Belongs to `Thread` and `User`. Stores Deep Research run status, decomposed plan, execution metrics, confidence, and citation metadata.

---

## Deep Research & Multi-Agent Architecture (LangGraph)
- **StateGraph**: Typed `ResearchState` orchestrating query decomposition, parallel execution, evidence aggregation, verification, adaptive refinement, and synthesis.
- **Agent Nodes**:
  - `Planner`: Breaks down complex prompts into independent research tasks across web, document, and finance domains.
  - `WebAgent`: Executes parallel web queries and fetches full page text via DuckDuckGo + HTML parser.
  - `DocumentAgent`: Queries workspace vector embeddings using pgvector similarity.
  - `FinanceAgent`: Evaluates stock ticker prices and cryptocurrency metrics.
  - `Verifier`: Assesses evidence sufficiency, identifies unsupported claims, and flags contradictory information.
  - `Refiner`: Reformulates search queries for detected knowledge gaps.
  - `Synthesizer`: Builds a comprehensive Markdown report structured with numbered citations.

---

## SSE Event Flow
1. **Chat SSE**: `message_start` -> `text_delta` (or `tool_started`/`tool_result`) -> `message_complete`.
2. **Deep Research SSE**:
   - `research_started`
   - `research_planning` -> `research_plan_created`
   - `research_task_started` -> `research_task_progress` -> `research_task_completed`
   - `research_evidence_collected`
   - `research_verification_started` -> `research_verification_complete`
   - `research_retry` (if gaps detected)
   - `research_synthesis_started` -> `text_delta` chunks -> `research_citation`
   - `research_complete` / `research_error`

