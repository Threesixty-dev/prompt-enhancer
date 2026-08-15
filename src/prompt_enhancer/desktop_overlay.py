"""Native Windows host for the content-free live-metrics overlay.

The host deliberately reuses the authenticated loopback application.  It does
not put API credentials, provider identifiers, or session identifiers in the
window URL, command line, logs, or Javascript bridge.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import ipaddress
import json
import socket
from threading import Thread
import time
from types import ModuleType
from typing import Any
import urllib.request

from .config import AppSettings, is_loopback_host
from .privacy import load_or_create_api_token


_OVERLAY_PATH = "/overlay/model-ensemble"
_CAPABILITY_PATH = "/v1/capabilities"
_PROBE_TIMEOUT_SECONDS = 1.0
_STARTUP_TIMEOUT_SECONDS = 20.0
_STARTUP_POLL_SECONDS = 0.1
_MAX_PROBE_BYTES = 64 * 1024


class DesktopOverlayError(RuntimeError):
    """Base class for safe, content-free desktop-host failures."""


class DesktopOverlayDependencyError(DesktopOverlayError):
    """Raised when the optional native host dependency is unavailable."""


class DesktopOverlayServiceError(DesktopOverlayError):
    """Raised when the configured loopback service cannot be trusted or started."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Keep the local authentication header on exactly one loopback request."""

    def redirect_request(
        self,
        request: urllib.request.Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> None:
        del request, file_pointer, code, message, headers, new_url
        return None


@dataclass
class _OwnedServer:
    server: Any
    thread: Thread

    def stop(self) -> None:
        """Stop only the Uvicorn instance created by this desktop host."""

        self.server.should_exit = True
        self.thread.join(timeout=10.0)
        if self.thread.is_alive():
            self.server.force_exit = True
            self.thread.join(timeout=5.0)


def _loopback_origin(host: str, port: int) -> str:
    if not is_loopback_host(host) or not 1024 <= port <= 65535:
        raise DesktopOverlayServiceError(
            "desktop overlay requires a validated loopback service"
        )
    normalized = host.casefold()
    if normalized == "localhost":
        authority = "localhost"
    else:
        address = ipaddress.ip_address(host)
        authority = f"[{address.compressed}]" if address.version == 6 else address.compressed
    return f"http://{authority}:{port}"


def _port_is_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=_PROBE_TIMEOUT_SECONDS):
            return True
    except OSError:
        return False


def _authenticated_service_probe(origin: str, token: str) -> bool:
    """Verify that a listener is this authenticated, offline-only application."""

    from .api import API_TOKEN_HEADER

    request = urllib.request.Request(
        f"{origin}{_CAPABILITY_PATH}",
        method="GET",
        headers={
            "Accept": "application/json",
            API_TOKEN_HEADER: token,
        },
    )
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirect(),
    )
    try:
        with opener.open(request, timeout=_PROBE_TIMEOUT_SECONDS) as response:
            if response.status != 200:
                return False
            content_type = response.headers.get_content_type().casefold()
            if content_type != "application/json":
                return False
            body = response.read(_MAX_PROBE_BYTES + 1)
            if not body or len(body) > _MAX_PROBE_BYTES:
                return False
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        # Transport exceptions can retain the Request object, including its
        # authentication header.  Collapse every probe failure to one boolean
        # so callers and CLI error handling can never render that exception.
        return False
    return (
        isinstance(payload, dict)
        and payload.get("cost_mode") == "offline_only"
        and payload.get("data_tier") == "metadata"
        and payload.get("network_inference") is False
        and payload.get("raw_transcripts") is False
        and payload.get("arbitrary_sql") is False
        and payload.get("browser_session") is True
    )


def _start_owned_server(settings: AppSettings) -> _OwnedServer:
    import uvicorn

    from .bootstrap import bootstrap_local_application

    application = bootstrap_local_application(settings)
    configuration = uvicorn.Config(
        application.create_http_app(),
        host=settings.host,
        port=settings.port,
        access_log=False,
        log_level="warning",
    )
    server = uvicorn.Server(configuration)
    thread = Thread(
        target=server.run,
        name="prompt-enhancer-desktop-loopback",
        daemon=True,
    )
    thread.start()
    return _OwnedServer(server=server, thread=thread)


def _wait_for_owned_service(
    origin: str,
    token: str,
    owned: _OwnedServer,
) -> None:
    deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if _authenticated_service_probe(origin, token):
            return
        if not owned.thread.is_alive():
            break
        time.sleep(_STARTUP_POLL_SECONDS)
    raise DesktopOverlayServiceError("desktop loopback service did not become ready")


def _load_webview() -> ModuleType:
    try:
        return importlib.import_module("webview")
    except ImportError:
        raise DesktopOverlayDependencyError(
            "desktop support is not installed; install the desktop extra"
        ) from None


def _open_overlay_window(webview: ModuleType, url: str) -> None:
    webview.create_window(
        "Prompt Enhancer - Live metrics",
        url=url,
        width=420,
        height=620,
        min_size=(340, 420),
        resizable=True,
        frameless=False,
        on_top=True,
        confirm_close=False,
        background_color="#F4F8F7",
        text_select=True,
    )
    webview.start(gui="edgechromium", debug=False)


def run_desktop_overlay(settings: AppSettings) -> None:
    """Attach to the trusted local service or own one for the window lifetime."""

    if not sys_platform_is_windows():
        raise DesktopOverlayError("desktop overlay is currently available only on Windows")
    origin = _loopback_origin(settings.host, settings.port)
    token = load_or_create_api_token(settings.api_token_path)
    owned: _OwnedServer | None = None

    if _port_is_open(settings.host, settings.port):
        if not _authenticated_service_probe(origin, token):
            raise DesktopOverlayServiceError(
                "configured loopback port is occupied by an untrusted service"
            )
    else:
        owned = _start_owned_server(settings)
        try:
            _wait_for_owned_service(origin, token, owned)
        except Exception:
            owned.stop()
            raise

    try:
        _open_overlay_window(_load_webview(), f"{origin}{_OVERLAY_PATH}")
    finally:
        if owned is not None:
            owned.stop()


def _show_safe_desktop_error() -> None:
    """Show one content-free native error when the GUI entry point cannot start."""

    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None,
            "Prompt Enhancer could not open the local live-metrics window.",
            "Prompt Enhancer",
            0x10,
        )
    except Exception:
        # The GUI entry point intentionally has no console.  If even the native
        # message box is unavailable, fail without rendering exception details.
        return


def desktop_main() -> int:
    """Console-free Windows entry point for the React/WebView overlay."""

    try:
        run_desktop_overlay(AppSettings.from_env())
    except Exception:
        _show_safe_desktop_error()
        return 1
    return 0


def sys_platform_is_windows() -> bool:
    """Small test seam that avoids importing GUI dependencies on other systems."""

    import sys

    return sys.platform == "win32"


__all__ = [
    "DesktopOverlayDependencyError",
    "DesktopOverlayError",
    "DesktopOverlayServiceError",
    "desktop_main",
    "run_desktop_overlay",
]
