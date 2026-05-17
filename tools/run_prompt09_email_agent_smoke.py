"""PROMPT#09 local smoke runner for the ADK Gmail sender tool."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sl_trigger_leads.tools.gmail_sender_tools import send_hello_nilhan_test_email

LOG_PATH = ROOT / "logs" / "PROMPT#09_email_agent.log"
DRY_RUN_OUTPUT_PATH = ROOT / "outputs" / "PROMPT#09_email_agent_dry_run.json"
SEND_RESULT_OUTPUT_PATH = ROOT / "outputs" / "PROMPT#09_email_agent_send_result.json"
CONFIRMATION_PHRASE = "SEND_TO_NILHAN_ADK"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    print("About to send the ADK Hello Nilhan test email.")
    print("From: nilhan.d@1billiontech.com")
    print("To: nilhan@gmail.com")
    print("Subject: Hello Nilhan from Business Intel")
    print("Body:")
    print("Hello Nilhan, this is a test email from the Business_Intel ADK email sender agent.")
    try:
        confirmation = input("Type SEND_TO_NILHAN_ADK to send this test email: ")
    except EOFError:
        confirmation = ""
    if confirmation != CONFIRMATION_PHRASE:
        result = send_hello_nilhan_test_email(dry_run=False, confirm_send=False)
        log_safe(
            "send_refused",
            recipient=result["recipient"],
            subject=result["subject"],
            sent=result["sent"],
            dry_run=result["dry_run"],
            refusal_reason="missing_or_incorrect_terminal_confirmation",
        )
        print("Confirmation not provided exactly. No email sent.")
        return 2

    result = send_hello_nilhan_test_email(dry_run=False, confirm_send=True)
    if result["sent"]:
        write_json(SEND_RESULT_OUTPUT_PATH, result)
    log_safe(
        "send_result",
        recipient=result["recipient"],
        subject=result["subject"],
        sent=result["sent"],
        dry_run=result["dry_run"],
        gmail_message_id=result["gmail_message_id"],
        refusal_reason=result["refusal_reason"],
        output=str(SEND_RESULT_OUTPUT_PATH) if result["sent"] else None,
    )
    if not result["sent"]:
        print(f"SEND FAILED: {result['error'] or result['refusal_reason']}", file=sys.stderr)
        return 1
    print(f"SEND OK: Gmail message ID {result['gmail_message_id']}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PROMPT#09 ADK email tool smoke")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Dry-run the ADK test email")
    mode.add_argument("--send", action="store_true", help="Send after exact confirmation")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    if args.send:
        return run_send()
    return run_dry_run()


if __name__ == "__main__":
    raise SystemExit(main())
