# Local agent metric-evidence API

This boundary lets a local coding agent prepare a small, canonical JSON file
that Prompt Enhancer can validate and turn into an **unconfirmed** metric
proposal. It does not let the agent assign a score, declare task success, or
confirm its own evidence.

## Current coverage

The v1 file contract covers the five collaboration lifecycle families:

- ambiguity resolution;
- clarification yield;
- exploration conversion;
- scope-change discipline;
- rework-candidate rate.

It does not accept prose, transcript excerpts, paths, model rationale, numeric
scores, or objective-verification claims. Prompt-profile denominators and the
five objective-receipt metrics need separate reviewed evidence adapters; this
file format must not be presented as support for those metrics.

## Safe workflow

Before writing a file, the client may read the content-free all-twenty release
map from `GET /v1/metric-contracts/v2/operability-catalog`. This distinguishes a
currently supported evidence path from a task-profile or provider-adapter gap;
it does not disclose session data or authorize a measured value.

1. The authenticated loopback client reads
   `GET /v1/sessions/{session_id}/agent-metric-evidence/contract`. The response
   binds the current sealed run, source-window fingerprint, all contract
   fingerprints, accepted closed enums, size limit, and expiry policy.
2. The agent writes canonical UTF-8 JSON using that exact contract. The body is
   at most 64 KiB, expires within 24 hours, contains no floating-point values,
   and uses sorted keys with no insignificant whitespace or duplicate keys.
3. The client sends the unchanged bytes to
   `POST /v1/sessions/{session_id}/agent-metric-evidence/preview` with media type
   `application/vnd.prompt-enhancer.agent-metric-evidence+json`. Previewing is
   read-only and returns the payload digest and exact source-window binding.
4. After displaying that preview, the client may import the same bytes through
   `POST /v1/sessions/{session_id}/agent-metric-evidence/import`, binding the
   preview digest, an idempotency key, and the literal import confirmation.
   Import creates only an inert proposal; raw bytes and producer claims are not
   persisted as evidence authority.
5. A person reviews the proposal in the same-origin dashboard. Confirming or
   rejecting it is a separate two-step browser action protected by the
   ephemeral browser session and CSRF token. The decision endpoint refuses the
   general API token, and the command requires the exact decision-confirmation
   literal.
6. A new local analysis publishes any effect in a fresh sealed snapshot. The
   previous snapshot is never mutated.

Every response on these routes is private and non-cacheable. All identifiers
are installation-local pseudonyms, and stale run, window, revision, digest, or
contract bindings fail closed.

## Threat boundary

The API-token/browser-session split prevents the same application credential
from both proposing and admitting evidence. It is not proof of physical human
presence against malware that can control the local desktop or browser. A
future commercial remote API must add account entitlements, scoped API clients,
revocation, audit, rate limits, and a reviewed user-presence mechanism; it must
not weaken this local confirmation boundary.
