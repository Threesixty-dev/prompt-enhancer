# Experiment bench implementation

Status: implemented for deterministic profiles and configured consumer/gateway
adapters; local validation passed; owner review required.
Date: 2026-10-12. Branch: `codex/test-bench-infrastructure`.

## Task card

- Task/atlas/gates: bench MWE; W02/W03/W05/W07 and WP03/WP05/WP07/WP08
  are relevant boundaries, not gates closed by this standalone bench.
- Approved baseline: `6fa1100e01e37f477ca7b65daba51706927f2502` plus 55
  inherited inference-provider files. A content-free hash inventory was recorded
  outside the repository before edits. Inherited files are outside this patch.
- Outcome: import an immutable experiment revision and image digest, execute the
  newest eligible revision once, inspect correlated results, and rerun from the UI
  with immutable effective settings. Interrupted agent calls are never replayed.
- Owned files: `bench/`, `deployment/bench/`, `tests/bench/`, `docs/bench/`, and
  `.github/workflows/bench-*.yml`. Core and `contracts/enhancement/` belong to B.
- Contract: consume B's versioned headless API and shared schemas. There is no
  independent testing harness and no new general workflow builder.
- Evidence required: synthetic durable/concurrent/fault/restart integration,
  desktop/mobile browser checks, core image smoke, privacy scan, build/config
  validation. Real consumer/evaluator qualification remains separately visible.
- Bounds: one active enhancer container and one unit at a time initially;
  per-stage and whole-run deadlines, finite HTTP bodies and subprocess timeouts.
- Review: proposed architecture remains pending owner acceptance. No publication,
  merge, live deployment, provider-session access or model downloads are implied.

## Reference observations

- ADE/OpenHands: workers are static, use `RemoteWorkspace` and `ACPAgent`, and
  have no Docker socket. The durable dispatcher uses transactional claim and
  unique event keys; restart marks an uncertain delivered turn instead of replay.
  The PR-review API is not an enhancer-compatible consumer endpoint.
- News Feed Concierge: durable jobs and delivery reconciliation distinguish
  uncertain side effects. Persistent volumes need explicit restart/restore proof.
- Threesixty: observed generation and spec hash identify the desired state being
  reconciled. Events describe transitions and do not replace the durable state.

## Progress

- Baseline, ownership, privacy boundaries and relevant gates inspected.
- Assigned branch created; inherited changes preserved.
- Durable bench, UI, GitOps import, bounded worker, CI and deployment recipes implemented.
- Objective/steering overrides are frozen per unit and matched to core results.
- Dedicated network-isolated consumer, private Unix-socket API/gateway bridges,
  bounded HTTPS relay and supervised transport lifecycle implemented and checked.
- Synthetic and real-container evidence is recorded in the evidence ledger.
- Operator-owned model-cache/device/resource wiring and distinct model-enabled
  publication variants are implemented and validated with synthetic fixtures and
  real containers. Live deployment/model/GPU qualification remains external.
