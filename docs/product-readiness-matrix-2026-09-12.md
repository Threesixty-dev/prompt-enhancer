# Product feature and readiness matrix

Updated 2026-09-23 for checkpoint B00. This is the authoritative beta ledger,
not a release certification. The filename is retained to preserve existing links.
It distinguishes code present in this working tree from a product a new user can
install, sign into, or buy. The repository's synthetic fixtures and local tests
are not evidence of a packaged product or a live external service.

Point-in-time dispositions such as "committed locally" and "nothing was pushed"
record the state at their named B00 review event. They are retained as historical
evidence, not asserted as live remote-sync status when this ledger is read.

## Current beta contract

The approved release is a **free, local-first Windows 11 x64 invited-test beta**:
no Prompt Enhancer account or payment is required. CPU inference and one verified
NVIDIA/hybrid profile are required. Source stays private; public distribution is
through a separate binary-only repository. Signing uses an owner-controlled beta
certificate with explicit fingerprint-verified trust setup. Public downloads are
not access-controlled invitations. Previously acquired source cannot be recalled.

Accounts, billing, teams, hosted/social features, arbitrary Hugging Face support,
unverified modalities, universal MCP support, other desktop platforms, OpenHands,
new research metrics and major redesigns are deferred. Preserve their code/data;
later B01 hides or clearly separates unsupported UI. Client-side JavaScript
remains inspectable; compiled packaging is deterrence, not uncopyability.

The owner authorized a sequential beta campaign on September 23. B00 is still
the active gate; B01 has not started and cannot be claimed from this authority.
Record each checkpoint's evidence and continue only when its exit gate is met.
Owner-dependent signing, hardware, custody or product decisions remain explicit
stops. No recurring automation, repository visibility change, reboot, release
or source push is authorized by this ledger. One implementation worker maximum; two
hypothesis-driven corrections maximum for a failure; no blind reruns or budget
increases. Use synthetic data and hidden, bounded, owned processes only.

### Approved workflow scope amendment — W00–W08

The beta now also requires a future **local text/image/audio typed workflow**
extension. It is approved scope, not current implementation: every W00–W08 row
is **required but not started**, remains gated on B00 and the applicable native
foundations, and cannot be used to claim that B00 is accepted. The beta ceiling
is 32 nodes, including at most 16 model nodes, at most two concurrently executing
stages, and one active workflow run. Sequential scheduling must support unloading
between model stages for constrained-memory devices.

| ID | Required beta result | Current state / gate |
| --- | --- | --- |
| W00 | Qualification and packaging feasibility: freeze profiles, fixtures, hardware and dependencies; prove early compiled text/image/audio workers. | Required, not started; gated on B00. No profile, hardware or package acceptance exists. |
| W01 | Types and graph validation for bounded text/image/audio nodes, compatible ports and fail-closed invalid edges. | Required, not started; W00 contracts and fixtures required. |
| W02 | Durable sequential engine with persisted run state, deterministic dependency ordering, cancellation/recovery and unload between constrained-memory model stages. | Required, not started; native owned-process/model cleanup foundations required. |
| W03 | Production model adapters for the explicitly supported local text, image and audio formats/runtimes. | Required, not started; no arbitrary model/runtime compatibility is implied. |
| W04 | Resource-aware parallel execution capped at two ready stages, 32 total nodes, 16 model nodes and one active run. | Required, not started; measured RAM/VRAM and cleanup evidence required. |
| W05 | Visual builder and model advisor with typed composition, including image-classifier → LLM → rendered-output flows and reasoned compatible-model recommendations. | Required, not started; native UX and genuine device/profile acceptance remain separate. |
| W06 | Headless export/import for the installed Prompt Enhancer runner, binding workflow and model/runtime requirements without weights, credentials, source history or arbitrary code. | Required, not started; not standalone/package acceptance. |
| W07 | End-to-end qualification of the exact installed-runner workflow across supported local modalities, limits, interruption/recovery and cleanup. | Required, not started; qualifying native/hardware/package evidence required. |
| W08 | Beta integration with B00–B11, preserving their custody, privacy, packaging, native acceptance and release gates. | Required, not started; cannot close or bypass any B00–B11 gate. |

Arbitrary-code nodes and remote cloud, email or other connector endpoints are
outside this beta amendment. They require a later privacy/security/product
decision; existing related code, if any, is not activated or accepted here.

## B00 — custody and baseline, 2026-09-16

**Status: selected repairs finished; B00 blocked, not accepted.** Private source visibility was independently
confirmed on September 16 and rechecked on September 17 through
`gh repo view --json visibility,isPrivate`; result `PRIVATE`,
`isPrivate=true`. The private source remote's identity is intentionally not copied
into this document. A separate binary-release destination is not yet supplied or
verified. No source history has been copied to a release repository.

Starting source commit: `7888064a1cf25703b6e312da97868edd4573c5b3`, on the existing
`codex/real-metrics-campaign` branch, with **zero staged entries**. This commit does
not include the pending implementation. The author identity check returned a
public/noreply identity without recording the address.

The default porcelain count of 637 expands to **646 files** when untracked
directories are enumerated: 226 modified tracked files and 420 untracked files.
Every entry is classified in the linked [B00 inventory](beta-b00-worktree-inventory-2026-09-16.json).
Classification is triage, not approval of a diff, a test result, or permission to
stage it. Counts below describe the starting tree, before these B00 documents.

| Category | Files | Disposition |
| --- | ---: | --- |
| Beta implementation | 160 | Preserve; review coherent changes against their checkpoint before staging. |
| Beta tests/build tooling | 404 | Preserve; verify exact dependency and test boundaries before staging. |
| Documentation | 56 | Preserve historical evidence; this matrix is the sole current release queue. |
| Interrupted/incomplete | 2 | Exclude frontend notice CLI/module until B08 review and regression tests. |
| Unrelated to beta | 14 | Preserve paid-product implementation/tests; do not advance them for this beta. |
| Generated output | 10 | Preserve leftover synthetic lifecycle files in place; never stage them. |

Two additional source files were discovered outside Git's visible inventory:
`frontend/src/build/viteModuleInputInventory.ts` and its `.test.ts` file are
initially ignored by the broad `build/` rule. Their hashes and disposition are recorded in
the inventory addendum. They are preserved separately, not silently inserted
into the initial test snapshot. This was a concrete source-custody/build blocker:
`frontend/vite.config.ts` imports a module absent from a Git-derived checkout.

An external 2,098-file source snapshot preserves all enumerated non-generated
inputs. Its inventory SHA-256 is
`43d43d410865f0c41e849adc1795f49435601cc372d602fe767df54c653cc704`.
This is a file snapshot, **not a committed baseline or a distributable artifact**.
The ten generated files remain in place, hash-bound in the inventory. The existing
external quarantine remains untouched: 4,904 files / 440,628,343 bytes were moved
with prior owner approval, not deleted. No generated outputs were restored.

The interrupted notice work is specifically
`src/prompt_enhancer/infrastructure/frontend_notice_inventory.py` and
`scripts/prepare_frontend_notice_inventory.py`. It projects partial hash-bound
notice evidence and explicitly returns `complete=False`; its planned
`tests/test_frontend_notice_inventory.py` does not exist. No new renderer/framework
or notice-closure claim is justified. Resolve it under B08, reusing the existing
Windows notice inventory/renderer. The opaque PDF worker remains unresolved;
either prove dependency/notice closure or omit the viewer **and worker payload**.

### Initial B00 validation receipts — September 16

All new test state, dependencies, caches, reports and build output use an external
snapshot/validation directory. The user's app, ports 8765/8766, private provider
state and model/GPU were not test targets. Outputs are bounded; reports retain
closed results and test identifiers, not transcript content. The snapshot is
bound to the starting dirty tree, not merely the HEAD commit. No package is tested
in B00; `artifact digest = not applicable` for these source checks.

| Check / test ID | Latest result | Scope and limit |
| --- | --- | --- |
| `B00-CUSTODY` — GitHub visibility | Pass | Repository metadata only; no visibility mutation. |
| `B00-INVENTORY` — all 646 status files | Pass | Entry classification/hashes, not correctness review. Ignored-source addendum tracked separately. |
| `uv lock --check` | Pass | Offline lock validation in isolated source snapshot. |
| `uv run --frozen --extra dev python -m pytest` | Fail — exit 2, one collection error | Exact identifier: `tests/test_windows_stage_recipe.py`. Import-time dependency on `test-results/prepare_windows_stage_43.py` is absent after quarantine. No tests executed; the rest of the suite is unverified. Two bounded dependency-preparation corrections preceded the one actual collection attempt; no test was retried or skipped to obtain a pass. |
| `npm ci --ignore-scripts --no-audit --no-fund` | Pass | Frozen frontend dependencies; package lifecycle scripts disabled, not a blanket assertion that scripts are unnecessary for every release input. |
| `npm test` | Fail before useful acceptance | Isolated configuration cannot resolve the ignored build module. No passing test count is claimed. |
| `npm run check:api` | Pass | Generated API contract drift check. |
| `npm run build` | Fail | `TS2307`, `vite.config.ts`: missing `./src/build/viteModuleInputInventory`. |
| `node --test scripts/check-agent-bundle-budget.test.mjs` | Pass | Budget-checker fixtures, not a current built-bundle measurement. |
| `npm run check:bundle-budget` | Blocked | Build failed; deliberately did not evaluate stale output. |
| `npm run test:e2e` | Fail during startup | Isolated port 14873, no existing server reuse, one worker, zero retries. No browser journey is claimed passed. |
| `python scripts/privacy_scan.py` | Pass — exit 0, zero findings | Full source-checkout scan, no rule/exemption changes; repeated after B00 documentation reconciliation. |
| `git diff --check` | Pass — exit 0 | Whitespace only; cannot replace source/security review. |

The initial failure was at collection, not a failed assertion in every test in that
module. Lines 13–18 of `tests/test_windows_stage_recipe.py` load the missing helper
at import time. Do not restore quarantined generated output or skip the test to
make CI green. The September 17 repair below extracts the reusable recipe into
a source-controlled tooling location candidate and updates this test; generated
artifacts remain quarantined.

All completed baseline commands confirmed owned-process cleanup. No native app,
model, signing, installation, release or personal app port was used. No files
were staged, committed or pushed. The baseline remains recoverable as an external
file snapshot, **not yet as reviewed source commits**, so the B00 exit criterion
is deliberately left open. Evidence runner/configuration and closed receipts are
retained externally under validation run ID `b00-20260916-01`; no raw terminal
output or private configuration is included in this ledger.

### B00 baseline repairs — September 17

One implementation worker was explicitly configured as `gpt-5.6-sol` with
`medium` effort. The orchestrator reviewed its changes and runs the independent
baseline. No next checkpoint, production runtime, model, or installer was started.

- Four narrow ignore rules expose only the Vite inventory helper and its test;
  generated build output remains ignored. Both recovered files are byte-unchanged.
- The composite TypeScript project now explicitly includes that helper. This
  resolves the subsequent `TS6307` found by the forced clean typecheck; no broad
  source/test glob was added.
- `scripts/prepare_windows_stage_recipe.py` replaces the test's dependency on a
  quarantined generated helper. It requires explicit runtime identity and source
  inputs, performs offline review, and delegates preparation only after verifying
  the supplied archive. No default private artifact path, download, signing,
  install, fixed wheel-count assembly, or quarantined output was restored.
- `tests/test_windows_stage_recipe.py` checks missing/unsafe inputs, content-free
  review, actual archive identity mismatch, and propagation of the verified pin.

These checks use validation run `b00-repair-20260917-01`. The frontend input
manifest SHA-256 is `b9ea428a2052f95cf73c8568fae5b4199fd18b60cb7bc285c960333cc6181709`;
the later 2,102-file backend snapshot manifest is
`90fc68cee7604dd37c0c082e783575b6bc43efe10e889e5ecfa6599b478ca652`.
The build continuation additionally replaces only `frontend/tsconfig.node.json`
with SHA-256 `b0e666ce208d8c1354f66975c829cd04064e428856332795270c9ef58adaac98`.
All are dirty-snapshot evidence, not a release commit or package digest.

| Check / test ID | Latest result | Evidence scope / limitation |
| --- | --- | --- |
| Vite inventory helper focused tests | Pass — 17 tests | Unit; recovered source unchanged. |
| `tests/test_windows_stage_recipe.py` | Pass — 23 tests | Unit/integration with synthetic runtime bytes; not package installation. |
| Full backend suite | Blocked/incomplete — `owned_process_timeout` at 1,800.11 seconds | 7,606 collected. Last persisted progress: 3,668 passed reports, 25 failed reports, 7 skipped reports. Not a completed suite or a final count; see receipt limitation below. |
| Full frontend suite | Pass — 3,586 tests, zero failed/pending | Source-level UI tests; not real-model/native acceptance. |
| `npm run check:api` | Pass | No contract drift. |
| Forced TypeScript build and Vite production build | Pass | External snapshot; no stale incremental state accepted. |
| Bundle-checker fixtures and production budget | Pass | Existing limits unchanged. |
| Browser suite | Fail — 355 passed, 4 failed, 6 skipped | Completed once in 596.73 seconds; isolated loopback port, one worker, zero retries; cleanup confirmed. No native acceptance. |
| Browser repair recheck | Pass — 6 cases, zero failed/skipped/retried | All four failed IDs plus two wider-layout controls; 14.72 seconds; production code unchanged and cleanup confirmed. Full suite not repeated. |
| Privacy scan | Pass — full checkout plus explicit recovered-source scan | Repeated after fixture/document reconciliation: both exit 0, zero findings. The normal scanner skips `build` directories, so its existing explicit-path interface also checked the two recovered files. No exemptions added. |

The first frontend preparation attempt ran before the dependency-copy handle had
finished, so it failed before executing any tests. Its receipt was retained; the
copy was allowed to finish before the single actual full frontend run. The
TypeScript include correction then reran typecheck/build checks only, not all
3,586 tests. No full suite is restarted merely because it is slow.

The reviewed four-file frontend group is now saved locally in
`b77329559ef6affc6e50e2b05ea0f1ac4e366a8b` (`.gitignore`, the helper and its test,
and `frontend/tsconfig.node.json`). Staged content matched the reviewed files;
privacy, focused/full frontend tests, API, type/build, budget and staged whitespace
checks passed. This commit does not certify the failed browser baseline, the
incomplete backend baseline, or remaining application changes. The browser
failures were subsequently repaired and rechecked as described below. Nothing was pushed.

There are 648 remaining pending entries and zero staged entries after that commit.
The new recipe depends on existing untracked packaging modules, so it must not be
committed alone as a purported self-contained baseline. The original inventory
hashes remain historical; the repair addendum records new inputs without
overwriting the initial observation. Full reviewed baseline recovery is still open.

#### Exact browser baseline failures — repaired and rechecked

The four failed IDs from Playwright's completed last-run record were mapped to
test titles using `--list` only; no browser test was rerun. The general console
location list also contains passing tests, so it is not used as a failure index.

