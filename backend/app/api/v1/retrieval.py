from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.retrieval import (
    ContextBuildRequest,
    ContextBuildResponse,
    RetrievalQueryRequest,
    RetrievalResponse,
)
from app.services.retrieval.context_builder import ContextBuilder
from app.services.retrieval.hybrid import HybridRetriever
from app.services.retrieval.keyword import KeywordRetriever
from app.services.retrieval.vector import VectorRetriever

router = APIRouter(prefix="/retrieval", tags=["retrieval"])

vector_retriever = VectorRetriever()
keyword_retriever = KeywordRetriever()
hybrid_retriever = HybridRetriever(
    vector_retriever=vector_retriever,
    keyword_retriever=keyword_retriever
)
context_builder = ContextBuilder()


@router.post("/vector", response_model=RetrievalResponse)
async def vector_search(
    req: RetrievalQueryRequest,
    session: AsyncSession = Depends(get_db_session)
) -> RetrievalResponse:
    results = await vector_retriever.search(
        session=session,
        query=req.query,
        user_id=req.user_id,
        project_id=req.project_id,
        file_ids=req.file_ids,
        top_k=req.top_k,
    )
    return RetrievalResponse(
        query=req.query,
        results=results,
        retrieval_type="vector",
        count=len(results),
    )


@router.post("/keyword", response_model=RetrievalResponse)
async def keyword_search(
    req: RetrievalQueryRequest,
    session: AsyncSession = Depends(get_db_session)
) -> RetrievalResponse:
    results = await keyword_retriever.search(
        session=session,
        query=req.query,
        user_id=req.user_id,
        project_id=req.project_id,
        file_ids=req.file_ids,
        top_k=req.top_k,
    )
    return RetrievalResponse(
        query=req.query,
        results=results,
        retrieval_type="keyword",
        count=len(results),
    )


@router.post("/hybrid", response_model=RetrievalResponse)
async def hybrid_search(
    req: RetrievalQueryRequest,
    session: AsyncSession = Depends(get_db_session)
) -> RetrievalResponse:
    results = await hybrid_retriever.search(
        session=session,
        query=req.query,
        user_id=req.user_id,
        project_id=req.project_id,
        file_ids=req.file_ids,
        top_k=req.top_k,
    )
    return RetrievalResponse(
        query=req.query,
        results=results,
        retrieval_type="hybrid",
        count=len(results),
    )


@router.post("/context", response_model=ContextBuildResponse)
async def build_context(
    req: ContextBuildRequest,
    session: AsyncSession = Depends(get_db_session)
) -> ContextBuildResponse:
    if req.retrieval_type == "vector":
        results = await vector_retriever.search(
            session=session,
            query=req.query,
            user_id=req.user_id,
            project_id=req.project_id,
            file_ids=req.file_ids,
            top_k=req.top_k,
        )
    elif req.retrieval_type == "keyword":
        results = await keyword_retriever.search(
            session=session,
            query=req.query,
            user_id=req.user_id,
            project_id=req.project_id,
            file_ids=req.file_ids,
            top_k=req.top_k,
        )
    else:
        results = await hybrid_retriever.search(
            session=session,
            query=req.query,
            user_id=req.user_id,
            project_id=req.project_id,
            file_ids=req.file_ids,
            top_k=req.top_k,
        )

    return context_builder.build_context(
        query=req.query,
        chunks=results,
        max_tokens=req.max_tokens,
    )
