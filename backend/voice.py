"""Real-time voice conversation endpoint using Gemini Live API."""

import asyncio
import json
import base64

from fastapi import WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types

from config import GOOGLE_API_KEY
from agent.tools.geocoder import get_block_info
from agent.tools.pluto import get_zoning_data
from agent.tools.complaints import get_311_complaints
from agent.tools.vision_zero import get_safety_data
from agent.tools.tree_census import get_canopy_data
from agent.tools.air_quality import get_air_quality
VOICE_SYSTEM_PROMPT = """You are URBANLENS, a friendly urban intelligence assistant having a real-time voice conversation. You are embedded in a mobile AR app exploring NYC streets.

RULES:
1. Be conversational and natural. Respond to greetings, questions, small talk — anything the user says.
2. Keep responses SHORT — 1-2 sentences. This is a spoken conversation.
3. You have tools to look up NYC data (zoning, 311 complaints, safety, trees, air quality). Only use them when the user asks about something specific.
4. If the user sends camera frames, you can comment on what you see — but only if relevant to the conversation.
5. Never say "As an AI" or give disclaimers. Talk like a knowledgeable friend.
6. If the user says hi, say hi back. If they ask about the weather, chat about it. Be human.
"""

# Tool registry for Live API tool calls
TOOL_FUNCTIONS = {
    "get_block_info": get_block_info,
    "get_zoning_data": get_zoning_data,
    "get_311_complaints": get_311_complaints,
    "get_safety_data": get_safety_data,
    "get_canopy_data": get_canopy_data,
    "get_air_quality": get_air_quality,
}

# Tool declarations for Gemini
TOOL_DECLARATIONS = [
    types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name="get_block_info",
            description="Convert lat/lng to NYC block info (BBL, address, borough)",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "lat": types.Schema(type="NUMBER", description="Latitude"),
                    "lng": types.Schema(type="NUMBER", description="Longitude"),
                },
                required=["lat", "lng"],
            ),
        ),
        types.FunctionDeclaration(
            name="get_zoning_data",
            description="Get PLUTO zoning, FAR, lot area for a NYC tax lot by BBL",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "bbl": types.Schema(type="STRING", description="10-digit BBL"),
                },
                required=["bbl"],
            ),
        ),
        types.FunctionDeclaration(
            name="get_311_complaints",
            description="Get recent 311 complaints near a location",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "lat": types.Schema(type="NUMBER", description="Latitude"),
                    "lng": types.Schema(type="NUMBER", description="Longitude"),
                },
                required=["lat", "lng"],
            ),
        ),
        types.FunctionDeclaration(
            name="get_safety_data",
            description="Get traffic crash and safety data near a location",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "lat": types.Schema(type="NUMBER", description="Latitude"),
                    "lng": types.Schema(type="NUMBER", description="Longitude"),
                },
                required=["lat", "lng"],
            ),
        ),
        types.FunctionDeclaration(
            name="get_canopy_data",
            description="Get street tree and canopy data near a location",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "lat": types.Schema(type="NUMBER", description="Latitude"),
                    "lng": types.Schema(type="NUMBER", description="Longitude"),
                },
                required=["lat", "lng"],
            ),
        ),
        types.FunctionDeclaration(
            name="get_air_quality",
            description="Get current AQI for a location",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "lat": types.Schema(type="NUMBER", description="Latitude"),
                    "lng": types.Schema(type="NUMBER", description="Longitude"),
                },
                required=["lat", "lng"],
            ),
        ),
    ])
]


async def handle_voice(websocket: WebSocket):
    """Handle real-time voice conversation via Gemini Live API."""
    await websocket.accept()

    # Get initial GPS from query params
    lat = websocket.query_params.get("lat")
    lng = websocket.query_params.get("lng")
    gps_context = ""
    if lat and lng:
        gps_context = f" The user is currently at GPS coordinates: lat={lat}, lng={lng}."

    client = genai.Client(api_key=GOOGLE_API_KEY)

    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=VOICE_SYSTEM_PROMPT + gps_context,
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
                                print(f"[Voice] Got audio: {len(msg.data)} bytes")
                                audio_b64 = base64.b64encode(msg.data).decode()
                                await websocket.send_json({
                                    "type": "audio",
                                    "data": audio_b64,
                                })

                            # Transcription of agent's speech
                            if msg.server_content and hasattr(msg.server_content, 'output_transcription') and msg.server_content.output_transcription:
                                await websocket.send_json({
                                    "type": "transcript",
                                    "role": "agent",
                                    "text": msg.server_content.output_transcription.text,
                                })

                            # Transcription of user's speech
                            if msg.server_content and hasattr(msg.server_content, 'input_transcription') and msg.server_content.input_transcription:
                                await websocket.send_json({
                                    "type": "transcript",
                                    "role": "user",
                                    "text": msg.server_content.input_transcription.text,
                                })

                            # Tool calls
                            if msg.tool_call:
                                for fc in msg.tool_call.function_calls:
                                    func = TOOL_FUNCTIONS.get(fc.name)
                                    if func:
                                        # Run tool in thread pool (they use httpx sync)
                                        result = await asyncio.to_thread(func, **fc.args)
                                    else:
                                        result = {"error": f"Unknown tool: {fc.name}"}

                                    await session.send_tool_response(
                                        function_responses=types.FunctionResponse(
                                            name=fc.name,
                                            response=result,
                                            id=fc.id,
                                        )
                                    )

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
                            print(f"[Voice] Sending {len(audio_bytes)} bytes mic audio to Gemini")
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
