from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.coding import router as coding_router
from app.api.v1.documents import router as documents_router
from app.api.v1.embeddings import router as embeddings_router
from app.api.v1.files import router as files_router
from app.api.v1.memory import router as memory_router
from app.api.v1.projects import router as projects_router
from app.api.v1.rag import router as rag_router
from app.api.v1.research import router as research_router
from app.api.v1.retrieval import router as retrieval_router
from app.api.v1.settings import router as settings_router
from app.api.v1.threads import router as threads_router
from app.api.v1.tools import router as tools_router
from app.api.v1.voice import router as voice_router
from app.api.v1.integrations import router as integrations_router
from app.api.v1.tasks import router as tasks_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(projects_router)
api_router.include_router(threads_router)
api_router.include_router(files_router)
api_router.include_router(documents_router)
api_router.include_router(embeddings_router)
api_router.include_router(retrieval_router)
api_router.include_router(rag_router)
api_router.include_router(memory_router)
api_router.include_router(tools_router)
api_router.include_router(research_router)
api_router.include_router(coding_router)
api_router.include_router(settings_router)
api_router.include_router(voice_router)
api_router.include_router(integrations_router)
api_router.include_router(tasks_router)





