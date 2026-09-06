from app.services.parsers.base import BaseParser
from app.services.parsers.docx import DocxParser
from app.services.parsers.image import ImageParser
from app.services.parsers.pdf import PdfParser
from app.services.parsers.pptx import PptxParser
from app.services.parsers.tabular import TabularParser
from app.services.parsers.text import TextParser


def get_parser_for_extension(extension: str) -> BaseParser:
    ext = extension.lower()
    if ext == ".pdf":
        return PdfParser()
    elif ext == ".docx":
        return DocxParser()
    elif ext == ".pptx":
        return PptxParser()
    elif ext in (
        ".txt", ".md", ".py", ".js", ".jsx", ".ts", ".tsx", ".html",
        ".css", ".json", ".sql", ".yaml", ".yml", ".xml", ".java",
        ".cpp", ".c", ".h", ".hpp", ".go", ".rs", ".php", ".sh",
        ".bash", ".toml", ".ini", ".graphql"
    ):
        return TextParser()
    elif ext in (".csv", ".xlsx"):
        return TabularParser()
    elif ext in (".png", ".jpg", ".jpeg", ".webp"):
        return ImageParser()
    else:
        raise ValueError(f"No parser available for extension: {extension}")
