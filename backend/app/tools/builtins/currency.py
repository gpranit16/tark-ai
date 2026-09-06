"""Currency Conversion Tool for TARK AI using free Frankfurter / Open Exchange Rate API."""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Type
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolExecutionContext, ToolPermission, ToolResult

logger = logging.getLogger(__name__)


class CurrencyInput(BaseModel):
    amount: float = Field(default=1.0, description="The monetary amount to convert (e.g. 100).", ge=0.0)
    from_currency: str = Field(
        ...,
        description="3-letter ISO code of the source currency (e.g. 'USD', 'EUR', 'GBP', 'INR', 'JPY').",
        min_length=3,
        max_length=4,
    )
    to_currency: str = Field(
        ...,
        description="3-letter ISO code of the target currency (e.g. 'EUR', 'USD', 'INR', 'CAD', 'JPY').",
        min_length=3,
        max_length=4,
    )


class CurrencyConversionTool(BaseTool):
    name: str = "convert_currency"
    description: str = (
        "Convert monetary values between different international fiat currencies using live exchange rates. "
        "Use this whenever the user wants to convert money, check exchange rates, or compare currency values."
    )
    permission: ToolPermission = ToolPermission.NETWORK
    input_schema: Type[BaseModel] = CurrencyInput

    async def execute(self, arguments: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        try:
            amount = float(arguments.get("amount", 1.0))
            from_curr = arguments.get("from_currency", "").upper().strip()
            to_curr = arguments.get("to_currency", "").upper().strip()

            if not from_curr or not to_curr:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error="Both from_currency and to_currency ISO codes are required.",
                )

            if from_curr == to_curr:
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    data={
                        "amount": amount,
                        "from_currency": from_curr,
                        "to_currency": to_curr,
                        "rate": 1.0,
                        "converted_amount": amount,
                        "date": "current",
                    },
                    source="Frankfurter API",
                )

            # Frankfurter API (free, open, European Central Bank reference rates)
            url = f"https://api.frankfurter.app/latest?amount={amount}&from={from_curr}&to={to_curr}"

            req = urllib.request.Request(url, headers={"User-Agent": "TarkAI-CurrencyTool/1.0"})
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            rates = data.get("rates", {})
            converted_amount = rates.get(to_curr)

            if converted_amount is None:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error=f"Exchange rate from {from_curr} to {to_curr} is not supported.",
                    source="Frankfurter API",
                )

            rate = round(converted_amount / amount, 6) if amount > 0 else None

            result_data = {
                "amount": amount,
                "from_currency": from_curr,
                "to_currency": to_curr,
                "rate": rate,
                "converted_amount": round(converted_amount, 4),
                "date": data.get("date", ""),
            }

            return ToolResult(
                tool_name=self.name,
                success=True,
                data=result_data,
                source=f"European Central Bank / Frankfurter API (as of {data.get('date', 'today')})",
            )

        except urllib.error.HTTPError as http_err:
            if http_err.code == 404:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error=f"Unsupported currency symbol. Ensure standard 3-letter codes like USD, EUR, GBP, JPY, INR.",
                    source="Frankfurter API",
                )
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Currency conversion API error: {http_err}",
                source="Frankfurter API",
            )
        except Exception as exc:
            logger.exception("Error in CurrencyConversionTool: %s", exc)
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Failed to convert currency: {str(exc)}",
                source="Frankfurter API",
            )
