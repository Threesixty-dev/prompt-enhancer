"""Synthetic policy tests for the public HTTPS fetch boundary."""

from __future__ import annotations

import threading
import time
import http.client
import socket

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from prompt_enhancer.application.governed_web_fetch import GovernedWebFetchError
from prompt_enhancer.application.local_agent import LocalAgentService
from prompt_enhancer.infrastructure import governed_web_fetch
from prompt_enhancer.infrastructure.governed_web_fetch import (
    PinnedWebOrigin,
    PublicHttpsTextFetcher,
    WebFetchResponse,
)
from prompt_enhancer.interfaces.http.local_agent_routes import create_local_agent_router


class _Resolver:
    def __init__(self, addresses: tuple[str, ...] = ("8.8.8.8",)) -> None:
        self.addresses = addresses
        self.calls = 0

    def resolve(
        self,
        _host: str,
        _port: int,
        *,
        timeout: float,
        cancellation: threading.Event | None,
    ) -> tuple[str, ...]:
        assert timeout > 0
        assert cancellation is None or not cancellation.is_set()
        self.calls += 1
        return self.addresses


def test_prepare_refuses_unreviewable_targets_before_dns() -> None:
    resolver = _Resolver()
    fetcher = PublicHttpsTextFetcher(resolver=resolver)
    for target in (
        "http://public.example.test/",
        "https://user:secret@public.example.test/",
        "https://public.example.test/path#fragment",
        "https://public.example.test/\r\nnext",
        "https://public.example.test/\u202e",
    ):
        with pytest.raises(GovernedWebFetchError) as refused:
            fetcher.prepare(target)
        assert refused.value.code == "web_fetch_url_invalid"
    assert resolver.calls == 0


def test_public_fetch_strips_active_html_and_closes_on_every_refusal() -> None:
    resolver = _Resolver()
    closed: list[str] = []

    def requester(_origin, _request, _cancel, _deadline):  # type: ignore[no-untyped-def]
        return WebFetchResponse(
            200,
            (("Content-Type", "text/html; charset=utf-8"),),
            [b"<head>hidden</head><p>Useful <script>ignore()</script>reference</p>"],
            close=lambda: closed.append("closed"),
        )

    fetcher = PublicHttpsTextFetcher(resolver=resolver, requester=requester)
    result = fetcher.fetch(fetcher.prepare("https://public.example.test/reference"))
    assert result.text == "Useful reference"
    assert result.truncated is False
    assert closed == ["closed"]

    for status, headers, expected in (
        (302, (("Content-Type", "text/plain"),), "web_fetch_redirect_refused"),
        (200, (("Content-Type", "application/json"),), "web_fetch_content_type_unsupported"),
    ):
        closed.clear()

        def refused_requester(_origin, _request, _cancel, _deadline, *, _status=status, _headers=headers):  # type: ignore[no-untyped-def]
            return WebFetchResponse(_status, _headers, [b"not returned"], close=lambda: closed.append("closed"))

        rejected = PublicHttpsTextFetcher(resolver=resolver, requester=refused_requester)
        with pytest.raises(GovernedWebFetchError) as error:
            rejected.fetch(rejected.prepare("https://public.example.test/reference"))
        assert error.value.code == expected
        assert closed == ["closed"]


def test_private_dns_and_pre_cancel_never_call_requester() -> None:
    resolver = _Resolver(("127.0.0.1",))
    requested: list[object] = []

    def requester(*_args):  # type: ignore[no-untyped-def]
        requested.append(object())
        raise AssertionError("requester must not run")

    fetcher = PublicHttpsTextFetcher(resolver=resolver, requester=requester)
    with pytest.raises(GovernedWebFetchError) as private:
        fetcher.fetch(fetcher.prepare("https://public.example.test/"))
    assert private.value.code == "web_fetch_address_not_public"
    assert requested == []

    stopped = threading.Event()
    stopped.set()
    with pytest.raises(GovernedWebFetchError) as cancelled:
        fetcher.fetch(fetcher.prepare("https://public.example.test/"), cancellation=stopped)
    assert cancelled.value.code == "web_fetch_cancelled"
    assert resolver.calls == 1
    assert requested == []


