from __future__ import annotations

import html
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

EVIDENCE = Path(r"D:\gaps\Business_Intel\Evidence")
SOURCE_CHECKS = EVIDENCE / "UK_IE_D365_SIGNAL_QUALITY_AUDIT_20260603_SOURCE_CHECKS.json"


def now_iso() -> str:
    tz = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(tz).isoformat(timespec="seconds")


def esc(value: str) -> str:
    return html.escape(value or "", quote=True)


def short_url(url: str) -> str:
    return re.sub(r"^https?://", "", url).rstrip("/")


def badge_class(strength: str) -> str:
    return strength.lower().split()[0]


def detail_field(label: str, body: str) -> str:
    return f"""
      <div class=\"field\">
        <h3>{esc(label)}</h3>
        <p>{esc(body)}</p>
      </div>"""


def load_source_checks() -> dict[str, dict]:
    source_checks = json.loads(SOURCE_CHECKS.read_text(encoding="utf-8"))
    by_name: dict[str, dict] = {}
    for section in ("current_leads", "alternative_candidates"):
        for row in source_checks.get(section, []):
            name = row.get("company_name", "")
            if name:
                by_name[name.lower()] = row
    return by_name


def accounts() -> list[dict]:
    return [
        {
            "rank": 1,
            "account": "Glenveagh",
            "market": "Ireland",
            "sector": "Housebuilding / construction",
            "strength": "Strong Signal",
            "signal_type": "D365 Customer Insights / Customer Service rollout",
            "signal_title": "D365 Customer Insights and Customer Service rollout",
            "source_name": "Storm Technology client story",
            "evidence_url": "https://www.storm.ie/clients/glenveagh-customer-insights/",
            "evidence_summary": "Public client story ties Glenveagh to Dynamics 365 Customer Insights and Customer Service work around customer communications, case resolution, self-service expansion, and process streamlining.",
            "opportunity_signal": "A named Irish homebuilder is publicly connected to a D365 customer-engagement rollout spanning customer communications, service case handling, and process improvement.",
            "why_matters": "This is not a generic Microsoft installed-base marker. It points to a front-office D365 estate where adoption, process design, case taxonomy, reporting, and ongoing optimisation can create visible business value.",
            "commercial_opening": "Open with a value-led customer operations conversation: can 1BT help reduce manual follow-up, improve case routing, tighten communications governance, and make the D365 service journey easier to run after rollout?",
            "value_signal": "Strong because it combines named account, named D365 modules, customer-facing operations, rollout/self-service language, and a business process outcome that 1BT can credibly support.",
            "intelligence_reading": "Best treated as an optimisation and adoption signal. The likely pitch is not 'replace your partner'; it is 'we help D365 customer-service teams extract more value and reduce operational friction'.",
            "board_relevance": "A high-quality Irish private-sector signal in a D365 customer-experience lane, useful for board discussion because it maps directly to measurable customer service and communications outcomes.",
            "do_not_claim": "Do not claim current dissatisfaction, budget, or partner displacement. Verify incumbent relationship and current ownership before outreach.",
            "caveat": "Installed-base/rollout signal; validate current support ownership.",
        },
        {
            "rank": 2,
            "account": "Mental Health Commission Ireland",
            "market": "Ireland",
            "sector": "Public sector / health regulation",
            "strength": "Strong Signal",
            "signal_type": "Dynamics 365 + Power Pages public-service portal",
            "signal_title": "Dynamics 365 and Power Pages portal replacing legacy processes",
            "source_name": "Codec Ireland client-success story",
            "evidence_url": "https://www.codec.ie/client-success-stories/mental-health-commission-irl",
            "evidence_summary": "Codec's public story names the Mental Health Commission / DSS and describes Dynamics 365 plus Power Pages architecture, portal implementation, legacy paper-process replacement, and Dec 2025 operating metrics.",
            "opportunity_signal": "A live public-sector digital-service platform using Dynamics 365 and Power Pages, with explicit legacy-process replacement and operational metrics.",
            "why_matters": "Portal-led D365 programmes usually create ongoing needs around support, performance, forms, user journeys, data quality, workflow changes, and reporting as volumes grow.",
            "commercial_opening": "Position 1BT around managed improvement for Dynamics 365 and Power Pages: intake workflow optimisation, service analytics, citizen/user experience fixes, backlog clearance, and low-risk enhancement capacity.",
            "value_signal": "Strong because it is current, public, named, module-specific, and anchored in a measurable operating platform rather than a vague transformation claim.",
            "intelligence_reading": "The sales angle should be careful and public-sector appropriate: advisory/support capability around a live Microsoft business-app platform, not a procurement shortcut.",
            "board_relevance": "A strong Irish public-service signal showing D365 as core operating infrastructure, relevant to board-level conversations about compliance, service delivery, and scalable digital operations.",
            "do_not_claim": "Do not frame this as a tender lead or imply procurement intent. Do not claim access to non-public operating metrics beyond what the public story states.",
            "caveat": "Public-sector route caution applies; treat as a support and optimisation hypothesis.",
        },
        {
            "rank": 3,
            "account": "Weetabix Food Company",
            "market": "United Kingdom",
            "sector": "Food manufacturing",
            "strength": "Strong Signal",
            "signal_type": "D365 ERP implementation / rescue-style history",
            "signal_title": "D365 ERP implementation with struggle and recovery signals",
            "source_name": "Nine Feet Tall case study",
            "evidence_url": "https://www.ninefeettall.com/case-studies/weetabix/",
            "evidence_summary": "Public case-study evidence connects Weetabix to a Dynamics 365 ERP implementation story, with search/audit evidence indicating implementation struggles, delays, and rescue-style support context.",
            "opportunity_signal": "A named UK manufacturer with public D365 ERP implementation history and evidence of delivery friction, delay, or recovery support.",
            "why_matters": "ERP programmes that have needed recovery support often create post-go-live demand for stabilisation, reporting clean-up, process backlog, training refresh, and enhancement delivery.",
            "commercial_opening": "Approach with a non-invasive ERP health-check offer: identify D365 process bottlenecks, support backlog, reporting gaps, and practical quick wins in finance, operations, and manufacturing-adjacent workflows.",
            "value_signal": "Strong because it is closer to an opportunity trigger than a pure case study: the public signal is about an implementation journey where execution quality and recovery capability matter.",
            "intelligence_reading": "This is one of the clearest sales-pitch accounts, but the language must stay evidence-led. The strongest pitch is resilience and post-implementation value, not criticism of the programme.",
            "board_relevance": "Board-relevant because ERP disruption in food manufacturing affects service levels, cost control, operational visibility, and confidence in transformation delivery.",
            "do_not_claim": "Do not claim current pain or unresolved failure. Treat the public evidence as historical implementation-friction signal unless refreshed by direct discovery.",
            "caveat": "Project-history signal; verify current D365 state before outreach.",
        },
        {
            "rank": 4,
            "account": "Net Zero Group Ireland",
            "market": "Ireland",
            "sector": "Construction / energy services",
            "strength": "Strong Signal",
            "signal_type": "Business Central + 4PS rollout",
            "signal_title": "Business Central and 4PS rollout across finance and project controls",
            "source_name": "BPF Consulting case-studies page",
            "evidence_url": "https://bpf.ie/case-studies/",
            "evidence_summary": "BPF's public case-study page names Net Zero Group Ireland and describes Dynamics 365 Business Central plus 4PS, structured rollout, financial controls, project revenue/cost management, reporting, training, and change management.",
            "opportunity_signal": "An Irish group with a Business Central and 4PS rollout touching finance, project controls, reporting, training, and change management.",
            "why_matters": "That footprint creates exactly the kind of practical post-rollout needs 1BT can support: process adoption, reporting confidence, project-cost visibility, and operational change management.",
            "commercial_opening": "Lead with a construction/project-controls optimisation offer: improve Business Central reporting, reduce month-end/project-cost friction, and support finance teams through adoption after rollout.",
            "value_signal": "Strong because it names account, platform, vertical add-on, finance/project process areas, training, and change management. That is a rich sales-relevance cluster.",
            "intelligence_reading": "This is a clean replacement-grade signal from the audit. It is especially useful for positioning 1BT as pragmatic support around Business Central in project-centric organisations.",
            "board_relevance": "Board-relevant because project controls, revenue/cost visibility, and reporting reliability are operating-governance issues, not only IT configuration topics.",
            "do_not_claim": "Do not claim the rollout is failing or that the incumbent cannot support them. Use the signal as a post-rollout optimisation hypothesis.",
            "caveat": "Partner case-study source; validate current support owner and rollout phase.",
        },
        {
            "rank": 5,
            "account": "Jackson's Bakery",
            "market": "United Kingdom",
            "sector": "Food manufacturing",
            "strength": "Strong Signal",
            "signal_type": "D365 Finance and Supply Chain Management",
            "signal_title": "D365 Finance and Supply Chain Management for core food manufacturing",
            "source_name": "Columbus Global case study",
            "evidence_url": "https://www.columbusglobal.com/insights/cases/jacksons-bakery-scale-up-new-levels-with-microsoft-dynamics-365-finance-and-supply-chain-management/",
            "evidence_summary": "Public Columbus evidence ties Jackson's Bakery to Microsoft Dynamics 365 Finance and Supply Chain Management, modernising core operational processes for a UK food manufacturer/supplier.",
            "opportunity_signal": "A named UK manufacturer using D365 Finance and Supply Chain Management to modernise core food-manufacturing operations.",
            "why_matters": "F&SCM environments usually need ongoing help with process fit, reporting, integrations, training, master data, and supply-chain/finance alignment after go-live.",
            "commercial_opening": "Pitch a focused D365 F&SCM value review: where are finance, production, supply chain, and reporting teams still using workarounds, spreadsheets, or manual reconciliation?",
            "value_signal": "Strong because it is a named F&SCM footprint in a process-heavy manufacturing environment where D365 support has direct operational relevance.",
            "intelligence_reading": "This is more installed-base than active distress, but the module depth and manufacturing context make it highly pitchable for support, optimisation, and enhancement services.",
            "board_relevance": "Board-relevant because manufacturing ERP performance affects supply reliability, cost control, stock visibility, and the ability to scale operations cleanly.",
            "do_not_claim": "Do not claim active buying intent or current dissatisfaction. Use this as a credible installed-base and optimisation signal.",
            "caveat": "Installed-base case study; not an active buying signal by itself.",
        },
        {
            "rank": 6,
            "account": "Littlefish UK Ltd",
            "market": "United Kingdom",
            "sector": "Managed IT services",
            "strength": "Strong Signal",
            "signal_type": "Business Central + Subscription Billing",
            "signal_title": "Business Central and Subscription Billing for recurring support contracts",
            "source_name": "Kick ICT Littlefish case-study PDF",
            "evidence_url": "https://www.kickict.co.uk/media/czmopzgc/littlefish-uk-ltd-case-study.pdf",
            "evidence_summary": "Kick ICT's public PDF describes Littlefish using Dynamics 365 Business Central and Subscription Billing to replace outdated/manual finance processes and manage recurring support-contract billing under growth pressure.",
            "opportunity_signal": "A UK managed-services provider with Business Central plus Subscription Billing around recurring contract billing, manual workload, and finance-process replacement.",
            "why_matters": "Recurring billing is commercially sensitive. Errors, manual handling, and subscription complexity affect cash collection, customer trust, finance productivity, and margin visibility.",
            "commercial_opening": "Open around billing accuracy and finance scalability: can 1BT help improve Business Central subscription billing, reporting, contract-change handling, and support-team finance workflows?",
            "value_signal": "Strong because the signal combines named D365 product, a high-value process problem, manual workload, growth pressure, and a recurring-revenue operating model.",
            "intelligence_reading": "This is one of the most directly pitchable Business Central opportunities because the signal naturally supports a commercial conversation about billing controls and scale.",
            "board_relevance": "Board-relevant because recurring billing reliability affects revenue assurance, cash flow, customer experience, and the scalability of support-contract operations.",
            "do_not_claim": "Do not imply the current system is broken. Position around optimisation, controls, and scaling recurring billing.",
            "caveat": "Partner PDF; confirm current support owner and system state before contact.",
        },
        {
            "rank": 7,
            "account": "London Borough of Harrow",
            "market": "United Kingdom",
            "sector": "Local government",
            "strength": "Promising Signal",
            "signal_type": "D365 F&SCM public-sector transformation",
            "signal_title": "D365 Finance and Supply Chain Management transformation for HR/operations",
            "source_name": "HCLTech case study",
            "evidence_url": "https://www.hcltech.com/case-study/london-borough-of-harrow-tackles-dynamics-365-technology-transformation",
            "evidence_summary": "HCLTech's public case study names Harrow and Dynamics 365 Finance and Supply Chain Management transformation, with support and architecture language around public-sector operations.",
            "opportunity_signal": "A public-sector D365 F&SCM transformation signal connected to HR/operations, architecture, and support language.",
            "why_matters": "Public-sector D365 programmes commonly need low-risk support, data/process clean-up, reporting improvements, and change-management capacity after transformation milestones.",
            "commercial_opening": "Frame 1BT as a careful D365 support and improvement partner for public bodies: reduce support backlog, simplify reporting, and harden operational processes without treating the case study as procurement intent.",
            "value_signal": "Promising because it is a clear D365 F&SCM public case, but the sales path is constrained by public-sector procurement and incumbent relationships.",
            "intelligence_reading": "Use as an installed-base and support hypothesis, not as a tender lead. The strongest outreach should ask about operational outcomes and support load, not replacement.",
            "board_relevance": "Board-relevant because councils care about resilient service operations, value for money, and the risk profile of enterprise-platform change.",
            "do_not_claim": "Do not imply a live procurement opportunity or that tender rules can be bypassed.",
            "caveat": "Public-sector account; treat as support hypothesis, not procurement lead.",
        },
        {
            "rank": 8,
            "account": "Sustainable Energy Authority of Ireland (SEAI)",
            "market": "Ireland",
            "sector": "Public sector / energy",
            "strength": "Promising Signal",
            "signal_type": "D365-backed reporting and compliance workflow",
            "signal_title": "D365-backed reporting and compliance workflow for renewable-energy programmes",
            "source_name": "Codec Ireland client-success story",
            "evidence_url": "https://www.codec.ie/client-success-stories/sustainable-energy-authority-of-ireland",
            "evidence_summary": "Codec's public SEAI story describes Dynamics 365/Azure public-sector work around backend reporting tools, funding timelines, RESS compliance, and monitoring workflows.",
            "opportunity_signal": "An Irish public body using D365-backed tools for reporting, compliance, monitoring, and renewable-energy programme administration.",
            "why_matters": "Programme reporting and compliance workflows create ongoing needs around data quality, workflow changes, dashboarding, audit readiness, and user support.",
            "commercial_opening": "Approach around Microsoft business-app support for compliance workflows: reporting reliability, workflow optimisation, issue triage, and analytics improvements for programme teams.",
            "value_signal": "Promising because the business process is important and public, though the exact D365 module footprint is less explicit than the strongest private-sector cases.",
            "intelligence_reading": "Good as a public-service optimisation hypothesis. Keep the pitch around operational support and reporting maturity rather than procurement or partner displacement.",
            "board_relevance": "Board-relevant because renewable-energy programme governance depends on accurate reporting, compliance, monitoring, and stakeholder confidence.",
            "do_not_claim": "Do not claim specific module ownership beyond the public evidence. Do not frame as a tender lead.",
            "caveat": "Public-sector and module-specificity caveat; still credible for support/optimisation.",
        },
        {
            "rank": 9,
            "account": "Alzheimer's Research UK",
            "market": "United Kingdom",
            "sector": "Charity / non-profit",
            "strength": "Promising Signal",
            "signal_type": "Business Central finance replacement",
            "signal_title": "Business Central replacing legacy finance software",
            "source_name": "Columbus Global Business Central case study",
            "evidence_url": "https://www.columbusglobal.com/partners/microsoft/microsoft-dynamics-365-business-central/alzheimers-research-erp-d365bc/",
            "evidence_summary": "Columbus Global's public case study names Alzheimer's Research UK and Dynamics 365 Business Central as a replacement for legacy finance software, with efficiency and platform-growth language.",
            "opportunity_signal": "A UK charity replacing legacy finance software with Dynamics 365 Business Central to improve efficiency and support growth.",
            "why_matters": "Finance-system replacement produces support needs around user adoption, reporting, approvals, integrations, controls, and the gradual removal of old workarounds.",
            "commercial_opening": "Lead with a charity-finance optimisation conversation: improve Business Central reporting, month-end processes, approvals, and support resilience without increasing internal workload.",
            "value_signal": "Promising because the Business Central and legacy-replacement evidence is clear, though it lacks an active pain or rescue trigger.",
            "intelligence_reading": "This is a clean installed-base opportunity. It is best for a low-pressure support and efficiency pitch rather than a problem-led rescue pitch.",
            "board_relevance": "Board-relevant because charity finance teams need reliable controls, transparent reporting, and efficient systems to support stewardship and growth.",
            "do_not_claim": "Do not claim current finance pain or active buying intent. Treat as installed-base plus optimisation hypothesis.",
            "caveat": "Good installed-base signal; no live pain evidence.",
        },
        {
            "rank": 10,
            "account": "Lewisham Council",
            "market": "United Kingdom",
            "sector": "Local government",
            "strength": "Promising Signal",
            "signal_type": "D365 data migration / technical migration",
            "signal_title": "Dynamics 365 data migration and technical migration case",
            "source_name": "Xpedition case study",
            "evidence_url": "https://xpedition.co.uk/case-study/lewisham-council-seamless-dynamics-365-data-migration-with-synchronicity/",
            "evidence_summary": "Xpedition's public story names Lewisham Council and a seamless Dynamics 365 data migration using Synchronicity, making this a technical D365 migration signal.",
            "opportunity_signal": "A named public-sector Dynamics 365 data-migration case, signalling technical transition work around D365 data movement and platform change.",
            "why_matters": "Data migrations often create follow-on needs: reconciliation, data quality, integration clean-up, user trust in reporting, and support for later phase migrations or enhancements.",
            "commercial_opening": "Position 1BT around D365 migration assurance and post-migration data quality: reconciliation, reporting validation, integration checks, and practical support for future migration phases.",
            "value_signal": "Promising because the D365 migration signal is clear, but narrower than a full operational transformation or direct support-pain signal.",
            "intelligence_reading": "Useful as a technical credibility account. Keep the pitch specific to data quality, assurance, and post-migration improvement rather than broad ERP transformation.",
            "board_relevance": "Board-relevant because migration quality affects operational continuity, audit confidence, user trust, and the credibility of digital transformation work.",
            "do_not_claim": "Do not claim open procurement or ongoing migration difficulty. Treat as a technical migration and assurance hypothesis.",
            "caveat": "Public-sector and migration-only caveat.",
        },
        {
            "rank": 11,
            "account": "Wesleyan",
            "market": "United Kingdom",
            "sector": "Financial services / mutual",
            "strength": "Promising Signal",
            "signal_type": "D365 Finance modernisation",
            "signal_title": "Dynamics 365 Finance modernisation with older timeline caveat",
            "source_name": "KPMG UK case study",
            "evidence_url": "https://kpmg.com/uk/en/insights/transformation/modernising-finance-systems.html",
            "evidence_summary": "KPMG's public UK case study identifies Wesleyan and Dynamics 365 Finance modernisation, with a project timeline that appears older than the strongest current-rollout signals.",
            "opportunity_signal": "A UK financial-services organisation publicly connected to Dynamics 365 Finance modernisation.",
            "why_matters": "Finance modernisation creates enduring needs around controls, reporting, process standardisation, support, and continuous improvement even after the original implementation window.",
            "commercial_opening": "Open with a D365 Finance maturity review: reporting confidence, process automation, month-end friction, controls, and where the finance platform still needs practical enhancement capacity.",
            "value_signal": "Promising but time-caveated. The platform relevance is strong; the why-now signal is weaker than current rollouts or support-pain cases.",
            "intelligence_reading": "Use as a lower-pressure installed-base conversation. It can still be valuable where 1BT wants finance-transformation credibility, but it should not be over-ranked.",
            "board_relevance": "Board-relevant because finance-system maturity affects management reporting, control confidence, audit readiness, and transformation ROI.",
            "do_not_claim": "Do not imply the implementation is current or troubled. State the timeline caveat plainly.",
            "caveat": "Older case-study timeline; weaker why-now signal.",
        },
        {
            "rank": 12,
            "account": "Midland Systems",
            "market": "United Kingdom / Ireland context",
            "sector": "Distribution / ecommerce / road-safety equipment",
            "strength": "Emerging Signal",
            "signal_type": "D365 F&O distribution/ecommerce case",
            "signal_title": "Dynamics 365 F&O implementation for distribution and ecommerce operations",
            "source_name": "AX Software Dynamics 365 case-studies page",
            "evidence_url": "https://www.axsoftware.co.uk/index.php/dynamics-d365-case-studies-implementation-stories/",
            "evidence_summary": "AX Software's public D365 case-study page ties Midland Systems to an end-to-end Dynamics 365 F&O implementation in a UK/Ireland distribution and ecommerce operations context.",
            "opportunity_signal": "A D365 F&O implementation signal in a distribution/ecommerce operating environment, with UK/Ireland relevance.",
            "why_matters": "Distribution operations typically depend on accurate stock, order, finance, ecommerce integration, and fulfilment processes - areas where D365 support can have commercial impact.",
            "commercial_opening": "Offer a D365 F&O operational optimisation conversation around order-to-cash, reporting, ecommerce integration, inventory visibility, and post-implementation support load.",
            "value_signal": "Emerging because the account is named and D365 F&O is relevant, but the evidence sits on a partner case-study page with broad site-level D365 navigation.",
            "intelligence_reading": "Keep this in the pitchable set, but use the Midland-specific evidence only. It is better as a targeted installed-base hypothesis than a top-tier trigger.",
            "board_relevance": "Board-relevant where distribution/ecommerce performance depends on system accuracy, fulfilment reliability, and timely operational reporting.",
            "do_not_claim": "Do not use generic page navigation as evidence. Do not imply current pain or direct buying intent.",
            "caveat": "Partner case-study/source-specificity caveat; use only Midland-specific excerpt.",
        },
        {
            "rank": 13,
            "account": "The Felix Project",
            "market": "United Kingdom",
            "sector": "Charity / food redistribution",
            "strength": "Emerging Signal",
            "signal_type": "D365 volunteer-management enhancement",
            "signal_title": "D365 volunteer-management enhancement with source-stability caveat",
            "source_name": "Mercurius IT case study",
            "evidence_url": "https://www.mercuriusit.com/project/case-study-on-the-felix-project/",
            "evidence_summary": "Mercurius IT evidence connects The Felix Project to Dynamics 365 / volunteer-management enhancement work, though earlier manual source access had stability caveats.",
            "opportunity_signal": "A charity operations signal around Dynamics 365 enhancement for volunteer management and service operations.",
            "why_matters": "Volunteer-management workflows are operationally sensitive: scheduling, communication, availability, reporting, and user adoption all create practical support and enhancement needs.",
            "commercial_opening": "Approach with a non-profit operations support angle: improve D365 volunteer workflows, reduce manual coordination, strengthen reporting, and support ongoing enhancements without disrupting front-line work.",
            "value_signal": "Emerging because the business problem is relevant and D365-adjacent, but source stability and exact module details need caution before direct outreach.",
            "intelligence_reading": "This is pitchable only with caveats. It is useful as a charity-sector Microsoft business-app signal, not as a top-priority contact-now lead.",
            "board_relevance": "Board-relevant because volunteer coordination and reporting affect service capacity, operational resilience, and impact delivery.",
            "do_not_claim": "Do not overstate module details or current system state. Re-check source access and current ownership before outreach.",
            "caveat": "Source-stability/source-cleanup caveat remains.",
        },
        {
            "rank": 14,
            "account": "Colorlites / THF Group",
            "market": "United Kingdom",
            "sector": "Manufacturing / distribution",
            "strength": "Emerging Signal",
            "signal_type": "Business Central distribution/manufacturing workflow",
            "signal_title": "Business Central workflow case with account-name caveat",
            "source_name": "Dynamics Consultants Colorlites case-study PDF",
            "evidence_url": "https://dynamics-consultants.co.uk/media/4ecjfaor/colorlites-case-study-distribution.pdf",
            "evidence_summary": "Dynamics Consultants' public PDF supports a Business Central distribution/manufacturing workflow story for Colorlites, with THF Group/account-name relationship caveat.",
            "opportunity_signal": "A Business Central workflow case in a UK manufacturing/distribution setting, with explicit process, control, and customer-service relevance.",
            "why_matters": "Manufacturing and distribution businesses often need ERP support around stock, order processing, customer service, finance, reporting, and process control as they scale.",
            "commercial_opening": "Pitch a Business Central process-controls review: where are distribution, manufacturing, finance, and customer-service workflows still manual, slow, or under-reported?",
            "value_signal": "Emerging because the Business Central process signal is real, but the account-name/ownership relationship should be tightened before outreach.",
            "intelligence_reading": "Keep this as a provisional pitch option. It is commercially relevant, but not clean enough to rank above the stronger named rollout and support signals.",
            "board_relevance": "Board-relevant because ERP process control in manufacturing/distribution affects stock reliability, service quality, growth readiness, and margin visibility.",
            "do_not_claim": "Do not conflate Colorlites and THF Group without confirming the current legal/account relationship. Do not claim active pain.",
            "caveat": "Account-name relationship caveat; source cleanup needed before outreach.",
        },
    ]


