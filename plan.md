# WAYPOINT — Brooklyn Tourist Guide
## Implementation Plan

---

## Problem & Solution

**Problem:** First-time tourists in Brooklyn have no intelligent companion to help them explore. Google Maps tells you how to get somewhere, but not *what's worth going to* or *why* — and it doesn't talk back. Wandering is great, but tourists miss 80% of what makes a neighborhood interesting.

**Solution:** A voice-first mobile web app that acts as a smart local guide. The tourist walks around Brooklyn, speaks naturally ("what's interesting around here?"), and an AI guide responds — describing nearby places, answering follow-up questions, and handing off to Google Maps when they're ready to navigate. The camera adds context so the guide understands what the tourist is already looking at.

---

## Core Flows

```
[Voice Input] → [Orchestrator Agent]
                        ↓ immediately
              [Quick Response Agent] → speaks within 0.5s
                        ↓ in parallel (background)
        ┌──────────────┬───────────────┬──────────────┐
   [POI Agent]   [Vision Agent]  [Search Agent]  [Maps Agent]
  (nearby POIs) (what's in      (details, hours, (distances,
  from dataset)  camera frame)   context)         routes)
        └──────────────┴───────────────┴──────────────┘
                        ↓
              [Synthesis] → streams updated speech to user
```

### How the Two Inputs Work Together

| Input | Source | Purpose |
|-------|--------|---------|
| **Voice** | Microphone (Web Speech API or Gemini Live) | Tourist's questions + requests |
| **Camera frame** | Periodic JPEG capture (every ~10s or on-demand) | Visual context — what the tourist is looking at right now |
| **GPS** | `navigator.geolocation` | Location anchor for POI queries |

The camera gives the agent *context*, not commands. If a tourist asks "what is this building?" the agent cross-references the Vision API result with nearby POIs to give a grounded answer — not a hallucination.

---

## Multi-Agent Architecture (Core Design Decision)

This is the key architectural pattern: **two-phase speech with parallel background agents.**

### Why Multi-Agent for Fast Speech?

A single agent querying 3–4 APIs before speaking takes 3–5 seconds. That feels broken for a guide. The fix: separate *acknowledgment* from *enrichment*.

```
Phase 1 — Immediate (< 0.5s):
  Quick Agent hears the user's intent and speaks a natural acknowledgment.
  "Let me look around for you..."
  "Good question — checking what's near you now..."

Phase 2 — Enriched (1–4s later, streams in):
  Background agents complete their tool calls.
  Synthesis agent builds the full answer and speaks it, picking up from Phase 1.
  "...there's the Jane's Carousel right by the waterfront, about 3 minutes south.
   It's a 1922 antique carousel that got restored — really worth seeing up close."
```

The tourist hears a response in under a second. The full answer arrives as the agent "thinks aloud." This is how a real human guide talks.

### Agent Roster

| Agent | Model | Role | Tools |
|-------|-------|------|-------|
| **Orchestrator** | `gemini-2.5-flash` | Routes intent, manages conversation state | — |
| **Quick Response** | `gemini-2.5-flash` | Immediate spoken acknowledgment | — |
| **POI Agent** | `gemini-2.5-flash` | Finds nearby Points of Interest | `get_nearby_pois()` |
| **Vision Agent** | `gemini-2.5-flash` | Analyzes camera frame for landmarks/context | `analyze_frame()` |
| **Search Agent** | `gemini-2.5-flash` | Fetches rich details, hours, context | `google_search` (built-in ADK tool) |
| **Maps Agent** | `gemini-2.5-flash` | Calculates distances, builds Maps handoff links | `get_distance()`, `build_maps_url()` |
| **Synthesis Agent** | `gemini-2.5-pro` | Combines all results into final spoken response | — |

> **Note on model choice:** All sub-agents use `gemini-2.5-flash` for speed. Only the final Synthesis uses `gemini-2.5-pro` for quality — it has all the data by then and just needs to tell a good story.

### ADK Multi-Agent Wiring

