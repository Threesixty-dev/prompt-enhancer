# ADR 0016: Local agent workspace - a local model working in one folder with approvals

- Status: accepted (2026-08-20), streaming and manual-editor slices added
- Owner direction: a separate window where the chosen local model works the
  way Codex or Claude Code work - with tools (files, terminal, web), usable
  through the endpoint or inside the app's chat, to write code and documents;
  the elements a code editor needs should live inside this application, built
  on a sound architecture.

## Context

The app already runs a strong local model on the owner's GPU (ADR 0013) and
talks to it through an OpenAI-compatible loopback endpoint; llama.cpp's chat
template engine emits proper `tool_calls` for Qwen3 when started with
`--jinja`. What was missing was a place where that model can *act*: inspect a
folder, change files, run tests, and report - under the same rule as the rest
of the app: nothing happens to the person's machine without their say-so.

## Decision

1. **One folder, one session.** `application/local_agent.py` holds sessions
   in memory. A session is bound to an absolute folder the person chose (not a
   drive root; optionally restricted to allowed roots). Production composition
   refuses any workspace that overlaps the app home, provider homes, local
   model store, or common credential directories. Every path the model names
   must stay inside the workspace; symlink/reparse components and hard-linked
   write targets fail closed. The session records its own event stream (user, assistant,
   tool_call, tool_result, approval_required/resolved, status, error, done),
   bounded and cursor-paged, so any UI can follow it.
2. **Tools with two trust levels.** `read_file`, `list_dir`, `search_text`
   run immediately (bounded output, binaries refused, noisy folders skipped).
   `write_file` (a unified diff is produced first), `run_command` (PowerShell
   on Windows, bash elsewhere, workspace as cwd, timeout, output capped) and
   `fetch_url` (off unless enabled) **pause the run** with an
   `approval_required` event carrying the exact arguments and the diff; the
   person approves or denies that one call through an owned native confirmation
   bridge (the API token and browser cookie are not human-decision credentials);
   standard `serve` and attached-window modes keep these controls unavailable; a denial is
   reported to the model as a tool result so it adapts instead of retrying;
   stop cancels any pending approval. A write preview is bound to the exact
   file hash, file identity and parent identity; a file changed while approval
   is pending is never overwritten.
3. **The loop.** Per user message the service runs at most N model steps:
   the model gets the conversation plus the tool schemas for the permissions
   the session allows; tool calls are executed in order and their results
   appended as tool messages; a plain reply ends the turn. Thinking is off for
   speed; the model's own chat template is used (`--jinja`, on by default in
   the runtime activation together with flash attention and an 8-bit KV
   cache, with a plain retry if the runtime refuses them).
   The agent consumes the runtime's OpenAI-compatible SSE reply directly.
   Bounded `assistant_delta` events carry content (and, only when the person
   enabled thinking, separately labelled reasoning) while tool-call fragments
   are reassembled and validated before the approval loop sees them. A stream
   must end with `[DONE]` or a terminal `finish_reason`; stopped, incomplete,
   malformed and oversized replies get an explicit terminal state and never
   enter model history as completed assistant messages.
4. **Surfaces.** `/v1/agent/*` (sessions, messages, events, private SSE event
   stream, approvals, stop, and session-bound workspace tree/file/preview/apply)
   under the app token; the *Agent* page (folder, model, permissions,
   sessions list, transcript with tool cards, approval dialog with diff,
   composer, stop) and a chrome-less popup `/agent/window/{id}`. A dedicated
   Windows `prompt-enhancer-agent` launcher opens `/agent`, owns the loopback
   server and native confirmation manager together, and refuses to attach to
   an already-running listener. Its explicit Browse action uses an
   exact-origin, exact-`/agent` native folder dialog; cancel/unavailable results
   are content-free and the chosen path remains subject to the service's full
   workspace validation. The same page
   now includes a typed file tree and dependency-free UTF-8 text editor beside
   the chat. Manual edits use a server-created diff plus a short-lived,
   single-use, content-free capability and require owned-window native confirmation to
   apply; the model's `allow_writes` switch does not restrict the person's own
   manual edit.
5. **Boundaries.** Nothing is persisted beyond the server's memory (no
   transcript of the agent's work is stored); the agent module itself opens
   no network connection - web fetch is a pluggable callable that is absent
   unless the app composes one, and even then every fetch needs approval;
   the runtime stays on loopback.

## Consequences

- Verified on the owner's machine: the 27B unrestricted model listed the
  workspace, read two files, proposed a diff (approved), added a test
  (approved), ran `pytest` (approved, 3 passed) and summarised - about 17 s
  end to end.
- The first editor slice intentionally opens only existing strict UTF-8 text
  files, preserves LF/CRLF style, caps files and diffs, and does not create,
  rename, move or delete files. Rich syntax editing, multi-file change sets,
  persistent agent transcripts (content tier), shell sessions that survive
  between calls, and web search remain future slices.
- The agent is only as good as the model and the prompts; the app keeps the
  person in the loop at every change, which is the property that matters.
