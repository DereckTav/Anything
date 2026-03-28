# CITYSCOPE — 4 Workstream Split

Each person gets a self-contained prompt to give Claude. Work can proceed in parallel — dependency handoff points are noted.

---

## Person 1: Backend Core — FastAPI + WebSocket + ADK Agent

**Scope:** Everything in `backend/` except the report generator. This is the spine of the app.

### Prompt for Claude:

```
You are building the backend for CITYSCOPE, an NYC real-time urban site analysis app. Build everything inside the `backend/` directory.

## What to build

### 1. FastAPI WebSocket server (`backend/main.py`)
- FastAPI app with a WebSocket endpoint at `/ws/analyze`
- Accepts JSON messages with three types:
  - `"frame"`: `{type: "frame", image_b64: "...", gps: {lat, lng}}` — a JPEG camera frame + GPS coords
  - `"pause"`: signals the user wants the Layer Inspector view
  - `"end"`: signals session end, triggers report generation
- Uses Google ADK `Runner` and `InMemorySessionService` to manage agent sessions
- For `"frame"` messages: build a multimodal message with the base64 image + GPS context, send to ADK runner, extract the narration text and AR label JSON from the response, send back `{type: "narration", text: "...", ar_labels: [...]}`
- For `"pause"` messages: ask the agent to produce a structured JSON summary, send back `{type: "layer_data", zoning: {...}, environment: {...}, safety: {...}, activity_311: {...}}`
- For `"end"` messages: accumulate session data and send back `{type: "report", ...}` with narrative log, metadata, and verdict
- Also serve the `frontend/` directory as static files so the whole app runs from one server
- Add a `GET /report/{session_id}/pdf` endpoint (stub it — Person 4 will implement the PDF generator)

### 2. ADK Agent (`backend/agent/agent.py`)
- Define a `root_agent` using `google.adk.agents.LlmAgent`
- Model: `gemini-2.5-pro`
- Name: `cityscope_agent`
- System instruction (use exactly this):
  """You are CITYSCOPE, an urban intelligence analyst. You receive a live video stream of NYC streets. As you observe each frame:
  1. Identify buildings, signage, block characteristics
  2. GPS coordinates are required. Always call tools to fetch PLUTO, 311, Vision Zero, and Tree Census data using the provided coordinates.
  3. Synthesize what you SEE with what the DATA says into spoken narration. Speak like a knowledgeable friend walking the block, not a documentary narrator.
  4. Emit structured AR labels as JSON array: {"source": "PLUTO"|"311"|"PARKS"|"SAFETY"|"AQI", "text": "label", "position": "top-left"|"top-right"|"mid-left"|"mid-right"|"bottom-left"|"bottom-right"}
  5. Keep narration to 2-3 sentences per frame. Be grounded: only state facts from tools or clearly observed visuals.
  When the user pauses, emit a structured JSON summary for the Layer Inspector with keys: zoning, environment, safety, activity_311.
  When the user ends the session, compile a synthesis report."""
- Tools: all 6 tools from the tools/ directory

### 3. ADK Tools (`backend/agent/tools/`)
Create `__init__.py` and these tool files:

**`geocoder.py`** — `get_block_info(lat: float, lng: float) -> dict`
- Use NYC's geoclient or a reverse geocoding approach to convert lat/lng to an address and BBL (Borough-Block-Lot)
- You can use the NYC Planning Labs geocoder: `https://geosearch.planninglabs.nyc/v2/reverse?point.lon={lng}&point.lat={lat}`
- Return: `{address, bbl, borough, block, lot, zipcode}`

**`pluto.py`** — `get_zoning_data(bbl: str) -> dict`
- Socrata endpoint: `https://data.cityofnewyork.us/resource/64uk-42ks.json`
- Query by BBL, return: `{zoning, far, lot_area_sqft, year_built, land_use, address}`

**`complaints.py`** — `get_311_complaints(lat: float, lng: float, radius_meters: int = 200) -> dict`
- Socrata endpoint: `https://data.cityofnewyork.us/resource/erm2-nwe9.json`
- Use `within_circle(location, lat, lng, radius)` for geospatial query
- Last 90 days, limit 50, order by created_date DESC
- Return: `{total_count, top_types: [{type, count}], recent: [{type, description, date}]}`