| Exact test identifier | Tested variant | Observed boundary / next action |
| --- | --- | --- |
| `frontend/e2e/beta-runtime-recovery.spec.ts:4` — runtime read recovery preserves draft and pending choices | 320px | The fixed chooser covered the external fixture injection button. The test now uses its accessible Close control, injects failure and reopens Refresh. Recheck passed with all draft/pending assertions retained. |
| `frontend/e2e/beta-runtime-recovery.spec.ts:63` — runtime read recovery retains an exact last-confirmed Stop target | 320px | Same covered-control test assumption; fixed through Close/reopen. Recheck passed, including exact Stop target. Original line 63 is now 64. |
| `frontend/e2e/workflow-panels.spec.ts:600` — Agent controller health is private, keyboard reachable and subordinate to chat | 360px | Obsolete directory-move wording at `:674`, not a port failure. Updated assertion checks tracked-or-recovery state and never-claimed contents review. Recheck passed. |
| `frontend/e2e/workflow-panels.spec.ts:600` — same controller-health test | 1440px | Same stale assertion; recheck passed. |

Detailed error evidence corrected the initial port hypothesis: both the fixture
and test hardcoded port 4173, so that assertion falsely agreed with itself even
on port 14873. The fixture endpoint, generated client setup and test expectation
now derive from the actual page origin. This strengthens an additional check; it
was not the cause of the four failures. Only the two specs and their shared
fixture changed; no production popover, runtime, approval or artifact code changed.
The six-case recheck includes both runtime scenarios at 1440px as controls.
Its input deltas and receipt are retained externally as
`browser-focused-input-binding.json` and `browser-focused-receipt.json`.

These are source/browser observations, not a reason to weaken native approvals,
claim runtime/GPU testing, skip failed checks, or change a release bundle limit.

#### Backend baseline limitation and cleanup

The single full backend run hit its existing 30-minute bound. It was not restarted
or given a larger budget. Collection passed, but the last saved progress contains
only report counts: 3,668 passed, 25 failed and seven skipped out of 7,606 collected.
Counts are reports, not an assertion that every collected test ran or a deduplicated
final outcome. The runner records exact failed IDs only in `pytest_sessionfinish`;
forced timeout prevented that hook from writing the final receipt. Therefore the
25 exact failure identifiers are **unavailable**, and B00's exact-blocker-index
exit criterion is not satisfied. Do not invent their causes or call them 25
independent product defects. The next run must persist failure IDs incrementally
before attempting bounded, resumable selections; no automatic full rerun.

The wrapper's exception receipt retained `cleanup_confirmed=false`; that field is
not a successful cleanup receipt. A separate read-only check confirmed all five
observed backend-tree processes exited, no process referencing this validation
run remained, and isolated browser port 14873 was released. The underlying owner
returned `owned_process_timeout`, not `owned_process_cleanup_unconfirmed`.
No personal app, provider profile, GPU model, installer, certificate or reboot was
used. Raw output is not copied into this ledger. The external partial counts and
closed timeout receipt are retained rather than relabeled as a pass.

#### Bounded backend evidence continuation

The opt-in `tests/support/bounded_pytest_receipt.py` writes a flushed,
content-free phase journal to an explicit external directory. It records the
active test before execution and failure/collection identifiers immediately,
keeps phase-report counts separate from unique test outcomes, distinguishes
completion from interruption, and recovers only complete records before an
actually torn final record. It has no `conftest` registration or automatic
activation. The final ten focused synthetic tests passed in 0.91 seconds in the
existing frozen development environment. The added process-boundary regression
uses the hidden owned-process runner: synthetic test A fails, test B hard-exits,
and the journal retains A's exact failure ID plus B's active ID, no completion
record and no assertion/stdout payload. Its first integration attempt returned
pytest usage code 4 before either child test because the synthetic root was not
explicit; adding `--rootdir=.` corrected that harness boundary. The earlier
nine-test receipt remains historical. These worker executions are not independent
root, native, model or package acceptance.

The root then ran two selected batches through the hash-bound external runner,
each with a 300-second ceiling, `maxfail=3`, zero retries and confirmed owned
cleanup:

| Batch | Selected scope | Unique outcomes | Phase reports | Duration / journal |
| --- | --- | ---: | ---: | --- |
| `adapter-agent-catalog-01` | Adapter contract, Agent artifacts, attachments and catalog — four modules | 121 passed; 0 failed/skipped | 363 passed | 59.469s; SHA-256 `128046834ae6a357c28365dda778d5e9e367910b97c6a4d0fc2adb3a9b5d964c` |
| `agent-retention-workspace-02` | Agent change set, directory-move artifacts/policy, document previews, hardening, history and message search — seven modules | 84 passed; 0 failed/skipped | 252 passed | 26.547s; SHA-256 `3ad18256b354c7e95e8df6b249c308746d11398ac5e8f495ad2722ba50bf284f` |

The combined selected result is **205 unique tests passed across 11 modules**
and 615 passing phase reports. Inputs bind to the unchanged 2,102-file manifest
SHA-256 `90fc68cee7604dd37c0c082e783575b6bc43efe10e889e5ecfa6599b478ca652`,
the four separately enumerated reviewed frontend overlays above, and receipt
plugin SHA-256
`4a7a568b9e4de776c52d5d37ef861de1d7b7dc53c97e1a69e0128d85d9a143aa`.
This is synthetic source unit/API evidence only. It does not complete the 7,606
test baseline or map/resolve the old run's 25 failed reports; B00 remains blocked.

Four further root-owned bounded batches used the same manifest/plugin binding,
300-second ceiling, `maxfail=3`, zero retries and confirmed cleanup:

| Batch | Scope | Unique outcomes | Duration / journal |
| --- | --- | ---: | --- |
| `agent-controller-03` | Four controller CLI/client/HTTP/ownership modules | 113 passed, 1 failed of 114 | 22.875s; SHA-256 `03efc0914e48d6b3b433815e42bec6fe05f40763c40c5a7d01ded2e1e5e395e8` |
| `agent-mcp-contracts-04` | Five fixture/in-process MCP contract, configuration, packaging, connection and HTTP modules | 79 passed, 0 failed/skipped | 8.969s; SHA-256 `3815b26061029d511484d0ee5abcd0149e8005b9337073d308a5661e76fd05f9` |
| `agent-contract-retention-05` | Seven metric/orchestration/parameter/hardening/fork/write-proposal modules | 79 passed, 1 failed of 80 | 47.094s; SHA-256 `ba1bd7acca85d6e74f38ee89bdc7844093063ee689a013c3a7aa73e2c207128d` |
| `agent-command-boundary-06` | Command API and Windows command boundary modules | 11 passed, 0 failed/skipped | 9.453s; SHA-256 `9fcc09f1ce66c56acb80daa22d45773cbdee3a397c6f97f76669d7dee4723b71` |

The controller failure was a stale schema-23 test fixture: it removed schema
24–30 objects but retained schema 31 message-search and schema 32 directory-move
tables, so forward migration encountered duplicate schema-31 DDL. The fixture now
removes every post-23 object and proves the v23 marker plus exact preservation of
two projects, one session and three scoped connections; migration still invents
zero ownership rows. The final exact node passed in 2.5 seconds and its full
16-test module passed in 15.281 seconds, both with confirmed cleanup. This is a
test-fixture correction only; production migrations were not weakened or changed.
After the 988-input binding check found only this reviewed test delta, root's
privacy and diff checks passed and the file was committed locally as
`3640b1d6fce54f1ebb51633aaf24bb0dd036e987`. Nothing was pushed and no staging
remains. This one-file commit does not accept the whole dirty baseline.

After deduplicating that module recheck, the four new batches contain **283 passed
and one unresolved failed test across 284 selected tests**. Combined with the
earlier disjoint 205, current selected evidence is **488 passed and one failed**;
the ten recorder regressions remain a separate tooling result. This is not the
complete 7,606-test baseline.

The unresolved failure is
`tests/test_agent_orchestration.py::test_orchestration_manifest_covers_every_agent_route_and_only_real_routes`.
An owned synthetic OpenAPI probe found 75 current Agent routes versus 72 declared
controller routes. The exact actual-only set is `GET
/v1/agent/web-fetch-capability`, `POST
/v1/agent/catalog/sessions/message-search`, and `PUT
/v1/agent/sessions/{session_id}/parameters`; no declared route is absent from
OpenAPI. The stale test's verb filter omits PUT and therefore observes 74 rather
than 75 routes. Message search is explicitly body-only/private and forbidden by
source contract from orchestration/MCP exposure; the capability and parameter
routes are UI transport surfaces with no controller/MCP operation. Do not add
them blindly or weaken exhaustive coverage. A separately scoped repair must make
the selected controller-route contract and its explicit private/UI exclusions
truthful; no production or orchestration-test change was made here.

At this review point, the real-listener `tests/test_agent_mcp_integration.py` was
deliberately held: all three tests first attempted personal port 8766 before
ephemeral fallback, and one used direct `subprocess.run` rather than the shared
owned-process helper. The passing five-module MCP batch above was
fixture/in-process evidence only and did not absorb those listener/process risks.
That historical hold was repaired and closed by B00a below.

### B00 route-contract and metric validation — September 21

The known orchestration coverage failure is closed in the current dirty source
tree. local-agent-orchestration.v23 truthfully declares a selected surface of 72
Agent routes plus five controller runtime routes. The route test partitions all
75 actual Agent routes across every OpenAPI HTTP verb into those 72 declared controller
routes and three explicit non-controller exclusions: web-fetch capability
metadata, private body-only message search, and UI-only session-parameter
control. Server and frontend validators reject those excluded paths; controller
and MCP regressions refuse message search. No callable route, permission, native
approval boundary or runtime-selection authority was added. The server,
frontend parser/self-test, generated OpenAPI and API types moved together to
v23; v22 clients require a matching update.

These are independent scoped receipts and are **not** added to the historical
488-pass baseline subtotal:

| Receipt | Result | Scope / limit |
| --- | --- | --- |
| route-contract-20260921-01 | 139 passed, zero failed/skipped in 142.391s | Current-tree unit, in-process API, controller, MCP and OpenAPI selection; 955 bound input hashes unchanged; source-inputs SHA-256 ac9fdde7673e3c4b9692543f844053a40cf25ad0267eb9d3613c8223db0bd103; journal 5dda7c22f3106d3c312fe70775afd84bd97349d97b1e841038ad8b85e8282361. |
| route-ui-20260921-01 | 264 component tests passed in 38.781s; app TypeScript passed in 28.25s | Frontend contract/controller/MCP/transport scope; 748 input hashes unchanged; source-inputs SHA-256 5554bcecb9ab730e2cf8ac34eacea69c95aa8c5ff3a26f5bfd69c5c4ec4e4fa1; headless runner used no config cache and TypeScript state was external. |
| route-api-types-20260921-01 | check:api passed in 9.406s | Generated API type equality for the scoped contract change; input hashes unchanged. |
| metric-truth-20260921-01 | 50 tests across nine modules passed in 76.484s | Unknown versus zero, denominators/coverage, timestamp basis, provenance, SQLite/API/publication and 20-contract operability; journal f801add48dfd4564d5d06383319f3e36824e6d2bbef811c26e3849c40a2f2e86. |
| metric-ui-20260921-01 | 72 component tests passed in 50s | Metric, radar and coverage rendering only. |
| metric-browser-20260921-01 | 12 headless Chromium fixture tests passed in 13.578s; zero failed/flaky/skipped | Narrow 360px and desktop 1440px, keyboard, zero/unknown, stale/retry and cancellation; isolated port 14873 was released. |

The scoped totals are 189 backend tests, 336 component tests and 12 browser
tests; they are not a full quality gate. All owned processes were hidden and
cleaned up. No native-window monitor 2/3 acceptance, model/GPU, real provider
read, app restart, hook, package, release candidate or Blueprint/workflow
implementation was exercised. Metric evidence used an immutable prior snapshot
whose 952 backend and 748 frontend inputs were compared with current inputs
before this repair; only an unrelated reviewed ownership fixture differed. The
current-tree source integration base was HEAD
fa95747cb8c7e73d0ac9656abd1a4d8e4d6dc044; there is no RC or artifact digest.
Receipt route-final-privacy-20260921-01 records the full current-checkout privacy
scan passing with zero findings in 27.953s, exit 0 and confirmed cleanup.
git diff --check also passed; nothing was staged, committed or pushed, and 660
pending files remained after this slice.

### B00a held Agent MCP integration harness safety — September 21

B00a is closed. The held Agent MCP integration harness now continuously owns an
OS-assigned loopback socket from reservation through server startup, requires an
explicit validated probe endpoint, and runs child probes through the shared
hidden, bounded owned-process boundary. Synthetic child homes, provider roots,
caches and temporary paths are isolated. No user runtime or personal port was
contacted, and no product source behavior changed.

These current-checkout receipts are independent scoped evidence and are not
added to the historical 488-pass baseline subtotal:

| Receipt | Result | Scope / limit |
| --- | --- | --- |
| `b00a-regression-01` | 6 passed, zero failed/skipped in 9.437s | Listener handoff/setup-failure, explicit endpoint, no-redirect/bounded response, and owned-process success/nonzero/overflow/spawn/timeout cleanup regressions; runner receipt SHA-256 `68a1653cf12ec4ad9857fd8f865ee0f4dfd6379f0a73b582a3bc369c6bf8ac56`. |
| `b00a-integration-01` | 4 passed, zero failed/skipped in 59.594s | Exact real owned-loopback Agent MCP selection, including authentication, revocation/negative behavior, stdio protocol and reviewed synthetic workspace transactions; runner receipt SHA-256 `2d81b6fcea3c4d7c1103c05b8554cf68f4fc50da75b5265909dd8c53dcbcc627`. |
| `b00a-privacy-01` | 8 passed, zero failed/skipped in 42.406s | Full-checkout privacy scanner plus its seven canary tests; runner receipt SHA-256 `1a38a860eb11a844ba4f413617dd48cdda428a6521420aaf73f50030325ced03`. |

All 18 tests passed on their initial execution with no corrections or retries;
owned cleanup was confirmed. The runner's bound files were unchanged within
each batch. A separate before/after hash covered 983 files total: the
source/test/script Python files plus `pyproject.toml` and `uv.lock`; both trees were SHA-256
`290b71157da83767e186ece757589492cccc82c3c151803bd6c54ddd53578a4e` at
HEAD `fa95747cb8c7e73d0ac9656abd1a4d8e4d6dc044`. This is source/test evidence,
not a release artifact. A read-only pre-edit/current reproduction also confirmed
that the old probe accepted a missing endpoint while the repaired probe rejected
it before socket use; no network was executed.

The integration tests issue presence capabilities directly from the in-process
test approval manager. They do **not** prove a genuine native approval dialog,
packaged application, model/GPU path or release candidate. There is no artifact
digest, commit or push for B00a. B00 remains blocked: the next bounded checkpoint
is B00b, the unresolved baseline/failure inventory and reviewed custody work.
B01 and W00–W08, including the required Blueprint-style workflows, remain not
started.

Historically, before B00a, root review, cached-diff inspection and a passing
privacy scan led to exactly the receipt plugin and its focused test being
committed locally as
`d070f79cba823d47ef55edb956df3beacd132ea7`. Nothing was pushed. This coherent
two-file tooling commit makes failure evidence durable; it does not accept the
whole dirty baseline, complete the backend suite, or advance W00.

### B00b baseline evidence reconciliation — September 21

