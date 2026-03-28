---
name: google-adk
description: This skill should be used when the user asks to "build an agent with ADK", "use Google ADK", "create a Gemini agent", "use google.adk", "set up google-adk", "use LlmAgent", "run adk web", "adk run", "deploy to Vertex AI", mentions "google.adk.agents", "gemini-2.5-flash agent", or discusses Google Agent Development Kit, Vertex AI agents, or Google AI Studio agent development.
version: 1.0.0
---

# Google Agent Development Kit (ADK)

## Overview

Google ADK is a Python framework for building agents powered by Gemini models. It supports Google AI Studio (quickstart) and Vertex AI (production).

**Install:** `pip install google-adk` (requires Python 3.12+, recommend `uv`)

## Authentication

### Option A: Google AI Studio (Fast Prototyping)
```env
GOOGLE_GENAI_USE_VERTEXAI=FALSE
GOOGLE_API_KEY=your_api_key_from_aistudio.google.com
```

### Option B: Vertex AI (Production)
```env
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=your_project_id
GOOGLE_CLOUD_LOCATION=us-central1
```
Run `gcloud auth application-default login` for local dev credentials.

## Required Project Files

Every ADK agent needs exactly three files:

**`agent.py`** — instantiate the agent:
```python
from google.adk.agents import LlmAgent

root_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="my_agent",
    description="Brief description of what this agent does",
    instruction="Your system prompt here"
)
```

**`__init__.py`** — expose the agent for the runner:
```python
from . import agent
```

**`.env`** — credentials (never commit this):
```env
GOOGLE_GENAI_USE_VERTEXAI=FALSE
GOOGLE_API_KEY=your_key_here
```

## Running Agents

```bash
# CLI mode
adk run my_agent_folder

# Web UI at http://localhost:8000 (better for debugging, renders Markdown)
adk web
```

## Key Agent Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `model` | Yes | e.g. `"gemini-2.5-flash"`, `"gemini-2.5-pro"` |
| `name` | Yes | snake_case identifier |
| `instruction` | Yes | System prompt / agent behavior |
| `description` | Recommended | For multi-agent routing |
| `tools` | No | List of callable functions or built-in tools |
| `sub_agents` | No | List of child agents for orchestration |

## Built-in Tools

```python
from google.adk.tools import google_search, code_execution

agent = LlmAgent(
    model="gemini-2.5-flash",
    name="research_agent",
    instruction="Use search to answer questions.",
    tools=[google_search]
)
```

## Multi-Agent Pattern

```python
from google.adk.agents import LlmAgent

sub_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="specialist",
    description="Handles specialized tasks",
    instruction="You specialize in..."
)

orchestrator = LlmAgent(
    model="gemini-2.5-flash",
    name="orchestrator",
    instruction="Route tasks to the right agent.",
    sub_agents=[sub_agent]
)
```

## Custom Tools

```python
def get_weather(city: str) -> dict:
    """Get weather for a city. Args: city: The city name."""
    # implementation
    return {"temp": 72, "condition": "sunny"}

agent = LlmAgent(
    model="gemini-2.5-flash",
    name="weather_agent",
    instruction="Help users with weather questions.",
    tools=[get_weather]
)
```
ADK uses the function signature and docstring to describe tools to the model — keep them descriptive.

## Model Names

- `gemini-2.5-flash` — fast, efficient, best for most tasks
- `gemini-2.5-pro` — most capable, for complex reasoning
- `gemini-2.0-flash-live-001` — Live API (voice/video streaming)

## Common Issues

**429 Rate Limit** — Add retry config or upgrade quota in Google Cloud Console.

**Import errors** — Ensure virtual env is activated and `google-adk` is installed.

**Auth errors** — For Vertex AI, verify `gcloud auth application-default login` was run and project/location env vars are set.

**Agent not found** — `adk run` expects a folder name matching a Python package with `__init__.py` that imports `agent`.
