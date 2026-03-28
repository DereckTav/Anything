# CITYSCOPE — NYC Real-Time Site Analysis
## Implementation Plan

---

## Problem & Solution

**Problem:** First-time homebuyers and real estate professionals lack quick, contextual insight into a neighborhood — currently requiring digging through disconnected municipal datasets (PLUTO, 311, tree census, crash data).

**Solution:** A mobile web app where you point your phone's camera at any NYC block and an AI agent narrates what it sees — synthesizing live video with real NYC open data into a spoken, cinematic urban analysis. Like having a seasoned urban planner in your ear.

---

## Core Flows

```
[Camera Feed] → [Gemini Live Vision] → [ADK Agent Tools: PLUTO/311/VisionZero/Trees]
                      ↓
          [Spoken Narration + AR Labels + Subtitles]
                      ↓
            [Pause] → [Layer Inspector]
                      ↓
            [End] → [Synthesis Report]
```

### Three App States
1. **Active Analysis** — Full-screen live `<video>`, gradient overlay, top bar with live GPS coords, canvas AR label chips anchored to buildings (`[PLUTO]`, `[311]`, `[PARKS]` prefixed), cinematic italic subtitles at bottom, floating bottom nav pill (Voice/Cam/Inspect/Stop), desktop-only side HUD ("AI ACTIVE STREAM")
2. **Layer Inspector** — Grayscaled/darkened paused frame, "Intelligence Overlay" header with "Contextual Breakdown" title, Resume button, 4 stacked glassmorphic data cards (Zoning · Environment · Safety · 311 Activity), decorative viewfinder brackets on sides, bottom nav (Audio/Feed/Paused/Exit)
3. **Synthesis Report** — Solid dark background, Report ID metadata block (Location/Date/Session Duration), timeline narrative log with timestamps, horizontal-scroll captured stills with category tags, Summary Verdict score block, PDF export button, bottom nav (Listen/Record/End/Discard)

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Mobile Browser (PWA)                  │
│  MediaStream → VideoCanvas → WebSocket Client            │
│  AR Overlay (Canvas) + Subtitles + Audio playback        │
└───────────────────┬─────────────────────────────────────┘
                    │ WebSocket (video frames + GPS)
┌───────────────────▼─────────────────────────────────────┐
│              Cloud Run — FastAPI + ADK Agent             │
│                                                          │
│  WebSocket Handler                                       │
│       ↓                                                  │
│  ADK Orchestrator Agent (gemini-2.5-pro)                 │
│       ↓ tools                                            │
│  ┌──────┐ ┌──────┐ ┌─────────────┐ ┌──────┐ ┌───────┐  │
│  │PLUTO │ │ 311  │ │ Vision Zero │ │Trees │ │  AQI  │  │
│  │ Tool │ │ Tool │ │    Tool     │ │ Tool │ │ Tool  │  │
│  └──┬───┘ └──┬───┘ └──────┬──────┘ └──┬───┘ └───┬───┘  │
└───────┼──────────┼────────────┼───────────────┼─────────┘
        └──────────┴────────────┴───────────────┘
                         │
         NYC Open Data (Socrata API) + AirNow API
