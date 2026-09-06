"""Real RAG request test script to verify CRAG pipeline and token budget."""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from uuid import uuid4
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.models.chunk import DocumentChunk
from app.models.conversation import User
from app.models.file import File
from app.services.embeddings.factory import get_embedding_provider
from app.services.rag.crag import CRAGOrchestrator


async def main():
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
        pan_content = "Government of India Income Tax Department. Permanent Account Number (PAN): ABCDE1234F. Name: John Doe. Date of Birth: 01/01/1990."
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

        print("=== Running Consecutive RAG Benchmark for Pan.pdf ===")
        orchestrator = CRAGOrchestrator()
        query = "What is the PAN number in Pan.pdf?"

        for i in range(1, 4):
            print(f"\n--- [Request #{i}] Query: '{query}' ---")
            result = await orchestrator.run(
                query=query,
                user_id=user_id,
                session=session,
                file_ids=[pan_file_id],
            )
            print(f"Decision: {result.decision}")
            print(f"Answer: {result.answer}")
            print(f"Citations: {[c.reference for c in result.citations]}")
            print(f"Reranker Used: {result.reranker_used}")
            print(f"Latency: {result.latency}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
