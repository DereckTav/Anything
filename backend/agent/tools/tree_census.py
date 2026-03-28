import httpx
from config import NYC_OPEN_DATA_BASE, TOOL_TIMEOUT_S

TREES_URL = f"{NYC_OPEN_DATA_BASE}/uvpi-gqnh.json"


def get_canopy_data(lat: float, lng: float, radius_meters: int = 150) -> dict:
    """Get street tree data near a location from the NYC Tree Census.

    Args:
        lat: Latitude of the location.
        lng: Longitude of the location.
        radius_meters: Search radius in meters (default 150).

    Returns:
        dict with street_trees count, canopy_pct estimate, species list,
        health_distribution, and top_species.
        Returns error dict on failure.
    """
    try:
        # Bounding box using lat/lng columns
        lat_off = radius_meters * 0.000009
        lng_off = radius_meters * 0.000012
        params = {
            "$where": (
                f"latitude >= {lat - lat_off} AND latitude <= {lat + lat_off} "
                f"AND longitude >= {lng - lng_off} AND longitude <= {lng + lng_off}"
            ),
            "$limit": 200,
            "$select": "spc_common,health,tree_dbh,status",
        }
        r = httpx.get(TREES_URL, params=params, timeout=TOOL_TIMEOUT_S)
        r.raise_for_status()
        data = r.json()

        if not data:
            return {
                "street_trees": 0,
                "canopy_pct": 0,
                "species": [],
                "health_distribution": {},
                "top_species": [],
            }

        # Count trees and analyze
        tree_count = len(data)
        health_counts = {}
        species_counts = {}
        total_dbh = 0

        for tree in data:
            health = tree.get("health", "Unknown") or "Unknown"
            health_counts[health] = health_counts.get(health, 0) + 1

            species = tree.get("spc_common", "Unknown") or "Unknown"
            species_counts[species] = species_counts.get(species, 0) + 1

            dbh = tree.get("tree_dbh")
            if dbh:
                total_dbh += int(dbh)

        # Estimate canopy coverage: rough approximation based on tree count
        # and average diameter at breast height in the search area
        area_sqm = 3.14159 * (radius_meters ** 2)
        avg_dbh_inches = total_dbh / tree_count if tree_count > 0 else 0
        avg_canopy_radius_m = avg_dbh_inches * 0.0254 * 5  # rough canopy spread estimate
        total_canopy_sqm = tree_count * 3.14159 * (avg_canopy_radius_m ** 2)
        canopy_pct = min(int((total_canopy_sqm / area_sqm) * 100), 100) if area_sqm > 0 else 0

        # Top species
        top_species = sorted(species_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "street_trees": tree_count,
            "canopy_pct": canopy_pct,
            "health_distribution": health_counts,
            "top_species": [{"species": s, "count": c} for s, c in top_species],
        }
    except httpx.TimeoutException:
        return {"error": "Tree census request timed out"}
    except Exception as e:
        return {"error": f"Tree census lookup failed: {str(e)}"}