```

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Frontend | Vanilla JS / PWA (no framework) | Fast load on mobile, no build step complexity |
| Styling | Tailwind CSS CDN | No build step; config embedded in `<script>` per HTML file |
| Camera | `navigator.mediaDevices.getUserMedia` | Native browser MediaStream |
| AR Overlay | HTML5 Canvas | Draw label chips anchored to video coords |
| Real-time comms | WebSocket | Low-latency bidirectional streaming |
| Backend | Python FastAPI on Cloud Run | Handles WebSocket + ADK |
| Agent | Google ADK `LlmAgent` | Orchestrates tools, manages session |
| Vision + Voice | Gemini 2.5 Pro (`gemini-2.5-pro`) | Most capable model; multimodal analysis + tool use. **Note:** If Live API (real-time audio streaming) requires `gemini-2.0-flash-live-001` at build time, use a two-model setup: 2.5-pro for analysis/tools, 2.0-flash-live for the audio stream. |
| Data APIs | NYC Open Data (Socrata) + AirNow API | PLUTO, 311, Vision Zero, Tree Census, AQI |
| PDF Export | `reportlab` or `weasyprint` | Server-side PDF generation |
| Hosting | Google Cloud Run | Mandatory, handles WebSocket |
| Auth | None for MVP (public datasets need no key) | Simplify demo |

---

## Design System

Derived from the HTML mockups. All three screens share this exact system.

### Fonts (Google Fonts CDN)
| Tailwind class | Family | Usage |
|----------------|--------|-------|
| `font-headline` | Newsreader (italic) | Screen titles, subtitles, report headings, still captions |
| `font-body` | Manrope | Body text, descriptions, nav labels |
| `font-label` | Space Mono | Data values, GPS coords, `[SOURCE]` tags, timestamps, filenames |

### Icons
Material Symbols Outlined via Google Fonts CDN. Default: `wght 200, FILL 0`. Active state: `FILL 1`.
Key icons: `close`, `mic`, `videocam`, `pause` (fill=1 when active), `cancel`, `play_arrow`, `layers`, `air`, `security`, `forum`, `location_on`, `picture_as_pdf`.

### Key Color Tokens
| Token | Hex | Usage |
|-------|-----|-------|
| `primary` | `#f1dfbe` | AR label borders, active nav, accent text, button bg |
| `background` | `#121316` | App bg |
| `surface-container` | `#1f1f23` | Cards, metadata blocks |
| `on-surface` | `#e3e2e6` | Body text |
| `on-surface-variant` | `#cec5b9` | Secondary text, subtitles |
| `error` | `#ffb4ab` | Safety/flood risk indicators |
| `on-primary` | `#392f18` | Text on primary-colored buttons |
| `outline-variant` | `#4b463d` | Dividers, inactive timeline markers |

### Glassmorphic Panel Recipe
```css
background: rgba(20, 22, 28, 0.65);
backdrop-filter: blur(12px);
-webkit-backdrop-filter: blur(12px);
```
Applied via `.glass-panel` class or inline `bg-[#14161C]/65 backdrop-blur-custom`. Used for: bottom nav pill, AR label chips, Layer Inspector cards.

### Shared Bottom Nav Pill
Structure: `bg-[#14161C]/65 backdrop-blur-xl rounded-full px-8–10 py-4 flex gap-8–10`
4 buttons per screen. Button anatomy: icon (`material-symbols-outlined text-2xl`) + label (`font-label text-[8–9px] uppercase tracking-tighter`).
Active button: `text-[#D4C3A3] scale-110`. Inactive: `text-white/40 hover:text-white`.

| Screen | Btn 1 | Btn 2 | Btn 3 *(active)* | Btn 4 |
|--------|-------|-------|-----------------|-------|
| Active Analysis | mic / VOICE | videocam / CAM | pause / **INSPECT** | cancel / STOP |
| Layer Inspector | mic / AUDIO | videocam / FEED | pause / **PAUSED** | cancel / EXIT |
| Synthesis Report | mic / LISTEN | videocam / RECORD | pause / **END** | cancel / DISCARD |

---

## File Structure

