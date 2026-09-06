"""Unit and integration tests for Phase 9 Tool Calling Infrastructure."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from app.tools.base import ToolExecutionContext, ToolPermission, ToolResult
from app.tools.builtins.calculator import CalculatorTool, SafeMathEvaluator
from app.tools.builtins.conversation_search import ConversationSearchTool
from app.tools.builtins.crypto import CryptoPriceTool
from app.tools.builtins.currency import CurrencyConversionTool
from app.tools.builtins.finance import StockPriceTool
from app.tools.builtins.knowledge_search import KnowledgeSearchTool
from app.tools.builtins.memory_search import MemorySearchTool
from app.tools.builtins.news import NewsSearchTool
from app.tools.builtins.url_reader import SSRFValidator, URLReaderTool
from app.tools.builtins.weather import WeatherTool
from app.tools.builtins.web_search import WebSearchTool
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry, get_tool_registry
from app.services.chat.tool_loop import format_tools_system_prompt, parse_tool_calls, strip_tool_call_markup

TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


# ── 1. Registry Tests ──────────────────────────────────────────────────────────

def test_registry_registration_and_lookup():
    reg = ToolRegistry()
    calc = CalculatorTool()
    reg.register(calc)

    assert reg.has_tool("calculator")
    assert reg.get("calculator") is calc
    assert len(reg.list_tools()) == 1

    schemas = reg.get_schemas()
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "calculator"
    assert "parameters" in schemas[0]["function"]

    catalog = reg.get_catalog()
    assert len(catalog) == 1
    assert catalog[0]["name"] == "calculator"
    assert "safe" in [p.lower() for p in catalog[0].get("permissions", [])]


def test_global_registry_contains_all_11_builtins():
    reg = get_tool_registry()
    tools = reg.list_tools()
    tool_names = {t.name for t in tools}

    expected = {
        "calculator",
        "web_search",
        "read_url",
        "get_weather",
        "convert_currency",
        "search_news",
        "get_stock_price",
        "get_crypto_price",
        "search_knowledge_base",
        "search_user_memory",
        "search_conversation_history",
    }
    assert expected.issubset(tool_names)
    assert len(tools) >= 11


# ── 2. Calculator & AST Math Security Tests ───────────────────────────────────

def test_safe_math_evaluator_valid_expressions():
    evaluator = SafeMathEvaluator()

    assert evaluator.evaluate("2 + 2") == 4
    assert evaluator.evaluate("10 * 5 + 3") == 53
    assert evaluator.evaluate("(100 - 20) / 4") == 20.0
    assert evaluator.evaluate("2 ** 8") == 256
    assert evaluator.evaluate("sqrt(144)") == 12.0
    assert evaluator.evaluate("abs(-42)") == 42
    assert evaluator.evaluate("15% of 200") == 30.0
    assert evaluator.evaluate("12345 * 678") == 8369910


def test_safe_math_evaluator_rejects_malicious_code():
    evaluator = SafeMathEvaluator()

    # Reject imports and arbitrary execution
    with pytest.raises(ValueError):
        evaluator.evaluate("__import__('os').system('dir')")

    with pytest.raises(ValueError):
        evaluator.evaluate("open('/etc/passwd').read()")

    with pytest.raises(Exception):
        evaluator.evaluate("exec('x = 1')")

    # Reject division by zero
    with pytest.raises(ZeroDivisionError, match="Division by zero"):
        evaluator.evaluate("100 / 0")


@pytest.mark.asyncio
async def test_calculator_tool_execution():
    calc = CalculatorTool()
    ctx = ToolExecutionContext(user_id=TEST_USER_ID)

    result = await calc.execute({"expression": "12345 * 678"}, ctx)
    assert result.success is True
    assert result.data["result"] == 8369910
    assert result.data["expression"] == "12345 * 678"


# ── 3. SSRF Validator & URL Reader Security Tests ─────────────────────────────

def test_ssrf_validator_blocks_private_and_loopback_ips():
    # Loopback
    with pytest.raises(ValueError, match="blocked"):
        SSRFValidator.validate_url("http://127.0.0.1/admin")

    with pytest.raises(ValueError, match="blocked"):
        SSRFValidator.validate_url("http://localhost:8000")

    # RFC 1918 Private Ranges
    with pytest.raises(ValueError, match="blocked"):
        SSRFValidator.validate_url("http://10.0.0.1/secrets")

    with pytest.raises(ValueError, match="blocked"):
        SSRFValidator.validate_url("http://192.168.1.1/router")

    with pytest.raises(ValueError, match="blocked"):
        SSRFValidator.validate_url("http://172.16.0.1/internal")

    # Cloud Metadata (AWS/GCP/Azure)
    with pytest.raises(ValueError, match="blocked"):
        SSRFValidator.validate_url("http://169.254.169.254/latest/meta-data")

    # Internal TLDs
    with pytest.raises(ValueError, match="blocked"):
        SSRFValidator.validate_url("http://service.local/api")

    # Non-HTTP protocols
    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        SSRFValidator.validate_url("file:///etc/passwd")


# ── 4. Currency Conversion Tests ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_currency_conversion_same_currency():
    tool = CurrencyConversionTool()
    ctx = ToolExecutionContext(user_id=TEST_USER_ID)

    result = await tool.execute({"amount": 100, "from_currency": "USD", "to_currency": "USD"}, ctx)
    assert result.success is True
    assert result.data["converted_amount"] == 100.0
    assert result.data["rate"] == 1.0


# ── 5. Tool Executor Guardrails Tests ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_tool_executor_enforces_permissions_and_validation():
    reg = ToolRegistry()
    reg.register(CalculatorTool())
    executor = ToolExecutor(reg)
    ctx = ToolExecutionContext(user_id=TEST_USER_ID)

    # Missing tool
    result = await executor.execute("non_existent_tool", {}, ctx)
    assert result.success is False
    assert "not found" in result.error

    # Missing required argument
    result = await executor.execute("calculator", {}, ctx)
    assert result.success is False
    assert "Missing required argument" in result.error

    # Successful execution with arguments: dict
    result = await executor.execute("calculator", {"expression": "50 + 50"}, ctx)
    assert result.success is True
    assert result.data["result"] == 100


# ── 6. Tool Parsing & Markup Stripping Tests ──────────────────────────────────

def test_parse_tool_calls_xml_format():
    text = """Let me calculate that for you:
<tool_call>
{"name": "calculator", "arguments": {"expression": "45 * 12"}}
</tool_call>
Here is the math."""

    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0][0] == "calculator"
    assert calls[0][1] == {"expression": "45 * 12"}

    cleaned = strip_tool_call_markup(text)
    assert "<tool_call>" not in cleaned
    assert "45 * 12" not in cleaned


def test_parse_tool_calls_json_codeblock_format():
    text = """```json
{"tool": "get_weather", "arguments": {"location": "London"}}
```"""

    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0][0] == "get_weather"
    assert calls[0][1] == {"location": "London"}


def test_parse_tool_calls_qwen_format():
    text = '<tool_call> <function=web_search> {"query": "latest OpenAI ChatGPT new model release 2026", "max_results": 10} </tool_call>'
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0][0] == "web_search"
    assert calls[0][1]["query"] == "latest OpenAI ChatGPT new model release 2026"

    cleaned = strip_tool_call_markup(text)
    assert "<tool_call>" not in cleaned
    assert "function=web_search" not in cleaned


def test_tool_registry_aliases():
    reg = ToolRegistry()
    calc = CalculatorTool()
    reg.register(calc)
    assert reg.get("calculator") is calc
    assert reg.get("calculate") is calc
    assert reg.get("calc") is calc


def test_format_tools_system_prompt():
    reg = ToolRegistry()
    reg.register(CalculatorTool())
    prompt = format_tools_system_prompt(reg)

    assert "## AVAILABLE TOOLS" in prompt
    assert "`calculator`" in prompt
    assert "<tool_call>" in prompt


# ── 7. Direct Execution of Builtin Tools ──────────────────────────────────────

@pytest.mark.asyncio
async def test_direct_execution_builtin_tools():
    ctx = ToolExecutionContext(user_id=TEST_USER_ID)

    # Calculator
    calc = CalculatorTool()
    res = await calc.execute({"expression": "100 / 4"}, ctx)
    assert res.success is True
    assert res.data["result"] == 25

    # Web search mock or direct
    ws = WebSearchTool()
    ws_res = await ws.execute({"query": "python fastapi", "max_results": 2}, ctx)
    assert ws_res.success is True
    assert "results" in ws_res.data or "query" in ws_res.data

    # URL Reader SSRF rejection
    ur = URLReaderTool()
    ur_res = await ur.execute({"url": "http://127.0.0.1:8000/secret"}, ctx)
    assert ur_res.success is False
    assert "Security rejection" in ur_res.error


# ── 8. REST API Integration Tests ─────────────────────────────────────────────

def test_rest_api_list_tools(client):
    response = client.get("/api/v1/tools")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 11
    names = {t["name"] for t in data["tools"]}
    assert "calculator" in names
    assert "get_weather" in names


def test_rest_api_execute_tool_calculator(client):
    payload = {
        "tool_name": "calculator",
        "arguments": {
            "expression": "12345 * 678"
        },
        "user_id": str(TEST_USER_ID),
    }
    response = client.post("/api/v1/tools/execute", json=payload)
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
    assert res["tool_name"] == "calculator"
    assert res["data"]["result"] == 8369910
    assert res["data"]["expression"] == "12345 * 678"


def test_rest_api_execute_tool_with_parameters_alias(client):
    payload = {
        "tool_name": "calculator",
        "parameters": {
            "expression": "500 + 250"
        },
        "user_id": str(TEST_USER_ID),
    }
    response = client.post("/api/v1/tools/execute", json=payload)
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
    assert res["data"]["result"] == 750
