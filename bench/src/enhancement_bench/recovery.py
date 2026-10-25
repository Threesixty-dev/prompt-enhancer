"""Content-free failure context shared by the UI and operator client."""

from __future__ import annotations


def failure_summary(run):
    """Prefer the recorded cause over the worker's terminal-state wrapper."""
    for attempt in run.get("attempts", []):
        result = attempt.get("result") or {}
        errors = result.get("errors") or []
        review = ((result.get("workflow_result") or {}).get("review") or {}).get("state")
        if errors:
            error = errors[0]
        elif attempt.get("status") in {"failed", "interrupted"}:
            error = {"code": attempt.get("error_code") or run.get("error_code") or "cause_not_recorded",
                     "stage": (attempt.get("progress") or {}).get("stage")}
        elif review in {"reply_invalid", "model_error"}:
            error = {"code": "workflow_review_" + review, "stage": "generate"}
        else:
            continue
        return {"code": error["code"], "stage": error.get("stage"),
                "operationId": error.get("operation_id"), "attemptId": attempt["id"],
                "subjectId": attempt["subject_id"], "unitId": attempt["unit_id"],
                "attemptPosition": attempt["position"]}
    if run.get("error_code"):
        return {"code": run["error_code"], "stage": None, "operationId": None,
                "attemptId": None, "subjectId": None, "unitId": None, "attemptPosition": None}
    return None


def recovery_summary(run):
    cleanup, remote = bool(run["cleanup_pending"]), bool(run["reconciliation_required"])
    active = run["status"] in {"queued", "running"}
    check = run.get("cleanup_check")
    receipt = run.get("reconciliation")
    if active:
        action = "observe_run"
    elif cleanup:
        action = "wait_for_cleanup" if not check or check["next_check"] is not None else "retry_cleanup"
    else:
        action = "confirm_remote_stop" if remote else "inspect_result"
    return {"schemaVersion": "bench-recovery/v1", "blocked": not active and (cleanup or remote),
            "localCleanup": "pending" if cleanup else "confirmed" if run.get("started") else "not_required",
            "remoteCompletion": "unconfirmed" if remote else "operator_confirmed" if receipt else "not_held",
            "nextAction": action,
            "cleanupCheck": check, "reconciliation": receipt, "automaticReplay": False}