B00b's finite reconciliation is complete; **B00 remains blocked and is not
accepted**. The pre-documentation observation has 662 pending entries: all 646
September 16 entries remain pending with their dated classifications, plus 16
newly classified paths. Totals are 241 modified and 421 untracked: 163 beta
implementation, 417 tests/build tooling, 56 documentation, 10 generated output,
two interrupted/incomplete and 14 unrelated-work entries. Classification is
triage, not content approval, test evidence or staging permission. The existing
[B00 inventory](beta-b00-worktree-inventory-2026-09-16.json) contains the dated
addendum; the complete external snapshot is SHA-256
`f17ec9e34679122a8ba328b5246bca343338962a8b432160f3090d082c6af1d9`.

The external 24-receipt backend index is SHA-256
`64e8a6a2172e771ff9a40f998208eb00034e29e21fee933a0f449b8aef2f032b`.
The interrupted 7,606-test legacy run still has only 3,668 passed, 25 failed and
seven skipped phase-report counts. No final journal exists, so its exact failure
and skip IDs, unique outcomes and unexecuted set are unavailable. All 25 old
failed reports remain unknown. The two failure IDs in later journals belong to
separate selections and do not identify or reduce that count. A separate
post-timeout observation confirmed owned-tree and isolated-port cleanup only; it
does not turn the timeout or any test into a pass.

The one approved current selection, `tests/test_windows_stage_recipe.py`, passed
23 unique synthetic tests on its first run: 69 passed phase reports, zero
failures/skips/retries, completed termination, no active ID, confirmed cleanup
and all 983 bound inputs unchanged. Receipt SHA-256 is
`2e96d7482629bc71fd6d53a3567f68501d9327ecb0934f5500a23a38ff1503ea`;
journal `cd31e014903718d45e9f8a2244e90339cb58943dab8db28567d6771d9dbf09f6`;
input manifest `ae4785ad05659f74dbcbe659b9ca6bd1ae71a331263a3bb999be9380263bea82`.
This is recipe-unit evidence, not a coherent recipe-only commit or package,
native, model/GPU, installation or release acceptance.

The final B00b privacy batch `b00b-privacy-01` passed eight unique tests—the
full-checkout scanner and seven canaries—with zero failures, skips or retries in
27.750s. Cleanup was confirmed and the bound source was unchanged. Runner
receipt SHA-256 is
`b074deb51f345c2e634ed576590f564d169e520a91d422d316644670223a08c1`.
The full `git diff --check` also exited 0. These checks cover the observed dirty
checkout and documentation diff; they do not accept the whole baseline.

Both read-only custody-refresh interfaces timed out. Historical PRIVATE remains
historical, current visibility is unknown, and no publication or visibility
mutation occurred. Current coverage beyond the bound B00a/B00b selections is
unverified; full-suite collection/rerun, personal provider/app state, fixed user
ports, native windows, model/GPU and package/release paths remain safety-held.
Product/test commits remain held across route/generated-contract/untracked
dependency boundaries. The reviewed commit scope is exactly this ledger and the
dated inventory addendum. Any resulting local commit is identified by Git history
and handoff rather than embedded here; no publication is authorized or claimed.

### B00c Windows stage-recipe source custody — September 23

B00c reviewed one coherent 16-file untracked custody group: three offline Windows
recipe/inventory command scripts, five directly required infrastructure modules
and eight synthetic test modules. Tracked path-policy, owned-process, domain,
test-configuration and bounded-receipt inputs were hash-bound execution
dependencies rather than new custody files. No adjacent packaging, acquisition,
staging or release helper was included.

Review first found three bounded readers that compared the named path before and
after consumption without binding the opened descriptor. Staged-scope review then
found the same gap in the desktop dependency input hasher. All four corrections
now check device, inode, file type, link count, size, timestamps and Windows file
attributes on the opened handle, while retaining exact full-mode and file-attribute
comparison between the two path snapshots and the existing symlink, reparse-point
and hard-link refusals.
Windows may assign different permission bits to an opened `.exe`, so handle
comparison intentionally uses `stat.S_IFMT` rather than requiring identical full
mode bits. Redirected-open regressions cover reviewed inputs, build output and
provenance, and an ordinary synthetic `.exe` covers the Windows mode distinction.

The first full selection exposed the `.exe` mode distinction with two failures;
receipt SHA-256 is
`199b4c4a7012d774207f10f3d88ffff29afbe16717b800df3b0f05b4f39cd8ff`.
After the focused correction, five unique proxy-reader checks passed with 15
passed phase reports, zero failures/skips and unchanged source; receipt SHA-256 is
`5949ee0c51025d082f179d29a5a95b677184789a48b637b16a5764ea5f06c51d`
and journal SHA-256 is
`f948692d6585e6535db7518c86a4eb2f380c7ac1440ac2d52030db05e36b9e10`.
The final eight-module selection then passed 123 unique tests with 373 passed
phase reports and zero failures in 4.344s. Two checks were skipped because this
Windows environment could not create the required symlinks:
`test_export_rejects_symlinked_lockfile` and
`test_symlinked_lock_or_parent_is_rejected`. They remain unverified capability
checks, not passes. Cleanup was confirmed and all bound inputs were unchanged.
Receipt SHA-256 is
`3b857080a4be1c4b835c1778bee30bd6da7806ab62571b4f173e57ddafee06be`;
journal SHA-256 is
`405829f709e48509b507bcd3c5f4af5a9f55d1f50481e77c808b629d523cd222`.
That batch is preserved as historical evidence but is superseded by the final
post-staged-review gates. Six unique opened-reader checks passed with 18 passed
phase reports and no failures/skips; receipt SHA-256 is
`1cedd2ca2e8a65ff3f6e921b6d578b3b365352d240df5c716c9eb8d156753a44`
and journal SHA-256 is
`60a13cf90c0eb3af349d50a7e3404078c311c4e339f8c8e1e5c062ce238f464f`.
The final eight-module batch passed 124 unique tests with 376 passed phase reports,
zero failures and the same two Windows symlink-capability skips in 4.453s. Cleanup
was confirmed and all bound inputs were unchanged. Final receipt SHA-256 is
`47a06ca3e9ac6c613b85e6e0a45ad8b25fb19b338cf20cfa72efb871b492958a`;
final journal SHA-256 is
`105006fda76273d5b295902813b2d6b8168a15729135914c0964b2b96abeea6f`.

The bounded full-checkout privacy scan passed one unique test with three passed
phase reports, no failures/skips, confirmed cleanup and unchanged bound inputs.
Receipt SHA-256 is
`a3474029ac4dada0ade4dfdc28667893ca459f9e04b2dca4f1f16f4793f41613`;
journal SHA-256 is
`f206d98082eb627d594448512fa60eb740b928bfe3d2586cedb68b1a184d4cd4`.
The privacy gate was repeated after the staged-review correction and again passed
one unique test with three passed phase reports, no failures/skips, confirmed
cleanup and unchanged bound inputs. Its final receipt SHA-256 is
`4c25e9971e678af22e8ae26e19f00c77a190fd6559897b5f59ddedac3b545705`;
the unchanged journal content has the same SHA-256 above.
This is source-custody and synthetic-test evidence only. It does not prove a
package, native execution, installer, network-isolated build, model/GPU path,
release candidate or publication. B00 remains blocked and no push is authorized
or claimed.

### B00d bounded baseline reconciliation — September 23

The main B00 status below now includes B00c's locally committed 16-file Windows
recipe custody group (`ae22e99`) instead of stopping at B00b. At the start of
this slice, 636 other worktree entries remained pending with zero staged files;
this count is a point-in-time status, not 636 confirmed defects or authorization
to blanket-commit them. The original interrupted backend run's 25 failed phase
reports still lack exact test IDs and are neither reproduced nor resolved by a
passing selected test.

One historically identified failure was rechecked, without changing its dirty
source or fixture:
`tests/test_agent_orchestration.py::test_orchestration_manifest_covers_every_agent_route_and_only_real_routes`.
It passed on the current checkout (one unique test, three passed phase reports,
zero failures/skips), with completed termination, confirmed owned-process cleanup
and unchanged hashes for the four selected test/runner inputs. The bound input
set is intentionally partial: other modules imported by the application remain
current-tree inputs, not an immutable release artifact. Receipt SHA-256 is
`f152d1ca270c4f3674c86bc7b7f039bebd43554203b7eaea7071ad2da6e96c71`;
journal SHA-256 is
`73efdde05e1c672e08a8e42f33ec7cfe118b482571a018728a05abd2d1e665f8`.
This recheck confirms that named route-contract failure remains closed in this
selection. A second, non-additive run of its complete four-test module also
passed (12 passed phase reports, zero failures/skips), with completed termination,
confirmed cleanup and unchanged selected inputs. Its receipt SHA-256 is
`8c677d93c3f3fdfd7416064d35caa7e0554b8a056fcc3d6f95008100f75606da`;
journal SHA-256 is
`8f232a4a757721fcf115b37f1a25fb66f3c577da5c3ab7c31c8abde1903c5f94`.
These overlapping selections do not map the other historical failures, finish
the full backend baseline, or establish native, model, package or beta acceptance.
B00d's bounded full-checkout privacy selection also passed eight unique tests
with 24 passed phase reports, zero failures/skips, unchanged bound inputs and
confirmed cleanup. Its receipt SHA-256 is
`7c274e211556980ddf167047088d2408f1c447936276fe1d420f0dde8f3c8b90`.
B00 remains open; B01 and W00 have not started.

### B00e remaining-worktree disposition and first broad backend shard — September 23

The 636 `git status --short` entries expand to 645 individual pending files when
untracked directories are enumerated. All 645 have a dated category: 630 match
the September 16 inventory and the remaining 15 match B00b's September 21
new-entry addendum. **Zero paths are unclassified.** The 16 original inventory
paths no longer pending are the B00c Windows recipe group plus this ledger; no
pending path was deleted or blanket-staged by this reconciliation.

| Current category | Individual pending files | Disposition |
| --- | ---: | --- |
| Beta implementation | 163 | Preserve for coherent code review and checkpoint-specific acceptance. |
| Beta tests/build tooling | 401 | Preserve with the implementation or build boundary they verify. |
| Documentation | 55 | Review against observed behavior before committing. |
| Interrupted/incomplete | 2 | Preserve; frontend notice inventory belongs to B08. |
| Unrelated post-beta work | 14 | Preserve outside this beta workstream. |
| Generated output | 10 | Preserve in place; do not stage as source. |

The 15 addendum-classified paths still pending form one Agent controller/MCP
route-contract source-and-test group (three implementation files and twelve
test/support files). Their classification is triage, **not** content approval or
permission to commit the group. Historical hashes do not certify current bytes.

The first broad backend shard selected ten Agent controller, orchestration and
MCP contract modules, excluding listener/process integration. It passed **199
unique tests** with 597 passed phase reports, zero failures/skips and completed
termination in 40.235s. Twenty-two selected test/source inputs were hashed before
and after; all were unchanged, and owned-process cleanup was confirmed. The
receipt SHA-256 is
`ef78475d6f95b70a192c794d93c512aead40b8feda3995668659e83f83dce1f4`;
journal SHA-256 is
`916aa35f448eda47bd03d403d1ad8de1ce5528d985a6ddcfd83b99ac641c02c0`.
Other imported application modules were current-tree inputs but not part of the
22-file hash boundary. This shard overlaps earlier selections; its count is not
added to prior pass totals. It is synthetic/in-process evidence, not native
approval, real MCP host lifecycle, model/GPU, package, or release acceptance.
The bounded full-checkout privacy selection passed eight unique tests with no
failures/skips and confirmed cleanup; receipt SHA-256 is
`ff2c008b6871c918c07c235bb72d0cda0058f10f1bf7391c3a5428f57bd803fc`.
The historical 25 failed phase reports remain unidentified, so B00 remains open.

### B00f controller/MCP dependency review — September 23

The 15-file addendum group was reviewed against its current diffs, including
the disposable owned-listener harness. Its v23 controller manifest selects 72
Agent routes and five runtime routes while excluding the web-fetch capability
metadata, private-body message search, and native session-parameter control.
Current API documentation and one browser assertion were aligned to v23;
historical checkpoint documents retain their original v22 claims as history.

Focused current-tree validation passed: **14 backend tests** across the direct
MCP probe, owned real-loopback integration and orchestration manifest; **26
frontend contract tests** across three files; **two Chromium controller-panel
journeys** at 360 and 1440 px; and `npm run check:api`. The backend run used a
disposable OS-assigned loopback port and synthetic user/provider roots. Its
process tests assert hidden windows, bounded streams, timeout cleanup and
confirmed owned exit. The browser server's test port was free after the run.
These are scoped source/browser results, not protected native approval,
packaged MCP lifecycle, owner-model, or release evidence. No app/model in the
owner's running session was stopped or restarted.

**The candidate is not commit-ready as 15 files.** At HEAD, the three newly
excluded local API routes are absent. Their current definitions also depend on
dirty `local_agent_routes.py` and `agent_catalog.py`; the matching v23 OpenAPI,
generated TypeScript client and OpenAPI test are dirty as well. The browser spec
contains other unrelated pending changes. A commit of only the 15 addendum
files would produce an internally inconsistent checkout; staging the entire
dependent files without review would violate source custody. No files were
staged, committed or pushed in B00f. The next bounded action is to review these
route/contract dependencies as coherent exact hunks or a larger reviewed group,
then rerun the affected tests before any commit. B00 remains open.

### Evidence corrections that supersede older wording

- Full privacy scan `6f25d8` **passed** after the owner-approved quarantine.
  The older `67bc62` result with 3,184 findings is historical, not the current
  unresolved privacy state. Recheck the final proposed publication inputs.
- Historical unsigned MSIX normalization/payload repeatability was demonstrated:
  34,014,174 bytes, normalized SHA-256
  `bdf694073425cebe14595ebdd48d0fa4cea6397a5f969ec7176969a1ead49f73`.
  This was a dirty-snapshot source-shipping candidate, not the agreed compiled,
  signed beta, not native byte-for-byte reproducibility, and not installation.
- The latest two-phase packaged MCP cache/restart/outage execution was
  **canceled** by the owner. There is no passing receipt for it. Its 37 focused
  harness tests and the older single-launch synthetic browsing probe do not
  establish V11 restart/outage acceptance.
- Native installation, actual update execution, compiled-package acceptance,
  genuine model/hardware and current native approval journeys remain unproven.
  The update handoff evaluator still cannot apply/install an update.
- Production accounts and payments are deferred, not beta release blockers.
  Historical implementation/tests remain preserved, with no service activation.

## Authoritative beta requirements and acceptance ledger

The [Windows beta acceptance gates](beta-acceptance-gates.md) define the exact
V01–V18 and W00–W08 closure predicates, evidence levels, negative cases and
content-free receipt fields. The gate contract is not a second status ledger:
all current results, blockers and next actions remain here. Its structural
inventory test guards definition completeness, not application correctness.

The source scope for every row below is the starting dirty snapshot at
`7888064a1cf25703b6e312da97868edd4573c5b3`; **no release candidate commit or compiled,
signed artifact digest exists yet**. Vxx are acceptance scenario IDs from the
approved plan, not claims that a corresponding executable test has passed.
For each row, replace the source/artifact binding with exact current evidence
when its selected checkpoint runs. Historical receipts later in this file retain
their original code/artifact scope and cannot close these rows automatically.