def test_default_transport_closes_response_and_connection_on_header_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[str] = []

    class Response:
        status = 302

        def getheaders(self):  # type: ignore[no-untyped-def]
            return (("Content-Type", "text/plain"),)

        def close(self) -> None:
            closed.append("response")

    class Socket:
        def settimeout(self, _value: float) -> None:
            return None

        def shutdown(self, _how: int) -> None:
            return None

    class Connection:
        def __init__(self, **_kwargs) -> None:  # type: ignore[no-untyped-def]
            self.sock = Socket()

        def request(self, *_args, **_kwargs) -> None:  # type: ignore[no-untyped-def]
            return None

        def getresponse(self) -> Response:
            return Response()

        def close(self) -> None:
            closed.append("connection")

    monkeypatch.setattr(governed_web_fetch, "_PinnedHttpsConnection", Connection)
    fetcher = PublicHttpsTextFetcher(resolver=_Resolver())
    with pytest.raises(GovernedWebFetchError) as refused:
        fetcher.fetch(fetcher.prepare("https://public.example.test/"))
    assert refused.value.code == "web_fetch_redirect_refused"
    assert closed == ["response", "connection"]


def test_default_transport_enforces_total_deadline_during_body_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]
    closed: list[str] = []

    class Response:
        status = 200

        def getheaders(self):  # type: ignore[no-untyped-def]
            return (("Content-Type", "text/plain"),)

        def read1(self, _size: int) -> bytes:
            clock[0] = 13.0
            return b"synthetic slow response"

        def close(self) -> None:
            closed.append("response")

    class Socket:
        def settimeout(self, _value: float) -> None:
            return None

        def shutdown(self, _how: int) -> None:
            return None

    class Connection:
        def __init__(self, **_kwargs) -> None:  # type: ignore[no-untyped-def]
            self.sock = Socket()

        def request(self, *_args, **_kwargs) -> None:  # type: ignore[no-untyped-def]
            return None

        def getresponse(self) -> Response:
            return Response()

        def close(self) -> None:
            closed.append("connection")

    monkeypatch.setattr(governed_web_fetch, "_PinnedHttpsConnection", Connection)
    fetcher = PublicHttpsTextFetcher(resolver=_Resolver(), monotonic=lambda: clock[0])
    with pytest.raises(GovernedWebFetchError) as timed_out:
        fetcher.fetch(fetcher.prepare("https://public.example.test/"))
    assert timed_out.value.code == "web_fetch_timeout"
    assert closed == ["response", "connection"]


def test_cancelled_header_read_quarantines_fetches_until_late_worker_closes() -> None:
    fetcher = PublicHttpsTextFetcher(resolver=_Resolver())
    cancellation = threading.Event()
    started = threading.Event()
    release = threading.Event()
    closed: list[str] = []
    observed: list[GovernedWebFetchError] = []

    class Connection:
        def close(self) -> None:
            closed.append("connection")

    class LateResponse:
        def close(self) -> None:
            closed.append("response")

    def operation() -> LateResponse:
        started.set()
        assert release.wait(2)
        return LateResponse()

    def await_header() -> None:
        try:
            fetcher._await_network_operation(  # noqa: SLF001 - worker ownership fence
                operation,
                connection=Connection(),
                deadline=time.monotonic() + 5,
                cancellation=cancellation,
            )
        except GovernedWebFetchError as error:
            observed.append(error)

    thread = threading.Thread(target=await_header)
    thread.start()
    assert started.wait(1)
    cancellation.set()
    thread.join(1)
    assert observed and observed[0].code == "web_fetch_cancelled"
    assert closed == ["connection"]
    assert fetcher._header_cleanup_unconfirmed.is_set()  # noqa: SLF001
    release.set()
    deadline = time.monotonic() + 1
    while fetcher._header_cleanup_unconfirmed.is_set() and time.monotonic() < deadline:  # noqa: SLF001
        time.sleep(0.01)
    assert closed == ["connection", "response"]
    assert not fetcher._header_cleanup_unconfirmed.is_set()  # noqa: SLF001


