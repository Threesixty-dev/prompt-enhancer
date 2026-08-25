"""Native Windows host for the content-free live-metrics overlay.

The host deliberately reuses the authenticated loopback application.  It does
not put API credentials, provider identifiers, or session identifiers in the
window URL, command line, logs, or Javascript bridge, and it never sends the
persistent API token to a listener whose identity has not been proven first.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import ipaddress
import json
from pathlib import PureWindowsPath
import socket
from threading import Thread
import time
from types import ModuleType
from typing import Any
import urllib.request
import urllib.parse

from .config import AppSettings
from .interfaces.http.desktop_identity import (
    DESKTOP_CHALLENGE_HEADER,
    DESKTOP_IDENTITY_PATH,
    DESKTOP_IDENTITY_VERSION,
    canonical_loopback_origin,
    is_desktop_owned_instance_path,
    new_desktop_owned_instance_path,
    new_desktop_challenge,
    verify_desktop_identity_proof,
)
from .interfaces.http.user_presence import (
    USER_PRESENCE_HEADER,
    USER_PRESENCE_VERSION,
    UserPresenceApprovalManager,
)
from .privacy import load_or_create_api_token


_OVERLAY_PATH = "/overlay/model-ensemble"
_AGENT_PATH = "/agent"
_FOLDER_PICKER_VERSION = "native-folder-picker-v1"
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
    """Never follow a redirect away from the probed loopback origin."""

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
    user_presence: UserPresenceApprovalManager
    readiness_path: str

    def stop(self) -> None:
        """Stop only the Uvicorn instance created by this desktop host."""

        self.server.should_exit = True
        self.thread.join(timeout=10.0)
        if self.thread.is_alive():
            self.server.force_exit = True
            self.thread.join(timeout=5.0)


class _DesktopWindowApi:
    """Content-free bridge for window chrome and native user presence."""

    def __init__(
        self,
        user_presence: UserPresenceApprovalManager | None = None,
        expected_origin: str | None = None,
    ) -> None:
        self._window: Any | None = None
        self._maximized = False
        self._user_presence = user_presence
        self._expected_origin = expected_origin

    def _bind(self, window: Any) -> None:
        self._window = window

    def minimize_window(self) -> None:
        if self._window is not None:
            self._window.minimize()

    def toggle_maximize_window(self) -> bool:
        if self._window is None:
            return False
        if self._maximized:
            self._window.restore()
        else:
            self._window.maximize()
        self._maximized = not self._maximized
        return self._maximized

    def close_window(self) -> None:
        if self._window is not None:
            self._window.destroy()

    def confirm_user_presence(self, request: Any) -> dict[str, Any]:
        """Show a native dialog and return one exact, short-lived capability."""

        manager = self._user_presence
        window = self._window
        if manager is None or window is None:
            return {
                "approved": False,
                "reason": "native_confirmation_unavailable",
                "version": USER_PRESENCE_VERSION,
            }
        if not self._window_origin_is_expected(window):
            return {
                "approved": False,
                "reason": "native_confirmation_unavailable",
                "version": USER_PRESENCE_VERSION,
            }
        if not isinstance(request, dict) or set(request) != {
            "method",
            "path",
            "body_sha256",
        }:
            return {
                "approved": False,
                "reason": "invalid_confirmation_request",
                "version": USER_PRESENCE_VERSION,
            }
        method = request.get("method")
        path = request.get("path")
        body_sha256 = request.get("body_sha256")
        if not all(isinstance(value, str) for value in (method, path, body_sha256)):
            return {
                "approved": False,
                "reason": "invalid_confirmation_request",
                "version": USER_PRESENCE_VERSION,
            }
        label = manager.action_label(method, path)
        if label is None:
            return {
                "approved": False,
                "reason": "action_not_allowed",
                "version": USER_PRESENCE_VERSION,
            }
        approved = bool(
            window.create_confirmation_dialog(
                "Confirm local action",
                f"{label}.\n\nApprove only if you initiated and reviewed this action.",
            )
        )
        if not approved:
            return {
                "approved": False,
                "reason": "user_declined",
                "version": USER_PRESENCE_VERSION,
            }
        if not self._window_origin_is_expected(window):
            return {
                "approved": False,
                "reason": "native_confirmation_unavailable",
                "version": USER_PRESENCE_VERSION,
            }
        try:
            token = manager.issue(
                method=method,
                path=path,
                body_sha256=body_sha256,
            )
        except ValueError:
            return {
                "approved": False,
                "reason": "invalid_confirmation_request",
                "version": USER_PRESENCE_VERSION,
            }
        return {
            "approved": True,
            "approval_token": token,
            "version": USER_PRESENCE_VERSION,
        }

    def _window_origin_is_expected(self, window: Any) -> bool:
        expected = self._expected_origin
        if expected is None:
            return False
        try:
            current = window.get_current_url()
            current_url = urllib.parse.urlsplit(current)
            expected_url = urllib.parse.urlsplit(expected)
            if (
                not isinstance(current, str)
                or current_url.username is not None
                or current_url.password is not None
                or current_url.scheme.casefold() not in {"http", "https"}
            ):
                return False
            return (
                current_url.scheme.casefold(),
                (current_url.hostname or "").casefold(),
                current_url.port,
            ) == (
                expected_url.scheme.casefold(),
                (expected_url.hostname or "").casefold(),
                expected_url.port,
            )
        except (AttributeError, TypeError, ValueError):
            return False


class _DesktopAgentWindowApi(_DesktopWindowApi):
    """Owned Agent bridge with one explicit, user-driven folder chooser.

    Unlike the content-free confirmation bridge, a successful folder choice
    returns the path the person selected.  The value is never logged or kept
    by this bridge, and the local-agent service remains authoritative for all
    protected-root, drive-root, reparse-point, and workspace validation.
    """

    def __init__(
        self,
        user_presence: UserPresenceApprovalManager,
        expected_origin: str,
        folder_dialog_type: Any | None,
    ) -> None:
        super().__init__(user_presence, expected_origin)
        self._folder_dialog_type = folder_dialog_type

    @staticmethod
    def _folder_picker_response(
        status: str,
        path: str | None = None,
    ) -> dict[str, Any]:
        if status == "selected" and path is not None:
            return {
                "version": _FOLDER_PICKER_VERSION,
                "status": "selected",
                "path": path,
            }
        return {
            "version": _FOLDER_PICKER_VERSION,
            "status": status,
        }

    def _window_route_is_agent(self, window: Any) -> bool:
        if not self._window_origin_is_expected(window):
            return False
        try:
            current = urllib.parse.urlsplit(window.get_current_url())
        except (AttributeError, TypeError, ValueError):
            return False
        return (
            current.path == _AGENT_PATH
            and current.query == ""
            and current.fragment == ""
        )

    def choose_workspace_folder(self) -> dict[str, Any]:
        """Open the owned native folder dialog and return the exact v1 shape."""

        window = self._window
        if (
            window is None
            or self._folder_dialog_type is None
            or not self._window_route_is_agent(window)
        ):
            return self._folder_picker_response("unavailable")
        try:
            selected = window.create_file_dialog(
                self._folder_dialog_type,
                allow_multiple=False,
            )
        except Exception:
            return self._folder_picker_response("unavailable")
        if not self._window_route_is_agent(window):
            return self._folder_picker_response("unavailable")
        if selected is None or selected == () or selected == []:
            return self._folder_picker_response("cancelled")
        if (
            not isinstance(selected, (tuple, list))
            or len(selected) != 1
            or not isinstance(selected[0], str)
        ):
            return self._folder_picker_response("unavailable")
        path = selected[0]
        if (
            not path
            or len(path) > 1024
            or "\0" in path
            or not PureWindowsPath(path).is_absolute()
        ):
            return self._folder_picker_response("unavailable")
        return self._folder_picker_response("selected", path)


def _loopback_origin(host: str, port: int) -> str:
    try:
        return canonical_loopback_origin(host, port)
    except ValueError:
        raise DesktopOverlayServiceError(
            "desktop overlay requires a validated loopback service"
        ) from None


def _exact_loopback_endpoints(host: str, port: int) -> tuple[tuple[str, str], ...]:
    """Resolve a configured loopback host to exact numeric HTTP origins.

    The WebView and identity probe use the returned numeric origin, never the
    ``localhost`` alias.  That makes the authority in the HMAC proof identical
    to the transport endpoint and prevents IPv4/IPv6 relay ambiguity.
    """

    # Validate the configuration and port before asking the resolver anything.
    _loopback_origin(host, port)
    if host.casefold() != "localhost":
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            raise DesktopOverlayServiceError(
                "desktop overlay requires a validated loopback service"
            ) from None
        return (
            (
                address.compressed,
                canonical_loopback_origin(address.compressed, port),
            ),
        )

    try:
        addresses = socket.getaddrinfo(
            host,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except OSError:
        raise DesktopOverlayServiceError(
            "desktop loopback authority could not be resolved"
        ) from None
    endpoints: list[tuple[str, str]] = []
    seen: set[str] = set()
    for family, _socktype, _protocol, _canonical_name, sockaddr in addresses:
        if family not in {socket.AF_INET, socket.AF_INET6} or not sockaddr:
            continue
        try:
            address = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        if not address.is_loopback or address.compressed in seen:
            continue
        seen.add(address.compressed)
        endpoints.append(
            (
                address.compressed,
                canonical_loopback_origin(address.compressed, port),
            )
        )
    if not endpoints:
        raise DesktopOverlayServiceError(
            "desktop loopback authority could not be resolved"
        )
    return tuple(endpoints)


def _port_is_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=_PROBE_TIMEOUT_SECONDS):
            return True
    except OSError:
        return False


def _fetch_identity_payload(origin: str, challenge: str) -> Any:
    """Send exactly one unauthenticated challenge and return the parsed body.

    The request carries no token, no cookie, and no identifier.  Any transport,
    status, size, or encoding problem is reported as ``None`` so callers never
    render provider or exception details.
    """

    request = urllib.request.Request(
        f"{origin}{DESKTOP_IDENTITY_PATH}",
        method="GET",
        headers={
            "Accept": "application/json",
            DESKTOP_CHALLENGE_HEADER: challenge,
        },
    )
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirect(),
    )
    try:
        with opener.open(request, timeout=_PROBE_TIMEOUT_SECONDS) as response:
            if response.status != 200:
                return None
            content_type = response.headers.get_content_type().casefold()
            if content_type != "application/json":
                return None
            body = response.read(_MAX_PROBE_BYTES + 1)
            if not body or len(body) > _MAX_PROBE_BYTES:
                return None
        return json.loads(body.decode("utf-8"))
    except Exception:
        # Collapse every failure to one value so callers and CLI error handling
        # can never render an exception that embeds listener-controlled bytes.
        return None


def _verify_service_identity(origin: str, token: str) -> bool:
    """Prove that a listener is this application without disclosing the token.

    A fresh 256-bit challenge is sent in the clear; only a service that already
    holds the same local token can return the origin-bound keyed digest.  A port
    squatter therefore sees a random value and learns nothing reusable, and a
    squatter relaying to a real instance on another loopback origin fails the
    origin binding.  Malformed, oversized, or unexpected answers are untrusted.
    """

    challenge = new_desktop_challenge()
    payload = _fetch_identity_payload(origin, challenge)
    if not isinstance(payload, dict):
        return False
    if payload.get("identity_version") != DESKTOP_IDENTITY_VERSION:
        return False
    try:
        return verify_desktop_identity_proof(
            token, origin, bytes.fromhex(challenge), payload.get("proof")
        )
    except Exception:
        return False


def _verify_owned_service_instance(origin: str, readiness_path: str) -> bool:
    """Prove readiness belongs to this exact in-process server instance.

    Persistent desktop identity intentionally allows the metrics overlay to
    attach to another trusted Prompt Enhancer process.  Protected Agent mode
    needs a stronger property: the HTTP dependency and native bridge must share
    the same approval manager.  A per-launch, unguessable exact route closes the
    bind race without putting the persistent API token on the wire.
    """

    if not is_desktop_owned_instance_path(readiness_path):
        return False
    request = urllib.request.Request(
        f"{origin}{readiness_path}",
        method="GET",
        headers={"Accept": "application/json"},
    )
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirect(),
    )
    try:
        with opener.open(request, timeout=_PROBE_TIMEOUT_SECONDS) as response:
            if response.status != 204:
                return False
            return response.read(1) == b""
    except Exception:
        return False


def _start_owned_server(settings: AppSettings) -> _OwnedServer:
    import uvicorn
    from .bootstrap import bootstrap_local_application

    application = bootstrap_local_application(settings)
    user_presence = UserPresenceApprovalManager()

    def verify_user_presence(request: Any, body: bytes) -> None:
        if not user_presence.consume(
            token=request.headers.get(USER_PRESENCE_HEADER),
            method=request.method,
            path=request.url.path,
            body=body,
        ):
            from fastapi import HTTPException

            raise HTTPException(
                status_code=403,
                detail="native user-presence confirmation required",
            )

    readiness_path = new_desktop_owned_instance_path()
    http_app = application.create_http_app(
        user_presence_confirmation=verify_user_presence,
        user_presence_confirmation_mode="native_bridge_bound_token",
        desktop_owned_readiness_path=readiness_path,
    )
    configuration = uvicorn.Config(
        http_app,
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
    return _OwnedServer(
        server=server,
        thread=thread,
        user_presence=user_presence,
        readiness_path=readiness_path,
    )


def _wait_for_owned_service(
    endpoints: tuple[tuple[str, str], ...],
    token: str,
    owned: _OwnedServer,
) -> str:
    deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        for _address, origin in endpoints:
            if _verify_service_identity(
                origin, token
            ) and _verify_owned_service_instance(
                origin, owned.readiness_path
            ):
                return origin
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


def _native_folder_dialog_type(webview: ModuleType) -> Any | None:
    """Resolve pywebview 6's folder enum with a narrow legacy fallback."""

    file_dialog = getattr(webview, "FileDialog", None)
    current = None if file_dialog is None else getattr(file_dialog, "FOLDER", None)
    if current is not None:
        return current
    legacy = getattr(webview, "FOLDER_DIALOG", None)
    return legacy if legacy is not None else None


