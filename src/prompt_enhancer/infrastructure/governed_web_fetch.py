"""One bounded public-HTTPS fetch boundary for native-approved Agent calls.

The adapter intentionally has no ambient proxy, cookie, authentication, or
redirect support. DNS answers are admitted once and each TCP connection is
made directly to one admitted address while TLS verifies the reviewed hostname.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from html.parser import HTMLParser
import http.client
import io
import ipaddress
import select
import socket
import ssl
import threading
import time
from typing import Literal, Protocol
from urllib.parse import urlsplit, urlunsplit

from pydantic import SecretStr

from ..application.governed_web_fetch import (
    GovernedWebFetchError,
    GovernedWebFetchResult,
    PreparedWebFetch,
    WEB_FETCH_POLICY_VERSION,
)
from ..application.local_agent_limits import MAX_TOOL_RESULT_CHARS


MAX_WEB_FETCH_URL_CHARS = 2_048
MAX_WEB_FETCH_DNS_ADDRESSES = 16
MAX_WEB_FETCH_RESPONSE_BYTES = 512 * 1024
MAX_WEB_FETCH_HEADERS = 128
MAX_WEB_FETCH_HEADER_NAME_BYTES = 256
MAX_WEB_FETCH_HEADER_VALUE_BYTES = 8 * 1024
MAX_WEB_FETCH_HEADER_BYTES = 64 * 1024
MAX_WEB_FETCH_TEXT_CHARS = MAX_TOOL_RESULT_CHARS
_TRUNCATION_MARKER = "\n\n[Fetch text truncated by governed policy.]"
WEB_FETCH_CONNECT_TIMEOUT_SECONDS = 5.0
WEB_FETCH_READ_TIMEOUT_SECONDS = 8.0
WEB_FETCH_TOTAL_TIMEOUT_SECONDS = 12.0


class WebFetchDnsResolver(Protocol):
    def resolve(
        self,
        host: str,
        port: int,
        *,
        timeout: float,
        cancellation: threading.Event | None,
    ) -> tuple[str, ...]: ...


class SystemWebFetchDnsResolver:
    """Resolve precisely one requested hostname without probing local networks."""

    _pending = threading.BoundedSemaphore(4)

    def resolve(
        self,
        host: str,
        port: int,
        *,
        timeout: float,
        cancellation: threading.Event | None,
    ) -> tuple[str, ...]:
        result: list[object] = []
        completed = threading.Event()

        def resolve() -> None:
            try:
                result.append(
                    socket.getaddrinfo(
                        host,
                        port,
                        family=socket.AF_UNSPEC,
                        type=socket.SOCK_STREAM,
                        proto=socket.IPPROTO_TCP,
                    )
                )
            except (OSError, UnicodeError):
                result.append(None)
            finally:
                completed.set()

        deadline = time.monotonic() + timeout
        while not self._pending.acquire(timeout=min(0.05, max(0.0, deadline - time.monotonic()))):
            if cancellation is not None and cancellation.is_set():
                raise GovernedWebFetchError("web_fetch_cancelled")
            if time.monotonic() >= deadline:
                raise GovernedWebFetchError("web_fetch_timeout")

        def bounded_resolve() -> None:
            try:
                resolve()
            finally:
                self._pending.release()

        threading.Thread(target=bounded_resolve, daemon=True).start()
        while not completed.wait(min(0.05, max(0.0, deadline - time.monotonic()))):
            if cancellation is not None and cancellation.is_set():
                raise GovernedWebFetchError("web_fetch_cancelled")
            if time.monotonic() >= deadline:
                raise GovernedWebFetchError("web_fetch_timeout")
        if cancellation is not None and cancellation.is_set():
            raise GovernedWebFetchError("web_fetch_cancelled")
        rows = result[0] if result else None
        if not isinstance(rows, list):
            raise GovernedWebFetchError("web_fetch_host_unresolvable")
        values = tuple(dict.fromkeys(str(row[4][0]) for row in rows))
        if not values or len(values) > MAX_WEB_FETCH_DNS_ADDRESSES:
            raise GovernedWebFetchError("web_fetch_host_unresolvable")
        return values


@dataclass(frozen=True, slots=True)
class PinnedWebOrigin:
    host: str
    port: int
    addresses: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WebFetchResponse:
    status_code: int
    headers: tuple[tuple[str, str], ...]
    body: Iterable[bytes]
    close: Callable[[], None] | None = None


WebFetchRequester = Callable[
    [PinnedWebOrigin, PreparedWebFetch, threading.Event | None, float], WebFetchResponse
]


def _public_address(value: str) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        raise GovernedWebFetchError("web_fetch_address_invalid") from None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    if (
        not address.is_global
        or address.is_loopback
        or address.is_link_local
        or address.is_private
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        or isinstance(address, ipaddress.IPv6Address) and address.is_site_local
    ):
        raise GovernedWebFetchError("web_fetch_address_not_public")
    return str(address)


def _request_target(parsed) -> str:
    path = parsed.path or "/"
    return path if not parsed.query else f"{path}?{parsed.query}"


def _normalized_url(raw_url: str) -> PreparedWebFetch:
    if (
        not isinstance(raw_url, str)
        or not raw_url
        or len(raw_url) > MAX_WEB_FETCH_URL_CHARS
        or any(ord(character) < 32 or ord(character) == 127 or character in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069" for character in raw_url)
    ):
        raise GovernedWebFetchError("web_fetch_url_invalid")
    try:
        parsed = urlsplit(raw_url)
        host = parsed.hostname
        port = parsed.port or 443
    except ValueError:
        raise GovernedWebFetchError("web_fetch_url_invalid") from None
    if (
        parsed.scheme.casefold() != "https"
        or host is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or host.endswith(".")
        or "%" in host
        or not 1 <= port <= 65_535
    ):
        raise GovernedWebFetchError("web_fetch_url_invalid")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        try:
            normalized_host = host.encode("idna").decode("ascii").casefold()
        except UnicodeError:
            raise GovernedWebFetchError("web_fetch_url_invalid") from None
        authority = normalized_host if port == 443 else f"{normalized_host}:{port}"
    else:
        normalized_host = str(literal)
        authority = f"[{normalized_host}]" if isinstance(literal, ipaddress.IPv6Address) else normalized_host
        if port != 443:
            authority = f"{authority}:{port}"
    # urlunsplit preserves the exact path/query semantics without silently
    # trimming a reviewed suffix. The normalized origin is the one displayed.
    normalized = urlunsplit(("https", authority, parsed.path or "/", parsed.query, ""))
    if len(normalized) > MAX_WEB_FETCH_URL_CHARS:
        raise GovernedWebFetchError("web_fetch_url_invalid")
    return PreparedWebFetch(url=SecretStr(normalized))


def _origin(
    request: PreparedWebFetch,
    resolver: WebFetchDnsResolver,
    *,
    timeout: float,
    cancellation: threading.Event | None,
) -> PinnedWebOrigin:
    raw_url = request.url.get_secret_value()
    try:
        parsed = urlsplit(raw_url)
        host = parsed.hostname
        port = parsed.port or 443
    except ValueError:
        raise GovernedWebFetchError("web_fetch_url_invalid") from None
    if host is None:
        raise GovernedWebFetchError("web_fetch_url_invalid")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        addresses = resolver.resolve(host, port, timeout=timeout, cancellation=cancellation)
    else:
        addresses = (str(literal),)
    admitted = tuple(dict.fromkeys(_public_address(value) for value in addresses))
    if not admitted or len(admitted) > MAX_WEB_FETCH_DNS_ADDRESSES:
        raise GovernedWebFetchError("web_fetch_host_unresolvable")
    return PinnedWebOrigin(host=host, port=port, addresses=admitted)


def _validate_headers(headers: tuple[tuple[str, str], ...]) -> None:
    total = 0
    if len(headers) > MAX_WEB_FETCH_HEADERS:
        raise GovernedWebFetchError("web_fetch_headers_too_large")
    for name, value in headers:
        encoded_name = name.encode("ascii", "strict")
        encoded_value = value.encode("latin-1", "strict")
        if not encoded_name or len(encoded_name) > MAX_WEB_FETCH_HEADER_NAME_BYTES or len(encoded_value) > MAX_WEB_FETCH_HEADER_VALUE_BYTES:
            raise GovernedWebFetchError("web_fetch_headers_too_large")
        total += len(encoded_name) + len(encoded_value) + 4
        if total > MAX_WEB_FETCH_HEADER_BYTES:
            raise GovernedWebFetchError("web_fetch_headers_too_large")


def _response_content_type(headers: tuple[tuple[str, str], ...]) -> Literal["text/plain", "text/html"]:
    encoded = [value.strip().casefold() for name, value in headers if name.casefold() == "content-encoding"]
    if encoded and encoded != ["identity"]:
        raise GovernedWebFetchError("web_fetch_content_encoding_unsupported")
    values = [value for name, value in headers if name.casefold() == "content-type"]
    if len(values) != 1:
        raise GovernedWebFetchError("web_fetch_content_type_unsupported")
    content_type = values[0].split(";", 1)[0].strip().casefold()
    if content_type not in {"text/plain", "text/html"}:
        raise GovernedWebFetchError("web_fetch_content_type_unsupported")
    lengths = [value.strip() for name, value in headers if name.casefold() == "content-length"]
    if len(lengths) > 1:
        raise GovernedWebFetchError("web_fetch_headers_invalid")
    if lengths:
        try:
            declared = int(lengths[0])
        except ValueError:
            raise GovernedWebFetchError("web_fetch_headers_invalid") from None
        if declared < 0:
            raise GovernedWebFetchError("web_fetch_headers_invalid")
        if declared > MAX_WEB_FETCH_RESPONSE_BYTES:
            raise GovernedWebFetchError("web_fetch_response_too_large")
    return content_type  # type: ignore[return-value]


class _InertHtmlText(HTMLParser):
    _HIDDEN = frozenset({"script", "style", "template", "noscript", "svg", "canvas", "head"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._hidden_depth = 0
        self._parts: list[str] = []
        self._characters = 0
        self._truncated = False

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[no-untyped-def]
        if tag.casefold() in self._HIDDEN:
            self._hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in self._HIDDEN and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._hidden_depth:
            return
        if self._characters >= MAX_WEB_FETCH_TEXT_CHARS:
            if data:
                self._truncated = True
            return
        remaining = MAX_WEB_FETCH_TEXT_CHARS - self._characters
        portion = data[:remaining]
        self._characters += len(portion)
        self._parts.append(portion)
        if len(portion) < len(data):
            self._truncated = True

    def text(self) -> str:
        return " ".join(" ".join(self._parts).split())[:MAX_WEB_FETCH_TEXT_CHARS]

    @property
    def truncated(self) -> bool:
        return self._truncated


class _PinnedHttpsConnection(http.client.HTTPSConnection):
    def __init__(
        self,
        *,
        origin: PinnedWebOrigin,
        address: str,
        timeout: float,
        cancellation: threading.Event | None,
        deadline: float,
        monotonic: Callable[[], float],
    ) -> None:
        super().__init__(origin.host, origin.port, timeout=timeout, context=_strict_tls_context())
        self._address = address
        self._cancellation = cancellation
        self._deadline = deadline
        self._monotonic = monotonic

    def connect(self) -> None:
        if self._cancellation is not None and self._cancellation.is_set():
            raise GovernedWebFetchError("web_fetch_cancelled")
        sock = socket.create_connection((self._address, self.port), self.timeout)
        try:
            if self._cancellation is not None and self._cancellation.is_set():
                raise GovernedWebFetchError("web_fetch_cancelled")
            remaining = self._deadline - self._monotonic()
            if remaining <= 0:
                raise GovernedWebFetchError("web_fetch_timeout")
            sock.settimeout(min(WEB_FETCH_CONNECT_TIMEOUT_SECONDS, remaining))
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
            if self._cancellation is not None and self._cancellation.is_set():
                self.close()
                raise GovernedWebFetchError("web_fetch_cancelled")
        except BaseException:
            sock.close()
            raise


class _GovernedSocketRaw(io.RawIOBase):
    """The stdlib HTTP parser's bounded, cancellable read boundary."""

    def __init__(
        self,
        sock: socket.socket,
        *,
        deadline: float,
        cancellation: threading.Event | None,
        monotonic: Callable[[], float],
    ) -> None:
        super().__init__()
        self._sock = sock
        self._deadline = deadline
        self._cancellation = cancellation
        self._monotonic = monotonic
        self._header = bytearray()
        self._headers_complete = False

    def readable(self) -> bool:
        return True

    def close(self) -> None:
        if not self.closed:
            try:
                self._sock.close()
            finally:
                super().close()

    def readinto(self, buffer: bytearray) -> int:
        view = memoryview(buffer)
        want_write = False
        while True:
            if self._cancellation is not None and self._cancellation.is_set():
                raise GovernedWebFetchError("web_fetch_cancelled")
            remaining = self._deadline - self._monotonic()
            if remaining <= 0:
                raise GovernedWebFetchError("web_fetch_timeout")
            try:
                pending = int(getattr(self._sock, "pending", lambda: 0)())
            except (OSError, ValueError):
                pending = 0
            if not pending:
                if want_write:
                    _, writable, _ = select.select(
                        [], [self._sock], [], min(0.05, remaining)
                    )
                    if not writable:
                        continue
                else:
                    readable, _, _ = select.select(
                        [self._sock], [], [], min(0.05, remaining)
                    )
                    if not readable:
                        continue
            try:
                received = self._sock.recv_into(view)
            except (BlockingIOError, ssl.SSLWantReadError):
                want_write = False
                continue
            except ssl.SSLWantWriteError:
                want_write = True
                continue
            except OSError:
                if self._cancellation is not None and self._cancellation.is_set():
                    raise GovernedWebFetchError("web_fetch_cancelled") from None
                if self._monotonic() >= self._deadline:
                    raise GovernedWebFetchError("web_fetch_timeout") from None
                raise GovernedWebFetchError("web_fetch_read_failed") from None
            if received and not self._headers_complete:
                candidate = bytes(self._header) + bytes(view[:received])
                header_end = candidate.find(b"\r\n\r\n")
                if header_end >= 0:
                    if header_end + 4 > MAX_WEB_FETCH_HEADER_BYTES:
                        raise GovernedWebFetchError("web_fetch_headers_too_large")
                    self._headers_complete = True
                    self._header.clear()
                elif len(candidate) > MAX_WEB_FETCH_HEADER_BYTES:
                    raise GovernedWebFetchError("web_fetch_headers_too_large")
                else:
                    self._header = bytearray(candidate)
            return received


