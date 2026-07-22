"""Fail-closed HTTP boundary for fetching public internet resources."""

from __future__ import annotations

import http.client
import ipaddress
import queue
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

DEFAULT_MAX_REDIRECTS = 5
DEFAULT_MAX_BODY_BYTES = 1_500_000
MAX_ALLOWED_REDIRECTS = 10
MAX_ALLOWED_BODY_BYTES = 5_000_000
MAX_ALLOWED_TIMEOUT_SECONDS = 30.0
DEFAULT_DNS_TIMEOUT_SECONDS = 5.0

_METADATA_HOSTS = frozenset(
    {
        "instance-data.ec2.internal",
        "metadata",
        "metadata.google.internal",
        "metadata.goog",
    }
)
_LOCAL_HOSTS = frozenset({"localhost", "localhost.localdomain"})
_SENSITIVE_REDIRECT_HEADERS = frozenset(
    {"authorization", "cookie", "proxy-authorization"}
)
_NAT64_WELL_KNOWN_PREFIX = ipaddress.ip_network("64:ff9b::/96")


class PublicHTTPError(ValueError):
    """Raised when a request violates the public HTTP security boundary."""


@dataclass(frozen=True, slots=True)
class PublicHTTPResponse:
    """Bounded response returned after all destination checks pass."""

    url: str
    status_code: int
    headers: Any
    body: bytes


def validate_public_url(
    url: str, *, timeout_seconds: float = DEFAULT_DNS_TIMEOUT_SECONDS
) -> str:
    """Normalize a URL and prove that every resolved address is public."""
    normalized, _addresses = resolve_public_url(
        url, timeout_seconds=timeout_seconds
    )
    return normalized


def resolve_public_url(
    url: str,
    *,
    timeout_seconds: float = DEFAULT_DNS_TIMEOUT_SECONDS,
) -> tuple[str, tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]]:
    """Normalize a URL and return the public addresses validated for its host."""
    value = str(url or "").strip()
    if not value:
        raise PublicHTTPError("public URL is required")
    if any(ord(character) < 32 for character in value):
        raise PublicHTTPError("public URL contains control characters")

    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise PublicHTTPError(f"invalid public URL: {exc}") from exc

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise PublicHTTPError("public URL scheme must be http or https")
    if parsed.username is not None or parsed.password is not None:
        raise PublicHTTPError("public URL credentials are not allowed")
    if not parsed.hostname:
        raise PublicHTTPError("public URL host is required")

    host = _normalize_host(parsed.hostname)
    _reject_metadata_host(host)
    effective_port = port or (443 if scheme == "https" else 80)
    addresses = _validate_resolved_addresses(
        host, effective_port, timeout_seconds=timeout_seconds
    )

    display_host = f"[{host}]" if ":" in host else host
    netloc = display_host if port is None else f"{display_host}:{port}"
    normalized = urllib.parse.urlunsplit(
        (scheme, netloc, parsed.path, parsed.query, "")
    )
    return normalized, addresses


