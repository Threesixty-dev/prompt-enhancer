"""Synthetic directory moves preserve nested reviewed artifact lineage."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import Path
import threading

import pytest

from prompt_enhancer.application.agent_artifacts import (
    AgentArtifactError,
    AgentArtifactService,
    CaptureAgentArtifact,
    DirectoryArtifactMoveReconciliation,
    MAX_DIRECTORY_MOVE_RECONCILIATION_BYTES,
)
from prompt_enhancer.application.agent_catalog import (
    AgentCatalogService,
    AgentRetentionPolicy,
    CreateAgentProject,
    ResumeAgentSession,
)
from prompt_enhancer.application.local_agent import AgentSettings, LocalAgentService
from prompt_enhancer.application.local_agent_file_lifecycle import (
    WORKSPACE_DIRECTORY_MOVE_CONFIRMATION,
    WorkspaceDirectoryMoveApplyCommand,
    WorkspaceDirectoryMovePreviewCommand,
)
from prompt_enhancer.infrastructure.sqlite.agent_artifacts import (
    SqliteAgentArtifactRepository,
)
from prompt_enhancer.infrastructure.sqlite.agent_catalog import (
    AGENT_CATALOG_DATABASE_FILENAME,
    AgentCatalogSqliteDatabase,
    SqliteAgentCatalogRepository,
)


T0 = datetime(2026, 8, 27, 15, 0, tzinfo=UTC)


def _ids(start: int = 1):
    value = start
    while True:
        yield f"{value:032x}"
        value += 1


def _fixture(tmp_path: Path):
    database = AgentCatalogSqliteDatabase(
        tmp_path / "catalog" / AGENT_CATALOG_DATABASE_FILENAME
    )
    catalog = AgentCatalogService(
        SqliteAgentCatalogRepository(database),
        clock=lambda: T0,
        id_factory=_ids(1).__next__,
    )
    project = catalog.create_project(CreateAgentProject(name="Synthetic move project"))
    workspace = tmp_path / "example-workspace"
    workspace.mkdir()
    artifacts = AgentArtifactService(
        SqliteAgentArtifactRepository(database),
        catalog,
        clock=lambda: T0,
        id_factory=_ids(100).__next__,
    )
    return database, catalog, artifacts, project, workspace


def test_verified_directory_move_advances_nested_artifacts_after_recomposition(
    tmp_path: Path,
) -> None:
    database, catalog, artifacts, project, workspace = _fixture(tmp_path)
    files = {
        "docs/guides/alpha.md": b"Synthetic alpha artifact.\n",
        "docs/guides/nested/beta.txt": b"Synthetic beta artifact.\n",
    }
    for relative_path, payload in files.items():
        path = workspace / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    (workspace / "archive").mkdir()

    agent = LocalAgentService(
        chat=lambda _alias, _body: (200, b"{}", "application/json"),
        active_model=lambda: None,
        allowed_roots=(tmp_path,),
        catalog=catalog,
        artifacts=artifacts,
        clock=lambda: T0,
    )
    session = agent.create(
        AgentSettings(
            workspace=str(workspace),
            project_id=project.project_id,
            title="Synthetic directory move chat",
            retention_policy=AgentRetentionPolicy.LOCAL_HISTORY,
        )
    )

    captured = {}
    for relative_path, payload in files.items():
        captured[relative_path] = agent.capture_artifact(
            project_id=project.project_id,
            session_id=session.session_id,
            command=CaptureAgentArtifact(
                path=relative_path,
                expected_sha256=hashlib.sha256(payload).hexdigest(),
                expected_byte_size=len(payload),
            ),
        )

    preview = agent.preview_workspace_directory_move(
        session.session_id,
        WorkspaceDirectoryMovePreviewCommand(
            source_path="docs",
            target_path="archive/docs",
        ),
    )
    moved = agent.apply_workspace_directory_move(
        session.session_id,
        preview.preview_id,
        WorkspaceDirectoryMoveApplyCommand(
            source_path=preview.source_path,
            target_path=preview.target_path,
            confirmation=WORKSPACE_DIRECTORY_MOVE_CONFIRMATION,
        ),
    )

    assert moved.operation == "directory_moved"
    assert not (workspace / "docs").exists()
    for old_path, payload in files.items():
        new_path = f"archive/{old_path}"
        assert (workspace / new_path).read_bytes() == payload
        relocated = agent.get_artifact(
            project_id=project.project_id,
            session_id=session.session_id,
            artifact_id=captured[old_path].artifact_id,
        )
        assert relocated.artifact_id == captured[old_path].artifact_id
        assert relocated.path == new_path
        assert relocated.version_count == 2
        assert [version.path for version in relocated.versions] == [old_path, new_path]
        assert [version.provenance for version in relocated.versions] == [
            "verified_output",
            "reviewed_move",
        ]
        assert [version.sha256 for version in relocated.versions] == [
            hashlib.sha256(payload).hexdigest(),
            hashlib.sha256(payload).hexdigest(),
        ]

    restarted_catalog = AgentCatalogService(
        SqliteAgentCatalogRepository(AgentCatalogSqliteDatabase(database.path)),
        clock=lambda: T0,
        id_factory=_ids(500).__next__,
    )
    restarted_artifacts = AgentArtifactService(
        SqliteAgentArtifactRepository(AgentCatalogSqliteDatabase(database.path)),
        restarted_catalog,
        clock=lambda: T0,
        id_factory=_ids(600).__next__,
    )
    for old_path, captured_artifact in captured.items():
        recovered = restarted_artifacts.get_artifact(
            project_id=project.project_id,
            session_id=session.session_id,
            artifact_id=captured_artifact.artifact_id,
            workspace=workspace,
        )
        assert recovered.path == f"archive/{old_path}"
        assert recovered.version_count == 2
        assert [version.path for version in recovered.versions] == [
            old_path,
            f"archive/{old_path}",
        ]


def _prepared_nested_directory_move(tmp_path: Path):
    database, catalog, artifacts, project, workspace = _fixture(tmp_path)
    files = {"docs/a.txt": b"Synthetic A.\n", "docs/nested/b.txt": b"Synthetic B.\n"}
    for relative, payload in files.items():
        path = workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    (workspace / "archive").mkdir()
    agent = LocalAgentService(
        chat=lambda _alias, _body: (200, b"{}", "application/json"), active_model=lambda: None,
        allowed_roots=(tmp_path,), catalog=catalog, artifacts=artifacts, clock=lambda: T0,
    )
    session = agent.create(AgentSettings(
        workspace=str(workspace), project_id=project.project_id,
        title="Synthetic recovery directory move", retention_policy=AgentRetentionPolicy.LOCAL_HISTORY,
    ))
    captured = {
        path: agent.capture_artifact(project_id=project.project_id, session_id=session.session_id,
            command=CaptureAgentArtifact(path=path, expected_sha256=hashlib.sha256(payload).hexdigest(), expected_byte_size=len(payload)))
        for path, payload in files.items()
    }
    live = agent._session(session.session_id)  # synthetic pre-effect seam
    prepared = live.tools.prepare_directory_move("docs", "archive/docs")
    intent = artifacts.prepare_reviewed_directory_move(
        project_id=project.project_id, session_id=session.session_id, workspace=workspace,
        source_path=prepared.source_path, target_path=prepared.target_path,
        source_directory_identity=prepared.source_identity,
    )
    assert intent is not None
    return database, catalog, artifacts, project, workspace, session, live, prepared, intent, captured


def _resume_after_directory_move(*, tmp_path: Path, catalog, artifacts, project, session, workspace: Path):
    record = catalog.get_session(session.session_id)
    history = catalog.load_history(project_id=project.project_id, session_id=session.session_id)
    restarted = LocalAgentService(
        chat=lambda _alias, _body: (200, b"{}", "application/json"), active_model=lambda: None,
        allowed_roots=(tmp_path,), catalog=catalog, artifacts=artifacts, clock=lambda: T0,
    )
    view = restarted.resume(project_id=project.project_id, session_id=session.session_id,
        command=ResumeAgentSession(expected_catalog_revision=record.revision, expected_history_revision=history.history_revision))
    return restarted, view


def test_recovery_after_filesystem_move_commits_once_on_resume(tmp_path: Path) -> None:
    _database, catalog, artifacts, project, workspace, session, live, prepared, _intent, captured = _prepared_nested_directory_move(tmp_path)
    assert live.tools.apply_prepared_directory_move(prepared).state == "verified"
    _resume_after_directory_move(tmp_path=tmp_path, catalog=catalog, artifacts=artifacts, project=project, session=session, workspace=workspace)
    for old_path, artifact in captured.items():
        recovered = artifacts.get_artifact(project_id=project.project_id, session_id=session.session_id, artifact_id=artifact.artifact_id, workspace=workspace)
        assert (recovered.path, recovered.version_count) == (f"archive/{old_path}", 2)
    # A subsequent resumed service sees the completed receipt and cannot add a third version.
    _resume_after_directory_move(tmp_path=tmp_path, catalog=catalog, artifacts=artifacts, project=project, session=session, workspace=workspace)
    assert all(artifacts.get_artifact(project_id=project.project_id, session_id=session.session_id, artifact_id=item.artifact_id, workspace=workspace).version_count == 2 for item in captured.values())


def test_recovery_cancels_source_intact_pre_effect_intent(tmp_path: Path) -> None:
    _database, catalog, artifacts, project, workspace, session, _live, _prepared, _intent, captured = _prepared_nested_directory_move(tmp_path)
    _resume_after_directory_move(tmp_path=tmp_path, catalog=catalog, artifacts=artifacts, project=project, session=session, workspace=workspace)
    assert (workspace / "docs").is_dir()
    assert artifacts._repository.list_pending_directory_move_intents(project_id=project.project_id, session_id=session.session_id, limit=4) == ()  # noqa: SLF001 - synthetic recovery receipt assertion
    assert all(artifacts.get_artifact(project_id=project.project_id, session_id=session.session_id, artifact_id=item.artifact_id, workspace=workspace).version_count == 1 for item in captured.values())


def test_directory_recovery_refuses_replaced_target_and_child_mismatch_without_partial_heads(tmp_path: Path) -> None:
    _database, _catalog, artifacts, project, workspace, session, live, prepared, intent, captured = _prepared_nested_directory_move(tmp_path)
    assert live.tools.apply_prepared_directory_move(prepared).state == "verified"
    # A same-byte replacement has a different directory identity and must not
    # acquire reviewed-move authority merely because its children hash alike.
    moved = workspace / "archive" / "docs"
    moved.rename(workspace / "elsewhere")
    moved.mkdir()
    for relative in ("a.txt", "nested/b.txt"):
        target = moved / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((workspace / "elsewhere" / relative).read_bytes())
    with pytest.raises(AgentArtifactError) as refused:
        artifacts.complete_reviewed_directory_move(workspace=workspace, intent=intent)
    assert refused.value.code == "agent_artifact_relocation_unverified"
    assert all(artifacts.get_artifact(project_id=project.project_id, session_id=session.session_id, artifact_id=item.artifact_id, workspace=workspace).version_count == 1 for item in captured.values())


def test_directory_child_byte_mismatch_advances_no_partial_head(tmp_path: Path) -> None:
    _database, _catalog, artifacts, project, workspace, session, live, prepared, intent, captured = _prepared_nested_directory_move(tmp_path)
    assert live.tools.apply_prepared_directory_move(prepared).state == "verified"
    (workspace / "archive" / "docs" / "nested" / "b.txt").write_bytes(b"Synthetic changed child.\n")
    with pytest.raises(AgentArtifactError) as refused:
        artifacts.complete_reviewed_directory_move(workspace=workspace, intent=intent)
    assert refused.value.code == "agent_artifact_relocation_unverified"
    assert all(artifacts.get_artifact(project_id=project.project_id, session_id=session.session_id, artifact_id=item.artifact_id, workspace=workspace).version_count == 1 for item in captured.values())


def test_resume_surfaces_persisted_unverified_directory_move_without_advancing_heads(
    tmp_path: Path,
) -> None:
    _database, catalog, artifacts, project, workspace, session, live, prepared, _intent, captured = _prepared_nested_directory_move(tmp_path)
    # The reviewed source disappeared, but no directory with its exact reviewed
    # identity is present at the target. Recovery records only unverified state.
    (workspace / "docs").rename(workspace / "elsewhere")

    first_service, _first = _resume_after_directory_move(
        tmp_path=tmp_path,
        catalog=catalog,
        artifacts=artifacts,
        project=project,
        session=session,
        workspace=workspace,
    )
    notice = "A prior reviewed directory move could not be verified; artifact lineage was not advanced."
    assert [event.text for event in first_service.events(session.session_id).events].count(notice) == 1
    assert all(
        artifacts.get_artifact(
            project_id=project.project_id,
            session_id=session.session_id,
            artifact_id=item.artifact_id,
            workspace=workspace,
        ).version_count
        == 1
        for item in captured.values()
    )

    # The notice is reconstructed from the durable unverified resolution on a
    # later restart; it is not a transient exception or a fabricated version.
    second_service, _second = _resume_after_directory_move(
        tmp_path=tmp_path,
        catalog=catalog,
        artifacts=artifacts,
        project=project,
        session=session,
        workspace=workspace,
    )
    assert [event.text for event in second_service.events(session.session_id).events].count(notice) == 1


def test_concurrent_resume_waits_for_same_session_reconciliation_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _database, catalog, artifacts, project, workspace, session, _live, _prepared, _intent, _captured = _prepared_nested_directory_move(tmp_path)
    record = catalog.get_session(session.session_id)
    history = catalog.load_history(project_id=project.project_id, session_id=session.session_id)
    recovered = LocalAgentService(
        chat=lambda _alias, _body: (200, b"{}", "application/json"),
        active_model=lambda: None,
        allowed_roots=(tmp_path,),
        catalog=catalog,
        artifacts=artifacts,
        clock=lambda: T0,
    )
    entered = threading.Event()
    release = threading.Event()
    calls = 0
    original = artifacts.reconcile_reviewed_directory_moves
    original_admission = recovered._directory_move_admission  # noqa: SLF001 - admission race seam
    second_attempted = threading.Event()

    def blocked_reconcile(**kwargs):
        nonlocal calls
        calls += 1
        entered.set()
        assert release.wait(2)
        return original(**kwargs)

    monkeypatch.setattr(artifacts, "reconcile_reviewed_directory_moves", blocked_reconcile)

    def tracked_admission(target_session_id: str):
        if threading.current_thread().name == "second-resume":
            second_attempted.set()
        return original_admission(target_session_id)

    monkeypatch.setattr(recovered, "_directory_move_admission", tracked_admission)
    command = ResumeAgentSession(
        expected_catalog_revision=record.revision,
        expected_history_revision=history.history_revision,
    )
    outcomes: list[object] = []

    def resume_once() -> None:
        outcomes.append(recovered.resume(
            project_id=project.project_id,
            session_id=session.session_id,
            command=command,
        ))

    first = threading.Thread(target=resume_once, name="first-resume")
    second = threading.Thread(target=resume_once, name="second-resume")
    first.start()
    assert entered.wait(2)
    second.start()
    try:
        assert second_attempted.wait(2)
        # The second resume cannot cancel or independently inspect the pending
        # intent while the first owns recovery admission.
        assert len(outcomes) == 0
    finally:
        release.set()
        first.join(2)
        second.join(2)
    assert not first.is_alive()
    assert not second.is_alive()
    assert calls == 1
    assert len(outcomes) == 2


def test_recovery_admits_bounded_plans_before_any_child_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _database, _catalog, artifacts, project, workspace, session, _live, _prepared, intent, _captured = _prepared_nested_directory_move(tmp_path)
    # Model copies are an isolated repository seam: they simulate two historic
    # plans at the per-plan byte limit without creating oversized fixture files.
    child = intent.children[0].model_copy(
        update={"byte_size": 40 * 1024 * 1024}
    )
    first = intent.model_copy(
        update={"intent_id": "a" * 32, "children": (child,)}
    )
    second = intent.model_copy(
        update={"intent_id": "b" * 32, "children": (child,)}
    )
    resolved: list[str] = []

    class BoundedRepository:
        def count_pending_directory_move_intents(self, **_kwargs) -> int:
            return 2

        def list_pending_directory_move_intents(self, **kwargs):
            assert kwargs["limit"] == 4
            return (first, second)

        def count_unverified_directory_move_intents(self, **_kwargs) -> int:
            return 0

        def resolve_directory_move_intent(self, *, intent, **_kwargs) -> None:
            resolved.append(intent.intent_id)

    def no_child_read(*_args, **_kwargs):
        raise AssertionError("reconciliation exceeded its pre-I/O admission budget")

    monkeypatch.setattr(artifacts, "_repository", BoundedRepository())
    monkeypatch.setattr(artifacts, "_read", no_child_read)
    outcome = artifacts.reconcile_reviewed_directory_moves(
        project_id=project.project_id,
        session_id=session.session_id,
        workspace=workspace,
    )
    assert MAX_DIRECTORY_MOVE_RECONCILIATION_BYTES == 64 * 1024 * 1024
    assert outcome.deferred is True
    assert outcome.cancelled == 1
    assert resolved == ["a" * 32]


def test_resume_reports_mixed_completed_and_deferred_recovery_truthfully(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _database, catalog, artifacts, project, workspace, session, _live, _prepared, _intent, _captured = _prepared_nested_directory_move(tmp_path)
    record = catalog.get_session(session.session_id)
    history = catalog.load_history(project_id=project.project_id, session_id=session.session_id)
    monkeypatch.setattr(
        artifacts,
        "reconcile_reviewed_directory_moves",
        lambda **_kwargs: DirectoryArtifactMoveReconciliation(
            completed=1,
            deferred=True,
        ),
    )
    restarted = LocalAgentService(
        chat=lambda _alias, _body: (200, b"{}", "application/json"),
        active_model=lambda: None,
        allowed_roots=(tmp_path,),
        catalog=catalog,
        artifacts=artifacts,
        clock=lambda: T0,
    )
    restarted.resume(
        project_id=project.project_id,
        session_id=session.session_id,
        command=ResumeAgentSession(
            expected_catalog_revision=record.revision,
            expected_history_revision=history.history_revision,
        ),
    )
    assert [event.text for event in restarted.events(session.session_id).events].count(
        "Some directory-move artifact recovery remains pending within its safe resume budget."
    ) == 1