| Requirement / user journey | Beta classification | Implementation status | Acceptance IDs | Latest result / required scope | Limitation / next concrete action |
| --- | --- | --- | --- | --- | --- |
| B00: recoverable, private, reviewed baseline | Required | All 645 individual pending files classified by the dated inventory/addendum; frontend and B00c recipe groups committed locally; B00f found the 15-file controller/MCP candidate is not dependency-closed | B00-CUSTODY, B00-INVENTORY, quality commands above | Blocked / B00e 199-test shard and B00f focused 14 backend, 26 frontend, two browser checks passed; 25 legacy failed phase reports remain unmapped; current source visibility unverified | Review exact route/OpenAPI/client dependency closure before staging; continue bounded backend shards; confirm custody before any source push. |
| B01: supported navigation/actions and frozen release inputs | Required | Existing route/capability manifests; beta classifications not yet implemented | V02, V13, V17 | Not run / browser + source contracts | Map every route/action; hide unavailable actions without deleting data; record owner dependencies. |
| B02: launch, child windows, exit and recovery | Required | Owned lifecycle/hidden-process boundaries exist; native acceptance incomplete | V07, V13, V17 | Not run / native + ten repeated cycles | Verify one owner, port refusal, recovery and cleanup without affecting unrelated models. |
| B03: model-free projects/chats, draft and durable lifecycle | Required | Durable catalog/composer paths exist; current acceptance incomplete | V02, V03, V04, V07 | Not run / packaged + native restart | Verify folder select/cancel, CRUD/search/pin/archive/restore/delete/export/fork, draft and interrupted states. |
| B04: acquire, use, switch and unload supported models | Required | GGUF/llama.cpp adapter exists; real CPU/NVIDIA profiles unaccepted | V05, V06, V07 | Not run / installed app + real CPU/NVIDIA | Freeze artifacts/licenses/runtime/settings; prove inference, stop/switch and test-owned process/VRAM release. |
| B05: exact workspace approval and truthful artifacts | Required | Workspace tools/diffs/artifact paths exist; native end-to-end proof incomplete | V08, V09, V17 | Not run / native protected approval | Verify stale/reparse/traversal rejection, cancellation and actual-file-only artifact cards; resolve PDF shipping gate. |
| B06: curated MCP discovery/setup/use/revoke/remove | Required for declared curated profile | Registry/cache/managed boundaries exist; complete packaged/native lifecycle unaccepted | V10, V11, V17 | Not run; latest outage execution canceled / packaged + native | Complete real restart/exact-cache outage journey; then checksum-pinned local and loopback-remote lifecycle tests. |
| B07: useful, truthful analytics and mini-window | Required | 20 contracts, 18 conditional paths; not 20 measured metrics per session | V12, V13, V17 | Not run / storage → API → rendered UI + native mini-window | Hand-compute fixtures; preserve unknown vs zero, coverage, denominator, provenance, read-only ingestion. |
| B07-X: hypothesis linkage and claim grounding | Experimental/unavailable | Required adapter evidence remains incomplete | V12 negative/unavailable states | Not run / evidence contract + UI | Keep `logic.hypothesis_test_linkage` and `outcome.agent_claim_grounding` unavailable until supported evidence exists. |
| B08: compiled, source-private MSIX payload and notices | Required | Existing MSIX tooling; first-party compilation and notice closure missing | V18, V17 and all relevant packaged journeys | Not run / clean private build + compiled payload | Bounded representative Nuitka proof with pinned toolchain, maximum two corrections; resolve notices or remove unresolved payload. |
| B09: signed per-user install, verified update/recovery | Required | Verification/staging/handoff foundations; actual native executor missing | V01, V14, V15, V16, V17 | Not run / clean Windows + native update | Owner identity/keys; durable operation journal, exact reviewed consent, retention/recovery, no reboot/schema downgrade misuse. |
| B10: usable supported layouts and accessibility | Required | UI exists; no current full acceptance matrix | V02–V04, V08, V12–V14 | Not run / native/browser sizes and scaling | Test 1280×720, 1366×768, 1920×1080; 100/125/150/200% supported scaling; keyboard, focus and failure states. |
| B11: signed RC, clean-machine pilot and owner acceptance | Required | No qualifying release candidate | V01–V18 | Not run / exact RC and clean CPU + physical NVIDIA | Full quality gate, two consecutive packaged smokes, zero P0/P1, cleanup, owner review, approved binary-only publication. |
| W00–W08: bounded local typed multi-model workflow | Required | Approved scope; not started and gated on B00/native foundations | W00–W08 | Not run / exact installed runner + supported local text/image/audio profile | Implement only after its gates: 32 nodes, 16 model nodes, two concurrent stages, one active run; no arbitrary code or remote connectors. |
| Post-beta: accounts/payments/teams/hosted/social/new integrations | Deferred | Partial source/tests retained | Outside beta gate | Not run for release / no activation | Do not expand beta scope. A later owner decision is required. |

## Prioritized beta blocker list

1. **B00 / P1 — incomplete backend baseline and missing failure index:** 7,606
   tests collected; the 30-minute run ended with last-saved counts of 25 failed
   reports and no final per-test receipt. The durable incremental recorder is now
   implemented and validated. Historical deduplicated selections have 488 passes;
   the exact orchestration-contract failure is closed by the independent September
   21 receipts above, while the old 25 failed reports remain unmapped and cannot
   be recovered from counts. B00a closed
   the held MCP harness defects with 6 regression, 4 real owned-listener integration
   and 8 privacy tests passing under bounded cleanup. B00b reconciled the 662-entry
   classification and existing receipts. B00c's final Windows recipe selection
   passed 124 tests with two capability skips; B00d's four-test orchestration
   module and B00e's ten-module/199-test shard passed; B00f's 14-test
   listener/probe selection also passed. These overlapping selections
   do not complete the current backend baseline. Continue
   fresh bounded coverage and reviewed custody.
   Do not increase the timeout, blindly repeat the full suite, infer causes from
   counts, or broaden into unrelated product implementation.
2. **B00 — browser evidence boundary:** all four identified failures now pass
   after the bounded fixture/spec repair above. Six original skips remain skips;
   the full suite was not repeated after changing only these test inputs. Record
   this scoped evidence honestly; it is not native approval or installation proof.
3. **B00 — final evidence reconciliation:** frontend tests, API, types, build and
   bundle checks passed; all four browser failures passed targeted recheck.
   Preserve the completed and partial receipts with their exact source scope;
   final privacy/diff checks cover the reviewed documents and changes.
   The original missing-source and quarantined-helper defects are repaired,
   not remaining open defects. No automatic broad rerun or budget increase.
4. **B00 — source recovery/commit gate:** initial files are classified but not all
   content-reviewed. The four-file frontend custody group and 16-file Windows
   recipe group are committed locally. B00e confirmed that 645 then-pending
   individual files had a dated category, but most content is not yet reviewed.
   B00f found that the 15-file controller/MCP candidate depends on additional
   dirty routes, OpenAPI and generated-client inputs; it cannot be committed in
   isolation. No blanket stage/commit. Snapshot preservation alone does not meet
   full version-control recovery exit criteria. Review coherent dependency
   groups individually after their targeted gates.
5. **B00 custody owner input:** separate public binary-only release repository
   not yet identified/verified; never reuse the private source remote to publish
   binaries by copying its history.
6. **B01 owner inputs:** package identity/publisher, public signer fingerprint and
   update verification key, owner-controlled signing location, precise clean
   Windows/NVIDIA test environments, approved model artifacts/resource limits,
   support contact and beta terms are not yet verified. Do not collect secrets.
7. **B02–B07 / P1 acceptance gaps:** native lifecycle, durable usability, genuine
   model/VRAM behavior, exact native approvals, MCP lifecycle/outage, and metric
   truth still need the corresponding real executions, not source assertions.
8. **B08 / P1:** first-party compilation, clean-source repeatability, dependency
   notices and opaque PDF-worker closure are required before distribution.
9. **B09–B11 / P1:** signed install, actual update executor/recovery, clean-machine
   retention/uninstall, supported UX and owner pilot acceptance remain open.

The next recommended owner-selected action is a bounded B00 baseline repair,
**not** automatically starting B01. Beta closes only with zero P0/P1 issues, all V01–V18 required scenarios on
the exact compiled/signed candidate, full quality/privacy gates, appropriate
CPU/NVIDIA/native environments, two consecutive packaged smokes, no test-owned
process/model remaining, owner approval and published known P2 limitations.

## Historical feature audit (retained evidence, not the current queue)

The following sections preserve the earlier checkout audit and its receipt IDs.
Read all phrases such as "current", "latest" and "fresh" in these historical
sections as relative to that audit. The B00 ledger and explicit corrections above
control current release status and sequencing.

## How to read this matrix

- **Implemented** means a source-level path appears to exist in this checkout;
  it does not imply that it has passed a current verification run.
- **Partial** means a bounded foundation or contract exists, with meaningful
  behavior or acceptance gates still missing.
- **Missing** means the user-facing capability or required production path is
  not available in this checkout.
- **Tested evidence** records selected results only; any cell marked pending or
  not tested is an evidence gap, not an implementation judgment. Results below
  are synthetic or offline unless explicitly stated; no real provider sessions
  or account data were used.
- Local-agent and metrics receipts were reported earlier on 2026-09-12 before a
  pause; they were not rerun in the resumed docs phase. Release/update,
  privacy, and frontend build/check results are fresh receipts supplied by the
  root audit during this phase.
- **Released / installed** describes public availability, not source status.
  No supported installer or production account/billing service is established
  by this matrix.

## Local agent, models, and tools

| Area | Capability | Implementation status (implemented / partial / missing) | Working-tree evidence / paths | Tested evidence for this audit | Remaining verification / release state |
| --- | --- | --- | --- | --- | --- |
| Local Agent projects and chats | Durable project/chat metadata, navigation, and local conversation workflow | Implemented | `frontend/src/features/agent/AgentPage.tsx`; `src/prompt_enhancer/application/local_agent.py`; `src/prompt_enhancer/application/agent_catalog.py` | Latest selected core backend subset passed 255 tests across 7 modules (38.61s; command recorded below). Historical HTTP probe `fbcba7` passed empty retained-chat cold restart. Current packaged probe `2449de` used two staged-app launches and fresh browser contexts to preserve and reopen three user messages, two completed replies, and one stopped reply, then resumed read-only through the UI. | The offline CPU fixture is non-inference and termination was forced. Real model capability, GPU, graceful/native UX, owner, and installer acceptance remain open. |
| Composer attachments and artifacts | Attachments, artifact capture, artifact listing/viewing | Implemented | `frontend/src/features/agent/AgentComposerAttachments.tsx`; `frontend/src/features/agent/AgentArtifactsPanel.tsx`; `src/prompt_enhancer/application/agent_attachments.py`; `src/prompt_enhancer/application/agent_artifacts.py` | Reported earlier same date: synthetic frontend `npm test -- --run src/features/agent/AgentComposerAttachments.test.tsx src/features/agent/AgentArtifactsPanel.test.tsx` — 2 files, 54 passed (7.11s); backend `python -m pytest -q tests/test_agent_attachments.py` — 28 passed (9.13s). | No live file/media or native acceptance; packaged behavior unverified. |
| Local Agent workspace | Bounded workspace selection, file inspection, proposed edits, reviewable changes, and protected operations | Implemented | `frontend/src/features/agent/AgentWorkspacePane.tsx`; `src/prompt_enhancer/application/local_agent_workspace.py`; `src/prompt_enhancer/application/local_agent_editor.py`; `src/prompt_enhancer/application/local_agent_discovery.py`; `docs/adr/0016-local-agent-workspace.md` | Packaged browser/HTTP probe `8ab4e5` passed no-model project/chat creation, file GET/editor/diff, disabled Apply, CSRF 403/native-unavailable 503, traversal 403, discard/reopen, and stale-review 409 after controlled synthetic mutation. The fixture was restored unchanged; external requests, page errors, server 5xx, and forbidden mutations were zero, and owned browser/server resources and ports cleaned up. Combined workspace/restart/streaming receipt tests passed 235 (`9b82c0`); post-run `d0a5f2` matched all 2,584 candidate files with no extras. | This is scoped packaged read/refusal/stale evidence, not a native-approved write, model/GPU, native GUI, or installer acceptance. Earlier runs stopped on corrected harness expectations, not production defects. |
| Local model catalog/import | Model metadata, compatibility checks, revision/license provenance, and local acquisition foundations | Implemented | `docs/local-model-compatibility-matrix.md`; `docs/model-manifests/local-compatibility-catalog.md`; `src/prompt_enhancer/application/local_models.py`; `docs/adr/0013-local-model-runtimes.md` | Metrics/model provenance subset: covered in the audit's selected offline suite (285 passed, 3 failed, 1 skipped overall; failures detailed below). No live catalog/network/model test. | Recheck pinned revisions/licenses, catalog freshness, and supported combinations. |
| Model download and integrity | Staged/download lifecycle with progress and verification contracts | Partial | `src/prompt_enhancer/application/local_models.py`; `docs/local-models-and-agent-access.md` | No focused result from this audit. | Exercise cancel/restart/disk/integrity and actual supported runtime acquisition; no model bundle ships by default. |
| Model start/stop and placement | Local runtime lifecycle, health, configuration, and capability-gated placement | Partial | `frontend/src/features/agent/AgentRuntimeControl.tsx`; `src/prompt_enhancer/application/local_models.py`; `docs/local-models-and-agent-access.md` | Synthetic protocol gate `cdd760` passed bounded JSON/SSE, early disconnect followed by a fresh request, rejection cases, and cleanup. Packaged probe `775cf5` registered the manifest-bound fixture, reached CPU-ready state with GPU layers zero, and explicitly deactivated it before owned cleanup. | The fixture declares no inference capability and contains no real model weights. Hardware/native acceptance, real CPU/GPU model behavior, and model-runtime-port release were not independently established; that port is not exposed by the public status payload. |
| Images/audio and advanced model modalities | Modality controls gated by detected runtime/model capabilities | Partial | `docs/local-model-compatibility-matrix.md`; `docs/local-models-and-agent-access.md` | No actual-model or attachment test in this audit. | Verify against supported models; unsupported combinations must remain unavailable. |
| Prompt check | Local prompt structure/checking workflow | Implemented | `frontend/src/features/prompt-check/`; `docs/adr/0015-prompt-check.md` | Prompt-check and session-reader selected test modules: **14 passed** (25.51s, receipt `8b03eb`); synthetic coverage includes deterministic cues/context, commentary failure/bounds, history HTTP and MCP. | Verify current UI/API behavior and explanations; not a universal quality or developer score. No real provider sessions were read. |
| MCP analytics server | Allowlisted, read-only metric/calibration surface with no raw transcript or unrestricted query interface | Implemented | `docs/adr/0014-read-only-agent-surface.md`; `docs/openapi.json`; analytics MCP implementation under `src/prompt_enhancer/` | Not separately tested in the reported agent batch. | Run current protocol/security tests and verify allowlist; no raw-session MCP capability is intended. |
| Agent controller MCP/API and managed runtime | Scoped local controller operations and managed MCP server/process lifecycle | Partial | `frontend/src/features/agent/AgentMcpConnectionsPanel.tsx`; `frontend/src/features/agent/AgentMcpStorePanel.tsx`; `src/prompt_enhancer/application/mcp_managed_runtime.py`; `src/prompt_enhancer/application/agent_mcp_connections.py`; `src/prompt_enhancer/interfaces/http/agent_mcp_routes.py` | Earlier same-date focused batch had 71 passed / 5 failed; failures were migration-fixture expectations. A selected migration batch passed 106 tests across four files (118.94s; receipt `63ece2`). Latest MCP server-management selection: **93 passed** (22.64s, `d43ba2`), covering synthetic plans/configuration/vault adapter/revoke/install-update-rollback-recovery HTTP and historical migrations. Separate connections/client-config tests passed 28 (2.59s, `b44d49`), covering synthetic durable credential restart/rotation/revocation/scope and provider-config validation. | Historical schema fixtures were corrected without weakening production migration behavior. No actual external client or native/provider acceptance was performed; broader supported-schema recovery remains to be verified. |
| Native acceptance | Guarded native acceptance workflow for app/controller integration | Partial | `frontend/src/features/agent/AgentNativeAcceptancePanel.tsx`; `docs/agent-controller-api.md` | Not performed; native/browser/controller acceptance was not authorized in the audit. | Not done. No native or owner acceptance may be inferred from synthetic tests. |
| MCP Store browsing | Bounded registry browse/review UI and metadata | Partial | `frontend/src/features/agent/AgentMcpStorePanel.tsx`; packaged MCP Store probe and receipt tests | Backend run `8dd201` passed 38 tests for bounded normalization, restart cache/search/cursor, conflicts, icon/proxy, authenticated read-only HTTP and injected transport refusal. Packaged candidate-review4 probe `199e40` used an explicitly injected fictional registry client through the real `/agent` UI and authenticated APIs: two tiles, normalized search to one result, exact review/provenance and preview-only boundary, disabled Save setup plan, then return to the catalog. Catalog calls were 2, exact detail/history calls 1 each, invalid calls 0; browser external requests, mutations and model/native/managed mutating requests, page errors and 5xx were zero. Candidate integrity and all owned browser/server/tree/handle/reader/port cleanup passed; 26 receipt tests passed independently (`2bad65`). | This did not contact the official registry, install or run anything, exercise cache fallback after restart, or provide native confirmation/security approval. There were zero refused non-loopback attempts in the guarded Python socket events; this does not prove OS/native-library network isolation. Forced termination was not native/graceful acceptance. |
| Remote annotation/model providers | Consent/redaction/budget-oriented boundary and synthetic development path | Partial | `docs/adr/0017-remote-annotation-providers.md`; `docs/work-packages/wp-21-paid-product-boundary.md`; `src/prompt_enhancer/application/jobs/service.py` | Offline automation/resource-policy coverage is included in the metrics audit batch below; no production provider call. | Production provider adapters/accounts, retention terms, budgets, redaction preview, and owner activation are not established. |

