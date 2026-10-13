"""Run inside the isolated consumer image; synthetic history, no model calls."""
import json
import os
from pathlib import Path
import shutil
import sys
from uuid import uuid4

os.environ.update(HOME="/runtime/consumer", SESSION_API_KEY="example-retention-key",
    OH_CONVERSATIONS_PATH="/runtime/consumer/workspace/conversations",
    OH_ENABLE_VSCODE="false", OH_DISABLE_TELEMETRY="true",
    LITELLM_LOCAL_MODEL_COST_MAP="True", OPENHANDS_SUPPRESS_BANNER="1")
sys.path.insert(0, "/opt/bench-consumer")

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from openhands.sdk.agent import ACPAgent
from openhands.sdk.conversation.request import StartConversationRequest
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk import Message, TextContent
from openhands.sdk.workspace import LocalWorkspace
from consumer_retention import Retention, create_app


def main():
    identifier = uuid4()
    directory = Path(f"/tmp/enhancement-{identifier}")
    directory.mkdir(mode=0o700)
    app = create_app()
    headers = {"X-Session-API-Key": "example-retention-key"}
    native = f"/api/conversations/{identifier}"
    retained = f"/api/bench/conversations/{identifier}"
    retention = Retention(Path("/runtime/consumer/retention"), 7)
    with TestClient(app) as client:
        assert client.get("/api/bench/retention").status_code == 401
        assert client.get("/api/bench/retention", headers=headers).json()["retention_days"] == 7

        async def prepare():
            service = app.state.conversation_service
            await service.start_conversation(StartConversationRequest(
                conversation_id=identifier, workspace=LocalWorkspace(working_dir=str(directory)),
                agent=ACPAgent(acp_command=["false"], acp_model="example-model", acp_server="codex")))
            event_service = await service.get_event_service(identifier)
            await event_service.send_message(Message(role="user", content=[TextContent(text="Fictional widget request")]), False)
            state = await event_service.get_state()
            with state:
                state.execution_status = ConversationExecutionStatus.FINISHED
            # No run() call: this fixture tests persistence and lifecycle only.
        client.portal.call(prepare)
        assert client.post(retained + "/release", headers=headers).status_code == 200
        assert identifier not in app.state.conversation_service._event_services
        assert client.get(native, headers=headers).json()["execution_status"] == "finished"
        assert client.post(retained + "/retain", headers=headers).status_code == 409
        if (directory / ".git").is_dir():
            shutil.rmtree(directory / ".git")
        directory.rmdir()
        assert client.post(retained + "/retain", headers=headers).status_code == 200
        assert client.post(native + "/run").status_code == 401
        assert client.post(native + "/run", headers=headers).status_code == 409
        assert client.delete(native, headers=headers).status_code == 409
        for socket in ("events", "session"):
            try:
                with client.websocket_connect(f"/sockets/{socket}/{identifier}", headers=headers):
                    raise AssertionError("retained_socket_accepted")
            except WebSocketDisconnect as exc:
                assert exc.code == 4409

    # A new server lifespan rebuilds its native catalog from the same volume.
    app = create_app()
    with TestClient(app) as client:
        assert client.get(native, headers=headers).status_code == 200
        events = client.get(native + "/events/search", headers=headers)
        assert events.status_code == 200 and events.json()["items"]
        assert client.post(retained + "/release", headers=headers).status_code == 200
        receipt = retention.read(identifier)
        receipt["expires_at"] = 1
        retention.write(identifier, receipt)
        client.portal.call(retention.expire, app.state.conversation_service)
        assert client.get(native, headers=headers).status_code == 404
        assert not retention.path(identifier).exists()
        assert not directory.exists()
    print(json.dumps({"native_history_retained": True, "restart_verified": True,
        "read_only": True, "expiry_verified": True, "model_calls": 0}))


if __name__ == "__main__":
    main()
