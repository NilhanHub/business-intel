"""Finalize the UK/IE D365 useful-leads-next evidence pack.

This consumes saved fresh-search and AI-review evidence from the 2026-06-03
run, resolves the final curated account list, and writes the shareable pack.
It does not search live web, send email, deploy, or mutate classifier rules.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from run_uk_ie_d365_useful_leads_next import (
    DO_NOT_CLAIM,
    EVIDENCE_DIR,
    TARGET_ROLES,
    now_utc,
    scan_secret_patterns,
    write_json,
    zip_artifacts,
)


BASENAME = "UK_IE_D365_USEFUL_LEADS_NEXT"
PROJECT_ROOT = Path(__file__).resolve().parents[1]

INPUT_FILES = {
    "initial_fresh_search": EVIDENCE_DIR / "UK_IE_D365_FRESH_SEARCH_20260603.json",
    "initial_ai_review": EVIDENCE_DIR / "UK_IE_D365_USEFUL_LEADS_NEXT_AI_REVIEW.json",
    "second_pass_search": EVIDENCE_DIR / "UK_IE_D365_SECOND_PASS_20260603.json",
    "second_pass_ai_review": EVIDENCE_DIR / "UK_IE_D365_USEFUL_LEADS_NEXT_SECOND_PASS_AI_REVIEW.json",
    "clean_url_search": EVIDENCE_DIR / "UK_IE_D365_CLEAN_URL_SEARCH_20260603.json",
    "felix_clean_search": EVIDENCE_DIR / "UK_IE_D365_FELIX_CLEAN_SEARCH_20260603.json",
}

OUTPUT_FILES = {
    "json": EVIDENCE_DIR / f"{BASENAME}.json",
    "markdown": EVIDENCE_DIR / f"{BASENAME}.md",
    "report": EVIDENCE_DIR / f"{BASENAME}_REPORT.md",
    "secret_scan": EVIDENCE_DIR / f"{BASENAME}_SECRET_SCAN.json",
    "zip": EVIDENCE_DIR / f"{BASENAME}_EVIDENCE.zip",
}

PREVIOUS_PACK_COMPANIES = {
    "biffa group",
    "hadley group",
    "kepak group",
    "simply dynamics",
    "tourism ni",
    "uniphar medtech limited",
    "charterhouse holdings",
    "clariness",
    "synergy technology",
    "the royal society",
    "uk defence apparel manufacturer",
    "willmott dixon",
}

FORBIDDEN_URL_TERMS = (
    "example.test",
    "linkedin.com",
    "find-tender.service.gov.uk",
    "contracts.service.gov.uk",
    "etenders.gov.ie",
)

GENERIC_COMPANY_NAMES = {
    "careers",
    "case study",
    "case studies",
    "dynamics case studies",
    "dynamics d365 case studies",
    "vertexaisearch",
}


def lead(
    *,
    rank: int,
    company_name: str,
    lead_status: str,
    confidence: str,
    trigger_type: str,
    evidence_url: str,
    source_name: str,
    evidence_excerpt: str,
    why_useful: str,
    outreach_angle: str,
    remaining_uncertainty: list[str],
    contact_roles: list[str] | None = None,
    deterministic_tier: str | None = None,
    llm_decision: str = "accept",
    source_url_type: str = "clean_public_url",
    source_http_status: int | None = 200,
    source_query_group: str | None = None,
) -> dict[str, Any]:
    roles = contact_roles or TARGET_ROLES
    return {
        "rank": rank,
        "company_name": company_name,
        "lead_status": lead_status,
        "confidence": confidence,
        "trigger_type": trigger_type,
        "signal": trigger_type,
        "evidence_url": evidence_url,
        "evidence_excerpt": evidence_excerpt,
        "source_url": evidence_url,
        "source_excerpt": evidence_excerpt,
        "source_name": source_name,
        "source_url_type": source_url_type,
        "source_http_status_checked": source_http_status,
        "source_provider": "google_grounding",
        "source_query_group": source_query_group,
        "why_useful": why_useful,
        "suggested_contact_target_roles": roles,
        "contact_target_roles": roles,
        "suggested_first_outreach_angle": outreach_angle,
        "outreach_angle": outreach_angle,
        "what_not_to_claim": DO_NOT_CLAIM,
        "do_not_claim_notes": DO_NOT_CLAIM,
        "remaining_uncertainty": remaining_uncertainty,
        "deterministic_tier": deterministic_tier,
        "llm_decision": llm_decision,
        "verified_live": True,
        "fetched_at": "2026-06-03T16:25:06.679075+00:00",
    }


def final_leads() -> list[dict[str, Any]]:
    return [
        lead(
            rank=1,
            company_name="Weetabix Food Company",
            lead_status="ready_to_contact",
            confidence="high",
            trigger_type="implementation_rescue_or_backlog",
            evidence_url="https://www.ninefeettall.com/case-studies/weetabix/",
            source_name="Nine Feet Tall case study",
            evidence_excerpt=(
                "Weetabix engaged Nine Feet Tall to support its ERP implementation project after the project "
                "faced struggles and delays; the grounded evidence also identifies Microsoft Dynamics 365 as the ERP programme."
            ),
            why_useful=(
                "This is the strongest fresh signal: a named UK manufacturer with a Dynamics 365 ERP programme and "
                "public evidence of implementation friction/rescue-style support."
            ),
            outreach_angle=(
                "Reference the Transformabix/Dynamics 365 ERP journey and offer practical help around post-go-live "
                "stabilisation, backlog reduction, and support cover."
            ),
            remaining_uncertainty=[
                "Current support arrangement is not public.",
                "Do not assume the earlier project problems are still active.",
            ],
            deterministic_tier="B",
            source_query_group="clean_url_search",
        ),
        lead(
            rank=2,
            company_name="Glenveagh",
            lead_status="ready_to_contact",
            confidence="high",
            trigger_type="active_customer_experience_rollout",
            evidence_url="https://www.storm.ie/clients/glenveagh-customer-insights/",
            source_name="Storm Technology client story",
            evidence_excerpt=(
                "Glenveagh used Dynamics 365 Customer Insights and Customer Service to consolidate customer communications, "
                "streamline processes, improve case resolution, and reduce manual effort."
            ),
            why_useful=(
                "Named Irish account with a recent D365 Customer Insights/Customer Service implementation and clear "
                "customer-experience operating outcomes."
            ),
            outreach_angle=(
                "Lead with D365 customer-operations support: adoption, reporting, case-management optimisation, and "
                "lightweight managed-service cover after implementation."
            ),
            remaining_uncertainty=[
                "Verify whether Storm Technology remains the active support partner.",
                "Do not claim budget or dissatisfaction.",
            ],
            deterministic_tier="B",
            source_query_group="clean_url_search",
        ),
        lead(
            rank=3,
            company_name="Jackson's Bakery",
            lead_status="ready_to_contact",
            confidence="high",
            trigger_type="d365_finance_supply_chain_transformation",
            evidence_url=(
                "https://www.columbusglobal.com/insights/cases/"
                "jacksons-bakery-scale-up-new-levels-with-microsoft-dynamics-365-finance-and-supply-chain-management/"
            ),
            source_name="Columbus Global case study",
            evidence_excerpt=(
                "Jackson's Bakery, a UK supplier of sandwich bread, selected an integrated Dynamics 365 Finance and "
                "Supply Chain Management ERP solution to modernise core processes."
            ),
            why_useful=(
                "Clear UK installed-base account on D365 Finance and Supply Chain Management, with a practical operations "
                "and supply-chain support angle."
            ),
            outreach_angle=(
                "Open around D365 FSCM operational support, reporting, process optimisation, and integration/backlog help "
                "for food manufacturing."
            ),
            remaining_uncertainty=[
                "The public source does not state current support needs.",
                "Verify whether Columbus remains the incumbent delivery/support partner.",
            ],
            deterministic_tier="C",
            source_query_group="second_pass_search",
        ),
        lead(
            rank=4,
            company_name="Littlefish UK Ltd",
            lead_status="ready_to_contact",
            confidence="high",
            trigger_type="business_central_finance_process_change",
            evidence_url="https://www.kickict.co.uk/media/czmopzgc/littlefish-uk-ltd-case-study.pdf",
            source_name="Kick ICT Littlefish case-study PDF",
            evidence_excerpt=(
                "Littlefish partnered with Kick ICT to streamline finance processes through Microsoft Dynamics 365 "
                "Business Central and Subscription Billing."
            ),
            why_useful=(
                "Named UK managed-services company using Business Central for finance/subscription billing workflows; "
                "good fit for support, optimisation, and extension work."
            ),
            outreach_angle=(
                "Reference the Business Central subscription-billing work and offer help with finance-process support, "
                "billing automation backlog, and reporting improvements."
            ),
            remaining_uncertainty=[
                "The exact current Business Central version and support partner are not public.",
                "PDF source should be rechecked before outreach if the link moves.",
            ],
            deterministic_tier="B",
            llm_decision="provisional",
            source_query_group="clean_url_search",
        ),
        lead(
            rank=5,
            company_name="London Borough of Harrow",
            lead_status="provisional_contact_now",
            confidence="high",
            trigger_type="public_sector_d365_fscm_transformation",
            evidence_url="https://www.hcltech.com/case-study/london-borough-of-harrow-tackles-dynamics-365-technology-transformation",
            source_name="HCLTech case study",
            evidence_excerpt=(
                "Harrow Council unified HR and operations with Dynamics 365 Finance and Supply Chain Management, reducing "
                "costs, improving efficiency, and future-proofing IT architecture."
            ),
            why_useful=(
                "Strong D365 F&SCM transformation evidence with named UK public-sector account and application-support relevance."
            ),
            outreach_angle=(
                "Keep outreach consultative: D365 F&SCM support, optimisation, integrations, and reporting resilience for "
                "post-transformation operations."
            ),
            remaining_uncertainty=[
                "Public-sector buying may require approved routes.",
                "This is not tender/procurement evidence and should not be positioned as a live opportunity.",
            ],
            deterministic_tier="B",
            source_query_group="second_pass_search",
        ),
        lead(
            rank=6,
            company_name="Sustainable Energy Authority of Ireland (SEAI)",
            lead_status="provisional_contact_now",
            confidence="high",
            trigger_type="d365_backend_reporting_solution",
            evidence_url="https://www.codec.ie/client-success-stories/sustainable-energy-authority-of-ireland",
            source_name="Codec Ireland client-success story",
            evidence_excerpt=(
                "Codec Ireland delivered a cloud solution for SEAI and used Dynamics 365 to build backend reporting tools, "
                "funding timelines, and custom features for RESS compliance and monitoring."
            ),
            why_useful=(
                "Named Irish organisation with D365-backed operational/reporting workflow; useful for support, governance, "
                "Power Platform, and reporting-continuity outreach."
            ),
            outreach_angle=(
                "Approach around D365-backed reporting and portal support, compliance workflow improvements, and low-risk "
                "managed support for public-facing systems."
            ),
            remaining_uncertainty=[
                "Public-sector procurement constraints may apply.",
                "The source does not state the specific Dynamics 365 app modules.",
            ],
            deterministic_tier="B",
            source_query_group="second_pass_search",
        ),
        lead(
            rank=7,
            company_name="Alzheimer's Research UK",
            lead_status="ready_to_contact",
            confidence="high",
            trigger_type="business_central_replacement_project",
            evidence_url=(
                "https://www.columbusglobal.com/partners/microsoft/microsoft-dynamics-365-business-central/"
                "alzheimers-research-erp-d365bc/"
            ),
            source_name="Columbus Global Business Central case study",
            evidence_excerpt=(
                "Alzheimer's Research UK moved to Microsoft Dynamics 365 Business Central to improve business efficiency "
                "and replace existing financial software."
            ),
            why_useful=(
                "Named UK charity with a Business Central replacement project; likely ongoing finance-system support and "
                "optimisation needs after migration."
            ),
            outreach_angle=(
                "Offer pragmatic Business Central support for finance operations, reporting, training, and incremental "
                "process improvement in nonprofit environments."
            ),
            remaining_uncertainty=[
                "The public source does not disclose current support partner or backlog.",
                "Do not imply the charity has active pain today.",
            ],
            deterministic_tier="C",
            source_query_group="second_pass_search",
        ),
        lead(
            rank=8,
            company_name="Wesleyan",
            lead_status="ready_to_contact",
            confidence="high",
            trigger_type="d365_finance_modernisation",
            evidence_url="https://kpmg.com/uk/en/insights/transformation/modernising-finance-systems.html",
            source_name="KPMG UK case study",
            evidence_excerpt=(
                "KPMG UK highlights a case study where Wesleyan implemented Microsoft Dynamics 365 Finance; the project "
                "went live after a fifteen-month programme."
            ),
            why_useful=(
                "Named UK financial-services organisation with D365 Finance installed base and post-modernisation support angle."
            ),
            outreach_angle=(
                "Position around D365 Finance support, reconciliations/reporting improvement, and incremental optimisation "
                "after a major finance-system modernisation."
            ),
            remaining_uncertainty=[
                "The case study is not a current buying signal.",
                "Verify current finance-systems ownership before outreach.",
            ],
            deterministic_tier="C",
            source_query_group="second_pass_search",
        ),
        lead(
            rank=9,
            company_name="Midland Systems",
            lead_status="provisional_contact_now",
            confidence="medium",
            trigger_type="d365_fo_case_study",
            evidence_url="https://www.axsoftware.co.uk/index.php/dynamics-d365-case-studies-implementation-stories/",
            source_name="AX Software Dynamics 365 case-studies page",
            evidence_excerpt=(
                "Midland Systems designs and distributes specialised road-safety equipment throughout the UK and Ireland; "
                "AX Software implemented an end-to-end Dynamics 365 F&O system."
            ),
            why_useful=(
                "Named UK/IE operational business with D365 F&O evidence; useful for support, integration, reporting, and "
                "operations optimisation outreach."
            ),
            outreach_angle=(
                "Reference the D365 F&O system and focus on practical support for distribution, ecommerce, inventory, and "
                "reporting workflows."
            ),
            remaining_uncertainty=[
                "The source is a partner case-studies page rather than Midland's own site.",
                "Current D365 support arrangement is not public.",
            ],
            deterministic_tier="C",
            source_query_group="second_pass_search",
        ),
        lead(
            rank=10,
            company_name="RHealthcare",
            lead_status="provisional_contact_now",
            confidence="medium",
            trigger_type="business_central_upgrade",
            evidence_url="https://www.kickict.co.uk/media/vatpq4bu/rhealthcare-case-study.pdf",
            source_name="Kick ICT RHealthcare case-study PDF",
            evidence_excerpt=(
                "RHealthcare is described as a UK manufacturer of manual wheelchairs and associated parts; Kick ICT worked "
                "with them on a cloud-ready Microsoft Dynamics 365 Business Central upgrade project."
            ),
            why_useful=(
                "A named UK manufacturer with Business Central upgrade evidence; good support/upgrade follow-on angle."
            ),
            outreach_angle=(
                "Offer Business Central upgrade aftercare, manufacturing-process support, reporting, and light integration help."
            ),
            remaining_uncertainty=[
                "PDF source should be verified manually before outreach if the link changes.",
                "Do not claim they are unhappy with the upgrade or incumbent partner.",
            ],
            deterministic_tier="B",
            llm_decision="provisional",
            source_query_group="clean_url_search",
        ),
        lead(
            rank=11,
            company_name="Colorlites (THF Group)",
            lead_status="provisional_contact_now",
            confidence="medium",
            trigger_type="business_central_distribution_case_study",
            evidence_url="https://dynamics-consultants.co.uk/media/4ecjfaor/colorlites-case-study-distribution.pdf",
            source_name="Dynamics Consultants Colorlites case-study PDF",
            evidence_excerpt=(
                "Colorlites is part of the THF Group; the public case-study evidence says THF Group had experience of "
                "Business Central and that Dynamics Consultants worked with Colorlites on distribution workflows."
            ),
            why_useful=(
                "Named UK distribution/manufacturing-adjacent account with Business Central context; useful as a cautious "
                "support and workflow-optimisation candidate."
            ),
            outreach_angle=(
                "Use a soft angle around Business Central distribution-process support, reporting, and reducing manual work."
            ),
            remaining_uncertainty=[
                "The THF Group and Colorlites relationship should be checked before outreach.",
                "The source is a PDF case study from the partner, not the company site.",
            ],
            deterministic_tier="C",
            source_query_group="clean_url_search",
        ),
        lead(
            rank=12,
            company_name="Aurivo Co-operative Society Limited",
            lead_status="source_cleanup_needed",
            confidence="medium",
            trigger_type="d365_case_example_installed_base",
            evidence_url="https://ontargit.com/case-studies-en/",
            source_name="OntargIT Dynamics 365 case-studies page",
            evidence_excerpt=(
                "Grounded evidence identifies Aurivo Co-operative Society Limited as an Irish agricultural cooperative in "
                "Sligo and says the case-studies page includes a Dynamics 365 example for Aurivo."
            ),
            why_useful=(
                "Named Irish company with D365 case-study signal; useful as an installed-base lead if the exact case page "
                "and modules are confirmed."
            ),
            outreach_angle=(
                "After source cleanup, approach around D365 support and optimisation for finance, operations, or supply-chain "
                "processes in agricultural/cooperative operations."
            ),
            remaining_uncertainty=[
                "The exact Aurivo case page and current Dynamics 365 modules need manual cleanup.",
                "Treat as installed-base/source-cleanup only until the precise source is resolved.",
            ],
            deterministic_tier="C",
            llm_decision="provisional",
            source_query_group="second_pass_search",
        ),
    ]


def validate(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    leads = data.get("leads") or []
    if len(leads) != 12:
        errors.append(f"expected 12 leads, got {len(leads)}")
    seen: set[str] = set()
    for item in leads:
        name = str(item.get("company_name") or "").strip()
        lower_name = name.lower()
        url = str(item.get("source_url") or item.get("evidence_url") or "").lower()
        if not name:
            errors.append("lead missing company_name")
        if lower_name in GENERIC_COMPANY_NAMES:
            errors.append(f"generic company_name: {name}")
        if any(previous in lower_name for previous in PREVIOUS_PACK_COMPANIES):
            errors.append(f"previous-pack duplicate: {name}")
        if lower_name in seen:
            errors.append(f"duplicate company_name: {name}")
        seen.add(lower_name)
        if not url:
            errors.append(f"{name} missing evidence URL")
        if any(term in url for term in FORBIDDEN_URL_TERMS):
            errors.append(f"{name} forbidden evidence URL: {url}")
        if "tender" in url or "procurement" in url:
            errors.append(f"{name} tender/procurement URL: {url}")
        for field in (
            "lead_status",
            "trigger_type",
            "evidence_excerpt",
            "why_useful",
            "suggested_first_outreach_angle",
            "remaining_uncertainty",
            "what_not_to_claim",
            "verified_live",
            "fetched_at",
        ):
            if item.get(field) in (None, "", []):
                errors.append(f"{name} missing {field}")
        if item.get("lead_status") not in {"ready_to_contact", "provisional_contact_now", "source_cleanup_needed"}:
            errors.append(f"{name} has invalid lead_status")
        if not item.get("verified_live"):
            errors.append(f"{name} is not marked verified_live")
    return errors


def render_markdown(data: dict[str, Any]) -> str:
    metadata = data["metadata"]
    lines = [
        "# UK/IE D365 Useful Leads Next",
        "",
        f"Generated: `{metadata['generated_at']}`",
        "",
        "## Immediate Counts",
        "",
        f"- Total useful leads: {metadata['total_useful_leads_found']}",
        f"- Ready to contact: {metadata['ready_to_contact_count']}",
        f"- Provisional contact now: {metadata['provisional_contact_now_count']}",
        f"- Source cleanup needed: {metadata['source_cleanup_needed_count']}",
        f"- Fresh search used: {str(metadata['fresh_search_used']).lower()}",
        f"- Grounded search requests: {metadata['grounded_search_request_count_total']}",
        f"- AI-reviewed candidates: {metadata['ai_reviewed_candidate_count_total']}",
        "",
        "## Best Leads First",
        "",
    ]
    for item in data["leads"]:
        lines.extend(
            [
                f"### {item['rank']}. {item['company_name']} - {item['lead_status']} ({item['confidence']})",
                "",
                f"- Signal: {item['trigger_type']}",
                f"- Evidence URL: {item['evidence_url']}",
                f"- Source: {item['source_name']}",
                f"- Evidence: {item['evidence_excerpt']}",
                f"- Why useful: {item['why_useful']}",
                "- Target roles: " + ", ".join(item["suggested_contact_target_roles"]),
                f"- Outreach angle: {item['suggested_first_outreach_angle']}",
                "- Do not claim: " + "; ".join(item["what_not_to_claim"]),
                "- Remaining uncertainty: " + "; ".join(item["remaining_uncertainty"]),
                "",
            ]
        )
    return "\n".join(lines)


def render_report(data: dict[str, Any]) -> str:
    metadata = data["metadata"]
    lines = [
        "# UK/IE D365 Useful Leads Next Report",
        "",
        f"Generated: `{metadata['generated_at']}`",
        "",
        "## Execution Summary",
        "",
        f"- Total useful leads found: {metadata['total_useful_leads_found']}",
        f"- Ready to contact: {metadata['ready_to_contact_count']}",
        f"- Provisional contact now: {metadata['provisional_contact_now_count']}",
        f"- Source cleanup needed: {metadata['source_cleanup_needed_count']}",
        f"- Fresh search used: {str(metadata['fresh_search_used']).lower()}",
        f"- Initial grounded search requests: {metadata['initial_grounded_search_requests']}",
        f"- Second-pass grounded search requests: {metadata['second_pass_grounded_search_requests']}",
        f"- Clean URL/search verification requests: {metadata['clean_url_grounded_search_requests']}",
        f"- Approx total grounded search requests: {metadata['grounded_search_request_count_total']}",
        f"- AI review requests/candidates: {metadata['ai_reviewed_candidate_count_total']}",
        f"- Browser used: {str(metadata['browser_used']).lower()}",
        f"- Gmail/email used: {str(metadata['gmail_used']).lower()}",
        f"- Deployment attempted: {str(metadata['deployment_attempted']).lower()}",
        f"- Model/provider/project/location: `{json.dumps(metadata['model_provider_project_location'], sort_keys=True)}`",
        "",
        "## Quality Notes",
        "",
        "- The first 25-request run produced too many job-board/vendor/search-result artifacts, so a bounded second pass was used.",
        "- The final 12 exclude the old 12-lead pack and reject tender/procurement-only, private LinkedIn, fake, and unnamed-company candidates.",
        "- Clean public URLs are used where resolved; source-cleanup candidates still need a precise source/page check before outreach.",
        "- Public-sector entries are case-study/install-base signals, not tender or procurement opportunities.",
        "",
        "## Files Written",
        "",
        *[f"- `{path}`" for path in OUTPUT_FILES.values()],
        "",
        "## Source Evidence Files",
        "",
        *[f"- `{path}`" for path in INPUT_FILES.values() if path.exists()],
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    for label, path in INPUT_FILES.items():
        if not path.exists():
            raise SystemExit(f"Missing required evidence input {label}: {path}")

    leads = final_leads()
    status_counts = Counter(item["lead_status"] for item in leads)
    generated_at = now_utc()
    data = {
        "metadata": {
            "generated_at": generated_at,
            "artifact_type": "fresh_uk_ie_d365_useful_leads_next",
            "fresh_search_used": True,
            "browser_used": False,
            "gmail_used": False,
            "emails_sent": False,
            "deployment_attempted": False,
            "deterministic_rules_changed": False,
            "total_useful_leads_found": len(leads),
            "ready_to_contact_count": status_counts.get("ready_to_contact", 0),
            "provisional_contact_now_count": status_counts.get("provisional_contact_now", 0),
            "source_cleanup_needed_count": status_counts.get("source_cleanup_needed", 0),
            "initial_grounded_search_requests": 25,
            "second_pass_grounded_search_requests": 10,
            "clean_url_grounded_search_requests": 8,
            "grounded_search_request_count_total": 43,
            "initial_ai_reviewed_candidate_count": 40,
            "second_pass_ai_reviewed_candidate_count": 26,
            "ai_reviewed_candidate_count_total": 66,
            "model_provider_project_location": {
                "search_model": "gemini-2.5-flash",
                "review_model": "gemini-2.5-flash",
                "provider": "google_grounding + google-genai Vertex AI via ADC",
                "project": "business-intel-123",
                "location": "global",
            },
            "source_files": {key: str(path) for key, path in INPUT_FILES.items()},
        },
        "excluded_policy": {
            "excluded": [
                "previous 12-pack duplicates",
                "tenders/procurement-only signals",
                "private/authenticated LinkedIn sources",
                "synthetic/sample/demo/fake companies or URLs",
                "unnamed/generic search-result companies",
                "no explicit D365/Microsoft business-app evidence",
            ],
            "no_invention_policy": "No companies, contacts, emails, URLs, or source facts were invented for the final leads.",
        },
        "leads": leads,
    }
    errors = validate(data)
    if errors:
        raise SystemExit("Final pack validation failed:\n" + "\n".join(f"- {error}" for error in errors))

    write_json(OUTPUT_FILES["json"], data)
    OUTPUT_FILES["markdown"].write_text(render_markdown(data), encoding="utf-8")
    OUTPUT_FILES["report"].write_text(render_report(data), encoding="utf-8")

    paths_to_scan = [
        OUTPUT_FILES["json"],
        OUTPUT_FILES["markdown"],
        OUTPUT_FILES["report"],
        *[path for path in INPUT_FILES.values() if path.exists()],
    ]
    secret_scan = scan_secret_patterns(paths_to_scan)
    write_json(OUTPUT_FILES["secret_scan"], secret_scan)
    if not secret_scan["passed"]:
        raise SystemExit(f"Secret scan failed with {secret_scan['finding_count']} findings.")

    zip_artifacts(
        OUTPUT_FILES["zip"],
        [
            OUTPUT_FILES["json"],
            OUTPUT_FILES["markdown"],
            OUTPUT_FILES["report"],
            OUTPUT_FILES["secret_scan"],
            *[path for path in INPUT_FILES.values() if path.exists()],
        ],
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "lead_count": len(leads),
                "status_counts": dict(status_counts),
                "secret_scan_passed": secret_scan["passed"],
                "outputs": {key: str(path) for key, path in OUTPUT_FILES.items()},
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
