import os

# All tunable backend values in one place. Change here — nowhere else.

# --- Streaming ---
TOOL_TIMEOUT_S = 15         # Max seconds to wait for any single NYC Open Data tool call.
TOOLS_PARALLEL = True       # Run all 5 tools concurrently (asyncio.gather). Set False to debug sequentially.

# --- AR Labels ---
AR_LABELS_ENABLED = True    # Mirror of frontend flag. False = agent skips AR label generation (saves tokens).

# --- Session ---
MAX_STILLS_PER_SESSION = 12  # Cap on JPEG frames retained for the Synthesis Report.
SESSION_TIMEOUT_S = 3600     # Abandon session after 1 hour of inactivity.

# --- Report ---
REPORT_ID_PREFIX = "CS"      # Report IDs: CS-0001, CS-0002, etc.
PDF_MAX_STILLS = 6           # Max stills included in the PDF export.

# --- GPS ---
GPS_REQUIRED = True          # Master switch. If False, allows visual-only analysis (not recommended).

# --- API Keys ---
AIRNOW_API_KEY = os.getenv("AIRNOW_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# --- NYC Open Data Base URL ---
NYC_OPEN_DATA_BASE = "https://data.cityofnewyork.us/resource"
