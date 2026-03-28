import httpx
from config import NYC_OPEN_DATA_BASE, TOOL_TIMEOUT_S

PLUTO_URL = f"{NYC_OPEN_DATA_BASE}/64uk-42ks.json"


def get_zoning_data(bbl: str) -> dict:
    """Get PLUTO zoning, FAR, lot area, year built for a NYC tax lot.

    Args:
        bbl: NYC Borough-Block-Lot identifier (10 digits).

    Returns:
        dict with zoning, far, lot_area_sqft, year_built, land_use, address.
        Returns error dict if not found or on failure.
    """
    try:
        params = {"bbl": bbl, "$limit": 1}
        r = httpx.get(PLUTO_URL, params=params, timeout=TOOL_TIMEOUT_S)
        r.raise_for_status()
        data = r.json()

        if not data:
            return {"error": "No PLUTO data found for this location"}

        record = data[0]
        far_val = record.get("far")
        return {
            "zoning": record.get("zonedist1"),
            "far": float(far_val) if far_val else None,
            "lot_area_sqft": record.get("lotarea"),
            "year_built": record.get("yearbuilt"),
            "land_use": record.get("landuse"),
            "address": record.get("address"),
            "num_floors": record.get("numfloors"),
            "units_total": record.get("unitstotal"),
            "building_class": record.get("bldgclass"),
        }
    except httpx.TimeoutException:
        return {"error": "PLUTO request timed out"}
    except Exception as e:
        return {"error": f"PLUTO lookup failed: {str(e)}"}
