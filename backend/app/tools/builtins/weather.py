"""Weather Tool for TARK AI using free Open-Meteo API. Zero API keys required."""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any, Dict, Type
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolExecutionContext, ToolPermission, ToolResult

logger = logging.getLogger(__name__)


class WeatherInput(BaseModel):
    location: str = Field(
        ...,
        description="City or location name to get weather for (e.g. 'Tokyo', 'London', 'New York', 'Mumbai').",
        min_length=1,
        max_length=100,
    )


class WeatherTool(BaseTool):
    name: str = "get_weather"
    description: str = (
        "Get current weather and 3-day forecast for a given location (temperature, humidity, wind, conditions). "
        "Use this whenever the user asks about current weather, temperature, rain, or forecast in any city."
    )
    permission: ToolPermission = ToolPermission.NETWORK
    input_schema: Type[BaseModel] = WeatherInput

    # WMO Weather interpretation codes
    WEATHER_CODES = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        71: "Slight snow fall",
        73: "Moderate snow fall",
        75: "Heavy snow fall",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        95: "Thunderstorm",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail",
    }

    async def execute(self, arguments: Dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        location = arguments.get("location", "").strip()
        if not location:
            return ToolResult(tool_name=self.name, success=False, error="Location is required.")

        try:
            # 1. Geocode location with Open-Meteo Geocoding API
            encoded_loc = urllib.parse.quote(location)
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded_loc}&count=1&language=en&format=json"

            req = urllib.request.Request(geo_url, headers={"User-Agent": "TarkAI-WeatherTool/1.0"})
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                geo_data = json.loads(resp.read().decode("utf-8"))

            results = geo_data.get("results")
            if not results or len(results) == 0:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error=f"Could not find coordinates for location '{location}'.",
                    source="open-meteo.com",
                )

            geo = results[0]
            lat = geo.get("latitude")
            lon = geo.get("longitude")
            place_name = f"{geo.get('name')}, {geo.get('country', '')}"
            timezone = geo.get("timezone", "auto")

            # 2. Fetch forecast
            forecast_url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m&"
                f"daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max&"
                f"timezone={urllib.parse.quote(timezone)}"
            )

            req_weather = urllib.request.Request(forecast_url, headers={"User-Agent": "TarkAI-WeatherTool/1.0"})
            with urllib.request.urlopen(req_weather, timeout=5.0) as resp:
                weather_data = json.loads(resp.read().decode("utf-8"))

            current = weather_data.get("current", {})
            weather_code = current.get("weather_code", 0)
            condition = self.WEATHER_CODES.get(weather_code, "Unknown")

            daily = weather_data.get("daily", {})
            forecast_days = []
            dates = daily.get("time", [])
            max_temps = daily.get("temperature_2m_max", [])
            min_temps = daily.get("temperature_2m_min", [])
            precip_probs = daily.get("precipitation_probability_max", [])
            codes = daily.get("weather_code", [])

            for i in range(min(3, len(dates))):
                forecast_days.append({
                    "date": dates[i] if i < len(dates) else "",
                    "max_temp_c": max_temps[i] if i < len(max_temps) else None,
                    "min_temp_c": min_temps[i] if i < len(min_temps) else None,
                    "precipitation_prob_percent": precip_probs[i] if i < len(precip_probs) else None,
                    "condition": self.WEATHER_CODES.get(codes[i] if i < len(codes) else 0, "Unknown"),
                })

            data = {
                "location": place_name,
                "latitude": lat,
                "longitude": lon,
                "current": {
                    "temperature_c": current.get("temperature_2m"),
                    "temperature_f": round(current.get("temperature_2m", 0) * 9 / 5 + 32, 1) if current.get("temperature_2m") is not None else None,
                    "feels_like_c": current.get("apparent_temperature"),
                    "humidity_percent": current.get("relative_humidity_2m"),
                    "wind_speed_kmh": current.get("wind_speed_10m"),
                    "precipitation_mm": current.get("precipitation"),
                    "condition": condition,
                },
                "forecast_3_day": forecast_days,
            }

            return ToolResult(
                tool_name=self.name,
                success=True,
                data=data,
                source=f"Open-Meteo ({place_name})",
            )

        except Exception as exc:
            logger.exception("Error in WeatherTool execution: %s", exc)
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Failed to fetch weather for '{location}': {str(exc)}",
                source="open-meteo.com",
            )
