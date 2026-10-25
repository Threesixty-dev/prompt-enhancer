import copy
import json
from datetime import date
from uuid import uuid4

import pytest

from conftest import changed
from enhancement_bench.definitions import Overrides
from enhancement_bench.history import RunFilters, midnight
from test_api import client_for


def enqueue(store, publication, **overrides):
    return store.enqueue_ui(publication.definition.stableId, publication.definition.revision, Overrides(**overrides), str(uuid4()))


def test_history_names_selected_cases_without_rewriting_snapshots_or_exposing_content(store, publication, contracts):
    from enhancement_bench.store import Store

    subjects = [subject.model_dump() for subject in publication.definition.subjects]
    subjects.append({"id": "example-selected", "text": "EXAMPLE_PRIVATE_PROMPT",
                     "context": [{"role": "user", "content": "EXAMPLE_PRIVATE_CONTEXT"}]})
    definition = changed(publication, title="Example experiment - 2 cases x 2 variants", subjects=subjects, autoRun=False)
    store.import_publication(definition)
    run_id = enqueue(store, definition, subjectIds=["example-selected"], unitIds=["consumer"],
                     unitSteering={"consumer": {"instructions": "EXAMPLE_PRIVATE_STEERING"}})
    original = store.run(run_id)
    reopened = Store(store.path)
    with client_for(reopened, contracts) as client:
        row = client.get("/api/runs").json()["runs"][0]
        selected = row["configuration"]
        assert selected["subjectIds"] == ["example-selected"]
        assert selected["caseCount"] == 1
        assert [unit["id"] for unit in selected["units"]] == ["consumer"]
        assert "EXAMPLE_PRIVATE" not in json.dumps(row)
    assert reopened.run(run_id) == original
    assert original["effective"]["title"] == definition.definition.title
    assert len(original["attempts"]) == 1
    assert len(reopened.definitions()[0]["subjects"]) == 2


def test_filters_apply_before_pagination_and_summary_covers_all_matching_runs(store, publication, contracts):
    store.import_publication(changed(publication, autoRun=False))
    store.import_publication(changed(publication, stableId="example-other", autoRun=False))
    wanted = [enqueue(store, publication, unitIds=["script"]) for _ in range(105)]
    enqueue(store, changed(publication, stableId="example-other"))
    with store.transaction() as db:
        db.execute("UPDATE runs SET created=?,status='succeeded'", (midnight(date(2026, 10, 10)),))
    query = {"experiment": "example-widget", "revision": "1", "status": "succeeded", "origin": "ui",
             "fromDate": "2026-10-10", "toDate": "2026-10-10", "summary": "true", "limit": 10}
    with client_for(store, contracts) as client:
        page = client.get("/api/runs", params=query).json()
        summary = page["summary"]
        assert summary["total"] == summary["plannedAttempts"] == 105
        assert summary["activity"] == [{"day": "2026-10-10", "count": 105}]
        assert sum(row["count"] for row in summary["statuses"]) == 105
        assert next(row["count"] for row in summary["statuses"] if row["status"] == "succeeded") == 105
        seen = []
        while True:
            seen.extend(row["id"] for row in page["runs"])
            assert page["summary"] == summary
            if not page["nextCursor"]:
                break
            page = client.get("/api/runs", params=query | {"before": page["nextCursor"]}).json()
        assert len(seen) == 105 and set(seen) == set(wanted)
        assert client.get("/assets/history.js").status_code == 200


def test_utc_dates_include_whole_end_day_and_exclude_neighbors(store, publication):
    store.import_publication(changed(publication, autoRun=False))
    start = midnight(date(2026, 10, 10))
    ids = [enqueue(store, publication) for _ in range(4)]
    with store.transaction() as db:
        for run_id, created in zip(ids, [start - .01, start, start + 86399.99, start + 86400]):
            db.execute("UPDATE runs SET created=? WHERE id=?", (created, run_id))
    page = store.run_history(10, None, RunFilters(fromDate=date(2026, 10, 10), toDate=date(2026, 10, 10)))
    assert {run["id"] for run in page["runs"]} == set(ids[1:3])
    assert page["summary"]["activity"] == [{"day": "2026-10-10", "count": 2}]


def test_alias_filters_use_saved_overrides_and_evaluation_bindings(store, publication):
    evaluators = copy.deepcopy(publication.definition.evaluatorProfile)
    evaluators["evaluators"].append({"evaluator_id": "example-judge", "kind": "rubric", "binding_id": "example-judge-model"})
    store.import_publication(changed(publication, autoRun=False, evaluatorProfile=evaluators))
    selected = enqueue(store, publication, unitIds=["consumer"], unitConsumerBindings={"consumer": {"binding_id": "example-override"}})
    inherited = enqueue(store, publication, unitIds=["consumer"])
    scripted = enqueue(store, publication, unitIds=["script"])
    assert [r["id"] for r in store.runs(filters=RunFilters(model="example-override"))] == [selected]
    assert [r["id"] for r in store.runs(filters=RunFilters(model="example-consumer"))] == [inherited]
    assert {r["id"] for r in store.runs(filters=RunFilters(model="example-judge-model"))} == {selected, inherited, scripted}
    assert store.runs(filters=RunFilters(model="deterministic.v1")) == []
    page = store.run_history(10, None, RunFilters(status="failed"))
    assert page["summary"]["total"] == 0
    assert page["modelOptions"] == ["example-consumer", "example-judge-model", "example-override"]


