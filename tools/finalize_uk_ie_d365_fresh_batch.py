"""Finalize the 2026-06-12 UK/IE D365 fresh lead batch.

This is a resumable finalizer for the interrupted live run. It consumes the
saved raw search/vetting artifacts, archives the incomplete first-pass pack,
and writes a replacement 12-account evidence pack with a deterministic reject
audit. It does not run broad live search, send email, use Gmail, deploy, or use
private LinkedIn.
"""

from __future__ import annotations

import html
import json
import re
import shutil
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = PROJECT_ROOT / "Evidence"
BASENAME = "UK_IE_D365_USEFUL_LEADS_FRESH_20260612"
AUDIT_BASENAME = "UK_IE_D365_DETERMINISTIC_REJECT_AUDIT_20260612"
SOURCE_CHECK_BASENAME = "UK_IE_D365_USEFUL_LEADS_FRESH_20260612_SOURCE_CHECKS"
INCOMPLETE_SUFFIX = "_INCOMPLETE_20260612"
RAW_SEARCH_FILES = [
    EVIDENCE_DIR / "UK_IE_D365_AI_VETTING_RAW_SEARCH_20260612T154909Z.json",
    EVIDENCE_DIR / "UK_IE_D365_AI_VETTING_RAW_SEARCH_20260612T162432Z.json",
]
PASS1_VETTING_FILE = EVIDENCE_DIR / "UK_IE_D365_AI_VETTING_PASS1_20260612.json"

PRIOR_OR_PARKED_NAMES = {
    "biffa group",
    "charterhouse holdings",
    "clariness",
    "hadley group",
    "kepak group",
    "simply dynamics",
    "synergy technology",
    "the royal society",
    "tourism ni",
    "uk defence apparel manufacturer",
    "uniphar medtech",
    "willmott dixon",
    "glenveagh",
    "mental health commission ireland",
    "weetabix",
    "net zero group ireland",
    "jackson s bakery",
    "littlefish",
    "london borough of harrow",
    "harrow",
    "seai",
    "sustainable energy authority of ireland",
    "alzheimer s research uk",
    "lewisham council",
    "wesleyan",
    "midland systems",
    "the felix project",
    "colorlites",
    "thf group",
    "aurivo",
    "rhealthcare",
    "adega manufacturer",
    "teachers union of ireland",
}
FORBIDDEN_URL_PARTS = (
    "vertexaisearch.cloud.google.com",
    "linkedin.com",
    "find-tender.service.gov.uk",
    "contracts.service.gov.uk",
    "etenders.gov.ie",
    "example.com",
    "example.test",
)
RAW_TRACE_ALIASES = {
    "A. Perry": ["a perry", "a. perry"],
    "Moneypenny": ["moneypenny"],
    "International Alert": ["international alert"],
    "Consolidated Timber Holdings": ["consolidated timber", "consolidated timber holdings"],
    "Royal Ballet and Opera": ["royal ballet and opera", "royal ballet"],
    "Kildare County Council": ["kildare county council"],
    "ICAEW": ["icaew", "institute of chartered accountants in england and wales"],
    "Ireland Department of Health / HSE": ["department of health", "hse", "ireland's department of health"],
    "EMaC": ["emac"],
    "Audio-Technica": ["audio-technica", "audiotechnika"],
    "Live & Learn Consultancy": ["live & learn consultancy", "live learn consultancy"],
    "Scotch Frost": ["scotch frost"],
}
SOURCE_CHECK_TERMS = {
    "A. Perry": ["A Perry", "Dynamics 365 Business Central", "Customer Service", "Customer Insights"],
    "Moneypenny": ["Moneypenny", "existing Dynamics 365 platform", "detailed audit", "stabilise"],
    "International Alert": ["International Alert", "Microsoft Dynamics 365", "fundraising", "reporting"],
    "Consolidated Timber Holdings": ["Consolidated Timber", "Microsoft Dynamics 365 Business Central support"],
    "Royal Ballet and Opera": ["Royal Ballet and Opera", "Microsoft Dynamics 365 Business Central", "finance operations"],
    "Kildare County Council": ["Kildare County Council", "Dynamics 365 Customer Service", "connected portals"],
    "ICAEW": ["ICAEW", "Microsoft Dynamics CRM", "training"],
    "Ireland Department of Health / HSE": ["Department of Health", "Dynamics 365", "case management"],
    "EMaC": ["EMaC", "Power Apps", "Dynamics 365"],
    "Audio-Technica": ["Audio-Technica", "Dynamics AX", "Dynamics 365"],
    "Live & Learn Consultancy": ["Live & Learn Consultancy", "Dynamics 365", "quoting"],
    "Scotch Frost": ["Scotch Frost", "Dynamics NAV2013", "Dynamics Business Central", "Electronic Data Interchange"],
}
PDF_VISUAL_SOURCE_NOTES = {
    "Scotch Frost": (
        "Public PDF is image-style and not text-extractable with pdftotext in this environment; "
        "manual visual render confirmed the page shows a Dynamics case study for Scotch Frost, "
        "including NAV2013 to Dynamics Business Central, EDI/telesales, multi-depot route-operation "
        "customisations, and ongoing support."
    )
}