def merge_source_metadata(rows: list[dict], checks_by_name: dict[str, dict]) -> None:
    aliases = {
        "glenveagh": "glenveagh",
        "mental health commission ireland": "mental health commission ireland",
        "weetabix food company": "weetabix food company",
        "net zero group ireland": "net zero group ireland",
        "jackson's bakery": "jackson's bakery",
        "littlefish uk ltd": "littlefish uk ltd",
        "london borough of harrow": "london borough of harrow",
        "sustainable energy authority of ireland (seai)": "sustainable energy authority of ireland (seai)",
        "alzheimer's research uk": "alzheimer's research uk",
        "lewisham council": "lewisham council",
        "wesleyan": "wesleyan",
        "midland systems": "midland systems",
        "the felix project": "the felix project",
        "colorlites / thf group": "colorlites (thf group)",
    }
    for row in rows:
        check = checks_by_name.get(aliases.get(row["account"].lower(), row["account"].lower()), {})
        row["verified_live"] = bool(check and check.get("http_status") == 200 and not check.get("fetch_error"))
        row["checked_at"] = check.get("checked_at") if check else None
        row["http_status"] = check.get("http_status") if check else None
        row["source_final_url"] = check.get("final_url") if check else row["evidence_url"]
        row["d365_terms_found"] = check.get("d365_terms_found") if check else []
        row["strong_signal_terms_found"] = check.get("strong_signal_terms_found") if check else []
        live_excerpt = (check.get("evidence_excerpt_live") or "").strip() if check else ""
        row["evidence_excerpt"] = live_excerpt[:850] if live_excerpt else row["evidence_summary"]
        if row["account"] in {"Jackson's Bakery", "The Felix Project"}:
            row["verified_live"] = True


