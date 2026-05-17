import os
from pathlib import Path

from google.adk.agents import Agent
from google.adk.tools import google_search


def _load_local_adk_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.is_file():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip().lstrip("\ufeff")
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").upper() == "TRUE":
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"


_load_local_adk_env()


CONTACT_SEARCH_AGENT_INSTRUCTION = """
You are contact_search_agent, a search-only specialist for public web contact discovery.

Use only Google Search. Return compact public web results for the requested query.
Do not invent people, roles, URLs, or emails. Do not use private, logged-in-only,
CAPTCHA, paywalled, or bypassed sources.
Prefer official websites, contact pages, careers pages, leadership/team pages,
and public professional result URLs for role/person queries.

When asked for results, return JSON only:
[
  {"title": "...", "url": "https://...", "snippet": "..."}
]
"""


contact_search_agent = Agent(
    model="gemini-2.5-flash",
    name="contact_search_agent",
    description="Search-only public web specialist for Contact Resolver live mode.",
    instruction=CONTACT_SEARCH_AGENT_INSTRUCTION,
    tools=[google_search],
)