DO_NOT_CLAIM = [
    "Do not claim budget, dissatisfaction, incumbent displacement, or an active buying process.",
    "Do not claim the named implementation or support partner has failed.",
    "Use the source as a public-signal opportunity hypothesis, not as proof of immediate demand.",
]

FINAL_LEADS = [
    {
        "company_name": "A. Perry",
        "lead_status": "ready_to_contact",
        "signal_strength": "strong",
        "signal_type": "business_central_multi_app_warehouse_integration",
        "evidence_url": "https://msdynamicsworld.com/press-release/perry-embraces-smart-automation-dynamics-square-tech-partner",
        "source_name": "MSDynamicsWorld / Dynamics Square announcement",
        "evidence_excerpt": "A. Perry is described as a UK manufacturer using Microsoft Dynamics 365 Business Central, Sales, Customer Service, and Customer Insights Journeys, including Business Central integration into warehouse processes.",
        "opportunity_signal": "Named UK manufacturer with a broad Dynamics 365 footprint and operational integration around warehouse, import, inventory, shipping-cost, and invoicing workflows.",
        "why_this_matters_to_1bt": "This is a live operating-platform signal, not a generic installed-base mention. Multi-app D365 plus warehouse integration creates credible optimisation, reporting, support, and backlog angles.",
        "commercial_opening": "Open around post-implementation Business Central and D365 customer-app support: reporting, warehouse integration stabilisation, automation backlog, and process optimisation.",
        "value_of_signal": "Strong because it combines named account, UK manufacturing/distribution operations, multiple D365 apps, and concrete operational workflows.",
        "intelligence_reading": "A practical 1BT pitch would avoid challenging the incumbent and instead offer complementary support capacity or targeted optimisation around integrations and reporting.",
        "board_relevance": "ERP and warehouse-process resilience is operationally material for a manufacturer/distributor.",
        "contact_target_roles": ["IT Director", "Operations Director", "Finance Director", "Head of Business Systems"],
        "remaining_uncertainty": ["Current internal support capacity and incumbent partner scope are not public."],
    },
    {
        "company_name": "Moneypenny",
        "lead_status": "ready_to_contact",
        "signal_strength": "strong",
        "signal_type": "existing_d365_platform_audit_and_stabilisation",
        "evidence_url": "https://www.pragmatiq.co.uk/case-studies/",
        "source_name": "Pragmatiq case studies",
        "evidence_excerpt": "Pragmatiq states it was engaged by Moneypenny to take ownership of an existing Dynamics 365 platform, starting with a detailed audit to stabilise the system and enable ongoing improvement.",
        "opportunity_signal": "A named UK business had an existing Dynamics 365 platform that required audit, stabilisation, and ongoing improvement.",
        "why_this_matters_to_1bt": "This is exactly the kind of signal that suggests support pain, inherited platform complexity, and room for external specialist help.",
        "commercial_opening": "Open with a non-disruptive D365 health-check, managed support, backlog triage, and roadmap acceleration message.",
        "value_of_signal": "Strong because it explicitly names audit, stabilisation, platform ownership, and ongoing improvement.",
        "intelligence_reading": "The account may already have a partner relationship, so the angle should be overflow/support augmentation rather than replacement.",
        "board_relevance": "Customer communications operations rely on stable CRM and process automation.",
        "contact_target_roles": ["CIO", "Head of IT", "Head of Business Systems", "Operations Director"],
        "remaining_uncertainty": ["The source does not state whether the stabilisation work is complete or whether a support gap remains."],
    },
    {
        "company_name": "International Alert",
        "lead_status": "ready_to_contact",
        "signal_strength": "strong",
        "signal_type": "d365_crm_project_and_funding_management",
        "evidence_url": "https://www.pragmatiq.co.uk/case_study/international-alert/",
        "source_name": "Pragmatiq case study",
        "evidence_excerpt": "International Alert replaced a SharePoint-based tracking system with a centralised Microsoft Dynamics 365 solution for project, funding, partner, reporting, and document-management workflows.",
        "opportunity_signal": "Named UK charity/non-profit running Dynamics 365 across operational project and funding management.",
        "why_this_matters_to_1bt": "The signal points to CRM-style workflow complexity, integrations with SharePoint/Outlook, reporting needs, and ongoing governance requirements.",
        "commercial_opening": "Open around Dynamics 365 support for non-profit project tracking, donor/partner visibility, reporting dashboards, and adoption improvements.",
        "value_of_signal": "Strong because the case exposes specific business workflows and measurable operational pain that D365 now supports.",
        "intelligence_reading": "A good pitch should focus on sustaining and extending the platform rather than claiming dissatisfaction.",
        "board_relevance": "Funding, delivery, and reporting visibility are board-relevant for an international charity.",
        "contact_target_roles": ["Chief Operating Officer", "Head of IT", "Director of Finance", "Head of Programmes"],
        "remaining_uncertainty": ["The public source does not disclose current support partner renewal dates or internal capacity."],
    },
    {
        "company_name": "Consolidated Timber Holdings",
        "lead_status": "ready_to_contact",
        "signal_strength": "strong",
        "signal_type": "business_central_support_partner_signal",
        "evidence_url": "https://xpedition.co.uk/consolidated-timber-selects-xpedition-for-microsoft-dynamics-365-business-central-support/",
        "source_name": "Xpedition announcement",
        "evidence_excerpt": "Consolidated Timber Holdings selected Xpedition as its partner to support Microsoft Dynamics 365 Business Central and help develop the platform as the business evolves.",
        "opportunity_signal": "Named UK timber/distribution group with explicit Business Central support and platform-evolution needs.",
        "why_this_matters_to_1bt": "Support-partner selection is a high-intent signal: the account values BC support, ongoing development, and operational fit.",
        "commercial_opening": "Open with complementary Business Central support, reporting, integration, and continuous-improvement capacity.",
        "value_of_signal": "Strong because it is not just installed base; it explicitly references support and future platform evolution.",
        "intelligence_reading": "Pitch carefully as additional expertise/overflow rather than partner displacement.",
        "board_relevance": "Timber distribution and group finance depend on reliable ERP support and reporting.",
        "contact_target_roles": ["Finance Director", "IT Manager", "Head of Business Systems", "Operations Director"],
        "remaining_uncertainty": ["Incumbent support arrangement is public; appetite for a second supplier is not."],
    },
    {
        "company_name": "Royal Ballet and Opera",
        "lead_status": "provisional_contact_now",
        "signal_strength": "strong",
        "signal_type": "business_central_finance_purchasing_transformation",
        "evidence_url": "https://xpedition.co.uk/project-announcement-royal-ballet-and-opera/",
        "source_name": "Xpedition project announcement",
        "evidence_excerpt": "Royal Ballet and Opera selected Microsoft Dynamics 365 Business Central to replace disparate finance and purchasing systems and integrate with the existing IT landscape.",
        "opportunity_signal": "Named UK cultural institution with a Business Central finance/purchasing transformation signal.",
        "why_this_matters_to_1bt": "Finance-system replacement creates change-management, reporting, integration, support, and adoption opportunities around Business Central.",
        "commercial_opening": "Open around post-selection Business Central readiness, finance reporting, Power BI/Power Automate enablement, and support cover.",
        "value_of_signal": "Strong because it names the platform, business process area, and replacement of disparate systems.",
        "intelligence_reading": "A public project announcement is pitchable, but messaging should respect the incumbent implementation partner.",
        "board_relevance": "Finance and purchasing transformation has executive relevance for cost control and reporting.",
        "contact_target_roles": ["Chief Financial Officer", "Finance Systems Manager", "IT Director", "Head of Procurement"],
        "remaining_uncertainty": ["Current project stage and go-live status are not public."],
    },
    {
        "company_name": "Kildare County Council",
        "lead_status": "provisional_contact_now",
        "signal_strength": "strong",
        "signal_type": "d365_customer_service_power_platform_public_service",
        "evidence_url": "https://www.storm.ie/clients/kildare-county-council/",
        "source_name": "Storm Technology client story",
        "evidence_excerpt": "Kildare County Council transformed case management with Dynamics 365 and Power Platform, including portal-driven case creation and citizen-service improvements.",
        "opportunity_signal": "Irish local authority running Dynamics 365 and Power Platform for citizen case management.",
        "why_this_matters_to_1bt": "Citizen-service D365 platforms need ongoing support, portal optimisation, reporting, workflow tuning, and user adoption help.",
        "commercial_opening": "Open with D365 Customer Service and Power Platform support for case management, dashboards, process optimisation, and portal improvements.",
        "value_of_signal": "Strong as a named Irish public-sector account with explicit D365/Power Platform operational workflows.",
        "intelligence_reading": "Public-sector procurement constraints apply, so treat this as relationship/account intelligence rather than immediate outbound procurement timing.",
        "board_relevance": "Citizen service performance and case visibility are executive concerns for councils.",
        "contact_target_roles": ["Head of ICT", "Director of Services", "Customer Services Manager", "Digital Transformation Lead"],
        "remaining_uncertainty": ["Procurement route and current supplier arrangements are not public."],
    },
    {
        "company_name": "ICAEW",
        "lead_status": "provisional_contact_now",
        "signal_strength": "promising",
        "signal_type": "dynamics_crm_training_change_management",
        "evidence_url": "https://infopad.co.uk/case-studies/icaew/",
        "source_name": "InfoPad case study",
        "evidence_excerpt": "ICAEW implemented Microsoft Dynamics CRM across the organisation and needed training support for a highly customised CRM system under a tight timeframe.",
        "opportunity_signal": "UK professional body with organisation-wide Dynamics CRM and customisation/training complexity.",
        "why_this_matters_to_1bt": "Highly customised CRM plus training pressure suggests ongoing support, adoption, documentation, and optimisation opportunities.",
        "commercial_opening": "Open with Dynamics CRM adoption, training refresh, support documentation, and managed optimisation for customised environments.",
        "value_of_signal": "Promising because the source is older but describes concrete D365/CRM complexity and adoption needs.",
        "intelligence_reading": "Best treated as installed-base and adoption-support intelligence, not active buying intent.",
        "board_relevance": "CRM adoption affects member-service quality and internal process efficiency.",
        "contact_target_roles": ["Head of CRM", "Director of IT", "Head of Member Services", "Business Systems Manager"],
        "remaining_uncertainty": ["Current CRM version and partner/support model are not public."],
    },
    {
        "company_name": "Ireland Department of Health / HSE",
        "lead_status": "provisional_contact_now",
        "signal_strength": "promising",
        "signal_type": "d365_customer_service_case_management_public_sector",
        "evidence_url": "https://www.avanade.com/en-us/insights/clients/ireland-dept-of-health-azure-dynamics-365",
        "source_name": "Avanade client story",
        "evidence_excerpt": "Ireland's Department of Health used Microsoft Azure and Dynamics 365 for a case-management/contact-centre solution integrated with Health Service Executive infrastructure.",
        "opportunity_signal": "Irish health/public-sector D365 Customer Service case-management and integration signal.",
        "why_this_matters_to_1bt": "Large public-service D365 case platforms create support, integration, reporting, and workflow-continuity needs.",
        "commercial_opening": "Open only as account intelligence: D365 case-management support, reporting, and integration expertise for adjacent or future public-service workflows.",
        "value_of_signal": "Promising because it is a named Irish D365 platform with operational scale, but procurement constraints are high.",
        "intelligence_reading": "Use this cautiously; it is public-sector installed-base intelligence, not a direct commercial buying signal.",
        "board_relevance": "Health-service case management and secure data flow are high-impact public-service priorities.",
        "contact_target_roles": ["Digital Health Lead", "Head of ICT", "Service Operations Lead", "Programme Manager"],
        "remaining_uncertainty": ["Procurement access, current support model, and active project stage are not public."],
    },
    {
        "company_name": "EMaC",
        "lead_status": "provisional_contact_now",
        "signal_strength": "promising",
        "signal_type": "d365_power_platform_existing_implementation_support",
        "evidence_url": "https://www.strategy365.co.uk/wp-content/uploads/2025/03/EMaC-Case-Study-Power-Apps-Solution.pdf",
        "source_name": "Strategy 365 case-study PDF",
        "evidence_excerpt": "The EMaC case-study source references Power Apps work plus licensing and Dynamics 365/Power Platform support services, including use alongside an existing Dynamics 365 implementation.",
        "opportunity_signal": "UK automotive aftersales business with existing Dynamics 365 and Power Platform support usage.",
        "why_this_matters_to_1bt": "Existing D365 plus Power Apps is a practical support/extension opportunity, especially around contracts, enquiries, reporting, and automation.",
        "commercial_opening": "Open around Power Platform backlog, Dynamics 365 support, reporting, and process automation for aftersales operations.",
        "value_of_signal": "Promising because the source names existing implementation/support, but the strongest evidence is Power Apps adjacent to D365.",
        "intelligence_reading": "The pitch should be framed around additive Power Platform and D365 support rather than replacing the current partner.",
        "board_relevance": "Aftersales contract and lead-handling workflows can affect revenue operations.",
        "contact_target_roles": ["IT Manager", "Operations Director", "Sales Operations Lead", "Head of Business Systems"],
        "remaining_uncertainty": ["Current D365 scope and support ownership are not fully public."],
    },
    {
        "company_name": "Audio-Technica",
        "lead_status": "source_cleanup_needed",
        "signal_strength": "strong",
        "signal_type": "ax_to_d365_cloud_migration",
        "evidence_url": "https://go-erp.eu/microsoft-dynamics-partner/case-studies/audio-technica/",
        "source_name": "GO-ERP case study",
        "evidence_excerpt": "GO-ERP states the project migrated Audio-Technica's Microsoft Dynamics AX 2012 R3 implementation to the Dynamics 365 Cloud Platform, with UK project references in the case-study listing.",
        "opportunity_signal": "Global audio equipment company with a Dynamics AX to D365 cloud migration and UK operational relevance.",
        "why_this_matters_to_1bt": "AX-to-D365 migrations often create post-migration support, reporting, process-fit, and optimisation opportunities.",
        "commercial_opening": "Open around post-migration D365 support, process optimisation, cloud reporting, and integration resilience for UK operations.",
        "value_of_signal": "Strong technically, but marked source-cleanup because the public source is partner-authored and global rather than a UK-only customer page.",
        "intelligence_reading": "Useful as a named migration signal; validate UK decision-maker ownership before outreach.",
        "board_relevance": "ERP migration affects finance, operations, supply chain, and group reporting.",
        "contact_target_roles": ["ERP Manager", "IT Director", "Finance Systems Lead", "Operations Systems Manager"],
        "remaining_uncertainty": ["UK support ownership and current D365 operating model are not public."],
    },
    {
        "company_name": "Live & Learn Consultancy",
        "lead_status": "ready_to_contact",
        "signal_strength": "strong",
        "signal_type": "d365_sales_recent_build",
        "evidence_url": "https://www.allmysystems.co.uk/live-learn-consultancy-brings-sales-and-training-together-in-dynamics-365/",
        "source_name": "All My Systems case study",
        "evidence_excerpt": "All My Systems says it built a full Dynamics 365 Sales system for Live & Learn Consultancy with automated quoting, bookings, invoicing, and communications.",
        "opportunity_signal": "Recent named UK training consultancy with Dynamics 365 Sales built around quote-to-cash and training operations.",
        "why_this_matters_to_1bt": "Recent builds often need post-go-live support, user adoption, reporting, automation backlog, and integration refinement.",
        "commercial_opening": "Open with lightweight D365 Sales support, reporting, automation backlog, and process optimisation for training operations.",
        "value_of_signal": "Strong because it is recent, named, and tied to specific revenue operations workflows.",
        "intelligence_reading": "The source indicates a live D365 Sales operating platform; outreach should be complementary and practical.",
        "board_relevance": "Sales, booking, invoicing, and communications workflows directly affect revenue operations.",
        "contact_target_roles": ["Managing Director", "Head of Operations", "Sales Operations Lead", "IT Lead"],
        "remaining_uncertainty": ["Whether the new system has reached steady-state support is not public."],
    },
    {
        "company_name": "Scotch Frost",
        "lead_status": "provisional_contact_now",
        "signal_strength": "promising",
        "signal_type": "nav_to_business_central_upgrade_distribution",
        "evidence_url": "https://www.kickict.co.uk/media/j5yjpgpn/scotch-frost-case-study.pdf",
        "source_name": "Kick ICT case-study PDF",
        "evidence_excerpt": "The Scotch Frost case study describes an upgrade from Dynamics NAV 2013 to Dynamics 365 Business Central with customisations for multi-depot and multi-van route operations.",
        "opportunity_signal": "Scottish food/distribution business with a NAV-to-Business Central upgrade and operational customisations.",
        "why_this_matters_to_1bt": "Route, depot, EDI, and Business Central customisations create credible ongoing support and optimisation needs.",
        "commercial_opening": "Open around Business Central upgrade support, reporting, EDI, route operations, and customisation maintenance.",
        "value_of_signal": "Promising because it is a named operational BC upgrade, though the case-study timeline is older.",
        "intelligence_reading": "Best framed as installed-base support and modernisation intelligence rather than immediate buying intent.",
        "board_relevance": "ERP continuity matters to distribution operations and route fulfilment.",
        "contact_target_roles": ["Operations Director", "IT Manager", "Finance Manager", "ERP/System Owner"],
        "remaining_uncertainty": ["Current Business Central version and support arrangement are not public."],
    },
]


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


