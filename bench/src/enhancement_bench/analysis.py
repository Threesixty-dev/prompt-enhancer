"""Versioned, content-minimized analysis of immutable Bench results."""

from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import io
import math
from pathlib import Path

from .comparisons import identity, numeric
from .definitions import IMAGE, fingerprint
from .errors import BenchError
from .private_io import local_path, write_json, write_new
from .remote import identifier
from .store import TERMINAL
from .recovery import failure_summary, recovery_summary

VERSION = "bench-analysis/v2"
MAX_EXPORT_ROWS = 50_000
MAX_EXPORT_BYTES = 64_000_000
STATES = ("known", "unknown", "abstained", "not_applicable", "execution_error", "missing")
TABLES = {
    "runs": {
        **dict.fromkeys(("run_id", "experiment_id", "revision", "core_version", "core_image", "run_status", "assertion_outcome", "evaluation_profile_sha256", "effective_settings_sha256"), "string"),
        **dict.fromkeys(("workflow_id", "workflow_version", "workflow_sha256", "evaluator_profile_id", "evaluator_profile_revision"), "string?"),
        **dict.fromkeys(("created_seconds", "started_seconds", "finished_seconds"), "number?"),
        "cleanup_pending": "boolean", "reconciliation_required": "boolean", "attempt_count": "integer",
    },
    "attempts": {
        **dict.fromkeys(("run_id", "attempt_id", "subject_id", "unit_id", "status", "technical_outcome", "assertion_outcome", "parameters_sha256", "step_settings_sha256", "strategy", "objective_sha256", "steering_sha256", "context_sha256"), "string"),
        **dict.fromkeys(("execution_status", "review_state", "workflow_configuration_sha256", "input_sha256", "candidate_sha256", "generation_context_version", "generation_prompt_version"), "string?"),
        "position": "integer", "has_candidate": "boolean", "result_recorded": "boolean",
        "generation_provenance": "object?", "missing_before_evaluators": "array", "missing_after_evaluators": "array",
        "parameters": "object", "consumer_binding": "object?", "workflow_steps": "object", "workflow_step_order": "array",
    },
    "metrics": {
        **dict.fromkeys(("run_id", "attempt_id", "evaluator_id", "evaluator_kind", "binding_id", "metric_key", "before_state", "before_reason", "after_state", "after_reason", "delta_state", "delta_reason", "comparison_scope"), "string"),
        **dict.fromkeys(("before_value", "after_value", "delta_value"), "number?"),
        **dict.fromkeys(("before_label", "after_label", "exclusion_reason"), "string?"),
        "before_provenance": "object?", "after_provenance": "object?", "pair_eligible": "boolean",
    },
    "assertions": {
        **dict.fromkeys(("run_id", "attempt_id", "evaluator_id", "metric_key", "operator", "outcome"), "string"),
        "position": "integer", "threshold": "number", "observed": "number?", "recorded": "boolean",
    },
    "timings": {"run_id": "string", "attempt_id": "string", "stage": "string", "seconds": "number"},
    "errors": {"run_id": "string", "attempt_id": "string", "stage": "string", "code": "string", "retryable": "boolean",
               "validation_reason": "string?", "validation_field": "string?"},
}


def analysis_schema():
    def field(kind):
        base = kind.rstrip("?")
        result = {"type": [base, "null"] if kind.endswith("?") else base}
        if base == "array":
            result["items"] = {"type": "string"}
        return result
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "additionalProperties": False,
        "required": ["schemaVersion", "createdAt", "tables"],
        "properties": {"schemaVersion": {"const": VERSION}, "createdAt": {"type": "string"},
            "tables": {"type": "object", "additionalProperties": False, "required": list(TABLES),
                "properties": {table: {"type": "array", "items": {"type": "object", "additionalProperties": False,
                    "required": list(columns), "properties": {name: field(kind) for name, kind in columns.items()}}}
                    for table, columns in TABLES.items()}}}}


def require(condition, code="run_contract_invalid"):
    if not condition:
        raise BenchError(code)


