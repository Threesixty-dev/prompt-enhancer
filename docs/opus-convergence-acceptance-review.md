# Independent acceptance review: Agent keyboard, short-height, disabled-explanation and owner-scope recovery

Reviewer role: independent acceptance worker (assignment `10-independent-acceptance`).
Date: 2026-09-07.
Owned files: `frontend/e2e/opus-convergence-accessibility.spec.ts` and this document.
No application, fixture, configuration, register or plan file was modified.

## 1. Evidence status — read this first

**Updated 2026-09-07 (post-settlement root pass).** The latest root run of this
spec is **8/8 passed**, including assertions for the **F1 and F2 direct
descriptions**. The owning standard browser project is now green on the final
code. The original "authored, not executed" status is kept below for the audit
trail; it no longer describes the current state.

- **Authored by this worker (no command tools):** the eight cases in
  `frontend/e2e/opus-convergence-accessibility.spec.ts`.
- **Executed by root (latest):** all 8 cases **passed**, including case 5
  (560 px height, which no prior suite exercised) and the F1/F2 direct-
  description assertions against worker 06's landed association fix.
- **Executed by root, owning gate:** the standard Playwright project at
  **183 passed, zero failures**, with 6 intentional screenshot skips (4.1 m),
  after the PDF and contrast settlement fixes. This run happened **before** the
  batch's last bounded `AgentPage` startup guard patch and was **not** re-run
  after it.
- **Executed by root, final unit gate:** the **final frozen full frontend unit
  run** on the final code — **2861 passed across 192 files, zero failures**
  (248.25 s, `npm test -- --maxWorkers=4 --reporter=dot`). Earlier full runs
  (2843/7 unfrozen, 2859/1 frozen) are **superseded**.
- **Executed by root, after the final patch:** the production build passed (the
  existing over-500 kB chunk warning remains), and the **rebuilt** real
  built-loopback project passed **16/16** (22.8 s) with cleanup confirmed:
  listener released, temp removed, models 0.
- **Executed by root, typecheck:** the isolated strict `tsc` of §5 item 3 passed
  for **both** `opus-convergence-accessibility.spec.ts` and
  `sweep-01b-accessibility.spec.ts`. It ran before the startup guard patch; both
  specs are unchanged since, so the result still holds.
- **Executed by root, earlier and supporting:** repeated PDF browser run **6/6**;
  intercepted contracts **41/41**; `check:api` and `privacy_scan` green, to be
  re-checked after the documentation edits.
- **Not run, not claimed:** native, packaging, model, provider and real-MCP
  evidence, and a post-patch re-run of the standard browser project. No
  installation, relaunch, restart, model load or screenshot was produced for this
  packet. No commit or push.
- **Still a working checkpoint.** A green unit gate validates this bounded batch;
  it does **not** mean the software is finished, and no checkpoint advances.

## 2. Scope and method

Read first: the finish goal (`prompt-enhancer-finish-goal-2026-08-29.md`,
execution order §Converge-01…07 and the feature closure scorecard), the owner
feature register (`prompt-enhancer-owner-feature-register-2026-08-31.md`), the
Playwright standard project (`frontend/playwright.config.ts`), the existing
Agent browser suites (`workflow-panels.spec.ts`, `sweep-01b-accessibility.spec.ts`,
`ui-00-shell-primitives.spec.ts`, `loopback-built.spec.ts`) and the owning
components (`AgentRuntimeControl.tsx`, `AgentPage.tsx`,
`AgentMcpConnectionsPanel.tsx`, `shared/ui/Dialog.tsx`).

Constraints honoured: synthetic fixtures only (existing
`e2e/fixtures/workflow-panels.html` panels `agent-shell` and
`agent-controller-ownership`); no privileged/real transport; no server launch, no
model, no provider or account data; no new fixture, component or config file
(those belong to other workers); no duplication of assertions already made by
the suites above.

## 3. Requirement mapping for the authored cases

