from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest

from prompt_enhancer import cli
from prompt_enhancer.config import AppSettings
from prompt_enhancer import desktop_overlay


TOKEN = "example_desktop_overlay_token_123456789"


class FakeWindow:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def minimize(self) -> None:
        self.calls.append("minimize")

    def maximize(self) -> None:
        self.calls.append("maximize")

    def restore(self) -> None:
        self.calls.append("restore")

    def destroy(self) -> None:
        self.calls.append("destroy")


class FakeWebview:
    def __init__(self, *, fail_start: bool = False) -> None:
        self.created: list[tuple[tuple[object, ...], dict[str, object]]] = []
        self.started: list[dict[str, object]] = []
        self.window = FakeWindow()
        self.fail_start = fail_start

    def create_window(self, *args: object, **kwargs: object) -> object:
        self.created.append((args, kwargs))
        return self.window

    def start(self, **kwargs: object) -> None:
        self.started.append(kwargs)
        if self.fail_start:
            raise RuntimeError("synthetic GUI failure")


class FakeOwnedServer:
    def __init__(self) -> None:
        self.stops = 0
        self.thread = SimpleNamespace(is_alive=lambda: True)

    def stop(self) -> None:
        self.stops += 1


def settings(tmp_path: Path) -> AppSettings:
    return AppSettings(home=tmp_path, host="127.0.0.1", port=18765)


def prepare_common(
    monkeypatch: pytest.MonkeyPatch,
    *,
    service_open: bool,
    trusted: bool,
) -> None:
    monkeypatch.setattr(desktop_overlay, "sys_platform_is_windows", lambda: True)
    monkeypatch.setattr(
        desktop_overlay,
        "load_or_create_api_token",
        lambda _path: TOKEN,
    )
    monkeypatch.setattr(
        desktop_overlay,
        "_port_is_open",
        lambda _host, _port: service_open,
    )
    monkeypatch.setattr(
        desktop_overlay,
        "_verify_service_identity",
        lambda _origin, supplied: supplied == TOKEN and trusted,
    )


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", "http://127.0.0.1:8765"),
        ("localhost", "http://localhost:8765"),
        ("::1", "http://[::1]:8765"),
    ],
)
def test_loopback_origin_is_canonical(host: str, expected: str) -> None:
    assert desktop_overlay._loopback_origin(host, 8765) == expected


def test_loopback_origin_rejects_remote_hosts_and_unsafe_ports() -> None:
    with pytest.raises(desktop_overlay.DesktopOverlayServiceError):
        desktop_overlay._loopback_origin("192.0.2.10", 8765)
    with pytest.raises(desktop_overlay.DesktopOverlayServiceError):
        desktop_overlay._loopback_origin("127.0.0.1", 80)


def test_attaches_to_authenticated_service_without_owning_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    prepare_common(monkeypatch, service_open=True, trusted=True)
    webview = FakeWebview()
    monkeypatch.setattr(desktop_overlay, "_load_webview", lambda: webview)
    monkeypatch.setattr(
        desktop_overlay,
        "_start_owned_server",
        lambda _settings: pytest.fail("trusted listeners must be reused"),
    )

    desktop_overlay.run_desktop_overlay(settings(tmp_path))

    assert len(webview.created) == 1
    args, options = webview.created[0]
    assert args == ("Prompt Enhancer - Live metrics",)
    assert options["url"] == "http://127.0.0.1:18765/overlay/model-ensemble"
    assert TOKEN not in str(args)
    assert TOKEN not in str(options)
    assert options["on_top"] is True
    assert options["resizable"] is True
    assert options["frameless"] is True
    assert options["easy_drag"] is False
    assert options["shadow"] is True
    assert options["min_size"] == (340, 420)
    window_api = options["js_api"]
    window_api.minimize_window()
    assert window_api.toggle_maximize_window() is True
    assert window_api.toggle_maximize_window() is False
    window_api.close_window()
    assert webview.window.calls == ["minimize", "maximize", "restore", "destroy"]
    assert webview.started == [{"gui": "edgechromium", "debug": False}]


