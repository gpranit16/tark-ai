import io
from uuid import UUID
import pypdf

from app.schemas.document import Block, ImageData, Page, ParsedDocumentData
from app.services.ocr.factory import get_ocr_provider
from app.services.parsers.base import BaseParser


class PdfParser(BaseParser):
    async def parse(
        self, content_bytes: bytes, file_id: UUID, filename: str, extension: str
    ) -> tuple[ParsedDocumentData, bool]:
        reader = pypdf.PdfReader(io.BytesIO(content_bytes))
        total_pages = len(reader.pages)
        pages: list[Page] = []
        ocr_used = False

        total_extracted_text = ""
        page_raw_texts: list[str] = []

        # 1. First pass: extract text page by page using pypdf
        for page_idx, pypdf_page in enumerate(reader.pages, start=1):
            try:
                extracted = pypdf_page.extract_text() or ""
            except Exception:
                extracted = ""
            page_raw_texts.append(extracted)
            total_extracted_text += extracted

        # Detect text-based vs scanned PDF
        avg_text_per_page = len(total_extracted_text.strip()) / max(total_pages, 1)
        is_scanned = avg_text_per_page < 20

        ocr_provider = get_ocr_provider()

        # 2. Second pass: construct pages & blocks
        for page_idx, pypdf_page in enumerate(reader.pages, start=1):
            raw_text = page_raw_texts[page_idx - 1]
            page_blocks: list[Block] = []
            page_images: list[ImageData] = []

            # Extract images from pypdf page if available
            extracted_images: list[bytes] = []
            try:
                for img in pypdf_page.images:
                    extracted_images.append(img.data)
                    page_images.append(ImageData(
                        page_number=page_idx,
                        image_index=len(page_images),
                        format=img.name.split(".")[-1] if "." in img.name else "png"
                    ))
            except Exception:
                pass

            # If page text is sparse/scanned and we extracted page images, run OCR on images
            if (is_scanned or len(raw_text.strip()) < 10) and extracted_images:
                ocr_used = True
                ocr_texts: list[str] = []
                for img_bytes in extracted_images:
                    ocr_t, _ = await ocr_provider.extract_text(img_bytes)
                    if ocr_t.strip():
                        ocr_texts.append(ocr_t.strip())
                
                if ocr_texts:
                    combined_ocr = "\n".join(ocr_texts)
                    raw_text = (raw_text + "\n" + combined_ocr).strip()
                    page_blocks.append(Block(
                        block_type="paragraph",
                        content=combined_ocr,
                        page_number=page_idx,
                        metadata={"source": "ocr_image_extraction"}
                    ))

            # Build normal text blocks
            if raw_text.strip():
                lines = raw_text.splitlines()
                current_p: list[str] = []
                for line in lines:
                    stripped = line.strip()
                    if not stripped:
                        if current_p:
                            page_blocks.append(Block(
                                block_type="paragraph",
                                content="\n".join(current_p),
                                page_number=page_idx
                            ))
                            current_p = []
                    else:
                        current_p.append(stripped)
                
                if current_p:
                    page_blocks.append(Block(
                        block_type="paragraph",
                        content="\n".join(current_p),
                        page_number=page_idx
                    ))

            pages.append(Page(
                page_number=page_idx,
                text=raw_text,
                blocks=page_blocks,
                tables=[],
                images=page_images
            ))

        doc_data = ParsedDocumentData(
            file_id=file_id,
            filename=filename,
            extension=extension,
            pages=pages,
            metadata={
                "parser": "PdfParser",
                "total_pages": total_pages,
                "is_scanned": is_scanned,
                "ocr_used": ocr_used
            }
        )
        return doc_data, ocr_used
