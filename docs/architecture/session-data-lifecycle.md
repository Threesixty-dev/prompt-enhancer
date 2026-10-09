# Session data: what is stored, temporary or missing

Source audit: 2026-10-08, preserved development checkout at `acdf0e5` plus pending
changes. This describes code, not the running installation's settings or a
complete data inventory. No personal sessions, database or private configuration
were opened. Source may differ from published main; see the atlas baseline.

## Where data lives

On Windows the configured application root is `PROMPT_ENHANCER_HOME` when set,
otherwise `%LOCALAPPDATA%/PromptEnhancer`; a legacy home-directory fallback exists
when local application data is unavailable. These are code defaults, not an
inspection of anyone's actual installation. See `src/prompt_enhancer/config.py`.

| Data lane | Location / lifetime | Current contents and limits |
| --- | --- | --- |
| Imported analytics | `<app home>/metrics.sqlite3` | Pseudonymous sessions/events, usage, metrics, derived labels, versions, coverage and analysis fingerprints. Sensitive project/session display names are an explicit exception to content-free identifiers. Not a full prompt archive. |
| Imported original conversation | Provider-owned history | Codex through app-server; Claude through a version-gated read-only transcript adapter. Provider history must still exist, be supported and fit bounds when re-read. |
| Local transcript viewer | In-memory request and loopback response | Bounded owner-facing text; catalog/consent/auth checks; response is `no-store, private`, transcript declares `persisted=False`. This reader does not save the full conversation. |
| Local text/model analysis | Ephemeral redacted input window | Grant explicitly forbids input persistence. Results, fingerprints and provenance can persist without the input text. A hash cannot reconstruct the original prompt. |
| Authored Agent chats | `<app home>/agent-catalog.sqlite3` | Separate private project/chat catalog. With local-history retention, stores user/assistant text, runtime-exposed reasoning, bounded event receipts and a text search index. Not the imported analytics DB. |
| Agent attachments | Agent catalog database BLOBs | Bytes are temporarily staged even for metadata-only chats; sent local-history attachments persist, metadata-only staged rows are removed after sending. Unsent staging has bounded expiry. |
| Agent artifacts | Workspace files plus catalog metadata | Actual file bytes remain in the workspace; catalog keeps path/hash/size/provenance. A catalog entry is not an immutable copy of file contents. |
| Team review archive | Not delivered | Existing team foundation is content-free. Shared prompts need TR01–TR08 and the proposed retention architecture. |

## Imported analytics: available fields

The normalized storage DTOs in `domain.py`, minimized in `ingestion.py` and saved
through `database.py`, carry:

- Session/provider identity pseudonyms, adapter/schema versions, start/end times,
  terminal state and completeness.
- Event kind, sequence, time basis, optional duration, optional success and tool
  category. The enum includes lifecycle, plans, decisions, verification,
  approvals, usage, compaction, subagents, forks and artifacts; enum presence does
  not prove every provider supplies every event.
- Optional input/output/cache/cache-creation/reasoning/total tokens, model and
  counter scope. Missing remains unknown. Usage is usually request/turn/session
  scoped, not attributable to every individual tool invocation.
- Metric values/closed labels, evidence coverage and provenance. Analysis
  snapshots and model judgments keep input fingerprints and version identity,
  not an automatic stored copy of the input conversation.

The imported `SafeEvent` has no raw prompt, command, tool-argument or tool-output
field. `DataTier.RAW_VAULT` is a named tier, not an implemented archive; current
settings enforce metadata storage for this import path.

**Sensitive-label exception:** session names can derive from provider titles or
the first prompt line. Claude hook title extraction defaults on, bounded to a
short line. `display_labels.py` rejects paths/control characters and limits
length; it is not a general secret/PII redactor. Labels must remain private,
excluded from content-free exports unless separately admitted, and covered by
future retention/sharing review. Do not claim the database contains no
prompt-derived text or that pseudonyms make its records anonymous.

## Tool-use coverage by source

