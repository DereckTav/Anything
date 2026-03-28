import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ── POI Discovery ──
POI_RADIUS_METERS       = 500    # Search radius. 500m ≈ 6 min walk at tourist pace.
POI_MAX_RESULTS         = 20     # Max POIs returned per query.
POI_CHIPS_MAX           = 5      # Max chips shown on screen at once.

# ── Vision ──
VISION_ENABLED          = True   # Kill switch. Set False to skip Vision API calls.

# ── Maps ──
MAPS_TRAVEL_MODE        = "walking"

# ── Tools ──
TOOL_TIMEOUT_S          = 8      # Per-tool HTTP timeout in seconds.
TOOLS_PARALLEL          = True   # Run tools concurrently where possible.

# ── Session ──
SESSION_TIMEOUT_S       = 7200   # 2 hours (tourist exploring for a day).

# ── GPS ──
GPS_REQUIRED            = True   # Require GPS for POI queries.

# ── API Keys ──
GOOGLE_API_KEY          = os.getenv("GOOGLE_API_KEY", "")

# ── NYC Open Data ──
NYC_OPEN_DATA_BASE      = "https://data.cityofnewyork.us/resource"
