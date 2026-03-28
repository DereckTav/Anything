"""
Google Vision API tool.
Identifies landmarks, labels, and text in a camera frame.
Used to give the tourist guide visual context about what the user is looking at.
"""

import httpx
from config import GOOGLE_API_KEY, TOOL_TIMEOUT_S


def analyze_frame(image_b64: str) -> dict:
    """
    Analyze a camera frame to identify landmarks, objects, and signage visible in the image.
    Use this when the tourist points their camera at something and wants to know what it is,
    or when you want to understand the tourist's visual surroundings.

    Args:
        image_b64: Base64-encoded JPEG image from the tourist's camera
    """
    if not GOOGLE_API_KEY:
        return {"error": "Google API key not configured", "landmarks": [], "labels": []}

    # Strip data URL prefix if present
    if "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]

    try:
        url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_API_KEY}"
        payload = {
            "requests": [{
                "image": {"content": image_b64},
                "features": [
                    {"type": "LANDMARK_DETECTION", "maxResults": 5},
                    {"type": "LABEL_DETECTION", "maxResults": 8},
                    {"type": "TEXT_DETECTION", "maxResults": 5},
                ],
            }]
        }

        with httpx.Client(timeout=TOOL_TIMEOUT_S) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()

        annotations = result.get("responses", [{}])[0]

        # Check for Vision API errors
        if "error" in annotations:
            return {"error": annotations["error"].get("message", "Vision API error"), "landmarks": [], "labels": []}

        # Landmarks (e.g. "Brooklyn Bridge", "Jane's Carousel")
        landmarks = []
        for lm in annotations.get("landmarkAnnotations", []):
            landmarks.append({
                "name": lm.get("description"),
                "confidence": round(lm.get("score", 0), 2),
            })

        # Labels (e.g. "Bridge", "Park", "Building", "Street")
        labels = [
            l.get("description")
            for l in annotations.get("labelAnnotations", [])[:6]
            if l.get("description")
        ]

        # Text from signs, storefronts, etc.
        text_items = []
        full_text = ""
        for i, t in enumerate(annotations.get("textAnnotations", [])):
            desc = t.get("description", "").strip()
            if i == 0:
                # First annotation is the full concatenated text
                full_text = desc[:200] if desc else ""
            else:
                if desc and len(desc) > 2 and len(text_items) < 5:
                    text_items.append(desc)

        return {
            "landmarks": landmarks,
            "labels": labels,
            "text": text_items,
            "full_text": full_text,
        }

    except httpx.TimeoutException:
        return {"error": "Vision API request timed out", "landmarks": [], "labels": []}
    except Exception as e:
        return {"error": str(e), "landmarks": [], "labels": []}
