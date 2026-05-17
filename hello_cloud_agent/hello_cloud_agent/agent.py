"""Minimal hello-world ADK agent for PROMPT#07 cloud deployment."""

import os

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

import google.auth

HELLO_RESPONSE = "Hello Nilhan, the Business-Intel cloud agent is working."

_, project_id = google.auth.default()
if project_id:
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project_id)
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are a minimal cloud deployment health-check agent. "
        f"For every user message, reply with exactly: {HELLO_RESPONSE} "
        "Do not add any other words, formatting, tools, links, or explanations."
    ),
    tools=[],
)

app = App(
    root_agent=root_agent,
    name="hello_cloud_agent",
)
