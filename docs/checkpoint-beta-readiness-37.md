# Beta readiness checkpoint 37 — frontend baseline and truthful metric copy

Status: IN PROGRESS. This checkpoint records the initial terminal frontend
baseline and narrow metric/scanner corrections. It does not claim beta, release,
native, owner, provider, model, or whole-product completion.

## Scope

The initial full frontend run covered 240 files and ended with **3,426 passed
and 2 failed** (`36ab9b`). Those two failures were the stale metric-copy and
statically-disabled scanner-correction slices; their focused corrections are
green, but this checkpoint does not relabel the original run as green.

The quality-profile preview correction updates stale 16/4 copy and expectations
to canonical **20 checks / 17 supported measurement paths / 3 provider-adapter
gaps**. The dialog derives the explanatory gap count from the canonical gap list.
Its focused synthetic suite passed **21/21**.

Terra corrected a statically-disabled Cancel-control scanner false positive:
the control intentionally has no `onclick` when its job identity mismatches,
and retains a literal disabled reason. This is a scanner interpretation fix,
not evidence of a newly available runtime capability, and it does not weaken
the privacy scanner.

Subsequent focused evidence is split: four focused frontend files passed
**54/54** (`aa1443`), the production build passed (`03ff50`) with port 8765
absent, and the bundle-budget check passed (`305616`) with the existing Vite
greater-than-500k warning. The dedicated runtime-recovery browser matrix passed
**8/8** in 16.3 seconds at 320px and 1440px, covering pending and hung reads;
the independent root rerun also passed **8/8** in 12.5 seconds (`6449bd`). The
corresponding diff check passed (`666251`).
The later full frontend rerun passed **3,429/3,429 across 240 files**
(`9fefea`).

## Current limits

Privacy remains OPEN/RED: the latest scan (`fae1af`) still reports two known
synthetic `.tmp-cp34-privacy` databases. Native and owner walkthroughs, provider/model execution,
packaged restart, release, beta, and v1 acceptance remain unverified. No real
provider data, credentials, models, network service, native execution, restart,
or durable source text is part of this checkpoint.

The [checkpoint 36 handoff](checkpoint-beta-readiness-36.md) points to this
initial terminal frontend result. Focused/build receipts are recorded
separately and must not be merged into the 3,426/2 baseline.
