#!/usr/bin/env python3
"""Versioned ACP 1.10.0 failure compatibility for OpenHands SDK 1.49.1."""

from __future__ import annotations

import copy
import json
import os
import signal
import subprocess
import sys
import threading

VENDOR = "/opt/bench-consumer/vendor/bin/codex-acp"
VENDOR_VERSION = "@agentclientprotocol/codex-acp 1.10.0"
MAX_FRAME = 8_000_000
CATEGORIES = frozenset({"connection", "access", "limit", "request", "service", "unknown"})


class ProtocolError(Exception):
    pass


def air(value):
    for key in ("_meta", "jetbrains", "air"):
        value = value.get(key, {}) if isinstance(value, dict) else {}
    return value if isinstance(value, dict) else {}


def failure_response(identifier, category):
    category = category if isinstance(category, str) and category in CATEGORIES else "unknown"
    return {"jsonrpc": "2.0", "id": identifier, "error": {
        "code": -32603, "message": "bench_consumer_upstream_" + category}}


class FailureGuard:
    def __init__(self):
        self.pending = {}
        self.negotiated = False

    def client_message(self, message):
        if not isinstance(message, dict):
            raise ProtocolError
        method = message.get("method")
        if method not in {"initialize", "session/prompt"}:
            return message
        identifier = message.get("id")
        if type(identifier) not in (str, int) or identifier in self.pending or len(self.pending) >= 64:
            raise ProtocolError
        if method == "session/prompt" and not self.negotiated:
            raise ProtocolError
        self.pending[identifier] = method
        if method == "initialize":
            message = copy.deepcopy(message)
            try:
                capabilities = message["params"].setdefault("clientCapabilities", {})
                metadata = capabilities.setdefault("_meta", {}).setdefault("jetbrains", {}).setdefault("air", {})
                advertised = metadata.setdefault("capabilities", [])
                if not isinstance(advertised, list) or metadata.get("version", 1) != 1:
                    raise ProtocolError
                metadata["version"] = 1
                if "sessionFailure" not in advertised:
                    advertised.append("sessionFailure")
            except (KeyError, AttributeError, TypeError):
                raise ProtocolError from None
        return message

    def server_message(self, message):
        if not isinstance(message, dict):
            raise ProtocolError
        identifier = message.get("id")
        # Server-initiated requests have a separate JSON-RPC ID namespace.
        if "method" in message or type(identifier) not in (str, int):
            return message
        method = self.pending.pop(identifier, None)
        if method is None:
            return message
        result = message.get("result")
        if method == "initialize":
            metadata = air(result)
            advertised = metadata.get("capabilities")
            self.negotiated = (type(metadata.get("version")) is int and metadata["version"] == 1
                and isinstance(advertised, list) and "sessionFailure" in advertised)
            if not self.negotiated:
                raise ProtocolError
            return message
        if "error" in message:
            return failure_response(identifier, "unknown")
        if not isinstance(result, dict):
            raise ProtocolError
        metadata = air(result)
        if "sessionFailure" not in metadata:
            return message
        failure = metadata["sessionFailure"]
        if type(metadata.get("version")) is not int or metadata["version"] != 1 or not isinstance(failure, dict):
            raise ProtocolError
        severity = failure.get("severity", "error")
        if severity == "warning":
            return message
        if severity != "error":
            raise ProtocolError
        # Interpret only the prompt response's typed failure, never assistant text
        # or a possibly unrelated late session-update notification.
        return failure_response(identifier, failure.get("category", "unknown"))


def read_message(stream):
    line = stream.readline(MAX_FRAME + 1)
    if not line:
        return None
    if len(line) > MAX_FRAME or not line.endswith(b"\n"):
        raise ProtocolError
    try:
        value = json.loads(line)
    except (ValueError, UnicodeError):
        raise ProtocolError from None
    if not isinstance(value, dict):
        raise ProtocolError
    return value


def write_message(stream, message):
    data = json.dumps(message, ensure_ascii=True, separators=(",", ":")).encode() + b"\n"
    if len(data) > MAX_FRAME:
        raise ProtocolError
    stream.write(data)
    stream.flush()


def stop_process(process):
    if os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    elif process.poll() is None:
        process.terminate()
    if process.poll() is None:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                if os.name != "nt":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
            process.wait(timeout=5)


def bridge(command, incoming, outgoing):
    guard, lock, failed = FailureGuard(), threading.Lock(), threading.Event()
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, start_new_session=os.name != "nt")

    def forward_client():
        try:
            while (message := read_message(incoming)) is not None:
                with lock:
                    message = guard.client_message(message)
                write_message(process.stdin, message)
            process.stdin.close()
            stop_process(process)
        except (ProtocolError, OSError):
            failed.set()
            stop_process(process)

    threading.Thread(target=forward_client, daemon=True).start()
    try:
        while (message := read_message(process.stdout)) is not None:
            with lock:
                message = guard.server_message(message)
            write_message(outgoing, message)
        return 1 if failed.is_set() else process.wait(timeout=5)
    finally:
        stop_process(process)


def main():
    def interrupted(*_):
        raise SystemExit(1)

    signal.signal(signal.SIGTERM, interrupted)
    try:
        version = subprocess.run([VENDOR, "--version"], capture_output=True, text=True, timeout=10, check=True)
        if version.stdout.strip() != VENDOR_VERSION:
            return 1
        if sys.argv[1:] == ["--version"]:
            print(VENDOR_VERSION)
            return 0
        return bridge([VENDOR, *sys.argv[1:]], sys.stdin.buffer, sys.stdout.buffer)
    except (ProtocolError, OSError, subprocess.SubprocessError):
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