```python
from google.adk.agents import LlmAgent

poi_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="poi_agent",
    description="Finds Points of Interest near the user's GPS location",
    tools=[get_nearby_pois]
)

vision_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="vision_agent",
    description="Analyzes what the tourist's camera sees using Google Vision",
    tools=[analyze_frame]
)

search_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="search_agent",
    description="Searches the internet for details about a specific place",
    tools=[google_search]
)

maps_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="maps_agent",
    description="Calculates walking distance and builds Google Maps navigation links",
    tools=[get_distance, build_maps_url]
)

orchestrator = LlmAgent(
    model="gemini-2.5-flash",
    name="waypoint_orchestrator",
    instruction="...",  # see prompts.py
    sub_agents=[poi_agent, vision_agent, search_agent, maps_agent]
)
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Mobile Browser (PWA)                       │
│                                                               │
│  Microphone → Web Speech API (STT) → WebSocket               │
│  Camera → periodic JPEG frame → WebSocket                     │
│  GPS → navigator.geolocation → included in each request      │
│                                                               │
│  Speech output ← streaming TTS (Web Speech API)              │
│  POI chips on screen ← rendered from agent response          │
└───────────────────────┬──────────────────────────────────────┘
                        │ WebSocket
┌───────────────────────▼──────────────────────────────────────┐
│              Cloud Run — FastAPI + ADK                        │
│                                                               │
│  WebSocket Handler                                            │
│       ↓                                                       │
│  Orchestrator Agent (gemini-2.5-flash)                        │
│       ↓ routes to sub-agents in parallel                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐         │
│  │   POI    │ │  Vision  │ │  Search  │ │  Maps    │         │
│  │  Agent   │ │  Agent   │ │  Agent   │ │  Agent   │         │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘         │
│       └────────────┴────────────┴────────────┘               │
│                          ↓                                    │
│              Synthesis Agent (gemini-2.5-pro)                 │
└───────────────────────────────────────────────────────────────┘
         │                    │                   │
  NYC POI Dataset      Google Vision API    Google Search /
  (Socrata API)        (landmark ID)        Google Maps API
```

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Frontend | Vanilla JS / PWA | Fast mobile load, no build step |
| Styling | Tailwind CSS CDN | Same as before, works well |
| Voice Input | Web Speech API `SpeechRecognition` | Native browser, no cost |
| Camera | `getUserMedia` → periodic JPEG | Visual context only, not continuous |
| Speech Output | Web Speech API `speechSynthesis` | Streaming-friendly, queues naturally |
| Real-time comms | WebSocket | Low-latency, same as before |
| Backend | Python FastAPI + Google ADK | Multi-agent orchestration |
| Vision | Google Vision API (`LANDMARK_DETECTION`, `LABEL_DETECTION`) | Identifies what tourist is looking at |
| Maps | Google Maps Platform (Directions API + Maps URLs) | Distances + deep-link handoff |
| POI Data | NYC Open Data — Points of Interest dataset | Authoritative nearby location data |
| Internet Search | ADK built-in `google_search` tool | POI details, hours, context, current info |
| Hosting | Google Cloud Run | WebSocket support, HTTPS (required for mic/camera) |

---

## Data Sources

### 1. NYC Points of Interest — Primary Location Data

**Dataset:** `https://data.cityofnewyork.us/resource/rxuy-2muj.json`
**Used for:** Geospatial query — "what POIs are within X meters of me?"
**NOT used for:** Descriptions, hours, reviews (those come from Google Search)

```python
# Tool: get_nearby_pois(lat, lng, radius_meters=500)
# Socrata geospatial query
url = "https://data.cityofnewyork.us/resource/rxuy-2muj.json"
params = {
    "$where": f"within_circle(the_geom, {lat}, {lng}, {radius_meters})",
    "$limit": 20,
    "$select": "name, facility_t, address, the_geom"
}
# Returns: [{name, facility_type, address, lat, lng}]
```

**Why only this dataset:** We don't need zoning, 311, crash data, or air quality for tourists. We need *what is nearby and worth visiting*. The POI dataset gives us the location anchors; Google Search fills in the story.

### 2. Google Vision API — Camera Context

```python
# Tool: analyze_frame(image_b64: str) -> dict
# Sends camera JPEG to Vision API
# Detects: LANDMARK_DETECTION, LABEL_DETECTION, TEXT_DETECTION
# Returns: {landmarks: [{name, confidence}], labels: [...], text: [...]}
```

Used when: tourist asks "what is this?" or every ~30s passively to give the guide ambient context.

### 3. Google Search (ADK built-in)

```python
from google.adk.tools import google_search

# Search agent uses this to find:
# - POI descriptions and history
# - Opening hours
# - "Worth visiting?" context
# - Current events at a location
```

This is why we don't need RAG — the model searches live. The POI dataset gives us *what exists nearby*, Google Search gives us *why it matters*.

### 4. Google Maps Platform

