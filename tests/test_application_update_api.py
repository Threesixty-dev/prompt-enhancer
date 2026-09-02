from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from prompt_enhancer.api import API_TOKEN_HEADER, create_app
from prompt_enhancer.application.updates import (
    ApplicationUpdateReason,
    ApplicationUpdateState,
    ApplicationUpdateStatus,
    UpdateChannel,
    UnconfiguredApplicationUpdateSurface,
)
from prompt_enhancer.config import AppSettings
from prompt_enhancer.interfaces.http.browser_session import CSRF_HEADER


TOKEN = "synthetic-update-token-000000000000000000000000"


class _EmptyStore:
    def initialize(self) -> None:
        return None

    def task_repository(self):
        from prompt_enhancer.application.tasks import MemoryTaskRepository

        return MemoryTaskRepository()

    def analysis_run_repository(self):
        from prompt_enhancer.application.analysis import MemoryAnalysisRunRepository

        return MemoryAnalysisRunRepository()

    def list_metric_definitions(self):
        return []

    def list_sessions(self, *, limit: int = 100, offset: int = 0):
        return []

    def get_session_metrics(self, session_id: str):
        return []


class _RecordingSurface:
    def __init__(self) -> None:
        self.checks = 0
        self.snapshot = ApplicationUpdateStatus(
            installed_version="1.2.3",
            channel=UpdateChannel.STABLE,
            state=ApplicationUpdateState.READY_TO_CHECK,
            can_check=True,
            can_stage=False,
            can_cancel=False,
            can_apply=False,
        )

    def status(self) -> ApplicationUpdateStatus:
        return self.snapshot

    def check(self) -> ApplicationUpdateStatus:
        self.checks += 1
        return self.snapshot


def _app(tmp_path: Path, service=None):
    return create_app(
        settings=AppSettings(home=tmp_path / "synthetic-state"),
        database=_EmptyStore(),
        api_token=TOKEN,
        application_update_service=service,
    )


def test_unconfigured_surface_is_content_free_and_network_silent() -> None:
    surface = UnconfiguredApplicationUpdateSurface(installed_version="1.2.3")

    assert surface.status() == surface.check()
    assert surface.status().model_dump(mode="json") == {
        "contract_version": "application-update-status.v1",
        "contains_private_data": False,
        "installed_version": "1.2.3",
        "channel": "stable",
        "state": "unconfigured",
        "available_version": None,
        "artifact_size_bytes": None,
        "downloaded_bytes": None,
        "last_checked_at": None,
        "reason_code": "release_feed_unconfigured",
        "verification_code": None,
        "can_check": False,
        "can_stage": False,
        "can_cancel": False,
        "can_apply": False,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"reason_code": None},
        {"can_check": True},
        {"available_version": "2.0.0"},
        {"downloaded_bytes": 0},
    ],
)
def test_unconfigured_contract_rejects_invented_capabilities(changes: dict) -> None:
    values = {
        "installed_version": "1.2.3",
        "channel": UpdateChannel.STABLE,
        "state": ApplicationUpdateState.UNCONFIGURED,
        "reason_code": ApplicationUpdateReason.RELEASE_FEED_UNCONFIGURED,
        "can_check": False,
        "can_stage": False,
        "can_cancel": False,
        "can_apply": False,
        **changes,
    }

    with pytest.raises(ValueError):
        ApplicationUpdateStatus(**values)


def test_update_status_is_authenticated_and_does_not_trigger_a_check(
    tmp_path: Path,
) -> None:
    service = _RecordingSurface()
    app = _app(tmp_path, service)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/v1/application-updates/status").status_code == 401
        response = client.get(
            "/v1/application-updates/status",
            headers={API_TOKEN_HEADER: TOKEN},
        )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, private"
    assert response.headers["pragma"] == "no-cache"
    assert response.json()["state"] == "ready_to_check"
    assert response.json()["contains_private_data"] is False
    assert service.checks == 0


def test_update_check_requires_an_explicit_same_origin_browser_gesture(
    tmp_path: Path,
) -> None:
    service = _RecordingSurface()
    app = _app(tmp_path, service)
    client = TestClient(app, base_url="http://127.0.0.1")

    assert client.post("/v1/application-updates/check").status_code == 401
    bootstrap = client.get("/auth/session")
    csrf = bootstrap.json()["csrf_token"]
    assert client.post(
        "/v1/application-updates/check",
        headers={CSRF_HEADER: csrf, "Origin": "http://example.invalid"},
    ).status_code == 403
    assert client.post(
        "/v1/application-updates/check",
        headers={
            API_TOKEN_HEADER: TOKEN,
            CSRF_HEADER: csrf,
            "Origin": "http://127.0.0.1",
        },
    ).status_code == 403
    assert service.checks == 0

    checked = client.post(
        "/v1/application-updates/check",
        headers={CSRF_HEADER: csrf, "Origin": "http://127.0.0.1"},
    )

    assert checked.status_code == 200
    assert checked.headers["cache-control"] == "no-store, private"
    assert checked.json()["state"] == "ready_to_check"
    assert service.checks == 1


def test_default_app_exposes_only_an_unconfigured_update_surface(tmp_path: Path) -> None:
    app = _app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.get(
            "/v1/application-updates/status",
            headers={API_TOKEN_HEADER: TOKEN},
        )

    assert response.status_code == 200
    assert response.json()["state"] == "unconfigured"
    assert response.json()["reason_code"] == "release_feed_unconfigured"
    assert response.json()["can_check"] is False
