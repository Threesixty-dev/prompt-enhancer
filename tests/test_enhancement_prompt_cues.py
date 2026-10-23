"""Synthetic regression cases for explicit coding deliverables and constraints."""
import asyncio
import json
from pathlib import Path

import pytest

from prompt_enhancer.enhancement.contracts import Evaluator, Subject
from prompt_enhancer.enhancement.engine import compare
from prompt_enhancer.enhancement.evaluators import DeterministicEvaluation


def evaluate(text, *, version="v2", context=()):
    return asyncio.run(DeterministicEvaluation(version=version).evaluate(
        Subject(text=text, context=context),
        Evaluator(evaluator_id="example", kind="deterministic", binding_id=f"deterministic.{version}"),
    ))


def metric(text, key, *, version="v2"):
    return next(m for m in evaluate(text, version=version).metrics if m.key == "prompt." + key)


@pytest.mark.parametrize("text", [
    "Return a patch and tests for the fictional parser.",
    "Provide a diff and unit tests for the fictional parser.",
    "Add unit tests for the fictional parser.",
    "Deliverables: a patch and unit tests for the fictional parser.",
])
def test_requested_code_artifacts_are_known_detailed_deliverables(text):
    value = metric(text, "deliverable_contract")
    assert value.state == "known" and value.value == 1


@pytest.mark.parametrize("text", [
    "Run tests to verify the fictional parser.",
    "The fictional parser already has tests.",
    "Do not return a patch for the fictional parser.",
    "Would you provide a patch for the fictional parser?",
])
def test_verification_mentions_and_negated_requests_do_not_create_deliverables(text):
    value = metric(text, "deliverable_contract")
    assert value.state == "unknown" and value.value is None


@pytest.mark.parametrize("text", [
    "Do not add dependencies to the fictional parser.",
    "Don't change pagination in the fictional filter.",
    "Never mutate items in the fictional filter because callers reuse them.",
    "Must not send data over a network from the fictional parser.",
])
def test_explicit_prohibitions_are_known_precise_constraints(text):
    value = metric(text, "constraint_precision")
    assert value.state == "known" and value.value == 1


def test_missing_constraints_and_vague_prohibitions_do_not_become_perfect_scores():
    missing = metric("Improve the fictional parser.", "constraint_precision")
    assert missing.state == "unknown" and missing.value is None
    vague = metric("Do not change something in the fictional parser.", "constraint_precision")
    assert vague.state == "known" and vague.value == 0


def test_language_guard_is_preserved_for_unclassified_short_input():
    result = metric("Never mutate items in the fictional filter.", "constraint_precision")
    assert result.state == "abstained" and result.reason == "unsupported_language"
    assert result.value is None


def test_version_one_is_unchanged_and_cross_version_deltas_are_rejected():
    text = "Add a parser for fictional widget records. Return a patch and tests. Do not add dependencies."
    old, new = evaluate(text, version="v1"), evaluate(text)
    old_metrics = {m.key: m for m in old.metrics}
    new_metrics = {m.key: m for m in new.metrics}
    for key in ["prompt.deliverable_contract", "prompt.constraint_precision"]:
        assert old_metrics[key].state == "unknown"
        assert new_metrics[key].state == "known"
    for key in set(old_metrics) - {"prompt.deliverable_contract", "prompt.constraint_precision"}:
        assert old_metrics[key] == new_metrics[key]
    assert old.provenance.adapter_version == "prompt-evaluation.v1"
    assert new.provenance.adapter_version == "prompt-evaluation.v2"
    assert new.provenance.metric_version == "prompt-cues-en-pl-1"
    assert all(d.state == "not_comparable" and d.reason == "provenance_mismatch"
               and d.value is None for d in compare((old,), (new,)))


def test_reviewed_synthetic_inputs_have_observable_deliverables():
    root = Path(__file__).resolve().parents[1]
    definition = json.loads((root / "experiments/example-prompt-check-policies-20261022-r3.json").read_text())
    for subject in definition["subjects"]:
        readings = {m.key: m for m in evaluate(subject["text"]).metrics}
        assert readings["prompt.deliverable_contract"].state == "known", subject["id"]
        constraints = readings["prompt.constraint_precision"]
        assert constraints.state == ("unknown" if subject["id"].endswith("sparse") else "known")
        assert readings["prompt.problem_evidence_quality"].state == "unknown"


def test_assistant_context_cannot_supply_requested_artifacts():
    result = evaluate("Improve the fictional parser.", context=(
        {"role": "assistant", "content": "Return a patch and tests. Do not add dependencies."},
    ))
    metrics = {m.key: m for m in result.metrics}
    assert metrics["prompt.deliverable_contract"].state == "unknown"
    assert metrics["prompt.constraint_precision"].state == "unknown"
