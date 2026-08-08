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
