# Team prompt and metric review — explicit product requirement

Recorded: 2026-10-08, at the owner's request. Implementation: **not delivered**.
This adds a named product requirement, not a new accepted local-beta gate.
Teams remain deferred until the owner explicitly assigns this milestone.
No collection, persistence, sharing or access is enabled by this document.

## Required user outcome

A team leader can browse deliberately shared projects/sessions, inspect shared
prompts and permitted conversation/tool context, and see their corresponding
metrics, coverage, provenance and verification evidence in the same review.
Members can see what is shared and with whom. A role alone is not permission to
read every private session on every device. "All prompts" means all supported,
authorized records in the selected scope, not every prompt on a PC.

The existing numeric team control plane and synthetic Team Analytics preview do
not implement this requirement. Content sharing needs its own boundary; it must
not add free text to the allowlisted metric-snapshot envelope.

## Work items and acceptance gates

| ID | Deliverable | Required passing evidence |
| --- | --- | --- |
| TR01 | Source/data contract | Enumerate messages, tool calls/results, lifecycle, usage, approvals, artifacts and evidence by provider/version. Each field declares retained/ephemeral/unsupported/redacted/truncated state. Missing records cannot be labeled a complete transcript. |
| TR02 | Explicit capture scope | Users select sources/projects/sessions and data classes independently of sharing. Select/cancel/revoke work; unrelated/private sessions remain unread. Ongoing capture must declare scope, start time and backfill behavior. |
| TR03 | Private retained-content store, if approved | Repeated analysis can use an immutable retained snapshot instead of mutable provider files. Separately review encryption/key recovery, retention, storage bounds, migrations, backup/restore and deletion. An enum named raw_vault is not implementation. |
| TR04 | Identity and grants | Authenticated tenant/member/device identities and explicit project/session/data-class grants. Wrong tenant, role escalation, expired/revoked grants and stale caches cannot read content. Personal provider CLI credentials are never a team backend. |
| TR05 | Reviewed publication | Preview exact shared content/metric classes, destination, retention and redaction. Private coaching/affect and unapproved tool payloads stay excluded. No silent upload; ordinary analytics stays content-minimized. |
| TR06 | Leader review views | Filter allowed project/member/session/time; inspect shared prompts and permitted context/tool timeline alongside metrics. Bind metrics to exact source revision/window and rubric/model versions. Display denominator, missingness, coverage and stale state; no universal employee ranking. |
| TR07 | Revocation, deletion, export and audit | Content-free access receipts; visible sharing policy. Revoke future reads/cached authority; test deletion and backup expiry. Export needs separate permission and preview. Explain that already downloaded copies cannot be recalled automatically. |
| TR08 | End-to-end qualification | Two isolated synthetic member installations and a leader exercise publish/review/revoke/restart against real supported transport/storage. Prove tenant isolation and failed/offline recovery, then applicable native/installed journeys. Demo fixtures alone cannot close this gate. |

Order: TR01 → TR02 plus owner-reviewed retention design → TR03/TR04 → TR05 →
TR06/TR07 → TR08. Reuse existing foundations only after checking their actual
capabilities. No TR gate has passing implementation evidence.

## Decisions before implementation

- Milestone: post-beta team release by default; including it in the current beta
  requires an explicit scope amendment.
- Capture: on-demand provider reads or retained selected sessions for repeatable
  analysis. The current app has no universal imported transcript archive.
- Data classes: prompts, replies, tool arguments/results, attachments, code/diffs
  and provider-exposed reasoning each need explicit scope. Never infer hidden
  reasoning or treat arbitrary tool stdout as proof of success.
- Deployment, encryption/key ownership, retention duration, storage limits,
  deletion/backup behavior and member-notice policy need owner review.
- Aggregate/individual disclosure remains distinct from prompt sharing. Private
  coaching signals do not become manager-visible when a prompt is shared.

Do not invent endpoints, identities, secret keys or unlimited retention. The
owner reviews the ADR and implementation PRs. Ingestion remains read-only.

## References

- [ADR 0022: proposed retention and team review boundary](../adr/0022-consented-session-retention-and-team-review.md)
- [Current session-data lifecycle](../architecture/session-data-lifecycle.md)
- [ADR 0005: content-free team foundation](../adr/0005-team-control-plane-boundary.md)
- [Readiness ledger](../product-readiness-matrix-2026-09-12.md)
