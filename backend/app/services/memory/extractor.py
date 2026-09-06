import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Optional

from app.core.config import get_settings
from app.core.enums import MemoryCategory
from app.schemas.memory import MemoryCandidate, MemoryExtractionResult


class ExplicitIntent(StrEnum):
    NONE = "none"
    REMEMBER = "remember"
    FORGET = "forget"
    QUERY = "query"
    FORGET_ALL = "forget_all"


@dataclass
class ExplicitMemoryCommand:
    intent: ExplicitIntent
    raw_query: str
    target_subject: str | None = None
    extracted_candidate: MemoryCandidate | None = None


class MemoryExtractor:
    """Extracts personalization-relevant memory candidates from user messages.

    Filters out conversational fluff, generic knowledge queries, temporary mood states,
    and sensitive secrets / credentials. Assigns category, key, value, confidence, and importance scores.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    # Secret and credential regexes that MUST NEVER be saved into memory
    _SECRET_PATTERNS = [
        r"\b(?:sk|pk|api[_-]?key|secret|token|ghp|gho|glpat|bearer)[_-]?[a-zA-Z0-9_\-\.]{16,}\b",
        r"\bAIza[0-9A-Za-z-_]{35}\b",
        r"\b(?:password|passwd|pwd)\s*[:=]\s*\S+",
        r"\bBearer\s+[a-zA-Z0-9_\-\.]{20,}\b",
        r"\b(?:\d{4}[ -]?){3}\d{4}\b",  # Credit cards
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    ]

    # Transient moods, daily plans, and fluff patterns to immediately reject
    _FLUFF_PATTERNS = [
        r"^(hi|hello|hey|greetings|good\s+(morning|afternoon|evening))\b",
        r"^(thanks|thank\s+you|thx|ty|ok|okay|k|cool|sure|great|got\s+it|understood|nice|yep|nope)\b",
        r"^(who\s+is|what\s+is|where\s+is|when\s+did|why\s+is|how\s+does)\s+(?!my|our|i\b).+",
        r"^(summarize|explain|describe|calculate|convert|translate|define|list)\b(?!.*(my|i\b|our\s+project|this\s+project))",
        r"^(tell\s+me\s+a\s+joke|write\s+a\s+poem|help|ping|test)$",
        # Transient physical/mood states (should not be durable long-term memories)
        r"\bi['’]?m\s+(tired|sleepy|bored|hungry|sick|exhausted|busy|sleepy)\s*(today|tonight|right now|now)?\b",
        r"\bi['’]?m\s+(going\s+out|heading\s+out|leaving|eating|having\s+dinner)\s*(tonight|today|now)?\b",
    ]

    # Preference patterns
    _PREFERENCE_PATTERNS = [
        # Concise / style preferences
        (
            r"\b(i\s+(prefer|like|want)\s+concise\s+(explanations?|answers?)|keep\s+(answers?|responses?|explanations?)\s+(short|concise|brief)|be\s+(concise|brief|short)|i\s+prefer\s+short\s+answers?|keep\s+answers?\s+short\s+from\s+now\s+on|from\s+now\s+on[,\s]+keep\s+answers?\s+(short|concise|brief))\b",
            MemoryCategory.PREFERENCE,
            "response_style",
            "Prefers concise explanations",
            0.95,
            0.85,
        ),
        (
            r"\b(i\s+(prefer|like|want)\s+detailed\s+answers?|give\s+(detailed|in-depth|thorough)\s+explanations?|be\s+detailed)\b",
            MemoryCategory.PREFERENCE,
            "response_style",
            "Prefers detailed and thorough explanations",
            0.95,
            0.85,
        ),
        # Explanation style preferences (e.g. with examples)
        (
            r"\b(from\s+now\s+on[,\s]+explain\s+code\s+with\s+examples?|explain\s+code\s+with\s+examples?\s+from\s+now\s+on|always\s+provide\s+code\s+examples?|explain\s+with\s+examples?)\b",
            MemoryCategory.PREFERENCE,
            "explanation_style",
            "Prefers code explanations with examples",
            0.95,
            0.85,
        ),
        # Language / technology preferences
        (
            r"\b(i\s+switched\s+from\s+java\s+to\s+python|switched\s+from\s+java\s+to\s+python)\b",
            MemoryCategory.PREFERENCE,
            "preferred_programming_language",
            "Prefers Python (switched from Java)",
            0.95,
            0.90,
        ),
        (
            r"\b(i\s+mostly\s+use\s+javascript\s+now|i\s+switched\s+to\s+javascript|i\s+prefer\s+javascript|use\s+javascript\s+now)\b",
            MemoryCategory.PREFERENCE,
            "preferred_programming_language",
            "Prefers JavaScript for programming",
            0.95,
            0.85,
        ),
        (
            r"\b(i\s+prefer\s+python|i\s+mostly\s+use\s+python|my\s+preferred\s+language\s+is\s+python|always\s+use\s+python)\b",
            MemoryCategory.PREFERENCE,
            "preferred_programming_language",
            "Prefers Python for programming",
            0.95,
            0.90,
        ),
        (
            r"\b(i\s+prefer\s+typescript|i\s+mostly\s+use\s+typescript|always\s+use\s+typescript)\b",
            MemoryCategory.PREFERENCE,
            "preferred_programming_language",
            "Prefers TypeScript for programming",
            0.95,
            0.85,
        ),
        (
            r"\bmy\s+preferred\s+(?:programming\s+)?language\s+is\s+([a-zA-Z+#]+)\b",
            MemoryCategory.PREFERENCE,
            "preferred_programming_language",
            "Prefers {0} for programming",
            0.95,
            0.90,
        ),
        # Generic preference extraction: "I prefer X", "I prefer to X"
        (
            r"\bi\s+prefer\s+([^.!?\n]+)",
            MemoryCategory.PREFERENCE,
            "user_preference",
            "Prefers {0}",
            0.90,
            0.80,
        ),
        (
            r"\bi\s+(always\s+)?(like|want|enjoy)\s+(to\s+have\s+|to\s+use\s+|to\s+see\s+)?([^.!?\n]+)",
            MemoryCategory.PREFERENCE,
            "user_preference",
            "Likes {0}",
            0.80,
            0.70,
        ),
    ]

    # Project context patterns
    _PROJECT_PATTERNS = [
        (
            r"\b(i['’]?m\s+building\s+tark\s+ai|we\s+are\s+building\s+tark\s+ai|building\s+tark\s+ai)\b",
            MemoryCategory.PROJECT_CONTEXT,
            "project_name",
            "Building TARK AI workspace",
            0.95,
            0.90,
        ),
        (
            r"\b(i\s+use\s+react\s+and\s+fastapi|my\s+project\s+uses\s+react\s+and\s+fastapi|stack\s+is\s+react\s+and\s+fastapi)\b",
            MemoryCategory.PROJECT_CONTEXT,
            "project_stack",
            "Project stack: React and FastAPI",
            0.95,
            0.90,
        ),
        (
            r"\b(backend\s+uses\s+fastapi|backend\s+is\s+built\s+with\s+fastapi|fastapi\s+backend|my\s+project\s+uses\s+fastapi)\b",
            MemoryCategory.PROJECT_CONTEXT,
            "backend_framework",
            "Backend uses FastAPI",
            0.95,
            0.85,
        ),
        (
            r"\b(frontend\s+uses\s+react|frontend\s+is\s+built\s+with\s+react|react\s+frontend|my\s+project\s+uses\s+react)\b",
            MemoryCategory.PROJECT_CONTEXT,
            "frontend_framework",
            "Frontend uses React",
            0.95,
            0.85,
        ),
        (
            r"\b(database\s+uses\s+postgresql\s*\+\s*pgvector|database\s+is\s+postgres(ql)?\s*\+\s*pgvector|postgres(ql)?\s+with\s+pgvector)\b",
            MemoryCategory.PROJECT_CONTEXT,
            "database_stack",
            "Database uses PostgreSQL + pgvector",
            0.95,
            0.85,
        ),
        (
            r"\b(this\s+project\s+is\s+|our\s+project\s+is\s+|the\s+project\s+stack\s+is\s+)([^.!?\n]+)",
            MemoryCategory.PROJECT_CONTEXT,
            "project_stack",
            "Project stack: {0}",
            0.85,
            0.80,
        ),
    ]

    # Goal patterns
    _GOAL_PATTERNS = [
        (
            r"\bi['’]?m\s+preparing\s+for\s+(ml\s+interviews?|machine\s+learning\s+interviews?)\b",
            MemoryCategory.GOAL,
            "interview_preparation",
            "Preparing for ML interviews",
            0.95,
            0.90,
        ),
        (
            r"\bi['’]?m\s+preparing\s+for\s+(placements?|interviews?|campus\s+placements?|coding\s+interviews?)\b",
            MemoryCategory.GOAL,
            "interview_preparation",
            "Preparing for {0}",
            0.95,
            0.90,
        ),
        (
            r"\b(my\s+goal\s+is\s+to\s+|i['’]?m\s+trying\s+to\s+|i\s+aim\s+to\s+|i\s+plan\s+to\s+)([^.!?\n]+)",
            MemoryCategory.GOAL,
            "user_goal",
            "Goal: {0}",
            0.90,
            0.85,
        ),
        (
            r"\bi['’]?m\s+building\s+([^.!?\n]+)",
            MemoryCategory.GOAL,
            "current_project",
            "Currently building {0}",
            0.90,
            0.85,
        ),
    ]

    # Skill & Learning patterns
    _SKILL_PATTERNS = [
        (
            r"\b(i['’]?m\s+learning\s+langchain|learning\s+langchain)\b",
            MemoryCategory.SKILL,
            "learning_topic",
            "Learning LangChain",
            0.95,
            0.80,
        ),
        (
            r"\bi['’]?m\s+learning\s+([^.!?\n]+)",
            MemoryCategory.SKILL,
            "learning_topic",
            "Learning {0}",
            0.90,
            0.80,
        ),
        (
            r"\bi\s+(know|have\s+experience\s+with|am\s+proficient\s+in|specialize\s+in)\s+([^.!?\n]+)",
            MemoryCategory.SKILL,
            "technical_skill",
            "Skilled in {0}",
            0.85,
            0.75,
        ),
    ]

    # Fact patterns (Personal identity & facts)
    _FACT_PATTERNS = [
        (
            r"\bmy\s+name\s+is\s+([A-Z][a-zA-Z\s]+?)(?:\.|\,|\band\b|$)",
            MemoryCategory.FACT,
            "name",
            "Name is {0}",
            0.95,
            0.95,
        ),
        (
            r"\bi\s+am\s+a\s+([^.!?\n]+(engineer|developer|architect|student|researcher|designer|manager|analyst))",
            MemoryCategory.FACT,
            "user_role",
            "Works as {0}",
            0.90,
            0.85,
        ),
        (
            r"\bi\s+(work\s+at|work\s+for)\s+([^.!?\n]+)",
            MemoryCategory.FACT,
            "user_employer",
            "Works at {0}",
            0.90,
            0.80,
        ),
        (
            r"\bi\s+(live\s+in|am\s+based\s+in|am\s+located\s+in)\s+([^.!?\n]+)",
            MemoryCategory.FACT,
            "user_location",
            "Located in {0}",
            0.90,
            0.75,
        ),
    ]

    # Recurring Interest patterns
    _INTEREST_PATTERNS = [
        (
            r"\bi\s+am\s+(really\s+|very\s+)?interested\s+in\s+([^.!?\n]+)",
            MemoryCategory.INTEREST,
            "user_interest",
            "Interested in {0}",
            0.85,
            0.75,
        ),
        (
            r"\bi\s+love\s+learning\s+about\s+([^.!?\n]+)",
            MemoryCategory.INTEREST,
            "user_interest",
            "Enjoys learning about {0}",
            0.85,
            0.75,
        ),
    ]

    def contains_secrets(self, text: str) -> bool:
        """Check if text contains credentials, passwords, or API keys."""
        for pattern in self._SECRET_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def detect_explicit_command(self, text: str) -> ExplicitMemoryCommand:
        """Analyze if text contains an explicit memory command (Remember, Forget, Query, Forget All)."""
        clean = text.strip()

        # 1. Forget All
        if re.search(r"\b(forget\s+everything(\s+you\s+know\s+about\s+me)?|clear\s+all\s+(my\s+)?memories|delete\s+all\s+(my\s+)?memories|don['’]?t\s+remember\s+this\s+conversation)\b", clean, re.IGNORECASE):
            return ExplicitMemoryCommand(intent=ExplicitIntent.FORGET_ALL, raw_query=clean)

        # 2. Query Memory
        if re.search(r"^(what\s+do\s+you\s+(remember|know)\s+about\s+me\??|show\s+me\s+what\s+you\s+remember\??|what\s+are\s+my\s+preferences\??|what\s+is\s+my\s+name\??|what\s+do\s+you\s+know\s+about\s+my\s+project\??|list\s+my\s+memories\??)$", clean, re.IGNORECASE):
            return ExplicitMemoryCommand(intent=ExplicitIntent.QUERY, raw_query=clean)

        # 3. Explicit Forget / Delete target memory
        forget_match = re.search(
            r"\b(forget\s+this|forget\s+my\s+([^.!?\n]+)|forget\s+that\s+([^.!?\n]+)|delete\s+that\s+memory|the\s+previous\s+preference\s+is\s+no\s+longer\s+valid|delete\s+memory\s+about\s+([^.!?\n]+)|remove\s+preference\s+for\s+([^.!?\n]+))\b",
            clean,
            re.IGNORECASE,
        )
        if forget_match:
            # Extract target subject if available
            groups = [g for g in forget_match.groups() if g]
            subject = groups[-1] if groups else None
            return ExplicitMemoryCommand(intent=ExplicitIntent.FORGET, raw_query=clean, target_subject=subject)

        # 4. Explicit Remember / Save permanently
        remember_match = re.search(
            r"\b(remember\s+this|save\s+this\s+permanently|don['’]?t\s+forget\s+this|please\s+remember\s+this|save\s+to\s+memory|remember\s+that\s+([^.!?\n]+))\b",
            clean,
            re.IGNORECASE,
        )
        if remember_match:
            # Attempt to extract candidate from the same text
            # Strip the explicit remember phrase to parse the fact
            text_without_cmd = re.sub(r"\b(remember\s+this|save\s+this\s+permanently|don['’]?t\s+forget\s+this|please\s+remember\s+this|save\s+to\s+memory|remember\s+that)\b[.,!?]?", "", clean, flags=re.IGNORECASE).strip()
            candidate = None
            if text_without_cmd:
                ext = self.extract(text_without_cmd)
                if ext.candidates:
                    candidate = ext.candidates[0]
                else:
                    # Fallback general remember candidate
                    candidate = MemoryCandidate(
                        category=MemoryCategory.PREFERENCE if any(w in text_without_cmd.lower() for w in ["prefer", "like", "want", "always", "never"]) else MemoryCategory.FACT,
                        key="user_note",
                        value=text_without_cmd,
                        confidence=1.0,
                        importance=0.9,
                        reasoning="Explicit user remember command",
                    )

            return ExplicitMemoryCommand(
                intent=ExplicitIntent.REMEMBER,
                raw_query=clean,
                target_subject=text_without_cmd or None,
                extracted_candidate=candidate,
            )

        return ExplicitMemoryCommand(intent=ExplicitIntent.NONE, raw_query=clean)

    def extract(self, text: str, is_rag_query: bool = False) -> MemoryExtractionResult:
        """Extract memory candidates from raw text.

        If `is_rag_query` is True (document question), document content must not
        become long-term memory.
        """
        if not text or not text.strip():
            return MemoryExtractionResult(skipped_reason="Empty text")

        clean_text = text.strip()

        # Privacy check: Reject secrets / credentials immediately
        if self.contains_secrets(clean_text):
            return MemoryExtractionResult(skipped_reason="Contains sensitive credentials or secrets")

        # If this is a document RAG search, ignore document-specific extractions
        if is_rag_query:
            if not any(keyword in clean_text.lower() for keyword in ["i prefer", "my goal", "i am", "i like", "i mostly use"]):
                return MemoryExtractionResult(skipped_reason="RAG document query without explicit user preference")

        # Check for conversational fluff / generic non-personal queries
        for fluff_pattern in self._FLUFF_PATTERNS:
            if re.search(fluff_pattern, clean_text, re.IGNORECASE):
                # Ensure it doesn't also contain an explicit personal statement
                if not any(k in clean_text.lower() for k in [
                    "i prefer", "i'm building", "i am building", "backend uses",
                    "frontend uses", "database uses", "i mostly use", "i'm learning",
                    "my name is", "i'm preparing", "i am preparing", "i switched from"
                ]):
                    return MemoryExtractionResult(skipped_reason="Conversational fluff or non-personal query")

        candidates: list[MemoryCandidate] = []

        all_pattern_groups = [
            self._PREFERENCE_PATTERNS,
            self._PROJECT_PATTERNS,
            self._GOAL_PATTERNS,
            self._SKILL_PATTERNS,
            self._FACT_PATTERNS,
            self._INTEREST_PATTERNS,
        ]

        for group in all_pattern_groups:
            for pattern_tuple in group:
                pattern, category, key, val_template, conf, imp = pattern_tuple
                match = re.search(pattern, clean_text, re.IGNORECASE)
                if match:
                    if "{0}" in val_template:
                        # Extract the captured group
                        groups = match.groups()
                        extracted_val = groups[-1].strip() if groups else match.group(0).strip()
                        # Clean trailing punctuation
                        extracted_val = re.sub(r"[.!?]+$", "", extracted_val).strip()
                        if not extracted_val or len(extracted_val) < 2:
                            continue
                        value = val_template.format(extracted_val)
                    else:
                        value = val_template

                    # Validate thresholds
                    if conf >= self.settings.memory_min_confidence and imp >= self.settings.memory_min_importance:
                        candidate = MemoryCandidate(
                            category=category,
                            key=key,
                            value=value,
                            confidence=conf,
                            importance=imp,
                            reasoning=f"Matched pattern '{pattern}' in text",
                        )
                        # Avoid duplicate keys in candidate list
                        if not any(c.key == candidate.key for c in candidates):
                            candidates.append(candidate)
                            break  # Highest-precedence match in this group taken

        if not candidates:
            return MemoryExtractionResult(skipped_reason="No qualifying memory patterns detected")

        return MemoryExtractionResult(candidates=candidates)