def test_header_watchdog_shuts_down_owned_socketpair_before_late_cleanup() -> None:
    fetcher = PublicHttpsTextFetcher(resolver=_Resolver())
    client_socket, server_socket = socket.socketpair()
    cancellation = threading.Event()
    started = threading.Event()
    settled = threading.Event()
    observed: list[GovernedWebFetchError] = []
    closed: list[str] = []

    class Connection:
        def close(self) -> None:
            closed.append("connection")

    class LateResponse:
        def close(self) -> None:
            closed.append("response")

    def operation() -> LateResponse:
        started.set()
        try:
            client_socket.recv(1)
        except OSError:
            return LateResponse()
        finally:
            settled.set()
        return LateResponse()

    def await_header() -> None:
        try:
            fetcher._await_network_operation(  # noqa: SLF001 - header ownership fence
                operation,
                connection=Connection(),
                transport_socket=client_socket,
                deadline=time.monotonic() + 5,
                cancellation=cancellation,
            )
        except GovernedWebFetchError as error:
            observed.append(error)

    thread = threading.Thread(target=await_header)
    try:
        thread.start()
        assert started.wait(1)
        cancellation.set()
        thread.join(1)
        assert observed and observed[0].code == "web_fetch_cancelled"
        assert settled.wait(1)
        deadline = time.monotonic() + 1
        while fetcher._header_cleanup_unconfirmed.is_set() and time.monotonic() < deadline:  # noqa: SLF001
            time.sleep(0.01)
        assert "connection" in closed
        assert "response" in closed
        assert not fetcher._header_cleanup_unconfirmed.is_set()  # noqa: SLF001
    finally:
        client_socket.close()
        server_socket.close()


def test_default_transport_watchdog_interrupts_a_blocked_body_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cancellation = threading.Event()
    read_started = threading.Event()
    response_closed = threading.Event()
    closed: list[str] = []
    result: list[GovernedWebFetchError] = []

    class Response:
        status = 200

        def getheaders(self):  # type: ignore[no-untyped-def]
            return (("Content-Type", "text/plain"),)

        def read1(self, _size: int) -> bytes:
            read_started.set()
            assert response_closed.wait(2)
            raise OSError("synthetic read was shut down")

        def close(self) -> None:
            closed.append("response")
            response_closed.set()

    class Socket:
        def settimeout(self, _value: float) -> None:
            return None

        def shutdown(self, _how: int) -> None:
            response_closed.set()

        def close(self) -> None:
            response_closed.set()

    class Connection:
        def __init__(self, **_kwargs) -> None:  # type: ignore[no-untyped-def]
            self.sock = Socket()

        def request(self, *_args, **_kwargs) -> None:  # type: ignore[no-untyped-def]
            return None

        def getresponse(self) -> Response:
            return Response()

        def close(self) -> None:
            closed.append("connection")

    monkeypatch.setattr(governed_web_fetch, "_PinnedHttpsConnection", Connection)
    fetcher = PublicHttpsTextFetcher(resolver=_Resolver())

    def fetch() -> None:
        try:
            fetcher.fetch(
                fetcher.prepare("https://public.example.test/"),
                cancellation=cancellation,
            )
        except GovernedWebFetchError as error:
            result.append(error)

    thread = threading.Thread(target=fetch)
    thread.start()
    assert read_started.wait(1)
    cancellation.set()
    thread.join(1)
    assert result and result[0].code == "web_fetch_cancelled"
    assert "response" in closed
    assert "connection" in closed


