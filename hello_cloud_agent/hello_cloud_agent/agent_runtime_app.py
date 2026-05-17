"""Agent Runtime entrypoint for the PROMPT#07 hello-world agent."""

from vertexai.agent_engines.templates.adk import AdkApp

from hello_cloud_agent.agent import app as adk_app

agent_runtime = AdkApp(app=adk_app)
