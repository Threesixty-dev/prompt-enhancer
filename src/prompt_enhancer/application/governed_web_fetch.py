"""Content-free contracts for exact, native-approved public web fetches."""

from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Literal, Protocol

from pydantic import SecretStr

from ..domain import StrictModel


WEB_FETCH_POLICY_VERSION = "governed-web-fetch.v1"


class GovernedWebFetchError(ValueError):
    """A content-free refusal; URLs and response text never enter its message."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class AgentWebFetchCapability(StrictModel):
    """Local capability metadata; availability does not grant network authority."""

    contract_version: Literal["agent-web-fetch-capability.v1"] = (
        "agent-web-fetch-capability.v1"
    )
    available: bool
    policy_version: Literal[WEB_FETCH_POLICY_VERSION] = WEB_FETCH_POLICY_VERSION
    reason_code: Literal["available", "governed_fetcher_unavailable"]
    requires_per_fetch_approval: Literal[True] = True
    network_scope: Literal["public_https"] = "public_https"


@dataclass(frozen=True, slots=True)
class PreparedWebFetch:
    """Exact normalized target displayed and approved before egress."""

    url: SecretStr


@dataclass(frozen=True, slots=True)
class GovernedWebFetchResult:
    """Ephemeral decoded text plus bounded, non-content execution facts."""

    text: str
    content_type: Literal["text/plain", "text/html"]
    byte_size: int
    truncated: bool
    policy_version: Literal[WEB_FETCH_POLICY_VERSION] = WEB_FETCH_POLICY_VERSION


class GovernedWebFetcher(Protocol):
    def prepare(self, raw_url: str) -> PreparedWebFetch: ...

    def fetch(
        self,
        request: PreparedWebFetch,
        *,
        cancellation: threading.Event | None = None,
    ) -> GovernedWebFetchResult: ...


__all__ = (
    "AgentWebFetchCapability",
    "GovernedWebFetcher",
    "GovernedWebFetchError",
    "GovernedWebFetchResult",
    "PreparedWebFetch",
    "WEB_FETCH_POLICY_VERSION",
)
