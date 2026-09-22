# Beta readiness checkpoint 41 — automation revocation and bounded cancellation

Status: SCOPED AUTOMATED IMPLEMENTATION COMPLETE; global deadline,
cross-process, native, owner, and release acceptance pending (2026-09-08)

CP41 narrows the project-automation revocation language to the durable fact
the current response proves: the exact grant was revoked. Before confirmation,
the UI says that active work may still be stopping afterward and directs the
owner to the Job Centre. After a revoked grant is returned, the receipt says
the same thing and preserves the fact that durable receipts remain. A failed
revocation does not show the success receipt or raw transport error.

The current bounded implementation reuses the durable publication cutoff in
runtime scope and Codex waiting. Bad-clock, nested-scope, and late-response
paths are fenced; helper cleanup errors are sanitized; and the worker's
process-lifetime quarantine blocks `run_once`/`start` while reporting stop
uncertainty. These are local process-lifetime guards only: no cross-process
restart quarantine or hard global preemption is claimed.

The 1,800-second value remains a declared runtime budget, not a hard global
execution deadline. The scheduler receipt continues to distinguish the
restart-durable session-quality publication cutoff (enforced) from blocking
call force-stop and hard runtime preemption (not provided/not enforced).

Final scoped frontend evidence is **17/17** for
`ProjectAutomationSettings.test.tsx` (`3bd335`), including successful and
failed revocation wording; shared chat-cancellation evidence is **19/19**
(`8d3d73`). Source integration is **1/1** (`507d5d`) using the actual
worker/handler/service/CodexSource path with a synthetic client transport
interrupting at list time; no run was persisted. Stdio waiting was tested
separately. The same-worker quarantine check is **1/1** (`c6710f`), and the
production build plus TypeScript check passed (`c8397b`) with port 8765 absent.
The seven-file root suite is **116/116** in 47.32 seconds (`82864f`, terminal
`70066`); an earlier ambiguous agent report was not treated as evidence, and
no matching process was found before the independent rerun (`5cd457`). The
final general built-loopback regression is **29/29** in 29.8 seconds
(`cf3694`), with cleanup confirmed, zero model runtimes, and no server failure.
This is general regression evidence, not dedicated browser, native-owner, or
provider execution proof.

The source contract still needs a typed cancellation outcome if the product is
to distinguish queued work cancelled immediately from active cancellation
requested and any cleanup that remains unconfirmed. Current backend baselines
are transport **4** (`43d2ff`) and publication-deadline **16** (`16acb6`)
tests. No hard global runtime deadline, cross-process restart quarantine, native
acceptance, physical helper cleanup proof, provider/model run, or release
acceptance is claimed here; the overall goal remains active.
