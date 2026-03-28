# CITYSCOPE — Test Plan

## How to Use This Document

| Who | When | What to do |
|-----|------|------------|
| Claude (me) | While coding | Check boxes as each piece is built; run data shape validators after each tool |
| You (manual QA) | After each phase | Run the frontend screen checklists + end-to-end flows on a real device |
| Both | After any change | Re-run the section relevant to what changed (regression) |

Check off items with `[x]` as they pass. Leave `[ ]` for anything that's failing or not yet built.

---

## 1. Tool Tests (`backend/agent/tools/`)

Each tool can be tested in isolation. Run from the `backend/` directory with:
```bash
python -c "from agent.tools.pluto import get_zoning_data; print(get_zoning_data('1000477501'))"
```

### PLUTO (`pluto.py`)
- [ ] Known good BBL `1000477501` (Manhattan) → returns `zoning`, `far` (float), `address` (non-null)
- [ ] Invalid BBL `0000000000` → returns `{"error": "..."}`, does NOT raise an exception
- [ ] BBL with no data → returns `{"error": "No PLUTO data found..."}`, does NOT crash
- [ ] Response time < 3 seconds

### 311 (`complaints.py`)
- [ ] `lat=40.7580, lng=-73.9855` (Times Square) → returns list of complaints, each has `type` and `description`
- [ ] Results are from last 90 days — spot-check `created_date` on at least 1 result
- [ ] `lat=40.5000, lng=-74.5000` (ocean off NJ) → returns empty list, does NOT crash
- [ ] Response time < 3 seconds

### Vision Zero (`vision_zero.py`)
- [ ] `lat=40.7484, lng=-73.9967` (busy Midtown intersection) → returns `flood_risk` ("High Risk" or "Low Risk") and `emergency_response_min` (positive float)
- [ ] Low-traffic residential coords → returns zeroed/empty dict, does NOT crash or return negative numbers
- [ ] Response time < 3 seconds

### Tree Census (`tree_census.py`)
- [ ] `lat=40.7282, lng=-73.7949` (Queens residential street) → `canopy_pct` is int 0–100, at least 1 tree returned
- [ ] Industrial zone coords → returns `{"street_trees": 0, ...}`, does NOT crash
- [ ] Response time < 3 seconds

### AQI (`air_quality.py`)
- [ ] Any valid NYC coords → `aqi` is an int, `aqi_category` is one of: `Good` / `Moderate` / `Unhealthy for Sensitive Groups` / `Unhealthy` / `Very Unhealthy` / `Hazardous`
- [ ] Missing `AIRNOW_API_KEY` env var → returns `{"error": "API key required"}`, does NOT crash
- [ ] AirNow timeout (mock slow response) → returns `{"error": "AQI data unavailable"}` within 5 seconds
- [ ] Response time < 5 seconds (AirNow can be slow)

### Geocoder (`geocoder.py`)
- [ ] `lat=40.7484, lng=-73.9967` → returns a valid 10-digit BBL string (digits only, no spaces or dashes)
- [ ] Coords outside NYC → returns `{"error": "Location outside NYC"}`, does NOT crash
- [ ] Response time < 2 seconds

---

## 2. Agent Behavior Tests

Run the agent locally with `adk web` and send test messages, or use a Python test script.

### GPS Enforcement
- [ ] Send `frame` message with **no `gps` field** → response is `{"type": "gps_required", ...}`, NO narration text
- [ ] Send `frame` message with `"gps": null` → same result
- [ ] Send `frame` with valid GPS → analysis proceeds normally

### Tool Calls
- [ ] Send valid frame + GPS → verify in ADK logs that **all 5 tools** were called (PLUTO, 311, Vision Zero, Trees, AQI)
- [ ] Mock one tool to return a 503 error → agent narrates using the other 4 data sources and explicitly mentions the unavailable source ("...though I couldn't retrieve [X] data at this moment")

### AR Label Schema
- [ ] Agent response includes an `ar_labels` array
- [ ] Each label has exactly 3 keys: `source`, `text`, `position`
- [ ] `source` is one of: `PLUTO`, `311`, `PARKS`, `SAFETY`, `AQI`
- [ ] `position` is one of: `top-left`, `top-right`, `mid-left`, `mid-right`, `bottom-left`, `bottom-right`
- [ ] `text` is a non-empty string
- [ ] Run 3 frames — all labels parse without errors (use `validate_ar_labels()` from Section 6)

