"""Independent synthetic coverage for the governed public-HTTPS policy."""

from __future__ import annotations

from collections.abc import Iterable
import threading

import pytest

from prompt_enhancer.application.governed_web_fetch import GovernedWebFetchError
from prompt_enhancer.infrastructure.governed_web_fetch import (
    MAX_WEB_FETCH_HEADER_BYTES,
    MAX_WEB_FETCH_HEADER_NAME_BYTES,
    MAX_WEB_FETCH_HEADER_VALUE_BYTES,
    MAX_WEB_FETCH_HEADERS,
    MAX_WEB_FETCH_RESPONSE_BYTES,
    MAX_WEB_FETCH_TEXT_CHARS,
    PinnedWebOrigin,
    PreparedWebFetch,
    PublicHttpsTextFetcher,
    WebFetchResponse,
)


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


def _requester_for(
    *,
    status: int = 200,
    headers: tuple[tuple[str, str], ...] = (("Content-Type", "text/plain"),),
    body: Iterable[bytes] = (b"synthetic body",),
) -> tuple[PublicHttpsTextFetcher, list[str]]:
    closed: list[str] = []

    def requester(
        _origin: PinnedWebOrigin,
        _request: PreparedWebFetch,
        _cancellation: threading.Event | None,
        _deadline: float,
    ) -> WebFetchResponse:
        return WebFetchResponse(
            status,
            headers,
            body,
            close=lambda: closed.append("response"),
        )

    return PublicHttpsTextFetcher(resolver=_Resolver(), requester=requester), closed


def test_prepare_rejects_malformed_targets_without_dns() -> None:
    resolver = _Resolver()
    fetcher = PublicHttpsTextFetcher(resolver=resolver)
    targets = (
        "http://public.example.test/",
        "https://user:secret@public.example.test/",
        "https://public.example.test/path#fragment",
        "https://public.example.test/line\nfeed",
        "https://public.example.test/\u202e",
        "https://public.example.test/" + "x" * 2_048,
    )

    for target in targets:
        with pytest.raises(GovernedWebFetchError) as refused:
            fetcher.prepare(target)
        assert refused.value.code == "web_fetch_url_invalid"

    assert resolver.calls == 0


def test_mixed_public_and_private_dns_answers_are_refused_before_request() -> None:
    resolver = _Resolver(("8.8.8.8", "127.0.0.1"))
    requested: list[object] = []

    def requester(*_args: object) -> WebFetchResponse:
        requested.append(object())
        raise AssertionError("a mixed public/private DNS result must not request")

    fetcher = PublicHttpsTextFetcher(resolver=resolver, requester=requester)
    with pytest.raises(GovernedWebFetchError) as refused:
        fetcher.fetch(fetcher.prepare("https://public.example.test/"))

    assert refused.value.code == "web_fetch_address_not_public"
    assert resolver.calls == 1
    assert requested == []


@pytest.mark.parametrize(
    ("status", "headers", "body", "expected"),
    (
        (302, (("Content-Type", "text/plain"),), (b"redirect",), "web_fetch_redirect_refused"),
        (503, (("Content-Type", "text/plain"),), (b"failure",), "web_fetch_http_status_refused"),
        (200, (("Content-Type", "application/json"),), (b"{}",), "web_fetch_content_type_unsupported"),
        (200, (("Content-Type", "text/plain"), ("Content-Encoding", "gzip")), (b"data",), "web_fetch_content_encoding_unsupported"),
        (200, (("Content-Type", "text/plain"), ("Content-Length", "1"), ("content-length", "1")), (b"x",), "web_fetch_headers_invalid"),
        (200, ([("Content-Type", "text/plain")] + [("X-Synthetic", "ok")] * MAX_WEB_FETCH_HEADERS), (b"data",), "web_fetch_headers_too_large"),
        (200, (("Content-Type", "text/plain"), ("x" * (MAX_WEB_FETCH_HEADER_NAME_BYTES + 1), "v")), (b"data",), "web_fetch_headers_too_large"),
        (200, (("Content-Type", "text/plain"), ("X-Synthetic", "x" * (MAX_WEB_FETCH_HEADER_VALUE_BYTES + 1))), (b"data",), "web_fetch_headers_too_large"),
        (200, tuple(("X-Synthetic", "x" * 600) for _ in range(MAX_WEB_FETCH_HEADERS)), (b"data",), "web_fetch_headers_too_large"),
    ),
)
def test_acquired_response_is_closed_on_status_encoding_mime_and_header_refusal(
    status: int,
    headers: tuple[tuple[str, str], ...] | list[tuple[str, str]],
    body: Iterable[bytes],
    expected: str,
) -> None:
    fetcher, closed = _requester_for(
        status=status,
        headers=tuple(headers),
        body=body,
    )

    with pytest.raises(GovernedWebFetchError) as refused:
        fetcher.fetch(fetcher.prepare("https://public.example.test/resource"))

    assert refused.value.code == expected
    assert closed == ["response"]


