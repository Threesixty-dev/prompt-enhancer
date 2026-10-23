"""Execute the actual CLI on loopback with synthetic input and no app home."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx
import pytest

from prompt_enhancer.enhancement.contracts import ExecutionResult

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("binding", ["deterministic.v1", "deterministic.v2"])
def test_headless_cli_subprocess_uses_real_http_and_has_no_application_store(tmp_path, binding):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    environment = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(ROOT / "src"),
        "ENHANCEMENT_API_TOKEN": "example-benchmark-api-access-value-only",
        "PYTHONDONTWRITEBYTECODE": "1", "HOME": str(tmp_path), "USERPROFILE": str(tmp_path)}
    if "SYSTEMROOT" in os.environ:
        environment["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    process = subprocess.Popen([sys.executable, "-m", "prompt_enhancer.enhancement.cli",
        "--synthetic-benchmark", "--port", str(port)], env=environment, cwd=tmp_path,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=2,
                headers={"Authorization": "Bearer " + environment["ENHANCEMENT_API_TOKEN"]}, trust_env=False) as client:
            for _ in range(100):
                assert process.poll() is None
                try:
                    if client.get("/health/ready").status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                time.sleep(0.05)
            else:
                raise AssertionError("core_not_ready")
            payload = json.loads((ROOT / "contracts/enhancement/examples/script-request.json").read_text())
            payload["evaluation"]["evaluators"][0]["binding_id"] = binding
            accepted = client.post("/v1/executions", json=payload)
            assert accepted.status_code == 202
            key = accepted.json()["execution_id"]
            for _ in range(100):
                response = client.get(f"/v1/executions/{key}/result")
                if response.status_code == 200:
                    break
                time.sleep(0.02)
            result = ExecutionResult.model_validate(response.json())
            assert result.status == "succeeded" and result.before and result.after
            assert result.before[0].provenance.adapter_version == binding.replace("deterministic", "prompt-evaluation")
            assert client.delete(f"/v1/executions/{key}").status_code == 204
        assert not list(tmp_path.rglob("*.sqlite*"))
        assert not list(tmp_path.rglob("*.jsonl"))
    finally:
        process.terminate()
        process.wait(timeout=10)
