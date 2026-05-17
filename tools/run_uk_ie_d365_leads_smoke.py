import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from uk_ie_d365_leads.agent import root_agent
from uk_ie_d365_leads.tools.lead_tools import (
    discover_d365_search_providers,
    find_uk_ie_d365_leads,
)


def main() -> int:
    providers = discover_d365_search_providers()
    result = find_uk_ie_d365_leads(
        query='"Dynamics 365" "support" ("UK" OR "Ireland")',
        max_results=3,
        provider_name="definitely_missing_provider",
    )
    smoke = {
        "agent_name": root_agent.name,
        "sub_agents": [agent.name for agent in root_agent.sub_agents],
        "provider_discovery_shape": sorted(providers.keys()),
        "blocked_status": result["status"],
        "blocked_lead_count": result["lead_count"],
        "no_fake_leads": result["leads"] == [],
    }
    print(json.dumps(smoke, indent=2))
    if smoke["agent_name"] != "uk_ie_d365_leads":
        return 1
    if "d365_search_agent" not in smoke["sub_agents"]:
        return 1
    if smoke["blocked_status"] != "blocked" or smoke["blocked_lead_count"] != 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
