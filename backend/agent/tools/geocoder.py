import httpx
from config import NYC_OPEN_DATA_BASE, TOOL_TIMEOUT_S

# Use PLUTO dataset to reverse-geocode lat/lng to BBL
# PLUTO has latitude/longitude columns (not a geospatial the_geom column)
PLUTO_URL = f"{NYC_OPEN_DATA_BASE}/64uk-42ks.json"

# Approximate degree offset for ~100m at NYC latitude
_LAT_OFFSET = 0.0009
_LNG_OFFSET = 0.0012


def get_block_info(lat: float, lng: float) -> dict:
    """Convert latitude/longitude to NYC block info including BBL, address, and borough.

    Args:
        lat: Latitude of the location.
        lng: Longitude of the location.

    Returns:
        dict with bbl, address, borough, block, and lot. Returns error dict on failure.
    """
    try:
        # Use bounding box filter on latitude/longitude columns
        params = {
            "$where": (
                f"latitude >= {lat - _LAT_OFFSET} AND latitude <= {lat + _LAT_OFFSET} "
                f"AND longitude >= {lng - _LNG_OFFSET} AND longitude <= {lng + _LNG_OFFSET}"
            ),
            "$limit": 1,
            "$select": "bbl,address,borough,block,lot,zipcode,cd,latitude,longitude",
        }
        r = httpx.get(PLUTO_URL, params=params, timeout=TOOL_TIMEOUT_S)
        r.raise_for_status()
        data = r.json()

        if not data:
            return {"error": "Location outside NYC or no lot data found for these coordinates"}

        record = data[0]
        # Clean BBL: Socrata returns it as float string, convert to 10-digit int
        raw_bbl = record.get("bbl", "")
        bbl = str(int(float(raw_bbl))) if raw_bbl else None
        return {
            "bbl": bbl,
            "address": record.get("address"),
            "borough": record.get("borough"),
            "block": record.get("block"),
            "lot": record.get("lot"),
            "zipcode": record.get("zipcode"),
            "community_district": record.get("cd"),
        }
    except httpx.TimeoutException:
        return {"error": "Geocoder request timed out"}
    except Exception as e:
        return {"error": f"Geocoder failed: {str(e)}"}
