"""Pinned SDK websocket shutdown against an isolated real consumer HTTP server."""

import argparse
import json
from pathlib import Path
import subprocess
import uuid


RUNTIME = r'''
import importlib.metadata, json, os, pathlib, shutil, subprocess, sys, time, uuid
import httpx

payload = json.load(sys.stdin)
root = pathlib.Path('/tmp/example-lifecycle')
root.mkdir(mode=0o700)
os.environ.update({'HOME': str(root / 'home'), 'CODEX_HOME': str(root / 'codex'),
    'OH_CONVERSATIONS_PATH': str(root / 'conversations'), 'OH_DISABLE_TELEMETRY': 'true',
    'OTEL_SDK_DISABLED': 'true', 'LITELLM_LOCAL_MODEL_COST_MAP': 'True',
    'SESSION_API_KEY': 'example-retention-key', 'OH_ENABLE_VSCODE': 'false',
    'OPENHANDS_SUPPRESS_BANNER': '1'})
for key in ('HOME', 'CODEX_HOME', 'OH_CONVERSATIONS_PATH'):
    pathlib.Path(os.environ[key]).mkdir()
assert importlib.metadata.version('openhands-sdk') == '1.49.1'
app_dir = '/opt/bench-consumer'
if payload.get('retention') is not None:
    (root / 'consumer_retention.py').write_text(payload['retention'])
    app_dir = str(root)
vendor = root / 'example_server.py'
vendor.write_text(r"""import sys,json
for line in sys.stdin:
    request = json.loads(line)
    method = request.get('method')
    if method == 'initialize':
        result = {'protocolVersion': 1, 'agentCapabilities': {}, 'authMethods': [],
            '_meta': {'jetbrains': {'air': {'version': 1, 'capabilities': ['sessionFailure']}}}}
    elif method == 'session/new':
        result = {'sessionId': 'example-session', 'modes': {'currentModeId': 'read-only',
            'availableModes': [{'id': 'read-only', 'name': 'Read only'}]}}
    elif method in ('session/set_mode', 'session/set_model'):
        result = {}
    elif method == 'session/prompt':
        print(json.dumps({'jsonrpc': '2.0', 'method': 'session/update',
            'params': {'sessionId': 'example-session', 'update': {
                'sessionUpdate': 'agent_message_chunk',
                'content': {'type': 'text', 'text': 'Fictional widget accepted'}}}}), flush=True)
        result = {'stopReason': 'end_turn'}
    else:
        if 'id' not in request:
            continue
        print(json.dumps({'jsonrpc': '2.0', 'id': request['id'],
            'error': {'code': -32601, 'message': 'Method not found'}}), flush=True)
        continue
    print(json.dumps({'jsonrpc': '2.0', 'id': request['id'], 'result': result}), flush=True)
""")
server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'consumer_retention:create_app',
    '--factory', '--app-dir', app_dir, '--host', '127.0.0.1', '--port', '8000', '--no-access-log'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
results = []
try:
    with httpx.Client(base_url='http://127.0.0.1:8000', timeout=30, trust_env=False,
            headers={'X-Session-API-Key': 'example-retention-key'}) as client:
        for _ in range(60):
            try:
                if client.get('/health').status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(.25)
        else:
            raise RuntimeError('synthetic_consumer_start_failed')
        from openhands.sdk import Conversation
        from openhands.sdk.agent import ACPAgent
        from openhands.sdk.workspace import RemoteWorkspace
        for guarded in (False, True):
            identifier = uuid.uuid4()
            directory = pathlib.Path('/tmp/enhancement-' + str(identifier))
            directory.mkdir(mode=0o700)
            command = [sys.executable, str(vendor)]
            if guarded:
                command = [sys.executable, '-c',
                    "import runpy,sys; m=runpy.run_path(sys.argv[1]); "
                    "raise SystemExit(m['bridge'](sys.argv[2:],sys.stdin.buffer,sys.stdout.buffer))",
                    '/opt/bench-consumer/bin/codex-acp', *command]
            workspace = RemoteWorkspace(host='http://127.0.0.1:8000',
                api_key='example-retention-key', working_dir=str(directory))
            conversation = Conversation(agent=ACPAgent(acp_command=command, acp_server='codex',
                acp_session_mode='read-only', acp_startup_timeout=10, acp_prompt_timeout=10),
                workspace=workspace, conversation_id=identifier, delete_on_close=False, visualizer=None)
            native = '/api/conversations/' + str(identifier)
            retained = '/api/bench/conversations/' + str(identifier)
            try:
                conversation.send_message('Fictional widget request')
                conversation.run()
                assert client.get(native).json()['execution_status'] == 'finished'
                # A subscriber that has not asked to stop must still block release.
                active = client.post(retained + '/release')
                assert active.status_code == 409
                assert active.json()['detail'] == 'conversation_still_active'
                thread = conversation._ws_client._thread
                conversation.close()
                released = client.post(retained + '/release')
                assert released.status_code == 200, 'stopped_subscriber_not_released'
                assert released.json()['runtime_released'] is True
                thread.join(timeout=2)
                assert not thread.is_alive(), 'sdk_subscriber_thread_still_running'
                assert client.get(native).json()['execution_status'] == 'finished'
                assert client.get(native + '/events/search').json()['items']
                assert all(entry.name == '.git' for entry in directory.iterdir())
                if (directory / '.git').is_dir():
                    shutil.rmtree(directory / '.git')
                directory.rmdir()
                assert client.post(retained + '/retain').json()['cleanup_confirmed'] is True
                results.append({'guarded': guarded, 'live_subscriber_preserved': True,
                    'stopped_subscriber_released': True, 'native_history_retained': True,
                    'workspace_cleanup_confirmed': True})
            finally:
                conversation.close()
                workspace.reset_client()
    print('RETENTION_LIFECYCLE_RESULT ' + json.dumps({'sdk': '1.49.1', 'results': results,
        'source_override': payload.get('retention') is not None, 'network': 'none',
        'model_calls': 0, 'provider_account_access': False}))
finally:
    server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait(timeout=5)
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--consumer-image", default="local/enhancement-consumer:validation")
    parser.add_argument("--retention-source", type=Path)
    args = parser.parse_args()
    name = "example-retention-lifecycle-" + uuid.uuid4().hex[:12]
    source = args.retention_source.read_text() if args.retention_source else None
    try:
        result = subprocess.run(["docker", "run", "--rm", "-i", "--name", name,
            "--label", "enhancement-bench.test=retention-lifecycle", "--network", "none", "--read-only",
            "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit", "256",
            "--memory", "2g", "--cpus", "2", "--init",
            "--tmpfs", "/tmp:rw,nosuid,size=256m,mode=1777",
            "--tmpfs", "/runtime/consumer:rw,nosuid,size=128m,mode=1777",
            "--entrypoint", "python3", args.consumer_image, "-c", RUNTIME],
            input=json.dumps({"retention": source}), capture_output=True, text=True, timeout=90)
        summary = next((line for line in result.stdout.splitlines()
                        if line.startswith("RETENTION_LIFECYCLE_RESULT ")), None)
        if result.returncode or summary is None:
            raise RuntimeError("retention_lifecycle_smoke_failed")
        print(summary)
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=15)
        probe = subprocess.run(["docker", "inspect", name], capture_output=True, timeout=15)
        if probe.returncode == 0:
            raise RuntimeError("retention_lifecycle_smoke_cleanup_unconfirmed")


if __name__ == "__main__":
    main()
