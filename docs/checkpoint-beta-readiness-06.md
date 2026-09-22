# Beta-readiness checkpoint 06

Status: bounded automated validation complete; this is not beta, beta-v1, or
release completion.

## Scope

AgentRuntimeControl now distinguishes a failed coordinator refresh from an
operation failure.
The page must distinguish a failed runtime read from an operation failure:
cached last-confirmed runtime data may remain visible as stale context, but it
must not be presented as current Ready/Applied authority. The selected model,
device/context choices, and the text draft remain in place while recovery is
pending.

The runtime GET has a local 10-second deadline. A timeout aborts the status
read, releases Refresh, ignores any late response, and retains only the
guarded exact alias/revision needed for an existing Stop attempt. Retained
runtime details are labeled last-confirmed. An unchanged model/device/context
selection is not marked pending merely because status is unverified; genuine
user draft choices remain pending as entered.

Apply remains blocked until a fresh runtime read succeeds. A cached served
alias/revision is retained only for an existing guarded exact Stop attempt; it
does not create new authority, bypass backend compare-and-set checks, or start
or load a model. A failed read clears current frontend runtime capability
evidence; legacy text-send checks remain backend-authoritative and unchanged.
Manual Refresh recovers the state without auto-loading a model.

Legacy AgentPage catalogue-unknown, send, and backend-verification behavior is
intentionally unchanged. Owner/native/physical-GPU/release acceptance remains
open.

## Evidence boundary

Final targeted and disposable integration receipts:

| Gate | Final result |
| --- | --- |
| Owning runtime-control tests | **47/47 passed** (6.11s) |
| Strict frontend TypeScript | **Passed** for the explicit fixture/spec list |
| Final focused runtime-recovery/accessibility browser checks | **12/12 passed** (10.6s) |
| Production build | **Passed**; existing AgentPage 656.16 KB chunk warning |
| Built disposable real-loopback browser | **16/16 passed** (18.1s); listener released, temporary state removed, cleanup confirmed, zero model runtimes, no startup/server-thread failures |

The historical pre-cleanup full snapshot (2947/2947 frontend tests across 198
files, 410.80s; browser 210 passed, 6 intentional screenshot skips, 0 failed,
3.5 min) is not represented as a rerun after final cleanup. A regression was
red before the fix (timer expected 0, got 1) and green after the fix in the
final owning gates. Post-doc privacy scan passed and documentation diff check
passed after this update.
Earlier checkpoint receipts remain unchanged.

No native, model/GPU, application reload/restart, installation, real provider
data, commit, or push action was used here.

## Owner click-later checks

1. Cause or observe a runtime status read failure through the normal UI and
   confirm the runtime is labeled stale/unavailable rather than Ready/Applied;
   verify the selected model, device/context choices, and draft remain.
2. Confirm Apply is unavailable while the read is stale, then use the visible
   Refresh control and verify recovery requires a fresh read and does not
   automatically load a model.
3. With a previously confirmed served model, use the normal Stop control during
   a stale-read state and confirm it is limited to that exact guarded runtime;
   verify no new model authority is granted.

## Next candidate checkpoint

Remaining runtime/placement/model compatibility and native acceptance gaps
remain in the feature register; the next bounded checkpoint will be chosen from
verified evidence, not a parity or release claim.
