"""
ResearchSynthesizer — Phase 10 LangGraph Node.

Uses the reasoning/normal model to synthesize a structured final answer
from verified evidence, with proper citations.

CRITICAL: Only makes claims supported by verified evidence.
Never fabricates information or invents sources.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from app.core.enums import ConversationMode, MessageRole
from app.providers.base import NormalizedMessage
from app.services.chat.router import ModelRouter
from app.services.research.models import Citation, Evidence, EvidenceSource, VerificationResult

logger = logging.getLogger(__name__)

_SYNTHESIZER_SYSTEM = """You are a rigorous research analyst synthesizing verified evidence into an objective, factual, and strictly grounded report.

CRITICAL GROUNDING AND ACCURACY RULES:
1. STRICT GROUNDING: Every factual claim (pricing, features, architecture, autonomy levels, context windows, model names) MUST be directly supported by a cited source [N] from the provided evidence.
2. REJECT UNSUPPORTED CLAIMS & PROHIBITED INFERENCES: NEVER infer or assume corporate acquisitions, parent organizations, pricing tiers, system architectures, or security incidents from unrelated or ambiguous snippets.
3. EXPLICIT "NOT VERIFIED" REQUIREMENT: If the retrieved evidence does not contain verified data for any specific aspect asked in the query (e.g., pricing, context limit, or architecture), you MUST explicitly state: "[Aspect]: Not verified". Do NOT speculate or guess.
4. OFFICIAL SOURCE PREFERENCE: Prefer official/primary sources (marked [Official]) for product capabilities, pricing, and availability.
5. CITATIONS: Use [N] notation where N matches the source number provided. Every bullet point in Key Findings and Detailed Analysis MUST include at least one valid [N] citation.
6. CLEAR LIMITATIONS: In ## Limitations & Caveats, explicitly list what was not verified or where sources conflict.

Structure your response strictly as:

## Executive Summary
[2–3 sentence factual overview of verified findings]

## Key Findings
[Bullet points of verified facts, each cited with [N]; for unverified aspects state "Not verified"]

## Detailed Analysis
[Detailed structured comparison/analysis with citations [N]]

## Limitations & Caveats
[List all unverified aspects, missing data points, or source conflicts]

## Sources
[List all cited sources formatted as: - [N] Title (Domain) - URL]

