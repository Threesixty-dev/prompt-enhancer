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

Changes that reverse an accepted decision should add a superseding ADR rather
than silently rewriting the original rationale.
