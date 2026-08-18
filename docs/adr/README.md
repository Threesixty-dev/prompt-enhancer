# Architecture decision records

Architecture decision records (ADRs) capture consequential technical decisions,
their evidence, their trade-offs, and the conditions that should cause them to be
revisited. An accepted ADR describes the current default; it is not permission to
weaken the repository's privacy or safety rules.

| ADR | Status | Decision |
|---|---|---|
| [0001](0001-modular-monolith-hexagonal-metric-graph.md) | Accepted | Modular monolith with hexagonal boundaries and an explicit metric graph |
| [0002](0002-codex-app-server-read-boundary.md) | Accepted | Bounded Codex local-history access with selector-gated detail reads |
| [0003](0003-offline-provider-schema-compatibility-lifecycle.md) | Accepted | Offline, reviewed provider-schema compatibility releases without runtime adapter downloads |
| [0004](0004-full-available-session-scope-boundary.md) | Accepted seam | Full available-session coverage is an explicit completeness claim; durable incremental publication remains follow-up work |
| [0005](0005-team-control-plane-boundary.md) | Accepted foundation | Content-free team control plane with default-deny authorization and a replaceable storage port; no deployment, identity provider, or billing is accepted |
| [0006](0006-private-social-and-direct-file-foundation.md) | Accepted development foundation | Invite-only social metadata and direct-only owner-hosted files; no production identity, cryptography, signaling, relay or routes are accepted |

Changes that reverse an accepted decision should add a superseding ADR rather
than silently rewriting the original rationale.