def validated_run(run: dict, contracts):
    """Check correlation and every stored result before any projection or export."""
    try:
        for key in ("id", "stable_id", "revision"):
            identifier(run[key])
        require(run["status"] in TERMINAL | {"queued", "running"})
        require(run["assertion_outcome"] in {"passed", "failed", "unknown", "not_evaluated"})
        require(isinstance(run["image"], str) and IMAGE.fullmatch(run["image"]))
        for key in ("cleanup_pending", "reconciliation_required"):
            require(type(run[key]) in (int, bool) and run[key] in (0, 1))
        for key in ("created", "started", "finished"):
            require(run[key] is None or (numeric(run[key]) and run[key] >= 0))
        effective, attempts = run["effective"], run["attempts"]
        require(effective["stableId"] == run["stable_id"] and effective["revision"] == run["revision"])
        expected = [(s["id"], u["id"]) for s in effective["subjects"] for u in effective["units"]]
        require(0 < len(expected) <= 512 and isinstance(attempts, list) and len(attempts) == len(expected))
        require(len({a["id"] for a in attempts}) == len(attempts))
        for position, (attempt, pair) in enumerate(zip(attempts, expected)):
            identifier(attempt["id"])
            require(attempt["run_id"] == run["id"] and attempt["position"] == position)
            require((attempt["subject_id"], attempt["unit_id"]) == pair)
            require(attempt["status"] in TERMINAL | {"queued", "running", "skipped"})
            request = contracts.request(run, attempt)
            stored_request = attempt.get("request")
            if stored_request is not None:
                require(stored_request == request, "run_request_mismatch")
            result = attempt.get("result")
            if result is not None:
                require(stored_request is not None)
                contracts.result(result, request, effective["enhancerVersion"])
                for side in ("before", "after"):
                    metric_index(result, side, {e["evaluator_id"]: e for e in request["evaluation"]["evaluators"]})
                steps = (result.get("workflow_result") or {}).get("steps", [])
                require(len({step["step_id"] for step in steps}) == len(steps), "analysis_duplicate_step")
        return run
    except (KeyError, TypeError, ValueError, AttributeError, StopIteration):
        raise BenchError("run_contract_invalid") from None


def technical_outcome(attempt):
    result = attempt.get("result")
    if not result:
        return "incomplete" if attempt["status"] in {"queued", "running", "skipped"} else "failed"
    workflow = result.get("workflow_result") or {}
    failed_review = (workflow.get("review") or {}).get("state") in {"reply_invalid", "model_error"}
    failed_step = any(s["status"] == "failed" for s in workflow.get("steps", []))
    failed_evaluation = any(m["state"] == "execution_error" for side in ("before", "after")
                            for e in result.get(side, []) for m in e["metrics"])
    return "failed" if (attempt["status"] != "succeeded" or result["status"] != "succeeded"
                         or result.get("errors") or failed_review or failed_step or failed_evaluation) else "succeeded"


def continuation_decision(run):
    """A settled result permits only independent work, never automatic replay."""
    try:
        return _continuation_decision(run)
    except (KeyError, TypeError, ValueError, AttributeError):
        return {"decision": "stop", "reason": "result_evidence_invalid", "replayAllowed": False}


def _continuation_decision(run):
    def decision(allowed, reason):
        return {"decision": "continue_independent_case" if allowed else "stop", "reason": reason, "replayAllowed": False}

    if run["cleanup_pending"] or run["reconciliation_required"]:
        return decision(False, "recovery_required")
    if run.get("status") not in {"succeeded", "failed"}:
        return decision(False, "run_not_settled_success_or_review_failure")
    if run.get("error_code") not in {None, "core_failed"}:
        return decision(False, "operational_failure")
    if run["status"] == "succeeded" and run.get("error_code") is not None:
        return decision(False, "contradictory_outcome")
    attempts = run.get("attempts", [])
    if not attempts or any(a.get("status") not in {"succeeded", "failed"} for a in attempts):
        return decision(False, "incomplete_selection")
    effective = run["effective"]
    if [(a["subject_id"], a["unit_id"]) for a in attempts] != [
        (s["id"], u["id"]) for s in effective["subjects"] for u in effective["units"]
    ]:
        return decision(False, "incomplete_selection")
    expected = [e["evaluator_id"] for e in effective["evaluatorProfile"]["evaluators"]]
    failures = 0
    for attempt in attempts:
        result = attempt.get("result") or {}
        if [e["evaluator_id"] for e in result.get("before", [])] != expected:
            return decision(False, "incomplete_evaluation")
        if technical_outcome(attempt) == "succeeded":
            expected_after = expected if result.get("candidate") is not None else []
            if [e["evaluator_id"] for e in result.get("after", [])] != expected_after:
                return decision(False, "incomplete_evaluation")
            continue
        workflow = result.get("workflow_result") or {}
        errors = result.get("errors") or []
        completed_review_failure = (
            attempt.get("status") == result.get("status") == "failed"
            and (workflow.get("review") or {}).get("state") == "reply_invalid"
            and [(s.get("step_id"), s.get("status")) for s in workflow.get("steps", [])]
                == [("diagnose", "succeeded"), ("context", "succeeded"), ("review", "failed")]
            and len(errors) == 1 and errors[0].get("code") == "workflow_review_reply_invalid"
            and errors[0].get("stage") == "generate"
            and bool(result.get("consumer_provenance"))
            and not any(m["state"] == "execution_error" for e in result.get("before", []) for m in e["metrics"])
            and not result.get("candidate") and not result.get("enhanced_prompt")
            and not result.get("after") and not result.get("deltas")
        )
        if not completed_review_failure:
            return decision(False, "technical_failure_requires_inspection")
        failures += 1
    if (run["status"] == "failed") != bool(failures):
        return decision(False, "contradictory_outcome")
    return decision(True, "completed_invalid_review" if failures else "completed_successfully")


