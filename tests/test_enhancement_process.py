"""Bounded owned worker cleanup; all subprocesses are test-created."""
import asyncio
import json
import os
import sys

import pytest

from prompt_enhancer.application.inference import INFERENCE_TRANSPORT_ERROR_CODES
from prompt_enhancer.enhancement.ports import CoreError
from prompt_enhancer.enhancement.process import run_worker


def test_worker_failure_is_sanitized():
    with pytest.raises(CoreError, match="remote_execution_unconfirmed"):
        asyncio.run(run_worker({"operation": "unknown", "content": "fictional untrusted text"}))


@pytest.mark.parametrize("code,uncertain,expected", [
    ("consumer_reply_invalid", False, "consumer_reply_invalid"),
    ("nli_tokenizer_unavailable", False, "nli_tokenizer_unavailable"),
    ("nli_tokenization_failed", False, "nli_tokenization_failed"),
    ("remote_cleanup_unconfirmed", True, "remote_cleanup_unconfirmed"),
    ("consumer_failure_protocol_unavailable", False, "consumer_failure_protocol_unavailable"),
    ("fictional private exception", False, "provider_failed"),
    ({"fictional": "exception"}, True, "remote_execution_unconfirmed"),
] + [(code, True, code) for code in sorted(INFERENCE_TRANSPORT_ERROR_CODES)]
  + [("consumer_upstream_" + category, True, "consumer_upstream_" + category)
     for category in ("connection", "access", "limit", "request", "service", "unknown")])
def test_worker_preserves_only_allowlisted_codes(monkeypatch, code, uncertain, expected):
    original = asyncio.create_subprocess_exec
    async def replace(*args, **kwargs):
        reply = json.dumps({"error": code, "uncertain": uncertain})
        return await original(sys.executable, "-c",
            "import sys;sys.stdin.read();print(" + repr(reply) + ")", **kwargs)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", replace)
    with pytest.raises(CoreError) as caught:
        asyncio.run(run_worker({}, remote=True))
    assert caught.value.code == expected
    assert caught.value.uncertain is uncertain


@pytest.mark.parametrize("code", sorted(INFERENCE_TRANSPORT_ERROR_CODES))
def test_child_serializes_only_safe_transport_category(monkeypatch, capsys, code):
    import io
    from types import SimpleNamespace
    from prompt_enhancer.enhancement import worker

    def fail(payload):
        raise CoreError(code, uncertain=True)
    monkeypatch.setattr(worker, "inference", fail)
    monkeypatch.setattr(worker.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b'{"operation":"inference"}')))
    worker.main()
    output = capsys.readouterr()
    assert json.loads(output.out) == {"error": code, "uncertain": True}
    assert output.err == ""


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
