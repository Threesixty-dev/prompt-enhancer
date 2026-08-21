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

    configuration = uvicorn.Config(
        application.create_http_app(
            user_presence_confirmation=verify_user_presence,
            user_presence_confirmation_mode="native_bridge_bound_token",
        ),
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
    )


def _wait_for_owned_service(
    endpoints: tuple[tuple[str, str], ...],
    token: str,
    owned: _OwnedServer,
) -> str:
    deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        for _address, origin in endpoints:
            if _verify_service_identity(origin, token):
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
