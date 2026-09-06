from typing import Any

from app.core.config import get_settings
from app.schemas.document import ParsedDocumentData
from app.services.chunking.base import BaseChunker


class DocumentChunker(BaseChunker):
    def __init__(self, default_chunk_size: int | None = None, default_chunk_overlap: int | None = None):
        settings = get_settings()
        self.default_chunk_size = default_chunk_size or settings.chunk_size
        self.default_chunk_overlap = default_chunk_overlap or settings.chunk_overlap

    def chunk_document(
        self,
        doc_data: ParsedDocumentData,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> list[dict[str, Any]]:
        size = chunk_size or self.default_chunk_size
        overlap = chunk_overlap or self.default_chunk_overlap

        chunks: list[dict[str, Any]] = []
        global_chunk_idx = 0

        for page in doc_data.pages:
            page_num = page.page_number

            # If page has structured blocks, pack blocks into chunks
            if page.blocks:
                current_chunk_text = ""
                current_block_types: list[str] = []
                current_meta: dict[str, Any] = {
                    "source_file_id": str(doc_data.file_id),
                    "filename": doc_data.filename,
                    "extension": doc_data.extension,
                    "page_number": page_num,
                }

                for block in page.blocks:
                    block_content = block.content.strip()
                    if not block_content:
                        continue

                    # If block itself exceeds chunk_size, split by sliding window
                    if len(block_content) > size:
                        # Flush accumulated text first
                        if current_chunk_text:
                            chunks.append({
                                "chunk_index": global_chunk_idx,
                                "content": current_chunk_text.strip(),
                                "page_number": page_num,
                                "metadata": {
                                    **current_meta,
                                    "block_types": list(set(current_block_types)),
                                }
                            })
                            global_chunk_idx += 1
                            current_chunk_text = ""
                            current_block_types = []

                        # Split the oversized block
                        step = max(size - overlap, 1)
                        for start in range(0, len(block_content), step):
                            sub_text = block_content[start:start + size].strip()
                            if sub_text:
                                chunks.append({
                                    "chunk_index": global_chunk_idx,
                                    "content": sub_text,
                                    "page_number": page_num,
                                    "metadata": {
                                        **current_meta,
                                        "block_types": [block.block_type],
                                        "is_partial_block": True,
                                    }
                                })
                                global_chunk_idx += 1
                        continue

                    # Check if adding this block exceeds target chunk_size
                    potential_len = len(current_chunk_text) + len(block_content) + 2
                    if potential_len > size and current_chunk_text:
                        # Emit chunk
                        chunks.append({
                            "chunk_index": global_chunk_idx,
                            "content": current_chunk_text.strip(),
                            "page_number": page_num,
                            "metadata": {
                                **current_meta,
                                "block_types": list(set(current_block_types)),
                            }
                        })
                        global_chunk_idx += 1

                        # Carry over overlap if possible
                        if overlap > 0 and len(current_chunk_text) > overlap:
                            current_chunk_text = current_chunk_text[-overlap:].strip() + "\n\n" + block_content
                        else:
                            current_chunk_text = block_content
                        current_block_types = [block.block_type]
                    else:
                        if current_chunk_text:
                            current_chunk_text += "\n\n" + block_content
                        else:
                            current_chunk_text = block_content
                        current_block_types.append(block.block_type)

                if current_chunk_text.strip():
                    chunks.append({
                        "chunk_index": global_chunk_idx,
                        "content": current_chunk_text.strip(),
                        "page_number": page_num,
                        "metadata": {
                            **current_meta,
                            "block_types": list(set(current_block_types)),
                        }
                    })
                    global_chunk_idx += 1

            # Fallback: if page only has raw text
            elif page.text and page.text.strip():
                raw_text = page.text.strip()
                page_meta = {
                    "source_file_id": str(doc_data.file_id),
                    "filename": doc_data.filename,
                    "extension": doc_data.extension,
                    "page_number": page_num,
                    "block_types": ["raw_text"],
                }

                step = max(size - overlap, 1)
                for start in range(0, len(raw_text), step):
                    sub_text = raw_text[start:start + size].strip()
                    if sub_text:
                        chunks.append({
                            "chunk_index": global_chunk_idx,
                            "content": sub_text,
                            "page_number": page_num,
                            "metadata": page_meta
                        })
                        global_chunk_idx += 1

        return chunks
