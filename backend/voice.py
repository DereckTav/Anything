"""Real-time voice conversation endpoint using Gemini Live API — WAYPOINT tourist guide."""

import asyncio
import json
import base64

from fastapi import WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types

from config import GOOGLE_API_KEY
from agent.tools.poi import get_nearby_pois
from agent.tools.vision import analyze_frame
from agent.tools.maps import get_distance, get_transit_directions, build_maps_url

VOICE_SYSTEM_PROMPT = """You are WAYPOINT, a friendly city exploration companion. You're having a real-time voice conversation.

Be conversational. Just talk naturally. Do NOT call tools unless the user explicitly asks you to find, look up, or navigate somewhere.

RULES:
- Keep responses SHORT — 1-2 sentences. This is spoken audio.
- Be warm and enthusiastic, like a friend showing someone around.
- Never say "As an AI". Just talk.
- Chat freely. Ask follow-up questions. React to what they say.

ONLY use tools when the user asks you to:
- "What's nearby?" / "Find me something" → call get_nearby_pois (results appear on their Nearby screen)
- "What is that?" / "What am I looking at?" → call analyze_frame
- "How far is X?" → call get_distance
- "How do I get there?" / "Take me there" → call get_transit_directions or build_maps_url
- For vague requests ("something exotic"), ask one quick clarifying question, then use get_nearby_pois

If no GPS is available, ask where they are before using location tools.
"""

# Tool registry for Live API tool calls
TOOL_FUNCTIONS = {
    "get_nearby_pois": get_nearby_pois,
    "analyze_frame": analyze_frame,
    "get_distance": get_distance,
    "get_transit_directions": get_transit_directions,
    "build_maps_url": build_maps_url,
}

# Tool declarations for Gemini Live API
TOOL_DECLARATIONS = [
    types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name="get_nearby_pois",
            description="Find Points of Interest near the user's GPS location",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "lat": types.Schema(type="NUMBER", description="User's current latitude"),
                    "lng": types.Schema(type="NUMBER", description="User's current longitude"),
                    "radius_meters": types.Schema(
                        type="INTEGER",
                        description="Search radius in meters (default 500)",
                    ),
                },
                required=["lat", "lng"],
            ),
        ),
        types.FunctionDeclaration(
            name="analyze_frame",
            description="Analyze a camera frame to identify landmarks, objects, and text visible to the user",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "image_b64": types.Schema(
                        type="STRING",
                        description="Base64-encoded JPEG image from the user's camera",
                    ),
                },
                required=["image_b64"],
            ),
        ),
        types.FunctionDeclaration(
            name="get_distance",
            description="Get walking distance and time from the user to a destination",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "origin_lat": types.Schema(type="NUMBER", description="User's current latitude"),
                    "origin_lng": types.Schema(type="NUMBER", description="User's current longitude"),
                    "dest_lat": types.Schema(type="NUMBER", description="Destination latitude"),
                    "dest_lng": types.Schema(type="NUMBER", description="Destination longitude"),
                },
                required=["origin_lat", "origin_lng", "dest_lat", "dest_lng"],
            ),
        ),
        types.FunctionDeclaration(
            name="get_transit_directions",
            description="Get public transit directions (subway, bus) between two points with step-by-step route",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "origin_lat": types.Schema(type="NUMBER", description="User's current latitude"),
                    "origin_lng": types.Schema(type="NUMBER", description="User's current longitude"),
                    "dest_lat": types.Schema(type="NUMBER", description="Destination latitude"),
                    "dest_lng": types.Schema(type="NUMBER", description="Destination longitude"),
                },
                required=["origin_lat", "origin_lng", "dest_lat", "dest_lng"],
            ),
        ),
        types.FunctionDeclaration(
            name="build_maps_url",
            description="Build a Google Maps navigation link so the user can navigate to a destination",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "dest_name": types.Schema(type="STRING", description="Name of the destination"),
                    "dest_lat": types.Schema(type="NUMBER", description="Destination latitude"),
                    "dest_lng": types.Schema(type="NUMBER", description="Destination longitude"),
                },
                required=["dest_name", "dest_lat", "dest_lng"],
            ),
        ),
    ]),
]


def _format_poi_context(pois: list) -> str:
    """Format pre-fetched POIs as context for the voice agent system prompt."""
    if not pois:
        return ""

    lines = ["\nYou already know these places near the user (pre-loaded, no need to call tools for these):"]
    for p in pois[:15]:  # Cap at 15 to keep context manageable
        line = f"- {p['name']} ({p['type']}) — {p.get('walk_min', '?')} min walk"
        if p.get('address'):
            line += f", {p['address']}"
        lines.append(line)

    lines.append("\nUse this info to answer casual questions. Only call get_nearby_pois if the user wants a fresh search or a different area.")
    return "\n".join(lines)


