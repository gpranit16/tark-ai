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

- **Main Intelligence Workspace**: Low-latency SSE chat streaming powered by Groq LPUs, multimodal vision, prompt cards, and live tool execution.
- **Interactive Companion Mascot**: Real-time 2D cursor tracking companion with automatic password privacy shielding.
- **Personal OS & "My Space"**: Daily intelligence pulse, AI Daily Plan generation, 2-way Google Calendar synchronization, and audio reminder alerts.
- **Smart Tasks & Habit Planning**: Conversational natural language task creation, category taxonomies, priority scheduling, and background alert daemons.
- **Universal Knowledge Base**: Multi-format document extraction (PDF, Word DOCX, PowerPoint PPTX, Excel XLSX, Images via RapidOCR ONNX) with dual-tier storage (Local + Backblaze B2).
- **Corrective RAG (CRAG)**: Hybrid dense vector (`BAAI/bge-m3`) and lexical search with cross-encoder reranking (`bge-reranker-v2-m3`).
- **Contextual Long-Term Memory**: Automatic semantic extraction of facts, preferences, and project context with confidence weighting.

---

## 2. Application Showcase

### 🌟 1. Main Intelligence Workspace & Multi-Model Chat
> Low-latency SSE streaming workspace with intelligent prompt suggestion cards, model switching (`qwen3.8-27b`, `gpt-oss-120b`, `llama-3.3-70b`), private B2 cloud storage toggling, and 3D companion mascot integration.

![Main Intelligence Workspace](assets/screenshots/chat_workspace.png)

---

### 🤖 2. Authentication & Interactive Companion Mascot
> Secure JWT authentication featuring an interactive companion robot that tracks cursor movement in real time and automatically shields its eyes for password privacy.

![Sign In & Mascot](assets/screenshots/auth_login.png)

---

### 📅 3. Personal OS & "My Space"
> Central command dashboard featuring real-time Google Calendar synchronization, AI-generated daily schedules, upcoming reminder alerts, and productivity metrics.

![My Space Dashboard](assets/screenshots/myspace_dashboard.png)

---

### 📋 4. Tasks & Smart Planning
> Conversational task creation with category tags (*Finance, Health, Personal, Projects, Study, Work*), priority management, and smart filter views (*Today, Upcoming, Overdue, Completed, AI Daily Plan*).

![Tasks and Smart Planning](assets/screenshots/tasks_planning.png)

---

### 📚 5. Universal Knowledge Base
> Ingest and search documents across formats (PDF, DOCX, PPTX, XLSX, Images via RapidOCR ONNX) backed by PostgreSQL `pgvector` and private Backblaze B2 cloud storage.

![Knowledge Base](assets/screenshots/knowledge_hub.png)

---

### 🧠 6. Personal Memory & Context Console
> Intelligent long-term semantic memory that extracts durable facts and preferences with confidence scoring, importance weights, and user controls.

![Personal Memory Console](assets/screenshots/memory_console.png)

---

## 3. Core Features

### 💬 Intelligence Workspace & Chat
- **Ultra-Fast Streaming**: Groq LPU acceleration delivering 150–250 tokens/second with under 150ms latency.
- **Multi-Model Routing**: Switch dynamically between Fast, Normal, Reasoning, RAG, and Deep Research modes.
- **Context & Citations**: Real-time RAG document citations, web search verification, and execution pills.

### 🤖 Interactive Companion Mascot
- **Real-Time 2D Gaze Tracking**: Interactive companion tracks cursor position across the screen.
- **Privacy Shielding**: Mascot automatically covers its eyes when the user types in password inputs.

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

    A["🖥️ Frontend Client<br/>(React 19 + Vite + Tailwind + Framer Motion)"]:::client
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
| **Email Service** | Resend API | Transactional account emails |

---

## 6. Local Setup Guide

### 1. Clone Repository
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
.\.venv\Scripts\Activate.ps1  # On Windows
# source .venv/bin/activate   # On macOS/Linux

# Install dependencies & run migrations
pip install -r requirements.txt
alembic upgrade head

# Start FastAPI server
uvicorn app.main:app --reload --port 8001
```

### 4. Setup and Run Frontend
```bash
cd ../frontend
npm install
npm run dev
```

Open **`http://localhost:5173`** in your browser.

---

## 7. License

Distributed under the **MIT License**. See `LICENSE` for details.
