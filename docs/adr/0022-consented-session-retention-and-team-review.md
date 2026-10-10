# ADR 0022: Consented session retention and team prompt review

- Status: **proposed**. The owner requested the product requirement explicitly;
  retention architecture, deployment and beta inclusion are not yet approved.
- Date: 2026-10-08.
- Related: ADRs 0005, 0011, 0016 and 0020. None is silently superseded.

## Context

The owner wants team leaders to review shared prompts with metrics and session
activity. Imported analytics stores minimized events/metrics and sensitive local
labels, not complete transcripts. The reader obtains bounded text on demand.
Authored Agent history has a separate retention setting. The current team
contract exchanges numeric snapshots, not prompt text.

Analysis does not always require raw-content retention. Reproducible retrospective
analysis after provider-history removal, however, needs an explicit retained-
content capability. Do not imply that all prompts are already saved.

## Proposed boundary

1. Separate capture for local analysis, retention of selected content, and
   disclosure to another person. Enabling one does not enable the others.
2. Keep minimized analytics apart from any future private content vault and
   reviewed team-content store. Do not put text/tool payloads in the numeric team
   envelope, metrics logs or content-free job records.
3. If durable capture is selected, bind records to source/provider/adapter/schema
   versions, event identity, source revision, consent, redaction and completeness.
   Bounded, redacted or partial records must never be labeled a full transcript.
4. Review encryption/key lifecycle, access, retention, capacity, migration,
   backup and deletion before implementing a raw-content vault. Do not invent
   retention periods or deployment defaults without owner acceptance.
5. Team review needs authenticated identities and explicit project/session/data-
   class grants, revocation, access receipts and separately authorized exports.
   A manager role never means blanket access to private sessions.
6. Metrics retain their source scope. Prose and model judgments are not execution
   receipts. Private coaching/affect stays excluded under current team policy.

## Alternatives and consequences

On-demand reads minimize duplication but cannot guarantee replay if provider
history disappears or changes. Opt-in retained snapshots enable replay but add
sensitive storage, key recovery, deletion and capacity obligations. Unrestricted
retention/upload of all machine history is not the selected design.

The account-free local beta remains independent of team infrastructure. The owner
must separately decide whether TR01–TR08 become beta gates. An accepted product
requirement is not evidence that its data path exists.

See [the work package](../work-packages/team-prompt-review.md) and
[observed storage behavior](../architecture/session-data-lifecycle.md).
Documentation does not authorize real capture, network publication, provider-data
inspection by coding agents, schema changes or new access grants.
