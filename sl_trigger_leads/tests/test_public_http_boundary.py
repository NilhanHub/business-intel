from __future__ import annotations

import socket
import threading
import time
import urllib.error
import urllib.request
from email.message import Message
from typing import Any

import pytest

from business_intel import public_http
from sl_trigger_leads.tools import (
    live_contact_search_tools,
    source_fetcher,
    source_health,
)


def _dns_result(address: str, port: int) -> list[tuple[Any, ...]]:
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    socket_address: tuple[Any, ...]
    if family == socket.AF_INET6:
        socket_address = (address, port, 0, 0)
    else:
        socket_address = (address, port)
    return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", socket_address)]


def _install_dns(
    monkeypatch: pytest.MonkeyPatch,
    addresses: dict[str, list[str]],
) -> None:
    def fake_getaddrinfo(
        host: str,
        port: int,
        *,
        family: int,
        type: int,
    ) -> list[tuple[Any, ...]]:
        del family, type
        return [
            record
            for address in addresses[host]
            for record in _dns_result(address, port)
        ]

    monkeypatch.setattr(public_http.socket, "getaddrinfo", fake_getaddrinfo)


class _FakeConnection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakeResponse:
    reason = "OK"

    def __init__(
        self,
        *,
        status: int = 200,
        body: bytes = b"",
        headers: Message | None = None,
    ) -> None:
        self.status = status
        self.headers = headers or Message()
        self._body = body
        self.closed = False
        self.read_limit: int | None = None

    def getheader(self, name: str) -> str | None:
        return self.headers.get(name)

    def read(self, limit: int) -> bytes:
        self.read_limit = limit
        chunk, self._body = self._body[:limit], self._body[limit:]
        return chunk

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    "url",
    [
        "ftp://public.test/file",
        "https://user:password@public.test/file",
        "http://metadata.google.internal/latest/meta-data",
        "http://localhost/admin",
    ],
)
def test_validate_public_url_rejects_non_public_url_forms(url: str) -> None:
    with pytest.raises(public_http.PublicHTTPError):
        public_http.validate_public_url(url)


def test_validate_public_url_rejects_private_and_mixed_dns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_dns(
        monkeypatch,
        {
            "private.test": ["10.20.30.40"],
            "mixed.test": ["93.184.216.34", "127.0.0.1"],
        },
    )

    with pytest.raises(public_http.PublicHTTPError, match="non-public"):
        public_http.validate_public_url("https://private.test/resource")
    with pytest.raises(public_http.PublicHTTPError, match="non-public"):
        public_http.validate_public_url("https://mixed.test/resource")


@pytest.mark.parametrize(
    "address",
    [
        "10.0.0.1",
        "127.0.0.1",
        "169.254.1.1",
        "224.0.0.1",
        "240.0.0.1",
        "0.0.0.0",
        "::1",
        "fe80::1",
        "ff02::1",
        "::",
        "64:ff9b::7f00:1",
        "2002:0a00:0001::",
    ],
)
def test_validate_public_url_rejects_each_non_public_address_class(
    monkeypatch: pytest.MonkeyPatch,
    address: str,
) -> None:
    _install_dns(monkeypatch, {"blocked.test": [address]})

    with pytest.raises(public_http.PublicHTTPError, match="non-public"):
        public_http.validate_public_url("https://blocked.test/resource")


def test_validate_public_url_accepts_public_dns_and_strips_fragment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_dns(monkeypatch, {"public.test": ["93.184.216.34"]})

    assert (
        public_http.validate_public_url("HTTPS://Public.Test:8443/path?q=1#fragment")
        == "https://public.test:8443/path?q=1"
    )


