import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / '.env')

from groq import AsyncGroq


async def main() -> None:
    key = os.getenv('GROQ_API_KEY')
    models = ['qwen/qwen3.6-27b', 'qwen/qwen3.8-27b', 'openai/gpt-oss-120b', 'groq/compound', 'groq/compound-mini']
    client = AsyncGroq(api_key=key, timeout=30.0, max_retries=0)
    for model in models:
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=[{'role': 'user', 'content': 'Reply with exactly: TARK AI works'}],
                max_tokens=20,
            )
            print(json.dumps({'model': model, 'ok': True, 'text': resp.choices[0].message.content}, ensure_ascii=False))
        except Exception as e:
            print(json.dumps({
                'model': model,
                'ok': False,
                'type': type(e).__name__,
                'status': getattr(e, 'status_code', None),
                'message': str(e).replace(key, '[REDACTED]') if key else str(e),
            }, ensure_ascii=False))
    await client.close()


if __name__ == '__main__':
    asyncio.run(main())
