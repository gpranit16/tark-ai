# TARK AI — Luxury Autonomous Intelligence & Personal OS

[![React](https://img.shields.io/badge/react-%2320232a.svg?style=for-the-badge&logo=react&logoColor=%2361DAFB)](https://react.dev/)
[![Vite](https://img.shields.io/badge/vite-%23646CFF.svg?style=for-the-badge&logo=vite&logoColor=white)](https://vite.dev/)
[![TailwindCSS](https://img.shields.io/badge/tailwindcss-%2338B2AC.svg?style=for-the-badge&logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![pgvector](https://img.shields.io/badge/pgvector-0.5.0-336791?style=for-the-badge)](https://github.com/pgvector/pgvector)
[![Groq](https://img.shields.io/badge/Groq-LPU%20Inference-F05A28?style=for-the-badge)](https://groq.com/)
[![Google Calendar](https://img.shields.io/badge/Google_Calendar-2--Way_Sync-4285F4?style=for-the-badge&logo=googlecalendar&logoColor=white)](https://workspace.google.com/products/calendar/)
[![Backblaze B2](https://img.shields.io/badge/Backblaze_B2-Private_Storage-E02020?style=for-the-badge&logo=backblaze&logoColor=white)](https://www.backblaze.com/b2/)

---

## 1. Overview

**TARK AI** is an enterprise-grade AI intelligence platform and autonomous personal operating system (Personal OS). Engineered with an obsidian and champagne gold aesthetic, TARK AI unifies:

- **Personal OS & Daily Hub**: Real-time daily briefing, AI Daily Plan generation, 2-way Google Calendar synchronization, and audio reminder alerts.
- **Smart Tasks & Habit Planning**: Conversational natural language task creation, category filtering, priority scheduling, and background alert daemons.
- **Universal Knowledge Base**: Multi-format document ingestion (PDF, Word DOCX, PowerPoint PPTX, Excel XLSX, Scanned Images via RapidOCR ONNX) with dual-tier storage (Local + Backblaze B2).
- **Corrective RAG (CRAG)**: Hybrid dense vector (`BAAI/bge-m3`) and lexical search with cross-encoder reranking (`bge-reranker-v2-m3`).
- **Contextual Long-Term Memory**: Automatic semantic extraction of facts, preferences, and project context with confidence weighting.
- **High-Speed Inference**: Sub-150ms SSE streaming powered by Groq LPUs, NVIDIA Vision, Gemini, and Mistral.

---

## 2. Application Showcase

### 🌟 1. Personal OS & "My Space"
> Central command dashboard featuring real-time calendar synchronization, AI-generated daily schedules, upcoming reminder alerts, and productivity metrics.

![My Space Dashboard](assets/screenshots/myspace_dashboard.png)

---

### 📋 2. Tasks & Smart Planning
> Conversational task creation with category tags (*Finance, Health, Personal, Projects, Study, Work*), priority management, and smart filter views (*Today, Upcoming, Overdue, Completed, AI Daily Plan*).

![Tasks and Smart Planning](assets/screenshots/tasks_planning.png)

---

### 📚 3. Universal Knowledge Base
> Ingest and search documents across formats (PDF, DOCX, PPTX, XLSX, Images via RapidOCR ONNX) backed by PostgreSQL `pgvector` and private Backblaze B2 cloud storage.

![Knowledge Base](assets/screenshots/knowledge_hub.png)

---

### 🧠 4. Personal Memory & Context Console
> Intelligent long-term semantic memory that extracts durable facts and preferences with confidence scoring, importance weights, and user controls.

![Personal Memory Console](assets/screenshots/memory_console.png)

---

## 3. Core Features

### 🌟 Personal OS ("My Space")
- **AI Daily Plan**: Optimizes daily routines, meetings, and prioritized tasks into an actionable hourly schedule.
- **Google Calendar Sync**: Full OAuth2 integration to fetch live events, detect schedule conflicts, and add events.
- **Harmonic Audio Alerts**: Multi-harmonic sound notifications when task deadlines or reminders arrive.
- **Intelligence Pulse**: Real-time summary of today's tasks, overdue deadlines, and synchronized calendar events.

### 📋 Smart Tasks & Scheduling
- **Natural Language Input**: Quickly create tasks from conversational prompts (e.g., *"Revise DBMS queries for 45 mins at 6 PM"*).
- **Taxonomy Categories**: Organize by Finance, Health, Personal, Projects, Study, and Work.
- **Smart Views**: Instant filtering by Today, Upcoming, Overdue, Completed, All Tasks, Reminders, and Daily Plan.
- **Background Worker**: Asynchronous daemon evaluating pending deadlines and dispatching notifications.

### 📚 Knowledge Ingestion & RapidOCR
- **Multi-Format Extraction**: Parses PDFs, DOCX, PPTX, XLSX, Markdown, and plain text.
- **On-Device OCR**: Extracts text from scanned receipts, invoices, and images via RapidOCR ONNX.
- **Hybrid Storage**: Local disk storage or private Backblaze B2 S3 storage with signed token streaming.
- **Storage Breakdown**: Real-time telemetry tracking document counts, total size, and ingestion status.

### 🎯 Corrective RAG (CRAG) & Vector Search
- **Dense Vector Search**: 1024-dimensional dense embeddings (`BAAI/bge-m3`) indexed in PostgreSQL with `pgvector`.
- **Lexical Keyword Search**: Sparse matching combined with dense vectors for hybrid retrieval.
- **Cross-Encoder Reranking**: Re-scores top candidate passages using `bge-reranker-v2-m3` to ensure relevance.
- **Document Grading**: Evaluates context quality and dynamically triggers external web search fallback when required.

### 🧠 Semantic Long-Term Memory
- **Automatic Fact Extraction**: Identifies durable preferences and user facts from conversation threads.
- **Confidence Scoring**: Assigns confidence percentages and importance weights to every entity.
- **Scoped Injection**: Injects relevant memories into active prompts without cross-workspace leakage.
- **User Controls**: Edit, disable, search, or delete stored memories directly from the console.

### ⚡ Multi-Model Intelligence & Tools
- **Groq LPU Inference**: High-throughput streaming (`qwen-2.5-72b`, `gpt-oss-120b`, `llama-3.3-70b`).
- **NVIDIA NIM Vision**: Multimodal image inspection and document understanding.
- **Autonomous Tools**: DuckDuckGo / Tavily Web Search, Yahoo Finance stock quotes, OpenMeteo weather forecasts, and currency conversion.
- **LangSmith Tracing**: Full execution observability for token metrics, tool calls, and RAG evaluation.

---

## 4. System Architecture

```mermaid
graph TD
    classDef client fill:#0B0B0C,stroke:#C9A86A,stroke-width:2px,color:#F2F0EB;
    classDef gateway fill:#141416,stroke:#8E7241,stroke-width:2px,color:#F2F0EB;
    classDef router fill:#1E170A,stroke:#E5C378,stroke-width:2px,color:#FFF;
    classDef data fill:#0A1918,stroke:#2DD4BF,stroke-width:2px,color:#2DD4BF;
    classDef cloud fill:#1A0F1F,stroke:#A855F7,stroke-width:2px,color:#E9D5FF;
    classDef ext fill:#1B0E0E,stroke:#F43F5E,stroke-width:2px,color:#FDA4AF;

    A["🖥️ Frontend Client<br/>(React 19 + Vite + Tailwind)"]:::client
    B["⚙️ API Gateway & Auth<br/>(FastAPI + JWT Auth)"]:::gateway
    C["🧠 Neural Router & Providers<br/>(Groq, NVIDIA Vision, Gemini, Mistral)"]:::router
    D["🎯 CRAG & Retrieval Engine<br/>(BGE-M3 Embeddings + BGE Reranker v2)"]:::router
    E["🗄️ PostgreSQL 16 + pgvector<br/>(Users, Tasks, Threads, Memory, Chunks)"]:::data
    F["📦 Object Storage<br/>(Local Disk / Backblaze B2)"]:::cloud
    G["🤖 Autonomous Tools & Connectors<br/>(Google Calendar, Tavily, Yahoo Finance)"]:::ext
    H["⏰ Background Reminder Daemon<br/>(Async Deadline Worker)"]:::gateway

    A <-->|REST APIs & SSE Streams| B
    B --> C
    B <-->|Hybrid Search & Scoring| D
    D <-->|Vector Cosine & BM25| E
    B <-->|Persistence & ORM| E
    B <-->|File Upload & OCR Streaming| F
    B <-->|OAuth2 Sync & Live Data| G
    H <-->|Evaluate Pending Reminders| E
    H -.->|Push Notifications| A
```

---

## 5. Technical Stack

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **Frontend** | React 19, Vite, Tailwind CSS, Framer Motion | Modern client UI with obsidian luxury styling |
| **State Management** | Zustand, TanStack React Query v5 | Client state and server data caching |
| **Backend** | FastAPI, Python 3.12, Uvicorn | High-performance asynchronous REST and SSE backend |
| **Database** | PostgreSQL 16 with `pgvector` | Relational storage and 1024-dim dense vector search |
| **ORM & Migrations** | SQLAlchemy 2.0 (Async), Alembic | Declarative schema and versioned migrations |
| **LLM Inference** | Groq LPU API | Ultra-low latency token generation (150+ tokens/sec) |
| **Multimodal Vision** | NVIDIA NIM API (`llama-3.2-11b-vision-instruct`) | Visual document and image analysis |
| **Embeddings & Rerank** | BAAI/bge-m3, BAAI/bge-reranker-v2-m3 | Hybrid embedding and cross-encoder reranking |
| **OCR Ingestion** | RapidOCR ONNX | Scanned image and document text parsing |
| **Cloud Storage** | Backblaze B2 (S3-compatible) | Secure, private object storage |
| **Calendar Sync** | Google Calendar API (OAuth2) | Two-way agenda synchronization |
| **Observability** | LangSmith (`LANGCHAIN_TRACING_V2`) | End-to-end LLM and agent execution tracing |
| **Email Service** | Resend API | Transactional account emails |

---

## 6. Local Setup Guide

### 1. Clone the Repository
```bash
git clone https://github.com/gpranit16/tark-ai.git
cd tark-ai
```

### 2. Start PostgreSQL with pgvector
```bash
docker compose up -d
```

### 3. Setup and Run Backend
```bash
cd backend

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start FastAPI server
uvicorn app.main:app --reload --port 8001
```

### 4. Setup and Run Frontend
```bash
cd ../frontend

# Install dependencies
npm install

# Start Vite dev server
npm run dev
```

Open **`http://localhost:5173`** in your browser.

---

## 7. Environment Configuration

### Backend (`backend/.env`)
```env
APP_ENV=development
DATABASE_URL=postgresql+asyncpg://tarkai:change-me@127.0.0.1:5433/tarkai
JWT_SECRET_KEY=your-secure-64-character-jwt-secret-key-here
FRONTEND_URL=http://localhost:5173
CORS_ORIGINS=http://localhost:5173

# LLM Providers
DEFAULT_PROVIDER=groq
GROQ_API_KEY=your_groq_api_key
GEMINI_API_KEY=your_gemini_api_key
MISTRAL_API_KEY=your_mistral_api_key

# NVIDIA Vision
NVIDIA_API_KEY=your_nvidia_api_key
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_MODEL=meta/llama-3.2-11b-vision-instruct

# Search & Tools
TAVILY_API_KEY=your_tavily_key

# Google Calendar Integration
GOOGLE_CLIENT_ID=your_google_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8001/api/v1/integrations/google/calendar/callback

# LangSmith Observability
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_key
LANGCHAIN_PROJECT=tark-ai

# Storage (local or b2)
STORAGE_PROVIDER=b2
B2_KEY_ID=your_b2_key_id
B2_APPLICATION_KEY=your_b2_app_key
B2_BUCKET_NAME=tarkai-files
B2_ENDPOINT=https://s3.us-east-005.backblazeb2.com

# Email (Resend)
RESEND_API_KEY=your_resend_api_key
RESEND_FROM_EMAIL=onboarding@resend.dev
```

### Frontend (`frontend/.env`)
```env
VITE_API_BASE_URL=http://127.0.0.1:8001
```

---

## 8. API Reference Summary

| Group | Method | Endpoint | Description |
| :--- | :--- | :--- | :--- |
| **Auth** | `POST` | `/api/v1/auth/signup` | Register new user |
| **Auth** | `POST` | `/api/v1/auth/login` | Authenticate and return JWT tokens |
| **Tasks** | `GET` | `/api/v1/tasks` | List tasks by category, status, and date |
| **Tasks** | `POST` | `/api/v1/tasks` | Create task with priority and reminder |
| **Tasks** | `GET` | `/api/v1/tasks/summary` | Get aggregated task counts and metrics |
| **Tasks** | `POST` | `/api/v1/tasks/daily-plan` | Generate AI daily plan from tasks & calendar |
| **Calendar** | `GET` | `/api/v1/integrations/google/calendar/auth-url` | Get Google OAuth2 authorization URL |
| **Calendar** | `GET` | `/api/v1/integrations/google/calendar/events` | Fetch live Google Calendar events |
| **Chat** | `POST` | `/api/v1/threads/{id}/chat` | SSE streaming chat with tool execution |
| **Knowledge**| `POST` | `/api/v1/files/upload` | Upload & OCR process document |
| **Knowledge**| `GET` | `/api/v1/files/stats` | Storage breakdown (Local vs B2, total size) |
| **Memory** | `GET` | `/api/v1/memory` | Retrieve extracted semantic memory entities |
| **Tools** | `POST` | `/api/v1/tools/execute` | Execute tool with JSON parameters |

---

## 9. License

Distributed under the **MIT License**. See `LICENSE` for details.