```
/
├── plan.md                        ← this file
├── .env                           ← GOOGLE_API_KEY, GCP project, etc.
├── .claude-plugin/
│   └── plugin.json
├── skills/google-adk/
│   └── SKILL.md
│
├── backend/
│   ├── main.py                    ← FastAPI app, WebSocket endpoint
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── agent.py               ← ADK LlmAgent definition
│   │   ├── tools/
│   │   │   ├── __init__.py
│   │   │   ├── pluto.py           ← PLUTO zoning tool
│   │   │   ├── complaints.py      ← 311 data tool
│   │   │   ├── vision_zero.py     ← crash/safety tool
│   │   │   ├── tree_census.py     ← canopy tool
│   │   │   ├── air_quality.py     ← AQI tool (AirNow API)
│   │   │   └── geocoder.py        ← lat/lng → address/block/BBL
│   │   └── prompts.py             ← system prompt + narration style
│   ├── report/
│   │   ├── generator.py           ← PDF synthesis report builder
│   │   └── templates/
│   │       └── report.html        ← report template
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── index.html                 ← entry point; loads app.js for state routing
│   ├── screens/
│   │   ├── active-analysis.html   ← live video + AR chips + subtitles + bottom nav
│   │   ├── layer-inspector.html   ← paused frame + 4 stacked glass cards + viewfinder
│   │   └── synthesis-report.html  ← timeline log + horizontal stills + verdict + PDF
│   ├── app.js                     ← state machine: IDLE→ANALYZING→INSPECTING→REPORT
│   ├── camera.js                  ← MediaStream, frame capture, GPS, WebSocket send
│   ├── overlay.js                 ← Canvas AR label chips + ar-line connectors
│   └── audio.js                   ← TTS audio chunk playback
│   (No CSS files — Tailwind CDN + inline config handles all styling)
│
├── cloudbuild.yaml                ← Cloud Build → Cloud Run deploy
└── README.md
```

---

## Backend Implementation

### 1. ADK Agent (`backend/agent/agent.py`)

```python
from google.adk.agents import LlmAgent
from .tools import pluto, complaints, vision_zero, tree_census, geocoder, air_quality

root_agent = LlmAgent(
    model="gemini-2.5-pro",
    name="cityscope_agent",
    description="Real-time NYC urban site analyst with vision and voice",
    instruction="""You are CITYSCOPE, an urban intelligence analyst.

You receive a live video stream of NYC streets. As you observe each frame:
1. Identify buildings, signage, block characteristics
2. GPS coordinates are required. Always call tools to fetch PLUTO, 311, Vision Zero, and Tree Census data using the provided coordinates. If GPS is missing or unavailable, halt analysis and prompt the user to enable location before continuing.
3. Synthesize what you SEE with what the DATA says into a spoken dialogue with the client — not a monologue. Ask them what aspects matter most to them (e.g., "Are you more concerned about the zoning limits or the neighborhood safety record?"), acknowledge their goals, and tailor what you highlight next based on their responses. The tone should feel like a knowledgeable friend walking the block with them, not a documentary voice-over.
4. Emit structured AR labels (JSON) for buildings you identify, using this exact schema:
   {"source": "PLUTO", "text": "R7-2 Zoning", "position": "top-left"}
   Valid sources: PLUTO, 311, PARKS, SAFETY, AQI. Valid positions: top-left, top-right, mid-left, mid-right, bottom-left, bottom-right.
5. Speak in a clear, warm, and engaging tone — like a knowledgeable friend, not a documentary narrator.
6. Be grounded: only state facts from tools or clearly observed visuals. If tool data is unavailable or ambiguous, say so explicitly — and re-verify with the client before drawing conclusions (e.g., "The zoning record shows mixed-use but I want to confirm — are you looking at the residential or commercial portion of this lot?"). Never infer or fill in gaps silently.
7. Keep narration to 2-3 sentences before pausing for new observations. This pacing rule is what creates conversational space — after each short narration chunk, listen for the client's response before continuing.

When the user pauses, emit a structured JSON summary for the Layer Inspector.
When the user ends the session, call generate_synthesis to compile the report.""",
    tools=[
        geocoder.get_block_info,
        pluto.get_zoning_data,
        complaints.get_311_complaints,
        vision_zero.get_safety_data,
        tree_census.get_canopy_data,
        air_quality.get_air_quality,
    ]
)
```

### 2. ADK Tools (NYC Open Data via Socrata)

Each tool follows this pattern — Socrata base URL + SoQL query:

**PLUTO (`pluto.py`)**
```python
import httpx

PLUTO_URL = "https://data.cityofnewyork.us/resource/64uk-42ks.json"

def get_zoning_data(bbl: str) -> dict:
    """Get PLUTO zoning, FAR, lot area, year built for a tax lot.
    Args:
        bbl: NYC Borough-Block-Lot identifier (10 digits)
    Returns: dict with zonedist1, far, lotarea, yearbuilt, landuse
    """
    params = {"bbl": bbl, "$limit": 1}
    r = httpx.get(PLUTO_URL, params=params, timeout=5)
    data = r.json()
    if not data:
        return {"error": "No PLUTO data found for this location"}
    return {
        "zoning": data[0].get("zonedist1"),
        "far": data[0].get("far"),
        "lot_area_sqft": data[0].get("lotarea"),
        "year_built": data[0].get("yearbuilt"),
        "land_use": data[0].get("landuse"),
        "address": data[0].get("address"),
    }
```

**311 (`complaints.py`)**
```python
COMPLAINTS_URL = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"

def get_311_complaints(lat: float, lng: float, radius_meters: int = 200) -> dict:
    """Get recent 311 complaints near a location (last 90 days).
    Args:
        lat: Latitude
        lng: Longitude
        radius_meters: Search radius
    Returns: dict with complaint counts by type and top complaints
    """
    # Socrata geospatial query
    query = f"within_circle(location, {lat}, {lng}, {radius_meters})"
    params = {
        "$where": query,
        "$limit": 50,
        "$order": "created_date DESC",
    }
    ...
```

**Vision Zero (`vision_zero.py`)**
```python
CRASHES_URL = "https://data.cityofnewyork.us/resource/h9gi-nx95.json"

def get_safety_data(lat: float, lng: float) -> dict:
    """Get traffic crashes and pedestrian safety near a location (last 12 months).
    Args:
        lat: Latitude
        lng: Longitude
    Returns: dict with crash count, injury count, pedestrian incidents
    """
    ...
```

**Tree Census (`tree_census.py`)**
```python
TREES_URL = "https://data.cityofnewyork.us/resource/uvpi-gqnh.json"

def get_canopy_data(lat: float, lng: float) -> dict:
    """Get street tree data near a location.
    Args:
        lat: Latitude
        lng: Longitude
    Returns: dict with tree count, species diversity, health distribution
    """
    ...
```

### 3. WebSocket Handler (`main.py`)

```python
from fastapi import FastAPI, WebSocket
import asyncio, json, base64
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from agent.agent import root_agent

app = FastAPI()
session_service = InMemorySessionService()

@app.websocket("/ws/analyze")
async def analyze(websocket: WebSocket):
    await websocket.accept()
    session = session_service.create_session(app_name="cityscope", user_id="user")
    runner = Runner(agent=root_agent, app_name="cityscope", session_service=session_service)

    try:
        async for message in websocket.iter_json():
            msg_type = message.get("type")

            if msg_type == "frame":
                # message: {type: "frame", image_b64: "...", gps: {lat, lng}}
                response = await runner.run_async(
                    user_id="user",
                    session_id=session.id,
                    new_message=build_multimodal_message(message)
                )
                for event in response:
                    if event.is_final_response():
                        await websocket.send_json({
                            "type": "narration",
                            "text": event.content.parts[0].text,
                            "ar_labels": extract_ar_labels(event),
                        })

            elif msg_type == "pause":
                # Return structured layer data
                layer_data = await get_layer_summary(runner, session)
                await websocket.send_json({"type": "layer_data", **layer_data})

            elif msg_type == "end":
                report = await generate_report(runner, session)
                await websocket.send_json({"type": "report", **report})

    except Exception as e:
        await websocket.send_json({"type": "error", "message": str(e)})
```

---

## Frontend Implementation

### State Machine (`app.js`)

```
States: IDLE → ANALYZING → INSPECTING → REPORT
                 ↑              ↓
                 └──────────────┘ (resume)
```

### Screen: Active Analysis (`screens/active-analysis.html`)

**Layout layers (z-order):**
1. `fixed inset-0 z-0` — `<video autoplay playsinline>` fills screen
2. `absolute inset-0` — gradient overlay: `bg-gradient-to-b from-black/40 via-transparent to-black/60`
3. `fixed top-0 z-50` — top bar: `close` icon + "CITYSCOPE" (left) | live LAT/LNG in `font-label text-[10px]` (right)
4. `relative z-10 pointer-events-none` — AR label chips + subtitle text
5. `fixed bottom-0 z-50` — bottom nav pill (see Design System)
6. `fixed right-4 top-1/2 hidden md:flex` — desktop side HUD: "AI ACTIVE STREAM" `writing-mode: vertical-rl`