The following additional UI surfaces are present in the checkout but were not
individually functionally audited in this pass. Their listing is not a claim
that they are complete, production-backed, or tested end to end.

| Area | Capability | Implementation status (implemented / partial / missing) | Working-tree evidence / paths | Tested evidence for this audit | Remaining verification / release state |
| --- | --- | --- | --- | --- | --- |
| Session reader and timeline | Read-only session transcript presentation and event timeline | Partial | `frontend/src/features/session-reader/SessionTranscriptPane.tsx`; `frontend/src/features/session-timeline/SessionTimelinePane.tsx`; `src/prompt_enhancer/application/analysis/session_reader.py`; `src/prompt_enhancer/interfaces/http/session_reader_routes.py` | Prompt-check/session-reader selected modules passed 14 tests (25.51s, receipt `8b03eb`); reader scope covers consent/enabled/catalog gates, bounded synthetic Claude/Codex mapping, and HTTP. No live provider content was read. | Verify provider/source scope and native handling of boundedness, redaction and missing/unavailable history. |
| Task flow | Task-flow board, summary, timeline and audit views | Partial | `frontend/src/features/task-flow/TaskFlowPage.tsx`; `frontend/src/features/task-flow/TaskFlowTimeline.tsx`; `src/prompt_enhancer/application/` task-flow implementation | Not individually reviewed in the reported focused tests. | Verify UI/API consistency, evidence provenance and non-inference of completion. |
| Research lab | Research and metric-operability exploration UI | Partial | `frontend/src/features/research-lab/ResearchLab.tsx`; `src/prompt_enhancer/interfaces/http/research_routes.py`; `src/prompt_enhancer/application/analysis/method_research.py` | Research UI source test exists but was not in reported audit; no research-method efficacy evaluation. | Validate calculations, provenance, and any external/provider boundary before production claims. |
| Model-link experiment | Experimental cross-model/session link workflow | Partial | `frontend/src/features/model-link-experiment/ModelLinkExperimentPanel.tsx`; `src/prompt_enhancer/application/analysis/model_link_experiments.py`; `src/prompt_enhancer/interfaces/http/model_link_experiment_routes.py` | Source tests exist but not covered by reported test totals. | Remains experimental; validate identity/link correctness and privacy boundaries. |
| Onboarding | Local workflow setup and source onboarding | Partial | `src/prompt_enhancer/application/onboarding.py`; `src/prompt_enhancer/interfaces/http/onboarding_routes.py` | Not individually audited. | Verify first-run, recovery, consent, and no-login local path. |
| Source discovery | Local source discovery and review inbox | Partial | `frontend/src/features/local-sources/LocalSources.tsx`; `frontend/src/features/discovery-inbox/DiscoveryInbox.tsx`; `src/prompt_enhancer/application/local_sources.py`; `src/prompt_enhancer/application/discovery/` | Not individually audited; provider/session content was not read. | Verify discovery is bounded, consented, metadata-minimizing, and handles stale or unsupported providers. |
| Live mini window | Floating live local watch/radar window | Partial | `frontend/src/features/live-window/LiveMiniWindow.tsx`; `docs/live-metric-radar-pipeline.md` | Component tests exist but no result in reported audit; no native window acceptance. | Verify native lifecycle, loopback data, stale receipt handling, and resource caps. |
| Social and direct-transfer preview | Social workspace and prototype transfer surfaces | Partial | `frontend/src/features/social/SocialHubPage.tsx`; `frontend/src/features/social/directTransfer/DirectTransferPrototypePanel.tsx`; `src/prompt_enhancer/application/social/service.py`; `docs/adr/0018-shared-team-folders.md` | Source tests exist but no live transfer/service acceptance. | Treat as preview/prototype scope; network consent, auth, abuse controls, and release gates remain open. |

Latest selected Agent backend tests: `uv run --frozen --no-sync python -m
pytest -q --tb=short -W error -p no:cacheprovider tests/test_agent_catalog.py
tests/test_agent_session_forking.py tests/test_local_agent.py
tests/test_local_agent_completion.py tests/test_local_agent_receipts.py
tests/test_local_agent_usage_transport.py tests/test_local_agent_turn_details.py`
— **255 passed** (38.61s). This is a bounded synthetic backend subset, not
the full Agent acceptance suite.

Fresh built-frontend/disposable-loopback backend gate: `uv run --frozen
--no-sync python tests/support/convergence_loopback_runner.py --skip-build`
— **29 passed** (42.1s; receipt `9fa074`). Cleanup confirmed the listener was
released, model runtimes were 0, and temporary state was removed. The journey
covers durable project/chat no-model creation, reload, generation-settings
reread, retained history/search, rename/pin/archive/restore, workspace read,
catalog paging, metric inventory, and optional-chunk failure with draft
retention. It used the built frontend against synthetic API state; it did not
exercise native effects, a provider, or a model runtime.

Latest synthetic browser journeys: `npm run test:e2e --
beta-model-free-drafting.spec.ts beta-conversation-navigation.spec.ts
--workers=2` — **16 passed** (16.8s), covering no-model drafting and
conversation navigation/resizing/search at compact and narrow sizes; the
temporary test listener was confirmed gone after the run. After the
`DiscoveryScreen` lazy split, `npm run test:e2e -- discovery.spec.ts
--workers=1` — **4 passed** (5.2s), covering skip-link keyboard access,
synthetic discovery/review and metrics drilldown, and 900/600px viewport bounds.
These do not exercise a real model, native acceptance, or provider content.
After subsequent UI/runtime fixes, the real-loopback gate completed **29
passed** in 34.1s (receipt `7e786a`). Cleanup checks all passed, no model runtime
remained, and temporary state/listener cleanup completed. This result replaces
the earlier post-fix pending gate, but is still not native/model/provider or
packaged acceptance.

### Packaged check-later gate

The earlier authenticated HTTP result `fbcba7` remains valid only for its
empty-chat cold-restart scope and is separate from this browser result.
Historical build receipt `2d6a1a` and stage receipts `1518e0`/`fef114` remain
valid only for their old-wheel review1 scope. Fresh wheel review9 (`dc68f9`) produced
SHA-256
`8c21bcb640e3fcd7155e84922735959f5547151049468d77c938b167d6dbdc01`
(3,875,478 bytes), identical across two independent builds. Independent `7356c8`
verified all 91 dashboard entries and embedded graph `0e65f72d…`; `c39812`
verified 475 source modules. Fresh Python 3.13.15 stage receipt `9817bb` matched all 2,582 staged files and
is authoritative for current packaging. Its provenance still records a dirty
source snapshot and does not prove runtime closure or network isolation.
Earlier Python 3.13.0 stage evidence remains historical and is the runtime used
by the older packaged browser/workspace probes below. Python 3.13.15 launchers
were executed only against bounded synthetic entry stubs (`7bbc19`); the fresh
older candidate-review3 application was serve/browser tested by `2449de`, but the
native launchers and installed GUI were not exercised.

Candidate review4 (`b405eb`) assembled 2,588 files; independent `e2d7b7`
verified the exact set and hashes. Its 393,824-byte manifest is
`9e08c053102c6ce064e1dc9e663cf7bfb233d5469c3154640c606d6a34b9671a`.
The explicit stage-count pin retained the existing bound and passed 56 tests
(`1d47e3`). Wheel cleanup checks passed 12 selected tests (`d1d329`): an
unconfirmed process cleanup preserves only its unpublished workspace, while
completed owned builds can be cleaned. This candidate has been SDK-packed and
validated as described below, but not signed, installed or native-launched. Fresh candidate-review4 analytics probe
`89ce69` passed the consent/onboarding/catalog and 24-stored-metric journey:
two categories and three metric HTTP responses were verified; missing tokens
remained Unknown with 0/1 coverage and provenance, and fictional completion
prose yielded zero verification events and an Unknown pass rate. External,
model and mutation requests, page errors and server 5xx were zero. Fixture and
candidate integrity and all owned cleanup/ports passed. Termination was forced,
not graceful or native. Earlier restart/calibration/workspace probes below
remain scoped to their earlier candidates, not automatic candidate-review4 acceptance.

Candidate-review4 MCP Store probe `199e40` passed the packaged `/agent`
browse/search/review journey with an explicitly injected fictional registry
client. It rendered two tiles, normalized one search to one result, verified
exact provenance and preview-only boundaries, kept Save setup plan disabled,
and returned to the catalog. Catalog/detail/history calls were bounded and
valid; browser external requests, mutations and model/native/managed mutating
requests, page
errors and server 5xx were zero. Candidate integrity and all owned cleanup
passed. This is not official-registry networking, restart-cache, installation,
native confirmation, security approval, graceful shutdown or OS-level network
isolation evidence.

Probe `afea9d` passed one project, one empty retained chat, one unsent draft,
the model menu at 1280×800, 720×720, and 480×640, compact scrolling and
model/close pointer-hit checks, and one page reload/catalog reopen. The draft
was intentionally cleared before reload. Sends, model starts, external
requests, page errors, and server 5xx responses were all zero. Owned tree,
handle, and port cleanup passed, with peak process count 6 under the limit of
8; shutdown was forced owned-process termination, not graceful/native
shutdown. Focused frontend tests passed 77 (`bf51a1`).

Final packaged Python 3.13.0 workspace probe `51ccb0` passed five reads, one
reviewed create, edit, and move, and one stale-review refusal through the
public editor/lifecycle direct services. Cross-API ctime difference was
observed after real file mutation and birth time remained equal; there were
zero network attempts, stderr bytes, and temporary writes. Owned cleanup, port
release, and the retained external synthetic fixture were confirmed. This
supersedes initial probe `1603a1`, which passed the same workflow but observed
no ctime difference on only the initial fresh file. Parser tests passed 29
(`50b381`).

Packaged streaming probe `775cf5` then passed the real browser UI using the
manifest-bound offline fixture from protocol gate `cdd760`. It created one
project and retained chat, issued three sends and one Stop, observed four
incremental deltas across the normal and cancelled turns, and verified two
completed turns comprising six fixed synthetic chunks. The composer returned
ready three times. After one page reload/catalog reopen, both completed user
messages and both assistant replies remained. Browser stderr, external
requests, page errors, server 5xx responses, and browser-originated model
mutations were zero. The browser tree peaked at 7 processes under its limit of
8; the app limit was 4. Exact trees, handles, capture readers, explicit model
deactivation, and app-port release were confirmed. The model runtime port was
not publicly reported, so it was not independently checked; closure is bounded
by public deactivation and the owned app job.

Fixture rebuild `6636d8` produced the 12,288-byte executable with SHA-256
`5c60dca7ed579399f2f66fd63e684ece227c832965ff0233fce997f133662490`.
The fixture-only legacy compiler path validated its adjacent `cvtres` closure
within a two-process compiler budget; it did not change application budgets.
Source/pure checks passed (`36d111c6`), while runner plus protocol selection
`0d7f72` passed 59 tests with 15 overlapping cases, so those counts are not
summed. Current packaged probe `2449de` started candidate-review3's staged
Python 3.13.15 application twice under isolated synthetic homes. Phase one made
three sends and one Stop, observed four deltas, and completed two turns with
six chunks in total. A fresh phase-two browser displayed all three user
messages, two completed replies, and the stopped reply, performed one UI Resume, typed and
cleared an unsent editable draft, confirmed Send disabled and every protected
permission off, then preserved the view across reload/reopen. Post-browser HTTP
history and idempotent resume also remained intact; the model was stopped before
and after resume. External requests, page errors, server 5xx responses, and
restart-time forbidden mutations were zero. Browser peak was 7/8; both owned
trees, handles, readers, and app ports cleaned up, and the fixture was explicitly
deactivated. Post-run check `41130a` matched all 2,584 candidate files and the
manifest and found zero synthetic runtime processes. The runtime port was not
reported, so no independent model-port claim follows. This used a non-inference
CPU fixture and forced termination,
not a real model, GPU, graceful shutdown, native launcher, or installed GUI.

The corrected MSIX manifest/signature reader passed 58 synthetic tests
(`dfc116`). Staged-Python 3.13 source seam `b87d9b` additionally verified a real
cross-API ctime split with equal birth time and identity, exact reading,
wrong-length and over-budget refusal, source hash, and owned cleanup. This is
source CLI-reader evidence, distinct from the installed preflight module now
hash-verified in fresh stage `288bda`; neither result is Authenticode, signing,
or installation acceptance. Pure generation of a
candidate manifest and three code-derived logos plus launcher contracts passed
47 tests with one directory-link capability skip (`9a22af`). Independent check
`24df54` matched the exact external four-file set and every generated byte; the
XML was reviewed and the 150px logo visually inspected. These inputs were later
assembled and packed as described below; no signed, installed, or launched
application follows from this file-level evidence.
Native build `15c1d3` produced each fixed main/metrics launcher twice with
byte-identical output and owned cleanup; independent `a8a0ec` verified hashes,
sizes, zero PE timestamps, and GUI subsystem 2. Native probe `7bbc19` then ran
both launchers against fixed synthetic Python entries: exact exit codes 17/19,
two extra-argument refusals, four cleaned owned runs, 34 unchanged runtime
files, decoy working-directory/PYTHONPATH isolation, and job limit 1 all passed;
nine pure tests passed `7ccc50`. The real application, GUI, and model were not
run. Recipe/runtime tests passed 39 (`c09889`), while the
overlapping launcher/manifest selection passed 58 with one directory-link
capability skip (`da12cd`); these counts are not summed. Current browser-side
cold-restart evidence is recorded below; real native-app, signing, and installer
acceptance remain separate.

