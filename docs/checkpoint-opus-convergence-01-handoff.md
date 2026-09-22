# Checkpoint Opus-Convergence-01 handoff — ten bounded worker batches

Status: **working checkpoint, not finished software.** All ten logical worker
batches are done with their review follow-ups, the three audit findings F1–F3 are
closed, and the standard browser project, the build, `check:api` and the privacy
scan are green. The **final frozen full frontend unit run has now landed:
2861 passed across 192 files, zero failures (248.25 s)**, on the final code. That
is a unit-gate receipt for this bounded batch only — it is **not** a claim that
the software is finished, and no completeness or percentage claim is made here.

Date: 2026-09-07 (updated with root's post-settlement receipts)
Scope: one bounded documentation checkpoint for the ten logical workers in this
convergence batch, their owned files, the receipts root has produced so far, and
what is still pending.

## 1. Model and roles

- The driving CLI session model ID was verified as exactly `claude-opus-5`.
- Auxiliary **Haiku** metadata is also present for internal/background calls in
  the same session. So the accurate claim is: *the session's driving model is
  `claude-opus-5`, with internal auxiliary Haiku traffic observed.* Do **not**
  claim that every call in this batch was served exclusively by Opus 5.
- **Root** orchestrates and **performs no implementation itself**: it assigns the
  bounded batches, reviews the diffs, runs every command, and owns every result
  reported below.
- **Workers 01–10** are logical Opus 5 agents that **edit files only**. They have
  no command tools, so nothing a worker writes is a receipt. A worker's claim is
  source-read until root executes it.

## 2. Batch rules

- One owned file set per worker; every other file is off limits, including other
  workers' files, fixtures, configuration, registers and plans.
- Synthetic fixtures and fictional identities only. No personal or absolute home
  paths, account data, provider transcripts or screenshots in code or docs.
- A worker never closes its own item. Root closes an item only with an executed
  receipt against the worker's landed change.
- **Not performed anywhere in this batch:** commit, push, application or PC
  restart, native install, relaunch, real MCP transport, model run, VRAM use,
  screenshots.

## 3. Worker assignments and current state

| # | Owned files | Scope | State |
| --- | --- | --- | --- |
| 01 | `frontend/src/features/model-ensemble/MetricEvidenceFilePanel.{tsx,test.tsx}`, `RequirementActionEvidencePanel.{tsx,test.tsx}`, `frontend/src/entities/discovery/EvidenceList.contrast.test.ts` | Evidence focus behaviour, the receipt-acknowledgement race, and the dark-theme contrast follow-up | Edits landed; covered by the combined Evidence + Catalog run (102 passed). Contrast follow-up delivered as a deterministic browser settlement plus a new static palette test (**3/3 passed**) — see §4.2 |
| 02 | `frontend/src/features/agent/AgentPage.{tsx,test.tsx}` (onboarding modal), `frontend/src/test/setup.ts`, `frontend/src/test/reactCleanup.test.tsx` | Onboarding modal plus centralised React Testing Library cleanup (6 cleanup tests) | **Green** — cleanup 6 passed; AgentPage suite **171/171 passed** (291.79 s) |
| 03 | `frontend/src/features/agent/AgentPdfPreview.{tsx,css,test.tsx}`, `frontend/e2e/workflow-panels.spec.ts` | PDF render resources and real zoom | **Green** — component **10/10 passed**; repeated browser run **6/6 passed** |
| 04 | `frontend/src/features/agent/AgentRuntimeControl.{tsx,test.tsx}` | Deferred context-limit read and Escape focus restoration; **F3** (Placement/Context-limit selects disabled without an `aria-describedby` association) | **Green** — **31/31 passed** (39 combined with the 8 PDF cases); F3 closed at component level |
| 05 | `frontend/src/features/agent/AgentCatalogRail.{tsx,css,test.tsx}` | Transient selected-project preservation and focus | Edits landed; covered by the combined Evidence + Catalog run (102 passed). The speculative rail-retarget guards added during triage were reviewed and **removed** — see §4.1 |
| 06 | `frontend/src/features/agent/AgentMcpConnectionsPanel.{tsx,test.tsx}` | Stale async ownership state and failure re-read; **owned F1 and F2** (unexplained disabled controller actions; `title`-only release explanation) | **Green** — **26/26 passed**; F1/F2 closed, with the direct descriptions also asserted in the 8/8 browser run |
| 07 | `frontend/src/features/model-ensemble/ModelEnsembleOverlay.{tsx,test.tsx}` | Collapsed metric error surface | **25/25 passed** after a deterministic auto-collapse fixture and wait fix |
| 08 | `src/prompt_enhancer/application/updates/handoff_plan.py`, `tests/test_update_handoff_plan.py` | Exact package/owner-review binding for a **pure offline** handoff plan | Covered by the backend contracts run (114 passed) |
| 09 | `src/prompt_enhancer/application/updates/recovery_plan.py`, `tests/test_update_recovery_plan.py` | Exact operation/receipt binding for a **pure offline** recovery plan | Covered by the backend contracts run (114 passed) |
| 10 | `frontend/e2e/opus-convergence-accessibility.spec.ts`, `docs/opus-convergence-acceptance-review.md` | Eight browser acceptance cases (keyboard, short height, disabled explanation, owner-scope recovery) | **8/8 passed** in the latest revision, now including the F1/F2 direct-description assertions; F6 still unassigned |

### 3.1 Correction to an earlier statement about worker 02

If any earlier note in this batch described the onboarding drawer as a modality
defect, that reading was wrong. Settings overlap **is** prevented. The project
test failure was an **async rail reload**, not an inert modal.

## 4. Root-run evidence

Every number below is root's, from an executed run. Runs overlap: **do not add
them together** and do not read any of them as a suite-wide total.

### 4.1 Current evidence

Read the chronology column: the last bounded change in this batch was a narrow
`AgentPage` startup guard patch. Only the runs marked *after* it were executed on
the final code.

| Area | Run | Result | Chronology |
| --- | --- | --- | --- |
| Frontend | Full unit suite, **final frozen** run (`npm test -- --maxWorkers=4 --reporter=dot`) | **2861 passed across 192 files, 0 failed** (248.25 s) | **After** the startup guard patch — covers the final code |
| Build | Production build | Passed; the existing over-500 kB chunk warning remains | **After** the patch |
| Browser | Loopback against the **rebuilt** real production build | **16/16 passed** (22.8 s), cleanup confirmed: listener released, temp removed, models 0 | **After** the patch, on the rebuilt output — covers the final code |
| Typecheck | Isolated strict `tsc` for `opus-convergence-accessibility.spec.ts` **and** `sweep-01b-accessibility.spec.ts` | Both **passed** | Executed **before** the startup guard patch; both specs are unchanged since, so the result still holds |
| Browser | Standard Playwright project | **183 passed, 0 failed**, 6 intentional screenshot skips (4.1 m), after the PDF and contrast settlement fixes | **Before** the startup guard patch — *not* re-run after it |
| Browser | The 8 acceptance cases | **8/8 passed**, including the F1/F2 direct descriptions | Before the patch, supporting |
| Browser | PDF keyboard/zoom, repeated | **6/6 passed** | Before the patch, supporting |
| Browser | Intercepted HTTP contracts | **41/41 passed** | Earlier, supporting |
| Frontend components | PDF preview (worker 03) | **10/10 passed** | Earlier, supporting |
| Frontend components | Static dark-theme contrast (worker 01, new) | **3/3 passed** | Earlier, supporting |
| Repo checks | `check:api`, `privacy_scan` | Green | Root will re-check after these documentation edits |

The final unit run and the rebuilt loopback run are the two receipts that cover
the final code. The 183-case standard browser run is deliberately **not** labelled
as a post-patch run.

### 4.2 Trajectory of the earlier runs (consolidated)

These runs are history, not current state; they are kept only so the path is
auditable.

- Focused component receipts behind the worker table: Evidence + Catalog 102
  passed, AgentPage **171/171** (291.79 s), RuntimeControl **31/31**, MCP
  connections **26/26**, Overlay **25/25**, central RTL cleanup 6 passed.
- Backend: contracts 114 passed; contracts + privacy/harness 132 passed (an
  overlapping superset, **not additive** with the 114).
- The **initial** full frontend run (2843 passed, 7 failed of 2850) was **not
  frozen code** — four of those tests were being edited mid-flight. Each owning
  file passed on its own afterwards. Both this run and the later 2859/1 run in
  §4.3 are **superseded** by the final 2861/0 receipt.
- The **initial** broader browser run (180 passed, 3 failed, 6 skips) produced
  three triage items, all since resolved: MCP stale expected text (re-executed,
  8 passed); the PDF `tabIndex` measurement mismatch (repaired with both-axis
  before-paint measurement and true keyboard panning); and the dark-theme 768 px
  contrast reading of 3.68 on the `/` route (see §4.4).

### 4.3 The selected-project failure was a test defect, not a product rollback

An earlier frozen full frontend run, **superseded** by the final 2861/0 run in
§4.1, was **2859 passed, 1 failed of 2860 across 192 files**. That single failure
has been diagnosed and **was not a proven product rollback**:

- It was a **detached-DOM test click**. The test's query returned a project row
  that the reload had already removed, so **the click never fired** — nothing in
  the product reverted the selection.
- Three isolated runs reproduced the same detachment, so the diagnosis rests on
  repetition, not on a single sample.
- The corrected test now waits for the **actual project reload**, queries and
  clicks **synchronously**, and then **positively asserts the selected row**
  instead of inferring selection from absence.
- Both the original and the new deferred-startup tests passed in **all three
  parallel repeats** (2 cases each, 170 deselected). That is a focused receipt
  only: **no full-suite claim is made from it.**

The product change retained from this triage is deliberately narrow: **only the
late-startup landing abandonment after the user opens New chat**, plus the
pre-existing branch-feedback and settings fixes. The speculative
`selectedProjectIdRef` / `newChatProjectRef` state and the rail-retarget guards
introduced while chasing the failure were reviewed and **removed**, because the
evidence never supported them.

### 4.4 The contrast item: settlement fix, flash still unconfirmed

The contrast follow-up landed as a **deterministic browser settlement**: an
explicit settled flag plus a finite animation count, so the reading is taken at a
defined point instead of at an arbitrary frame. A new static test asserts the
palette itself (**3/3 passed**) and the static palette is good.

**No production CSS was changed.** Whether an actual transient flash ever occurs
in a real session remains **unconfirmed** and is recorded as future
investigation, not as a closed defect.

Not run and not claimed: native, packaging, installer, model, provider, real-MCP
and VRAM evidence; and a re-run of the standard browser project after the final
startup guard patch. No commit, push, application or PC restart, model load,
native install or external MCP transport occurred anywhere in this batch.

## 5. Closed this pass, and what is still pending

Closed on executed root receipts: the two AgentPage failures (171/171), the PDF
render/zoom work (component 10/10, browser 6/6), the MCP stale async ownership and
failure re-read (26/26), **F1 and F2** (association landed, asserted in the 8/8
browser run), **F3** at component level (31/31), the standard browser project
(183 passed, 0 failed, 6 intentional skips, pre-patch), the real built-loopback
project (16/16, rebuilt after the final patch, cleanup confirmed), the intercepted
contracts (41/41), the build, `check:api` and `privacy_scan`, the isolated strict
E2E typechecks of both accessibility specs, and the **final frozen full frontend
unit gate (2861 passed, 0 failed across 192 files, 248.25 s)**.

| Pending item | Owner | Evidence required to close |
| --- | --- | --- |
| Whether a real transient dark-theme flash exists | Future investigation, unassigned | A reproduction in a real session, or a documented reason none can occur |
| F6 — MOD-03 live placement refusal has no browser evidence | **Unassigned** | An independent fixture owner for `e2e/fixtures/workflow-panels.tsx`, then a browser case |
| F1-class follow-up: `Create direct connection` and `Prepare replacement` lack direct disabled descriptions | Queued, unassigned | Landed associations plus a root run asserting them |
| `AgentArtifacts` viewer-body stable-gutter polish | Queued, unassigned | Landed change plus a focused root receipt |
| Owner visual, native, model and packaging release gates | Unchanged | Untouched by this batch; see the finish goal board |

## 6. Explicit non-claims

This checkpoint advances no feature to complete and gates no release. **It is a
validated bounded ten-worker batch, not finished software**, and **C07 does not
advance**. The final unit gate is green on the final code, but a green unit suite
is not a finished product: the standard browser project has not been re-run after
the last startup guard patch; native, packaging, model, provider and real-MCP
evidence does not exist; whether a real transient dark-theme flash exists is
unconfirmed; and F6 plus the queued gaps have no owner. No percentage or
"everything passes" statement is supported by the evidence above. Worker-authored
assertions carry no weight until root executes them, and the passing 8/8
acceptance run proves only what those eight cases assert.

Owner visual, native, model and packaging release gates are **unchanged** by this
batch.

## 7. Next actions

**Root:** the final unit run and the spec typechecks are reported and recorded
above; re-check `check:api` and `privacy_scan` after these documentation edits.

**Queue for the next batch, unchanged (owners still to be assigned):** direct
disabled descriptions for `Create direct connection` and `Prepare replacement` (a
new F1-class gap); an independent owner for the F6 placement fixture gap;
`AgentArtifacts` viewer-body stable-gutter polish; and the owner visual, native,
model and packaging release gates. Each stays inside its owned file set and hands
back to root for the receipt.
