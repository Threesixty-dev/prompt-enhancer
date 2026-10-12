# Core validation evidence

Date: 2026-10-12. Branch: `codex/enhancer-core-refactor`. Baseline: `6fa1100`
with inherited inference-provider changes recorded separately. All task inputs,
responses and test identities are synthetic. No real sessions, account files,
personal endpoints or provider credentials were inspected.

## Passing bounded evidence

- Final focused command: `python -m pytest -q` with
  `test_enhancement_contracts.py`, `test_enhancement_core.py`,
  `test_enhancement_adapters.py`, `test_enhancement_process.py`,
  `test_enhancement_packaging.py`, `test_prompt_check.py`, `test_model_reply.py`,
  `test_coaching_metric_pack.py`, `test_litellm.py`,
  `test_inference_providers.py`, `test_local_text_model_evaluation.py`,
  `test_privacy_scan.py`, and `test_scanner_symlink.py`: **184 passed**.
  Tests reside under `tests/`. HTTP/TLS/process tests ran with local socket
  access after the sandbox denied loopback bind; no test was weakened/skipped
  to conceal that environment restriction.
- Final adapter forwarding check: `python -m pytest -q
  tests/test_enhancement_adapters.py`: **21 passed**, including two additional
  tests proving `ProcessConsumer` forwards the exact generation context for
  both supported consumer providers. This overlaps the focused run above.
- Contracts: exported schemas equal authoritative models; fictional request,
  result and generation-context fixtures validate. Unsupported versions,
  bindings, controls, targets, invalid Unicode, extra fields and malformed model
  replies fail. Unknown/abstained/categorical values remain distinct.
- Flow: both strategies evaluate before and after; consumer adapters receive
  measured baseline, provenance, typed objective and steering. Changed objectives
  and steering are tested through both ACP and inference adapters. The consumer
  cannot return evaluator evidence. Partial evaluator failure preserves completed
  measurements. Fixed-profile comparisons, separate assertion outcomes and
  effective configuration are covered.
- Lifecycle: duplicate/conflicting identity, bounded admission/retention,
  progress, immediate/in-flight cancellation, deadline, local child exit,
  uncertain remote cleanup quarantine and terminal deletion are tested.
- Existing Prompt Check, coaching metrics, strict replies and inference behavior
  pass the affected regressions. Application prompt history still stores only
  metrics/content-free fields; the headless core mounts no history/session APIs.
- `uv lock --offline --check`: passed. `uv sync --frozen --extra dev
  --extra enhancement-acp`: passed in the task environment. Core package imports
  and CLI are executable. The SDK is pinned to 1.49.1; image Python is 3.12.
- `python -m compileall -q src tests scripts`: passed.
- `python scripts/privacy_scan.py`: passed. Git metadata exclusion stays narrow;
  source secret/PII canaries and root `.git` symlink rejection remain enforced.
- `python scripts/render_architecture_atlas.py --check`: passed; this verifies
  consistency, not acceptance of a new architecture or real-model gate.
- `git diff --check`: passed. No inherited cohort was staged wholesale.

## Packaged evidence

The core Docker recipe builds locally using its frozen lock and pinned base
image. The pinned ACP SDK imports in a network-disabled image. A disposable
network-namespace container and a read-only, unprivileged enhancer container
exercise actual loopback HTTP: authenticated readiness/capabilities, execution,
six deterministic before/after readings, duplicate submission, result retrieval
and terminal deletion. Both containers are removed in the validation cleanup.
No host port is published and no source/image is uploaded.

Workstream B's default measured-generation local image ID:
`sha256:8769f889a14ba6e5f2e9ab67885402f105dc7af23ea3fb3e055fa80abc9118b1`.
This is a local image ID, not a published registry digest or release certificate.
Workstream A separately owns bench persistence/container-lifecycle integration;
this core HTTP check does not stand in for that test.

### Workstream A model-enabled integration handoff

On 2026-10-12, the supervisor supplied a verified command receipt from
Workstream A's integrated smoke using the locally built model-enabled image
variant. This evidence is attributed to A; B did not rerun the smoke for this
documentation handoff. The default-image ID above does not identify A's variant.

- Real core containers completed **2 runs / 4 attempts**, preserving measured
  generation context and changed objective/steering overrides, with persistence
  and cleanup verified.
