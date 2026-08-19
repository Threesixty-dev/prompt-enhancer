"""End to end: a Claude Code session, an accepted task, a passing test run.

The transcript adapter classifies the shell command as a TEST receipt, the
discovery engine proposes a candidate, a person accepts it, and the real
model-ensemble service (decoder 4, per-provider descriptor, Claude text
source) publishes outcome.first_pass_verification = 1/1 as an objective
receipt. Synthetic transcript in an isolated Claude home.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

from fastapi.testclient import TestClient

from prompt_enhancer.api import API_TOKEN_HEADER
from prompt_enhancer.application.discovery import AcceptCandidate, TaskReviewService
from prompt_enhancer.application.discovery.contracts import TaskCategory
from prompt_enhancer.bootstrap import bootstrap_local_application
from prompt_enhancer.config import AppSettings
from prompt_enhancer.domain import DataTier, Provider
from prompt_enhancer.infrastructure.identifiers import LocalArtifactIdFactory


T0 = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)
SESSION = "1d2e3f40-aaaa-4bbb-8ccc-000000000001"
CWD = "/srv/example/workspaces/e2e-demo"


def _row(kind: str, content: object, second: int) -> str:
    at = (T0 + timedelta(seconds=second)).isoformat().replace("+00:00", "Z")
    return json.dumps({"type": kind, "timestamp": at, "sessionId": SESSION, "cwd": CWD, "version": "2.1.0",
                       "message": {"role": kind, "content": content}})


def _write(claude_home: Path) -> None:
    project = claude_home / "projects" / "-srv-example-workspaces-e2e-demo"
    project.mkdir(parents=True, exist_ok=True)
    lines = [
        _row("user", "Please make the uploader retry three times and prove it with the tests.", 0),
        _row("assistant", [{"type": "text", "text": "I will add the retry and run the suite."},
                           {"type": "tool_use", "id": "toolu_1", "name": "Edit", "input": {"file_path": "/srv/example/uploader.py", "old_string": "x", "new_string": "y"}}], 5),
        _row("user", [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "ok"}], 6),
        _row("assistant", [{"type": "tool_use", "id": "toolu_2", "name": "Bash", "input": {"command": "pytest tests/test_uploader.py -q"}}], 10),
        _row("user", [{"type": "tool_result", "tool_use_id": "toolu_2", "content": "3 passed", "is_error": False}], 20),
        _row("assistant", [{"type": "text", "text": "Done: three retries, and the three uploader tests pass."}], 25),
    ]
    (project / f"{SESSION}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_claude_session_with_accepted_task_publishes_first_pass_verification(tmp_path: Path, monkeypatch) -> None:
    claude_home = tmp_path / "claude-home"
    monkeypatch.setenv("PROMPT_ENHANCER_CLAUDE_HOME", str(claude_home))
    _write(claude_home)
    settings = AppSettings(home=tmp_path / "app")
    application = bootstrap_local_application(settings)
    database = application.database
    database.grant_consent(Provider.CLAUDE_CODE, DataTier.REDACTED_CONTENT)
    assert application.create_claude_local_source_service().index(max_sessions=10).sessions_seen == 1
    row = database.list_sessions(limit=5, offset=0)[0]
    assert row["provider"] == "claude_code"
    session_id = str(row["session_id"])

    # Propose and accept the task so the session has one current accepted revision.
    sessions = [database.get_session(session_id)]
    discovery = application.create_discovery_persistence_service().discover_and_persist(sessions)
    candidate = discovery.batch.candidates[0]
    identifiers = LocalArtifactIdFactory(application.pseudonymizer)
    review = TaskReviewService(database.task_repository(), identifiers).apply(
        AcceptCandidate(
            candidate_id=candidate.candidate_id,
            expected_discovery_version=candidate.discovery_version,
            task_category=TaskCategory.FEATURE_IMPLEMENTATION,
        ),
        idempotency_key="example-e2e-accept-1",
    )
    assert len(review.output_revisions) == 1
    assert len(database.task_repository().list_current_revisions_for_session(session_id)) == 1

    # The composed typed-evidence projector (decoder 4, Claude descriptor) turns
    # the classified test run into a verification receipt linked to the
    # accepted task, and the objective projection publishes 1/1.
    from prompt_enhancer.application.analysis.objective_metric_projection import (
        project_objective_metric_overrides_v3,
    )

    projector = application.create_typed_evidence_projector()
    projection = projector.project(provider=Provider.CLAUDE_CODE, session_id=session_id)
    assert projection is not None
    assert projection.provenance.provider is Provider.CLAUDE_CODE
    assert projection.provenance.adapter_version == "claude-code-transcripts-adapter-1"
    assert len(projection.eligible_verification_task_reference_ids) == 1
    overrides = project_objective_metric_overrides_v3(projection, projector.descriptor_for(Provider.CLAUDE_CODE))
    first_pass = overrides["outcome.first_pass_verification"]
    assert (first_pass.value_state.value, first_pass.numerator, first_pass.denominator) == ("known", 1, 1)
    assert first_pass.explanation_code == "typed_first_verification_outcomes"

    # Without an accepted task the same session declares no task family.
    other = application.create_typed_evidence_projector()
    database.task_repository()  # the repository is shared; simulate "no revision" via a fresh store below
    from prompt_enhancer.application.analysis.provider_evidence import SafeEventTypedEvidenceProjector

    class _NoTasks:
        def list_current_revisions_for_session(self, _session_id: str):
            return ()

    bare = SafeEventTypedEvidenceProjector(
        database,
        identifiers,
        other.descriptor,
        tasks=_NoTasks(),
        descriptors={Provider.CLAUDE_CODE: other.descriptor_for(Provider.CLAUDE_CODE)},
    ).project(provider=Provider.CLAUDE_CODE, session_id=session_id)
    assert bare is not None and bare.eligible_verification_task_reference_ids == ()
    bare_first = project_objective_metric_overrides_v3(bare, other.descriptor_for(Provider.CLAUDE_CODE))["outcome.first_pass_verification"]
    assert bare_first.value_state.value == "unknown"

    # The session-analysis routes resolve the session's provider instead of
    # assuming Codex: the preview for this Claude session is served (200) rather
    # than failing as an unknown Codex thread.
    client = TestClient(application.create_http_app(), base_url="http://127.0.0.1")
    headers = {API_TOKEN_HEADER: settings.api_token_path.read_text(encoding="utf-8").strip()}
    preview = client.post(
        f"/v1/sessions/{session_id}/quality-analysis-previews",
        headers=headers,
        json={"preset_id": "coaching_profile_v1"},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["binding"]["provider"] == "claude_code"
