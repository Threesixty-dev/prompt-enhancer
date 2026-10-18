"""Bench-only history retention adapter for OpenHands Agent Server 1.49.1.

The pinned server has no API to unload a runtime without deleting history.
Keep the small compatibility boundary here, never in provider ingestion.
"""

import asyncio
from contextlib import asynccontextmanager, suppress
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse


class RetainedSocketGuard:
    def __init__(self, app, retention):
        self.app, self.retention = app, retention

    async def __call__(self, scope, receive, send):
        parts = scope.get("path", "").strip("/").split("/")
        if (scope["type"] == "websocket" and len(parts) == 3
                and parts[0] == "sockets" and parts[1] in {"events", "session"}):
            try:
                identifier = UUID(parts[2])
            except ValueError:
                pass
            else:
                # Both native sockets accept inbound messages that run the agent.
                # Historical inspection uses the authenticated REST event API.
                if self.retention.read(identifier) is not None:
                    await send({"type": "websocket.close", "code": 4409})
                    return
        await self.app(scope, receive, send)


class Retention:
    def __init__(self, directory: Path, days: int):
        if not 1 <= days <= 90:
            raise ValueError("retention_days_invalid")
        self.directory, self.seconds = directory, days * 86400
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory.chmod(0o700)

    def path(self, conversation_id: UUID):
        return self.directory / f"{conversation_id}.json"

    def read(self, conversation_id: UUID):
        path = self.path(conversation_id)
        if not path.exists():
            return None
        if path.is_symlink():
            raise ValueError("retention_receipt_invalid")
        value = json.loads(path.read_text())
        if value.get("conversation_id") != str(conversation_id):
            raise ValueError("retention_receipt_invalid")
        return value

    def write(self, conversation_id: UUID, value):
        path = self.path(conversation_id)
        fd, name = tempfile.mkstemp(dir=self.directory, suffix=".pending")
        pending = Path(name)
        try:
            with os.fdopen(fd, "w") as output:
                json.dump(value, output)
                output.flush()
                os.fsync(output.fileno())
            pending.replace(path)
        finally:
            pending.unlink(missing_ok=True)
        # Windows cannot open a directory with os.open; the file was synced above.
        if os.name != "nt":
            fd = os.open(self.directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    async def release(self, service, conversation_id: UUID):
        async with service._conversation_lifecycle(conversation_id):
            info = await service.get_conversation(conversation_id)
            if info is None:
                raise HTTPException(404, "conversation_not_found")
            if getattr(info.execution_status, "value", info.execution_status) != "finished":
                raise HTTPException(409, "conversation_not_finished")
            if info.workspace.working_dir != f"/tmp/enhancement-{conversation_id}":
                raise HTTPException(409, "conversation_not_bench_owned")
            event_service = service._event_services.get(conversation_id)
            if event_service is not None:
                # Never cancel work or discard a subscribed/uncertain runtime.
                deadline = time.monotonic() + 2
                while not event_service.is_idle_evictable():
                    if time.monotonic() >= deadline:
                        raise HTTPException(409, "conversation_still_active")
                    await asyncio.sleep(0.05)
                agent = event_service.get_conversation().agent
                process = getattr(agent, "_process", None)
                await event_service.__aexit__(None, None, None)
                if event_service.is_open() or (process is not None and not isinstance(process.returncode, int)):
                    raise HTTPException(409, "runtime_release_unconfirmed")
                record = service._conversation_records[conversation_id]
                record.stored, record.cached_info = event_service.stored, None
                service._event_services.pop(conversation_id)
            # A held receipt never expires: core must confirm workspace cleanup.
            receipt = self.read(conversation_id) or {
                "conversation_id": str(conversation_id), "runtime_released": True,
                "cleanup_confirmed": False, "expires_at": None,
            }
            self.write(conversation_id, receipt)
            return receipt

    async def retain(self, service, conversation_id: UUID):
        async with service._conversation_lifecycle(conversation_id):
            receipt = self.read(conversation_id)
            if receipt is None or conversation_id in service._event_services:
                raise HTTPException(409, "runtime_release_required")
            info = await service.get_conversation(conversation_id)
            if info is None or getattr(info.execution_status, "value", info.execution_status) != "finished":
                raise HTTPException(409, "conversation_not_finished")
            workspace = Path(f"/tmp/enhancement-{conversation_id}")
            if workspace.exists() or workspace.is_symlink():
                raise HTTPException(409, "workspace_cleanup_required")
            if not receipt["cleanup_confirmed"]:
                receipt.update(cleanup_confirmed=True, expires_at=time.time() + self.seconds)
                self.write(conversation_id, receipt)
            return receipt

    async def expire(self, service):
        # Only acknowledged completed bench attempts are eligible. Uncertain
        # conversations and cleanup holds are never inferred to be disposable.
        for path in self.directory.glob("*.json"):
            conversation_id = UUID(path.stem)
            receipt = self.read(conversation_id)
            if (not receipt["cleanup_confirmed"] or receipt["expires_at"] > time.time()
                    or conversation_id in service._event_services):
                continue
            info = await service.get_conversation(conversation_id)
            if info is not None:
                if (getattr(info.execution_status, "value", info.execution_status) != "finished"
                        or info.workspace.working_dir != f"/tmp/enhancement-{conversation_id}"):
                    continue
                if not await service.delete_conversation(conversation_id):
                    continue
            if (await service.get_conversation(conversation_id) is None
                    and not (service.conversations_dir / conversation_id.hex).exists()):
                # Native event inspection can recreate the empty owned workspace.
                workspace = Path(f"/tmp/enhancement-{conversation_id}")
                if workspace.is_symlink():
                    raise ValueError("workspace_cleanup_unconfirmed")
                metadata = workspace / ".git"
                if metadata.is_symlink():
                    metadata.unlink()
                elif metadata.is_dir():
                    shutil.rmtree(metadata)
                if workspace.exists():
                    workspace.rmdir()
                path.unlink()


def create_app():
    if any(importlib.metadata.version(name) != "1.49.1" for name in
           ("openhands-agent-server", "openhands-sdk")):
        raise RuntimeError("retention_server_version_unsupported")
    from openhands.agent_server.api import create_app as upstream_app
    from openhands.agent_server.dependencies import check_session_api_key, get_conversation_service

    retention = Retention(Path("/runtime/consumer/retention"),
                          int(os.environ.get("BENCH_CONSUMER_RETENTION_DAYS", "7")))
    app = upstream_app()
    upstream_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with upstream_lifespan(application):
            async def sweep():
                while True:
                    try:
                        await retention.expire(application.state.conversation_service)
                    except Exception:
                        # No exception text: upstream errors can contain content.
                        application.state.retention_error = True
                    else:
                        application.state.retention_error = False
                    await asyncio.sleep(60)
            task = asyncio.create_task(sweep())
            try:
                yield
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    app.router.lifespan_context = lifespan
    app.add_middleware(RetainedSocketGuard, retention=retention)

    @app.middleware("http")
    async def retained_history_is_read_only(request, call_next):
        parts = request.url.path.strip("/").split("/")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and parts[:2] == ["api", "conversations"] and len(parts) >= 3:
            try:
                conversation_id = UUID(parts[2])
            except ValueError:
                pass
            else:
                if retention.read(conversation_id) is not None:
                    if request.headers.get("X-Session-API-Key") not in app.state.config.session_api_keys:
                        return JSONResponse({"detail": "Unauthorized"}, status_code=401)
                    return JSONResponse({"detail": "retained_conversation_read_only"}, status_code=409)
        return await call_next(request)

    router = APIRouter(prefix="/api/bench", dependencies=[Depends(check_session_api_key)])

    @router.get("/retention")
    async def policy():
        return {"version": "bench-retention.v1", "retention_days": retention.seconds // 86400,
                "sweep_error": getattr(app.state, "retention_error", False)}

    @router.post("/conversations/{conversation_id}/release")
    async def release(conversation_id: UUID, service=Depends(get_conversation_service)):
        return await retention.release(service, conversation_id)

    @router.post("/conversations/{conversation_id}/retain")
    async def retain(conversation_id: UUID, service=Depends(get_conversation_service)):
        return await retention.retain(service, conversation_id)

    # Insert ahead of the upstream optional SPA catch-all.
    app.router.routes[0:0] = router.routes
    return app
