# Beta readiness checkpoint 42 — per-job cancellation propagation

Status: SCOPED AUTOMATED IMPLEMENTATION COMPLETE; cross-process, native,
owner, and release acceptance pending (2026-09-09)

CP42 covers the in-process propagation path for cancelling an analysis job.
The durable job mutation remains authoritative: `AnalysisJobService.cancel`
and automation-grant revocation commit the SQLite cancellation request first,
then signal a content-free, process-local event.  The shared registry keys an
admission by the full job, lease-owner, and lease-token identity, so a wakeup
can be matched to the active attempt's full lease identity.  `signal_job`
wakes all active attempts for that durable job; the full key prevents an old
attempt's cleanup from deregistering a newer attempt.  A missing registration
is expected for queued, completed, or separately hosted work; the durable
fence still applies.

The worker registers the active attempt before a durable admission reread.  A
cancellation that wins after claim is therefore either delivered to the
registered event or observed by that reread before handler/provider work starts.
The execution context also rechecks the durable row at its cooperative
publication checkpoint (and existing stage/authorization/fingerprint
boundaries).  Cancellation or revocation stops before publication and carries
the persisted reason code.  If the exact publication has already committed,
the committed success takes precedence over a later cancel request; late
publication against a cancelled automation job is rejected without derived
rows.

The bounded source/runtime seam can use the admission event to wake an owned
provider wait.  This is cooperative cancellation, not forced interruption.
When cleanup is reported unconfirmed, the worker enters process-lifetime
quarantine: `run_once` refuses further admission and `start`/`stop` report the
uncertainty.  Worker-stop signaling is keyed to that worker's lease owner and
does not stop another worker's active attempt.  Production bootstrap passes
the API service's cancellation registry to the automation worker, preserving
one registry within the local composition.

The evidence for this checkpoint is the implementation and synthetic
coverage in `tests/test_analysis_job_cancellation_propagation.py` and
`tests/test_analysis_job_cancel_publication_races.py`: per-job wakeups,
grant-revocation reason preservation, admission-race recheck, worker-specific
stop wakeups, publication precedence, rejection of late publication, and
cleanup quarantine are represented there.  These tests were inspected for
scope. Existing root notes
remain: migration baseline **32passed, 2 failed due stale expected 64,
corrected to 65** and root **13passed (734434)** (migration2 +
publicationcontext11), historical evidence separate from the final scoped
CP42 suite.

The final scoped root suite is recorded as **35 passed in 60.78s** (terminal
`1b7727`) across cancellation propagation, publication races, fake Stdio
cancellation, cancellation signals, publication context, and queue. The fake
Stdio get-barrier wait interrupted in under 0.5s and fake close was verified;
cleanup-race coverage performs an actual cancellation, and overlapping-attempt
registry behavior is covered. This is scoped evidence, not full beta
acceptance.

A separate root regression is recorded as **92 passed in 1.43s**
(terminal `2528a5`) for runtime cancellation,
Codex transport boundary/text ingress, and automation metric scope.  It is
separate from the scoped CP42 suite and is not release acceptance evidence.

Limits remain explicit.  Signals and quarantine are process-local and do not
provide cross-process preemption, restart quarantine, a hard global runtime
deadline, or guaranteed termination of arbitrary blocking provider/model
work.  No real provider or model execution, native UI/owner acceptance, or
release acceptance is proven by this checkpoint.  The checkpoint remains
scoped-verified while broader global, cross-process, native, provider/model,
owner, and release acceptance remains pending.
Final root privacy scan `11e602` is not green: it reports exactly two known
synthetic `.tmp-cp34-privacy/test_current_source_review_the{0,1}/metrics.sqlite3`
artifacts and no new findings. Cleanup removal was not retried after policy
denial; release cleanliness remains outstanding. The accompanying
`diff --check` was clean, but the combined shell exit is not privacy evidence.
