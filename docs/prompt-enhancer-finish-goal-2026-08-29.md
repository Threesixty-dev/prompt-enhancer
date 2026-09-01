# Prompt Enhancer finish goal

Status: active implementation program; Sweep-01b and Sweep-01c are automated complete, Acceptance-01 owner evidence remains queued, Release-01a.1 is automated complete, and Release-01a.2 is next
Established: 2026-08-29
Expanded and reconciled: 2026-08-31
Scope owner: local user

## Product outcome

Finish Prompt Enhancer as a local-first, privacy-preserving AI workbench that
combines:

1. a Codex/Claude-style project and chat experience;
2. reliable local Hugging Face model download, loading, switching and cleanup;
3. a reviewed coding-agent workspace for reading, creating, editing, moving,
   comparing and viewing files and generated artifacts;
4. safe external orchestration through a direct loopback Agent API and MCP;
5. a searchable MCP Store with trustworthy source metadata, icons, review,
   install/update/uninstall, project-scoped tool permissions and observable tool
   execution;
6. a coherent, responsive and accessible UI across the whole application.

The product is not finished because a page renders or a narrow unit test passes.
Every advertised control must work through the real local stack, survive the
appropriate restart boundary, report failures truthfully, and have automated
and owner-visible acceptance evidence.

The feature-level release obligations are enumerated in the
[owner feature acceptance register](prompt-enhancer-owner-feature-register-2026-08-31.md).
The two documents form one goal: this document controls sequencing and safety;
the register prevents any requested capability from disappearing inside a broad
milestone label.

## Goal hierarchy and completion rule

This program has four nested levels. They must never be confused:

1. **Product goal:** the complete local AI workbench described in this document.
2. **Milestone:** one coherent product area such as Agent, Runtime, Workspace,
   Artifacts, Orchestration, MCP Store, application sweep or release hardening.
3. **Checkpoint:** one bounded, independently testable user outcome inside a
   milestone. Exactly one implementation checkpoint is active at a time.
4. **Owner acceptance:** the short real-machine review that cannot be replaced
   honestly by synthetic automation.

`Automated implementation complete` therefore does not mean `released`. A
milestone is release-complete only when its current automated evidence, required
owner evidence and integration evidence are all green. An old handoff is useful
history, but cannot hide a new regression.

Status terms have exact meanings:

- **Pending:** required production behavior is not implemented.
- **Implementation active:** the current bounded code slice.
- **Automated implementation complete:** current synthetic, integration and
  browser gates pass; listed owner evidence may remain.
- **Owner review pending:** automation is green, but a real-machine or
  subjective check is still explicitly open.
- **Locked:** the UI and backend deliberately refuse an action until a later
  authority, safety or compatibility checkpoint exists.
- **Release complete:** no required acceptance debt, workaround or falsely
  advertised control remains.

## North-star release journey

The final representative walkthrough is one connected journey. Passing its
parts on different pages or with different hidden setup does not pass release:

1. Launch the packaged Windows application once. Exactly one loopback listener
   appears, no terminal window flashes, and no model or MCP process starts by
   surprise.
2. Create or reopen a durable Agent project, choose its workspace, create a
   chat, switch chats and restart the application without losing retained state.
3. Discover or import an exact Hugging Face model revision, review provenance
   and capabilities, choose CPU, GPU or supported split placement, load it and
   receive an honest readiness result.
4. Chat with text and, only where capability evidence permits, image, audio or
   document input. Streaming, Stop, retry, edit/regenerate, Markdown/code,
   context usage and recovery behave deterministically.
5. Observe concise model-provided reasoning summaries, plans, progress and tool
   activity without exposing or pretending to expose hidden chain of thought.
6. Let the Agent inspect the admitted workspace, propose a multi-file change,
   review the exact diff, approve or deny it, run one reviewed command and
   verify the result objectively.
7. Open a generated artifact from its producing turn, inspect it in the safe
   viewer, compare or export the intended version and return to the same chat.
8. Search the MCP Store, inspect a source-provenanced tile and detail view,
   install an exact compatible server, select exact project tools, approve one
   consequential call, then update, roll back or uninstall it cleanly.
9. Create a project-bound Codex-, Claude- or provider-neutral controller
   connection, observe its ownership, run and stop a scoped turn, revoke it and
   prove that another project or controller is unaffected.
10. Rename, search, pin, archive, restore, fork and export retained work; delete
    only after an explicit consequence preview.
11. Switch to another model and prove the previous owned runtime released its
    processes and accelerator memory before the replacement becomes ready.
12. Reload and then shut down. Durable state reconciles, interrupted work is
    truthful, and no listener, model, command or MCP child remains orphaned.

Any failure in this journey reopens the owning checkpoint. The release is not
accepted by bypassing the failing control or performing an undocumented manual
setup.

## Feature closure scorecard

Every requested capability belongs to one scorecard row and must close all four
columns: behavior, persistence/recovery, interface and independent evidence.

| Area | Required owner-visible capability | Mandatory failure/recovery coverage | Release evidence |
| --- | --- | --- | --- |
| Agent projects and chats | Durable project rail and searchable chats with create, switch, rename, pin, archive, restore, move, fork, export and explicit delete | restart, stale selection, concurrent mutation, duplicate request and interrupted stream | backend state-machine tests, strict UI contracts and real two-width browser journey |
| Conversation experience | Streaming Markdown/code, attachments, Stop, edit/retry/regenerate, safe reasoning summaries, progress, tool cards and truthful context | late/out-of-order events, reconnect, Stop race, unsupported input and failed-send recovery | event-order tests, accessibility states and owner conversation review |
| Local models | Exact revision discovery/download, readiness, parameters, CPU/GPU/supported split placement, switch and unload | disk refusal, cancellation, crash, OOM, stale health, incompatible modality and cleanup uncertainty | synthetic runtime matrix plus owner-approved real CPU/GPU and VRAM-release run |
| Workspace agent | Bounded discovery/search/read, editor, multi-file diffs, create/move/recover, commands and reviewed web actions | traversal, symlink/race, stale revision, partial publication, denial, timeout and child cleanup | objective read-back, approval tests and owner file/command walkthrough |
| Artifacts and multimodal | Capability-gated image/audio/document input and versioned safe viewers linked to exact turns | spoofed/oversized/corrupt/encrypted input, unsupported viewer, stale version and export race | format matrix, exact-byte evidence and narrow/desktop viewer journeys |
| Direct orchestration | Project-bound Codex/Claude/provider-neutral connections with visible owner, status, Stop, reconnect, resume/fork and revocation | stale token, restart, cross-project access, simultaneous clients and cancellation | direct HTTP/MCP isolation tests and owner-approved client handshake |
| MCP Store | Provenanced searchable tiles, safe details, compatibility, install/update/rollback/uninstall, health, permissions and project tool drawer | malicious metadata/logo, secret handling, schema bombs, redirects/DNS, hangs/crashes, floods and orphan escape | registry/transport/adversarial matrices plus Store-to-Agent browser journey |
| Whole application UI | Coherent hierarchy, icons, responsive panes, truthful controls and complete loading/empty/error states | narrow layout, keyboard traps, stale responses, slow lists, offline/local failures and unavailable authority | route/control inventory, 320–1440 px matrix, accessibility and console checks |
| Privacy and release | Loopback-only operation, content-free diagnostics, recoverable migrations, bounded performance and Windows package parity | migration interruption, retention, startup/shutdown recursion, listener collision and process leak | privacy/OpenAPI/build suites, process census and packaged owner walkthrough |