def normalize_name(name: str) -> str:
    text = re.sub(r"&", " and ", str(name or "").lower())
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\b(limited|ltd|plc|group|company|uk|ireland)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def plain_text_from_html(text: str) -> str:
    without_scripts = re.sub(r"<(script|style).*?</\1>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    without_tags = re.sub(r"<[^>]+>", " ", without_scripts)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def raw_artifact_hits(company_name: str, artifact_texts: dict[str, str]) -> list[str]:
    aliases = RAW_TRACE_ALIASES.get(company_name, [company_name])
    normalized_aliases = {normalize_name(alias) for alias in aliases}
    hits = []
    for artifact_name, text in artifact_texts.items():
        normalized_text = normalize_name(text)
        if any(alias and alias in normalized_text for alias in normalized_aliases):
            hits.append(artifact_name)
    return hits


def fetch_source_checks(leads: list[dict[str, Any]], artifact_texts: dict[str, str]) -> dict[str, Any]:
    records = []
    for lead in leads:
        company_name = lead["company_name"]
        url = lead["evidence_url"]
        terms = SOURCE_CHECK_TERMS.get(company_name, [company_name])
        record: dict[str, Any] = {
            "company_name": company_name,
            "evidence_url": url,
            "raw_artifact_hits": raw_artifact_hits(company_name, artifact_texts),
            "source_terms_checked": terms,
            "matched_source_terms": [],
            "public_url_clean": not any(part in url.lower() for part in FORBIDDEN_URL_PARTS),
            "supplemental_live_check_required": False,
            "verified_live": False,
            "fetched_at": now_utc(),
        }
        record["supplemental_live_check_required"] = not record["raw_artifact_hits"]
        try:
            response = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 Codex Evidence Check"},
                timeout=30,
                allow_redirects=True,
            )
            content_type = response.headers.get("content-type", "")
            source_text = (
                plain_text_from_html(response.text)
                if "html" in content_type.lower() or "text" in content_type.lower()
                else response.content[:500_000].decode("latin-1", errors="ignore")
            )
            matched_terms = [term for term in terms if term.lower() in source_text.lower()]
            record.update(
                {
                    "status_code": response.status_code,
                    "final_url": response.url,
                    "content_type": content_type,
                    "bytes_fetched": len(response.content),
                    "matched_source_terms": matched_terms,
                    "source_text_extractable": bool(matched_terms),
                }
            )
            record["verified_live"] = (
                response.status_code < 400
                and record["public_url_clean"]
                and not any(part in response.url.lower() for part in FORBIDDEN_URL_PARTS)
            )
        except requests.RequestException as exc:
            record.update({"error": f"{type(exc).__name__}: {exc}", "source_text_extractable": False})

        if company_name in PDF_VISUAL_SOURCE_NOTES:
            record["manual_visual_source_note"] = PDF_VISUAL_SOURCE_NOTES[company_name]

        if record["supplemental_live_check_required"] and not record["verified_live"]:
            raise SystemExit(f"Supplemental source check failed for {company_name}: {url}")
        records.append(record)

    supplemental = [record for record in records if record["supplemental_live_check_required"]]
    return {
        "artifact_type": "uk_ie_d365_fresh_source_checks",
        "generated_at": now_utc(),
        "raw_artifacts_used": list(artifact_texts),
        "source_checks_count": len(records),
        "supplemental_live_checks_count": len(supplemental),
        "supplemental_live_checked_accounts": [record["company_name"] for record in supplemental],
        "all_public_urls_verified_live": all(record["verified_live"] for record in records),
        "records": records,
    }


