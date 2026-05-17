import os

from google.adk.agents import Agent


def review_model_name() -> str:
    """Return the future live-review model without exposing credentials."""
    return os.environ.get("D365_REVIEW_MODEL") or os.environ.get("D365_GOOGLE_MODEL") or "gemini-2.5-flash"


CLASSIFICATION_REVIEWER_INSTRUCTION = """
You are d365_classification_reviewer, a future Phase 2 LLM-intelligence reviewer
for the uk_ie_d365_leads deterministic classifier.

Phase 1 status:
- You are present as a local ADK-style wrapper only.
- You must not make live LLM calls during Phase 1 dry-run execution.
- You must not search the web, browse, resolve contacts, send email, deploy, call
  gcloud, or register anything in Gemini Enterprise.

Future Phase 2 review contract:
- Review only candidate evidence provided in the input payload.
- Do not invent companies, URLs, Dynamics 365 evidence, contacts, emails, dates,
  source facts, product usage claims, or missing evidence.
- Compare deterministic decisions with reviewer judgment only as an audit pass.
- The deterministic classifier remains the source of truth until separately
  changed by a later deterministic-rule implementation phase.
- Identify suspected false negatives, false positives, tier mismatches, reason
  mismatches, and ambiguous cases.
- Explain which deterministic rule likely failed and recommend deterministic
  rule changes for human review.
- Return JSON-compatible output only.
"""


classification_reviewer_agent = Agent(
    model=review_model_name(),
    name="d365_classification_reviewer",
    description=(
        "Future bounded LLM reviewer for UK/Ireland D365 deterministic "
        "classification audit. Phase 1 wrapper only; no live review is run."
    ),
    instruction=CLASSIFICATION_REVIEWER_INSTRUCTION,
    tools=[],
)


__all__ = ["classification_reviewer_agent", "review_model_name"]