def _open_overlay_window(
    webview: ModuleType,
    url: str,
    user_presence: UserPresenceApprovalManager | None = None,
) -> None:
    parsed_url = urllib.parse.urlsplit(url)
    expected_origin = f"{parsed_url.scheme}://{parsed_url.netloc}"
    window_api = _DesktopWindowApi(user_presence, expected_origin)
    window = webview.create_window(
        "Prompt Enhancer - Live metrics",
        url=url,
        js_api=window_api,
        width=420,
        height=620,
        min_size=(340, 420),
        resizable=True,
        frameless=True,
        easy_drag=False,
        shadow=True,
        on_top=True,
        confirm_close=False,
        background_color="#F4F8F7",
        text_select=True,
    )
    if window is None:
        raise DesktopOverlayDependencyError("desktop window could not be created")
    window_api._bind(window)
    webview.start(gui="edgechromium", debug=False)


def _open_agent_window(
    webview: ModuleType,
    url: str,
    user_presence: UserPresenceApprovalManager,
) -> None:
    """Open the full Agent surface with the owned native safety bridge."""

    parsed_url = urllib.parse.urlsplit(url)
    expected_origin = f"{parsed_url.scheme}://{parsed_url.netloc}"
    window_api = _DesktopAgentWindowApi(
        user_presence,
        expected_origin,
        _native_folder_dialog_type(webview),
    )
    window = webview.create_window(
        "Prompt Enhancer - Agent workspace",
        url=url,
        js_api=window_api,
        width=1280,
        height=900,
        min_size=(840, 640),
        resizable=True,
        frameless=False,
        shadow=True,
        on_top=False,
        confirm_close=True,
        background_color="#F4F8F7",
        text_select=True,
    )
    if window is None:
        raise DesktopOverlayDependencyError("desktop window could not be created")
    window_api._bind(window)
    webview.start(gui="edgechromium", debug=False)


