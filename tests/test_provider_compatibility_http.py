from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from prompt_enhancer.api import API_TOKEN_HEADER, create_app
from prompt_enhancer.application.providers import (
    CapabilityObservation,
    CapabilityState,
    CompatibilityReason,
    CompatibilityReasonCode,
    CompatibilityState,
    ExtractionCompleteness,
    ExtractionCompletenessState,
    ProviderCompatibilityBlockedError,
    ProviderCompatibilityCatalog,
    ProviderCompatibilityReport,
    ProviderCompatibilityService,
    ProviderSurface,
    ProviderSurfaceCompatibilityPolicy,
    TrustedProviderRegistry,
)
from prompt_enhancer.infrastructure.providers.codex_app_server import (
    CODEX_TEXT_WINDOW_DECODER_DESCRIPTOR,
)
from prompt_enhancer.infrastructure.providers.claude_code_hooks.adapter import (
    CLAUDE_CODE_HOOKS_DECODER_DESCRIPTOR,
)
from prompt_enhancer.infrastructure.providers.claude_code_hooks.text_source import (
    CLAUDE_CODE_TEXT_WINDOW_DECODER_DESCRIPTOR,
)
from prompt_enhancer.config import AppSettings
from prompt_enhancer.database import Database
from prompt_enhancer.interfaces.http.provider_compatibility_routes import (
    create_provider_compatibility_router,
)


NOW = datetime(2044, 5, 6, 7, 8, tzinfo=UTC)


def _report(state: CompatibilityState, descriptor=CODEX_TEXT_WINDOW_DECODER_DESCRIPTOR) -> ProviderCompatibilityReport:
    if state is CompatibilityState.UNAVAILABLE:
        return ProviderCompatibilityReport(
            descriptor=descriptor,
            provider_version=None,
            state=state,
            capabilities=tuple(CapabilityObservation(
                key=key, state=CapabilityState.UNKNOWN,
                reason_code=CompatibilityReasonCode.PROVIDER_UNAVAILABLE,
            ) for key in descriptor.capabilities),
            extraction=ExtractionCompleteness(state=ExtractionCompletenessState.NONE, observed_units=0),
            reasons=(CompatibilityReason(code=CompatibilityReasonCode.PROVIDER_UNAVAILABLE),),
            checked_at=NOW,
        )
    if state is CompatibilityState.EXACT:
        return ProviderCompatibilityReport(
            descriptor=descriptor,
            provider_version="0.144.5",
            state=state,
            capabilities=tuple(
                CapabilityObservation(key=key, state=CapabilityState.SUPPORTED)
                for key in descriptor.capabilities
            ),
            extraction=ExtractionCompleteness(
                state=ExtractionCompletenessState.COMPLETE,
                observed_units=len(descriptor.capabilities),
                eligible_units=len(descriptor.capabilities),
                coverage=1,
            ),
            checked_at=NOW,
        )
    return ProviderCompatibilityReport(
        descriptor=descriptor,
        provider_version="0.145.0",
        state=CompatibilityState.DEGRADED,
        capabilities=tuple(
            CapabilityObservation(key=key, state=CapabilityState.SUPPORTED)
            for key in descriptor.capabilities
        ),
        extraction=ExtractionCompleteness(
            state=ExtractionCompletenessState.UNKNOWN,
            observed_units=0,
        ),
        reasons=(
            CompatibilityReason(code=CompatibilityReasonCode.UNKNOWN_UNION_VARIANT),
        ),
        checked_at=NOW,
    )


class FixedProbe:
    def __init__(self, state: CompatibilityState, descriptor=CODEX_TEXT_WINDOW_DECODER_DESCRIPTOR) -> None:
        self.state = state
        self._descriptor = descriptor
        self.calls = 0

    @property
    def descriptor(self):
        return self._descriptor

    def check(self) -> ProviderCompatibilityReport:
        self.calls += 1
        return _report(self.state, self.descriptor)


def _catalog(state: CompatibilityState = CompatibilityState.EXACT):
    descriptor = CODEX_TEXT_WINDOW_DECODER_DESCRIPTOR
    probe = FixedProbe(state)
    service = ProviderCompatibilityService(
        TrustedProviderRegistry((descriptor,)),
        (probe,),
        clock=lambda: NOW,
    )
    return ProviderCompatibilityCatalog(service, (descriptor,)), probe


