# Proposal: versioned experiment bench

Status: proposed for owner review, 2026-10-12. This does not supersede accepted
ADRs or certify workflow beta gates. Central ADR/atlas integration is coordinated
by the supervisor and core workstream.

The bench stores experiment revisions, run snapshots, per-subject/unit attempts,
complete results and lifecycle events in its own private SQLite database. It does
not store benchmark prompts in the application's metrics-only prompt-check history.
The subject is the input prompt, with explicitly supplied optional context.

An experiment revision has a stable identity, a monotonically increasing desired
generation, a code-owned enhancer version, sibling strategy units, typed base
parameters, a versioned objective, per-strategy steering, and separate inherited
consumer/evaluation bindings. JSON is the
initial GitOps definition format. A publication adds the immutable image digest;
both definition and digest become immutable for that stable ID and revision.
Changing only a definition can reuse the exact same image.

Import and automatic queue insertion share a SQLite transaction. Unique keys
enforce one automatic run per revision and stable UI request idempotency. Late
delivery cannot queue an older eligible generation. New eligible generations
supersede queued automatic work, while already-running work records its actual
outcome. UI runs have their own idempotency key and frozen override snapshot.

One dedicated worker admits one run and one unit at a time. Its replaceable runtime
adapter pulls an allowlisted immutable image, verifies its digest, creates an
owned container, invokes the enhancer's own HTTP interface, persists each result,
deletes ephemeral core retention, and confirms container removal. The container
name is durable before creation so a crash during Docker create can be reconciled.
The initial implementation intentionally has no general inference/GPU scheduler.
An optional operator-owned model profile mounts one existing reviewed local volume
read-only at the core's isolated cache path. It validates CPU/memory limits and
supports CPU or one explicitly provisioned CUDA device. These choices never come
from experiment/UI input. Default and model-enabled images have separate tags,
build-input fingerprints and labels, then bind to immutable publication digests.

The core shares the dedicated bench worker's network namespace and binds to
`127.0.0.1:8787`. The relay binds `127.0.0.1:8000` there and forwards the
authenticated Agent Server API over a private Unix socket. The STATIC consumer
has `network_mode: none`, with its own loopback Agent Server and a loopback model
listener bridged through a second Unix socket to the relay's fixed HTTPS gateway.
It hosts neither the enhancer nor a testing harness.
The core receives a per-container API token. The worker needs Docker authority;
the browser-facing API, relay and static consumer receive no Docker socket. Sharing a
namespace does not share files or credentials. The port arrangement requires
one bench worker instance per namespace; scale-out needs a reviewed port/namespace
allocation policy before admission capacity changes.

Queued work survives restart. Active work becomes interrupted and is never
automatically replayed. Cleanup blocks new work until owned containers are gone.
Uncertain consumer delivery additionally holds admission until an operator has
verified remote termination and records a content-free evidence reference.
Reconciliation does not rewrite an interrupted run as success; an explicit retry
gets fresh run, correlation and attempt IDs.

Execution status and assertions remain independent. All core provenance,
before/after evaluations, unknown states, deltas and timings are preserved.
Request/response correlation and effective settings are checked before a result
is accepted. The core supplies the measured baseline, its profile and the frozen
objective/steering in a versioned generation context. A consumer returns only a
candidate; evaluator evidence stays under core ownership. Uncertain operation
IDs remain durable even if later result deletion fails. Container cleanup alone
cannot release that remote-operation hold.
The server never logs request bodies or upstream diagnostic text.
API access uses separate operator/import tokens and same-origin browser checks.
Content is rendered as text, without HTML interpretation or local token storage.

Affected existing boundaries: W02 immutable/recovery semantics, W03 typed
adapters, W05 results views, W07 packaged qualification, WP03 run binding,
WP05 interruption, WP07 separate private storage, WP08 headless parity. A bench
smoke alone does not close those broader product gates.

Alternatives considered: using Agent conversation history would conflate chat
retention and benchmark ownership; a separate harness would duplicate the enhancer
engine; automatic turn replay would lose side-effect uncertainty. A distributed
queue is deferred until concurrency is needed and can preserve this admission port.
