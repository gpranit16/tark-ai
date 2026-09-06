"""Stock Price / Equity Tool for TARK AI using public Yahoo Finance quote endpoint. Zero API keys required."""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Type
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolExecutionContext, ToolPermission, ToolResult

logger = logging.getLogger(__name__)


class StockPriceInput(BaseModel):
    symbol: str = Field(
        ...,
        description="Ticker symbol of the stock or ETF (e.g. 'AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'SPY').",
        min_length=1,
        max_length=10,
    )


class StockPriceTool(BaseTool):
    name: str = "get_stock_price"
    description: str = (
        "Get current real-time or near real-time price, change, market cap, day high/low, and trading summary for any publicly traded stock or ETF ticker. "
        "Use this whenever the user asks about stock prices, share performance, market valuation, or ticker metrics."
    )
    permission: ToolPermission = ToolPermission.NETWORK
    input_schema: Type[BaseModel] = StockPriceInput

    async def execute(self, arguments: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        raw_symbol = arguments.get("symbol", "").upper().strip()
        if not raw_symbol:
            return ToolResult(tool_name=self.name, success=False, error="Stock symbol is required.")

        symbol = raw_symbol.replace("$", "")

        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?interval=1d&range=1d"
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json",
                },
            )

            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            chart = data.get("chart", {})
            results = chart.get("result")
            if not results or len(results) == 0:
                err = chart.get("error", {}).get("description", f"Ticker '{symbol}' not found.")
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error=f"Could not retrieve stock info for '{symbol}': {err}",
                    source="Yahoo Finance",
                )

            meta = results[0].get("meta", {})
            regular_price = meta.get("regularMarketPrice")
            previous_close = meta.get("chartPreviousClose") or meta.get("previousClose")
            currency = meta.get("currency", "USD")
            exchange = meta.get("exchangeName", "")
            instrument_type = meta.get("instrumentType", "")
            day_high = meta.get("regularMarketDayHigh")
            day_low = meta.get("regularMarketDayLow")

            change = round(regular_price - previous_close, 2) if (regular_price and previous_close) else 0.0
            change_percent = round((change / previous_close) * 100, 2) if (previous_close and previous_close > 0) else 0.0

            result_data = {
                "symbol": symbol,
                "current_price": regular_price,
                "currency": currency,
                "change": change,
                "change_percent": change_percent,
                "previous_close": previous_close,
                "day_high": day_high,
                "day_low": day_low,
                "exchange": exchange,
                "instrument_type": instrument_type,
            }

            return ToolResult(
                tool_name=self.name,
                success=True,
                data=result_data,
                source=f"Yahoo Finance ({symbol} - {exchange})",
            )

        except urllib.error.HTTPError as http_err:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Financial data service error ({http_err.code}) for '{symbol}'.",
                source="Yahoo Finance",
            )
        except Exception as exc:
            logger.exception("Error in StockPriceTool: %s", exc)
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Failed to fetch stock price for '{symbol}': {str(exc)}",
                source="Yahoo Finance",
            )
