import asyncio
import json
import logging
import re
import sys
import uuid

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("live_verify")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.conversation import User, Thread, Message
from app.models.research import ResearchSession
from app.services.research.manager import ResearchManager

LONG_QUERY = (
    "Compare Cursor, Claude Code, Windsurf, GitHub Copilot, and Devin in 2026. "
    "For each product analyze official pricing, architecture, agentic capabilities, "
    "autonomy level, context window limits, supported IDE/workflows, enterprise availability, "
    "strengths, weaknesses, and major limitations. Prefer official sources. "
    "Cite every factual claim and explicitly mark anything that cannot be verified."
)

def parse_sse_block(block: str):
    event_name = None
    data_lines = []
    for line in block.strip().split("\n"):
        if line.startswith("event: "):
            event_name = line[7:].strip()
        elif line.startswith("data: "):
            data_lines.append(line[6:].strip())
    data_str = "\n".join(data_lines)
    data = {}
    if data_str:
        try:
            data = json.loads(data_str)
        except Exception:
            data = {"raw": data_str}
    return event_name, data

async def run_live_test():
    async with AsyncSessionLocal() as db:
        # Get or create dev user
        result = await db.execute(select(User).limit(1))
        user = result.scalars().first()
        if not user:
            user = User(id=uuid.uuid4())
            db.add(user)
            await db.commit()
            await db.refresh(user)

        # Create thread
        thread = Thread(
            id=uuid.uuid4(),
            user_id=user.id,
            title="Deep Research 5-Entity Comparison Live Test"
        )
        db.add(thread)
        await db.commit()
        await db.refresh(thread)

        user_id = user.id
        thread_id = thread.id

    print("=" * 80)
    print("STARTING LIVE DEEP RESEARCH VERIFICATION")
    print(f"User ID: {user_id}")
    print(f"Thread ID: {thread_id}")
    print(f"Query: {LONG_QUERY}")
    print("=" * 80)

    events_received = []
    text_deltas = []
    complete_event_payload = None

    manager = ResearchManager()

    async with AsyncSessionLocal() as db:
        async for sse_chunk in manager.stream_research(
            session=db,
            thread_id=thread_id,
            user_id=user_id,
            project_id=None,
            query=LONG_QUERY,
            is_disconnected=lambda: False,
        ):
            for block in sse_chunk.strip().split("\n\n"):
                if not block.strip():
                    continue
                event_name, data = parse_sse_block(block)
                if not event_name:
                    continue
                events_received.append((event_name, data))

                if event_name == "text_delta":
                    delta = data.get("delta", "")
                    text_deltas.append(delta)
                    print(delta, end="", flush=True)
                elif event_name == "research_complete":
                    complete_event_payload = data
                    print(f"\n\n[EVENT: research_complete received: {json.dumps(data, default=str)}]")
                else:
                    print(f"\n[EVENT: {event_name}] {json.dumps(data, default=str)[:120]}", flush=True)

    streamed_full_text = "".join(text_deltas)
    print("\n" + "=" * 80)
    print("STREAMING FINISHED. RUNNING VERIFICATION CHECKS...")
    print("=" * 80)

    # 1. Verify Event Order
    event_names = [e[0] for e in events_received]
    print(f"\nEvent sequence ({len(event_names)} events total):")
    distinct_sequence = []
    for name in event_names:
        if not distinct_sequence or distinct_sequence[-1] != name:
            distinct_sequence.append(name)
    print(" -> ".join(distinct_sequence))

    assert "research_started" in event_names, "Missing research_started event"
    assert "research_complete" in event_names, "Missing research_complete event"
    assert "message_end" in event_names, "Missing message_end event"

    # Assert research_complete and message_end come AFTER all text_deltas
    last_text_delta_idx = max((i for i, n in enumerate(event_names) if n == "text_delta"), default=-1)
    complete_idx = event_names.index("research_complete")
    end_idx = event_names.index("message_end")

    assert complete_idx > last_text_delta_idx, f"research_complete ({complete_idx}) emitted before last text_delta ({last_text_delta_idx})"
    assert end_idx > complete_idx, f"message_end ({end_idx}) emitted before research_complete ({complete_idx})"
    print("[PASS] Event ordering invariant verified: text_deltas -> research_complete -> message_end")

    # 2. Verify Database Persistence
    message_end_event = next((e[1] for e in events_received if e[0] == "message_end"), {})
    message_id = message_end_event.get("message_id") or (complete_event_payload.get("message_id") if complete_event_payload else None)
    assert message_id, "No message_id found in message_end or research_complete event"

    async with AsyncSessionLocal() as db:
        msg = await db.get(Message, uuid.UUID(message_id))
        assert msg is not None, f"Message {message_id} not found in DB"
        persisted_text = msg.content
        assert persisted_text == streamed_full_text, (
            f"DB message length ({len(persisted_text)}) does not match streamed text length ({len(streamed_full_text)})"
        )
        print("[PASS] Database persistence matches streamed text exactly")

        # Check research session
        session_res = await db.execute(
            select(ResearchSession).where(ResearchSession.thread_id == thread_id)
        )
        session = session_res.scalars().first()
        assert session is not None, "ResearchSession not found in DB"
        assert session.status == "completed", f"Session status is {session.status}, expected completed"
        print(f"[PASS] ResearchSession status is completed (confidence: {session.confidence})")

    # 3. Text Completeness & Quality Checks
    char_count = len(streamed_full_text)
    word_count = len(streamed_full_text.split())
    source_count = complete_event_payload.get("source_count", 0) if complete_event_payload else 0
    conf = complete_event_payload.get("confidence", 0.0) if complete_event_payload else 0.0

    # Calculate coverage
    target_entities = ["Cursor", "Claude Code", "Windsurf", "GitHub Copilot", "Devin"]
    target_attributes = ["pricing", "architecture", "agentic", "autonomy", "context window", "IDE", "enterprise", "strengths", "weaknesses", "limitations"]
    covered_entities = [e for e in target_entities if e.lower() in streamed_full_text.lower()]
    covered_attributes = [a for a in target_attributes if a.lower() in streamed_full_text.lower()]
    entity_coverage_pct = (len(covered_entities) / len(target_entities)) * 100
    attribute_coverage_pct = (len(covered_attributes) / len(target_attributes)) * 100

    print(f"\nFinal Report Metrics:")
    print(f"  - Character count: {char_count}")
    print(f"  - Word count: {word_count}")
    print(f"  - Usable Source count: {source_count}")
    print(f"  - Confidence: {conf * 100:.1f}% ({conf})")
    print(f"  - Entity Coverage: {entity_coverage_pct:.1f}% ({len(covered_entities)}/{len(target_entities)}) -> {covered_entities}")
    print(f"  - Attribute Coverage: {attribute_coverage_pct:.1f}% ({len(covered_attributes)}/{len(target_attributes)}) -> {covered_attributes}")

    # Check that report doesn't end mid-sentence / truncation
    stripped = streamed_full_text.strip()
    assert not re.search(r'\b(and|or|but|the|a|an|in|with|to|for|of|is|are|was|were|has|have|that|which|because)\s*$', stripped, re.IGNORECASE), (
        f"Report ends abruptly with dangling word: {stripped[-50:]!r}"
    )
    assert not stripped.endswith((",", ";", ":", "/", "\\")), (
        f"Report ends with mid-sentence punctuation: {stripped[-50:]!r}"
    )
    print("[PASS] Report does not end mid-sentence")

    # Check that entities are covered
    entities = ["Cursor", "Claude Code", "Windsurf", "GitHub Copilot", "Devin"]
    for entity in entities:
        assert entity.lower() in streamed_full_text.lower(), f"Entity {entity} missing from final report"
    print(f"[PASS] All 5 entities ({entities}) present in final report")

    # Check structure (headings, sections)
    assert "##" in streamed_full_text, "Markdown headings missing from final report"
    print("[PASS] Markdown structure intact")

    print("\n" + "=" * 80)
    print("ALL LIVE VERIFICATION ASSERTIONS PASSED SUCCESSFULLY!")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(run_live_test())
