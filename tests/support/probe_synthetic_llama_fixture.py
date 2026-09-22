"""Reviewed, bounded loopback protocol gate for an explicitly hashed test fixture."""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import tempfile
import time

from prompt_enhancer.application.owned_process import run_owned_process, start_owned_process, terminate_owned_process
from packaged_serve_probe import _ephemeral_loopback_port, _port_is_released
from prepare_synthetic_llama_fixture import QuietParser, checked_path, fingerprint, gguf_payload, SOURCE, REPOSITORY

CONTRACT = "synthetic-llama-protocol-probe.v1"
FLAGS = ("manifest_verified", "version_verified", "invalid_host_refused", "invalid_gpu_refused",
         "health_verified", "models_verified", "input_tokens_verified", "completion_verified",
         "sse_verified", "cancellation_disconnected", "fresh_request_verified", "malformed_refused",
         "oversize_refused", "unknown_scenario_refused", "owned_tree_stopped",
         "process_handles_closed", "port_released")


class ProbeFailure(Exception):
    pass


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProbeFailure()
        result[key] = value
    return result


def decode(payload: bytes):
    if len(payload) > 16384:
        raise ProbeFailure()
    return json.loads(payload, object_pairs_hook=unique_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(ProbeFailure()))


def verify_fixture(root: Path, manifest_hash: str) -> tuple[Path, Path]:
    if os.name != "nt" or re.fullmatch(r"[0-9a-f]{64}", manifest_hash) is None:
        raise ProbeFailure()
    root = checked_path(root, directory=True)
    for protected in (REPOSITORY.resolve(), Path.home().resolve()):
        if root.is_relative_to(protected) or protected.is_relative_to(root):
            raise ProbeFailure()
    manifest = checked_path(root / "fixture-manifest.json", directory=False)
    with manifest.open("rb") as stream:
        content = stream.read(16385)
    if len(content) > 16384 or hashlib.sha256(content).hexdigest() != manifest_hash:
        raise ProbeFailure()
    data = decode(content)
    if data.get("contract") != "synthetic-llama-fixture-build.v1" or data.get("passed") is not True or data.get("inference_capable") is not False:
        raise ProbeFailure()
    executable = checked_path(root / "synthetic-llama-server.exe", directory=False)
    model = checked_path(root / "synthetic-fixture.gguf", directory=False)
    for file, key in ((executable, "executable"), (model, "model"), (SOURCE.absolute(), "source")):
        if fingerprint(file) != data.get(key):
            raise ProbeFailure()
    with model.open("rb") as stream:
        if stream.read(25) != gguf_payload():
            raise ProbeFailure()
    return executable, model


def arguments(executable: Path, model: Path, port: int, *, host="127.0.0.1", gpu="0") -> list[str]:
    if type(port) is not int or not 1024 <= port <= 65535 or port in {8765, 8766}:
        raise ProbeFailure()
    return [str(executable), "-m", str(model), "--host", host, "--port", str(port),
            "-ngl", gpu, "-c", "4096", "--no-webui"]


def body(prompt="Synthetic streaming acceptance.", *, stream=False) -> bytes:
    return json.dumps({"model": "synthetic-fixture", "messages": [{"role": "user", "content": prompt}],
                       "stream": stream}, separators=(",", ":")).encode("ascii")


def request(port: int, method: str, path: str, payload: bytes | None = None, *, oversized=False):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=0.5)
    try:
        headers = {"Content-Type": "application/json"}
        if oversized:
            headers["Content-Length"] = "262145"
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        content = response.read(16385)
        if len(content) > 16384:
            raise ProbeFailure()
        return response.status, content
    finally:
        connection.close()


def sse(port: int, *, cancel: bool, deadline: float) -> int:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=0.5)
    response = None
    try:
        prompt = "Synthetic cancellation acceptance." if cancel else "Synthetic streaming acceptance."
        connection.request("POST", "/v1/chat/completions", body(prompt, stream=True), {"Content-Type": "application/json"})
        response = connection.getresponse()
        if response.status != 200 or response.getheader("Content-Type") != "text/event-stream":
            raise ProbeFailure()
        chunks = 0
        finished = False
        for _ in range(16):
            if time.monotonic() >= deadline:
                raise ProbeFailure()
            line = response.readline(2049)
            if len(line) > 2048:
                raise ProbeFailure()
            if line == b"\n":
                continue
            if line == b"data: [DONE]\n":
                if chunks == 3 and finished:
                    return chunks
                raise ProbeFailure()
            if not line.startswith(b"data: "):
                raise ProbeFailure()
            choice = decode(line[6:])["choices"][0]
            if choice == {"index": 0, "delta": {"content": "Synthetic chunk. "}, "finish_reason": None}:
                chunks += 1
                if cancel:
                    return chunks
            elif choice == {"index": 0, "delta": {}, "finish_reason": "stop"}:
                finished = True
            else:
                raise ProbeFailure()
        raise ProbeFailure()
    finally:
        if response is not None:
            response.close()
        connection.close()