| # | Case (spec title fragment) | Register / checkpoint IDs | Obligation asserted | Prior coverage |
| --- | --- | --- | --- | --- |
| 1 | `explains its already-applied refusal` | UX-01, UX-04, MOD-03, AGT-10 | The composer overlay's blocked primary action carries a machine-readable reason; no control in the overlay is disabled without one; controls that are still usable stay enabled | `workflow-panels.spec.ts:530-543` uses the overlay but never asserts an explanation for a blocked control |
| 2 | `opens, tabs and closes by keyboard` | UX-04, AGT-01, Converge-03, Agent-12f | Overlay is openable from the keyboard, tab order enters the panel in visual order, Escape closes it and restores focus to the summary | Existing browser tests open/close the overlay by pointer only (`workflow-panels.spec.ts:53-84, 530-543`); Escape/focus restoration existed only in component tests |
| 3 | `Escape inside the nested runtime evidence disclosure` | UX-04, AGT-01 | Nested `details` inside the overlay is not a keyboard trap: one Escape closes the whole overlay and restores focus | None |
| 4 | `pointer dismissal … without pulling focus back` | UX-04, Agent-12f | Outside dismissal closes the overlay but does not steal focus back into the disclosure (the documented difference from Escape) | None |
| 5 | `560px-tall window keeps the runtime overlay…` | UX-02, UX-04, AGT-01, Converge-03 | At a viewport shorter than any covered height, the overlay stays inside the viewport and its sticky primary/stop actions stay in view without page-level horizontal overflow | Shortest Agent-shell heights asserted today are 640 px (`workflow-panels.spec.ts:39`) and 720 px (`:90`) |
| 6 | `browser-only chat setup names the exact native gate` | UX-01, UX-05, WSP-01, WSP-06, WSP-07 | With native presence unavailable, the disabled Protected-actions group is programmatically described by the exact recovery path, the web-fetch control states its own refusal, and Escape closes the drawer with focus restored | Only `loopback-built.spec.ts:220-222`, which the standard project excludes (see finding F4); Escape/focus restoration for this drawer: none |
| 7 | `external controller ownership explains every unavailable owner action` | ORC-02, ORC-03, ORC-04, UX-01, UX-05 | Owner-scope recovery: unavailable owner actions state their gate, the ownership card shows its native next step, and the incoming-handoff card exposes no control that could imply local acceptance | `workflow-panels.spec.ts:571-591` asserts the copy and that Release is disabled, but not that any unavailable control is explained, nor that the handoff card is control-free |
| 8 | `560px-tall window keeps owner-scope recovery guidance readable` | ORC-04, UX-02, UX-04, UX-05 | The settings dialog holding controller recovery guidance stays inside a short viewport, scrolls internally, avoids horizontal overflow and is Escape-closable with focus returned to its trigger | None at short height; `workflow-panels.spec.ts:593-640` covers the Connections tab at the default height only |

Fixture states used (all synthetic, all pre-existing):
`workflow-panels.tsx:628-799` (ready coordinator serving `example` on CPU at 4096
context with a measured request), `:1806-1808` (native presence deliberately
unavailable in the browser fixture), `:312-359` (two controller connections and
one `waiting_native_approval` ownership with an offered handoff).

## 4. Findings

The findings were originally source-read observations on files owned by other
workers. F1, F2 and F3 have since been repaired by their owners and executed by
root; the rest of this section records both the original observation and the
receipt that closed it.

Assignment status (2026-09-07, post-settlement root pass), owner-tracked in
`checkpoint-opus-convergence-01-handoff.md`:

| Finding | Owning file | Assigned worker | Status |
| --- | --- | --- | --- |
| F1 | `AgentMcpConnectionsPanel.tsx` | 06 | **Closed** — direct description asserted in the latest 8/8 browser run; MCP component suite 26/26 passed |
| F2 | `AgentMcpConnectionsPanel.tsx` | 06 | **Closed** — same run and receipt as F1 |
| F3 | `AgentRuntimeControl.tsx` | 04 | **Closed at component level** — RuntimeControl 31/31 passed against the landed association; browser-level proof still blocked by F6 |
| F4 | `playwright.config.ts` scope | 10 (this packet) | Case 6 landed and passed; scope gap addressed for the standard project |
| F5 | Agent short-height coverage | 10 (this packet) | Cases 5 and 8 landed and passed at 560 px |
| F6 | `e2e/fixtures/workflow-panels.tsx` | unassigned | **Blocked — still open.** Needs a fixture owner |
| F1-class follow-up | `AgentMcpConnectionsPanel.tsx` | queued, unassigned | **Open.** `Create direct connection` and `Prepare replacement` still lack direct disabled descriptions — a new gap of the same class as F1, found after the F1/F2 repair |

**F1, F2 and F3 are closed by executed root receipts, not by this document's
say-so.** F6 and the F1-class follow-up remain open. Closure of F1/F2/F3 does
not advance any checkpoint or release gate.

