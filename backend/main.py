import asyncio
import json
import base64
import re

from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agent.agent import root_agent
from agent.tools.poi import get_nearby_pois
from agent.tools.maps import get_distance, build_maps_url
from config import GPS_REQUIRED, POI_CHIPS_MAX
from voice import handle_voice

app = FastAPI(title="WAYPOINT API")
session_service = InMemorySessionService()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "waypoint"}


# ── Helpers ──────────────────────────────────────────────────

def extract_poi_chips(text: str) -> list:
    """Extract <poi_chips>[...]</poi_chips> JSON from agent response."""
    match = re.search(r"<poi_chips>(.*?)</poi_chips>", text, re.DOTALL)
    if match:
        try:
            chips = json.loads(match.group(1))
            if isinstance(chips, list):
                return chips
        except json.JSONDecodeError:
            pass
    return []


def clean_response_text(text: str) -> str:
    """Strip poi_chips tags and JSON from spoken text."""
    text = re.sub(r"<poi_chips>.*?</poi_chips>", "", text, flags=re.DOTALL)
    return text.strip()


def build_multimodal_message(message: dict) -> types.Content:
    """Build a Gemini multimodal Content from a frame + GPS payload."""
    parts = []

    image_b64 = message.get("image_b64", "")
    if image_b64:
        if "," in image_b64:
            image_b64 = image_b64.split(",", 1)[1]
        image_bytes = base64.b64decode(image_b64)
        parts.append(types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))

    gps = message.get("gps")
    if gps:
        lat, lng = gps.get("lat"), gps.get("lng")
        parts.append(types.Part.from_text(
            text=f"Tourist GPS: lat={lat}, lng={lng} (Brooklyn, NYC). "
                 f"Find what's interesting nearby and guide them."
        ))
    else:
        parts.append(types.Part.from_text(
            text="The tourist is in Brooklyn. No GPS provided yet."
        ))

    return types.Content(role="user", parts=parts)


# ── WebSocket: /ws/analyze ────────────────────────────────────
# Used for text-based tourist guide interactions:
#   - "discover" message: proactive POI discovery (sent every ~60s)
#   - "chat" message: text query from tourist
#   - "frame" message: camera frame + GPS (optional visual context)

@app.websocket("/ws/analyze")
async def analyze(websocket: WebSocket):
    await websocket.accept()

    session = await session_service.create_session(
        app_name="waypoint", user_id="user"
    )
    runner = Runner(
        agent=root_agent, app_name="waypoint", session_service=session_service
    )
    session_id = session.id

    try:
        async for raw_message in websocket.iter_text():
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = message.get("type")

            # ── Proactive discovery ────────────────────────────
            if msg_type == "discover":
                gps = message.get("gps")
                if GPS_REQUIRED and (not gps or gps.get("lat") is None):
                    await websocket.send_json({
                        "type": "gps_required",
                        "message": "GPS required to find nearby places.",
                    })
                    continue

                lat, lng = gps["lat"], gps["lng"]

                # Call tools directly — reliable, no JSON parsing of agent output
                poi_result = await asyncio.to_thread(get_nearby_pois, lat, lng)
                pois = poi_result.get("pois", [])

                if pois:
                    # Enrich top POI_CHIPS_MAX places with walk time + maps URL
                    chips = []
                    for poi in pois[:POI_CHIPS_MAX]:
                        if poi.get("lat") and poi.get("lng"):
                            dist = await asyncio.to_thread(
                                get_distance, lat, lng, poi["lat"], poi["lng"]
                            )
                            url = build_maps_url(poi["name"], poi["lat"], poi["lng"])
                            chips.append({
                                **poi,
                                "walk_min": round(dist.get("duration_min", 0)),
                                "maps_url": url.get("maps_url", ""),
                            })

                    if chips:
                        await websocket.send_json({"type": "poi_chips", "pois": chips})

                    # Ask agent for a short spoken intro about what's nearby
                    names = ", ".join(c["name"] for c in chips[:3])
                    intro_prompt = (
                        f"I found these nearby places for a tourist at lat={lat}, lng={lng}: {names}. "
                        f"Give a 1-2 sentence friendly spoken intro about what's nearby — "
                        f"don't list all the places, just give a warm overview."
                    )
                    spoken = await _run_agent(runner, session_id, types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=intro_prompt)],
                    ))
                    if spoken:
                        await websocket.send_json({"type": "narration", "text": clean_response_text(spoken)})
                else:
                    # No POIs found — ask agent to greet the tourist
                    fallback_prompt = (
                        f"A tourist just arrived in Brooklyn at lat={lat}, lng={lng}. "
                        f"Welcome them and ask what they'd like to explore."
                    )
                    spoken = await _run_agent(runner, session_id, types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=fallback_prompt)],
                    ))
                    if spoken:
                        await websocket.send_json({"type": "narration", "text": clean_response_text(spoken)})

            # ── Text chat (tourist typed or speech-to-text) ───
            elif msg_type == "chat":
                user_text = message.get("text", "").strip()
                gps = message.get("gps")
                if not user_text:
                    continue

                gps_context = ""
                if gps:
                    gps_context = f" [Tourist GPS: lat={gps['lat']}, lng={gps['lng']}]"

                content = types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=user_text + gps_context)],
                )
                final_text = await _run_agent(runner, session_id, content)
                if final_text:
                    chips = extract_poi_chips(final_text)
                    spoken = clean_response_text(final_text)
                    if spoken:
                        await websocket.send_json({"type": "narration", "text": spoken})
                    if chips:
                        await websocket.send_json({"type": "poi_chips", "pois": chips})

            # ── Camera frame with GPS (visual context) ────────
            elif msg_type == "frame":
                gps = message.get("gps")
                if GPS_REQUIRED and (not gps or gps.get("lat") is None):
                    await websocket.send_json({
                        "type": "gps_required",
                        "message": "GPS required to guide you.",
                    })
                    continue

                content = build_multimodal_message(message)
                final_text = await _run_agent(runner, session_id, content)
                if final_text:
                    chips = extract_poi_chips(final_text)
                    spoken = clean_response_text(final_text)
                    if spoken:
                        await websocket.send_json({"type": "narration", "text": spoken})
                    if chips:
                        await websocket.send_json({"type": "poi_chips", "pois": chips})

            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}",
                })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


async def _run_agent(runner: Runner, session_id: str, content: types.Content) -> str:
    """Run the ADK agent and return the final text response."""
    final_text = ""
    response = runner.run_async(
        user_id="user",
        session_id=session_id,
        new_message=content,
    )
    async for event in response:
        if event.is_final_response() and event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    final_text += part.text
    return final_text


# ── WebSocket: /ws/voice ──────────────────────────────────────
# Real-time voice conversation via Gemini Live API (audio in / audio out)

@app.websocket("/ws/voice")
async def voice(websocket: WebSocket):
    await handle_voice(websocket)


# ── Static frontend ───────────────────────────────────────────
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.get("/")
async def serve_index():
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
