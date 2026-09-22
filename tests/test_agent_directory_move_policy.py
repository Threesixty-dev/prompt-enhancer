"""Synthetic policy regressions for reviewed directory artifact moves."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import os
from pathlib import Path

import pytest

from prompt_enhancer.application.agent_artifacts import (
    AgentArtifactError,
    AgentArtifactService,
    CaptureAgentArtifact,
    RemoveAgentArtifact,
    UpdateAgentArtifact,
)
from prompt_enhancer.application.agent_catalog import (
    AgentCatalogService,
    AgentRetentionPolicy,
    CreateAgentProject,
)
from prompt_enhancer.application.local_agent import AgentSettings, LocalAgentService
from prompt_enhancer.application.local_agent_file_lifecycle import (
    WORKSPACE_DIRECTORY_MOVE_CONFIRMATION,
    WorkspaceDirectoryMoveApplyCommand,
    WorkspaceDirectoryMovePreviewCommand,
)
from prompt_enhancer.infrastructure.sqlite.agent_artifacts import SqliteAgentArtifactRepository
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
    project = catalog.create_project(CreateAgentProject(name="Synthetic move policy"))
    workspace = tmp_path / "example-workspace"
    workspace.mkdir()
    artifacts = AgentArtifactService(
        SqliteAgentArtifactRepository(database),
        catalog,
        clock=lambda: T0,
        id_factory=_ids(100).__next__,
    )
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
            title="Synthetic move policy chat",
            retention_policy=AgentRetentionPolicy.LOCAL_HISTORY,
        )
    )
    return artifacts, project, workspace, agent, session


def _capture(artifacts, project, session, workspace: Path, relative: str, payload: bytes):
    path = workspace / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return artifacts.capture(
        project_id=project.project_id,
        session_id=session.session_id,
        workspace=workspace,
        command=CaptureAgentArtifact(
            path=relative,
            expected_sha256=hashlib.sha256(payload).hexdigest(),
            expected_byte_size=len(payload),
        ),
    )


def _move(agent, session, source: str = "docs", target: str = "archive/docs"):
    preview = agent.preview_workspace_directory_move(
        session.session_id,
        WorkspaceDirectoryMovePreviewCommand(source_path=source, target_path=target),
    )
    return agent.apply_workspace_directory_move(
        session.session_id,
        preview.preview_id,
        WorkspaceDirectoryMoveApplyCommand(
            source_path=preview.source_path,
            target_path=preview.target_path,
            confirmation=WORKSPACE_DIRECTORY_MOVE_CONFIRMATION,
        ),
    )


def test_archived_nested_artifact_is_preserved_and_relocated(tmp_path: Path) -> None:
    artifacts, project, workspace, agent, session = _fixture(tmp_path)
    captured = _capture(artifacts, project, session, workspace, "docs/guides/archived.md", b"archived\n")
    archived = artifacts.update_artifact(
        project_id=project.project_id,
        session_id=session.session_id,
        artifact_id=captured.artifact_id,
        command=UpdateAgentArtifact(expected_revision=captured.revision, operation="archive"),
    )
    (workspace / "archive").mkdir()

    moved = _move(agent, session)

    assert moved.artifact_projection == "complete"
    assert moved.artifact_versions_advanced == 1
    relocated = artifacts.get_artifact(
        project_id=project.project_id,
        session_id=session.session_id,
        artifact_id=archived.artifact_id,
        workspace=workspace,
    )
    assert relocated.lifecycle_state == "archived"
    assert relocated.path == "archive/docs/guides/archived.md"
    assert relocated.version_count == 2
    assert [version.path for version in relocated.versions] == [
        "docs/guides/archived.md",
        "archive/docs/guides/archived.md",
    ]


def test_removed_nested_artifact_is_excluded_from_relocation(tmp_path: Path) -> None:
    artifacts, project, workspace, agent, session = _fixture(tmp_path)
    captured = _capture(artifacts, project, session, workspace, "docs/removed.txt", b"removed\n")
    archived = artifacts.update_artifact(
        project_id=project.project_id,
        session_id=session.session_id,
        artifact_id=captured.artifact_id,
        command=UpdateAgentArtifact(expected_revision=captured.revision, operation="archive"),
    )
    artifacts.remove_artifact(
        project_id=project.project_id,
        session_id=session.session_id,
        artifact_id=captured.artifact_id,
        command=RemoveAgentArtifact(
            expected_revision=archived.revision,
            confirmation="move_archived_artifact_record_to_removed",
        ),
    )
    (workspace / "archive").mkdir()

    moved = _move(agent, session)

    assert moved.artifact_projection == "not_applicable"
    assert moved.artifact_versions_advanced == 0
    listed = artifacts.list_artifacts(
        project_id=project.project_id,
        session_id=session.session_id,
        view="all",
    )
    assert len(listed.artifacts) == 1
    assert listed.artifacts[0].lifecycle_state == "removed"
    assert listed.artifacts[0].path == "docs/removed.txt"
    assert listed.artifacts[0].version_count == 1


def test_directory_policy_uses_exact_segments_not_prefixes(tmp_path: Path) -> None:
    artifacts, project, workspace, agent, session = _fixture(tmp_path)
    captured = _capture(artifacts, project, session, workspace, "docs-other/keep.txt", b"keep\n")
    (workspace / "docs").mkdir()
    (workspace / "archive").mkdir()

    moved = _move(agent, session)

    assert moved.artifact_projection == "not_applicable"
    assert moved.artifact_versions_advanced == 0
    unchanged = artifacts.get_artifact(
        project_id=project.project_id,
        session_id=session.session_id,
        artifact_id=captured.artifact_id,
        workspace=workspace,
    )
    assert unchanged.path == "docs-other/keep.txt"
    assert unchanged.version_count == 1
    assert (workspace / "archive" / "docs").is_dir()
    assert (workspace / "docs-other" / "keep.txt").read_bytes() == b"keep\n"


def test_directory_intent_rejects_wrong_session_replay(tmp_path: Path) -> None:
    artifacts, project, workspace, agent, session = _fixture(tmp_path)
    captured = _capture(artifacts, project, session, workspace, "docs/replay.txt", b"replay\n")
    (workspace / "archive").mkdir()
    source_identity = os.stat(workspace / "docs", follow_symlinks=False)
    intent = artifacts.prepare_reviewed_directory_move(
        project_id=project.project_id,
        session_id=session.session_id,
        workspace=workspace,
        source_path="docs",
        target_path="archive/docs",
        source_directory_identity=(int(source_identity.st_dev), int(source_identity.st_ino)),
    )
    assert intent is not None
    (workspace / "docs").rename(workspace / "archive" / "docs")
    foreign = intent.model_copy(update={"session_id": "b" * 32})

    with pytest.raises(AgentArtifactError) as refused:
        artifacts.complete_reviewed_directory_move(workspace=workspace, intent=foreign)

    assert refused.value.code == "agent_catalog_session_not_found"
    unchanged = artifacts.get_artifact(
        project_id=project.project_id,
        session_id=session.session_id,
        artifact_id=captured.artifact_id,
        workspace=workspace,
    )
    assert unchanged.path == "docs/replay.txt"
    assert unchanged.version_count == 1


def test_second_child_stale_cas_leaves_all_heads_unchanged(tmp_path: Path) -> None:
    artifacts, project, workspace, agent, session = _fixture(tmp_path)
    first = _capture(artifacts, project, session, workspace, "docs/first.txt", b"first\n")
    second = _capture(artifacts, project, session, workspace, "docs/second.txt", b"second\n")
    (workspace / "archive").mkdir()
    source_identity = os.stat(workspace / "docs", follow_symlinks=False)
    intent = artifacts.prepare_reviewed_directory_move(
        project_id=project.project_id,
        session_id=session.session_id,
        workspace=workspace,
        source_path="docs",
        target_path="archive/docs",
        source_directory_identity=(int(source_identity.st_dev), int(source_identity.st_ino)),
    )
    assert intent is not None
    artifacts.update_artifact(
        project_id=project.project_id,
        session_id=session.session_id,
        artifact_id=second.artifact_id,
        command=UpdateAgentArtifact(
            expected_revision=second.revision,
            operation="rename",
            title="Renamed synthetic second child",
        ),
    )
    (workspace / "docs").rename(workspace / "archive" / "docs")

    with pytest.raises(AgentArtifactError) as refused:
        artifacts.complete_reviewed_directory_move(workspace=workspace, intent=intent)

    assert refused.value.code == "agent_artifact_relocation_conflict"
    first_after = artifacts.get_artifact(
        project_id=project.project_id,
        session_id=session.session_id,
        artifact_id=first.artifact_id,
        workspace=workspace,
    )
    second_after = artifacts.get_artifact(
        project_id=project.project_id,
        session_id=session.session_id,
        artifact_id=second.artifact_id,
        workspace=workspace,
    )
    assert (first_after.path, first_after.version_count) == ("docs/first.txt", 1)
    assert (second_after.path, second_after.version_count) == ("docs/second.txt", 1)
    assert second_after.title == "Renamed synthetic second child"