def review_validation_issue(result):
    review = (result.get("workflow_result") or {}).get("review") or {}
    return review.get("validation_issue") or {}


def inspect_run(run):
    attempts, states = [], Counter()
    expected = {e["evaluator_id"] for e in run["effective"]["evaluatorProfile"]["evaluators"]}
    for attempt in run["attempts"]:
        result = attempt.get("result") or {}
        for side in ("before", "after"):
            states.update(m["state"] for e in result.get(side, []) for m in e["metrics"])
        review = ((result.get("workflow_result") or {}).get("review") or {}).get("state")
        attempts.append({"attemptId": attempt["id"], "subjectId": attempt["subject_id"], "unitId": attempt["unit_id"],
            "status": attempt["status"], "technicalOutcome": technical_outcome(attempt),
            "reviewState": review, "hasCandidate": result.get("candidate") is not None,
            "workflowSteps": [{"stepId": step["step_id"], "implementation": step["implementation"], "status": step["status"]}
                              for step in (result.get("workflow_result") or {}).get("steps", [])],
            "missingEvaluators": {side: sorted(expected - {e["evaluator_id"] for e in result.get(side, [])}) for side in ("before", "after")},
            "assertionOutcome": result.get("assertion_outcome", "not_evaluated"),
            "errors": [{"code": e["code"], "stage": e["stage"],
                        "validationIssue": review_validation_issue(result) or None
                            if e["code"] == "workflow_review_reply_invalid" else None} for e in result.get("errors", [])]})
    return {"schemaVersion": "bench-inspection/v1", "runId": run["id"], "status": run["status"],
        "assertionOutcome": run["assertion_outcome"], "cleanupPending": bool(run["cleanup_pending"]),
        "reconciliationRequired": bool(run["reconciliation_required"]),
        "attemptCounts": dict(Counter(a["status"] for a in attempts)),
        "technicalOutcomes": dict(Counter(a["technicalOutcome"] for a in attempts)),
        "readingStates": {state: states[state] for state in STATES if state != "missing"}, "attempts": attempts,
        "continuation": continuation_decision(run), "failure": failure_summary(run),
        "recovery": recovery_summary(run)}


def metric_index(result, side, expected):
    values, evaluator_ids = {}, set()
    for evaluation in result.get(side, []):
        eid = evaluation["evaluator_id"]
        require(eid in expected and eid not in evaluator_ids, "analysis_evaluator_mismatch")
        require(expected[eid]["kind"] == evaluation["kind"], "analysis_evaluator_mismatch")
        evaluator_ids.add(eid)
        for metric in evaluation["metrics"]:
            key = (eid, metric["key"])
            require(key not in values, "analysis_duplicate_metric")
            number, label = metric.get("value"), metric.get("label")
            require((metric["state"] == "known" and ((numeric(number) and label is None) or (number is None and isinstance(label, str))))
                    or (metric["state"] != "known" and number is None and label is None), "analysis_metric_invalid")
            values[key] = (metric, evaluation["provenance"])
    return values, evaluator_ids


def step_settings(receipt):
    result = {}
    for step in receipt.get("steps", []):
        require(step["step_id"] not in result, "analysis_duplicate_step")
        values = {key: step.get(key) for key in ("implementation", "status", "binding", "generation", "enable_thinking")}
        values["provenance"] = identity(step["provenance"]) if step.get("provenance") else None
        policy = step.get("policy")
        values["policy"] = None if policy is None else {"policy_id": policy["policy_id"], "revision": policy["revision"],
            "instructions_sha256": hashlib.sha256(policy["instructions"].encode()).hexdigest()}
        result[step["step_id"]] = values
    return result