**`vision_zero.py`** — `get_safety_data(lat: float, lng: float) -> dict`
- Socrata endpoint: `https://data.cityofnewyork.us/resource/h9gi-nx95.json`
- Query crashes within ~200m, last 12 months
- Return: `{crash_count, injuries, pedestrian_incidents, cyclist_incidents}`

**`tree_census.py`** — `get_canopy_data(lat: float, lng: float) -> dict`
- Socrata endpoint: `https://data.cityofnewyork.us/resource/uvpi-gqnh.json`
- Query trees within ~200m
- Return: `{tree_count, species: [{name, count}], health: {good, fair, poor}}`

**`air_quality.py`** — `get_air_quality(lat: float, lng: float) -> dict`
- AirNow API: `https://www.airnowapi.org/aq/observation/latLong/current/`
- Needs AIRNOW_API_KEY env var
- Return: `{aqi, category, pollutant, color}`

All tools should use `httpx` with `timeout=5`, handle errors gracefully returning `{error: "message"}`.

### 4. Files to also create
- `backend/agent/__init__.py` — expose agent module
- `backend/agent/tools/__init__.py` — export all tool functions
- `backend/agent/prompts.py` — store the system prompt as a constant
- `backend/requirements.txt`: fastapi, uvicorn[standard], google-adk, httpx, python-dotenv
- `backend/Dockerfile`:
  ```
  FROM python:3.12-slim
  WORKDIR /app
  COPY requirements.txt .
  RUN pip install --no-cache-dir -r requirements.txt
  COPY . .
  CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
  ```
- `.env` template with: GOOGLE_API_KEY, GOOGLE_GENAI_USE_VERTEXAI, GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION, AIRNOW_API_KEY

## Tech notes
- Use `async` throughout — all tool calls should be async with httpx.AsyncClient
- No auth needed for NYC Socrata APIs (1000 req/hr per IP)
- AirNow requires a free API key from airnow.gov
- Python 3.12+, use google-adk package
```

---

## Person 2: Frontend — Camera, WebSocket, State Machine, App Shell

**Scope:** `frontend/index.html`, `frontend/app.js`, `frontend/camera.js`, `frontend/audio.js`, and the basic HTML structure for all 3 screens. Does NOT do the AR overlay (Person 3) or the report screen data (Person 4).

### Prompt for Claude:

```
You are building the frontend for CITYSCOPE, an NYC real-time urban site analysis mobile web app. Everything is vanilla JS, no build step, Tailwind CSS via CDN. Build inside the `frontend/` directory.

## Design System (use exactly these)

### Fonts (Google Fonts CDN)
- `font-headline`: Newsreader (italic) — titles, subtitles, report headings
- `font-body`: Manrope — body text, descriptions, nav labels
- `font-label`: Space Mono — data values, GPS coords, source tags, timestamps

### Icons
Material Symbols Outlined via Google Fonts CDN. Default: weight 200, fill 0. Active: fill 1.

### Colors
- primary: #f1dfbe — accents, AR label borders, active nav
- background: #121316 — app bg
- surface-container: #1f1f23 — cards, metadata blocks
- on-surface: #e3e2e6 — body text
- on-surface-variant: #cec5b9 — secondary text
- error: #ffb4ab — safety indicators
- on-primary: #392f18 — text on primary buttons
- outline-variant: #4b463d — dividers

### Glassmorphic Panel
```css
.glass-panel { background: rgba(20, 22, 28, 0.65); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); }
```

## What to build

### 1. `frontend/index.html` — Entry point
- Loads Tailwind CDN with custom config (fonts, colors above)
- Loads Google Fonts (Newsreader, Manrope, Space Mono, Material Symbols Outlined)
- Contains a single `<div id="app">` container
- Loads `app.js`, `camera.js`, `audio.js` as modules
- Mobile-first: `<meta name="viewport" content="width=device-width, initial-scale=1">`
- PWA manifest link (create a basic `manifest.json`)

