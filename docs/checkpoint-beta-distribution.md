# Free local beta distribution — implementation reference

Updated for B00 on 2026-09-17. The [product-readiness matrix](product-readiness-matrix-2026-09-12.md)
is the **only current release ledger and prioritized queue**. This document
describes existing distribution mechanisms; it does not schedule another task.

## Agreed destination

Private source; a separate public binary-only release repository; invited testers
initially; Windows 11 x64; free local use without a Prompt Enhancer account.
Production accounts/billing/teams are deferred. Source visibility was verified
private during B00; the release repository is not yet identified/verified.
No repository visibility, release, signing or trust-store change was made.

Keep the MSIX direction. The later B08 checkpoint must prove a bounded,
pinned-toolchain Nuitka compilation path, omit first-party Python/TypeScript
source and source maps, and preserve dependency obligations. JavaScript remains
inspectable. No stronger anti-copying guarantee is made.

## Existing mechanisms, with limits

- Explicit-file, hash-bound staging:
  `scripts/stage_windows_release.py` and
  `infrastructure/build_staging.py`.
- Locked desktop export, runtime/wheel preparation and application inputs:
  `scripts/export_windows_desktop_requirements.py`,
  `scripts/prepare_windows_python_runtime.py`,
  `scripts/prepare_windows_dependencies.py`,
  `scripts/stage_windows_wheels.py`,
  `scripts/prepare_application_wheel.py`.
- MSIX candidate assembly, SDK packing/unpacking and optional ZIP timestamp
  normalization: `scripts/prepare_msix_candidate.py`,
  `scripts/pack_msix_candidate.py`, `scripts/verify_msix_sdk_unpack.py`,
  `scripts/canonicalize_unsigned_msix.py`.
- Read-only signature/publisher/version preflight:
  `scripts/verify_msix_package.py`,
  `infrastructure/updates/msix_preflight.py`.
- Private staging/review/recovery and pure handoff evaluation exist.
  `application/updates/handoff_plan.py` still reports executor unavailable;
  `application/updates/package_preflight.py` retains `can_install=False`.
  These do not install or relaunch an application.

The previous claim that no runtime recipe/MSIX builder existed is superseded.
Historical candidate-review4 outputs normalized to the same unsigned payload:
SHA-256 `bdf694073425cebe14595ebdd48d0fa4cea6397a5f969ec7176969a1ead49f73`,
34,014,174 bytes, with SDK unpack/payload verification.
This is dirty-snapshot timestamp-normalized repeatability, not a clean private
commit build, compilation, native byte-for-byte reproducibility, signing,
native GUI, installation, update or uninstall acceptance.

## Remaining required proof

B08 must close first-party compilation and dependency notices, including the
interrupted frontend notice inventory and opaque PDF worker. If the PDF worker
cannot be accounted for, remove the viewer and worker from the beta payload;
hiding its control is insufficient.

B09 must add a native update executor behind exact staged-release review, fresh
native consent, local authentication/CSRF and a durable operation journal.
Prove signed N-to-N+1 installation, data retention, interrupted handoff/relaunch,
safe package/data recovery, schema compatibility and uninstall/reinstall on the
declared clean standard-user Windows environment. Never reboot, silently install
a root certificate, or delete retained data.

B11 binds the full gate to the exact compiled/signed candidate and requires owner
review before publishing approved binaries/metadata only. No push to a source
branch automatically updates an installed application.

## Owner-controlled inputs

Still required: binary-release repository, package identity/publisher, public
certificate fingerprint, update-manifest verification key, owner-controlled
signing location, exact Windows/NVIDIA acceptance environments, approved model
artifacts/resource limits, support contact and beta terms. Private keys, tokens,
credentials and personal configuration stay outside chat and version control.

## Current checkpoint boundary

B00 only. The September 17 source-custody repairs restored the clean frontend
build and removed the backend collection dependency on quarantined test output.
The explicit offline stage-recipe wrapper is tooling, not a compiled or signed
package. Remaining baseline failures and coherent-commit requirements are in the
authoritative ledger. Do not restore generated artifacts, claim native release
acceptance, or start B01 automatically.