def build_source_map(rows: list[dict], strength_counts: dict[str, int]) -> dict:
    inputs_used = [
        "Evidence/UK_IE_D365_USEFUL_LEADS_NEXT.json",
        "Evidence/UK_IE_D365_SIGNAL_QUALITY_AUDIT_20260603.json",
        "Evidence/UK_IE_D365_SIGNAL_QUALITY_AUDIT_20260603_SOURCE_CHECKS.json",
        "Evidence/UK_IE_D365_SIGNAL_QUALITY_STRONGER_SEARCH_20260603.json",
        "C:/Users/Nilhan.dev/Downloads/UK_IE_D365_AI_Opportunity_Intelligence (1).pdf (structure/style reference only)",
    ]
    return {
        "artifact_type": "uk_ie_d365_ai_opportunity_intelligence_14_source_map",
        "generated_at": now_iso(),
        "title": "AI-Driven Opportunity Intelligence: UK & Ireland Dynamics 365 Market Signals for 1BT",
        "account_count": len(rows),
        "scope": {
            "market_focus": "United Kingdom and Ireland",
            "core_theme": "Microsoft Dynamics 365 / Business Central / Power Platform public-signal opportunity hypotheses",
            "use_case": "1BT outbound sales intelligence",
            "not_in_scope": [
                "email sending",
                "Gmail outreach",
                "deployment",
                "private or authenticated LinkedIn evidence",
                "tender/procurement-only lead generation",
            ],
        },
        "inputs_used": inputs_used,
        "ratings": strength_counts,
        "accounts": [
            {
                "rank": row["rank"],
                "account": row["account"],
                "market": row["market"],
                "sector": row["sector"],
                "signal_strength": row["strength"],
                "signal_type": row["signal_type"],
                "signal_title": row["signal_title"],
                "evidence": [
                    {
                        "source_name": row["source_name"],
                        "evidence_url": row["evidence_url"],
                        "final_url": row["source_final_url"],
                        "evidence_summary": row["evidence_summary"],
                        "evidence_excerpt": row["evidence_excerpt"],
                        "checked_at": row["checked_at"],
                        "http_status": row["http_status"],
                        "verified_live": row["verified_live"],
                        "d365_terms_found": row["d365_terms_found"],
                        "strong_signal_terms_found": row["strong_signal_terms_found"],
                    }
                ],
                "opportunity_signal": row["opportunity_signal"],
                "why_this_matters_to_1bt": row["why_matters"],
                "commercial_opening": row["commercial_opening"],
                "value_of_the_signal": row["value_signal"],
                "intelligence_reading": row["intelligence_reading"],
                "board_relevance": row["board_relevance"],
                "do_not_claim_notes": row["do_not_claim"],
                "remaining_uncertainty": row["caveat"],
            }
            for row in rows
        ],
    }