Historical old-wheel review3/review4 packages normalized to identical bytes
(SHA-256 `24c1ac5b151d5ae839e9909c710fdec07972f44ebff490bb3016432b1240b811`).
SDK unpack `7ca3eb` verified 2,584 payload members plus BlockMap; the
archive-only content-types footprint was also verified. Those packages were
unsigned and uninstalled and did not exercise the current wheel.

Current candidate-review4 SDK packs `2b0b83` and `ae55b0` passed validation,
all 2,588 payload hashes and owned cleanup. Their raw SHA-256 values differ:
`8dde498d01350ac6a366efcbdaf34bbc54955df010b2985e1f29d49170d4716b`
and `b3a17e982823df6c4c0fe17db8bfab4130d0bcc98e62be354308a7638d2662e3`.
Pre-sign normalization (`ad25fb`, `9ff5b0`) produced identical 34,014,174-byte
copies at `bdf694073425cebe14595ebdd48d0fa4cea6397a5f969ec7176969a1ead49f73`.
Independent byte check `2605d9` verified normalization of 5,180 ZIP timestamp
fields (2,590 local/central pairs; only their 20,720 byte positions were eligible
to change); both originals and candidate
remained unchanged. SDK unpack `874a5e` and `b5f290` each verified all 2,588
payload files, both archive footprints and one extracted footprint; the SDK
omits `[Content_Types].xml` from extraction but its archive bytes stay verified.
Validation and owned cleanup passed. Independent root check `e3694a` matched
normalized hashes, payloads and candidate integrity. Root selections passed
36 pack/unpack tests (`ef1296`) and 20 canonicalization tests (`8d760d`).
This is normalized same-snapshot repeatability, not native SDK-byte or clean-HEAD
reproducibility, signing, installability, native launch, notice closure or privacy clearance.

Historical candidate review3 (`1dfa60`) assembled and hash-bound all 2,584 files;
independent `27daa7` verified the candidate and found zero findings in the two
selector files. SDK review8 (`a9a60c`) and independent review9 (`64889f`) both
passed with validation and cleanup. Normalization receipts `0791a7`/`4a29e9`
yielded two byte-identical 33,952,451-byte unsigned packages with SHA-256
`4a16c1a3ff9b0f50fd9a56ebd9e07141fe8a6c45f6d239185735f4014267b223`.
Full unpack `ab50de` verified all 2,584 payload files, one extracted SDK
footprint, and both archive footprints with cleanup; no MakeAppx process
remained. This proves repeat packaging of the same reviewed staged snapshot
after timestamp normalization, not reproducible native SDK bytes or current
source HEAD. The packages remain unsigned and uninstalled. One combined
nine-file selection covering restart/streaming receipts, candidate/stager,
canonicalization, SDK unpack/output/pack, and notice inventory passed 264 tests
(`d4c275`); this is bounded helper coverage, not a full suite or runtime
acceptance.

Fresh notice inventory `f0a2e4` covered all 43 distributions in the current
candidate and found every declared notice present. External renderer `73630e`
then emitted a deterministic 223,889-byte partial Python/runtime notice bundle
for 55 distribution license files plus CPython (SHA-256
`b65752244fdcba848c357a0465987c69e82c75049845d34842f7b3ed2cedd182`).
Independent `dc4d58` rebound every payload and all 43 sections; second render
`c3ca5c` matched the same bytes. Renderer/inventory/candidate selection passed
82 tests (`1236e9`). The bundle remains external and is not embedded in the
package. Frontend notices, the application's own license, and the proxy-tools
metadata/source-license conflict remain open; this is not legal approval.

## Ingestion, metrics, and calibration

The focused offline audit, reported earlier on the same date, selected 24 test modules across metrics, analysis,
calibration, automation, ingestion, and provenance: **285 passed, 3 failed,
1 skipped** (202.94s). All fixtures were synthetic/content-free; this did not
test real provider imports, real sessions, network-backed model behavior, or
end-to-end artifact/export. The three failures were stale schema-version
assertions: `tests/test_analysis_job_queue.py` expected 65 while current schema
is 67; `tests/test_calibration_report_persistence.py` expected 64 while current
schema is 67; `tests/test_calibration_cases.py` expected `PRAGMA user_version`
64 while current is 67. One local-model provenance symlink test skipped because
the OS could not create symlinks. This is not a 100% pass. A fresh targeted
regression batch then ran `tests/test_mcp_managed_runtime.py`,
`tests/test_analysis_job_queue.py`,
`tests/test_calibration_report_persistence.py`, and
`tests/test_calibration_cases.py`: **106 passed** in 118.94s (receipt
`63ece2`). Historical schema fixtures were corrected; production migrations
were not weakened. The full 24-module batch has not been repeated, so its
earlier aggregate remains the complete broad-scope receipt.

A separate current run selected all 25 `tests/test_metric*.py` modules. Its
first pass had 302 passes and four stale terminal-schema assertions; after a
reviewed test-only correction preserving historical migration checksums, the
same 25-module selection passed **306 tests** in 97.23s (`7684cd`). This is a
metric-named module sweep, not a rerun of the historical mixed 24-module
metrics/calibration/automation/ingestion/provenance selection.

| Area | Capability | Implementation status (implemented / partial / missing) | Working-tree evidence / paths | Tested evidence for this audit | Remaining verification / release state |
| --- | --- | --- | --- | --- | --- |
| Codex ingestion | Consent-scoped, bounded discovery/read path for supported provider interfaces | Partial | `docs/phase-1.md`; `docs/adr/0002-codex-app-server-read-boundary.md`; Codex adapter tests under `tests/test_codex_*` | Synthetic fixture/provenance/ingestion modules were included in the 24-module offline audit (aggregate 285 passed, 3 failed, 1 skipped); no live import. | Revalidate provider-version compatibility, consent, read-only behavior, and unsupported-shape handling. |
| Claude Code ingestion | Opt-in local source plus optional hooks/telemetry routes | Partial | `docs/phase-1.md`; `docs/adr/0010-claude-code-hook-capture-boundary.md`; `docs/provider-checkpoints/CLAUDE-HOOKS-r7.md`; `tests/test_claude_code_hooks_r7_readiness.py` | Synthetic fixture coverage included in the offline audit aggregate; no live provider import or credential access. | Revalidate adapter versions and separately enabled capture routes; no provider mutation is allowed. |
| Ingestion consent and minimization | Explicit source selection and bounded/minimized local metadata ingestion | Implemented | `docs/phase-1.md`; `docs/adr/0011-owner-authorized-session-reader.md`; `PRIVACY.md` | Synthetic ingestion/provenance paths covered in the offline audit aggregate. Current full privacy-scan blockers and the separate targeted type-annotation finding are recorded under Privacy, security, and recovery; no clean-scan result is claimed. | Confirm consent revocation, cleanup, and obtain a reviewed clean privacy/canary suite. |
| Selected-session text analysis | Fresh opt-in, bounded, redacted in-memory text analysis; content-free results | Partial | `docs/privacy-text-analysis.md`; `docs/live-metric-radar-pipeline.md`; `src/prompt_enhancer/application/analysis/session_text_service.py` | Analysis/metric modules are represented in aggregate offline run; not live provider content or end-to-end real-session analysis. | Verify redaction boundary, exact cap, content-free persistence, and local-model eligibility. Not full-history analysis. |
| Metric contracts and catalog | Separately versioned metric definitions, typed evidence, denominators, coverage, and provenance | Implemented | `docs/metrics-catalog.md`; `docs/metric-operability.md`; `src/prompt_enhancer/application/analysis/` | Fresh static catalog `656249` confirms 20 contracts, 18 shipped measurement paths, two adapter gaps (`logic.hypothesis_test_linkage`, `outcome.agent_claim_grounding`), and zero model-authoritative contracts. Earlier broad and migration selections remain recorded below. | A 20-contract catalog is not 20 measured metrics per session or end-to-end all-metric display. Domain-validity and calibration remain distinct. |
| Metric operability and provenance | Exact metric inventory, family calculations, task evidence/provenance and malformed-input rejection | Partial | `tests/test_metric_operability.py`; `tests/test_task_metric_provenance.py`; `tests/test_requirement_action_transcript_operability.py`; `docs/metrics-catalog.md`; `docs/metric-operability.md` | The separate all-`test_metric*.py` selection passed 306 tests (`7684cd`) after four stale schema assertions were corrected; focused backend/frontend selections passed 35 (`996438`) and 34 (`c8935d`) tests. | These are synthetic selections, not complete source-to-display, real-provider, all-metric, or native save-completion evidence. The historical mixed 24-module batch remains distinct. |
| Claim-grounding review, census, and links | Review/census/source/link/repository/migration/API composition for grounded claims | Partial | `tests/test_claim_grounding*.py`; `src/prompt_enhancer/application/analysis/claim_grounding_review.py`; `src/prompt_enhancer/application/analysis/claim_grounding_links.py` | Synthetic claim-grounding tests: **168 passed** (147.09s, receipt `eaefc6`). | Does not establish full metric source-to-display or native save-completion journeys; keep explicit operability gaps open. |
| Objective outcome verification | Task-scoped receipts for tests/builds/artifacts/acceptance separated from inferred text judgments | Partial | `docs/adr/0012-task-scoped-verification-evidence.md`; `docs/goal-verification-ledger-2026-08-26.md`; `src/prompt_enhancer/application/verification/` | No separate end-to-end result recorded in the reported batch. | Verify receipt provenance, task binding, expiry/recovery; assistant completion text is not proof. |
| Live mini radar / Quality Profile | Live selected-session view of eligible deterministic measures and distinct experimental model ranges | Partial | `docs/live-metric-radar-pipeline.md`; `docs/metrics-catalog.md`; `frontend/src/features/session-radar/` | Underlying synthetic metric paths are represented in the offline audit aggregate; no real-loopback/browser receipt from this audit. | Run real-loopback/browser and resource gates; calibration, coverage, and owner acceptance remain separate. |
| Model-based scoring and calibration | Experimental local model ranges with calibration/resource gates | Partial | `docs/live-metric-radar-pipeline.md`; `docs/research/methodology.md`; `docs/metric-operability.md`; calibration reporting, ratings, comparison-case, case, persistence, UI and packaged-probe tests | Focused synthetic selections passed 85 backend tests (`3627e7`) and 46 UI tests (`5e11ee`). Two consecutive packaged probes (`d9ff5a`, `73227d`) used public consent/onboarding and real browser/API paths for one fictional session: both reviews returned 200 and rendered the expected evidence; three ratings, including one cannot-judge, persisted across page reload and matched the local export. Forbidden/model mutations, external requests, page errors and server 5xx were zero; fixtures and owned browser/server cleanup were verified. Its 23 receipt tests passed independently (`b31894`). | This is a synthetic no-model journey, not live-provider, review-expiry, model-quality, full 24-module, native UI or complete calibration acceptance. The earlier `a03efe` first-run failure lacked the later status diagnostic; no product root cause or fix is claimed. |
| Analytics dashboards and aggregation | Task/session views, separate measurement dimensions, and aggregate lenses | Implemented | `docs/metrics-catalog.md`; `docs/architecture.md`; `frontend/src/features/quality-profile/`; `frontend/src/features/session-catalog/`; `frontend/src/features/metric-coverage/` | Packaged probe `b0e075` used public consent/onboarding and real HTTP/browser paths for one fictional Claude session. All 24 stored metrics loaded; the browser opened Sessions, readiness, model usage and outcome. Missing total tokens displayed Unknown with observed 0 / eligible 1 / coverage 0 and provenance, while fictional assistant completion prose still yielded verification count 0 and pass-rate Unknown. Two category responses were verified and three metric HTTP events observed; external/model/mutation requests, page errors and 5xx were zero. Fixture/candidate integrity and all owned browser/server/tree/handle/reader/port cleanup passed. Its 20 receipt tests passed independently (`b122e0`). Earlier `b4f97c` and `87716e` stopped on corrected harness assumptions and are not product-defect evidence. | This is one synthetic source-to-display slice, not live-provider, all-metric, measured token usage/other metric states, native, or production acceptance. Server termination was forced rather than graceful/native. |
| Automation and metric scope | Scheduled/granted analysis policy, resource gates, and metric scoping | Implemented | `src/prompt_enhancer/application/automation/`; `src/prompt_enhancer/application/jobs/service.py`; `tests/test_automation_grant_persistence.py`; `tests/test_automation_metric_scope.py` | Covered by the 24-module synthetic/offline audit aggregate; not evidence of production schedule execution. | Verify current aggregate after schema expectation corrections; production schedule/remote provider availability is separate. |
| Data export/import and backup | Allowlisted local projections and recovery foundations | Partial | `docs/work-packages/wp-22-windows-distribution-hardening.md`; `docs/checkpoint-beta-distribution.md` | No completed end-to-end user-data export/restore test result recorded in this audit; the dependency-export CLI receipt is tracked separately below. | Verify current schema/hash/recovery behavior, sensitivity labels, and application-level erase semantics. |

## Distribution and updates

