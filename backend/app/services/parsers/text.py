from uuid import UUID

from app.schemas.document import Block, Page, ParsedDocumentData
from app.services.parsers.base import BaseParser


class TextParser(BaseParser):
    async def parse(
        self, content_bytes: bytes, file_id: UUID, filename: str, extension: str
    ) -> tuple[ParsedDocumentData, bool]:
        try:
            text = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = content_bytes.decode("latin-1", errors="replace")

        lines = text.splitlines()
        blocks: list[Block] = []
        current_paragraph: list[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                if current_paragraph:
                    para_text = "\n".join(current_paragraph)
                    blocks.append(Block(block_type="paragraph", content=para_text, page_number=1))
                    current_paragraph = []
            elif stripped.startswith("#"):
                if current_paragraph:
                    blocks.append(Block(block_type="paragraph", content="\n".join(current_paragraph), page_number=1))
                    current_paragraph = []
                blocks.append(Block(block_type="heading", content=stripped, page_number=1))
            else:
                current_paragraph.append(line)

        if current_paragraph:
            blocks.append(Block(block_type="paragraph", content="\n".join(current_paragraph), page_number=1))

        if not blocks and text.strip():
            blocks.append(Block(block_type="paragraph", content=text.strip(), page_number=1))

        page = Page(
            page_number=1,
            text=text,
            blocks=blocks,
            tables=[],
            images=[]
        )

        doc_data = ParsedDocumentData(
            file_id=file_id,
            filename=filename,
            extension=extension,
            pages=[page],
            metadata={"parser": "TextParser", "total_lines": len(lines)}
        )
        return doc_data, False