@pytest.mark.parametrize("query", [
    {"status": "unknown"}, {"origin": "other"}, {"model": "example invalid"},
    {"experiment": "' OR 1=1"}, {"revision": "x" * 81}, {"fromDate": "2026-02-30"},
    {"fromDate": "2026-10-11", "toDate": "2026-10-10"},
])
def test_invalid_filters_are_safe_422s(store, contracts, query):
    with client_for(store, contracts) as client:
        response = client.get("/api/runs", params=query | {"summary": "true"})
        assert response.status_code == 422
        assert set(response.json()) == {"error"}


@pytest.mark.parametrize("filters,length", [
    (RunFilters(), 30), (RunFilters(toDate=date.min), 1),
    (RunFilters(fromDate=date.max), 1), (RunFilters(toDate=date.max), 30),
])
def test_empty_charts_and_extreme_dates_are_bounded(store, filters, length):
    summary = store.run_history(10, None, filters)["summary"]
    assert summary["total"] == summary["plannedAttempts"] == 0
    assert len(summary["activity"]) == length
    assert summary["activityFrom"] <= summary["activityTo"]
    assert all(day["count"] == 0 for day in summary["activity"])
    assert summary["comparisons"]["groups"] == []


def save_result(store, publication, result):
    run_id = enqueue(store, publication, unitIds=["script"])
    with store.transaction() as db:
        db.execute("UPDATE attempts SET result=?,status='succeeded' WHERE run_id=?", (json.dumps(result), run_id))
    return run_id


def test_comparisons_pair_numeric_results_preserve_zero_and_exclude_content(store, publication, result_template):
    store.import_publication(changed(publication, autoRun=False))
    first = copy.deepcopy(result_template)
    first["enhanced_prompt"] = "EXAMPLE_PRIVATE_PROMPT"
    first["effective_steering"]["instructions"] = "EXAMPLE_PRIVATE_INSTRUCTIONS"
    first["consumer_provenance"]["operation_id"] = "EXAMPLE_PRIVATE_OPERATION"
    first["consumer_provenance"]["extra"] = "EXAMPLE_PRIVATE_EXTRA"
    save_result(store, publication, first)
    second = copy.deepcopy(first)
    for side, value in [("before", .2), ("after", .4)]:
        second[side][0]["metrics"][0]["value"] = value
    second["deltas"][0]["value"] = .2
    save_result(store, publication, second)
    payload = store.run_history(10, None, RunFilters())
    groups = {g["metric"]: g for g in payload["summary"]["comparisons"]["groups"]}
    coverage = groups["prompt.task_definition_coverage"]
    assert coverage["count"] == 2
    assert coverage["before"] == pytest.approx((2 / 3 + .2) / 2)
    assert coverage["after"] == pytest.approx(.7)
    assert coverage["delta"] == pytest.approx((1 / 3 + .2) / 2)
    assert groups["prompt.acceptance_testability"]["after"] == 0
    assert groups["prompt.problem_evidence_quality"]["count"] == 0
    assert groups["prompt.problem_evidence_quality"]["before"] is None
    assert groups["prompt.problem_evidence_quality"]["excluded"] == 2
    assert "EXAMPLE_PRIVATE" not in json.dumps(payload)
    assert publication.definition.subjects[0].text not in json.dumps(payload)


@pytest.mark.parametrize("difference", ["metric_version", "rubric_version", "model_revision", "reported_model"])
def test_evaluator_versions_are_separate_and_mismatched_passes_are_excluded(store, publication, result_template, difference):
    store.import_publication(changed(publication, autoRun=False))
    save_result(store, publication, result_template)
    changed_result = copy.deepcopy(result_template)
    for side in ["before", "after"]:
        changed_result[side][0]["provenance"][difference] = "example-version-2"
    save_result(store, publication, changed_result)
    changed_result["after"][0]["provenance"][difference] = "example-version-3"
    save_result(store, publication, changed_result)
    groups = [g for g in store.run_history(10, None, RunFilters())["summary"]["comparisons"]["groups"] if g["metric"] == "prompt.task_definition_coverage"]
    assert len(groups) == 2
    assert len({g["scopeKey"] for g in groups}) == 2
    assert sum(g["count"] for g in groups) == 2
    assert sum(g["excluded"] for g in groups) == 1


def test_diagnostics_only_is_distinct_from_missing_model_metadata(store, publication, result_template):
    store.import_publication(changed(publication, autoRun=False))
    result = copy.deepcopy(result_template)
    result.update(strategy="prompt.check.v1", consumer_binding=None, consumer_provenance=None,
                  effective_workflow_steps={}, enhanced_prompt=None, after=[], deltas=[])
    result["workflow_result"] = {"review": {"state": "no_active_model", "notes": "EXAMPLE_PRIVATE_NOTE"}}
    save_result(store, publication, result)
    result["workflow_result"] = None
    save_result(store, publication, result)
    payload = store.run_history(10, None, RunFilters())
    groups = [g for g in payload["summary"]["comparisons"]["groups"] if g["metric"] == "prompt.task_definition_coverage"]
    assert len(groups) == 2
    assert {g.get("generationState") for g in groups} == {None, "no_active_model"}
    assert all(g["model"] is None and g["count"] == 0 and g["excluded"] == 1 for g in groups)
    assert "EXAMPLE_PRIVATE_NOTE" not in json.dumps(payload)


def test_comparison_group_limit_is_explicit_and_filters_scope_results(store, publication, result_template, monkeypatch):
    import enhancement_bench.comparisons as module

    monkeypatch.setattr(module, "MAX_GROUPS", 2)
    store.import_publication(changed(publication, autoRun=False))
    save_result(store, publication, result_template)
    summary = store.run_history(10, None, RunFilters())["summary"]["comparisons"]
    assert len(summary["groups"]) == 2
    assert summary["truncated"] and summary["groupLimit"] == 2
    assert store.run_history(10, None, RunFilters(status="failed"))["summary"]["comparisons"]["groups"] == []
