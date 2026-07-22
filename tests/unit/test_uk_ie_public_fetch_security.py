from __future__ import annotations

import socket
import urllib.error
from collections.abc import Iterator
from typing import Any
from unittest.mock import Mock

import pytest

from business_intel import public_http
from uk_ie_d365_leads.tools import lead_tools, report_composer_tools


def public_dns(host: str, port: int, **_kwargs: Any) -> list[tuple[Any, ...]]:
    if host in {"public.test", "next-public.test"}:
        address = "93.184.216.34"
    elif host == "private-dns.test":
        address = "10.0.0.7"
    else:
        address = host
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]


class FakeRequestsResponse:
    def __init__(
        self,
        *,
        url: str,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        chunks: list[bytes] | None = None,
        encoding: str | None = "utf-8",
    ) -> None:
        self.url = url
        self.status_code = status_code
        self.headers = headers or {"content-type": "text/plain; charset=utf-8"}
        self.chunks = chunks or []
        self.encoding = encoding
        self.closed = False
        self.reason = "OK"

    @property
    def status(self) -> int:
        return self.status_code

    def getheader(self, name: str) -> str | None:
        for key, value in self.headers.items():
            if key.lower() == name.lower():
                return value
        return None

    def read(self, limit: int) -> bytes:
        data = b"".join(self.chunks)
        chunk = data[:limit]
        remainder = data[limit:]
        self.chunks = [remainder] if remainder else []
        return chunk

    def iter_content(self, *, chunk_size: int) -> Iterator[bytes]:
        del chunk_size
        yield from self.chunks

    def close(self) -> None:
        self.closed = True


class FakeConnection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    ("url", "expected_status"),
    [
        ("http://127.0.0.1/private", "skipped_non_http_source"),
        ("http://169.254.169.254/latest/meta-data", "skipped_unsafe_source"),
        ("https://private-dns.test/internal", "skipped_unsafe_source"),
        ("https://user:secret@public.test/story", "skipped_unsafe_source"),
        ("file:///etc/passwd", "skipped_non_http_source"),
    ],
)
def test_source_fetcher_rejects_non_public_destinations_before_request(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
    expected_status: str,
) -> None:
    request = Mock(side_effect=AssertionError("unsafe URL reached requests"))
    monkeypatch.setattr(public_http.socket, "getaddrinfo", public_dns)
    monkeypatch.setattr(public_http, "_open_pinned_response", request)

    result = lead_tools.SourceFetcher().fetch(url, provider="unit")

    assert result["source_fetch_status"] == expected_status
    assert result["verified_live"] is False
    request.assert_not_called()


def test_source_fetcher_returns_structured_network_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        lead_tools,
        "fetch_public_url_requests",
        Mock(side_effect=urllib.error.URLError("connection refused")),
    )

    result = lead_tools.SourceFetcher().fetch(
        "https://public.test/unavailable", provider="unit"
    )

    assert result["source_fetch_status"] == "fetch_error"
    assert result["verified_live"] is False
    assert "connection refused" in result["fetch_error"]


def test_source_fetcher_blocks_private_redirect_before_second_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redirect = FakeRequestsResponse(
        url="https://public.test/start",
        status_code=302,
        headers={"location": "http://169.254.169.254/latest/meta-data"},
    )
    connection = FakeConnection()
    request = Mock(return_value=(redirect, connection))
    monkeypatch.setattr(public_http.socket, "getaddrinfo", public_dns)
    monkeypatch.setattr(public_http, "_open_pinned_response", request)

    result = lead_tools.SourceFetcher().fetch("https://public.test/start", provider="unit")

    assert result["source_fetch_status"] == "skipped_unsafe_source"
    assert result["verified_live"] is False
    assert request.call_count == 1
    assert request.call_args.args[1] == "93.184.216.34"
    assert redirect.closed is True
    assert connection.closed is True