Features are not traded between rows. For example, a polished chat does not
compensate for unreliable model cleanup, and a safe MCP installer does not
compensate for missing project-scoped tool admission.

## Non-negotiable product truths

- Local services bind to loopback. No transcript, prompt, file content,
  credential, tool argument/result or sensitive derived data leaves the machine
  without an exact task-specific action and visible review.
- Hidden chain of thought is never claimed or exposed. The chat may show
  model-provided reasoning summaries, plans, progress, tool activity and evidence
  when available.
- Starting or stopping a model, agent, command or MCP server must not open a
  terminal window. Cleanup is successful only when the owned root and ordinary
  descendants are verified gone.
- Missing duration, tokens, cost, outcome, context use or capability stays
  unknown. It is never silently converted to zero, failure or support.
- A model's statement that work is complete is not proof. File state, command
  results, tests, diffs and other objective evidence outrank completion text.
- All protected writes, commands, web access, MCP installation and consequential
  tool calls require the exact scoped approval defined for that action.
- Existing user work and unrelated dirty-worktree changes are preserved.

## Checkpoint discipline

Each checkpoint ends with one compact handoff containing:

- what changed and what deliberately remains locked;
- backend, frontend, contract, privacy and browser evidence;
- process/model cleanup evidence where relevant;
- a short owner click checklist;
- the exact next checkpoint.

No checkpoint is called complete while its acceptance test is red, its state is
ambiguous, or the UI claims authority the backend does not provide.

## Operational milestone board

This board is the execution source of truth. Earlier checkpoint documents are
evidence and design history; they do not make a later regression disappear.
Existing implemented behavior is reconciled and repaired in place rather than
needlessly rewritten.

