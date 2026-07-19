import json
import unittest

from sl_trigger_leads.tools import contact_resolver_tools as tools
from sl_trigger_leads.tools.gmail_sender_tools import refuse_lead_outreach_email

EXPLICIT_THREE_LEAD_TEXT = """Lead 1:
company_name: Vs One World (Pvt) Ltd
signal_summary: QE Engineer - API & Integration hiring signal
signal_source_url: https://itpro.lk/job/13609/qe-engineer-api-integration-at-vs-one-world-pvt-ltd/
service_bucket: Software Development
country: Sri Lanka

Lead 2:
company_name: WSO2
signal_summary: Enterprise software company; test whether resolver can find public/company contact routes.
signal_source_url: https://wso2.com/contact/
service_bucket: Software Development
country: Sri Lanka

Lead 3:
company_name: Microsoft
signal_summary: Large public technology company; test Hunter/domain/contact route behavior.
signal_source_url: https://www.microsoft.com/en-us/contactus
service_bucket: MS 365D
country: United States
"""


class FakeSearchProvider:
    name = "fake_public_provider"
    configured = True

    def __init__(self, pages):
        self.pages = pages
        self.queries = []
        self.fetches = []

    def search_web(self, query, limit):
        self.queries.append(query)
        if query not in self.pages:
            return []
        return [tools.SearchResult(title="Result", url=self.pages[query]["url"], snippet="")]

    def fetch_page(self, url):
        self.fetches.append(url)
        for page in self.pages.values():
            if page["url"] == url:
                return tools.PageText(url=url, text=page["text"], source="fixture")
        return tools.PageText(url=url, text="", source="fixture")

    def extract_emails(self, text):
        return tools.extract_emails(text)

    def extract_people_roles(self, text, company, target_personas):
        return tools.extract_people_roles(text, company, target_personas)


def sample_lead(**overrides):
    lead = tools.prompt10_sample_lead()
    lead.update(overrides)
    return lead


def hunter_record(
    *,
    email="person@wso2.com",
    full_name="Asanka Abeysinghe",
    position="CTO",
    confidence=99,
    verification_status=None,
    source_urls=None,
):
    first, last = ([*full_name.split(" ", 1), None])[:2] if full_name else (None, None)
    status = tools.HUNTER_VERIFIED if verification_status == "valid" else (
        tools.HUNTER_NOT_FOUND if verification_status == "invalid" else tools.HUNTER_FOUND
    )
    return tools.HunterEmailRecord(
        email=email,
        full_name=full_name,
        first_name=first,
        last_name=last,
        position=position,
        department=None,
        email_kind="personal",
        confidence=confidence,
        verification_status=verification_status,
        hunter_status=status,
        domain="wso2.com",
        source_urls=source_urls if source_urls is not None else ["https://wso2.com/team"],
        linkedin_url=None,
    )


