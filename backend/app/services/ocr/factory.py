from app.services.ocr.base import BaseOCRProvider
from app.services.ocr.rapid_ocr import RapidOCRProvider

_ocr_instance: BaseOCRProvider | None = None


def get_ocr_provider() -> BaseOCRProvider:
    global _ocr_instance
    if _ocr_instance is None:
        _ocr_instance = RapidOCRProvider()
    return _ocr_instance