```python
# Tool: get_distance(origin_lat, origin_lng, dest_lat, dest_lng) -> dict
# Uses Distance Matrix API
# Returns: {walking_distance_m, walking_duration_min, walking_duration_text}

# Tool: build_maps_url(dest_name, dest_lat, dest_lng) -> str
# Builds a deep-link: https://www.google.com/maps/dir/?api=1&destination=...
# Opens Google Maps with walking directions pre-loaded
```

No embedded map in the app. When a tourist says "take me there," the app opens Google Maps. This is better UX than a tiny embedded map.

---

## App Screens

### Screen 1 — Explore (main screen)

**What it looks like:**
- Camera feed in background (subtle, darkened — visual context not the focus)
- Large microphone button, center bottom — tap to speak
- Status line at top: "Listening..." / "Looking around..." / "Found 4 places nearby"
- 2–3 POI chips at bottom: `[CAROUSEL] Jane's Carousel · 3 min` with a tap target
- Live GPS coords top-right (small, monospace)
- Subtitles at bottom when agent is speaking

**Interactions:**
- Tap mic → speak → agent responds
- Tap a POI chip → go to Place Detail screen
- App proactively speaks when new POIs are detected nearby (every ~60s)

### Screen 2 — Place Detail

**What it looks like:**
- POI name large, italic serif
- Address + walking time (from Maps agent)
- Agent-generated description (1–2 sentences from Search agent)
- "Take me there" button → opens Google Maps deep-link
- "Tell me more" button → agent speaks more detail
- Back button → return to Explore

### Screen 3 — Nearby (on demand)