class ContactResolverToolsTest(unittest.TestCase):
    def test_explicit_contact_target_roles_take_priority(self):
        personas = tools.merge_personas_for_lead(
            {
                "company": "Northstar Housing",
                "contact_target_roles": [
                    "Chief Information Officer",
                    "Head of Business Applications",
                    "Chief Information Officer",
                ],
                "opportunity_bucket_primary": "Custom Software Development",
            }
        )

        self.assertEqual(
            [item["persona"] for item in personas[:2]],
            ["Chief Information Officer", "Head of Business Applications"],
        )
        self.assertEqual(personas[0]["priority"], 1)
        self.assertIn("verified lead", personas[0]["why_relevant"])

    def test_persona_mapping_per_bucket(self):
        self.assertEqual(
            tools.map_personas_for_bucket("Staff Augmentation / Delivery Capacity")[0]["persona"],
            "CTO",
        )
        integration_personas = [
            item["persona"] for item in tools.map_personas_for_bucket("Integrations / API / Middleware")
        ]
        self.assertIn("Integration Lead", integration_personas)
        qa_personas = [item["persona"] for item in tools.map_personas_for_bucket("QA / Test Automation")]
        self.assertIn("QA Manager", qa_personas)
        dynamics_personas = [
            item["persona"]
            for item in tools.map_personas_for_bucket("Microsoft Dynamics 365 / CRM / Power Platform")
        ]
        self.assertIn("CRM Manager", dynamics_personas)

    def test_status_is_not_used_as_primary_service_bucket(self):
        lead = sample_lead(
            opportunity_bucket_primary="Low Fit / Watch",
            primary_bucket_display=None,
            primary_bucket=None,
            onebt_fit=[],
            opportunity_bucket_secondary=[],
            trigger="QE Engineer - API & Integration",
        )
        normalized = tools.normalize_lead(lead)
        self.assertEqual(normalized["opportunity_bucket_primary"], "QA / Test Automation")
        self.assertEqual(normalized["verdict"], "Contact now")

    def test_signal_bucket_inference_for_api_and_ai_roles(self):
        api = tools.normalize_lead(
            {
                "company": "TestCo",
                "trigger": "Senior Software Engineer - .NET API Middleware",
                "verdict": "Watch",
            }
        )
        self.assertEqual(api["opportunity_bucket_primary"], "Integrations / API / Middleware")
        ai = tools.normalize_lead(
            {
                "company": "TestCo",
                "trigger": "AI Developer",
                "verdict": "Watch",
            }
        )
        self.assertEqual(ai["opportunity_bucket_primary"], "AI Apps / AI Workflow Automation")

    def test_generic_inbox_is_lower_confidence_than_named_role_match(self):
        target = ["CTO", "Head of Engineering"]
        generic = tools.score_candidate_contact(
            {
                "name": None,
                "role": "Company contact inbox",
                "company": "Vs One World (Pvt) Ltd",
                "email": "info@vsoneworld.lk",
                "email_type": "public_generic",
                "source_urls": ["https://vsoneworld.lk/contact"],
                "source_kind": "official_company",
            },
            target_personas=target,
        )
        named = tools.score_candidate_contact(
            {
                "name": "Jane Perera",
                "role": "Head of Engineering",
                "company": "Vs One World (Pvt) Ltd",
                "email": None,
                "email_type": "unknown",
                "source_urls": ["https://vsoneworld.lk/team"],
                "source_kind": "official_company",
            },
            target_personas=target,
        )
        self.assertLess(generic["confidence"], named["confidence"])
        self.assertLessEqual(generic["confidence"], 45)

    def test_inferred_email_pattern_is_disabled(self):
        inferred = tools.infer_email_pattern(
            name="Jane Perera",
            domain="vsoneworld.lk",
            observed_emails=["saman.silva@vsoneworld.lk"],
        )
        self.assertIsNone(inferred["email"])
        self.assertEqual(inferred["email_type"], "unknown")

    def test_former_role_is_not_promoted_as_current_named_contact(self):
        people = tools.extract_people_roles(
            "Kaushala Lankadikara. Director. an experienced tech leader and former CTO.",
            "Vs One World (Pvt) Ltd",
            ["CTO"],
        )
        self.assertEqual(people, [])

    def test_company_name_is_not_promoted_as_named_contact(self):
        people = tools.extract_people_roles(
            "VS ONE WORLD Engineering Manager jobs and careers",
            "Vs One World (Pvt) Ltd",
            ["Engineering Manager"],
        )
        self.assertEqual(people, [])

    def test_role_phrase_is_not_promoted_as_named_contact(self):
        people = tools.extract_people_roles(
            "Business Architect - CTO and integration strategy",
            "WSO2",
            ["CTO", "Solutions Architect"],
        )
        self.assertEqual(people, [])

    def test_article_title_is_not_promoted_as_named_contact(self):
        people = tools.extract_people_roles(
            "Five Practical Ways Leaders can evaluate CTO priorities",
            "Microsoft",
            ["CTO"],
        )
        self.assertEqual(people, [])

    def test_leadership_phrase_is_not_promoted_as_named_contact(self):
        people = tools.extract_people_roles(
            "VIVID's Leadership - Chief Information Officer",
            "VIVID",
            ["Chief Information Officer"],
        )
        self.assertEqual(people, [])

    def test_person_honorific_is_removed_from_named_contact(self):
        people = tools.extract_people_roles(
            "Mr Manpreet Dillon - Director of Housing Services",
            "Origin Housing",
            ["Director of Housing Services"],
        )
        self.assertEqual(people[0].name, "Manpreet Dillon")

    def test_no_invented_emails_when_search_provider_missing(self):
        result = tools.resolve_contact_route_for_lead(sample_lead(), dry_run=True)
        self.assertEqual(result["candidate_contacts"], [])
        self.assertIsNone(result["best_contact_route"]["email"])
        self.assertEqual(
            result["search_summary"]["stopped_reason"],
            "search_provider_not_configured",
        )
        self.assertEqual(result["search_summary"]["hunter_status"], "HUNTER_NOT_CONFIGURED")

    def test_provider_discovery_reports_hunter_status_without_secret(self):
        status = tools.discover_contact_live_search_provider()
        self.assertIn(status["hunter_status"], {"HUNTER_NOT_CONFIGURED", "HUNTER_NOT_FOUND"})
        self.assertIn("hunter", status["fallback_hooks"])
        self.assertNotIn("HUNTER_" + "API_KEY=", json.dumps(status))

    def test_hunter_first_invalid_later_unknown_high_confidence_is_usable(self):
        normalized = tools.normalize_lead(
            {
                "company": "WSO2",
                "evidence_url": "https://wso2.com/contact/",
                "opportunity_bucket_primary": "Custom Software Development",
            }
        )
        personas = ["CTO", "Director of Engineering", "Head of Engineering"]
        invalid = hunter_record(
            email="invalid@wso2.com",
            full_name="Invalid Person",
            position="Vice President",
            verification_status="invalid",
        )
        usable = hunter_record(
            email="ishara@wso2.com",
            full_name="Ishara Karunarathna",
            position="Director of Engineering",
            confidence=99,
            verification_status=None,
            source_urls=["https://wso2.com/team"],
        )
        self.assertIsNone(
            tools._hunter_record_to_candidate(
                invalid,
                normalized=normalized,
                target_personas=personas,
                endpoint="domain_search",
            )
        )
        candidate = tools._hunter_record_to_candidate(
            usable,
            normalized=normalized,
            target_personas=personas,
            endpoint="domain_search",
        )
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["hunter_status"], "HUNTER_FOUND")
        self.assertEqual(candidate["email"], "ishara@wso2.com")
        self.assertGreaterEqual(candidate["confidence"], 70)

    def test_hunter_valid_result_is_verified(self):
        normalized = tools.normalize_lead(
            {
                "company": "WSO2",
                "evidence_url": "https://wso2.com/contact/",
                "opportunity_bucket_primary": "Custom Software Development",
            }
        )
        candidate = tools._hunter_record_to_candidate(
            hunter_record(verification_status="valid"),
            normalized=normalized,
            target_personas=["CTO", "Head of Engineering"],
            endpoint="domain_search",
        )
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["hunter_status"], "HUNTER_VERIFIED")
        self.assertEqual(candidate["hunter_verification_status"], "valid")

    def test_all_invalid_hunter_results_are_rejected(self):
        normalized = tools.normalize_lead(
            {
                "company": "WSO2",
                "evidence_url": "https://wso2.com/contact/",
                "opportunity_bucket_primary": "Custom Software Development",
            }
        )
        records = [
            hunter_record(email="one@wso2.com", verification_status="invalid"),
            hunter_record(email="two@wso2.com", verification_status="invalid"),
        ]
        candidates = [
            tools._hunter_record_to_candidate(
                record,
                normalized=normalized,
                target_personas=["CTO"],
                endpoint="domain_search",
            )
            for record in records
        ]
        self.assertEqual(candidates, [None, None])

    def test_hunter_unknown_requires_high_confidence_named_role_and_evidence(self):
        normalized = tools.normalize_lead(
            {
                "company": "WSO2",
                "evidence_url": "https://wso2.com/contact/",
                "opportunity_bucket_primary": "Custom Software Development",
            }
        )
        personas = ["CTO", "Head of Engineering"]
        self.assertIsNone(
            tools._hunter_record_to_candidate(
                hunter_record(confidence=89, verification_status="unknown"),
                normalized=normalized,
                target_personas=personas,
                endpoint="domain_search",
            )
        )
        self.assertIsNone(
            tools._hunter_record_to_candidate(
                hunter_record(position=None, verification_status="unknown"),
                normalized=normalized,
                target_personas=personas,
                endpoint="domain_search",
            )
        )
        self.assertIsNone(
            tools._hunter_record_to_candidate(
                hunter_record(source_urls=[], verification_status="unknown"),
                normalized=normalized,
                target_personas=personas,
                endpoint="domain_search",
            )
        )

    def test_candidate_loss_audit_logs_invalid_candidates_as_rejected(self):
        normalized = tools.normalize_lead(
            {
                "company": "WSO2",
                "evidence_url": "https://wso2.com/contact/",
                "opportunity_bucket_primary": "Custom Software Development",
            }
        )
        state = {"audit_mode": True, "candidate_audit_entries": []}
        record = hunter_record(email="invalid@wso2.com", verification_status="invalid")
        tools._record_hunter_candidate_audit(
            state,
            record,
            normalized=normalized,
            endpoint="domain_search",
            candidate=None,
        )
        audit = tools._build_candidate_loss_audit(
            state,
            final_candidates=[],
            best_route={"reason": "No final route selected."},
        )
        self.assertEqual(audit["raw_hunter_results_count"], 1)
        self.assertEqual(audit["invalid_rejected_count"], 1)
        self.assertEqual(audit["candidates"][0]["rejection_reason"], "invalid_verification")

    def test_candidate_loss_audit_logs_unknown_high_confidence_as_accepted(self):
        normalized = tools.normalize_lead(
            {
                "company": "WSO2",
                "evidence_url": "https://wso2.com/contact/",
                "opportunity_bucket_primary": "Custom Software Development",
            }
        )
        record = hunter_record(
            email="ishara@wso2.com",
            full_name="Ishara Karunarathna",
            position="Director of Engineering",
            confidence=99,
            verification_status=None,
            source_urls=["https://wso2.com/team"],
        )
        candidate = tools._hunter_record_to_candidate(
            record,
            normalized=normalized,
            target_personas=["CTO", "Director of Engineering"],
            endpoint="domain_search",
        )
        state = {"audit_mode": True, "candidate_audit_entries": []}
        tools._record_hunter_candidate_audit(
            state,
            record,
            normalized=normalized,
            endpoint="domain_search",
            candidate=candidate,
        )
        audit = tools._build_candidate_loss_audit(
            state,
            final_candidates=[candidate],
            best_route={"reason": "Hunter returned this contact route."},
        )
        self.assertEqual(audit["unknown_accepted_count"], 1)
        self.assertEqual(audit["final_candidate_count"], 1)
        self.assertEqual(audit["candidates"][0]["final_rank"], 1)
        self.assertEqual(audit["candidates"][0]["email"], "ishara@wso2.com")

    def test_candidate_loss_audit_exposes_useful_looking_rejected_candidate(self):
        normalized = tools.normalize_lead(
            {
                "company": "WSO2",
                "evidence_url": "https://wso2.com/contact/",
                "opportunity_bucket_primary": "Custom Software Development",
            }
        )
        record = hunter_record(
            email="useful@wso2.com",
            full_name="Useful Candidate",
            position=None,
            confidence=99,
            verification_status="unknown",
            source_urls=["https://wso2.com/team"],
        )
        state = {"audit_mode": True, "candidate_audit_entries": []}
        tools._record_hunter_candidate_audit(
            state,
            record,
            normalized=normalized,
            endpoint="domain_search",
            candidate=None,
        )
        audit = tools._build_candidate_loss_audit(
            state,
            final_candidates=[],
            best_route={"reason": "No final route selected."},
        )
        self.assertTrue(audit["high_confidence_candidate_rejected"])
        self.assertTrue(audit["filters_appear_too_strict"])
        self.assertEqual(audit["top_rejected_candidates"][0]["rejection_reason"], "no_role")

    def test_parse_explicit_three_lead_text_preserves_companies(self):
        leads = tools.parse_explicit_leads_text(EXPLICIT_THREE_LEAD_TEXT)
        self.assertEqual(len(leads), 3)
        self.assertEqual([lead["company"] for lead in leads], ["Vs One World (Pvt) Ltd", "WSO2", "Microsoft"])
        self.assertEqual(leads[0]["trigger"], "QE Engineer - API & Integration hiring signal")
        self.assertEqual(leads[1]["evidence_url"], "https://wso2.com/contact/")
        self.assertEqual(leads[2]["opportunity_bucket_primary"], "MS 365D")

    def test_alias_fields_do_not_normalize_to_unknown_company(self):
        result = tools.normalize_lead(
            {
                "company_name": "WSO2",
                "signal_summary": "Enterprise software company",
                "signal_source_url": "https://wso2.com/contact/",
                "service_bucket": "Software Development",
            }
        )
        self.assertEqual(result["company"], "WSO2")
        self.assertEqual(result["trigger"], "Enterprise software company")
        self.assertEqual(result["evidence_url"], "https://wso2.com/contact/")
        self.assertNotEqual(result["company"], "unknown")

    def test_explicit_text_wrapper_returns_three_grouped_rows_without_live_search(self):
        result = tools.resolve_contact_routes_from_text(
            EXPLICIT_THREE_LEAD_TEXT,
            max_leads=3,
            dry_run=True,
        )
        self.assertEqual(result["parsed_leads_count"], 3)
        self.assertEqual(result["resolved_count"], 3)
        self.assertEqual([item["company"] for item in result["results"]], ["Vs One World (Pvt) Ltd", "WSO2", "Microsoft"])
        self.assertNotIn("unknown", [item["company"].lower() for item in result["results"]])
        for item in result["results"]:
            self.assertIn("hunter_status", item["search_summary"])

    def test_stops_after_search_budget(self):
        provider = FakeSearchProvider(
            {
                '"Vs One World (Pvt) Ltd" "CTO"': {
                    "url": "https://vsoneworld.lk/contact",
                    "text": "Contact us at info@vsoneworld.lk",
                },
                '"Vs One World (Pvt) Ltd" "Head of Engineering"': {
                    "url": "https://vsoneworld.lk/team",
                    "text": "No useful contacts here",
                },
            }
        )
        result = tools._resolve_contact_route_for_lead(
            sample_lead(),
            provider=provider,
            dry_run=True,
            max_search_queries=2,
            max_pages_to_fetch=1,
            max_candidate_contacts=5,
            max_runtime_seconds=90,
        )
        self.assertLessEqual(len(result["search_summary"]["queries_attempted"]), 2)
        self.assertLessEqual(len(result["search_summary"]["sources_checked"]), 1)
        self.assertTrue(result["search_summary"]["timeboxed"])

    def test_duplicate_companies_are_grouped(self):
        leads = [
            sample_lead(company="Vs One World (Pvt) Ltd", trigger="QE Engineer - API & Integration"),
            sample_lead(company="Vs One World (Pvt) Ltd", trigger="Senior Software Engineer - .NET API Middleware"),
            sample_lead(company="Innovay", trigger="AI Developer"),
        ]
        grouped = tools.group_leads_by_company(leads)
        self.assertEqual(len(grouped), 2)
        vs = next(item for item in grouped if item["company"] == "Vs One World (Pvt) Ltd")
        self.assertEqual(vs["signal_count"], 2)

    def test_compact_output_is_contact_first_and_short(self):
        result = {
            "company": "Vs One World (Pvt) Ltd",
            "signal_count": 2,
            "lead_evidence_url": "https://itpro.lk/job/13609/qe-engineer-api-integration-at-vs-one-world-pvt-ltd/",
            "ideal_buyer_personas": [{"persona": "CTO"}, {"persona": "Head of Engineering"}],
            "best_contact_route": {
                "type": "generic_company",
                "email": "info@vsoneworld.com",
                "url": "https://www.vsoneworld.com/",
                "confidence": 45,
            },
            "search_summary": {
                "named_person_search_attempted": True,
                "named_roles_attempted": ["CTO", "Head of Engineering"],
            },
        }
        output = tools.format_contact_routes_table([result])
        self.assertTrue(output.startswith("Contact routes found:"))
        self.assertIn("| Company | Best contact | Type | Confidence | Evidence |", output)
        self.assertIn("info@vsoneworld.com", output)
        self.assertIn("Named contact search:", output)
        self.assertNotIn("Do-not-claim", output)
        self.assertNotIn("candidate_loss_audit", output)
        self.assertNotIn("rejection_reason", output)
        self.assertLessEqual(len(output.splitlines()), 12)

    def test_candidate_loss_audit_contains_no_secret_values(self):
        normalized = tools.normalize_lead(
            {
                "company": "WSO2",
                "evidence_url": "https://wso2.com/contact/",
                "opportunity_bucket_primary": "Custom Software Development",
            }
        )
        record = hunter_record(email="secretcheck@wso2.com", verification_status="invalid")
        state = {"audit_mode": True, "candidate_audit_entries": []}
        tools._record_hunter_candidate_audit(
            state,
            record,
            normalized=normalized,
            endpoint="domain_search",
            candidate=None,
        )
        audit = tools._build_candidate_loss_audit(
            state,
            final_candidates=[],
            best_route={"reason": "No final route selected."},
        )
        serialized = json.dumps(audit)
        self.assertNotIn("api_key", serialized.lower())
        self.assertNotIn("hunter_api_key", serialized.lower())
        tools.assert_no_secret_patterns({"candidate_loss_audit": audit})

    def test_no_sending_behavior_exists(self):
        refusal = tools.refuse_contact_resolver_sending("Can you send the email now?")
        self.assertFalse(refusal["sent"])
        self.assertFalse(refusal["sending_enabled"])
        self.assertIn("Sending to leads is still locked", refusal["refusal_reason"])

    def test_lead_outreach_remains_blocked(self):
        result = refuse_lead_outreach_email("Send email to a lead")
        self.assertFalse(result["sent"])
        self.assertIn("Lead outreach is not unlocked yet", result["refusal_reason"])

    def test_personal_email_rejected_unless_official_and_flagged(self):
        rejected, rejected_notes = tools.filter_public_email(
            "person@gmail.com",
            official_context=False,
        )
        self.assertIsNone(rejected)
        self.assertIn("Personal/private email domain rejected.", rejected_notes)
        allowed, allowed_notes = tools.filter_public_email(
            "owner@gmail.com",
            official_context=True,
        )
        self.assertEqual(allowed, "owner@gmail.com")
        self.assertTrue(any("Personal-domain email" in note for note in allowed_notes))

    def test_ambiguous_company_identity_lowers_confidence(self):
        target = ["Head of Engineering"]
        clear = tools.score_candidate_contact(
            {
                "name": "Jane Perera",
                "role": "Head of Engineering",
                "company": "Vs One World (Pvt) Ltd",
                "email": "jane.perera@vsoneworld.lk",
                "email_type": "public_named",
                "source_urls": ["https://vsoneworld.lk/team"],
                "source_kind": "official_company",
            },
            target_personas=target,
        )
        ambiguous = tools.score_candidate_contact(
            {**clear, "ambiguous_company": True},
            target_personas=target,
        )
        self.assertLess(ambiguous["confidence"], clear["confidence"])

    def test_stale_evidence_lowers_confidence(self):
        target = ["Head of Engineering"]
        fresh = tools.score_candidate_contact(
            {
                "name": "Jane Perera",
                "role": "Head of Engineering",
                "company": "Vs One World (Pvt) Ltd",
                "email": "jane.perera@vsoneworld.lk",
                "email_type": "public_named",
                "source_urls": ["https://vsoneworld.lk/team"],
                "source_kind": "official_company",
            },
            target_personas=target,
        )
        stale = tools.score_candidate_contact({**fresh, "stale_evidence": True}, target_personas=target)
        self.assertLess(stale["confidence"], fresh["confidence"])

    def test_output_schema_validates(self):
        result = tools.resolve_contact_route_for_lead(sample_lead(), dry_run=True)
        for key in (
            "company",
            "lead_evidence_url",
            "opportunity_bucket_primary",
            "ideal_buyer_personas",
            "candidate_contacts",
            "best_contact_route",
            "fallback_contact_route",
            "do_not_claim",
            "compliance_notes",
            "search_summary",
        ):
            self.assertIn(key, result)
        self.assertIn("type", result["best_contact_route"])
        self.assertIn("queries_attempted", result["search_summary"])

    def test_root_batch_cap_works(self):
        leads = [sample_lead(company=f"Company {index}") for index in range(12)]
        result = tools.resolve_contacts_for_leads(leads, max_leads=50, dry_run=True)
        self.assertEqual(result["resolved_count"], 10)
        self.assertEqual(result["max_leads_hard_cap"], 10)

    def test_dry_run_sample_works(self):
        result = tools.show_contact_resolver_dry_run()
        self.assertEqual(result["agent"], "Contact Resolver Agent")
        self.assertEqual(result["input_source_kind"], "prompt10_dry_run_fixture")
        self.assertGreaterEqual(result["resolved_count"], 1)

    def test_secret_patterns_are_not_emitted(self):
        result = tools.resolve_contact_route_for_lead(sample_lead(), dry_run=True)
        serialized = json.dumps(result).lower()
        for forbidden in (
            "access_" + "token",
            "refresh_" + "token",
            "client_" + "secret",
            "private_" + "key",
        ):
            self.assertNotIn(forbidden, serialized)
        with self.assertRaises(ValueError):
            tools.assert_no_secret_patterns({"bad": "client_" + "secret=abc"})

    def test_generic_inbox_fallback_implemented(self):
        first_query = tools.build_search_queries(
            sample_lead(),
            tools.merge_personas_for_lead(sample_lead()),
            max_search_queries=1,
        )[0]
        provider = FakeSearchProvider(
            {
                first_query: {
                    "url": "https://vsoneworld.lk/contact",
                    "text": "For business inquiries contact info@vsoneworld.lk",
                }
            }
        )
        result = tools._resolve_contact_route_for_lead(
            sample_lead(),
            provider=provider,
            dry_run=True,
            max_search_queries=1,
            max_pages_to_fetch=2,
            max_candidate_contacts=5,
            max_runtime_seconds=90,
        )
        self.assertEqual(result["best_contact_route"]["type"], "generic_company")
        self.assertEqual(result["candidate_contacts"][0]["email_type"], "public_generic")

    def test_partner_page_email_is_not_used_as_target_company_inbox(self):
        lead = sample_lead(
            company="Octavia Housing",
            evidence_url="https://veriland.co.uk/insights/case-studies/octavia-housing-crm-mobile-app",
        )
        first_query = tools.build_live_search_queries(
            lead,
            tools.merge_personas_for_lead(lead),
            max_search_queries=1,
        )[0]
        provider = FakeSearchProvider(
            {
                first_query: {
                    "url": "https://veriland.co.uk/insights/case-studies/octavia-housing-crm-mobile-app",
                    "text": "For enquiries contact enquiries@veriland.co.uk",
                }
            }
        )

        result = tools._resolve_contact_route_for_lead(
            lead,
            provider=provider,
            dry_run=False,
            max_search_queries=1,
            max_pages_to_fetch=2,
            max_candidate_contacts=5,
            max_runtime_seconds=90,
        )

        self.assertFalse(any(item.get("email") for item in result["candidate_contacts"]))

    def test_case_study_seed_is_not_promoted_to_job_apply_route(self):
        lead = sample_lead(
            company="Billi UK",
            evidence_url="https://tecvia.co.uk/blog/case-study/billi-uk-business-central-case-study/",
        )
        provider = FakeSearchProvider(
            {
                "unused": {
                    "url": lead["evidence_url"],
                    "text": "Billi UK replaced a legacy ERP. This case study describes the project.",
                }
            }
        )

        result = tools._resolve_contact_route_for_lead(
            lead,
            provider=provider,
            dry_run=False,
            max_search_queries=1,
            max_pages_to_fetch=1,
            max_candidate_contacts=5,
            max_runtime_seconds=90,
        )

        self.assertNotEqual(result["best_contact_route"]["type"], "job_post_apply")

    def test_official_company_url_matching_rejects_similar_foreign_entities(self):
        self.assertFalse(
            tools.is_likely_official_company_url("https://thrivehomesllc.com/contact", "Thrive Homes")
        )
        self.assertFalse(
            tools.is_likely_official_company_url("https://www.sagehomesnw.com/contact", "Sage Homes")
        )
        self.assertTrue(
            tools.is_likely_official_company_url("https://www.thrivehomes.org.uk/contact-us", "Thrive Homes")
        )
        self.assertTrue(
            tools.is_likely_official_company_url("https://www.eonenergy.com/contact", "E.ON UK")
        )
        self.assertTrue(
            tools.is_likely_official_company_url("https://www.lqgroup.org.uk/contact", "London & Quadrant (L&Q)")
        )
        self.assertTrue(
            tools.is_likely_official_company_url("https://www.ntu.ac.uk/about-us", "Nottingham Trent University")
        )
        self.assertTrue(
            tools.is_likely_official_company_url("https://tourismni.gov.ie/about", "Tourism NI")
        )
        self.assertFalse(
            tools.is_likely_official_company_url("https://thecompetitor.ie", "The National Museum")
        )

    def test_named_person_search_recorded_before_generic_fallback(self):
        first_queries = tools.build_live_search_queries(
            sample_lead(),
            tools.merge_personas_for_lead(sample_lead()),
            max_search_queries=5,
        )
        provider = FakeSearchProvider(
            {
                first_queries[0]: {
                    "url": "https://vsoneworld.lk/contact",
                    "text": "For business inquiries contact info@vsoneworld.lk",
                }
            }
        )
        result = tools._resolve_contact_route_for_lead(
            sample_lead(),
            provider=provider,
            dry_run=False,
            max_search_queries=5,
            max_pages_to_fetch=2,
            max_candidate_contacts=5,
            max_runtime_seconds=90,
        )
        self.assertEqual(result["best_contact_route"]["type"], "generic_company")
        self.assertTrue(result["search_summary"]["named_person_search_attempted"])
        self.assertTrue(result["search_summary"]["generic_fallback_after_named_search"])

    def test_named_contact_can_score_high_with_public_named_email(self):
        first_query = tools.build_search_queries(
            sample_lead(),
            tools.merge_personas_for_lead(sample_lead()),
            max_search_queries=1,
        )[0]
        provider = FakeSearchProvider(
            {
                first_query: {
                    "url": "https://vsoneworld.lk/team",
                    "text": "Jane Perera - Head of Engineering jane.perera@vsoneworld.lk",
                }
            }
        )
        result = tools._resolve_contact_route_for_lead(
            sample_lead(),
            provider=provider,
            dry_run=True,
            max_search_queries=1,
            max_pages_to_fetch=2,
            max_candidate_contacts=5,
            max_runtime_seconds=90,
        )
        self.assertEqual(result["best_contact_route"]["type"], "named_person")
        self.assertGreaterEqual(result["best_contact_route"]["confidence"], 80)


if __name__ == "__main__":
    unittest.main()
