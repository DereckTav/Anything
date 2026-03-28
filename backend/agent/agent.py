from google.adk.agents import LlmAgent
from .tools import pluto, complaints, vision_zero, tree_census, geocoder, air_quality
from .prompts import SYSTEM_PROMPT

root_agent = LlmAgent(
    model="gemini-2.5-pro",
    name="urbanlens_agent",
    description="Real-time NYC urban site analyst with vision and voice",
    instruction=SYSTEM_PROMPT,
    tools=[
        geocoder.get_block_info,
        pluto.get_zoning_data,
        complaints.get_311_complaints,
        vision_zero.get_safety_data,
        tree_census.get_canopy_data,
        air_quality.get_air_quality,
    ],
)
