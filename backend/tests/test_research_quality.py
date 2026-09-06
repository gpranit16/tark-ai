"""
Automated tests for Deep Research Quality Layer & Grounding Hardening.

Covers:
- Unsupported claim rejection
- Official / primary source preference and domain credibility ranking
- Source count accuracy and deduplication
- Citation-to-evidence validation and hallucinated citation stripping
- "Not verified" fallback for missing or ungrounded aspects
"""
from __future__ import annotations

import pytest
from uuid import uuid4

from app.services.research.models import Evidence, EvidenceSource, VerificationResult, Citation
from app.services.research.nodes.web_agent import WebResearchAgent
from app.services.research.nodes.verifier import VerifierAgent
from app.services.research.nodes.synthesizer import ResearchSynthesizer
from app.services.research.graph import DeepResearchGraph


class TestSourceCredibilityAndOfficialPreference:
    """Test source credibility scoring and official domain preference."""

    def test_official_domain_detection(self):
        """Official vendor domains must receive high credibility score >= 0.90 and is_official=True."""
        official_urls = [
            "https://docs.anthropic.com/claude/reference/claude-3-7-sonnet",
            "https://cursor.com/features",
            "https://docs.cursor.com/context/rules-for-ai",
            "https://github.com/anthropics/anthropic-sdk-python",
            "https://openai.com/index/introducing-canvas/",
            "https://arxiv.org/abs/2401.00001",
        ]
        for url in official_urls:
            score, is_official = WebResearchAgent._score_source_credibility(
                url=url, title="Official Docs", snippet="Official product capabilities"
            )
            assert is_official is True, f"Expected is_official=True for {url}"
            assert score >= 0.90, f"Expected score >= 0.90 for {url}, got {score}"

    def test_reputable_tech_media_scoring(self):
        """Reputable tech media receives high credibility >= 0.80 but is_official=False."""
        media_urls = [
            "https://techcrunch.com/2026/01/15/ai-coding-agents-breakdown/",
            "https://www.reuters.com/technology/ai-software-agents-2026/",
            "https://news.ycombinator.com/item?id=123456",
        ]
        for url in media_urls:
            score, is_official = WebResearchAgent._score_source_credibility(
                url=url, title="TechCrunch Report", snippet="Analysis of coding tools"
            )
            assert is_official is False
            assert score >= 0.80

    def test_low_quality_scraper_domain_penalization(self):
        """Scraper and content-farm domains must receive low credibility <= 0.50."""
        scraper_urls = [
            "https://spammy-site.blogspot.com/2026/01/best-ai-tools.html",
            "https://myblog.wordpress.com/ai-coding-cheap-tricks/",
            "https://contentfarm.com/article/ai-tools-list",
        ]
        for url in scraper_urls:
            score, is_official = WebResearchAgent._score_source_credibility(
                url=url, title="Generic Blog", snippet="SEO text"
            )
            assert is_official is False
            assert score <= 0.50


class TestSourceCountAccuracyAndDeduplication:
    """Test that source counts reflect actual unique usable sources without inflation."""

    def test_evidence_deduplication_by_canonical_url(self):
        """Duplicate URLs with different query params or fragments must be collapsed to 1."""
        raw_evidence = [
            Evidence(
                source_id="1",
                title="Cursor IDE Official",
                url="https://cursor.com/features?ref=producthunt",
                domain="cursor.com",
                snippet="AI powered code editor",
                content="Full features of Cursor",
                credibility_score=0.95,
                is_official=True,
            ),
            Evidence(
                source_id="2",
                title="Cursor Features",
                url="https://cursor.com/features?utm_source=twitter#pricing",
                domain="cursor.com",
                snippet="AI powered code editor features",
                content="Full features of Cursor",
                credibility_score=0.95,
                is_official=True,
            ),
            Evidence(
                source_id="3",
                title="Claude 3.7 Documentation",
                url="https://docs.anthropic.com/claude/3-7",
                domain="docs.anthropic.com",
                snippet="Claude 3.7 Sonnet capabilities",
                content="Claude 3.7 hybrid reasoning",
                credibility_score=0.95,
                is_official=True,
            ),
        ]
        deduped = DeepResearchGraph._deduplicate_evidence(raw_evidence)
        assert len(deduped) == 2
        urls = [e.url for e in deduped]
        assert "https://docs.anthropic.com/claude/3-7" in urls

    def test_evidence_deduplication_by_title_and_domain(self):
        """Identical titles from the same domain without URLs must be deduplicated."""
        raw_evidence = [
            Evidence(
                source_id="1",
                title="Financial Analysis Report 2026",
                domain="sec.gov",
                snippet="Revenue growth report",
            ),
            Evidence(
                source_id="2",
                title="Financial Analysis Report 2026",
                domain="sec.gov",
                snippet="Revenue growth report duplicate",
            ),
        ]
        deduped = DeepResearchGraph._deduplicate_evidence(raw_evidence)
        assert len(deduped) == 1


