# ADR 0011: Owner-authorized on-demand session reader

- Status: Accepted, off by default; owner-authorized on 2026-08-19
- Date: 2026-08-19
- Contract version: `session-reader.v1`
- Setting: `PROMPT_ENHANCER_SESSION_READER=enabled`
- Supersedes: ADR 0010's "no reading of `~/.claude`" for exactly one purpose,
  under the owner's explicit authorization

## Decision

Let the person who owns the sessions **read them inside the local dashboard,
on demand**, so that when they rate a session for metric calibration they can
see what actually happened rather than judge a fictional stand-in. Both
providers are read through the least-privileged surface that yields the
conversation:

| Provider | Surface | Notes |
|---|---|---|
| Codex | the documented app-server text read (`thread/read`), same client, snapshot scope, and thread selection as the P1 text-analysis source | unredacted, because the owner is reading their own conversation |
| Claude Code | the owner's own transcript files under `<claude home>/projects/<encoded cwd>/<session id>.jsonl` | version-gated; only `user` and `assistant` lines with a `message` object are read; a non-empty file that yields no recognised line fails closed as `format_unrecognized` |

## Boundaries that hold regardless of provider

1. **Off unless enabled.** The reader mounts only when
   `PROMPT_ENHANCER_SESSION_READER=enabled`; the public
   `raw_transcripts` capability is `false` otherwise and `true` only then -
   it is a boolean now, never a silent promise.
2. **Catalog, consent, one session.** A read happens only for a session
   already in the local catalog, only for a provider whose local-history
   consent is active, and only for the one session the dashboard asked for.
3. **Nothing persisted.** The transcript is built, sent over loopback with
   `no-store`, and dropped. The store contains no line of it; a test dumps
   every table and asserts so.
4. **Bounded.** At most 2 000 turns, 20 000 characters per turn, 2 000 per
   tool call or result, 4 000 000 in total, 64 MiB per file, 200 000 lines;
   the response says when it truncated.
5. **No raw identifier is stored.** The Claude reader recovers the raw session
   identifier from the transcript filename at read time by re-deriving the
   catalog pseudonym through the same HMAC chain the hook receiver and the
   ingestion service use, opens only the file that matches, and drops it.
6. **The coding agent that maintains this repository never reads a session.**
   The application does, for its owner, on the owner's machine. Test fixtures
   are fictional.

## Transcript adapter: the default Claude Code source (added 2026-08-19)

At the owner's direction the same read surface is also the **primary Claude
Code source**: a `ProviderAdapter` over the transcript files indexes every
session - history included - with the provider's own timestamps, per-response
token usage from `message.usage`, tool calls with their results and
`is_error`, compaction markers, the project from `cwd`, and a title from the
first prompt. Identity uses the exact pseudonym chain of the hook receiver, so
a session seen by both channels is one catalog row.

One source of record per session: where a transcript exists, the hook adapter
does not list that session and the transcript supplies every event (hook-space
sequences from 0, usage in a separate sequence space); where none exists, hooks
and the OTLP receiver remain the source exactly as before. A session that was
indexed from hooks before its transcript was read is superseded once, by a
guarded, session-scoped deletion of its receiver-clock events - only when the
stored session still carries the hook schema - and never touches analysis
runs, tasks, or any other session. Re-indexing is idempotent.

The adapter is read-only and bounded (20 000 files, 64 MiB and 200 000 lines
per file, 60 head lines for listing); it scans filenames and heads to list and
reads one file fully only when that session is ingested. The status surface
reports `reads_transcripts = true` when it is wired. Under test the Claude home
is always an isolated temporary directory, so no real session is ever scanned.

## What this does not accept

Reading any provider file that is not a session transcript; reading a session
that is not in the local catalog; any network transmission; any persistence -
the owner has separately authorized an encrypted local copy (Tier 3 vault),
which is a distinct decision with its own security review and is not part of
this ADR; and any change to what the metric pipeline reads.
