import asyncio
import os
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from app.models.chunk import DocumentChunk
from app.models.conversation import User
from app.models.file import File
from app.services.embeddings.factory import get_embedding_provider
from app.services.rag.crag import CRAGOrchestrator
from app.services.retrieval.hybrid import clear_retrieval_cache


async def _create_test_file(
    session: AsyncSession,
    user: User,
    filename: str,
    content: str,
) -> tuple[File, DocumentChunk]:
    fid = uuid4()
    db_file = File(
        id=fid,
        user_id=user.id,
        original_filename=filename,
        mime_type="application/pdf" if filename.endswith(".pdf") else "image/png",
        extension=os.path.splitext(filename)[1],
        size_bytes=len(content),
        storage_provider="local",
        storage_key=f"users/{user.id}/{filename}",
        status="active",
    )
    session.add(db_file)
    await session.flush()

    provider = get_embedding_provider()
    vec = await provider.embed_query(content)

    chunk = DocumentChunk(
        file_id=fid,
        user_id=user.id,
        chunk_index=0,
        content=content,
        page_number=1,
        embedding=vec,
        metadata_={"filename": filename},
    )
    session.add(chunk)
    await session.commit()
    await session.refresh(db_file)
    await session.refresh(chunk)
    return db_file, chunk


@pytest.mark.asyncio
async def test_all_six_regression_scenarios(db_session: AsyncSession, user: User):
    """Verify all 6 regression scenarios with Pan.pdf, screenshot.png, and RevaluationCourses.pdf in KB."""
    clear_retrieval_cache()

    # Seed 3 distinct files in User's Knowledge Base
    pan_content = (
        "INCOME TAX DEPARTMENT GOVT. OF INDIA. Permanent Account Number: ABCDE1234F. "
        "Name: Rahul Sharma. Father's Name: Suresh Sharma. Date of Birth: 12/07/2006."
    )
    screenshot_content = (
        "Screenshot of France Government Portal: President of France is Emmanuel Macron. Prime Minister is Michel Barnier."
    )
    reval_content = (
        "BMSIT Revaluation Courses Notification: Course Code 21CS51 Math, 21CS52 Data Structures. Bank Account for fee payment: 987654321000."
    )

    pan_file, pan_chunk = await _create_test_file(db_session, user, "Pan.pdf", pan_content)
    shot_file, shot_chunk = await _create_test_file(db_session, user, "screenshot.png", screenshot_content)
    reval_file, reval_chunk = await _create_test_file(db_session, user, "RevaluationCourses.pdf", reval_content)

    orchestrator = CRAGOrchestrator()

    # ──────────────────────────────────────────────────────────────────────────
    # Scenario 1: "According to Pan.pdf, who is the President of France?"
    # Must NOT answer from screenshot.png. Must NOT mention Emmanuel Macron.
    # Must be grounded strictly in Pan.pdf evidence.
    # ──────────────────────────────────────────────────────────────────────────
    res1 = await orchestrator.run(
        query="According to Pan.pdf, who is the President of France?",
        user_id=user.id,
        session=db_session,
    )
    assert "Pan.pdf" in res1.answer or all(c.filename == "Pan.pdf" for c in res1.citations)
    assert "Emmanuel Macron" not in res1.answer
    assert "Michel Barnier" not in res1.answer
    assert "screenshot" not in str(res1.citations).lower()
    assert "revaluation" not in str(res1.citations).lower()

    # ──────────────────────────────────────────────────────────────────────────
    # Scenario 2: "Tell me the most important information contained in Pan.pdf."
    # Must retrieve Pan.pdf only and cite Pan.pdf.
    # ──────────────────────────────────────────────────────────────────────────
    res2 = await orchestrator.run(
        query="Tell me the most important information contained in Pan.pdf.",
        user_id=user.id,
        session=db_session,
    )
    assert res2.decision == "grounded"
    assert "ABCDE1234F" in res2.answer or "Rahul Sharma" in res2.answer
    assert all(c.filename == "Pan.pdf" for c in res2.citations)
    assert "screenshot" not in str(res2.citations).lower()
    assert "revaluation" not in str(res2.citations).lower()

    # ──────────────────────────────────────────────────────────────────────────
    # Scenario 3: "What is the person's bank account number mentioned in Pan.pdf?"
    # Must NOT fetch bank account from RevaluationCourses.pdf (987654321000).
    # ──────────────────────────────────────────────────────────────────────────
    res3 = await orchestrator.run(
        query="What is the person's bank account number mentioned in Pan.pdf?",
        user_id=user.id,
        session=db_session,
    )
    assert "987654321000" not in res3.answer
    assert "revaluation" not in str(res3.citations).lower()
    assert "screenshot" not in str(res3.citations).lower()

    # ──────────────────────────────────────────────────────────────────────────
    # Scenario 4: Current attachment = Pan.pdf, Query = "What is the date of birth in this document?"
    # Must resolve "this document" -> Pan.pdf and answer 12/07/2006.
    # ──────────────────────────────────────────────────────────────────────────
    res4 = await orchestrator.run(
        query="What is the date of birth in this document?",
        user_id=user.id,
        session=db_session,
        file_ids=[pan_file.id],
    )
    assert res4.decision == "grounded"
    assert "12/07/2006" in res4.answer or "2006" in res4.answer
    assert len(res4.citations) >= 1
    assert all(c.filename == "Pan.pdf" for c in res4.citations)

    # ──────────────────────────────────────────────────────────────────────────
    # Scenario 5: Current attachment = Pan.pdf, Query = "Summarize this document."
    # Must summarize only Pan.pdf without mentioning screenshot or revaluation.
    # ──────────────────────────────────────────────────────────────────────────
    res5 = await orchestrator.run(
        query="Summarize this document.",
        user_id=user.id,
        session=db_session,
        file_ids=[pan_file.id],
    )
    assert res5.decision == "grounded"
    assert all(c.filename == "Pan.pdf" for c in res5.citations)
    assert "screenshot" not in str(res5.citations).lower()
    assert "revaluation" not in str(res5.citations).lower()

    # ──────────────────────────────────────────────────────────────────────────
    # Scenario 6: No attachment, Query = "What is the PAN number in Pan.pdf?"
    # Must resolve Pan.pdf by name -> return ABCDE1234F.
    # ──────────────────────────────────────────────────────────────────────────
    res6 = await orchestrator.run(
        query="What is the PAN number in Pan.pdf?",
        user_id=user.id,
        session=db_session,
        file_ids=None,
    )
    assert res6.decision == "grounded"
    assert "ABCDE1234F" in res6.answer
    assert len(res6.citations) >= 1
    assert all(c.filename == "Pan.pdf" for c in res6.citations)
