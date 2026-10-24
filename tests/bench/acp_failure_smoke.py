"""Pinned SDK + synthetic ACP server, isolated from networks and provider accounts."""

import argparse
import json
from pathlib import Path
import subprocess
import uuid


RUNTIME = r'''
import importlib.metadata, json, os, pathlib, subprocess, sys, tempfile
payload=json.load(sys.stdin)
root=pathlib.Path(tempfile.mkdtemp(prefix='example-acp-'))
os.environ.update({'HOME':str(root/'home'),'CODEX_HOME':str(root/'codex'),
    'OH_CONVERSATIONS_PATH':str(root/'conversations'),'OH_DISABLE_TELEMETRY':'true',
    'OTEL_SDK_DISABLED':'true','LITELLM_LOCAL_MODEL_COST_MAP':'True'})
for key in ('HOME','CODEX_HOME','OH_CONVERSATIONS_PATH'):pathlib.Path(os.environ[key]).mkdir()
assert importlib.metadata.version('openhands-sdk')=='1.49.1'
from openhands.sdk import Conversation
from openhands.sdk.agent import ACPAgent
from openhands.sdk.workspace import LocalWorkspace
from openhands.sdk.event import ActionEvent
from openhands.sdk.event.conversation_error import ConversationErrorEvent
from openhands.sdk.tool.builtins.finish import FinishAction
guard=root/'guard.py'
if payload.get('guard') is None:
 assert subprocess.check_output(['/opt/bench-consumer/bin/codex-acp','--version'],text=True,timeout=10).strip()=='@agentclientprotocol/codex-acp 1.10.0'
guard.write_text(payload['guard'] if payload.get('guard') is not None
    else pathlib.Path('/opt/bench-consumer/bin/codex-acp').read_text())
vendor=root/'example_server.py'
vendor.write_text(r"""import sys,json
typed=False
def send(value):print(json.dumps(value),flush=True)
for line in sys.stdin:
 request=json.loads(line)
 method=request.get('method')
 if method=='initialize':
  typed='sessionFailure' in request.get('params',{}).get('clientCapabilities',{}).get('_meta',{}).get('jetbrains',{}).get('air',{}).get('capabilities',[])
  result={'protocolVersion':1,'agentCapabilities':{},'authMethods':[],
    '_meta':{'jetbrains':{'air':{'version':1,'capabilities':['sessionFailure']}}}}
 elif method=='session/new':
  result={'sessionId':'example-session','modes':{'currentModeId':'read-only',
    'availableModes':[{'id':'read-only','name':'Read only'}]}}
 elif method in ('session/set_mode','session/set_model'):result={}
 elif method=='session/prompt':
  result={'stopReason':'end_turn'}
  if sys.argv[1]=='failure' and typed:
   result['_meta']={'jetbrains':{'air':{'version':1,'sessionFailure':{'id':'example-turn:error',
     'revision':1,'category':'limit','severity':'error','title':'example-private-gateway-detail','actions':[]}}}}
  else:
   text='example-provider-failure' if sys.argv[1]=='failure' else '{"example":"accepted"}'
   send({'jsonrpc':'2.0','method':'session/update','params':{'sessionId':'example-session',
     'update':{'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':text}}}})
 else:
  if 'id' not in request:continue
  send({'jsonrpc':'2.0','id':request['id'],'error':{'code':-32601,'message':'Method not found'}})
  continue
 send({'jsonrpc':'2.0','id':request['id'],'result':result})
""")
results=[]
for guarded,scenario in ((False,'failure'),(True,'failure'),(True,'success')):
 command=[sys.executable,str(vendor),scenario]
 if guarded:
  launcher="import runpy,sys; m=runpy.run_path(sys.argv[1]); raise SystemExit(m['bridge'](sys.argv[2:],sys.stdin.buffer,sys.stdout.buffer))"
  command=[sys.executable,'-c',launcher,str(guard),*command]
 working=root/('guarded-' if guarded else 'legacy-')/scenario
 working.mkdir(parents=True)
 agent=ACPAgent(acp_command=command,acp_server='codex',acp_session_mode='read-only',
     acp_startup_timeout=10,acp_prompt_timeout=10)
 conversation=Conversation(agent=agent,workspace=LocalWorkspace(working_dir=str(working)),visualizer=None)
 try:
  conversation.send_message('Fictional widget')
  try:conversation.run()
  except Exception:pass
  status=getattr(conversation.state.execution_status,'value',conversation.state.execution_status)
  events=list(conversation.state.events)
  finished=[e for e in events if isinstance(e,ActionEvent) and isinstance(e.action,FinishAction)]
  failures=[e for e in events if isinstance(e,ConversationErrorEvent)]
  if guarded and scenario=='failure':
   assert status=='error' and not finished
   assert any(e.code=='ACPPromptError' and e.detail=='[-32603] bench_consumer_upstream_limit' for e in failures)
  else:
   assert status=='finished' and len(finished)==1 and not failures
   assert finished[0].action.message==('example-provider-failure' if scenario=='failure' else '{"example":"accepted"}')
  results.append({'guarded':guarded,'scenario':scenario,'status':status,'passed':True})
 finally:conversation.close()
print('ACP_SMOKE_RESULT '+json.dumps({'sdk':'1.49.1','results':results,'network':'none','providerAccountAccess':False}))
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--consumer-image", default="local/enhancement-consumer:validation")
    parser.add_argument("--guard-source", type=Path)
    args = parser.parse_args()
    name = "example-acp-smoke-" + uuid.uuid4().hex[:12]
    guard = args.guard_source.read_text() if args.guard_source else None
    try:
        result = subprocess.run(["docker", "run", "--rm", "-i", "--name", name,
            "--label", "enhancement-bench.test=acp-failure", "--network", "none", "--read-only",
            "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit", "128",
            "--memory", "1g", "--cpus", "1", "--tmpfs", "/tmp:rw,nosuid,size=128m,mode=1777",
            "--entrypoint", "python3", args.consumer_image, "-c", RUNTIME],
            input=json.dumps({"guard": guard}), capture_output=True, text=True, timeout=90)
        summary = next((line for line in result.stdout.splitlines() if line.startswith("ACP_SMOKE_RESULT ")), None)
        if result.returncode or summary is None:
            raise RuntimeError("acp_failure_smoke_failed")
        print(summary)
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=15)
        probe = subprocess.run(["docker", "inspect", name], capture_output=True, timeout=15)
        if probe.returncode == 0:
            raise RuntimeError("acp_failure_smoke_cleanup_unconfirmed")


if __name__ == "__main__":
    main()
