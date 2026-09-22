# Beta readiness checkpoint 38 — governed web-fetch capability

Status: IN PROGRESS. This checkpoint records the bounded WSP-07 frontend
capability and opt-in slice. It does not claim governed web-fetch acceptance,
native acceptance, beta, release, or whole-product completion.

## Scope

The intended workflow is an explicit, default-off opt-in for governed public
HTTPS requests that may return plain text or HTML. The UI requires both the
server capability contract and the existing native confirmation capability.
Each URL request remains separately native-approved; the copy explains that an
approved request leaves this machine and sends no cookies or credentials and
does not follow redirects. Durable resume does not silently restore this
authority.

The frontend adds strict capability-contract parsing, a bounded capability
read, explicit retry, default-off session settings, and transport replacement
fencing. Unsupported, malformed, rejected, timed-out, and stale capability
responses remain unavailable and cannot turn the opt-in on automatically.

## Evidence boundary

The independent governed-adapter and policy suite passed **33/33** (`f609f7`),
and the full local-agent module passed **57/57** (`ed7e1c`). Schema validation
passed **6/6** (`f7548f`); the production build passed (`13c2aa`). The exact
stdlib `HTTPConnection` delayed-body/detach and socket-cleanup diagnostic
passed (`0e1451`). The earlier socket-pair reds (`c20779`, then `528818`) are
retained as history: the blocking-reader approach and the rejected 50 ms
timeout workaround were replaced by a select-driven raw reader beneath the
standard-library parser; its targeted replacement gate passed **4/4**
(`4d359e`). The general built integration passed **28/28** (`9efc3e`) with
listener, runtime, temporary-resource cleanup, and zero-model checks. These
are automated synthetic receipts, not native or owner acceptance.

The complete frontend suite passed **3,436/3,436 across 240 files** (`26665f`).
The dedicated synthetic WSP-07 browser suite passed **8/8** with port-4173
cleanup confirmed. The production-built WSP-07 journey passed **29/29**
(`b97baa`; wrapper `3b28f5`), including the real capability schema/no-store and
native-unavailable disabled state; listener, runtime, temporary-resource
cleanup, zero models, and no server failure were confirmed. The two earlier
built-fixture reds (`ae4dbb`, `7cf8d0`) were corrected before this terminal
run and remain history only.

## Current limits

The select-driven reader preserves the standard-library status/header/chunked
parser while making raw reads deadline- and cancellation-aware; it retains the
actual socket across `Connection: close` handoff and closes it only after the
response reader releases ownership. The scope still contains no real fetch,
provider, model, native action, app restart, or network-service execution.

The latest privacy scan remains red
(`564e73`) for exactly two residual synthetic database artifacts; no cleanup
was attempted.

Native, owner, beta, and release acceptance remain unverified.

See [CP37](checkpoint-beta-readiness-37.md) for the prior frontend baseline and
the [finish-goal tracker](prompt-enhancer-finish-goal-2026-08-29.md) and
[convergence audit](prompt-enhancer-convergence-audit-2026-09-04.md) for the
authoritative workstream status.
