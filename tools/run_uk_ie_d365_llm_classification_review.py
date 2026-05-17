"""Run the UK/IE D365 LLM classification review harness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uk_ie_d365_leads.tools.classification_review_tools import (  # noqa: E402
    DEFAULT_EVIDENCE_FILE,
    EVIDENCE_DIR,
    build_live_review_package,
    build_review_package,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="UK/IE D365 LLM classification review")
    parser.add_argument("--live-llm", action="store_true", help="Run bounded Phase 2 Gemini/Vertex review")
    parser.add_argument("--max-candidates", type=int, default=20, help="Live review candidate cap")
    parser.add_argument("--model", default=None, help="Live review model override")
    parser.add_argument("--evidence-file", default=str(DEFAULT_EVIDENCE_FILE), help="Saved audit replay JSON")
    parser.add_argument("--output-dir", default=str(EVIDENCE_DIR), help="Evidence output directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.max_candidates <= 0:
        parser.error("--max-candidates must be greater than 0")

    command_log = [
        "python tools\\run_uk_ie_d365_llm_classification_review.py"
        + (" --live-llm" if args.live_llm else "")
        + f" --max-candidates {args.max_candidates}",
    ]
    if args.live_llm:
        package = build_live_review_package(
            evidence_file=Path(args.evidence_file),
            output_dir=Path(args.output_dir),
            max_candidates=args.max_candidates,
            model=args.model,
            command_log=command_log,
        )
        output = package["review_output"]
        summary = {
            "live_llm_mode_executed": True,
            "dry_run_mode_executed": False,
            "live_request_count": output["counts"]["live_request_count"],
            "candidates_loaded": output["counts"]["candidates_loaded"],
            "candidates_reviewed_by_llm": output["counts"]["candidates_reviewed_by_llm"],
            "llm_accept_count": output["counts"]["llm_accept_count"],
            "llm_provisional_count": output["counts"]["llm_provisional_count"],
            "llm_reject_count": output["counts"]["llm_reject_count"],
            "llm_discrepancy_count": output["counts"]["llm_discrepancy_count"],
            "suspected_false_negative_count": output["counts"]["suspected_false_negative_count"],
            "suspected_false_positive_count": output["counts"]["suspected_false_positive_count"],
            "model": output["metadata"]["model_used"],
            "provider_path": output["metadata"]["provider_path"],
            "project": output["metadata"]["project"],
            "location": output["metadata"]["location"],
            "token_usage": output["counts"]["token_usage"],
            "artifacts": package["artifacts"],
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    package = build_review_package(
        evidence_file=Path(args.evidence_file),
        output_dir=Path(args.output_dir),
        command_log=command_log,
    )
    output = package["review_output"]
    summary = {
        "dry_run_mode_executed": True,
        "live_llm_mode_executed": False,
        "live_request_count": 0,
        "candidates_loaded": output["counts"]["candidates_loaded"],
        "candidates_prepared_for_review": output["counts"]["candidates_prepared_for_review"],
        "candidates_reviewed_by_llm": 0,
        "schema_validation_result": output["metadata"]["schema_validation_result"],
        "invented_candidate_facts_check_result": output["metadata"]["invented_candidate_facts_check_result"],
        "artifacts": package["artifacts"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