class _GovernedSocket:
    """A socket facade used only after the exact request bytes were sent."""

    def __init__(
        self,
        sock: socket.socket,
        *,
        deadline: float,
        cancellation: threading.Event | None,
        monotonic: Callable[[], float],
    ) -> None:
        self._sock = sock
        self._raw = _GovernedSocketRaw(
            sock,
            deadline=deadline,
            cancellation=cancellation,
            monotonic=monotonic,
        )
        self._reader_acquired = False
        setblocking = getattr(sock, "setblocking", None)
        if callable(setblocking):
            setblocking(False)

    def makefile(self, mode: str, buffering: int | None = None):  # type: ignore[no-untyped-def]
        if mode != "rb":
            raise OSError("governed response is read-only")
        self._reader_acquired = True
        return io.BufferedReader(self._raw, buffer_size=buffering or io.DEFAULT_BUFFER_SIZE)

    def settimeout(self, _timeout: float | None) -> None:
        # The raw reader uses select against the one absolute deadline.
        return None

    def shutdown(self, how: int) -> None:
        self._sock.shutdown(how)

    def close(self) -> None:
        # HTTPConnection closes its socket reference as soon as a
        # Connection: close response is parsed. The response BufferedReader
        # still owns ``_raw`` and must remain readable until response.close().
        if not self._reader_acquired:
            self._sock.close()


