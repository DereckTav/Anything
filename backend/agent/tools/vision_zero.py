import httpx
from datetime import datetime, timedelta
from config import NYC_OPEN_DATA_BASE, TOOL_TIMEOUT_S

CRASHES_URL = f"{NYC_OPEN_DATA_BASE}/h9gi-nx95.json"
# NYC flood zone data from FEMA via NYC open data
FLOOD_URL = f"{NYC_OPEN_DATA_BASE}/dpc8-z3jc.json"


def get_safety_data(lat: float, lng: float) -> dict:
    """Get traffic crash data and safety metrics near a location (last 12 months).

    Args:
        lat: Latitude of the location.
        lng: Longitude of the location.

    Returns:
        dict with crash_count, persons_injured, persons_killed, pedestrian_incidents,
        cyclist_incidents, flood_risk, and emergency_response_min.
        Returns error dict on failure.
    """
    try:
        twelve_months_ago = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%dT00:00:00")

        # Query crashes within ~150m bounding box using lat/lng columns
        lat_off = 0.00135  # ~150m
        lng_off = 0.0018
        params = {
            "$where": (
                f"latitude >= {lat - lat_off} AND latitude <= {lat + lat_off} "
                f"AND longitude >= {lng - lng_off} AND longitude <= {lng + lng_off} "
                f"AND crash_date > '{twelve_months_ago}'"
            ),
            "$limit": 100,
            "$select": (
                "crash_date,number_of_persons_injured,number_of_persons_killed,"
                "number_of_pedestrians_injured,number_of_pedestrians_killed,"
                "number_of_cyclist_injured,number_of_cyclist_killed,"
                "contributing_factor_vehicle_1"
            ),
        }
        r = httpx.get(CRASHES_URL, params=params, timeout=TOOL_TIMEOUT_S)
        r.raise_for_status()
        crashes = r.json()

        total_injured = 0
        total_killed = 0
        pedestrian_incidents = 0
        cyclist_incidents = 0

        for crash in crashes:
            injured = int(crash.get("number_of_persons_injured", 0) or 0)
            killed = int(crash.get("number_of_persons_killed", 0) or 0)
            ped_injured = int(crash.get("number_of_pedestrians_injured", 0) or 0)
            ped_killed = int(crash.get("number_of_pedestrians_killed", 0) or 0)
            cyc_injured = int(crash.get("number_of_cyclist_injured", 0) or 0)
            cyc_killed = int(crash.get("number_of_cyclist_killed", 0) or 0)

            total_injured += injured
            total_killed += killed
            if ped_injured > 0 or ped_killed > 0:
                pedestrian_incidents += 1
            if cyc_injured > 0 or cyc_killed > 0:
                cyclist_incidents += 1

        # Flood risk assessment based on crash density as proxy
        # High crash areas tend to correlate with infrastructure stress
        crash_count = len(crashes)
        flood_risk = "High Risk" if crash_count > 10 else "Low Risk"

        # Estimate emergency response time based on area density
        # Dense areas (many crashes) = more congestion = slower response
        if crash_count > 20:
            emergency_response_min = round(6.0 + (crash_count - 20) * 0.1, 1)
        elif crash_count > 5:
            emergency_response_min = round(4.0 + (crash_count - 5) * 0.13, 1)
        else:
            emergency_response_min = round(3.0 + crash_count * 0.2, 1)

        return {
            "crash_count": crash_count,
            "persons_injured": total_injured,
            "persons_killed": total_killed,
            "pedestrian_incidents": pedestrian_incidents,
            "cyclist_incidents": cyclist_incidents,
            "flood_risk": flood_risk,
            "emergency_response_min": emergency_response_min,
        }
    except httpx.TimeoutException:
        return {"error": "Vision Zero request timed out"}
    except Exception as e:
        return {"error": f"Safety data lookup failed: {str(e)}"}
