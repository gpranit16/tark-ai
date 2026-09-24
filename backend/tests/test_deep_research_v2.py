import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.config import get_settings
from app.providers.base import ProviderName
from app.services.research.models import (
    Citation,
    Evidence,
    EvidenceSource,
    ImagePlan,
    ImageItem,
    ResearchQuery,
    ResearchRouterResult,
    SectionResult,
    SectionTask,
)
from app.services.research.router import ResearchTaskType, select_research_model
from app.services.research.tavily import TavilyResearchService
from app.services.research.nodes.router_node import ResearchRouter
from app.services.research.nodes.verifier import VerifierAgent
from app.services.research.nodes.image_planner import ImagePlanner
from app.services.research.pollinations import PollinationsImageProvider
from app.services.research.graph import DeepResearchGraph


class TestDeepResearchV2ModelSelection:
    def test_heavy_task_selects_gemini_35_flash_lite(self):
        settings = get_settings()
        with patch.object(settings, "gemini_api_key", "fake-key"), \
             patch.object(settings, "deep_research_gemini_model", "gemini-3.5-flash-lite"):
            for heavy_task in (
                ResearchTaskType.RESEARCH_PLANNING,
                ResearchTaskType.SECTION_WORKER,
                ResearchTaskType.SYNTHESIS,
            ):
                decision = select_research_model(heavy_task, settings=settings)
                assert decision.model == "gemini-3.5-flash-lite"
                assert "2.5" not in decision.model

    def test_fast_task_selects_groq_when_available(self):
        settings = get_settings()
        with patch.object(settings, "groq_api_key", "fake-groq-key"), \
             patch.object(settings, "fast_provider", "groq"), \
             patch.object(settings, "gemini_api_key", "fake-gemini-key"):
            for fast_task in (ResearchTaskType.CLASSIFICATION, ResearchTaskType.IMAGE_PLANNING):
                decision = select_research_model(fast_task, settings=settings)
                assert decision.provider == ProviderName.GROQ
                assert decision.model is not None and len(decision.model) > 0

    def test_gemini_never_uses_25_flash_or_pro(self):
        settings = get_settings()
        with patch.object(settings, "gemini_api_key", "fake-gemini-key"):
            for task in ResearchTaskType:
                decision = select_research_model(task, settings=settings)
                if decision.provider == ProviderName.GEMINI:
                    assert decision.model == "gemini-3.5-flash-lite"
                    assert "2.5" not in decision.model

    def test_synthesis_does_not_get_overridden_by_chat_ui_default_model(self):
        settings = get_settings()
        with patch.object(settings, "gemini_api_key", "fake-gemini-key"), \
             patch.object(settings, "deep_research_gemini_model", "gemini-3.5-flash-lite"):
            decision = select_research_model(
                ResearchTaskType.SYNTHESIS,
                explicit_provider="groq",
                explicit_model="qwen/qwen3.8-27b",
                settings=settings,
            )
            assert decision.provider == "gemini"
            assert decision.model == "gemini-3.5-flash-lite"