def test_http_exposes_cached_status_and_refreshes_only_on_explicit_post() -> None:
    catalog, probe = _catalog()
    app = FastAPI()
    app.include_router(create_provider_compatibility_router(lambda: None, catalog))
    client = TestClient(app)

    before = client.get("/v1/providers/codex/compatibility")
    assert before.status_code == 200
    assert before.json() == {
        "provider": "codex",
        "capability": "session_text_analysis",
        "state": "untested",
        "capability_state": "unknown",
        "provider_family": "codex_app_server",
        "provider_version": None,
        "adapter_family": "codex_app_server",
        "adapter_version": "0.7.0",
        "source_schema_family": "codex_thread",
        "source_schema_version": "codex-consumed-schema-v1",
        "content_schema_family": "codex_thread_items",
        "content_schema_version": "codex-thread-item-text-v8",
        "reason_code": "not_checked",
        "checked_at": None,
        "update_support": "unknown",
        "update_target": None,
    }
    assert probe.calls == 0

    refreshed = client.post("/v1/providers/codex/compatibility/check")
    assert refreshed.status_code == 200
    assert refreshed.json()["state"] == "exact"
    assert refreshed.json()["capability_state"] == "supported"
    assert refreshed.json()["checked_at"] == "2044-05-06T07:08:00Z"
    assert probe.calls == 1

    after = client.get("/v1/providers/codex/compatibility")
    assert after.json() == refreshed.json()
    assert probe.calls == 1
    assert client.get("/v1/providers/claude_code/compatibility").status_code == 404


@pytest.mark.parametrize("recovered", [False, True])
def test_explicit_check_reconsiders_an_unavailable_text_surface(recovered: bool) -> None:
    descriptors = (CLAUDE_CODE_TEXT_WINDOW_DECODER_DESCRIPTOR, CLAUDE_CODE_HOOKS_DECODER_DESCRIPTOR)
    text_probe = FixedProbe(CompatibilityState.UNAVAILABLE, descriptors[0])
    event_probe = FixedProbe(CompatibilityState.EXACT, descriptors[1])
    catalog = ProviderCompatibilityCatalog(ProviderCompatibilityService(
        TrustedProviderRegistry(descriptors), (text_probe, event_probe), clock=lambda: NOW,
    ), descriptors)
    catalog.refresh("claude_code", ProviderSurface.TEXT_WINDOW)
    text_probe.state = CompatibilityState.EXACT if recovered else CompatibilityState.UNAVAILABLE
    app = FastAPI()
    app.include_router(create_provider_compatibility_router(lambda: None, catalog))
    with TestClient(app) as client:
        cached = client.get("/v1/providers/claude_code/compatibility")
        assert cached.json()["capability"] == "operational_events"
        assert (text_probe.calls, event_probe.calls) == (1, 0)
        checked = client.post("/v1/providers/claude_code/compatibility/check")
        assert checked.status_code == 200
        assert checked.json()["capability"] == ("session_text_analysis" if recovered else "operational_events")
        assert checked.json()["state"] == "exact"
        assert text_probe.calls == 2
        assert event_probe.calls == (0 if recovered else 1)
        assert client.get("/v1/providers/claude_code/compatibility").json() == checked.json()
        assert text_probe.calls == 2


def test_degraded_compatibility_is_visible_but_cannot_authorize_text_read() -> None:
    catalog, _probe = _catalog(CompatibilityState.DEGRADED)
    policy = ProviderSurfaceCompatibilityPolicy(
        catalog,
        surface=ProviderSurface.TEXT_WINDOW,
        required_capabilities=CODEX_TEXT_WINDOW_DECODER_DESCRIPTOR.capabilities,
    )

    with pytest.raises(ProviderCompatibilityBlockedError):
        policy.require_compatible("codex")

    report = catalog.get_cached("codex", ProviderSurface.TEXT_WINDOW)
    assert report is not None
    assert report.state is CompatibilityState.DEGRADED
    assert "PRIVATE" not in report.model_dump_json()


def test_integrated_routes_require_local_auth_and_post_is_the_only_refresh(
    tmp_path,
) -> None:
    catalog, probe = _catalog()
    database = Database(tmp_path / "metrics.sqlite3")
    app = create_app(
        settings=AppSettings(home=tmp_path),
        database=database,
        api_token="example_provider_compatibility_token_12345",
        provider_compatibility_catalog=catalog,
    )
    client = TestClient(app, base_url="http://127.0.0.1")

    with client:
        unauthorized = client.get("/v1/providers/codex/compatibility")
        cached = client.get(
            "/v1/providers/codex/compatibility",
            headers={
                API_TOKEN_HEADER: "example_provider_compatibility_token_12345"
            },
        )
        refreshed = client.post(
            "/v1/providers/codex/compatibility/check",
            headers={
                API_TOKEN_HEADER: "example_provider_compatibility_token_12345"
            },
        )

    assert unauthorized.status_code == 401
    assert cached.status_code == 200
    assert cached.json()["state"] == "untested"
    assert refreshed.status_code == 200
    assert refreshed.json()["state"] == "exact"
    assert probe.calls == 1
