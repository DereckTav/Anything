import httpx
from config import AIRNOW_API_KEY, TOOL_TIMEOUT_S

AIRNOW_URL = "https://www.airnowapi.org/aq/observation/latLong/current/"


def get_air_quality(lat: float, lng: float) -> dict:
    """Get current air quality index (AQI) for a location using AirNow API.

    Args:
        lat: Latitude of the location.
        lng: Longitude of the location.

    Returns:
        dict with aqi (int), aqi_category (str), pollutant, and observation_time.
        Returns error dict on failure.
    """
    if not AIRNOW_API_KEY:
        return {"error": "API key required"}

    try:
        params = {
            "format": "application/json",
            "latitude": lat,
            "longitude": lng,
            "distance": 25,
            "API_KEY": AIRNOW_API_KEY,
        }
        r = httpx.get(AIRNOW_URL, params=params, timeout=TOOL_TIMEOUT_S)
        r.raise_for_status()
        data = r.json()

        if not data:
            return {"error": "No AQI data available for this location"}

        # Find the primary pollutant (highest AQI)
        primary = max(data, key=lambda x: x.get("AQI", 0))

        return {
            "aqi": int(primary.get("AQI", 0)),
            "aqi_category": primary.get("Category", {}).get("Name", "Unknown"),
            "pollutant": primary.get("ParameterName", "Unknown"),
            "observation_time": primary.get("DateObserved", ""),
        }
    except httpx.TimeoutException:
        return {"error": "AQI data unavailable"}
    except Exception as e:
        return {"error": f"AQI lookup failed: {str(e)}"}