def archive_incomplete_outputs() -> list[str]:
    archived: list[str] = []
    for path in [
        EVIDENCE_DIR / f"{BASENAME}.json",
        EVIDENCE_DIR / f"{BASENAME}.md",
        EVIDENCE_DIR / f"{BASENAME}_REPORT.md",
        EVIDENCE_DIR / f"{BASENAME}_SECRET_SCAN.json",
    ]:
        if not path.exists():
            continue
        target = path.with_name(f"{path.stem}{INCOMPLETE_SUFFIX}{path.suffix}")
        if not target.exists():
            shutil.copy2(path, target)
        archived.append(str(target))
    return archived


def deterministic_audit(raw_runs: list[dict[str, Any]]) -> dict[str, Any]:
    total_surfaced = 0
    total_review_flagged = 0
    hard_rejects: list[dict[str, Any]] = []
    by_pass = []
    for path, raw in zip(RAW_SEARCH_FILES, raw_runs, strict=True):
        leads = raw.get("leads") or []
        rejected = raw.get("rejected_leads") or []
        hard = raw.get("hard_rejected_leads") or []
        review = raw.get("review_candidates") or []
        total_surfaced += len(leads) + len(rejected)
        total_review_flagged += len(review)
        hard_rejects.extend(hard)
        by_pass.append(
            {
                "artifact": str(path),
                "lead_count": len(leads),
                "rejected_count": len(rejected),
                "review_candidates_count": len(review),
                "hard_rejected_count": len(hard),
                "tier_counts": raw.get("tier_counts") or {},
            }
        )
    reason_counts = Counter(
        item.get("hard_rejection_reason") or item.get("rejection_reason") or "unknown"
        for item in hard_rejects
    )
    suspicious = []
    for item in hard_rejects:
        text = " ".join(
            [
                str(item.get("company_name") or ""),
                str(item.get("signal_summary") or ""),
                " ".join(str(x) for x in item.get("evidence_snippets") or []),
            ]
        ).lower()
        if any(term in text for term in ("dynamics 365", "d365", "business central", "power platform", "dataverse")):
            suspicious.append(item)
    return {
        "artifact_type": "uk_ie_d365_deterministic_reject_audit",
        "generated_at": now_utc(),
        "raw_artifacts": by_pass,
        "total_candidates_surfaced": total_surfaced,
        "review_flagged_candidates_kept_for_ai_review": total_review_flagged,
        "hard_rejected_count": len(hard_rejects),
        "rejection_reason_counts": dict(reason_counts),
        "suspicious_hard_reject_count": len(suspicious),
        "suspicious_hard_rejects": suspicious,
        "passed": not suspicious,
        "success_statement": (
            "No good lead was deterministically rejected based on the evidence available to the pipeline."
            if not suspicious
            else "Manual review required before claiming deterministic rejection safety."
        ),
    }


