from __future__ import annotations

import json

from scripts.export_openapi import build_openapi_schema, export_openapi


def test_build_time_schema_contains_bounded_queries_and_review_commands() -> None:
    schema = build_openapi_schema()
    paths = schema["paths"]

    assert "/v1/discovery/candidates" in paths
    assert "/v1/tasks/{task_id}/revisions/{revision}" in paths
    assert "/v1/analysis/runs/{run_id}" in paths
    assert "/v1/task-decisions/accept" in paths
    assert "/v1/task-decisions/reject" in paths
    assert "/v1/task-decisions/merge" in paths
    assert "/v1/task-decisions/split" in paths
    assert (
        "/v1/tasks/{task_id}/revisions/{revision}/analysis-runs" in paths
    )
    assert "/v1/sql" not in paths
    assert "/v1/local-sources/codex" in paths
    assert "/v1/local-sources/codex/consents/local-history" in paths
    assert "/v1/local-sources/codex/index" in paths
    assert "/v1/local-sources/codex/analysis" in paths
    assert "/v1/local-sources/codex/display-labels/enrich" in paths
    assert "/v1/catalog/projects/{project_id}/display-label" in paths
    assert "/v1/catalog/sessions/{session_id}/display-label" in paths
    assert "/v1/research/text-analysis-methods" in paths
    assert "/v1/providers/{provider}/capabilities" in paths
    assert "/v1/sessions/{session_id}/metric-readiness" in paths
    assert "/v1/analysis-jobs" in paths
    assert "/v1/analysis-jobs/{job_id}" in paths
    assert "/v1/analysis-jobs/{job_id}/cancellation" in paths
    assert "/v1/sessions/{session_id}/analysis-jobs/latest" in paths
    assert set(paths["/v1/estimators/plans"]) == {"get"}
    assert set(paths["/v1/control-plane/readiness"]) == {"get"}
    assert {
        path for path in paths if path.startswith("/v1/control-plane/")
    } == {"/v1/control-plane/readiness"}

    readiness = paths["/v1/control-plane/readiness"]["get"]
    assert "requestBody" not in readiness
    assert all(
        parameter["name"] != "X-Control-Plane-Credential"
        for parameter in readiness.get("parameters", [])
    )
    readiness_schema = readiness["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert readiness_schema == {
        "$ref": "#/components/schemas/ControlPlaneReadiness"
    }
    assert "X-Control-Plane-Credential" not in json.dumps(schema)

    analysis_limit = schema["components"]["schemas"]["CodexAnalysisRequest"][
        "properties"
    ]["max_sessions"]
    assert analysis_limit["default"] == 10
    assert analysis_limit["maximum"] == 100

    label_limit = schema["components"]["schemas"]["CodexLabelEnrichmentRequest"][
        "properties"
    ]["max_sessions"]
    assert label_limit["default"] == 10
    assert label_limit["maximum"] == 25

    session_parameters = paths["/v1/sessions"]["get"]["parameters"]
    provider_parameter = next(
        parameter
        for parameter in session_parameters
        if parameter["name"] == "provider"
    )
    assert provider_parameter["in"] == "query"
    assert provider_parameter["required"] is False
    assert all("transcript" not in path for path in paths)


def test_exporter_writes_reproducible_json_without_runtime_state(tmp_path) -> None:
    first = tmp_path / "contract.json"
    second = tmp_path / "contract-copy.json"

    export_openapi(first)
    export_openapi(second)

    assert first.read_bytes() == second.read_bytes()
    document = json.loads(first.read_text(encoding="utf-8"))
    serialized = json.dumps(document).casefold()
    assert document["info"]["title"] == "Prompt Enhancer Local API"
    assert "example-state" not in serialized
    assert "schema_token" not in serialized
    assert "openapi.json" not in document["paths"]
