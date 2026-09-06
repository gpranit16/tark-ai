"""Cryptocurrency Price Tool for TARK AI using public CoinGecko API. Zero API keys required."""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Type
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolExecutionContext, ToolPermission, ToolResult

logger = logging.getLogger(__name__)


class CryptoPriceInput(BaseModel):
    symbol: str = Field(
        ...,
        description="Cryptocurrency symbol or name (e.g. 'BTC', 'ETH', 'SOL', 'bitcoin', 'ethereum', 'dogecoin').",
        min_length=1,
        max_length=50,
    )
    vs_currency: str = Field(
        default="USD",
        description="Target comparison currency ISO code (e.g. 'USD', 'EUR', 'INR', 'GBP').",
        min_length=3,
        max_length=4,
    )


class CryptoPriceTool(BaseTool):
    name: str = "get_crypto_price"
    description: str = (
        "Get current market price, 24-hour price change percentage, 24-hour volume, and market cap for any cryptocurrency. "
        "Use this whenever the user asks about cryptocurrency prices (Bitcoin, Ethereum, Solana, Altcoins, etc.)."
    )
    permission: ToolPermission = ToolPermission.NETWORK
    input_schema: Type[BaseModel] = CryptoPriceInput

    # Common symbol mappings to CoinGecko IDs
    COINGECKO_MAP = {
        "btc": "bitcoin",
        "bitcoin": "bitcoin",
        "eth": "ethereum",
        "ethereum": "ethereum",
        "sol": "solana",
        "solana": "solana",
        "bnb": "binancecoin",
        "binancecoin": "binancecoin",
        "xrp": "ripple",
        "ripple": "ripple",
        "ada": "cardano",
        "cardano": "cardano",
        "doge": "dogecoin",
        "dogecoin": "dogecoin",
        "dot": "polkadot",
        "polkadot": "polkadot",
        "avax": "avalanche-2",
        "avalanche": "avalanche-2",
        "link": "chainlink",
        "chainlink": "chainlink",
        "matic": "matic-network",
        "polygon": "matic-network",
        "usdt": "tether",
        "tether": "tether",
        "usdc": "usd-coin",
    }

    async def execute(self, arguments: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        raw_symbol = arguments.get("symbol", "").lower().strip()
        vs_currency = arguments.get("vs_currency", "USD").lower().strip()

        if not raw_symbol:
            return ToolResult(tool_name=self.name, success=False, error="Crypto symbol or name is required.")

        coin_id = self.COINGECKO_MAP.get(raw_symbol, raw_symbol)

        try:
            url = (
                f"https://api.coingecko.com/api/v3/simple/price?"
                f"ids={urllib.parse.quote(coin_id)}&vs_currencies={urllib.parse.quote(vs_currency)}&"
                f"include_24hr_vol=true&include_24hr_change=true&include_market_cap=true"
            )

            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "TarkAI-CryptoTool/1.0",
                    "Accept": "application/json",
                },
            )

            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            coin_data = data.get(coin_id)
            if not coin_data:
                # Fallback: search coin search endpoint
                search_url = f"https://api.coingecko.com/api/v3/search?query={urllib.parse.quote(raw_symbol)}"
                search_req = urllib.request.Request(search_url, headers={"User-Agent": "TarkAI-CryptoTool/1.0"})
                with urllib.request.urlopen(search_req, timeout=5.0) as s_resp:
                    s_data = json.loads(s_resp.read().decode("utf-8"))
                    coins = s_data.get("coins", [])
                    if coins and len(coins) > 0:
                        resolved_id = coins[0].get("id")
                        if resolved_id:
                            # Retry with resolved id
                            retry_url = (
                                f"https://api.coingecko.com/api/v3/simple/price?"
                                f"ids={urllib.parse.quote(resolved_id)}&vs_currencies={urllib.parse.quote(vs_currency)}&"
                                f"include_24hr_vol=true&include_24hr_change=true&include_market_cap=true"
                            )
                            with urllib.request.urlopen(urllib.request.Request(retry_url, headers={"User-Agent": "TarkAI-CryptoTool/1.0"}), timeout=5.0) as r_resp:
                                r_data = json.loads(r_resp.read().decode("utf-8"))
                                coin_data = r_data.get(resolved_id)
                                coin_id = resolved_id

            if not coin_data:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error=f"Cryptocurrency '{raw_symbol}' not found on CoinGecko.",
                    source="CoinGecko API",
                )

            price = coin_data.get(vs_currency)
            change_24h = coin_data.get(f"{vs_currency}_24h_change")
            vol_24h = coin_data.get(f"{vs_currency}_24h_vol")
            market_cap = coin_data.get(f"{vs_currency}_market_cap")

            result_data = {
                "coin": coin_id,
                "symbol": raw_symbol.upper(),
                "price": price,
                "currency": vs_currency.upper(),
                "change_24h_percent": round(change_24h, 2) if change_24h is not None else None,
                "volume_24h": round(vol_24h, 2) if vol_24h is not None else None,
                "market_cap": round(market_cap, 2) if market_cap is not None else None,
            }

            return ToolResult(
                tool_name=self.name,
                success=True,
                data=result_data,
                source=f"CoinGecko ({coin_id})",
            )

        except Exception as exc:
            logger.exception("Error in CryptoPriceTool: %s", exc)
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Failed to fetch crypto price for '{raw_symbol}': {str(exc)}",
                source="CoinGecko API",
            )
