# Experiment publication task

Date: 2026-10-13. Status: local verification complete; live publication blocked
on approval of GitHub deployment access.

## Task card

- Task: repair JSON-only Experiment publication and established domain language.
  Related atlas nodes: W02, W05, W06, W07 and WP08. This bounded Test Bench flow
  does not satisfy the general workflow or release gates.
- Baseline: `5d2228d`, the later core/Test Bench integration branch. The source
  depends on that integration; the older `develop` and `main` are not equivalent.
- User outcome: add an Experiment JSON in `experiments/`, push, and observe its
  automatic Run and results in Test Bench.
- Reproduction: the publication workflow required manual dispatch, definitions
  lived under a development fixture directory, delivery omitted Origin, and all
  Experiments were forced to use the checkout's core version.
- Scope: publication workflow/helper, delivery client, domain aliases, UI copy,
  synthetic fixtures/tests and documentation. Preserve the v1 wire schema and
  immutable publication identities, the independent Evaluator and core pipeline.
- Change: push-triggered delivery on the selected branch, retained artifact or
  registry resolution per version, newest-first import, Origin and optional
  access headers, and Experiment Unit terminology.
- Verification: synthetic API/worker delivery, duplicate suppression, version
  retention, conflicting revision rejection, invalid-origin/redirect rejection,
  privacy scanning and desktop/mobile browser checks. Hosted delivery remains
  separate evidence until a JSON-only push creates an automatic Run.
- Resource bound: one serial publication job and the existing serial Test Bench
  worker. Acceptance uses two fictional Subjects and two scripted Experiment
  Units with one shared deterministic Evaluator, without model inference.
- Assertions: each result requires a nonnegative acceptance-testability delta.
  This is a deterministic regression check, not a semantic quality claim.
- Owner authority: review and merge remain with the repository owner. Deployment
  credentials, core artifact availability and publication-branch configuration
  are external prerequisites, not permissions implied by workflow metadata.

## Evidence

The authored acceptance Experiment is
`experiments/example-clarification-focus.json`, revision `1`, generation `1`,
requesting core `0.1.4`. General clarification and acceptance-focused clarification
are Experiment Units; their strategies remain the packaged `script.clarify.v1`.
Runtime checks must report core `0.1.4` before that retained image is registered.
Stale OCI labels are not accepted as source-build provenance.

The October 8 atlas observation remains unchanged. This task updates the bounded
integration evidence, not its historical hashes or general readiness colors.

Local checks: 103 Test Bench tests, six desktop/mobile browser cases, JavaScript
syntax, Experiment schema validation and the repository privacy scan pass.
The deployed retained core reports runtime version `0.1.4` and variant `default`;
its stale `0.1.2` OCI version/build labels are not used to claim build provenance.

The deployment-access configuration was rejected by automatic approval review:
authorizing the feature branch in the GitHub environment needs explicit owner
approval. No live import, automatic Run, registry publication or deployment is
claimed by these local checks. The acceptance criterion remains a JSON-only push
followed by an observed automatic Run; a manual import is not equivalent evidence.
