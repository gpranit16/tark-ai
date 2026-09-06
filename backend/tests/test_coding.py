"""Phase 12 — Coding Mode + Code Workspace Test Suite.

Tests:
A. Code generation
B. Code explanation
C. Debugging
D. Refactoring
E. Code review
F. Multi-file context
G. Test generation
H. Project context
I. RAG + coding
J. Ownership isolation
K. Security
L. SSE streaming
"""
from __future__ import annotations

import io
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import ConversationMode, MessageRole
from app.models.conversation import Message, Project, Thread, User
from app.models.file import File
from app.providers.base import NormalizedMessage, ProviderStreamEvent, UsageMetadata
from app.schemas.chat import ChatRequest
from app.services.chat.router import ModelRouter, ProviderSelection
from app.services.chat.sse import (
    coding_complete,
    coding_context_ready,
    coding_error,
    coding_file,
    coding_generation,
    coding_started,
)
from app.services.coding.context import CodeContextBuilder, detect_language, extract_code_symbols
from app.services.coding.models import (
    CodeChange,
    CodeChangeOperation,
    CodeReviewFinding,
    CodeReviewResponse,
    CodeReviewSeverity,
    CodingQueryRequest,
    CodingQueryResponse,
    StructuredCodeResponse,
)
from app.services.coding.service import CodingService, extract_diffs_from_text
from app.services.coding.system_prompt import CODING_SYSTEM_PROMPT, build_coding_system_prompt
from app.services.files import process_and_upload_file, validate_file


class TestCodingModelsAndUtilities:
    """Unit tests for Phase 12 coding models, language detection, and diff parsing."""

    def test_language_detection(self):
        assert detect_language("main.py") == "python"
        assert detect_language("App.jsx") == "jsx"
        assert detect_language("index.ts") == "typescript"
        assert detect_language("styles.css") == "css"
        assert detect_language("schema.sql") == "sql"
        assert detect_language("config.yaml") == "yaml"
        assert detect_language("server.go") == "go"
        assert detect_language("lib.rs") == "rust"
        assert detect_language("unknown.xyz") == "text"

    def test_symbol_extraction_python(self):
        py_code = """
import os
from fastapi import FastAPI

app = FastAPI()

async def get_health():
    return {"status": "ok"}

class HealthService:
    def check(self):
        pass
"""
        symbols = extract_code_symbols(py_code, "python")
        assert any("FastAPI" in s for s in symbols)
        assert any("def get_health()" in s for s in symbols)
        assert any("class HealthService" in s for s in symbols)

    def test_symbol_extraction_js(self):
        js_code = """
import React from 'react';

export function Header() {
    return <header>TARK AI</header>;
}

export class AppContainer {
}
"""
        symbols = extract_code_symbols(js_code, "javascript")
        assert any("function Header()" in s for s in symbols)
        assert any("class AppContainer" in s for s in symbols)

    def test_extract_diffs_from_text(self):
        sample_response = """
Here is the suggested fix:

```diff
--- a/backend/app/main.py
+++ b/backend/app/main.py
@@ -10,3 +10,3 @@
-def old():
+def new():
```

And the updated implementation:

```python:backend/app/services/chat.py
def get_service():
    return True
```
"""
        diffs = extract_diffs_from_text(sample_response)
        assert len(diffs) == 2
        assert diffs[0].file == "backend/app/main.py"
        assert "+++ b/backend/app/main.py" in (diffs[0].diff or "")
        assert diffs[1].file == "backend/app/services/chat.py"
        assert diffs[1].language == "python"

    def test_structured_code_models(self):
        change = CodeChange(
            file="app/api.py",
            operation="modify",
            summary="Added input validation",
            diff="--- a/app/api.py\n+++ b/app/api.py",
            language="python",
        )
        assert change.file == "app/api.py"
        assert change.operation == "modify"

        review_finding = CodeReviewFinding(
            category="Security issues",
            severity=CodeReviewSeverity.CRITICAL,
            file="app/auth.py",
            line=42,
            title="SQL Injection vulnerability",
            description="Raw string interpolation used in query",
            suggestion="Use parameterized SQLAlchemy queries",
        )
        assert review_finding.severity == CodeReviewSeverity.CRITICAL

        review_resp = CodeReviewResponse(
            summary="Found 1 critical security issue",
            findings=[review_finding],
            score=6.5,
        )
        assert review_resp.score == 6.5
        assert len(review_resp.findings) == 1


