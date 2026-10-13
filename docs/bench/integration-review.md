# Combined core and bench review

## Consumer retention follow-up - 2026-10-13

The owner requested retained OpenHands history after the successful pilot was
deleted by completion cleanup. Core 0.1.3 and the dedicated consumer adapter now
separate process release from history expiry. The configurable default is seven
days after confirmed cleanup; uncertain attempts remain held. Native history is
read-only and survives restart. Complete Bench results keep their existing
independent retention. See the [task and policy](consumer-retention.md).

Initial focused validation: 46 synthetic tests passed. The pinned 1.49.1 consumer
container also preserved a fictional native conversation and its events across
server restart, rejected unauthenticated access and replay, and expired the
acknowledged history. Networking was disabled and no inference was performed.
Live rollout and a future consumer run remain separate evidence.

Date: 2026-10-12. Branch: `codex/enhancer-integration-review`.
Initial disposition: local review candidate. The October 13 addendum records a
later live synthetic deployment; architecture acceptance remains pending.
See [ADR 0025](../adr/0025-enhancement-experiment-boundary.md).

## Reconciliation with current main

The owner subsequently requested a PR and promotion to main. Main had advanced
to `4b4efba`, including separate quality-gate repairs. The candidate now retains
those changes and the enhancement implementation. Conflicting evidence entries
were combined, both dependency sets retained, and the two new proposals were
renumbered 0024/0025 to preserve main's existing ADR identities.

Of the original 36 failures and four errors, main's repairs clear 30. Updating
seven HTTP test factory signatures to accept the explicit `inference` argument
clears the remaining ten without changing their assertions. All 40 cases now
pass within an affected-module run of **621 passed, six platform/tooling skips**.
The combined core/provider/bench selection also passes **265 tests**. The
complete frontend suite passes **2,920 tests**; generated API consistency and the
production frontend build pass, retaining the existing chunk-size advisory. The
historical evidence below remains attributable to its earlier source baseline;
it is not the current residual-failure count. Hosted full-suite checks and live
model qualification are separate from these local results.

## Hosted CI portability repairs

The hosted container smoke now resolves the Docker daemon socket group before
starting the non-root worker. The worker uses a native byte-range lock on Windows
and POSIX flock elsewhere; local exclusion and exception-release coverage passes
within all 80 bench tests. The hosted bench container, consumer startup, relay
and model-enabled smoke workflow passes with synthetic fixtures.

Python versions also supply different default HTTP 413 descriptions. Six chat
and analysis route declarations now explicitly retain `Content Too Large`.
A regression exercises both standard-library wording variants. Each variant
produces the exact committed OpenAPI bytes; no schema/client regeneration or
relaxation of the byte-exact artifact gate is needed. Full hosted platform
results must still pass on the final integration commit before merge.

## October 13 pilot failure diagnosis

Core 0.1.2 adds an operator-bound `reasoning_effort` setting, recorded in provider provenance.
The Qwen gateway pilot exhausted its 1,024-token budget in reasoning, with
`finish_reason: length` and empty answer text. A bounded diagnostic using the
same fictional input and budget with `reasoning_effort: none` returned completed
rubric JSON in 12 tokens. Truncated and malformed replies still remain unknown.

The pinned OpenHands SDK 1.49.1 emits the completed ACP answer in a typed
`FinishAction`, which the old MessageEvent-only reader ignored. The adapter now
requires exactly one matching finish event after both completion checks. A
second failure was a Codex startup warning prepended to the valid JSON because
the gateway alias had no catalog entry. The static consumer now writes an
explicit text-only client catalog for its configured alias, with tools disabled
and unknown context limits left null. This is client policy, not a verified
upstream model identity or capability claim. No arbitrary preamble is stripped.

Only finite package-owned error codes cross the worker boundary; arbitrary
exception text remains suppressed. Automatic runs stay disabled. This diagnosis
does not by itself qualify an end-to-end experiment or close any beta gate.

