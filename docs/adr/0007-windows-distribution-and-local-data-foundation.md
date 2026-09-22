# ADR 0007: Windows distribution and local-data foundation

- Status: Accepted for an offline development foundation
- Date: 2026-08-18
- Scope: WP-22 contracts and fail-closed local adapters only

## Context

The source checkout previously discovered the dashboard and accelerator probe by
walking repository parents. That layout is not a packaged application contract.
Windows also cannot be described as private merely because Python requested
POSIX mode bits. Backup, update, diagnostic, and build evidence need explicit
boundaries before a supported installer or release channel can exist.

This decision does not make the repository a supported Windows release. It
creates bounded ports and deterministic evidence that later owner-controlled
packaging work can use.

## Decision

1. Runtime assets are resolved from a fixed package-owned layout. The packaged
   resolver never falls back to a repository parent or temporary extraction.
   Vite emits its ignored production output directly into that layout. A
   missing dashboard disables static hosting; a missing probe produces an
   unknown hardware result.
2. Existing path components receive a tri-state inspection. A symlink, Windows
   reparse point, or non-missing operating-system inspection error is rejected.
   A Windows path is never reported as hardened until a reviewed DACL adapter
   proves it; the current adapter reports `windows_dacl_unavailable`.
3. Application-created paths have stable identifiers plus sensitivity,
   export, erase, and backup classifications. SQLite databases have explicit
   WAL and SHM erase entries. Secrets and SQLite sidecars are excluded from
   portable backup.
4. Public build manifests contain only sorted relative paths, sizes, hashes,
   public tool versions, lockfile hashes, and a revision. Timestamps, absolute
   paths, ambient environment, and host identity are excluded. The manifest is
   unconditionally `distributable: false` in this tranche.
5. Diagnostic bundles accept bounded structured facts, apply the existing
   deterministic local redactor, omit prose or failed values, and return the
   exact local-write bytes plus their hash and preview. There is no destination
   or transport port.
6. Update manifests are bounded, strict, URL-free, and verified in this order:
   size, UTF-8 decoding, schema, signature over the original bytes, then time,
   channel, and version semantics. Only an unregistered development HMAC fake
   exists. No manifest fetcher exists.
7. SQLite snapshotting uses `sqlite3.Connection.backup` and verifies the
   destination with `PRAGMA integrity_check`. Restore approval is pure and
   validates every manifest entry before returning any approved identifiers;
   mutation remains unimplemented.
8. Current loopback and no-egress modules are registered explicitly. The
   reviewed public-model download path is classified as explicit opt-in. The
   bounded Codex child-CLI runner is classified as implemented but uncomposed.
   Signed-update transport remains declared and unimplemented.
9. The offline Windows release stager accepts a versioned public JSON plan and
   copies only its explicit relative file entries after checking each pinned
   size and SHA-256. Its destination is a fresh no-clobber directory and its
   only success output is the existing deterministic content-only manifest,
   still marked `distributable: false`. For a synthetic plan containing only
   relative paths, the assembly command is:

   ```powershell
   uv run --frozen --no-sync python scripts/stage_windows_release.py synthetic-stage-plan.json --source-root .\synthetic-input --destination .\synthetic-output
   ```

   This is assembly evidence, not a runnable package. It neither builds a
   frontend/runtime, downloads dependencies, signs, installs, starts, nor
   publishes anything. Its checks reduce accidental path substitution, but do
   not claim protection against an arbitrary hostile same-user filesystem race.
   The focused synthetic staging/path gate recorded **66 passed, 2 skipped**
   on 2026-09-09 (receipt `cd91d8`); this is not installer or runtime evidence.
10. The desktop dependency recipe runs `uv lock --check` and `uv export` with
    frozen, offline, no-config, and no-download flags. It selects only the
    explicit `desktop` extra while excluding development/default groups and the
    project, then returns normalized exact-version hash-bound requirements for
    later reviewed wheel preparation. It does not download, install, build
    wheels, select Windows wheels from universal markers, or make a runnable
    release. The recipe parser is declared in the dedicated `release` extra;
    a future reviewed operator may invoke it with `uv run --extra release
    --frozen --no-sync python scripts/export_windows_desktop_requirements.py`.

## Privacy and security consequences

- Manifests and diagnostics never include absolute host paths by contract.
- Diagnostic data remains sensitive even after redaction and is local/manual.
- Backups remain sensitive plaintext local artifacts. Encrypted portable backup
  is reported as unsupported; no custom cipher is introduced.
- Backup hashes are useful only with a separately trusted manifest. This tranche
  adds no manifest authentication, and restore compatibility is schema-based;
  it does not compare the recorded application version.
- Analyzer and social databases retain separate path identities and SQLite
  snapshots. The inventory does not create a cross-domain join key.
- Fail-closed component checks reduce path substitution risk but do not replace
  handle-relative Windows filesystem operations or installer signature checks.

## Explicit readiness gaps

The following remain unavailable: MSIX/AppInstaller and MSI output, publisher
identity and signing keys, Authenticode verification, a production update key
or downloader, firewall rules, services, telemetry, remote listeners, a Windows
DACL implementation, DPAPI custody, encrypted portable backup, restore
mutation, automatic diagnostic upload, SBOM/license approval, and a verified
two-build release pipeline. The dashboard remains absent until the committed
frontend build is run; notices and the SBOM remain absent until a real staging
process supplies them.

The explicit-file stager is not locked-runtime preparation: producing a
runnable Windows release still needs a reviewed runtime/frontend build, pinned
runtime inventory, MSIX/AppInstaller or MSI packaging, signing, verification,
and owner-controlled publication acceptance.

The development model cache and free-disk probe still use the repository-local
`runtime/model-eval` containment root. Selecting and hardening the installed,
non-roaming model-cache root remains a later composition task.

No code in this decision changes `SECURITY.md` or claims production release
readiness.
