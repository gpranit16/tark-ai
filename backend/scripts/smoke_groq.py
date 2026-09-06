import asyncio
import json
import os

from app.core.config import get_settings
from app.providers.groq import GroqProvider


async def main() -> None:
    settings = get_settings()
    if not settings.groq_api_key:
        print("SKIP: GROQ_API_KEY not configured")
        return

    provider = GroqProvider(api_key=settings.groq_api_key, default_model="llama-3.1-8b-instant", timeout=30.0)
    async for event in provider.stream(
        messages=[{"role": "user", "content": "Say hello from Groq."}],
        model="llama-3.1-8b-instant",
        mode="normal",
    ):
        print(json.dumps({"delta": event.delta, "finish_reason": event.finish_reason}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