def fetch_public_http(
    request: str | urllib.request.Request,
    *,
    timeout_seconds: float,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
) -> PublicHTTPResponse:
    """Fetch a public resource while connecting only to the validated IP."""
    timeout = _bounded_timeout(timeout_seconds)
    redirect_limit = _bounded_redirects(max_redirects)
    body_limit = _bounded_body_bytes(max_body_bytes)
    deadline = time.monotonic() + timeout
    safe_request = _validated_request(request, timeout_seconds=timeout)
    current_url = safe_request.full_url
    method = safe_request.get_method()
    data = safe_request.data
    headers = dict(safe_request.header_items())

    for redirect_count in range(redirect_limit + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("public HTTP request exceeded its deadline")
        safe_url, addresses = resolve_public_url(
            current_url, timeout_seconds=remaining
        )
        try:
            response, connection = _open_pinned_response(
                safe_url,
                str(addresses[0]),
                method=method,
                headers=headers,
                data=data,
                timeout=remaining,
            )
        except TimeoutError:
            raise
        except (OSError, http.client.HTTPException) as exc:
            raise urllib.error.URLError(exc) from exc
        try:
            status = int(response.status)
            if status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                if not location:
                    raise PublicHTTPError("redirect response is missing Location")
                if redirect_count >= redirect_limit:
                    raise PublicHTTPError("public HTTP redirect limit exceeded")
                next_url = urllib.parse.urljoin(safe_url, location)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("public HTTP request exceeded its deadline")
                next_url = validate_public_url(
                    next_url, timeout_seconds=remaining
                )
                if _origin(safe_url) != _origin(next_url):
                    headers = {
                        key: value
                        for key, value in headers.items()
                        if key.lower() not in _SENSITIVE_REDIRECT_HEADERS
                    }
                if status in {301, 302, 303} and method not in {"GET", "HEAD"}:
                    method = "GET"
                    data = None
                    headers = {
                        key: value
                        for key, value in headers.items()
                        if key.lower() not in {"content-length", "content-type"}
                    }
                current_url = next_url
                continue
            if status >= 400:
                error = urllib.error.HTTPError(
                    safe_url,
                    status,
                    response.reason,
                    response.headers,
                    response,
                )
                error.close()
                raise error
            try:
                body = _read_bounded_response(response, body_limit, deadline)
            except TimeoutError:
                raise
            except (OSError, http.client.HTTPException) as exc:
                raise urllib.error.URLError(exc) from exc
            return PublicHTTPResponse(
                url=safe_url,
                status_code=status,
                headers=response.headers,
                body=body,
            )
        finally:
            response.close()
            connection.close()

    raise PublicHTTPError("public HTTP redirect limit exceeded")


def _normalize_host(host: str) -> str:
    normalized = host.rstrip(".").lower()
    try:
        return normalized.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise PublicHTTPError("public URL host is invalid") from exc


def _reject_metadata_host(host: str) -> None:
    if host in _LOCAL_HOSTS or host.endswith(".localhost"):
        raise PublicHTTPError(f"public URL host is local: {host}")
    if host in _METADATA_HOSTS or host.endswith(".metadata.google.internal"):
        raise PublicHTTPError(f"public URL host is metadata-only: {host}")


def _validate_resolved_addresses(
    host: str,
    port: int,
    *,
    timeout_seconds: float,
) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
    timeout = _bounded_timeout(timeout_seconds)
    result_queue: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

    def resolve() -> None:
        try:
            result = socket.getaddrinfo(
                host,
                port,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
            )
        except Exception as exc:
            result_queue.put((False, exc))
        else:
            result_queue.put((True, result))

    threading.Thread(
        target=resolve,
        name="business-intel-public-dns",
        daemon=True,
    ).start()
    try:
        succeeded, result = result_queue.get(timeout=timeout)
    except queue.Empty as exc:
        raise TimeoutError(f"public URL DNS resolution timed out for {host}") from exc
    if not succeeded:
        if isinstance(result, socket.gaierror):
            exc = result
        else:
            raise PublicHTTPError(
                f"public URL DNS resolution failed for {host}"
            ) from result
        raise PublicHTTPError(f"public URL DNS resolution failed for {host}") from exc
    records = result
    if not records:
        raise PublicHTTPError(f"public URL DNS returned no addresses for {host}")

    addresses: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    for record in records:
        raw_address = str(record[4][0]).split("%", 1)[0]
        try:
            addresses.add(ipaddress.ip_address(raw_address))
        except ValueError as exc:
            raise PublicHTTPError(
                f"public URL DNS returned an invalid address for {host}"
            ) from exc
    for address in addresses:
        inspected_addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = [
            address
        ]
        if isinstance(address, ipaddress.IPv6Address):
            embedded_ipv4 = address.ipv4_mapped or address.sixtofour
            if embedded_ipv4 is None and address in _NAT64_WELL_KNOWN_PREFIX:
                embedded_ipv4 = ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)
            if embedded_ipv4 is not None:
                inspected_addresses.append(embedded_ipv4)
        if any(not _is_public_address(item) for item in inspected_addresses):
            raise PublicHTTPError(
                f"public URL resolved to a non-public address: {address}"
            )
    return tuple(sorted(addresses, key=lambda address: (address.version, int(address))))


def _is_public_address(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
        or not address.is_global
    )


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, pinned_address: str, port: int, timeout: float) -> None:
        super().__init__(host, port=port, timeout=timeout)
        self._pinned_address = pinned_address

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self._pinned_address, self.port),
            self.timeout,
            self.source_address,
        )


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, pinned_address: str, port: int, timeout: float) -> None:
        super().__init__(
            host,
            port=port,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
        self._pinned_address = pinned_address

    def connect(self) -> None:
        raw_socket = socket.create_connection(
            (self._pinned_address, self.port),
            self.timeout,
            self.source_address,
        )
        self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)


def _open_pinned_response(
    url: str,
    pinned_address: str,
    *,
    method: str,
    headers: dict[str, str],
    data: bytes | None,
    timeout: float,
) -> tuple[http.client.HTTPResponse, http.client.HTTPConnection]:
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    connection_type = (
        _PinnedHTTPSConnection if parsed.scheme == "https" else _PinnedHTTPConnection
    )
    connection = connection_type(host, pinned_address, port, timeout)
    path = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
    connection.request(method, path, body=data, headers=headers)
    return connection.getresponse(), connection


