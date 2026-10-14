"""Reuse successful main-push CI without starting or rerunning any workflow."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from urllib.parse import urlencode

WORKFLOW = ".github/workflows/quality-gate.yml"
REQUIRED_JOBS = frozenset({
    "Repository integrity",
    "Quality result",
})
PENDING = {"queued", "in_progress", "waiting", "pending", "requested"}


class QualityError(Exception):
    """A fixed, content-free diagnostic safe for Actions logs."""


def github_api(endpoint):
    try:
        result = subprocess.run(
            ["gh", "api", "--hostname", "github.com", "--method", "GET",
             "-H", "Accept: application/vnd.github+json",
             "-H", "X-GitHub-Api-Version: 2026-03-10", endpoint],
            check=True, capture_output=True, text=True, timeout=30,
        )
        return json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        raise QualityError("Cannot read quality evidence from GitHub Actions.") from None


def records(api, endpoint, key):
    """Read complete result pages; never silently accept truncated evidence."""
    rows = []
    for page in range(1, 21):
        payload = api(f"{endpoint}&per_page=100&page={page}")
        if (not isinstance(payload, dict)
                or not isinstance(payload.get(key), list)
                or type(payload.get("total_count")) is not int):
            raise QualityError("GitHub returned incomplete quality evidence.")
        batch = payload[key]
        if any(not isinstance(row, dict) for row in batch):
            raise QualityError("GitHub returned incomplete quality evidence.")
        rows.extend(batch)
        if len(rows) == payload["total_count"]:
            return rows
        if not batch or len(rows) > payload["total_count"]:
            break
    raise QualityError("GitHub returned incomplete quality evidence.")


def latest_run(api, repository, revision):
    query = urlencode({"branch": "main", "event": "push", "head_sha": revision})
    runs = records(api, f"repos/{repository}/actions/workflows/quality-gate.yml/runs?{query}",
                   "workflow_runs")
    if not runs:
        raise QualityError("No main-push Quality gate run exists for this commit. "
                           "Wait for main CI to appear before deploying.")
    for run in runs:
        if (run.get("head_sha") != revision or run.get("head_branch") != "main"
                or run.get("event") != "push"
                or run.get("path") not in {WORKFLOW, WORKFLOW + "@main", WORKFLOW + "@refs/heads/main"}
                or not isinstance(run.get("repository"), dict)
                or run["repository"].get("full_name") != repository
                or not isinstance(run.get("head_repository"), dict)
                or run["head_repository"].get("full_name") != repository
                or type(run.get("id")) is not int or run["id"] < 1
                or type(run.get("run_attempt")) is not int or run["run_attempt"] < 1):
            raise QualityError("Quality evidence does not match this main commit and repository.")
    # Do not filter by success: a newer failure must supersede an older success.
    return max(runs, key=lambda run: run["id"])


def require_jobs(api, repository, revision, run):
    jobs = records(api, f"repos/{repository}/actions/runs/{run['id']}/jobs?filter=all", "jobs")
    latest = {}
    for job in jobs:
        name = job.get("name")
        if not isinstance(name, str) or name not in REQUIRED_JOBS:
            continue
        attempt = job.get("run_attempt")
        if (job.get("run_id") != run["id"] or job.get("head_sha") != revision
                or type(attempt) is not int or not 1 <= attempt <= run["run_attempt"]):
            raise QualityError("Required job evidence does not match the validated run.")
        previous = latest.get(name)
        if previous is not None and previous["run_attempt"] == attempt:
            raise QualityError("Required job evidence is ambiguous.")
        if previous is None or previous["run_attempt"] < attempt:
            latest[name] = job
    # A failed-job-only rerun legitimately retains successful earlier jobs.
    if (set(latest) != REQUIRED_JOBS
            or any(job.get("status") != "completed" or job.get("conclusion") != "success"
                   for job in latest.values())):
        raise QualityError("Every required quality job must have successful evidence; "
                           "missing, skipped or unsuccessful jobs block deployment.")


def require_quality(env, *, api=github_api, sleep=time.sleep, clock=time.monotonic,
                    timeout=3900):
    repository = env.get("GITHUB_REPOSITORY", "")
    revision = env.get("GITHUB_SHA", "")
    if (env.get("GITHUB_REF") != "refs/heads/main"
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", repository)
            or not re.fullmatch(r"[0-9a-f]{40}", revision)):
        raise QualityError("Quality reuse requires a repository and exact main commit.")
    deadline = clock() + timeout
    announced = False
    while True:
        run = latest_run(api, repository, revision)
        if run.get("status") == "completed":
            if run.get("conclusion") != "success":
                raise QualityError("The latest Quality gate run for this main commit did not pass. "
                                   "Resolve its checks before deploying.")
            require_jobs(api, repository, revision, run)
            # Recheck after fetching jobs in case a rerun started in the meantime.
            confirmed = latest_run(api, repository, revision)
            if (confirmed["id"] == run["id"] and confirmed["run_attempt"] == run["run_attempt"]
                    and confirmed.get("status") == "completed"
                    and confirmed.get("conclusion") == "success"):
                print("Reused successful Quality gate evidence for the exact main commit.", flush=True)
                return
        elif run.get("status") not in PENDING:
            raise QualityError("Quality gate has an unsupported state; deployment is blocked.")
        if clock() >= deadline:
            raise QualityError("Timed out waiting for existing main quality checks; no deployment started.")
        if not announced:
            print("Waiting for existing main quality checks; no tests are being restarted.", flush=True)
            announced = True
        sleep(min(20, max(0, deadline - clock())))


def main():
    try:
        require_quality(os.environ)
    except QualityError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