async def handle_voice(websocket: WebSocket):
    """Handle real-time voice conversation via Gemini Live API."""
    await websocket.accept()

    # Get initial GPS from query params
    lat = websocket.query_params.get("lat")
    lng = websocket.query_params.get("lng")
    gps_context = ""
    poi_context = ""
    cached_pois = []
    if lat and lng:
        gps_context = f" The user is currently at GPS coordinates: lat={lat}, lng={lng}."
        # Pre-fetch nearby POIs once — used for both Gemini context and frontend Nearby tab
        try:
            cached_result = await asyncio.to_thread(get_nearby_pois, float(lat), float(lng), 3200)
            cached_pois = cached_result.get("pois", [])
            poi_context = _format_poi_context(cached_pois)
        except Exception as e:
            print(f"[Voice] POI pre-cache failed: {e}")

    client = genai.Client(api_key=GOOGLE_API_KEY)

    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=VOICE_SYSTEM_PROMPT + gps_context + poi_context,
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name="Kore"
                )
            )
        ),
        tools=TOOL_DECLARATIONS,
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )

    # Send pre-cached POIs to frontend so Nearby tab is populated immediately
    if cached_pois:
        await websocket.send_json({"type": "poi_chips", "pois": cached_pois})

    try:
        print("[Voice] Connecting to Gemini Live API...")
        async with client.aio.live.connect(
            model="gemini-2.5-flash-native-audio-latest",
            config=config,
        ) as session:
            print("[Voice] Connected to Gemini Live API!")

            # Task: receive from Gemini and forward to client
            async def gemini_to_client():
                try:
                    while True:
                        async for msg in session.receive():
                            # Audio response
                            if msg.data:
                                audio_b64 = base64.b64encode(msg.data).decode()
                                await websocket.send_json({
                                    "type": "audio",
                                    "data": audio_b64,
                                })

                            # Transcription of agent's speech
                            if (
                                msg.server_content
                                and hasattr(msg.server_content, "output_transcription")
                                and msg.server_content.output_transcription
                            ):
                                await websocket.send_json({
                                    "type": "transcript",
                                    "role": "agent",
                                    "text": msg.server_content.output_transcription.text,
                                })

                            # Transcription of user's speech
                            if (
                                msg.server_content
                                and hasattr(msg.server_content, "input_transcription")
                                and msg.server_content.input_transcription
                            ):
                                await websocket.send_json({
                                    "type": "transcript",
                                    "role": "user",
                                    "text": msg.server_content.input_transcription.text,
                                })

                            # Tool calls
                            if msg.tool_call:
                                for fc in msg.tool_call.function_calls:
                                    # Notify frontend that a tool is being called
                                    tool_labels = {
                                        "get_nearby_pois": "Searching nearby places...",
                                        "analyze_frame": "Analyzing what you see...",
                                        "get_distance": "Checking distance...",
                                        "get_transit_directions": "Finding transit routes...",
                                        "build_maps_url": "Getting directions...",
                                    }
                                    await websocket.send_json({
                                        "type": "tool_status",
                                        "tool": fc.name,
                                        "status": "calling",
                                        "label": tool_labels.get(fc.name, f"Using {fc.name}..."),
                                    })

                                    func = TOOL_FUNCTIONS.get(fc.name)
                                    if func:
                                        result = await asyncio.to_thread(func, **fc.args)
                                    else:
                                        result = {"error": f"Unknown tool: {fc.name}"}

                                    # Notify frontend tool is done (or errored)
                                    has_error = "error" in result and result["error"]
                                    await websocket.send_json({
                                        "type": "tool_status",
                                        "tool": fc.name,
                                        "status": "error" if has_error else "done",
                                        "label": result.get("error", "") if has_error else "",
                                    })

                                    await session.send_tool_response(
                                        function_responses=types.FunctionResponse(
                                            name=fc.name,
                                            response=result,
                                            id=fc.id,
                                        )
                                    )

                                    # UPDATE FRONTEND BASED ON TOOL RESULTS

                                    # 1. Populate nearby list
                                    if fc.name == "get_nearby_pois" and "pois" in result:
                                        await websocket.send_json({
                                            "type": "poi_chips",
                                            "pois": result["pois"],
                                        })

                                    # 2. Forward maps URL for "Take me there" button
                                    if fc.name == "build_maps_url" and "maps_url" in result:
                                        await websocket.send_json({
                                            "type": "maps_url",
                                            "maps_url": result["maps_url"],
                                            "destination": result.get("destination", ""),
                                        })

                            # Turn complete
                            if msg.server_content and msg.server_content.turn_complete:
                                await websocket.send_json({"type": "turn_complete"})
                except Exception as e:
                    if "close" not in str(e).lower():
                        print(f"[Voice] Gemini receive error: {e}")

            # Task: receive from client and forward to Gemini
            async def client_to_gemini():
                try:
                    async for raw in websocket.iter_text():
                        msg = json.loads(raw)

                        if msg["type"] == "audio":
                            # Mic audio — forward as PCM to Gemini
                            audio_bytes = base64.b64decode(msg["data"])
                            await session.send_realtime_input(
                                audio=types.Blob(
                                    data=audio_bytes,
                                    mime_type="audio/pcm;rate=16000",
                                )
                            )

                        elif msg["type"] == "frame":
                            # Camera frame — send as image context
                            img_b64 = msg.get("image_b64", "")
                            if "," in img_b64:
                                img_b64 = img_b64.split(",", 1)[1]
                            img_bytes = base64.b64decode(img_b64)
                            await session.send_realtime_input(
                                media=types.Blob(
                                    data=img_bytes,
                                    mime_type="image/jpeg",
                                )
                            )

                        elif msg["type"] == "gps":
                            # GPS update — send as text context
                            await session.send_client_content(
                                turns=types.Content(
                                    role="user",
                                    parts=[types.Part.from_text(
                                        text=f"GPS updated: lat={msg['lat']}, lng={msg['lng']}"
                                    )],
                                ),
                                turn_complete=False,
                            )
                except WebSocketDisconnect:
                    pass
                except Exception as e:
                    if "close" not in str(e).lower():
                        print(f"[Voice] Client receive error: {e}")

            # Run both tasks concurrently
            tasks = [
                asyncio.create_task(gemini_to_client()),
                asyncio.create_task(client_to_gemini()),
            ]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
