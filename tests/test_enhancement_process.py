"""Bounded owned worker cleanup; all subprocesses are test-created."""
import asyncio
import os
import sys

import pytest

from prompt_enhancer.enhancement.ports import CoreError
from prompt_enhancer.enhancement.process import run_worker


def test_worker_failure_is_sanitized():
    with pytest.raises(CoreError, match="remote_execution_unconfirmed"):
        asyncio.run(run_worker({"operation": "unknown", "content": "fictional untrusted text"}))


def test_worker_environment_has_no_inherited_credentials(monkeypatch):
    original = asyncio.create_subprocess_exec
    monkeypatch.setenv("ENHANCEMENT_UNRELATED_CREDENTIAL", "example-invalid-value")
    async def replace(*args, **kwargs):
        return await original(sys.executable, "-c",
            "import json,os,sys;sys.stdin.read(); print(json.dumps({'isolated': 'ENHANCEMENT_UNRELATED_CREDENTIAL' not in os.environ}))", **kwargs)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", replace)
    assert asyncio.run(run_worker({}))["isolated"] is True


@pytest.mark.parametrize("remote", [False, True])
def test_cancel_confirms_local_process_exit_and_preserves_remote_unknown(monkeypatch, remote):
    original = asyncio.create_subprocess_exec
    owned = []
    async def replace(*args, **kwargs):
        if args[0] == "taskkill":
            return await original(*args, **kwargs)
        process = await original(sys.executable, "-c", "import time; time.sleep(30)", **kwargs)
        owned.append(process)
        return process
    monkeypatch.setattr(asyncio, "create_subprocess_exec", replace)
    async def scenario():
        task = asyncio.create_task(run_worker({}, remote=remote))
        while not owned:
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(CoreError if remote else asyncio.CancelledError) as exc:
            await task
        if remote:
            assert exc.value.uncertain
        assert owned[0].returncode is not None
    asyncio.run(scenario())