def test_declared_response_limit_is_refused_before_body_decode_and_closes() -> None:
    fetcher, closed = _requester_for(
        headers=(
            ("Content-Type", "text/plain"),
            ("Content-Length", str(MAX_WEB_FETCH_RESPONSE_BYTES + 1)),
        ),
        body=(b"\xff",),
    )

    with pytest.raises(GovernedWebFetchError) as refused:
        fetcher.fetch(fetcher.prepare("https://public.example.test/declared"))

    assert refused.value.code == "web_fetch_response_too_large"
    assert closed == ["response"]


def test_streamed_response_limit_is_refused_before_utf8_decode_and_closes() -> None:
    fetcher, closed = _requester_for(
        body=(b"\xff" * (MAX_WEB_FETCH_RESPONSE_BYTES + 1),),
    )

    with pytest.raises(GovernedWebFetchError) as refused:
        fetcher.fetch(fetcher.prepare("https://public.example.test/streamed"))

    assert refused.value.code == "web_fetch_response_too_large"
    assert closed == ["response"]


def test_invalid_utf8_response_is_rejected_and_closes() -> None:
    fetcher, closed = _requester_for(body=(b"valid prefix ", b"\xff"))

    with pytest.raises(GovernedWebFetchError) as refused:
        fetcher.fetch(fetcher.prepare("https://public.example.test/encoding"))

    assert refused.value.code == "web_fetch_text_decode_failed"
    assert closed == ["response"]


def test_html_active_content_is_removed_and_truncation_is_explicit() -> None:
    visible = "visible synthetic reference "
    html = (
        b"<head>secret-head</head><p>"
        + visible.encode()
        + b"<script>secret-script()</script><style>secret-style</style>"
        + b"<svg>secret-svg</svg><canvas>secret-canvas</canvas>"
        + b"<template>secret-template</template><noscript>secret-noscript</noscript>"
        + (visible.encode() * ((MAX_WEB_FETCH_TEXT_CHARS // len(visible)) + 4))
        + b"</p>"
    )
    fetcher, closed = _requester_for(
        headers=(("Content-Type", "text/html; charset=utf-8"),),
        body=(html,),
    )

    result = fetcher.fetch(fetcher.prepare("https://public.example.test/html"))

    assert result.content_type == "text/html"
    assert result.truncated is True
    assert "visible synthetic reference" in result.text
    assert "secret-script" not in result.text
    assert "secret-style" not in result.text
    assert "secret-head" not in result.text
    assert "secret-svg" not in result.text
    assert "secret-canvas" not in result.text
    assert "secret-template" not in result.text
    assert "secret-noscript" not in result.text
    assert "[Fetch text truncated by governed policy.]" in result.text
    assert closed == ["response"]


def test_empty_acquired_response_is_rejected_and_closed() -> None:
    fetcher, closed = _requester_for(body=())

    with pytest.raises(GovernedWebFetchError) as refused:
        fetcher.fetch(fetcher.prepare("https://public.example.test/empty"))

    assert refused.value.code == "web_fetch_response_empty"
    assert closed == ["response"]


def test_declared_content_length_mismatch_does_not_weaken_stream_limit() -> None:
    fetcher, closed = _requester_for(
        headers=(
            ("Content-Type", "text/plain"),
            ("Content-Length", "1"),
        ),
        body=(b"\xff" * (MAX_WEB_FETCH_RESPONSE_BYTES + 1),),
    )

    with pytest.raises(GovernedWebFetchError) as refused:
        fetcher.fetch(fetcher.prepare("https://public.example.test/mismatch"))

    assert refused.value.code == "web_fetch_response_too_large"
    assert closed == ["response"]


def test_header_budget_boundary_is_checked_before_content_processing() -> None:
    # Keep this fixture just over the aggregate budget while staying below the
    # per-name/value and count limits, so the aggregate guard is the observed
    # reason rather than an unrelated MIME or body refusal.
    value_size = (MAX_WEB_FETCH_HEADER_BYTES // MAX_WEB_FETCH_HEADERS) + 1
    headers = tuple(
        ("X-Synthetic", "x" * value_size)
        for _ in range(MAX_WEB_FETCH_HEADERS)
    )
    fetcher, closed = _requester_for(headers=headers, body=(b"ignored",))

    with pytest.raises(GovernedWebFetchError) as refused:
        fetcher.fetch(fetcher.prepare("https://public.example.test/header-budget"))

    assert refused.value.code == "web_fetch_headers_too_large"
    assert closed == ["response"]
