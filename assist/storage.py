from __future__ import annotations

import json
from pathlib import Path
from typing import Any

APP_DIR = Path.home() / ".assist"
PLACES_FILE = APP_DIR / "places.json"

DEFAULT_PLACES: list[dict[str, Any]] = [
    {
        "id": "tokyo",
        "name": "Tokyo",
        "admin": "Tokyo",
        "country": "Japan",
        "latitude": 35.6895,
        "longitude": 139.6917,
        "timezone": "Asia/Tokyo",
    },
    {
        "id": "san-francisco",
        "name": "San Francisco",
        "admin": "California",
        "country": "United States",
        "latitude": 37.7749,
        "longitude": -122.4194,
        "timezone": "America/Los_Angeles",
    },
    {
        "id": "london",
        "name": "London",
        "admin": "England",
        "country": "United Kingdom",
        "latitude": 51.5072,
        "longitude": -0.1276,
        "timezone": "Europe/London",
    },
]


def _normalize(raw: dict[str, Any]) -> dict[str, Any] | None:
    try:
        place = {
            "id": str(raw["id"]),
            "name": str(raw["name"]),
            "admin": str(raw.get("admin") or ""),
            "country": str(raw.get("country") or ""),
            "latitude": float(raw["latitude"]),
            "longitude": float(raw["longitude"]),
            "timezone": str(raw.get("timezone") or "UTC"),
        }
    except (KeyError, TypeError, ValueError):
        return None
    return place


def load_places() -> list[dict[str, Any]]:
    try:
        if not PLACES_FILE.exists():
            return [dict(p) for p in DEFAULT_PLACES]
        data = json.loads(PLACES_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, list) or not data:
            return [dict(p) for p in DEFAULT_PLACES]
        places = [p for p in (_normalize(item) for item in data) if p]
        return places or [dict(p) for p in DEFAULT_PLACES]
    except (OSError, json.JSONDecodeError):
        return [dict(p) for p in DEFAULT_PLACES]


def save_places(places: list[dict[str, Any]]) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    cleaned = [p for p in (_normalize(item) for item in places) if p]
    PLACES_FILE.write_text(json.dumps(cleaned, indent=2), encoding="utf-8")
