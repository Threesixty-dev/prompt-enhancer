"""Standalone headless API. No desktop, sessions, database, or history routes."""
from __future__ import annotations

from contextlib import asynccontextmanager
import hmac
import json

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from . import CORE_VERSION, PROTOCOL_VERSION
from .contracts import Capabilities, ExecuteRequest, ExecutionResult, Progress
from .manager import ExecutionManager
from .ports import CoreError


def error(code: str, status: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code}}, status_code=status, headers={"Cache-Control": "no-store"})


def create_app(manager: ExecutionManager, *, api_token: str) -> FastAPI:
    if len(api_token) < 32:
        raise ValueError("api_token_too_short")

    @asynccontextmanager
    async def lifespan(app):
        yield
        await manager.close()

    app = FastAPI(title="Enhancement Core", version=CORE_VERSION, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        if request.headers.get("origin") is not None:
            return error("browser_origin_forbidden", 403)
        auth = request.headers.get("authorization", "")
        if not hmac.compare_digest(auth.encode(), ("Bearer " + api_token).encode()):
            return error("unauthorized", 401)
        if request.method == "POST":
            if request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
                return error("json_required", 415)
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 320_000:
                    return error("request_too_large", 413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
            def unique(pairs):
                value = {}
                for key, item in pairs:
                    if key in value:
                        raise ValueError("duplicate_json_key")
                    value[key] = item
                return value
            try:
                json.loads(request._body, object_pairs_hook=unique)
            except (ValueError, UnicodeError, RecursionError):
                return error("request_invalid", 422)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        return error("request_invalid", 422)

    @app.exception_handler(CoreError)
    async def failed(request, exc):
        status = {"execution_not_found": 404, "identity_conflict": 409,
                  "execution_active": 409, "result_pending": 409,
                  "admission_unavailable": 429, "synthetic_benchmark_disabled": 403}.get(exc.code, 422)
        return error(exc.code, status)

    @app.get("/health/ready")
    async def ready():
        state = manager.readiness()
        return JSONResponse(state.model_dump(), status_code=200 if state.ready else 503)

    @app.get("/v1/capabilities", response_model=Capabilities)
    async def capabilities():
        return {"protocol_version": PROTOCOL_VERSION, "core_version": CORE_VERSION,
            "strategies": ["script.clarify.v1", "consumer.rewrite.v1"],
            "consumers": [{"binding_id": key, "provider": value.provider,
                "provenance": value.provenance.model_dump()} for key, value in manager.engine.consumers.items()],
            "evaluators": [{"binding_id": key, "kind": value.kind,
                "provenance": value.provenance.model_dump()} for key, value in manager.engine.evaluators.items()],
            "request_schema": ExecuteRequest.model_json_schema(),
            "data_policies": ["synthetic_benchmark"],
            "result_storage": "ephemeral", "max_active": manager.max_active,
            "max_retained": manager.max_retained}

    @app.post("/v1/executions", response_model=Progress, status_code=202)
    async def execute(request: ExecuteRequest):
        return manager.submit(request)

    @app.get("/v1/executions/{key}", response_model=Progress)
    async def progress(key: str):
        return manager.get(key).progress

    @app.get("/v1/executions/{key}/result", response_model=ExecutionResult)
    async def result(key: str):
        value = manager.get(key).result
        if value is None:
            raise CoreError("result_pending")
        return value

    @app.post("/v1/executions/{key}/cancel", response_model=Progress, status_code=202)
    async def cancel(key: str):
        return manager.cancel(key)

    @app.delete("/v1/executions/{key}", status_code=204)
    async def delete(key: str):
        manager.delete(key)
        return Response(status_code=204)

    return app
