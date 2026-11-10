from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

WMO: dict[int, str] = {
    0: "Clear",
    1: "Mostly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    56: "Freezing drizzle",
    57: "Freezing drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Freezing rain",
    67: "Freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Rain showers",
    81: "Rain showers",
    82: "Heavy showers",
    85: "Snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm",
    99: "Thunderstorm",
}


def weather_label(code: int | None) -> str:
    if code is None:
        return "Unavailable"
    return WMO.get(int(code), "Unavailable")


def _get_json(url: str, timeout: float = 12.0) -> Any:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "AssistDesktop/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def search_places(query: str, count: int = 6) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {"name": query, "count": count, "language": "en", "format": "json"}
    )
    data = _get_json(f"{GEOCODE_URL}?{params}")
    results = data.get("results") if isinstance(data, dict) else None
    return list(results) if isinstance(results, list) else []


def result_to_place(result: dict[str, Any]) -> dict[str, Any]:
    raw_id = result.get("id") or f"{result.get('latitude')},{result.get('longitude')}"
    slug = "-".join(
        [
            str(raw_id),
            str(result.get("name") or "place"),
            str(result.get("country_code") or ""),
        ]
    ).lower()
    place_id = "".join(ch if ch.isalnum() else "-" for ch in slug).strip("-")
    while "--" in place_id:
        place_id = place_id.replace("--", "-")

    return {
        "id": place_id or "place",
        "name": str(result.get("name") or "Place"),
        "admin": str(result.get("admin1") or ""),
        "country": str(result.get("country") or ""),
        "latitude": float(result["latitude"]),
        "longitude": float(result["longitude"]),
        "timezone": str(result.get("timezone") or "UTC"),
    }


def fetch_weather(places: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not places:
        return {}

    latitudes = ",".join(str(p["latitude"]) for p in places)
    longitudes = ",".join(str(p["longitude"]) for p in places)
    params = urllib.parse.urlencode(
        {
            "latitude": latitudes,
            "longitude": longitudes,
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "timezone": "auto",
        }
    )
    data = _get_json(f"{WEATHER_URL}?{params}")
    rows = data if isinstance(data, list) else [data]
    out: dict[str, dict[str, Any]] = {}

    for place, row in zip(places, rows):
        current = row.get("current") if isinstance(row, dict) else None
        if not isinstance(current, dict):
            continue
        out[place["id"]] = {
            "temperature": current.get("temperature_2m"),
            "humidity": current.get("relative_humidity_2m"),
            "weather_code": current.get("weather_code"),
            "wind": current.get("wind_speed_10m"),
        }
    return out


class WeatherError(RuntimeError):
    pass


def safe_search(query: str) -> list[dict[str, Any]]:
    try:
        return search_places(query)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise WeatherError(str(exc)) from exc


def safe_fetch_weather(places: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    try:
        return fetch_weather(places)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise WeatherError(str(exc)) from exc
