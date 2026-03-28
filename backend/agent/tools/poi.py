"""
Points of Interest tool using OpenStreetMap Overpass API.

The NYC Open Data POI dataset (rxuy-2muj) currently returns empty rows, so we use
the free OpenStreetMap Overpass API instead, which has richer and up-to-date data.
No API key required.
"""

import math
import httpx
from config import TOOL_TIMEOUT_S


def _dist_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine distance in metres."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2
         + math.cos(phi1) * math.cos(phi2)
         * math.sin(math.radians(lng2 - lng1) / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))

# Overpass API endpoint
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# OSM tourism/amenity/historic values that are tourist-relevant
_TOURIST_QUERY = """[out:json][timeout:{timeout}];
(
  node["tourism"~"attraction|museum|gallery|artwork|viewpoint|historic|monument|memorial"](around:{radius},{lat},{lng});
  node["historic"](around:{radius},{lat},{lng});
  node["amenity"~"theatre|cinema|library|community_centre|arts_centre|place_of_worship"](around:{radius},{lat},{lng});
  node["leisure"~"park|garden|playground|nature_reserve"](around:{radius},{lat},{lng});
  way["leisure"~"park|garden|nature_reserve"]["name"](around:{radius},{lat},{lng});
);
out body center;
"""

# Human-friendly type labels
_TYPE_MAP = {
    "attraction":        "Tourist Attraction",
    "museum":            "Museum",
    "gallery":           "Art Gallery",
    "artwork":           "Public Art",
    "viewpoint":         "Viewpoint",
    "monument":          "Monument",
    "memorial":          "Memorial",
    "historic":          "Historic Site",
    "theatre":           "Theatre",
    "cinema":            "Cinema",
    "library":           "Library",
    "community_centre":  "Community Center",
    "arts_centre":       "Arts Center",
    "place_of_worship":  "Landmark",
    "park":              "Park",
    "garden":            "Garden",
    "playground":        "Playground",
    "nature_reserve":    "Nature Reserve",
}


def get_nearby_pois(lat: float, lng: float, radius_meters: int = 500) -> dict:
    """
    Get Points of Interest near a GPS location in Brooklyn.
    Returns up to 20 nearby tourist-relevant places with names, types, and coordinates.
    Use this whenever the tourist asks what is nearby, what to see, or where to go.

    Args:
        lat: Latitude of the tourist's current location
        lng: Longitude of the tourist's current location
        radius_meters: Search radius in meters (default 500 ≈ 6 min walk)
    """
    try:
        query = _TOURIST_QUERY.format(
            lat=lat,
            lng=lng,
            radius=radius_meters,
            timeout=max(8, TOOL_TIMEOUT_S - 1),
        )

        with httpx.Client(timeout=TOOL_TIMEOUT_S + 2) as client:
            response = client.post(OVERPASS_URL, data=query)
            response.raise_for_status()
            data = response.json()

        seen_names = set()
        pois = []

        for element in data.get("elements", []):
            tags = element.get("tags", {})
            name = tags.get("name", "").strip()
            if not name or name in seen_names:
                continue
            seen_names.add(name)

            # Get coordinates (nodes have lat/lng directly; ways have center)
            if element["type"] == "node":
                poi_lat = element.get("lat")
                poi_lng = element.get("lon")
            elif element["type"] == "way":
                center = element.get("center", {})
                poi_lat = center.get("lat")
                poi_lng = center.get("lon")
            else:
                continue

            if poi_lat is None or poi_lng is None:
                continue

            # Determine human-readable type
            poi_type = "Point of Interest"
            for key in ("tourism", "historic", "amenity", "leisure"):
                val = tags.get(key, "")
                if val in _TYPE_MAP:
                    poi_type = _TYPE_MAP[val]
                    break
                elif val:
                    poi_type = val.replace("_", " ").title()
                    break

            address_parts = []
            if tags.get("addr:housenumber") and tags.get("addr:street"):
                address_parts.append(f"{tags['addr:housenumber']} {tags['addr:street']}")
            elif tags.get("addr:street"):
                address_parts.append(tags["addr:street"])
            address = ", ".join(address_parts) if address_parts else ""

            dist = _dist_m(lat, lng, poi_lat, poi_lng)
            walk_min = round(dist / 80)  # ~80 m/min tourist pace

            pois.append({
                "name":       name,
                "type":       poi_type,
                "address":    address,
                "lat":        poi_lat,
                "lng":        poi_lng,
                "distance_m": round(dist),
                "walk_min":   walk_min,
            })

        # Sort closest first, then cap
        pois.sort(key=lambda p: p["distance_m"])
        pois = pois[:20]

        return {"pois": pois, "count": len(pois), "radius_meters": radius_meters}

    except httpx.TimeoutException:
        return {"error": "POI request timed out", "pois": []}
    except Exception as e:
        return {"error": str(e), "pois": []}
