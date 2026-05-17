import json
import unittest

from sl_trigger_leads.tools import contact_resolver_tools as tools


class FakeLiveProvider:
    name = "adk_google_search"
    configured = True
    unavailable_reason = None

    def __init__(self):
        self.searches = []
        self.pages = {
            "https://itpro.lk/job/13609/qe-engineer-api-integration-at-vs-one-world-pvt-ltd/": (
                "QE Engineer API Integration Apply for this job"
            ),
            "https://www.vsoneworld.com": "VS ONE WORLD enterprise solutions",
            "https://www.vsoneworld.com/contact": "Contact VS ONE WORLD at info@vsoneworld.com",
            "https://www.vsoneworld.com/careers": "Careers page",
            "https://www.vsoneworld.com/about": "About page",
            "https://www.vsoneworld.com/team": "",
            "https://www.vsoneworld.com/leadership": "",
            "https://www.vsoneworld.com/news": "",
        }

    def search_web(self, query, limit):
        self.searches.append(query)
        return [
            tools.SearchResult(
                title="VS ONE WORLD",
                url="https://www.vsoneworld.com",
                snippet="Official website for VS ONE WORLD.",
            )
        ]

    def fetch_page(self, url):
        return tools.PageText(url=url, text=self.pages.get(url, ""), source=self.name, fetched_at="200")

    def extract_emails(self, text):
        return tools.extract_emails(text)

    def extract_people_roles(self, text, company, target_personas):
        return tools.extract_people_roles(text, company, target_personas)


class FakeUnavailableProvider:
    name = "none"
    configured = False
    unavailable_reason = (
        "ADK google_search unavailable in this install. Configure GOOGLE_CSE_API_KEY and GOOGLE_CSE_CX."
    )

    def search_web(self, query, limit):
        return []

    def fetch_page(self, url):
        return tools.PageText(url=url, text="", source=self.name)

    def extract_emails(self, text):
        return []

    def extract_people_roles(self, text, company, target_personas):
        return []


def sample_lead():
    return tools.prompt10_sample_lead()


class ContactResolverLiveModeTest(unittest.TestCase):
    def test_live_mode_no_longer_defaults_to_dry_run(self):
        result = tools.resolve_contacts_for_leads([], max_leads=3)
        self.assertFalse(result["dry_run"])

    def test_no_contact_found_only_after_real_attempts(self):
        result = tools._resolve_contact_route_for_lead(
            sample_lead(),
            provider=FakeLiveProvider(),
            dry_run=False,
            max_search_queries=1,
            max_pages_to_fetch=1,
            max_candidate_contacts=5,
            max_runtime_seconds=120,
        )
        self.assertNotEqual(result["search_summary"]["stopped_reason"], "search_provider_not_configured")
        self.assertGreaterEqual(len(result["search_trace"]), 1)

    def test_generic_inbox_fallback_is_allowed_but_low_confidence(self):
        result = tools._resolve_contact_route_for_lead(
            sample_lead(),
            provider=FakeLiveProvider(),
            dry_run=False,
            max_search_queries=1,
            max_pages_to_fetch=4,
            max_candidate_contacts=5,
            max_runtime_seconds=120,
        )
        self.assertIn(result["best_contact_route"]["type"], {"generic_company", "contact_form", "job_post_apply"})
        self.assertLessEqual(result["best_contact_route"]["confidence"], 45)

    def test_job_post_apply_route_is_allowed_as_fallback(self):
        provider = FakeLiveProvider()
        provider.search_web = lambda query, limit: []
        result = tools._resolve_contact_route_for_lead(
            sample_lead(),
            provider=provider,
            dry_run=False,
            max_search_queries=1,
            max_pages_to_fetch=1,
            max_candidate_contacts=5,
            max_runtime_seconds=120,
        )
        self.assertEqual(result["best_contact_route"]["type"], "job_post_apply")

    def test_contact_form_route_is_allowed_as_fallback(self):
        provider = FakeLiveProvider()
        provider.pages["https://www.vsoneworld.com/contact"] = "Contact form"
        result = tools._resolve_contact_route_for_lead(
            sample_lead(),
            provider=provider,
            dry_run=False,
            max_search_queries=1,
            max_pages_to_fetch=3,
            max_candidate_contacts=5,
            max_runtime_seconds=120,
        )
        route_types = {candidate.get("route_type") for candidate in result["candidate_contacts"]}
        self.assertIn("contact_form", route_types)

    def test_named_relevant_person_outranks_generic_inbox(self):
        provider = FakeLiveProvider()
        provider.pages["https://www.vsoneworld.com"] = (
            "Jane Perera - Head of Engineering jane.perera@vsoneworld.com"
        )
        result = tools._resolve_contact_route_for_lead(
            sample_lead(),
            provider=provider,
            dry_run=False,
            max_search_queries=1,
            max_pages_to_fetch=2,
            max_candidate_contacts=5,
            max_runtime_seconds=120,
        )
        self.assertEqual(result["best_contact_route"]["type"], "named_person")
        self.assertGreater(result["best_contact_route"]["confidence"], 45)

    def test_search_budget_stops_properly(self):
        result = tools._resolve_contact_route_for_lead(
            sample_lead(),
            provider=FakeLiveProvider(),
            dry_run=False,
            max_search_queries=1,
            max_pages_to_fetch=1,
            max_candidate_contacts=5,
            max_runtime_seconds=120,
        )
        self.assertLessEqual(len(result["search_summary"]["queries_attempted"]), 1)
        self.assertLessEqual(len(result["search_summary"]["sources_checked"]), 1)

    def test_provider_unavailable_message_is_explicit(self):
        result = tools._resolve_contact_route_for_lead(
            sample_lead(),
            provider=FakeUnavailableProvider(),
            dry_run=False,
            max_search_queries=1,
            max_pages_to_fetch=1,
            max_candidate_contacts=5,
            max_runtime_seconds=120,
        )
        self.assertEqual(result["search_summary"]["stopped_reason"], "live_provider_unavailable")
        self.assertIn("Configure GOOGLE_CSE_API_KEY", result["search_summary"]["setup_message"])

    def test_no_sending_behavior_added(self):
        refusal = tools.refuse_contact_resolver_sending("send now")
        self.assertFalse(refusal["sending_enabled"])

    def test_search_trace_output_is_serializable(self):
        result = tools._resolve_contact_route_for_lead(
            sample_lead(),
            provider=FakeLiveProvider(),
            dry_run=False,
            max_search_queries=1,
            max_pages_to_fetch=1,
            max_candidate_contacts=5,
            max_runtime_seconds=120,
        )
        serialized = json.dumps(result["search_trace"])
        self.assertIn("seed_fetch", serialized)


if __name__ == "__main__":
    unittest.main()

