"""RAGRouter — decides whether a chat message should use the RAG pipeline.

Isolated, testable decision logic. Does NOT depend on DB or LLM.
Decision is based on:
  1. Explicit file_ids attached to the request (strongest signal).
  2. Document-reference keywords in the message content.
"""

import re

# Keywords and phrases that specifically indicate querying an attached/uploaded document
_DOC_REFERENCE_PATTERNS = [
    r"\bthe\s+document\b",
    r"\bthe\s+pdf\b",
    r"\bthe\s+attachment\b",
    r"\buploaded\s+(?:document|file|pdf|report|paper)\b",
    r"\battached\s+(?:document|file|pdf)\b",
    r"\bin\s+the\s+(?:document|pdf|uploaded\s+file)\b",
    r"\bfrom\s+the\s+(?:document|pdf|uploaded\s+file)\b",
    r"\bsummarize\s+(?:the\s+)?(?:document|pdf|uploaded\s+file)\b",
    r"\bwhat\s+does\s+the\s+document\s+say\b",
]

_COMPILED_DOC_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _DOC_REFERENCE_PATTERNS]


class RAGRouter:
    """Determines whether a request should use the RAG pipeline.

    Kept separate from ModelRouter to maintain single-responsibility.
    """

    def should_use_rag(
        self,
        content: str,
        file_ids: list | None = None,
        mode: str | None = None,
    ) -> bool:
        """Return True if the request should be routed through RAG.

        Args:
            content: The user message text.
            file_ids: File IDs explicitly attached to this request.
            mode: The conversation mode string ('rag', 'normal', etc.).

        Returns:
            True if RAG pipeline should be used.
        """
        # Explicit RAG mode always triggers RAG
        if mode and mode.lower() == "rag":
            return True

        # Explicit file attachments trigger RAG
        if file_ids:
            return True

        # Document reference phrase detection
        content_lower = content.lower().strip()
        for pattern in _COMPILED_DOC_PATTERNS:
            if pattern.search(content_lower):
                return True

        # Common file extensions in query (e.g. "Pan.pdf", "data.csv")
        if re.search(r"\b[\w\-.]+\.(?:pdf|txt|docx|doc|csv|xlsx|pptx|png|jpg|jpeg|json|md|py|js|ts|html)\b", content_lower):
            return True

        return False