**F1 — Unavailable controller actions are explained only positionally.**
*Closed: worker 06 landed the association; root's latest run of this spec
asserts the direct description and passed 8/8, with the MCP component suite at
26/26.* Original observation follows.
`AgentMcpConnectionsPanel.tsx:1545-1570` disables Rotate and Revoke whenever
native presence is unavailable. The reason exists once per region as
`<p role="status">Open the owned native app window to create, rotate, or revoke
connections.</p>` (`:1095-1097`), but no disabled control references it via
`aria-describedby`. A screen-reader user who lands on the buttons receives no
reason. UX-01/UX-04. Suggested repair (owner of that file): give the status
paragraph an id and point the three controls at it. Case 7 originally asserted
the region copy and the disabled state, deliberately not the association; the
latest spec revision does assert the direct description, and that assertion
passed.

**F2 — `Release settled control` relies on `title` alone, and the title omits the
gate that is actually active.**
*Closed by the same run and receipt as F1.* Original observation follows.
`AgentMcpConnectionsPanel.tsx:1492-1507` disables
the button on four independent conditions, including `!userPresenceAvailable`,
but the only attached explanation is a static `title` about backend settlement.
`title` on a disabled (non-focusable) button is unreliable for assistive tech.
ORC-04/UX-01. Case 7 asserts only that the explanation exists and mentions
settlement, which is true today.

**F3 — Placement and Context-limit selects are disabled without a description.**
*Closed at component level: worker 04 landed the association and root's
RuntimeControl run passed 31/31 (39 combined with the 8 PDF cases). Browser-level
proof is still blocked by F6, so this is a component receipt, not a browser one.*
Original observation follows.
`AgentRuntimeControl.tsx:1133` and `:1149` disable both selects on
`busy || anyTurnRunning`, while the sibling Model select at `:1115` carries
`aria-describedby={applyDisabledReasonId}`. A visible hint (`:1264`,
`#agent-runtime-active-turn-hint`) exists, so the gap is association, not copy.
UX-04/MOD-03. Not asserted: reaching `anyTurnRunning` in the browser needs a
fixture panel with a live running turn, which is another worker's file.

**F4 — The only browser assertion that browser-scope protected actions are
disabled lives outside the standard gate.** `playwright.config.ts:5-9` excludes
`loopback-built.spec.ts` from the standard project, and that is where
`Protected actions` was asserted (`:220-222`). Until case 6 lands, a regression
that silently enabled protected-action toggles in a browser-scoped session would
not be caught by the standard suite. WSP-06/UX-01.

**F5 — Agent short-height coverage stopped at 640 px.** `workflow-panels.spec.ts`
asserts the Agent shell at 640 px and 720 px only; the register's responsive
obligation (UX-02, 320/360/768/1440 px widths) has no *height* floor, so the
overlay behaviour on short laptop windows was unasserted. Cases 5 and 8 add a
560 px floor.

**F6 — MOD-03 live placement refusal has no browser evidence (blocked, not
fixed).** `AgentRuntimeControl.tsx:520-591` implements `placementLoading`,
`placementReadFailed` and `livePlacementUnavailable` refusal copy, but
`workflow-panels.tsx` supplies no `getLocalModelPlacement`, so the browser suite
can only ever exercise the cached-placement branch. Closing this needs a fixture
change (`e2e/fixtures/workflow-panels.tsx`, not owned here); recorded for the
Sweep-01a/Runtime-01 owner rather than worked around.

## 5. Acceptance commands for the orchestrator

Run from the repository's `frontend/` directory (PowerShell). The Playwright
project starts its own Vite dev server on `127.0.0.1:4173`
(`playwright.config.ts:24-28`); no application, model or provider process is
required.

| # | Command | Status |
| --- | --- | --- |
| 1 | `npx playwright test e2e/opus-convergence-accessibility.spec.ts --reporter=list` | **Run by root — 8/8 passed** in the latest revision, including the F1/F2 direct-description assertions |
| 2 | `npx playwright test` (owning standard gate; must stay at its prior count plus these 8) | **Run by root — 183 passed, zero failures**, 6 intentional screenshot skips (4.1 m), after the PDF and contrast settlement fixes but **before** the final `AgentPage` startup guard patch |
| 3 | `npx tsc --noEmit --strict --skipLibCheck --target ES2022 --module ESNext --moduleResolution Bundler --lib ES2022,DOM,DOM.Iterable --types node e2e/opus-convergence-accessibility.spec.ts` (and the same for `e2e/sweep-01b-accessibility.spec.ts`) | **Run by root — both passed.** Needed because the app project's `tsconfig.app.json` includes only `src`, so `npm run build` does not cover `e2e/` |

