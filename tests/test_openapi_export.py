from __future__ import annotations

import json
from pathlib import Path

from scripts.export_openapi import build_openapi_schema, export_openapi


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


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
    verification_base = (
        "/v1/sessions/{session_id}/requirement-verification-evidence"
    )
    assert {
        path for path in paths if path.startswith(verification_base)
    } == {
        f"{verification_base}/opportunity-sets/current",
        (
            f"{verification_base}/opportunity-sets/"
            "{opportunity_set_fingerprint}"
        ),
        f"{verification_base}/objective-results",
        f"{verification_base}/acceptances",
    }
    acceptance_operation = paths[f"{verification_base}/acceptances"]["post"]
    acceptance_parameters = {
        parameter["name"]: parameter
        for parameter in acceptance_operation["parameters"]
    }
    native_proofs = {
        "prompt_enhancer_session",
        "Origin",
        "X-Prompt-Enhancer-CSRF",
        "X-Prompt-Enhancer-User-Presence",
    }
    assert set(acceptance_parameters) == {
        "session_id",
        "Idempotency-Key",
        *native_proofs,
    }
    assert all(
        acceptance_parameters[name]["required"] is True
        for name in native_proofs
    )
    assert acceptance_parameters["prompt_enhancer_session"]["in"] == "cookie"
    assert "X-Prompt-Enhancer-Token" not in acceptance_parameters
    assert "Authorization" not in acceptance_parameters
    assert acceptance_operation["security"] == []
    assert set(acceptance_operation["responses"]) == {
        "200",
        "201",
        "401",
        "403",
        "404",
        "409",
        "422",
        "503",
    }
    response_schema = acceptance_operation["responses"]["422"]["content"][
        "application/json"
    ]["schema"]
    assert {item["$ref"] for item in response_schema["anyOf"]} == {
        "#/components/schemas/RequirementVerificationMessageErrorDto",
        "#/components/schemas/RequirementVerificationServiceErrorDto",
    }
    verification_schema = json.dumps(
        {
            name: value
            for name, value in schema["components"]["schemas"].items()
            if "RequirementVerification" in name
            or "RequirementAcceptance" in name
        }
    ).casefold()
    for prohibited in (
        "assistant_claim",
        "prompt",
        "transcript",
        "excerpt",
        "file_path",
        "raw_content",
        "idempotency_key_digest",
        "command_fingerprint",
    ):
        assert prohibited not in verification_schema
    assert "/v1/analysis-jobs" in paths
    assert "/v1/analysis-jobs/{job_id}" in paths
    assert "/v1/analysis-jobs/{job_id}/cancellation" in paths
    assert "/v1/sessions/{session_id}/analysis-jobs/latest" in paths
    assert set(paths["/v1/estimators/plans"]) == {"get"}
    assert set(paths["/v1/control-plane/readiness"]) == {"get"}
    assert set(paths["/v1/agent/sessions/{session_id}/events/stream"]) == {"get"}
    agent_contract = schema["components"]["schemas"]["AgentEvents"]["properties"]["contract_version"]
    assert agent_contract["const"] == "local-agent.v2"
    assert "text/event-stream" in paths["/v1/agent/sessions/{session_id}/events/stream"]["get"]["responses"]["200"]["content"]
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
    # ADR 0011: exactly one owner-authorized, read-only transcript route, GET only,
    # returning the bounded SessionTranscript whose persisted flag is fixed false.
    transcript_paths = [path for path in paths if "transcript" in path]
    assert transcript_paths == ["/v1/sessions/{session_id}/transcript"]
    assert set(paths["/v1/sessions/{session_id}/transcript"]) == {"get"}
    transcript_schema = schema["components"]["schemas"]["SessionTranscript"]["properties"]
    assert transcript_schema["persisted"].get("const") is False or transcript_schema["persisted"].get("enum") == [False]
    assert transcript_schema["turns"]["maxItems"] == 2000


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


def test_committed_openapi_artifact_is_byte_exact_to_current_schema() -> None:
    expected = (
        json.dumps(build_openapi_schema(), indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    actual = (REPOSITORY_ROOT / "docs" / "openapi.json").read_bytes()

    assert actual == expected