## October 13 live synthetic completion

The deployed consumer catalog must expose its configured alias in Codex's
selectable model list. Hiding its sole entry caused ACP initialization to fail
before generation. The corrected image passes an offline initialization and
model-list check using the pinned Codex executable, with no inference submitted.
The failed operation was removed and independently checked before its
reconciliation hold was released. A separate core-startup failure was traced to
configuration-file ownership and repaired without widening its read permissions.

Manual pilot revision 7 completed in approximately 41 seconds on core 0.1.2.
All four original Qwen rubric responses parsed: three labels were known and one
explicitly abstained. OpenHands/Codex returned a valid rewritten prompt; all four
candidate rubric responses parsed as known labels. Ten comparison records were
saved, including honest unknown and non-comparable outcomes. No provider error
was recorded. Assertions remain `not_evaluated`, so this is execution evidence,
not a demonstrated prompt-quality improvement.

The deployment retains the separately delivered portal runtime and routing,
with updated shared schemas on its pinned image. The final consumer image binds
source `a653b2d`; the core and shared schemas bind `42de206`. The retained core
archive checksum was verified. Final checks found the synthetic conversation
absent, no owned Codex process or workspace, no ephemeral core, and no queued
runs, cleanup holds or reconciliation holds. Receipts remain outside the repo.
Automatic runs stay disabled.

Validation includes the earlier 69 focused synthetic tests, the affected
consumer-config regression rerun after the final visibility correction, and the
privacy scan. No complete suite or CI wait was added. Hosted model revisions and
licenses remain unknown; live cancellation and wider qualification remain open.

## Review boundary

The integration checkout combines the completed core and bench workstreams on
`6fa1100`, including the 55 inherited source changes needed by both. Those 55
files are baseline dependencies, not all newly authored enhancement work.
The initial import was byte-verified against 151 source/build/test/documentation
files. The original checkout and both workstream checkouts remain preserved.
The accompanying review patch is relative to that inherited original checkout,
so unchanged inherited work is excluded from its diff.

Core owns `contracts/enhancement/`, the evaluate/generate/reevaluate flow, its
typed adapters and container recipe. Bench owns GitOps import, immutable run
settings, the serial queue, container lifecycle, private results and UI. It calls
the core's authenticated HTTP API directly. There is no separate testing harness.
Consumer generation and metric evaluation remain separate provider roles.

## Integration fixes

1. **Sibling model selection.** A consumer unit can override the experiment's
   configured consumer alias. UI overrides are applied last, persisted per unit
   and retained on rerun. The evaluator profile and core image remain shared.
   Unsupported providers, endpoints, credentials, unknown units and consumer
   settings on script units are rejected. Omitted unit bindings preserve existing
   v1 publication hashes, and older queued snapshots remain readable.
2. **Stable build inputs.** The image build fingerprint and Docker context ignore
   generated Python installation metadata. Installing the package locally no
   longer changes its build identity. Actual source changes still change the
   fingerprint and require a new code version before replacing a published tag.
3. **Local demo artifact retention.** The launcher retains the exact core image
   with a demo-specific local tag. Rebuilding the development tag cannot make the
   demo's referenced manifest unreachable while that retained image is present.

## Fresh combined evidence

| Check | Result and scope |
| --- | --- |
| Core selection | 186 passing tests: contracts, engine, adapters, owned processes, packaging, Prompt Check, inference, local evaluation and privacy |
| Complete bench selection | 79 passing Python tests, including seven sibling-binding regressions and generated-metadata fingerprint coverage |
| Desktop/mobile UI | Six passing Chromium checks, including model overrides and rerun retention; no screenshots, traces or video retained |
| Final core/bench container smoke | Two runs, four attempts; measured generation context, steering changes, shared evaluator, duplicate suppression, persistence and cleanup verified; HTTPS inference simulator only |
| Interactive local demo | Revision 2: automatic run, UI override run and rerun all succeed, with two attempts each; changing steering changes the candidate |
| Demo restart | All six historical run records survive byte-equivalent JSON comparison by hash; reimport creates no additional automatic run |
| Configuration | Default, model CPU and explicit CUDA Compose variants validate using reserved example values |
| Repository checks | Frozen locks, privacy scanner, architecture output consistency and whitespace checks pass |

