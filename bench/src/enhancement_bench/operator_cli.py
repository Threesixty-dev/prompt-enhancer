"""Human and AI entrypoints using the deployed Bench's authoritative contracts."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import time
from urllib.parse import urlencode

from .analysis import analysis_schema, dataset, inspect_run, validated_run, write_export
from .definitions import Definition, Overrides, RunPlan
from .errors import BenchError
from .private_io import read_json
from .protocol import Contracts
from .remote import BenchClient, bounded_seconds, identifier
from .store import TERMINAL

COMMANDS = {"experiments", "runs", "preflight", "run", "wait", "inspect", "export", "cancel", "schema"}
HINTS = {
    "transport_unconfirmed": "Inspect the saved receipt; repeat submission only with the same receipt and settings.",
    "submission_acknowledgement_invalid": "Keep the receipt. Resolve admission using the same receipt and settings.",
    "submission_receipt_mismatch": "Use the original origin and settings with this receipt; use a new receipt for an intentional new run.",
    "output_exists": "Choose a new output path; existing artifacts are never overwritten.",
    "wait_timeout": "The run was not cancelled. Inspect or wait for the same run again.",
    "gateway_access_denied": "Ask the operator to check machine access; keep credentials out of output.",
    "gateway_redirect_refused": "Configure machine access to the private API; do not follow the login redirect.",
    "private_file_required": "Use an owner-only submission receipt file.",
    "export_too_large": "Split the explicit run cohort into smaller exports.",
    "submission_not_acknowledged": "Repeat run with the same receipt and original settings to reconcile admission first.",
}


def emit(command, *, data=None, error=None):
    result = {"schemaVersion": "bench-cli/v1", "command": command, "ok": error is None}
    if data is not None:
        result["data"] = data
    if error:
        result["error"] = {"code": error, "nextAction": HINTS.get(error, "Check command help and the Bench client guide.")}
    print(json.dumps(result, allow_nan=False, separators=(",", ":")))


def add_commands(sub):
    for name, help_text in {
        "experiments": "List experiment identities without prompt content.",
        "runs": "List one bounded page of run identities and states.",
        "preflight": "Validate a plan and core registration without invoking models.",
        "run": "Submit once using a durable, reusable private receipt.",
        "wait": "Wait for a run; timeout does not cancel execution.",
        "inspect": "Read technical outcomes, coverage and assertions without prompt text.",
        "export": "Write private versioned JSON and CSV analysis tables for explicit runs.",
        "cancel": "Request cancellation; inspect or wait to confirm cleanup.",
        "schema": "Print the local analysis or run-plan JSON Schema.",
    }.items():
        parser = sub.add_parser(name, help=help_text, description=help_text)
        if name == "schema":
            parser.add_argument("kind", choices=("analysis", "run-plan"))
            continue
        parser.add_argument("--url", default=None, help="Private HTTPS origin (or loopback HTTP); defaults to BENCH_URL.")
        if name in {"preflight", "run"}:
            parser.add_argument("--experiment", required=True)
            parser.add_argument("--revision", required=True)
            parser.add_argument("--overrides", type=Path, help="Explicit authored JSON overrides; no environment file is loaded.")
            parser.add_argument("--subject", action="append", help="Select a case ID; repeat to select more.")
            parser.add_argument("--unit", action="append", help="Select a variant ID; repeat to select more.")
        if name == "run":
            parser.add_argument("--receipt", type=Path, required=True, help="Private receipt, saved before admission; reuse it to reconcile a lost acknowledgement.")
            parser.add_argument("--retry-of", help="Intentional rerun of a reconciled terminal run.")
        if name in {"wait", "inspect", "cancel"}:
            parser.add_argument("run_id", nargs="?")
            parser.add_argument("--receipt", type=Path, help="Use the acknowledged run ID in this submission receipt.")
        if name == "wait":
            parser.add_argument("--timeout", default="300", help="Observation limit in seconds (1-3600).")
            parser.add_argument("--poll-interval", default="2", help="Seconds between reads (0.1-30).")
            parser.add_argument("--require-assertions", action="store_true", help="Exit unsuccessfully unless assertions passed, independently of execution.")
        if name == "runs":
            parser.add_argument("--experiment")
            parser.add_argument("--revision")
            parser.add_argument("--before", help="Cursor returned by the previous page.")
            parser.add_argument("--limit", type=int, default=25)
        if name == "export":
            parser.add_argument("--run", action="append", default=[], help="Exact run ID to include; repeat for a cohort.")
            parser.add_argument("--receipt", type=Path, action="append", default=[])
            parser.add_argument("--output", type=Path, required=True, help="New private directory; never overwrite an existing export.")


def plan_for(args):
    values = read_json(args.overrides) if args.overrides else {}
    if not isinstance(values, dict):
        raise BenchError("invalid_overrides")
    for attr, key in (("subject", "subjectIds"), ("unit", "unitIds")):
        selected = getattr(args, attr)
        if selected:
            if key in values or len(set(selected)) != len(selected):
                raise BenchError("selection_conflict")
            values[key] = selected
    return RunPlan(stableId=args.experiment, revision=args.revision, overrides=Overrides.model_validate(values))


def receipt_run(path, client):
    receipt = read_json(path, private=True)
    if (not isinstance(receipt, dict) or receipt.get("schemaVersion") != "bench-submission/v1"
            or receipt.get("originSha256") != hashlib.sha256(client.origin.encode()).hexdigest()):
        raise BenchError("submission_receipt_mismatch")
    if not receipt.get("runId"):
        raise BenchError("submission_not_acknowledged")
    return identifier(receipt["runId"])


def selected_run(args, client):
    if bool(args.run_id) == bool(args.receipt):
        raise BenchError("exactly_one_run_reference_required")
    return identifier(args.run_id) if args.run_id else receipt_run(args.receipt, client)


def execute(args, *, client_factory=BenchClient, clock=time.monotonic, sleep=time.sleep):
    if args.command == "schema":
        return (analysis_schema() if args.kind == "analysis" else RunPlan.model_json_schema()), 0
    origin = args.url or os.environ.get("BENCH_URL")
    with client_factory(origin, access_client_id=os.environ.get("BENCH_CF_ACCESS_CLIENT_ID"),
                        access_client_secret=os.environ.get("BENCH_CF_ACCESS_CLIENT_SECRET")) as client:
        if args.command == "preflight":
            return client.preflight(plan_for(args)), 0
        if args.command == "run":
            receipt = client.submit(plan_for(args), args.receipt, retry_of=args.retry_of)
            return {"requestId": receipt["requestId"], "runId": receipt["runId"], "receiptSaved": True, "admitted": True}, 0
        if args.command == "experiments":
            values = client.request("GET", "/api/experiments").get("experiments")
            if not isinstance(values, list) or len(values) > 10000:
                raise BenchError("response_contract_invalid")
            projected = []
            for value in values:
                definition = Definition.model_validate({key: item for key, item in value.items() if key not in {"specHash", "image"}})
                projected.append({"stableId": definition.stableId, "revision": definition.revision,
                    "coreVersion": definition.enhancerVersion, "caseIds": [s.id for s in definition.subjects],
                    "unitIds": [u.id for u in definition.units], "workflow": definition.workflow})
            return {"experiments": projected}, 0
        if args.command == "runs":
            if not 1 <= args.limit <= 100:
                raise BenchError("invalid_page_limit")
            query = {"limit": args.limit}
            for name in ("experiment", "revision", "before"):
                if getattr(args, name):
                    query[name] = identifier(getattr(args, name))
            value = client.request("GET", "/api/runs?" + urlencode(query))
            if not isinstance(value.get("runs"), list) or len(value["runs"]) > args.limit:
                raise BenchError("response_contract_invalid")
            rows = [{"runId": identifier(row["id"]), "stableId": identifier(row["stable_id"]),
                     "revision": identifier(row["revision"]), "status": identifier(row["status"]),
                     "assertionOutcome": identifier(row["assertion_outcome"])} for row in value["runs"]]
            return {"runs": rows, "nextCursor": identifier(value["nextCursor"]) if value.get("nextCursor") else None}, 0
        if args.command == "cancel":
            run_id = selected_run(args, client)
            value = client.request("POST", "/api/runs/" + run_id + "/cancel", body={}, expected=202)
            if value.get("id") != run_id:
                raise BenchError("run_identity_mismatch")
            return {"runId": run_id, "cancellationRequested": True, "stopConfirmed": False}, 0
        contracts = Contracts.from_payload(client.request("GET", "/api/client-contracts"))
        if args.command == "export":
            run_ids = [identifier(key) for key in args.run] + [receipt_run(path, client) for path in args.receipt]
            if not 1 <= len(run_ids) <= 50 or len(set(run_ids)) != len(run_ids):
                raise BenchError("unique_run_cohort_required")
            value = dataset(validated_run(client.run(key), contracts) for key in run_ids)
            manifest = write_export(args.output, value)
            return {"exportVersion": manifest["schemaVersion"], "analysisVersion": manifest["analysisVersion"],
                    "runIds": run_ids, "rowCounts": manifest["rowCounts"], "filesWritten": len(manifest["files"]) + 1,
                    "containsPromptText": False}, 0
        run_id = selected_run(args, client)
        if args.command == "inspect":
            return inspect_run(validated_run(client.run(run_id), contracts)), 0
        timeout = bounded_seconds(args.timeout, 1, 3600)
        interval = bounded_seconds(args.poll_interval, 0.1, 30)
        deadline = clock() + timeout
        while clock() < deadline:
            remaining = deadline - clock()
            if remaining <= 0:
                break
            run = validated_run(client.run(run_id, timeout=min(30, remaining)), contracts)
            result = inspect_run(run)
            if run["status"] in TERMINAL:
                failed = (run["status"] != "succeeded" or run["cleanup_pending"] or run["reconciliation_required"]
                          or any(a["technicalOutcome"] != "succeeded" for a in result["attempts"]))
                if args.require_assertions and run["assertion_outcome"] != "passed":
                    failed = True
                return result, 3 if failed else 0
            sleep(min(interval, max(0, deadline - clock())))
        raise BenchError("wait_timeout")
