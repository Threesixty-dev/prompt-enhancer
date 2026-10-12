from __future__ import annotations

import pytest

from scripts.privacy_scan import scan_repository


def test_root_git_symlink_is_not_exempted_as_worktree_metadata(tmp_path):
    target = tmp_path / "example.txt"
    target.write_text("fictional example")
    try:
        (tmp_path / ".git").symlink_to(target)
    except OSError as exc:
        pytest.skip(f"file symlinks are unavailable: {exc.__class__.__name__}")
    assert any(finding.path == ".git" and finding.kind == "prohibited repository symlink"
               for finding in scan_repository(tmp_path))


def test_scanner_rejects_symlink_without_reading_target(tmp_path) -> None:
    target = tmp_path / "synthetic-target.txt"
    target.write_text("synthetic placeholder", encoding="utf-8")
    link = tmp_path / "synthetic-link.txt"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"file symlinks are unavailable: {exc.__class__.__name__}")

    findings = {
        (finding.path, finding.kind) for finding in scan_repository(tmp_path)
    }

    assert ("synthetic-link.txt", "prohibited repository symlink") in findings
