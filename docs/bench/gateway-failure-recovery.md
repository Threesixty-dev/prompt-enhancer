# Gateway failure diagnostics and evaluator recovery

## Task card - 2026-10-24

- Scope: MA18 and W02/W03/W05/W07, from reviewed develop `9cd3016`.
- Reproduction: a diagnostics-only Rewrite attempt stops during embedding
  evaluation. The gateway transport replaces several different failures with
  the same synthetic HTTP 502; the core records only `evaluator_failed`.
  Bench incorrectly infers reconciliation need from generation bindings, so
  this remote evaluator interruption leaves the hold unset.
- Correction: proposed core `0.3.5` retains fixed transport categories through
  both process boundaries. Bench holds any admitted running/interrupted attempt
  until explicit reconciliation, including attempts with no generation binding.
- Evidence: nine regressions fail before the fixes: three evaluator transports,
  two acknowledgement/restart paths, and four evaluator-only engine/storage
  paths. After correction, 575 affected tests pass, including the complete
  Bench suite. Ten desktop/mobile checks verify error presentation, held retry,
  unchanged measurement states and reconnection without duplicate submission.
- Resources: synthetic fixtures, owned subprocesses and one loopback browser
  server. No live inference, model download, credential change or automatic retry
  is part of these checks.
- Remaining gates: source review, promotion, separate core publication, API and
  worker/relay deployment, a new pinned experiment revision, fresh qualification
  and independent onboarding. Historical runs and acceptance statuses remain.

## What the diagnostic means

The enhanced core opts into fixed, allowlisted categories. Existing interactive
inference clients retain their generic failure response. No upstream error body,
header, endpoint, token, exception text or model output enters the diagnostic.
Requests still verify TLS and route identity and keep their original size/time
limits. The transport makes one request; it never retries or follows redirects.

| Code | Observed condition |
| --- | --- |
| `gateway_request_invalid` | The configured alias or local request payload is invalid. |
| `gateway_connect_timeout` | Connection establishment did not finish within its limit. |
| `gateway_connect_failed` | An operating-system connection error occurred before connection completion. |
| `gateway_tls_failed` | TLS failed or the configured certificate pin did not match. |
| `gateway_io_timeout` | Request/response I/O timed out after connection establishment. |
| `gateway_io_failed` | Request/response I/O failed after connection establishment. |
| `gateway_protocol_error` | The HTTP exchange could not be parsed or validated. |
| `gateway_http_unauthorized` | The contacted HTTP service returned 401. |
| `gateway_http_forbidden` | The contacted HTTP service returned 403. |
| `gateway_http_rate_limited` | The contacted HTTP service returned 429. |
| `gateway_http_redirect` | The contacted HTTP service returned a 3xx response; no redirect was followed. |
| `gateway_http_client_error` | Another 4xx response was received. |
| `gateway_http_server_error` | A 5xx response was received. |
| `gateway_http_unexpected_status` | Another response status was received instead of 200. |
| `gateway_route_mismatch` | A required model-route header was missing or different. |
| `gateway_response_too_large` | The response exceeded the existing byte limit. |

An HTTP category does not identify which gateway/proxy/upstream originated it.
A category does not confirm remote completion. The core retains conservative
uncertainty, the failing stage and a non-retryable result; the UI and private
JSON/CSV export preserve the code. Unknown readings are never replaced by zero.

Core gateway adapter versions advance to chat `litellm-chat-v2`, embedding
`litellm-embedding.v2`, NLI `litellm-nli.v3`, rerank `litellm-rerank.v2` and rubric
`litellm-rubric.v3`. Successful measurement formulas, inputs and model pins do
not change. Existing artifact and adapter provenance remains historical.

## Recover deliberately

1. Preserve the run, submission receipt, partial results and private export.
2. Inspect the failing stage/code and both cleanup/reconciliation flags. An
   absent generation binding does not imply that no remote model was called.
3. Verify container cleanup and actual remote consumer/evaluator completion.
   A cancelled HTTP client or a diagnostic category alone is insufficient.
4. Record a short evidence reference through the existing reconciliation API/UI.
   This releases the admission hold and preserves the interrupted result.
5. Preflight and submit a deliberate new run with a new receipt and appropriate
   retry lineage. Never treat reconciliation as a successful attempt or replay
   automatically. Use the [run budgets](run-budgets.md).

Confirmed terminal work and work stopped before any attempt was admitted do not
gain a new reconciliation hold. Lost acknowledgements and worker restarts after
admission do. No database migration rewrites old results or retroactively adds
holds to historical rows; operators must inspect older uncertain runs explicitly.

The preserved core 0.3.4 failure remains unclassified. The new diagnostics cannot
recover evidence that the older adapter discarded. A different core pin requires
a new definition revision and separate comparison cohort; do not pool its results
with the partial core 0.3.4 matrix to claim one complete qualification.
