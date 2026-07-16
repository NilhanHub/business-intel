"""Agent Runtime entrypoint for the PROMPT#07 hello-world agent."""

import os

if os.environ.get("BT_ENABLE_AGENT_RUNTIME") != "1":
    raise RuntimeError(
        "Agent Runtime is disabled for this local-only build. "
        "Set BT_ENABLE_AGENT_RUNTIME=1 and install the agent-runtime extra only for an explicitly approved cloud workflow."
    )

try:
    from vertexai.agent_engines.templates.adk import AdkApp
except ImportError as exc:
    raise RuntimeError(
        "Agent Runtime dependencies are not installed. Run `uv sync --extra agent-runtime` only for an explicitly approved cloud workflow."
    ) from exc

from hello_cloud_agent.agent import app as adk_app

agent_runtime = AdkApp(app=adk_app)
