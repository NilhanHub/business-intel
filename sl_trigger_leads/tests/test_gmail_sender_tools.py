import base64
import json
import unittest
from unittest.mock import patch

from sl_trigger_leads.tools import gmail_sender_tools as tools


class _FakeSendCall:
    def execute(self):
        return {"id": "fake-message-id"}


class _FakeMessages:
    def __init__(self):
        self.sent_payloads = []

    def send(self, userId, body):
        self.sent_payloads.append({"userId": userId, "body": body})
        return _FakeSendCall()


class _FakeUsers:
    def __init__(self, messages):
        self._messages = messages

    def messages(self):
        return self._messages


class _FakeGmailService:
    def __init__(self):
        self.messages_resource = _FakeMessages()

    def users(self):
        return _FakeUsers(self.messages_resource)


class GmailSenderToolsTest(unittest.TestCase):
    def test_only_nilhan_gmail_is_allowed(self):
        tools.validate_allowed_recipient("nilhan@gmail.com")

    def test_other_recipients_are_refused(self):
        with self.assertRaises(ValueError):
            tools.validate_allowed_recipient("lead@example.com")

    def test_dry_run_does_not_call_gmail_api(self):
        def fail_factory(_credentials):
            raise AssertionError("Gmail API must not be called during dry-run")

        result = tools.send_fixed_test_email(
            body=tools.HELLO_NILHAN_ADK_BODY,
            dry_run=True,
            confirm_send=False,
            gmail_service_factory=fail_factory,
        )
        self.assertFalse(result["sent"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["refusal_reason"], "dry_run_only_no_email_sent")
        self.assertTrue(result["mime_created"])

    def test_real_send_requires_explicit_confirmation(self):
        def fail_factory(_credentials):
            raise AssertionError("Gmail API must not be called without confirmation")

        result = tools.send_fixed_test_email(
            body=tools.HELLO_NILHAN_ADK_BODY,
            dry_run=False,
            confirm_send=False,
            gmail_service_factory=fail_factory,
        )
        self.assertFalse(result["sent"])
        self.assertFalse(result["dry_run"])
        self.assertEqual(result["refusal_reason"], "confirmation_required_for_real_send")

    def test_mime_message_is_built_correctly(self):
        message = tools.build_plain_text_mime(
            sender=tools.TEST_SENDER,
            recipient=tools.ALLOWED_TEST_RECIPIENT,
            subject=tools.HELLO_NILHAN_SUBJECT,
            body=tools.HELLO_NILHAN_ADK_BODY,
        )
        self.assertEqual(message["To"], tools.ALLOWED_TEST_RECIPIENT)
        self.assertEqual(message["From"], tools.TEST_SENDER)
        self.assertEqual(message["Subject"], tools.HELLO_NILHAN_SUBJECT)
        self.assertIn(tools.HELLO_NILHAN_ADK_BODY, message.get_content())

    def test_raw_message_is_base64url_encoded(self):
        message = tools.build_plain_text_mime(
            sender=tools.TEST_SENDER,
            recipient=tools.ALLOWED_TEST_RECIPIENT,
            subject=tools.HELLO_NILHAN_SUBJECT,
            body=tools.HELLO_NILHAN_ADK_BODY,
        )
        raw = tools.encode_message_base64url(message)
        decoded = base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8")
        self.assertIn("To: nilhan@gmail.com", decoded)
        self.assertIn("Subject: Hello Nilhan from Business Intel", decoded)

    def test_token_and_secret_values_are_never_returned(self):
        fake_service = _FakeGmailService()

        with patch.object(tools, "validate_oauth_client_file", return_value="installed"):
            result = tools.send_fixed_test_email(
                body=tools.HELLO_NILHAN_ADK_BODY,
                dry_run=False,
                confirm_send=True,
                credentials_loader=lambda: object(),
                gmail_service_factory=lambda _credentials: fake_service,
            )

        self.assertTrue(result["sent"])
        self.assertEqual(result["gmail_message_id"], "fake-message-id")
        serialized = json.dumps(result).lower()
        for forbidden in ("access_token", "refresh_token", "client_secret", "token_uri"):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
