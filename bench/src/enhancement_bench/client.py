"""Bounded HTTP client for the enhancer's own execution API."""

import json
from dataclasses import dataclass, field

import httpx

from .errors import BenchError
from .protocol import Contracts, execution_id


@dataclass(frozen=True)
class Endpoint:
    url: str
    token: str = field(repr=False)


def static_consumer_ready(token: str) -> bool:
    try:
        with httpx.Client(timeout=2, follow_redirects=False, trust_env=False) as client:
            with client.stream("GET", "http://127.0.0.1:8000/health", headers={"X-Session-API-Key": token}) as response:
                return response.status_code == 200
    except httpx.HTTPError:
        return False


class CoreClient:
    def __init__(self, endpoint: str | Endpoint, contracts: Contracts, *, transport=None):
        self.contracts = contracts
        headers = {"Authorization": "Bearer " + endpoint.token} if isinstance(endpoint, Endpoint) else {}
        self.http = httpx.Client(base_url=endpoint.url if isinstance(endpoint, Endpoint) else endpoint, headers=headers, timeout=httpx.Timeout(5),
                                 follow_redirects=False, trust_env=False, transport=transport)

    def close(self):
        self.http.close()

    def _json(self, method, path, value=None):
        try:
            with self.http.stream(method, path, json=value) as response:
                if response.status_code not in (200, 202, 204):
                    code = {404: "core_execution_missing", 409: "core_conflict", 422: "core_rejected",
                            429: "core_admission_denied", 503: "core_not_ready"}.get(response.status_code, "core_http_error")
                    raise BenchError(code, 502)
                if response.status_code == 204:
                    return None
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 2_000_000:
                        raise BenchError("core_response_too_large", 502)
                data = json.loads(body)
                if not isinstance(data, dict):
                    raise BenchError("core_contract_violation", 502)
                return data
        except (httpx.HTTPError, ValueError):
            raise BenchError("core_transport_uncertain", 502) from None

    def ready(self, core_version: str):
        value = self.contracts.validate("readiness", self._json("GET", "/health/ready"))
        if value["core_version"] != core_version:
            raise BenchError("core_version_mismatch", 502)
        if not value["ready"]:
            raise BenchError("core_not_ready", 503)
        return value

    def capabilities(self):
        value = self._json("GET", "/v1/capabilities")
        if value.get("protocol_version") != "enhancement.v1":
            raise BenchError("core_protocol_mismatch", 502)
        return value

    def submit(self, request):
        self.contracts.validate("execute-request", request)
        return self.contracts.correlated("progress", self._json("POST", "/v1/executions", request), request)

    def progress(self, request):
        return self.contracts.correlated("progress", self._json("GET", f"/v1/executions/{execution_id(request)}"), request)

    def cancel(self, request):
        return self.contracts.correlated("progress", self._json("POST", f"/v1/executions/{execution_id(request)}/cancel", {}), request)

    def result(self, request, core_version):
        value = self._json("GET", f"/v1/executions/{execution_id(request)}/result")
        return self.contracts.result(value, request, core_version)

    def forget(self, request):
        self._json("DELETE", f"/v1/executions/{execution_id(request)}")