| Milestone | Deliverable | Current state | Exit gate |
| --- | --- | --- | --- |
| Goal-00 | Product contract, privacy boundaries and finish definition | Complete | This document exists, the active goal matches it and the dirty worktree is preserved. |
| Store-05c | Exact local MCP update, one retained rollback generation, uninstall and interrupted-operation cleanup | Complete; owner UI review pending | Install/update/rollback/uninstall/cleanup survive failure and restart tests; UI and API agree; one protected app reload passes with no terminal, MCP or model leak. |
| Store-06 | Project-scoped MCP admission, configuration, tool routing and approvals | Automated implementation complete through Store-06e.4; owner protected clicks remain | Exact reviewed snapshots and project allowlists are durable. An installed admitted host starts only after an exact revision-bound preview and native confirmation, stays memory-only for the current app run, rechecks tool contracts, never auto-starts, and is omitted from model schemas as soon as durable authority drifts. Every call receives a separate non-reusable native confirmation, bounded schema validation/result projection, cancellation/timeout handling, synchronous cleanup on unsafe outcomes, and a content-free SQLite receipt. Configuration-bearing MCPB packages require an exact non-executing schema inspection whose archive, staging and values are discarded. The Store separates focused Browse and Managed workspaces, exposes source-provenanced catalog and compatibility evidence, reconciles exact project/tool/host authority, and renders each actual call as one friendly approval/activity/result card without retaining raw arguments or output. See [Store-06c handoff](checkpoint-mcp-store-06c-handoff.md), [Store-06d handoff](checkpoint-mcp-store-06d-handoff.md), [Store-06e.1 handoff](checkpoint-mcp-store-06e-1-handoff.md), [Store-06e.2 handoff](checkpoint-mcp-store-06e-2-handoff.md), [Store-06e.3 handoff](checkpoint-mcp-store-06e-3-handoff.md), and [Store-06e.4 handoff](checkpoint-mcp-store-06e-4-handoff.md). |
| Store-07 | Adversarial MCP acceptance | Automated complete through Store-07e; owner trusted-MCP review remains in Acceptance-01 | Registry, transport, process, network, schema, secret, crash and isolation matrix passes with content-free diagnostics. See [Store-07e handoff](checkpoint-mcp-store-07e-handoff.md). |
| Agent-11 | Durable project/session/chat parity reconciliation | Automated implementation complete through 11f; native restart review pending | Durable create/browse/switch/rename/pin/archive/restore/move/delete, retained-history resume/fork/export, and restart behavior have automated evidence. Global search follows ownership; Move loads every valid destination; confirmed chat mutations reconcile open state; selected deletion clears stale history/actions without hijacking a background foreground chat; browser export is bound to the visible catalog/history heads; and dedicated routes fall back from cleared live memory to exact durable retained or metadata-only records without accepting stale lookup results. See [Agent-11a handoff](checkpoint-agent-11a-handoff.md), [Agent-11b handoff](checkpoint-agent-11b-handoff.md), [Agent-11c handoff](checkpoint-agent-11c-handoff.md), [Agent-11d handoff](checkpoint-agent-11d-handoff.md), [Agent-11e handoff](checkpoint-agent-11e-handoff.md), and [Agent-11f handoff](checkpoint-agent-11f-handoff.md). |
| Agent-12 | Chat timeline, reasoning summaries and truthful context | Automated implementation complete through Agent-12c; owner review pending | Streaming, Stop, retry/edit/regenerate, Markdown/code, progress, tool evidence and safe reasoning summaries pass ordering and recovery tests. Agent-12a adds exact retained-history Edit/Retry/Regenerate branches with root-turn support, attachment refusal, navigation cancellation and failed-send draft recovery. Agent-12b makes stream/command state monotonic, prevents equal-head Stop rewind, bounds duplicate-snapshot and unexpected-EOF reconnect loops, and proves exact-cursor late-terminal replacement. Agent-12c binds exact-or-unknown context evidence to chat/model/turn, removes streamed-delta request churn, distinguishes admitted/compacted/refused preflights, preserves visibly stale last-confirmed evidence, and provides accessible utilization warnings without substituting a heuristic estimate; see [Agent-12a handoff](checkpoint-agent-12a-handoff.md), [Agent-12b handoff](checkpoint-agent-12b-handoff.md), and [Agent-12c handoff](checkpoint-agent-12c-handoff.md). |
| Runtime-01 | Production local-model acquisition and lifecycle | Automated implementation complete through Runtime-01c; owner review and physical real-runtime acceptance remain | Models and Agent share one revision-bound lifecycle coordinator and placement admission. CPU/GPU/split requests fail closed from current evidence. Verified immutable downloads now have disk admission, a durable restart-reconciled ledger, monotonic progress, pause/resume/retry/cancel, provenance revalidation and confirmed owned-partial cleanup. Runtime processes use minimized environments, exact crash/OOM classification and atomic Windows descendant ownership. The UI exposes truthful capacity, recovery and stale-command states. Owner-approved CPU/GPU/switch/unload and accelerator-release evidence remains pending. See [Runtime-01a handoff](checkpoint-runtime-01a-handoff.md), [Runtime-01b handoff](checkpoint-runtime-01b-handoff.md), and [Runtime-01c handoff](checkpoint-runtime-01c-handoff.md). |
| Workspace-01 | Reviewed coding workspace and tool execution | Automated implementation complete through Workspace-01c; owner walkthrough remains | Bounded discovery, search, edit, multi-file changes, create/move, diffs, commands and web actions pass path/race/approval/read-back tests. `local-agent.v9` provides content-free terminal execution receipts. `agent-change-restore.v1` adds exact preview-first recovery for modified, missing-original and session-created paths, with native confirmation, objective read-back, retained LF/CRLF recovery and direct artifact capture/viewer handoff. Workspace-01c gives every file-change surface one line-numbered, copyable, wrap-aware structured diff viewer; malformed and very tall reviews remain exact and explicitly raw, while contradictory summary counts stay visibly disclosed. Recovery cards now name restore, recreation and Recycle Bin effects before preview. Current controller discovery is `local-agent-orchestration.v22`, with restore apply native-only, project-scoped managed-MCP runtime truth and snapshot-bound catalog paging declared explicitly. See [Workspace-01a handoff](checkpoint-workspace-01a-handoff.md), [Workspace-01b handoff](checkpoint-workspace-01b-handoff.md), and [Workspace-01c handoff](checkpoint-workspace-01c-handoff.md). |
| Artifact-01 | Multimodal input and generated artifact experience | Automated implementation complete through Artifact-01d; owner attachment/lifecycle/viewer review pending | Producing-turn navigation, exact project/chat-bound lifecycle, native PNG/JPEG/PCM-WAV input, bounded inert projections for supported text/data/Office/ODT documents, and the complete version-aware text/code/image/PDF/Office viewer are automated at 360 px and 1440 px. Raw download and sensitive lineage export are separate exact-readback actions; export contains no artifact bytes or absolute workspace path. PDF input still fails closed; staged projections survive service reconstruction and remain model/session bound. See [Artifact-01a handoff](checkpoint-artifact-01a-handoff.md), [Artifact-01b handoff](checkpoint-artifact-01b-handoff.md), [Artifact-01c handoff](checkpoint-artifact-01c-handoff.md), and [Artifact-01d handoff](checkpoint-artifact-01d-handoff.md). |
| Orchestration-01 | Governed Codex/Claude/provider-neutral control | Automated implementation complete through Orchestration-01b; owner external-client walkthrough remains | Two isolated clients can connect within exact project scope, atomically own one live chat operation, reconnect without resubmission, perform a revision-bound two-party handoff, and be revoked without inheriting native approvals or exposing private state. Owner-only wait/Stop, proof-gated release, visible recovery state and restart-safe content-free ownership are verified. See [Orchestration-01a handoff](checkpoint-orchestration-01a-handoff.md) and [Orchestration-01b handoff](checkpoint-orchestration-01b-handoff.md). |
| Sweep-01 | Route-by-route UI/UX, accessibility and scale repair | Sweep-01a, Sweep-01b.1–01b.4 and Sweep-01c.1–01c.3 automated complete; owner review queued | Every route/control/state is inventoried and exercised at desktop and narrow widths with keyboard, focus, contrast, copy and icon consistency checks; loaded high-volume surfaces have explicit render budgets, snapshot-bound durable pages, fixed retained-history windows and stale-response isolation. See [Sweep-01a handoff](checkpoint-sweep-01a-handoff.md), [route/control ledger](sweep-01a-route-control-ledger.md), [state recovery ledger](sweep-01a-state-recovery-ledger.md), [Sweep-01b.1 handoff](checkpoint-sweep-01b-1-handoff.md), [Sweep-01b.2 handoff](checkpoint-sweep-01b-2-handoff.md), [Sweep-01b.3 handoff](checkpoint-sweep-01b-3-handoff.md), [Sweep-01b.4 handoff](checkpoint-sweep-01b-4-handoff.md), [Sweep-01c.1 handoff](checkpoint-sweep-01c-1-handoff.md), [Sweep-01c.2 handoff](checkpoint-sweep-01c-2-handoff.md) and [Sweep-01c.3 handoff](checkpoint-sweep-01c-3-handoff.md). |
| Release-01 | Recovery, performance, Windows packaging and owner acceptance | Active through Release-01a.1; later recovery, process, package and owner gates remain | Agent catalog schemas 1 through 29 now upgrade transactionally to checksummed schema 30 and fail closed on migration-history corruption. Full clean gates, remaining durable-store recovery, process census, production package smoke test and the representative owner walkthrough must still pass without hidden workarounds. See [Release-01a.1 handoff](checkpoint-release-01a-1-handoff.md). |

## Detailed remaining checkpoint map

This is the bounded sequence from the present application state to release. A
checkpoint may be split further when a safety boundary or migration would make
one review too large, but it may not silently absorb a later checkpoint.