**AR label chips** (each absolutely positioned):
```html
<div class="bg-[#14161C]/65 backdrop-blur-custom px-3 py-1.5 border-l-2 border-[#D4C3A3]">
  <span class="font-label text-[10px] text-primary uppercase">[SOURCE]</span>
  <span class="font-body text-sm text-white ml-2">Label text</span>
</div>
<div class="ar-line ..."></div>  <!-- connector line -->
```
`.ar-line`: `background: linear-gradient(to right, rgba(212,195,163,0.8), transparent); height:1px; width:60px;`

**Subtitles:** `absolute bottom-32 px-8 text-center` → `font-headline italic text-lg md:text-xl text-white text-shadow-strong leading-relaxed`

**AR label backend JSON:**
```json
[
  {"source": "PLUTO", "text": "R7-2 Zoning",      "position": "top-left"},
  {"source": "311",   "text": "3x Noise Density",  "position": "mid-right"},
  {"source": "PARKS", "text": "8% Canopy",         "position": "bottom-left"}
]
```
`overlay.js` maps `position` to predefined `top/left` percentage coords on the screen.

### Screen: Layer Inspector (`screens/layer-inspector.html`)

**Layout:**
- `fixed inset-0 z-0` — paused frame `<img>` with `grayscale-[0.4] contrast-125` + `bg-black/60` overlay
- Top bar: "CITYSCOPE" (left) + `<button class="bg-primary px-4 py-2">▶ Resume</button>` (right)
- `pt-24 pb-32 px-6` scroll area with header + 4 cards
- Decorative viewfinder brackets: `fixed top-1/2 left-6` and `right-6` — thin CSS border lines

**Header:**
```
"Intelligence Overlay"   ← font-label text-[10px] uppercase tracking-[0.3em] text-primary/60
"Contextual Breakdown"   ← font-headline italic text-4xl text-primary
GEO: 40.7128° N ...      ← font-label text-[10px] text-white/40
```

**4 Glass Cards** (`glass-panel p-6 border-l-2 border-primary/20`):

| Card | Icon | Data |
|------|------|------|
| **Zoning** | `layers` | District (e.g. R7A), Density Index (FAR), italic agent description |
| **Environment** | `air` | Canopy Cover % + canopy progress bar, AQI int + category ("Good"/"Moderate"/"Poor") |
| **Safety** | `security` (`text-error/60`) | Flood Vulnerability (text-error if High Risk), Emergency Response time (min) |
| **311 Activity** | `forum` | List of complaint entries: `w-1 bg-primary/40` left bar + type label + description text |

### Screen: Synthesis Report (`screens/synthesis-report.html`)

**Layout:** `bg-background` (solid dark, no video)
- Top bar: "CITYSCOPE" + `bg-primary "EXPORT PDF"` button with `picture_as_pdf` icon
- Metadata block (`bg-surface-container p-5`): Report ID, Location, Date, Session Duration
- `pt-24 pb-32 px-6 max-w-md mx-auto` scroll area

**Section 1 — Narrative Log (timeline):**
- Vertical line: `before:` pseudo-element, `left-[11px] w-[1px] bg-outline-variant/20`
- Each entry: `pl-8 relative` with circular marker div (active = `border-primary`, past = `border-outline-variant/40`), timestamp `font-label text-[10px] text-primary/70`, narration text with highlights in `text-primary font-medium`

**Section 2 — Captured Stills (horizontal scroll):**
- `flex overflow-x-auto gap-4 no-scrollbar -mx-6 px-6 pb-4` (bleeds to screen edge)
- Each card `min-w-[280px] bg-surface-container`: image `h-48` with gradient overlay + tag chips (`font-label text-[8px]`) + filename (`font-label text-[10px]`) + italic caption (`font-headline text-xs`)
- Tag colors: `bg-primary/20 border-primary/30 text-primary` for data, `bg-error/20 border-error/30 text-error` for alerts

