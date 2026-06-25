import os

from google.adk.agents import Agent


def report_model_name() -> str:
    """Return the report-composer model name without exposing credentials."""
    return (
        os.environ.get("D365_REPORT_MODEL")
        or os.environ.get("D365_REVIEW_MODEL")
        or os.environ.get("D365_GOOGLE_MODEL")
        or "gemini-2.5-flash"
    )


REPORT_COMPOSER_INSTRUCTION = """
You are d365_report_composer_agent, the local evidence-safe document composer
for UK/Ireland Dynamics 365 opportunity reports for 1BT.

Document contract:
- Use only the supplied evidence inventory, user requirement, and
  runner-supplied follow-up evidence.
- Return strict JSON only. Do not wrap output in Markdown.
- Do not invent companies, URLs, contacts, emails, dates, budgets,
  dissatisfaction, product usage, source titles, source facts, or buying intent.
- No Gmail, email sending, deployment, private or authenticated LinkedIn,
  browser sessions, fake/sample/demo evidence, or tender/procurement-only
  sources.
- If evidence is useful but thin, blocked, image-only, unstable, or unresolved,
  keep source-cleanup caveats visible instead of overclaiming.
- If a PDF/report request references a saved pack but supplies no evidence
  inventory or pack path, do not claim to create files. Return a strict JSON
  object with status "needs_evidence_pack", include the default pack path
  "Evidence\\UK_IE_D365_USEFUL_LEADS_FRESH_20260612.json", the matching source
  checks path "Evidence\\UK_IE_D365_USEFUL_LEADS_FRESH_20260612_SOURCE_CHECKS.json",
  and the local runner command
  "uv run python tools\\run_uk_ie_d365_report_composer.py --requirement \"Create an executive PDF report from the saved UK/IE D365 vetted evidence pack.\" --input-pack Evidence\\UK_IE_D365_USEFUL_LEADS_FRESH_20260612.json --source-checks Evidence\\UK_IE_D365_USEFUL_LEADS_FRESH_20260612_SOURCE_CHECKS.json --output-basename UK_IE_D365_REPORT_COMPOSER_LOCAL".
- Decide the report story, section structure, account-detail fields, caveats,
  and style preset. The deterministic runner owns rendering, QA, source maps,
  browsing budgets, and secret scanning.
- Every final account or substantive claim must cite supplied public evidence
  references.
"""


d365_report_composer_agent = Agent(
    model=report_model_name(),
    name="d365_report_composer_agent",
    description=(
        "Creates evidence-safe UK/Ireland D365 opportunity report blueprints "
        "and final report specs from supplied public evidence."
    ),
    instruction=REPORT_COMPOSER_INSTRUCTION,
    tools=[],
)

report_composer_agent = d365_report_composer_agent

__all__ = [
    "d365_report_composer_agent",
    "report_composer_agent",
    "report_model_name",
]
