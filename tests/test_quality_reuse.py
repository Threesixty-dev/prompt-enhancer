"""Synthetic CI metadata only: no network, credentials or real job logs."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import re
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("quality_reuse", ROOT / "scripts/require_quality_run.py")
quality = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quality)

ENV = {"GITHUB_REPOSITORY": "example-org/example-repo", "GITHUB_REF": "refs/heads/main",
       "GITHUB_SHA": "a" * 40}


def run(**changes):
    return {"id": 42, "head_sha": ENV["GITHUB_SHA"], "head_branch": "main", "event": "push",
            "path": ".github/workflows/quality-gate.yml", "run_attempt": 1,
            "repository": {"full_name": ENV["GITHUB_REPOSITORY"]},
            "head_repository": {"full_name": ENV["GITHUB_REPOSITORY"]},
            "status": "completed", "conclusion": "success", **changes}


def jobs(**changes):
    return [{"name": name, "run_id": 42, "run_attempt": 1, "head_sha": ENV["GITHUB_SHA"],
             "status": "completed", "conclusion": "success", **changes}
            for name in sorted(quality.REQUIRED_JOBS)]


class API:
    def __init__(self, snapshots=None, job_rows=None):
        self.snapshots = snapshots if snapshots is not None else [[run()]]
        self.job_rows = job_rows if job_rows is not None else jobs()
        self.calls = []

    def __call__(self, endpoint):
        self.calls.append(endpoint)
        assert endpoint.startswith("repos/example-org/example-repo/actions/")
        if "/workflows/quality-gate.yml/runs?" in endpoint:
            assert "event=push" in endpoint and "branch=main" in endpoint
            assert "head_sha=" + ENV["GITHUB_SHA"] in endpoint
            assert "status=" not in endpoint  # Never choose only successful older runs.
            snapshot = self.snapshots[0]
            if len(self.snapshots) > 1:
                self.snapshots.pop(0)
            return {"total_count": len(snapshot), "workflow_runs": deepcopy(snapshot)}
        assert "/runs/42/jobs?filter=all" in endpoint
        return {"total_count": len(self.job_rows), "jobs": deepcopy(self.job_rows)}


class Clock:
    def __init__(self):
        self.now = 0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, duration):
        self.now += duration
        self.sleeps.append(duration)


def verify(api, timeout=60):
    clock = Clock()
    quality.require_quality(ENV, api=api, sleep=clock.sleep, clock=clock, timeout=timeout)
    return clock


def test_success_reuses_six_jobs_without_starting_tests_or_workflows(capsys):
    api = API()
    assert verify(api).sleeps == []
    assert len(api.calls) == 3
    assert capsys.readouterr().out == "Reused successful Quality gate evidence for the exact main commit.\n"


@pytest.mark.parametrize("status", sorted(quality.PENDING))
def test_existing_incomplete_run_is_waited_for(status):
    api = API([[run(status=status, conclusion=None)], [run()]])
    assert verify(api).sleeps == [20]


def test_pending_run_wait_is_bounded_and_does_not_read_job_evidence():
    api = API([[run(status="in_progress", conclusion=None)]])
    clock = Clock()
    with pytest.raises(quality.QualityError, match="Timed out"):
        quality.require_quality(ENV, api=api, sleep=clock.sleep, clock=clock, timeout=25)
    assert clock.sleeps == [20, 5]
    assert all("/jobs?" not in call for call in api.calls)


@pytest.mark.parametrize("changes", [
    {"head_sha": "b" * 40}, {"head_branch": "develop"}, {"event": "pull_request"},
    {"path": ".github/workflows/publish-coolify.yml"},
    {"repository": {"full_name": "example-org/another-repo"}},
    {"head_repository": {"full_name": "example-fork/example-repo"}},
    {"head_repository": None}, {"repository": None}, {"run_attempt": 0}, {"id": "42"},
])
def test_wrong_or_incomplete_provenance_blocks_deployment(changes):
    with pytest.raises(quality.QualityError, match="does not match"):
        verify(API([[run(**changes)]]))


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "timed_out", "skipped", "neutral", None])
def test_newer_unsuccessful_run_cannot_be_hidden_by_older_success(conclusion):
    with pytest.raises(quality.QualityError, match="did not pass"):
        verify(API([[run(), run(id=43, conclusion=conclusion)]]))


def test_missing_run_blocks_deployment():
    with pytest.raises(quality.QualityError, match="No main-push"):
        verify(API([[]]))


def test_unknown_state_blocks_deployment():
    with pytest.raises(quality.QualityError, match="unsupported state"):
        verify(API([[run(status="example-unknown")]]))


@pytest.mark.parametrize("changes", [{"conclusion": "skipped"}, {"conclusion": "failure"},
                                     {"conclusion": "cancelled"}, {"status": "in_progress"}])
def test_overall_success_does_not_hide_unsuccessful_required_job(changes):
    rows = jobs()
    rows[0].update(changes)
    with pytest.raises(quality.QualityError, match="Every required"):
        verify(API(job_rows=rows))


def test_missing_required_job_blocks_deployment():
    with pytest.raises(quality.QualityError, match="Every required"):
        verify(API(job_rows=jobs()[1:]))


@pytest.mark.parametrize("changes", [{"head_sha": "b" * 40}, {"run_id": 43},
                                     {"run_attempt": 0}, {"run_attempt": 2}])
def test_wrong_job_evidence_blocks_deployment(changes):
    with pytest.raises(quality.QualityError, match="does not match"):
        verify(API(job_rows=jobs(**changes)))


def test_failed_job_only_rerun_reuses_unchanged_successes():
    rows = jobs()
    corrected = {**rows[0], "run_attempt": 2}
    rows[0]["conclusion"] = "failure"
    verify(API([[run(run_attempt=2)]], rows + [corrected]))


def test_skipped_latest_attempt_cannot_reuse_old_job_success():
    rows = jobs()
    with pytest.raises(quality.QualityError, match="Every required"):
        verify(API([[run(run_attempt=2)]], rows + [{**rows[0], "run_attempt": 2, "conclusion": "skipped"}]))


def test_duplicate_job_attempt_is_not_accepted():
    rows = jobs()
    with pytest.raises(quality.QualityError, match="ambiguous"):
        verify(API(job_rows=rows + [rows[0]]))


def test_rerun_started_during_job_read_is_rechecked():
    api = API([[run()], [run(status="in_progress", conclusion=None, run_attempt=2)],
               [run(run_attempt=2, conclusion="failure")]])
    with pytest.raises(quality.QualityError, match="did not pass"):
        verify(api)


def test_complete_pagination_and_truncation_detection():
    pages = iter([{"total_count": 2, "jobs": [{"id": 1}]},
                  {"total_count": 2, "jobs": [{"id": 2}]}])
    assert quality.records(lambda _: next(pages), "example?filter=all", "jobs") == [{"id": 1}, {"id": 2}]
    pages = iter([{"total_count": 2, "jobs": [{"id": 1}]}, {"total_count": 2, "jobs": []}])
    with pytest.raises(quality.QualityError, match="incomplete"):
        quality.records(lambda _: next(pages), "example?filter=all", "jobs")


@pytest.mark.parametrize("payload", [None, [], {}, {"total_count": "0", "jobs": []},
                                    {"total_count": 1, "jobs": [None]}])
def test_malformed_api_evidence_is_rejected(payload):
    with pytest.raises(quality.QualityError, match="incomplete"):
        quality.records(lambda _: payload, "example?filter=all", "jobs")


@pytest.mark.parametrize("changes", [{"GITHUB_REF": "refs/heads/develop"}, {"GITHUB_SHA": "main"},
                                     {"GITHUB_REPOSITORY": "../example-repo"}])
def test_invalid_release_context_never_calls_api(changes):
    def forbidden(_):
        pytest.fail("invalid context reached GitHub")
    with pytest.raises(quality.QualityError, match="requires"):
        quality.require_quality({**ENV, **changes}, api=forbidden)


def test_api_client_only_reads_and_does_not_echo_errors(monkeypatch):
    def command(args, **kwargs):
        assert args[:7] == ["gh", "api", "--hostname", "github.com", "--method", "GET", "-H"]
        assert kwargs == {"check": True, "capture_output": True, "text": True, "timeout": 30}
        raise subprocess.CalledProcessError(1, args, output="example-invalid-secret", stderr="example-private-body")
    monkeypatch.setattr(quality.subprocess, "run", command)
    with pytest.raises(quality.QualityError) as error:
        quality.github_api("repos/example-org/example-repo/actions/runs")
    assert str(error.value) == "Cannot read quality evidence from GitHub Actions."


def test_main_reports_only_content_free_failure(monkeypatch, capsys):
    def failed(_):
        raise quality.QualityError("Example fixed failure.")
    monkeypatch.setattr(quality, "require_quality", failed)
    assert quality.main() == 1
    assert capsys.readouterr().err == "Example fixed failure.\n"


def test_workflow_scheduling_keeps_quality_and_manual_release_boundaries():
    gate = (ROOT / ".github/workflows/quality-gate.yml").read_text()
    triggers = gate.split("on:\n", 1)[1].split("\npermissions:", 1)[0]
    assert re.search(r"^  pull_request:\s*$", triggers, re.M)
    assert re.search(r"^  push:\n    branches: \[main\]$", triggers, re.M)
    assert "workflow_call" not in gate
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in gate
    deploy = (ROOT / ".github/workflows/publish-coolify.yml").read_text()
    assert "workflow_dispatch:" in deploy
    assert not re.search(r"^  (push|pull_request|workflow_run):", deploy, re.M)
    assert "uses: ./.github/workflows/quality-gate.yml" not in deploy
    assert "actions: read" in deploy and "python3 scripts/require_quality_run.py" in deploy
    assert "  container:\n    needs: quality" in deploy
    assert "  deploy:\n    needs: container" in deploy
