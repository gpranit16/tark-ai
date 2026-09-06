"""
VerifierAgent — Phase 10 LangGraph Node.

Uses the reasoning model to evaluate evidence quality, detect contradictions,
and determine whether the evidence is sufficient to synthesize a final answer.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Optional

from app.core.enums import ConversationMode, MessageRole
from app.providers.base import NormalizedMessage
from app.services.chat.router import ModelRouter
from app.services.research.models import Evidence, VerificationResult

logger = logging.getLogger(__name__)

_VERIFIER_SYSTEM = """You are a rigorous research evidence evaluator.

Given a research question and collected evidence, evaluate whether the evidence is sufficient to answer the question accurately and check whether all candidate claims are grounded in the retrieved sources.

Output ONLY valid JSON in this exact format:
{{
  "sufficient": true/false,
  "confidence": 0.0-1.0,
  "supported_claims": ["claim 1", "claim 2"],
  "unsupported_claims": ["claim that lacks evidence or is speculative"],
  "conflicts": ["source A says X but source B says Y"],
  "missing_information": ["specific topic or data point that is missing or unverified"],
  "reasoning": "brief explanation of your assessment"
}}

Rules:
- Be strict: insufficient or contradictory evidence → sufficient=false
- confidence reflects how well the evidence supports a complete, grounded answer (0.0–1.0)
- Never invent evidence that is not in the provided sources
- Identify factual conflicts between sources
- NEVER accept inferences regarding corporate acquisitions, parent companies, architecture specs, or pricing unless explicitly stated in the evidence
- List any sub-topic from the query that is unverified or lacks official evidence in "missing_information" and "unsupported_claims"
"""

_JSON_EXTRACT = re.compile(r"\{[\s\S]*\}", re.DOTALL)


class VerifierAgent:
    """Evaluates evidence quality and determines if synthesis can proceed."""

    def __init__(
        self,
        router: Optional[ModelRouter] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.router = router or ModelRouter.from_settings()
        self.provider = provider
        self.model = model

    async def verify(
        self,
        query: str,
        evidence: list[Evidence],
        min_confidence: float = 0.40,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> VerificationResult:
        """
        Verify evidence quality and coverage against the research query.

        Returns VerificationResult with sufficient=True if confidence >= min_confidence.
        """
        if not evidence:
            return VerificationResult(
                sufficient=False,
                confidence=0.0,
                missing_information=["No evidence was collected."],
                reasoning="No evidence available to verify.",
            )

        coverage = self.analyze_coverage(query, evidence)
        evidence_text = self._format_evidence(evidence)
        messages = [
            NormalizedMessage(role=MessageRole.SYSTEM, content=_VERIFIER_SYSTEM),
            NormalizedMessage(
                role=MessageRole.USER,
                content=f"Research question: {query}\n\nEvidence collected:\n{evidence_text}\n\nEvaluate this evidence.",
            ),
        ]

        active_provider = provider or self.provider
        active_model = model or self.model
        raw_output = await self._stream_collect(
            messages,
            provider=active_provider,
            model=active_model,
        )
        return self._parse_result(raw_output, min_confidence, coverage, evidence)

    @classmethod
    def analyze_coverage(cls, query: str, evidence: list[Evidence]) -> dict[str, Any]:
        """
        Analyze entity coverage and attribute coverage in collected evidence.
        """
        if not query or not evidence:
            return {
                "entity_coverage": 1.0,
                "attribute_coverage": 1.0,
                "requested_entities": [],
                "covered_entities": [],
                "missing_entities": [],
                "requested_attributes": [],
                "covered_attributes": [],
                "missing_attributes": [],
            }

        known_agents = [
            "cursor", "claude code", "claude 3.7 sonnet", "claude 3.7", "claude",
            "windsurf", "github copilot", "copilot workspace", "copilot", "devin",
            "cody", "aider", "cline", "continue", "v0", "bolt", "replit",
        ]
        query_lower = query.lower()
        requested_entities = [ent for ent in known_agents if ent in query_lower]

        ignored_words = {
            "query", "research", "evidence", "analyze", "compare", "what", "how",
            "why", "who", "explain", "evaluate", "terms", "major", "available", "and", "the",
        }

        if not requested_entities:
            caps = re.findall(r"\b[A-Z][a-zA-Z0-9\.\-]+(?:\s+[A-Z][a-zA-Z0-9\.\-]+)*\b", query)
            requested_entities = [
                c.lower() for c in caps
                if len(c) > 2 and c.lower() not in ignored_words
            ]

        known_attributes = [
            "pricing", "price", "cost", "architecture", "autonomy", "context window",
            "context limits", "ide", "workflows", "enterprise", "strengths", "weaknesses", "limitations",
        ]
        requested_attributes = [attr for attr in known_attributes if attr in query_lower]

        combined_evidence_text = " ".join(
            f"{e.title} {e.snippet} {e.content}".lower() for e in evidence
        )

        covered_entities = [ent for ent in requested_entities if ent in combined_evidence_text]
        missing_entities = [ent for ent in requested_entities if ent not in combined_evidence_text]

        covered_attributes = [attr for attr in requested_attributes if attr in combined_evidence_text]
        missing_attributes = [attr for attr in requested_attributes if attr not in combined_evidence_text]

        ent_cov = len(covered_entities) / max(len(requested_entities), 1) if requested_entities else 1.0
        attr_cov = len(covered_attributes) / max(len(requested_attributes), 1) if requested_attributes else 1.0

        return {
            "entity_coverage": round(ent_cov, 2),
            "attribute_coverage": round(attr_cov, 2),
            "requested_entities": requested_entities,
            "covered_entities": covered_entities,
            "missing_entities": missing_entities,
            "requested_attributes": requested_attributes,
            "covered_attributes": covered_attributes,
            "missing_attributes": missing_attributes,
        }

    def _format_evidence(self, evidence: list[Evidence]) -> str:
        """Format evidence list for the verifier prompt."""
        lines = []
        for idx, ev in enumerate(evidence[:15], 1):  # Cap at 15 pieces
            lines.append(
                f"[{idx}] Source: {ev.title or 'Unknown'} ({ev.source_type})\n"
                f"    URL: {ev.url or 'N/A'}\n"
                f"    Content: {ev.content[:400]}..."
            )
        return "\n\n".join(lines)

    async def _stream_collect(
        self,
        messages: list[NormalizedMessage],
        provider: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 25.0,
    ) -> str:
        chunks: list[str] = []

        async def _collect():
            async for _sel, event in self.router.stream(
                messages=messages,
                mode=ConversationMode.DEEP_RESEARCH,
                provider=provider,
                model=model,
                max_tokens=1000,
            ):
                if event.delta:
                    chunks.append(event.delta)

        try:
            await asyncio.wait_for(_collect(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Verifier stream timed out after %.1fs", timeout)
        except Exception as exc:
            logger.warning("Verifier stream failed: %s", exc)
        return "".join(chunks)

    def _parse_result(
        self,
        text: str,
        min_confidence: float,
        coverage: Optional[dict[str, Any]] = None,
        evidence: Optional[list[Evidence]] = None,
    ) -> VerificationResult:
        data = self._extract_json_dict(text)
        if not data:
            logger.warning("Verifier returned no valid JSON")
            data = {}

        try:
            raw_conf = float(data.get("confidence", 0.35))
            
            # Incorporate credibility and coverage into confidence
            if coverage and evidence:
                cred_avg = sum(getattr(e, "credibility_score", 0.7) for e in evidence) / max(len(evidence), 1)
                ent_cov = coverage.get("entity_coverage", 1.0)
                attr_cov = coverage.get("attribute_coverage", 1.0)
                # Weighted confidence: 30% model judgment, 25% source credibility, 25% entity coverage, 20% attribute coverage
                confidence = round((0.30 * raw_conf) + (0.25 * cred_avg) + (0.25 * ent_cov) + (0.20 * attr_cov), 2)
            else:
                confidence = raw_conf

            sufficient = (
                bool(data.get("sufficient", False))
                and confidence >= min_confidence
            )

            missing_info = list(data.get("missing_information", []))
            unsupported = list(data.get("unsupported_claims", []))

            if coverage:
                for me in coverage.get("missing_entities", []):
                    missing_info.append(f"No retrieved evidence for entity: {me}")
                for ma in coverage.get("missing_attributes", []):
                    missing_info.append(f"No retrieved evidence for attribute: {ma}")

            return VerificationResult(
                sufficient=sufficient,
                confidence=confidence,
                supported_claims=list(data.get("supported_claims", [])),
                unsupported_claims=unsupported,
                conflicts=list(data.get("conflicts", [])),
                missing_information=missing_info,
                reasoning=str(data.get("reasoning", "Evidence and coverage assessment completed.")),
            )
        except Exception as exc:
            logger.warning("Verifier JSON parse failed: %s", exc)
            return VerificationResult(
                sufficient=False,
                confidence=0.3,
                reasoning=f"Parse error: {exc}",
            )

    @staticmethod
    def _extract_json_dict(text: str) -> dict:
        if not text:
            return {}
        text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
        text = re.sub(r"```(?:json)?\s*([\s\S]*?)\s*```", r"\1", text).strip()
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            snippet = text[start : end + 1]
            try:
                data = json.loads(snippet)
                if isinstance(data, dict):
                    return data
            except Exception:
                cleaned = re.sub(r",\s*([\}\]])", r"\1", snippet)
                try:
                    data = json.loads(cleaned)
                    if isinstance(data, dict):
                        return data
                except Exception:
                    pass
        return {}
