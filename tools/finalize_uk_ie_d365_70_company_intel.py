"""Create the final 70-company CRM and Google Sheets intelligence packs.

The five PDF companion packs remain the source of record.  This command overlays
the bounded live refresh for the older weak batch, preserves the canonical
Northwind company order, and emits separate detailed CRM and concise Sheet data.
It performs no CRM or Google Sheets mutation.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "Evidence"
EVIDENCE_ROOT = EVIDENCE.resolve()
DEFAULT_BASE = EVIDENCE / "UK_IE_D365_70_COMPANY_INTELLIGENCE_20260719.json"
DEFAULT_REFRESH = (
    EVIDENCE / "UK_IE_D365_70_COMPANY_ADK_REFRESH_20260719_FINAL_PROOF_V2.json"
)
DEFAULT_PREFIX = EVIDENCE / "UK_IE_D365_70_COMPANY_INTELLIGENCE_FINAL_20260719"
DEFAULT_CRM_PROFILE = DEFAULT_PREFIX.with_name(
    DEFAULT_PREFIX.name + "_CRM_PROFILE_BEFORE.json"
)
CRM_PROJECT = "globalapps-northwind-crm"
CRM_DATABASE = "(default)"
CRM_WORKSPACE = "default"

COUNTRY_FALLBACKS = {
    "Biffa Group": "United Kingdom",
    "Charterhouse Holdings": "United Kingdom",
    "Clariness": "United Kingdom presence; Germany headquartered",
    "Hadley Group": "United Kingdom",
    "Kepak Group": "Ireland and United Kingdom",
    "Simply Dynamics 365": "Ireland",
    "Synergy Technology": "United Kingdom",
    "The Royal Society / Subscribe360": "United Kingdom",
    "Tourism NI": "Northern Ireland",
    "UK defence apparel manufacturer (unnamed in source)": "United Kingdom",
    "Uniphar Medtech": "Ireland and United Kingdom",
    "Willmott Dixon": "United Kingdom",
}

STANDARD_DO_NOT_CLAIM = [
    "Do not claim current budget, dissatisfaction, procurement intent, or an active buying cycle unless separately verified.",
    "Treat public implementation, hiring, and case-study evidence as an opportunity hypothesis, not proof of immediate demand.",
]


def override(
    *,
    evidence: str,
    opening: str,
    url: str,
    source: str,
    why: str,
    reading: str,
    value: str,
    sheet: str,
    signal_type: str,
    status: str = "actionable_hypothesis",
    uncertainty: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "specific_evidence": evidence,
        "opportunity_signal": evidence,
        "commercial_opening": opening,
        "curated_evidence_url": url,
        "curated_source_name": source,
        "why_this_matters_to_1bt": why,
        "intelligence_reading": reading,
        "value_of_signal": value,
        "sheet_summary": sheet,
        "signal_type": signal_type,
        "opportunity_status": status,
        "remaining_uncertainty": uncertainty or [],
    }


INTEL_OVERRIDES = {
    "Biffa Group": override(
        evidence=(
            "Biffa uses Dynamics 365 Finance for high-volume finance and procurement: roughly 200,000-250,000 "
            "invoice lines per month, £450m annual purchasing across 4,500+ suppliers, about 100 legal entities, and "
            "3,500+ leases. It is targeting zero-touch invoice automation and uses Power Pages for supplier onboarding."
        ),
        opening=(
            "Offer focused D365 Finance/F&O capacity around AP automation, supplier/Power Pages workflows, acquisition "
            "onboarding, lease accounting, integrations, and the Finance/Manufacturing/Supply Chain roadmap."
        ),
        url="https://www.microsoft.com/en/customers/story/25289-biffa-dynamics-365-finance",
        source="Microsoft Customer Stories",
        why="This is a large, active and measurable D365 operating estate with substantial transaction, supplier, entity and asset complexity.",
        reading="The clearest opening is complementary delivery and optimisation capacity, not incumbent replacement.",
        value="Very strong: named platform, current Microsoft story, operating scale, target automation outcome, and adjacent hiring/roadmap evidence.",
        sheet=(
            "D365 Finance runs Biffa's high-volume finance/procurement estate: 200k-250k invoice lines monthly, £450m "
            "annual spend, 4,500+ suppliers, ~100 entities and 3,500+ leases; it is targeting zero-touch AP. Opportunity: "
            "AP/Power Pages automation, integrations, acquisition onboarding and F&O roadmap capacity."
        ),
        signal_type="d365_finance_high_volume_automation",
        uncertainty=["Current internal and incumbent-partner capacity is not public."],
    ),
    "Charterhouse Holdings": override(
        evidence=(
            "Charterhouse's Xpres ecommerce platform was deeply integrated with D365: ERP upgrades could force the "
            "website offline and peak promotions strained scale. Its AP add-on also lagged D365FO's twice-yearly "
            "updates, while expenses still relied on spreadsheets and paper receipts."
        ),
        opening="Lead with D365FO release compatibility, ecommerce integration resilience, AP automation, testing, and removal of spreadsheet expense workflows.",
        url="https://www.medius.com/resources/case-studies/charterhouse-holdings/",
        source="Medius / Columbus customer case studies",
        why="The evidence identifies concrete recurring release, integration, availability and manual-finance problems rather than a generic installed-base signal.",
        reading="This is a post-remediation optimisation opportunity; confirm what remains after the Columbus and Medius work before proposing scope.",
        value="Strong: named D365FO estate, twice-yearly update pressure, ecommerce downtime exposure, and manual AP/expense processes.",
        sheet=(
            "Charterhouse's D365-integrated ecommerce stack suffered upgrade conflicts and website downtime; its AP "
            "add-on repeatedly lagged twice-yearly D365FO updates, while expenses used spreadsheets/paper. Opportunity: "
            "release testing, integration resilience, AP automation and support."
        ),
        signal_type="d365fo_release_and_ecommerce_integration_pain",
        uncertainty=[
            "Confirm which pain points remain after the published remediation projects."
        ],
    ),
    "Clariness": override(
        evidence=(
            "Clariness implemented Dynamics 365 Sales and Customer Insights - Journeys for lead/opportunity management, "
            "campaign execution and sales/marketing coordination. It is Germany-headquartered but has a UK office and "
            "delivers patient-recruitment services internationally."
        ),
        opening="Keep as a watchlist: approach only with a concrete UK-owned CRM, campaign, data-quality or managed-support need.",
        url="https://www.intelegain.com/a-german-pharma-companys-digital-transformation-with-microsoft-dynamics-365/",
        source="Intelegain case study and Clariness company site",
        why="The D365 workload is specific, but the account's UK commercial ownership and current change pressure are not established.",
        reading="Useful installed-base intelligence, not a strong immediate UK/Ireland outreach signal.",
        value="Moderate: named Sales/Journeys processes, but weak current urgency and a cross-border qualification caveat.",
        sheet=(
            "Clariness uses D365 Sales and Customer Insights - Journeys for lead/opportunity management and campaigns. "
            "It has a UK office but is Germany-headquartered; keep as a watchlist until a UK-owned CRM, data or support "
            "need is confirmed."
        ),
        signal_type="d365_sales_customer_insights_installed_base",
        status="watchlist",
        uncertainty=[
            "UK ownership of the D365 estate and current demand are unverified."
        ],
    ),
    "Colorlites / THF Group": override(
        evidence=(
            "Colorlites, a UK glass-packaging manufacturer within THF Group, implemented Dynamics 365 Business Central "
            "for a high-stock-line manufacturing/distribution operation with bespoke coating and printing services; "
            "the project aimed to streamline workflows, reduce errors/costs and improve service and insight."
        ),
        opening="Offer Business Central optimisation around inventory, production/distribution workflows, extensions, reporting and integration support.",
        url="https://dynamics-consultants.co.uk/media/4ecjfaor/colorlites-case-study-distribution.pdf",
        source="Dynamics Consultants Colorlites case study",
        why="The evidence ties Business Central to a specific mixed manufacturing/distribution operating model with custom services and extensive inventory.",
        reading="Treat Colorlites as the operating company and THF Group as ownership context; do not merge the identities.",
        value="Strong workflow fit; urgency is not established, but extension/integration and stock/production complexity create plausible support demand.",
        sheet=(
            "Colorlites (part of THF Group) implemented Business Central for a large-stock-line glass packaging business "
            "with bespoke coating/printing. Opportunity: inventory, manufacturing/distribution workflows, extensions, "
            "reporting and integration support."
        ),
        signal_type="business_central_manufacturing_distribution",
        uncertainty=["Current backlog and partner scope are not public."],
    ),
    "Hadley Group": override(
        evidence=(
            "Hadley's CRM programme had stalled during its third implementation attempt. A rescue integrated Dynamics "
            "CRM with legacy Baan ERP and ClickDimensions, then reached go-live—including a Dynamics upgrade—within "
            "four months, supporting shared sales-pipeline visibility and mobile CRM use."
        ),
        opening="Use the rescue history to propose a current-state CRM health check, integration review, upgrade path and adoption/backlog support—not another rescue claim.",
        url="https://xpedition.co.uk/case-study/hadley-group-case-study/",
        source="Xpedition Hadley Group case study",
        why="The case exposes complex ERP/marketing integration and past delivery failure, but it is historical rather than evidence of a current crisis.",
        reading="A maturity and modernisation conversation is defensible; presenting the old failure as current would not be.",
        value="Strong technical history and concrete four-month recovery; current urgency remains unknown.",
        sheet=(
            "Hadley's third CRM attempt had stalled; the rescue integrated Dynamics CRM with Baan ERP and ClickDimensions "
            "and reached go-live, including an upgrade, in four months. Opportunity: current-state health check, integration/upgrade review and backlog support."
        ),
        signal_type="historical_dynamics_crm_rescue_and_integration",
        uncertainty=[
            "The rescue is historical; current platform version, partner and pain points are not public."
        ],
    ),
    "Kepak Group": override(
        evidence=(
            "Kepak entered a two-year Dynamics 365 programme covering finance, stock management, production and sales "
            "across 13 Ireland/UK manufacturing facilities, alongside Fabric analytics. A Senior D365 F&O role is tasked "
            "with primary support and functionality enhancements for the group and Meat Division Ireland."
        ),
        opening="Offer F&O rollout/BAU capacity across finance, stock, production and sales, plus Fabric integration, enhancement backlog and release support.",
        url="https://www.kepak.com/kepak-group-and-nexer-in-strategic-partnership-to-support-innovation/",
        source="Kepak / Microsoft / current role evidence",
        why="This combines programme duration, 13-site scale, named workflows, analytics integration and an explicit support/enhancement role.",
        reading="Position 1BT as surge or specialist capacity alongside Kepak and Nexer rather than a replacement partner.",
        value="Very strong: active multi-site rollout plus direct evidence of BAU and change capacity needs.",
        sheet=(
            "Kepak's two-year D365 programme spans finance, stock, production and sales across 13 Ireland/UK plants, with "
            "Fabric analytics; a Senior D365 F&O role owns primary support and enhancements. Opportunity: rollout/BAU "
            "augmentation, Fabric integration and backlog capacity."
        ),
        signal_type="active_d365_fo_multisite_rollout_and_support_hiring",
        uncertainty=["Exact open backlog and external capacity budget are not public."],
    ),
    "Simply Dynamics 365": override(
        evidence=(
            "Simply Dynamics is an Irish D365 partner citing 18+ years and 100+ projects. Its careers page lists full-time "
            "Dynamics 365 Consultant, Business Central Senior Consultant and Business Central Support Consultant roles."
        ),
        opening="Treat as a partner-capacity/channel opportunity: offer vetted overflow delivery or specialist augmentation for BC/CRM projects and support queues.",
        url="https://www.simplydynamics.com/about-us-simply-dynamics-365-ireland/careers-portal-for-dynamics-365-experts/",
        source="Simply Dynamics careers and company pages",
        why="Multiple specialist vacancies are a direct capacity signal, but the company is a delivery partner rather than an end-customer buyer.",
        reading="A partnership/overflow conversation is appropriate; an end-customer managed-service pitch is not.",
        value="Strong partner-capacity signal with named roles and substantial D365 delivery history.",
        sheet=(
            "Irish D365 partner Simply Dynamics cites 18+ years/100+ projects and lists full-time D365 Consultant, BC "
            "Senior Consultant and BC Support Consultant roles. Opportunity: partner overflow/specialist augmentation—not an end-customer pitch."
        ),
        signal_type="d365_partner_capacity_hiring",
        status="partner_capacity",
        uncertainty=[
            "Confirm vacancies remain open and whether external subcontract capacity is acceptable."
        ],
    ),
    "Synergy Technology": override(
        evidence=(
            "Synergy is a UK Microsoft Solutions Partner delivering Business Central implementation, migration, "
            "integration, training and support. Its Microsoft Marketplace offer packages a six-working-day BC setup "
            "with data preparation, configuration/import troubleshooting and two days of onsite training for £5,000."
        ),
        opening="Treat as a partner/channel prospect: explore overflow BC implementation, migration, integration or support capacity that complements its packaged delivery model.",
        url="https://marketplace.microsoft.com/en-gb/product/synergy_technology.consulting_service_started_6_days",
        source="Microsoft Marketplace / Synergy Technology",
        why="The public evidence defines an exact delivery model and service scope, but does not establish that Synergy currently lacks capacity.",
        reading="Useful for a targeted partner conversation; not evidence of an end-customer D365 buying need.",
        value="Moderate: precise service offer and UK delivery footprint, but no live hiring or backlog signal.",
        sheet=(
            "UK Microsoft partner Synergy sells a £5,000 six-day BC setup covering data prep, configuration/import and "
            "training, plus migration/integration/support services. Opportunity: overflow delivery partnership; no public capacity shortage is yet proven."
        ),
        signal_type="business_central_partner_delivery_model",
        status="partner_channel",
        uncertainty=["No current hiring, backlog or subcontracting need was found."],
    ),
    "The Royal Society / Subscribe360": override(
        evidence=(
            "The Royal Society replaced three separate membership, fundraising and events systems with Subscribe360, "
            "a Dynamics 365/Power Platform solution. The pilot put about 100 users on Fundraising and Subscription apps; "
            "Events went live in 2021 with portal booking, automated renewals, ClickDimensions and a unified Fellow view."
        ),
        opening="Explore platform modernisation, renewals/events automation, portal experience, reporting, data quality and managed enhancement support.",
        url="https://www.kickict.co.uk/media/lhgdjice/the-royal-society-kick-case-studies.pdf",
        source="Kick ICT / Subscribe360 Royal Society case study",
        why="The evidence names users, applications, integrations, migration and operating workflows; the main caveat is age rather than vagueness.",
        reading="A maturity/continuous-improvement pitch is defensible, but not an implementation-rescue pitch.",
        value="Strong installed-base detail; current change pressure is unverified.",
        sheet=(
            "The Royal Society unified three systems on Dynamics 365/Power Platform Subscribe360: ~100 pilot users, "
            "Fundraising/Subscription apps, automated renewals, ClickDimensions and an events portal live since 2021. "
            "Opportunity: portal, reporting, data and enhancement support."
        ),
        signal_type="d365_membership_fundraising_events_platform",
        uncertainty=[
            "The implementation milestones are historical; current backlog and partner scope are not public."
        ],
    ),
    "Tourism NI": override(
        evidence=(
            "Tourism NI moved from multiple legacy systems to Dynamics 365 Customer Engagement and a Microsoft cloud "
            "roadmap, then expanded into D365 Finance & Operations and Talent plus Azure migration. The programme created "
            "a single customer view, integrated core processes and continued into further projects with Codec."
        ),
        opening="Offer incremental D365/Azure integration, reporting, release, data-quality and managed enhancement capacity across the multi-product estate.",
        url="https://www.codec.uk/client-success-stories/tourism-northern-ireland",
        source="Codec Tourism Northern Ireland client story",
        why="This is a multi-product public-sector estate with legacy replacement, integration and continuing-project evidence.",
        reading="The strongest angle is complementary improvement capacity around a mature platform, not a new implementation.",
        value="Strong platform breadth and operating-process evidence; current project scope is not public.",
        sheet=(
            "Tourism NI moved from multiple legacy systems to D365 Customer Engagement, then expanded to F&O, Talent "
            "and Azure, creating a single customer view and integrated processes. Opportunity: cross-product integration, "
            "reporting, data quality and managed enhancements."
        ),
        signal_type="multi_product_d365_and_azure_transformation",
        uncertainty=[
            "Current active project backlog and procurement route are not public."
        ],
    ),
    "UK defence apparel manufacturer (unnamed in source)": override(
        evidence=(
            "A Dynamics Square case-study listing says an unnamed UK defence-apparel manufacturer improved efficiency "
            "and accuracy by up to 50% after implementing Dynamics 365 Business Central online. The end-customer name is "
            "still withheld, so the record cannot yet be matched to an outreach account."
        ),
        opening="Do not route for outreach. First resolve the end-customer identity from a named public source; only then assess BC support or optimisation potential.",
        url="https://www.dynamicssquare.co.uk/case-studies/",
        source="Dynamics Square UK case-study listing",
        why="The quantified outcome is useful market intelligence, but an unnamed account is not an actionable lead.",
        reading="Retain as an identity-resolution item rather than allowing a generic manufacturer record into outreach.",
        value="Quantified technical evidence but zero routing value until identity is resolved.",
        sheet=(
            "Unnamed UK defence-apparel manufacturer reportedly gained up to 50% efficiency/accuracy with Business "
            "Central Online. Not actionable: the source withholds the company name; resolve identity before any outreach "
            "or account-level claim."
        ),
        signal_type="business_central_quantified_outcome_identity_unresolved",
        status="identity_unresolved",
        uncertainty=["End-customer identity is unresolved; do not infer or guess it."],
    ),
    "Uniphar Medtech": override(
        evidence=(
            "Uniphar is recruiting a full-time Dynamics 365 Business Central ERP Support Specialist. The role covers "
            "BAU incident resolution, change design/delivery, testing and releases, permissions/security, vendor "
            "coordination, documentation, training, audit evidence, performance monitoring and service-cost inputs."
        ),
        opening="Offer Business Central support/change augmentation to absorb BAU, enhancements, release/testing work, vendor escalations, documentation and optimisation backlog.",
        url="https://uniphar.wd3.myworkdayjobs.com/en-US/uniphar_external_careers/job/Dynamics-365-Business-Central-ERP-Support-Specialist_JR-0000007389",
        source="Uniphar Workday careers",
        why="This is an unusually explicit current statement of internal BC operational load and change responsibilities.",
        reading="A flexible augmentation pitch can map directly to the advertised workload without claiming the team is failing.",
        value="Very strong: current first-party vacancy with detailed BAU, change, governance, vendor and optimisation scope.",
        sheet=(
            "Uniphar is hiring a BC ERP Support Specialist for BAU incidents, change design/delivery, testing/releases, "
            "permissions, vendor coordination, training, audit evidence and optimisation. Opportunity: immediate BC "
            "support/change augmentation against this explicit workload."
        ),
        signal_type="active_business_central_support_and_change_hiring",
        uncertainty=[
            "Confirm the vacancy remains open and whether external augmentation is permitted."
        ],
    ),
    "Willmott Dixon": override(
        evidence=(
            "Willmott Dixon replaced business-critical systems nearing end of support with Dynamics 365 Sales and "
            "Finance. It automated payment proposals, bank reconciliation and customer statements, integrated existing "
            "applications, and simplified financial data retrieval and reporting."
        ),
        opening="Offer D365 Finance/Sales optimisation around financial automation, integrations, reporting, release support and developer backlog.",
        url="https://www.microsoft.com/en/customers/story/24555-willmott-dixon-dynamics-365-finance",
        source="Microsoft Customer Stories",
        why="The evidence names the replacement trigger, exact applications and specific automated finance workflows.",
        reading="A post-implementation optimisation and backlog conversation is stronger than a generic support pitch.",
        value="Strong named workflow evidence from Microsoft; current external-capacity demand is unverified.",
        sheet=(
            "Willmott Dixon replaced systems nearing end of support with D365 Sales/Finance, automating payment proposals, "
            "bank reconciliation and statements while integrating existing apps. Opportunity: finance automation, "
            "integration, reporting and developer backlog support."
        ),
        signal_type="d365_sales_finance_end_of_support_replacement",
        uncertainty=[
            "Current backlog, team capacity and partner scope are not public."
        ],
    ),
    "TalkTalk Group": override(
        evidence=(
            "TalkTalk replaced AX 2012 with Dynamics 365 Finance. It processes about 2,000 supplier invoices monthly "
            "through Medius touchless AP, imports customer/product-level billing data for analysis, and projects a further "
            "£250,000 annual audit-cost saving from improved data capabilities."
        ),
        opening="Offer D365 Finance optimisation around AP exceptions, period close, billing-data integration, controls, reporting and automation backlog.",
        url="https://www.microsoft.com/en/customers/story/23266-talktalk-dynamics-365-finance/",
        source="Microsoft Customer Stories",
        why="The signal has measurable invoice volume, named integration/automation processes and a quantified audit outcome.",
        reading="This is a mature finance-automation estate where specialised optimisation and integration support are more credible than replacement messaging.",
        value="Very strong operating-scale and value evidence from Microsoft.",
        sheet=(
            "TalkTalk moved AX 2012 to D365 Finance; Medius handles ~2,000 supplier invoices monthly with touchless AP, and "
            "better data is projected to save another £250k/year in audit costs. Opportunity: AP exceptions, close, "
            "billing integration and reporting optimisation."
        ),
        signal_type="d365_finance_touchless_ap_and_audit_savings",
        uncertainty=[
            "Current enhancement backlog and external support demand are not public."
        ],
    ),
}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", type=Path, default=DEFAULT_BASE)
    p.add_argument("--refresh", type=Path, default=DEFAULT_REFRESH)
    p.add_argument("--output-prefix", type=Path, default=DEFAULT_PREFIX)
    p.add_argument("--crm-profile", type=Path, default=DEFAULT_CRM_PROFILE)
    p.add_argument(
        "--refresh-crm-profiles",
        action="store_true",
        help="Read current company profiles from Firestore instead of the saved Evidence snapshot.",
    )
    p.add_argument("--crm-project", default=CRM_PROJECT)
    p.add_argument("--crm-database", default=CRM_DATABASE)
    p.add_argument("--crm-workspace", default=CRM_WORKSPACE)
    return p


def now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def evidence_path(path: str | Path, *, label: str) -> Path:
    """Resolve a read or write target and require it to remain under Evidence."""
    resolved = Path(path).resolve()
    try:
        resolved.relative_to(EVIDENCE_ROOT)
    except ValueError as exc:
        raise RuntimeError(
            f"{label} must stay within {EVIDENCE_ROOT}: {resolved}"
        ) from exc
    return resolved


def safe_public_url(value: Any) -> str | None:
    url = str(value or "").strip()
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host:
        return None
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".test"):
        return None
    if host == "vertexaisearch.cloud.google.com" and parsed.path.startswith(
        "/grounding-api-redirect/"
    ):
        return None
    return url


def normalized_fetched_at(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    parsed: datetime
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(raw, "%d/%m/%Y %H:%M:%S").replace(tzinfo=UTC)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _clean_excerpt(value: Any, *, limit: int = 4_000) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit].rstrip()


def refresh_evidence(refresh: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(refresh, dict):
        return None
    source = refresh.get("best_live_source")
    if not isinstance(source, dict):
        return None
    if source.get("verified_live") is not True:
        return None
    if source.get("source_fetch_status") != "fetched":
        return None
    url = safe_public_url(source.get("final_url"))
    excerpt = _clean_excerpt(source.get("text_excerpt") or source.get("snippet"))
    fetched_at = normalized_fetched_at(source.get("fetched_at"))
    if not url or not excerpt or not fetched_at:
        return None
    source_name = str(source.get("title") or urlparse(url).netloc).strip()
    if not source_name:
        return None
    return {
        "evidence_url": url,
        "evidence_excerpt": excerpt,
        "source_name": source_name,
        "fetched_at": fetched_at,
        "verified_live": True,
        "direct_public_source": True,
        "source_channel": "public_web",
        "evidence_proof": "targeted_live_refresh",
    }


def base_evidence(base: dict[str, Any]) -> dict[str, Any] | None:
    if (
        base.get("verified_live") is not True
        or base.get("direct_public_source") is not True
    ):
        return None
    url = safe_public_url(base.get("evidence_url"))
    excerpt = _clean_excerpt(
        base.get("evidence_excerpt") or base.get("specific_evidence")
    )
    source_name = str(base.get("source_name") or "").strip()
    fetched_at = normalized_fetched_at(
        base.get("fetched_at") or base.get("evidence_date")
    )
    if not url or not excerpt or not source_name or not fetched_at:
        return None
    return {
        "evidence_url": url,
        "evidence_excerpt": excerpt,
        "source_name": source_name,
        "fetched_at": fetched_at,
        "verified_live": True,
        "direct_public_source": True,
        "source_channel": "public_web",
        "evidence_proof": "verified_base_record",
    }


def evidence_proof(
    base: dict[str, Any], refresh: dict[str, Any] | None
) -> dict[str, Any]:
    proof = refresh_evidence(refresh) or base_evidence(base)
    if proof:
        return proof
    name = str(base.get("canonical_company_name") or "<unknown>")
    raise RuntimeError(
        f"{name} has no validated direct public evidence in either the refresh or base record."
    )


def load_crm_profiles(
    project: str, database: str, workspace: str
) -> dict[str, dict[str, Any]]:
    from google.cloud import firestore

    client = firestore.Client(project=project, database=database)
    docs = list(
        client.collection("workspaces")
        .document(workspace)
        .collection("companies")
        .stream()
    )
    profiles = {}
    for doc in docs:
        row = doc.to_dict() or {}
        name = str(row.get("name") or "")
        if name:
            profiles[name] = {
                "id": doc.id,
                "country": str(row.get("country") or ""),
                "sector": str(row.get("sector") or ""),
                "version": int(row.get("version") or 0),
                "had_intel_before": bool(row.get("intel")),
            }
    return profiles


def load_crm_profile_snapshot(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    profiles = payload.get("profiles")
    if not isinstance(profiles, dict):
        raise RuntimeError("CRM profile snapshot must contain a profiles object.")
    normalized: dict[str, dict[str, Any]] = {}
    for name, value in profiles.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(value, dict):
            raise RuntimeError(
                "CRM profile snapshot contains a malformed company profile."
            )
        normalized[name] = dict(value)
    return normalized


def compact_summary(evidence: str, opening: str, *, limit: int = 560) -> str:
    text = f"{evidence.strip()} Opportunity: {opening.strip()}"
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    shortened = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:")
    return shortened + "…"


def report_metadata(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "round": int(record.get("batch") or 0),
        "title": str(record.get("report_title") or ""),
        "pdfFilename": str(record.get("pdf_filename") or ""),
        "evidencePackFilename": str(record.get("source_pack_filename") or ""),
        "leadCount": {1: 14, 2: 12, 3: 12, 4: 12, 5: 20}.get(
            int(record.get("batch") or 0), 0
        ),
    }


def merge_record(
    base: dict[str, Any],
    profile: dict[str, Any],
    refresh: dict[str, Any] | None,
) -> dict[str, Any]:
    name = str(base["canonical_company_name"])
    record = dict(base)
    record.update(INTEL_OVERRIDES.get(name, {}))
    record.update(evidence_proof(base, refresh))
    record["country"] = (
        str(base.get("country") or "")
        or str(profile.get("country") or "")
        or COUNTRY_FALLBACKS.get(name, "")
    )
    record["sector"] = str(base.get("sector") or "") or str(profile.get("sector") or "")
    record["board_relevance"] = str(
        record.get("board_relevance") or record.get("why_this_matters_to_1bt") or ""
    )
    contact_roles = [
        str(role).strip()
        for role in record.get("contact_target_roles") or []
        if str(role).strip()
    ]
    record["contact_target_roles"] = contact_roles or [
        "CIO",
        "IT Director",
        "Head of Business Systems",
        "ERP/CRM Manager",
    ]
    record["opportunity_status"] = str(
        record.get("opportunity_status") or "actionable_hypothesis"
    )
    record["do_not_claim_notes"] = list(
        dict.fromkeys(
            [
                *[str(item) for item in record.get("do_not_claim_notes") or []],
                *STANDARD_DO_NOT_CLAIM,
            ]
        )
    )
    if name in INTEL_OVERRIDES:
        record["sheet_summary"] = str(record["sheet_summary"])
    else:
        record["sheet_summary"] = compact_summary(
            str(record.get("specific_evidence") or ""),
            str(record.get("commercial_opening") or ""),
        )
    record["report"] = report_metadata(record)
    record["crm_document_id"] = profile.get("id")
    record["crm_version_before"] = profile.get("version")
    record["crm_had_intel_before"] = profile.get("had_intel_before")
    record["refresh_run_id"] = refresh.get("run_id") if refresh else None
    record["refresh_query"] = refresh.get("query") if refresh else None
    record["refresh_source_count"] = (
        len(refresh.get("live_sources") or []) if refresh else 0
    )
    record["needs_adk_refresh"] = False
    record["refresh_reasons"] = []
    return record


def crm_lead(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "company_name": record["canonical_company_name"],
        "country": record["country"],
        "sector": record["sector"],
        "signal_type": record["signal_type"],
        "signal_strength": record["signal_strength"],
        "opportunity_status": record["opportunity_status"],
        "opportunity_signal": record["specific_evidence"],
        "specific_evidence": record["specific_evidence"],
        "why_this_matters_to_1bt": record["why_this_matters_to_1bt"],
        "commercial_opening": record["commercial_opening"],
        "value_of_signal": record["value_of_signal"],
        "intelligence_reading": record["intelligence_reading"],
        "board_relevance": record["board_relevance"],
        "contact_target_roles": record["contact_target_roles"],
        "remaining_uncertainty": record["remaining_uncertainty"],
        "do_not_claim_notes": record["do_not_claim_notes"],
        "evidence_url": record["evidence_url"],
        "evidence_excerpt": record["evidence_excerpt"],
        "source_name": record["source_name"],
        "fetched_at": record["fetched_at"],
        "verified_live": record["verified_live"],
        "direct_public_source": record["direct_public_source"],
        "source_channel": record["source_channel"],
        "sheet_summary": record["sheet_summary"],
        "report": record["report"],
    }


def validate(records: list[dict[str, Any]], profiles: dict[str, Any]) -> None:
    if (
        len(records) != 70
        or len({row["canonical_company_name"] for row in records}) != 70
    ):
        raise RuntimeError(
            "Final intelligence must contain exactly 70 unique companies."
        )
    names = [row["canonical_company_name"] for row in records]
    if set(names) != set(profiles) or len(profiles) != 70:
        raise RuntimeError(
            "Final company identities do not exactly match the 70-company Northwind workspace."
        )
    batch_counts = Counter(int(row.get("batch") or 0) for row in records)
    if batch_counts != Counter({1: 14, 2: 12, 3: 12, 4: 12, 5: 20}):
        raise RuntimeError(
            f"Unexpected five-PDF batch distribution: {dict(batch_counts)}"
        )
    required = (
        "country",
        "sector",
        "signal_type",
        "signal_strength",
        "opportunity_status",
        "specific_evidence",
        "why_this_matters_to_1bt",
        "commercial_opening",
        "value_of_signal",
        "intelligence_reading",
        "board_relevance",
        "contact_target_roles",
        "remaining_uncertainty",
        "do_not_claim_notes",
        "evidence_url",
        "evidence_excerpt",
        "source_name",
        "fetched_at",
        "sheet_summary",
        "pdf_filename",
        "report",
    )
    vague_fragments = (
        "supporting evidence is retained",
        "reference the public microsoft/d365 signal",
        "offer practical support, but keep it provisional",
    )
    for row in records:
        allow_empty = {"remaining_uncertainty"}
        missing = [
            key
            for key in required
            if key not in row or (key not in allow_empty and not row.get(key))
        ]
        if missing:
            raise RuntimeError(f"{row['canonical_company_name']} is missing {missing}.")
        if not str(row["evidence_url"]).startswith(("https://", "http://")):
            raise RuntimeError(
                f"{row['canonical_company_name']} has an unsafe evidence URL."
            )
        if safe_public_url(row["evidence_url"]) is None:
            raise RuntimeError(
                f"{row['canonical_company_name']} has a non-public evidence URL."
            )
        if row.get("verified_live") is not True:
            raise RuntimeError(
                f"{row['canonical_company_name']} is not backed by verified live evidence."
            )
        if row.get("direct_public_source") is not True:
            raise RuntimeError(
                f"{row['canonical_company_name']} is not backed by a direct public source."
            )
        if row.get("source_channel") != "public_web":
            raise RuntimeError(
                f"{row['canonical_company_name']} has an invalid source channel."
            )
        if normalized_fetched_at(row["fetched_at"]) != row["fetched_at"]:
            raise RuntimeError(
                f"{row['canonical_company_name']} has a malformed evidence timestamp."
            )
        if any(
            fragment in row["sheet_summary"].lower() for fragment in vague_fragments
        ):
            raise RuntimeError(
                f"{row['canonical_company_name']} still has a vague sheet summary."
            )
        if len(row["sheet_summary"]) > 700:
            raise RuntimeError(
                f"{row['canonical_company_name']} sheet summary is too long."
            )


def render_markdown(records: list[dict[str, Any]], generated_at: str) -> str:
    lines = [
        "# UK & Ireland D365 — 70-Company Opportunity Intelligence",
        "",
        f"Generated: {generated_at}",
        "",
        "This crosswalk consolidates the five completed PDF batches. Each account separates the public fact from the "
        "commercial hypothesis; uncertainty is retained instead of being converted into a sales claim.",
        "",
    ]
    for index, row in enumerate(records, start=1):
        lines.extend(
            [
                f"## {index}. {row['canonical_company_name']}",
                "",
                f"- Specific public evidence: {row['specific_evidence']}",
                f"- Practical 1BT opening: {row['commercial_opening']}",
                f"- Interpretation: {row['intelligence_reading']}",
                f"- Status: {row['opportunity_status']}",
                f"- Source: {row['source_name']} — {row['evidence_url']}",
                f"- Uncertainty: {'; '.join(row['remaining_uncertainty']) or 'No additional material caveat recorded.'}",
                f"- PDF: {row['pdf_filename']}",
                "",
            ]
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    base_path = evidence_path(args.base, label="Base intelligence artifact")
    refresh_path = evidence_path(args.refresh, label="Refresh artifact")
    prefix = evidence_path(args.output_prefix, label="Output prefix")
    crm_profile_path = evidence_path(args.crm_profile, label="CRM profile snapshot")
    base_payload = json.loads(base_path.read_text(encoding="utf-8"))
    refresh_payload = json.loads(refresh_path.read_text(encoding="utf-8"))
    if args.refresh_crm_profiles:
        profiles = load_crm_profiles(
            args.crm_project, args.crm_database, args.crm_workspace
        )
        profile_source = "live_firestore"
    else:
        profiles = load_crm_profile_snapshot(crm_profile_path)
        profile_source = str(crm_profile_path)
    refresh_rows = refresh_payload.get("companies") or []
    refresh_names = [
        str(row.get("canonical_company_name") or "") for row in refresh_rows
    ]
    if len(refresh_names) != len(set(refresh_names)):
        raise RuntimeError(
            "Refresh artifact contains duplicate canonical company names."
        )
    refresh_by_name = dict(zip(refresh_names, refresh_rows, strict=True))
    generated_at = now_utc()
    records = [
        merge_record(
            row,
            profiles.get(row["canonical_company_name"], {}),
            refresh_by_name.get(row["canonical_company_name"]),
        )
        for row in base_payload.get("companies") or []
    ]
    validate(records, profiles)

    prefix.parent.mkdir(parents=True, exist_ok=True)
    crosswalk_path = prefix.with_suffix(".json")
    markdown_path = prefix.with_suffix(".md")
    crm_path = prefix.with_name(prefix.name + "_CRM_PACK.json")
    sheet_path = prefix.with_name(prefix.name + "_SHEET_SUMMARIES.json")
    profile_path = prefix.with_name(prefix.name + "_CRM_PROFILE_BEFORE.json")

    crosswalk = {
        "artifact_type": "uk_ie_d365_70_company_intelligence_final",
        "generated_at": generated_at,
        "company_count": 70,
        "pdf_count": 5,
        "source_base": str(base_path),
        "targeted_refresh": str(refresh_path),
        "live_override_count": len(INTEL_OVERRIDES),
        "companies": records,
    }
    crm_pack = {
        "artifact_type": "uk_ie_d365_70_company_northwind_enrichment_pack",
        "generated_at": generated_at,
        "lead_count": 70,
        "leads": [crm_lead(row) for row in records],
    }
    sheet_pack = {
        "artifact_type": "uk_ie_d365_70_company_sheet_summary_pack",
        "generated_at": generated_at,
        "spreadsheet_id": "1nikwNWJ3N5622S_a8l9YQsP_pTLxCLtmezgNmBq4abs",
        "sheet_name": "Warm Paths",
        "target_range": "C309:C378",
        "company_count": 70,
        "rows": [
            {
                "sheet_row": 309 + index,
                "company_name": row["canonical_company_name"],
                "summary": row["sheet_summary"],
            }
            for index, row in enumerate(records)
        ],
    }
    profile_snapshot = {
        "artifact_type": "northwind_70_company_profile_before_intelligence_enrichment",
        "generated_at": generated_at,
        "project": args.crm_project,
        "database": args.crm_database,
        "workspace": args.crm_workspace,
        "profile_source": profile_source,
        "company_count": len(profiles),
        "profiles": profiles,
    }
    crosswalk_path.write_text(
        json.dumps(crosswalk, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(render_markdown(records, generated_at), encoding="utf-8")
    crm_path.write_text(
        json.dumps(crm_pack, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    sheet_path.write_text(
        json.dumps(sheet_pack, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    profile_path.write_text(
        json.dumps(profile_snapshot, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "company_count": len(records),
                "crosswalk": str(crosswalk_path),
                "markdown": str(markdown_path),
                "crm_pack": str(crm_path),
                "sheet_pack": str(sheet_path),
                "profile_snapshot": str(profile_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
