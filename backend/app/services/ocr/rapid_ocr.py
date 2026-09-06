import asyncio
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

    def _sync_extract(self, image_bytes: bytes) -> tuple[str, list[dict[str, Any]]]:
        try:
            engine = self._get_engine()
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            
            # Downscale large images to max 1280px to speed up inference 10x and save memory on cloud
            max_dimension = 1280
            if max(img.width, img.height) > max_dimension:
                img.thumbnail((max_dimension, max_dimension), Image.Resampling.BILINEAR)

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

    async def extract_text(self, image_bytes: bytes) -> tuple[str, list[dict[str, Any]]]:
        try:
            # Run CPU-bound OCR in a background worker thread with 12s timeout to never block event loop
            return await asyncio.wait_for(
                asyncio.to_thread(self._sync_extract, image_bytes),
                timeout=12.0
            )
        except Exception:
            return "", []

