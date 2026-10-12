"""Owned process boundary for blocking SDK/model calls and bounded cleanup."""
from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import tempfile
from pathlib import Path

from .ports import CoreError

MAX_WORKER_OUTPUT = 512_000


async def run_worker(payload: dict, *, remote: bool = False) -> dict:
    with tempfile.TemporaryDirectory(prefix="enhancement-worker-") as isolated:
        # No inherited account, telemetry, proxy, or provider configuration.
        environment = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "WINDIR") if key in os.environ}
        environment.update({"HOME": isolated, "USERPROFILE": isolated,
            "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
            "PYTHONDONTWRITEBYTECODE": "1", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
            "HF_HOME": isolated, "HF_TOKEN_PATH": str(Path(isolated) / "disabled-token"),
            "LITELLM_LOCAL_MODEL_COST_MAP": "True", "DO_NOT_TRACK": "1",
            "OPENHANDS_SUPPRESS_BANNER": "1", "OTEL_SDK_DISABLED": "true"})
        return await _run(payload, remote=remote, environment=environment, cwd=isolated)


async def _run(payload: dict, *, remote: bool, environment: dict, cwd: str) -> dict:
    spawn = asyncio.create_task(asyncio.create_subprocess_exec(
        sys.executable, "-m", "prompt_enhancer.enhancement.worker",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL, start_new_session=os.name != "nt", env=environment, cwd=cwd,
    ))
    cancelled_during_spawn = False
    try:
        process = await asyncio.shield(spawn)
    except asyncio.CancelledError:
        process = await spawn
        cancelled_during_spawn = True

    async def stop():
        if process.returncode is None:
            if os.name != "nt":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                # SDK/model workers must not leave any owned subprocess alive.
                killer = await asyncio.create_subprocess_exec(
                    "taskkill", "/PID", str(process.pid), "/T", "/F",
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                try:
                    status = await asyncio.wait_for(killer.wait(), 5)
                except TimeoutError:
                    killer.kill()
                    await asyncio.wait_for(killer.wait(), 5)
                    raise CoreError("worker_cleanup_unconfirmed", uncertain=True) from None
                if status != 0:
                    raise CoreError("worker_cleanup_unconfirmed", uncertain=True)
            try:
                await asyncio.wait_for(process.wait(), 5)
            except TimeoutError:
                raise CoreError("worker_cleanup_unconfirmed", uncertain=True) from None

    try:
        if cancelled_during_spawn:
            raise asyncio.CancelledError
        process.stdin.write(json.dumps(payload).encode())
        await process.stdin.drain()
        process.stdin.close()
        chunks, size = [], 0
        while chunk := await process.stdout.read(16_384):
            size += len(chunk)
            if size > MAX_WORKER_OUTPUT:
                raise CoreError("worker_reply_invalid", uncertain=remote)
            chunks.append(chunk)
        await process.wait()
        if process.returncode != 0:
            raise CoreError("worker_failed", uncertain=remote)
        value = json.loads(b"".join(chunks))
        if not isinstance(value, dict):
            raise CoreError("worker_reply_invalid", uncertain=remote)
        if value.get("error"):
            raise CoreError("remote_execution_unconfirmed" if value.get("uncertain") else "provider_failed",
                            uncertain=value.get("uncertain") is True)
        return value
    except asyncio.CancelledError:
        await stop()
        if remote:
            # Killing an HTTP client is not confirmation that the remote agent
            # stopped. Quarantine the instance until operator reconciliation.
            raise CoreError("remote_execution_unconfirmed", uncertain=True) from None
        raise
    except CoreError:
        await stop()
        raise
    except Exception:
        await stop()
        raise CoreError("worker_reply_invalid", uncertain=remote) from None
