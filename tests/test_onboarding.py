"""First-run detection, one consent, first index, and periodic refresh."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import threading

from fastapi.testclient import TestClient

from prompt_enhancer.api import API_TOKEN_HEADER
from prompt_enhancer.application.onboarding import (
    LocalSourceRefreshWorker,
    OnboardingAccept,
    OnboardingService,
    count_transcripts,
    detect_codex,
)
from prompt_enhancer.bootstrap import bootstrap_local_application
from prompt_enhancer.config import AppSettings
from prompt_enhancer.database import Database
from prompt_enhancer.domain import DataTier, Provider


T0 = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)


def _transcript(claude_home: Path, session: str) -> None:
    project = claude_home / "projects" / "-srv-example-onboard"
    project.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps({"type": "user", "message": {"role": "user", "content": "Fix the onboarding demo"}, "timestamp": T0.isoformat().replace("+00:00", "Z"), "sessionId": session, "cwd": "/srv/example/onboard", "version": "2.1.0"}),
        json.dumps({"type": "assistant", "message": {"role": "assistant", "model": "claude-opus-5", "usage": {"input_tokens": 10, "output_tokens": 5}, "content": [{"type": "text", "text": "Done."}]}, "timestamp": (T0 + timedelta(seconds=5)).isoformat().replace("+00:00", "Z"), "sessionId": session, "cwd": "/srv/example/onboard", "version": "2.1.0"}),
    ]
    (project / f"{session}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_detection_reads_only_presence(tmp_path: Path) -> None:
    assert detect_codex(lambda name: None) is False
    assert detect_codex(lambda name: "/usr/local/bin/codex" if name == "codex" else None) is True
    assert count_transcripts(tmp_path) is None
    _transcript(tmp_path, "one")
    assert count_transcripts(tmp_path) == 1


def test_status_accept_and_refresh_flow(tmp_path: Path, monkeypatch) -> None:
    claude_home = tmp_path / "claude-home"
    monkeypatch.setenv("PROMPT_ENHANCER_CLAUDE_HOME", str(claude_home))
    settings = AppSettings(home=tmp_path / "app")
    application = bootstrap_local_application(settings)
    _transcript(claude_home, "s1")
    _transcript(claude_home, "s2")
    service = OnboardingService(
        application.database,
        claude_home=lambda: claude_home,
        set_claude_home=None,
        index_codex=lambda: 0,
        index_claude=lambda: int(application.create_claude_local_source_service().index(max_sessions=100).sessions_seen),
        which=lambda name: None,
        clock=lambda: T0,
    )
    status = service.status()
    codex, claude = status.providers
    assert codex.installed is False and claude.installed is True and claude.transcript_files == 2
    assert status.needs_onboarding is True and status.any_installed is True
    result = service.accept(OnboardingAccept(providers=frozenset({"claude_code"})))
    assert result.granted == ("claude_code",) and result.indexed_sessions == 2
    assert application.database.has_active_consent(Provider.CLAUDE_CODE, DataTier.REDACTED_CONTENT)
    after = service.status()
    assert after.needs_onboarding is False and after.last_refresh_at == T0 and after.last_refresh_error is False
    assert after.providers[1].indexed_sessions == 2
    # A provider that is not installed cannot be accepted.
    try:
        service.accept(OnboardingAccept(providers=frozenset({"codex"})))
    except Exception as error:  # noqa: BLE001
        assert "codex_not_installed" in str(error)
    else:
        raise AssertionError("expected codex_not_installed")


def test_refresh_swallows_provider_errors_and_worker_stops(tmp_path: Path) -> None:
    settings = AppSettings(home=tmp_path / "app")
    application = bootstrap_local_application(settings)
    Database(settings.database_path).grant_consent(Provider.CODEX, DataTier.REDACTED_CONTENT)
    calls = {"n": 0}

    def failing_codex() -> int:
        calls["n"] += 1
        raise RuntimeError("app server unavailable")

    service = OnboardingService(application.database, claude_home=lambda: tmp_path / "none", set_claude_home=None,
                                index_codex=failing_codex, index_claude=lambda: 0, which=lambda n: None,
                                refresh_interval_seconds=60, clock=lambda: T0)
    assert service.refresh() == 0
    assert calls["n"] == 1 and service.status().last_refresh_error is True
    worker = LocalSourceRefreshWorker(service, initial_delay_seconds=0.05)
    worker.start()
    deadline = datetime.now(UTC) + timedelta(seconds=5)
    while calls["n"] < 2 and datetime.now(UTC) < deadline:
        threading.Event().wait(0.05)
    worker.stop()
    assert calls["n"] >= 2


def test_http_onboarding_routes_and_path_override(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("PROMPT_ENHANCER_CLAUDE_HOME", raising=False)
    # Pin PATH detection: this machine may have the real Codex CLI installed.
    monkeypatch.setattr("prompt_enhancer.application.onboarding.shutil.which", lambda name: None)
    settings = AppSettings(home=tmp_path / "app")
    application = bootstrap_local_application(settings)
    client = TestClient(application.create_http_app(), base_url="http://127.0.0.1")
    headers = {API_TOKEN_HEADER: settings.api_token_path.read_text(encoding="utf-8").strip()}
    assert client.get("/v1/onboarding").status_code == 401
    status = client.get("/v1/onboarding", headers=headers).json()
    assert {p["provider"] for p in status["providers"]} == {"codex", "claude_code"}
    # Point the app at a folder the person supplies.
    supplied = tmp_path / "supplied-claude-home"
    _transcript(supplied, "p1")
    bad = client.post("/v1/onboarding/accept", headers=headers, json={"providers": ["claude_code"], "claude_home": str(tmp_path / "nope")})
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "claude_home_invalid"
    ok = client.post("/v1/onboarding/accept", headers=headers, json={"providers": ["claude_code"], "claude_home": str(supplied)})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["granted"] == ["claude_code"] and body["indexed_sessions"] == 1
    assert (settings.claude_home_override_path).read_text(encoding="utf-8").strip() == str(supplied)
    sessions = client.get("/v1/sessions?limit=50&offset=0", headers=headers).json()["sessions"]
    assert [s["provider"] for s in sessions] == ["claude_code"]
    assert sessions[0]["session_display_name"] == "Fix the onboarding demo"
    refreshed = client.post("/v1/onboarding/refresh", headers=headers)
    assert refreshed.status_code == 200 and refreshed.json()["needs_onboarding"] is False
    # Default-on analysis: the indexed project holds a standing local grant,
    # and refreshing again does not duplicate it.
    grants = client.get("/v1/automation-grants?provider=claude_code&active_only=true", headers=headers)
    assert grants.status_code == 200, grants.text
    records = grants.json()
    assert len(records) == 1
    assert records[0]["scope"]["provider"] == "claude_code"
    assert records[0]["scope"]["project_id"] == sessions[0]["project_id"]
    assert records[0]["scope"]["local_only"] is True
    client.post("/v1/onboarding/refresh", headers=headers)
    assert len(client.get("/v1/automation-grants?provider=claude_code&active_only=true", headers=headers).json()) == 1
    # Indexing also proposes task candidates, so the Discovery inbox is not empty.
    inbox = client.get("/v1/discovery/candidates?limit=50&offset=0", headers=headers)
    assert inbox.status_code == 200, inbox.text
    candidates = inbox.json()["candidates"]
    assert len(candidates) >= 1, inbox.text
    # Candidates carry the catalog names so the inbox shows titles, not hashes.
    assert candidates[0]["candidate"]["session_display_name"] == "Fix the onboarding demo"
    assert candidates[0]["candidate"]["project_display_name"]
    # The transcript text window is now the provider's primary compatibility surface.
    compat = client.post("/v1/providers/claude_code/compatibility/check", headers=headers).json()
    assert compat["capability"] == "session_text_analysis"
    assert compat["state"] == "compatible" and compat["provider_version"] == "2.1.0"