def test_watchdog_shuts_down_owned_socketpair_before_closing_http_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_socket, server_socket = socket.socketpair()
    cancellation = threading.Event()
    read_started = threading.Event()
    transport_shutdown = threading.Event()
    result: list[GovernedWebFetchError] = []
    server_socket.sendall(
        b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\n"
    )

    class Response(http.client.HTTPResponse):
        def read1(self, size: int) -> bytes:
            read_started.set()
            return super().read1(size)

    class Connection:
        def __init__(self, **_kwargs) -> None:  # type: ignore[no-untyped-def]
            self.sock = client_socket

        def request(self, *_args, **_kwargs) -> None:  # type: ignore[no-untyped-def]
            return None

        def getresponse(self) -> Response:
            response = Response(self.sock)
            response.begin()
            return response

        def close(self) -> None:
            client_socket.close()

    monkeypatch.setattr(governed_web_fetch, "_PinnedHttpsConnection", Connection)
    fetcher = PublicHttpsTextFetcher(resolver=_Resolver())

    def fetch() -> None:
        try:
            fetcher.fetch(
                fetcher.prepare("https://public.example.test/"),
                cancellation=cancellation,
            )
        except GovernedWebFetchError as error:
            result.append(error)

    thread = threading.Thread(target=fetch)
    try:
        thread.start()
        assert read_started.wait(1)
        cancellation.set()
        thread.join(1)
        assert not thread.is_alive()
        assert result and result[0].code == "web_fetch_cancelled"
    finally:
        client_socket.close()
        server_socket.close()


def test_stdlib_response_parser_accepts_delayed_body_within_governed_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_socket, server_socket = socket.socketpair()
    writer_done = threading.Event()

    def write_response() -> None:
        try:
            server_socket.sendall(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n"
                b"Content-Length: 17\r\nConnection: close\r\n\r\n"
            )
            time.sleep(0.12)
            server_socket.sendall(b"delayed reference")
        finally:
            writer_done.set()
            server_socket.close()

    class Connection:
        def __init__(self, **_kwargs) -> None:  # type: ignore[no-untyped-def]
            self.sock = client_socket

        def request(self, *_args, **_kwargs) -> None:  # type: ignore[no-untyped-def]
            return None

        def getresponse(self) -> http.client.HTTPResponse:
            response = http.client.HTTPResponse(self.sock)
            response.begin()
            if response.will_close:
                self.close()
            return response

        def close(self) -> None:
            if self.sock is not None:
                self.sock.close()
                self.sock = None

    monkeypatch.setattr(governed_web_fetch, "_PinnedHttpsConnection", Connection)
    writer = threading.Thread(target=write_response)
    writer.start()
    try:
        fetcher = PublicHttpsTextFetcher(resolver=_Resolver())
        result = fetcher.fetch(fetcher.prepare("https://public.example.test/"))
        assert result.text == "delayed reference"
        assert result.truncated is False
        assert writer_done.wait(1)
    finally:
        client_socket.close()
        server_socket.close()
        writer.join(1)


def test_stdlib_response_parser_enforces_deadline_without_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_socket, server_socket = socket.socketpair()
    server_socket.sendall(
        b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\n"
    )
    monkeypatch.setattr(
        governed_web_fetch, "WEB_FETCH_TOTAL_TIMEOUT_SECONDS", 0.1
    )

    class Connection:
        def __init__(self, **_kwargs) -> None:  # type: ignore[no-untyped-def]
            self.sock = client_socket

        def request(self, *_args, **_kwargs) -> None:  # type: ignore[no-untyped-def]
            return None

        def getresponse(self) -> http.client.HTTPResponse:
            response = http.client.HTTPResponse(self.sock)
            response.begin()
            return response

        def close(self) -> None:
            client_socket.close()

    monkeypatch.setattr(governed_web_fetch, "_PinnedHttpsConnection", Connection)
    try:
        fetcher = PublicHttpsTextFetcher(resolver=_Resolver())
        with pytest.raises(GovernedWebFetchError) as timed_out:
            fetcher.fetch(fetcher.prepare("https://public.example.test/"))
        assert timed_out.value.code == "web_fetch_timeout"
    finally:
        client_socket.close()
        server_socket.close()


