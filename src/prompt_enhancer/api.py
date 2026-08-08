"""Authenticated, loopback-only HTTP views over the local metadata store."""

from __future__ import annotations

import hmac
from pathlib import Path
from typing import Annotated, Any, Mapping, Protocol, Sequence
from urllib.parse import urlsplit

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Path as PathParameter,
    Query,
    Request,
    Response,
)
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles

from .application.display_labels import ManualDisplayLabelService
from .application.local_sources import CodexLocalSourceService
from .config import (
    AppSettings,
    is_loopback_host,
    lexical_absolute_path,
    path_has_symlink_component,
    prepare_app_home,
)
from .domain import PSEUDONYM_PATTERN, Provider
from .interfaces.http import create_task_query_router
from .interfaces.http.browser_session import (
    BROWSER_SESSION_COOKIE,
    CSRF_HEADER,
    BrowserSessionManager,
)
from .interfaces.http.analysis_routes import (
    TaskAnalysisCommandService,
    create_task_analysis_router,
)
from .interfaces.http.review_routes import (
    ReviewCommandService,
    create_task_review_router,
)
from .interfaces.http.local_source_routes import create_local_source_router
from .interfaces.http.display_label_routes import create_display_label_router
from .privacy import load_or_create_api_token


API_TOKEN_HEADER = "X-Prompt-Enhancer-Token"


class ReadStore(Protocol):
    """The intentionally narrow database surface exposed by the API."""

    def initialize(self) -> None: ...

    def list_metric_definitions(self) -> list[dict[str, Any]]: ...

    def list_sessions(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        provider: Provider | None = None,
    ) -> list[dict[str, Any]]: ...

    def get_session_metrics(self, session_id: str) -> list[dict[str, Any]]: ...


def _default_port(scheme: str) -> int | None:
    if scheme == "http":
        return 80
    if scheme == "https":
        return 443
    return None


def _host_header_is_loopback(host_header: str | None) -> bool:
    """Parse Host without ambiguous colon splitting or user information."""

    if host_header is None or not host_header:
        return False
    if any(character.isspace() for character in host_header):
        return False
    try:
        parsed = urlsplit(f"//{host_header}")
        _ = parsed.port
    except ValueError:
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    if parsed.path or parsed.query or parsed.fragment:
        return False
    if parsed.hostname is None:
        return False
    return is_loopback_host(parsed.hostname)


def _origin_matches_request(origin: str, request: Request) -> bool:
    """Accept only a syntactically valid same-origin loopback Origin header."""

    try:
        parsed = urlsplit(origin)
        origin_port = parsed.port
    except ValueError:
        return False

    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        return False
    if parsed.hostname is None or not is_loopback_host(parsed.hostname):
        return False

    request_host = request.url.hostname
    if request_host is None or not is_loopback_host(request_host):
        return False
    if parsed.scheme != request.url.scheme:
        return False
    if parsed.hostname.casefold() != request_host.casefold():
        return False

    effective_origin_port = origin_port or _default_port(parsed.scheme)
    effective_request_port = request.url.port or _default_port(request.url.scheme)
    return effective_origin_port == effective_request_port


def _json_records(records: Sequence[Mapping[str, Any] | Any]) -> list[Any]:
    """Encode public database records without inspecting arbitrary object attributes."""

    encoded: list[Any] = []
    for record in records:
        if isinstance(record, Mapping):
            encoded.append(jsonable_encoder(dict(record)))
            continue
        model_dump = getattr(record, "model_dump", None)
        if callable(model_dump):
            encoded.append(jsonable_encoder(model_dump(mode="json")))
            continue
        raise TypeError("database returned an unsupported public record type")
    return encoded