| Area | Capability | Implementation status (implemented / partial / missing) | Working-tree evidence / paths | Tested evidence for this audit | Remaining verification / release state |
| --- | --- | --- | --- | --- | --- |
| Local development quick start | Python/uv and frontend setup for a developer checkout; synthetic demo | Implemented | `README.md` Quick start; `pyproject.toml`; `frontend/package.json` | Clean-dependency frontend build `f6683b` published 91 verified outputs and the module-input graph; bundle gate `70f4f5` passed unchanged limits. The current wheel/stage/candidate chain is recorded above; candidate-review4 analytics passed `89ce69`. Older probe `2449de` retains its synthetic browser restart scope. | Developer quick start remains distinct from packaged runtime readiness; native and installer acceptance remain open. |
| WebView2 startup prerequisite | Read-only native preflight before overlay/Agent startup; distinct missing vs unverified diagnostics | Implemented | `src/prompt_enhancer/infrastructure/windows_desktop_prerequisites.py`; `src/prompt_enhancer/desktop_overlay.py`; `tests/test_windows_desktop_prerequisites.py`; `tests/test_desktop_prerequisite_preflight.py`; [Microsoft WebView2 distribution guidance](https://learn.microsoft.com/microsoft-edge/webview2/concepts/distribution) | Root combined detector/bootstrap/preflight/overlay/lifecycle synthetic batch: 101 passed (21.06s, receipt `57c664`). Fake registry values and injected detection results only; no live registry or GUI. Missing state directs users to Microsoft's runtime page; unknown stays an unable-to-verify diagnostic. | This is detection and safe startup gating only. No automatic download/install/elevation/restart, and no WebView2 window creation, clean-machine installation, or supported installer acceptance. |
| Supported installer / first install | Public, supported install package for end users | Missing | `docs/checkpoint-beta-distribution.md`; `docs/work-packages/wp-22-windows-distribution-hardening.md` | Current candidate-review4 SDK packs normalized to identical 34,014,174-byte unsigned MSIX copies (`bdf69407…`); both passed full SDK unpack and independent verification (`e3694a`). The partial Python/runtime notice bundle remains external. | This is not a supported installer: frontend/application/proxy notice closure, opaque worker dependencies, clean-source/native-SDK reproducibility, signing, real app/GUI, clean-machine installation and installer acceptance remain open. |
| Deterministic staging and manifest | Hash-bound staging/manifest tooling for supplied release inputs | Partial | `scripts/build_public_manifest.py`; `scripts/stage_windows_release.py`; `src/prompt_enhancer/infrastructure/build_staging.py`; `scripts/prepare_msix_manifest.py`; `docs/checkpoint-beta-distribution.md` | Current wheel `8c21bcb6…` has two identical builds. Stage `9817bb` verified 2,582 files; candidate review4 `e2d7b7` verified 2,588 files. Two SDK packs had different raw hashes but identical normalized copies; both passed SDK unpack (`874a5e`, `b5f290`). Count-pin tests passed 56 (`1d47e3`), wheel cleanup 12 (`d1d329`), pack/unpack 36 (`ef1296`) and canonicalization 20 (`8d760d`). | Normalized same-snapshot repeatability does not establish source-HEAD or native SDK-byte reproducibility, real-app launcher execution, signing, clean-machine installation, or installer/update lifecycle. |
| Target-platform wheel builder | Prepare deterministic target-platform wheels from reviewed inputs | Partial | `scripts/prepare_proxy_tools_wheel.py`; `scripts/plan_windows_wheels.py`; `scripts/prepare_windows_dependencies.py`; `src/prompt_enhancer/infrastructure/proxy_tools_wheel_preparation.py`; `src/prompt_enhancer/infrastructure/application_wheel_preparation.py`; `tests/test_proxy_tools_wheel_preparation.py`; `tests/test_application_wheel_preparation.py` | Current reproducible wheel `8c21bcb6…` is 3,875,478 bytes (`dc68f9`); independent `7356c8` verified its dashboard and `c39812` its source modules. Exact 43-wheel Python 3.13.15 staging passed `9817bb`. Earlier dependency-builder selections remain scoped evidence; launcher execution used synthetic entries only. | Dirty-snapshot provenance remains, and dependency/runtime-closure and network-isolation claims are unproven. Full native/installer acceptance remains open. |
| Desktop dependency export | Offline, allowlisted export of reviewed desktop dependencies | Partial | `scripts/export_windows_desktop_requirements.py`; `src/prompt_enhancer/infrastructure/desktop_dependency_export.py`; `src/prompt_enhancer/application/owned_process.py`; `tests/test_desktop_dependency_export_adversarial.py`; `tests/test_owned_process.py`; `tests/test_process_launcher_policy.py` | A static check first caught direct `Popen` use (`f15403`); it was replaced by shared `owned_process` with bounded 8 MiB streams, 60s timeout, max one process, and allowlisted environment. Focused exporter tests: 36 passed, 1 symlink skip (2.82s, `a5253b`); owned-process tests: 7 passed (2.79s, `523dfa`); latest process-launcher policy and owned-process regression selection: 10 passed (5.43s, receipt `586125`). Real offline owned export emitted 50 requirements (`ed17a5`). | These static/owned-process checks do not establish full native-app terminal-storm acceptance. Confirm exact target-platform wheel inventory and integrate into the installer builder; no package/install/sign acceptance yet. |
| Package signature/preflight | Offline package/signature metadata validation foundation | Partial | `scripts/verify_msix_package.py`; `src/prompt_enhancer/infrastructure/updates/msix_preflight.py`; `docs/checkpoint-beta-distribution.md` | The reviewed cross-ctime correction passed 101 root-run synthetic tests (`84fa75`, `2b71b9`; independently `c793d5`). Source CLI-reader seam `b87d9b` passed staged-Python metadata/read bounds; fresh stage `288bda` includes the corrected installed preflight module. Full unsigned package structure/payload was independently unpack-verified (`ab50de`). | Structure/payload verification is not Authenticode verification. No signer, install/update, or supported-release acceptance follows. |
| In-app updater | Verify-only/staging/review foundations | Partial | `src/prompt_enhancer/application/updates/handoff_plan.py`; `src/prompt_enhancer/application/updates/recovery_plan.py`; `docs/checkpoint-beta-distribution.md` | Update API tests included in corrected batch (96 passed, 1 symlink skip). Source contract: `can_apply`/`can_install` are `LiteralFalse`, executor unavailable. | Installer executor, apply, relaunch, rollback, release workflow and clean-machine tests remain missing. |
| Auto-update/release channel | Build-sign-publish channel with artifact provenance and supported update flow | Missing | `docs/checkpoint-beta-distribution.md`; `.github/workflows/quality-gate.yml` | Workflow inventory: only quality-gate workflow; no release-channel verification. | No production update channel or published supported artifact. Repository push does not update installed copies. |
| Desktop lifecycle and Windows hardening | Loopback ownership, private roots, packaged resources, ACL and native host contracts | Partial | `docs/work-packages/wp-22-windows-distribution-hardening.md`; `docs/adr/0007-windows-distribution-and-local-data-foundation.md` | Not fully audited in this pass. | Native Windows packaged install/update/rollback and clean-machine evidence remain required. |
| Supported platforms | Declared platform support beyond the development checkout | Partial | `docs/work-packages/wp-22-windows-distribution-hardening.md`; `SECURITY.md` | Not fully audited in this pass. | Confirm exact supported baseline and tested platform matrix; do not infer cross-platform release from source portability. |

The initial selected release/paid/update command, run in the resumed audit, was `uv run --extra release --frozen
--no-sync python -m pytest -q --tb=short -W error -p no:cacheprovider
tests/test_windows_wheel_inventory.py
tests/test_windows_wheel_inventory_adversarial.py
tests/test_windows_release_staging.py
tests/test_windows_desktop_dependency_export.py
tests/test_paid_product_foundation.py tests/test_paid_product_http.py
tests/test_application_update_api.py`: **91 passed, 2 failed, 1 symlink
skip** (8.22s). The two failures were in adversarial wheel inventory: a reversed
`platform_system` marker was falsely rejected and requirement extras were
accepted unexpectedly. The fix now rejects extras before marker activation,
handles the reversed marker, and bounds lockfile reads. Root reran the same
seven-file release/paid/update selection plus added regression tests: **96
passed, 1 symlink skip** (12.49s; receipt `ac58c9`). The skip remains because
the OS could not create symlinks. A hash-matched public proxy-tools source
distribution has since been reviewed and a worker-reported Python 3.11 build
smoke completed; the retained artifact hash/size and observed cleanup were
independently verified. A dependency-preparation bridge was rejected on review
for version/hash exclusions and provenance gaps. This does not establish a
reproducible supported dependency closure or an installable/signed release.

Additional frontend history in the resumed audit: the initial `npm run build`
passed TypeScript + Vite (619 modules), `npm run check:api` passed, and the
first `npm run check:bundle-budget` failed with `E_BUDGET` at shell **1,195,390**
bytes vs 1,180,000 and initial Agent **1,764,235** bytes vs 1,750,000. After a
`DiscoveryScreen` lazy-loading correction (onboarding and inbox imports moved
behind the existing retryable lazy boundary; route/Suspense boundary retained),
the bundle gate passed at shell **1,167,551 / 1,180,000**, incremental
**569,037 / 575,000**, and initial Agent **1,736,588 / 1,750,000** bytes. No
budget was raised. The latest production build passed after a test-fixture role
correction; `npm run check:api` passed. Full Vitest first finished with
**250 test files passed, 1 failed; 3,561 tests passed, 1 failed**
(443.48s). The failure was `AnalyzeLocallyDialog.test.tsx`: a test fixture
expected 17 metrics / 3 excluded while the canonical metric set is 18 / 2.
After root review of that canonical set and explicit IDs
`logic.hypothesis_test_linkage` and `outcome.agent_claim_grounding`, the focused
command `npm test -- --run
src/features/quality-profile/AnalyzeLocallyDialog.test.tsx
src/shared/api/metricOperabilityContract.test.ts` passed **37 tests in 2 files**
(4.41s); it includes a regression check that assistant prose alone is not
evidence. A combined five-file frontend run then passed **86 tests** (20.93s)
across app, onboarding, discovery, metric coverage, and operability tests. The
latest full Vitest rerun at that point completed (receipt `ec274d`): **250 test files passed,
1 failed; 3,562 tests passed, 1 failed** (3,563 total; 535.70s). Its sole
failure is `AgentRuntimeControl`: at line 414,
`updateAgentSessionParameters` was not called after the enabled save click in
the chat-switch test. Focused runtime-control repairs and build validation are
recorded below. A subsequent full frontend run completed green (receipt
`4354f4`): **251 test files passed, 3,566 tests passed** (540.87s). This closes
the reported full-suite test gate for the current frontend revision, not native,
live-provider, real-model, packaged, or owner acceptance. Rerun after material
frontend changes.

After that receipt, the runtime-control path was updated to bind Save/Reload
readiness to the current catalog identity and transport, gate Save and Reload
independently, and recover across immediate/deferred chat switches and catalog
read failures. Focused tests passed **79 tests in 2 files** (6.82s; receipt
`4a6b7a`). A production build then caught a redundant abort after a non-null
guard (`TS2339`); that was corrected and the production build passed (receipt
`d49633`). The subsequent full-suite pass `4354f4` validates this frontend
revision; this does not replace native or packaged acceptance.

## Accounts, premium, billing, and team features

| Area | Capability | Implementation status (implemented / partial / missing) | Working-tree evidence / paths | Tested evidence for this audit | Remaining verification / release state |
| --- | --- | --- | --- | --- | --- |
| Basic local use | Free local checkout/demo without a Prompt Enhancer account | Implemented | `README.md` Quick start; `src/prompt_enhancer/` local app composition | Packaged HTTP probe `fbcba7` resumed one empty retained chat after cold restart; browser probe `775cf5` passed synthetic streaming/Stop and retained completed messages after page reload. Direct-service packaged workspace probe `51ccb0` passed synthetic reviewed create/edit/move and stale refusal. | Basic local use does not require production Prompt Enhancer login. The new browser result used a non-inference fixture and was not a server restart; workspace evidence was not HTTP/browser/native approval. Real models, GPU, personal data, and installer acceptance were not exercised. |
| Optional provider sign-in/access | Import from locally configured Codex/Claude provider sources with user consent | Partial | `docs/phase-1.md`; `docs/adr/0002-codex-app-server-read-boundary.md`; `docs/adr/0010-claude-code-hook-capture-boundary.md` | Synthetic/offline ingestion tests in the 24-module metrics audit (285 passed, 3 failed, 1 skipped aggregate); no provider credentials/sessions or live login tested. | May depend on the user's separate provider login/session and local configuration; distinct from a Prompt Enhancer account. |
| Production login/account service | End-user identity, sign-in, recovery, and production issuer for paid/control-plane access | Missing | `src/prompt_enhancer/application/paid_product/contracts.py`; `docs/work-packages/wp-21-paid-product-boundary.md` | Selected paid foundation/HTTP tests were part of corrected release batch (96 passed, 1 symlink skip overall). Source says production identity/provider paths are `LiteralFalse`. | No production Prompt Enhancer login service configured or supported. Synthetic issuer/test identity is not a live account. |
| Local synthetic Checkout and Portal mapper / durable intent | Test-mode Checkout/Portal request/response contract plus immutable tenant-scoped SQLite intents | Partial | `src/prompt_enhancer/infrastructure/paid_product/stripe_checkout_testmode.py`; `src/prompt_enhancer/application/paid_product/checkout.py`; `src/prompt_enhancer/infrastructure/paid_product/sqlite.py`; `src/prompt_enhancer/interfaces/http/paid_checkout_routes.py`; `src/prompt_enhancer/api.py`; `tests/test_paid_product_checkout.py`; `tests/test_paid_product_checkout_intents.py`; `tests/test_paid_product_checkout_http.py` | Latest independent four-module run: **75 passed** in 30.07s (receipt `2368ba`) across Checkout HTTP, Checkout, durable intents, and paid-product HTTP. It exercises actual `create_app` + SQLite with synthetic principals and fake transport: default-off opt-in development-route composition; Checkout/Portal success and unavailable cases; local auth, CSRF, revoked and cross-tenant denial; server-selected identity (request-body spoofing does not select a principal); timeout/no-store behavior; and intent persistence/reopen. The earlier authorization-enum defect was corrected to use `PaidReasonCode.DEFAULT_DENY`. | Development routes remain off by default and are not production login/account composition. Synthetic/fake-HTTP evidence only: no Stripe API, sandbox Checkout/Portal, account registration/recovery, or production payment integration. |
| Local test-mode webhook contract | Synthetic signed-event parsing and billing projection through the local HTTP route into SQLite | Partial | `src/prompt_enhancer/infrastructure/paid_product/stripe_testmode.py`; `src/prompt_enhancer/interfaces/http/paid_product_routes.py`; `tests/test_paid_product_stripe_testmode.py`; `tests/test_paid_product_stripe_adversarial.py` | Combined five-module paid/Stripe suite: **79 passed** (17.78s, receipt `9a7907`). The 16 new adversarial tests cover raw signed event → real application HTTP route → SQLite, default-off route (`404`) and unrelated auth (`401`), all 9 normalized MAC fields, duplicate/different-ID cancellation policy, accepted-invoice replay after cancellation, cancellation tombstone/fence rollback, generic revoke→later-grant reactivation, signed NaN/deep JSON returning HTTP 400, and genuine schema 3→4 migration preserving binding and integrity. | This verifies only local synthetic test-mode composition; it is not a call to Stripe or acceptance of Checkout, Customer Portal, registration, recovery, production account service, or replacement-subscription lifecycle. |
| Stripe checkout/customer portal | Production plans, Checkout, Customer Portal, tax/refund, webhook secret, customer records | Missing | `src/prompt_enhancer/application/paid_product/contracts.py`; `docs/work-packages/wp-21-paid-product-boundary.md` | Local synthetic Checkout/Portal and webhook routes have targeted coverage, including the 75-test four-module app/SQLite run above. No Stripe API, sandbox Checkout/Portal, or production account test was performed. | No production Stripe integration/account is activated; no production checkout, billing, or customer portal. Any separately authorized sandbox work and production service acceptance remain outstanding. |
| Entitlement and billing ledger | Tenant-bound entitlement and append-only billing design/foundation | Partial | `docs/work-packages/wp-21-paid-product-boundary.md`; `docs/adr/0005-team-control-plane-boundary.md`; `src/prompt_enhancer/application/control_plane/contracts.py` | Selected paid foundation/HTTP tests included in release batch; no live payment event. | Contracts include placeholder tiers/no billing; live payment events and commercial activation are absent. |
| Hosted analysis jobs | Paid remote analysis behind consent, redaction preview, scopes, budget and settlement gates | Partial | `docs/work-packages/wp-21-paid-product-boundary.md`; `docs/adr/0017-remote-annotation-providers.md`; `src/prompt_enhancer/application/jobs/service.py` | Synthetic policy/automation tests in offline aggregate; no production provider call. | Production adapters/accounts, spend controls, retention/legal decisions and egress acceptance remain open. |
| Teams, organizations, membership and invites | Team control-plane concepts and shared-folder direction | Partial | `docs/adr/0005-team-control-plane-boundary.md`; `docs/adr/0018-shared-team-folders.md`; `docs/work-packages/wp-21-paid-product-boundary.md` | No production identity or team-service run in audit. | Verify current persistence/authorization and recovery; no production team service or paid rollout established. |
| Roles, devices, API clients and revocation | Scoped authorization and revocation foundations | Partial | `docs/work-packages/wp-21-paid-product-boundary.md`; `src/prompt_enhancer/application/control_plane/contracts.py` | No production issuer/device service tested. | Verify end-to-end identity, device and membership enforcement with production issuer/secret custody; no public API service claim. |
| Shared/team folders and direct transfer | Private sharing architecture and bounded transfer preview | Partial | `docs/adr/0018-shared-team-folders.md`; `docs/work-packages/wp-20-private-social-metric-product.md`; `frontend/src/features/social/directTransfer/DirectTransferPrototypePanel.tsx` | No live transfer or team-service acceptance in audit. | Verify network consent, transport, retention, and revoke/delete behavior; preview/prototype is not production sharing. |
| Team analytics | Team-context and aggregate analytics UI | Partial | `frontend/src/features/team-analytics/TeamAnalyticsPage.tsx`; `frontend/src/features/team-analytics/TeamAggregateBoard.tsx` | Source/UI tests exist, but not covered by reported focused audit results. | UI/code presence is not evidence of production teams, auth, multi-tenant isolation, or paid availability. |
| Premium plan availability | Purchasable production subscription and customer support lifecycle | Missing | `docs/work-packages/wp-21-paid-product-boundary.md`; `src/prompt_enhancer/application/paid_product/contracts.py` | Production readiness path intentionally unavailable in source; no live checkout test. | No production login, live Stripe checkout, or supported paid subscription is available. |

## Privacy, security, and recovery

| Area | Capability | Implementation status (implemented / partial / missing) | Working-tree evidence / paths | Tested evidence for this audit | Remaining verification / release state |
| --- | --- | --- | --- | --- | --- |
| Local-first / loopback boundary | Local service default and separation of network/egress decisions | Implemented | `README.md` Privacy and egress; `PRIVACY.md`; `SECURITY.md`; `docs/architecture.md` | Not separately covered in the summarized audit evidence. | Re-run binding, origin, and egress tests; native packaged ownership is a separate release gate. |
| Transcript/content retention | Metadata-first persistence; selected content analysis only after explicit opt-in | Partial | `PRIVACY.md`; `docs/privacy-text-analysis.md`; `docs/adr/0011-owner-authorized-session-reader.md` | Synthetic, content-free fixtures only; no live content inspected. | Verify persistence/log/error paths and retention with synthetic canaries. Derived data remains sensitive. |
| Redaction and secret/PII scanning | Redaction boundaries and repository canary scanner | Partial | `scripts/privacy_scan.py`; `tests/test_privacy_scan.py`; `docs/privacy-text-analysis.md`; `CONTRIBUTING.md` | Fresh full scan `67bc62` failed with 3,184 findings: 3,182 under generated test results and two other findings. The earlier ten synthetic-canary source-format findings no longer contribute; their fixes preserved generated bytes and scanner rules. Only closed counts were reported, without finding contents. | The global gate remains failed. Generated-artifact hygiene and the two previously known database paths remain unresolved; do not commit, push, publish or claim scanner clearance. |
| Provider adapter read-only safety | Ingestion cannot mutate provider sessions | Implemented | `docs/phase-1.md`; `docs/adr/0002-codex-app-server-read-boundary.md`; `docs/adr/0010-claude-code-hook-capture-boundary.md` | Synthetic provider/fixture tests included in the offline metrics batch; no real provider accessed. | Confirm permission scopes and provider schema compatibility; provider versions vary. |
| Protected local effects | Human/native approval required for file writes, commands, and other protected effects | Implemented | `docs/local-models-and-agent-access.md`; `docs/agent-controller-api.md`; `docs/adr/0016-local-agent-workspace.md` | Workspace synthetic boundaries: 161 passed across read/write/transaction/lifecycle/discovery test files. Packaged probe `8ab4e5` observed disabled Apply, CSRF/native/traversal refusal, discard/reopen, and stale-review rejection with unchanged final fixture and bounded cleanup. | Verify no remote/MCP path can approve effects; native approval/write UX and broader adversarial acceptance remain required. |
| Credential and secret custody | Local secret storage and private-root foundations | Partial | `docs/work-packages/wp-22-windows-distribution-hardening.md`; `docs/adr/0007-windows-distribution-and-local-data-foundation.md` | No credential stores or provider secrets read; platform custody not fully audited. | Verify platform-specific custody and ACL behavior; never infer protection from POSIX bits or test doubles. |
| Restart and interrupted-operation recovery | Durable metadata and explicit reconciliation contracts | Partial | `docs/architecture.md`; `docs/prompt-enhancer-owner-feature-register-2026-08-31.md`; `docs/work-packages/wp-22-windows-distribution-hardening.md` | Current packaged probe `2449de` preserved three synthetic user messages, two completed replies, and one stopped reply across two staged-app launches and fresh browser contexts. The second browser reopened history, performed UI Resume with all protected permissions off, and preserved it across reload/reopen; post-browser HTTP history/idempotent resume also passed. Both owned process trees, readers, handles, and app ports cleaned up. | Termination was forced rather than graceful; the stopped reply was retained, not presented as completed. Verify broader interrupted recovery, real-model behavior, runtime-port closure, and native behavior. |
| Backup, restore, export, and erase | Application-level maintenance and sensitive export/recovery foundations | Partial | `docs/work-packages/wp-22-windows-distribution-hardening.md`; `docs/checkpoint-beta-distribution.md` | No completed end-to-end export/restore result recorded. | Verify consistency, manifests, schema/hash rejection, erase inventory; do not imply forensic sanitization. |
| Threat model and security response | Public security/privacy guidance and local threat boundaries | Implemented | `SECURITY.md`; `PRIVACY.md`; `docs/architecture.md` | Documentation inspected; no full security review performed. | Review against current packaged/remote scope; unsupported-release status remains explicit. |

## Historical A–E backlog (superseded by B00–B11 above)

This older queue is retained as historical context, not an active work plan.
In particular, sandbox accounts and payment activation do not gate the agreed
free beta. Record new status only in the authoritative beta ledger above.

| Order | Requirement | Checkpoint / action | Current state | Exit evidence required |
| --- | --- | --- | --- | --- |
| 1 | D — Windows distribution and updates; A — reliable local Agent | Complete cross-ctime handling consistently across workspace I/O, local Agent workspace boundaries, and MSIX preflight without broad acceptance inference. | Workspace selections passed 112 (`f7305b`) and 83 (`dddc31`); packaged direct-service probe `51ccb0` exercised historical Python 3.13.0 behavior. Fresh Python 3.13.15 stage `288bda` includes the corrected installed preflight module; native probe `7bbc19` exercised only synthetic entry stubs, not that real app path. Current full unsigned package structure and payload passed unpack verification, but signature preflight necessarily remains unaccepted. | Run the actual full package verifier after signing. Source-reader, installed-module, and unsigned-structure evidence are distinct and are not Authenticode, signing, install, update, or installer acceptance. |
| 2 | C — Analytics and metrics; A — reliable local Agent | Keep the canonical 18-included / 2-gap metric set and exact IDs `logic.hypothesis_test_linkage` and `outcome.agent_claim_grounding`; reject assistant prose as outcome evidence. | Static catalog `656249` confirms 20 contracts, 18 shipped paths, the two named adapter gaps, and zero model-authoritative contracts. Fresh backend/frontend selections passed 35 (`996438`) and 34 (`c8935d`) tests. Earlier full frontend receipt `4354f4` passed 3,566 tests before later focused changes. | Preserve explicit-ID, unknown/coverage, and assistant-prose regressions; do not present the catalog as 20 metrics measured per session. Rerun the full suite after material frontend changes. |
| 3 | B — Tools and MCP | Repair agent-catalog schema/migration expectations and simulated upgrades for versions 24–27. | Earlier focused MCP batch had 71 passed / 5 failed on historical fixture expectations. Selected migration tests later passed within 106 tests / 4 files (118.94s, `63ece2`); latest server-management synthetic batch passed 93 tests (22.64s, `d43ba2`), and connections/client-config passed 28 (2.59s, `b44d49`). Migration fixtures were corrected; production migration behavior was not weakened. | Continue supported-schema recovery and native/actual-external-client acceptance. These selected synthetic/API tests do not establish live MCP client or provider acceptance. |
| 4 | C — Analytics and metrics | Reconcile stale schema assertions while preserving historical migration identities. | Historical mixed 24-module batch had 285 passed / 3 failed / 1 skipped. A distinct current selection of all 25 `test_metric*.py` modules passed 306 (`7684cd`) after four test-only terminal-schema corrections, while v43/v44 identities and the current ledger remain asserted. | Repeat the historical mixed 24-module batch and retain its symlink-capability skip separately. Do not infer ingestion/calibration, model evaluation, or full source-to-display coverage from the 25 metric-named modules. |
| 5 | D — Windows distribution and updates; A — reliable local Agent | Keep shell and initial-Agent bundles within their existing hard budgets; do not raise limits merely to pass. | Targeted fix applied and reviewed. `DiscoveryScreen` onboarding/inbox imports use the existing retryable lazy boundary while preserving route/Suspense behavior. Latest clean-dependency bundle gate passes: shell 1,167,551/1,180,000; incremental 569,349/575,000; initial Agent 1,736,900/1,750,000 bytes (`70f4f5`), with all ten deferred boundaries retained. | Recheck unchanged limits after future changes. This does not replace full-suite or packaged acceptance. |
| 6 | A–E — public/release integrity | Investigate accumulated-artifact hygiene and repository privacy-scan categories without weakening the scanner or exposing finding contents. | Six confirmed owned stages were safely relocated outside the repository with manifests retained and hashes reverified; no deletion or database change occurred. Fresh full scan `67bc62` failed with 3,184 findings: 3,182 generated-test-result findings and two other findings. Earlier synthetic-source fixes removed ten findings without changing scanner rules. | Complete generated-artifact hygiene and authorized review of the remaining categories, then rerun the repository-wide scan. Until it passes, do not commit, push, publish or claim scanner clearance. |
| 7 | A — reliable local Agent | Complete a full local journey from no-model/no-login start through folder selection, project/chat, composition, streaming, stop/retry/restart, truthful activity/reasoning, Markdown/artifacts, modality gating, and process cleanup. | Packaged probe `2449de` covers streaming, Stop, cold restart into a fresh browser, retained completed/stopped history, read-only Resume, and bounded cleanup. Workspace probe `8ab4e5` adds real GET/editor/diff, protected-effect and traversal refusal, discard/reopen, stale-review rejection, restored fixture, and bounded cleanup. | Continue native-approved workspace writes, real-model/GPU behavior, graceful recovery, native launcher/UI, and installer acceptance separately; the model fixture was CPU non-inference and its runtime port was not independently reported. |
| 8 | B — tools and MCP | Complete workspace approval and MCP lifecycle journey: connect, discover, verify provenance/configuration, install/use/remove/revoke, migrate/restart; ensure protected workspace effects can only be approved in the native UI. | Selected server-management synthetic tests (93) and connections/client-config tests (28) pass. Packaged candidate-review4 probe `199e40` adds real HTTP/UI browse, normalized search, exact provenance/review boundaries and disabled setup-plan authority with an injected fictional registry; its catalog/detail/history calls, zero forbidden actions and owned cleanup were verified. | Add separately authorized official-registry transport and cache-restart acceptance, then native-confirmed plan/install/use/remove/revoke/recovery journeys. Browsing metadata and a disabled control are not tool trust, install, or protected-effect approval. |
| 9 | C — analytics and metrics | Complete source-to-display journeys for consented ingestion, session reader/timeline, task flow, evidence/provenance, Unknown/Pending states, calibration/research/model-link surfaces, live mini window, and allowlisted export. | Not yet broadly end-to-end accepted. Two packaged calibration passes (`d9ff5a`, `73227d`) covered reviewed evidence and saved ratings. Packaged analytics pass `b0e075` added a narrow fictional source-to-display path for missing-token Unknown/coverage/provenance and kept assistant completion prose separate from objective verification while displaying a measured zero verification count. All used no model/external mutation and verified owned cleanup. Static catalog `656249` still has two adapter gaps and no model-authoritative measures. | Continue Pending and measured token-usage/other-metric browser coverage, the two adapter paths, review expiry, research/model-link/live-window surfaces, the historical mixed 24-module batch, and real-provider testing only with separate authorization and redaction preview. |
| 10 | D — Windows distribution and updates | Produce and validate a reproducible per-user installer with reviewed dependencies, signing, lifecycle and recovery; prove consented update, relaunch/rollback, and clean install/upgrade/uninstall without reboot on the declared Windows baseline. | Still missing as a supported release. Clean lock-derived dependencies and the verified 91-output dashboard are embedded in wheel review9, stage review3 and candidate review4. Two current SDK packs normalized to identical 34,014,174-byte copies (`bdf69407…`) and both passed SDK unpack; independent `e3694a` verified payloads and unchanged candidate. Root pack/unpack tests passed 36 (`ef1296`) and canonicalization 20 (`8d760d`). Current candidate analytics passed `89ce69`; earlier restart/calibration/workspace scopes remain distinct. Bundle limits remain unchanged (`70f4f5`). Worktree dependencies/app remained untouched. | Close frontend/application/proxy notices and opaque worker dependencies. Then verify clean-source reproducibility, native app, signing, install/update/rollback, secure-baseline acceptance and the whole-repository privacy gate. Normalized packaging, graph/build and synthetic analytics evidence are not release acceptance. |
| 11 | E — optional accounts and premium | Keep free local use fully usable without Prompt Enhancer login. After owner choices, exercise sandbox registration/recovery/revocation/authorization, Stripe test-mode Checkout/Portal/webhooks/idempotency/entitlements, and offline free fallback. | Production paths unavailable; no pricing choice, production identity issuer, Stripe API/sandbox Checkout/Portal, or live service. Local synthetic webhook and actual-app/SQLite Checkout/Portal route tests passed in the independent 75-test four-module run (`2368ba`); routes are opt-in development composition and off by default. No live provider or account lifecycle was exercised. | Obtain separately authorized sandbox evidence for auth, Checkout/Portal, webhook replay/idempotency, entitlement lapse/reactivation, replacement-subscription lifecycle, privacy/egress and offline behavior; no production credentials. Keep local synthetic scope distinct from sandbox and production acceptance. |
| 12 | D/E — production owner gates | Only after earlier gates close, obtain owner decisions and public release inputs: supported baseline/channel, pricing, signing identity/public metadata, artifact host, retention/legal terms, provider/model allowlists, budgets, support/incident and deletion policy. Keep all private secrets in owner-controlled custody. | Pending owner choices; never infer or fabricate values. | Documented owner approval and production acceptance for each external service. Private signing/API/payment credentials remain outside the repository and audit artifacts. |

## Current user-facing conclusion

Prompt Enhancer has substantial local source, documented boundaries, and
synthetic verification contracts. It remains an actively developed checkout,
not a supported end-user release. In particular, there is no supported
installer, no production login/account service, and no production Stripe
checkout or billing activation. Staging, UI controls, design documents, and
historical passing tests must not be read as proof that a released product or
external service is available. Consult fresh test evidence and owner/native
acceptance before changing these states.
