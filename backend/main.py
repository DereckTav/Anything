import asyncio
import json
import base64
import re
import time
import string
import random
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agent.agent import root_agent
from agent.prompts import LAYER_SUMMARY_PROMPT, REPORT_PROMPT
from config import GPS_REQUIRED, REPORT_ID_PREFIX, MAX_STILLS_PER_SESSION
from report.generator import generate_pdf

app = FastAPI(title="URBANLENS API")
session_service = InMemorySessionService()

# In-memory store for session data (narration history, stills, etc.)
sessions_data: dict[str, dict] = {}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "urbanlens"}


def generate_report_id() -> str:
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(random.choices(chars, k=4))
    return f"{REPORT_ID_PREFIX}-{suffix}"


def build_multimodal_message(message: dict) -> types.Content:
    """Build a Gemini-compatible multimodal message from a frame + GPS payload."""
    parts = []

    # Add image
    image_b64 = message.get("image_b64", "")
    if image_b64:
        # Strip data URL prefix if present
        if "," in image_b64:
            image_b64 = image_b64.split(",", 1)[1]
        image_bytes = base64.b64decode(image_b64)
        parts.append(types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))

    # Add GPS context as text
    gps = message.get("gps")
    if gps:
        lat = gps.get("lat")
        lng = gps.get("lng")
        parts.append(types.Part.from_text(
            text=f"Current GPS coordinates: lat={lat}, lng={lng}. "
                 f"Analyze this frame and call all data tools with these coordinates."
        ))
    else:
        parts.append(types.Part.from_text(
            text="No GPS coordinates provided with this frame."
        ))

    return types.Content(role="user", parts=parts)


