"""Bounded direct-service workspace probe for a reviewed staged runtime.

The caller supplies an external task-owned artifact root. Each run retains one
fresh synthetic fixture there and emits only a closed boolean/count receipt.
No browser, listener, model, provider state, credential, or native UI is used.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import sys
import tempfile

from packaged_serve_probe import _environment, _ephemeral_loopback_port, _port_is_released
from prompt_enhancer.application.owned_process import run_owned_process


_CHILD_ERRORS = {
    "bootstrap_failed", "workspace_read_failed", "new_write_failed",
    "existing_write_failed", "move_failed", "stale_review_failed",
    "verification_failed", "cleanup_failed", "unexpected_failure",
}
_COUNT_FIELDS = {
    "workspace_reads", "reviewed_new_writes", "reviewed_existing_writes",
    "reviewed_moves", "stale_reviews_rejected", "temporary_files_remaining",
    "network_attempts",
}

_CODE = r'''
import json, os, sys
from pathlib import Path

report = {
    "contract": "packaged-workspace-child.v1",
    "passed": False,
    "bootstrap_closed": False,
    "workspace_reads": 0,
    "reviewed_new_writes": 0,
    "reviewed_existing_writes": 0,
    "reviewed_moves": 0,
    "stale_reviews_rejected": 0,
    "temporary_files_remaining": 0,
    "network_attempts": 0,
    "python_version": [sys.version_info.major, sys.version_info.minor, sys.version_info.micro],
    "cross_api_ctime_diff_observed": False,
    "birthtime_equal": False,
    "error_code": None,
}
phase = "bootstrap"
bootstrap = None
workspace = Path(sys.argv[1])
birthtime_observations = []

def prohibit_network(event, arguments):
    if event in {"socket.connect", "socket.bind", "socket.getaddrinfo"}:
        report["network_attempts"] += 1
        raise RuntimeError("synthetic_probe_network_denied")

sys.addaudithook(prohibit_network)
try:
    from prompt_enhancer.infrastructure.windows_runtime_bootstrap import bootstrap_current_embedded_windows_runtime
    bootstrap = bootstrap_current_embedded_windows_runtime()
    from prompt_enhancer.application.local_agent_editor import (
        WORKSPACE_APPLY_CONFIRMATION,
        LocalAgentWorkspaceEditor,
        WorkspaceApplyCommand,
        WorkspaceLineEnding,
        WorkspacePreviewCommand,
    )
    from prompt_enhancer.application.local_agent_file_lifecycle import (
        WORKSPACE_CREATE_CONFIRMATION,
        WORKSPACE_MOVE_CONFIRMATION,
        LocalAgentWorkspaceFileLifecycle,
        WorkspaceCreateApplyCommand,
        WorkspaceCreatePreviewCommand,
        WorkspaceMoveApplyCommand,
        WorkspaceMovePreviewCommand,
    )
    from prompt_enhancer.application.local_agent_limits import LocalAgentError
    from prompt_enhancer.application.local_agent_workspace import WorkspaceTools
    from prompt_enhancer.application.local_workspace_io import WorkspaceIO

    session = "0123456789abcdef0123456789abcdef"
    original = b"Synthetic original workspace text.\n"
    replacement = "Synthetic reviewed replacement.\n"
    created_text = "Synthetic reviewed new file.\n"
    external_text = b"Synthetic external revision.\n"

    def observe_cross_api_metadata(path):
        path_metadata = path.lstat()
        with path.open("rb") as stream:
            opened_metadata = os.fstat(stream.fileno())
        report["cross_api_ctime_diff_observed"] = (
            report["cross_api_ctime_diff_observed"]
            or path_metadata.st_ctime_ns != opened_metadata.st_ctime_ns
        )
        birthtime_observations.append(
            hasattr(path_metadata, "st_birthtime_ns")
            and hasattr(opened_metadata, "st_birthtime_ns")
            and path_metadata.st_birthtime_ns == opened_metadata.st_birthtime_ns
        )
        report["birthtime_equal"] = all(birthtime_observations)

    phase = "workspace_read"
    observe_cross_api_metadata(workspace / "existing.txt")
    inspected = WorkspaceIO(workspace).read(workspace / "existing.txt", limit=1024)
    if inspected.payload != original or inspected.truncated:
        raise RuntimeError("synthetic_read_mismatch")
    report["workspace_reads"] += 1
    tools = WorkspaceTools(workspace)
    editor = LocalAgentWorkspaceEditor()
    lifecycle = LocalAgentWorkspaceFileLifecycle()

    phase = "new_write"
    create_preview = lifecycle.preview_create(
        session, tools,
        WorkspaceCreatePreviewCommand(path="created.txt", content=created_text, line_ending=WorkspaceLineEnding.LF),
    )
    created = lifecycle.apply_create(
        session, create_preview.preview_id, tools,
        WorkspaceCreateApplyCommand(
            path=create_preview.path, content=created_text,
            proposed_revision=create_preview.proposed_revision,
            line_ending=create_preview.line_ending,
            confirmation=WORKSPACE_CREATE_CONFIRMATION,
        ),
    )
    if not created.applied:
        raise RuntimeError("synthetic_create_unverified")
    if WorkspaceIO(workspace).read(workspace / "created.txt", limit=1024).payload != created_text.encode():
        raise RuntimeError("synthetic_create_mismatch")
    report["workspace_reads"] += 1
    report["reviewed_new_writes"] = 1

    phase = "existing_write"
    current = editor.read(session, tools, "existing.txt")
    edit_preview = editor.preview(
        session, tools,
        WorkspacePreviewCommand(
            path=current.path, content=replacement, expected_revision=current.revision,
            line_ending=current.line_ending,
        ),
    )
    edited = editor.apply(
        session, edit_preview.preview_id, tools,
        WorkspaceApplyCommand(
            path=edit_preview.path, content=replacement,
            expected_revision=edit_preview.expected_revision,
            proposed_revision=edit_preview.proposed_revision,
            line_ending=edit_preview.line_ending,
            confirmation=WORKSPACE_APPLY_CONFIRMATION,
        ),
    )
    if not edited.applied:
        raise RuntimeError("synthetic_edit_unverified")
    if WorkspaceIO(workspace).read(workspace / "existing.txt", limit=1024).payload != replacement.encode():
        raise RuntimeError("synthetic_edit_mismatch")
    observe_cross_api_metadata(workspace / "existing.txt")
    report["workspace_reads"] += 1
    report["reviewed_existing_writes"] = 1

    phase = "move"
    source = tools.read_text_snapshot("created.txt")
    move_preview = lifecycle.preview_move(
        session, tools,
        WorkspaceMovePreviewCommand(
            source_path="created.txt", target_path="archive/moved.txt",
            expected_revision=source.revision,
        ),
    )
    moved = lifecycle.apply_move(
        session, move_preview.preview_id, tools,
        WorkspaceMoveApplyCommand(
            source_path=move_preview.source_path, target_path=move_preview.target_path,
            expected_revision=move_preview.expected_revision,
            confirmation=WORKSPACE_MOVE_CONFIRMATION,
        ),
    )
    if not moved.applied or (workspace / "created.txt").exists():
        raise RuntimeError("synthetic_move_unverified")
    if WorkspaceIO(workspace).read(workspace / "archive" / "moved.txt", limit=1024).payload != created_text.encode():
        raise RuntimeError("synthetic_move_mismatch")
    report["workspace_reads"] += 1
    report["reviewed_moves"] = 1

    phase = "stale_review"
    stale_current = editor.read(session, tools, "existing.txt")
    stale_content = "Synthetic stale reviewed proposal.\n"
    stale_preview = editor.preview(
        session, tools,
        WorkspacePreviewCommand(
            path=stale_current.path, content=stale_content,
            expected_revision=stale_current.revision, line_ending=stale_current.line_ending,
        ),
    )
    (workspace / "existing.txt").write_bytes(external_text)
    try:
        editor.apply(
            session, stale_preview.preview_id, tools,
            WorkspaceApplyCommand(
                path=stale_preview.path, content=stale_content,
                expected_revision=stale_preview.expected_revision,
                proposed_revision=stale_preview.proposed_revision,
                line_ending=stale_preview.line_ending,
                confirmation=WORKSPACE_APPLY_CONFIRMATION,
            ),
        )
    except LocalAgentError as error:
        if str(error) != "workspace_revision_changed":
            raise RuntimeError("synthetic_stale_wrong_rejection") from error
    else:
        raise RuntimeError("synthetic_stale_accepted")
    if WorkspaceIO(workspace).read(workspace / "existing.txt", limit=1024).payload != external_text:
        raise RuntimeError("synthetic_stale_changed")
    observe_cross_api_metadata(workspace / "existing.txt")
    report["workspace_reads"] += 1
    report["stale_reviews_rejected"] = 1

    phase = "verification"
except Exception:
    report["error_code"] = {
        "bootstrap": "bootstrap_failed",
        "workspace_read": "workspace_read_failed",
        "new_write": "new_write_failed",
        "existing_write": "existing_write_failed",
        "move": "move_failed",
        "stale_review": "stale_review_failed",
        "verification": "verification_failed",
    }.get(phase, "unexpected_failure")
finally:
    if bootstrap is not None:
        try:
            bootstrap.close()
            report["bootstrap_closed"] = True
        except Exception:
            report["error_code"] = report["error_code"] or "cleanup_failed"
    try:
        report["temporary_files_remaining"] = min(
            1001, sum(1 for _ in workspace.rglob(".prompt-enhancer-*.tmp"))
        )
    except Exception:
        report["error_code"] = report["error_code"] or "cleanup_failed"
        report["temporary_files_remaining"] = 1001

report["passed"] = (
    report["error_code"] is None
    and report["bootstrap_closed"]
    and report["workspace_reads"] == 5
    and report["reviewed_new_writes"] == 1
    and report["reviewed_existing_writes"] == 1
    and report["reviewed_moves"] == 1
    and report["stale_reviews_rejected"] == 1
    and report["temporary_files_remaining"] == 0
    and report["network_attempts"] == 0
    and report["python_version"][:2] == [3, 13]
    and report["birthtime_equal"]
)
print("PACKAGED_WORKSPACE_CHILD=" + json.dumps(report, sort_keys=True, separators=(",", ":")))
'''


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_field")
        result[key] = value
    return result


def _child_receipt(output: bytes | bytearray) -> dict[str, object] | None:
    prefix = b"PACKAGED_WORKSPACE_CHILD="
    raw = bytes(output).strip()
    if not raw.startswith(prefix) or b"\n" in raw or b"\r" in raw:
        return None
    try:
        receipt = json.loads(raw[len(prefix):], object_pairs_hook=_unique_pairs)
    except (ValueError, UnicodeError):
        return None
    if not isinstance(receipt, dict) or set(receipt) != (
        _COUNT_FIELDS | {
            "contract", "passed", "bootstrap_closed", "error_code", "python_version",
            "cross_api_ctime_diff_observed", "birthtime_equal",
        }
    ):
        return None
    if receipt["contract"] != "packaged-workspace-child.v1":
        return None
    if any(type(receipt[key]) is not bool for key in (
        "passed", "bootstrap_closed", "cross_api_ctime_diff_observed", "birthtime_equal",
    )):
        return None
    version = receipt["python_version"]
    if (
        not isinstance(version, list) or len(version) != 3
        or any(type(value) is not int or not 0 <= value <= 1000 for value in version)
    ):
        return None
    if any(type(receipt[key]) is not int or not 0 <= receipt[key] <= 1000 for key in _COUNT_FIELDS):
        return None
    error = receipt["error_code"]
    if error is not None and (not isinstance(error, str) or error not in _CHILD_ERRORS):
        return None
    return receipt


def _child_passed(receipt: dict[str, object]) -> bool:
    return (
        receipt["passed"] is True
        and receipt["bootstrap_closed"] is True
        and receipt["error_code"] is None
        and receipt["workspace_reads"] == 5
        and receipt["reviewed_new_writes"] == 1
        and receipt["reviewed_existing_writes"] == 1
        and receipt["reviewed_moves"] == 1
        and receipt["stale_reviews_rejected"] == 1
        and receipt["temporary_files_remaining"] == 0
        and receipt["network_attempts"] == 0
        and receipt["python_version"][:2] == [3, 13]
        and receipt["birthtime_equal"] is True
    )


def _safe_artifact_root(candidate: Path) -> Path | None:
    try:
        if not candidate.is_absolute():
            return None
        lexical = Path(os.path.abspath(os.fspath(candidate)))
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        for component in (lexical, *lexical.parents):
            metadata = component.lstat()
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or bool(getattr(metadata, "st_file_attributes", 0) & reparse)
            ):
                return None
        resolved = lexical.resolve(strict=True)
        repository = Path(__file__).resolve().parents[2]
        home = Path.home().resolve(strict=True)
        if (
            resolved == Path(resolved.anchor)
            or resolved == home or resolved.is_relative_to(home) or home.is_relative_to(resolved)
            or resolved == repository or resolved.is_relative_to(repository)
            or repository.is_relative_to(resolved)
        ):
            return None
        return resolved
    except OSError:
        return None


def probe(runtime: Path, artifact_root: Path) -> dict[str, object]:
    report: dict[str, object] = {
        "contract": "packaged-workspace-probe.v1", "passed": False,
        "child_exit_ok": False, "child_receipt_ok": False,
        "owned_cleanup_confirmed": False, "port_released": False,
        "fixture_retained": False, "stdout_bytes": 0, "stderr_bytes": 0,
        "workspace_reads": 0, "reviewed_new_writes": 0,
        "reviewed_existing_writes": 0, "reviewed_moves": 0,
        "stale_reviews_rejected": 0, "temporary_files_remaining": 0,
        "network_attempts": 0, "child_error_code": None, "error_code": None,
        "python_version": [0, 0, 0], "cross_api_ctime_diff_observed": False,
        "birthtime_equal": False,
    }
    executable = runtime / "python.exe"
    retained_root = _safe_artifact_root(artifact_root)
    if sys.platform != "win32" or not runtime.is_absolute() or not executable.is_file():
        report["error_code"] = "runtime_unavailable"
        return report
    if retained_root is None:
        report["error_code"] = "artifact_root_unsafe"
        return report
    port = _ephemeral_loopback_port()
    fixture: Path | None = None
    try:
        fixture = Path(tempfile.mkdtemp(prefix="packaged-workspace-", dir=retained_root))
        (fixture / "temp").mkdir()
        (fixture / "empty-profile").mkdir()
        workspace = fixture / "workspace"
        workspace.mkdir()
        (workspace / "archive").mkdir()
        (workspace / "existing.txt").write_bytes(b"Synthetic original workspace text.\n")
        result = run_owned_process(
            (os.fspath(executable), "-I", "-B", "-c", _CODE, os.fspath(workspace)),
            cwd=fixture, env=_environment(runtime, fixture, port), timeout=30,
            stdout_limit=16 * 1024, stderr_limit=16 * 1024,
            maximum_active_processes=1,
        )
        report["owned_cleanup_confirmed"] = True
        report["child_exit_ok"] = result.returncode == 0
        report["stdout_bytes"] = len(result.stdout)
        report["stderr_bytes"] = len(result.stderr)
        receipt = _child_receipt(result.stdout) if not result.stderr else None
        if receipt is None:
            report["error_code"] = "invalid_child_receipt"
        else:
            report["child_receipt_ok"] = True
            for key in _COUNT_FIELDS:
                report[key] = receipt[key]
            report["child_error_code"] = receipt["error_code"]
            report["python_version"] = receipt["python_version"]
            report["cross_api_ctime_diff_observed"] = receipt["cross_api_ctime_diff_observed"]
            report["birthtime_equal"] = receipt["birthtime_equal"]
            if not report["child_exit_ok"] or not _child_passed(receipt):
                report["error_code"] = "child_workflow_failed"
    except Exception:
        report["error_code"] = "workspace_probe_failed"
    finally:
        report["fixture_retained"] = fixture is not None and fixture.is_dir()
        report["port_released"] = _port_is_released(port)
        if not report["owned_cleanup_confirmed"] or not report["port_released"]:
            report["error_code"] = report["error_code"] or "cleanup_unconfirmed"
    report["passed"] = (
        report["error_code"] is None and report["child_exit_ok"]
        and report["child_receipt_ok"] and report["owned_cleanup_confirmed"]
        and report["port_released"] and report["fixture_retained"]
        and report["stderr_bytes"] == 0
    )
    return report


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 3 or arguments[1] != "--artifact-root":
        report = {"contract": "packaged-workspace-probe.v1", "passed": False, "error_code": "invalid_arguments"}
    else:
        report = probe(Path(arguments[0]), Path(arguments[2]))
    print("PACKAGED_WORKSPACE_PROBE=" + json.dumps(report, sort_keys=True, separators=(",", ":")), flush=True)
    return 0 if report.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
