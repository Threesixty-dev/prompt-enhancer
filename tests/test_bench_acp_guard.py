"""Synthetic ACP messages; no model, provider session or credential access."""

import io
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading

import pytest

from deployment.bench.acp_guard import FailureGuard, ProtocolError, read_message, write_message
from deployment.bench import acp_guard


def metadata(**values):
    return {"_meta": {"jetbrains": {"air": {"version": 1, **values}}}}


def negotiated():
    guard = FailureGuard()
    guard.client_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    guard.server_message({"jsonrpc": "2.0", "id": 1, "result": metadata(capabilities=["sessionFailure"])})
    return guard


def prompt(guard, identifier="example-request"):
    request = {"jsonrpc": "2.0", "id": identifier, "method": "session/prompt",
               "params": {"sessionId": "example-session", "prompt": [{"type": "text", "text": "Fictional widget"}]}}
    assert guard.client_message(request) == request
    return identifier


def test_guard_negotiates_failure_capability_without_mutating_other_client_settings():
    original = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": 1, "clientCapabilities": {"fs": {"readTextFile": False},
        **metadata(capabilities=["example-existing"])}}}
    before = json.dumps(original)
    result = FailureGuard().client_message(original)
    assert result["params"]["protocolVersion"] == 1
    assert result["params"]["clientCapabilities"]["fs"] == {"readTextFile": False}
    assert result["params"]["clientCapabilities"]["_meta"]["jetbrains"]["air"] == {
        "version": 1, "capabilities": ["example-existing", "sessionFailure"]}
    assert json.dumps(original) == before


@pytest.mark.parametrize("category", ["connection", "access", "limit", "request", "service", "unknown"])
def test_terminal_failure_is_a_protocol_error_and_never_an_assistant_reply(category):
    guard = negotiated()
    identifier = prompt(guard)
    result = guard.server_message({"jsonrpc": "2.0", "id": identifier, "result": {
        "stopReason": "end_turn", **metadata(sessionFailure={"id": "example-turn:error", "revision": 1,
            "category": category, "severity": "error", "title": "example-private-provider-detail",
            "details": "example-private-token", "actions": ["retry"]})}})
    assert result == {"jsonrpc": "2.0", "id": identifier, "error": {
        "code": -32603, "message": "bench_consumer_upstream_" + category}}
    assert "example-private" not in json.dumps(result)


@pytest.mark.parametrize("category", ["example-unsupported", None, {}, []])
def test_unknown_failure_category_remains_unknown(category):
    guard = negotiated()
    identifier = prompt(guard)
    result = guard.server_message({"jsonrpc": "2.0", "id": identifier,
        "result": metadata(sessionFailure={"category": category})})
    assert result["error"]["message"] == "bench_consumer_upstream_unknown"


def test_success_warning_cancellation_and_model_text_do_not_become_transport_failures():
    guard = negotiated()
    notification = {"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": "example-session",
        "update": {"sessionUpdate": "agent_message_chunk", "content": {
            "type": "text", "text": "bench_consumer_upstream_limit"}}}}
    assert guard.server_message(notification) is notification
    for result in ({"stopReason": "end_turn"}, {"stopReason": "cancelled"},
                   {"stopReason": "end_turn", **metadata(sessionFailure={"severity": "warning", "category": "limit"})}):
        identifier = prompt(guard)
        response = {"jsonrpc": "2.0", "id": identifier, "result": result}
        assert guard.server_message(response) is response


def test_foreign_late_failure_and_server_request_cannot_consume_current_prompt_id():
    guard = negotiated()
    identifier = prompt(guard, 3)
    late = {"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": "example-session",
        "update": {"sessionUpdate": "session_info_update", **metadata(sessionFailure={"severity": "error"})}}}
    request = {"jsonrpc": "2.0", "id": 3, "method": "fs/read_text_file", "params": {}}
    assert guard.server_message(late) is late
    assert guard.server_message(request) is request
    response = {"jsonrpc": "2.0", "id": identifier, "result": {"stopReason": "end_turn"}}
    assert guard.server_message(response) is response


@pytest.mark.parametrize("result", [{}, metadata(capabilities=[]), metadata(capabilities=None),
    {"_meta": {"jetbrains": {"air": {"version": 2, "capabilities": ["sessionFailure"]}}}}])