Current date: {current_date}
"""


class ResearchSynthesizer:
    """Synthesizes verified evidence into a structured final answer with citations."""

    def __init__(
        self,
        router: Optional[ModelRouter] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.router = router or ModelRouter.from_settings()
        self.provider = provider
        self.model = model

    async def synthesize(
        self,
        query: str,
        evidence: list[Evidence],
        verification: Optional[VerificationResult] = None,
        is_partial: bool = False,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> tuple[str, list[Citation]]:
        """
        Produce a complete final answer and citation list from the evidence.
        Guarantees completion with bounded 1-time continuation if generation was truncated.

        Returns (final_answer_markdown, citations).
        """
        current_date = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")
        system_prompt = _SYNTHESIZER_SYSTEM.format(current_date=current_date)

        if not evidence:
            partial_note = "\n\n> ⚠️ **Note**: Insufficient evidence was gathered for a complete answer. The above represents the best available information."
            return (
                f"## Research Results\n\nI was unable to gather sufficient evidence to comprehensively answer your research question: **{query}**\n\n"
                f"**Reason**: {verification.reasoning if verification else 'No evidence collected.'}{partial_note}",
                [],
            )

        evidence_text, source_index = self._format_evidence_for_synthesis(evidence)

        partial_warning = ""
        conflict_note = ""
        missing_note = ""
        if is_partial:
            partial_warning = "\n\n**Important**: Evidence gathering was incomplete. Some aspects may not be fully covered."
        if verification:
            if verification.conflicts:
                conflict_note = f"\n\nNote: Source conflicts detected: {'; '.join(verification.conflicts[:3])}"
            if verification.missing_information:
                missing_note = f"\n\nNote: The following aspects lacked sufficient evidence and must be marked 'Not verified': {'; '.join(verification.missing_information[:4])}"

        user_prompt = (
            f"Research question: {query}{partial_warning}{conflict_note}{missing_note}\n\n"
            f"Verified evidence sources:\n{evidence_text}\n\n"
            f"Synthesize a comprehensive, accurate, and well-cited answer strictly following the grounding rules."
        )

        messages = [
            NormalizedMessage(role=MessageRole.SYSTEM, content=system_prompt),
            NormalizedMessage(role=MessageRole.USER, content=user_prompt),
        ]

        active_provider = provider or self.provider
        active_model = model or self.model
        raw_answer, finish_reason = await self._stream_collect(
            messages,
            provider=active_provider,
            model=active_model,
            max_tokens=6000,
            timeout=75.0,
        )

        if not raw_answer.strip():
            raw_answer = f"Research on '{query}' gathered {len(evidence)} sources but synthesis failed. Please try again."

        # Truncation Detection & Bounded Continuation (1 attempt max)
        if self._is_truncated(raw_answer, finish_reason):
            logger.info("Synthesizer detected truncated generation (finish_reason=%s). Attempting 1-time continuation.", finish_reason)
            continuation_text = await self._continue_synthesis(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                partial_answer=raw_answer,
                provider=active_provider,
                model=active_model,
            )
            if continuation_text:
                raw_answer = self._merge_continuation(raw_answer, continuation_text)

        # Post-process: Clean hallucinated citations & build verified citation objects
        cleaned_answer, citations = self._validate_and_build_citations(raw_answer, source_index)
        return cleaned_answer, citations

    @classmethod
    def _is_truncated(cls, text: str, finish_reason: Optional[str] = None) -> bool:
        """Detect whether synthesis output stopped prematurely."""
        if not text or len(text.strip()) < 30:
            return False

        if finish_reason and finish_reason.lower() in ("length", "max_tokens"):
            return True

        stripped = text.strip()

        # 1. Check if unclosed code fence
        if stripped.count("```") % 2 != 0:
            return True

        # 2. Check if ends with dangling connector words or punctuation
        dangling_pattern = re.compile(
            r"\b(and|or|in|to|with|for|the|a|an|as|of|by|from|which|that|e\.g\.|i\.e\.|including|such as|namely)\s*$",
            re.IGNORECASE,
        )
        if dangling_pattern.search(stripped):
            return True

        # 3. Check if missing terminal sentence punctuation in last 50 characters
        last_chars = stripped[-50:]
        if not any(c in last_chars for c in (".", "!", "?", "]", ")", "*", "`", ":", "\n")):
            return True

        # 4. If long analysis exists but lacks closing sections
        if ("## Detailed Analysis" in stripped or "## Key Findings" in stripped) and len(stripped) > 400:
            if "## Sources" not in stripped and "## Limitations" not in stripped:
                return True

        return False

    async def _continue_synthesis(
        self,
        system_prompt: str,
        user_prompt: str,
        partial_answer: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str:
        """Perform one-time bounded continuation call for truncated synthesis."""
        tail_snippet = partial_answer[-300:].strip()
        continuation_messages = [
            NormalizedMessage(role=MessageRole.SYSTEM, content=system_prompt),
            NormalizedMessage(role=MessageRole.USER, content=user_prompt),
            NormalizedMessage(role=MessageRole.ASSISTANT, content=partial_answer),
            NormalizedMessage(
                role=MessageRole.USER,
                content=(
                    f"Your previous response stopped before completion (ending around: \"{tail_snippet}\"). "
                    "Continue exactly from where the previous response stopped. "
                    "Do NOT repeat previous content. Complete the unfinished section and finish the report "
                    "with ## Limitations & Caveats and ## Sources."
                ),
            ),
        ]
        continuation_text, _reason = await self._stream_collect(
            continuation_messages,
            provider=provider,
            model=model,
            max_tokens=4000,
            timeout=50.0,
        )
        return continuation_text

    @classmethod
    def _merge_continuation(cls, initial_text: str, continuation_text: str) -> str:
        """Merge continuation text cleanly without duplicating words or breaking formatting."""
        if not continuation_text or not continuation_text.strip():
            return initial_text

        init_clean = initial_text.rstrip()
        cont_clean = continuation_text.lstrip()

        # Check for small overlapping phrase (2 to 8 words)
        init_words = [re.sub(r"[^\w]", "", w).lower() for w in init_clean.split()]
        cont_words_raw = cont_clean.split()
        cont_words_clean = [re.sub(r"[^\w]", "", w).lower() for w in cont_words_raw]

        for overlap_len in range(min(8, len(init_words), len(cont_words_clean)), 1, -1):
            tail_phrase = " ".join(init_words[-overlap_len:])
            head_phrase = " ".join(cont_words_clean[:overlap_len])
            if tail_phrase and tail_phrase == head_phrase:
                regex_pattern = r"^\s*" + r"\s+".join(re.escape(w) for w in cont_words_raw[:overlap_len])
                m = re.match(regex_pattern, cont_clean, re.IGNORECASE)
                if m:
                    cont_clean = cont_clean[m.end():].lstrip()
                else:
                    cont_clean = " ".join(cont_words_raw[overlap_len:])
                break

        # Join cleanly
        if init_clean.endswith(("\n", ".", "!", "?", ":", ";", "*", "-", ">", "#")):
            if cont_clean.startswith(("\n", "##", "*", "-", "1.", "2.")):
                return f"{init_clean}\n\n{cont_clean}"
            return f"{init_clean} {cont_clean}"
        return f"{init_clean} {cont_clean}"

    def _format_evidence_for_synthesis(
        self, evidence: list[Evidence]
    ) -> tuple[str, dict[int, Evidence]]:
        """Format evidence with numbered sources. Returns (formatted_text, {number: evidence})."""
        lines = []
        source_index: dict[int, Evidence] = {}
        for idx, ev in enumerate(evidence[:25], 1):  # Cap at 25 sources
            source_index[idx] = ev
            official_tag = " [Official/Primary]" if ev.is_official else ""
            domain_info = f" (Domain: {ev.domain})" if ev.domain else ""
            page_info = f", Page {ev.page_number}" if ev.page_number else ""
            pub_info = f", Published: {ev.published_at}" if ev.published_at else ""
            lines.append(
                f"[{idx}]{official_tag} {ev.title or 'Source'}{domain_info} ({ev.source_type}){page_info}{pub_info}\n"
                f"    URL: {ev.url or ev.file_id or 'N/A'}\n"
                f"    Content: {ev.content[:700]}"
            )
        return "\n\n".join(lines), source_index

    async def _stream_collect(
        self,
        messages: list[NormalizedMessage],
        provider: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 6000,
        timeout: float = 75.0,
    ) -> tuple[str, Optional[str]]:
        chunks: list[str] = []
        finish_reason: Optional[str] = None

        async def _collect():
            nonlocal finish_reason
            async for _sel, event in self.router.stream(
                messages=messages,
                mode=ConversationMode.DEEP_RESEARCH,
                provider=provider,
                model=model,
                max_tokens=max_tokens,
            ):
                if event.delta:
                    chunks.append(event.delta)
                if event.finish_reason:
                    finish_reason = event.finish_reason

        try:
            await asyncio.wait_for(_collect(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Synthesizer stream timed out after %.1fs", timeout)
            finish_reason = "timeout"
        except Exception as exc:
            logger.warning("Synthesizer stream failed: %s", exc)
            finish_reason = "error"
        clean_output = re.sub(r"<think>[\s\S]*?</think>", "", "".join(chunks)).strip()
        return clean_output, finish_reason

    def _validate_and_build_citations(
        self,
        answer_text: str,
        source_index: dict[int, Evidence],
    ) -> tuple[str, list[Citation]]:
        """
        Validates citations in the synthesized text:
        - Removes citations [N] that do not exist in source_index (hallucinated tags)
        - Builds Citation objects only for actually cited valid evidence sources
        """
        valid_nums = set(source_index.keys())

        # Replace any citation [N] where N not in valid_nums with empty string
        def _replace_invalid(match: re.Match) -> str:
            num = int(match.group(1))
            return match.group(0) if num in valid_nums else ""

        cleaned_text = re.sub(r"\[(\d+)\]", _replace_invalid, answer_text)

        # Re-scan for valid used citation numbers
        used_nums = set(int(m) for m in re.findall(r"\[(\d+)\]", cleaned_text) if int(m) in valid_nums)

        citations: list[Citation] = []
        for num in sorted(used_nums):
            ev = source_index[num]
            citations.append(Citation(
                source_type=ev.source_type,
                title=ev.title or "Source",
                url=ev.url,
                domain=ev.domain,
                file_id=ev.file_id,
                page_number=ev.page_number,
                published_at=ev.published_at,
            ))
        return cleaned_text, citations

    def _build_citations(
        self,
        evidence: list[Evidence],
        source_index: dict[int, Evidence],
        answer_text: str,
    ) -> list[Citation]:
        """Backward-compatible helper to build Citation objects from answer text."""
        _cleaned, citations = self._validate_and_build_citations(answer_text, source_index)
        return citations


