# CI quality gate

The owner-approved development policy keeps quick integrity checks automatic and
makes full regression suites available on demand. The workflow has read-only
repository permission, does not receive repository secrets, and does not upload test or runtime
artifacts. Tests remain subject to the suite-wide non-loopback socket guard.

## Scheduling and deployment reuse

A pull-request update and each `main` push run privacy scanning, architecture
consistency and patch-whitespace checks. PR metadata validation remains automatic.
The pinned `dorny/paths-filter` Action uses `.github/validation-paths.yml` only to
select focused CI-policy tests when CI configuration or the evidence verifier
changes. With its token disabled, it compares Git commits: the previous head for
a PR update or main push, and the PR base for a newly opened PR.

The full Ubuntu/Windows backend matrix and frontend unit/build/browser suite run
only through manual dispatch of **Quality gate** on the selected branch. Both
backend shards and their platform security preflights remain required in that
manual run. Ordinary source changes do not start these jobs automatically.

**Bench checks** runs automatically only for PR changes under `experiments/`.
It validates definition contracts, revision/generation identities and privacy.
Manual dispatch also runs the full Bench synthetic/browser/container/runtime
verification, after definitions succeed. **Verify hosted candidate** is entirely
manual. Select the source branch in Actions when requesting either workflow.
Newer Bench checks cancel the superseded run for the same PR or selected branch.

An automatic green run establishes fast integrity evidence only. It does not
establish full regression, platform, browser or release qualification. Run
affected tests locally during development and dispatch the relevant full suites
on a frozen candidate when that evidence is needed. No test implementation,
privacy rule, release acceptance requirement or deployed service boundary is
removed by this scheduling change.

Feature and `develop` pushes do not start a second quality workflow; their
proposals are checked through PRs. A newer update cancels the superseded quality
run for the same PR. Main runs retain their own evidence and are not cancelled
when another main commit arrives.

Manual deployment reads the successful **Quality gate** run for its exact
`main` commit through `scripts/require_quality_run.py`. It never calls the suite
again. Only a `push` run of `.github/workflows/quality-gate.yml` in the same
repository, with the same source repository, branch and SHA, is eligible. This
automatic run now supplies fast integrity evidence, not a full regression result.
The newest run must succeed, with successful `Repository integrity` and
`Quality result` job evidence. The always-running aggregate requires every
selected suite to succeed and every unselected suite to be skipped. Backend
matrix failures remain failures of that selected job. An unexpected skip,
failure or cancellation fails the aggregate. Missing or skipped required
aggregate jobs, malformed API responses and different commits block deployment.
A failed-job-only rerun may retain successes from earlier attempts of the same
immutable run; a newer unsuccessful attempt takes precedence. The verifier does
not search older commits or treat an unselected suite as newly validated.

If the eligible run is still pending, deployment waits up to 65 minutes.
If no run exists, wait for main CI to appear before dispatching deployment.
A failed main run must be repaired or rerun through its own Actions page.
The read-only check uses the job's temporary `GITHUB_TOKEN` with `actions: read`;
it has no deployment secrets and cannot start tests. Container smoke checks
and authenticated live revision verification still run during deployment.

Bench API/UI deployment keeps its focused tests, privacy scan, syntax check and
exact running-revision verification. Experiment publication and the separate
manual core release retain their existing validation. These workflows do not
wait for the full optional development suites.

## CI ownership

| Job | Platform | Required commands and evidence |
| --- | --- | --- |
| Repository integrity | Ubuntu | `python scripts/privacy_scan.py`; `python scripts/render_architecture_atlas.py --check`; event-range `git diff --check` |
| Backend (manual) | Two required shards each on Ubuntu and Windows | `uv lock --check`; `uv sync --frozen --extra dev`; frozen `uv run` compilation, platform security preflight, and the complete pytest collection split across both shards |
| Frontend (manual) | Ubuntu, Node.js 24 | `npm ci`; `npm test`; `npm run check:api`; `npm run build`; `npx playwright install --with-deps chromium`; `npm run test:e2e` |
| CI policy | Ubuntu | Focused synthetic release-evidence tests when CI configuration or its verifier changes |
| Quality result | Ubuntu | Require integrity and all selected jobs to succeed; require unselected jobs to be skipped |