def project_run(run):
    effective = run["effective"]
    tables = {key: [] for key in TABLES}
    workflow, profile = effective.get("workflow") or {}, effective["evaluatorProfile"]
    profile_hash = fingerprint(profile)
    settled = run["status"] in TERMINAL and not run["cleanup_pending"] and not run["reconciliation_required"]
    tables["runs"].append({"run_id": run["id"], "experiment_id": run["stable_id"], "revision": run["revision"],
        "core_version": effective["enhancerVersion"], "core_image": run["image"], "run_status": run["status"],
        "assertion_outcome": run["assertion_outcome"], "evaluation_profile_sha256": profile_hash,
        "effective_settings_sha256": fingerprint(effective),
        "workflow_id": workflow.get("workflow_id"), "workflow_version": workflow.get("version"), "workflow_sha256": workflow.get("definition_sha256"),
        "evaluator_profile_id": profile.get("profile_id"), "evaluator_profile_revision": profile.get("revision"),
        "created_seconds": run["created"], "started_seconds": run["started"], "finished_seconds": run["finished"],
        "cleanup_pending": bool(run["cleanup_pending"]), "reconciliation_required": bool(run["reconciliation_required"]), "attempt_count": len(run["attempts"])})
    expected = {e["evaluator_id"]: e for e in profile["evaluators"]}
    require(len(expected) == len(profile["evaluators"]), "analysis_evaluator_mismatch")
    for attempt in run["attempts"]:
        base = {"run_id": run["id"], "attempt_id": attempt["id"]}
        result = attempt.get("result") or {}
        receipt = result.get("workflow_result") or {}
        unit = next(u for u in effective["units"] if u["id"] == attempt["unit_id"])
        subject = next(s for s in effective["subjects"] if s["id"] == attempt["subject_id"])
        outcome = technical_outcome(attempt)
        sides = {side: metric_index(result, side, expected) for side in ("before", "after")}
        tables["attempts"].append({**base, "subject_id": attempt["subject_id"], "unit_id": attempt["unit_id"],
            "position": attempt["position"], "status": attempt["status"], "technical_outcome": outcome,
            "assertion_outcome": result.get("assertion_outcome", "not_evaluated"), "execution_status": result.get("status"),
            "review_state": (receipt.get("review") or {}).get("state"), "result_recorded": bool(result),
            "has_candidate": result.get("candidate") is not None, "parameters_sha256": fingerprint(unit["parameters"]),
            "parameters": result.get("effective_parameters", unit["parameters"]), "workflow_steps": step_settings(receipt),
            "workflow_step_order": [step["step_id"] for step in receipt.get("steps", [])],
            "strategy": unit["strategy"], "consumer_binding": result.get("consumer_binding") if result else
                (unit.get("consumerBinding", effective.get("consumerBinding")) if unit["strategy"].startswith("consumer.") or unit["strategy"] == "prompt.check.v1" else None),
            "objective_sha256": fingerprint(unit["objective"]), "steering_sha256": fingerprint(unit["steering"]),
            "context_sha256": fingerprint(subject["context"]),
            "generation_context_version": result.get("generation_context_version"),
            "generation_prompt_version": result.get("generation_prompt_version"),
            "input_sha256": (result.get("original") or {}).get("sha256"),
            "candidate_sha256": (result.get("candidate") or {}).get("sha256"),
            "step_settings_sha256": fingerprint(unit.get("stepSettings", {})),
            "workflow_configuration_sha256": receipt.get("configuration_sha256"),
            "generation_provenance": identity(result["consumer_provenance"]) if result.get("consumer_provenance") else None,
            **{"missing_" + side + "_evaluators": sorted(set(expected) - sides[side][1]) for side in sides}})
        deltas = {}
        for delta in result.get("deltas", []):
            key = (delta["evaluator_id"], delta["metric_key"])
            require(key not in deltas and key[0] in expected, "analysis_duplicate_metric")
            deltas[key] = delta
        keys = set(sides["before"][0]) | set(sides["after"][0]) | set(deltas)
        for eid, metric_key in sorted(keys):
            row = {**base, "evaluator_id": eid, "metric_key": metric_key,
                   "evaluator_kind": expected[eid]["kind"], "binding_id": expected[eid]["binding_id"]}
            provenances = []
            for side in sides:
                metric, provenance = sides[side][0].get((eid, metric_key), ({"state": "missing", "reason": "not_recorded"}, None))
                provenances.append(provenance)
                row.update({side + "_state": metric["state"], side + "_reason": metric["reason"],
                    side + "_value": metric.get("value"), side + "_label": metric.get("label"),
                    side + "_provenance": identity(provenance) if provenance else None})
            delta = deltas.get((eid, metric_key), {"state": "missing", "reason": "not_recorded"})
            row.update(delta_state=delta["state"], delta_reason=delta["reason"], delta_value=delta.get("value"))
            reason = ("run_unsettled" if not settled else "attempt_not_successful" if outcome != "succeeded"
                else "reading_unavailable" if row["before_state"] != "known" or row["after_state"] != "known"
                else "provenance_mismatch" if not provenances[0] or provenances[0] != provenances[1]
                else "categorical_metric" if row["before_label"] is not None or row["after_label"] is not None
                else "delta_unavailable" if delta["state"] != "comparable" or not numeric(delta.get("value"))
                else "delta_mismatch" if not math.isclose(row["after_value"] - row["before_value"], delta["value"], rel_tol=1e-9, abs_tol=1e-12)
                else None)
            row.update(pair_eligible=reason is None, exclusion_reason=reason,
                comparison_scope=fingerprint({"experiment": run["stable_id"], "revision": run["revision"],
                    "image": run["image"], "workflow": workflow, "profile": profile_hash,
                    "evaluator": eid, "metric": metric_key, "provenance": row["before_provenance"]}))
            tables["metrics"].append(row)
        checks = result.get("assertions", [])
        require(not checks or len(checks) == len(unit["assertions"]), "analysis_assertion_mismatch")
        for position, assertion in enumerate(unit["assertions"]):
            check = checks[position] if checks else {}
            require(not check or check["assertion"] == assertion, "analysis_assertion_mismatch")
            tables["assertions"].append({**base, "position": position, "evaluator_id": assertion["evaluator_id"],
                "metric_key": assertion["metric_key"], "operator": assertion["operator"], "threshold": assertion["threshold"],
                "outcome": check.get("outcome", "not_evaluated"), "observed": check.get("observed"), "recorded": bool(check)})
        for timing in result.get("timings", []):
            tables["timings"].append({**base, "stage": timing["stage"], "seconds": timing["seconds"]})
        for error in result.get("errors", []):
            issue = review_validation_issue(result) if error["code"] == "workflow_review_reply_invalid" else {}
            tables["errors"].append({**base, "stage": error["stage"], "code": error["code"], "retryable": error["retryable"],
                                    "validation_reason": issue.get("reason"), "validation_field": issue.get("field")})
    return tables


