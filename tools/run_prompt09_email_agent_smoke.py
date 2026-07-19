"""PROMPT#09 local smoke runner for the ADK Gmail sender tool."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sl_trigger_leads.tools.gmail_sender_tools import (
    REAL_SEND_DISABLED_REFUSAL,
    send_hello_nilhan_test_email,
)

LOG_PATH = ROOT / "logs" / "PROMPT#09_email_agent.log"
DRY_RUN_OUTPUT_PATH = ROOT / "outputs" / "PROMPT#09_email_agent_dry_run.json"
SEND_RESULT_OUTPUT_PATH = ROOT / "outputs" / "PROMPT#09_email_agent_send_result.json"


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def log_safe(event: str, **fields: Any) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": utc_now(), "event": event, **fields}
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run_dry_run() -> int:
    result = send_hello_nilhan_test_email(dry_run=True, confirm_send=False)
    write_json(DRY_RUN_OUTPUT_PATH, result)
    log_safe(
        "dry_run",
        recipient=result["recipient"],
        subject=result["subject"],
        sent=result["sent"],
        dry_run=result["dry_run"],
        refusal_reason=result["refusal_reason"],
        output=str(DRY_RUN_OUTPUT_PATH),
    )
    if result["error"]:
        print(f"DRY-RUN FAILED: {result['error']}", file=sys.stderr)
        return 1
    print(f"DRY-RUN OK: no email sent. Wrote {DRY_RUN_OUTPUT_PATH}")
    return 0


def run_send() -> int:
    result = send_hello_nilhan_test_email(dry_run=False, confirm_send=True)
    write_json(SEND_RESULT_OUTPUT_PATH, result)
    if result["error"]:
        log_safe(
            "send_failed",
            recipient=result["recipient"],
            subject=result["subject"],
            sent=result["sent"],
            dry_run=result["dry_run"],
            refusal_reason=result["refusal_reason"],
            output=str(SEND_RESULT_OUTPUT_PATH),
        )
        print(f"SEND FAILED: {result['error']}", file=sys.stderr)
        return 1
    if result["sent"] or result["refusal_reason"] != REAL_SEND_DISABLED_REFUSAL:
        log_safe(
            "unexpected_send_result",
            recipient=result["recipient"],
            subject=result["subject"],
            sent=result["sent"],
            dry_run=result["dry_run"],
            refusal_reason=result["refusal_reason"],
            output=str(SEND_RESULT_OUTPUT_PATH),
        )
        print("SEND FAILED: Gmail sender returned an unexpected result.", file=sys.stderr)
        return 1
    log_safe(
        "send_refused",
        recipient=result["recipient"],
        subject=result["subject"],
        sent=result["sent"],
        dry_run=result["dry_run"],
        refusal_reason=result["refusal_reason"],
        output=str(SEND_RESULT_OUTPUT_PATH),
    )
    print(
        "Real Gmail sending is disabled; the public mailbox values are reserved placeholders."
    )
    return 2


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PROMPT#09 ADK email tool smoke")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_true", help="Dry-run the ADK test email"
    )
    mode.add_argument(
        "--send", action="store_true", help="Send after exact confirmation"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    if args.send:
        return run_send()
    return run_dry_run()


if __name__ == "__main__":
    raise SystemExit(main())
