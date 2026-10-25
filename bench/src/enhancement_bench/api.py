"""Same-origin API behind an authenticating gateway; content-free access logs/errors."""

from __future__ import annotations

from pathlib import Path
from datetime import date
import re
import time
from uuid import uuid4

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError
from typing import Literal

from .definitions import CoreImage, Definition, Overrides, Publication, RunInput, RunPlan, StrictModel
from .errors import BenchError
from .history import RunFilters, RunStatus
from .protocol import Contracts
from .store import Store
from .analysis import continuation_decision
from .recovery import failure_summary, recovery_summary


class ReconcileInput(StrictModel):
    remoteStopped: Literal[True]
    evidenceReference: str


def create_app(store: Store, contracts: Contracts, *, allowed_repositories: tuple[str, ...],
               origin="http://127.0.0.1:8088") -> FastAPI:
    app = FastAPI(title="Enhancement Bench", docs_url=None, redoc_url=None, openapi_url=None)
    static = Path(__file__).with_name("static")
    revision_file = Path(__file__).with_name("revision.txt")
    revision = revision_file.read_text().strip() if revision_file.is_file() else None

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        if request.headers.get("host") != origin.split("://", 1)[1]:
            return JSONResponse({"error": {"code": "host_not_allowed"}}, 403)
        if request.headers.get("origin") not in (None, origin):
            return JSONResponse({"error": {"code": "origin_not_allowed"}}, 403)
        if request.url.path.startswith("/api/"):
            if request.method not in {"GET", "HEAD", "OPTIONS"} and request.headers.get("origin") != origin:
                # The gateway uses browser cookies, so writes need an explicit same origin.
                return JSONResponse({"error": {"code": "origin_required"}}, 403,
                                    headers={"Cache-Control": "no-store"})
            if request.method == "POST" and request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"error": {"code": "json_required"}}, 415)
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 1_000_000:
                    return JSONResponse({"error": {"code": "request_too_large"}}, 413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                                 "Referrer-Policy": "no-referrer",
                                 "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
        if (request.url.path == "/health/ready" and request.method == "GET"
            and response.status_code == 200 and request.client is not None
            and request.client.host in {"127.0.0.1", "::1"}
            and isinstance(revision, str) and re.fullmatch(r"[a-f0-9]{40}", revision)):
            # The controller can verify local health without public gateway access.
            print(f"BENCH_READY_V1 revision={revision} time_ms={time.time_ns() // 1_000_000}", flush=True)
        return response

    @app.exception_handler(BenchError)
    async def bench_error(_request, error):
        return JSONResponse({"error": {"code": error.code}}, error.status)

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    async def invalid(_request, _error):
        return JSONResponse({"error": {"code": "invalid_request"}}, 422)

    @app.get("/health/ready")
    def health():
        return JSONResponse({"ready": True, "schemaVersion": "bench.v1", "revision": revision},
                            headers={"Cache-Control": "no-store"})

    @app.get("/")
    @app.get("/experiments")
    @app.get("/stats")
    @app.get("/experiments/{experiment_id}")
    @app.get("/experiments/{experiment_id}/stats")
    @app.get("/experiments/{experiment_id}/runs/new")
    @app.get("/experiments/{experiment_id}/runs/{run_id}")
    def index():
        return FileResponse(static / "index.html")

    @app.get("/assets/{name}")
    def asset(name: str):
        if name not in {"app.js", "app.css", "forms.js", "overview.js", "history.js", "metrics.js", "flow.js", "recovery.js"}:
            raise BenchError("not_found", 404)
        return FileResponse(static / name)

    @app.post("/api/publications", status_code=202)
    def publication(value: Publication):
        if value.image is not None and value.image.split("@", 1)[0] not in allowed_repositories:
            raise BenchError("image_repository_not_allowed", 403)
        if value.definition.coreBuild and value.definition.coreBuild.image.split("@", 1)[0] not in allowed_repositories:
            raise BenchError("image_repository_not_allowed", 403)
        # Exercise the authoritative request schema for every combination before import.
        from .definitions import effective_settings

        run = {"stable_id": value.definition.stableId, "revision": value.definition.revision,
               "id": str(uuid4()), "correlation_id": str(uuid4()),
               "effective": effective_settings(value.definition, Overrides())}
        for subject in value.definition.subjects:
            for unit in value.definition.units:
                contracts.request(run, {"id": str(uuid4()), "subject_id": subject.id, "unit_id": unit.id})
        return store.import_publication(value)

    @app.post("/api/core-images", status_code=202)
    def register_core_image(value: CoreImage):
        if value.image.split("@", 1)[0] not in allowed_repositories:
            raise BenchError("image_repository_not_allowed", 403)
        return store.register_core_image(value)

    @app.get("/api/experiments")
    def experiments():
        return {"experiments": store.definitions()}

    @app.get("/api/client-contracts")
    def client_contracts():
        return contracts.payload()

    @app.get("/api/run-form-schema")
    def run_form_schema():
        schema = contracts.validators["execute-request"].schema
        return {"$defs": schema["$defs"], "properties": {
            key: schema["properties"][key] for key in ("objective", "steering", "consumer", "workflow_steps")
        }, "workflows": contracts.workflows}

    @app.get("/api/runs")
    def runs(limit: int = Query(100, ge=1, le=100), before: str | None = Query(None, max_length=80),
             status: RunStatus | None = None, origin: Literal["gitops", "ui"] | None = None,
             experiment: str | None = Query(None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$"),
             revision: str | None = Query(None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$"),
             model: str | None = Query(None, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$"),
             fromDate: date | None = None, toDate: date | None = None, summary: bool = False):
        filters = RunFilters(status=status, origin=origin, experiment=experiment, revision=revision,
                             model=model, fromDate=fromDate, toDate=toDate)
        if summary:
            return store.run_history(limit, before, filters)
        rows = store.runs(limit + 1, before=before, filters=filters)
        return {"runs": rows[:limit], "nextCursor": rows[limit - 1]["id"] if len(rows) > limit else None}

    @app.get("/api/runs/{run_id}")
    def run(run_id: str):
        value = store.run(run_id)
        return value | {"continuation": continuation_decision(value),
                        "failure": failure_summary(value), "recovery": recovery_summary(value)}

    @app.get("/api/recovery")
    def recovery():
        return store.recovery_queue()

    @app.post("/api/runs/{run_id}/cleanup-check", status_code=202)
    def cleanup_check(run_id: str, value: StrictModel):
        store.request_cleanup_check(run_id)
        return {"runId": run_id, "recovery": recovery_summary(store.run(run_id))}

    def validate_plan(value: RunPlan):
        from .definitions import effective_settings

        definition = next((d for d in store.definitions() if d["stableId"] == value.stableId and d["revision"] == value.revision), None)
        if definition is None:
            raise BenchError("definition_not_found", 404)
        definition = Definition.model_validate({k: v for k, v in definition.items() if k not in {"image", "specHash"}})
        effective = effective_settings(definition, value.overrides)
        request_run = {"stable_id": value.stableId, "revision": value.revision, "id": str(uuid4()),
                       "correlation_id": str(uuid4()), "effective": effective}
        for subject in effective["subjects"]:
            for unit in effective["units"]:
                contracts.request(request_run, {"id": str(uuid4()), "subject_id": subject["id"], "unit_id": unit["id"]})
        return definition, effective

    @app.post("/api/runs/preflight")
    def preflight(value: RunPlan):
        definition, effective = validate_plan(value)
        return store.preflight(definition, effective)

    @app.post("/api/runs", status_code=202)
    def enqueue(value: RunInput):
        validate_plan(value)
        return {"runId": store.enqueue_ui(value.stableId, value.revision, value.overrides,
                                          value.requestId, value.retryOf)}

    @app.post("/api/runs/{run_id}/cancel", status_code=202)
    def cancel(run_id: str):
        return store.cancel(run_id)

    @app.post("/api/runs/{run_id}/reconcile")
    def reconcile(run_id: str, value: ReconcileInput):
        store.acknowledge_remote_stopped(run_id, value.evidenceReference)
        return store.run(run_id)

    return app
