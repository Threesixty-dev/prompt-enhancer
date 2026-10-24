"""Isolated consumer/API/gateway transport; no actual model or account access."""

import json
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

from docker_smoke import docker

PROVIDER = """import json, ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        assert self.path == '/v1/responses'
        assert self.headers.get('Authorization') == 'Bearer example-gateway-token-not-a-secret'
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        assert body == {'model': 'example-qualified-model', 'input': 'Fictional widget'}
        payload = b'data: {"example":"accepted"}\\n\\ndata: [DONE]\\n\\n'
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    def log_message(self, *args):
        pass
server = ThreadingHTTPServer(('127.0.0.1', 9443), Handler)
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain('/tmp/provider.crt', '/tmp/provider.key')
server.socket = context.wrap_socket(server.socket, server_side=True)
server.serve_forever()
"""


def probe(name, code):
    result = subprocess.run(["docker", "exec", name, "python3", "-c", code],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    return result.returncode == 0


def wait_probe(name, code):
    for _ in range(40):
        if probe(name, code):
            return
        state = docker(["inspect", "--format", "{{.State.Running}}", name], capture=True)
        if state.strip() != b"true":
            raise RuntimeError("test_container_stopped")
        time.sleep(0.25)
    raise RuntimeError("test_readiness_timeout")


def main():
    identifier = uuid.uuid4().hex[:12]
    namespace, relay, consumer = ["bench-relay-smoke-" + role + "-" + identifier for role in ("namespace", "relay", "consumer")]
    api_volume, gateway_volume = ["bench-relay-smoke-" + role + "-" + identifier for role in ("api", "gateway")]
    containers, volumes, provider = [], [], None
    hardening = ["--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--init",
                 "--label", "enhancement-bench.test=relay", "--pids-limit=512", "--memory=2g", "--cpus=2"]
    try:
        with tempfile.TemporaryDirectory(prefix="bench-relay-fixture-") as directory:
            cert, key = Path(directory).resolve() / "provider.crt", Path(directory).resolve() / "provider.key"
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key),
                "-out", str(cert), "-days", "1", "-subj", "/CN=localhost", "-addext", "subjectAltName=IP:127.0.0.1,DNS:localhost"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=True)
            for volume in (api_volume, gateway_volume):
                docker(["volume", "create", "--label", "enhancement-bench.test=relay", volume])
                volumes.append(volume)
            docker(["run", "-d", "--name", namespace, "--network", "none", *hardening,
                "--tmpfs", "/tmp:rw,nosuid,size=32m,mode=1777", "--entrypoint", "sleep", "local/enhancement-bench:validation", "300"])
            containers.append(namespace)
            for payload, path in ((cert.read_bytes(), "/tmp/provider.crt"), (key.read_bytes(), "/tmp/provider.key"),
                                  (PROVIDER.encode(), "/tmp/provider.py")):
                docker(["exec", "-i", namespace, "python", "-c", "import pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read())", path], input=payload)
            provider = subprocess.Popen(["docker", "exec", namespace, "python", "/tmp/provider.py"],
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            docker(["run", "-d", "--name", relay, "--network", "container:" + namespace, *hardening,
                "--group-add", "10003", "--tmpfs", "/tmp:rw,nosuid,size=32m",
                "--mount", f"type=volume,src={api_volume},dst=/run/bench-consumer-api,readonly",
                "--mount", f"type=volume,src={gateway_volume},dst=/run/bench-gateway",
                "--mount", f"type=bind,src={cert},dst=/etc/ssl/certs/ca-certificates.crt,readonly",
                "--env", "BENCH_LITELLM_URL=https://127.0.0.1:9443/v1",
                "--entrypoint", "python", "local/enhancement-bench:validation", "-m", "enhancement_bench.relay"])
            containers.append(relay)
            docker(["run", "-d", "--name", consumer, "--network", "none", *hardening, "--group-add", "10003",
                "--tmpfs", "/tmp:rw,nosuid,size=256m,mode=1777", "--tmpfs", "/runtime/consumer:rw,nosuid,size=128m,mode=1777",
                "--mount", f"type=volume,src={api_volume},dst=/run/bench-consumer-api",
                "--mount", f"type=volume,src={gateway_volume},dst=/run/bench-gateway,readonly",
                "--env", "BENCH_GATEWAY_BRIDGE=1", "--env", "BENCH_LITELLM_URL=http://127.0.0.1:4000/v1",
                "--env", "BENCH_CONSUMER_API_TOKEN=example-consumer-token-not-a-secret",
                "--env", "BENCH_LITELLM_TOKEN=example-gateway-token-not-a-secret", "--env", "BENCH_CONSUMER_MODEL=example-qualified-model",
                "--env", "EXAMPLE_STACK_CANARY=example-unrelated-stack-value", "local/enhancement-consumer:validation"])
            containers.append(consumer)
            wait_probe(consumer, "import subprocess; subprocess.run(['python3','/opt/bench-consumer/start.py','health'],check=True)")
            wait_probe(relay, "from enhancement_bench.relay import health; health()")
            assert probe(namespace, "from enhancement_bench.client import static_consumer_ready; assert static_consumer_ready('example-consumer-token-not-a-secret')")
            for name, readonly in ((consumer, "/run/bench-gateway"), (relay, "/run/bench-consumer-api")):
                mounts = json.loads(docker(["inspect", "--format", "{{json .Mounts}}", name], capture=True))
                assert not next(m for m in mounts if m["Destination"] == readonly)["RW"]
            assert probe(consumer, """from pathlib import Path
import stat
for directory, name in (('/run/bench-consumer-api','agent.sock'),('/run/bench-gateway','gateway.sock')):
    root=Path(directory)
    assert root.stat().st_gid==10003 and root.stat().st_mode & 0o007 == 0
    assert (root/name).stat().st_gid==10003 and stat.S_ISSOCK((root/name).stat().st_mode)
""")
            assert probe(namespace, "import urllib.request; r=urllib.request.Request('http://127.0.0.1:8000/health',headers={'X-Session-API-Key':'example-consumer-token-not-a-secret'}); assert urllib.request.urlopen(r,timeout=2).status==200")
            assert probe(consumer, """import json,urllib.request
request=urllib.request.Request('http://127.0.0.1:4000/v1/responses', data=json.dumps({'model':'example-qualified-model','input':'Fictional widget'}).encode(), headers={'Content-Type':'application/json','Authorization':'Bearer example-gateway-token-not-a-secret'})
assert urllib.request.urlopen(request,timeout=10).read().endswith(b'[DONE]\\n\\n')
""")
            state = json.loads(docker(["inspect", "--format", "{{json .HostConfig.NetworkMode}}", consumer], capture=True))
            assert state == "none"
            assert probe(consumer, """import errno,socket,urllib.request,urllib.error
try:
    socket.create_connection(('192.0.2.1',443),timeout=0.2)
except OSError as error:
    assert error.errno==errno.ENETUNREACH
else: raise AssertionError('unexpected_network_route')
request=urllib.request.Request('http://127.0.0.1:4000/v1/responses',data=b'{}',headers={'Content-Type':'application/json'})
try:
    urllib.request.urlopen(request,timeout=2)
except urllib.error.HTTPError as error:
    assert error.code==401
else: raise AssertionError('unauthenticated_gateway_request')
""")
            assert probe(namespace, """import urllib.request,urllib.error
try:
    urllib.request.urlopen('http://127.0.0.1:8000/api/conversations',timeout=2)
except urllib.error.HTTPError as error:
    assert error.code==401
else: raise AssertionError('unauthenticated_agent_request')
""")
            assert probe(consumer, """from pathlib import Path
matched=0
for entry in Path('/proc').iterdir():
    if not entry.name.isdigit(): continue
    try:
        command=(entry/'cmdline').read_bytes().split(b'\\0')
        if command[1:4] == [b'-m', b'uvicorn', b'consumer_retention:create_app']:
            environment=(entry/'environ').read_bytes()
            assert b'EXAMPLE_STACK_CANARY=' not in environment
            assert b'PATH=/opt/bench-consumer/bin:' in environment
            matched+=1
    except (FileNotFoundError,PermissionError): pass
assert matched==1
""")
            # A killed bridge must take its whole consumer down; restart belongs to Docker.
            assert probe(consumer, """import os,signal
from pathlib import Path
for entry in Path('/proc').iterdir():
    if not entry.name.isdigit(): continue
    try:
        command=(entry/'cmdline').read_bytes().split(b'\\0')
        if command and command[0]==b'socat' and any(b'UNIX-LISTEN:' in arg for arg in command):
            os.kill(int(entry.name),signal.SIGTERM)
            break
    except (FileNotFoundError,PermissionError): pass
else: raise AssertionError('bridge_missing')
""")
            for _ in range(40):
                if docker(["inspect", "--format", "{{.State.Running}}", consumer], capture=True).strip() == b"false":
                    break
                time.sleep(0.25)
            else:
                raise RuntimeError("bridge_exit_not_supervised")
            assert docker(["inspect", "--format", "{{.State.ExitCode}}", consumer], capture=True).strip() != b"0"
            docker(["restart", consumer])
            wait_probe(consumer, "import subprocess; subprocess.run(['python3','/opt/bench-consumer/start.py','health'],check=True)")
            docker(["restart", relay])
            wait_probe(relay, "from enhancement_bench.relay import health; health()")
            wait_probe(consumer, "import subprocess; subprocess.run(['python3','/opt/bench-consumer/start.py','health'],check=True)")
            assert probe(namespace, "import urllib.request; r=urllib.request.Request('http://127.0.0.1:8000/health',headers={'X-Session-API-Key':'example-consumer-token-not-a-secret'}); assert urllib.request.urlopen(r,timeout=2).status==200")
            assert probe(consumer, """import json,urllib.request
request=urllib.request.Request('http://127.0.0.1:4000/v1/responses', data=json.dumps({'model':'example-qualified-model','input':'Fictional widget'}).encode(), headers={'Content-Type':'application/json','Authorization':'Bearer example-gateway-token-not-a-secret'})
assert urllib.request.urlopen(request,timeout=10).read().endswith(b'[DONE]\\n\\n')
""")
            print(json.dumps({"scope": "static_consumer_unix_gateway_bridge", "consumer_network_none": True,
                "authenticated_agent_api": True, "verified_https_gateway_stream": True,
                "unrelated_agent_environment_removed": True, "bridge_exit_supervised": True,
                "socket_ownership_readonly_mounts": True, "restart_verified": True,
                "unauthenticated_requests_rejected": True, "external_route_absent": True,
                "model_call_performed": False, "live_provider_qualified": False}))
    finally:
        for name in reversed(containers):
            docker(["rm", "--force", name])
        if provider is not None:
            provider.wait(timeout=10)
        for volume in volumes:
            docker(["volume", "rm", volume])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("relay_smoke_failed") from None