**What it looks like:**
- Text list of nearby POIs (not a map — we're handing Maps off)
- Each row: name, type (park / landmark / museum / etc.), distance
- Tap any row → Place Detail

---

## WebSocket Message Protocol

### Client → Server

```json
// User spoke
{"type": "voice", "transcript": "what's around here?", "gps": {"lat": 40.7033, "lng": -73.9888}}

// Camera frame (periodic, ~every 30s)
{"type": "frame", "image_b64": "...", "gps": {"lat": 40.7033, "lng": -73.9888}}

// User tapped a POI chip — wants more detail
{"type": "poi_detail", "poi_name": "Jane's Carousel", "gps": {"lat": 40.7033, "lng": -73.9888}}
```

### Server → Client

```json
// Immediate acknowledgment (Phase 1, < 0.5s)
{"type": "ack_speech", "text": "Let me look around you..."}

// Full response (Phase 2, streams in)
{"type": "response", "text": "There's Jane's Carousel...", "pois": [...], "maps_url": "..."}

// POI chips to show on screen
{"type": "poi_chips", "pois": [
  {"name": "Jane's Carousel", "type": "landmark", "walk_min": 3, "lat": ..., "lng": ...},
  {"name": "Brooklyn Bridge Park", "type": "park", "walk_min": 5, "lat": ..., "lng": ...}
]}
```

---

## ADK Tools Reference

All tools live in `backend/agent/tools/`.

| File | Function | API | Returns |
|------|----------|-----|---------|
| `poi.py` | `get_nearby_pois(lat, lng, radius_meters)` | NYC Socrata POI dataset | `[{name, type, address, lat, lng}]` |
| `vision.py` | `analyze_frame(image_b64)` | Google Vision API | `{landmarks, labels, text}` |
| `maps.py` | `get_distance(origin_lat, origin_lng, dest_lat, dest_lng)` | Google Maps Distance Matrix | `{distance_m, duration_min, duration_text}` |
| `maps.py` | `build_maps_url(dest_name, dest_lat, dest_lng)` | Google Maps URL scheme | Deep-link string |

Google Search is provided by ADK's built-in `google_search` tool — no custom tool needed.

---

## Configuration

### `backend/config.py`

```python
# POI Query
POI_RADIUS_METERS       = 500    # How far to search. 500m ≈ 6 min walk.
POI_MAX_RESULTS         = 20     # Max POIs returned per query.

# Vision
VISION_ENABLED          = True   # Kill switch. False = skip Vision API call.
VISION_INTERVAL_S       = 30     # Passive frame analysis interval (seconds).

# Speech
PHASE1_MAX_TOKENS       = 30     # Quick agent: short acknowledgment only.
PHASE2_MAX_TOKENS       = 200    # Synthesis agent: full response.

# Maps
MAPS_TRAVEL_MODE        = "walking"  # Always walking for tourists.

# Tools
TOOL_TIMEOUT_S          = 5     # Per-tool timeout.
TOOLS_PARALLEL          = True  # Run POI + Vision + Search in parallel.

# Session
SESSION_TIMEOUT_S       = 7200  # 2 hours — tourist exploring for a day.
```

### `frontend/config.js`

```js
const CONFIG = {
  FRAME_INTERVAL_MS:      30000,  // Passive camera frame every 30s (context only)
  GPS_POLL_INTERVAL_MS:   5000,   // GPS refresh every 5s (tourist is walking)
  POI_CHIPS_MAX:          3,      // Max POI chips shown on screen at once
  SPEECH_RATE:            0.95,   // Slightly slower than default — tourist-friendly pace
  SPEECH_PITCH:           1.0,
  WS_URL:                 `ws://${location.host}/ws/guide`,
  AUTO_DISCOVER_INTERVAL_MS: 60000, // Proactively check for new POIs every 60s
};
```

---

## File Structure

```
/
├── plan.md                          ← this file
├── test-plan.md
├── workstreams.md
├── .env
├── skills/google-adk/SKILL.md
│
├── backend/
│   ├── config.py
│   ├── main.py                      ← FastAPI + WebSocket at /ws/guide
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── agent.py                 ← Orchestrator + sub-agents defined here
│   │   ├── prompts.py               ← All system prompts as constants
│   │   └── tools/
│   │       ├── __init__.py
│   │       ├── poi.py               ← get_nearby_pois() → NYC POI dataset
│   │       ├── vision.py            ← analyze_frame() → Google Vision API
│   │       └── maps.py              ← get_distance() + build_maps_url()
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── index.html                   ← Entry point, loads config + app
│   ├── config.js                    ← All tunable frontend params
│   ├── app.js                       ← State machine: IDLE → EXPLORING → DETAIL → NEARBY
│   ├── voice.js                     ← SpeechRecognition (input) + speechSynthesis (output)
│   ├── camera.js                    ← Periodic frame capture + GPS
│   ├── manifest.json
│   └── screens/
│       ├── explore.html             ← Main screen: camera bg, mic button, POI chips
│       ├── place-detail.html        ← POI name, description, "Take me there" button
│       └── nearby.html              ← Text list of nearby POIs
│
└── cloudbuild.yaml
```

---

## Workstream Split (4 People)

| Person | Scope |
|--------|-------|
| **1 — Backend Core** | `main.py` WebSocket handler, ADK orchestrator agent, `poi.py` tool, `maps.py` tool |
| **2 — Frontend Core** | `app.js` state machine, `voice.js` (STT + TTS), `camera.js`, all 3 screen HTML shells |
| **3 — Vision + Search** | `vision.py` tool, Search agent wiring, POI chip UI rendering, speech streaming glue |
| **4 — Multi-Agent + Deploy** | Sub-agent definitions in `agent.py`, parallel tool execution pattern, `cloudbuild.yaml`, Cloud Run deployment |

---

## What Changed From the Previous Plan

| Old (URBANLENS) | New (WAYPOINT) |
|-----------------|----------------|
| Building analysis for homebuyers/developers | Exploration guide for first-time tourists |
| Camera is primary input (analyzed every 2s) | Camera is background context (every 30s) |
| Voice is output only | Voice is primary I/O (voice-first) |
| 5 data tools: PLUTO, 311, Vision Zero, Trees, AQI | 3 data tools: POI dataset, Vision API, Maps API |
| RAG-style municipal data synthesis | Live Google Search for richness, no RAG |
| Single Gemini agent | Multi-agent: Quick + POI + Vision + Search + Maps + Synthesis |
| Single agent responds after all tools finish | Two-phase speech: acknowledge immediately, enrich as data arrives |
| Layer Inspector + Synthesis Report screens | Place Detail + Nearby List screens |
| No navigation handoff | "Take me there" → Google Maps deep-link |
| All of NYC | Brooklyn only (can expand city-agnostically later) |

---

## Open Questions (Decide Before Building)

1. **Voice activation:** Push-to-talk (tap mic button) or always-on wake word? Push-to-talk is simpler and avoids false triggers in a noisy city.

2. **Proactive narration:** Should the app *spontaneously* say "Hey, there's something interesting nearby" without the user asking? Or only respond to explicit questions? (Recommendation: opt-in toggle.)

3. **POI filtering:** The dataset includes all facility types. Should we filter to tourist-relevant types only (landmarks, parks, museums, cultural) or show everything?

4. **Offline fallback:** Tourist in a tunnel? Should the last-known POIs stay on screen, or show "no connection" state?

5. **Language:** English only for MVP, or is multi-language TTS a priority?
