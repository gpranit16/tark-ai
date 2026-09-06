import io
from typing import Any
from PIL import Image
import numpy as np

from app.services.ocr.base import BaseOCRProvider


class RapidOCRProvider(BaseOCRProvider):
    def __init__(self) -> None:
        self._engine: Any = None

    def _get_engine(self) -> Any:
        if self._engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
                self._engine = RapidOCR()
            except Exception as e:
                raise RuntimeError(f"RapidOCR initialization failed: {e}")
        return self._engine

    @property
    def provider_name(self) -> str:
        return "rapidocr"

    async def extract_text(self, image_bytes: bytes) -> tuple[str, list[dict[str, Any]]]:
        try:
            engine = self._get_engine()
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img_np = np.array(img)
            result, _ = engine(img_np)
            if not result:
                return "", []

            lines = []
            blocks = []
            for item in result:
                if len(item) >= 2:
                    box = item[0]
                    text = item[1]
                    score = item[2] if len(item) > 2 else 1.0
                    lines.append(text)
                    blocks.append({
                        "text": text,
                        "confidence": float(score),
                        "box": box if isinstance(box, list) else str(box)
                    })

            full_text = "\n".join(lines)
            return full_text, blocks
        except Exception:
            return "", []