### Narration Quality
- [ ] Each narration chunk is ≤ 4 sentences (target: 2–3)
- [ ] After 3+ frames, agent has asked the client at least 1 direct question
- [ ] Agent does NOT use phrases like "As an AI..." or "As a documentary narrator..."
- [ ] Send a solid black/blank frame with valid GPS → narration references only tool data, makes no visual claims about "the building I can see"

### Grounding / No Hallucination
- [ ] Every number stated in narration (FAR, crash count, AQI, tree count) matches tool output
- [ ] Mock PLUTO returning ambiguous `land_use` → agent asks client a clarifying question rather than stating a definitive interpretation

---

## 3. WebSocket Protocol Tests

Install `wscat`: `npm install -g wscat`

Connect locally: `wscat -c ws://localhost:8080/ws/analyze`

### `frame` message — happy path
```json
{"type": "frame", "image_b64": "<valid_jpeg_b64>", "gps": {"lat": 40.7484, "lng": -73.9967}}
```
- [ ] Response arrives within 10 seconds
- [ ] Response has `type: "narration"`
- [ ] Response has `text` (non-empty string)
- [ ] Response has `ar_labels` (valid array, may be empty)

### `frame` message — missing GPS
```json
{"type": "frame", "image_b64": "<b64>"}
```
- [ ] Response has `type: "gps_required"`
- [ ] No `narration` response follows
- [ ] Server does NOT crash

### `pause` message
```json
{"type": "pause"}
```
(Send after at least 1 frame has been processed)
- [ ] Response has `type: "layer_data"`
- [ ] Response has all 4 keys: `zoning`, `environment`, `safety`, `activity_311`
- [ ] `zoning.district` is a non-null string
- [ ] `zoning.far` is a non-null float
- [ ] `environment.aqi` is an int
- [ ] `environment.aqi_category` is one of the 6 valid AQI strings
- [ ] `safety.flood_risk` is "High Risk" or "Low Risk"
- [ ] `activity_311.complaints` is an array (may be empty)
- [ ] Response arrives within 5 seconds

### `end` message
```json
{"type": "end"}
```
(Send after at least 3 frames)
- [ ] Response has `type: "report"`
- [ ] Response has `id` starting with `"CS-"`
- [ ] Response has `narrative` — array of `{timestamp, text}` objects
- [ ] `narrative` has at least 1 entry
- [ ] Response has `score` — float between 0 and 10
- [ ] Response has `verdict` — non-empty string
- [ ] Response arrives within 8 seconds

### Error handling
- [ ] Send `not valid json` → response is `{"type": "error", "message": "..."}`, server does NOT crash
- [ ] Open connection, send 2 frames, abruptly close without `end` → server cleans up gracefully (no error in logs, no hung process)

---

## 4. Frontend Screen Tests

Open each screen in a browser (Chrome DevTools open, mobile simulation on).

### Active Analysis (`screens/active-analysis.html`)

**Camera**
- [ ] On mobile: rear camera activates (`facingMode: "environment"`) — check in DevTools Application → Permissions
- [ ] On desktop: available camera activates
- [ ] Camera denied: clear error message shown, not blank screen

**GPS Gate**
- [ ] Location permission prompt appears before analysis starts
- [ ] GPS denied: full-screen blocking message: "Location required — please enable GPS to continue"
- [ ] No frames sent to backend while GPS is blocked (check Network → WS tab in DevTools)
- [ ] Analysis starts after GPS is granted

**AR Labels**
- [ ] After first narration, ≥ 1 AR label chip appears on screen
- [ ] Each chip shows `[SOURCE]` in Space Mono + label text in Manrope
- [ ] Left border line is warm cream (`#D4C3A3`)
- [ ] `.ar-line` gradient connector is visible below/beside chip
- [ ] Labels fade out after ~8 seconds if no new frame response
- [ ] Labels refresh (not duplicated) with each new narration cycle