| Checkpoint | User-visible outcome | Required acceptance before advancing |
| --- | --- | --- |
| Artifact-01a | Reviewed outputs link back to the exact producing turn; immutable versions can be compared truthfully; unsafe PDFs never enter the renderer. | Complete: focused backend/frontend tests, full Agent frontend regression, two-width browser E2E, production build, privacy scan and protected live reload are green. |
| Artifact-01b | Artifacts have durable rename, archive, restore and explicit recover/remove behavior inside the owning project and chat. | Complete: schema migration, restart, replay/stale-revision, cross-scope, missing/current-file and removed-resynchronization tests; strict API/frontend contracts; keyboard and 360/1440 px browser lifecycle journeys; production build, privacy scan and protected live reload are green. |
| Artifact-01c | The composer admits images, audio and supported documents only when the selected model/runtime can consume them. Recording and upload state are understandable and recoverable. | Complete: strict MIME/suffix/signature/structure/size/capability matrices; restart reprojection and identity binding; explicit PDF refusal; no original document bytes sent to a model; MCP/controller propagation; keyboard and 360/1440 px browser tests; production build, privacy scan and protected live reload are green. |
| Artifact-01d | Generated files and admitted inputs have coherent previews, safe open/download/export, lineage and exact-byte evidence across all supported viewers. | Complete: text/code/image/PDF/Office viewer matrix; active-content refusal; corrupted/encrypted/oversized fixtures; exact scope/revision/version/size/digest read-back; metadata-race refusal; progressive transport fallback; responsive reload/linkage/export tests; production build, privacy scan and protected live reload are green. |
| Orchestration-01a | A user can create, inspect and revoke a scoped Codex-, Claude- or provider-neutral controller connection without opening a terminal. | Complete except owner setup review: project-bound v4 credentials, one-time `pemcp2` setup material, restart/fail-closed legacy-scope behavior, independent revocation, two-client isolation, zero inherited native approval authority and the protected hidden reload are verified. See [Orchestration-01a handoff](checkpoint-orchestration-01a-handoff.md). |
| Orchestration-01b | External controllers can start, observe, stop, resume/fork and hand off exact project/chat turns with visible ownership and status. | Complete: atomic same-project ownership, owner-only wait/Stop, reconnect, stale credential, concurrent claim, revocation, revision-bound handoff, restart migration and proof-gated native release tests pass; strict API/UI projections agree; 360/1440 px ownership journeys, hidden live reload and process/browser census are green. See [Orchestration-01b handoff](checkpoint-orchestration-01b-handoff.md). |
| Store-06c | Installed MCP servers can be started under exact project scope and consequential tool calls enter the native approval lane. | Automated implementation and read-only live gates complete: inert reads, exact start/stop, host ownership, schema and binding revalidation, per-call approval, denial, concurrency, timeout/cancel, malformed/oversized result, cleanup, receipt privacy, Agent activity, protected hidden reload, responsive no-plan Store review and process census pass. Owner authority-increasing clicks remain. |
| Store-06d | Configuration-bearing local MCPB plans are inspected, configured and recovered without retaining plaintext values or accidentally executing the package. | Automated implementation complete: strict v0.3/v0.4 scalar `user_config` inspection, vault-backed required values, install/start just-in-time resolution, exact invalidation, schema-27 restart migration, private confirmed HTTP/UI contracts, 151-test MCP regression, 2,504-test frontend regression, build, privacy scan and hidden loopback reload pass. Owner protected click-through remains. See [Store-06d handoff](checkpoint-mcp-store-06d-handoff.md). |
| Store-06e | The MCP Store and Agent tool drawer expose search, detail, install state, permissions, health, project tool selection and actual call evidence without crowding the chat. | Complete through 06e.4: exact per-call approval/activity/result ordering, denial/Stop/interruption truth, retained-history privacy, keyboard accessibility and 360/1440 px layouts are green. Owner protected clicks remain. See [Store-06e.4 handoff](checkpoint-mcp-store-06e-4-handoff.md). |
| Store-07 | Malicious metadata, transports, schemas and process behavior fail closed without leaking data or leaving children. | Automated complete through Store-07e. Registry presentation, redirect/DNS/proxy/TLS/stream hostility, local process containment, schema/replay, exact vault binding, canary non-disclosure and project/chat/client isolation are green. Owner trusted-MCP click-through remains Acceptance-01. See [Store-07a handoff](checkpoint-mcp-store-07a-handoff.md), [Store-07b handoff](checkpoint-mcp-store-07b-handoff.md), [Store-07c handoff](checkpoint-mcp-store-07c-handoff.md), [Store-07d handoff](checkpoint-mcp-store-07d-handoff.md), and [Store-07e handoff](checkpoint-mcp-store-07e-handoff.md). |
| Acceptance-01 | Previously automated Agent, Runtime, Workspace and Store milestones receive the remaining physical owner evidence without reopening their scope. | Retained-chat restart; real CPU/GPU/split admission; model switch/unload and VRAM release; native picker/confirmation; workspace and Store click ledgers. |
| Sweep-01a | Every route and interactive element has an inventory tied to a real contract and test. Dead, duplicated and misleading controls are fixed or explicitly gated. | Route/control/state matrix; click and keyboard automation; no unexplained disabled controls; no console errors. |
| Sweep-01b | The application uses one coherent responsive design system for hierarchy, panes, icons, focus, status, empty/loading/error states and reduced motion. | 320/360/768/1440 px visual matrix, forced colors, keyboard order and automated accessibility checks. |
| Sweep-01c | Long histories, catalogs, trees and event streams remain usable and truthful under load. | Pagination/virtualization, cancellation, stale-response and layout-shift tests against bounded synthetic stress fixtures. |
| Release-01a | Data migrations, interrupted-operation reconciliation, retention, diagnostics and process cleanup are production-safe. | Active through 01a.1: the Agent catalog has an every-supported-schema migration matrix, checksummed contiguous history, atomic interruption proof, strict API/UI compatibility and a hidden live reload with one listener and zero model processes. Remaining stores, interrupted-operation reconciliation and crash/start/stop process composition stay pending. See [Release-01a.1 handoff](checkpoint-release-01a-1-handoff.md). |
| Release-01b | The packaged Windows application behaves like the validated development stack and the representative owner journey has no hidden workaround. | Production-package install/start/reload/shutdown smoke; privacy/API/build gates; signed owner acceptance checklist. |

### Acceptance debt that remains visible

Automated completion does not erase physical checks that need the owner's real
machine or judgment. The following items stay on the release board while new
implementation continues:

- Agent-11/12: retained project/chat restart and subjective conversation-layout
  review;
- Runtime-01: an explicitly approved real CPU, GPU and supported split run,
  model switch, unload and accelerator-memory release;
- Workspace-01: native picker/confirmation plus create/edit/move/test/recover
  walkthrough;
- Store-05/06: native confirmation and final Store-to-Agent tool-use review;
- each finished visual checkpoint: the short click-later list recorded in its
  handoff.

### Remaining delivery packets

The remaining milestones are deliberately divided into reviewable packets. A
packet may be split when a newly discovered safety boundary demands it, but it
may not absorb unrelated work merely to keep implementation moving.

| Packet | Bounded product outcome | Primary evidence gate |
| --- | --- | --- |
| Store-06e.1 | Complete. Establish the Store/chat information architecture: Store lives in a focused management view; the Agent keeps a compact project tool drawer; advanced lifecycle/configuration moves behind details. | 23 focused Store tests, 36 Store/layout contracts, 475 Agent tests, 2,506 full frontend tests, 360/1440 px rendered journeys, production build, privacy scan and live loopback/browser/process evidence pass. See [handoff](checkpoint-mcp-store-06e-1-handoff.md). |
| Store-06e.2 | Complete. Ship source-provenanced logo tiles, search/filter/sort, trustworthy details, compatibility, install/update/rollback/uninstall state and explicit empty/loading/offline/error recovery. | 29 focused Store tests, 42 Store/layout contracts, 26 backend Registry/icon checks, 20 strict frontend contracts, 481 Agent tests, 2,512 full frontend tests, 360/1440 px rendered journeys, build, privacy scan and live read-only Store/process evidence pass. See [handoff](checkpoint-mcp-store-06e-2-handoff.md). |
| Store-06e.3 | Complete. Reconcile permissions, health, project admission and tool selection between Store, project and active chat without stale authority. | 47 focused MCP UI tests, 497 Agent tests, 48 strict contract/transport tests, 92 backend state-machine tests, 2,528 full frontend tests, 360/1440 px chat-to-Store journeys, production build, privacy scan and loopback/process/GPU census pass. See [handoff](checkpoint-mcp-store-06e-3-handoff.md). |
| Store-06e.4 | Complete. Finish the in-chat tool experience: concise tool availability, exact approval/activity/result cards, settings escape hatch and no chat overcrowding. | 66 direct receipt/privacy tests, 168 affected backend tests, 186 affected frontend tests, 507 complete Agent tests, 360/1440 px keyboard/result journeys, generated API check, production build, privacy scan and loopback/process/GPU census pass. See [handoff](checkpoint-mcp-store-06e-4-handoff.md). |
| Store-07a | Complete. Registry and presentation hostility: poisoned metadata, icons, pagination, identity/version collisions and source disagreement. | 35 focused backend tests, 184 affected backend tests, 64 focused frontend tests, 224 affected contract tests, 514 Agent tests, normal and hostile 360/1440 px browser journeys, API/build/privacy gates and live reload/process evidence pass. See [handoff](checkpoint-mcp-store-07a-handoff.md). |
| Store-07b | Complete. Remote transport hostility: redirects, proxy inheritance, private/reserved DNS, rebinding, TLS/origin drift, SSE/HTTP hangs and oversized streams. | 121 focused backend tests, 202 core backend tests, 364 complete MCP regressions, 214 focused frontend tests, 515 Agent tests, API/build/privacy gates and live loopback/network/GPU evidence pass. No unauthorized connection is retained. See [handoff](checkpoint-mcp-store-07b-handoff.md). |
| Store-07c | Complete. Local process hostility: startup crash, stderr flood, process-tree escape, timeout, Stop race, restart and cleanup uncertainty. | 464-test combined MCP/process matrix, 102 Windows lifecycle/distribution tests, 734 frontend tests, build/API/privacy gates and a 10-second loopback/window/network/GPU census pass. See [handoff](checkpoint-mcp-store-07c-handoff.md). |
| Store-07d | Complete. Tool/schema hostility: recursive/schema bombs, alias collisions, malformed arguments/results, output flood and approval replay. | 476 affected backend tests, 803 affected frontend tests, build/API/compile/privacy gates and a read-only `/agent` smoke pass. Fresh approval claims are atomic and one-use. See [handoff](checkpoint-mcp-store-07d-handoff.md). |
| Store-07e | **Complete.** Secret and scope hostility: value/log leakage, stale vault references, cross-project/cross-chat access and concurrent clients. | Database/log/API/UI canaries, project/chat/client isolation, restart reconciliation, complete backend/frontend gates and a hidden live reload pass. See [handoff](checkpoint-mcp-store-07e-handoff.md). |
| Acceptance-01 | Collect only physical evidence automation cannot supply: retained-chat restart, native dialogs, real model placement/switch/unload/VRAM, workspace action and trusted MCP click-through. | Owner-observed receipts recorded without using private transcript content. |
| Sweep-01a | **Automated complete.** Twenty-two typed route families, 27 direct shapes, shared rendered/source control contracts, complete regressions and the rebuilt loopback-browser pass are green. | Route/control/state ledger, synthetic and local-real traversal, zero unexplained disabled controls or console errors, and a clean listener/process/VRAM census. See [handoff](checkpoint-sweep-01a-handoff.md) and [state recovery ledger](sweep-01a-state-recovery-ledger.md). |
| Sweep-01b | **Automated complete through 01b.4; owner review queued.** Shared hierarchy, typography, spacing, icons, status and primary-action ownership cover Agent and every inventoried route family. Twenty-six route shapes pass 208 settled audits at 320/360/768/1440 px in both themes; keyboard/focus, screen-reader names, contrast, forced colors and reduced motion are green. | Preserve the complete matrix while Sweep-01c proceeds. See [entry](checkpoint-sweep-01b-entry.md), [01b.1 handoff](checkpoint-sweep-01b-1-handoff.md), [01b.2 handoff](checkpoint-sweep-01b-2-handoff.md), [01b.3 handoff](checkpoint-sweep-01b-3-handoff.md) and [01b.4 handoff](checkpoint-sweep-01b-4-handoff.md). |
| Sweep-01c | **Automated complete through 01c.3; owner review queued.** Large loaded collections have fixed render pages or deterministic timeline sampling; Agent projects/chats/artifacts use strict immutable paging; maximum retained history has a fixed mounted window; and stale, cancelled or out-of-order continuations fail closed. | Preserve the maximum synthetic node, latency, overflow and settled-layout-shift gates while release work proceeds. See [entry](checkpoint-sweep-01c-entry.md), [01c.1 handoff](checkpoint-sweep-01c-1-handoff.md), [01c.2 handoff](checkpoint-sweep-01c-2-handoff.md) and [01c.3 handoff](checkpoint-sweep-01c-3-handoff.md). |
| Release-01a.1 | **Automated complete; owner click-later review queued.** Give the Agent project/chat catalog exact checksummed migration provenance and fail-closed recovery from every supported schema. | Schemas 1–29 upgrade to 30; corruption and forced interruption remain non-mutating; full backend/frontend/OpenAPI/build/privacy gates, responsive health journeys and a hidden live reload pass. See [handoff](checkpoint-release-01a-1-handoff.md). |
| Release-01a.2 | Inventory and prove remaining durable-store migrations and interrupted-operation reconciliation across restart. | Every supported synthetic store head upgrades or fails closed; interrupted downloads, artifacts, MCP work and controller ownership never reappear as completed. |
| Release-01a.3 | Prove combined process ownership and cleanup under repeated start, stop, crash, timeout and listener collision. | One loopback listener, no visible console storm and zero silently orphaned model, command, MCP or helper descendants. |
| Release-01b | Prove the installed Windows application matches the validated stack and complete the north-star journey. | Packaged install/start/reload/shutdown smoke and explicit owner sign-off with no undocumented workaround. |

