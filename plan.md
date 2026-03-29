# WAYPOINT — Intelligent City Exploration Companion

## Vision

WAYPOINT is a voice-first mobile app that acts as an intelligent exploration companion. It doesn't just show you what's nearby — it understands *what kind of experience you're looking for* and guides you there.

A user says: *"I don't know what to explore today, I kinda want something exotic."*
The app thinks (showing a "thinking..." subtitle), figures out what fits that description in the city, and responds conversationally: *"There's a Moroccan tea house in the East Village with incredible tilework — about 15 minutes on the L train from you. Want me to guide you there?"*

Users can explore the city, learn the layout, try the subway, discover neighborhoods — all with an intelligent companion that sees what they see, knows where they are, and talks naturally.

---

## Core Experience

### How It Works

1. **User speaks naturally** — vague preferences, specific questions, or anything in between
2. **Agent processes in real-time** — uses GPS, camera, speech, and external data to understand context
3. **"Thinking" feedback** — while searching, the agent either keeps talking or shows a thinking subtitle so the user isn't left in silence
4. **Responds conversationally** — recommends places, explains why, gives transit/walking options
5. **Location tab for navigation** — once a destination is picked, the user switches to navigation guidance
6. **Continuous conversation** — the user can always ask follow-up questions, change their mind, or ask about what they're seeing

### Input Signals

| Signal | Source | Purpose |
|--------|--------|---------|
| **Voice** | Microphone → Gemini Live API | Primary interaction — questions, preferences, reactions |
| **Camera** | Device camera (environment-facing) | Visual context — "what is that building?", landmark ID |
| **GPS** | `navigator.geolocation` (continuous) | Location anchor — nearby POIs, transit routing, walking distance |

The camera gives the agent *context*, not commands. If a user asks "what is this?" the agent cross-references the camera frame with nearby POIs and its knowledge to give a grounded answer.

---

## Current Architecture

### Backend (`backend/`)

**Framework:** FastAPI + Uvicorn (ASGI)
**AI:** Google ADK (text agent) + Gemini Live API (voice agent)
**Hosting:** Google Cloud Run

```
Client (Mobile Browser)
    │
    ├── WebSocket /ws/analyze ──→  ADK Agent (gemini-2.5-flash)
    │     text chat, POI discovery,       │
    │     camera frames                   ├── get_nearby_pois()  → OpenStreetMap Overpass API
    │                                     ├── analyze_frame()    → Google Vision API
    │                                     ├── get_distance()     → Google Maps Distance Matrix
    │                                     └── build_maps_url()   → Google Maps deep-link
    │
    └── WebSocket /ws/voice ───→  Gemini Live API (gemini-2.5-flash-native-audio)
          real-time audio I/O             │
          (bidirectional streaming)        └── Same 4 tools via function calling
```

**Two parallel systems serve different interaction modes:**
- **Text agent (ADK):** Handles the `/ws/analyze` endpoint — proactive POI discovery (every 60s), text chat, and camera frame analysis. Returns JSON messages (narration text, POI chips).
- **Voice agent (Gemini Live):** Handles `/ws/voice` — real-time bidirectional audio conversation with tool calling. Streams PCM audio back to the client.

Both agents have access to the same 4 tools.

### Backend Files

```
backend/
├── main.py              ← FastAPI app, /ws/analyze endpoint, static file serving
├── voice.py             ← /ws/voice endpoint, Gemini Live API session management
├── config.py            ← Environment config (API keys, timeouts, feature flags)
├── Dockerfile
├── requirements.txt
└── agent/
    ├── agent.py         ← ADK root_agent definition (single LlmAgent)
    ├── prompts.py       ← System prompt for the ADK agent
    └── tools/
        ├── __init__.py  ← Exports all 4 tools
        ├── poi.py       ← get_nearby_pois() → Overpass API
        ├── vision.py    ← analyze_frame() → Google Vision API
        └── maps.py      ← get_distance() + build_maps_url() → Google Maps
```

### Frontend (`frontend/`)

**Stack:** Vanilla JS, Tailwind CSS, no build step (PWA-ready)

```
frontend/
├── index.html           ← Entry point, all screen templates inline
├── app.js               ← State machine (IDLE → EXPLORING → NEARBY → DETAIL)
├── camera.js            ← Camera stream + JPEG frame capture
├── audio.js             ← PCM audio playback (Gemini Live responses)
├── overlay.js           ← GPS permission overlay
├── manifest.json
└── screens/
    ├── explore.html     ← Main screen: camera bg, voice, POI chips, nav bar
    ├── nearby.html      ← List/map view of nearby places (Leaflet map)
    ├── place-detail.html← POI detail + "Take Me There" button
    ├── active-analysis.html    ← (legacy, unused)
    ├── layer-inspector.html    ← (legacy, unused)
    └── synthesis-report.html   ← (legacy, unused)
```

