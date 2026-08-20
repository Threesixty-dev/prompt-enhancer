# ADR 0017: Remote annotation providers - models the person already has access to annotate sessions

- Status: accepted direction (2026-08-20); Stage 1 scoped, not yet implemented
- Owner direction: besides rating sessions manually, the person can point the
  app at models they already have access to (Claude Opus / Fable, GPT-class
  models, anything OpenAI-compatible) and have them annotate sessions
  automatically - after an explicit allowance - so annotations, sessions and
  projects together form a useful calibration dataset.

## Context

The judgment store is already model-neutral: `model_judgments` (migration 50)
keys every annotation by `model_alias`, `model_identity` and `prompt_version`,
and the Calibration page compares each model's labels against the person's
blind ratings (agreement, Cohen's κ). Today the only annotators are local
llama.cpp models. The repository's standing rules: no transcript text leaves
the machine without explicit consent, redaction and a destination preview;
model judgments stay visibly separate from measured evidence; no rankings.

## Decision

1. **Stage 1 - remote judges, local dataset.** A *remote annotation provider*
   is an OpenAI-compatible chat endpoint plus the person's own credential
   (BYOK): base URL, model name, key. Keys are stored only in the app home's
   private inventory (never in the database, never logged, never in exports).
   The judge lane gains a provider-backed chat callable; its judgments land in
   the same `model_judgments` table with `model_alias = remote:<name>` and the
   exact served model recorded as `model_identity` - one dataset, human and
   model annotations side by side, per model, never merged into metrics.
2. **The allowance.** Remote annotation is off until the person grants a
   *remote annotation allowance* per provider: a consent record naming the
   provider, the destination host, the redactor version, and the window bound.
   Granting shows a destination preview (one representative redacted window
   rendered exactly as it would be sent). The allowance is standing for the
   sweep it starts but revocable at any time; each sweep logs, content-free,
   how many windows were sent and to which host. Only the redacted analysis
   window (the same one P1 and the local judge read) is ever sent - never raw
   transcripts, paths, names, or metrics.
3. **Dataset.** "Central" means the app's own store on this machine: sessions,
   projects, human ratings and per-model judgments are already joined by
   pseudonymous ids there, and the Calibration export (labels + pseudonyms
   only) is the dataset artifact. Aggregation across people onto a shared
   server stays gated on the identity and sharing decisions
   (docs/pending-owner-decisions.md, Tracks 1 and 4); nothing in Stage 1
   creates a remote store.
4. **Boundaries.** The provider client lives in one module registered in the
   egress registry as `APPROVED_PROVIDER_REQUEST` and in the hardening
   allowlist; it refuses to run while the allowance is absent or revoked;
   failures are closed codes. Agreement math treats every remote model like
   any other judge; the activation gate for model-backed metrics is unchanged.

## Consequences

- The person can annotate the whole history with any model they can call -
  and see, per model, how well it matches their own blind ratings before
  trusting it with anything.
- Sending redacted windows to a provider places them under that provider's
  terms; the allowance text says so plainly, which is why it is per provider
  and revocable.
- Stage 1 needs: the provider registry + key inventory entry, the allowance
  consent + preview UI, the remote chat adapter, sweep wiring, and tests that
  prove nothing leaves without an allowance. Estimated one focused session.