def test_raw_reader_retries_tls_want_write_without_waiting_for_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[bool, bool]] = []

    class SyntheticTlsSocket:
        def __init__(self) -> None:
            self.reads = 0

        def pending(self) -> int:
            return 0

        def recv_into(self, view: memoryview) -> int:
            self.reads += 1
            if self.reads == 1:
                raise __import__("ssl").SSLWantWriteError(2, "synthetic want write")
            view[:1] = b"x"
            return 1

    sock = SyntheticTlsSocket()

    def selected(read, write, _errors, _timeout):  # type: ignore[no-untyped-def]
        calls.append((bool(read), bool(write)))
        if read:
            assert write == []
            return [sock], [], []
        assert write == [sock]
        return [], [sock], []

    monkeypatch.setattr(governed_web_fetch.select, "select", selected)
    raw = governed_web_fetch._GovernedSocketRaw(  # noqa: SLF001 - TLS readiness invariant
        sock, deadline=time.monotonic() + 1, cancellation=None, monotonic=time.monotonic
    )
    buffer = bytearray(1)
    assert raw.readinto(buffer) == 1
    assert bytes(buffer) == b"x"
    assert calls == [(True, False), (False, True)]


def test_governed_socket_closes_before_reader_ownership_transfers() -> None:
    client_socket, server_socket = socket.socketpair()
    try:
        facade = governed_web_fetch._GovernedSocket(  # noqa: SLF001 - ownership transfer invariant
            client_socket,
            deadline=time.monotonic() + 1,
            cancellation=None,
            monotonic=time.monotonic,
        )
        facade.close()
        assert client_socket.fileno() == -1
    finally:
        client_socket.close()
        server_socket.close()


def test_parser_construction_failure_closes_transferred_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_socket, server_socket = socket.socketpair()
    server_socket.sendall(b"not an HTTP response\r\n")
    server_socket.close()

    class Connection:
        def __init__(self, **_kwargs) -> None:  # type: ignore[no-untyped-def]
            self.sock = client_socket

        def request(self, *_args, **_kwargs) -> None:  # type: ignore[no-untyped-def]
            return None

        def getresponse(self) -> http.client.HTTPResponse:
            response = http.client.HTTPResponse(self.sock)
            response.begin()
            return response

        def close(self) -> None:
            if self.sock is not None:
                self.sock.close()
                self.sock = None

    monkeypatch.setattr(governed_web_fetch, "_PinnedHttpsConnection", Connection)
    try:
        fetcher = PublicHttpsTextFetcher(resolver=_Resolver())
        with pytest.raises(GovernedWebFetchError) as refused:
            fetcher.fetch(fetcher.prepare("https://public.example.test/"))
        assert refused.value.code == "web_fetch_connect_failed"
        assert client_socket.fileno() == -1
    finally:
        client_socket.close()
        server_socket.close()


def test_capability_route_is_authenticated_content_free_and_never_fetches() -> None:
    calls: list[object] = []

    def require_auth(request: Request) -> None:
        if request.headers.get("x-synthetic-auth") != "granted":
            raise HTTPException(status_code=401)

    def router_for(fetcher=None) -> TestClient:  # type: ignore[no-untyped-def]
        service = LocalAgentService(
            chat=lambda *_args: calls.append(object()),
            active_model=lambda: None,
            fetcher=fetcher,
        )
        app = FastAPI()
        app.include_router(create_local_agent_router(require_auth, lambda *_args: None, service))
        return TestClient(app)

    unavailable = router_for().get("/v1/agent/web-fetch-capability")
    assert unavailable.status_code == 401

    denied = router_for().get(
        "/v1/agent/web-fetch-capability", headers={"x-synthetic-auth": "granted"}
    )
    assert denied.status_code == 200
    assert denied.headers["cache-control"] == "no-store, private"
    assert denied.json() == {
        "contract_version": "agent-web-fetch-capability.v1",
        "available": False,
        "policy_version": "governed-web-fetch.v1",
        "reason_code": "governed_fetcher_unavailable",
        "requires_per_fetch_approval": True,
        "network_scope": "public_https",
    }

    ready = router_for(PublicHttpsTextFetcher(resolver=_Resolver())).get(
        "/v1/agent/web-fetch-capability", headers={"x-synthetic-auth": "granted"}
    )
    assert ready.status_code == 200
    assert ready.json()["available"] is True
    assert ready.json()["reason_code"] == "available"
    assert calls == []
