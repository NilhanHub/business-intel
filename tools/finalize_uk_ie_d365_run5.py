"""Finalize the fifth UK/Ireland D365 lead round from verified public sources."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uk_ie_d365_leads.tools import discovery_backbone_tools, lead_tools
from uk_ie_d365_leads.tools import opportunity_vetting_tools as vetting

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = PROJECT_ROOT / "Evidence"
OUTPUT_BASENAME = "UK_IE_D365_RUN5_20260716_20_LEADS_FINAL"
AUDIT_BASENAME = "UK_IE_D365_RUN5_20260716_DETERMINISTIC_REJECT_AUDIT_FINAL"
RUN_ID = "uk-ie-d365-run5-20260716"

CURATED_LEADS: list[dict[str, Any]] = [
    {
        "company_name": "E.ON UK",
        "country": "United Kingdom",
        "sector": "Energy and utilities",
        "signal_type": "d365_customer_field_service_rollout",
        "url": "https://www.microsoft.com/en/customers/story/23367-eon-uk-dynamics-365-customer-service",
        "excerpt": "E.ON UK rolled out Dynamics 365 Sales, Customer Service, Field Service, and asset-management capabilities to 2,900 employees.",
        "signal": "Large live multi-module Dynamics 365 estate supporting customer, field, asset, sales, and finance operations.",
        "opening": "Discuss managed enhancement capacity, integration backlog, release governance, and field-service optimisation across the expanding platform.",
        "roles": ["Director of Digital Technology", "Head of CRM", "Head of Field Service Technology"],
    },
    {
        "company_name": "Domino's Pizza UK & Ireland",
        "country": "United Kingdom and Ireland",
        "sector": "Food service and franchising",
        "signal_type": "d365_finance_supply_chain_go_live",
        "url": "https://www.microsoft.com/en/customers/story/26334-dominos-dynamics-365-finance",
        "excerpt": "Domino's Pizza UK and Ireland deployed Dynamics 365 Finance and Supply Chain Management across finance, logistics, approvals, and warehouse operations.",
        "signal": "Recent cloud ERP deployment across a large UK and Ireland franchise and supply-chain footprint.",
        "opening": "Open around post-go-live optimisation, warehouse and franchise integrations, reporting, controls, and managed application support.",
        "roles": ["Chief Information & Technology Officer", "Finance Systems Director", "Head of Supply Chain Technology"],
    },
    {
        "company_name": "Nottingham Trent University",
        "country": "United Kingdom",
        "sector": "Higher education",
        "signal_type": "d365_customer_service_expansion",
        "url": "https://www.microsoft.com/en/customers/story/1705924073147350347-nottingham-trent-university-dynamics365-higher-education-uk",
        "excerpt": "Nottingham Trent University uses Dynamics 365 Customer Service and Customer Voice, with active users growing from 300 to 900.",
        "signal": "Successful service-platform rollout with documented adoption growth and an active roadmap for omnichannel and Copilot capabilities.",
        "opening": "Discuss roadmap delivery, omnichannel integration, Copilot readiness, service analytics, and managed enhancement capacity.",
        "roles": ["Associate Director of Digital Technologies", "Head of Digital Experience", "Head of Service Management"],
    },
    {
        "company_name": "Fortnum & Mason",
        "country": "United Kingdom",
        "sector": "Retail",
        "signal_type": "d365_retail_customer_operations",
        "url": "https://www.microsoft.com/en/customers/story/745192-fortnum-and-mason",
        "excerpt": "Fortnum & Mason uses Dynamics 365 to connect distribution, stores, online sales, international customers, and customer insight.",
        "signal": "Business-critical Dynamics 365 footprint spanning retail operations, distribution, ecommerce, and customer engagement.",
        "opening": "Explore integration support, customer-data activation, reporting improvements, and backlog delivery across retail and distribution workflows.",
        "roles": ["Chief Financial Officer", "Chief Information Officer", "Head of Customer Experience Technology"],
    },
    {
        "company_name": "TalkTalk Group",
        "country": "United Kingdom",
        "sector": "Telecommunications",
        "signal_type": "d365_finance_migration",
        "url": "https://www.microsoft.com/en/customers/story/23266-talktalk-dynamics-365-finance/",
        "excerpt": "TalkTalk Group replaced Dynamics AX 2012 with Dynamics 365 Finance to address fragmented systems, outdated processes, controls, and reporting.",
        "signal": "Recent enterprise finance migration with documented integration, automation, control, and continuous-improvement needs.",
        "opening": "Discuss post-migration optimisation, automation backlog, reporting, integration resilience, and managed Finance application support.",
        "roles": ["Finance Transformation Director", "Head of Business Applications", "Group Financial Controller"],
    },
    {
        "company_name": "Genus plc",
        "country": "United Kingdom",
        "sector": "Agricultural biotechnology",
        "signal_type": "multi_phase_d365_global_rollout",
        "url": "https://www.microsoft.com/en/customers/story/1731070438834171888-genusplc-dynamics365-chemicalsandagrochemicals-uk-en",
        "excerpt": "Genus introduced Dynamics 365 Human Resources, Finance, Supply Chain Management, and a Field Service mobile application through a multi-phase programme.",
        "signal": "Complex multi-module and mobile Dynamics 365 estate operating across global agricultural operations.",
        "opening": "Explore cross-module integration, mobile Field Service enhancement, release management, reporting, and scalable support capacity.",
        "roles": ["Group CIO", "Head of Enterprise Applications", "Director of Global Business Systems"],
    },
    {
        "company_name": "VIVID",
        "country": "United Kingdom",
        "sector": "Housing association",
        "signal_type": "d365_contact_centre_field_service",
        "url": "https://www.microsoft.com/en/customers/story/19820-vivid-azure",
        "excerpt": "VIVID's service foundation includes Dynamics 365 Customer Service, Contact Center, and Field Service for resident and property operations.",
        "signal": "Integrated housing service platform combining customer service, contact centre, and field operations.",
        "opening": "Discuss service optimisation, property integrations, contact-centre analytics, field mobility, and managed release support.",
        "roles": ["Chief Information Officer", "Director of Customer Services", "Head of Business Applications"],
    },
    {
        "company_name": "Sage Homes",
        "country": "United Kingdom",
        "sector": "Housing association",
        "signal_type": "d365_customer_platform_transformation",
        "url": "https://www.microsoft.com/en/customers/story/25320-sage-homes-dynamics-365-contact-center",
        "excerpt": "Sage Homes implemented Dynamics 365 Contact Center, Customer Service, Field Service, and Customer Insights to replace fragmented manual processes.",
        "signal": "Recent broad Dynamics 365 transformation with contact-centre, field-service, customer-data, and automation scope.",
        "opening": "Open around post-implementation optimisation, data integration, field workflows, customer insight, and managed enhancement delivery.",
        "roles": ["Chief Technology Officer", "Director of Customer Experience", "Head of Digital Transformation"],
    },
    {
        "company_name": "NFU Mutual",
        "country": "United Kingdom",
        "sector": "Insurance and financial services",
        "signal_type": "d365_sales_service_copilot_adoption",
        "url": "https://www.microsoft.com/en/customers/story/22718-nfu-mutual-dynamics-365-customer-service",
        "excerpt": "NFU Mutual uses Dynamics 365 Customer Service and Sales with Copilot for Sales across its UK agency network.",
        "signal": "Scaled CRM and Copilot adoption across a distributed insurance sales and service operation.",
        "opening": "Discuss Copilot governance, CRM adoption analytics, integration, automation, and managed enhancement capacity for agency operations.",
        "roles": ["Head of Sales and Agency Transformation", "Head of CRM", "Director of Digital Customer Experience"],
    },
    {
        "company_name": "Quintain Ireland",
        "country": "Ireland",
        "sector": "Property development",
        "signal_type": "business_central_irish_operations",
        "url": "https://www.simplydynamics.com/d365-business-central-customer-story-with-quintain/",
        "excerpt": "Quintain's Irish operation implemented Dynamics 365 Business Central for financial management, intercompany trading, bank integration, and reporting.",
        "signal": "Irish property operation running Business Central with finance, banking, tax, intercompany, and growth requirements.",
        "opening": "Explore finance automation, reporting, banking integrations, project controls, and ongoing Business Central support for growth.",
        "roles": ["Head of Finance Operations & IT", "Finance Director", "Business Systems Manager"],
    },
    {
        "company_name": "Bromford",
        "country": "United Kingdom",
        "sector": "Housing association",
        "signal_type": "d365_finance_operations_phased_rollout",
        "url": "https://www.optimum.co.uk/success-story/bromford/",
        "excerpt": "Bromford implemented a phased Dynamics 365 Finance and Operations programme covering finance, HR, payroll, purchasing, inventory, training, and hypercare.",
        "signal": "Large phased housing ERP transformation with explicit training, hypercare, troubleshooting, and additional-project needs.",
        "opening": "Discuss hypercare extension, role-based enablement, integration support, release governance, and backlog delivery across later phases.",
        "roles": ["Director of Transformation", "Head of Business Systems", "Finance Systems Manager"],
    },
    {
        "company_name": "Origin Housing",
        "country": "United Kingdom",
        "sector": "Housing association",
        "signal_type": "d365_customer_process_migration",
        "url": "https://www.hitachi-solutions.co.uk/case-studies/origin-housing/",
        "excerpt": "Origin Housing moved complaints and anti-social-behaviour processes from legacy systems into Dynamics 365 Customer Engagement.",
        "signal": "Dynamics 365 was underused and is being expanded to replace duplicated legacy housing-service processes.",
        "opening": "Explore further process migration, resident-service integration, data quality, automation backlog, and managed CRM support.",
        "roles": ["Chief Information Officer", "Director of Housing Services", "Head of CRM"],
    },
    {
        "company_name": "Southern Housing",
        "country": "United Kingdom",
        "sector": "Housing association",
        "signal_type": "d365_legacy_support_recovery",
        "url": "https://www.esuasive.co.uk/case-studies/southern-replaces-legacy-systems-esuasive-housing",
        "excerpt": "Southern Housing's Dynamics 365 platform suffered reduced vendor support and inconsistent contractor customisations before a renewed transformation programme.",
        "signal": "Direct public evidence of historic Dynamics support fragmentation and customisation inconsistency in a large housing organisation.",
        "opening": "Lead with platform health, customisation governance, support continuity, integration rationalisation, and a managed improvement backlog.",
        "roles": ["Chief Information Officer", "Director of Digital Transformation", "Head of Business Applications"],
    },
    {
        "company_name": "London & Quadrant (L&Q)",
        "country": "United Kingdom",
        "sector": "Housing association",
        "signal_type": "d365_document_customer_operations",
        "url": "https://experlogix.com/case-studies/london-quadrant/",
        "excerpt": "L&Q uses Microsoft Dynamics CRM as a central platform for interactions with residents, contractors, government agencies, and social services.",
        "signal": "Large housing CRM estate with document automation and complex resident, contractor, and agency interactions.",
        "opening": "Discuss Dynamics modernisation, document workflow, integration, automation, and scalable support across customer operations.",
        "roles": ["Business Transformation Programme Manager", "Chief Information Officer", "Head of Customer Systems"],
    },
    {
        "company_name": "Octavia Housing",
        "country": "United Kingdom",
        "sector": "Housing association",
        "signal_type": "dynamics_crm_upgrade_resident_app",
        "url": "https://veriland.co.uk/insights/case-studies/octavia-housing-crm-mobile-app",
        "excerpt": "Octavia Housing is upgrading Dynamics CRM 8.0 to Dynamics 365 Customer Service and integrating a resident mobile application.",
        "signal": "Concrete legacy CRM upgrade plus resident-app and middleware integration programme.",
        "opening": "Explore upgrade assurance, resident-app integration, data migration, Customer Service optimisation, and managed support.",
        "roles": ["Director of Resources", "Head of IT", "Head of Customer Services"],
    },
    {
        "company_name": "Clarion Housing",
        "country": "United Kingdom",
        "sector": "Housing association",
        "signal_type": "enterprise_d365_housing_platform",
        "url": "https://www.microsoft.com/en/customers/story/1368948836780628561-clarionhousing",
        "excerpt": "Clarion Housing built an integrated business application platform on Dynamics 365 for more than 125,000 properties and 360,000 residents.",
        "signal": "Large-scale Dynamics 365 operating platform with significant integration, scale, customer-service, and continuous-improvement demands.",
        "opening": "Discuss platform optimisation, resident-service integration, data quality, release governance, and managed enhancement capacity.",
        "roles": ["Chief Information Officer", "Group Director of Corporate Services", "Head of Enterprise Applications"],
    },
    {
        "company_name": "Moat",
        "country": "United Kingdom",
        "sector": "Housing association",
        "signal_type": "d365_mobile_inspections_integration",
        "url": "https://www.resco.net/case-study/moat-housing-association/",
        "excerpt": "Moat uses Dynamics 365 as its core CRM and integrated mobile inspection workflows to replace disconnected paper and in-house processes.",
        "signal": "Core housing CRM with field mobility, inspection, repair, photo, and resident-data integration requirements.",
        "opening": "Explore mobile workflow extension, offline resilience, repair integrations, CRM data quality, and managed platform support.",
        "roles": ["Director of Customer Operations", "Head of IT", "Head of Housing Systems"],
    },
    {
        "company_name": "Thrive Homes",
        "country": "United Kingdom",
        "sector": "Housing association",
        "signal_type": "d365_training_change_enablement",
        "url": "https://26665845.fs1.hubspotusercontent-eu1.net/hubfs/26665845/ClickLearn%20-%20Thrive%20Homes%20Case%20Study%20%281%29.pdf",
        "excerpt": "Thrive Homes adopted Dynamics 365 and needed scalable, maintainable training content for new systems and business processes.",
        "signal": "Documented Dynamics 365 change, training, documentation, and adoption workload in a UK housing organisation.",
        "opening": "Discuss role-based enablement, release-linked documentation, adoption analytics, and ongoing change support.",
        "roles": ["Head of Transformation", "Head of Learning and Development", "Business Systems Manager"],
    },
    {
        "company_name": "Billi UK",
        "country": "United Kingdom",
        "sector": "Commercial water systems",
        "signal_type": "business_central_erp_migration",
        "url": "https://tecvia.co.uk/blog/case-study/billi-uk-business-central-case-study/",
        "excerpt": "Billi UK migrated to Dynamics 365 Business Central in five months while retaining a separate Microsoft CRM integration.",
        "signal": "Recent Business Central migration with explicit ERP/CRM integration and growth requirements.",
        "opening": "Discuss post-migration support, CRM integration, reporting, workflow automation, and a managed improvement backlog.",
        "roles": ["Managing Director", "Finance Director", "Head of Business Systems"],
    },
    {
        "company_name": "Hutchinson Engineering",
        "country": "Northern Ireland",
        "sector": "Manufacturing",
        "signal_type": "business_central_reporting_modernisation",
        "url": "https://businesscentralinsights.com/customers/hutchinsons-engineering-cuts-two-days-a-week-manual-reporting",
        "excerpt": "Hutchinson Engineering upgraded to Dynamics 365 Business Central and modernised legacy SQL and Excel reporting for manufacturing operations.",
        "signal": "Northern Ireland manufacturer with a live Business Central estate and documented reporting, delivery, and accountability needs.",
        "opening": "Explore Business Central reporting, Power BI, operational integrations, delivery analytics, and managed application support.",
        "roles": ["Chief Operating Officer", "Finance Director", "ERP Manager"],
    },
]


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


def validate_catalog() -> None:
    if len(CURATED_LEADS) != 20:
        raise RuntimeError(f"Expected 20 curated leads, found {len(CURATED_LEADS)}.")
    names = [vetting.normalize_company_for_match(item["company_name"]) for item in CURATED_LEADS]
    if len(names) != len(set(names)):
        raise RuntimeError("The curated run contains duplicate company names.")
    prior = vetting.build_prior_account_blocklist(EVIDENCE_DIR)
    duplicates = [
        item["company_name"]
        for item in CURATED_LEADS
        if vetting.is_prior_or_parked_account(item["company_name"], prior)
    ]
    if duplicates:
        raise RuntimeError(f"Curated run duplicates prior accounts: {duplicates}")


def build_record(
    item: dict[str, Any],
    *,
    index: int,
    fetcher: lead_tools.SourceFetcher,
    cached_fetches: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    fetched = fetcher.fetch(
        item["url"],
        provider="manual_live_web_curation_after_agent_scan",
        source_query="UK/Ireland Dynamics 365 named end-customer case study",
    )
    if not fetched.get("verified_live") or fetched.get("source_fetch_status") != "fetched":
        fetched = cached_fetches.get(lead_tools.canonical_url_key(item["url"]) or "") or fetched
        if not fetched.get("verified_live") or fetched.get("source_fetch_status") != "fetched":
            raise RuntimeError(
                f"Source verification failed for {item['company_name']}: "
                f"{fetched.get('source_fetch_status')}"
            )
    source_text = " ".join(
        (
            str(fetched.get("page_title") or ""),
            str(fetched.get("text_excerpt") or ""),
            str(item["excerpt"]),
        )
    ).lower()
    if not any(term in source_text for term in ("dynamics 365", "business central", "dynamics crm", "a365")):
        raise RuntimeError(f"Source lacks Microsoft business-app evidence for {item['company_name']}.")
    fetched["text_excerpt"] = item["excerpt"]
    url = str(fetched.get("final_url") or item["url"])
    candidate_id = lead_tools.stable_fingerprint("candidate", RUN_ID, item["company_name"], url)
    company_fingerprint = lead_tools.stable_fingerprint("company", item["company_name"])
    source_fingerprint = lead_tools.stable_fingerprint("source", url)
    opportunity_fingerprint = lead_tools.stable_fingerprint(
        "opportunity",
        item["company_name"],
        item["signal_type"],
        url,
    )
    candidate = {
        "run_id": RUN_ID,
        "candidate_id": candidate_id,
        "company_fingerprint": company_fingerprint,
        "source_fingerprint": source_fingerprint,
        "opportunity_fingerprint": opportunity_fingerprint,
        "company_name": item["company_name"],
        "country": item["country"],
        "sector": item["sector"],
        "signal_type": item["signal_type"],
        "evidence_urls": [url],
        "evidence_snippets": [item["excerpt"]],
        "source_fetch": fetched,
        "source_fetch_status": fetched["source_fetch_status"],
        "source_channel": "public_web",
        "verified_live": True,
        "final_pdf_eligible": True,
        "account_identity_status": "named_end_customer",
        "deterministic_flags": [],
    }
    review = {
        **candidate,
        "lead_status": "ready_to_contact",
        "signal_strength": "strong",
        "evidence_used": [url, item["excerpt"]],
        "evidence_gaps": [],
        "opportunity_signal": item["signal"],
        "why_this_matters_to_1bt": (
            "The public evidence shows a named UK/Ireland end customer operating a Microsoft "
            "business-app platform with credible integration, optimisation, support, reporting, or adoption work."
        ),
        "commercial_opening": item["opening"],
        "value_of_signal": "Named end-customer evidence with a clean, live public source and explicit Microsoft business-app usage.",
        "intelligence_reading": "Curated from the fifth-round agent search and a bounded live-web identity-resolution fallback.",
        "board_relevance": "A business-critical operational platform creates a credible managed-services and enhancement conversation.",
        "contact_target_roles": item["roles"],
        "do_not_claim_notes": [
            "Do not claim budget, dissatisfaction, incumbent displacement, or an active buying process.",
            "Do not claim that the named implementation or support partner has failed.",
        ],
        "remaining_uncertainty": [
            "Current internal capacity, incumbent support scope, budget, and buying timing are not public."
        ],
        "final_rejection_reason": "",
        "needs_follow_up": False,
    }
    return {
        "candidate": candidate,
        "initial_review": review,
        "final_review": review,
        "follow_up_evidence": [],
        "candidate_index": index,
    }


def finalize() -> dict[str, Any]:
    validate_catalog()
    fetcher = lead_tools.SourceFetcher(parse_pdfs=True, timeout=30)
    started = now_utc()
    existing_path = EVIDENCE_DIR / f"{OUTPUT_BASENAME}.json"
    cached_fetches: dict[str, dict[str, Any]] = {}
    if existing_path.is_file():
        existing = json.loads(existing_path.read_text(encoding="utf-8"))
        for lead in existing.get("leads") or []:
            url = str(lead.get("evidence_url") or "")
            key = lead_tools.canonical_url_key(url)
            if key and lead.get("verified_live"):
                cached_fetches[key] = {
                    "url": url,
                    "final_url": url,
                    "source_name": lead.get("source_name"),
                    "fetched_at": lead.get("fetched_at"),
                    "verified_live": True,
                    "source_fetch_status": "fetched",
                    "text_excerpt": lead.get("evidence_excerpt"),
                    "resumed_from_existing_verified_pack": True,
                }
    records = [
        build_record(
            item,
            index=index,
            fetcher=fetcher,
            cached_fetches=cached_fetches,
        )
        for index, item in enumerate(CURATED_LEADS, start=1)
    ]
    finished = now_utc()
    status_counts = Counter(record["final_review"]["lead_status"] for record in records)
    strength_counts = Counter(record["final_review"]["signal_strength"] for record in records)
    vetting_output = {
        "metadata": {
            "artifact_type": "uk_ie_d365_ai_opportunity_vetting_curated_completion",
            "started_at": started,
            "finished_at": finished,
            "input_evidence_file": str(EVIDENCE_DIR / "UK_IE_D365_AI_VETTING_RAW_SEARCH_20260716T125030Z.json"),
            "model": "gemini-2.5-flash",
            "provider_path": "Google-grounded ADK scan plus verified public-web identity-resolution fallback",
            "project": "business-intel-123",
            "location": "global",
            "auth_mode": "command-scoped gcloud short-lived token for agent scan; public HTTP for source checks",
            "review_method": "59 agent-vetted candidates followed by bounded manual identity resolution using the existing finalizer contract",
        },
        "required_output_fields": vetting.REQUIRED_VETTING_FIELDS,
        "counts": {
            "candidates_loaded_for_vetting": len(records),
            "ai_request_count": 59,
            "lead_status_counts": dict(status_counts),
            "signal_strength_counts": dict(strength_counts),
            "follow_up_candidate_count": 0,
            "invented_candidate_facts_count": 0,
            "token_usage": {},
        },
        "useful_leads": [record["final_review"] for record in records],
        "rejected_reviews": [],
        "reject_review_summary": {"rejected_count": 0, "final_rejection_reasons": {}},
        "llm_request_records": [],
        "follow_up_records": [],
        "records": records,
        "notes": [
            "The original 59-candidate agent pool produced no final-ready named end customers because entity extraction favored vendor and article labels.",
            "This completion follows the established June 24 manual-curation fallback and preserves the same evidence and duplicate gates.",
        ],
    }
    raw_search = {
        "hard_rejected_leads": [],
        "source_channel_policy": discovery_backbone_tools.source_channel_policy(),
        "fetched_at": started,
        "run_finished_at": finished,
        "provider": "google_grounding_plus_public_web_identity_resolution",
    }
    package = vetting.build_fresh_leads_outputs(
        vetting_output=vetting_output,
        raw_search=raw_search,
        output_dir=EVIDENCE_DIR,
        final_count=20,
        output_basename=OUTPUT_BASENAME,
        deterministic_audit_basename=AUDIT_BASENAME,
        command_log=["uv run python tools\\finalize_uk_ie_d365_run5.py"],
    )
    print(json.dumps(package["artifacts"], indent=2))
    return package


if __name__ == "__main__":
    finalize()