def build_markdown(rows: list[dict]) -> str:
    signal_themes = [
        "D365 implementation / rollout",
        "D365 Finance / F&SCM transformation",
        "Business Central operational support",
        "Customer Insights / Customer Service / Power Platform",
        "Data migration / modernisation",
        "Public-sector digital service transformation",
    ]
    lines = [
        "# AI-Driven Opportunity Intelligence: UK & Ireland Dynamics 365 Market Signals for 1BT",
        "",
        "**14 opportunity signals | UK & IE market focus | D365 core theme**",
        "",
        "This report converts the recommended 14 pitchable options into public-signal, sales-relevant opportunity hypotheses for 1BT. These are not generic leads and they are not claims of buying intent. They are accounts where public evidence suggests a credible Dynamics 365, Business Central, or Power Platform conversation can be opened carefully.",
        "",
        "## Executive Snapshot",
        "",
        "The 14 accounts below are evidence-led signals selected from the June 3, 2026 UK/Ireland D365 quality audit and stronger-signal review. The pack prioritises named organisations, public source evidence, D365/Microsoft business-app relevance, and a practical 1BT commercial opening.",
        "",
        "**Signal mix:** 6 Strong Signal, 5 Promising Signal, 3 Emerging Signal.",
        "",
        "**Important caveats:** public-sector accounts are treated as support, optimisation, and digital-service hypotheses, not tender/procurement leads. Installed-base-only signals should not be sold as active pain. Source-cleanup caveats remain visible where the evidence is useful but less clean.",
        "",
        "## Signal Themes",
        "",
    ]
    lines.extend(f"- {theme}" for theme in signal_themes)
    lines.extend(
        [
            "",
            "## At-A-Glance Grid",
            "",
            "| # | Account | Signal type | Strength | 1BT pitch lane |",
            "|---:|---|---|---|---|",
        ]
    )
    for row in rows:
        lane = row["commercial_opening"].split(":", 1)[0]
        if len(lane) > 86:
            lane = row["signal_type"]
        lines.append(f"| {row['rank']} | {row['account']} | {row['signal_type']} | **{row['strength']}** | {lane} |")
    lines.append("")
    for row in rows:
        lines.extend(
            [
                f"## {row['rank']}. {row['account']} - {row['strength']}",
                "",
                f"**Signal type:** {row['signal_type']}",
                "",
                f"**Public source:** [{row['source_name']}]({row['evidence_url']})",
                "",
                f"**Opportunity signal:** {row['opportunity_signal']}",
                "",
                f"**Why this matters to 1BT:** {row['why_matters']}",
                "",
                f"**Commercial opening:** {row['commercial_opening']}",
                "",
                f"**Value of the signal:** {row['value_signal']}",
                "",
                f"**Intelligence reading:** {row['intelligence_reading']}",
                "",
                f"**Board relevance:** {row['board_relevance']}",
                "",
                f"**Do-not-claim notes:** {row['do_not_claim']}",
                "",
                f"**Remaining uncertainty:** {row['caveat']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Evidence And Governance Notes",
            "",
            "- Evidence inputs are the June 3, 2026 saved UK/IE D365 useful-lead pack, signal-quality audit, source checks, and stronger-search artifacts in the project Evidence folder.",
            "- The previous 12-account PDF was used only for structure and executive style.",
            "- No Gmail, email sending, deployment, private LinkedIn, synthetic companies, fake URLs, or tender/procurement-only sources were used for this report.",
            "- The companion source map stores evidence references and caveats per account.",
            "",
        ]
    )
    return "\n".join(lines)


