import uuid
import pytest
from uuid import UUID, uuid4
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Message, Thread, User
from app.models.file import File
from app.services.rag.scope_resolver import FileScopeResolver


@pytest.mark.asyncio
async def test_scope_resolver_explicit_attachments(db_session: AsyncSession, user: User):
    resolver = FileScopeResolver()

    # Create file for user
    f1 = File(
        id=uuid.uuid4(),
        user_id=user.id,
        original_filename="Pan.pdf",
        storage_key=f"{user.id}/pan.pdf",
        storage_provider="local",
        mime_type="application/pdf",
        extension=".pdf",
        size_bytes=1024,
    )
    db_session.add(f1)
    await db_session.commit()

    # 1. Explicit attachment provided
    scope = await resolver.resolve_scope(
        session=db_session,
        user_id=user.id,
        query="What is the date of birth?",
        explicit_file_ids=[f1.id],
    )

    assert scope.is_document_scoped is True
    assert scope.source == "explicit_attachments"
    assert scope.file_ids == [f1.id]
    assert scope.filenames == ["Pan.pdf"]


@pytest.mark.asyncio
async def test_scope_resolver_explicit_filename_in_query(db_session: AsyncSession, user: User):
    resolver = FileScopeResolver()

    f1 = File(
        id=uuid.uuid4(),
        user_id=user.id,
        original_filename="Pan.pdf",
        storage_key=f"{user.id}/pan.pdf",
        storage_provider="local",
        mime_type="application/pdf",
        extension=".pdf",
        size_bytes=1024,
    )
    f2 = File(
        id=uuid.uuid4(),
        user_id=user.id,
        original_filename="BMSIT_Syllabus.pdf",
        storage_key=f"{user.id}/syllabus.pdf",
        storage_provider="local",
        mime_type="application/pdf",
        extension=".pdf",
        size_bytes=2048,
    )
    db_session.add_all([f1, f2])
    await db_session.commit()

    # Query explicitly mentions Pan.pdf
    scope1 = await resolver.resolve_scope(
        session=db_session,
        user_id=user.id,
        query="According to Pan.pdf, who is the President of France?",
    )
    assert scope1.is_document_scoped is True
    assert scope1.source == "explicit_filename"
    assert scope1.file_ids == [f1.id]
    assert scope1.filenames == ["Pan.pdf"]

    # Query mentions BMSIT_Syllabus
    scope2 = await resolver.resolve_scope(
        session=db_session,
        user_id=user.id,
        query="What are the course credits from bmsit_syllabus.pdf?",
    )
    assert scope2.is_document_scoped is True
    assert scope2.source == "explicit_filename"
    assert scope2.file_ids == [f2.id]
    assert scope2.filenames == ["BMSIT_Syllabus.pdf"]


@pytest.mark.asyncio
async def test_scope_resolver_deictic_reference_from_thread(db_session: AsyncSession, user: User):
    resolver = FileScopeResolver()

    f1 = File(
        id=uuid.uuid4(),
        user_id=user.id,
        original_filename="Pan.pdf",
        storage_key=f"{user.id}/pan.pdf",
        storage_provider="local",
        mime_type="application/pdf",
        extension=".pdf",
        size_bytes=1024,
    )
    thread = Thread(
        id=uuid.uuid4(),
        user_id=user.id,
        title="Test Doc Chat",
    )
    db_session.add_all([f1, thread])
    await db_session.commit()

    msg = Message(
        id=uuid.uuid4(),
        thread_id=thread.id,
        role="user",
        content="Here is my document",
        attachments=[{"file_id": str(f1.id), "filename": "Pan.pdf"}],
    )
    db_session.add(msg)
    await db_session.commit()

    # User in follow-up turn says "What is the date of birth in this document?"
    scope = await resolver.resolve_scope(
        session=db_session,
        user_id=user.id,
        query="What is the date of birth in this document?",
        thread_id=thread.id,
    )

    assert scope.is_document_scoped is True
    assert scope.source == "thread_history"
    assert scope.file_ids == [f1.id]
    assert scope.filenames == ["Pan.pdf"]


@pytest.mark.asyncio
async def test_scope_resolver_user_isolation(db_session: AsyncSession, user: User):
    resolver = FileScopeResolver()
    user_b = User(id=uuid4())
    db_session.add(user_b)
    await db_session.commit()

    # File owned by User B
    file_b = File(
        id=uuid.uuid4(),
        user_id=user_b.id,
        original_filename="Secret_UserB.pdf",
        storage_key=f"{user_b.id}/secret.pdf",
        storage_provider="local",
        mime_type="application/pdf",
        extension=".pdf",
        size_bytes=1024,
    )
    db_session.add(file_b)
    await db_session.commit()

    # User (A) tries to explicitly request User B's file_id
    scope_attack1 = await resolver.resolve_scope(
        session=db_session,
        user_id=user.id,
        query="Read file",
        explicit_file_ids=[file_b.id],
    )
    assert scope_attack1.file_ids == []  # Denied

    # User (A) mentions User B's filename
    scope_attack2 = await resolver.resolve_scope(
        session=db_session,
        user_id=user.id,
        query="According to Secret_UserB.pdf, tell me secrets",
    )
    assert scope_attack2.is_document_scoped is False
    assert scope_attack2.file_ids is None
