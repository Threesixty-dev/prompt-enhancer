# Claude Code instructions

This repository analyzes highly sensitive coding-agent data. Load the shared
repository requirements and development skill for every task:

@AGENTS.md
@.agents/skills/prompt-enhancer-development/SKILL.md

The required-reading table in `AGENTS.md` also applies to Claude Code. For Bench
or Experiment work, read `docs/bench/README.md` and the applicable tracked skill
before implementation or validation. Open the skill files directly if a skill
invocation tool is unavailable; no personal skill installation is required.
Keep the existing-core/new-core decision explicit and use the separate core
release skill when a new version is needed.

Follow the imported requirements and these privacy rules for every task:

- Never read or commit real files from `~/.claude`, `~/.codex`, provider credentials, private repositories, or local transcript/database paths unless the user explicitly authorizes a narrowly scoped read-only diagnostic. Even then, never reproduce sensitive contents.
- Use synthetic examples only. Replace identities, hostnames, project names, paths, account IDs, remotes, and tokens with obvious reserved examples.
- Keep all ingestion read-only and prefer official SDK, app-server, hook, or OpenTelemetry surfaces. Isolate unstable transcript parsers behind version checks.
- No transcript text may leave the machine without explicit per-run consent, redaction, and a destination preview.
- Do not add employee rankings or a single prompt/developer quality score. Keep outcome evidence and uncertain model judgments visibly separate.
- Before any commit, inspect staged content and verify that Git uses a public/noreply email.
