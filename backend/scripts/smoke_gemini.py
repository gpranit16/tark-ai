import asyncio
import json

from app.core.config import get_settings
from app.providers.gemini import GeminiProvider


async def main() -> None:
    settings = get_settings()
    if not settings.gemini_api_key:
        print("SKIP: GEMINI_API_KEY not configured")
        return

    provider = GeminiProvider(api_key=settings.gemini_api_key, default_model="gemini-2.5-flash", timeout=30.0)
    async for event in provider.stream(
        messages=[{"role": "user", "content": "Say hello from Gemini."}],
        model="gemini-2.5-flash",
        mode="normal",
    ):
        print(json.dumps({"delta": event.delta, "finish_reason": event.finish_reason}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