def probe(root: Path, manifest_hash: str) -> dict:
    report = {"contract": CONTRACT, "passed": False, "error_code": None,
              "sse_chunks": 0, "invalid_launches": 0, **{key: False for key in FLAGS}}
    process = None
    port = None
    phase = "fixture_validation_failed"
    deadline = time.monotonic() + 25
    try:
        executable, model = verify_fixture(root, manifest_hash)
        report["manifest_verified"] = True
        working = Path(tempfile.mkdtemp(prefix="protocol-", dir=executable.parent))
        for name in ("home", "temp", "local", "roaming"):
            (working / name).mkdir()
        system = os.environ.get("SystemRoot", "")
        env = {"SystemRoot": system, "WINDIR": system, "PATH": str(Path(system) / "System32"),
               "HOME": str(working / "home"), "USERPROFILE": str(working / "home"),
               "TEMP": str(working / "temp"), "TMP": str(working / "temp"),
               "LOCALAPPDATA": str(working / "local"), "APPDATA": str(working / "roaming")}
        phase = "version_failed"
        result = run_owned_process([str(executable), "--version"], cwd=working, env=env,
                                  timeout=3, stdout_limit=256, stderr_limit=256, maximum_active_processes=1)
        if result.returncode != 0 or result.stdout.replace(b"\r\n", b"\n") != b"synthetic-llama-fixture.v1 (no inference)\n" or result.stderr:
            raise ProbeFailure()
        del result
        report["version_verified"] = True
        port = _ephemeral_loopback_port()
        for key, overrides in (("invalid_host_refused", {"host": "0.0.0.0"}), ("invalid_gpu_refused", {"gpu": "1"})):
            phase = "invalid_arguments_accepted"
            result = run_owned_process(arguments(executable, model, port, **overrides), cwd=working, env=env,
                                      timeout=3, stdout_limit=256, stderr_limit=256, maximum_active_processes=1)
            if result.returncode != 2 or result.stdout or result.stderr or not _port_is_released(port):
                raise ProbeFailure()
            del result
            report[key] = True
            report["invalid_launches"] += 1
        phase = "server_start_failed"
        process = start_owned_process(arguments(executable, model, port), cwd=working, env=env,
                                      pipe_stdin=False, capture_stdout=False, capture_stderr=False,
                                      maximum_active_processes=1)
        ready_until = min(deadline, time.monotonic() + 5)
        while time.monotonic() < ready_until:
            try:
                status, content = request(port, "GET", "/health")
                if status == 200 and decode(content) == {"status": "ok"}:
                    report["health_verified"] = True
                    break
            except OSError:
                pass
            time.sleep(0.05)
        if not report["health_verified"]:
            raise ProbeFailure()
        checks = (
            ("models_verified", "GET", "/v1/models", None, 200, {"data": [{"id": "synthetic-fixture", "input_modalities": ["text"]}]}),
            ("input_tokens_verified", "POST", "/v1/chat/completions/input_tokens", body(), 200, {"object": "response.input_tokens", "input_tokens": 32}),
            ("completion_verified", "POST", "/v1/chat/completions", body(), 200, {"choices": [{"message": {"role": "assistant", "content": "Synthetic fixture answer."}, "finish_reason": "stop"}]}),
            ("malformed_refused", "POST", "/v1/chat/completions", b"{", 400, {"error": "synthetic_scenario_refused"}),
            ("unknown_scenario_refused", "POST", "/v1/chat/completions", body("Unknown synthetic scenario."), 400, {"error": "synthetic_scenario_refused"}),
        )
        for key, method, path, payload, expected_status, expected in checks:
            phase = key + "_failed"
            if time.monotonic() >= deadline:
                raise ProbeFailure()
            status, content = request(port, method, path, payload)
            if status != expected_status or decode(content) != expected:
                raise ProbeFailure()
            report[key] = True
        phase = "oversize_refused_failed"
        status, content = request(port, "POST", "/v1/chat/completions", b"", oversized=True)
        report["oversize_refused"] = status == 400 and decode(content) == {"error": "synthetic_request_refused"}
        if not report["oversize_refused"]:
            raise ProbeFailure()
        phase = "sse_failed"
        report["sse_chunks"] = sse(port, cancel=False, deadline=deadline)
        report["sse_verified"] = report["sse_chunks"] == 3
        phase = "cancellation_failed"
        report["cancellation_disconnected"] = sse(port, cancel=True, deadline=deadline) == 1
        status, content = request(port, "POST", "/v1/chat/completions", body("Synthetic retry acceptance."))
        report["fresh_request_verified"] = status == 200 and decode(content) == checks[2][5]
        if time.monotonic() >= deadline or not report["fresh_request_verified"]:
            raise ProbeFailure()
    except Exception:
        report["error_code"] = phase
    finally:
        if process is not None:
            try:
                report["owned_tree_stopped"] = terminate_owned_process(process, graceful_timeout=0.1, forced_timeout=2)
            except Exception:
                pass
            try:
                report["process_handles_closed"] = bool(process.close(close_streams=True))
            except Exception:
                pass
        if port is not None:
            until = time.monotonic() + 1
            while time.monotonic() < until:
                if _port_is_released(port):
                    report["port_released"] = True
                    break
                time.sleep(0.05)
        if report["error_code"] is None and not all(report[key] for key in FLAGS):
            report["error_code"] = "cleanup_or_contract_unconfirmed"
        report["passed"] = report["error_code"] is None and all(report[key] for key in FLAGS)
    return report


def main(argv=None):
    try:
        parser = QuietParser(description=__doc__)
        parser.add_argument("--fixture-root", type=Path, required=True)
        parser.add_argument("--manifest-sha256", required=True)
        args = parser.parse_args(argv)
        report = probe(args.fixture_root, args.manifest_sha256)
    except Exception:
        report = {"contract": CONTRACT, "passed": False, "error_code": "invalid_arguments"}
    print("SYNTHETIC_LLAMA_PROTOCOL_PROBE=" + json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
