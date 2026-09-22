# Beta-readiness checkpoint 28

Status date: 2026-09-08

Status: **bounded implementation and automated validation complete; owner
review remains pending.**

## Scope and current truth

CP28 narrows the conversation-layout correction to the live Agent log. At
1440×420 and 1440×600, the first container-height cap could leave an 18px
log with no usable content area while the composer remained visible. The
revised CSS gives the live main an intrinsic minimum, gives the conversation
stage a 12rem minimum so the log cannot become zero-height, and sizes the
sticky finder from the live log. The retained-history fallback is unchanged.

The current catalog remains `metric-operability-v5`: 17 shipped conditional
paths, 0 task-profile gaps, and 3 provider/extractor or release-composition
gaps. The seventeenth path is scoped to a complete compatible Claude
transcript, confirmed plan, and native-reviewed links; it is not automatic
success proof. The guided reviewed-proposal UX remains missing, and no beta,
v1, provider, native, or release claim is made.

## Evidence boundary

The original pre-production RED was `04f224` (2 failures, 2 passes); the
cap-only attempt then failed 8/39 (`6fe730`), and geometry receipt `9a2160`
showed the 18px live log. Revised focused CSS coverage is 6/6 (`a5c0ab`),
owning unit coverage is 201/201 (`30023d`), transcript coverage is 3/3
(`4ab627`), related browser coverage is 16/16 (`d041c0`), and the build is
green (`3fb127`). The built disposable loopback is 27/27 (`c55080`, cleanup
true, zero model runtimes), strict E2E/bundle validation is green (`2e13d3`)
with caps unchanged, and expanded navigation is 42/42 with zero retries
(`d3ce66`), including four viewport regressions and native textarea resize.

No real model, native interaction, live database upgrade, application
restart, install, commit, or push is claimed. Synthetic fixtures and browser
validation do not establish provider or release readiness.

## Owner checks (maximum four)

1. Confirm the live log remains usable at 1440×420, 1440×600, 1440×720, and
   360px, including a vertically resized composer (`d3ce66`).
2. Confirm retained history keeps its original scroll/paging behavior and is
   not affected by the live-only container rule.
3. Confirm Find-next/previous, selected-message focus, Earlier/Later/Latest,
   and composer focus remain usable after layout reflow.
4. Keep the guided reviewed-proposal UX, native/provider proof, and beta/v1
   release decision visible as open owner gates.
