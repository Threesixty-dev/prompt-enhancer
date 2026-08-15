"""Command-line entry points for the offline-only Phase 1 service."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import sys
from typing import Any

from .bootstrap import LocalApplication, bootstrap_local_application
from .config import AppSettings
from .domain import DataTier, Provider
from .ingestion import IngestionSelection


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prompt-enhancer",
        description="Private, local-only coding-agent metadata analytics.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init", help="initialize the private local metadata store")
    subparsers.add_parser("demo", help="load deterministic synthetic metadata")
    subparsers.add_parser("status", help="show safe aggregate store status")
    subparsers.add_parser("serve", help="serve the authenticated loopback API")
    subparsers.add_parser(
        "desktop",
        help="open the native always-on-top live-metrics window",
    )

    grant = subparsers.add_parser(
        "codex-consent-grant",
        help="grant a local Codex source-access scope without reading it",
    )
    grant.add_argument("scope", choices=("local-history",))
    revoke = subparsers.add_parser(
        "codex-consent-revoke",
        help="revoke a local Codex source-access scope",
    )
    revoke.add_argument("scope", choices=("local-history",))
    index = subparsers.add_parser(
        "codex-index",
        help="build a bounded content-discarding Codex project/session index",
    )
    index.add_argument("--max-sessions", type=int, default=500)
    analyze = subparsers.add_parser(
        "codex-analyze",
        help="derive bounded operational metrics for selected safe IDs",
    )
    analyze.add_argument("--project-id", action="append", default=[])
    analyze.add_argument("--session-id", action="append", default=[])
    analyze.add_argument("--max-sessions", type=int, default=100)
    return parser


def _initialize(settings: AppSettings) -> LocalApplication:
    return bootstrap_local_application(settings)


def _safe_count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _status_lines(summary: Any) -> list[str]:
    """Render only a small allowlist of non-identifying aggregate counters."""

    lines = ["Local metadata store is ready."]
    if not isinstance(summary, dict):
        return lines
    labels = (
        ("sessions", "Sessions"),
        ("events", "Events"),
        ("metric_results", "Metric results"),
    )
    for key, label in labels:
        count = _safe_count(summary.get(key))
        if count is not None:
            lines.append(f"{label}: {count}")
    return lines


def _run_init(settings: AppSettings) -> int:
    _initialize(settings)
    print("Initialized the private local metadata store.")
    return 0


def _run_demo(settings: AppSettings) -> int:
    from .adapters.synthetic import SyntheticAdapter

    application = _initialize(settings)
    report = application.create_ingestion_service().ingest(SyntheticAdapter())
    safe_sessions = []
    offset = 0
    while True:
        page = application.database.list_sessions(limit=500, offset=offset)
        for item in page:
            if item.get("provider") != "synthetic":
                continue
            session = application.database.get_session(str(item["session_id"]))
            if session is not None:
                safe_sessions.append(session)
        offset += len(page)
        if len(page) < 500:
            break
    discovery = (
        application.create_discovery_persistence_service().discover_and_persist(
            safe_sessions
        )
    )
    print(
        "Synthetic demo loaded: "
        f"{report.sessions_seen} sessions, {report.events_seen} events, and "
        f"{len(discovery.batch.candidates)} reviewable task suggestion(s)."
    )
    return 0


def _run_status(settings: AppSettings) -> int:
    application = _initialize(settings)
    for line in _status_lines(application.database.summary()):
        print(line)
    return 0



def _codex_tier(scope: str) -> DataTier:
    if scope == "local-history":
        return DataTier.REDACTED_CONTENT
    raise ValueError("unsupported Codex source-access scope")


def _run_codex_consent(
    settings: AppSettings,
    args: argparse.Namespace,
    *,
    revoke: bool,
) -> int:
    application = _initialize(settings)
    tier = _codex_tier(str(args.scope))
    if revoke:
        application.database.revoke_consent(Provider.CODEX, tier)
        print("Revoked the selected local Codex source-access scope.")
    else:
        application.database.grant_consent(Provider.CODEX, tier)
        print("Granted the selected local Codex source-access scope.")
    return 0


def _provider_sessions(
    application: LocalApplication,
    provider: Provider,
) -> list[Any]:
    sessions = []
    offset = 0
    while True:
        page = application.database.list_sessions(limit=500, offset=offset)
        for item in page:
            if item.get("provider") != provider.value:
                continue
            session = application.database.get_session(str(item["session_id"]))
            if session is not None:
                sessions.append(session)
        offset += len(page)
        if len(page) < 500:
            return sessions


def _run_codex_index(settings: AppSettings, args: argparse.Namespace) -> int:
    application = _initialize(settings)
    selection = IngestionSelection(max_sessions=int(args.max_sessions))
    report = application.create_ingestion_service().ingest(
        application.create_codex_adapter(),
        selection=selection,
    )
    discovery = (
        application.create_discovery_persistence_service().discover_and_persist(
            _provider_sessions(application, Provider.CODEX)
        )
    )
    suffix = " (bounded result)" if report.truncated else ""
    print(
        "Codex metadata index loaded: "
        f"{report.sessions_selected} sessions and "
        f"{len(discovery.batch.candidates)} reviewable task suggestion(s){suffix}."
    )
    return 0


def _run_codex_analysis(settings: AppSettings, args: argparse.Namespace) -> int:
    project_ids = frozenset(str(value) for value in args.project_id)
    session_ids = frozenset(str(value) for value in args.session_id)
    if not project_ids and not session_ids:
        raise ValueError("Codex analysis requires a safe project or session ID")
    application = _initialize(settings)
    report = application.create_codex_local_source_service().analyze(
        project_ids=project_ids,
        session_ids=session_ids,
        max_sessions=int(args.max_sessions),
    )
    suffix = " (bounded result)" if report.truncated else ""
    print(
        "Codex operational metrics updated: "
        f"{report.sessions_selected} sessions, {report.events_seen} events, and "
        f"{report.metrics_written} metric observations{suffix}."
    )
    return 0

def _run_serve(settings: AppSettings) -> int:
    import uvicorn

    application = _initialize(settings)
    app = application.create_http_app()
    print(f"Serving the authenticated local API on loopback port {settings.port}.")
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        access_log=False,
        log_level="warning",
    )
    return 0


def _run_desktop(settings: AppSettings) -> int:
    from .desktop_overlay import run_desktop_overlay

    run_desktop_overlay(settings)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        settings = AppSettings.from_env()
        if args.command == "codex-consent-grant":
            return _run_codex_consent(settings, args, revoke=False)
        if args.command == "codex-consent-revoke":
            return _run_codex_consent(settings, args, revoke=True)
        if args.command == "codex-index":
            return _run_codex_index(settings, args)
        if args.command == "codex-analyze":
            return _run_codex_analysis(settings, args)
        handlers = {
            "init": _run_init,
            "demo": _run_demo,
            "status": _run_status,
            "serve": _run_serve,
            "desktop": _run_desktop,
        }
        return handlers[args.command](settings)
    except (OSError, RuntimeError, ValueError):
        print("prompt-enhancer: local operation failed safely.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
