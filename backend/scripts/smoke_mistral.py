import asyncio
import json

from app.core.config import get_settings
from app.providers.mistral import MistralProvider


async def main() -> None:
    settings = get_settings()
    if not settings.mistral_api_key:
        print("SKIP: MISTRAL_API_KEY not configured")
        return

    provider = MistralProvider(api_key=settings.mistral_api_key, default_model="mistral-medium-latest", timeout=30.0)
    async for event in provider.stream(
        messages=[{"role": "user", "content": "Say hello from Mistral."}],
        model="mistral-medium-latest",
        mode="normal",
    ):
        print(json.dumps({"delta": event.delta, "finish_reason": event.finish_reason}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
