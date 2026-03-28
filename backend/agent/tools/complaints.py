import httpx
from datetime import datetime, timedelta
from config import NYC_OPEN_DATA_BASE, TOOL_TIMEOUT_S

COMPLAINTS_URL = f"{NYC_OPEN_DATA_BASE}/erm2-nwe9.json"


def get_311_complaints(lat: float, lng: float, radius_meters: int = 200) -> dict:
    """Get recent 311 complaints near a location (last 90 days).

    Args:
        lat: Latitude of the location.
        lng: Longitude of the location.
        radius_meters: Search radius in meters (default 200).

    Returns:
        dict with total_count, complaint_types (counts by type), and top_complaints list.
        Returns error dict on failure.
    """
    try:
        ninety_days_ago = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%dT00:00:00")
        # ~200m bounding box using lat/lng columns
        lat_off = radius_meters * 0.000009
        lng_off = radius_meters * 0.000012
        geo_filter = (
            f"latitude >= {lat - lat_off} AND latitude <= {lat + lat_off} "
            f"AND longitude >= {lng - lng_off} AND longitude <= {lng + lng_off}"
        )
        date_filter = f"created_date > '{ninety_days_ago}'"

        params = {
            "$where": f"{geo_filter} AND {date_filter}",
            "$limit": 50,
            "$order": "created_date DESC",
            "$select": "complaint_type,descriptor,created_date,resolution_description,status",
        }
        r = httpx.get(COMPLAINTS_URL, params=params, timeout=TOOL_TIMEOUT_S)
        r.raise_for_status()
        data = r.json()

        if not data:
            return {
                "total_count": 0,
                "complaint_types": {},
                "top_complaints": [],
            }

        # Count by type
        type_counts = {}
        for record in data:
            ctype = record.get("complaint_type", "Unknown")
            type_counts[ctype] = type_counts.get(ctype, 0) + 1

        # Top complaints with details
        top_complaints = []
        for record in data[:10]:
            top_complaints.append({
                "type": record.get("complaint_type", "Unknown"),
                "description": record.get("descriptor", "No description"),
                "created_date": record.get("created_date"),
                "status": record.get("status"),
            })

        return {
            "total_count": len(data),
            "complaint_types": type_counts,
            "top_complaints": top_complaints,
        }
    except httpx.TimeoutException:
        return {"error": "311 complaints request timed out"}
    except Exception as e:
        return {"error": f"311 lookup failed: {str(e)}"}