### 2. `frontend/app.js` — State machine
States: `IDLE → ANALYZING → INSPECTING → REPORT`
- IDLE: Show a start button. On click → request camera + GPS permissions → transition to ANALYZING
- ANALYZING: Load `screens/active-analysis.html` content, start camera stream, open WebSocket to `ws://{host}/ws/analyze`, begin frame capture loop (1 frame / 2 seconds)
- INSPECTING: Pause camera, capture still frame, send `{type: "pause"}` via WebSocket, load `screens/layer-inspector.html`, populate with received layer data. Resume button → back to ANALYZING.
- REPORT: Send `{type: "end"}` via WebSocket, load `screens/synthesis-report.html`, populate with report data.

Each state transition should:
- Clean up previous state (stop camera, close connections if needed)
- Load the appropriate screen HTML
- Initialize the screen's functionality

### 3. `frontend/camera.js` — Camera + GPS + WebSocket streaming
- Export: `startCamera()`, `stopCamera()`, `captureFrame()`, `getGPS()`
- Camera: `getUserMedia({ video: { facingMode: "environment", width: 640 } })` — rear camera
- Frame capture: draw `<video>` to offscreen `<canvas>` → `canvas.toDataURL("image/jpeg", 0.6)` → strip `data:image/jpeg;base64,` prefix
- GPS: `navigator.geolocation.watchPosition` — continuously update. GPS is MANDATORY. If denied, show blocking overlay: "Location required — please enable GPS to continue."
- WebSocket: connect to `/ws/analyze`, send `{type: "frame", image_b64: "...", gps: {lat, lng}}` every 2 seconds
- Handle incoming messages: dispatch to appropriate handler based on `type` (narration, layer_data, report, error)

### 4. `frontend/audio.js` — TTS playback
- Use Web Speech API `speechSynthesis`
- Export: `speakNarration(text)`, `stopSpeaking()`
- Queue narration chunks so they don't overlap
- Use a clear, moderate-speed voice

### 5. Screen HTML files (structure + styling only, data populated by app.js)

**`screens/active-analysis.html`**
- Full-screen `<video autoplay playsinline>` as background (z-0)
- Gradient overlay: `bg-gradient-to-b from-black/40 via-transparent to-black/60`
- Top bar (fixed, z-50): close icon + "CITYSCOPE" left, live GPS coords right (font-label, text-[10px])
- AR overlay container: `<canvas id="ar-canvas">` positioned over video (Person 3 will use this)
- Subtitle area: `absolute bottom-32 px-8 text-center` with `font-headline italic text-lg text-white`
- Bottom nav pill (glassmorphic): 4 buttons — VOICE (mic), CAM (videocam), INSPECT (pause, active), STOP (cancel)
- Desktop-only side HUD: "AI ACTIVE STREAM" vertical text, `hidden md:flex`

**`screens/layer-inspector.html`**
- Paused frame `<img>` as bg with `grayscale-[0.4] contrast-125` + dark overlay
- Top bar: "CITYSCOPE" left, Resume button (primary bg) right
- Header: "Intelligence Overlay" (font-label, small, uppercase, primary/60) + "Contextual Breakdown" (font-headline, italic, text-4xl, primary)
- GEO coordinates line
- 4 stacked glass cards (glass-panel, border-l-2 border-primary/20, p-6):
  - Zoning (layers icon): district, density index, description
  - Environment (air icon): canopy % with progress bar, AQI with category
  - Safety (security icon, text-error/60): flood risk, emergency response time
  - 311 Activity (forum icon): list of complaints with left accent bar
- Decorative viewfinder brackets on left and right edges
- Bottom nav pill: AUDIO, FEED, PAUSED (active), EXIT

**`screens/synthesis-report.html`**
- Solid dark bg (no video)
- Top bar: "CITYSCOPE" + EXPORT PDF button (primary bg, picture_as_pdf icon)
- Metadata block (surface-container bg): Report ID, Location, Date, Session Duration
- Timeline narrative log: vertical line with circular markers, timestamps, narration text
- Horizontal scroll captured stills: cards with images, tags, captions
- Summary Verdict: bordered box with score and paragraph
- Bottom nav pill: LISTEN, RECORD, END (active), DISCARD

### Bottom nav pill pattern (shared)
```html
<div class="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 glass-panel rounded-full px-8 py-4 flex gap-8">
  <button class="flex flex-col items-center gap-1 text-white/40 hover:text-white transition">
    <span class="material-symbols-outlined text-2xl">icon_name</span>
    <span class="font-label text-[8px] uppercase tracking-tighter">LABEL</span>
  </button>
  <!-- active button gets: text-[#D4C3A3] scale-110 -->
</div>
```