### Current UI States

| State | Screen | What's Shown |
|-------|--------|-------------|
| **IDLE** | Splash | "Start Exploring" button, app branding |
| **EXPLORING** | Main | Full camera background, voice status, live captions, POI chips, bottom nav (Voice / Nearby / Exit) |
| **NEARBY** | List/Map | Toggle between scrollable POI cards and Leaflet map with markers |
| **DETAIL** | Place | POI name, address, walking time, "Take Me There" → Google Maps |

---

## What Needs to Change

The current app works as a Brooklyn tourist guide with basic POI discovery and voice chat. The vision is broader — an intelligent companion that understands preferences, recommends experiences, and guides users through the city (including transit). Here's what needs to evolve:

### 1. Intelligent Recommendation Engine

**Current:** User asks "what's nearby?" → agent returns nearest POIs by distance.
**Goal:** User says "I want something exotic" → agent reasons about what "exotic" means, searches for matching experiences, and recommends specific places with *why* they fit.

This requires:
- A richer data source than Overpass (which only has basic POI types/names). Options: Google Places API, Yelp Fusion, or Google Search via ADK.
- Prompt engineering so the agent interprets vague preferences and maps them to concrete experiences.
- Possibly a "preference → search query" step where the agent generates targeted queries.

### 2. Camera PiP Window

**Current:** Full-screen camera background with dark overlay on the explore screen.
**Goal:** Small picture-in-picture camera preview (like a video call self-view) in the bottom-right corner. The main screen should feel more like a conversation interface, not a camera app.

### 3. Transit & Routing Guidance

**Current:** "Take Me There" opens Google Maps for walking directions only.
**Goal:** The agent can recommend transit routes (subway, bus), explain how to use them ("take the L train two stops to 1st Ave"), and the location tab provides step-by-step guidance.

This requires:
- Google Directions API with `mode=transit` support
- A dedicated navigation/location view that shows route steps
- The agent understanding subway lines, transfer points, and giving human-friendly directions

### 4. City-Agnostic (Not Brooklyn-Only)

**Current:** Prompts, branding, and POI queries are Brooklyn-specific.
**Goal:** Works in any city. The agent adapts its knowledge and personality to wherever the user is. The Overpass API already works globally; prompts need to be location-aware rather than hardcoded.

### 5. "Thinking" State UX

**Current:** Agent either speaks or is silent. No intermediate feedback.
**Goal:** When the agent is searching/reasoning, show a "thinking..." subtitle or have the agent say something like "let me look into that..." so the user knows it's working. The voice agent already does this somewhat naturally (Gemini Live streams), but the text flow needs it too.

### 6. Cleanup Legacy Frontend Screens

Three screen templates in `frontend/screens/` are unused leftovers from the URBANLENS design:
- `active-analysis.html`
- `layer-inspector.html`
- `synthesis-report.html`

These should be removed.

---

## Tools Reference

| Tool | File | API | Purpose |
|------|------|-----|---------|
| `get_nearby_pois(lat, lng, radius_meters)` | `poi.py` | OpenStreetMap Overpass | Find POIs within radius — returns name, type, address, coords |
| `analyze_frame(image_b64)` | `vision.py` | Google Vision API | Identify landmarks, labels, text in camera frame |
| `get_distance(origin_lat, origin_lng, dest_lat, dest_lng)` | `maps.py` | Google Maps Distance Matrix | Walking distance and duration between two points |
| `build_maps_url(dest_name, dest_lat, dest_lng)` | `maps.py` | Google Maps URL scheme | Deep-link to Google Maps with walking directions |

### Tools That May Need to Be Added

