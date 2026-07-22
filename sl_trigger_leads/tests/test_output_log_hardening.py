from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sl_trigger_leads.tools import cloud_ops_tools as cloud_ops
from sl_trigger_leads.tools import live_source_tools as live_source
from sl_trigger_leads.tools import opportunity_analysis_tools as opportunity


def _valid_live_lead(company: str) -> dict[str, object]:
    return {
        "company": company,
        "country": "Sri Lanka",
        "sector": "software",
        "trigger_type": "hiring_spike",
        "evidence_url": "https://wso2.com/careers/",
        "evidence_excerpt": "Public hiring signal for software engineers.",
        "source_name": "WSO2 Careers",
        "published_or_seen_date": "2026-07-22",
        "fetched_at": "2026-07-22T00:00:00+00:00",
        "score": {"total": 70, "verdict": "Verify contact first"},
        "outreach_angle": "Verify the need before outreach.",
        "limits": "Public evidence only.",
        "verified_live": True,
    }


class OutputAndLogHardeningTest(unittest.TestCase):
    def test_live_export_is_contained_atomic_and_formula_safe(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            output_root = Path(raw_temp) / "outputs"
            output_root.mkdir()
            input_path = output_root / "live.json"
            input_path.write_text(
                json.dumps({"leads": [_valid_live_lead(" \t=HYPERLINK(\"https://evil.invalid\")")]}),
                encoding="utf-8",
            )

            with (
                mock.patch.object(live_source, "OUTPUT_DIR", output_root),
                mock.patch.object(live_source.os, "replace", wraps=live_source.os.replace) as replace,
            ):
                result = live_source.export_live_leads_csv("live.json", "nested/live.csv")

            csv_path = output_root / "nested" / "live.csv"
            self.assertEqual(result["csv_path"], str(csv_path.resolve()))
            self.assertEqual(result["row_count"], 1)
            self.assertTrue(replace.called)
            with csv_path.open(encoding="utf-8", newline="") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["company"], "' \t=HYPERLINK(\"https://evil.invalid\")")

    def test_live_export_rejects_outside_traversal_and_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp_root = Path(raw_temp)
            output_root = temp_root / "outputs"
            outside_root = temp_root / "outside"
            output_root.mkdir()
            outside_root.mkdir()
            inside_json = output_root / "live.json"
            inside_json.write_text('{"leads": []}', encoding="utf-8")
            outside_json = outside_root / "live.json"
            outside_json.write_text('{"leads": []}', encoding="utf-8")

            with mock.patch.object(live_source, "OUTPUT_DIR", output_root):
                with self.assertRaises(ValueError):
                    live_source.export_live_leads_csv(str(outside_json), "safe.csv")
                with self.assertRaises(ValueError):
                    live_source.export_live_leads_csv("live.json", str(outside_root / "escape.csv"))
                with self.assertRaises(ValueError):
                    live_source.export_live_leads_csv("live.json", "../escape.csv")

                symlink = output_root / "linked-outside"
                try:
                    symlink.symlink_to(outside_root, target_is_directory=True)
                except OSError:
                    symlink_created = False
                else:
                    symlink_created = True
                if symlink_created:
                    with self.assertRaises(ValueError):
                        live_source.export_live_leads_csv(
                            "live.json", "linked-outside/escape.csv"
                        )

            self.assertFalse((outside_root / "escape.csv").exists())

    def test_opportunity_export_is_contained_atomic_and_formula_safe(self) -> None:
        dangerous = ["=one", "+two", "-three", "@four", " \t=five"]
        analyses = [{"company": value} for value in dangerous]
        with tempfile.TemporaryDirectory() as raw_temp:
            output_root = Path(raw_temp) / "outputs"
            output_root.mkdir()
            with (
                mock.patch.object(opportunity, "OUTPUT_DIR", output_root),
                mock.patch.object(opportunity.os, "replace", wraps=opportunity.os.replace) as replace,
            ):
                result = opportunity.export_opportunity_analyses_csv(analyses, "reviews/analysis.csv")

            csv_path = output_root / "reviews" / "analysis.csv"
            self.assertEqual(result["csv_path"], str(csv_path.resolve()))
            self.assertTrue(replace.called)
            with csv_path.open(encoding="utf-8", newline="") as handle:
                companies = [row["company"] for row in csv.DictReader(handle)]
            self.assertEqual(companies, [f"'{value}" for value in dangerous])

            outside = Path(raw_temp) / "outside.csv"
            with mock.patch.object(opportunity, "OUTPUT_DIR", output_root):
                with self.assertRaises(ValueError):
                    opportunity.export_opportunity_analyses_csv([], str(outside))
                with self.assertRaises(ValueError):
                    opportunity.export_opportunity_analyses_csv([], "../outside.csv")
                outside_root = Path(raw_temp) / "outside"
                outside_root.mkdir()
                symlink = output_root / "linked-outside"
                try:
                    symlink.symlink_to(outside_root, target_is_directory=True)
                except OSError:
                    symlink_created = False
                else:
                    symlink_created = True
                if symlink_created:
                    with self.assertRaises(ValueError):
                        opportunity.export_opportunity_analyses_csv(
                            [],
                            "linked-outside/analysis.csv",
                        )
            self.assertFalse(outside.exists())

    def test_atomic_replace_failure_preserves_existing_export(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            output_root = Path(raw_temp) / "outputs"
            output_root.mkdir()
            input_path = output_root / "live.json"
            input_path.write_text('{"leads": []}', encoding="utf-8")
            csv_path = output_root / "live.csv"
            csv_path.write_text("ORIGINAL\n", encoding="utf-8")

            with (
                mock.patch.object(live_source, "OUTPUT_DIR", output_root),
                mock.patch.object(live_source.os, "replace", side_effect=OSError("replace blocked")),
            ):
                with self.assertRaisesRegex(OSError, "replace blocked"):
                    live_source.export_live_leads_csv("live.json", "live.csv")

            self.assertEqual(csv_path.read_text(encoding="utf-8"), "ORIGINAL\n")
            self.assertEqual(list(output_root.glob(".live-*.tmp")), [])

    def test_runtime_log_search_returns_metadata_without_payload_previews(self) -> None:
        response = {
            "status": "OK",
            "payload": {
                "entries": [
                    {
                        "timestamp": "2026-07-22T00:00:00Z",
                        "logName": "projects/test/logs/runtime",
                        "severity": "ERROR",
                        "resource": {"type": "aiplatform.googleapis.com/ReasoningEngine"},
                        "jsonPayload": {
                            "email": "private.person@corp.test",
                            "message": "CONFIDENTIAL_LOG_CANARY",
                        },
                    },
                    {
                        "timestamp": "2026-07-22T00:01:00Z",
                        "logName": "projects/test/logs/runtime",
                        "severity": "INFO",
                        "resource": {"type": "aiplatform.googleapis.com/ReasoningEngine"},
                        "textPayload": "SECOND_PRIVATE_CANARY",
                    },
                ]
            },
        }
        with (
            mock.patch.object(cloud_ops, "_google_access_token", return_value={"status": "OK", "token": "test"}),
            mock.patch.object(cloud_ops, "_google_json_post", return_value=response),
        ):
            result = cloud_ops.search_runtime_logs("HUNTER", limit=20)

        serialized = json.dumps(result)
        self.assertEqual(result["result_count"], 2)
        self.assertEqual(result["returned_count"], 2)
        self.assertEqual(result["severity_counts"], {"ERROR": 1, "INFO": 1})
        self.assertEqual(result["entries"][0]["severity"], "ERROR")
        self.assertNotIn("text_preview", serialized)
        self.assertNotIn("jsonPayload", serialized)
        self.assertNotIn("textPayload", serialized)
        self.assertNotIn("PRIVATE", serialized)
        self.assertNotIn("CONFIDENTIAL_LOG_CANARY", serialized)


if __name__ == "__main__":
    unittest.main()
