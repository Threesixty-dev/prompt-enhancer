"""Hand-computable analysis, missingness, provenance and private-file evidence."""

import copy
import csv
import hashlib
import json
import os

import httpx
from jsonschema import Draft202012Validator
import pytest

from enhancement_bench.analysis import analysis_schema, continuation_decision, dataset, inspect_run, project_run, validated_run, write_export
from enhancement_bench.errors import BenchError
from enhancement_bench.private_io import read_json, write_json
from test_client_worker import make_worker


@pytest.fixture
def completed(store, publication, contracts, result_template):
    assertion = {"evaluator_id": "prompt", "metric_key": "prompt.task_definition_coverage", "operator": "minimum_delta", "threshold": 0}
    for unit in publication.definition.units:
        unit.assertions = [assertion]
    result_template["assertions"] = [{"assertion": assertion, "outcome": "passed", "observed": 0.5}]
    result_template["assertion_outcome"] = "passed"
    result_template["timings"] = [{"stage": stage, "seconds": seconds} for stage, seconds in (
        ("evaluate_original", 0), ("generate", 0.25), ("evaluate_candidate", 0.125), ("compare", 0.01))]
    run_id = store.import_publication(publication)["runId"]
    worker, _, _ = make_worker(store, contracts, result_template)
    worker.step()
    return validated_run(store.run(run_id), contracts)


def metric_pair(run):
    result = run["attempts"][0]["result"]
    left, right = result["before"][0]["metrics"][0], result["after"][0]["metrics"][0]
    delta = next(d for d in result["deltas"] if d["metric_key"] == left["key"])
    left.update(state="known", value=0, label=None)
    right.update(state="known", value=0.5, label=None)
    delta.update(state="comparable", value=0.5, reason="same_evaluator")
    return result, left, right, delta


def invalid_review_run(run):
    run['attempts'] = run['attempts'][:1]
    run['effective']['subjects'] = run['effective']['subjects'][:1]
    run['effective']['units'] = run['effective']['units'][:1]
    run.update(status='failed', error_code='core_failed')
    attempt = run['attempts'][0]
    attempt['status'] = 'failed'
    result = attempt['result']
    result.update(status='failed', candidate=None, enhanced_prompt=None, after=[], deltas=[],
        consumer_provenance={'provider': 'inference', 'model': 'example-model'},
        errors=[{'code': 'workflow_review_reply_invalid', 'stage': 'generate', 'retryable': False}],
        workflow_result={'steps': [{'step_id': step, 'status': status, 'implementation': 'example-step.v1'} for step, status in
            [('diagnose', 'succeeded'), ('context', 'succeeded'), ('review', 'failed')]],
            'review': {'state': 'reply_invalid', 'validation_issue': {
                'reason': 'enum_mismatch', 'field': 'reformulated_elements[1].element'}}})
    return result


def test_invalid_review_diagnostic_matches_inspection_json_and_csv(completed, tmp_path):
    invalid_review_run(completed)
    report = inspect_run(completed)
    assert report['continuation'] == {'decision': 'continue_independent_case',
        'reason': 'completed_invalid_review', 'replayAllowed': False}
    assert report['attempts'][0]['errors'][0]['validationIssue'] == {
        'reason': 'enum_mismatch', 'field': 'reformulated_elements[1].element'}
    value = dataset([completed])
    assert value['schemaVersion'] == 'bench-analysis/v2'
    Draft202012Validator(analysis_schema()).validate(value)
    write_export(tmp_path / 'analysis', value)
    row = value['tables']['errors'][0]
    assert row['validation_reason'] == 'enum_mismatch'
    assert row['validation_field'] == 'reformulated_elements[1].element'
    with (tmp_path / 'analysis/errors.csv').open() as stream:
        exported = next(csv.DictReader(stream))
    assert exported['validation_reason'] == row['validation_reason']
    assert exported['validation_field'] == row['validation_field']


