import asyncio
import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

load_dotenv(Path(__file__).resolve().parents[1] / '.env')

base = 'http://127.0.0.1:8124'
user_id = '00000000-0000-0000-0000-000000000001'


async def check_db(thread_id: str) -> None:
    database_url = os.getenv('DATABASE_URL')
    engine = create_async_engine(database_url, pool_pre_ping=True)
    async with AsyncSession(engine) as session:
        rows = await session.execute(
            select(
                __import__('app.models.conversation', fromlist=['Message']).Message.role,
                __import__('app.models.conversation', fromlist=['Message']).Message.content,
                __import__('app.models.conversation', fromlist=['Message']).Message.provider,
                __import__('app.models.conversation', fromlist=['Message']).Message.model,
                __import__('app.models.conversation', fromlist=['Message']).Message.thread_id,
            ).where(__import__('app.models.conversation', fromlist=['Message']).Message.thread_id == __import__('uuid').UUID(thread_id))
        )
        result = rows.all()
        print('DB_MESSAGES')
        for row in result:
            print(row)
    await engine.dispose()


def main() -> None:
    print('SEED', requests.post(f'{base}/dev/seed-test-user', timeout=30).text)

    thread = requests.post(
        f'{base}/api/v1/threads',
        json={'user_id': user_id, 'title': 'Live SSE check', 'default_mode': 'normal'},
        timeout=30,
    )
    print('THREAD_STATUS', thread.status_code)
    print('THREAD_BODY', thread.text)
    thread_id = thread.json()['id']

    chat = requests.post(
        f'{base}/api/v1/threads/{thread_id}/chat',
        json={'content': 'Reply with exactly: TARK AI works', 'mode': 'normal'},
        stream=True,
        timeout=180,
    )
    print('CHAT_STATUS', chat.status_code)
    print('CHAT_CONTENT_TYPE', chat.headers.get('content-type'))
    events = []
    for line in chat.iter_lines():
        if not line:
            continue
        text = line.decode('utf-8', 'replace')
        print(text)
        events.append(text)

    if not any('event: message_start' in e for e in events):
        raise RuntimeError('Missing message_start event')
    if not any('event: text_delta' in e for e in events):
        raise RuntimeError('Missing text_delta event')
    if not any('event: message_complete' in e for e in events):
        raise RuntimeError('Missing message_complete event')

    asyncio.run(check_db(thread_id))


if __name__ == '__main__':
    main()
