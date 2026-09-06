# TARK AI — Luxury Intelligence Workspace

TARK AI is an AI-powered intelligence and research workspace built with FastAPI, PostgreSQL + pgvector, React, and Vite.

---

## Key Capabilities

- **Intelligent Chat & Provider Routing**: Streaming SSE generation via Groq, Mistral, and Gemini with automatic fallback and retry logic.
- **Enterprise Authentication**: Secure JWT access & refresh tokens, email verification, password reset, and profile management via Resend.
- **Document Knowledge & OCR**: Automated multi-format document parser (PDF, DOCX, PPTX, XLSX, Images with RapidOCR) and B2 private object storage.
- **Hybrid RAG & Corrective RAG (CRAG)**: Multi-stage vector + lexical search, BGE-M3 embeddings, BGE reranking, dynamic document grading, and query rewriting.
- **Contextual Long-Term Memory**: Automatic semantic memory extraction, user preference retrieval, and conversation synthesis.
- **Multi-Source Tool Calling**: Integrated web search, financial data, weather, currency conversion, crypto rates, and knowledge base search.
- **Deep Research Engine**: Multi-step parallel research orchestration, evidence collection, source verification, and synthesized reporting.
- **Projects & File Workspaces**: Thread organization, custom project instructions, and scoped file retrieval.
- **Interactive Companion Robot Mascot**: Custom SVG/CSS & Framer Motion interactive character with 2D cursor tracking and privacy gestures.

---

## Quick Start (Local Development)

### 1. Prerequisites
- Node.js 18+ & npm
- Python 3.12+
- Docker & Docker Compose (for PostgreSQL 16 + pgvector)

### 2. Environment Setup
```bash
# Backend environment
cp backend/.env.example backend/.env

# Frontend environment
cp frontend/.env.example frontend/.env
```

### 3. Start PostgreSQL + pgvector
```bash
docker compose up -d
```

### 4. Setup & Run Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # On Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8001
```

### 5. Setup & Run Frontend
```bash
cd frontend
npm install
npm run dev
```

Visit `http://localhost:5173` in your browser.

---

## Production Deployment

For complete, step-by-step production deployment instructions on **Render** (Backend + Database) and **Vercel** (Frontend), see [DEPLOYMENT.md](DEPLOYMENT.md).

### Quick Deployment Summary:

1. **Backend (Render Web Service)**:
   - Root directory: `backend`
   - Build Command: `pip install -r requirements.txt && alembic upgrade head`
   - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Health check: `/health`

2. **Frontend (Vercel)**:
   - Root directory: `frontend`
   - Framework preset: `Vite`
   - Build Command: `npm run build`
   - Output Directory: `dist`
   - Environment Variable: `VITE_API_BASE_URL=https://your-backend.onrender.com`

---

## Testing & Validation

### Backend Test Suite (247 tests)
```bash
cd backend
pytest
```

### Frontend Build
```bash
cd frontend
npm run build
```

---

## License

Private and proprietary. All rights reserved.
