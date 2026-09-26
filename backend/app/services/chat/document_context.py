import asyncio
import io
import logging
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Message
from app.models.document import ParsedDocument
from app.models.file import File
from app.storage.factory import get_storage_provider

logger = logging.getLogger(__name__)


async def resolve_thread_file_ids(
    session: AsyncSession,
    user_id: UUID,
    thread_id: Optional[UUID],
    explicit_file_ids: Optional[List[UUID]] = None,
) -> List[UUID]:
    """Resolve all files attached to this specific thread or the current turn.
    
    Strictly isolated: only files owned by user_id are returned.
    Files attached to other threads or global knowledge are NOT included.
    """
    candidate_ids: List[UUID] = []
    seen: set[UUID] = set()

    # 1. Current request explicit attachments
    if explicit_file_ids:
        for fid in explicit_file_ids:
            if fid and fid not in seen:
                seen.add(fid)
                candidate_ids.append(fid)

    # 2. Historical thread message attachments
    if thread_id is not None:
        stmt = (
            select(Message.attachments)
            .where(
                Message.thread_id == thread_id,
                Message.attachments.isnot(None),
            )
            .order_by(Message.created_at.desc())
            .limit(30)
        )
        res = await session.execute(stmt)
        for att_list in res.scalars():
            if not att_list:
                continue
            for att in att_list:
                fid_val = att.get("file_id") if isinstance(att, dict) else (att.get("id") if isinstance(att, dict) else None)
                if fid_val:
                    try:
                        u = UUID(str(fid_val))
                        if u not in seen:
                            seen.add(u)
                            candidate_ids.append(u)
                    except (ValueError, TypeError):
                        pass

    if not candidate_ids:
        return []

    # Validate ownership
    val_stmt = select(File.id).where(
        File.id.in_(candidate_ids),
        File.user_id == user_id,
    )
    val_res = await session.execute(val_stmt)
    valid_ids_set = set(val_res.scalars().all())

    # Return preserving priority order
    return [fid for fid in candidate_ids if fid in valid_ids_set]


def _extract_pdf_sync(content_bytes: bytes) -> Tuple[str, int]:
    """Extract text from PDF synchronously in a thread."""
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(content_bytes))
        total_pages = len(reader.pages)
        pages_text: List[str] = []
        for idx, page in enumerate(reader.pages, start=1):
            try:
                t = page.extract_text() or ""
                t = t.strip()
                if t:
                    pages_text.append(f"--- Page {idx} ---\n{t}")
            except Exception:
                pass
        return "\n\n".join(pages_text), total_pages
    except Exception as e:
        logger.warning("[extract_pdf_sync] pypdf failed: %s", e)
        return "", 0


