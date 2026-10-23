"""Bounded Bench API client. No provider access, implicit retries or raw output."""

from __future__ import annotations

import hashlib
import ipaddress
import math
from pathlib import Path
import re
import ssl
import time
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx

from .definitions import PreflightReceipt, RunInput, RunPlan, fingerprint
from .errors import BenchError
from .private_io import decode_json, local_path, read_json, write_json

MAX_RESPONSE_BYTES = 32_000_000
REMOTE_ERRORS = frozenset({
    "invalid_request", "definition_not_found", "run_not_found", "invalid_request_id",
    "idempotency_conflict", "unknown_selection", "invalid_override_parameters",
    "core_contract_violation", "core_version_unavailable", "pinned_core_build_unavailable",
    "pinned_core_build_mismatch", "core_image_variant_mismatch", "workflow_definition_unsupported",
    "workflow_core_incompatible", "retry_requires_reconciled_terminal_run", "invalid_run_cursor",
    "versioned_experiment_required", "workflow_step_not_configurable", "request_too_large",
    "consumer_binding_requires_consumer_strategy", "core_protocol_mismatch",
})


def identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", value):
        raise BenchError("invalid_identifier")
    return value


def origin_url(value: str) -> str:
    try:
        if not isinstance(value, str) or len(value) > 2048 or not value.isascii() or any(c.isspace() or ord(c) < 32 for c in value):
            raise ValueError
        value = value.rstrip("/")
        parts = urlsplit(value)
        port = parts.port
        if (not parts.hostname or parts.username is not None or parts.password is not None
                or parts.path or parts.query or parts.fragment or "\\" in value
                or (port is not None and not 0 < port < 65536)):
            raise ValueError
        loopback = parts.hostname == "localhost"
        try:
            loopback = loopback or ipaddress.ip_address(parts.hostname).is_loopback
        except ValueError:
            pass
        if parts.scheme != "https" and not (parts.scheme == "http" and loopback):
            raise ValueError
        return value
    except (ValueError, AttributeError):
        raise BenchError("https_or_loopback_origin_required") from None


class BenchClient:
    def __init__(self, origin: str, *, access_client_id=None, access_client_secret=None, transport=None):
        self.origin = origin_url(origin)
        if bool(access_client_id) != bool(access_client_secret):
            raise BenchError("gateway_credentials_incomplete")
        headers = {"Origin": self.origin, "Accept": "application/json", "User-Agent": "PromptEnhancer-Bench-Client/1"}
        if access_client_id and access_client_secret:
            if any(ord(c) < 33 or ord(c) > 126 for c in access_client_id + access_client_secret):
                raise BenchError("invalid_access_credentials")
            headers.update({"CF-Access-Client-Id": access_client_id, "CF-Access-Client-Secret": access_client_secret})
        self.http = httpx.Client(base_url=self.origin, headers=headers, timeout=10,
            verify=ssl.create_default_context(), follow_redirects=False, trust_env=False, transport=transport)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.http.close()

    def request(self, method: str, path: str, *, body=None, expected=200, timeout=30):
        started = time.monotonic()
        try:
            with self.http.stream(method, path, json=body, timeout=min(10, timeout)) as response:
                if 300 <= response.status_code < 400:
                    raise BenchError("gateway_redirect_refused")
                if response.status_code in {401, 403}:
                    raise BenchError("gateway_access_denied")
                if response.headers.get("content-type", "").split(";")[0] != "application/json":
                    raise BenchError("json_response_required")
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_RESPONSE_BYTES:
                        raise BenchError("response_too_large")
                    if time.monotonic() - started >= timeout:
                        raise BenchError("request_timeout")
                value = decode_json(bytes(data))
                if not isinstance(value, dict):
                    raise BenchError("response_contract_invalid")
                if response.status_code != expected:
                    error = value.get("error")
                    code = error.get("code") if isinstance(error, dict) else None
                    raise BenchError(code if isinstance(code, str) and code in REMOTE_ERRORS else "bench_http_error")
                return value
        except (httpx.HTTPError, OSError):
            raise BenchError("transport_unconfirmed") from None

    def preflight(self, plan: RunPlan):
        try:
            value = PreflightReceipt.model_validate(self.request("POST", "/api/runs/preflight", body=plan.model_dump()))
        except ValueError:
            raise BenchError("response_contract_invalid") from None
        if value.stableId != plan.stableId or value.revision != plan.revision:
            raise BenchError("response_contract_invalid")
        return value.model_dump()

    def run(self, run_id: str, *, timeout=30):
        value = self.request("GET", "/api/runs/" + identifier(run_id), timeout=timeout)
        if value.get("id") != run_id:
            raise BenchError("run_identity_mismatch")
        return value

    def submit(self, plan: RunPlan, receipt_path: Path, *, retry_of=None):
        if retry_of is not None:
            identifier(retry_of)
        receipt_path = local_path(receipt_path)
        origin_hash = hashlib.sha256(self.origin.encode()).hexdigest()
        body = plan.model_dump() | {"retryOf": retry_of}
        request_hash = fingerprint(body)
        if receipt_path.exists():
            receipt = read_json(receipt_path, private=True)
            try:
                if (not isinstance(receipt, dict) or set(receipt) != {"schemaVersion", "originSha256", "requestSha256", "requestId", "runId"}
                        or receipt["schemaVersion"] != "bench-submission/v1"
                        or receipt["originSha256"] != origin_hash or receipt["requestSha256"] != request_hash
                        or str(UUID(receipt["requestId"])) != receipt["requestId"]
                        or (receipt["runId"] is not None and str(UUID(receipt["runId"])) != receipt["runId"])):
                    raise ValueError
            except (ValueError, TypeError, AttributeError, KeyError):
                raise BenchError("submission_receipt_mismatch") from None
            if receipt["runId"] is not None:
                return receipt
        else:
            receipt = {"schemaVersion": "bench-submission/v1", "originSha256": origin_hash,
                       "requestSha256": request_hash, "requestId": str(uuid4()), "runId": None}
            write_json(receipt_path, receipt)
        payload = RunInput.model_validate(body | {"requestId": receipt["requestId"]})
        value = self.request("POST", "/api/runs", body=payload.model_dump(), expected=202)
        try:
            run_id = str(UUID(value["runId"]))
            if run_id != value["runId"]:
                raise ValueError
        except (KeyError, ValueError, TypeError, AttributeError):
            raise BenchError("submission_acknowledgement_invalid") from None
        receipt["runId"] = run_id
        write_json(receipt_path, receipt, replace=True)
        return receipt


def bounded_seconds(value, minimum, maximum):
    try:
        number = float(value)
    except (ValueError, TypeError):
        raise BenchError("invalid_time_limit") from None
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise BenchError("invalid_time_limit")
    return number
