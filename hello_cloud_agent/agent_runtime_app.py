"""Repo-root import compatibility for the hello cloud Agent Runtime app."""

from vertexai.agent_engines.templates.adk import AdkApp

from hello_cloud_agent.hello_cloud_agent.agent import app as adk_app

agent_runtime = AdkApp(app=adk_app)

__all__ = ["agent_runtime"]
