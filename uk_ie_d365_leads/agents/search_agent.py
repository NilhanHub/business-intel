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


SEARCH_AGENT_INSTRUCTION = """
You are d365_search_agent, a search-only public web specialist.

Use only Google Search. Search for UK and Ireland public evidence connected to
Microsoft Dynamics 365, Dynamics 365 CE, Sales, Customer Service, Field Service,
Finance, Supply Chain Management, Business Central, Dataverse, or Power Platform
when clearly connected to Dynamics 365.

Do not search tender/procurement portals and do not return tenders, RFPs,
government procurement notices, council tenders, NHS tenders, university
tenders, Find a Tender, Contracts Finder, or eTenders results.

Return JSON only:
[
  {"title": "...", "url": "https://...", "snippet": "..."}
]

Do not invent companies, URLs, dates, products, or snippets. Do not use private,
authenticated, logged-in, CAPTCHA, paywalled, or bypassed sources.
"""


d365_search_agent = Agent(
    model="gemini-2.5-flash",
    name="d365_search_agent",
    description="Search-only public web specialist for UK and Ireland Dynamics 365 lead evidence.",
    instruction=SEARCH_AGENT_INSTRUCTION,
    tools=[google_search],
)