### Checkpoint control loop

Every packet uses the same six visible checkpoints so progress and token spend
remain reviewable:

1. **Entry snapshot:** state the user-visible problem, current evidence, frozen
   scope, exclusions, risk and expected files before broad edits.
2. **Implementation checkpoint:** make only the bounded behavior/API/UI changes;
   record newly discovered unrelated work in the later packet ledger.
3. **Focused proof:** run success, refusal, cancellation, stale/retry and privacy
   tests while the slice is changing. Do not repeatedly rerun broad suites.
4. **Independent gate:** run the affected backend/frontend integration matrix,
   strict contracts, build and privacy scanner once the slice is coherent.
5. **Protected reload:** restart the loopback app hidden, verify one listener,
   zero surprise model/MCP/terminal children and exercise the live route without
   inventing unavailable authority.
6. **Handoff:** update this board and write one compact receipt containing exact
   passes, remaining locks, at most five owner clicks and exactly one next packet.

No later packet starts with ambiguous red tests, undocumented process state or
a missing handoff. Owner-only acceptance may remain visibly pending while a
non-overlapping implementation packet proceeds.

### Anti-loop execution rules

1. Exactly one implementation checkpoint is active. Research may prepare later
   tests, but later production code does not drift into the active slice.
2. The checkpoint starts with a frozen user outcome, touched surfaces, explicit
   exclusions and adversarial acceptance matrix.
3. Focused tests run while code changes. The broad affected regression suite
   runs once after the slice is coherent, and is not rerun without a relevant
   change or a previously red result.
4. A regression discovered on the active path is repaired and recorded. An
   unrelated improvement is added to the named future checkpoint instead of
   expanding the current one invisibly.
5. The production frontend is built and the protected app is reloaded once at
   the end of the slice. Process, listener, model/VRAM and console evidence is
   captured after that reload.
6. Every handoff records exact pass counts, remaining limitations and a maximum
   five-action owner checklist. Unknown evidence remains pending, never passed.
7. No commit, push, real model download, destructive real-data action or remote
   disclosure is inferred from checkpoint approval; each needs its own explicit
   authority when applicable.
8. The next checkpoint begins only after the previous checkpoint has a coherent
   handoff and its state is reflected on this board. Owner visual review may stay
   pending while unrelated implementation proceeds.

Only one milestone is implementation-active at a time. A later milestone may be
researched or test-inventoried, but it does not receive broad code changes until
the current checkpoint has a coherent handoff. This is the guard against the
previous loop where many surfaces changed without a stable review point.

## Definition of done for every implementation checkpoint

A checkpoint is complete only when all applicable layers below are green:

1. **Behavior:** the real backend state machine implements success, refusal,
   cancellation, retry, stale-request and interrupted-operation outcomes.
2. **Persistence:** restart, migration, idempotency and recovery behavior are
   explicit; memory-only behavior is labelled as such.
3. **Contract:** strict request/response parsing, OpenAPI export and generated
   frontend types agree. Unexpected or contradictory fields fail closed.
4. **Interface:** loading, empty, ready, disabled, approval, stopping, failed,
   cleanup-uncertain and completed states are understandable and keyboard
   reachable at narrow and desktop widths.
5. **Evidence:** unit, integration, failure-injection and browser tests cover
   the feature from independent angles. A passing happy path alone is not an
   acceptance result.
6. **Privacy and safety:** only synthetic fixtures are used; diagnostics remain
   content-free; protected effects are exact and reviewed; no private provider
   data or credential store is inspected.
7. **Runtime hygiene:** owned listeners, model workers, command trees and MCP
   hosts have bounded lifecycle evidence. Relevant GPU/process cleanup is
   checked, and no visible terminal window is spawned.
8. **Integration:** the production frontend builds, the protected app is
   reloaded once for the coherent slice and the live route is smoke-tested.
9. **Handoff:** the checkpoint ledger records what changed, exact test receipts,
   limitations, what the user should click later and the next milestone.

## Owner interaction budget

Work continues autonomously for code, synthetic fixtures, migrations, contract
tests, browser automation, accessibility checks, failure injection, privacy
scans, builds and loopback smoke tests. The owner is needed only where evidence
cannot truthfully be synthesized:

- subjective visual preference after a checkpoint reload;
- native picker/confirmation clicks that automation cannot safely perform;
- an explicitly approved real model download or CPU/GPU/VRAM acceptance run;
- login or consent for a real external provider/client handshake;
- destructive handling of real user-created projects, chats, models or files;
- final release sign-off.

An unavailable owner check does not stall unrelated implementation. It is
recorded as **owner acceptance pending**, never silently reported as passed.

## Checkpoint report shown to the owner

Each checkpoint update uses the same compact order:

1. **Outcome:** the user-visible capability that now works.
2. **Changed:** the bounded implementation and UI surfaces touched.
3. **Validated:** exact automated receipts and live process/runtime evidence.
4. **Still locked:** behavior intentionally unavailable or awaiting acceptance.
5. **Click later:** a short numbered manual review, normally no more than five
   actions.
