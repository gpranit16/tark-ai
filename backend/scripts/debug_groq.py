import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / '.env')

import groq
from groq import AsyncGroq


def redact(value: str | None) -> str | None:
    if not value:
        return value
    return '[REDACTED]'


async def main() -> None:
    key = os.getenv('GROQ_API_KEY')
    model = 'llama-3.3-70b-versatile'
    message = 'Reply with exactly: TARK AI works'
    max_tokens = 20
    result = {
        'key_exists': bool(key),
        'sdk_version': getattr(groq, '__version__', 'unknown'),
        'model': model,
        'message': message,
        'max_tokens': max_tokens,
        'request': {
            'model': model,
            'messages': [{'role': 'user', 'content': message}],
            'max_tokens': max_tokens,
        },
    }

    try:
        client = AsyncGroq(api_key=key, timeout=30.0, max_retries=0)
        models = await client.models.list()
        ids = [m.id for m in getattr(models, 'data', [])]
        print("ALL_MODELS:", ids)
        result['model_available'] = model in ids
        response = await client.chat.completions.create(
            model=model,
            messages=[{'role': 'user', 'content': message}],
            max_tokens=max_tokens,
        )
        result['success'] = True
        result['response_text'] = response.choices[0].message.content if getattr(response, 'choices', None) else None
        result['usage'] = getattr(response, 'usage', None)
    except Exception as exc:
        result['success'] = False
        result['exception_type'] = type(exc).__name__
        result['status_code'] = getattr(exc, 'status_code', None)
        err = str(exc)
        if key:
            err = err.replace(key, '[REDACTED]')
        result['message'] = err
        result['body'] = getattr(exc, 'body', None)
        if isinstance(result['body'], dict):
            text = json.dumps(result['body'])
            if key:
                text = text.replace(key, '[REDACTED]')
            result['body'] = json.loads(text)
    print(json.dumps(result, default=str, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
