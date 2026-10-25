# Consumer failure reporting

## Release status - 2026-10-25

Owner-approved PRs #94/#95 complete source review and promotion. Core 0.3.7
passes publication, offline runtime identity/tokenizer verification, probe cleanup
and Bench registration. The successful publication retry reuses the immutable
image built by the first attempt. API/UI deployment verifies the reviewed main
revision through both controller health and protected readiness checks.

The subsequent owner-attested recovery permitted the reviewed consumer, worker
and relay rollout. Runtime image, environment, mount, namespace and authenticated
readiness checks passed. The first revision-6 smoke reached generation after
completing its before evaluations, then exposed a separate
[SDK subscriber cleanup defect](consumer-retention.md#finished-subscriber-release---2026-10-25).
That failure is preserved and no later smoke/main attempts were submitted.
Consumer cleanup correction, review/rollout and complete live qualification
remain open; acceptance statuses are unchanged.

## Task card - 2026-10-25

- Scope: MA18 and W02/W03/W05/W07, from reviewed develop `b3d42e7`.
- Reproduction: the relay changes every upstream HTTP rejection into 502.
  The pinned ACP adapter can then expose a provider error as assistant text.
  OpenHands records a finished turn; the workflow reports invalid review JSON.
  The synthetic qualification's earlier failures remain preserved. Their exact
  historical cause cannot be reconstructed from the discarded response details.
- Correction: proposed core 0.3.7, a versioned consumer compatibility adapter,
  preserved HTTP status categories, and explanatory Bench error messages.
- Preserved contracts: model inputs and outputs, review JSON validation,
  evaluator order, missing-value semantics, isolated consumer networking,
  immutable historical results, and operator-controlled reconciliation.
- Resources: synthetic protocol fixtures, bounded owned processes, and an
  isolated consumer container with no network or provider-account access.
- Evidence: 612 affected core/Bench tests and 14 desktop/mobile checks pass.
  The built consumer passes authenticated startup/profile/PATH verification.
  Its isolated pinned-SDK probe reproduces the legacy failure and verifies the
  corrected failure and success paths without a provider account.
- Remaining gates: specific source review/promotion, separate core publication,
  coordinated consumer/worker/relay deployment, a new pinned experiment revision,
  fresh qualification and independent onboarding. Running cohorts retain their
  existing deployment and pins. Acceptance statuses are unchanged.

## Why a finished turn was insufficient

`@agentclientprotocol/codex-acp` 1.10.0 supports the version-1 AIR
`sessionFailure` capability in its ACP metadata. Without negotiation, some
non-authentication provider failures are emitted as ordinary assistant text.
OpenHands SDK 1.49.1 does not negotiate or consume that extension. Its finished
turn alone therefore cannot establish that the provider supplied a model answer.

The consumer compatibility adapter negotiates this capability and requires the
server to advertise it. A terminal failure on the response to the corresponding
`session/prompt` request becomes a fixed JSON-RPC error. Its only retained cause
is an allowlisted category. Provider titles, details, tokens and response bodies
are discarded. The adapter never classifies assistant text, attributes a late
session notification to a different turn, or automatically retries a request.
Warnings, cancellation responses and successful replies retain their semantics.
Malformed negotiation or unsupported versions stop explicitly.

The adapter is restricted to the pinned ACP package and SDK versions. The
consumer image pins ACP 1.10.0 explicitly and selects the compatibility command
through its private process PATH. Its readiness metadata advertises
`bench-acp-failure.v1`; core 0.3.7 requires that profile before starting a turn.
Core provenance advances to `openhands-acp-1.49.1.v6`.

The Apache-2.0 ACP package comes from the official npm registry and the
`agentclientprotocol/codex-acp` repository at tag `v1.10.0`. It installs in the
consumer's private vendor prefix, avoiding the base image's existing executable.
The compatibility code is local and version gated; no vendor source is copied
into the repository. OpenHands SDK remains pinned to the existing MIT-licensed
version 1.49.1.

The core accepts a category only from a typed SDK `ConversationErrorEvent` with
the exact fixed error representation produced by the compatibility adapter.
Arbitrary exception text, similar model text and unrecognized details retain an
unknown cause. The category survives the worker boundary, stored result,
inspection and private export. Existing review-contract failures still report
their safe JSON/schema validation reason.

## Interpretation

| Code | Evidence and limitation |
| --- | --- |
| `consumer_failure_protocol_unavailable` | The consumer does not advertise the required profile. No model turn was started. |
| `consumer_upstream_connection` | The ACP server reported a connection failure; remote completion is unconfirmed. |
| `consumer_upstream_access` | The ACP server reported an access failure. This does not distinguish a credential from a permission problem. |
| `consumer_upstream_limit` | The ACP server reported a limit. Its exact budget, rate, context or other limit remains unknown. |
| `consumer_upstream_request` | The ACP server reported a rejected request. |
| `consumer_upstream_service` | The ACP server reported a service failure. |
| `consumer_upstream_unknown` | A provider/protocol failure was reported without a recognized safe category. |

Every upstream category retains remote uncertainty and the existing recovery
hold. A completed ACP error exchange does not prove a remote model stopped.
The UI explains the category and continues to require stop evidence before
reconciliation. No failed or unexecuted attempt counts as a successful review.

The relay separately preserves upstream 4xx/5xx statuses with fixed
`gateway_http_*` codes, without forwarding the upstream body or headers.
Redirects remain refused. Authentication, TLS verification, capacity limits and
response bounds are unchanged. The relay itself performs no retry.

## Qualification boundaries

The isolated SDK probe exercises three cases: the legacy synthetic error becomes
a finished turn, the guarded error becomes an SDK error with its safe category,
and the guarded success retains its original output. It verifies SDK 1.49.1 and
uses no provider account, real model or network. The packaged probe reads the
adapter from the built consumer image; an explicit source override is only a
compatibility test and is reported separately.

The packaged checks use the built consumer, network disabled, a read-only root,
synthetic credentials, temporary state and bounded resources. Static startup
verifies the SDK/ACP/Codex versions, authenticated retention profile, and the
actual Agent Server process PATH. Both probes pass and remove their owned
containers. The temporary build harness initially copied unreadable startup
files; rebuilding with the repository's normal file permissions corrected that
test artifact. No production deployment was used as a candidate test.

Before a future rollout, settle every active operation and recovery hold. Deploy
the reviewed consumer and relay, verify the profile and pinned command selection,
then qualify a new definition revision selecting the separately published core
0.3.7. Keep the earlier cohort and artifact pins available. Rollback restores the
previous reviewed images and compatible core selection; it does not rewrite
stored failures. The new core explicitly refuses an older unguarded consumer.

Live results from core 0.3.6 are historical evidence for that deployed combination.
Do not retroactively reclassify its invalid reviews, replace failed rows with a
retry, or combine a future core/consumer version into the same scientific cohort.
