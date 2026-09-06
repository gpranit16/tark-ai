"""RAGRouter — decides whether a chat message should use the RAG pipeline.

Isolated, testable decision logic. Does NOT depend on DB or LLM.
Decision is based on:
  1. Explicit file_ids attached to the request (strongest signal).
  2. Document-reference keywords in the message content.
"""

# Keywords that strongly suggest the user is asking about an attached document
_DOC_REFERENCE_KEYWORDS = frozenset({
    "document", "file", "pdf", "report", "paper", "attachment",
    "uploaded", "according to", "based on", "in the", "from the",
    "the document", "the file", "the report", "the paper",
    "what does", "what is in", "summarize", "summary of",
    "page", "section", "paragraph", "table", "chart", "figure",
    "extract", "find in", "look up", "check the",
})


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

        # Keyword and file extension detection
        content_lower = content.lower()
        for keyword in _DOC_REFERENCE_KEYWORDS:
            if keyword in content_lower:
                return True

        # Common file extensions in query (e.g. "Pan.pdf", "data.csv")
        import re
        if re.search(r"\b[\w\-\.]+\.(?:pdf|txt|docx|doc|csv|xlsx|pptx|png|jpg|jpeg|json|md|py|js|ts|html)\b", content_lower):
            return True

        return False