Triage of the three earlier broader-browser failures (root's, none in this
packet's eight cases), all now resolved:

- **MCP stale expected text** — fixed and re-executed: **8 passed**.
- **PDF keyboard measurement** — a `tabIndex` mismatch. The repair adds both-axis
  before-paint measurement and true keyboard panning; component **10/10 passed**
  and the repeated browser run **6/6 passed**.
- **Dark-theme contrast at 768 px, ratio 3.68, on the `/` route only** — the
  browser reading is now taken under a **deterministic settlement** (an explicit
  settled flag and a finite animation count) rather than at an arbitrary frame,
  and a new static test asserts the palette itself (**3/3 passed**); the static
  palette is good. **No production CSS changed.** Whether a real transient flash
  ever occurs is **unconfirmed** and left as future investigation.

Not required and not claimed by this packet: backend tests, the intercepted
contract project, the real-loopback project, the production build, the API check
and any app reload. This file changes no runtime code path.

## 6. Risks and remaining gates

- **Resolved: the authored cases now have a receipt.** Cases 2 and 3 (Chromium
  activating a `<summary>` with Enter; the document-level Escape handler at
  `AgentRuntimeControl.tsx:693-712`), case 6 (the window-level Escape handler at
  `AgentPage.tsx:2398-2407` and the deferred focus restore at `:2357-2369`) and
  case 5 (560 px, below any previously asserted Agent height, bounded by
  `AgentRuntimeControl.css:225`) all passed in root's run. The keyboard, focus
  and short-height obligations they encode are now asserted, not assumed.
- **This is still not a final gate.** The final unit run and both spec typechecks
  are reported, but the standard browser project has not been re-run after the
  last startup guard patch, and native, packaging, model, provider and real-MCP
  evidence does not exist. This remains a working checkpoint, not finished
  software. No percentage or suite-wide completeness claim is made here.
- **Full-suite trajectory, now closed.** Root's initial run gave 2843 passed, 7
  failed of 2850 and was **not frozen code** (four of those tests were being
  edited mid-flight); every owning file passed subsequently on its own (AgentPage
  171/171 in 291.79 s, RuntimeControl 31/31, Overlay 25/25). A later frozen run
  gave **2859 passed, 1 failed of 2860 across 192 files**. Both are **superseded**
  by the final **2861 passed, zero failures across 192 files** (248.25 s).
- **That single remaining failure was a test defect, not a proven product
  rollback.** The selected-project case performed a **detached-DOM click**: the
  query returned a row the reload had already removed, so the click never fired.
  Three isolated runs reproduced the detachment. The corrected test waits for the
  actual project reload, queries and clicks synchronously, and positively asserts
  the selected row. Both the original and the new deferred-startup tests passed in
  all three parallel repeats (2 cases each, 170 deselected) — a focused receipt
  only, **no full-suite claim**. The product change kept from the triage is narrow:
  only the late-startup landing abandonment after the user opens New chat, plus
  the pre-existing branch-feedback and settings fixes. The speculative
  `selectedProjectIdRef` / `newChatProjectRef` state and the rail-retarget guards
  were reviewed and **removed**.
- **Cases 1 and 7 encode a snapshot of the current fixture's settled state**
  (`Applied` / already-applied reason; `waiting_native_approval`). If another
  worker changes those fixture states, these cases fail loudly rather than
  silently weakening — that is intended, but the fixture owner should be told.
- **F1, F2 and F3 are now closed on executed receipts** (worker 06 and worker 04
  landed the associations; root ran them). F3's receipt is a component receipt
  only. **F6 stays open and blocked** on a fixture owner.
- **The queued work is unchanged and unowned.** `Create direct connection` and
  `Prepare replacement` still lack direct disabled descriptions in
  `AgentMcpConnectionsPanel.tsx` (a new F1-class gap); the F6 placement fixture
  needs an independent owner; `AgentArtifacts` viewer-body stable-gutter polish
  is outstanding; and the owner visual, native, model and packaging gates are
  untouched. None of these has an owner receipt.
- **Nothing here advances a checkpoint, including C07.** No feature is complete
  because of this packet; owner visual, native, model and packaging release gates
  (Converge-03/04/05b and all Converge-07 evidence) are **unchanged**. Nothing in
  this batch involved a commit, push, restart, model load, native install or
  external MCP transport.
