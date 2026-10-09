# ADR 0023: Develop integration and the owner work branch

- Status: records the owner's branch-flow instruction on 2026-10-09; exact
  implementation and validation are reviewed in the associated PR.
- Clarifies ADR 0019's original main-only routing; owner authority is unchanged.

## Decision

Task branches target `develop`; reviewed integration sets promote from `develop`
to `main`. The exact `dev_pm` branch is the requested owner working branch and
starts at the successfully integrated develop head. It does not publish releases
or bypass review. Contributors otherwise use task-named prefixed branches.

Preserve long-lived ancestry with merge commits for `dev_pm` → `develop` and
`develop` → `main`. Squash is available for disposable task branches; do not reuse
them afterward. Hotfixes may use a reviewed `fix/` PR into main and must then be
integrated into develop. There are no direct shared-branch feature pushes.

The metadata validator admits main/develop targets according to this routing,
and exact dev_pm only into develop. It still uses trusted base code, bounded
input parsing and fixed errors. It does not inspect author identity, infer owner
approval or establish platform permission enforcement.

The owner authorizes merges. An explicit instruction to execute one merge does
not delegate approval judgment or authorize later automatic merges. Required
platform checks/protection are never bypassed; unavailable CI is reported as
unexecuted, never green. Integration does not certify application or beta release.

## Alternatives and consequences

Main-only PRs were simpler, but did not provide the requested integration line.
Direct editing of shared develop would lose review boundaries. A long-lived
dev_pm can accumulate unrelated work, so keep each PR scoped and prefer separate
task branches when several changes are independent.

The preserved dirty development checkout is not automatically copied into a new
branch. Integrate reviewed, tested cohorts explicitly. Creating a branch does
not publish 747 pending files or recover features absent from its starting commit.

See [collaboration workflow](../collaboration-workflow.md) for commands, review
rules and the trusted-base policy bootstrap limitation.