| Source | Persisted analytics | Detail and limitations |
| --- | --- | --- |
| Codex app-server | Typed tool events for command/file/MCP/search/image operations; optional status/duration/usage, plan/compaction/subagent signals | Current raw transcript reader maps user/assistant/plan text, not tool call/result turns. Separate ephemeral local-review descriptors (not ordinary model text input) can contain bounded redacted tool invocation/effect. Time can fall back to turn/session basis and is labeled. |
| Claude transcript adapter | Tool start/end pairing, category, provider timestamps, result error flag, elapsed duration and response usage/model | Local reader can show bounded tool input/result previews. Full payloads are not stored by metadata ingestion. Missing pairs/status/usage remain unknown. |
| Claude hooks | Pre/PostToolUse categories, pseudonymous pairing, receiver-clock timing | Does not retain tool arguments/output/name. PostToolUse maps to successful completion; unmatched starts remain unknown. Hooks alone do not supply token counts. |
| Claude OTLP | Allowlisted exported request usage/cache/model/duration/cost counters | Requires configured export/consent; no arbitrary prompt or tool payload fields. Not evidence of full conversation or every tool event. |

A tool execution status is not proof that the overall user task succeeded.
Unsupported provider versions, missing tool results, truncation and partial
history must remain visible rather than filled in from assistant claims.

## Authored Agent history is different

The backend `AgentSettings` default is metadata-only, but the current Agent UI
initializes **Save locally** as selected and submits local-history retention.
It also offers Metadata only. Report the selected policy, not a blanket default.
With local history, the message text is saved directly; do not call this store a
redacted analytics archive. Settings/instructions and a full-text index are also
sensitive. Stored reasoning is only what the runtime provides.

`LocalAgentService._stored_event` excludes streaming deltas and approval-required/
resolved events, does not allow raw tool arguments, and strips raw tool-result
text. Bounded tool identities/status and execution/write/MCP receipts can remain.
Current journal bounds are 4,000 events/chat, 250,000 serialized characters/event,
and 120,000 characters per retained text/reasoning field. It is not an unlimited
lossless session recorder. Drafts remain in window memory in the reviewed path.

Closing a live chat does not delete its retained history. Catalog deletion removes
associated journal/search/attachment metadata rows, not workspace artifact files.
This is logical database deletion, not proof of secure erasure from WAL/backups.
Agent JSON export contains bounded retained events, not attachment/file bytes or
raw tool output. Export for the local owner is not a manager sharing grant.

## Gaps for complete retrospective analysis

- No durable archive of all imported prompts/tool payloads; re-analysis relies
  on provider history still being available and within limits.
- Viewer limit: 2,000 turns, 20,000 characters/turn, 2,000/tool preview and
  4,000,000 total. Text-analysis limit: 500 messages / 500,000 characters.
  Full-available selection still respects bounds and must disclose incompleteness.
- The reader setting currently defaults on, while older reader prose says off;
  catalog/consent checks still apply. Resolve this documentation drift separately.
- Revoking import consent is not deletion of already stored analytics. No general
  automatic age-based purge was found in the inspected session/history paths.
- SQLite persistence is not, by itself, evidence of encryption at rest, secure
  deletion or backup expiry. These require explicit design and acceptance.

For new retention and team review use [TR01–TR08](../work-packages/team-prompt-review.md)
and proposed [ADR 0022](../adr/0022-consented-session-retention-and-team-review.md).
Capturing enough evidence for analysis, retaining raw content and sharing it are
three separate decisions; none implies unlimited or automatic collection.

## Source entry points

All short paths below are under `src/prompt_enhancer/` in the observed checkout:
`config.py`, `domain.py`, `ingestion.py`, `database.py`, `display_labels.py`,
`application/analysis/session_reader.py`, `application/analysis/text_source.py`,
`application/analysis/text_contracts.py`, `interfaces/http/session_reader_routes.py`,
`infrastructure/providers/codex_app_server/` and `infrastructure/providers/claude_code_hooks/`.
Authored history: `application/local_agent.py`, `application/agent_catalog.py`,
`application/agent_attachments.py`, `application/agent_artifacts.py`,
`infrastructure/sqlite/agent_catalog.py`, `infrastructure/sqlite/agent_attachments.py`,
and `frontend/src/features/agent/AgentPage.tsx` from repository root.