**Section 3 — Summary Verdict:**
- `bg-primary-container/10 border border-primary/10 p-6`
- `font-headline italic text-xl text-primary` + body text with score in `text-primary font-bold`

**PDF export:** `GET /report/{session_id}/pdf` → binary download. Frontend: `window.location.href = url`.

### Camera & Frame Streaming (`camera.js`)

- `getUserMedia({ video: { facingMode: "environment" } })` — rear camera on mobile
- Capture frame: draw `<video>` to `<canvas>` → `canvas.toDataURL("image/jpeg", 0.6)` → strip prefix → send via WebSocket
- Frame rate: 1 frame/2 seconds
- GPS is **mandatory**: `navigator.geolocation.getCurrentPosition` required before first frame. If denied or unavailable, display blocking UI: "Location required — please enable GPS to continue." Do not send frames without GPS coords.

---

## Data Flow Detail

```
Every 2s:
  Frontend captures frame (JPEG, ~30KB) + GPS coords
  → WebSocket → FastAPI → ADK Runner
  → Gemini Live receives image + GPS context
  → GPS is required — if absent, backend sends "gps_required" event and halts
  → Agent calls all 4 data tools using GPS coordinates
  → Tools fetch NYC Open Data (parallel async calls)
  → Gemini synthesizes visual + data → narration text + AR label JSON
  → WebSocket → Frontend
  → Audio: Web Speech API TTS (or Gemini Live audio output if available)
  → Canvas: render AR labels
  → Subtitle bar: animate text
```

---

## Layer Inspector Data Structure

Emitted by backend on `pause` event. Maps directly to the 4 glass card UI:

```json
{
  "zoning": {
    "district": "R7A",
    "far": 4.0,
    "description": "High-density residential with mandatory inclusionary housing requirements active in this sector."
  },
  "environment": {
    "canopy_pct": 18,
    "aqi": 42,
    "aqi_category": "Good"
  },
  "safety": {
    "flood_risk": "High Risk",
    "emergency_response_min": 4.2
  },
  "activity_311": {
    "complaints": [
      {"type": "NOISE COMPLAINT", "description": "Construction outside of permitted hours at 144 Bowery."},
      {"type": "STREET LIGHT",    "description": "Infrastructure failure reported at intersection. Ticket #992-B."}
    ]
  }
}
```

---

## Synthesis Report

Backend builds from accumulated session data (narration chunks, frame stills, tool results).

**Structure:**
1. **Metadata** — Report ID (`CS-XXXX`), Location address, Date, Session Duration
2. **Narrative Log** — Timeline of timestamped narration entries; key terms highlighted
3. **Captured Stills** — JPEG frames captured at pause points; tagged by data category
4. **Summary Verdict** — AI-generated score (X/10) + paragraph verdict
5. *(PDF includes all of the above in printable layout)*

**Export:** `GET /report/{session_id}/pdf` → server generates via `reportlab`; frontend triggers browser download.

---

## Deployment

### Dockerfile (`backend/Dockerfile`)
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### Cloud Run Config
- **Min instances:** 1 (cold start kills WebSocket UX)
- **Max instances:** 10
- **Memory:** 512MB
- **Concurrency:** 80
- **Region:** us-east1 (closest to NYC for data latency)
- **WebSocket:** Cloud Run supports WebSocket natively — no special config

### Secrets (Cloud Secret Manager)
- `GOOGLE_API_KEY` or use Workload Identity for Vertex AI
- `GOOGLE_CLOUD_PROJECT`
- `GOOGLE_CLOUD_LOCATION`
- `AIRNOW_API_KEY` — for AQI tool (free registration at airnow.gov)

### Deploy Command
```bash
gcloud run deploy cityscope \
  --source ./backend \
  --region us-east1 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=YOUR_PROJECT
```

---

## Implementation Order

### Phase 1 — Skeleton (get video → get any AI response)
- [ ] FastAPI app with `/ws/analyze` WebSocket endpoint
- [ ] Frontend: camera stream + frame capture + WebSocket send
- [ ] ADK agent returns basic text response to a frame
- [ ] Frontend displays text as subtitle

