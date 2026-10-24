"""Content-free transport diagnostics with no network or provider requests."""
import http.client
import ssl
import traceback

import pytest

from prompt_enhancer.application.inference import InferenceTransportError
from prompt_enhancer.infrastructure.litellm import LiteLLMChat, MAX_RESPONSE_BYTES
from test_litellm import Connection, certificate, install, settings


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("status,code", [
    (201, "gateway_http_unexpected_status"), (302, "gateway_http_redirect"),
    (400, "gateway_http_client_error"), (401, "gateway_http_unauthorized"),
    (403, "gateway_http_forbidden"), (429, "gateway_http_rate_limited"),
    (502, "gateway_http_server_error"),
])
def test_http_failure_categories_keep_bodies_private_and_never_retry(monkeypatch, strict, status, code):
    connection = Connection(status=status, data=b"EXAMPLE_PRIVATE_RESPONSE")
    def never_read(*args):
        pytest.fail("Rejected response bodies must not be read")
    connection.read = never_read
    created = install(monkeypatch, connection)
    adapter = LiteLLMChat(settings(), report_failures=strict)
    if strict:
        with pytest.raises(InferenceTransportError) as caught:
            adapter("example-qwen", b'{"messages":[]}')
        assert caught.value.code == code and str(caught.value) == code
    else:
        assert adapter("example-qwen", b'{"messages":[]}') == (502, b"{}", "application/json")
    assert len(created) == len(connection.requests) == 1 and connection.closed


@pytest.mark.parametrize("phase,error,code", [
    ("connect", TimeoutError, "gateway_connect_timeout"),
    ("connect", ConnectionRefusedError, "gateway_connect_failed"),
    ("connect", ssl.SSLCertVerificationError, "gateway_tls_failed"),
    ("request", TimeoutError, "gateway_io_timeout"),
    ("request", BrokenPipeError, "gateway_io_failed"),
    ("getresponse", TimeoutError, "gateway_io_timeout"),
    ("getresponse", http.client.BadStatusLine, "gateway_protocol_error"),
    ("read", TimeoutError, "gateway_io_timeout"),
    ("read", ConnectionResetError, "gateway_io_failed"),
    ("read", ssl.SSLError, "gateway_tls_failed"),
])
def test_transport_phase_keeps_safe_category_and_suppresses_exception_text(monkeypatch, phase, error, code):
    connection = Connection()
    def fail(*args):
        raise error("EXAMPLE_PRIVATE_EXCEPTION")
    setattr(connection, phase, fail)
    created = install(monkeypatch, connection)
    with pytest.raises(InferenceTransportError) as caught:
        LiteLLMChat(settings(), report_failures=True)("example-qwen", b'{"messages":[]}')
    assert caught.value.code == code and str(caught.value) == code
    assert "EXAMPLE_PRIVATE_EXCEPTION" not in "".join(traceback.format_exception(caught.value))
    assert len(created) == 1 and connection.closed
    assert len(connection.requests) == (0 if phase in {"connect", "request"} else 1)


@pytest.mark.parametrize("failure,code", [
    ("pin", "gateway_tls_failed"), ("route", "gateway_route_mismatch"),
    ("size", "gateway_response_too_large"), ("payload", "gateway_request_invalid"),
    ("alias", "gateway_request_invalid"),
])
def test_strict_validation_keeps_existing_tls_route_and_size_boundaries(monkeypatch, certificate, failure, code):
    connection = Connection(data=b"x" * (MAX_RESPONSE_BYTES + 1) if failure == "size" else b"{}")
    connection.getheader = lambda *args: "example-other-route"
    install(monkeypatch, connection)
    config = settings(tls_cert_pem=certificate) if failure == "pin" else settings()
    with pytest.raises(InferenceTransportError) as caught:
        LiteLLMChat(config, report_failures=True,
                    expected_route_id="example-route" if failure == "route" else None)(
            "example-other-alias" if failure == "alias" else "example-qwen",
            b"not JSON" if failure == "payload" else b'{"messages":[]}')
    assert caught.value.code == code
    assert len(connection.requests) == (1 if failure in {"route", "size"} else 0)
    assert connection.closed == (failure not in {"payload", "alias"})


def test_unrecognized_transport_code_is_not_exposed():
    assert str(InferenceTransportError("EXAMPLE_PRIVATE_ERROR")) == "gateway_protocol_error"