class TestCitationValidationAndHallucinationStripping:
    """Test claim-to-evidence citation mapping and hallucination filtering."""

    def test_hallucinated_citation_index_removal(self):
        """If synthesizer outputs [99] when only [1] and [2] exist, [99] must be stripped."""
        synthesizer = ResearchSynthesizer()
        source_index = {
            1: Evidence(
                source_id="1",
                title="Claude 3.7 Sonnet",
                url="https://anthropic.com/news/claude-3-7-sonnet",
                domain="anthropic.com",
                snippet="Claude 3.7 Sonnet features hybrid reasoning.",
                is_official=True,
            ),
            2: Evidence(
                source_id="2",
                title="Cursor AI",
                url="https://cursor.com",
                domain="cursor.com",
                snippet="Cursor provides agentic background execution.",
                is_official=True,
            ),
        }
        raw_text = (
            "Claude 3.7 provides hybrid reasoning [1]. Cursor supports agentic workflows [2]. "
            "Devin was acquired by Microsoft for 10 billion dollars [99]."
        )
        cleaned_text, citations = synthesizer._validate_and_build_citations(raw_text, source_index)

        # [99] must not be in the cleaned text
        assert "[99]" not in cleaned_text
        assert "[1]" in cleaned_text
        assert "[2]" in cleaned_text

        # Citations list must have exactly 2 valid citation objects
        assert len(citations) == 2
        assert citations[0].title == "Claude 3.7 Sonnet"
        assert citations[0].domain == "anthropic.com"
        assert citations[1].title == "Cursor AI"
        assert citations[1].domain == "cursor.com"


class TestUnsupportedClaimRejectionAndNotVerified:
    """Test that missing or unsupported facts are flagged as unsupported / not verified."""

    def test_verifier_flags_unsupported_speculations(self):
        """VerifierResult correctly identifies unsupported speculative claims in its fields."""
        res = VerificationResult(
            sufficient=False,
            confidence=0.45,
            supported_claims=["Claude 3.7 supports hybrid reasoning", "Cursor supports agentic edits"],
            unsupported_claims=["Devin was acquired by Microsoft", "Pricing is $5/month"],
            missing_information=["Official 2026 pricing details", "Autonomous benchmark evaluations"],
            reasoning="Pricing and acquisition claims are not backed by any retrieved evidence.",
        )
        assert not res.sufficient
        assert "Devin was acquired by Microsoft" in res.unsupported_claims
        assert "Official 2026 pricing details" in res.missing_information

    def test_synthesizer_evidence_formatting_includes_official_and_domain_tags(self):
        """Evidence formatted for LLM synthesizer explicitly marks official sources and domains."""
        synthesizer = ResearchSynthesizer()
        evidence = [
            Evidence(
                source_id="1",
                title="Claude 3.7 Docs",
                url="https://docs.anthropic.com/claude",
                domain="docs.anthropic.com",
                snippet="Hybrid reasoning models",
                is_official=True,
                credibility_score=0.95,
            ),
            Evidence(
                source_id="2",
                title="Tech Blog",
                url="https://blog.example.com/post",
                domain="blog.example.com",
                snippet="Opinion piece",
                is_official=False,
                credibility_score=0.60,
            ),
        ]
        formatted, source_idx = synthesizer._format_evidence_for_synthesis(evidence)
        assert "[1] [Official/Primary]" in formatted
        assert "(Domain: docs.anthropic.com)" in formatted
        assert "[2]" in formatted
        assert "(Domain: blog.example.com)" in formatted
        assert 1 in source_idx and 2 in source_idx