**Subtitles**
- [ ] Narration text appears at bottom of screen (above bottom nav)
- [ ] Font is Newsreader italic
- [ ] Text wraps correctly, no overflow
- [ ] New subtitle replaces old one cleanly

**Top Bar**
- [ ] "CITYSCOPE" visible top-left
- [ ] LAT/LNG updates as device moves
- [ ] Format: "LAT: 40.7128 N" / "LNG: 74.0060 W"

**Bottom Nav**
- [ ] 4 buttons: VOICE · CAM · INSPECT · STOP
- [ ] INSPECT is highlighted (cream color, slightly larger)
- [ ] Tapping INSPECT → transitions to Layer Inspector
- [ ] Tapping STOP → transitions to Synthesis Report

**Desktop Side HUD**
- [ ] Hidden on screen width < `md` breakpoint
- [ ] Visible at `md` and above
- [ ] "AI ACTIVE STREAM" text is vertical (`writing-mode: vertical-rl`)

---

### Layer Inspector (`screens/layer-inspector.html`)

**Background**
- [ ] Paused video frame is visible (not black)
- [ ] Frame has grayscale + contrast filter applied
- [ ] Dark translucent overlay covers the frame

**Header**
- [ ] "Intelligence Overlay" in small uppercase monospace
- [ ] "Contextual Breakdown" in large italic serif
- [ ] GPS coordinates shown below title

**Resume Button**
- [ ] Top-right, warm cream background (`bg-primary`)
- [ ] Dark text on button
- [ ] Tapping resumes live camera and returns to Active Analysis

**Zoning Card**
- [ ] Title: "Zoning" with `layers` icon
- [ ] Shows district (e.g., "R7A") and FAR (e.g., "4.0 FAR")
- [ ] Italic description text at bottom of card

**Environment Card**
- [ ] Title: "Environment" with `air` icon
- [ ] Shows canopy % with a thin progress bar
- [ ] Shows AQI number + category label (e.g., "42 GOOD")

**Safety Card**
- [ ] Title: "Safety" with `security` icon (in error/red color)
- [ ] "High Risk" flood vulnerability appears in red (`#ffb4ab`)
- [ ] "Low Risk" appears in normal text color
- [ ] Emergency response time shown (e.g., "4.2m")

**311 Activity Card**
- [ ] Title: "311 Activity" with `forum` icon
- [ ] At least 1 complaint entry rendered
- [ ] Each entry has a left accent bar + complaint type + description
- [ ] Most recent complaint has brighter accent bar

**Viewfinder Brackets**
- [ ] Two bracket shapes visible on left and right screen edges
- [ ] Non-interactive (no cursor change, no click response)

---

### Synthesis Report (`screens/synthesis-report.html`)

**Export Button**
- [ ] "EXPORT PDF" button top-right with `picture_as_pdf` icon
- [ ] Tapping triggers browser file download
- [ ] Downloaded file opens as a valid PDF

**Metadata Block**
- [ ] Report ID format: `CS-XXXX` (4 alphanumeric chars after hyphen)
- [ ] Location shows address (e.g., "District 7, Central Perimeter"), not raw coordinates
- [ ] Date is human-readable (e.g., "24 Oct 2023")
- [ ] Session duration is `mm:ss` format

**Narrative Log**
- [ ] Vertical timeline line is visible
- [ ] Number of log entries matches number of narration chunks from the session
- [ ] Each entry has a timestamp (e.g., "04:12")
- [ ] Key phrases in each entry are highlighted in cream color
- [ ] Most recent entry: circular marker has `border-primary` color
- [ ] Older entries: circular markers are muted (`border-outline-variant/40`)

**Captured Stills**
- [ ] Horizontal scroll works (mouse drag on desktop, swipe on mobile)
- [ ] Each card is 280px wide (not squeezed)
- [ ] Image is not broken / loads correctly
- [ ] Tag chips visible over image
- [ ] Filename shows (e.g., "STILL_001.RAW")
- [ ] Caption below image is italic serif font

**Summary Verdict**
- [ ] Score is displayed (e.g., "6.2/10")
- [ ] Verdict paragraph is non-empty
- [ ] Box has correct subtle border styling

---

## 5. Data Shape Validators

Save as `backend/validate.py` and run: `python validate.py`