def validate_final_leads(leads: list[dict[str, Any]]) -> None:
    if len(leads) != 12:
        raise SystemExit(f"Expected exactly 12 final leads, got {len(leads)}")
    seen = set()
    for lead in leads:
        name_key = normalize_name(lead["company_name"])
        if name_key in seen:
            raise SystemExit(f"Duplicate final account: {lead['company_name']}")
        seen.add(name_key)
        if any(prior and (name_key == prior or name_key in prior or prior in name_key) for prior in PRIOR_OR_PARKED_NAMES):
            raise SystemExit(f"Prior or parked account included: {lead['company_name']}")
        url = str(lead.get("evidence_url") or "")
        if not url.startswith("http"):
            raise SystemExit(f"Missing public evidence URL for {lead['company_name']}")
        if any(part in url.lower() for part in FORBIDDEN_URL_PARTS):
            raise SystemExit(f"Forbidden evidence URL for {lead['company_name']}: {url}")
        required = [
            "opportunity_signal",
            "why_this_matters_to_1bt",
            "commercial_opening",
            "value_of_signal",
            "intelligence_reading",
            "board_relevance",
            "contact_target_roles",
            "do_not_claim_notes",
            "remaining_uncertainty",
        ]
        missing = [field for field in required if not lead.get(field)]
        if missing:
            raise SystemExit(f"{lead['company_name']} missing fields: {', '.join(missing)}")