@pytest.mark.parametrize("category", ["connection", "access", "limit", "request", "service", "unknown"])
def test_consumer_failure_keeps_cause_and_hold_through_storage_and_export(
        store, publication, contracts, result_template, tmp_path, category):
    publication.definition.units = publication.definition.units[-1:]
    run_id = store.import_publication(publication)["runId"]
    worker, core, runtime = make_worker(store, contracts, result_template)
    handle = core.handle
    code = "consumer_upstream_" + category

    def failed_response(request):
        response = handle(request)
        if request.url.path.startswith("/v1/executions") and request.method != "DELETE":
            value = response.json()
            value["status"] = "uncertain"
            if request.url.path.endswith("/result"):
                value.update(candidate=None, enhanced_prompt=None, after=[], deltas=[],
                    assertions=[], assertion_outcome="not_evaluated",
                    errors=[{"code": code, "stage": "generate", "retryable": False}],
                    workflow_result=None)
            else:
                value.update(stage="finished", result_available=True)
            return httpx.Response(response.status_code, json=value)
        return response

    from enhancement_bench.client import CoreClient
    worker.client_factory = lambda endpoint, c: CoreClient(
        endpoint, c, transport=httpx.MockTransport(failed_response))
    assert worker.step()
    run = validated_run(store.run(run_id), contracts)
    assert run["status"] == "interrupted" and run["reconciliation_required"]
    assert not run["cleanup_pending"] and len(runtime.cleaned) == 1
    assert not worker.step() and len(core.requests) == 1
    report = inspect_run(run)
    assert report["continuation"] == {"decision": "stop", "reason": "recovery_required", "replayAllowed": False}
    assert report["attempts"][0]["errors"][0]["code"] == code
    value = dataset([run])
    Draft202012Validator(analysis_schema()).validate(value)
    row = value["tables"]["errors"][0]
    assert row["code"] == code and row["stage"] == "generate"
    assert row["validation_reason"] is row["validation_field"] is None
    write_export(tmp_path / "analysis", value)
    with (tmp_path / "analysis/errors.csv").open() as stream:
        exported = next(csv.DictReader(stream))
    assert exported["code"] == code and exported["stage"] == "generate"
    assert exported["validation_reason"] == exported["validation_field"] == ""


@pytest.mark.parametrize('defect', ['cleanup', 'reconciliation', 'timeout', 'running', 'missing_result',
    'missing_provenance', 'extra_error', 'evaluator_error', 'candidate', 'after', 'missing_before', 'contradiction', 'skipped'])
def test_independent_continuation_requires_complete_safe_evidence(completed, defect):
    result = invalid_review_run(completed)
    if defect in {'cleanup', 'reconciliation'}:
        completed[defect + ('_pending' if defect == 'cleanup' else '_required')] = 1
    elif defect == 'timeout': completed['error_code'] = 'run_deadline_exceeded'
    elif defect == 'running': completed['status'] = 'running'
    elif defect == 'missing_result': completed['attempts'][0]['result'] = None
    elif defect == 'missing_provenance': result['consumer_provenance'] = None
    elif defect == 'extra_error': result['errors'].append({'code': 'remote_execution_unconfirmed', 'stage': 'generate'})
    elif defect == 'evaluator_error': result['before'][0]['metrics'][0]['state'] = 'execution_error'
    elif defect == 'candidate': result['candidate'] = {'example': True}
    elif defect == 'after': result['after'] = copy.deepcopy(result['before'])
    elif defect == 'missing_before': result['before'] = []
    elif defect == 'contradiction': completed['status'] = 'succeeded'
    elif defect == 'skipped': completed['attempts'].append({'status': 'skipped', 'result': None})
    assert continuation_decision(completed)['decision'] == 'stop'


def test_historical_review_diagnostic_remains_unknown(completed):
    result = invalid_review_run(completed)
    del result['workflow_result']['review']['validation_issue']
    row = project_run(completed)['errors'][0]
    assert row['validation_reason'] is row['validation_field'] is None


def test_completed_success_allows_independent_cases_without_replay(completed):
    assert continuation_decision(completed) == {'decision': 'continue_independent_case',
        'reason': 'completed_successfully', 'replayAllowed': False}


@pytest.mark.parametrize('defect', ['missing_before', 'missing_after', 'missing_attempt', 'missing_hold',
    'malformed_result', 'malformed_metrics', 'contradictory_error'])
def test_incomplete_or_malformed_success_does_not_advise_continuation(completed, defect):
    result = completed['attempts'][0]['result']
    if defect == 'missing_before': result['before'] = []
    elif defect == 'missing_after': result['after'] = []
    elif defect == 'missing_attempt': completed['attempts'].pop()
    elif defect == 'missing_hold': del completed['cleanup_pending']
    elif defect == 'malformed_result': completed['attempts'][0]['result'] = ['example-invalid']
    elif defect == 'malformed_metrics': result['before'][0]['metrics'] = None
    elif defect == 'contradictory_error': completed['error_code'] = 'core_failed'
    assert continuation_decision(completed)['decision'] == 'stop'