## Important notes
- No build step. Everything loaded via CDN or direct script tags.
- Mobile-first design. Test at 390px width.
- The `<canvas id="ar-canvas">` should overlay the video exactly (same dimensions, position absolute). Person 3 will write overlay.js to draw on it.
- Use ES modules (type="module") for JS files.
- WebSocket URL should auto-detect: `ws://${location.host}/ws/analyze` (or wss:// if on https)
```

---

## Person 3: AR Overlay + Visual Polish + Integration Glue

**Scope:** `frontend/overlay.js`, AR label rendering, subtitle animations, visual effects, and wiring everything together so screens feel polished and cinematic.

### Prompt for Claude:

```
You are building the AR overlay system and visual polish layer for CITYSCOPE, an NYC real-time urban analysis app. You work in the `frontend/` directory alongside code written by others.

## Context
The app has 3 screens managed by app.js:
1. Active Analysis — live camera feed with AI narration
2. Layer Inspector — paused view with data cards
3. Synthesis Report — session summary

Person 2 built the screen HTML, camera, state machine, and audio. You are responsible for the AR overlay on the camera view, subtitle animations, and making everything feel cinematic.

## What to build

### 1. `frontend/overlay.js` — AR Label Chip Renderer

The backend sends AR labels as JSON:
```json
[
  {"source": "PLUTO", "text": "R7-2 Zoning", "position": "top-left"},
  {"source": "311", "text": "3x Noise Density", "position": "mid-right"},
  {"source": "PARKS", "text": "8% Canopy", "position": "bottom-left"}
]
```

Export: `renderARLabels(labels)`, `clearARLabels()`

**Position mapping** (percentage of viewport):
| Position | Top | Left |
|----------|-----|------|
| top-left | 15% | 5% |
| top-right | 15% | 60% |
| mid-left | 45% | 5% |
| mid-right | 45% | 55% |
| bottom-left | 70% | 5% |
| bottom-right | 70% | 55% |

**Label chip HTML** (inject into a container div overlaying the video, NOT canvas):
```html
<div class="ar-label absolute transition-all duration-500 ease-out" style="top: {top}; left: {left};">
  <div class="glass-panel px-3 py-1.5 border-l-2 border-[#D4C3A3] flex items-center gap-2">
    <span class="font-label text-[10px] text-[#f1dfbe] uppercase">[{SOURCE}]</span>
    <span class="font-body text-sm text-white">{text}</span>
  </div>
  <div class="ar-line mt-0.5" style="background: linear-gradient(to right, rgba(212,195,163,0.8), transparent); height: 1px; width: 60px;"></div>
</div>
```

**Animation:** Labels should fade in with a slight upward slide (opacity 0→1, translateY 10px→0) over 500ms. When new labels arrive, old ones fade out (300ms) before new ones fade in. Use CSS transitions, not canvas.

### 2. Subtitle Animation System

The backend sends narration text. Display it as cinematic subtitles:
- Position: `absolute bottom-32 left-0 right-0 px-8 text-center`
- Style: `font-headline italic text-lg md:text-xl text-white` with text shadow
- Text shadow: `text-shadow: 0 2px 8px rgba(0,0,0,0.8), 0 0 20px rgba(0,0,0,0.4)`

**Animation:** Text should appear with a typewriter-like reveal or a smooth fade-in. Each new narration replaces the previous one with a crossfade (old fades out 300ms, new fades in 500ms).

Export: `showSubtitle(text)`, `hideSubtitle()`

### 3. Visual Effects

**Scanning line effect** (Active Analysis only):
- A subtle horizontal line that slowly moves down the screen, like a scanner
- `height: 1px`, `background: linear-gradient(to right, transparent, rgba(241,223,190,0.3), transparent)`
- Animation: top 0% → 100% over 8 seconds, repeating
- Add via CSS @keyframes

**Viewfinder brackets** (Layer Inspector):
- Four corner bracket marks using CSS borders
- Fixed position, slightly inset from screen edges
- Thin lines (1px) in primary/30 color
- Subtle pulse animation (opacity 0.3 → 0.6 → 0.3) over 3 seconds

**Gradient overlays:**
- Active Analysis: `bg-gradient-to-b from-black/40 via-transparent to-black/60`
- Layer Inspector: `bg-black/60` over the grayscaled frame

### 4. Screen Transition Animations
- When transitioning between screens, use a brief fade (opacity transition, 200ms)
- The app container should have `transition-opacity duration-200`

### 5. Glass card hover/active states (Layer Inspector)
- Cards should have a subtle hover effect: `hover:bg-[#14161C]/80 hover:border-primary/40`
- Active/expanded card: slightly brighter border

### 6. Progress indicators
- While waiting for backend responses, show a subtle pulsing dot or loading indicator near the subtitle area
- Style: small dot (6px), primary color, pulse animation

## Design tokens to use
- Primary: #f1dfbe
- Background: #121316
- Surface: #1f1f23
- Glass panel: rgba(20, 22, 28, 0.65) + backdrop-filter blur(12px)
- Font classes: font-headline (Newsreader italic), font-body (Manrope), font-label (Space Mono)

## Important notes
- Use DOM elements for AR labels, NOT canvas drawing. This gives better text rendering and animation control.
- The `<canvas id="ar-canvas">` from Person 2 can be repurposed or removed — DOM-based labels are preferred.
- All animations should be CSS-based for performance (transforms, opacity).
- Export all functions as ES modules.
- Keep the file focused: overlay.js handles AR labels + subtitles + visual effects.
```

---

## Person 4: Synthesis Report + PDF Export + Deployment

**Scope:** `backend/report/` (PDF generator), populating the synthesis report screen with real data, and all deployment config (Dockerfile, Cloud Run, cloudbuild.yaml).

### Prompt for Claude:

```
You are building the synthesis report system and deployment pipeline for CITYSCOPE, an NYC real-time urban analysis app.

## What to build

### 1. Backend Report Generator (`backend/report/generator.py`)

The backend accumulates session data during analysis:
- Narration chunks with timestamps: `[{timestamp, text, ar_labels}]`
- Captured still frames (JPEG base64) taken at pause points
- Tool results from each analysis cycle
- GPS coordinates

Build a `ReportGenerator` class:

```python
class ReportGenerator:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.narration_log = []      # [{timestamp, text}]
        self.captured_stills = []    # [{image_b64, timestamp, tags}]
        self.tool_results = {}       # accumulated tool data
        self.start_time = None
        self.location = None         # {address, lat, lng}

    def add_narration(self, text: str, timestamp: str, ar_labels: list = None): ...
    def add_still(self, image_b64: str, timestamp: str, tags: list = None): ...
    def set_location(self, address: str, lat: float, lng: float): ...
    def update_tool_results(self, tool_name: str, data: dict): ...

    def generate_summary(self) -> dict:
        """Generate the synthesis report data structure for the frontend."""
        return {
            "report_id": f"CS-{self.session_id[:4].upper()}",
            "location": self.location,
            "date": self.start_time.strftime("%B %d, %Y"),
            "duration": "...",  # calculate from start to now
            "narrative_log": self.narration_log,
            "captured_stills": self.captured_stills,
            "verdict": {
                "score": 7.5,  # AI-generated based on accumulated data
                "summary": "..."  # AI-generated paragraph
            }
        }

    def generate_pdf(self) -> bytes:
        """Generate a PDF version of the synthesis report."""
        ...
```

### 2. PDF Generation (`backend/report/generator.py` continued)

Use `reportlab` to generate a styled PDF:
- Page 1: Cover — CITYSCOPE logo/title, Report ID, Location, Date, Duration
- Page 2+: Narrative timeline with timestamps and key highlights
- Captured stills embedded as images (decode base64 → PIL Image → ReportLab)
- Final page: Summary Verdict with score and paragraph
- Style: dark theme inspired (dark gray bg, cream/gold text matching #f1dfbe accent)
- Page size: Letter
- Include page numbers in footer

Add `reportlab` and `Pillow` to `backend/requirements.txt`.

### 3. PDF API Endpoint

In `backend/main.py` (or coordinate with Person 1), add:
```python
from fastapi.responses import StreamingResponse
import io

@app.get("/report/{session_id}/pdf")
async def download_report(session_id: str):
    # Get the ReportGenerator for this session
    generator = active_reports.get(session_id)
    if not generator:
        raise HTTPException(status_code=404, detail="Report not found")
    pdf_bytes = generator.generate_pdf()
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=cityscope-{session_id}.pdf"}
    )
```

### 4. Frontend Report Data Population

In the synthesis report screen (`frontend/screens/synthesis-report.html`), the data arrives as:
```json
{
  "type": "report",
  "report_id": "CS-A1B2",
  "location": {"address": "144 Bowery, Manhattan", "lat": 40.7194, "lng": -73.9930},
  "date": "March 28, 2026",
  "duration": "4m 32s",
  "narrative_log": [
    {"timestamp": "00:00:12", "text": "Looking at a classic pre-war walk-up..."},
    {"timestamp": "00:00:28", "text": "PLUTO confirms R7-2 zoning with 40% unused FAR..."}
  ],
  "captured_stills": [
    {"image_b64": "...", "timestamp": "00:01:15", "tags": ["PLUTO", "311"]}
  ],
  "verdict": {
    "score": 7.5,
    "summary": "This block shows strong residential density potential..."
  }
}
```

Write a JS function `populateReport(data)` (can be in app.js or a separate report.js) that:
- Fills the metadata block (report ID, location, date, duration)
- Builds the timeline narrative log with proper markup (vertical line, markers, timestamps, text)
- Creates the horizontal scroll still cards with images (convert base64 to img src), tags, and captions
- Fills the verdict section with score and summary
- Wires the "EXPORT PDF" button to `window.location.href = /report/${session_id}/pdf`

### 5. Deployment Files

**`backend/Dockerfile`** (if not already created by Person 1):
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

**`cloudbuild.yaml`**:
```yaml
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'gcr.io/$PROJECT_ID/cityscope', './backend']
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'gcr.io/$PROJECT_ID/cityscope']
  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    args:
      - 'run'
      - 'deploy'
      - 'cityscope'
      - '--image=gcr.io/$PROJECT_ID/cityscope'
      - '--region=us-east1'
      - '--platform=managed'
      - '--allow-unauthenticated'
      - '--min-instances=1'
      - '--max-instances=10'
      - '--memory=512Mi'
      - '--concurrency=80'
      - '--set-env-vars=GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=$PROJECT_ID'
    entrypoint: gcloud
```

**`README.md`**:
Write a clear README with:
- Project description (1 paragraph)
- Prerequisites (Python 3.12+, Google Cloud account, API keys)
- Local development setup (install deps, set .env, run uvicorn)
- Deployment instructions (gcloud run deploy command)
- Environment variables list
- Architecture diagram (text-based, from plan.md)

### 6. Session data accumulation

Work with Person 1 to ensure the WebSocket handler accumulates data into a `ReportGenerator` instance throughout the session. The pattern:
- On WebSocket connect: create `ReportGenerator(session_id)`
- On each `"frame"` response: call `generator.add_narration(text, timestamp)`
- On `"pause"`: call `generator.add_still(image_b64, timestamp, tags)`
- On `"end"`: call `generator.generate_summary()` for frontend data, store generator for PDF endpoint

## Tech notes
- reportlab for PDF generation (pip install reportlab)
- Pillow for image handling (pip install Pillow)
- Cloud Run supports WebSocket natively, no special config needed
- HTTPS is automatic on Cloud Run (required for getUserMedia)
- Set min-instances=1 to avoid cold start killing WebSocket connections
```

---

## Dependency Map

```
Person 1 (Backend)  ←──────────────────── Person 4 (Report + Deploy)
    ↑ provides WebSocket API                  uses backend endpoints
    │
Person 2 (Frontend Core) ←──────────── Person 3 (AR + Visual Polish)
    ↑ provides HTML structure + camera       adds overlay + animations
```

**Integration order:**
1. Person 1 + Person 2 can work fully in parallel (backend vs frontend)
2. Person 3 needs Person 2's HTML structure before wiring in overlay.js
3. Person 4 needs Person 1's WebSocket handler structure to plug in the report generator
4. Final integration: merge all 4, test end-to-end

**Handoff protocol:** Each person should commit to a branch (`backend-core`, `frontend-core`, `ar-overlay`, `report-deploy`) and merge sequentially: 1 → 2 → 3 → 4.
