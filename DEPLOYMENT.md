# TARK AI — Production Deployment Guide

This guide walks through deploying TARK AI to production using **Render** (FastAPI Backend + PostgreSQL Database) and **Vercel** (React/Vite Frontend), along with **Backblaze B2** (Private Object Storage) and **Resend** (Transactional Email).

---

## Architecture Overview

```
 ┌────────────────────────┐         HTTPS / SSE          ┌───────────────────────────┐
 │     Vercel Frontend    │ ───────────────────────────> │    Render Web Service     │
 │ (React + Vite + SPA)   │ <─────────────────────────── │     (FastAPI Backend)     │
 └────────────────────────┘                              └─────────────┬─────────────┘
                                                                       │
                         ┌───────────────────────┬─────────────────────┼────────────────────┐
                         ▼                       ▼                     ▼                    ▼
               ┌──────────────────┐    ┌──────────────────┐   ┌────────────────┐   ┌────────────────┐
               │ Render PostgreSQL│    │   Backblaze B2   │   │   Groq / AI    │   │  Resend Email  │
               │   (+ pgvector)   │    │ (Private Storage)│   │ (LLM & Tools)  │   │  (Auth Links)  │
               └──────────────────┘    └──────────────────┘   └────────────────┘   └────────────────┘
```

---

## 1. Database Setup (Render / Supabase / Neon)

1. Create a **PostgreSQL 16** database with `pgvector` enabled on Render, Neon, or Supabase.
2. Note your connection string (`DATABASE_URL`).
   - Example: `postgresql://user:password@dpg-xxxx.oregon-postgres.render.com/tarkai`
   - *Note: TARK AI automatically normalizes connection strings to `postgresql+asyncpg://` for the FastAPI backend and `postgresql+psycopg://` for Alembic migrations.*

---

## 2. Backend Deployment (Render Web Service)

### A. Web Service Configuration
- **Repository**: `https://github.com/gpranit16/tark-ai`
- **Root Directory**: `backend`
- **Runtime**: `Python 3`
- **Build Command**:
  ```bash
  pip install -r requirements.txt && alembic upgrade head
  ```
- **Start Command**:
  ```bash
  uvicorn app.main:app --host 0.0.0.0 --port $PORT
  ```
- **Health Check Path**: `/health`

### B. Render Environment Variables

| Variable Name | Value / Description |
| :--- | :--- |
| `APP_ENV` | `production` |
| `DATABASE_URL` | Your PostgreSQL connection string |
| `JWT_SECRET_KEY` | Strong random 64-char key (`openssl rand -hex 32`) |
| `JWT_ALGORITHM` | `HS256` |
| `FRONTEND_URL` | `https://your-frontend-app.vercel.app` |
| `CORS_ORIGINS` | `https://your-frontend-app.vercel.app` |
| `GROQ_API_KEY` | Your Groq API key (`gsk_...`) |
| `TAVILY_API_KEY` | Your Tavily Search API key (`tvly-...`) |
| `STORAGE_PROVIDER` | `b2` |
| `B2_ENDPOINT` | `https://s3.us-east-005.backblazeb2.com` (or your B2 region) |
| `B2_KEY_ID` | Your Backblaze Key ID |
| `B2_APPLICATION_KEY` | Your Backblaze Application Key |
| `B2_BUCKET_NAME` | `tarkai-storage` (private bucket) |
| `RESEND_API_KEY` | Your Resend API key (`re_...`) |
| `RESEND_FROM_EMAIL` | `onboarding@resend.dev` (or your verified domain) |
| `RESEND_FROM_NAME` | `TARK AI` |
| `DEEP_RESEARCH_ENABLED` | `true` |
| `MEMORY_ENABLED` | `true` |
| `TOOL_CALLING_ENABLED` | `true` |

---

## 3. Frontend Deployment (Vercel)

### A. Project Import & Configuration
- **Repository**: `https://github.com/gpranit16/tark-ai`
- **Root Directory**: `frontend`
- **Framework Preset**: `Vite`
- **Build Command**: `npm run build`
- **Output Directory**: `dist`
- **Install Command**: `npm install`

### B. Vercel Environment Variables

| Variable Name | Value |
| :--- | :--- |
| `VITE_API_BASE_URL` | `https://your-backend-service.onrender.com` |

*Note: `vercel.json` is included in the repository to provide automatic SPA routing (`/index.html` rewrites) for routes like `/login`, `/signup`, `/verify-email`, `/reset-password`, `/projects`, `/memory`, `/tools`, and `/knowledge`.*

---

## 4. Backblaze B2 (Private Storage Setup)

1. Create a **Private Bucket** in Backblaze B2 named e.g. `tarkai-storage`.
2. Generate an **Application Key** with `readFiles`, `writeFiles`, `deleteFiles`, and `listFiles` permissions scoped to that bucket.
3. Add `B2_KEY_ID`, `B2_APPLICATION_KEY`, and `B2_BUCKET_NAME` to your Render environment variables.
4. Uploaded files remain strictly private and are accessible only through authenticated backend streaming routes (`/api/v1/files/{file_id}/content`).

---

## 5. Resend (Email Verification & Password Reset)

1. Sign up on [Resend.com](https://resend.com) and create an API Key.
2. For testing/onboarding, use `onboarding@resend.dev`.
3. For custom production domains, add and verify your domain DNS records in Resend and update `RESEND_FROM_EMAIL` to e.g. `auth@yourdomain.com`.

---

## 6. Manual Database Migration (If Needed)

If running migrations manually from a CLI or one-off task runner:

```bash
cd backend
alembic upgrade head
```

To verify the current migration status:
```bash
alembic current
```

---

## 7. Production Verification Checklist

- [ ] **Health Check**: `GET https://your-backend-service.onrender.com/health` returns `{"status": "ok"}`
- [ ] **Auth Flow**: Register new user -> Check verification email -> Sign in -> JWT issued
- [ ] **SSE Streaming**: Start a conversation -> Verify token streaming with live text generation
- [ ] **File Pipeline**: Upload document/image -> Verify B2 upload -> Check OCR/text extraction & download
- [ ] **RAG / CRAG**: Ask questions against uploaded documents -> Verify citation generation & grounding
- [ ] **SPA Routing**: Refresh `/projects`, `/memory`, or `/settings` in browser -> Verify no 404s
