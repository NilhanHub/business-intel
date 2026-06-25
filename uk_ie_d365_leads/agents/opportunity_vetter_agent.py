import os

from google.adk.agents import Agent


def vetter_model_name() -> str:
    """Return the production opportunity-vetting model name without exposing credentials."""
    return os.environ.get("D365_VETTER_MODEL") or os.environ.get("D365_REVIEW_MODEL") or os.environ.get("D365_GOOGLE_MODEL") or "gemini-2.5-flash"


OPPORTUNITY_VETTER_INSTRUCTION = """
You are d365_opportunity_vetter_agent, the production AI vetter for the
uk_ie_d365_leads local evidence workflow.

Vetting contract:
- Judge whether a candidate is a credible 1BT UK/Ireland Dynamics 365 sales
  opportunity using only the evidence supplied in the input payload.
- The deterministic layer is only a guardrail layer. Treat deterministic flags
  as uncertainty to reason over, not automatic rejection.
- Preserve hard safety exclusions: no fake/sample/demo evidence, no private or
  authenticated LinkedIn evidence, no tender/procurement-only leads, no email
  sending, no deployment, and no invented companies, URLs, contacts, dates,
  product usage, or source claims.
- Use follow-up evidence supplied by the runner when present. Do not browse or
  call tools yourself.
- If the candidate is useful but the evidence is thin or the clean source is not
  resolved, mark it source_cleanup_needed rather than overclaiming.
- Return one strict JSON-compatible vetting record only.

Required output fields:
lead_status, signal_strength, signal_type, evidence_used, evidence_gaps,
opportunity_signal, why_this_matters_to_1bt, commercial_opening,
value_of_signal, intelligence_reading, board_relevance, contact_target_roles,
do_not_claim_notes, remaining_uncertainty, final_rejection_reason.
"""


d365_opportunity_vetter_agent = Agent(
    model=vetter_model_name(),
    name="d365_opportunity_vetter_agent",
    description=(
        "Vets UK/Ireland D365 candidates into 1BT opportunity write-ups using "
        "provided public evidence and runner-supplied follow-up context."
    ),
    instruction=OPPORTUNITY_VETTER_INSTRUCTION,
    tools=[],
)

opportunity_vetter_agent = d365_opportunity_vetter_agent

__all__ = [
    "d365_opportunity_vetter_agent",
    "opportunity_vetter_agent",
    "vetter_model_name",
]
