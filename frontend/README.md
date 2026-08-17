# Prompt Enhancer dashboard

This directory contains the browser-first React dashboard for the synthetic
task-discovery milestone. It follows the dependency direction from ADR 0001:

```text
app -> features -> entities -> shared
```

The default development composition uses only fictional, content-free fixture
data. The HTTP transport accepts relative `/v1/...` paths, sends credentials only
to the same origin, and has no API-token or browser-storage facility. In a
production build, the integrated loopback server issues an ephemeral HttpOnly
cookie and an in-memory CSRF token. Page load and session bootstrap never access
a provider; indexing, selected summary-label enrichment, and analysis remain
separate explicit actions. Manual display labels modify only Prompt Enhancer's
local catalog and never rename provider tasks. A desktop host can later implement
the narrow platform adapter without changing features.

## Development

```console
npm install
npm run test
npm run build
npx playwright install chromium
npm run test:e2e
```

The dev and preview servers bind to `127.0.0.1`. No analytics, CDN, remote font,
image, or model request is included.

The packaged local server should send this production Content Security Policy:

```text
default-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self';
object-src 'none'; connect-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'
```

It is intentionally a server header rather than a static meta element because
the local server owns the browser security boundary. The production build emits
its stylesheet as a local asset; the current coverage visualization uses one
bounded inline width style, which is why `style-src` permits inline styles.

## API contract

`src/shared/api/generated/openapi.ts` is a checked-in snapshot of the content-free
WP-03 DTOs. After exporting the backend schema to `../docs/openapi.json`, run
`npm run generate:api` and review the diff. Runtime API documentation remains
disabled; generation is a build-time operation.

## Team control-plane port (frontend only)

`src/shared/api/teamControlPlane.ts` is a typed frontend port for a future
canonical team control plane. No backend implements it. Two honest adapters
exist:

- `createSyntheticTeamControlPlanePort()` serves a fictional, content-free
  cohort in the synthetic development preview (every payload is stamped
  `origin: "synthetic_fixture"`);
- `createUnavailableTeamControlPlanePort()` reports team, organization, sync,
  and billing as absent in the local loopback runtime and serves no scope.

`createTeamControlPlanePortForRuntime(mode)` binds each runtime data mode to
its adapter; a remote adapter must not be added until one exists with an
approval-bound transport. The port publishes aggregates only: cohort size,
missingness, comparability, freshness, and uncertainty per metric, with
measured typed rows and experimental model ranges kept as separate entries.
Individual member rows exist only behind an explicit visibility grant with
audit facts, are ordered by pseudonymous identifier, and never carry a total,
rank, or score. The `/team` route (Me · Team · Organization), the `/tasks/flow`
board and timeline, and the compact "Team context" drawer in the floating
overlay consume the port; per-metric two-sentence explainers reuse the
metric-help-v2 registry and decision guidance in both full and compact modes.
