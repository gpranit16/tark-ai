"""
SectionWorker Node for Deep Research 2.0.

Evidence-grounded parallel section worker.
Strict Rules:
1. Every externally verifiable claim must be grounded in provided evidence sources [N].
2. Never invent citations or fabricate URLs.
3. If evidence is insufficient for a key question or topic, explicitly state:
   "Not found in the provided sources."
4. Flags unsupported claims and collects cited sources.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from app.core.enums import ConversationMode, MessageRole
from app.providers.base import NormalizedMessage
from app.services.chat.router import ModelRouter
from app.services.research.models import Evidence, SectionResult, SectionTask
from app.services.research.router import ResearchTaskType, select_research_model

logger = logging.getLogger(__name__)

_SECTION_WORKER_SYSTEM = """You are a rigorous, evidence-grounded research specialist.
Your task is to write a detailed, authoritative section for a research report based ONLY on the provided evidence sources.

STRICT GROUNDING RULES:
1. Every factual statement (dates, numbers, features, specs, benchmarks, pricing) MUST cite the source using [N] notation.
2. If the provided evidence DOES NOT contain answers to any requested aspect or question, you MUST explicitly write:
   "Not found in the provided sources."
3. Do NOT make assumptions, speculate, or extrapolate beyond the provided text.
4. If sources disagree, explicitly state the conflict and cite both sources.
5. Format the section in clear Markdown with subheadings, concise bullet points, or comparison tables where appropriate.

Respond ONLY with valid JSON:
{{
  "section_title": "Title of section",
  "content": "Full markdown content with inline [N] citations...",
  "cited_sources": [1, 2],
  "unsupported_claims": ["any claim or requested aspect that was not verified in evidence"]
}}"""

_JSON_EXTRACT = re.compile(r"\{[\s\S]*\}", re.DOTALL)


class SectionWorker:
    """Drafts an individual research section strictly grounded in verified evidence."""

    def __init__(
        self,
        router: Optional[ModelRouter] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.router = router or ModelRouter.from_settings()
        self.provider = provider
        self.model = model

    async def execute_task(
        self,
        task: SectionTask,
        evidence: list[Evidence],
        provider: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 35.0,
    ) -> SectionResult:
        """Execute a single section drafting task grounded in evidence."""
        decision = select_research_model(
            ResearchTaskType.SECTION_WORKER,
            self.router,
            explicit_provider=provider or self.provider,
            explicit_model=model or self.model,
        )

        # Format evidence list for this worker with clean [N] indices
        evidence_lines = []
        source_map: dict[int, Evidence] = {}
        for idx, ev in enumerate(evidence, start=1):
            source_map[idx] = ev
            domain_label = f" ({ev.domain})" if ev.domain else ""
            official_label = " [Official Source]" if ev.is_official else ""
            date_label = f" [{ev.published_at[:10]}]" if ev.published_at else ""
            body = ev.content or ev.snippet
            evidence_lines.append(f"[{idx}] {ev.title}{domain_label}{official_label}{date_label}:\n{body[:1800]}\n")

        evidence_text = "\n".join(evidence_lines) if evidence_lines else "(No external evidence provided)"

        user_prompt = (
            f"Section Task: {task.title}\n"
            f"Goal: {task.goal}\n"
            f"Key Questions to address:\n" + "\n".join(f"- {q}" for q in task.key_questions) + "\n\n"
            f"Target word count: ~{task.target_words} words\n\n"
            f"Provided Evidence Sources:\n{evidence_text}\n\n"
            f"Write the section following all grounding rules."
        )

        messages = [
            NormalizedMessage(role=MessageRole.SYSTEM, content=_SECTION_WORKER_SYSTEM),
            NormalizedMessage(role=MessageRole.USER, content=user_prompt),
        ]

        chunks: list[str] = []
        try:
            async for _sel, event in self.router.stream(
                messages=messages,
                mode=ConversationMode.DEEP_RESEARCH,
                provider=decision.provider,
                model=decision.model,
                max_tokens=1500,
            ):
                if event.delta:
                    chunks.append(event.delta)
        except Exception as exc:
            logger.error("[SECTION_WORKER] Failed drafting section %r: %s", task.title, exc)
            return SectionResult(
                section_title=task.title,
                content=f"### {task.title}\n\n*Section generation failed due to a provider error.*",
                citations=[],
                unsupported_claims=["Section generation failed."],
            )

        raw = "".join(chunks)
        raw = re.sub(r"<think>[\s\S]*?</think>", "", raw).strip()
        data = self._parse_json(raw)

        content = data.get("content") or ""
        if not content.strip():
            # If JSON parsing was malformed, fallback to raw text if it looks like markdown
            content = raw if ("#" in raw or len(raw) > 50) else f"### {task.title}\n\nNot found in the provided sources."

        cited_indices = data.get("cited_sources", [])
        if not cited_indices:
            # Deterministic scan for [N] citations in content
            found = re.findall(r"\[(\d+)\]", content)
            cited_indices = [int(n) for n in found if n.isdigit()]

        valid_citations: list[dict] = []
        for c_idx in set(cited_indices):
            if c_idx in source_map:
                ev = source_map[c_idx]
                valid_citations.append({
                    "citation_id": f"cit-{c_idx}",
                    "source_type": ev.source_type.value if hasattr(ev.source_type, "value") else str(ev.source_type),
                    "title": ev.title,
                    "url": ev.url,
                    "domain": ev.domain,
                    "published_at": ev.published_at,
                })

        unsupported = data.get("unsupported_claims", [])

        return SectionResult(
            section_title=task.title,
            content=content,
            citations=valid_citations,
            unsupported_claims=unsupported,
        )

    @staticmethod
    def _parse_json(text: str) -> dict:
        if not text:
            return {}
        text = re.sub(r"```(?:json)?\s*([\s\S]*?)\s*```", r"\1", text).strip()
        try:
            return json.loads(text)
        except Exception:
            pass
        match = _JSON_EXTRACT.search(text)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
        return {}