Every external GitHub action is pinned to an immutable commit SHA. Adjacent
comments retain the reviewed release tag so dependency updates remain explicit
and auditable instead of following a mutable major-version ref. Checkout also
sets `persist-credentials: false` in every job. Backend dependency caching and
installation are keyed by the committed `uv.lock`; uv 0.10.4 refuses lock drift
through `uv lock --check`, then `--frozen` prevents any gate command from
updating the lock.

The Windows run on the source baseline reached approximately 97% of its 6,262
tests before the existing 60-minute job limit. Timestamped progress showed
several slow files, with the largest observed gap about 153 seconds. The backend
matrix therefore runs two required shards per platform without raising that
limit. `scripts/run_backend_shard.py` collects the complete suite in each job and
selects alternating collection positions; the two selections are disjoint and
cover every collected case. Each shard propagates pytest's exit status and prints
its collection count and slowest cases. A synthetic CLI test verifies complete,
exactly-once execution across the pair and failure propagation. Platform security
preflights still run without skips before each shard.

The workflow does not pin test totals or platform skip totals. Tests may grow,
but every command must exit successfully. The explicit security preflights also
parse their synthetic JUnit summaries and fail if an owned test is skipped:

- Ubuntu owns the file-link, directory-link, hard-link, state-root, model-cache,
  quarantine, social-database, and privacy-scanner link boundaries in
  `test_database_symlink.py`, `test_local_model_provenance.py`,
  `test_local_text_model_evaluation.py`,
  `test_quarantined_local_file_reader.py`, `test_scanner_symlink.py`,
  `test_social_sqlite_boundary.py`, and `test_symlink_home.py`.
- Windows owns positive owned-job exit, descendant cleanup, hidden-window and
  no-breakaway process checks. Its preflight also covers watch shutdown,
  exact fixture digests and the isolated manifest CLI.

This division ensures that a capability skip on one operating system does not
silently remove the security contract from the checkpoint.

## Local parity

The architecture check verifies the generated catalog, SVGs and layout data
against the reviewed atlas. PNG bytes remain covered by exact privacy-scanner
hash pins. It does not infer feature readiness or replace application tests.

From the repository root, use a supported Python runtime and run:

```console
uv lock --check
uv sync --frozen --extra dev
uv run --frozen --extra dev python -m compileall -q src tests scripts
uv run --frozen --extra dev python -m pytest
python scripts/privacy_scan.py
git diff --check
git diff --cached --check
```

Then run the locked frontend gate:

```console
cd frontend
npm ci
npm test
npm run check:api
npm run build
npx playwright install --with-deps chromium
npm run test:e2e
```

Linux parity for the link-boundary preflight is:

```console
uv run --frozen --extra dev python -m pytest -q tests/test_database_symlink.py tests/test_local_model_provenance.py tests/test_local_text_model_evaluation.py tests/test_quarantined_local_file_reader.py tests/test_scanner_symlink.py tests/test_social_sqlite_boundary.py tests/test_symlink_home.py
```

Windows parity for the process and portability preflight is:

```console
uv run --frozen --extra dev python -m pytest -q "tests/test_chunked_model_ensemble.py::test_windows_tree_cleanup_requires_positive_owned_job_exit" "tests/test_model_compatibility_catalog.py::test_windows_accelerator_cleanup_reaps_an_atomically_owned_descendant" "tests/test_owned_process.py::test_windows_owned_process_has_no_visible_window_and_no_breakaway" "tests/test_background_model_control.py::test_real_watch_controller_keeps_shutdown_cancelled_without_failure_streak" "tests/test_scope_router.py::test_frozen_scope_router_corpus_is_large_balanced_and_language_independent" "tests/test_scope_router.py::test_canonical_scope_router_fixture_requires_exact_digest" "tests/test_windows_distribution_hardening.py::test_public_build_manifest_cli_compares_two_trees_without_host_paths"
```

All fixtures and output must remain fictional and synthetic. These gates do not
authorize reading provider sessions, transcripts, credentials, local
configuration, or unrelated machine state.

## Outside this checkpoint

Live-provider/browser validation, dependency auditing, SBOM/signing, installer
production, and owner-led UI card review remain separate checkpoints.