def dataset(runs):
    tables = {key: [] for key in TABLES}
    seen = set()
    for run in runs:
        require(run["id"] not in seen, "duplicate_run")
        seen.add(run["id"])
        for name, rows in project_run(run).items():
            require(sum(map(len, tables.values())) + len(rows) <= MAX_EXPORT_ROWS, "export_too_large")
            tables[name].extend(rows)
    require(bool(seen), "runs_required")
    return {"schemaVersion": VERSION, "createdAt": datetime.now(timezone.utc).isoformat(), "tables": tables}


def write_export(path: Path, value):
    """Create an owned directory; manifest is written last as the completion marker."""
    from jsonschema import Draft202012Validator
    from .definitions import canonical
    require(Draft202012Validator(analysis_schema()).is_valid(value), "analysis_contract_invalid")
    path = local_path(path)
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        raise BenchError("output_exists") from None
    except OSError:
        raise BenchError("file_write_failed") from None
    owned, files = [], {}
    try:
        contents = {"analysis.json": (canonical(value) + "\n").encode(),
                    "analysis.schema.json": (canonical(analysis_schema()) + "\n").encode(),
                    "README.md": Path(__file__).with_name("analysis-guide.md").read_bytes()}
        for table, columns in TABLES.items():
            stream = io.StringIO(newline="")
            writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            for row in value["tables"][table]:
                def cell(item):
                    if item is None:
                        return ""
                    if isinstance(item, (dict, list, bool)):
                        return canonical(item)
                    if isinstance(item, str) and item.startswith(("=", "+", "-", "@", "\t", "\r")):
                        return "'" + item
                    return item
                writer.writerow({key: cell(item) for key, item in row.items()})
            contents[table + ".csv"] = stream.getvalue().encode()
        require(sum(map(len, contents.values())) <= MAX_EXPORT_BYTES, "export_too_large")
        for name, content in contents.items():
            target = path / name
            write_new(target, content)
            owned.append(target)
            files[name] = {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}
        manifest = {"schemaVersion": "bench-export/v1", "analysisVersion": VERSION, "files": files,
                    "rowCounts": {key: len(rows) for key, rows in value["tables"].items()},
                    "runIds": [row["run_id"] for row in value["tables"]["runs"]],
                    "csvNull": "empty cell", "csvFormulaPrefix": "apostrophe", "containsPromptText": False}
        write_json(path / "manifest.json", manifest)
        return manifest
    except BaseException:
        for target in owned:
            target.unlink(missing_ok=True)
        path.rmdir()
        raise
