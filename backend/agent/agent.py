from google.adk.agents import LlmAgent
from google.adk.tools import google_search
from .tools import get_nearby_pois, analyze_frame, get_distance, get_transit_directions, build_maps_url
from .prompts import SYSTEM_PROMPT

root_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="waypoint_agent",
    description="Intelligent city exploration companion — understands preferences, finds matching places, provides transit and walking directions",
    instruction=SYSTEM_PROMPT,
    tools=[
        get_nearby_pois,
        analyze_frame,
        get_distance,
        get_transit_directions,
        build_maps_url,
        google_search,
    ],
)
