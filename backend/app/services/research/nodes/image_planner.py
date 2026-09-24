"""
ImagePlanner Node for Deep Research 2.0.

Evaluates whether visuals (diagrams, timelines, architectures, charts) materially
improve comprehension. Strictly bounds generation to maximum 3 images and rejects
superficial or decorative images.

Strategy:
  1. FAST PATH — Deterministic keyword matcher checks the query.
     If the topic clearly involves architecture/pipeline/comparison → generate images
     immediately without any LLM call (avoids Groq TPM limits, latency, and failures).
  2. SLOW PATH — For ambiguous topics, ask the LLM to decide.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from app.core.config import get_settings
from app.core.enums import ConversationMode, MessageRole
from app.providers.base import NormalizedMessage
from app.services.chat.router import ModelRouter
from app.services.research.models import ImageItem, ImagePlan
from app.services.research.router import ResearchTaskType, select_research_model

logger = logging.getLogger(__name__)

_IMAGE_PLAN_SYSTEM = """You are a senior technical illustrator and research visual strategist.
Determine whether the research topic would materially benefit from 1 to 3 informative visual diagrams.

CRITERIA FOR GENERATING IMAGES:
- GOOD: System architecture, multi-stage pipeline, comparative workflow, timeline of milestones, or technical hardware schema.
- REJECT: Pure prose, simple facts, basic explanations, decorative portraits, generic stock illustrations.

If images DO NOT materially help the reader understand the technical substance, set "should_generate": false and "images": [].
Maximum 3 images allowed.

