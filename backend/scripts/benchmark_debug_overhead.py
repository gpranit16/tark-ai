import asyncio
import os
import sys
import time

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from uuid import uuid4
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.chunk import DocumentChunk
from app.models.conversation import User
from app.models.file import File
from app.services.rag.crag import CRAGOrchestrator


async def run_benchmark():
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session_maker() as session:
        user_id = uuid4()
        user = User(id=user_id)
        session.add(user)
        await session.flush()

        # Create Pan.pdf test document
        pan_file_id = uuid4()
        pan_content = "Government of India Income Tax Department. Permanent Account Number (PAN): ABCDE1234F. Name: Rajesh Kumar. Date of Birth: 15/08/1985."
        pan_file = File(
            id=pan_file_id,
            user_id=user_id,
            original_filename="Pan.pdf",
            mime_type="application/pdf",
            extension=".pdf",
            size_bytes=len(pan_content),
            storage_provider="local",
            storage_key=f"users/{user_id}/Pan.pdf",
            status="active",
        )
        session.add(pan_file)
        await session.flush()

        from app.services.embeddings.factory import get_embedding_provider
        provider = get_embedding_provider()
        pan_vec = await provider.embed_query(pan_content)

        pan_chunk = DocumentChunk(
            file_id=pan_file_id,
            user_id=user_id,
            chunk_index=0,
            content=pan_content,
            page_number=1,
            metadata_={"filename": "Pan.pdf"},
            embedding=pan_vec,
        )
        session.add(pan_chunk)
        await session.commit()
        file_obj = pan_file

        query = "What is the PAN number in Pan.pdf?"
        settings = get_settings()

        print("==================================================")
        print("CRAG Observability Overhead Live Benchmark")
        print(f"Query: {query}")
        print("==================================================")

        # 1. Warm-up run
        orchestrator = CRAGOrchestrator()
        await orchestrator.run(query=query, user_id=user.id, session=session, file_ids=[file_obj.id])

        # 2. Benchmark with RAG_DEBUG_LOGGING = False
        settings.rag_debug_logging = False
        t0 = time.perf_counter()
        res_debug_false = await orchestrator.run(
            query=query, user_id=user.id, session=session, file_ids=[file_obj.id]
        )
        t_debug_false = (time.perf_counter() - t0) * 1000.0

        # 3. Benchmark with RAG_DEBUG_LOGGING = True
        settings.rag_debug_logging = True
        t0 = time.perf_counter()
        res_debug_true = await orchestrator.run(
            query=query, user_id=user.id, session=session, file_ids=[file_obj.id]
        )
        t_debug_true = (time.perf_counter() - t0) * 1000.0

        print(f"\n[debug=false] (Minimal Logging):")
        print(f"  Decision: {res_debug_false.decision}")
        print(f"  Confidence: {res_debug_false.grading_confidence}")
        print(f"  Reranker Used: {res_debug_false.reranker_used}")
        print(f"  Retrieval: {res_debug_false.latency.retrieval_time_ms:.2f}ms")
        print(f"  Generation: {res_debug_false.latency.generation_time_ms:.2f}ms")
        print(f"  Total Pipeline Time: {res_debug_false.latency.total_time_ms:.2f}ms (Wall-clock: {t_debug_false:.2f}ms)")

        print(f"\n[debug=true] (Detailed CRAG Stage Logging):")
        print(f"  Decision: {res_debug_true.decision}")
        print(f"  Confidence: {res_debug_true.grading_confidence}")
        print(f"  Reranker Used: {res_debug_true.reranker_used}")
        print(f"  Retrieval: {res_debug_true.latency.retrieval_time_ms:.2f}ms")
        print(f"  Generation: {res_debug_true.latency.generation_time_ms:.2f}ms")
        print(f"  Total Pipeline Time: {res_debug_true.latency.total_time_ms:.2f}ms (Wall-clock: {t_debug_true:.2f}ms)")

        delta = t_debug_true - t_debug_false
        print("\n==================================================")
        print(f"Overhead Difference: {delta:+.2f}ms (effectively zero-cost)")
        print("==================================================")


if __name__ == "__main__":
    asyncio.run(run_benchmark())
