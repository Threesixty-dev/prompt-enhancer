# Bench evidence ledger

Date: 2026-10-12. Branch: `codex/test-bench-infrastructure`.
Highest completed level is recorded per row; this is not a release certificate.

| Criterion | Evidence | State |
| --- | --- | --- |
| Immutable revision import and newest eligible auto-run | Concurrent duplicate/import/claim, late delivery, generation conflicts and supersession tests | Passing synthetic integration |
| UI overrides and correlated persistence | SQLite reopen, immutable parameters/objective/steering, idempotency conflict, per-unit/attempt identities | Passing synthetic integration |
| Cancellation/restart/recovery | Queued cancel, running intent, lost acknowledgement, timeout, cleanup block, no replay; uncertain-result DELETE failure retains hold and operation ID through reopen/recovery | Passing synthetic integration |
| Shared protocol | B-owned JSON schema validation of definitions, client requests/results and correlation | Passing against current B schemas |
| UI desktop/mobile | Chromium, 1440x1000 and 390x844; evidence inspection, objective/steering controls, override/rerun retention, cancel, reload, invalid input, no horizontal overflow | Four browser checks passed |
| Deployment syntax | Docker Compose config with reserved example settings | Passing static/config validation |
| Core and bench images | Local Docker builds using B's core recipe and exact shared contracts | Built locally; no publication |
| Real core container lifecycle | Two runs/four attempts per smoke; real core API and verified HTTPS provider simulator; schema-validated generation payload matched to persisted baseline, objective, steering, profile and identities; changed controls delivered on rerun; digest/duplicates/reopen/cleanup | Passing packaged lifecycle; simulated provider only |
| Static worker startup | Built isolated OpenHands/Codex image; authenticated loopback readiness; SDK/server/tools 1.49.1, Codex 0.156.0, codex-acp 1.10.0 | Passing packaged startup; no model call |
| Dedicated consumer gateway isolation | Real network-none consumer and relay containers; both API/gateway directions, verified HTTPS stream completion, auth rejection, socket group/read-only mounts, unrelated env removal, no external route, transport failure and restart | Passing synthetic transport integration; no actual Codex generation request |
| Live OpenHands/Codex and gateway | No task-specific live binding/credential injected | Open live-access/qualification gate |
| Gateway rubric evaluation | B implements a separate configured rubric transport; A passes a distinct optional evaluator credential and documents the binding | Wiring implemented; real gateway/profile qualification not run |
| Local model runtime wiring | Operator-only reviewed volume, fixed read-only cache path, bounded CPU/memory, explicit single CUDA device, config/image checks; variant-specific tags, labels and fingerprints | Implemented; synthetic rejection/launch/variant tests pass |
| Model-enabled container | Built optional dependency image; B embedding alias initialized, Torch/Transformers imported, actual 4 GiB/2 CPU limits, core cache-boundary check, offline missing-snapshot rejection and read-only write rejection observed; test volume removed | Passing packaged runtime wiring; no model weights loaded |
| Genuine local models/GPU | Reviewed weights and target hardware were not used; CUDA selection tested through synthetic Docker commands only | Open model/device qualification gate |
| Source privacy | Full repository scan using B's corrected scanner plus A-owned source/canary tests; zero findings | Passing against combined scanner implementation |
| Inherited source preservation | Content-free hash comparison of all 55 inherited files | Zero changed |
| Hosted CI, registry delivery, Coolify deployment | Reviewable workflows/recipes only | Not executed; owner-controlled publication/deployment |

The fixture core and loopback provider simulator are labelled test doubles and
must never be cited as live model acceptance. No real provider history, local
account configuration, source publication or live deployment was used.

## Final local checks

- `tests/bench`: 71 passing synthetic Python tests. Ten worker/client cases
  include a stored uncertain consumer result followed by lost DELETE
  acknowledgement. Container cleanup, Store reopen and worker reconciliation do
  not clear the hold; explicit operator evidence is required before admission.
- Four responsive Chromium tests pass, including rerun retention of effective
  parameters and steering. Browser screenshots, traces and video are disabled.
- Definitions, JavaScript syntax and synthetic Compose configuration validate.
- Core and bench images were rebuilt locally against B's shared schemas. The
  updated measured-generation smoke passed twice, including the refreshed core
  worker artifact. Each smoke runs a script and inference-adapter sibling, then
  reruns with changed objective/steering and the same evaluator profile.
- Static consumer startup/authentication and pinned dependency versions pass in
  a network-disabled container. No gateway call or actual Codex turn occurred.
- The separate relay smoke makes only synthetic transport probes through real
  containers. The consumer remains network-none, the core's API binding remains
  loopback 8000, and the evaluator route stays separate. It verifies both missing
  credentials are rejected, SSE completion, socket ownership/read-only mounts,
  absence of an external route, bridge failure supervision and successful restart.
  No live gateway, actual Codex model request or account configuration was used.
- The model-enabled real-container smoke passes with two runs/four attempts,
  measured-generation checks, the fixed read-only synthetic cache mount and
  actual CPU/memory controls. Model image labels are enforced before launch;
  reuse/publication tests prevent collisions between default/model variants.
- Default, model CPU and explicit CUDA Compose profiles validate without actual
  deployment secrets. No model weights were downloaded or loaded, and no physical
  GPU was assigned during local checks.
- Both checked-in core configuration examples validate against B's authoritative
  `CoreConfiguration`. The default-container smoke remains passing after adding
  the optional model runtime controls.
- No hosted workflow, registry delivery or Coolify deployment was executed.

The bench alone does not carry B's source/contracts or scanner fix. Integration
requires the reviewed combined change; A used exact B-owned schemas from its
parallel checkout and a temporary build context without copying them into A's
source tree. Owner acceptance of the proposed architecture remains pending.
