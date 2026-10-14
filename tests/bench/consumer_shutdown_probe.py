"""Real pinned SDK socket shutdown with synthetic state; no agent/model call.

Executed inside the isolated static-consumer smoke container, never a provider
home. Runtime/history objects are fictional; the SDK and WebSocket are real.
"""
import asyncio
from contextlib import asynccontextmanager
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from uuid import uuid4

os.environ["OPENHANDS_SUPPRESS_BANNER"] = "1"
sys.path.insert(0, "/opt/bench-consumer")

from consumer_retention import Retention
from fastapi import HTTPException
from openhands.sdk.conversation.impl.remote_conversation import WebSocketCallbackClient
from openhands.sdk.event import ConversationStateUpdateEvent
from websockets.asyncio.server import serve


async def check(closing):
    connected, disconnected = asyncio.Event(), asyncio.Event()
    sockets = []
    update = ConversationStateUpdateEvent(key="execution_status", value="finished")

    async def handler(socket):
        sockets.append(socket)
        await socket.send(update.model_dump_json())
        connected.set()
        try:
            await socket.wait_closed()
        finally:
            disconnected.set()

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        identifier = uuid4()
        client = WebSocketCallbackClient(f"http://127.0.0.1:{port}", str(identifier), lambda event: None)
        client.start()
        thread = client._thread
        try:
            await asyncio.wait_for(connected.wait(), 3)
            assert await asyncio.to_thread(client.wait_until_ready, 3)
            if closing:
                await asyncio.to_thread(client.stop)
                assert thread.is_alive() and not disconnected.is_set()

            runtime = {"open": True}

            async def close(*args):
                runtime["open"] = False

            async def publish_state():
                await sockets[0].send(update.model_dump_json())

            event = SimpleNamespace(
                has_external_subscribers=lambda: not disconnected.is_set(),
                is_idle_evictable=lambda: disconnected.is_set(),
                _publish_state_update=publish_state,
                __aexit__=close, is_open=lambda: runtime["open"], stored=object(),
                get_conversation=lambda: SimpleNamespace(agent=SimpleNamespace(_process=None)))

            @asynccontextmanager
            async def lifecycle(identifier):
                yield

            async def info(identifier):
                return SimpleNamespace(execution_status="finished", workspace=SimpleNamespace(
                    working_dir=f"/tmp/enhancement-{identifier}"))

            service = SimpleNamespace(_conversation_lifecycle=lifecycle, get_conversation=info,
                _event_services={identifier: event},
                _conversation_records={identifier: SimpleNamespace(stored=None, cached_info=None)})
            with tempfile.TemporaryDirectory(prefix="example-socket-cleanup-") as directory:
                retention = Retention(Path(directory), 7)
                if closing:
                    receipt = await retention.release(service, identifier)
                    assert receipt["runtime_released"] and not receipt["cleanup_confirmed"]
                    assert receipt["expires_at"] is None and not runtime["open"]
                    await asyncio.to_thread(thread.join, 2)
                    assert not thread.is_alive() and disconnected.is_set()
                else:
                    try:
                        await retention.release(service, identifier)
                    except HTTPException as error:
                        assert error.status_code == 409 and error.detail == "conversation_still_active"
                    else:
                        raise AssertionError("connected observer was released")
                    assert runtime["open"] and retention.read(identifier) is None
        finally:
            # Stop our own test client and close only the test socket.
            stop = asyncio.create_task(asyncio.to_thread(client.stop))
            for socket in sockets:
                await socket.close()
            await stop
            await asyncio.to_thread(thread.join, 2)
            assert not thread.is_alive()


async def main():
    assert importlib.metadata.version("openhands-sdk") == "1.49.1"
    await check(True)
    await check(False)
    print(json.dumps({"scope": "static_consumer_socket_shutdown", "closing_client_released": True,
                      "connected_observer_held": True, "model_call_performed": False}))


if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(main(), timeout=30))
