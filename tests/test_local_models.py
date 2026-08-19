"""Local model runtimes (ADR 0013): registry, device mapping, activation,
chat proxy, downloads - against a stub llama-server, never a real model."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import time

from fastapi.testclient import TestClient

from prompt_enhancer.api import API_TOKEN_HEADER
from prompt_enhancer.application.local_models import (
    ActivateLocalModel,
    AddLocalModel,
    DeviceMode,
    DownloadRequest,
    HardwareSummary,
    LocalModelError,
    LocalModelService,
    RuntimeState,
    detect_llama_server,
    estimate_gpu_layers,
)
from prompt_enhancer.bootstrap import bootstrap_local_application
from prompt_enhancer.config import AppSettings


T0 = datetime(2026, 3, 4, 9, 0, tzinfo=UTC)

STUB_SERVER = textwrap.dedent(
    '''
    import json, sys
    from http.server import BaseHTTPRequestHandler, HTTPServer

    args = sys.argv[1:]
    port = int(args[args.index("--port") + 1])
    ngl = args[args.index("-ngl") + 1]
    ctx = args[args.index("-c") + 1]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_GET(self):
            if self.path == "/health":
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(b'{"status":"ok"}')
            else:
                self.send_response(404); self.end_headers()
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            text = "echo:" + body["messages"][-1]["content"] + " ngl=" + ngl + " ctx=" + ctx
            if body["messages"][-1]["content"] == "overflow":
                self.send_response(400); self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(b'{"error": {"code": 400, "message": "context too long"}}')
                return
            if body.get("stream") is True:
                self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
                for index, piece in enumerate(text.split(" ")):
                    chunk = {"id": "stub", "object": "chat.completion.chunk", "model": body.get("model"),
                             "choices": [{"index": 0, "delta": {"content": ("" if index == 0 else " ") + piece}, "finish_reason": None}]}
                    self.wfile.write(("data: " + json.dumps(chunk) + "\\n\\n").encode("utf-8")); self.wfile.flush()
                self.wfile.write(b"data: [DONE]\\n\\n"); self.wfile.flush()
                return
            reply = {"id": "stub", "object": "chat.completion", "model": body.get("model"),
                     "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                        "finish_reason": "stop"}], "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
            data = json.dumps(reply).encode("utf-8")
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(data)

    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
    '''
)


def _stub_binary(tmp_path: Path) -> Path:
    script = tmp_path / "stub_llama_server.py"
    script.write_text(STUB_SERVER, encoding="utf-8")
    return script


def _stub_popen(script: Path):
    def popen(command, **kwargs):
        # The service invokes "<binary> -m ... --port N -ngl N -c N"; run the stub through the interpreter.
        return subprocess.Popen([sys.executable, str(script), *command[1:]], **kwargs)
    return popen


def _weights(tmp_path: Path, name: str = "example-q4.gguf", size: int = 4096) -> Path:
    path = tmp_path / name
    path.write_bytes(b"GGUF" + b"\0" * (size - 4))
    return path


def _service(tmp_path: Path, *, gpu_free_mb: int | None = 12000) -> LocalModelService:
    script = _stub_binary(tmp_path)
    return LocalModelService(
        tmp_path / "local-models",
        llama_server=lambda: script,
        hardware=lambda binary: HardwareSummary(gpu_name="Example GPU", gpu_memory_mb=16384, gpu_memory_free_mb=gpu_free_mb, ram_mb=32768, llama_server_path=str(binary) if binary else None),
        popen=_stub_popen(script),
        clock=lambda: T0,
        health_timeout_seconds=30,
    )


def test_detection_honours_env_override_and_path(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    assert detect_llama_server({"PROMPT_ENHANCER_LLAMA_SERVER": str(missing)}) is None
    present = tmp_path / "llama-server"
    present.write_text("", encoding="utf-8")
    assert detect_llama_server({"PROMPT_ENHANCER_LLAMA_SERVER": str(present)}) == present


def test_detection_prefers_the_app_runtimes_folder_over_path(tmp_path: Path) -> None:
    home = tmp_path / "app"
    runtime = home / "runtimes" / "llama.cpp" / "llama-server.exe"
    runtime.parent.mkdir(parents=True)
    runtime.write_text("", encoding="utf-8")
    assert detect_llama_server({}, app_home=home) == runtime
    assert detect_llama_server({}, app_home=tmp_path / "elsewhere") in (None, detect_llama_server({}))


def test_split_estimate_is_conservative_and_never_guesses() -> None:
    assert estimate_gpu_layers(size_bytes=None, layer_count=64, gpu_memory_free_mb=16000, context_size=8192) == 0
    assert estimate_gpu_layers(size_bytes=16 * 1024 ** 3, layer_count=64, gpu_memory_free_mb=None, context_size=8192) == 0
    # 16 GiB over 64 layers = 256 MiB per layer; 16 GB free minus ~2.5 GB headroom -> about 52 layers.
    layers = estimate_gpu_layers(size_bytes=16 * 1024 ** 3, layer_count=64, gpu_memory_free_mb=16000, context_size=8192)
    assert 40 <= layers < 64
    assert estimate_gpu_layers(size_bytes=16 * 1024 ** 3, layer_count=64, gpu_memory_free_mb=1000, context_size=8192) == 0


def test_registry_activation_devices_chat_and_deactivation(tmp_path: Path) -> None:
    service = _service(tmp_path)
    weights = _weights(tmp_path)
    record = service.add(AddLocalModel(alias="qwen-test", path=str(weights), layer_count=8, default_device=DeviceMode.SPLIT))
    assert record.size_bytes == 4096 and record.layer_count == 8
    assert [m.alias for m in service.registry.list()] == ["qwen-test"]
    try:
        service.add(AddLocalModel(alias="qwen-test", path=str(weights)))
    except LocalModelError as error:
        assert error.code == "alias_exists"
    else:
        raise AssertionError("duplicate alias accepted")

    overview = service.overview()
    assert overview.runtime_available is True and overview.hardware.gpu_name == "Example GPU"
    assert overview.models[0].runtime.state is RuntimeState.STOPPED
    assert overview.models[0].endpoint_path == "/v1/local-models/qwen-test/chat/completions"

    # cpu -> no offload; gpu -> all layers; split -> estimate (tiny file fits fully).
    status = service.activate("qwen-test", ActivateLocalModel(device=DeviceMode.CPU))
    assert status.runtime.state is RuntimeState.RUNNING and status.runtime.gpu_layers == 0 and status.runtime.device is DeviceMode.CPU
    code, payload, content_type = service.chat("qwen-test", json.dumps({"messages": [{"role": "user", "content": "hi"}]}).encode("utf-8"))
    assert code == 200 and content_type.startswith("application/json")
    reply = json.loads(payload)
    assert reply["choices"][0]["message"]["content"] == "echo:hi ngl=0 ctx=8192"
    assert reply["model"] == "qwen-test"

    status = service.activate("qwen-test", ActivateLocalModel(device=DeviceMode.GPU, context_size=4096))
    assert status.runtime.gpu_layers == 999 and status.runtime.context_size == 4096
    code, payload, _ = service.chat("qwen-test", json.dumps({"messages": [{"role": "user", "content": "x"}]}).encode("utf-8"))
    assert json.loads(payload)["choices"][0]["message"]["content"].endswith("ngl=999 ctx=4096")
    assert service.running_aliases() == ("qwen-test",)

    # stream=true relays the runtime's server-sent events line by line and ends with [DONE].
    upstream = service.open_chat("qwen-test", json.dumps({"stream": True, "messages": [{"role": "user", "content": "a b"}]}).encode("utf-8"))
    assert upstream.status_code == 200 and upstream.content_type == "text/event-stream" and upstream.lines is not None and upstream.body is None
    lines = list(upstream.lines)
    events = [json.loads(line[len(b"data: "):]) for line in lines if line.startswith(b"data: ") and b"[DONE]" not in line]
    assert "".join(event["choices"][0]["delta"]["content"] for event in events) == "echo:a b ngl=999 ctx=4096"
    assert lines[-2] == b"data: [DONE]\n"
    # A non-streaming request through open_chat is a complete JSON body; an upstream 4xx stays a JSON error.
    plain = service.open_chat("qwen-test", json.dumps({"messages": [{"role": "user", "content": "x"}]}).encode("utf-8"))
    assert plain.lines is None and plain.status_code == 200 and json.loads(plain.body)["choices"][0]["message"]["content"].startswith("echo:x")
    overflow = service.open_chat("qwen-test", json.dumps({"stream": True, "messages": [{"role": "user", "content": "overflow"}]}).encode("utf-8"))
    assert overflow.status_code == 400 and overflow.lines is None and b"context too long" in (overflow.body or b"")

    status = service.activate("qwen-test", ActivateLocalModel(device=DeviceMode.SPLIT))
    assert status.runtime.device is DeviceMode.SPLIT and status.runtime.gpu_layers == 8  # whole tiny model fits
    status = service.activate("qwen-test", ActivateLocalModel(device=DeviceMode.SPLIT, gpu_layers=3))
    assert status.runtime.gpu_layers == 3
    # "remember" keeps the tuned split for next time; a plain split activation reuses it.
    status = service.activate("qwen-test", ActivateLocalModel(device=DeviceMode.SPLIT, gpu_layers=5, remember=True))
    assert service.registry.get("qwen-test").default_gpu_layers == 5
    status = service.activate("qwen-test", ActivateLocalModel(device=DeviceMode.SPLIT))
    assert status.runtime.gpu_layers == 5

    service.deactivate("qwen-test")
    assert service.status("qwen-test").runtime.state is RuntimeState.STOPPED
    try:
        service.chat("qwen-test", b'{"messages": []}')
    except LocalModelError as error:
        assert error.code == "model_not_active"
    else:
        raise AssertionError("chat without an active runtime")
    service.shutdown()


def test_activation_fails_closed_without_runtime_or_weights(tmp_path: Path) -> None:
    service = LocalModelService(tmp_path / "local-models", llama_server=lambda: None, hardware=lambda _b: HardwareSummary(), clock=lambda: T0)
    weights = _weights(tmp_path)
    service.add(AddLocalModel(alias="m", path=str(weights)))
    try:
        service.activate("m")
    except LocalModelError as error:
        assert error.code == "runtime_unavailable"
    else:
        raise AssertionError("activated without a runtime")
    assert service.overview().runtime_available is False
    weights.unlink()
    with_runtime = _service(tmp_path)
    with_runtime.registry.upsert(service.registry.get("m"))
    try:
        with_runtime.activate("m")
    except LocalModelError as error:
        assert error.code == "model_file_missing"
    else:
        raise AssertionError("activated without weights")


def test_download_requires_confirmed_size_and_registers_the_model(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def fake_download(*, repo_id: str, filename: str, local_dir: Path) -> Path:
        calls.append({"repo_id": repo_id, "filename": filename})
        path = Path(local_dir) / filename
        path.write_bytes(b"GGUF" + b"\0" * 2044)
        return path

    service = LocalModelService(tmp_path / "local-models", llama_server=lambda: None, hardware=lambda _b: HardwareSummary(), clock=lambda: T0, downloader=fake_download)
    status = service.start_download(DownloadRequest(repo_id="example-org/Example-GGUF", filename="example-q4_k_m.gguf", confirmed_size_bytes=2048, alias="example-q4"))
    assert status.state in {"queued", "downloading", "completed"}
    # The worker thread finishes quickly with the fake downloader.
    import time
    for _ in range(100):
        current = service.overview().downloads[0]
        if current.state in {"completed", "failed"}:
            break
        time.sleep(0.05)
    assert current.state == "completed" and current.bytes_done == 2048
    assert calls == [{"repo_id": "example-org/Example-GGUF", "filename": "example-q4_k_m.gguf"}]
    record = service.registry.get("example-q4")
    assert record is not None and record.source_repo == "example-org/Example-GGUF" and record.size_bytes == 2048
    assert Path(record.path).is_relative_to(service.registry.weights_dir)

    # A size that does not match what the person confirmed is refused, not registered.
    mismatch = service.start_download(DownloadRequest(repo_id="example-org/Example-GGUF", filename="other-q4_k_m.gguf", confirmed_size_bytes=50 * 1024 * 1024, alias="other-q4"))
    for _ in range(100):
        current = next(d for d in service.overview().downloads if d.download_id == mismatch.download_id)
        if current.state in {"completed", "failed"}:
            break
        time.sleep(0.05)
    assert current.state == "failed" and current.error_code == "size_mismatch"
    assert service.registry.get("other-q4") is None


def test_scan_folder_registers_every_gguf_once(tmp_path: Path) -> None:
    from prompt_enhancer.application.local_models import ScanFolderRequest

    service = _service(tmp_path)
    folder = tmp_path / "models"
    (folder / "sub").mkdir(parents=True)
    a = _weights(folder, "Cool-Model.Q4_K_M.gguf")
    b = _weights(folder / "sub", "other-IQ3_M.gguf")
    (folder / "notes.txt").write_text("x", encoding="utf-8")
    first = service.scan_folder(ScanFolderRequest(path=str(folder)))
    assert [r.alias for r in first.registered] == ["cool-model.q4_k_m", "other-iq3_m"]
    assert first.skipped_existing == 0 and {r.path for r in first.registered} == {str(a), str(b)}
    again = service.scan_folder(ScanFolderRequest(path=str(folder)))
    assert again.registered == () and again.skipped_existing == 2
    try:
        service.scan_folder(ScanFolderRequest(path=str(tmp_path / "missing")))
    except LocalModelError as error:
        assert error.code == "folder_not_found"
    else:
        raise AssertionError("missing folder accepted")


def test_download_reports_partial_bytes_while_the_hub_writes(tmp_path: Path, monkeypatch) -> None:
    import prompt_enhancer.application.local_models as module

    monkeypatch.setattr(module, "DOWNLOAD_PROGRESS_INTERVAL_SECONDS", 0.05)
    seen: list[int] = []

    def slow_downloader(*, repo_id: str, filename: str, local_dir: Path) -> Path:
        partial_dir = local_dir / ".cache" / "huggingface" / "download"
        partial_dir.mkdir(parents=True, exist_ok=True)
        partial = partial_dir / f"{filename}.abc123.incomplete"
        partial.write_bytes(b"GGUF" + b"\0" * 2044)
        import time as _time
        deadline = _time.monotonic() + 5
        while _time.monotonic() < deadline:
            status = next(iter(service.overview().downloads))
            if status.bytes_done:
                seen.append(status.bytes_done)
                break
            _time.sleep(0.02)
        partial.unlink()
        final = local_dir / filename
        final.write_bytes(b"GGUF" + b"\0" * 4092)
        return final

    service = LocalModelService(
        tmp_path / "local-models", llama_server=lambda: None, hardware=lambda _b: HardwareSummary(),
        clock=lambda: T0, downloader=slow_downloader,
    )
    status = service.start_download(DownloadRequest(repo_id="example/repo", filename="example-q4.gguf", confirmed_size_bytes=4096, alias="example-q4"))
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and service.overview().downloads[0].state in {"queued", "downloading"}:
        time.sleep(0.05)
    final = service.overview().downloads[0]
    assert final.state == "completed", final
    assert seen and seen[0] == 2048  # the partial file was reported before completion
    assert final.bytes_done == 4096


def test_http_routes_and_capability(tmp_path: Path, monkeypatch) -> None:
    script = _stub_binary(tmp_path)
    monkeypatch.setenv("PROMPT_ENHANCER_LLAMA_SERVER", str(script))
    settings = AppSettings(home=tmp_path / "app")
    application = bootstrap_local_application(settings)
    service = application.create_local_model_service()
    # Swap in the stub launcher so the route tests never need a real binary.
    service._popen = _stub_popen(script)  # noqa: SLF001 - test seam
    service._hardware = lambda binary: HardwareSummary(llama_server_path=str(binary) if binary else None)  # noqa: SLF001
    # The HTTP app composes its own service; hand it the stubbed one so activation goes through the stub launcher.
    monkeypatch.setattr(type(application), "create_local_model_service", lambda self: service)
    app = application.create_http_app()
    client = TestClient(app, base_url="http://127.0.0.1")
    headers = {API_TOKEN_HEADER: settings.api_token_path.read_text(encoding="utf-8").strip()}
    assert client.get("/v1/local-models").status_code == 401
    capabilities = client.get("/v1/capabilities", headers=headers).json()
    assert capabilities["local_models"] is True
    overview = client.get("/v1/local-models", headers=headers)
    assert overview.status_code == 200, overview.text
    assert overview.json()["contract_version"] == "local-models.v1" and overview.json()["models"] == []
    weights = _weights(tmp_path)
    added = client.post("/v1/local-models", headers=headers, json={"alias": "stub", "path": str(weights), "layer_count": 4})
    assert added.status_code == 201, added.text
    bad = client.post("/v1/local-models", headers=headers, json={"alias": "bad", "path": str(tmp_path / "missing.gguf")})
    assert bad.status_code == 422
    missing = client.post("/v1/local-models/nope/activate", headers=headers, json={"device": "cpu"})
    assert missing.status_code == 404
    inactive = client.post("/v1/local-models/stub/chat/completions", headers=headers, json={"messages": [{"role": "user", "content": "hi"}]})
    assert inactive.status_code == 409 and inactive.json()["detail"]["code"] == "model_not_active"
    reserved = client.post("/v1/local-models", headers=headers, json={"alias": "openai", "path": str(weights)})
    assert reserved.status_code == 422
    # OpenAI-style clients: bearer app token, a base URL per model or one shared base URL routed by "model".
    bearer = {"Authorization": f"Bearer {headers[API_TOKEN_HEADER]}"}
    assert client.get("/v1/local-models/openai/v1/models", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/v1/local-models/openai/v1/models", headers=bearer).json() == {"object": "list", "data": []}
    assert client.get("/v1/local-models/stub/v1/models", headers=bearer).json()["data"] == []
    started = client.post("/v1/local-models/stub/activate", headers=headers, json={"device": "cpu"})
    assert started.status_code == 200, started.text
    assert [m["id"] for m in client.get("/v1/local-models/openai/v1/models", headers=bearer).json()["data"]] == ["stub"]
    assert client.get("/v1/local-models/stub/v1/models", headers=bearer).json()["data"][0]["id"] == "stub"
    via_base = client.post("/v1/local-models/stub/v1/chat/completions", headers=bearer, json={"messages": [{"role": "user", "content": "hi"}]})
    assert via_base.status_code == 200 and via_base.json()["choices"][0]["message"]["content"].startswith("echo:hi")
    routed = client.post("/v1/local-models/openai/v1/chat/completions", headers=bearer, json={"model": "stub", "messages": [{"role": "user", "content": "yo"}]})
    assert routed.status_code == 200 and routed.json()["choices"][0]["message"]["content"].startswith("echo:yo")
    unrouted = client.post("/v1/local-models/openai/v1/chat/completions", headers=bearer, json={"model": "other", "messages": [{"role": "user", "content": "yo"}]})
    assert unrouted.status_code == 409 and unrouted.json()["detail"]["code"] == "model_not_active"
    with client.stream("POST", "/v1/local-models/stub/chat/completions", headers=bearer, json={"stream": True, "messages": [{"role": "user", "content": "a b"}]}) as streamed:
        assert streamed.status_code == 200 and streamed.headers["content-type"].startswith("text/event-stream")
        assert streamed.headers["cache-control"] == "no-store"
        body = b"".join(streamed.iter_bytes())
    assert body.endswith(b"data: [DONE]\n\n") and b'"content": "echo:a"' in body
    client.post("/v1/local-models/stub/deactivate", headers=headers)
    status = client.get("/v1/local-models/stub", headers=headers).json()
    assert status["runtime"]["state"] == "stopped" and status["endpoint_path"] == "/v1/local-models/stub/chat/completions"
    removed = client.delete("/v1/local-models/stub", headers=headers)
    assert removed.status_code == 204 and client.get("/v1/local-models/stub", headers=headers).status_code == 404
    assert weights.is_file()  # weights outside the managed directory are never deleted


def test_storage_root_is_configurable_without_moving_the_app_home(tmp_path: Path, monkeypatch) -> None:
    from prompt_enhancer.privacy import write_private_text

    monkeypatch.delenv("PROMPT_ENHANCER_LOCAL_MODELS_DIR", raising=False)
    settings = AppSettings(home=tmp_path / "app")
    assert settings.local_models_dir == tmp_path / "app" / "local-models"
    elsewhere = tmp_path / "big-drive" / "models"
    settings.home.mkdir(parents=True, exist_ok=True)
    write_private_text(settings.local_models_override_path, str(elsewhere) + "\n")
    assert AppSettings(home=tmp_path / "app").local_models_dir == elsewhere
    monkeypatch.setenv("PROMPT_ENHANCER_LOCAL_MODELS_DIR", str(tmp_path / "env-drive"))
    assert AppSettings(home=tmp_path / "app").local_models_dir == tmp_path / "env-drive"
    # The runtime is found under the storage root's runtimes folder.
    runtime = elsewhere / "runtimes" / "llama.cpp" / "llama-server.exe"
    runtime.parent.mkdir(parents=True)
    runtime.write_text("", encoding="utf-8")
    assert detect_llama_server({}, app_home=tmp_path / "app", models_root=elsewhere) == runtime


def test_gguf_block_count_reader_is_minimal_and_bounded(tmp_path: Path) -> None:
    import struct

    from prompt_enhancer.application.local_models import read_gguf_layer_count

    def gguf_string(text: str) -> bytes:
        raw = text.encode("utf-8")
        return struct.pack("<Q", len(raw)) + raw

    pairs = [
        ("general.architecture", 8, gguf_string("qwen3")),
        ("qwen3.block_count", 4, struct.pack("<I", 64)),
        ("tokenizer.ggml.tokens", 9, struct.pack("<IQ", 8, 2) + gguf_string("a") + gguf_string("b")),
    ]
    body = b"GGUF" + struct.pack("<I", 3) + struct.pack("<QQ", 0, len(pairs))
    for key, value_type, value in pairs:
        body += gguf_string(key) + struct.pack("<I", value_type) + value
    good = tmp_path / "good.gguf"
    good.write_bytes(body + b"\0" * 32)
    assert read_gguf_layer_count(good) == 64
    (tmp_path / "not.gguf").write_bytes(b"NOPE" + b"\0" * 64)
    assert read_gguf_layer_count(tmp_path / "not.gguf") is None
    truncated = tmp_path / "short.gguf"
    truncated.write_bytes(body[:40])
    assert read_gguf_layer_count(truncated) is None