def test_fetch_revalidates_redirect_before_following(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_dns(
        monkeypatch,
        {
            "public.test": ["93.184.216.34"],
            "private.test": ["192.168.10.20"],
        },
    )

    headers = Message()
    headers["Location"] = "http://private.test/admin"
    response = _FakeResponse(status=302, headers=headers)
    connection = _FakeConnection()
    monkeypatch.setattr(
        public_http,
        "_open_pinned_response",
        lambda *_args, **_kwargs: (response, connection),
    )

    with pytest.raises(public_http.PublicHTTPError, match="non-public"):
        public_http.fetch_public_http(
            "https://public.test/start",
            timeout_seconds=5,
        )


def test_redirect_limit_and_cross_origin_secret_header_removal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_dns(
        monkeypatch,
        {
            "public.test": ["93.184.216.34"],
            "other.test": ["142.250.72.14"],
        },
    )
    handler = public_http._PublicRedirectHandler(1)
    request = urllib.request.Request(
        "https://public.test/start",
        headers={"Authorization": "Bearer test-only"},
    )
    redirected = handler.redirect_request(
        request,
        None,
        302,
        "Found",
        Message(),
        "https://other.test/next",
    )

    assert redirected is not None
    assert redirected.get_header("Authorization") is None
    with pytest.raises(public_http.PublicHTTPError, match="redirect limit"):
        handler.redirect_request(
            redirected,
            None,
            302,
            "Found",
            Message(),
            "https://public.test/final",
        )


def test_fetch_bounds_timeout_and_body_and_closes_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_dns(monkeypatch, {"public.test": ["93.184.216.34"]})
    headers = Message()
    headers["Content-Type"] = "text/plain; charset=utf-8"

    response = _FakeResponse(body=b"bounded body", headers=headers)
    connection = _FakeConnection()
    seen_timeout: list[float] = []

    def fake_open(*_args: Any, timeout: float, **_kwargs: Any) -> tuple[Any, Any]:
        seen_timeout.append(timeout)
        return response, connection

    monkeypatch.setattr(public_http, "_open_pinned_response", fake_open)

    result = public_http.fetch_public_http(
        "https://public.test/start",
        timeout_seconds=999,
        max_body_bytes=99_000_000,
    )

    assert seen_timeout and seen_timeout[0] <= public_http.MAX_ALLOWED_TIMEOUT_SECONDS
    assert response.read_limit is not None
    assert response.read_limit <= public_http.MAX_ALLOWED_BODY_BYTES
    assert response.closed is True
    assert connection.closed is True
    assert result.body == b"bounded body"


def test_fetch_rejects_body_larger_than_byte_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_dns(monkeypatch, {"public.test": ["93.184.216.34"]})
    response = _FakeResponse(body=b"four")
    connection = _FakeConnection()
    monkeypatch.setattr(
        public_http,
        "_open_pinned_response",
        lambda *_args, **_kwargs: (response, connection),
    )

    with pytest.raises(public_http.PublicHTTPError, match="exceeds the byte limit"):
        public_http.fetch_public_http(
            "https://public.test/oversized",
            timeout_seconds=5,
            max_body_bytes=3,
        )
    assert response.closed is True
    assert connection.closed is True


def test_dns_resolution_obeys_fetch_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = threading.Event()

    def blocked_dns(*_args: Any, **_kwargs: Any) -> list[tuple[Any, ...]]:
        release.wait(timeout=2)
        return _dns_result("93.184.216.34", 443)

    monkeypatch.setattr(public_http.socket, "getaddrinfo", blocked_dns)
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError, match="DNS resolution timed out"):
            public_http.fetch_public_http(
                "https://public.test/slow-dns",
                timeout_seconds=0.05,
            )
    finally:
        release.set()
    assert time.monotonic() - started < 0.5


def test_fetch_closes_http_error_response(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_dns(monkeypatch, {"public.test": ["93.184.216.34"]})

    response = _FakeResponse(status=404)
    response.reason = "Not Found"
    connection = _FakeConnection()
    monkeypatch.setattr(
        public_http,
        "_open_pinned_response",
        lambda *_args, **_kwargs: (response, connection),
    )

    with pytest.raises(urllib.error.HTTPError):
        public_http.fetch_public_http(
            "https://public.test/missing",
            timeout_seconds=5,
        )
    assert response.closed is True
    assert connection.closed is True


def test_fetch_normalizes_connection_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_dns(monkeypatch, {"public.test": ["93.184.216.34"]})
    monkeypatch.setattr(
        public_http,
        "_open_pinned_response",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ConnectionRefusedError("connection refused")
        ),
    )

    with pytest.raises(urllib.error.URLError, match="connection refused"):
        public_http.fetch_public_http(
            "https://public.test/unavailable",
            timeout_seconds=5,
        )


def test_sri_lanka_fetchers_block_private_dns_before_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_dns(monkeypatch, {"private.test": ["10.0.0.8"]})

    def unexpected_open(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("network connection must not open for a private destination")

    monkeypatch.setattr(
        public_http,
        "_open_pinned_response",
        unexpected_open,
    )

    health = source_health.test_source_url("http://private.test/status")
    fetched = source_fetcher.fetch_url("http://private.test/source")
    contact = live_contact_search_tools._http_get_text(
        "http://private.test/contact",
        timeout=5,
    )
    hunter = live_contact_search_tools.HunterContactEnrichmentProvider(
        api_key="test-only"
    )
    hunter.base_url = "http://private.test"

    assert health["ok"] is False and health["status_code"] is None
    assert fetched["ok"] is False and fetched["status_code"] is None
    assert contact.status_code is None and contact.text == ""
    with pytest.raises(public_http.PublicHTTPError):
        hunter._request_json("domain-search", {"domain": "public.test"})


def test_sri_lanka_fetchers_preserve_success_shapes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = Message()
    headers["Content-Type"] = "text/html; charset=utf-8"
    response = public_http.PublicHTTPResponse(
        url="https://public.test/final",
        status_code=200,
        headers=headers,
        body=b"<p>Sri Lanka public company announcement</p>",
    )
    monkeypatch.setattr(source_health, "fetch_public_http", lambda *_a, **_k: response)
    monkeypatch.setattr(source_fetcher, "fetch_public_http", lambda *_a, **_k: response)
    monkeypatch.setattr(
        live_contact_search_tools,
        "fetch_public_http",
        lambda *_a, **_k: response,
    )

    health = source_health.test_source_url(
        "https://public.test/start",
        search_terms=["announcement"],
    )
    fetched = source_fetcher.fetch_url("https://public.test/start")
    contact = live_contact_search_tools._http_get_text(
        "https://public.test/start",
        timeout=5,
    )

    assert health["ok"] is True
    assert health["url"] == response.url
    assert health["relevant_content"] is True
    assert fetched["ok"] is True
    assert fetched["url"] == response.url
    assert fetched["text"].startswith("<p>")
    assert contact == live_contact_search_tools._HTTPText(
        url=response.url,
        status_code=200,
        text="<p>Sri Lanka public company announcement</p>",
        error=None,
    )


def test_contact_url_normalizer_rejects_url_credentials() -> None:
    assert (
        live_contact_search_tools.normalize_public_url(
            "https://user:password@public.test/contact"
        )
        is None
    )