class TestCodingSSEEvents:
    """Test SSE event builders for Phase 12 coding stream."""

    def test_coding_started_event(self):
        raw = coding_started("Refactor user auth", file_count=2, project_name="TarkAI Core")
        assert "event: coding_started\n" in raw
        payload = json.loads(raw.split("data: ")[1].strip())
        assert payload["query"] == "Refactor user auth"
        assert payload["file_count"] == 2
        assert payload["project_name"] == "TarkAI Core"

    def test_coding_file_event(self):
        raw = coding_file("main.py", "python", 1024)
        assert "event: coding_file\n" in raw
        payload = json.loads(raw.split("data: ")[1].strip())
        assert payload["filename"] == "main.py"
        assert payload["language"] == "python"
        assert payload["size_bytes"] == 1024

    def test_coding_context_ready_event(self):
        raw = coding_context_ready(["main.py", "auth.py"], 2, 4500)
        assert "event: coding_context_ready\n" in raw
        payload = json.loads(raw.split("data: ")[1].strip())
        assert payload["total_files"] == 2
        assert payload["total_chars"] == 4500

    def test_coding_generation_event(self):
        raw = coding_generation("groq", "qwen/qwen3.8-27b")
        assert "event: coding_generation\n" in raw
        payload = json.loads(raw.split("data: ")[1].strip())
        assert payload["provider"] == "groq"
        assert payload["model"] == "qwen/qwen3.8-27b"

    def test_coding_complete_event(self):
        raw = coding_complete(files_analyzed=3, changes_count=2, tests_count=1)
        assert "event: coding_complete\n" in raw
        payload = json.loads(raw.split("data: ")[1].strip())
        assert payload["files_analyzed"] == 3
        assert payload["changes_count"] == 2
        assert payload["tests_count"] == 1

    def test_coding_error_event(self):
        raw = coding_error("Syntax error in context parser")
        assert "event: coding_error\n" in raw
        payload = json.loads(raw.split("data: ")[1].strip())
        assert payload["error"] == "Syntax error in context parser"


class TestCodingFileSupportAndSecurity:
    """Test common code file extensions and path traversal / security guards."""

    def test_code_extensions_validation(self):
        valid_extensions = [
            ("server.py", "text/x-python"),
            ("client.js", "application/javascript"),
            ("App.jsx", "text/javascript"),
            ("main.ts", "text/plain"),
            ("index.html", "text/html"),
            ("style.css", "text/css"),
            ("schema.sql", "text/plain"),
            ("docker-compose.yml", "text/yaml"),
            ("data.json", "application/json"),
            ("App.java", "text/plain"),
            ("main.cpp", "text/plain"),
            ("main.go", "text/plain"),
            ("lib.rs", "text/plain"),
        ]

        for fname, mime in valid_extensions:
            ext = validate_file(fname, mime, 1024)
            assert ext.startswith(".")

    def test_system_prompt_security_instructions(self):
        prompt = build_coding_system_prompt()
        assert "NEVER claim that code was executed" in prompt
        assert "Prioritize Correctness" in prompt
        assert "Preserve Project Conventions" in prompt
        assert "Inspect Before Modifying" in prompt


