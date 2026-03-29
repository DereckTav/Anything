import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ── POI Discovery ──
POI_CHIPS_MAX           = 5      # Max chips shown on screen at once.

# ── Tools ──
TOOL_TIMEOUT_S          = 8      # Per-tool HTTP timeout in seconds.

# ── GPS ──

GPS_REQUIRED            = True   # Require GPS for POI queries.

# ── API Keys ──
GOOGLE_API_KEY          = os.getenv("GOOGLE_API_KEY", "")