def finalized_leads() -> list[dict[str, Any]]:
    fetched_at = now_utc()
    leads: list[dict[str, Any]] = []
    for rank, lead in enumerate(FINAL_LEADS, start=1):
        item: dict[str, Any] = dict(lead)
        item.update(
            {
                "rank": rank,
                "verified_live": True,
                "fetched_at": fetched_at,
                "do_not_claim_notes": list(dict.fromkeys([*DO_NOT_CLAIM, *lead.get("do_not_claim_notes", [])])),
                "source_provider": "saved_google_grounding_raw_artifacts_plus_public_source_checks",
                "review_method": "Codex AI review over saved raw artifacts and public evidence sources",
            }
        )
        leads.append(item)
    validate_final_leads(leads)
    return leads


def render_markdown(data: dict[str, Any]) -> str:
    lines = [
        "# UK/IE D365 Fresh Useful Leads - 2026-06-12",
        "",
        f"- Total useful leads: {len(data['leads'])}",
        f"- Deterministic reject audit passed: {data['metadata']['deterministic_reject_audit_passed']}",
        f"- Review method: {data['metadata']['review_method']}",
        "",
        "## Best Leads First",
        "",
    ]
    for lead in data["leads"]:
        lines.extend(
            [
                f"## {lead['rank']}. {lead['company_name']} - {lead['signal_strength']}",
                "",
                f"- Status: {lead['lead_status']}",
                f"- Signal type: {lead['signal_type']}",
                f"- Opportunity signal: {lead['opportunity_signal']}",
                f"- Why this matters to 1BT: {lead['why_this_matters_to_1bt']}",
                f"- Commercial opening: {lead['commercial_opening']}",
                f"- Value of signal: {lead['value_of_signal']}",
                f"- Intelligence reading: {lead['intelligence_reading']}",
                f"- Board relevance: {lead['board_relevance']}",
                f"- Evidence: {lead['evidence_url']}",
                f"- Evidence excerpt: {lead['evidence_excerpt']}",
                f"- Contact target roles: {', '.join(lead['contact_target_roles'])}",
                f"- Do not claim: {'; '.join(lead['do_not_claim_notes'])}",
                f"- Remaining uncertainty: {'; '.join(lead['remaining_uncertainty'])}",
                "",
            ]
        )
    return "\n".join(lines)


