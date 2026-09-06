from uuid import UUID

from app.schemas.document import Block, ImageData, Page, ParsedDocumentData
from app.services.ocr.factory import get_ocr_provider
from app.services.parsers.base import BaseParser
from app.services.vision.factory import get_vision_provider


class ImageParser(BaseParser):
    async def parse(
        self, content_bytes: bytes, file_id: UUID, filename: str, extension: str
    ) -> tuple[ParsedDocumentData, bool]:
        ocr = get_ocr_provider()
        ocr_text, ocr_blocks = await ocr.extract_text(content_bytes)

        vision = get_vision_provider()
        description = await vision.analyze_image(content_bytes)

        blocks: list[Block] = []
        if ocr_text.strip():
            blocks.append(Block(
                block_type="paragraph",
                content=ocr_text.strip(),
                page_number=1,
                metadata={"source": "ocr", "detected_blocks": ocr_blocks}
            ))

        if description:
            blocks.append(Block(
                block_type="paragraph",
                content=f"[Image Description]: {description}",
                page_number=1,
                metadata={"source": "vision"}
            ))

        image_data = ImageData(
            page_number=1,
            image_index=0,
            format=extension.replace(".", ""),
            ocr_text=ocr_text,
            description=description
        )

        full_text = f"{ocr_text}\n\n[Image Description]: {description}".strip()

        page = Page(
            page_number=1,
            text=full_text,
            blocks=blocks,
            tables=[],
            images=[image_data]
        )

        doc_data = ParsedDocumentData(
            file_id=file_id,
            filename=filename,
            extension=extension,
            pages=[page],
            metadata={"parser": "ImageParser", "ocr_used": True}
        )
        return doc_data, True