def _strict_tls_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


class PublicHttpsTextFetcher:
    """Public HTTPS GET only; no redirect, proxy, cookie, or ambient auth path."""

    policy_version: Literal[WEB_FETCH_POLICY_VERSION] = WEB_FETCH_POLICY_VERSION
    _pending_header_reads = threading.BoundedSemaphore(4)

    def __init__(
        self,
        *,
        resolver: WebFetchDnsResolver | None = None,
        requester: WebFetchRequester | None = None,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self._resolver = resolver or SystemWebFetchDnsResolver()
        self._requester = requester or self._request
        self._monotonic = monotonic or time.monotonic
        self._header_cleanup_unconfirmed = threading.Event()
        self._header_cleanup_lock = threading.Lock()
        self._abandoned_header_reads = 0

    def prepare(self, raw_url: str) -> PreparedWebFetch:
        return _normalized_url(raw_url)

    def fetch(
        self,
        request: PreparedWebFetch,
        *,
        cancellation: threading.Event | None = None,
    ) -> GovernedWebFetchResult:
        if self._header_cleanup_unconfirmed.is_set():
            raise GovernedWebFetchError("web_fetch_cleanup_unconfirmed")
        if cancellation is not None and cancellation.is_set():
            raise GovernedWebFetchError("web_fetch_cancelled")
        deadline = self._monotonic() + WEB_FETCH_TOTAL_TIMEOUT_SECONDS
        origin = _origin(
            request,
            self._resolver,
            timeout=max(0.0, deadline - self._monotonic()),
            cancellation=cancellation,
        )
        if cancellation is not None and cancellation.is_set():
            raise GovernedWebFetchError("web_fetch_cancelled")
        response = self._requester(origin, request, cancellation, deadline)
        try:
            if response.status_code in range(300, 400):
                raise GovernedWebFetchError("web_fetch_redirect_refused")
            if response.status_code != 200:
                raise GovernedWebFetchError("web_fetch_http_status_refused")
            headers = tuple(response.headers)
            _validate_headers(headers)
            content_type = _response_content_type(headers)
            body = bytearray()
            for chunk in response.body:
                if cancellation is not None and cancellation.is_set():
                    raise GovernedWebFetchError("web_fetch_cancelled")
                if not isinstance(chunk, bytes):
                    raise GovernedWebFetchError("web_fetch_response_invalid")
                if len(chunk) > MAX_WEB_FETCH_RESPONSE_BYTES - len(body):
                    raise GovernedWebFetchError("web_fetch_response_too_large")
                body.extend(chunk)
            if not body:
                raise GovernedWebFetchError("web_fetch_response_empty")
            try:
                decoded = bytes(body).decode("utf-8", "strict")
            except UnicodeDecodeError:
                raise GovernedWebFetchError("web_fetch_text_decode_failed") from None
            if content_type == "text/html":
                parser = _InertHtmlText()
                try:
                    parser.feed(decoded)
                    parser.close()
                except Exception:
                    raise GovernedWebFetchError("web_fetch_html_invalid") from None
                extracted = parser.text()
                truncated = parser.truncated
            else:
                extracted = decoded
                truncated = len(extracted) > MAX_WEB_FETCH_TEXT_CHARS
            text = extracted[:MAX_WEB_FETCH_TEXT_CHARS]
            if truncated:
                text = text[: MAX_WEB_FETCH_TEXT_CHARS - len(_TRUNCATION_MARKER)] + _TRUNCATION_MARKER
            if not text.strip():
                raise GovernedWebFetchError("web_fetch_text_empty")
            return GovernedWebFetchResult(
                text=text,
                content_type=content_type,
                byte_size=len(body),
                truncated=truncated,
            )
        finally:
            if response.close is not None:
                response.close()

    def _request(
        self,
        origin: PinnedWebOrigin,
        request: PreparedWebFetch,
        cancellation: threading.Event | None,
        deadline: float,
    ) -> WebFetchResponse:
        raw_url = request.url.get_secret_value()
        parsed = urlsplit(raw_url)
        for address in origin.addresses:
            if cancellation is not None and cancellation.is_set():
                raise GovernedWebFetchError("web_fetch_cancelled")
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise GovernedWebFetchError("web_fetch_timeout")
            connection = _PinnedHttpsConnection(
                origin=origin,
                address=address,
                timeout=min(WEB_FETCH_CONNECT_TIMEOUT_SECONDS, remaining),
                cancellation=cancellation,
                deadline=deadline,
                monotonic=self._monotonic,
            )
            transport_socket: socket.socket | None = None
            try:
                connection.request(
                    "GET",
                    _request_target(parsed),
                    headers={
                        "Accept": "text/plain, text/html;q=0.9",
                        "Accept-Encoding": "identity",
                        "Connection": "close",
                        "Host": origin.host if origin.port == 443 else f"{origin.host}:{origin.port}",
                        "User-Agent": "PromptEnhancerGovernedFetch/1",
                    },
                )
                if cancellation is not None and cancellation.is_set():
                    raise GovernedWebFetchError("web_fetch_cancelled")
                # HTTPResponse can detach this socket when Connection: close is
                # negotiated. Retaining it lets cancellation interrupt an
                # in-flight BufferedReader read without relying on close().
                transport_socket = connection.sock
                if transport_socket is None:
                    raise OSError("governed transport did not connect")
                connection.sock = _GovernedSocket(
                    transport_socket,
                    deadline=deadline,
                    cancellation=cancellation,
                    monotonic=self._monotonic,
                )
                response = self._await_network_operation(
                    connection.getresponse,
                    connection=connection,
                    transport_socket=transport_socket,
                    deadline=deadline,
                    cancellation=cancellation,
                )
                close_lock = threading.Lock()
                closed = threading.Event()
                watchdog_stop = threading.Event()

                def interrupt_transport() -> None:
                    if transport_socket is not None:
                        try:
                            transport_socket.shutdown(socket.SHUT_RDWR)
                        except (AttributeError, OSError):
                            pass
                    connection.close()

                def close_response() -> None:
                    with close_lock:
                        if closed.is_set():
                            return
                        closed.set()
                    try:
                        response.close()
                    finally:
                        interrupt_transport()

                def watch_read() -> None:
                    while not watchdog_stop.wait(
                        min(0.05, max(0.0, deadline - self._monotonic()))
                    ):
                        if (
                            cancellation is not None
                            and cancellation.is_set()
                        ) or self._monotonic() >= deadline:
                            # ``response.close`` can wait on the same buffered
                            # read we must interrupt. Shut down the retained
                            # transport only; normal finalization closes the
                            # response after the read unwinds.
                            interrupt_transport()
                            return

                watchdog = threading.Thread(target=watch_read, daemon=True)
                watchdog.start()

                def body() -> Iterable[bytes]:
                    while True:
                        if cancellation is not None and cancellation.is_set():
                            raise GovernedWebFetchError("web_fetch_cancelled")
                        remaining = deadline - self._monotonic()
                        if remaining <= 0:
                            raise GovernedWebFetchError("web_fetch_timeout")
                        try:
                            chunk = response.read1(min(8 * 1024, MAX_WEB_FETCH_RESPONSE_BYTES + 1))
                        except (OSError, http.client.HTTPException, TimeoutError):
                            if cancellation is not None and cancellation.is_set():
                                raise GovernedWebFetchError("web_fetch_cancelled") from None
                            if self._monotonic() >= deadline:
                                raise GovernedWebFetchError("web_fetch_timeout") from None
                            raise GovernedWebFetchError("web_fetch_read_failed") from None
                        if cancellation is not None and cancellation.is_set():
                            raise GovernedWebFetchError("web_fetch_cancelled")
                        if self._monotonic() >= deadline:
                            raise GovernedWebFetchError("web_fetch_timeout")
                        if not chunk:
                            return
                        yield chunk

                def close_with_watchdog() -> None:
                    watchdog_stop.set()
                    watchdog.join(timeout=0.2)
                    close_response()

                return WebFetchResponse(
                    response.status,
                    tuple(response.getheaders()),
                    body(),
                    close=close_with_watchdog,
                )
            except GovernedWebFetchError:
                connection.close()
                if transport_socket is not None:
                    transport_socket.close()
                raise
            except (OSError, ssl.SSLError, http.client.HTTPException, TimeoutError):
                connection.close()
                if transport_socket is not None:
                    transport_socket.close()
                continue
        raise GovernedWebFetchError("web_fetch_connect_failed")

    def _await_network_operation(
        self,
        operation: Callable[[], object],
        *,
        connection: http.client.HTTPSConnection,
        transport_socket: socket.socket | None = None,
        deadline: float,
        cancellation: threading.Event | None,
    ) -> object:
        def interrupt_transport() -> None:
            if transport_socket is not None:
                try:
                    transport_socket.shutdown(socket.SHUT_RDWR)
                except (AttributeError, OSError):
                    pass
                try:
                    transport_socket.close()
                except (AttributeError, OSError):
                    pass
            connection.close()

        while not self._pending_header_reads.acquire(
            timeout=min(0.05, max(0.0, deadline - self._monotonic()))
        ):
            if cancellation is not None and cancellation.is_set():
                connection.close()
                raise GovernedWebFetchError("web_fetch_cancelled")
            if self._monotonic() >= deadline:
                connection.close()
                raise GovernedWebFetchError("web_fetch_timeout")
        result: list[object] = []
        completed = threading.Event()
        abandoned = threading.Event()
        cleanup_tracked = threading.Event()
        result_lock = threading.Lock()

        def abandon() -> None:
            if not abandoned.is_set():
                abandoned.set()
                if not completed.is_set():
                    cleanup_tracked.set()
                    with self._header_cleanup_lock:
                        self._abandoned_header_reads += 1
                        self._header_cleanup_unconfirmed.set()
            with result_lock:
                values = tuple(result)
                result.clear()
            for value in values:
                if hasattr(value, "close"):
                    value.close()

        def run() -> None:
            try:
                value = operation()
                with result_lock:
                    discard = abandoned.is_set()
                    if not discard:
                        result.append(value)
                if discard and hasattr(value, "close"):
                    value.close()
            except BaseException as error:
                with result_lock:
                    if not abandoned.is_set():
                        result.append(error)
            finally:
                completed.set()
                self._pending_header_reads.release()
                if cleanup_tracked.is_set():
                    with self._header_cleanup_lock:
                        self._abandoned_header_reads -= 1
                        if self._abandoned_header_reads == 0:
                            self._header_cleanup_unconfirmed.clear()

        threading.Thread(target=run, daemon=True).start()
        while not completed.wait(min(0.05, max(0.0, deadline - self._monotonic()))):
            if cancellation is not None and cancellation.is_set():
                abandon()
                interrupt_transport()
                raise GovernedWebFetchError("web_fetch_cancelled")
            if self._monotonic() >= deadline:
                abandon()
                interrupt_transport()
                raise GovernedWebFetchError("web_fetch_timeout")
        if cancellation is not None and cancellation.is_set():
            abandon()
            interrupt_transport()
            raise GovernedWebFetchError("web_fetch_cancelled")
        with result_lock:
            value = result[0] if result else None
        if isinstance(value, BaseException):
            raise value
        return value


__all__ = (
    "MAX_WEB_FETCH_RESPONSE_BYTES",
    "PinnedWebOrigin",
    "PublicHttpsTextFetcher",
    "SystemWebFetchDnsResolver",
    "WebFetchDnsResolver",
    "WebFetchResponse",
)
