"""PROMPT#08 Gmail API sender smoke test.

Default mode is dry-run. The real send path requires the exact terminal
confirmation phrase and only allows the single requested test recipient.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sl_trigger_leads.tools.gmail_sender_tools import (
    ALLOWED_TEST_RECIPIENT,
    GMAIL_CREDENTIALS_PATH,
    GMAIL_SEND_SCOPE,
    GMAIL_TOKEN_PATH,
    HELLO_NILHAN_SUBJECT,
    TEST_SENDER,
    send_fixed_test_email,
    validate_oauth_client_file,
)

LOG_PATH = ROOT / "logs" / "PROMPT#08_gmail_sender_smoke.log"
DRY_RUN_OUTPUT_PATH = ROOT / "outputs" / "PROMPT#08_gmail_sender_dry_run.json"

BODY = "Hello Nilhan, this is a test email from the Business_Intel Gmail sender."
CONFIRMATION_PHRASE = "SEND_TO_NILHAN"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_safe(event: str, **fields: Any) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": utc_now(), "event": event, **fields}
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def dry_run() -> int:
    client_type = validate_oauth_client_file()
    result = send_fixed_test_email(body=BODY, dry_run=True, confirm_send=False)
    if result["error"]:
        raise RuntimeError(result["error"])

    payload = {
        "mode": "dry-run",
        "send_attempted": False,
        "recipient": ALLOWED_TEST_RECIPIENT,
        "sender": TEST_SENDER,
        "subject": HELLO_NILHAN_SUBJECT,
        "body": BODY,
        "gmail_scope": GMAIL_SEND_SCOPE,
        "credentials_path_exists": GMAIL_CREDENTIALS_PATH.is_file(),
        "token_path_exists": GMAIL_TOKEN_PATH.is_file(),
        "oauth_client_type": client_type,
        "mime_created": result["mime_created"],
        "mime_headers": {
            "to": ALLOWED_TEST_RECIPIENT,
            "from": TEST_SENDER,
            "subject": HELLO_NILHAN_SUBJECT,
        },
        "encoded_message_bytes": result["encoded_message_bytes"],
        "body_sha256": hashlib.sha256(BODY.encode("utf-8")).hexdigest(),
        "created_at": utc_now(),
    }
    DRY_RUN_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DRY_RUN_OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    log_safe(
        "dry_run_passed",
        recipient=ALLOWED_TEST_RECIPIENT,
        subject=HELLO_NILHAN_SUBJECT,
        send_attempted=False,
        mime_created=result["mime_created"],
        output=str(DRY_RUN_OUTPUT_PATH),
    )
    print(f"DRY-RUN OK: no email sent. Wrote {DRY_RUN_OUTPUT_PATH}")
    return 0


def send() -> int:
    print("About to send exactly one Gmail API test email.")
    print(f"From: {TEST_SENDER}")
    print(f"To: {ALLOWED_TEST_RECIPIENT}")
    print(f"Subject: {HELLO_NILHAN_SUBJECT}")
    print("Body:")
    print(BODY)
    try:
        confirmation = input("Type SEND_TO_NILHAN to send this test email: ")
    except EOFError:
        confirmation = ""

    if confirmation != CONFIRMATION_PHRASE:
        log_safe(
            "send_refused",
            recipient=ALLOWED_TEST_RECIPIENT,
            subject=HELLO_NILHAN_SUBJECT,
            reason="missing_or_incorrect_confirmation",
            send_attempted=False,
        )
        print("Confirmation not provided exactly. No email sent.")
        return 2

    result = send_fixed_test_email(body=BODY, dry_run=False, confirm_send=True)
    if not result["sent"]:
        log_safe(
            "send_failed",
            recipient=ALLOWED_TEST_RECIPIENT,
            subject=HELLO_NILHAN_SUBJECT,
            error=result["error"],
            refusal_reason=result["refusal_reason"],
            send_attempted=False,
        )
        print(f"SEND FAILED: {result['error'] or result['refusal_reason']}")
        return 1

    log_safe(
        "send_passed",
        recipient=ALLOWED_TEST_RECIPIENT,
        subject=HELLO_NILHAN_SUBJECT,
        send_attempted=True,
        gmail_message_id=result["gmail_message_id"],
    )
    print(f"SEND OK: Gmail message ID {result['gmail_message_id']}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PROMPT#08 Gmail sender smoke test")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Validate without sending")
    mode.add_argument("--send", action="store_true", help="Send after exact confirmation")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        if args.send:
            return send()
        return dry_run()
    except Exception as exc:
        log_safe(
            "failed",
            recipient=ALLOWED_TEST_RECIPIENT,
            subject=HELLO_NILHAN_SUBJECT,
            error_type=type(exc).__name__,
            send_attempted=False,
        )
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
