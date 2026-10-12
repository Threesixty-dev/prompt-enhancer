"""Start only a static Agent Server with a fresh, gateway-backed Codex home."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
from urllib.parse import urlsplit
import urllib.request


def main():
    if sys.argv[1:] == ["health"]:
        try:
            request = urllib.request.Request("http://127.0.0.1:8000/health", headers={
                "X-Session-API-Key": os.environ["BENCH_CONSUMER_API_TOKEN"]})
            with urllib.request.urlopen(request, timeout=2) as response:
                assert response.status == 200
            if os.environ.get("BENCH_GATEWAY_BRIDGE") == "1":
                with urllib.request.urlopen("http://127.0.0.1:4000/health/ready", timeout=2) as response:
                    assert response.status == 200
        except Exception:
            raise SystemExit(1) from None
        return
    endpoint = os.environ["BENCH_LITELLM_URL"].rstrip("/")
    parsed = urlsplit(endpoint)
    bridge_mode = os.environ.get("BENCH_GATEWAY_BRIDGE") == "1"
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
            or (bridge_mode and endpoint != "http://127.0.0.1:4000/v1")
            or (not bridge_mode and parsed.scheme != "https")):
        raise SystemExit("gateway_https_required")
    model = os.environ["BENCH_CONSUMER_MODEL"]
    if not model or len(model) > 160:
        raise SystemExit("consumer_model_required")
    directory = Path("/runtime/consumer/codex")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    # JSON string quoting is valid for these TOML basic strings.
    config = (f"model = {json.dumps(model)}\nmodel_provider = \"bench_gateway\"\n"
              'approval_policy = "never"\nsandbox_mode = "read-only"\nweb_search = "disabled"\n'
              '[model_providers.bench_gateway]\nname = "Bench gateway"\n'
              f"base_url = {json.dumps(endpoint)}\n"
              'env_key = "LITELLM_API_KEY"\nwire_api = "responses"\n')
    path = directory / "config.toml"
    path.write_text(config)
    path.chmod(0o600)
    # Coolify can inject unrelated stack secrets; the agent receives only its two credentials.
    environment = {"PATH": os.environ["PATH"], "HOME": "/runtime/consumer",
                   "CODEX_HOME": str(directory), "SESSION_API_KEY": os.environ["BENCH_CONSUMER_API_TOKEN"],
                   "LITELLM_API_KEY": os.environ["BENCH_LITELLM_TOKEN"],
                   "OH_DISABLE_TELEMETRY": "true", "OPENHANDS_SUPPRESS_BANNER": "1",
                   "OH_CONVERSATION_IDLE_TTL_SECONDS": "60", "LITELLM_LOCAL_MODEL_COST_MAP": "True"}
    command = ["python3", "-m", "openhands.agent_server", "--host", "127.0.0.1", "--port", "8000"]
    if not bridge_mode:
        os.execvpe("python3", command, environment)
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    commands = [command,
        ["socat", "UNIX-LISTEN:/run/bench-consumer-api/agent.sock,unlink-early,mode=0660,fork,max-children=16", "TCP:127.0.0.1:8000"],
        ["socat", "TCP-LISTEN:4000,bind=127.0.0.1,reuseaddr,fork,max-children=16", "UNIX-CONNECT:/run/bench-gateway/gateway.sock"]]
    children = []
    unexpected_exit = False
    try:
        for child in commands:
            children.append(subprocess.Popen(child, env=environment, stdin=subprocess.DEVNULL,
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        while not stop.wait(0.2):
            if any(child.poll() is not None for child in children):
                unexpected_exit = True
                break
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        Path("/run/bench-consumer-api/agent.sock").unlink(missing_ok=True)
    if unexpected_exit:
        raise SystemExit("consumer_transport_stopped")


if __name__ == "__main__":
    main()
