"""Authenticated, loopback-only HTTP views over the local metadata store."""

from __future__ import annotations

from contextlib import asynccontextmanager
import hmac
import re
from html.parser import HTMLParser
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
from .application.local_sources import (
    ClaudeCodeLocalSourceService,
    CodexLocalSourceService,
)
from .application.analysis.session_text_service import SessionTextAnalysisService
from .application.jobs import AnalysisJobService, AnalysisJobWorker
from .application.automation import AutomationGrantService, AutomationGrantWorker
from .application.analysis.metric_readiness import MetricReadinessService
from .application.analysis.metric_coverage import MetricCoverageService
from .application.analysis.metric_lifecycle_evidence import (
    MetricLifecycleEvidenceService,
)
from .application.analysis.agent_metric_evidence import AgentMetricEvidenceService
from .application.estimators import EstimatorRepository
from .application.analysis.model_link_experiments import (
    SessionModelLinkExperimentService,
)
from .application.analysis.session_model_ensemble import (
    SessionModelEnsembleService,
)
from .application.analysis.model_ensemble_watch import (
    ModelEnsembleWatchService,
    ModelEnsembleWatchWorker,
)
from .application.analysis.project_quality_aggregation import (
    ProjectQualityAggregationService,
)
from .application.providers import ProviderCompatibilityCatalog
from .infrastructure.text_models.jobs import LocalTextModelEvaluationService
from .config import (
    AppSettings,
    is_loopback_host,
    lexical_absolute_path,
    path_has_symlink_component,
    prepare_app_home,
)
from .domain import PSEUDONYM_PATTERN, Provider
from .application.control_plane import ControlPlaneService, PrincipalResolver
from .application.paid_product.contracts import ProductReadiness
from .application.social.contracts import SocialReadiness
from .application.social.ports import SocialPrincipalResolver
from .application.social.service import SocialService
from .application.task_lifecycle import TaskLifecycleService
from .interfaces.http import (
    create_agent_metric_evidence_router,
    create_control_plane_router,
    create_session_analysis_command_router,
    create_session_analysis_query_router,
    create_session_quality_aggregation_router,
    create_project_quality_aggregation_router,
    create_provider_compatibility_router,
    create_metric_readiness_router,
    create_metric_lifecycle_evidence_router,
    create_metric_coverage_router,
    create_research_router,
    create_model_link_experiment_router,
    create_model_ensemble_router,
    create_model_ensemble_watch_router,
    create_analysis_job_router,
    create_automation_grant_router,
    create_estimator_router,
    create_task_query_router,
    create_task_lifecycle_router,
    create_paid_product_readiness_router,
    create_social_mutation_router,
    create_social_readiness_router,
)
from .interfaces.http.browser_session import (
    BROWSER_SESSION_COOKIE,
    CSRF_HEADER,
    BrowserSessionManager,
)
from .interfaces.http.desktop_identity import (
    DESKTOP_CHALLENGE_HEADER,
    DESKTOP_IDENTITY_PATH,
    DESKTOP_IDENTITY_VERSION,
    desktop_identity_proof,
    exact_request_loopback_origin,
    parse_desktop_challenge,
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
from .interfaces.http.claude_local_source_routes import (
    create_claude_local_source_router,
)
from .interfaces.http.otlp_ingest_routes import create_otlp_ingest_router
from .interfaces.http.session_reader_routes import create_session_reader_router
from .interfaces.http.onboarding_routes import create_onboarding_router
from .interfaces.http.display_label_routes import create_display_label_router
from .interfaces.http.dto import (
    CapabilitiesDto,
    ProjectSessionCatalogResponse,
    SessionCatalogItemDto,
    SessionCatalogListResponse,
)
from .interfaces.http.spa_routes import is_spa_navigation_path
from .privacy import load_or_create_api_token


API_TOKEN_HEADER = "X-Prompt-Enhancer-Token"

_HASHED_STATIC_ASSET_PATTERN = re.compile(
    r"assets/[A-Za-z0-9][A-Za-z0-9._-]{0,95}-[A-Za-z0-9_-]{8,64}"
    r"\.[A-Za-z0-9]{1,8}"
)
_HASHED_MODULE_ASSET_PATTERN = re.compile(
    r"/?(assets/[A-Za-z0-9][A-Za-z0-9._-]{0,95}-[A-Za-z0-9_-]{8,64}\.js)"
)


class _ModuleScriptCollector(HTMLParser):
    """Collect module-script sources without executing or resolving HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sources: list[str | None] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag.casefold() != "script":
            return
        type_values = [value for name, value in attrs if name == "type"]
        if (
            len(type_values) != 1
            or (type_values[0] or "").strip().casefold() != "module"
        ):
            return
        src_values = [value for name, value in attrs if name == "src"]
        self.sources.append(src_values[0] if len(src_values) == 1 else None)


def _static_app_revision(static_root: Path) -> str:
    """Return the one safe, content-free module asset named by ``index.html``."""

    index_path = static_root / "index.html"
    try:
        if index_path.is_symlink():
            raise ValueError("integrated dashboard build is unavailable or unsafe")
        markup = index_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ValueError(
            "integrated dashboard build is unavailable or unsafe"
        ) from error

    collector = _ModuleScriptCollector()
    try:
        collector.feed(markup)
        collector.close()
    except Exception as error:
        raise ValueError(
            "integrated dashboard build is unavailable or unsafe"
        ) from error
    if len(collector.sources) != 1 or collector.sources[0] is None:
        raise ValueError("integrated dashboard build is unavailable or unsafe")

    match = _HASHED_MODULE_ASSET_PATTERN.fullmatch(collector.sources[0])
    if match is None:
        raise ValueError("integrated dashboard build is unavailable or unsafe")
    revision = match.group(1)
    if ".." in revision:
        raise ValueError("integrated dashboard build is unavailable or unsafe")
    module_path = static_root.joinpath(*revision.split("/"))
    try:
        module_is_unsafe = (
            path_has_symlink_component(module_path)
            or module_path.is_symlink()
            or not module_path.is_file()
        )
    except OSError as error:
        raise ValueError(
            "integrated dashboard build is unavailable or unsafe"
        ) from error
    if module_is_unsafe:
        raise ValueError("integrated dashboard build is unavailable or unsafe")
    return revision


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
        project_id: str | None = None,
    ) -> list[dict[str, Any]]: ...

    def count_sessions(
        self,
        *,
        provider: Provider | None = None,
        project_id: str | None = None,
    ) -> int: ...

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
    task_lifecycle_service: TaskLifecycleService | None = None,
    metric_lifecycle_evidence_service: MetricLifecycleEvidenceService | None = None,
    task_analysis_service: TaskAnalysisCommandService | None = None,
    session_text_analysis_service: SessionTextAnalysisService | None = None,
    session_model_link_experiment_service: SessionModelLinkExperimentService | None = None,
    session_model_ensemble_service: SessionModelEnsembleService | None = None,
    model_ensemble_watch_service: ModelEnsembleWatchService | None = None,
    model_ensemble_watch_worker: ModelEnsembleWatchWorker | None = None,
    project_quality_aggregation_service: ProjectQualityAggregationService | None = None,
    provider_compatibility_catalog: ProviderCompatibilityCatalog | None = None,
    metric_readiness_service: MetricReadinessService | None = None,
    metric_coverage_service: MetricCoverageService | None = None,
    codex_source_service: CodexLocalSourceService | None = None,
    claude_source_service: ClaudeCodeLocalSourceService | None = None,
    otlp_ingest_token: str | None = None,
    telemetry_ingest_service=None,
    session_reader_service=None,
    onboarding_service=None,
    calibration_rating_service=None,
    objective_overrides_provider=None,
    local_source_refresh_worker=None,
    display_label_service: ManualDisplayLabelService | None = None,
    model_evaluation_service: LocalTextModelEvaluationService | None = None,
    analysis_job_service: AnalysisJobService | None = None,
    analysis_job_worker: AnalysisJobWorker | None = None,
    automation_grant_service: AutomationGrantService | None = None,
    automation_grant_worker: AutomationGrantWorker | None = None,
    control_plane_service: ControlPlaneService | None = None,
    control_plane_principal_resolver: PrincipalResolver | None = None,
    paid_product_readiness: ProductReadiness | None = None,
    social_readiness: SocialReadiness | None = None,
    social_service: SocialService | None = None,
    social_principal_resolver: SocialPrincipalResolver | None = None,
    estimator_repository: EstimatorRepository | None = None,
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

    @asynccontextmanager
    async def local_lifespan(_app: FastAPI):
        if analysis_job_worker is not None:
            analysis_job_worker.start()
        if automation_grant_worker is not None:
            automation_grant_worker.start()
        if model_ensemble_watch_worker is not None:
            model_ensemble_watch_worker.start()
        if local_source_refresh_worker is not None:
            local_source_refresh_worker.start()
        try:
            yield
        finally:
            if local_source_refresh_worker is not None:
                local_source_refresh_worker.stop()
            if model_ensemble_watch_worker is not None:
                model_ensemble_watch_worker.stop()
            if automation_grant_worker is not None:
                automation_grant_worker.stop()
            if analysis_job_worker is not None:
                analysis_job_worker.stop()

    app = FastAPI(
        title="Prompt Enhancer Local API",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=local_lifespan,
    )
    app.state.database = database

    def _session_provider(session_id: str) -> Provider:
        """The catalog's provider for a session (Codex when unknown)."""

        try:
            record = database.get_session(session_id) if database is not None else None
        except Exception:
            record = None
        return record.provider if record is not None else Provider.CODEX
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
        static_asset = request.url.path.removeprefix("/")
        if any(
            marker in request.url.path
            for marker in (
                "quality-analysis-previews",
                "model-ensemble-runs",
                "model-ensemble-watch",
                "model-ensemble-watches",
                "model-ensemble-attempts",
                "model-ensemble-head",
                "model-ensemble-snapshots",
                "/metric-lifecycle-evidence",
                "metric-coverage",
                "/analysis-jobs",
                "/automation-grants",
                "/control-plane",
                "/paid-product",
                "/social",
                "/estimators",
                "/text-model-compatibility",
                "/text-model-runtime",
                "/task-lifecycles",
                "/lifecycle",
                "/agent-metric-evidence",
            )
        ):
            response.headers["Cache-Control"] = "no-store, private"
            response.headers["Pragma"] = "no-cache"
        elif (
            200 <= response.status_code < 300
            and _HASHED_STATIC_ASSET_PATTERN.fullmatch(static_asset) is not None
            and ".." not in static_asset
        ):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
            "form-action 'self'; object-src 'none'; connect-src 'self'; "
            "img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'"
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

    @app.get(DESKTOP_IDENTITY_PATH, include_in_schema=False)
    def desktop_identity(
        request: Request,
        challenge: Annotated[
            str | None, Header(alias=DESKTOP_CHALLENGE_HEADER)
        ] = None,
    ) -> dict[str, Any]:
        """Prove knowledge of the local token to the native launcher.

        The launcher never sends the token here.  It sends a fresh random
        challenge and checks the keyed, origin-bound answer locally, so a port
        squatter learns nothing it can reuse and a relay to another loopback
        instance fails the origin binding.  This endpoint grants no access.
        """

        fetch_site = request.headers.get("sec-fetch-site")
        if fetch_site not in {None, "same-origin", "none"}:
            raise HTTPException(status_code=403, detail="native launcher only")
        parsed_challenge = parse_desktop_challenge(challenge)
        if parsed_challenge is None:
            raise HTTPException(status_code=400, detail="invalid desktop challenge")
        origin = exact_request_loopback_origin(
            request.headers.get("host"), request.scope.get("server")
        )
        if origin is None:
            raise HTTPException(
                status_code=403,
                detail="exact loopback authority required",
            )
        return {
            "identity_version": DESKTOP_IDENTITY_VERSION,
            "proof": desktop_identity_proof(
                request.app.state.api_token, origin, parsed_challenge
            ),
        }

    @app.get(
        "/v1/capabilities",
        dependencies=[authenticated],
        response_model=CapabilitiesDto,
    )
    def capabilities() -> CapabilitiesDto:
        write_api = (
            task_review_service is not None
            or task_lifecycle_service is not None
            or task_analysis_service is not None
            or session_text_analysis_service is not None
            or session_model_link_experiment_service is not None
            or provider_compatibility_catalog is not None
            or codex_source_service is not None
            or claude_source_service is not None
            or display_label_service is not None
            or model_evaluation_service is not None
        )
        session_text_analysis = session_text_analysis_service is not None
        return CapabilitiesDto(
            cost_mode="offline_only",
            data_tier="metadata",
            network_inference=False,
            raw_transcripts=(
                session_reader_service is not None and session_reader_service.enabled
            ),
            arbitrary_sql=False,
            write_api=write_api,
            task_review=task_review_service is not None,
            task_lifecycle=task_lifecycle_service is not None,
            task_analysis=task_analysis_service is not None,
            session_text_analysis=session_text_analysis,
            session_model_link_experiment=(
                session_model_link_experiment_service is not None
            ),
            session_text_analysis_data_tier=(
                "redacted_content" if session_text_analysis else None
            ),
            session_text_content_persistence=False,
            codex_local_source=codex_source_service is not None,
            claude_code_local_source=claude_source_service is not None,
            manual_display_labels=display_label_service is not None,
            browser_session=True,
            demo_provider="synthetic",
        )

    @app.get("/v1/metrics/definitions", dependencies=[authenticated])
    def metric_definitions(request: Request) -> dict[str, list[Any]]:
        records = request.app.state.database.list_metric_definitions()
        return {"definitions": _json_records(records)}

    @app.get(
        "/v1/sessions",
        dependencies=[authenticated],
        response_model=SessionCatalogListResponse,
    )
    def sessions(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
        provider: Provider | None = None,
    ) -> SessionCatalogListResponse:
        if provider is None:
            records = request.app.state.database.list_sessions(limit=limit, offset=offset)
        else:
            records = request.app.state.database.list_sessions(
                limit=limit, offset=offset, provider=provider
            )
        return SessionCatalogListResponse(
            sessions=tuple(SessionCatalogItemDto.from_record(item) for item in records),
            limit=limit,
            offset=offset,
        )

    @app.get(
        "/v1/projects/{project_id}/sessions",
        dependencies=[authenticated],
        response_model=ProjectSessionCatalogResponse,
    )
    def project_sessions(
        request: Request,
        project_id: Annotated[
            str,
            PathParameter(pattern=PSEUDONYM_PATTERN.pattern),
        ],
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
        provider: Provider | None = None,
    ) -> ProjectSessionCatalogResponse:
        records = request.app.state.database.list_sessions(
            limit=limit,
            offset=offset,
            provider=provider,
            project_id=project_id,
        )
        total = request.app.state.database.count_sessions(
            provider=provider,
            project_id=project_id,
        )
        return ProjectSessionCatalogResponse(
            sessions=tuple(SessionCatalogItemDto.from_record(item) for item in records),
            limit=limit,
            offset=offset,
            total=total,
            has_more=offset + len(records) < total,
        )

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
    app.include_router(
        create_task_lifecycle_router(require_local_token, task_lifecycle_service)
    )
    if metric_lifecycle_evidence_service is not None:
        app.include_router(
            create_metric_lifecycle_evidence_router(
                require_local_token,
                metric_lifecycle_evidence_service,
            )
        )
        app.include_router(
            create_agent_metric_evidence_router(
                require_local_token,
                AgentMetricEvidenceService(metric_lifecycle_evidence_service),
            )
        )
    app.include_router(
        create_session_analysis_query_router(
            require_local_token, objective_overrides=objective_overrides_provider
        )
    )
    app.include_router(create_session_quality_aggregation_router(require_local_token))
    if project_quality_aggregation_service is not None:
        app.include_router(
            create_project_quality_aggregation_router(
                require_local_token,
                project_quality_aggregation_service,
            )
        )
    app.include_router(
        create_research_router(require_local_token, model_evaluation_service)
    )
    if estimator_repository is not None:
        app.include_router(
            create_estimator_router(require_local_token, estimator_repository)
        )
    if provider_compatibility_catalog is not None:
        app.include_router(
            create_provider_compatibility_router(
                require_local_token,
                provider_compatibility_catalog,
            )
        )
    if metric_readiness_service is not None:
        app.include_router(
            create_metric_readiness_router(
                require_local_token,
                metric_readiness_service,
            )
        )
    if metric_coverage_service is not None:
        app.include_router(
            create_metric_coverage_router(
                require_local_token,
                metric_coverage_service,
            )
        )
    if session_text_analysis_service is not None:
        app.include_router(
            create_session_analysis_command_router(
                require_local_token,
                session_text_analysis_service,
                provider_resolver=_session_provider,
            )
        )
    if analysis_job_service is not None:
        app.include_router(
            create_analysis_job_router(require_local_token, analysis_job_service)
        )
    if automation_grant_service is not None:
        app.include_router(
            create_automation_grant_router(
                require_local_token,
                automation_grant_service,
            )
        )
    # Three independent gates: an operator must opt in through settings, the
    # composition root must have built a service, and a principal resolver must
    # exist. Without a resolver there is no way to verify who is calling, so no
    # route is mounted at all rather than mounting one that trusts a body.
    if (
        control_plane_service is not None
        and control_plane_principal_resolver is not None
        and resolved_settings.control_plane_development_api
    ):
        app.include_router(
            create_control_plane_router(
                require_local_token,
                control_plane_service,
                control_plane_principal_resolver,
            )
        )
    # Readiness is intentionally the only paid-product browser surface. Both
    # an exact operator opt-in and an explicitly composed receipt are required;
    # identity, billing, approval, and hosted-analysis commands stay unmounted.
    if (
        paid_product_readiness is not None
        and resolved_settings.paid_product_development_api
    ):
        app.include_router(
            create_paid_product_readiness_router(
                require_local_token,
                paid_product_readiness,
            )
        )
    # Social routes are default-off and never self-compose. Readiness needs the
    # exact operator opt-in plus an explicitly supplied receipt; mutations need
    # the opt-in plus both a service and a principal resolver. Nothing here
    # opens social.sqlite3, and a browser session or local token alone can
    # never act as a social principal.
    if social_readiness is not None and resolved_settings.social_development_api:
        app.include_router(
            create_social_readiness_router(require_local_token, social_readiness)
        )
    if (
        social_service is not None
        and social_principal_resolver is not None
        and resolved_settings.social_development_api
    ):
        app.include_router(
            create_social_mutation_router(
                require_local_token,
                social_service,
                social_principal_resolver,
            )
        )
    if session_model_link_experiment_service is not None:
        app.include_router(
            create_model_link_experiment_router(
                require_local_token,
                session_model_link_experiment_service,
                provider_resolver=_session_provider,
            )
        )
    if session_model_ensemble_service is not None:
        app.include_router(
            create_model_ensemble_router(
                require_local_token,
                session_model_ensemble_service,
                provider_resolver=_session_provider,
            )
        )
    if (
        model_ensemble_watch_service is not None
        and session_model_ensemble_service is not None
    ):
        app.include_router(
            create_model_ensemble_watch_router(
                require_local_token,
                model_ensemble_watch_service,
                session_model_ensemble_service,
            )
        )
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
    if claude_source_service is not None:
        app.include_router(
            create_claude_local_source_router(
                require_local_token, claude_source_service
            )
        )
    if otlp_ingest_token is not None and telemetry_ingest_service is not None:
        app.include_router(
            create_otlp_ingest_router(otlp_ingest_token, telemetry_ingest_service)
        )
    if calibration_rating_service is not None:
        from .interfaces.http.calibration_routes import create_calibration_router

        app.include_router(create_calibration_router(require_local_token, calibration_rating_service))
    if session_reader_service is not None and session_reader_service.enabled:
        app.include_router(
            create_session_reader_router(require_local_token, session_reader_service)
        )
    if onboarding_service is not None:
        app.include_router(create_onboarding_router(require_local_token, onboarding_service))

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
        _static_app_revision(static_root)
        static_files = StaticFiles(directory=static_root, html=True)

        @app.api_route(
            "/app-revision.json", methods=["GET", "HEAD"], include_in_schema=False
        )
        def integrated_dashboard_revision() -> JSONResponse:
            try:
                revision = _static_app_revision(static_root)
            except ValueError:
                return JSONResponse(
                    status_code=503,
                    content={"detail": "dashboard revision temporarily unavailable"},
                )
            return JSONResponse(content={"revision": revision})

        @app.api_route(
            "/{asset_path:path}", methods=["GET", "HEAD"], include_in_schema=False
        )
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
            if not is_spa_navigation_path(asset_path):
                raise HTTPException(status_code=404, detail="not found")
            return await static_files.get_response("index.html", request.scope)

    return app