def run_desktop_overlay(settings: AppSettings) -> None:
    """Attach to the trusted local service or own one for the window lifetime."""

    if not sys_platform_is_windows():
        raise DesktopOverlayError("desktop overlay is currently available only on Windows")
    endpoints = _exact_loopback_endpoints(settings.host, settings.port)
    token = load_or_create_api_token(settings.api_token_path)
    owned: _OwnedServer | None = None

    origin: str | None = None
    occupied_untrusted = False
    for address, candidate_origin in endpoints:
        if not _port_is_open(address, settings.port):
            continue
        if _verify_service_identity(candidate_origin, token):
            origin = candidate_origin
            break
        occupied_untrusted = True
    if origin is None and occupied_untrusted:
        raise DesktopOverlayServiceError(
            "configured loopback port is occupied by an untrusted service"
        )
    if origin is None:
        owned = _start_owned_server(settings)
        try:
            origin = _wait_for_owned_service(endpoints, token, owned)
        except Exception:
            owned.stop()
            raise

    assert origin is not None
    try:
        _open_overlay_window(
            _load_webview(),
            f"{origin}{_OVERLAY_PATH}",
            None if owned is None else owned.user_presence,
        )
    finally:
        if owned is not None:
            owned.stop()


def run_desktop_agent(settings: AppSettings) -> None:
    """Own the loopback server and open Agent with protected actions enabled.

    Unlike the read-only-compatible metrics overlay, the Agent window never
    attaches to an existing listener.  The native window and HTTP dependency
    must share the same in-process one-shot approval manager, so an occupied
    configured port is a hard stop even when that listener proves its identity.
    """

    if not sys_platform_is_windows():
        raise DesktopOverlayError("desktop Agent is currently available only on Windows")
    endpoints = _exact_loopback_endpoints(settings.host, settings.port)
    if any(_port_is_open(address, settings.port) for address, _origin in endpoints):
        raise DesktopOverlayServiceError(
            "desktop Agent protected mode requires an unoccupied configured loopback port"
        )
    token = load_or_create_api_token(settings.api_token_path)
    owned = _start_owned_server(settings)
    try:
        origin = _wait_for_owned_service(endpoints, token, owned)
    except Exception:
        owned.stop()
        raise
    try:
        _open_agent_window(
            _load_webview(),
            f"{origin}{_AGENT_PATH}",
            owned.user_presence,
        )
    finally:
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


def _show_safe_agent_error() -> None:
    """Show one content-free native error for the protected Agent launcher."""

    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None,
            (
                "Prompt Enhancer could not open the protected Agent window. "
                "If the local service is already running, close it and try again."
            ),
            "Prompt Enhancer",
            0x10,
        )
    except Exception:
        return


def desktop_main() -> int:
    """Console-free Windows entry point for the React/WebView overlay."""

    try:
        run_desktop_overlay(AppSettings.from_env())
    except Exception:
        _show_safe_desktop_error()
        return 1
    return 0


def agent_desktop_main() -> int:
    """Console-free Windows entry point for the protected Agent window."""

    try:
        run_desktop_agent(AppSettings.from_env())
    except Exception:
        _show_safe_agent_error()
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
    "agent_desktop_main",
    "desktop_main",
    "run_desktop_agent",
    "run_desktop_overlay",
]
