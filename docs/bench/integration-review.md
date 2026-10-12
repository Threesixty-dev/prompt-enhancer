# Combined core and bench review

Date: 2026-10-12. Branch: `codex/enhancer-integration-review`.
Disposition: local review candidate; architecture acceptance and live deployment
remain pending. See [ADR 0025](../adr/0025-enhancement-experiment-boundary.md).

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
- Bind and qualify the dedicated static OpenHands/Codex consumer with fictional
  inputs, pinned model identity, real completion/cancellation and cleanup evidence.
- Independently qualify the evaluator aliases through the intended LiteLLM/local
  inference route, including genuine model revision, typed metrics, failure and
  timeout behavior. The consumer cannot substitute for evaluation models.
- Supply reviewed offline snapshots and selected hardware for actual local
  model/GPU qualification. Connectors and advanced GPU scheduling remain deferred.
- Deliberately authorize CI/registry publication and Coolify deployment. The
  recipes are implemented; neither hosted delivery nor deployment was executed.

At the initial review checkpoint, the broad repository suite was not green.
The core workstream recorded 6,134
passes, 37 failures, 56 skips and four errors, fixed one new inventory regression,
and reproduced all remaining 36 failures plus four errors on the actual inherited
baseline. The reconciliation above closes those 40 specific cases. It does not
close native, release or general workflow beta gates.
