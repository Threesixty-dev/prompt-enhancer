# Workstream B task card

- Task: independently runnable versioned enhancement core; MA18/A20,
  W03/W06/W08, WF03/WF04, WP01-WP08. Broader workflow gates remain open.
- Approved source baseline: `6fa1100` plus the deliberately inherited uncommitted
  inference-provider work. `inherited-paths.txt` records the initial path/status
  inventory. Branch: `codex/enhancer-core-refactor`. No original or sibling
  checkout is edited. Inherited work is not staged wholesale or attributed here.
- Observable outcome: selected enhancer image accepts a fictional prompt,
  validates separate role bindings, evaluates, generates, reevaluates and returns
  structured evidence under matching experiment/run/unit/attempt identities.
  Consumer generation receives the measured baseline, typed objectives and
  bounded steering; independent reevaluation alone supplies result evidence.
- Allowed implementation: core package and application extraction, authoritative
  enhancement contracts/fixtures, backend tests, package metadata/lock, core
  image recipe, and this task documentation. A owns bench UI/storage/jobs and CI.
- Preserved contracts: interactive egress/approval, six metric meanings, unknown
  states, metrics-only prompt history, provider read-only ingestion and owner
  review/merge/publication authority.
- Resource bounds: explicit synthetic opt-in; one active execution by default,
  at most four by explicit configuration; at most 32 retained results by default,
  hard limit 128; input 320 KB, subject 20K characters, 24 context messages / 40K
  context characters, eight evaluators, 600-second maximum execution deadline.
  Process cleanup is bounded separately; uncertain remote work is quarantined.
- Safety correction: scanner already excludes `.git` directories; it now also
  excludes the root managed-worktree `.git` metadata file. Source secret/PII
  canaries and symlink boundaries are still tested and enforced.
- Architecture review: [proposal](proposal.md) remains pending. General workflow,
  live provider/model, native and release gates are not closed by synthetic tests.
- Handoff: `contracts/enhancement/*.schema.json`, `contracts/enhancement/examples/`,
  `docs/enhancement-core/protocol.md`, and `containers/enhancement-core/Dockerfile`.
  The supervisor transfers these B-owned paths to A; no sibling edits are made.
- Evidence: command outcomes and remaining gates are recorded in
  [validation](validation.md). No source publication or deployment was performed.
