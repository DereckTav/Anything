from google.adk.agents import LlmAgent
from google.genai import types
from .tools import get_nearby_pois, analyze_frame, get_distance, build_maps_url
from .tools.search import search_web
from .prompts import SYSTEM_PROMPT

# Note: google_search built-in tool cannot be combined with custom function calling
# in the same Gemini request. Instead, search_web makes its own grounded Gemini call
# internally — same result, no conflict.
root_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="waypoint_agent",
    description="Brooklyn tourist guide — finds nearby places, identifies landmarks, provides walking directions",
    instruction=SYSTEM_PROMPT,
    tools=[
        get_nearby_pois,
        analyze_frame,
        get_distance,
        build_maps_url,
        search_web,
    ],
    generate_content_config=types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    ),
)
