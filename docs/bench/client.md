# Bench client and private analysis export

This is the local source candidate for human operators and AI clients. It uses
the same definitions, admission rules and stored results as the UI. Source tests
are complete only to the scope recorded in the readiness ledger; deployment and
an independent user's walkthrough remain handoff gates.

AI agents should load `.agents/skills/operate-bench-experiment/SKILL.md` through
the root `AGENTS.md` routing table. It uses this guide and the bundled export
dictionary rather than maintaining a separate command or analysis contract.

## Setup and discovery

Use `enhancement-bench` from the reviewed Bench Python environment. In a source
checkout, `python -m enhancement_bench.cli` is equivalent. The existing
[development setup](README.md#local-development) installs its dependencies.
The container builds its virtual environment at the final runtime path so the
installed console command retains a valid interpreter. Verify a candidate image
with `python tests/bench/docker_smoke.py --cli-only --bench-image <candidate>`;
this runs the packaged command without networking, credentials or model calls.
Remote client commands fetch authoritative contracts from the selected Bench API
and work outside a repository checkout. Offline definition validation still needs
the matching source contracts or an explicit `BENCH_CONTRACTS` directory.

The operator supplies the private HTTPS origin in `BENCH_URL` or `--url`. The
only permitted HTTP origins are loopback development addresses. Where machine
access is required, the operator configures `BENCH_CF_ACCESS_CLIENT_ID` and
`BENCH_CF_ACCESS_CLIENT_SECRET` in the process environment. The client loads no
environment file, does not print credentials and refuses authentication redirects.
Keep TLS verification enabled; obtain trusted certificate configuration from the
operator. Browser login alone does not configure machine access.

```sh
enhancement-bench experiments --url https://bench.example.com
enhancement-bench schema run-plan
enhancement-bench schema analysis
enhancement-bench validate --json example-definition.json
```

Discovery returns stable/revision, case and variant IDs without prompt text.
Select the actual returned identifiers. Validation checks an explicitly authored
synthetic definition locally; it does not import it or run a model. Definitions
are delivered through the existing reviewed publication workflow.

## One small run

Create a private working directory outside the repository, using a real path
without symlink components. Receipt parents must already exist. The following
reserved example identifiers must be replaced with selected definition IDs.
Run all commands against the same operator-configured `BENCH_URL`.

```sh
enhancement-bench preflight --experiment example-review --revision 1 \
  --subject example-case --unit example-variant
enhancement-bench run --experiment example-review --revision 1 \
  --subject example-case --unit example-variant --receipt run-01.json
enhancement-bench wait --receipt run-01.json --timeout 300
enhancement-bench inspect --receipt run-01.json
enhancement-bench export --receipt run-01.json --output analysis-01
```

Preflight validates the selected definition, effective requests and registered
core artifact. It reports the attempt count and a queue/hold snapshot. Worker
liveness, provider authentication and model readiness explicitly remain
`unverified`. Preflight makes no model call, queues no run, reserves no capacity
and cannot guarantee later execution. Resolve rejected settings before admission.

`--subject` and `--unit` may be repeated. `--overrides authored-overrides.json`
accepts the API's overrides object, including supported parameter/model/policy
settings. Do not select the same field both in that file and with a selection
flag. Omitting selections uses all cases/variants in the revision. The attempt
count is cases multiplied by variants; before/after are measurements within an
attempt. Keep model credentials outside overrides.

### Admission recovery

`run` saves a private `bench-submission/v1` receipt **before** sending the request.
It records the request UUID, origin/settings fingerprints and acknowledged run
ID. It contains no prompts, override text or credentials. Retain the original
settings as well as the receipt; fingerprints cannot reconstruct those settings.

If the acknowledgement is lost, repeat the exact `run` command with the same
receipt and settings. The API deduplicates the request UUID. Changed settings or
origin are rejected. Once a receipt contains a run ID, repeating `run` returns
that ID without another submission; this is a saved acknowledgement, not a fresh
readiness or completion check. Use `inspect` or `wait` for current state.

A fresh receipt means an intentional new run. Never use one to recover an
ambiguous submission. `--retry-of RUN_ID` denotes a deliberate rerun and requires
a reconciled terminal source run. There are no implicit transport retries or
automatic release of cleanup/reconciliation holds.

### Observation and cancellation

`inspect`, `wait` and `cancel` accept either a positional run ID or `--receipt`.
Inspection reports recorded status, technical outcome, review state, evaluator
coverage and assertion outcomes without prompt or rewrite text. Technical
failure, experimental assertion failure and missing measurements are separate.

`wait` observes for 1-3600 seconds (default 300), polling every 0.1-30 seconds
(default 2). Its timeout stops observation; the run is not cancelled or resubmitted.
Repeat `wait` for the same run if needed. A terminal status with a cleanup or
reconciliation hold still fails the operational check.

```sh
enhancement-bench cancel --receipt run-01.json
enhancement-bench wait --receipt run-01.json
```

Cancellation acknowledges a request, not confirmed remote stop. Only a verified
operator can resolve an uncertain remote operation. The client has no automatic
reconciliation command. See the [handoff state dictionary](handoff.md#interpret-results).

## Machine-readable output

The new client commands emit one `bench-cli/v1` JSON object on stdout, with
`command`, `ok` and either `data` or `error`. Errors contain a stable `code` and
`nextAction`; they do not echo raw server responses or invalid input. `validate
--json` uses the same envelope; the existing default validation output remains
human-readable. Command help is human-readable.

| Exit | Meaning | Next action |
| --- | --- | --- |
| `0` | The operation succeeded. Admission is not execution completion. | Interpret `data` for the specific command. |
| `2` | Input, transport, access, contract or local-file error. | Follow `error.nextAction`; preserve an existing submission receipt. |
| `3` | `wait` observed execution/technical failure or a hold, or required assertions did not pass. | Inspect the returned report and resolve the specific cause. |
| `4` | Observation deadline reached. | Inspect/wait for the same run; do not assume it stopped. |

`ok:true` means the command produced a valid report. A terminal failure report
from `wait` therefore has `ok:true` and exit `3`. Assertion failure alone does not
make execution fail; add `wait --require-assertions` to require assertion outcome
`passed` for exit `0`. Unknown assertions then fail that explicit gate too.

`schema run-plan` and `schema analysis` return their JSON Schema under `data`.
These describe the submission plan and export respectively, not a full OpenAPI
specification. The client validates core results against contracts served by
`GET /api/client-contracts`; unsupported/malformed results fail explicitly.

## Explicit analysis cohorts

```sh
enhancement-bench runs --experiment example-review --revision 1 --limit 25
enhancement-bench export --receipt run-01.json --receipt run-02.json \
  --output comparison-01
```

`runs` returns one page and `nextCursor`; use that cursor as `--before` for the
next page. Select explicit run IDs/receipts for an analysis cohort. Export accepts
1-50 unique runs, up to 50,000 total table rows and 64 MB of serialized files.
Split larger cohorts deliberately. It does not export every run on a stats page
or compute cross-run averages automatically.

The new output directory contains:

- `manifest.json`: `bench-export/v1`, exact run IDs, row counts and file hashes.
- `analysis.json`: typed `bench-analysis/v1` tables, with nulls preserved.
- `analysis.schema.json` and `README.md`: schema and the bundled data dictionary.
- `runs.csv`, `attempts.csv`, `metrics.csv`, `assertions.csv`, `timings.csv` and
  `errors.csv`: table views with documented join keys.

Every selected attempt remains represented, including skipped and unexecuted
ones. Metric states/reasons, known zero, categorical labels, provenance, reported
deltas and numeric inclusion/exclusion rules remain explicit. Missing values
stay null, not zero. Use `pair_eligible` and `comparison_scope`, then group by the
configuration fields described in the bundled dictionary. Report missing and
excluded counts with conclusions. Assertion and execution pass rates have
different denominators.

Exports omit prompt/context text, rewrites, review notes, target text, raw policy
instructions and credentials. They retain sensitive derived data, model
provenance, identifiers and content fingerprints; they are not anonymous.
Keep them private. CSV cells containing objects/lists use JSON; formula-leading
text is escaped for spreadsheets. Use `analysis.json` for original typed values.

The writer refuses existing output directories and symlink paths. POSIX files
are created with mode `0600`, directories with `0700`. Keep the parent directory
private too. Windows ACL qualification is still required. `manifest.json` is
written last: a directory without it is incomplete, including after a process
crash. Use a fresh path after inspecting any incomplete output. File permissions,
hashes and absent text fields do not make these files safe for public upload.

## Implementation task card - 2026-10-23

- Atlas/gates: MA18 and W02/W05/W07; handoff gates 3-5, scoped to fixed Bench flows.
- Baseline: reviewed develop `cdcfb5f`, on the existing isolated handoff branch.
- Outcome: one documented discovery/preflight/admission/observation/export path,
  with structured errors and durable admission recovery for human and AI clients.
- Contracts: shared request validation, authoritative core schemas, existing
  idempotency and operator reconciliation; no new execution engine or migration.
- Evidence: synthetic API and client fault injection; real CLI subprocesses
  against an owned loopback API from outside the checkout; hand-computable export
  fixtures, file failures and privacy canaries. Counts are in the readiness ledger.
- Bounds: explicit cohort/response/file/row limits; bounded polling, no implicit
  model calls or retries. Fixtures use synthetic runtime/container doubles.
- Remaining: source review, reviewed release/deployment, frozen-candidate live
  qualification, supported-platform file protection and an unaided walkthrough.

## Packaged command correction - 2026-10-23

- Atlas/gates: MA18 and W02/W05/W07; human/AI operator entry point.
- Baseline: reviewed develop `8bd1245`.
- Defect: copying the virtual environment to a different runtime directory left
  the installed command pointing to its absent build-time interpreter. The
  documented module entry point remained usable.
- Change: build and run the environment at the same path. The container smoke
  now executes the installed command and checks its run-plan schema; `--cli-only`
  isolates this check from core images, credentials and model execution.
- Evidence: the repaired local image passes the isolated command check; all 68
  affected client/runtime tests pass, including the owned-loopback CLI journey.
- Remaining: owner review and deployment of this packaging correction. Existing
  live qualification uses the module entry point and does not verify this image.