```python
def validate_layer_data(data: dict):
    assert "zoning" in data,        "Missing 'zoning' key"
    assert "environment" in data,   "Missing 'environment' key"
    assert "safety" in data,        "Missing 'safety' key"
    assert "activity_311" in data,  "Missing 'activity_311' key"

    assert isinstance(data["zoning"]["far"], (int, float)),     "FAR must be numeric"
    assert data["zoning"]["district"] is not None,              "District must be non-null"

    assert isinstance(data["environment"]["aqi"], int),         "AQI must be int"
    valid_aqi = {"Good","Moderate","Unhealthy for Sensitive Groups","Unhealthy","Very Unhealthy","Hazardous"}
    assert data["environment"]["aqi_category"] in valid_aqi,    f"Unknown AQI category"

    assert data["safety"]["flood_risk"] in {"High Risk","Low Risk"}, "Invalid flood_risk value"
    assert isinstance(data["activity_311"]["complaints"], list), "Complaints must be a list"
    print("✓ layer_data valid")


def validate_ar_labels(labels: list):
    valid_sources   = {"PLUTO","311","PARKS","SAFETY","AQI"}
    valid_positions = {"top-left","top-right","mid-left","mid-right","bottom-left","bottom-right"}
    for i, label in enumerate(labels):
        assert set(label.keys()) == {"source","text","position"}, f"Label {i} has wrong keys: {label.keys()}"
        assert label["source"]   in valid_sources,   f"Label {i} unknown source: {label['source']}"
        assert label["position"] in valid_positions, f"Label {i} unknown position: {label['position']}"
        assert len(label["text"]) > 0,               f"Label {i} has empty text"
    print(f"✓ ar_labels valid ({len(labels)} labels)")


def validate_report(report: dict):
    assert "id" in report and report["id"].startswith("CS-"),   "ID must start with 'CS-'"
    assert isinstance(report.get("narrative"), list),           "narrative must be a list"
    assert len(report["narrative"]) > 0,                        "narrative must have entries"
    for i, entry in enumerate(report["narrative"]):
        assert "timestamp" in entry, f"narrative[{i}] missing timestamp"
        assert "text" in entry,      f"narrative[{i}] missing text"
    assert 0 <= float(report.get("score", -1)) <= 10,           "score must be 0–10"
    assert len(report.get("verdict","")) > 0,                   "verdict must be non-empty"
    print("✓ report valid")
```

---

## 6. End-to-End Flow Tests

### Happy Path (full session)
1. Open `active-analysis.html` on a mobile device
2. Allow camera + GPS
3. Point at a building for ~10 seconds
   - [ ] Subtitles appear
   - [ ] AR labels appear on screen
   - [ ] Audio narration plays
4. Tap **INSPECT**
   - [ ] Layer Inspector loads
   - [ ] All 4 cards show real data (not placeholder text)
5. Tap **RESUME**
   - [ ] Live camera restarts
   - [ ] Analysis continues from where it left off
6. Tap **INSPECT** again
   - [ ] Data is refreshed (not identical to step 4)
7. Tap **STOP**
   - [ ] Synthesis Report loads
   - [ ] Narrative log has entries from this session
8. Tap **EXPORT PDF**
   - [ ] PDF downloads and opens correctly

### GPS Blocked
1. Open app with location permission already denied
   - [ ] Full-screen blocking prompt shown immediately
   - [ ] DevTools Network → WS tab shows no messages sent to backend
2. Enable GPS in browser settings, hard refresh
   - [ ] Analysis starts normally

### API Downtime (Socrata 503)
1. Temporarily replace one Socrata URL with an invalid URL in the tool file
2. Run a session
   - [ ] Agent narrates normally using other tools
   - [ ] Agent explicitly says the unavailable source cannot be retrieved
   - [ ] Layer Inspector card for that source shows a graceful "unavailable" state (not broken/blank UI)
3. Restore the URL

### Rapid Pause / Resume
1. Start session → immediately tap INSPECT → RESUME → INSPECT → RESUME (within 5 seconds)
   - [ ] No duplicate WebSocket messages (check DevTools)
   - [ ] App ends in a valid state (Active Analysis with live camera)
   - [ ] No JS errors in console

---