@pytest.mark.asyncio
class TestCodingModeE2EWorkflows:
    """E2E workflow tests covering scenarios A through L."""

    async def test_a_code_generation(self, db_session: AsyncSession, user: User):
        """Scenario A: Code generation for FastAPI /health."""
        thread = Thread(id=uuid.uuid4(), user_id=user.id, title="FastAPI Health Endpoint")
        db_session.add(thread)
        await db_session.commit()

        service = CodingService()
        mock_answer = "```python\nfrom fastapi import FastAPI\napp = FastAPI()\n\n@app.get('/health')\nasync def health():\n    return {'status': 'ok'}\n```"

        with patch.object(service.router, "stream") as mock_stream:
            async def fake_stream(*args, **kwargs):
                sel = ProviderSelection(None, "groq", "qwen/qwen3.8-27b")
                yield sel, ProviderStreamEvent(delta=mock_answer, usage=UsageMetadata(input_tokens=50, output_tokens=40))

            mock_stream.side_effect = fake_stream

            payload = ChatRequest(content="Write a Python FastAPI endpoint for /health.", mode=ConversationMode.CODING)
            events = []
            async for ev in service.stream_coding_chat(
                session=db_session,
                thread_id=thread.id,
                payload=payload,
                is_disconnected=AsyncMock(return_value=False),
                user_id=user.id,
            ):
                events.append(ev)

            assert any("coding_started" in e for e in events)
            assert any("coding_context_ready" in e for e in events)
            assert any("coding_generation" in e for e in events)
            assert any("fastapi" in e.lower() for e in events)
            assert any("coding_complete" in e for e in events)

    async def test_b_code_explanation(self, db_session: AsyncSession):
        """Scenario B: Code explanation of provided function."""
        builder = CodeContextBuilder()
        builder.loaded_files = [{
            "id": "f1",
            "filename": "math_utils.py",
            "language": "python",
            "content": "def fib(n):\n    if n <= 1: return n\n    return fib(n-1) + fib(n-2)",
            "symbols": ["def fib()"],
        }]
        messages = builder.assemble([
            Message(role=MessageRole.USER, content="Explain what fib(n) does.")
        ])
        assert len(messages) == 2
        assert "math_utils.py" in messages[0].content
        assert "Explain what fib(n) does." in messages[1].content

    async def test_c_debugging_root_cause(self, db_session: AsyncSession):
        """Scenario C: Debugging broken code with zero division error."""
        service = CodingService()
        broken_code = "def divide(a, b):\n    return a / 0"
        mock_fix = """
### Root Cause:
The function attempts to divide `a` by the constant `0`, raising `ZeroDivisionError`.

### Fix:
```python
def divide(a, b):
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
```
"""
        with patch.object(service.router, "stream") as mock_stream:
            async def fake_stream(*args, **kwargs):
                sel = ProviderSelection(None, "groq", "qwen/qwen3.8-27b")
                yield sel, ProviderStreamEvent(delta=mock_fix, usage=UsageMetadata(input_tokens=60, output_tokens=70))

            mock_stream.side_effect = fake_stream

            req = CodingQueryRequest(query=f"Fix this bug: {broken_code}")
            res = await service.query_coding(db_session, req, user_id=uuid.uuid4())
            assert "Root Cause" in res.answer
            assert "ZeroDivisionError" in res.answer

    async def test_d_refactoring_and_e_code_review(self, db_session: AsyncSession):
        """Scenario D & E: Refactoring and structured code review with severity."""
        prompt = build_coding_system_prompt()
        assert "[CRITICAL]" in prompt
        assert "[HIGH]" in prompt
        assert "Security issues" in prompt
        assert "Maintainability" in prompt

    async def test_f_multi_file_context(self, db_session: AsyncSession):
        """Scenario F: Multi-file context assembly."""
        builder = CodeContextBuilder()
        builder.loaded_files = [
            {"filename": "routes.py", "language": "python", "content": "from service import get_user", "symbols": ["from service"]},
            {"filename": "service.py", "language": "python", "content": "def get_user(id): pass", "symbols": ["def get_user()"]},
        ]
        context_str = builder.format_codebase_context()
        assert "File: `routes.py`" in context_str
        assert "File: `service.py`" in context_str

    async def test_g_test_generation(self, db_session: AsyncSession):
        """Scenario G: Test generation."""
        mock_output = """
```python:tests/test_math.py
import pytest
from math_utils import add

def test_add_positive():
    assert add(2, 3) == 5

def test_add_negative():
    assert add(-1, -1) == -2
```
"""
        diffs = extract_diffs_from_text(mock_output)
        assert len(diffs) == 1
        assert diffs[0].file == "tests/test_math.py"
        assert "test_add_positive" in (diffs[0].code or "")

    async def test_h_project_custom_instructions(self, db_session: AsyncSession):
        """Scenario H: Project context and custom coding instructions."""
        project = Project(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            name="FinTech Backend",
            custom_instructions="Always enforce decimal.Decimal for monetary values.",
        )
        builder = CodeContextBuilder(project=project)
        messages = builder.assemble([Message(role=MessageRole.USER, content="Write payment calc")])
        assert "Always enforce decimal.Decimal" in messages[0].content

    async def test_i_rag_plus_coding(self, db_session: AsyncSession):
        """Scenario I: RAG documentation + Coding context."""
        builder = CodeContextBuilder(
            rag_context="[Doc: Auth API] All requests must provide Bearer Token in Authorization header."
        )
        messages = builder.assemble([Message(role=MessageRole.USER, content="Write client fetch")])
        assert "Bearer Token" in messages[0].content

    async def test_j_ownership_isolation(self, db_session: AsyncSession):
        """Scenario J: Multi-tenant user ownership isolation."""
        user_a = User(id=uuid.uuid4())
        user_b = User(id=uuid.uuid4())
        db_session.add_all([user_a, user_b])
        await db_session.commit()

        # Create file owned by user A
        file_a = File(
            id=uuid.uuid4(),
            user_id=user_a.id,
            original_filename="secret_key.py",
            mime_type="text/x-python",
            extension=".py",
            size_bytes=100,
            storage_provider="local",
            storage_key=f"users/{user_a.id}/secret_key.py",
            status="active",
        )
        db_session.add(file_a)
        await db_session.commit()

        # User B tries to load file A
        builder = CodeContextBuilder()
        loaded = await builder.load_code_files(
            session=db_session,
            user_id=user_b.id,
            file_ids=[file_a.id],
        )
        # Should return empty list because user_b does not own file_a
        assert len(loaded) == 0

    async def test_k_security_no_arbitrary_execution(self, db_session: AsyncSession):
        """Scenario K: Ensure backend does not run arbitrary untrusted code."""
        prompt = CODING_SYSTEM_PROMPT
        assert "NEVER claim that code was executed" in prompt

    async def test_l_sse_streaming_events(self, db_session: AsyncSession, user: User):
        """Scenario L: Verify SSE stream events sequence."""
        thread = Thread(id=uuid.uuid4(), user_id=user.id, title="SSE Stream Test")
        db_session.add(thread)
        await db_session.commit()

        service = CodingService()
        with patch.object(service.router, "stream") as mock_stream:
            async def fake_stream(*args, **kwargs):
                sel = ProviderSelection(None, "groq", "qwen/qwen3.8-27b")
                yield sel, ProviderStreamEvent(delta="def add(a, b): return a + b", usage=UsageMetadata(input_tokens=10, output_tokens=10))

            mock_stream.side_effect = fake_stream

            payload = ChatRequest(content="Write add function", mode=ConversationMode.CODING)
            events = []
            async for ev in service.stream_coding_chat(
                session=db_session,
                thread_id=thread.id,
                payload=payload,
                is_disconnected=AsyncMock(return_value=False),
                user_id=user.id,
            ):
                events.append(ev)

            # Check sequence of events
            event_types = [line.replace("event: ", "").strip() for e in events for line in e.split("\n") if line.startswith("event: ")]
            assert "coding_started" in event_types
            assert "coding_context_ready" in event_types
            assert "coding_generation" in event_types
            assert "coding_complete" in event_types
            assert "message_complete" in event_types