| Tool | Purpose | Why |
|------|---------|-----|
| **Google Places / Search** | Rich place details — descriptions, ratings, hours, photos | Overpass only gives names/types; users need to know *why* a place is worth visiting |
| **Transit directions** | Subway/bus routing with human-friendly step descriptions | Core to the "explore the city" vision — users need to know how to get places |
| **Web search** | General knowledge lookup for context, history, recommendations | For vague queries like "something exotic" where the agent needs to reason and search |

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Frontend | Vanilla JS / PWA | Fast mobile load, no build step |
| Styling | Tailwind CSS (CDN) | Rapid styling, mobile-first |
| Voice I/O | Gemini Live API (bidirectional audio) | Real-time conversation with native audio, tool calling built in |
| Camera | `getUserMedia` → periodic JPEG capture | Visual context for the agent |
| GPS | `navigator.geolocation` (continuous watch) | Location anchor for all queries |
| Backend | Python FastAPI + Google ADK | WebSocket endpoints, agent orchestration |
| AI Models | `gemini-2.5-flash` (text), `gemini-2.5-flash-native-audio` (voice) | Fast, capable, supports tool calling |
| POI Data | OpenStreetMap Overpass API | Global coverage, no API key needed |
| Vision | Google Vision API | Landmark and label detection |
| Maps | Google Maps Platform (Distance Matrix + URL scheme) | Walking distance + navigation handoff |
| Hosting | Google Cloud Run | WebSocket support, HTTPS (required for mic/camera) |
| Map UI | Leaflet.js | Nearby screen map view |

---

## Configuration

### `backend/config.py` (current)

```python
POI_CHIPS_MAX   = 5       # Max POI chips shown on screen
TOOL_TIMEOUT_S  = 8       # Per-tool HTTP timeout
GPS_REQUIRED    = True     # Require GPS for POI queries
GOOGLE_API_KEY  = env      # Google API key (Maps, Vision)
```

---

## Edge Cases

### Required — Handle These Before Ship

These happen constantly in real-world use. The app feels broken without them.

- **WebSocket reconnect on app resume** — User locks their phone or switches apps (happens every session). WebSocket dies, camera stops, audio stops. On resume, auto-reconnect everything without requiring a restart. For voice, the Gemini Live session is stateful so a drop loses context — re-establish and re-prime the agent.
- **No-GPS conversational fallback** — User starts indoors or denies GPS. The agent should still converse ("where are you headed today?") instead of blocking. Location-based tools just aren't called until GPS arrives.
- **No POIs found** — User is in a residential area, on a bridge, industrial zone. Agent should acknowledge it and suggest heading toward a nearby neighborhood rather than returning nothing.
- **Too-vague query with no context** — "Show me something" with no GPS, no camera, nothing. Agent must ask a clarifying question rather than hallucinate a recommendation.

### Deferred — Don't Implement Unless Specifically Requested

These are real but lower-frequency. Handle them when the specific scenario comes up, not preemptively.

- **Subway/tunnel offline** — User goes underground, loses everything. Ideally cache the last recommendation and show a "reconnecting" state. Complex to do well — save for when transit guidance is built.
- **Urban canyon GPS bounce** — Tall buildings cause GPS to jump 50-100m. Could recommend a place across a highway. Mitigation: show accuracy radius, avoid recommending POIs within the error margin.
- **Voice interruption (barge-in)** — User speaks while agent is mid-response. Gemini Live supports this server-side, but frontend audio playback needs to stop cleanly without artifacts.
- **Hallucinated places** — Agent recommends somewhere that doesn't exist. Mitigate by grounding responses in tool results rather than pure generation. Not fully solvable.
- **Stale POI data** — Overpass says a museum is there, but it closed. Agent should hedge ("it should be around here") rather than guarantee.
- **Tab refresh loses context** — Session ID is lost on page refresh. Either persist in localStorage or accept a fresh start.
- **Phone orientation change** — Camera stream can break on rotation. Lock to portrait or handle reinit.
- **Destination not on Google Maps** — Deep-link opens Maps but it can't find the place by name. Fall back to lat/lng pin.
- **Arrival detection** — No way to know the user arrived. If they say "I'm here" the agent should switch from directions to talking about the place. Needs explicit handling.
- **Slow connection / audio buffering** — Choppy responses or long silence. A timeout should trigger "having trouble connecting" rather than dead air.

---

## Open Design Questions

1. **Recommendation depth:** How smart should preference matching be? Simple keyword → category mapping, or full reasoning chain where the agent searches, evaluates, and ranks options?

2. **Transit data source:** Google Directions API (paid, accurate) vs. open transit data (free, requires more work)?

3. **Camera PiP interaction:** Can the user tap the PiP to expand it? Or is it purely passive context?

4. **Offline/tunnel behavior:** What happens when the user loses connection underground? Cache last state? Show "reconnecting"?

5. **Multi-city onboarding:** Does the app detect the city automatically, or does the user set it? (GPS gives this for free, but the agent personality/knowledge may need to adapt.)