def create_app(
    settings: AppSettings | None = None,
    database: ReadStore | None = None,
    api_token: str | None = None,
    task_review_service: ReviewCommandService | None = None,
    task_analysis_service: TaskAnalysisCommandService | None = None,
    codex_source_service: CodexLocalSourceService | None = None,
    display_label_service: ManualDisplayLabelService | None = None,
    static_directory: Path | None = None,
    browser_session_manager: BrowserSessionManager | None = None,
) -> FastAPI:
    """Build the local API without enabling CORS or any remote integrations."""

    resolved_settings = settings or AppSettings.from_env()
    if database is None or api_token is None:
        prepare_app_home(resolved_settings)

    if database is None:
        from .database import Database

        database = Database(Path(resolved_settings.database_path))
    database.initialize()

    resolved_token = api_token
    if resolved_token is None:
        resolved_token = load_or_create_api_token(resolved_settings.api_token_path)
    if len(resolved_token) < 32:
        raise ValueError("local API token is unexpectedly short")

    app = FastAPI(
        title="Prompt Enhancer Local API",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.database = database
    app.state.api_token = resolved_token
    app.state.settings = resolved_settings
    app.state.browser_sessions = browser_session_manager or BrowserSessionManager()

    @app.exception_handler(RequestValidationError)
    async def sanitize_request_validation(
        _request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422, content={"detail": "request validation failed"}
        )

    @app.middleware("http")
    async def enforce_local_request_boundary(request: Request, call_next: Any) -> Any:
        if not _host_header_is_loopback(request.headers.get("host")):
            response = JSONResponse(
                status_code=400, content={"detail": "invalid host"}
            )
        else:
            origin = request.headers.get("origin")
            if origin is not None and not _origin_matches_request(origin, request):
                response = JSONResponse(
                    status_code=403, content={"detail": "origin not allowed"}
                )
            else:
                response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
            "form-action 'self'; object-src 'none'; connect-src 'self'; "
            "img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        )
        return response

    def require_local_token(
        request: Request,
        supplied_token: Annotated[str | None, Header(alias=API_TOKEN_HEADER)] = None,
        supplied_csrf: Annotated[str | None, Header(alias=CSRF_HEADER)] = None,
    ) -> None:
        candidate = supplied_token or ""
        expected = request.app.state.api_token
        token_authenticated = hmac.compare_digest(
            candidate.encode("utf-8"), expected.encode("utf-8")
        )
        if token_authenticated:
            return
        cookie_value = request.cookies.get(BROWSER_SESSION_COOKIE)
        sessions = request.app.state.browser_sessions
        if not sessions.authenticate(cookie_value):
            raise HTTPException(status_code=401, detail="authentication required")
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if origin is None or not _origin_matches_request(origin, request):
                raise HTTPException(
                    status_code=403, detail="same-origin mutation required"
                )
            if not sessions.verify_csrf(cookie_value, supplied_csrf):
                raise HTTPException(status_code=403, detail="CSRF validation failed")

    authenticated = Depends(require_local_token)

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "cost_mode": resolved_settings.cost_mode.value,
            "data_tier": resolved_settings.data_tier.value,
        }

    @app.get("/auth/session", include_in_schema=False)
    def browser_session(request: Request, response: Response) -> dict[str, Any]:
        fetch_site = request.headers.get("sec-fetch-site")
        if fetch_site not in {None, "same-origin", "none"}:
            raise HTTPException(status_code=403, detail="same-origin bootstrap required")
        grant = request.app.state.browser_sessions.issue(
            request.cookies.get(BROWSER_SESSION_COOKIE)
        )
        response.set_cookie(
            key=BROWSER_SESSION_COOKIE,
            value=grant.cookie_value,
            max_age=grant.expires_in_seconds,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="strict",
            path="/",
        )
        return {
            "csrf_token": grant.csrf_token,
            "expires_in_seconds": grant.expires_in_seconds,
        }

    @app.get("/v1/capabilities", dependencies=[authenticated])
    def capabilities() -> dict[str, Any]:
        return {
            "cost_mode": "offline_only",
            "data_tier": "metadata",
            "network_inference": False,
            "raw_transcripts": False,
            "arbitrary_sql": False,
            "write_api": (
                task_review_service is not None
                or task_analysis_service is not None
                or codex_source_service is not None
                or display_label_service is not None
            ),
            "task_review": task_review_service is not None,
            "task_analysis": task_analysis_service is not None,
            "codex_local_source": codex_source_service is not None,
            "manual_display_labels": display_label_service is not None,
            "browser_session": True,
            "demo_provider": "synthetic",
        }

    @app.get("/v1/metrics/definitions", dependencies=[authenticated])
    def metric_definitions(request: Request) -> dict[str, list[Any]]:
        records = request.app.state.database.list_metric_definitions()
        return {"definitions": _json_records(records)}

    @app.get("/v1/sessions", dependencies=[authenticated])
    def sessions(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
        provider: Provider | None = None,
    ) -> dict[str, Any]:
        if provider is None:
            records = request.app.state.database.list_sessions(limit=limit, offset=offset)
        else:
            records = request.app.state.database.list_sessions(
                limit=limit, offset=offset, provider=provider
            )
        return {"sessions": _json_records(records), "limit": limit, "offset": offset}

    @app.get("/v1/sessions/{session_id}/metrics", dependencies=[authenticated])
    def session_metrics(
        request: Request,
        session_id: Annotated[
            str,
            PathParameter(pattern=PSEUDONYM_PATTERN.pattern),
        ],
    ) -> dict[str, Any]:
        records = request.app.state.database.get_session_metrics(session_id)
        return {"session_id": session_id, "metrics": _json_records(records)}

    app.include_router(create_task_query_router(require_local_token))
    if task_review_service is not None:
        app.include_router(create_task_review_router(require_local_token, task_review_service))
    if task_analysis_service is not None:
        app.include_router(
            create_task_analysis_router(require_local_token, task_analysis_service)
        )
    if codex_source_service is not None:
        app.include_router(
            create_local_source_router(require_local_token, codex_source_service)
        )

    if display_label_service is not None:
        app.include_router(
            create_display_label_router(require_local_token, display_label_service)
        )
    if static_directory is not None:
        static_root = lexical_absolute_path(static_directory)
        if (
            path_has_symlink_component(static_root)
            or not static_root.is_dir()
            or not (static_root / "index.html").is_file()
        ):
            raise ValueError("integrated dashboard build is unavailable or unsafe")
        static_files = StaticFiles(directory=static_root, html=True)

        @app.get("/{asset_path:path}", include_in_schema=False)
        async def integrated_dashboard(request: Request, asset_path: str):
            first_segment = asset_path.partition("/")[0]
            if first_segment in {"v1", "auth", "health"}:
                raise HTTPException(status_code=404, detail="not found")
            requested = asset_path or "index.html"
            try:
                response = await static_files.get_response(requested, request.scope)
            except StarletteHTTPException as error:
                if error.status_code != 404:
                    raise
                response = None
            if response is not None and response.status_code != 404:
                return response
            if "text/html" not in request.headers.get("accept", ""):
                raise HTTPException(status_code=404, detail="not found")
            return await static_files.get_response("index.html", request.scope)

    return app
