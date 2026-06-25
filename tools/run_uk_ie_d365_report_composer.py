"""Run the UK/IE D365 evidence-safe report composer workflow.

The command is local-first. It creates JSON, Markdown, HTML, PDF, source map,
browse log, QA, and secret-scan artifacts under Evidence by default. Live AI or
public browsing is allowed only when explicitly requested and the Google project
guard passes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from uk_ie_d365_leads.tools import report_composer_tools as composer  # noqa: E402


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--requirement", required=True, help="Live user report requirement.")
    p.add_argument("--input-pack", required=True, help="Vetted lead/evidence JSON pack.")
    p.add_argument("--output-basename", required=True, help="Basename for Evidence outputs.")
    p.add_argument("--output-dir", default=str(composer.EVIDENCE_DIR))
    p.add_argument("--source-checks", default=None)
    p.add_argument("--style-reference-pdf", default=None)
    p.add_argument("--extra-evidence", action="append", default=[])
    p.add_argument("--live-ai", action="store_true")
    p.add_argument("--live-browse", action="store_true")
    p.add_argument("--required-project", default=None)
    p.add_argument("--model", default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    package = composer.build_report_composer_package(
        requirement=args.requirement,
        input_pack=args.input_pack,
        output_basename=args.output_basename,
        output_dir=args.output_dir,
        source_checks=args.source_checks,
        style_reference_pdf=args.style_reference_pdf,
        extra_evidence=args.extra_evidence,
        live_ai=args.live_ai,
        live_browse=args.live_browse,
        required_project=args.required_project,
        model=args.model,
    )
    print(json.dumps(package["artifacts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