6. **Next:** one proposed checkpoint, requiring explicit approval before broad
   work moves to it.

## Workstream A — durable Agent projects and chats

Required experience:

- A left rail of durable projects and chats with create, switch, rename, search,
  pin, archive, restore and explicit delete/trash behavior.
- Chats survive app restart according to the selected retention mode. Project,
  chat, branch and fork lineage is visible and recoverable.
- New chat, Stop, retry, fork/branch, export and close have deterministic state
  machines and never duplicate turns after retry or reload.
- The main conversation remains the visual priority. Settings, files, artifacts,
  diagnostics and permissions live in drawers or secondary panes.
- Streaming text, Markdown, code blocks, copy actions, citations, diffs,
  attachments, tool cards, progress, errors and completion evidence render in a
  consistent timeline.

Acceptance evidence:

- SQLite restart/migration/idempotency tests;
- desktop-width, narrow-width and keyboard-accessibility UI tests;
- real browser create/switch/reload/archive/restore/fork/export walkthrough;
- zero conversation-content crossover between projects or chats.

## Workstream B — local model lifecycle and broad model use

Required experience:

- Discover or import compatible Hugging Face model artifacts with revision,
  license, tokenizer and runtime provenance. Never enable `trust_remote_code` by
  default and never vendor model weights.
- Download with progress, pause/cancel/retry, integrity checks, disk-space truth
  and recoverable partial-download cleanup.
- Select CPU, GPU or bounded GPU/CPU placement when the runtime supports it.
  Unsupported combinations are disabled with a reason.
- Start, health-check, chat, Stop and unload are explicit. Switching models first
  closes the old session/runtime and verifies VRAM/process release before loading
  the replacement.
- Show truthful context-window capacity and usage as known, estimated or unknown.
- Negotiate text, image and audio input only when the selected model/runtime
  declares and passes that capability.

Acceptance evidence:

- synthetic runtime matrices plus at least one owner-approved real CPU and GPU
  model walkthrough;
- timeout, crash, cancellation, out-of-memory and switch-under-load tests;
- before/after process and accelerator-memory cleanup evidence;
- no visible terminal windows.

## Workstream C — coding workspace and reviewed file operations

Required experience:

- Choose one absolute workspace with a native folder picker and retain only the
  project-scoped reference the user approved.
- Bounded tree/search/read for admitted files; exact UTF-8 editor; rich diff;
  create, edit, multi-file transaction, new folder, no-overwrite move/rename and
  recoverable deletion where supported.
- The agent can propose changes and tests, but every publication is revision-
  bound and reviewable. Multi-file publication is failure-atomic within its
  documented boundary, with truthful rollback or cleanup quarantine.
- File-change, command and web effects appear as distinct timeline cards with
  status, duration, evidence and approval state.
- Git metadata is local and bounded. No private remote, credential or unrelated
  repository content enters logs or model context.

Acceptance evidence:

- adversarial path, symlink, race, stale revision, partial failure and restart
  tests;
- objective read-back of every applied file effect;
- owner walkthrough: create, edit, move, diff, run tests, revert/recover and open
  the resulting artifact.

## Workstream D — artifacts, documents and multimodal chat

Required experience:

- Image, audio and supported document attachments have upload/record controls,
  previews, validation, size/type limits and explicit model-capability routing.
- Generated files become versioned artifact cards linked to their producing turn
  and objective filesystem evidence.
- Safe viewers exist for text, code, images, PDF and other explicitly supported
  formats. Active content is never executed inside a viewer.
- Artifact open, download/export, compare versions, rename/archive and recovery
  behavior are explicit.

Acceptance evidence:

- malformed, oversized, spoofed MIME, truncated, encrypted and unsupported-file
  tests;
- viewer render tests at desktop and narrow widths;
- generated-file link, reload and exact-byte read-back tests.

## Workstream E — reasoning, activity and agent feedback

Required experience:

- Show a compact state header: ready, thinking, waiting for approval, running a
  tool, streaming, stopping, failed, cleanup uncertain or complete.
- Render model-provided reasoning summaries or structured plans when the runtime
  supplies them. Label inferred summaries separately; never label hidden chain
  of thought as available.
- Tool and command cards show what class of action is requested, why approval is
  needed, bounded input summaries, progress, result evidence and cleanup state.
- Long operations provide visible progress or heartbeat evidence and a working
  Stop control. Empty or silent panels are never used as success signals.

Acceptance evidence:

- event ordering, reconnect, duplicate, late-event and Stop-race tests;
- UI tests for every state and failure class;
- real-model walkthrough with at least one file proposal and one command.

## Workstream F — external Codex/Claude/agent orchestration

Required experience:

- Keep the direct loopback `/mcp/agent` direction distinct from the third-party
  MCP Store direction.
- Create scoped, revocable Agent connections with one-time private setup material
  for Codex, Claude Code and provider-neutral MCP clients.
- External controllers can discover projects/chats, start bounded turns, inspect
  events, propose reviewed file changes, fork/export sessions and coordinate
  local models only within their granted scopes.
- Native approvals cannot be forged or delegated through MCP. Revocation takes
  effect immediately and restart behavior is explicit.
- Support a parent agent orchestrating multiple local sessions without sharing
  chat content, credentials, workspace authority or pending approvals between
  them.

Acceptance evidence:

- direct HTTP and MCP contract tests for two simultaneous clients, revocation,
  reconnect, stale token, cross-project isolation and Stop;
- synthetic Codex/Claude configuration round trips with no bridge terminal;
- owner-approved live orchestration walkthrough.

## Workstream G — MCP Store discovery and lifecycle

Required experience:

- Search the Official MCP Registry first. Additional portal adapters use
  documented APIs or permitted feeds, retain source/provenance/fetch time and do
  not treat popularity or listing as a security approval.
- Deduplicate exact identities and versions. Small tiles show a safely proxied
  raster logo or deterministic fallback, name, publisher, description, source,
  version, local/remote transport and current management state.
- Detail review shows provenance, license/integrity evidence, declared inputs,
  permissions, risks and compatibility evidence without exposing endpoint paths,
  secrets or tool data.
- Install, update, uninstall and rollback/cleanup are separate native-confirmed
  state machines. Buttons reflect the real backend state and are idempotent.