def test_source_fetcher_manually_follows_public_redirect_within_byte_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redirect = FakeRequestsResponse(
        url="https://public.test/start",
        status_code=302,
        headers={"location": "https://next-public.test/story"},
    )
    final = FakeRequestsResponse(
        url="https://next-public.test/story",
        chunks=[b"hello", b" world"],
    )
    redirect_connection = FakeConnection()
    final_connection = FakeConnection()
    request = Mock(
        side_effect=[
            (redirect, redirect_connection),
            (final, final_connection),
        ]
    )
    monkeypatch.setattr(public_http.socket, "getaddrinfo", public_dns)
    monkeypatch.setattr(public_http, "_open_pinned_response", request)

    result = lead_tools.SourceFetcher(max_bytes=11).fetch(
        "https://public.test/start", provider="unit"
    )

    assert result["source_fetch_status"] == "fetched"
    assert result["final_url"] == "https://next-public.test/story"
    assert result["text_excerpt"] == "hello world"
    assert result["verified_live"] is True
    assert request.call_count == 2
    assert redirect.closed is True
    assert final.closed is True
    assert redirect_connection.closed is True
    assert final_connection.closed is True


def test_requests_adapter_enforces_redirect_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = FakeRequestsResponse(
        url="https://public.test/one",
        status_code=302,
        headers={"location": "https://next-public.test/two"},
    )
    second = FakeRequestsResponse(
        url="https://next-public.test/two",
        status_code=302,
        headers={"location": "https://public.test/three"},
    )
    first_connection = FakeConnection()
    second_connection = FakeConnection()
    request = Mock(
        side_effect=[
            (first, first_connection),
            (second, second_connection),
        ]
    )
    monkeypatch.setattr(public_http.socket, "getaddrinfo", public_dns)
    monkeypatch.setattr(public_http, "_open_pinned_response", request)

    with pytest.raises(public_http.PublicHTTPError, match="redirect limit"):
        lead_tools.fetch_public_url_requests(
            "https://public.test/one",
            headers={},
            timeout=12,
            max_bytes=100,
            pdf_max_bytes=100,
            allow_pdf=False,
            max_redirects=1,
        )

    assert request.call_count == 2
    assert first.closed is True
    assert second.closed is True


def test_source_fetcher_preserves_pdf_parsing_with_pdf_byte_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = FakeRequestsResponse(
        url="https://public.test/case-study.pdf",
        headers={"content-type": "application/pdf"},
        chunks=[b"123", b"456"],
        encoding=None,
    )
    parser = Mock(
        return_value={
            "parser_status": "pdf_text_extracted",
            "title": "Public case study",
            "page_count": 1,
            "text_excerpt": "Dynamics 365 public case study",
            "fetch_error": None,
        }
    )
    monkeypatch.setattr(public_http.socket, "getaddrinfo", public_dns)
    connection = FakeConnection()
    monkeypatch.setattr(
        public_http,
        "_open_pinned_response",
        Mock(return_value=(response, connection)),
    )
    monkeypatch.setattr(lead_tools, "extract_pdf_source_text", parser)

    result = lead_tools.SourceFetcher(
        max_bytes=2, pdf_max_bytes=6, parse_pdfs=True
    ).fetch("https://public.test/case-study.pdf", provider="unit")

    parser.assert_called_once_with(b"123456", "https://public.test/case-study.pdf")
    assert result["source_fetch_status"] == "fetched"
    assert result["verified_live"] is True
    assert result["pdf_parser_status"] == "pdf_text_extracted"


def test_report_composer_routes_fetch_through_hardened_urllib_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper = Mock(
        return_value=public_http.PublicHTTPResponse(
            url="https://next-public.test/story",
            status_code=200,
            headers={"content-type": "text/html; charset=utf-8"},
            body=b"<html><body>Dynamics 365 public evidence</body></html>",
        )
    )
    monkeypatch.setattr(report_composer_tools, "fetch_public_http", helper)

    result = report_composer_tools.fetch_public_source("https://public.test/start")

    assert result["verified_live"] is True
    assert result["final_url"] == "https://next-public.test/story"
    assert result["text_excerpt"] == "Dynamics 365 public evidence"
    helper.assert_called_once()
    assert helper.call_args.kwargs["max_body_bytes"] == 250_000


def test_report_composer_rejects_metadata_destination_without_opening(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opener = Mock(side_effect=AssertionError("unsafe URL reached network connection"))
    monkeypatch.setattr(public_http, "_open_pinned_response", opener)

    result = report_composer_tools.fetch_public_source(
        "http://169.254.169.254/latest/meta-data"
    )

    assert result["verified_live"] is False
    assert "non-public address" in result["fetch_error"]
    opener.assert_not_called()
