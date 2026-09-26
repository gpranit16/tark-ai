"""RAGRouter — decides whether a chat message should use the RAG pipeline.

Isolated, testable decision logic. Does NOT depend on DB or LLM.
Decision is based on:
  1. Explicit file_ids attached to the request (strongest signal).
  2. Document-reference keywords in the message content.
"""

import re

# Keywords and phrases that specifically indicate querying an attached/uploaded document
_DOC_REFERENCE_PATTERNS = [
    r"\b(?:the|this|that)\s+(?:document|pdf|file|attachment|report|paper|spreadsheet|receipt|invoice|doc)\b",
    r"\b(?:attached|uploaded)\s+(?:document|pdf|file|attachment|report|paper|spreadsheet|receipt|invoice|doc)\b",
    r"\bin\s+(?:this|the|that)\s+(?:document|pdf|uploaded\s+file|file|attachment|report|doc)\b",
    r"\bfrom\s+(?:this|the|that)\s+(?:document|pdf|uploaded\s+file|file|attachment|report|doc)\b",
    r"\bsummarize\s+(?:this|the|that|my)\s+(?:document|pdf|uploaded\s+file|file|attachment|report|doc)\b",
    r"\bexplain\s+(?:this|the|that|my)\s+(?:document|pdf|uploaded\s+file|file|attachment|report|doc)\b",
    r"\bwhat\s+does\s+(?:this|the|that)\s+(?:document|pdf|file|attachment|report|doc)\s+say\b",
    r"\bwhat(?:'s|\s+is)\s+in\s+(?:this|the|that)\s+(?:document|pdf|file|attachment|report|doc)\b",
    r"\btell\s+me\s+about\s+(?:this|the|that)\s+(?:document|pdf|file|attachment|report|doc)\b",
    r"\breview\s+(?:this|the|that)\s+(?:document|pdf|file|attachment|report|doc)\b",
    r"\baccording\s+to\s+(?:this|the|that)\s+(?:document|pdf|file|attachment|report|doc)\b",
    r"\bwhat\s+(?:content|contents|information)\s+(?:is|are)\s+in\s+this\b",
    r"\bwhat\s+(?:is|are)\s+(?:the\s+)?content\w*\s+in\s+this\b",
    r"\bcontent\w*\s+in\s+this\b",
    r"\bkya\s+(?:hai\s+)?isme\b",
    r"\bisme\s+kya\s+hai\b",
    r"\bkya\s+likha\s+hai\b",
    r"\bye\s+kiske\s+baar?e\s+me\s+hai\b",
    r"\bpdf\s+me\s+kya\s+hai\b",
    r"\bpage\s+\d+\b",
]

_COMPILED_DOC_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _DOC_REFERENCE_PATTERNS]

# Deictic follow-up queries that reference prior attachments in the SAME thread
_ATTACHMENT_FOLLOWUP_PATTERNS = [
    r"\b(?:what|who|where|when|why|how)\s+(?:is|are|was|were|does|did)\s+(?:in\s+)?(?:it|this|that)\b",
    r"\b(?:summarize|explain|review|analyze|translate)\s+(?:it|this|that)\b",
    r"\bwhat\s+(?:is|does|are)\s+it\s+say\b",
    r"\bwhat\s+is\s+this\b",
    r"\bwho\s+is\s+this\b",
    r"\bwhat(?:'s|\s+is)\s+in\s+(?:this|here|it)\b",
    r"\bwhat\s+content\w*\s+(?:is|are)\s+in\s+(?:this|it)\b",
    r"\bwho\s+signed\s+(?:it|this)\b",
    r"\bkya\s+(?:hai|likha)\s+(?:hai\s+)?(?:isme|ismein)?\b",
    r"\bye\s+kiske\s+baar?e\s+me\s+hai\b",
    r"\bpdf\s+me\s+kya\s+hai\b",
    r"\bdetails?\s+(?:of|in)\s+(?:this|it)\b",
    r"\bsummary\b",
    r"\btldr\b",
    r"\bsummarize\b",
]

_COMPILED_FOLLOWUP_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _ATTACHMENT_FOLLOWUP_PATTERNS]


class RAGRouter:
    """Determines whether a request should use the RAG pipeline.

    Kept separate from ModelRouter to maintain single-responsibility.
    """

    def should_use_rag(
        self,
        content: str,
        file_ids: list | None = None,
        mode: str | None = None,
        has_thread_attachments: bool = False,
    ) -> bool:
        """Return True if the request should be routed through RAG.

        Args:
            content: The user message text.
            file_ids: File IDs explicitly attached to this request.
            mode: The conversation mode string ('rag', 'normal', etc.).
            has_thread_attachments: Whether recent messages in thread contain attachments.

        Returns:
            True if RAG pipeline should be used.
        """
        # Explicit RAG mode always triggers RAG
        if mode and mode.lower() == "rag":
            return True

        # Explicit file attachments in current message trigger RAG
        if file_ids:
            return True

        content_lower = content.lower().strip()

        # Web search toggle takes precedence over passive thread document mentions
        if "[web search enabled]" in content_lower:
            return False

        # GitHub MCP queries (e.g. "update README.md of iot-bin repo", "show package.json") take precedence over file extension matching
        try:
            from app.services.chat.tool_loop import detect_github_intent
            if detect_github_intent(content):
                return False
        except Exception:
            pass

        # Document reference phrase detection (e.g., "in this document", "the pdf", etc.)
        for pattern in _COMPILED_DOC_PATTERNS:
            if pattern.search(content_lower):
                return True

        # Common file extensions in query (e.g. "Pan.pdf", "data.csv", "report.docx")
        if re.search(r"\b[\w\-.]+\.(?:pdf|txt|docx|doc|csv|xlsx|pptx|png|jpg|jpeg|json|md|py|js|ts|html)\b", content_lower):
            return True

        # If thread has attachments and user query asks a follow-up specifically referencing it
        if has_thread_attachments:
            for pattern in _COMPILED_FOLLOWUP_PATTERNS:
                if pattern.search(content_lower):
                    return True

        return False