def _read_bounded_response(
    response: http.client.HTTPResponse,
    max_bytes: int,
    deadline: float,
) -> bytes:
    chunks: list[bytes] = []
    remaining_bytes = max_bytes
    while remaining_bytes:
        remaining_time = deadline - time.monotonic()
        if remaining_time <= 0:
            raise TimeoutError("public HTTP response exceeded its deadline")
        response_fp = getattr(response, "fp", None)
        if response_fp and getattr(response_fp, "raw", None):
            raw_socket = getattr(response_fp.raw, "_sock", None)
            if raw_socket is not None:
                raw_socket.settimeout(remaining_time)
        chunk = response.read(min(64 * 1024, remaining_bytes))
        if not chunk:
            break
        chunks.append(chunk)
        remaining_bytes -= len(chunk)
    if remaining_bytes == 0:
        remaining_time = deadline - time.monotonic()
        if remaining_time <= 0:
            raise TimeoutError("public HTTP response exceeded its deadline")
        response_fp = getattr(response, "fp", None)
        if response_fp and getattr(response_fp, "raw", None):
            raw_socket = getattr(response_fp.raw, "_sock", None)
            if raw_socket is not None:
                raw_socket.settimeout(remaining_time)
        if response.read(1):
            raise PublicHTTPError("public HTTP response body exceeds the byte limit")
    return b"".join(chunks)


def _validated_request(
    request: str | urllib.request.Request,
    *,
    timeout_seconds: float,
) -> urllib.request.Request:
    if isinstance(request, urllib.request.Request):
        safe_url = validate_public_url(
            request.full_url, timeout_seconds=timeout_seconds
        )
        return urllib.request.Request(
            safe_url,
            data=request.data,
            headers=dict(request.header_items()),
            method=request.get_method(),
        )
    return urllib.request.Request(
        validate_public_url(str(request), timeout_seconds=timeout_seconds)
    )


def _bounded_timeout(value: float) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError) as exc:
        raise PublicHTTPError("timeout must be a positive number") from exc
    if timeout <= 0:
        raise PublicHTTPError("timeout must be a positive number")
    return min(timeout, MAX_ALLOWED_TIMEOUT_SECONDS)


def _bounded_redirects(value: int) -> int:
    try:
        redirects = int(value)
    except (TypeError, ValueError) as exc:
        raise PublicHTTPError("max_redirects must be an integer") from exc
    if redirects < 0:
        raise PublicHTTPError("max_redirects must not be negative")
    return min(redirects, MAX_ALLOWED_REDIRECTS)


def _bounded_body_bytes(value: int) -> int:
    try:
        body_bytes = int(value)
    except (TypeError, ValueError) as exc:
        raise PublicHTTPError("max_body_bytes must be an integer") from exc
    if body_bytes <= 0:
        raise PublicHTTPError("max_body_bytes must be positive")
    return min(body_bytes, MAX_ALLOWED_BODY_BYTES)


class _PublicRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, max_redirects: int) -> None:
        super().__init__()
        self._max_redirects = max_redirects
        self._redirect_count = 0

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        if self._redirect_count >= self._max_redirects:
            raise PublicHTTPError("public HTTP redirect limit exceeded")
        safe_url = validate_public_url(newurl)
        self._redirect_count += 1
        redirected = super().redirect_request(
            req,
            fp,
            code,
            msg,
            headers,
            safe_url,
        )
        if redirected is not None and _origin(req.full_url) != _origin(safe_url):
            _remove_sensitive_headers(redirected)
        return redirected

    def http_error_302(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
    ) -> Any:
        try:
            return super().http_error_302(
                req,
                fp,
                code,
                msg,
                headers,
            )
        except Exception:
            fp.close()
            raise

    http_error_301 = http_error_302
    http_error_303 = http_error_302
    http_error_307 = http_error_302
    http_error_308 = http_error_302


def _origin(url: str) -> tuple[str, str, int | None]:
    parsed = urllib.parse.urlsplit(url)
    return parsed.scheme.lower(), (parsed.hostname or "").lower(), parsed.port


def _remove_sensitive_headers(request: urllib.request.Request) -> None:
    for mapping in (request.headers, request.unredirected_hdrs):
        for header in list(mapping):
            if header.lower() in _SENSITIVE_REDIRECT_HEADERS:
                del mapping[header]
