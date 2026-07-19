import inspect
import unittest
from unittest.mock import patch

from sl_trigger_leads.tools import live_contact_search_tools as live_tools


class LiveContactSearchToolsTest(unittest.TestCase):
    def test_contact_search_model_is_built_off_the_async_event_loop(self):
        source = inspect.getsource(live_tools._run_contact_search_agent)
        self.assertIn("await asyncio.to_thread(contact_search_model)", source)

    def test_contact_search_agent_uses_command_scoped_credentials(self):
        credentials = object()
        with (
            patch.dict(
                "os.environ",
                {
                    "D365_GOOGLE_PROJECT": "business-intel-123",
                    "GOOGLE_CLOUD_LOCATION": "global",
                },
                clear=False,
            ),
            patch.object(live_tools, "gcloud_account_credentials", return_value=credentials),
        ):
            model = live_tools.contact_search_model()

        self.assertEqual(model.client_kwargs["credentials"], credentials)
        self.assertEqual(model.client_kwargs["project"], "business-intel-123")

    def test_adk_google_search_provider_discovery(self):
        discovery = live_tools.adk_google_search_discovery()
        self.assertIn("available", discovery)
        self.assertIn("provider", discovery)
        if discovery["available"]:
            self.assertEqual(discovery["provider"], "adk_google_search")

    def test_provider_unavailable_message_is_explicit(self):
        provider = live_tools.ProviderUnavailable("missing provider")
        self.assertFalse(provider.configured)
        self.assertEqual(provider.unavailable_reason, "missing provider")
        self.assertEqual(provider.search_web("test", limit=1), [])

    def test_parse_google_search_json_results(self):
        text = '[{"title":"VS ONE WORLD","url":"https://www.vsoneworld.com","snippet":"Enterprise solutions"}]'
        results = live_tools.parse_search_results(text, limit=3, source="adk_google_search")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].url, "https://www.vsoneworld.com")
        self.assertEqual(results[0].source, "adk_google_search")

    def test_parse_google_search_dict_url_result(self):
        text = '{"official_website":"http://www.vsoneworld.com"}'
        results = live_tools.parse_search_results(text, limit=3, source="adk_google_search")
        self.assertEqual(results[0].url, "http://www.vsoneworld.com")

    def test_normalize_public_url_adds_https(self):
        self.assertEqual(
            live_tools.normalize_public_url("www.innovay.com/"),
            "https://www.innovay.com/",
        )
        self.assertEqual(
            live_tools.normalize_public_url("vsoneworld.com/contact"),
            "https://vsoneworld.com/contact",
        )
        self.assertEqual(
            live_tools.normalize_public_url("https://www.vsoneworld.com/contact"),
            "https://www.vsoneworld.com/contact",
        )

    def test_parse_search_results_normalizes_scheme_less_urls(self):
        text = '[{"title":"Innovay","url":"www.innovay.com/","snippet":"Contact"}]'
        results = live_tools.parse_search_results(text, limit=3, source="adk_google_search")
        self.assertEqual(results[0].url, "https://www.innovay.com/")

    def test_page_fetch_rejects_malformed_urls(self):
        fetcher = live_tools.RequestsPageFetcher()
        result = fetcher.fetch_page("not a url")
        self.assertIsNone(result.status_code)
        self.assertIn("rejected_malformed_url", result.error)

    def test_page_fetch_result_shape(self):
        result = live_tools.PageFetchResult(
            url="https://example.com",
            status_code=200,
            text="Contact",
            error=None,
        )
        self.assertEqual(result.status_code, 200)

    def test_contact_route_shape(self):
        route = live_tools.ContactRoute(
            route_type="generic_company",
            name=None,
            role="Company contact inbox",
            email="info@example.com",
            url="https://example.com/contact",
            confidence=45,
            confidence_label="Low",
            evidence_urls=["https://example.com/contact"],
            why="Generic fallback.",
            source="official_company",
        )
        self.assertEqual(route.route_type, "generic_company")

    def test_hunter_not_configured_without_key(self):
        provider = live_tools.HunterContactEnrichmentProvider(api_key="")
        result = provider.domain_search("vsoneworld.com")
        self.assertEqual(result.status, live_tools.HUNTER_NOT_CONFIGURED)
        self.assertEqual(result.emails, [])

    def test_hunter_email_finder_requires_named_person(self):
        provider = live_tools.HunterContactEnrichmentProvider(api_key="unused")
        result = provider.email_finder(domain="vsoneworld.com", full_name="")
        self.assertEqual(result.status, live_tools.HUNTER_NOT_FOUND)
        self.assertEqual(result.error, "real_named_person_and_domain_required")

    def test_hunter_status_from_verification(self):
        self.assertEqual(
            live_tools.hunter_status_from_verification("valid", has_email=True),
            live_tools.HUNTER_VERIFIED,
        )
        self.assertEqual(
            live_tools.hunter_status_from_verification("unknown", has_email=True),
            live_tools.HUNTER_FOUND,
        )
        self.assertEqual(
            live_tools.hunter_status_from_verification("invalid", has_email=True),
            live_tools.HUNTER_NOT_FOUND,
        )
        self.assertEqual(
            live_tools.hunter_status_from_verification(None, has_email=False),
            live_tools.HUNTER_NOT_FOUND,
        )

    def test_hunter_domain_and_source_normalization(self):
        self.assertEqual(live_tools.normalize_company_domain("https://www.vsoneworld.com/contact"), "vsoneworld.com")
        self.assertEqual(live_tools.normalize_company_domain("www.innovay.com/"), "innovay.com")
        self.assertEqual(
            live_tools.hunter_source_urls([{"uri": "www.innovay.com/contact"}]),
            ["https://www.innovay.com/contact"],
        )


if __name__ == "__main__":
    unittest.main()
