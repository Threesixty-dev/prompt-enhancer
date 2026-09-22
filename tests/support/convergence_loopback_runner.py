"""Run the production dashboard against one disposable real loopback API.

The host uses only reserved-example state created below. Provider probes,
provider adapters, external model runtimes, and native mutation authority are
disabled. Child processes use Windows' no-window creation flag so this gate
cannot reproduce the terminal-window storm that affected earlier manual runs.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from typing import Iterator
import urllib.request


REPOSITORY = Path(__file__).resolve().parents[2]
FRONTEND = REPOSITORY / "frontend"
RESULTS = REPOSITORY / "test-results"
PLAYWRIGHT_CLI = FRONTEND / "node_modules" / "@playwright" / "test" / "cli.js"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PYTHON_HANDOFF = "PE_CONVERGENCE_PYTHON_HANDOFF"
RECOVERY_PROJECT = "Recovery example project"
RECOVERY_CHAT = "Recovered example chat"
CATALOG_PAGE_SIZE = 100
CATALOG_SEED_COUNT = CATALOG_PAGE_SIZE + 1

sys.path.insert(0, str(REPOSITORY / "src"))


@dataclass(frozen=True, slots=True)
class GateResult:
    browser_exit_code: int
    startup_ready: bool
    startup_failure_component: str | None
    listener_released: bool
    runtime_cleanup_confirmed: bool
    model_runtimes_remaining: int
    temporary_state_removed: bool
    server_thread_failed: bool

    @property
    def passed(self) -> bool:
        return (
            self.browser_exit_code == 0
            and self.startup_ready
            and self.startup_failure_component is None
            and self.listener_released
            and self.runtime_cleanup_confirmed
            and self.model_runtimes_remaining == 0
            and self.temporary_state_removed
            and not self.server_thread_failed
        )


def _run_child(
    argv: list[str],
    *,
    cwd: Path,
    environment: dict[str, str] | None = None,
    redactions: tuple[tuple[str, str], ...] = (),
) -> int:
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            env=environment,
            check=False,
            shell=False,
            creationflags=CREATE_NO_WINDOW,
            capture_output=bool(redactions),
            text=bool(redactions),
            encoding="utf-8" if redactions else None,
            errors="replace" if redactions else None,
        )
    except OSError:
        return 127
    if redactions:
        output = f"{completed.stdout or ''}{completed.stderr or ''}"
        for private, replacement in redactions:
            output = output.replace(private, replacement)
        if output.strip():
            output_encoding = sys.stdout.encoding or "utf-8"
            safe_output = output.encode(
                output_encoding,
                errors="backslashreplace",
            ).decode(output_encoding)
            print(safe_output.rstrip(), flush=True)
    return int(completed.returncode)


def _node_executable() -> str | None:
    return shutil.which("node.exe") or shutil.which("node")


def _npm_command() -> list[str] | None:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    return None if npm is None else [npm]


def _repository_python(repository: Path = REPOSITORY) -> Path | None:
    """Return the repo-managed interpreter when one exists.

    The npm entrypoint may be launched from an unactivated shell. Prefer the
    checked-out virtual environment so the gate uses the same dependency set as
    the backend tests, without opening a terminal window.
    """

    for relative in (
        Path(".venv") / "Scripts" / "python.exe",
        Path(".venv") / "bin" / "python",
    ):
        candidate = repository / relative
        if candidate.is_file():
            return candidate
    return None


def _handoff_to_repository_python(argv: list[str]) -> int | None:
    if os.environ.get(PYTHON_HANDOFF) == "1":
        return None
    interpreter = _repository_python()
    if interpreter is None:
        return None
    try:
        if interpreter.resolve() == Path(sys.executable).resolve():
            return None
    except OSError:
        return None
    environment = os.environ.copy()
    environment[PYTHON_HANDOFF] = "1"
    return _run_child(
        [str(interpreter), str(Path(__file__).resolve()), *argv],
        cwd=REPOSITORY,
        environment=environment,
        redactions=((str(REPOSITORY), "<repository>"),),
    )


def _build_dashboard() -> int:
    npm = _npm_command()
    if npm is None:
        return 127
    return _run_child([*npm, "run", "build"], cwd=FRONTEND)


def _reserve_listener() -> tuple[socket.socket, int]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.set_inheritable(False)
        listener.bind(("127.0.0.1", 0))
        return listener, int(listener.getsockname()[1])
    except BaseException:
        listener.close()
        raise


def _loopback_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def _wait_until_ready(origin: str, thread: threading.Thread) -> bool:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + 20
    while thread.is_alive() and time.monotonic() < deadline:
        request = urllib.request.Request(
            f"{origin}/health",
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with opener.open(request, timeout=0.5) as response:
                if response.status == 200 and response.read(1):
                    return True
        except Exception:
            threading.Event().wait(0.05)
    return False


def _seed_retained_history(application: object, workspace: Path) -> None:
    from prompt_enhancer.application.agent_catalog import (
        AgentRetentionPolicy,
        CreateAgentProject,
    )
    from prompt_enhancer.application.local_agent import (
        AgentSettings,
        LocalAgentService,
        SendMessage,
    )

    catalog = application.create_agent_catalog_service()  # type: ignore[attr-defined]
    project = catalog.create_project(CreateAgentProject(name=RECOVERY_PROJECT))

    def synthetic_chat(_alias: str, _body: bytes) -> tuple[int, bytes, str]:
        payload = {
            "choices": [{
                "message": {"content": "Synthetic retained answer from the disposable gate."},
                "finish_reason": "stop",
            }]
        }
        return 200, json.dumps(payload).encode("utf-8"), "application/json"

    service = LocalAgentService(
        chat=synthetic_chat,
        active_model=lambda: "example-model",
        model_ready=lambda alias: alias == "example-model",
        allowed_roots=(workspace,),
        catalog=catalog,
    )
    created = service.create(AgentSettings(
        workspace=str(workspace),
        project_id=project.project_id,
        model_alias="example-model",
        title=RECOVERY_CHAT,
        retention_policy=AgentRetentionPolicy.LOCAL_HISTORY,
        allow_writes=False,
        allow_commands=False,
        allow_web=False,
    ))
    service.send(
        created.session_id,
        SendMessage(text="Synthetic retained request from the disposable gate."),
    )
    deadline = time.monotonic() + 5
    while service.get(created.session_id).running and time.monotonic() < deadline:
        threading.Event().wait(0.01)
    if service.get(created.session_id).running:
        service.shutdown()
        raise RuntimeError("synthetic_history_seed_timeout")
    service.delete(created.session_id)
    service.shutdown()


def _seed_cp34_native_unavailable(settings: object) -> tuple[str, str, str]:
    """Create one sealed, fictional R8 run without a native-result authority.

    The production bootstrap must use the same disposable pseudonym key as the
    existing R8 fixture.  This keeps the normal repository fingerprint checks
    active: it is not an identity-validation bypass.  The fixture records only
    revision-zero reviewed opportunities and never invokes a model, provider,
    command, native presence, or objective-result issuance path.
    """

    from prompt_enhancer.application.analysis.session_model_ensemble import (
        SessionModelEnsembleOutcome,
    )
    from prompt_enhancer.config import prepare_app_home
    from prompt_enhancer.privacy import _create_private_file

    tests_directory = REPOSITORY / "tests"
    if str(tests_directory) not in sys.path:
        sys.path.insert(0, str(tests_directory))
    from test_model_ensemble_r8_persistence import _r8_record, _r8_setup

    # The temporary application directory is new for this runner invocation.
    # Use the existing exclusive private-file helper, rather than overwriting
    # or reading any owner key, before normal bootstrap loads it.
    prepare_app_home(settings)  # type: ignore[arg-type]
    _create_private_file(
        settings.pseudonym_key_path,  # type: ignore[attr-defined]
        bytes(range(32)),
    )
    (
        database,
        source,
        plan_snapshot,
        action_snapshot,
        _verification_service,
        verification_snapshot,
    ) = _r8_setup(settings.home)  # type: ignore[attr-defined]
    if database.path != settings.database_path:  # type: ignore[attr-defined]
        raise RuntimeError("cp34_seed_database_path_mismatch")
    if verification_snapshot.revision != 0 or verification_snapshot.evidence.verification_results:
        raise RuntimeError("cp34_seed_must_not_issue_objective_result")
    record = _r8_record(
        source.session_id,
        # The source setup uses ``e``; retain a different valid pseudonym.
        run_character="d",
        request_character="7",
        plan_snapshot=plan_snapshot,
        action_snapshot=action_snapshot,
        verification_snapshot=verification_snapshot,
    )
    database.model_ensemble_repository().save_completed(record)
    session = next(
        (
            item
            for item in database.list_sessions(limit=20)
            if item["session_id"] == source.session_id
        ),
        None,
    )
    if session is None or not isinstance(session.get("project_id"), str):
        raise RuntimeError("cp34_seed_session_missing")
    project_id = session["project_id"]

    # Publish through the normal watch lease path. The dashboard reads this
    # canonical head rather than an unowned standalone run. Disabling the
    # completed watch leaves its sealed head readable while ensuring this
    # synthetic fixture can never be claimed by a worker.
    now = datetime(2043, 1, 2, tzinfo=UTC)
    watches = database.model_ensemble_watch_repository()
    watch_id = "c" * 64
    watches.enable(
        watch_id=watch_id,
        provider=record.provider,
        project_id=project_id,
        session_id=source.session_id,
        max_messages=25,
        now=now,
    )
    claimed = watches.claim_due(
        owner="b" * 64,
        now=now,
        lease_duration=timedelta(minutes=30),
    )
    if claimed is None:
        raise RuntimeError("cp34_seed_watch_not_claimable")
    _running, lease = claimed
    watches.complete(
        lease,
        now=now + timedelta(seconds=1),
        next_check_at=now + timedelta(days=1),
        outcome=SessionModelEnsembleOutcome(run=record, applied=True),
    )
    head = watches.canonical_head(watch_id)
    if head.head_run_id != record.run_id:
        raise RuntimeError("cp34_seed_canonical_head_missing")
    watches.disable(watch_id, now=now + timedelta(seconds=2))
    retained_head = watches.canonical_head(watch_id)
    if retained_head.head_run_id != record.run_id:
        raise RuntimeError("cp34_seed_canonical_head_not_retained")
    return source.session_id, project_id, record.run_id


def _assert_cp34_seed_head(
    http_app: object,
    *,
    session_id: str,
    expected_run_id: str,
) -> None:
    """Read the published synthetic head without entering the app lifespan.

    ``ASGITransport`` exercises the production browser-authenticated route but
    does not start runtime lifecycle workers. This is a narrow preflight for
    the seed and is intentionally callable independently of Playwright.
    """

    import asyncio

    import httpx

    async def read_head() -> None:
        transport = httpx.ASGITransport(app=http_app)  # type: ignore[arg-type]
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://127.0.0.1",
            follow_redirects=False,
            trust_env=False,
        ) as client:
            bootstrap = await client.get(
                "/auth/session",
                headers={"Sec-Fetch-Site": "same-origin"},
            )
            if bootstrap.status_code != 200:
                raise RuntimeError("cp34_seed_browser_auth_failed")
            response = await client.get(
                f"/v2/sessions/{session_id}/model-ensemble-head",
            )
        if response.status_code != 200:
            raise RuntimeError("cp34_seed_head_route_unavailable")
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("head_run_id") != expected_run_id:
            raise RuntimeError("cp34_seed_head_route_mismatch")
        watch = payload.get("watch")
        if not isinstance(watch, dict) or watch.get("session_id") != session_id:
            raise RuntimeError("cp34_seed_head_session_mismatch")

    asyncio.run(read_head())


def verify_cp34_native_unavailable_seed() -> None:
    """Exercise the CP34 seed and canonical read without starting a server.

    This shares the loopback runner's disposable bootstrap guards, but does
    not enter the ASGI lifespan, bind a listener, or launch Playwright.
    """

    from prompt_enhancer.application.local_models import HardwareSummary, LocalModelService
    from prompt_enhancer.bootstrap import LocalApplication, bootstrap_local_application
    from prompt_enhancer.config import AppSettings
    from prompt_enhancer.infrastructure.providers.codex_app_server import (
        CodexInstalledSchemaProbe,
        CodexSchemaPreflightResult,
        CodexSchemaPreflightStatus,
    )

    class IsolatedSettings(AppSettings):
        @property
        def local_models_dir(self) -> Path:
            return self.home / "local-models"

    RESULTS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="convergence-cp34-seed-",
        dir=RESULTS,
    ) as temporary:
        root = Path(temporary)
        with _isolated_environment(root):
            settings = IsolatedSettings(
                home=root / "application",
                host="127.0.0.1",
                port=8765,
                session_reader_enabled=False,
            )
            models = LocalModelService(
                settings.local_models_dir,
                llama_server=lambda: None,
                hardware=lambda _binary: HardwareSummary(),
            )
            originals = {
                "claude_home": LocalApplication.__dict__["claude_home"],
                "create_local_model_service": LocalApplication.__dict__["create_local_model_service"],
                "create_codex_adapter": LocalApplication.__dict__["create_codex_adapter"],
                "probe": CodexInstalledSchemaProbe.__dict__["probe"],
            }

            def provider_access_forbidden(*_args: object, **_kwargs: object) -> object:
                raise RuntimeError("disposable_gate_provider_access_forbidden")

            try:
                LocalApplication.claude_home = lambda _self: root / "empty-provider"
                LocalApplication.create_local_model_service = lambda _self: models
                LocalApplication.create_codex_adapter = staticmethod(provider_access_forbidden)
                CodexInstalledSchemaProbe.probe = lambda _self: CodexSchemaPreflightResult(
                    status=CodexSchemaPreflightStatus.UNAVAILABLE,
                )
                session_id, _project_id, run_id = _seed_cp34_native_unavailable(settings)
                application = bootstrap_local_application(settings)
                http_app = application.create_http_app()
                _assert_cp34_seed_head(
                    http_app,
                    session_id=session_id,
                    expected_run_id=run_id,
                )
                watches = application.database.model_ensemble_watch_repository()
                watch = watches.get_for_session(session_id)
                if watch is None or watch.state.value != "disabled":
                    raise RuntimeError("cp34_seed_watch_not_disabled")
                if watches.claim_due(
                    owner="a" * 64,
                    now=datetime(2043, 1, 4, tzinfo=UTC),
                    lease_duration=timedelta(minutes=30),
                ) is not None:
                    raise RuntimeError("cp34_seed_created_claimable_work")
            finally:
                LocalApplication.claude_home = originals["claude_home"]
                LocalApplication.create_local_model_service = originals[
                    "create_local_model_service"
                ]
                LocalApplication.create_codex_adapter = originals["create_codex_adapter"]
                CodexInstalledSchemaProbe.probe = originals["probe"]
                models.shutdown()


def _catalog_id(label: str) -> str:
    """Return a deterministic pseudonym for a disposable catalog fixture."""

    return hashlib.sha256(
        f"reserved-cp15-catalog:{label}".encode("utf-8")
    ).hexdigest()


def _seed_indexed_catalog(application: object) -> None:
    """Seed only fictional metadata for the real analytics catalog paging gate."""

    from prompt_enhancer.domain import Provider, SafeSession, SessionState

    database = application.database  # type: ignore[attr-defined]
    newest = datetime(2041, 1, 1, tzinfo=UTC)
    for index in range(CATALOG_SEED_COUNT):
        started_at = newest - timedelta(minutes=index)
        database.persist_session(
            SafeSession(
                provider=Provider.SYNTHETIC,
                installation_id=_catalog_id("installation"),
                project_id=_catalog_id(f"project:{index:03}"),
                session_id=_catalog_id(f"session:{index:03}"),
                provider_version="synthetic-cp15-v1",
                adapter_version="synthetic-cp15-v1",
                source_schema_version="synthetic-cp15-v1",
                started_at=started_at,
                ended_at=None,
                terminal_state=SessionState.UNKNOWN,
                events_complete=False,
                project_display_name=f"Catalog page {index + 1:03}",
                session_display_name=f"Catalog session {index + 1:03}",
            ),
            (),
        )


@contextmanager
def _isolated_environment(root: Path) -> Iterator[None]:
    names = (
        "CODEX_HOME",
        "CLAUDE_CONFIG_DIR",
        "PROMPT_ENHANCER_LOCAL_MODELS_DIR",
    )
    previous = {name: os.environ.get(name) for name in names}
    empty_provider = root / "empty-provider"
    empty_provider.mkdir()
    os.environ["CODEX_HOME"] = str(empty_provider)
    os.environ["CLAUDE_CONFIG_DIR"] = str(empty_provider)
    os.environ["PROMPT_ENHANCER_LOCAL_MODELS_DIR"] = str(root / "application" / "local-models")
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _run_browser_gate(
    origin: str,
    workspace: Path,
    *,
    verification_session_id: str,
    verification_project_id: str,
) -> int:
    node = _node_executable()
    if node is None or not PLAYWRIGHT_CLI.is_file():
        return 127
    environment = os.environ.copy()
    environment.update({
        "PE_CONVERGENCE_BASE_URL": origin,
        "PE_CONVERGENCE_WORKSPACE": str(workspace),
        "PE_CP34_VERIFICATION_SESSION": verification_session_id,
        "PE_CP34_VERIFICATION_PROJECT": verification_project_id,
        "FORCE_COLOR": "0",
    })
    environment.pop("NO_COLOR", None)
    return _run_child(
        [
            node,
            str(PLAYWRIGHT_CLI),
            "test",
            "--config=playwright.loopback.config.ts",
            "--workers=1",
        ],
        cwd=FRONTEND,
        environment=environment,
        redactions=((str(workspace), "<synthetic-workspace>"), (origin, "<loopback>")),
    )


def run(*, build: bool = True) -> GateResult:
    if build:
        build_exit = _build_dashboard()
        if build_exit != 0:
            return GateResult(build_exit, False, None, True, True, 0, True, False)

    from prompt_enhancer.application.local_models import HardwareSummary, LocalModelService
    from prompt_enhancer.bootstrap import LocalApplication, bootstrap_local_application
    from prompt_enhancer.config import AppSettings
    from prompt_enhancer.infrastructure.providers.codex_app_server import (
        CodexInstalledSchemaProbe,
        CodexSchemaPreflightResult,
        CodexSchemaPreflightStatus,
    )
    import uvicorn

    logging.disable(logging.CRITICAL)
    RESULTS.mkdir(exist_ok=True)
    temporary_root: Path | None = None
    browser_exit = 1
    startup_ready = False
    startup_failure_component: str | None = None
    listener_released = False
    cleanup_confirmed = False
    model_runtimes_remaining = -1
    server_thread_failed = False

    class IsolatedSettings(AppSettings):
        @property
        def local_models_dir(self) -> Path:
            return self.home / "local-models"

    with tempfile.TemporaryDirectory(prefix="convergence-loopback-", dir=RESULTS) as temporary:
        temporary_root = Path(temporary)
        workspace = temporary_root / "example-workspace"
        workspace.mkdir()
        (workspace / "example.txt").write_text(
            "EXAMPLE_WORKSPACE_OK\n",
            encoding="utf-8",
        )
        listener, port = _reserve_listener()
        origin = f"http://127.0.0.1:{port}"
        server: uvicorn.Server | None = None
        thread: threading.Thread | None = None
        application = None
        http_app = None
        models: LocalModelService | None = None
        verification_session_id = ""
        verification_project_id = ""
        verification_run_id = ""
        with _isolated_environment(temporary_root):
            try:
                settings = IsolatedSettings(
                    home=temporary_root / "application",
                    host="127.0.0.1",
                    port=port,
                    session_reader_enabled=False,
                )
                models = LocalModelService(
                    settings.local_models_dir,
                    llama_server=lambda: None,
                    hardware=lambda _binary: HardwareSummary(),
                )
                LocalApplication.claude_home = lambda _self: temporary_root / "empty-provider"
                LocalApplication.create_local_model_service = lambda _self: models

                def provider_access_forbidden(*_args: object, **_kwargs: object) -> object:
                    raise RuntimeError("disposable_gate_provider_access_forbidden")

                LocalApplication.create_codex_adapter = staticmethod(provider_access_forbidden)
                CodexInstalledSchemaProbe.probe = lambda _self: CodexSchemaPreflightResult(
                    status=CodexSchemaPreflightStatus.UNAVAILABLE,
                )
                (
                    verification_session_id,
                    verification_project_id,
                    verification_run_id,
                ) = _seed_cp34_native_unavailable(settings)
                application = bootstrap_local_application(settings)
                _seed_retained_history(application, workspace)
                _seed_indexed_catalog(application)
                http_app = application.create_http_app()
                _assert_cp34_seed_head(
                    http_app,
                    session_id=verification_session_id,
                    expected_run_id=verification_run_id,
                )
                configuration = uvicorn.Config(
                    http_app,
                    host="127.0.0.1",
                    port=port,
                    access_log=False,
                    log_level="critical",
                    timeout_graceful_shutdown=5,
                    log_config={
                        "version": 1,
                        "disable_existing_loggers": False,
                        "handlers": {"gate_null": {"class": "logging.NullHandler"}},
                        "loggers": {
                            name: {"handlers": ["gate_null"], "propagate": False}
                            for name in ("uvicorn", "uvicorn.error", "uvicorn.access")
                        },
                    },
                )
                server = uvicorn.Server(configuration)
                failed = threading.Event()

                def serve() -> None:
                    try:
                        server.run(sockets=[listener])
                    except BaseException:
                        failed.set()

                thread = threading.Thread(
                    target=serve,
                    name="prompt-enhancer-convergence-loopback",
                    daemon=True,
                )
                thread.start()
                startup_ready = _wait_until_ready(origin, thread)
                if not startup_ready:
                    browser_exit = 1
                else:
                    browser_exit = _run_browser_gate(
                        origin,
                        workspace,
                        verification_session_id=verification_session_id,
                        verification_project_id=verification_project_id,
                    )
                server_thread_failed = failed.is_set()
            finally:
                if server is not None:
                    server.should_exit = True
                if thread is not None:
                    thread.join(timeout=15)
                    if thread.is_alive() and server is not None:
                        server.force_exit = True
                        thread.join(timeout=5)
                    server_thread_failed = server_thread_failed or thread.is_alive()
                try:
                    listener.close()
                except OSError:
                    server_thread_failed = True
                if http_app is not None:
                    lifecycle = getattr(http_app.state, "runtime_lifecycle", None)
                    startup_failure = getattr(lifecycle, "startup_failure", None)
                    startup_failure_component = (
                        None if startup_failure is None else str(startup_failure.value)
                    )
                    cleanup_confirmed = bool(
                        lifecycle is not None
                        and lifecycle.cleanup_finished
                        and not lifecycle.shutdown_failures
                    )
                if models is not None:
                    try:
                        models.shutdown()
                        model_runtimes_remaining = len(models.running_aliases())
                    except Exception:
                        model_runtimes_remaining = -1
                listener_released = not _loopback_open(port)

    temporary_state_removed = temporary_root is not None and not temporary_root.exists()
    return GateResult(
        browser_exit_code=browser_exit,
        startup_ready=startup_ready,
        startup_failure_component=startup_failure_component,
        listener_released=listener_released,
        runtime_cleanup_confirmed=cleanup_confirmed,
        model_runtimes_remaining=model_runtimes_remaining,
        temporary_state_removed=temporary_state_removed,
        server_thread_failed=server_thread_failed,
    )


def main() -> int:
    handoff = _handoff_to_repository_python(sys.argv[1:])
    if handoff is not None:
        return handoff
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Use the already-built dashboard while iterating locally.",
    )
    parser.add_argument(
        "--verify-cp34-seed",
        action="store_true",
        help="Verify the disposable CP34 canonical-head seed without a server or browser.",
    )
    arguments = parser.parse_args()
    try:
        if arguments.verify_cp34_seed:
            verify_cp34_native_unavailable_seed()
            print("CONVERGENCE_CP34_SEED_RESULT=passed", flush=True)
            return 0
        result = run(build=not arguments.skip_build)
    except Exception as error:
        print("CONVERGENCE_LOOPBACK_ERROR=" + json.dumps({
            "code": "isolated_gate_failed",
            "exception_type": type(error).__name__,
        }, sort_keys=True), flush=True)
        return 1
    print("CONVERGENCE_LOOPBACK_RESULT=" + json.dumps({
        "browser_exit_code": result.browser_exit_code,
        "startup_ready": result.startup_ready,
        "startup_failure_component": result.startup_failure_component,
        "listener_released": result.listener_released,
        "runtime_cleanup_confirmed": result.runtime_cleanup_confirmed,
        "model_runtimes_remaining": result.model_runtimes_remaining,
        "temporary_state_removed": result.temporary_state_removed,
        "server_thread_failed": result.server_thread_failed,
    }, sort_keys=True), flush=True)
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
