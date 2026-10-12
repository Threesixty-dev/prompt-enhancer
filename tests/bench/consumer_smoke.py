"""Static consumer startup/authentication only; no model or provider-account access."""

import json
import subprocess
import time
import uuid


def run(args, capture=False):
    return subprocess.run(["docker", *args], stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, timeout=45, check=False)


def main():
    name = "enhancement-consumer-smoke-" + uuid.uuid4().hex[:12]
    try:
        result = run(["run", "-d", "--name", name, "--label", "enhancement-bench.test=static-consumer",
                      "--network", "none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                      "--tmpfs", "/tmp:rw,nosuid,size=256m,mode=1777", "--tmpfs", "/runtime/consumer:rw,nosuid,size=128m,mode=1777",
                      "--pids-limit", "512", "--memory", "2g", "--cpus", "2", "--init",
                      "--env", "BENCH_CONSUMER_API_TOKEN=example-consumer-token-not-a-secret",
                      "--env", "BENCH_LITELLM_TOKEN=example-gateway-token-not-a-secret",
                      "--env", "BENCH_LITELLM_URL=https://gateway.example.com/v1",
                      "--env", "BENCH_CONSUMER_MODEL=example-qualified-model",
                      "local/enhancement-consumer:validation"])
        if result.returncode:
            raise RuntimeError
        ready = False
        for _ in range(30):
            probe = run(["exec", name, "python3", "-c",
                "import urllib.request; r=urllib.request.Request('http://127.0.0.1:8000/health',headers={'X-Session-API-Key':'example-consumer-token-not-a-secret'}); assert urllib.request.urlopen(r,timeout=2).status==200"])
            if probe.returncode == 0:
                ready = True
                break
            state = run(["inspect", "--format", "{{.State.Running}}", name], capture=True)
            if state.stdout.strip() != b"true":
                raise RuntimeError
            time.sleep(1)
        if not ready:
            raise RuntimeError
        checks = run(["exec", name, "python3", "-c",
            "import importlib.metadata as m,json,subprocess; v={k:m.version(k) for k in ('openhands-agent-server','openhands-sdk','openhands-tools')}; assert all(x=='1.49.1' for x in v.values()); v['codex']=subprocess.check_output(['codex','--version'],text=True).strip(); v['acp']=subprocess.check_output(['codex-acp','--version'],text=True).strip(); print(json.dumps(v))"], capture=True)
        if checks.returncode:
            raise RuntimeError
        versions = json.loads(checks.stdout)
        assert "0.156.0" in versions["codex"]
        assert "1.10.0" in versions["acp"]
        print(json.dumps({"scope": "static_consumer_startup", "ready": True, "versions": versions,
                          "model_call_performed": False, "provider_account_access": False}))
    finally:
        result = run(["rm", "--force", name])
        if result.returncode:
            raise SystemExit("static_consumer_cleanup_unconfirmed")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("static_consumer_startup_failed") from None