def row_for(run):
    rows = project_run(run)["metrics"]
    return next(row for row in rows if row["attempt_id"] == run["attempts"][0]["id"]
                and row["metric_key"] == run["attempts"][0]["result"]["before"][0]["metrics"][0]["key"])


def test_numeric_zero_and_pair_delta_match_json_csv_and_schema(completed, tmp_path):
    metric_pair(completed)
    value = dataset([completed])
    Draft202012Validator(analysis_schema()).validate(value)
    manifest = write_export(tmp_path / "analysis", value)
    assert manifest["rowCounts"] == {"runs": 1, "attempts": 2, "metrics": 12, "assertions": 2, "timings": 8, "errors": 0}
    row = row_for(completed)
    assert row["before_value"] == 0 and row["after_value"] == 0.5 and row["delta_value"] == 0.5
    assert row["pair_eligible"] and row["exclusion_reason"] is None
    with (tmp_path / "analysis" / "metrics.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    exported = next(item for item in rows if item["attempt_id"] == row["attempt_id"] and item["metric_key"] == row["metric_key"])
    assert float(exported["before_value"]) == 0 and float(exported["delta_value"]) == 0.5
    assert exported["before_label"] == "" and exported["pair_eligible"] == "true"
    assert read_json(tmp_path / "analysis" / "analysis.json", limit=1_000_000) == value
    for name, info in manifest["files"].items():
        contents = (tmp_path / "analysis" / name).read_bytes()
        assert info == {"bytes": len(contents), "sha256": hashlib.sha256(contents).hexdigest()}


@pytest.mark.parametrize("state", ["unknown", "abstained", "not_applicable", "execution_error"])
def test_unavailable_readings_remain_distinct_and_never_become_zero(completed, state):
    _, left, _, delta = metric_pair(completed)
    left.update(state=state, value=None, label=None, reason="example-unavailable")
    delta.update(state="unknown", value=None, reason="metric_unknown")
    row = row_for(completed)
    assert row["before_state"] == state and row["before_reason"] == "example-unavailable"
    assert row["before_value"] is None and row["delta_value"] is None and not row["pair_eligible"]
    assert row["exclusion_reason"] == ("attempt_not_successful" if state == "execution_error" else "reading_unavailable")


def test_missing_after_evaluator_and_unexecuted_attempt_are_explicit(completed):
    result, _, _, _ = metric_pair(completed)
    result.update(after=[], deltas=[], candidate=None, enhanced_prompt=None)
    completed["attempts"][1].update(status="skipped", result=None, request=None)
    completed["status"] = "failed"
    tables = project_run(completed)
    row = row_for(completed)
    assert row["after_state"] == "missing" and row["after_value"] is None and row["delta_state"] == "missing"
    assert tables["attempts"][0]["missing_after_evaluators"] == ["prompt"]
    absent = tables["attempts"][1]
    assert not absent["result_recorded"] and absent["technical_outcome"] == "incomplete"
    assert absent["generation_provenance"] is None
    check = next(item for item in tables["assertions"] if item["attempt_id"] == absent["attempt_id"])
    assert check["outcome"] == "not_evaluated" and check["observed"] is None and not check["recorded"]


def test_input_limit_reason_survives_json_and_csv_without_numeric_imputation(completed, tmp_path):
    _, left, _, delta = metric_pair(completed)
    left.update(state="unknown", value=None, label=None, reason="input_too_long")
    delta.update(state="unknown", value=None, reason="metric_unknown")
    row = row_for(completed)
    assert row["before_reason"] == "input_too_long" and not row["pair_eligible"]
    assert row["exclusion_reason"] == "reading_unavailable"
    value = dataset([completed])
    write_export(tmp_path / "analysis", value)
    with (tmp_path / "analysis" / "metrics.csv").open() as stream:
        exported = next(item for item in csv.DictReader(stream)
            if item["attempt_id"] == row["attempt_id"] and item["metric_key"] == row["metric_key"])
    assert exported["before_reason"] == "input_too_long"
    assert exported["before_value"] == exported["before_label"] == exported["delta_value"] == ""
    assert read_json(tmp_path / "analysis" / "analysis.json", limit=1_000_000) == value


def test_categorical_labels_are_preserved_without_numeric_delta(completed):
    _, left, right, delta = metric_pair(completed)
    left.update(value=None, label="neutral")
    right.update(value=None, label="entailment")
    delta.update(state="not_comparable", value=None, reason="categorical_metric")
    row = row_for(completed)
    assert (row["before_label"], row["after_label"]) == ("neutral", "entailment")
    assert row["delta_value"] is None and row["exclusion_reason"] == "categorical_metric" and not row["pair_eligible"]


@pytest.mark.parametrize("cause", ["provenance", "delta", "cleanup", "review"])
def test_invalid_pairs_are_excluded_with_specific_reason(completed, cause):
    result, _, _, delta = metric_pair(completed)
    expected = {"provenance": "provenance_mismatch", "delta": "delta_mismatch", "cleanup": "run_unsettled", "review": "attempt_not_successful"}
    if cause == "provenance":
        result["after"][0]["provenance"]["model_revision"] = "example-new-revision"
    elif cause == "delta":
        delta["value"] = 0.9
    elif cause == "cleanup":
        completed["cleanup_pending"] = 1
    else:
        result["workflow_result"] = {"steps": [{"step_id": "review", "implementation": "example-review.v1", "status": "failed"}], "review": {"state": "reply_invalid"}}
        report = inspect_run(completed)
        assert report["status"] == "succeeded" and report["technicalOutcomes"]["failed"] == 1
    row = row_for(completed)
    assert not row["pair_eligible"] and row["exclusion_reason"] == expected[cause]


def test_comparison_scope_separates_versions_but_retains_variant_identity(completed):
    original = row_for(completed)
    changed = copy.deepcopy(completed)
    changed["revision"] = "2"
    assert row_for(changed)["comparison_scope"] != original["comparison_scope"]
    changed = copy.deepcopy(completed)
    changed["image"] = "registry.example.com/example/core@sha256:" + "f" * 64
    assert row_for(changed)["comparison_scope"] != original["comparison_scope"]
    attempts = project_run(completed)["attempts"]
    assert attempts[0]["unit_id"] != attempts[1]["unit_id"]


def test_export_records_order_step_provenance_and_generation_versions(completed):
    result = completed["attempts"][0]["result"]
    provenance = copy.deepcopy(result["before"][0]["provenance"])
    result["workflow_result"] = {"steps": [
        {"step_id": key, "implementation": "example-step.v1", "status": "succeeded", "provenance": provenance}
        for key in ("score", "context", "review")]}
    result.update(generation_context_version="example-context.v1", generation_prompt_version="example-prompt.v2")
    row = project_run(completed)["attempts"][0]
    assert row["workflow_step_order"] == ["score", "context", "review"]
    assert row["workflow_steps"]["review"]["provenance"]["metric_version"] == provenance["metric_version"]
    assert row["generation_context_version"] == "example-context.v1"
    assert row["generation_prompt_version"] == "example-prompt.v2"
    assert [step["stepId"] for step in inspect_run(completed)["attempts"][0]["workflowSteps"]] == row["workflow_step_order"]
    result["workflow_result"]["steps"].append(result["workflow_result"]["steps"][0])
    with pytest.raises(BenchError, match="analysis_duplicate_step"):
        project_run(completed)


def test_configuration_fingerprints_distinguish_overrides_without_exporting_text(completed):
    before = project_run(completed)
    completed["effective"]["units"][0]["objective"]["description"] = "An independent fictional objective."
    completed["effective"]["units"][0]["steering"]["instructions"] = "Independent fictional steering."
    completed["effective"]["subjects"][0]["context"] = [{"kind": "note", "text": "Independent fictional context."}]
    after = project_run(completed)
    assert before["runs"][0]["effective_settings_sha256"] != after["runs"][0]["effective_settings_sha256"]
    for field in ("objective_sha256", "steering_sha256", "context_sha256"):
        assert before["attempts"][0][field] != after["attempts"][0][field]
    assert "Independent fictional" not in json.dumps(after)


def test_duplicate_runs_metrics_and_impossible_states_are_rejected(completed):
    with pytest.raises(BenchError, match="duplicate_run"):
        dataset([completed, completed])
    changed = copy.deepcopy(completed)
    metrics = changed["attempts"][0]["result"]["before"][0]["metrics"]
    metrics.append(copy.deepcopy(metrics[0]))
    with pytest.raises(BenchError, match="analysis_duplicate_metric"):
        dataset([changed])
    _, left, _, _ = metric_pair(completed)
    left.update(state="unknown", value=0)
    with pytest.raises(BenchError, match="analysis_metric_invalid"):
        dataset([completed])


def test_tampered_correlation_and_input_are_rejected_before_export(completed, contracts):
    changed = copy.deepcopy(completed)
    changed["attempts"][0]["result"]["correlation_id"] = "example-other"
    with pytest.raises(BenchError, match="core_correlation_mismatch"):
        validated_run(changed, contracts)
    changed = copy.deepcopy(completed)
    changed["effective"]["subjects"][0]["text"] = "An independently authored fictional changed input."
    with pytest.raises(BenchError, match="run_request_mismatch"):
        validated_run(changed, contracts)


def test_export_omits_text_targets_policies_and_provider_content(completed, tmp_path):
    canary = "example-private-content-canary"
    completed["effective"]["subjects"][0]["text"] = canary
    completed["effective"]["evaluatorProfile"]["evaluators"][0]["target"] = canary
    result = completed["attempts"][0]["result"]
    result["enhanced_prompt"] = canary
    result["workflow_result"] = {"review": {"state": "ok", "notes": canary, "findings": [canary]}, "steps": [
        {"step_id": "review", "implementation": "example-review.v1", "status": "succeeded",
         "policy": {"policy_id": "example-policy", "revision": "1", "instructions": canary},
         "generation": {"temperature": None, "max_tokens": None}}]}
    manifest = write_export(tmp_path / "analysis", dataset([completed]))
    assert not manifest["containsPromptText"]
    for path in (tmp_path / "analysis").iterdir():
        assert canary not in path.read_text()
    data = read_json(tmp_path / "analysis" / "analysis.json")
    steps = data["tables"]["attempts"][0]["workflow_steps"]
    assert steps["review"]["policy"]["instructions_sha256"] == hashlib.sha256(canary.encode()).hexdigest()
    assert steps["review"]["generation"]["temperature"] is None


def test_artifacts_are_private_and_existing_files_are_never_replaced(completed, tmp_path):
    output = tmp_path / "analysis"
    write_export(output, dataset([completed]))
    before = (output / "manifest.json").read_bytes()
    with pytest.raises(BenchError, match="output_exists"):
        write_export(output, dataset([completed]))
    assert (output / "manifest.json").read_bytes() == before
    if os.name != "nt":
        assert output.stat().st_mode & 0o777 == 0o700
        assert all(path.stat().st_mode & 0o777 == 0o600 for path in output.iterdir())


def test_linked_receipt_and_linked_export_parent_are_refused(completed, tmp_path):
    target = tmp_path / "original.json"
    write_json(target, {"example": "private"})
    link = tmp_path / "receipt.json"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation unavailable on this platform")
    with pytest.raises(BenchError, match="file_link_forbidden"):
        read_json(link)
    directory = tmp_path / "linked"
    directory.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(BenchError, match="file_link_forbidden"):
        write_export(directory / "analysis", dataset([completed]))
    assert read_json(target) == {"example": "private"}


def test_partial_export_is_removed_without_a_completion_manifest(completed, tmp_path, monkeypatch):
    import enhancement_bench.analysis as module
    original = module.write_new
    def fail(path, data):
        if path.name == "metrics.csv":
            raise BenchError("file_write_failed")
        original(path, data)
    monkeypatch.setattr(module, "write_new", fail)
    with pytest.raises(BenchError, match="file_write_failed"):
        write_export(tmp_path / "analysis", dataset([completed]))
    assert not (tmp_path / "analysis").exists()


def test_export_limits_fail_before_publishing_manifest(completed, tmp_path, monkeypatch):
    import enhancement_bench.analysis as module
    value = dataset([completed])
    monkeypatch.setattr(module, "MAX_EXPORT_ROWS", 1)
    with pytest.raises(BenchError, match="export_too_large"):
        dataset([completed])
    monkeypatch.setattr(module, "MAX_EXPORT_BYTES", 1)
    with pytest.raises(BenchError, match="export_too_large"):
        write_export(tmp_path / "analysis", value)
    assert not (tmp_path / "analysis").exists()