### Phase 2 — Data Tools
- [ ] Implement all 5 tools: PLUTO, 311, VisionZero, Trees, AQI (AirNow)
- [ ] Geocoder tool: lat/lng → BBL for PLUTO lookups
- [ ] Agent prompt enforces GPS as mandatory; tools always called with coordinates
- [ ] Test tool responses independently

### Phase 3 — AR + Audio
- [ ] AR label JSON schema (`source`/`text`/`position`) defined + agent emits it
- [ ] `overlay.js` renders label chips with `[SOURCE]` prefix + ar-line connectors
- [ ] Audio: Web Speech API TTS from narration text
- [ ] Subtitle animation: `font-headline italic` reveal at `bottom-32`

### Phase 4 — Layer Inspector
- [ ] Pause button: captures still, sends "pause" WebSocket message
- [ ] Backend returns 4-card layer JSON (zoning/environment/safety/activity_311)
- [ ] `layer-inspector.html` renders glass cards with correct icons + data fields
- [ ] Viewfinder brackets + grayscale overlay on paused frame

### Phase 5 — Synthesis Report
- [ ] Session accumulates: narration chunks (with timestamps), captured stills (JPEG), tool results
- [ ] PDF generator builds: metadata + timeline log + stills + verdict
- [ ] `synthesis-report.html`: timeline markup + horizontal scroll stills + summary verdict block
- [ ] Export via `GET /report/{session_id}/pdf` → browser download

### Phase 6 — Deploy
- [ ] Dockerfile + Cloud Build
- [ ] Deploy to Cloud Run (us-east1)
- [ ] Test on actual mobile device at a NYC block
- [ ] HTTPS required for `getUserMedia` — Cloud Run provides this automatically

---

## Key Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Gemini Live latency makes narration feel laggy | Buffer 2-3 sentences; start speaking while next frame processes |
| GPS unavailable / denied | Block analysis entirely. Display: "Location required — please enable GPS to continue." No fallback to visual-only. |
| 311/PLUTO API rate limits or downtime | Cache results per BBL for session duration; graceful "data unavailable" messages |
| Frame size too large → WebSocket slowdown | JPEG at 60% quality, resize to 640px wide before sending |
| Gemini hallucinates building details | System prompt: "only state what tools confirm or what is visually evident" |
| Cold start on Cloud Run breaks first WebSocket | Set min-instances=1 |
| `getUserMedia` denied on mobile | Graceful permission prompt UI with explanation of why camera is needed |

---

## Scoring Alignment

| Criterion | How We Hit It |
|-----------|--------------|
| Beyond Text (40%) | Live video + spoken narration + AR labels + glassmorphic UI — no text box anywhere |
| Fluidity (40%) | Streaming WebSocket, continuous narration, frame-by-frame analysis — not turn-based |
| Google Cloud Native (30%) | ADK `LlmAgent`, Gemini 2.5 Pro, Cloud Run, Cloud Secret Manager |
| Grounding / No Hallucinations (30%) | All claims backed by NYC Open Data tool calls; explicit fallback language |
| Working Demo (30%) | Real camera → real NYC data → real narration; film at an actual NYC block |

---

## NYC Open Data API Reference

| Dataset | Endpoint | Key Fields |
|---------|----------|------------|
| PLUTO | Socrata `64uk-42ks` | bbl, zonedist1, far, lotarea, yearbuilt |
| 311 | Socrata `erm2-nwe9` | complaint_type, location, created_date |
| Vision Zero Crashes | Socrata `h9gi-nx95` | latitude, longitude, number_of_persons_injured |
| Tree Census 2015 | Socrata `uvpi-gqnh` | latitude, longitude, spc_common, health |
| AQI (Air Quality) | AirNow API | `https://www.airnowapi.org/aq/observation/latLong/current/` → AQI int + category |

NYC Open Data base URL: `https://data.cityofnewyork.us/resource/{id}.json`
No key required for Socrata (1000 req/hr per IP). AirNow requires free API key from airnow.gov.
