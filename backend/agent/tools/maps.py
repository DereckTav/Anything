"""
Google Maps tools.
- get_distance: walking distance between two GPS points (Distance Matrix API with haversine fallback)
- build_maps_url: deep-link that opens Google Maps with walking directions
"""

import math
from urllib.parse import quote
import httpx
from config import GOOGLE_API_KEY, TOOL_TIMEOUT_S


def _haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Straight-line distance in meters using Haversine formula."""
    R = 6_371_000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def get_distance(origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float) -> dict:
    """
    Get walking distance and time from the tourist's current location to a destination.
    Use this to tell the tourist how far away a place is and how long it will take to walk there.

    Args:
        origin_lat: Tourist's current latitude
        origin_lng: Tourist's current longitude
        dest_lat: Destination latitude
        dest_lng: Destination longitude
    """
    # Try Google Maps Distance Matrix API first
    if GOOGLE_API_KEY:
        try:
            url = "https://maps.googleapis.com/maps/api/distancematrix/json"
            params = {
                "origins": f"{origin_lat},{origin_lng}",
                "destinations": f"{dest_lat},{dest_lng}",
                "mode": "walking",
                "key": GOOGLE_API_KEY,
            }
            with httpx.Client(timeout=TOOL_TIMEOUT_S) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

            if data.get("status") == "OK":
                element = data["rows"][0]["elements"][0]
                if element.get("status") == "OK":
                    return {
                        "distance_m": element["distance"]["value"],
                        "duration_min": round(element["duration"]["value"] / 60, 1),
                        "duration_text": element["duration"]["text"],
                        "source": "google_maps",
                    }
        except Exception:
            pass  # Fall through to haversine

    # Haversine fallback (no API key or Maps API error)
    dist_m = _haversine_meters(origin_lat, origin_lng, dest_lat, dest_lng)
    # Walking speed ~80 m/min (relaxed tourist pace)
    walk_min = dist_m / 80.0
    if walk_min < 1:
        duration_text = "under 1 min walk"
    elif walk_min < 2:
        duration_text = "1 min walk"
    else:
        duration_text = f"{int(round(walk_min))} min walk"

    return {
        "distance_m": round(dist_m),
        "duration_min": round(walk_min, 1),
        "duration_text": duration_text,
        "source": "estimated",
    }


def build_maps_url(dest_name: str, dest_lat: float, dest_lng: float) -> dict:
    """
    Build a Google Maps deep-link URL so the tourist can navigate to a destination.
    Use this when the tourist says they want to go somewhere or asks for directions.
    The URL opens Google Maps with walking directions pre-loaded.

    Args:
        dest_name: Name of the destination (e.g. "Jane's Carousel")
        dest_lat: Destination latitude
        dest_lng: Destination longitude
    """
    encoded_name = quote(dest_name)
    # This URL opens Google Maps (app or browser) with walking directions
    maps_url = (
        f"https://www.google.com/maps/dir/?api=1"
        f"&destination={dest_lat},{dest_lng}"
        f"&travelmode=walking"
        f"&destination_place={encoded_name}"
    )
    return {
        "maps_url": maps_url,
        "destination": dest_name,
        "lat": dest_lat,
        "lng": dest_lng,
    }