The browser walkthrough uses two packaged deterministic strategies on a fictional
widget prompt. It exercises real bench/core containers, persistence and the UI;
it makes no live model request. Assertion outcome is `not_evaluated` because these
demo units do not declare acceptance assertions. Successful execution alone does
not prove improved prompt quality.

One revision-1 rerun failed after a development-image rebuild removed its old
local digest. The failed record remains visible and unchanged. The retention fix
and revision-2 publication restore reproducible execution without rewriting old
results. A rerun preserves resolved execution settings while recording its own
explicit per-unit override recipe and fresh run/correlation/attempt identities.

The separate workstreams' [core validation](../enhancement-core/validation.md)
and [bench evidence](evidence.md) also record static worker startup, isolated
gateway relay transport and the model-enabled container/cache checks. Those
checks were not all repeated during this combined review. None loaded real
model weights or qualified a physical GPU or a live Codex generation turn.

## Open the local demo

From the integration checkout, with its frozen bench environment and local images:

```sh
bench/.venv/bin/python bench/local_demo.py start
bench/.venv/bin/python bench/local_demo.py status
bench/.venv/bin/python bench/local_demo.py stop
```

On a Linux Docker host, set `BENCH_DOCKER_GID` to the group that owns the
daemon's `/var/run/docker.sock` before starting the demo or container smoke.
Hosted CI resolves that group after starting Docker and supplies it to both
smoke variants. The default remains group `0` for Docker Desktop; a host-side
socket symlink can have a different group from the socket inside its daemon VM.

The completed review leaves the demo running at `http://127.0.0.1:8098`.
Use the synthetic token `example-review-operator-not-a-secret` in the local UI.
This fixture token is only for the loopback demonstration, not a deployment
credential. The token stays in tab memory and must be entered again after reload.

Open the latest revision and inspect its automatic run. Set parameter overrides
to `{"timeout_seconds":45}`. Expand the steering controls and set:

```json
{"script":{"profile":"targeted.v1","focus":["acceptance"]}}
```

Run both sibling strategies, inspect before/after evidence, then use **Rerun
effective settings**. The manual run and rerun retain their settings without
altering the GitOps revision. Consumer model controls are exercised by the
regression tests; this scripted demo has no consumer binding to override.

The launcher uses labelled containers and a dedicated persistent volume. Its
worker has no external network route; dynamically spawned cores share that
namespace. `stop` preserves the data. `start` reuses the stored publication and
volume. `stop --remove-data` explicitly deletes only this demo's owned volume and
state; do not use it to preserve review history. Local retained image tags are
left in place. After Docker pruning, restore the referenced image before rerun.

## Remaining acceptance

- Review this combined candidate and the proposed ADR before source integration.
- Extend the bounded live completion evidence with pinned upstream model identity
  and live cancellation qualification for the dedicated OpenHands/Codex consumer.
- Extend the Qwen rubric qualification with genuine model revision, typed metrics,
  and broader failure/timeout coverage. Consumer and evaluator roles stay separate.
- Supply reviewed offline snapshots and selected hardware for actual local
  model/GPU qualification. Connectors and advanced GPU scheduling remain deferred.
- Qualify CI/registry delivery separately from the authorized live deployment
  recorded above; the latter does not certify release delivery.

At the initial review checkpoint, the broad repository suite was not green.
The core workstream recorded 6,134
passes, 37 failures, 56 skips and four errors, fixed one new inventory regression,
and reproduced all remaining 36 failures plus four errors on the actual inherited
baseline. The reconciliation above closes those 40 specific cases. It does not
close native, release or general workflow beta gates.
