"""
FinanceResearchAgent — Phase 10 LangGraph Node.

Reuses get_stock_price and get_crypto_price tools via ToolExecutor.
Used when the research task involves financial/market data.
"""
from __future__ import annotations

import asyncio
import logging
import re

from app.services.research.models import Evidence, EvidenceSource, ResearchTask
from app.tools.base import ToolExecutionContext
from app.tools.executor import ToolExecutor
from app.tools.registry import get_tool_registry

logger = logging.getLogger(__name__)

# Patterns to detect financial symbols
_TICKER_RE = re.compile(r"\b([A-Z]{1,5})\b")
_CRYPTO_KEYWORDS = {"bitcoin", "btc", "ethereum", "eth", "crypto", "coin", "token", "defi"}
_STOCK_KEYWORDS = {"stock", "share", "equity", "nasdaq", "nyse", "s&p", "market cap", "price"}


class FinanceResearchAgent:
    """
    Gathers financial data for a ResearchTask.
    Reuses get_stock_price and get_crypto_price tools.
    """

    def __init__(self, executor: ToolExecutor | None = None) -> None:
        self.executor = executor or ToolExecutor(get_tool_registry())

    async def research(
        self,
        task: ResearchTask,
        context: ToolExecutionContext,
        max_sources: int = 5,
        timeout_seconds: float = 30.0,
    ) -> tuple[list[Evidence], str | None]:
        try:
            return await asyncio.wait_for(
                self._do_research(task, context),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            return [], f"Task timed out after {timeout_seconds}s"
        except Exception as exc:
            logger.error("FinanceResearchAgent error for task %s: %s", task.task_id, exc)
            return [], str(exc)

    async def _do_research(
        self,
        task: ResearchTask,
        context: ToolExecutionContext,
    ) -> tuple[list[Evidence], str | None]:
        query_lower = task.query.lower()
        evidence_list: list[Evidence] = []

        # Determine if crypto or stock
        is_crypto = any(k in query_lower for k in _CRYPTO_KEYWORDS)

        if is_crypto:
            # Extract possible coin names/IDs
            coins = self._extract_crypto_ids(query_lower)
            for coin in coins[:3]:
                result = await self.executor.execute(
                    tool_name="get_crypto_price",
                    arguments={"coin_id": coin},
                    context=context,
                )
                if result.success and result.data:
                    evidence_list.append(self._crypto_to_evidence(task, coin, result.data))
        else:
            # Extract ticker symbols
            tickers = _TICKER_RE.findall(task.query)[:3]
            for ticker in tickers:
                result = await self.executor.execute(
                    tool_name="get_stock_price",
                    arguments={"symbol": ticker},
                    context=context,
                )
                if result.success and result.data:
                    evidence_list.append(self._stock_to_evidence(task, ticker, result.data))

        if not evidence_list:
            # Fall back to web search for financial context
            result = await self.executor.execute(
                tool_name="web_search",
                arguments={"query": task.query, "max_results": 3},
                context=context,
            )
            if result.success and result.data:
                if isinstance(result.data, dict):
                    items = result.data.get("results", result.data.get("items", []))
                elif isinstance(result.data, list):
                    items = result.data
                else:
                    items = []
                for item in items[:3]:
                    if isinstance(item, dict):
                        evidence_list.append(Evidence(
                            task_id=task.task_id,
                            source_type=EvidenceSource.FINANCE,
                            title=str(item.get("title", ""))[:200],
                            url=str(item.get("url", ""))[:500] or None,
                            snippet=str(item.get("snippet", ""))[:500],
                            content=str(item.get("snippet", ""))[:1000],
                            relevance=0.6,
                            reliability=0.6,
                        ))

        return evidence_list, None

    def _extract_crypto_ids(self, query: str) -> list[str]:
        mapping = {
            "bitcoin": "bitcoin", "btc": "bitcoin",
            "ethereum": "ethereum", "eth": "ethereum",
            "solana": "solana", "sol": "solana",
            "cardano": "cardano", "ada": "cardano",
            "dogecoin": "dogecoin", "doge": "dogecoin",
            "ripple": "ripple", "xrp": "ripple",
        }
        found = []
        for key, coin_id in mapping.items():
            if key in query and coin_id not in found:
                found.append(coin_id)
        return found or ["bitcoin"]

    def _crypto_to_evidence(self, task: ResearchTask, coin: str, data: dict) -> Evidence:
        price = data.get("price", data.get("current_price", "N/A"))
        change = data.get("change_24h", data.get("price_change_percentage_24h", "N/A"))
        content = f"{coin.title()} Price: ${price} | 24h Change: {change}%\nFull data: {data}"
        return Evidence(
            task_id=task.task_id,
            source_type=EvidenceSource.FINANCE,
            title=f"{coin.title()} — CoinGecko",
            url=f"https://www.coingecko.com/en/coins/{coin}",
            snippet=f"Price: ${price}, 24h: {change}%",
            content=content[:2000],
            relevance=0.9,
            reliability=0.9,
        )

    def _stock_to_evidence(self, task: ResearchTask, ticker: str, data: dict) -> Evidence:
        price = data.get("price", data.get("current_price", "N/A"))
        name = data.get("name", data.get("longName", ticker))
        content = f"{name} ({ticker}): ${price}\nFull data: {data}"
        return Evidence(
            task_id=task.task_id,
            source_type=EvidenceSource.FINANCE,
            title=f"{name} ({ticker}) — Yahoo Finance",
            url=f"https://finance.yahoo.com/quote/{ticker}",
            snippet=f"Price: ${price}",
            content=content[:2000],
            relevance=0.9,
            reliability=0.9,
        )
