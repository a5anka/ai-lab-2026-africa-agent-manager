"""Hotel concierge tools.

Each tool validates input defensively and returns either a result dict or
{"error": "<reason>"}. Tools never raise into the agent loop.
"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.tools import tool

from hotel_data import MENU, RECOMMENDATIONS, ROOMS

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def check_room_availability(
    room_type: str,
    check_in: str | None = None,
    nights: int | None = None,
) -> dict[str, Any]:
    """Check availability and price for hotel rooms.

    Args:
        room_type: One of: honeymoon, deluxe, standard, junior, presidential.
        check_in: Check-in date (YYYY-MM-DD). Optional.
        nights: Number of nights. Optional, defaults to 1.
    """
    if not isinstance(room_type, str) or room_type not in ROOMS:
        return {"error": f"Unknown room type. Available: {', '.join(ROOMS.keys())}."}
    if check_in is not None and not _ISO_DATE.match(check_in):
        return {"error": "Check-in date must be in YYYY-MM-DD format."}
    n = 1 if nights is None else nights
    if not isinstance(n, int) or n < 1 or n > 30:
        return {"error": "Nights must be an integer between 1 and 30."}

    room = ROOMS[room_type]
    return {
        "room_type": room_type,
        "name": room["name"],
        "price_per_night_usd": room["price_per_night_usd"],
        "nights": n,
        "total_usd": room["price_per_night_usd"] * n,
        "size_sqft": room["size_sqft"],
        "description": room["description"],
        "available": True,
        "check_in": check_in,
    }


def get_room_service_menu(vegetarian_only: bool | None = None) -> dict[str, Any]:
    """Return the room service menu.

    Args:
        vegetarian_only: Filter to vegetarian items only. Optional.
    """
    veg = bool(vegetarian_only)
    items = [m for m in MENU if (not veg) or m["vegetarian"]]
    return {
        "items": items,
        "filtered": "vegetarian_only" if veg else "none",
        "count": len(items),
    }


def get_local_recommendations(category: str) -> dict[str, Any]:
    """Return curated recommendations near the hotel by category.

    Args:
        category: One of: restaurants, family, nightlife, outdoors.
    """
    if not isinstance(category, str) or category not in RECOMMENDATIONS:
        return {
            "error": f"Unknown category. Available: {', '.join(RECOMMENDATIONS.keys())}."
        }
    return {
        "category": category,
        "recommendations": RECOMMENDATIONS[category],
        "count": len(RECOMMENDATIONS[category]),
    }


# Wrap with tool() rather than @tool decorator so the underlying functions
# remain directly callable from tests.
LANGCHAIN_TOOLS = [
    tool(check_room_availability),
    tool(get_room_service_menu),
    tool(get_local_recommendations),
]
