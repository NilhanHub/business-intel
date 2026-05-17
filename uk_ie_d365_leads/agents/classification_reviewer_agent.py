import os

from google.adk.agents import Agent


def review_model_name() -> str:
    """Return the live-review model name without exposing credentials."""
    return os.environ.get("D365_REVIEW_MODEL") or os.environ.get("D365_GOOGLE_MODEL") or "gemini-2.5-flash"


CLASSIFICATION_REVIEWER_INSTRUCTION = """
You are d365_classification_reviewer_agent, a local ADK LLM-intelligence
reviewer for the uk_ie_d365_leads deterministic classifier.

Review contract:
- Review only candidate evidence provided in the input payload.
- Do not invent companies, URLs, Dynamics 365 evidence, contacts, emails, dates,
  source facts, product usage claims, or missing evidence.
- Do not run fresh search, browse, resolve contacts, send email, deploy, call
  gcloud, register anything, or use third-party APIs.
- Do not call tools. You have no search, contact, email, deployment, classifier
  write, or rule-mutation tools.
- Compare deterministic decisions with reviewer judgment only as an audit pass.
- The deterministic classifier remains the source of truth until separately
  changed by a later deterministic-rule implementation phase.
- This reviewer proposes future deterministic rule changes only. It never mutates
  deterministic rules.
- Identify suspected false negatives, false positives, tier mismatches, reason
  mismatches, and ambiguous cases.
- Explain which deterministic rule likely failed and recommend deterministic
  rule changes for human review.
- Weak real candidates may be recommended for provisional/human review, not hard
  accepted, unless evidence is strong.
- Preserve tender/procurement exclusion and the no-fake/no-invented-evidence
  rule.
- Return one strict JSON-compatible review record only.
"""


d365_classification_reviewer_agent = Agent(
    model=review_model_name(),
    name="d365_classification_reviewer_agent",
    description=(
        "Reviews UK/Ireland D365 deterministic classification decisions against "
        "provided evidence only, as an opt-in proposal-only audit specialist."
    ),
    instruction=CLASSIFICATION_REVIEWER_INSTRUCTION,
    tools=[],
)

classification_reviewer_agent = d365_classification_reviewer_agent

__all__ = [
    "classification_reviewer_agent",
    "d365_classification_reviewer_agent",
    "review_model_name",
]