Respond ONLY with valid JSON:
{{
  "should_generate": true | false,
  "images": [
    {{
      "purpose": "Clear explanation of what the diagram shows",
      "placement": "After section ## Detailed Analysis or relevant subheading",
      "prompt": "Highly detailed visual prompt describing the technical schema, clean vector styling, high contrast, elegant dark mode palette"
    }}
  ]
}}"""

_JSON_EXTRACT = re.compile(r"\{[\s\S]*\}", re.DOTALL)

# ── Deterministic fast-path ────────────────────────────────────────────────────
# Keywords that strongly signal a technical topic benefiting from diagrams.
_TECHNICAL_KEYWORDS = re.compile(
    r"\b("
    r"architecture|pipeline|workflow|system|framework|model|network|infrastructure|"
    r"training|optimization|algorithm|diagram|schema|topology|hierarchy|stack|layer|"
    r"comparison|benchmark|versus|vs\.?|versus|contrast|analysis|circuit|hardware|"
    r"transformer|attention|mixture|expert|moe|reinforcement|rl|grpo|ppo|sft|"
    r"deep[- ]?seek|openai|gpt|llm|ai|neural|inference|deployment|kubernetes|"
    r"docker|microservice|api|database|cloud|distributed|parallel|cluster|"
    r"encoder|decoder|embedding|token|latent|diffusion|autoregressive|generation"
    r")\b",
    re.IGNORECASE,
)


def _deterministic_image_plan(query: str) -> Optional[ImagePlan]:
    """
    Fast-path: if query clearly signals a technical/architecture topic,
    generate 2 targeted diagrams without any LLM call.
    Returns None if topic is ambiguous and should fall through to LLM path.
    """
    q = query.strip()
    matches = _TECHNICAL_KEYWORDS.findall(q)

    # Need at least 2 distinct technical signals
    unique = {m.lower() for m in matches}
    if len(unique) < 2:
        return None

    # Build targeted prompts based on detected topic signals
    q_lower = q.lower()

    # Architecture comparison (e.g. DeepSeek vs OpenAI, model comparisons)
    is_comparison = bool(re.search(r"\b(vs\.?|versus|compare|comparison|contrast|between)\b", q_lower))
    is_ai_model = bool(re.search(r"\b(llm|model|transformer|gpt|deepseek|openai|gemini|claude|mistral|qwen|llama)\b", q_lower))
    is_training = bool(re.search(r"\b(training|finetun|rl|reinforcement|grpo|ppo|sft|reward|optimization)\b", q_lower))
    is_system = bool(re.search(r"\b(architecture|system|pipeline|infrastructure|framework|stack|layer|topology)\b", q_lower))
    is_cloud = bool(re.search(r"\b(kubernetes|docker|k8s|aws|azure|gcp|cloud|microservice|cluster|pod|node)\b", q_lower))
    is_space = bool(re.search(r"\b(rocket|satellite|spacecraft|engine|propulsion|orbit|stage|separation|starship)\b", q_lower))

    images: list[ImageItem] = []

    if is_ai_model and is_comparison:
        images.append(ImageItem(
            purpose="Side-by-side system architecture comparison showing model topology, parameter scale, and inference pipeline differences",
            placement="After ## Detailed Analysis > System Architecture",
            prompt=f"Technical side-by-side system architecture diagram for: {q}. Two vertical panels. Clean vector dark mode, graphite background #0D0D0F, gold accent lines #D4AF37, labeled components, parameter counts, data flow arrows, modern sans-serif typography, ultra high contrast, minimal decorative elements",
        ))
        if is_training:
            images.append(ImageItem(
                purpose="Multi-stage training workflow and optimization pipeline comparison",
                placement="After ## Training Algorithms and Workflow",
                prompt=f"Multi-stage training pipeline workflow diagram for: {q}. Horizontal swimlane flowchart. Stages: SFT → RL → GRPO/PPO → Evaluation. Dark background #0D0D0F, gold nodes #D4AF37, teal arrows, crisp monospace labels, technical schematic aesthetic, ultra clean",
            ))
        if is_comparison:
            images.append(ImageItem(
                purpose="Benchmark performance comparison chart showing relative scores across key evaluation metrics",
                placement="After ## Key Findings",
                prompt=f"Benchmark performance radar/spider chart comparing models for: {q}. Dark mode, gold fill #D4AF37 for model A, teal fill for model B, labeled axes: AIME, MATH-500, MMLU, GPQA-Diamond, Coding. Clean vector, minimal grid lines, professional data visualization aesthetic",
            ))
    elif is_system or is_cloud:
        images.append(ImageItem(
            purpose="System architecture topology diagram showing component relationships and data flow",
            placement="After ## Detailed Analysis",
            prompt=f"System architecture topology diagram for: {q}. Node-link diagram with labeled components. Dark background #0D0D0F, gold accent #D4AF37, directional arrows, service boxes with rounded corners, clean technical schematic, high contrast labels",
        ))
        images.append(ImageItem(
            purpose="Operational workflow and pipeline execution sequence",
            placement="After ## System Architecture",
            prompt=f"Operational pipeline sequence diagram for: {q}. Left-to-right swimlane flow. Dark background, colored stage boxes, dashed dependency lines, clean monospace labels, technical documentation style",
        ))
    elif is_space:
        images.append(ImageItem(
            purpose="Technical cross-section and stage separation sequence diagram",
            placement="After ## Detailed Analysis",
            prompt=f"Detailed technical cross-section diagram for: {q}. Engineering blueprint style, dark background, gold accent highlights, labeled components with dimension callouts, side and front view panels, aerospace technical illustration",
        ))
    elif is_training:
        images.append(ImageItem(
            purpose="Reinforcement learning training pipeline and reward optimization workflow",
            placement="After ## Training Algorithms",
            prompt=f"RL training pipeline diagram for: {q}. Circular policy-reward feedback loop with labeled stages: Policy Model, Reward Model, Rollout, Advantage Estimation, Policy Update. Dark background #0D0D0F, teal nodes, gold arrows, clean vector schematic",
        ))
    else:
        # Generic technical topic
        images.append(ImageItem(
            purpose="Technical architecture and system overview diagram",
            placement="After ## Detailed Analysis",
            prompt=f"Technical architecture overview diagram for: {q}. Clean dark mode schematic, labeled components, directional data flow arrows, gold accent color #D4AF37, graphite background, professional technical illustration",
        ))

    return ImagePlan(should_generate=True, images=images[:3])


class ImagePlanner:
    """Plans optional, high-value technical visuals for research reports."""

    def __init__(
        self,
        router: Optional[ModelRouter] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.router = router or ModelRouter.from_settings()
        self.provider = provider
        self.model = model
        self.max_images = getattr(get_settings(), "deep_research_max_images", 3)

    async def plan_images(
        self,
        query: str,
        report_summary: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> ImagePlan:
        """Analyze research topic and decide if technical diagrams are warranted."""

        # ── Fast path: deterministic keyword matching ──────────────────────────
        fast_plan = _deterministic_image_plan(query)
        if fast_plan and fast_plan.should_generate:
            logger.info(
                "[IMAGE_PLANNER] Fast-path: generating %d diagrams for %r",
                len(fast_plan.images),
                query[:60],
            )
            return fast_plan

        # ── Slow path: LLM-based decision ────────────────────────────────────
        decision = select_research_model(
            ResearchTaskType.IMAGE_PLANNING,
            self.router,
            explicit_provider=provider or self.provider,
            explicit_model=model or self.model,
        )

        messages = [
            NormalizedMessage(role=MessageRole.SYSTEM, content=_IMAGE_PLAN_SYSTEM),
            NormalizedMessage(
                role=MessageRole.USER,
                content=f"Research topic: {query}\n\nSummary of findings:\n{report_summary[:1000]}",
            ),
        ]

        chunks: list[str] = []
        try:
            async for _sel, event in self.router.stream(
                messages=messages,
                mode=ConversationMode.DEEP_RESEARCH,
                provider=decision.provider,
                model=decision.model,
                max_tokens=600,
            ):
                if event.delta:
                    chunks.append(event.delta)
        except Exception as exc:
            logger.warning("[IMAGE_PLANNER] Streaming failed: %s; skipping visuals", exc)
            return ImagePlan(should_generate=False, images=[])

        raw = "".join(chunks)
        raw = re.sub(r"<think>[\s\S]*?</think>", "", raw).strip()
        raw = re.sub(r"```(?:json)?\s*([\s\S]*?)\s*```", r"\1", raw).strip()

        try:
            match = _JSON_EXTRACT.search(raw)
            data = json.loads(match.group(0)) if match else {}
            should_gen = bool(data.get("should_generate", False))
            raw_items = data.get("images", []) if should_gen else []
            items: list[ImageItem] = []
            for it in raw_items[: self.max_images]:
                if isinstance(it, dict) and it.get("prompt"):
                    items.append(
                        ImageItem(
                            purpose=str(it.get("purpose", "Technical Diagram")),
                            placement=str(it.get("placement", "Contextual")),
                            prompt=str(it.get("prompt")),
                        )
                    )
            return ImagePlan(should_generate=bool(items), images=items)
        except Exception as exc:
            logger.warning("[IMAGE_PLANNER] Failed parsing plan: %s", exc)
            return ImagePlan(should_generate=False, images=[])
