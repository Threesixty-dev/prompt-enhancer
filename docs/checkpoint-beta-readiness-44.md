# Beta readiness checkpoint 44 — artifact capture outcome truthfulness

Status: SCOPED AUTOMATED IMPLEMENTATION COMPLETE; owner/native/release acceptance pending (2026-09-09)

CP44 records the scoped artifact-capture outcome-truthfulness work across
`AgentArtifactCaptureDialog`, `AgentWorkspacePane`, and `AgentPage`. The dialog
reviews metadata first, sends no file bytes in the review, and binds capture to
the reviewed path, digest, and byte size. A stale or missing file, size limit,
or other definite service receipt is reported as “nothing captured”; a lost,
malformed, or otherwise ambiguous capture response is reported as unknown.
Unknown outcome blocks immediate resubmission, requests one read-only saved-
artifacts refresh through the callback, and does not call the success callback.

The inspected UI guards same-tick double clicks with the request ref in
addition to React state, ignores stale revisions and aborted/unmounted
requests, and keeps preview failures distinct from capture uncertainty. Native
user-presence unavailability keeps capture read-only. The typed
`native_confirmation_declined_before_dispatch` outcome is emitted only for a
strict local-bridge `user_declined` result before the capture request is sent;
the dialog leaves that case retryable and does not invoke the uncertainty
callback. An arbitrary HTTP 403 remains unknown, since it does not prove that
the mutation was never dispatched.

The authoritative terminal source-of-truth evidence records 273 tests passed in
`63454a` (18.62s) across the owning dialog, workspace, and HTTP-transport
coverage. Root build `884c15` passed after correcting fixture typing; an earlier
build (`da2999`) failed on a literal-false fixture and is superseded. Terra's
isolated page-integration output reports 1 passed and 196 skipped, covering the
initial artifact read plus one saved-artifacts refresh after a lost capture,
with no success notice; that output remains non-authoritative. The terminal
root AgentPage gate `5f9677` records 197 passed in 301.56s. Process check
`fdae38` found zero matching AgentPage node processes, the diff check was green,
and the read-only audit evidenced no leak. Existing backend evidence is the
two-test receipt `b6b7fd`, covering revision binding, metadata-only review, and
content-free boundaries. These are synthetic/scoped evidence only: this
checkpoint makes no broad, native-result, provider, or model execution claim.

The capture dedupe identity is limited to the current session plus path, digest,
and size; it is not an exactly-once guarantee. General built-loopback browser
regression `aeebeb` records 29 passed in 32.4s;
terminal cleanup `2be5b7` confirms cleanup, listener release, temporary removal,
and zero model runtimes. This is general regression only, not real native
artifact-capture evidence. Privacy scan `7b659a` is not green: it reports the
same two known synthetic CP34 database artifacts and no new findings.
Owner/native/release acceptance remains pending. No test, process, browser run,
or commit was launched by this documentation update.
