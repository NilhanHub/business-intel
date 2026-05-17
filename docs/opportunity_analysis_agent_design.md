# Opportunity Analysis Agent Design

Project: Business_Intel / sl_trigger_leads  
Prompt: PROMPT#06

## Purpose

Add a separate `opportunity_analyst` ADK sub-agent that studies verified live leads and maps each lead to the best 1BT service bucket and outreach response strategy.

The live-source finder remains responsible only for fetching, extracting, scoring, and guarding verified live leads. The opportunity analyst is responsible for service-bucket interpretation.

## Architecture

- `sl_trigger_leads/agent.py`
  - Root agent.
  - Keeps live lead finding tools.
  - Adds light routing instructions for opportunity-analysis requests.
  - Registers `opportunity_analyst` as a sub-agent.

- `sl_trigger_leads/agents/opportunity_analyst.py`
  - Separate ADK sub-agent.
  - Uses local taxonomy and deterministic opportunity-analysis tools.

- `sl_trigger_leads/tools/opportunity_analysis_tools.py`
  - Deterministic-first classification and outreach strategy tools.
  - Reuses `assert_no_simulation_data`.

- `sl_trigger_leads/data/onebt_service_taxonomy.json`
  - Local 1BT service taxonomy.
  - Prevents runtime dependency on the 1BT website.

## Classification Method

Classification is deterministic-first:

1. Validate live evidence fields.
2. Combine company, trigger summary, evidence excerpt, source name, source type, trigger type, sector, and existing 1BT fit.
3. Score taxonomy buckets using keyword and phrase rules.
4. Add trigger-type bonuses.
5. Add job-board delivery-capacity bonus when source evidence comes from public jobs pages.
6. Select primary bucket and secondary buckets.
7. Mark confidence as high, medium, or low based on score strength and margin.

Gemini may summarize the results in ADK Web, but bucket choice is reproducible from local rules.

## Output Schema

Each analysis includes:

- `company`
- `evidence_url`
- `trigger_type`
- `trigger_summary`
- `primary_bucket`
- `secondary_buckets`
- `bucket_confidence`
- `reasoning`
- `evidence_excerpt`
- `recommended_1bt_offer`
- `recommended_outreach_theme`
- `email_positioning`
- `who_to_contact`
- `what_to_verify_next`
- `do_not_claim`
- `verdict`

## Guardrails

- Do not analyze sample, synthetic, fake, or `example.test` records.
- Do not invent evidence, budget, contacts, or technology stack.
- If evidence is weak, say weak.
- If the bucket is uncertain, mark confidence low or medium.
- Do not claim Dynamics 365, AI, outsourcing intent, staffing shortage, or budget unless evidence supports it.
- Do not send email or create Gmail drafts.
- Do not deploy.

## VS One World Expected Behavior

The verified ITPro.lk lead:

`https://itpro.lk/job/13609/qe-engineer-api-integration-at-vs-one-world-pvt-ltd/`

maps to:

- Primary: `staff_augmentation_delivery_capacity`
- Secondary: `integrations_api_middleware`, `qa_test_automation`, `custom_software_development`

Reason: the live evidence is a QE Engineer role focused on API and integration, indicating delivery-capacity pressure around QA/API/integration work. This is better positioned as staff augmentation and delivery capacity than as a generic software pitch.