- Torch/Transformers imports and local evaluator alias initialization passed.
  Operator-owned cache/resource wiring was exercised with **4 GiB memory and
  2 CPU limits**; a cache write was rejected with `EROFS`, verifying the read-only
  mount. Missing snapshots were rejected.
- Receipt flags: `model_cache_resources_verified=true`,
  `missing_snapshot_rejected=true`, `cleanup_confirmed=true`,
  `weights_loaded=false`, `gpu_qualified=false`, and
  `live_consumer_qualified=false`.

The optional model-enabled image therefore has local build and runtime evidence.
This does not establish genuine model inference, GPU qualification, a live
consumer connection, or execution on another target platform. No weights were
loaded in this integrated smoke.

## Broad suite classification

The full repository suite ran once: **6,134 passed, 37 failed, 56 skipped,
4 errors** in 19m16s. The full suite was not rerun wholesale.

| Classification | Evidence |
| --- | --- |
| New and fixed | The core worker was missing from the direct-network inventory. It now has the exact `synthetic_benchmark_request` registration; the unchanged strict inventory semantics and companion egress/network guards pass: **3 passed** |
| Reproduced inherited baseline | All **40 residual nodes** were rerun on an isolated copy of `6fa1100` plus the actual recorded inherited dirty source files, using the baseline's own frozen `dev` environment: **36 failed, 4 errors**, matching the residual failing/error nodes |
| Initial environment limit, resolved | Sandbox denial of loopback bind was resolved by authorized local socket access; the real CLI/TLS tests pass and no test was skipped to hide it |
| Residual classification limit | Baseline reproduction establishes pre-existing failing outcomes, not root-cause fixes or a green full-suite gate. Detailed repair/causal diagnosis of these baseline failures remains outside this core change |

The original checkout's HEAD and path/status inventory matched the recorded
approved baseline before the copy. It was read only. Byte comparisons confirmed
only three inherited paths differ in this worktree: `src/prompt_enhancer/application/prompt_check.py`,
`src/prompt_enhancer/application/egress/classification.py`, and the network inventory test in
`tests/test_windows_distribution_hardening.py`; all three edits are intentional core
changes. The inherited lock's package versions are unchanged; 94 packages are
added for the optional ACP dependency. Baseline reproduction uses the original
lock without that extra, so optional dependency additions do not explain the
reproduced failures.

The residual families cover catalog migrations, application HTTP composition,
Agent controller/orchestration, MCP guarded host/runtime/package management,
wheel/build-manifest distribution, and a synthetic Claude analysis-lane test.
`baseline-failures.json` lists the exact 40 synthetic test node outcomes.
Temporary JUnit/source receipts remain outside the repository; no test traces
or machine paths are included here.

The first migration failure also reproduces on clean HEAD with the same runtime:
`test_catalog_v7_artifact_lineage_migrates_to_document_preview_without_rewrite`
raises `AgentCatalogError: agent_catalog_storage_unavailable`. Both that test and
its SQLite implementation are unchanged by this task. No unrelated baseline
implementation was repaired or safety test weakened.

## Open external gates

| Gate | Evidence still required |
| --- | --- |
| Live static consumer | Operator-supplied dedicated worker URL/credential and pinned model identity; confirm ACP read-only mode, fresh trial context, protocol-reported model, finished state and remote cleanup with fictional inputs |
| Live gateway evaluator | Independently supplied evaluation binding; verify actual loaded revision, response identity, retention policy, typed rubric output, timeout/cancellation and model consistency across both passes |
| Local model inference | Approved offline pinned snapshots/device; real classifier, embedding and rubric inference, memory/cleanup qualification; no weights downloaded or loaded during this task |
| Model-enabled image on other platforms | A's local build/runtime/cache/resource evidence is recorded above; build and execute `ENHANCEMENT_WITH_MODELS=1` on each additional selected target platform. Genuine model/GPU qualification remains separate |
| Architecture/release | Owner acceptance of the proposal, central atlas/ledger integration, broader platform gates and deliberate publication/deployment authority |

Synthetic provider tests and SDK imports do not satisfy those live gates.
The missing live prerequisites are never sourced from provider credential files
or local configuration. No live model, native approval, production worker,
multi-user deployment, GPU scheduler or release is claimed qualified.