## 7. Performance Benchmarks

Measure with DevTools (Network tab for WebSocket timing, Performance tab for frame capture).

| Metric | Target | Result | Pass? |
|--------|--------|--------|-------|
| Camera start → first frame sent | < 3s | | [ ] |
| Frame sent → narration received | < 8s | | [ ] |
| All 5 tools combined (server logs) | < 4s | | [ ] |
| JPEG frame size | ≤ 40KB | | [ ] |
| Pause sent → layer_data received | < 5s | | [ ] |
| End sent → report received | < 8s | | [ ] |
| PDF download complete | < 10s | | [ ] |

---

## 8. Cloud Run Deployment Checks

Replace `YOUR_CLOUD_RUN_URL` with the actual URL after deploying.

```bash
# Health check — expect HTTP 200
curl https://YOUR_CLOUD_RUN_URL/health

# WebSocket endpoint exists — expect HTTP 400 (Upgrade Required), NOT 404
curl https://YOUR_CLOUD_RUN_URL/ws/analyze

# PDF export test (use a real session ID)
curl -O https://YOUR_CLOUD_RUN_URL/report/CS-0001/pdf
```

- [ ] `/health` returns 200
- [ ] `/ws/analyze` returns 400 (not 404 — confirms route exists)
- [ ] `wss://` WebSocket connects successfully (test with `wscat`)
- [ ] HTTPS active — no certificate errors in browser
- [ ] Cloud Run logs visible: Cloud Console → Cloud Run → cityscope → Logs
- [ ] Min instances = 1 confirmed in Cloud Run → Edit & Deploy → Capacity
- [ ] Memory usage < 400MB during active session (Cloud Run → Metrics tab)

---

## 9. Mobile Device Checklist

Run this on an actual phone (not just DevTools mobile simulation).

- [ ] Rear camera activates, not front camera
- [ ] GPS coordinates appear in top bar within 5 seconds of granting permission
- [ ] Subtitles readable (no clipping or overflow at phone width)
- [ ] Bottom nav pill reachable with thumb at the very bottom of the screen
- [ ] AR label chips don't overlap each other
- [ ] Layer Inspector cards scroll vertically without triggering swipe-back
- [ ] Captured stills scroll horizontally with finger swipe
- [ ] PDF downloads and opens in the phone's browser/Files app

---

## 10. Visual / Design QA

Open each screen and verify by eye.

**Typography**
- [ ] Subtitles and card titles appear in a serif italic font (Newsreader) — NOT a sans-serif fallback
- [ ] Body text is rounded and clean (Manrope) — NOT Times New Roman or a system font
- [ ] `[SOURCE]` tags, GPS coords, and timestamps are clearly monospaced (Space Mono)

**Colors**
- [ ] Warm cream accent (`#f1dfbe`) is consistent across all 3 screens
- [ ] Background is very dark warm dark (`#121316`), not pure black
- [ ] "High Risk" text on Safety card is red/coral, NOT cream or white
- [ ] Active nav button is visibly brighter and slightly larger than inactive ones

**Glassmorphism**
- [ ] Bottom nav pill has visible blur effect (hold it over a colorful area to confirm)
- [ ] AR label chips have visible blur effect
- [ ] Layer Inspector cards have visible blur effect
- [ ] The effect is blur + translucency, not just a solid dark box

**Layout**
- [ ] Active Analysis: no UI elements cut off at screen edges on mobile
- [ ] Layer Inspector: viewfinder brackets visible on both sides
- [ ] Synthesis Report: horizontal still cards bleed to screen edges correctly (negative margin working)

---

## 11. Quick Reference — Known Good Test Coordinates

| Location | Lat | Lng | Expected interesting data |
|----------|-----|-----|--------------------------|
| Times Square | 40.7580 | -73.9855 | High 311 activity, commercial zoning |
| Midtown intersection | 40.7484 | -73.9967 | Vision Zero crashes, dense PLUTO data |
| Queens residential | 40.7282 | -73.7949 | Tree census data, R-zoning |
| Empire State Building | 40.7484 | -73.9857 | C5 commercial zoning, high FAR |
| Brooklyn Bridge Park | 40.6992 | -73.9979 | High canopy, low 311, park zoning |