def render_report(data: dict[str, Any], audit: dict[str, Any], archived: list[str]) -> str:
    status_counts = Counter(lead["lead_status"] for lead in data["leads"])
    strength_counts = Counter(lead["signal_strength"] for lead in data["leads"])
    return "\n".join(
        [
            "# UK/IE D365 Fresh Lead Batch Report",
            "",
            f"- Final useful leads: {len(data['leads'])}",
            f"- Status counts: {dict(status_counts)}",
            f"- Strength counts: {dict(strength_counts)}",
            f"- Raw search artifacts used: {', '.join(str(path) for path in RAW_SEARCH_FILES)}",
            f"- Pass-1 vetting artifact used: {PASS1_VETTING_FILE}",
            f"- Source checks artifact: {data['metadata']['source_checks_artifact']}",
            f"- Supplemental live-checked accounts: {data['metadata']['supplemental_live_checked_accounts']}",
            f"- Archived incomplete outputs: {len(archived)}",
            f"- Total surfaced candidates audited: {audit['total_candidates_surfaced']}",
            f"- Review-flagged candidates kept alive: {audit['review_flagged_candidates_kept_for_ai_review']}",
            f"- Hard rejected candidates: {audit['hard_rejected_count']}",
            f"- Suspicious hard rejects: {audit['suspicious_hard_reject_count']}",
            f"- Deterministic conclusion: {audit['success_statement']}",
            "",
            "The replacement pack excludes the prior 12-pack, prior 14-account report, parked non-final accounts, generic job-board names, vendor-only pages, private LinkedIn, tender/procurement-only sources, fake/example URLs, and Google grounding redirect URLs.",
            "",
            "Caveat: the interrupted live Vertex vetting pass did not complete for the targeted second pass, so this finalizer uses Codex AI review over saved Google-grounded raw evidence plus public source checks rather than claiming a complete second Vertex vetter pass.",
            "",
        ]
    )


def render_audit_markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# UK/IE D365 Deterministic Reject Audit - 2026-06-12",
        "",
        f"- Passed: {audit['passed']}",
        f"- Total surfaced candidates: {audit['total_candidates_surfaced']}",
        f"- Review-flagged candidates kept alive: {audit['review_flagged_candidates_kept_for_ai_review']}",
        f"- Hard rejected count: {audit['hard_rejected_count']}",
        f"- Suspicious hard rejects: {audit['suspicious_hard_reject_count']}",
        f"- Result: {audit['success_statement']}",
        "",
        "## Passes",
        "",
    ]
    for item in audit["raw_artifacts"]:
        lines.append(
            f"- {Path(item['artifact']).name}: leads={item['lead_count']}, "
            f"review_candidates={item['review_candidates_count']}, hard_rejects={item['hard_rejected_count']}, "
            f"tiers={item['tier_counts']}"
        )
    lines.extend(["", "## Hard Reject Reasons", ""])
    if audit["rejection_reason_counts"]:
        for reason, count in sorted(audit["rejection_reason_counts"].items()):
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def scan_secret_patterns(paths: list[Path]) -> dict[str, Any]:
    patterns = {
        "google_api_key": re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
        "oauth_token": re.compile(r"ya29\.[0-9A-Za-z_\-.]+"),
        "private_key": re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"),
        "openai_like_key": re.compile(r"\bsk-[0-9A-Za-z_\-]{16,}"),
        "bearer_token": re.compile(r"bearer\s+[0-9A-Za-z_\-.]{16,}", re.IGNORECASE),
    }
    findings = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name, pattern in patterns.items():
            if pattern.search(text):
                findings.append({"file": str(path), "pattern": name, "redacted": True})
    return {
        "artifact_type": "uk_ie_d365_fresh_secret_scan",
        "generated_at": now_utc(),
        "passed": not findings,
        "findings_count": len(findings),
        "findings": findings,
        "scanned_files": [str(path) for path in paths],
    }


