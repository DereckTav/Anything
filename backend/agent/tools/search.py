"""
Web search tool for the voice endpoint.

Makes a dedicated Gemini API call with Google Search grounding enabled.
This sidesteps the Gemini constraint that prevents mixing built-in tools
(google_search) with custom function calling in the same request.

The ADK text agent uses a proper search sub-agent instead.
This tool is only registered with the Gemini Live voice endpoint.
"""

from google import genai
from google.genai import types
from config import GOOGLE_API_KEY, TOOL_TIMEOUT_S


def search_web(query: str) -> dict:
    """
    Search the internet for current information about a place or topic.
    Use this when the tourist asks about opening hours, admission prices,
    current events, recent reviews, or anything requiring up-to-date facts.

    Args:
        query: What to search for, e.g. "Jane's Carousel Brooklyn hours admission price"
    """
    if not GOOGLE_API_KEY:
        return {"error": "No API key configured", "query": query}

    try:
        client = genai.Client(api_key=GOOGLE_API_KEY)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=(
                f"Search for this and give me the key facts in 2-3 sentences: {query}. "
                f"Focus on practical tourist information: hours, prices, what makes it worth visiting."
            ),
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.1,
            ),
        )
        return {
            "query": query,
            "result": response.text,
        }
    except Exception as e:
        return {"error": str(e), "query": query}