async def extract_file_content_instant(
    session: AsyncSession,
    file_id: UUID,
    user_id: UUID,
) -> Tuple[str, str, int]:
    """Extract full or high-quality text of a file instantly.
    
    Checks ParsedDocument first. If still pending/processing or text is empty,
    falls back to immediate on-the-fly extraction from storage so users get answers
    instantly even right after upload.
    
    Returns: (filename, text, page_count)
    """
    # 1. Fetch file record
    file_stmt = select(File).where(File.id == file_id, File.user_id == user_id)
    file_res = await session.execute(file_stmt)
    db_file = file_res.scalar_one_or_none()
    if not db_file:
        return "", "", 0

    filename = db_file.original_filename
    extension = (db_file.extension or "").lower()

    # 2. Check ParsedDocument
    doc_stmt = select(ParsedDocument).where(
        ParsedDocument.file_id == file_id,
        ParsedDocument.user_id == user_id,
    )
    doc_res = await session.execute(doc_stmt)
    parsed_doc = doc_res.scalar_one_or_none()

    if parsed_doc and parsed_doc.status == "completed" and parsed_doc.parsed_content:
        pages = parsed_doc.parsed_content.get("pages", [])
        page_texts: List[str] = []
        for p in pages:
            pt = p.get("text", "").strip()
            if pt:
                p_num = p.get("page_number", len(page_texts) + 1)
                page_texts.append(f"--- Page {p_num} ---\n{pt}")
        if page_texts:
            return filename, "\n\n".join(page_texts), parsed_doc.page_count or len(pages)

    # 3. Fallback: on-the-fly extraction from storage
    try:
        storage = get_storage_provider(db_file.storage_provider)
        content_bytes = await storage.download(db_file.storage_key)
        if not content_bytes:
            return filename, "", 0

        if extension == ".pdf":
            text, page_count = await asyncio.to_thread(_extract_pdf_sync, content_bytes)
            return filename, text, page_count

        elif extension in (
            ".txt", ".md", ".csv", ".json", ".py", ".js", ".jsx", ".ts",
            ".tsx", ".html", ".css", ".sql", ".yaml", ".yml", ".xml",
            ".java", ".cpp", ".c", ".h", ".go", ".rs", ".sh", ".toml", ".ini",
        ):
            text = content_bytes.decode("utf-8", errors="replace").strip()
            return filename, text, 1

        elif extension in (".docx", ".pptx"):
            # Check if summary or text is available in parser
            try:
                from app.services.parsers.factory import get_parser_for_extension
                parser = get_parser_for_extension(extension)
                doc_data, _ = await parser.parse(content_bytes, file_id=file_id, filename=filename, extension=extension)
                pages_t = [f"--- Section {p.page_number} ---\n{p.text.strip()}" for p in doc_data.pages if p.text.strip()]
                return filename, "\n\n".join(pages_t), len(doc_data.pages)
            except Exception:
                return filename, "[Document uploaded but detailed text extraction is currently processing]", 1

        elif extension in (".png", ".jpg", ".jpeg", ".webp"):
            return filename, f"[Attached Image: {filename}]", 1

    except Exception as e:
        logger.warning("[extract_file_content_instant] Fallback extraction failed for %s: %s", file_id, e)

    return filename, "", 0


async def build_thread_document_context(
    session: AsyncSession,
    user_id: UUID,
    thread_id: Optional[UUID],
    explicit_file_ids: Optional[List[UUID]] = None,
    max_total_chars: int = 25000,
) -> Tuple[str, List[dict]]:
    """Build formatted document context for all files attached to this thread.
    
    Returns:
        (formatted_markdown_context, list_of_file_info_dicts)
    """
    file_ids = await resolve_thread_file_ids(
        session=session,
        user_id=user_id,
        thread_id=thread_id,
        explicit_file_ids=explicit_file_ids,
    )
    if not file_ids:
        return "", []

    docs_blocks: List[str] = []
    files_info: List[dict] = []
    chars_per_doc = max(max_total_chars // max(len(file_ids), 1), 6000)

    for fid in file_ids:
        fname, text, pcount = await extract_file_content_instant(session, fid, user_id)
        if not text and not fname:
            continue

        files_info.append({
            "file_id": str(fid),
            "filename": fname,
            "page_count": pcount,
            "char_count": len(text),
        })

        if text:
            # Intelligent head + tail truncation for large documents
            if len(text) > chars_per_doc:
                head_size = int(chars_per_doc * 0.7)
                tail_size = int(chars_per_doc * 0.3)
                truncated_text = (
                    text[:head_size]
                    + f"\n\n[... {len(text) - (head_size + tail_size)} characters omitted from middle ...]\n\n"
                    + text[-tail_size:]
                )
            else:
                truncated_text = text

            block = (
                f"=== ATTACHED DOCUMENT: {fname} (Pages: {pcount}) ===\n"
                f"{truncated_text}\n"
                f"=== END OF ATTACHED DOCUMENT: {fname} ==="
            )
            docs_blocks.append(block)

    if not docs_blocks:
        return "", files_info

    formatted_context = "\n\n".join(docs_blocks)
    return formatted_context, files_info