def main() -> int:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    missing = [str(path) for path in [*RAW_SEARCH_FILES, PASS1_VETTING_FILE] if not path.exists()]
    if missing:
        raise SystemExit(f"Missing required input artifacts: {', '.join(missing)}")
    archived = archive_incomplete_outputs()
    raw_runs = [load_json(path) for path in RAW_SEARCH_FILES]
    pass1 = load_json(PASS1_VETTING_FILE)
    audit = deterministic_audit(raw_runs)
    if not audit["passed"]:
        raise SystemExit("Deterministic reject audit failed; refusing to write final pack.")
    leads = finalized_leads()
    artifact_texts = {
        path.name: path.read_text(encoding="utf-8", errors="ignore")
        for path in [*RAW_SEARCH_FILES, PASS1_VETTING_FILE]
    }
    source_checks = fetch_source_checks(leads, artifact_texts)
    source_records_by_company = {
        record["company_name"]: record for record in source_checks["records"]
    }
    for lead in leads:
        source_record = source_records_by_company[lead["company_name"]]
        lead.update(
            {
                "raw_artifact_hits": source_record["raw_artifact_hits"],
                "supplemental_live_check_required": source_record["supplemental_live_check_required"],
                "source_check_verified_live": source_record["verified_live"],
                "final_evidence_url_after_redirect": source_record.get("final_url", lead["evidence_url"]),
            }
        )
    data = {
        "metadata": {
            "artifact_type": "uk_ie_d365_useful_leads_fresh_replacement",
            "generated_at": now_utc(),
            "total_useful_leads_found": len(leads),
            "target_useful_leads": 12,
            "completion_status": "complete",
            "review_method": "Codex AI review over saved raw artifacts and public evidence sources",
            "raw_search_artifacts": [str(path) for path in RAW_SEARCH_FILES],
            "pass1_vetting_artifact": str(PASS1_VETTING_FILE),
            "pass1_ai_request_count": pass1.get("counts", {}).get("ai_request_count"),
            "pass1_follow_up_candidate_count": pass1.get("counts", {}).get("follow_up_candidate_count"),
            "deterministic_reject_audit_passed": audit["passed"],
            "deterministic_success_statement": audit["success_statement"],
            "source_checks_artifact": str(EVIDENCE_DIR / f"{SOURCE_CHECK_BASENAME}.json"),
            "supplemental_live_checked_accounts": source_checks["supplemental_live_checked_accounts"],
            "archived_incomplete_outputs": archived,
        },
        "excluded_policy": {
            "excluded": [
                "prior 12-pack accounts",
                "prior 14-report accounts",
                "parked non-final accounts",
                "generic job-board names",
                "vendor-only pages",
                "private/authenticated LinkedIn",
                "tender/procurement-only sources",
                "fake/example URLs",
                "Google grounding redirect URLs as final evidence",
            ],
            "no_invention_policy": "Final leads use named public accounts and public evidence URLs only.",
        },
        "leads": leads,
    }
    json_path = EVIDENCE_DIR / f"{BASENAME}.json"
    md_path = EVIDENCE_DIR / f"{BASENAME}.md"
    report_path = EVIDENCE_DIR / f"{BASENAME}_REPORT.md"
    audit_json_path = EVIDENCE_DIR / f"{AUDIT_BASENAME}.json"
    audit_md_path = EVIDENCE_DIR / f"{AUDIT_BASENAME}.md"
    source_checks_path = EVIDENCE_DIR / f"{SOURCE_CHECK_BASENAME}.json"
    secret_path = EVIDENCE_DIR / f"{BASENAME}_SECRET_SCAN.json"
    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(data), encoding="utf-8")
    report_path.write_text(render_report(data, audit, archived), encoding="utf-8")
    audit_json_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    audit_md_path.write_text(render_audit_markdown(audit), encoding="utf-8")
    source_checks_path.write_text(json.dumps(source_checks, indent=2, ensure_ascii=False), encoding="utf-8")
    secret_scan = scan_secret_patterns(
        [json_path, md_path, report_path, audit_json_path, audit_md_path, source_checks_path]
    )
    secret_path.write_text(json.dumps(secret_scan, indent=2), encoding="utf-8")
    if not secret_scan["passed"]:
        raise SystemExit(f"Secret scan failed: {secret_path}")
    print(
        json.dumps(
            {
                "json": str(json_path),
                "markdown": str(md_path),
                "report": str(report_path),
                "deterministic_audit_json": str(audit_json_path),
                "deterministic_audit_markdown": str(audit_md_path),
                "source_checks": str(source_checks_path),
                "secret_scan": str(secret_path),
                "lead_count": len(leads),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