class TestDeepResearchV2TavilyAndEvidence:
    def test_canonical_url_normalization(self):
        service = TavilyResearchService()
        raw_url = "HTTPS://WWW.Example.com/Docs/API/?utm_source=twitter&utm_medium=cpc#overview"
        normalized = service.canonicalize_url(raw_url)
        assert normalized == "https://example.com/docs/api"
        assert "utm_" not in normalized
        assert "#" not in normalized

    def test_domain_authority_scoring(self):
        service = TavilyResearchService()
        score1, is_off1 = service.score_source_credibility("https://docs.python.org/3/tutorial", "Python Tutorial", "Documentation")
        assert score1 >= 0.90
        score2, is_off2 = service.score_source_credibility("https://github.com/astral-sh/uv", "uv on GitHub", "Repo")
        assert score2 >= 0.90
        score3, is_off3 = service.score_source_credibility("https://techcrunch.com/2026/news", "TechCrunch", "Article")
        assert score3 >= 0.80
        score4, is_off4 = service.score_source_credibility("https://random-scraper-aggregator.xyz/page", "Scraper", "Content")
        assert score4 <= 0.70

    @pytest.mark.asyncio
    async def test_tavily_parallel_search_mocked(self):
        service = TavilyResearchService(api_key="fake-key")
        queries = [
            ResearchQuery(query="Agentic AI benchmarks 2026", angle="benchmarks", priority=1),
            ResearchQuery(query="Agentic AI architecture", angle="architecture", priority=2),
        ]

        fake_evidence = [
            Evidence(
                source_type=EvidenceSource.WEB,
                title="Agentic AI Benchmark Paper",
                url="https://arxiv.org/abs/2601.12345",
                snippet="Paper detailing agent benchmarks across 10 tasks.",
                reliability=0.95,
            )
        ]

        with patch.object(service, "search_single_query", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = fake_evidence
            evidence = await service.search_queries(queries)
            assert len(evidence) == 2
            assert evidence[0].title == "Agentic AI Benchmark Paper"


class TestDeepResearchV2DeterministicCitationValidation:
    def test_validates_grounded_and_strips_hallucinated(self):
        evidence = [
            Evidence(
                task_id="t1",
                source_type=EvidenceSource.WEB,
                title="LangGraph Overview",
                url="https://docs.langchain.com/langgraph",
                snippet="LangGraph coordinates cyclical agent state machines.",
            ),
            Evidence(
                task_id="t2",
                source_type=EvidenceSource.WEB,
                title="Tavily API",
                url="https://tavily.com",
                snippet="Search API designed for AI agents.",
            ),
        ]

        report_with_hallucinations = (
            "LangGraph enables agent state machines [1]. "
            "Tavily provides grounded web retrieval [2]. "
            "Fabricated claim with fake citation [99] and [5]."
        )

        cleaned_text, citations, coverage, rejected = (
            VerifierAgent.validate_citations_deterministically(
                evidence=evidence,
                content=report_with_hallucinations,
                candidate_citations=[],
            )
        )

        # Citations [1] and [2] are preserved
        assert "[1]" in cleaned_text
        assert "[2]" in cleaned_text
        # Hallucinated citations [99] and [5] are deterministically stripped
        assert "[99]" not in cleaned_text
        assert "[5]" not in cleaned_text
        assert len(citations) == 2
        assert citations[0]["url"] == "https://docs.langchain.com/langgraph"
        assert citations[1]["url"] == "https://tavily.com"
        assert coverage >= 0.5


class TestDeepResearchV2ImagePlanningAndPollinations:
    def test_pollinations_url_construction(self):
        provider = PollinationsImageProvider()
        url = provider.build_url("Agentic workflow diagram high tech", "16:9")
        assert "image.pollinations.ai/prompt/" in url
        assert "width=1280" in url
        assert "height=720" in url
        assert "diagram" in url.lower() or "workflow" in url.lower()

    @pytest.mark.asyncio
    async def test_image_planner_caps_at_3(self):
        mock_router = MagicMock()
        planner = ImagePlanner(mock_router)

        plan = ImagePlan(
            should_generate=True,
            images=[
                ImageItem(purpose="arch", placement="sec1", prompt="Diagram 1", caption="Workflow 1"),
                ImageItem(purpose="arch", placement="sec2", prompt="Diagram 2", caption="Workflow 2"),
                ImageItem(purpose="arch", placement="sec3", prompt="Diagram 3", caption="Workflow 3"),
                ImageItem(purpose="arch", placement="sec4", prompt="Diagram 4", caption="Workflow 4"),
            ],
        )

        async def fake_plan_stream(*args, **kwargs):
            from app.providers.base import ProviderStreamEvent
            yield None, ProviderStreamEvent(delta=plan.model_dump_json())

        mock_router.stream.side_effect = fake_plan_stream

        result = await planner.plan_images("Topic", "Section text", [])
        # Strict enforcement: maximum 3 images
        assert len(result.images) <= 3


class TestDeepResearchV2GraphCompilation:
    def test_graph_structure(self):
        mock_router = MagicMock()
        graph = DeepResearchGraph(mock_router)
        compiled = graph.build()
        assert compiled is not None

        nodes = compiled.nodes
        assert "plan_research" in nodes
        assert "research" in nodes
        assert "verify_evidence" in nodes
        assert "plan_sections" in nodes
        assert "fanout_sections" in nodes
        assert "synthesize" in nodes
        assert "images" in nodes