def extract_ar_labels(text: str) -> list:
    """Extract AR labels from agent response text."""
    # Look for <ar_labels>...</ar_labels> tags
    match = re.search(r"<ar_labels>(.*?)</ar_labels>", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Fallback: look for JSON array in the text
    match = re.search(r'\[[\s\S]*?\{[\s\S]*?"source"[\s\S]*?\}[\s\S]*?\]', text)
    if match:
        try:
            labels = json.loads(match.group())
            # Validate structure
            if all(
                isinstance(l, dict) and "source" in l and "text" in l and "position" in l
                for l in labels
            ):
                return labels
        except json.JSONDecodeError:
            pass

    return []


def clean_narration_text(text: str) -> str:
    """Remove AR label JSON and tags from narration text."""
    # Remove <ar_labels>...</ar_labels> blocks
    text = re.sub(r"<ar_labels>.*?</ar_labels>", "", text, flags=re.DOTALL)
    # Remove stray JSON arrays that look like AR labels
    text = re.sub(r'\[[\s\S]*?\{[\s\S]*?"source"[\s\S]*?\}[\s\S]*?\]', "", text)
    return text.strip()


def extract_json_from_text(text: str) -> dict | None:
    """Extract a JSON object from agent response text."""
    # Try to find JSON object in the text
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


@app.websocket("/ws/analyze")
async def analyze(websocket: WebSocket):
    await websocket.accept()

    session = await session_service.create_session(
        app_name="urbanlens", user_id="user"
    )
    runner = Runner(
        agent=root_agent, app_name="urbanlens", session_service=session_service
    )

    session_id = session.id
    sessions_data[session_id] = {
        "narrations": [],
        "stills": [],
        "start_time": time.time(),
        "last_layer_data": None,
        "report_id": generate_report_id(),
    }

    try:
        async for raw_message in websocket.iter_text():
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON message",
                })
                continue

            msg_type = message.get("type")

            if msg_type == "frame":
                gps = message.get("gps")

                # Enforce GPS requirement
                if GPS_REQUIRED and (not gps or gps.get("lat") is None or gps.get("lng") is None):
                    await websocket.send_json({
                        "type": "gps_required",
                        "message": "GPS coordinates are required for analysis. Please enable location services.",
                    })
                    continue

                # Build multimodal message and run agent
                content = build_multimodal_message(message)
                response = runner.run_async(
                    user_id="user",
                    session_id=session_id,
                    new_message=content,
                )

                final_text = ""
                async for event in response:
                    if event.is_final_response() and event.content and event.content.parts:
                        for part in event.content.parts:
                            if part.text:
                                final_text += part.text

                if final_text:
                    ar_labels = extract_ar_labels(final_text)
                    narration_text = clean_narration_text(final_text)

                    # Store narration
                    elapsed = time.time() - sessions_data[session_id]["start_time"]
                    minutes = int(elapsed // 60)
                    seconds = int(elapsed % 60)
                    timestamp = f"{minutes:02d}:{seconds:02d}"

                    sessions_data[session_id]["narrations"].append({
                        "timestamp": timestamp,
                        "text": narration_text,
                    })

                    # Store still (up to max)
                    if (
                        message.get("image_b64")
                        and len(sessions_data[session_id]["stills"]) < MAX_STILLS_PER_SESSION
                    ):
                        sessions_data[session_id]["stills"].append({
                            "image_b64": message["image_b64"],
                            "timestamp": timestamp,
                        })

                    await websocket.send_json({
                        "type": "narration",
                        "text": narration_text,
                        "ar_labels": ar_labels,
                    })

            elif msg_type == "pause":
                # Ask agent to produce structured layer data
                layer_content = types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=LAYER_SUMMARY_PROMPT)],
                )
                response = runner.run_async(
                    user_id="user",
                    session_id=session_id,
                    new_message=layer_content,
                )

                layer_text = ""
                async for event in response:
                    if event.is_final_response() and event.content and event.content.parts:
                        for part in event.content.parts:
                            if part.text:
                                layer_text += part.text

                layer_data = extract_json_from_text(layer_text)
                if layer_data:
                    sessions_data[session_id]["last_layer_data"] = layer_data
                    await websocket.send_json({"type": "layer_data", **layer_data})
                else:
                    # Return a fallback structure
                    fallback = {
                        "zoning": {"district": "N/A", "far": 0.0, "description": "Data unavailable"},
                        "environment": {"canopy_pct": 0, "aqi": 0, "aqi_category": "Unknown"},
                        "safety": {"flood_risk": "Low Risk", "emergency_response_min": 0.0},
                        "activity_311": {"complaints": []},
                    }
                    await websocket.send_json({"type": "layer_data", **fallback})

            elif msg_type == "end":
                # Ask agent to compile synthesis report
                report_content = types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=REPORT_PROMPT)],
                )
                response = runner.run_async(
                    user_id="user",
                    session_id=session_id,
                    new_message=report_content,
                )

                report_text = ""
                async for event in response:
                    if event.is_final_response() and event.content and event.content.parts:
                        for part in event.content.parts:
                            if part.text:
                                report_text += part.text

                report_data = extract_json_from_text(report_text)
                report_id = sessions_data[session_id]["report_id"]

                if report_data:
                    report_data["id"] = report_id
                    # Ensure narrative exists from session data if agent didn't provide it
                    if not report_data.get("narrative"):
                        report_data["narrative"] = sessions_data[session_id]["narrations"]
                else:
                    # Build from session data
                    report_data = {
                        "id": report_id,
                        "narrative": sessions_data[session_id]["narrations"],
                        "score": 5.0,
                        "verdict": "Analysis session completed. Review the narrative log for detailed findings.",
                    }

                # Store report for PDF generation
                sessions_data[session_id]["report"] = report_data

                await websocket.send_json({"type": "report", **report_data})

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
    finally:
        # Clean up session data after a delay (keep for PDF export)
        # In production, use a background task with TTL
        pass


@app.get("/report/{session_id}/pdf")
async def export_pdf(session_id: str):
    """Generate and download PDF report for a session."""
    # Find session by report ID
    target_session = None
    for sid, sdata in sessions_data.items():
        if sdata.get("report_id") == session_id or sid == session_id:
            target_session = sdata
            break

    if not target_session or "report" not in target_session:
        return JSONResponse(
            status_code=404,
            content={"error": "Report not found. Complete a session first."},
        )

    pdf_path = generate_pdf(target_session)
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"URBANLENS-{target_session['report_id']}.pdf",
    )