class TestTruncationAndContinuation:
    """Test truncation detection, continuation prompting, and clean merge without duplication."""

    def test_truncation_detection_on_finish_reason_length(self):
        """If finish_reason is length or max_tokens, truncation must be detected."""
        text = "## Executive Summary\nCursor is an AI code editor that offers several features for developers." * 5
        assert ResearchSynthesizer._is_truncated(text, finish_reason="length") is True
        assert ResearchSynthesizer._is_truncated(text, finish_reason="max_tokens") is True
        assert ResearchSynthesizer._is_truncated(text, finish_reason="stop") is False

    def test_truncation_detection_on_dangling_tail(self):
        """Text ending in dangling prepositions/connectors or unclosed code fences must be detected as truncated."""
        dangling_text = (
            "## Key Findings\n"
            "* Claude 3.7 provides hybrid reasoning [1].\n"
            "* Cursor provides background agentic execution and"
        )
        assert ResearchSynthesizer._is_truncated(dangling_text, finish_reason="stop") is True

        unclosed_code_text = (
            "## Key Findings\n"
            "* Here is the architecture configuration:\n"
            "```python\n"
            "def agent():\n"
            "    return True\n"
        )
        assert ResearchSynthesizer._is_truncated(unclosed_code_text, finish_reason="stop") is True

    def test_continuation_clean_merge_no_duplicate(self):
        """Continuation merge must cleanly join text and deduplicate small overlapping words."""
        part1 = "## Key Findings\n* Cursor provides agentic background execution with full workspace context"
        part2 = "workspace context [1].\n* Windsurf introduces Cascade flows [2].\n\n## Limitations & Caveats\nNone."
        merged = ResearchSynthesizer._merge_continuation(part1, part2)
        assert "workspace context workspace context" not in merged
        assert "Windsurf introduces Cascade flows [2]" in merged
        assert "## Limitations & Caveats" in merged

    def test_complete_report_not_detected_as_truncated(self):
        """A complete markdown report ending with Sources and punctuation must not be flagged as truncated."""
        complete_report = (
            "## Executive Summary\nAI coding agents have matured.\n\n"
            "## Key Findings\n* Cursor supports agentic workflows [1].\n\n"
            "## Detailed Analysis\nCursor and Claude Code provide robust developer tooling [1, 2].\n\n"
            "## Limitations & Caveats\nPricing for enterprise tiers is not verified.\n\n"
            "## Sources\n- [1] Cursor (cursor.com)\n- [2] Anthropic (anthropic.com)"
        )
        assert ResearchSynthesizer._is_truncated(complete_report, finish_reason="stop") is False


class TestMultiPageSameDomainPreservation:
    """Test that distinct pages from the same domain are preserved."""

    def test_same_domain_different_pages_preserved(self):
        """Distinct URLs on cursor.com must all be preserved."""
        raw_evidence = [
            Evidence(
                source_id="1",
                title="Cursor Features",
                url="https://cursor.com/features",
                domain="cursor.com",
                snippet="Features overview",
            ),
            Evidence(
                source_id="2",
                title="Cursor Pricing",
                url="https://cursor.com/pricing",
                domain="cursor.com",
                snippet="Pricing tiers",
            ),
            Evidence(
                source_id="3",
                title="Cursor Rules",
                url="https://docs.cursor.com/rules",
                domain="docs.cursor.com",
                snippet="System rules for AI",
            ),
        ]
        deduped = DeepResearchGraph._deduplicate_evidence(raw_evidence)
        assert len(deduped) == 3
        urls = {e.url for e in deduped}
        assert "https://cursor.com/features" in urls
        assert "https://cursor.com/pricing" in urls
        assert "https://docs.cursor.com/rules" in urls


class TestCoverageAndConfidenceAssessment:
    """Test entity coverage, attribute coverage, and weighted confidence calculations."""

    def test_entity_and_attribute_coverage_calculation(self):
        """Test coverage extraction on multi-entity comparison query."""
        query = (
            "Compare Cursor, Claude Code, Windsurf, GitHub Copilot, and Devin in 2026 "
            "in terms of pricing, architecture, and autonomy level."
        )
        evidence = [
            Evidence(
                source_id="1",
                title="Cursor Pricing & Architecture",
                snippet="Cursor pricing is $20/mo and uses a custom VS Code fork architecture.",
                credibility_score=0.95,
            ),
            Evidence(
                source_id="2",
                title="Claude Code Autonomy",
                snippet="Claude Code runs in terminal with high autonomy level.",
                credibility_score=0.90,
            ),
        ]
        coverage = VerifierAgent.analyze_coverage(query, evidence)
        assert coverage["entity_coverage"] > 0.0
        assert "cursor" in coverage["covered_entities"]
        assert "windsurf" in coverage["missing_entities"]
        assert "pricing" in coverage["covered_attributes"]

    def test_low_coverage_reduces_confidence(self):
        """When major requested entities are missing from evidence, confidence must be adjusted down."""
        verifier = VerifierAgent()
        query = "Compare Cursor, Devin, Windsurf, and Copilot on pricing and enterprise features."
        evidence = [
            Evidence(
                source_id="1",
                title="Cursor Info",
                snippet="Cursor is a code editor.",
                credibility_score=0.70,
            )
        ]
        res = verifier._parse_result(
            '{"sufficient": true, "confidence": 0.9}',
            min_confidence=0.50,
            coverage=VerifierAgent.analyze_coverage(query, evidence),
            evidence=evidence,
        )
        # Should NOT be blindly 0.90 because 3/4 entities and attributes are missing
        assert res.confidence < 0.70
        assert len(res.missing_information) > 0