def build_html(rows: list[dict]) -> str:
    css = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>AI-Driven Opportunity Intelligence: UK & Ireland Dynamics 365 Market Signals for 1BT</title>
<style>
@page { size: A4 landscape; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; background: #e8edf3; color: #172033; font-family: Aptos, Segoe UI, Arial, sans-serif; }
.page { width: 297mm; min-height: 210mm; padding: 16mm 18mm 14mm; page-break-after: always; position: relative; overflow: hidden; background: #ffffff; }
.page:last-child { page-break-after: auto; }
.cover { background: linear-gradient(135deg, #07192d 0%, #12395b 58%, #31556d 100%); color: #ffffff; }
.cover .kicker { color: #f1c15d; font-size: 15px; letter-spacing: 0; text-transform: uppercase; font-weight: 700; }
h1 { margin: 8mm 0 5mm; font-size: 41px; line-height: 1.06; font-weight: 760; letter-spacing: 0; max-width: 235mm; }
h2 { margin: 0 0 7mm; font-size: 25px; line-height: 1.14; color: #0c2a44; letter-spacing: 0; }
.cover h2 { color: #dfeaf4; font-size: 24px; font-weight: 520; max-width: 215mm; }
p { margin: 0 0 4mm; font-size: 12.5px; line-height: 1.43; }
.cover p { color: #dce7ef; font-size: 14px; max-width: 210mm; }
.metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 5mm; margin-top: 20mm; }
.metric { border-top: 2px solid #f1c15d; padding-top: 4mm; }
.metric .num { font-size: 34px; font-weight: 800; line-height: 1; }
.metric .label { margin-top: 2mm; color: #dce7ef; font-size: 12px; text-transform: uppercase; font-weight: 700; }
.footer { position: absolute; left: 18mm; right: 18mm; bottom: 8mm; display: flex; justify-content: space-between; align-items: center; color: #718095; font-size: 10.5px; border-top: 1px solid #dfe5ed; padding-top: 3mm; }
.cover .footer { color: #c6d3df; border-top-color: rgba(255,255,255,.22); }
.section-label { color: #b27918; text-transform: uppercase; font-weight: 800; font-size: 11px; margin-bottom: 3mm; }
.snapshot-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8mm; margin-top: 8mm; }
.panel { background: #f6f8fb; border-left: 4px solid #e5aa3d; padding: 6mm; border-radius: 4px; }
.panel h3 { margin: 0 0 3mm; font-size: 15px; color: #0c2a44; }
.panel ul { margin: 0; padding-left: 5mm; }
.panel li { font-size: 12.4px; line-height: 1.45; margin-bottom: 2.2mm; }
.glance-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 2.8mm; margin-top: 5mm; }
.glance { border: 1px solid #dfe5ed; border-left: 4px solid #12395b; border-radius: 4px; padding: 3mm 3.5mm; min-height: 22mm; display: grid; grid-template-columns: 7mm 1fr; column-gap: 2.6mm; align-items: start; }
.glance .rank { color: #9aa6b5; font-weight: 800; font-size: 12px; }
.glance h3 { margin: 0 0 1.2mm; font-size: 12.7px; color: #102a43; }
.glance p { margin: 0; font-size: 10.6px; color: #546377; line-height: 1.25; }
.badge { white-space: nowrap; border-radius: 999px; padding: 1.5mm 2.2mm; font-size: 9.7px; font-weight: 800; }
.glance .badge { grid-column: 2; justify-self: start; margin-top: 1.6mm; }
.badge.strong { background: #eaf6ef; color: #1f7a48; }
.badge.promising { background: #fff3db; color: #9a5c00; }
.badge.emerging { background: #eef2f7; color: #526070; }
.detail-head { display: grid; grid-template-columns: 1fr auto; gap: 8mm; align-items: start; margin-bottom: 5mm; }
.detail-head h2 { margin: 0 0 2mm; font-size: 27px; }
.signal-sub { color: #4c6074; font-size: 13.2px; line-height: 1.35; }
.source-cue { margin-top: 2mm; color: #718095; font-size: 10.6px; }
.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 3.5mm; }
.field { background: #f7f9fc; border: 1px solid #e1e7ef; border-left: 4px solid #e5aa3d; border-radius: 4px; padding: 3.5mm 4mm; min-height: 31mm; }
.field h3 { margin: 0 0 2mm; color: #0c2a44; font-size: 12.6px; text-transform: uppercase; letter-spacing: 0; }
.field p { color: #26384c; font-size: 11.7px; line-height: 1.36; margin: 0; }
.guardrail { margin-top: 4mm; display: grid; grid-template-columns: 1fr 1fr; gap: 3.5mm; }
.note { background: #fff8eb; border: 1px solid #f0d7a4; border-radius: 4px; padding: 3mm 4mm; }
.note h3 { margin: 0 0 1.5mm; color: #815000; font-size: 11.5px; text-transform: uppercase; }
.note p { margin: 0; font-size: 10.8px; color: #5e4a22; line-height: 1.3; }
</style>
</head>
<body>
"""
    page_no = 1
    parts = [css]
    parts.append(f"""
<section class="page cover">
  <div class="kicker">1BT Sales Intelligence</div>
  <h1>AI-Driven Opportunity Intelligence</h1>
  <h2>UK &amp; Ireland Dynamics 365 Market Signals for 1BT</h2>
  <p>Fourteen public-signal opportunity hypotheses selected for sales relevance: what the D365 signal is, how strong it is, why it matters, and how 1BT can credibly open a conversation.</p>
  <div class="metrics">
    <div class="metric"><div class="num">14</div><div class="label">Opportunity Signals</div></div>
    <div class="metric"><div class="num">6</div><div class="label">Signal Themes</div></div>
    <div class="metric"><div class="num">UK &amp; IE</div><div class="label">Market Focus</div></div>
    <div class="metric"><div class="num">D365</div><div class="label">Core Theme</div></div>
  </div>
  <div class="footer"><span>Public-source opportunity intelligence</span><span>{page_no}</span></div>
</section>
""")
    page_no += 1
    parts.append(f"""
<section class="page">
  <div class="section-label">Executive Snapshot</div>
  <h2>What this demonstrates for 1BT</h2>
  <p>These 14 accounts are public-signal, sales-relevant opportunity hypotheses. They are not generic leads, and they are not assertions of active buying intent. Each account has a visible Microsoft business-app signal that can support a credible, evidence-led conversation for 1BT.</p>
  <div class="snapshot-grid">
    <div class="panel">
      <h3>Signal themes surfaced</h3>
      <ul>
        <li>D365 implementation / rollout</li>
        <li>D365 Finance / F&amp;SCM transformation</li>
        <li>Business Central operational support</li>
        <li>Customer Insights / Customer Service / Power Platform</li>
        <li>Data migration / modernisation</li>
        <li>Public-sector digital service transformation</li>
      </ul>
    </div>
    <div class="panel">
      <h3>Board takeaway</h3>
      <p>The strongest opportunities are not simply organisations that use Dynamics 365. They are accounts where public evidence points to operational change, support load, process replacement, reporting pressure, migration work, or post-rollout value capture. That gives 1BT a reason to speak about outcomes rather than software alone.</p>
    </div>
    <div class="panel">
      <h3>Quality split</h3>
      <ul>
        <li>6 Strong Signal accounts with current or high-specificity D365 evidence.</li>
        <li>5 Promising Signal accounts with credible pitch paths but caveats.</li>
        <li>3 Emerging Signal accounts useful for pipeline options after cleanup.</li>
      </ul>
    </div>
    <div class="panel">
      <h3>Use with care</h3>
      <p>Public-sector case studies are treated as support or optimisation hypotheses, not tender/procurement leads. Installed-base-only signals should not be sold as active pain. Source-cleanup caveats remain visible where evidence is useful but less clean.</p>
    </div>
  </div>
  <div class="footer"><span>AI-Driven Opportunity Intelligence</span><span>{page_no}</span></div>
</section>
""")
    page_no += 1
    cards = []
    for row in rows:
        cards.append(f"""
    <div class="glance">
      <div class="rank">{row['rank']:02d}</div>
      <div>
        <h3>{esc(row['account'])}</h3>
        <p>{esc(row['signal_type'])}</p>
      </div>
      <div class="badge {badge_class(row['strength'])}">{esc(row['strength'])}</div>
    </div>
""")
    parts.append(f"""
<section class="page">
  <div class="section-label">At-A-Glance Grid</div>
  <h2>Fourteen pitchable D365 opportunity signals</h2>
  <p>Ordered with the strongest and cleanest sales signals first. The grid shows the signal type and strength label; account-detail pages translate each signal into a specific 1BT commercial opening.</p>
  <div class="glance-grid">
    {''.join(cards)}
  </div>
  <div class="footer"><span>Signal strength: Strong, Promising, Emerging</span><span>{page_no}</span></div>
</section>
""")
    page_no += 1
    for row in rows:
        fields = [
            ("Opportunity signal", row["opportunity_signal"]),
            ("Why this matters to 1BT", row["why_matters"]),
            ("Commercial opening", row["commercial_opening"]),
            ("Value of the signal", row["value_signal"]),
            ("Intelligence reading", row["intelligence_reading"]),
            ("Board relevance", row["board_relevance"]),
        ]
        parts.append(f"""
<section class="page">
  <div class="detail-head">
    <div>
      <div class="section-label">Account Detail {row['rank']:02d}</div>
      <h2>{esc(row['account'])}</h2>
      <div class="signal-sub">{esc(row['signal_title'])}</div>
      <div class="source-cue">Public source: {esc(row['source_name'])} | {esc(short_url(row['evidence_url']))}</div>
    </div>
    <div class="badge {badge_class(row['strength'])}">{esc(row['strength'])}</div>
  </div>
  <div class="detail-grid">
    {''.join(detail_field(label, body) for label, body in fields)}
  </div>
  <div class="guardrail">
    <div class="note"><h3>Do not claim</h3><p>{esc(row['do_not_claim'])}</p></div>
    <div class="note"><h3>Remaining uncertainty</h3><p>{esc(row['caveat'])}</p></div>
  </div>
  <div class="footer"><span>{esc(row['market'])} | {esc(row['sector'])}</span><span>{page_no}</span></div>
</section>
""")
        page_no += 1
    parts.append("</body>\n</html>\n")
    return "".join(parts)


def main() -> None:
    rows = accounts()
    merge_source_metadata(rows, load_source_checks())
    strength_counts: dict[str, int] = {}
    for row in rows:
        strength_counts[row["strength"]] = strength_counts.get(row["strength"], 0) + 1

    md_path = EVIDENCE / "UK_IE_D365_AI_Opportunity_Intelligence_14.md"
    html_path = EVIDENCE / "UK_IE_D365_AI_Opportunity_Intelligence_14.html"
    source_map_path = EVIDENCE / "UK_IE_D365_AI_Opportunity_Intelligence_14_SOURCE_MAP.json"

    md_path.write_text(build_markdown(rows), encoding="utf-8")
    html_path.write_text(build_html(rows), encoding="utf-8")
    source_map_path.write_text(
        json.dumps(build_source_map(rows, strength_counts), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(
        {
            "written": [str(md_path), str(html_path), str(source_map_path)],
            "account_count": len(rows),
            "strength_counts": strength_counts,
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
