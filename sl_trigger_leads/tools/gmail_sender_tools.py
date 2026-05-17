"""Local OAuth Gmail sender tools for the locked PROMPT#09 test mode."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SECRETS_DIR = PROJECT_ROOT / ".local_secrets"
GMAIL_CREDENTIALS_PATH = SECRETS_DIR / "gmail_sender_credentials.json"
GMAIL_TOKEN_PATH = SECRETS_DIR / "gmail_sender_token.json"

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GMAIL_SCOPES = [GMAIL_SEND_SCOPE]

TEST_SENDER = "nilhan.d@1billiontech.com"
ALLOWED_TEST_RECIPIENT = "nilhan@gmail.com"
HELLO_NILHAN_SUBJECT = "Hello Nilhan from Business Intel"
HELLO_NILHAN_ADK_BODY = (
    "Hello Nilhan, this is a test email from the Business_Intel ADK email sender agent."
)

LEAD_OUTREACH_REFUSAL = (
    "Lead outreach is not unlocked yet. This local Gmail sender can only send the "
    "single Hello Nilhan test email to nilhan@gmail.com."
)

CredentialLoader = Callable[[], Any]
GmailServiceFactory = Callable[[Any], Any]


def validate_allowed_recipient(recipient: str) -> None:
    """Raise when the requested recipient is outside the PROMPT#09 allowlist."""
    if recipient != ALLOWED_TEST_RECIPIENT:
        raise ValueError(f"Refusing recipient outside allowlist: {recipient}")


def build_plain_text_mime(
    *,
    sender: str,
    recipient: str,
    subject: str,
    body: str,
) -> EmailMessage:
    """Build the plain-text MIME message used by Gmail API sends."""
    validate_allowed_recipient(recipient)
    message = EmailMessage()
    message["To"] = recipient
    message["From"] = sender
    message["Subject"] = subject
    message.set_content(body)
    return message


def encode_message_base64url(message: EmailMessage) -> str:
    """Return a Gmail API raw message payload."""
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")


def validate_oauth_client_file(credentials_path: Path = GMAIL_CREDENTIALS_PATH) -> str:
    """Validate the local OAuth client file without returning secret values."""
    if not credentials_path.is_file():
        raise FileNotFoundError(f"OAuth credential file not found: {credentials_path}")
    try:
        data = json.loads(credentials_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("OAuth credential file is not valid JSON.") from exc

    client_type = "installed" if "installed" in data else "web" if "web" in data else ""
    if not client_type:
        raise ValueError("OAuth credential JSON must contain an installed or web client.")
    client = data[client_type]
    required = ["client_id", "client_secret", "auth_uri", "token_uri"]
    missing = [key for key in required if not client.get(key)]
    if missing:
        raise ValueError(f"OAuth credential JSON is missing required keys: {missing}")
    return client_type


def load_or_create_gmail_credentials(
    *,
    credentials_path: Path = GMAIL_CREDENTIALS_PATH,
    token_path: Path = GMAIL_TOKEN_PATH,
) -> Credentials:
    """Load or refresh local OAuth credentials for the Gmail send-only scope."""
    credentials: Credentials | None = None
    if token_path.is_file():
        credentials = Credentials.from_authorized_user_file(str(token_path), GMAIL_SCOPES)

    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())

    if not credentials or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), GMAIL_SCOPES)
        credentials = flow.run_local_server(port=0, prompt="consent")

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json(), encoding="utf-8")
    return credentials


def _default_gmail_service_factory(credentials: Any) -> Any:
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def _send_raw_message(raw_message: str, service: Any) -> str | None:
    response = (
        service.users()
        .messages()
        .send(userId="me", body={"raw": raw_message})
        .execute()
    )
    return response.get("id")


def _base_result(*, dry_run: bool, recipient: str, subject: str, body: str) -> dict[str, Any]:
    return {
        "sent": False,
        "dry_run": dry_run,
        "from": TEST_SENDER,
        "recipient": recipient,
        "subject": subject,
        "body": body,
        "gmail_message_id": None,
        "error": None,
        "refusal_reason": None,
        "gmail_scope": GMAIL_SEND_SCOPE,
        "mime_created": False,
    }


def _safe_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def send_fixed_test_email(
    *,
    body: str,
    dry_run: bool = True,
    confirm_send: bool = False,
    subject: str = HELLO_NILHAN_SUBJECT,
    recipient: str = ALLOWED_TEST_RECIPIENT,
    credentials_loader: CredentialLoader | None = None,
    gmail_service_factory: GmailServiceFactory | None = None,
) -> dict[str, Any]:
    """Send or dry-run the fixed allowlisted test email.

    The tool never accepts arbitrary recipient input from ADK prompts. Injection
    arguments exist only for unit tests and smoke scripts.
    """
    result = _base_result(dry_run=dry_run, recipient=recipient, subject=subject, body=body)
    try:
        validate_allowed_recipient(recipient)
        message = build_plain_text_mime(
            sender=TEST_SENDER,
            recipient=recipient,
            subject=subject,
            body=body,
        )
        raw_message = encode_message_base64url(message)
        result["mime_created"] = True
        result["encoded_message_bytes"] = len(raw_message.encode("ascii"))

        if dry_run:
            result["refusal_reason"] = "dry_run_only_no_email_sent"
            return result

        if not confirm_send:
            result["refusal_reason"] = "confirmation_required_for_real_send"
            return result

        validate_oauth_client_file()
        loader = credentials_loader or load_or_create_gmail_credentials
        service_factory = gmail_service_factory or _default_gmail_service_factory
        credentials = loader()
        service = service_factory(credentials)
        result["gmail_message_id"] = _send_raw_message(raw_message, service)
        result["sent"] = True
        result["refusal_reason"] = None
        return result
    except Exception as exc:
        result["error"] = _safe_error(exc)
        result["refusal_reason"] = result["refusal_reason"] or "send_failed_or_refused"
        return result


def send_hello_nilhan_test_email(
    dry_run: bool = True,
    confirm_send: bool = False,
) -> dict[str, Any]:
    """Dry-run or send the single allowed Hello Nilhan ADK test email."""
    return send_fixed_test_email(
        body=HELLO_NILHAN_ADK_BODY,
        dry_run=dry_run,
        confirm_send=confirm_send,
    )


def describe_email_sender_restrictions() -> dict[str, Any]:
    """Return the currently active local Gmail sender restrictions."""
    return {
        "test_mode_only": True,
        "allowed_recipient": ALLOWED_TEST_RECIPIENT,
        "sender": TEST_SENDER,
        "gmail_scope": GMAIL_SEND_SCOPE,
        "bulk_send_enabled": False,
        "lead_outreach_enabled": False,
        "cloud_deployment_enabled": False,
        "credential_mode": "local_oauth_user_authorized",
        "secrets_are_returned": False,
    }


def refuse_lead_outreach_email(request_summary: str = "") -> dict[str, Any]:
    """Refuse lead/company/prospect email requests until outreach is unlocked."""
    return {
        "sent": False,
        "dry_run": True,
        "from": TEST_SENDER,
        "recipient": None,
        "subject": None,
        "gmail_message_id": None,
        "error": None,
        "refusal_reason": LEAD_OUTREACH_REFUSAL,
        "request_summary": request_summary,
    }