def test_unsupported_server_cannot_silently_use_legacy_failure_text(result):
    guard = FailureGuard()
    guard.client_message({"id": 1, "method": "initialize", "params": {}})
    with pytest.raises(ProtocolError):
        guard.server_message({"id": 1, "result": result})
    with pytest.raises(ProtocolError):
        prompt(guard)


def test_existing_rpc_errors_are_content_free_and_requests_are_not_replayed():
    guard = negotiated()
    identifier = prompt(guard)
    result = guard.server_message({"jsonrpc": "2.0", "id": identifier,
        "error": {"code": -32603, "message": "example-private-error", "data": "example-private-token"}})
    assert result["error"] == {"code": -32603, "message": "bench_consumer_upstream_unknown"}
    assert guard.pending == {}


@pytest.mark.parametrize("payload", [b"[]\n", b"not-json\n", b"{}", b"\xff\n"])
def test_invalid_wire_frames_fail_closed(payload):
    with pytest.raises(ProtocolError):
        read_message(io.BytesIO(payload))


def test_messages_round_trip_with_unicode_and_eof_is_explicit():
    message = {"jsonrpc": "2.0", "id": "example", "result": {"text": "\u017c\u00f3\u0142\u0107"}}
    stream = io.BytesIO()
    write_message(stream, message)
    stream.seek(0)
    assert read_message(stream) == message
    assert read_message(stream) is None


def test_duplicate_requests_and_unbounded_pending_ids_are_rejected():
    guard = negotiated()
    prompt(guard, 10)
    with pytest.raises(ProtocolError):
        prompt(guard, 10)
    for identifier in range(11, 74):
        prompt(guard, identifier)
    with pytest.raises(ProtocolError):
        prompt(guard, 74)


@pytest.mark.parametrize("failure", [None, [], {"severity": "example-invalid"}])
def test_malformed_terminal_failure_never_becomes_a_success(failure):
    guard = negotiated()
    identifier = prompt(guard)
    with pytest.raises(ProtocolError):
        guard.server_message({"id": identifier, "result": metadata(sessionFailure=failure)})


def test_frame_limits_apply_before_decoding_and_after_encoding(monkeypatch):
    monkeypatch.setattr(acp_guard, "MAX_FRAME", 32)
    with pytest.raises(ProtocolError):
        read_message(io.BytesIO(b'{"text":"' + b'x' * 32 + b'"}\n'))
    with pytest.raises(ProtocolError):
        write_message(io.BytesIO(), {"text": "x" * 32})


def test_unsupported_vendor_version_never_starts_protocol_bridge(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(acp_guard.signal, "signal", lambda *args: None)
    monkeypatch.setattr(acp_guard.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout="example 2.0.0"))
    monkeypatch.setattr(acp_guard, "bridge", lambda *args: pytest.fail("unsupported adapter executed"))
    assert acp_guard.main() == 1


def test_owned_protocol_process_delivers_typed_failure_and_stops_on_disconnect():
    vendor = """import sys,json
for line in sys.stdin:
 request=json.loads(line)
 if request['method']=='initialize':
  assert 'sessionFailure' in request['params']['clientCapabilities']['_meta']['jetbrains']['air']['capabilities']
  result={'_meta':{'jetbrains':{'air':{'version':1,'capabilities':['sessionFailure']}}}}
 else:
  result={'stopReason':'end_turn','_meta':{'jetbrains':{'air':{'version':1,'sessionFailure':{'category':'limit','severity':'error','title':'example-private'}}}}}
 print(json.dumps({'jsonrpc':'2.0','id':request['id'],'result':result}),flush=True)
"""
    harness = ("from deployment.bench.acp_guard import bridge; import sys; "
               "raise SystemExit(bridge([sys.executable,'-c'," + repr(vendor) + "],sys.stdin.buffer,sys.stdout.buffer))")
    process = subprocess.Popen([sys.executable, "-c", harness], cwd=Path(__file__).resolve().parents[1],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    def response():
        received = queue.Queue()
        threading.Thread(target=lambda: received.put(read_message(process.stdout)), daemon=True).start()
        return received.get(timeout=5)
    try:
        write_message(process.stdin, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert response()["id"] == 1
        write_message(process.stdin, {"jsonrpc": "2.0", "id": 2, "method": "session/prompt", "params": {}})
        assert response() == {"jsonrpc": "2.0", "id": 2,
            "error": {"code": -32603, "message": "bench_consumer_upstream_limit"}}
        process.stdin.close()
        process.wait(timeout=10)
        assert process.stderr.read() == b""
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
