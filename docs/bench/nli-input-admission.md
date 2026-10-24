# NLI input admission

## Task card

- Task / atlas scope: bounded NLI input handling; MA18, W03, W05 and W07.
- Source baseline: develop `977cc641`, on a separate task branch.
- Reproduction: a valid Bench subject can exceed a pinned classifier's paired
  token limit. Sending it with truncation disabled can fail during evaluation.
- Change: count the complete premise/hypothesis pair locally before creating
  the gateway client. Use exact tokenizer revisions, verified bytes and pair
  special tokens. Core `0.3.3` and adapter `litellm-nli.v2` identify this candidate.
- Preserved contracts: full supported input, categorical labels, immutable
  experiment history, unknown values, and remote reconciliation requirements.
- Validation boundary: synthetic unit/integration/browser tests, public pinned
  tokenizer files, and an owned offline candidate container. These checks make
  no remote inference request and do not clear a production recovery hold.
- Owner decisions: source review, promotion, core publication and selection of
  the new artifact in a reviewed experiment revision remain separate gates.

## Runtime behavior

The guard counts both strings and the tokenizer's special tokens. It explicitly
disables serialized truncation and padding settings before counting. Exactly the
configured limit is accepted. Character counts are never used as token estimates.

| Outcome | Recorded behavior |
| --- | --- |
| Pair fits the manifest limit | Send the complete original pair through the existing typed NLI route. |
| Pair exceeds the limit | Record `nli.label` as `unknown`, reason `input_too_long`, with no label or number; make no NLI request. |
| Tokenizer missing, corrupt or mismatched | Fail definitively with `nli_tokenizer_unavailable` before any NLI request. |
| Input cannot be tokenized | Fail definitively with `nli_tokenization_failed` before any NLI request. |
| Unconfirmed remote operation | Retain the existing uncertainty and operator-reconciliation behavior. |

An oversized pair leaves an explicit unavailable measurement. Other evaluators
and the workflow can continue; numeric comparisons and dependent assertions keep
their existing unknown/exclusion behavior. A shorter generated candidate is
checked independently and can receive a valid NLI label. Completing this local
admission decision is not evidence that a classifier ran on the oversized input.

Bench displays **Unknown: input exceeds the evaluator token limit**. JSON/CSV
exports retain the reason, null values and ineligible-pair state. They do not
impute zero. The new adapter version prevents cross-version numeric comparisons.

## Installation and provenance

The default and models core images stage tokenizer JSON files during build into
`sys.prefix/share/prompt-enhancer/nli-tokenizers`. No tokenizer is added to the
source tree. Runtime inference reads these files locally and verifies SHA-256;
it does not discover a model cache, use account credentials or download files.
The tokenizer library is pinned to `tokenizers==0.22.2`.

| Manifest | Revision | License | Paired-token limit |
| --- | --- | --- | --- |
| `mdeberta_xnli` | `b5113eb38ab63efdd7f280f8c144ea8b13f978ce` | MIT | 512 |
| `deberta_small_long_nli` | `9a77395d4d3751be9e2a69c4ae318491d9b3fffb` | Apache-2.0 | 1680 |

The tokenizer SHA-256 values are code-owned in `enhancement/nli_tokenizer.py` and
covered by the core build fingerprint. The build downloads only `tokenizer.json`
from each public manifest repository at its exact revision, with TLS verification
and a size bound. Model weights and repository Python code are not downloaded.
The release probe verifies the installed files and performs local tokenization
inside its existing offline, read-only container before registration.

For a separate installed virtual environment with the `enhancement-tokenizers`
extra, staging is an explicit administrative action:

```sh
python -m prompt_enhancer.enhancement.nli_tokenizer --stage
```

Omitting `--stage` performs verification without downloading. Core images already
contain the staged files. An installation failure requires repair of that
environment; repeating an inference request cannot install its prerequisites.

## Qualification boundary

Local evidence on 2026-10-24 covers 509 affected unit/integration checks across
the regression run and final focused run, plus two desktop/mobile browser checks.
Tests cover exact limits, pair special tokens, Unicode, missing/corrupt assets,
no gateway call for oversized input, continued independent evaluators, retained
remote uncertainty, and JSON/CSV unknown/exclusion semantics.

The default core image builds with both verified tokenizer files. An owned
container with networking disabled, a read-only filesystem and no credentials
verifies both pins, accepts supported input and returns the oversized-input
unknown without constructing a gateway client. The probe container is removed.
This is packaged local evidence; it does not establish live classifier success.

Core `0.3.3` default completed owner-reviewed promotion and release verification
from main `52dff00e5057fa2c64810e5ee36a24afdad56c03` on 2026-10-24. The release
verified both tokenizer artifacts, offline runtime identity, cleanup and catalog
registration. The [robustness suite](robustness-experiment.md) prepares revision
2 against that exact digest; source review, publication and live qualification
of those definitions remain separate.
An existing v2 experiment keeps its original core pin. A new reviewed revision
must select the new artifact; its results form a separate qualification cohort.
Earlier successful attempts do not certify the changed artifact. The remote
operation from an interrupted run still requires stop evidence before clearing
its hold. This change does not make that attestation automatically.
