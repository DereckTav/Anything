from google.adk.agents import LlmAgent
from google.adk.tools import google_search
from .tools import get_nearby_pois, analyze_frame, get_distance, build_maps_url
from .prompts import SYSTEM_PROMPT

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
        google_search,
    ],
)