def test_localhost_attachment_probes_and_renders_only_an_exact_numeric_origin(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selected = AppSettings(home=tmp_path, host="localhost", port=18765)
    webview = FakeWebview()
    probed: list[str] = []
    monkeypatch.setattr(desktop_overlay, "sys_platform_is_windows", lambda: True)
    monkeypatch.setattr(
        desktop_overlay,
        "load_or_create_api_token",
        lambda _path: TOKEN,
    )
    monkeypatch.setattr(
        desktop_overlay,
        "_exact_loopback_endpoints",
        lambda _host, _port: (
            ("::1", "http://[::1]:18765"),
            ("127.0.0.1", "http://127.0.0.1:18765"),
        ),
    )
    monkeypatch.setattr(desktop_overlay, "_port_is_open", lambda *_args: True)

    def verify(origin: str, supplied: str) -> bool:
        probed.append(origin)
        return supplied == TOKEN and origin == "http://127.0.0.1:18765"

    monkeypatch.setattr(desktop_overlay, "_verify_service_identity", verify)
    monkeypatch.setattr(desktop_overlay, "_load_webview", lambda: webview)
    monkeypatch.setattr(
        desktop_overlay,
        "_start_owned_server",
        lambda _settings: pytest.fail("the trusted IPv4 listener must be reused"),
    )

    desktop_overlay.run_desktop_overlay(selected)

    assert probed == ["http://[::1]:18765", "http://127.0.0.1:18765"]
    assert len(webview.created) == 1
    assert webview.created[0][1]["url"] == (
        "http://127.0.0.1:18765/overlay/model-ensemble"
    )


def test_refuses_an_occupied_port_that_fails_authentication(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    prepare_common(monkeypatch, service_open=True, trusted=False)
    monkeypatch.setattr(
        desktop_overlay,
        "_load_webview",
        lambda: pytest.fail("an untrusted listener must never be rendered"),
    )

    with pytest.raises(
        desktop_overlay.DesktopOverlayServiceError,
        match="untrusted service",
    ):
        desktop_overlay.run_desktop_overlay(settings(tmp_path))


def test_starts_and_stops_only_an_owned_server(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    prepare_common(monkeypatch, service_open=False, trusted=False)
    owned = FakeOwnedServer()
    webview = FakeWebview()
    monkeypatch.setattr(desktop_overlay, "_start_owned_server", lambda _settings: owned)
    monkeypatch.setattr(
        desktop_overlay,
        "_wait_for_owned_service",
        lambda endpoints, supplied, candidate: (
            endpoints[0][1]
            if supplied == TOKEN and candidate is owned
            else pytest.fail("owned service readiness binding changed")
        ),
    )
    monkeypatch.setattr(desktop_overlay, "_load_webview", lambda: webview)

    desktop_overlay.run_desktop_overlay(settings(tmp_path))

    assert owned.stops == 1
    assert len(webview.created) == 1


def test_owned_server_stops_when_native_loop_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    prepare_common(monkeypatch, service_open=False, trusted=False)
    owned = FakeOwnedServer()
    monkeypatch.setattr(desktop_overlay, "_start_owned_server", lambda _settings: owned)
    monkeypatch.setattr(
        desktop_overlay,
        "_wait_for_owned_service",
        lambda endpoints, *_args: endpoints[0][1],
    )
    monkeypatch.setattr(
        desktop_overlay,
        "_load_webview",
        lambda: FakeWebview(fail_start=True),
    )

    with pytest.raises(RuntimeError, match="synthetic GUI failure"):
        desktop_overlay.run_desktop_overlay(settings(tmp_path))
    assert owned.stops == 1


def test_failed_owned_startup_is_stopped_before_error_propagates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    prepare_common(monkeypatch, service_open=False, trusted=False)
    owned = FakeOwnedServer()
    monkeypatch.setattr(desktop_overlay, "_start_owned_server", lambda _settings: owned)
    monkeypatch.setattr(
        desktop_overlay,
        "_wait_for_owned_service",
        lambda *_args: (_ for _ in ()).throw(
            desktop_overlay.DesktopOverlayServiceError("not ready")
        ),
    )

    with pytest.raises(desktop_overlay.DesktopOverlayServiceError, match="not ready"):
        desktop_overlay.run_desktop_overlay(settings(tmp_path))
    assert owned.stops == 1


def test_missing_optional_webview_is_a_safe_dependency_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(_name: str) -> object:
        raise ImportError("synthetic missing package")

    monkeypatch.setattr(desktop_overlay.importlib, "import_module", missing)
    with pytest.raises(
        desktop_overlay.DesktopOverlayDependencyError,
        match="desktop extra",
    ):
        desktop_overlay._load_webview()


def test_cli_desktop_has_no_identifier_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[AppSettings] = []
    monkeypatch.setattr(
        desktop_overlay,
        "run_desktop_overlay",
        lambda value: seen.append(value),
    )

    assert cli.main(["desktop"]) == 0
    assert len(seen) == 1
    with pytest.raises(SystemExit):
        cli._parser().parse_args(["desktop", "--session-id", "0" * 64])


def test_run_desktop_delegates_without_rendering_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selected = settings(tmp_path)
    calls: list[AppSettings] = []
    monkeypatch.setattr(
        desktop_overlay,
        "run_desktop_overlay",
        lambda value: calls.append(value),
    )

    assert cli._run_desktop(selected) == 0
    assert calls == [selected]


def test_parser_exposes_only_the_plain_desktop_command() -> None:
    parsed = cli._parser().parse_args(["desktop"])
    assert isinstance(parsed, argparse.Namespace)
    assert vars(parsed) == {"command": "desktop"}


def test_console_free_entry_loads_settings_and_opens_overlay(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selected = settings(tmp_path)
    calls: list[AppSettings] = []
    monkeypatch.setattr(AppSettings, "from_env", lambda: selected)
    monkeypatch.setattr(desktop_overlay, "run_desktop_overlay", calls.append)

    assert desktop_overlay.desktop_main() == 0
    assert calls == [selected]


def test_console_free_entry_reports_only_a_safe_native_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notices: list[bool] = []
    monkeypatch.setattr(
        desktop_overlay,
        "run_desktop_overlay",
        lambda _settings: (_ for _ in ()).throw(RuntimeError("example private detail")),
    )
    monkeypatch.setattr(AppSettings, "from_env", lambda: object())
    monkeypatch.setattr(desktop_overlay, "_show_safe_desktop_error", lambda: notices.append(True))

    assert desktop_overlay.desktop_main() == 1
    assert notices == [True]
