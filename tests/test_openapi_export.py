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


def test_onboarding_schema_keeps_unknowns_explicit_and_json_safe() -> None:
    schemas = build_openapi_schema()["components"]["schemas"]
    status = schemas["OnboardingStatus"]
    provider = schemas["ProviderDetection"]
    result = schemas["OnboardingResult"]

    assert {"last_refresh_at", "refresh_interval_seconds"}.issubset(
        status["required"]
    )
    assert status["properties"]["refresh_interval_seconds"] == {
        "maximum": 9_007_199_254_740_991,
        "minimum": 60,
        "title": "Refresh Interval Seconds",
        "type": "integer",
    }
    assert "transcript_files" in provider["required"]
    for field in ("indexed_sessions", "transcript_files"):
        choices = provider["properties"][field]["anyOf"]
        assert {choice.get("type") for choice in choices} == {"integer", "null"}
        integer = next(choice for choice in choices if choice.get("type") == "integer")
        assert integer["minimum"] == 0
        assert integer["maximum"] == 9_007_199_254_740_991
    result_choices = result["properties"]["indexed_sessions"]["anyOf"]
    assert {choice.get("type") for choice in result_choices} == {"integer", "null"}
    result_integer = next(
        choice for choice in result_choices if choice.get("type") == "integer"
    )
    assert result_integer["minimum"] == 0
    assert result_integer["maximum"] == 9_007_199_254_740_991
    assert "claude_transcript_count_capped" in schemas["DetectionSignal"]["enum"]


def test_overlapping_provider_and_domain_failures_remain_in_openapi() -> None:
    paths = build_openapi_schema()["paths"]

    def refs(path: str, method: str, status: int) -> set[str]:
        response_schema = paths[path][method]["responses"][str(status)][
            "content"
        ]["application/json"]["schema"]
        choices = response_schema.get("anyOf", [response_schema])
        return {choice["$ref"] for choice in choices}

    provider = "#/components/schemas/SessionProviderFailureResponse"
    assert refs(
        "/v1/sessions/{session_id}/model-ensemble-runs", "post", 404
    ) == {
        provider,
        "#/components/schemas/ModelEnsembleSelectionFailureResponse",
    }
    assert refs(
        "/v1/sessions/{session_id}/model-ensemble-runs", "post", 503
    ) == {
        provider,
        "#/components/schemas/ModelEnsembleUnavailableFailureResponse",
    }
    assert refs(
        "/v1/sessions/{session_id}/model-ensemble-watch", "put", 404
    ) == {
        provider,
        "#/components/schemas/ModelEnsembleWatchSelectionFailureResponse",
    }
    assert refs(
        "/v1/sessions/{session_id}/model-ensemble-watch", "put", 503
    ) == {
        provider,
        "#/components/schemas/ModelEnsembleWatchUnavailableFailureResponse",
    }
    profile_path = "/v1/sessions/{session_id}/declared-task-profile"
    assert refs(profile_path, "get", 404) == {provider}
    assert refs(profile_path, "get", 503) == {
        provider,
        "#/components/schemas/DeclaredTaskProfileUnavailableFailureResponse",
    }
    assert refs(profile_path, "post", 404) == {
        provider,
        "#/components/schemas/DeclaredTaskProfileNotFoundFailureResponse",
    }
    assert refs(profile_path, "post", 503) == {
        provider,
        "#/components/schemas/DeclaredTaskProfileUnavailableFailureResponse",
    }


def test_local_model_lifecycle_failures_are_declared_in_openapi() -> None:
    paths = build_openapi_schema()["paths"]
    base = "/v1/local-models/{alias}"

    def ref(operation: dict[str, object], status: int) -> str:
        return operation["responses"][str(status)]["content"][
            "application/json"
        ]["schema"]["$ref"]

    remove = paths[base]["delete"]
    assert ref(remove, 404).endswith("/LocalModelNotFoundFailureResponse")
    assert ref(remove, 503).endswith("/LocalModelStopFailureResponse")

    activate = paths[f"{base}/activate"]["post"]
    assert ref(activate, 404).endswith("/LocalModelNotFoundFailureResponse")
    assert ref(activate, 409).endswith(
        "/LocalModelActivationConflictFailureResponse"
    )
    assert ref(activate, 502).endswith("/LocalModelActivationFailureResponse")
    assert ref(activate, 503).endswith("/LocalModelStopFailureResponse")

    deactivate = paths[f"{base}/deactivate"]["post"]
    assert ref(deactivate, 404).endswith("/LocalModelNotFoundFailureResponse")
    assert ref(deactivate, 503).endswith("/LocalModelStopFailureResponse")


def test_committed_openapi_artifact_is_byte_exact_to_current_schema() -> None:
    expected = (
        json.dumps(build_openapi_schema(), indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    actual = (REPOSITORY_ROOT / "docs" / "openapi.json").read_bytes()

    assert actual == expected