- Local stdio servers use hidden, atomically owned process trees. Remote servers
  use exact reviewed HTTPS origins, public-only pinned DNS, no proxy/redirect and
  bounded I/O.
- Tool schemas are admitted separately from installation. Each Agent project
  selects exact servers, permissions and tools. Consequential tool calls receive
  per-action review unless a narrowly scoped remembered policy explicitly covers
  them.
- Store pages show health, update availability, recent content-free failures,
  tool count/schema revision and whether a host is stopped or running.

Acceptance evidence:

- malicious Registry metadata, logo and source-adapter fixtures;
- install/update/uninstall crash, retry, restart and rollback tests;
- modern/legacy stdio, Streamable HTTP and SSE protocol tests;
- schema bomb, pagination, response-size, redirect, DNS rebinding, credential,
  stderr flood, child escape, hang, crash and Stop tests;
- zero visible terminal or orphan process; no tool result requested by a health
  probe; strict project isolation for actual tool calls.

Current status: Store-01 discovery, Store-02 exact review, Store-03 durable
plans, Store-04 guarded compatibility checks, Store-05a exact durable remote
activation/deactivation and Store-05b checksum-pinned isolated MCPB installation
are implemented. Store-05c update/uninstall/rollback/cleanup is also complete,
with automated and protected live gates passed and owner UI review pending.
Store-06a exact tool review and project admission is complete. Store-06c adds an
inert-until-confirmed app-run supervisor, exact project host controls, fresh
approval for every admitted call, bounded result projection, content-free
receipts, stale-authority fail-closed behavior, and synchronous cleanup on
cancel or unsafe results. Its automated and read-only live gates are green;
authority-increasing owner clicks remain. Store-06d adds exact non-executing
MCPB configuration inspection, content-free durable schema evidence,
vault-backed just-in-time required values, strict invalidation and schema-27
restart migration. Its automated, build, privacy and hidden-reload gates are
green; protected click-through remains. Store-06e management/chat UX is
automated-complete through 06e.4; Store-07 adversarial acceptance is
automated-complete through 07e, with trusted protected click-through retained
for Acceptance-01. See the
[Store-05c handoff](checkpoint-mcp-store-05c-progress.md) and
[Store-06c handoff](checkpoint-mcp-store-06c-handoff.md) and
[Store-06d handoff](checkpoint-mcp-store-06d-handoff.md) for current evidence and
the authority that remains deliberately locked.

## Workstream H — whole-application UI/UX completion sweep

Required experience:

- Audit every route, card, button, checkbox, picker, dialog, drawer, empty state,
  loading state and error state against its backend contract.
- Remove duplicated icons, misleading affordances, dead controls, overcrowding,
  inconsistent terminology and layout shifts.
- Establish one icon system, spacing/type scale, focus system, status palette,
  responsive pane behavior and reusable primitives.
- Keyboard, screen-reader, contrast, reduced-motion and 320 px behavior are part
  of correctness, not polish deferred after release.

Acceptance evidence:

- route inventory mapped to interactive tests;
- screenshot/browser matrix for desktop and narrow widths;
- automated accessibility checks plus manual keyboard walkthrough;
- every intentionally unavailable control explains the next gate.

## Workstream I — privacy, recovery, performance and distribution

Required experience:

- Versioned migrations, bounded retention, content-free diagnostics and recovery
  states for interrupted model, Agent, file and MCP operations.
- Startup and shutdown cannot recursively spawn app windows or leave listeners,
  workers, models, commands or MCP hosts behind.
- Large histories, catalogs, file trees and event streams remain responsive via
  pagination, virtualization or bounded summaries.
- Packaged Windows behavior matches development behavior: folder picker,
  confirmations, hidden processes, loopback listener and cleanup.

Acceptance evidence:

- full backend/frontend/privacy/OpenAPI/build suites;
- migration from every supported schema version;
- cold start, reload, shutdown and crash-recovery process census;
- production-package smoke test on the owner's machine.

## Execution order

The sequence below starts from the current application state. Completed Agent,
Runtime, Workspace, Artifact and Store slices remain regression obligations; they
are not reimplemented merely to make progress look active.

1. **Preserve closed Orchestration-01a.** Keep the project-scoped connection
   contract and protected-live evidence green while its short owner setup review
   remains visible.
2. **Preserve closed Orchestration-01b.** Keep durable visible ownership,
   owner-only wait/Stop, exact reconnect and revision-bound two-party handoff
   green while its real external-client owner walkthrough remains visible.
3. **Preserve closed Store-06c.** Keep exact app-run hosting, project routing,
   per-call approval, cancellation and synchronous cleanup green while its
   authority-increasing owner click ledger remains visible.
4. **Preserve automated-complete Store-06d.** Keep exact non-executing MCPB
   configuration inspection, OS-vault value handling, restart migration and
   strict privacy contracts green while its protected click-through remains.
5. **Preserve automated-complete Store-06e.** Keep source-provenanced Store
   management, exact project tools and one-card in-chat call evidence green
   while its protected owner click ledger remains visible.
6. **Preserve automated-complete Store-07.** Keep registry/presentation,
   transport/network, process, schema/replay and secret/isolation packets green;
   do not substitute synthetic evidence for the trusted owner click-through.
7. **Close Acceptance-01 debt (next).** Collect the retained-chat restart, native
   picker/confirmation, real CPU/GPU/supported split, model switch/unload/VRAM,
   workspace and Store evidence that automation cannot honestly replace.
8. **Run Sweep-01a through 01c.** Inventory and exercise every route/control,
   repair misleading or unfinished behavior, unify the responsive accessible
   design system and stress long histories/catalogs/trees/streams.
9. **Run Release-01a.** Complete migration, retention, recovery, performance,
   startup/shutdown and process/listener cleanup acceptance.
10. **Run Release-01b.** Build and smoke-test the Windows package, execute the
    north-star journey and obtain explicit owner release sign-off.

At each numbered boundary the board, evidence ledger and click-later list are
updated before implementation advances. If a test exposes a regression in a
previously complete milestone, that regression becomes the bounded repair inside
the current dependency checkpoint; it is never hidden as historical debt.

## Final release gate

The finish goal is achieved only when all workstreams above have direct current
evidence, no required feature remains labelled partial or unavailable, every
protected action has the intended review boundary, all automated suites pass,
the production app reloads cleanly, and the owner can complete the representative
Agent + model + files + artifact + MCP + external-orchestrator walkthrough without
using a hidden workaround.
