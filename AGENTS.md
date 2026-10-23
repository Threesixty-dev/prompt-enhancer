# Repository instructions for coding agents

This is a privacy-sensitive repository for local coding-agent analytics.

## Required skills and Bench instructions

These requirements apply to both Codex and Claude Code. Resolve every path from
the selected repository root and use the tracked skills in `.agents/skills/`.
Personal installed copies may be older. When a matching skill is available by
name, still read the tracked version for this checkout's current contract.

1. Before substantive repository work, read and apply
   `.agents/skills/prompt-enhancer-development/SKILL.md` in full.
2. For Test Bench or Experiment work, also read `docs/bench/README.md` before
   designing changes, editing definitions or running validation. This includes
   Bench UI/API, runs, comparison design, publication and core integration.
3. Load the additional skill and instructions for each applicable task below.
   Read its referenced authoring/validation guidance when performing those steps.

| Task | Required additional reading |
| --- | --- |
| Prepare, revise, validate or publish an Experiment; design cases, variants or model comparisons | `.agents/skills/prepare-bench-experiment/SKILL.md` |
| Run, observe, inspect, cancel or export an existing Experiment; interpret its results | `.agents/skills/operate-bench-experiment/SKILL.md`, `docs/bench/client.md` and `docs/bench/handoff.md` |
| Prepare or publish a new core version for Bench | `.agents/skills/deploy-enhancement-core/SKILL.md` and `docs/bench/core-publication.md` |
| Deploy or operate Bench services | `docs/bench/deployment.md`; for API/UI deployment, also `docs/bench/continuous-deployment.md` |

Reading a skill's name or description is insufficient. If a skill invocation
tool is unavailable, open its `SKILL.md` directly and follow it. Briefly identify
the skills and Bench instructions loaded before implementation. If a required
file is missing, report the missing path and resolve the checkout prerequisite
before proceeding with dependent work.

For Experiment preparation, establish whether to reuse an existing released core
or prepare a new version separately. Ask once if that choice is unresolved;
respect an answer already given. Core publication is optional and separate from
Experiment publication and Bench service deployment. Loading these instructions
does not authorize a release or model run.

## Non-negotiable privacy rules

- Never copy, stage, commit, print, summarize, or upload real Codex or Claude sessions, prompts, tool output, source snippets, account data, or local configuration.
- Never read provider credential files such as Codex `auth.json`, Claude `.claude.json`, keychains, environment files, or unrelated home-directory content.
- Use only synthetic fixtures with fictional identities, repositories, paths, tokens, and conversations.
- Do not include usernames, personal email addresses, hostnames, account IDs, absolute home paths, private remotes, or screenshots in code, tests, logs, issues, or documentation.
- Do not send transcript content to a network service or remote model without an explicit task-specific user instruction and a redaction preview.
- Treat embeddings, summaries, labels, and aggregate metrics as sensitive derived data; pseudonymized is not anonymous.
- Bind local services to loopback by default. Do not add remote listening, unrestricted SQL, or raw-transcript MCP tools.

## Implementation rules

- Prefer documented provider interfaces. Raw JSONL and internal SQLite parsing must be isolated, version-gated compatibility adapters.
- Ingestion adapters are read-only. They must not delete, archive, resume, rename, or mutate provider sessions.
- Missing values remain unknown. Never silently convert missing token usage, duration, cost, or task outcome to zero or failure.
- Record provenance and versions for provider, adapter, metric definition, redactor, model, tokenizer, prompt/rubric, and schema.
- Objective verification evidence outranks inferred text scores. Never treat an assistant's completion claim as proof of task success.
- Keep prompt, outcome, efficiency, affect, and safety dimensions separate. Do not create a developer ranking or universal “intelligence” score.
- Pin model revisions and licenses; do not vendor model weights. Keep `trust_remote_code` disabled and prefer safetensors or ONNX.
- New fixtures must pass secret/PII canary tests and contain only reserved example values.

## Collaboration and architecture

- Work on feature branches and propose changes through pull requests.
- Task PRs target `develop`; accepted integration sets promote from `develop`
  to `main`. Exact `dev_pm` is the owner-requested work branch, not merge authority.
- The repository owner is the final reviewer and merge authority. Contributors
  and agents never autonomously self-merge or force-push shared branches. A direct
  owner instruction can authorize execution of one specific merge, not bypass
  protections or approve unrelated/future changes.
- Agents and contributors never publish source or releases automatically.
- Any collaborator may propose an architecture change; accepted decisions change
  only after owner review and acceptance. Record a superseding ADR instead of
  silently reversing the existing one.
- Read `docs/architecture/README.md` and the relevant component catalog entries
  before cross-component work. Check the approved baseline: unpublished local
  implementation may be absent from `main`.
- Use `.agents/skills/prompt-enhancer-development/SKILL.md` for component routing,
  evidence gates and contribution flow.
- Written policy and CI metadata checks are not GitHub permission enforcement.
  Do not claim branch protection or release authority from these instructions.

## Before committing

- Inspect `git diff --cached` and `git status --short`.
- Confirm the commit email is a public/noreply identity.
- Run the repository's tests and privacy/secret scanner once those commands exist.
- Do not bypass a safety test to make CI pass.
