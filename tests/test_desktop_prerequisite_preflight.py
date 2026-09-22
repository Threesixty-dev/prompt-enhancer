from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from prompt_enhancer import desktop_overlay
from prompt_enhancer.config import AppSettings
from prompt_enhancer.infrastructure.windows_desktop_prerequisites import (
    DetectionReason,
    PrerequisiteDetection,
    PrerequisiteState,
)


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(home=tmp_path, host="127.0.0.1", port=18765)


@pytest.mark.parametrize(
    "entrypoint",
    [desktop_overlay.run_desktop_overlay, desktop_overlay.run_desktop_agent],
)
@pytest.mark.parametrize(
    ("state", "expected_code"),
    [
        (PrerequisiteState.MISSING, "webview2_runtime_missing"),
        (PrerequisiteState.UNKNOWN, "webview2_runtime_unverified"),
    ],
)
def test_missing_and_unverified_prerequisites_stop_before_native_or_service_start(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    entrypoint,
    state: PrerequisiteState,
    expected_code: str,
) -> None:
    raw_detail = "SYNTHETIC_PRIVATE_REGISTRY_DETAIL"
    monkeypatch.setattr(desktop_overlay, "sys_platform_is_windows", lambda: True)
    monkeypatch.setattr(
        desktop_overlay,
        "detect_webview2_runtime",
        lambda: PrerequisiteDetection(
            state,
            None,
            DetectionReason.NO_REGISTERED_VERSION
            if state is PrerequisiteState.MISSING
            else DetectionReason.REGISTRY_ACCESS_DENIED,
        ),
    )
    monkeypatch.setattr(
        desktop_overlay,
        "NativeLifecycleMarker",
        lambda *_args: pytest.fail("preflight must run before lifecycle marker creation"),
    )
    monkeypatch.setattr(
        desktop_overlay,
        "_start_owned_server",
        lambda *_args, **_kwargs: pytest.fail("preflight must run before server start"),
    )
    monkeypatch.setattr(
        desktop_overlay,
        "_load_webview",
        lambda: pytest.fail("preflight must run before native dependency loading"),
    )

    with pytest.raises(desktop_overlay.DesktopOverlayDependencyError) as caught:
        entrypoint(_settings(tmp_path))

    assert caught.value.reason_code == expected_code
    assert raw_detail not in str(caught.value)
    assert raw_detail not in desktop_overlay._failure_notice(caught.value.reason_code)
    if state is PrerequisiteState.MISSING:
        assert "https://developer.microsoft.com/microsoft-edge/webview2/" in str(
            caught.value
        )
        assert "could not verify" not in str(caught.value)
    else:
        assert "could not verify" in str(caught.value)
        assert "no installation was attempted" in str(caught.value)
        assert "developer.microsoft.com" not in str(caught.value)


@pytest.mark.parametrize(
    ("entrypoint", "inner_operation"),
    [
        (desktop_overlay.run_desktop_overlay, "_run_desktop_overlay"),
        (desktop_overlay.run_desktop_agent, "_run_desktop_agent"),
    ],
)
def test_present_prerequisite_preserves_the_existing_start_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    entrypoint,
    inner_operation: str,
) -> None:
    selected = _settings(tmp_path)
    operations: list[tuple[object, ...]] = []
    monkeypatch.setattr(desktop_overlay, "sys_platform_is_windows", lambda: True)
    monkeypatch.setattr(
        desktop_overlay,
        "detect_webview2_runtime",
        lambda: PrerequisiteDetection(
            PrerequisiteState.PRESENT,
            "123.0.0.1",
            DetectionReason.REGISTERED_VERSION,
        ),
    )
    monkeypatch.setattr(
        desktop_overlay,
        "NativeLifecycleMarker",
        lambda *args: SimpleNamespace(arguments=args),
    )

    def run_with_marker(marker, operation) -> None:
        operations.append(("marker", marker))
        operation()

    monkeypatch.setattr(desktop_overlay, "_run_with_lifecycle_marker", run_with_marker)
    monkeypatch.setattr(
        desktop_overlay,
        inner_operation,
        lambda *args: operations.append((inner_operation, *args)),
    )

    entrypoint(selected)

    assert operations[0][0] == "marker"
    assert operations[1][0] == inner_operation
    assert operations[1][1] is selected


@pytest.mark.parametrize(
    "entrypoint",
    [desktop_overlay.run_desktop_overlay, desktop_overlay.run_desktop_agent],
)
def test_detector_exception_is_unknown_and_never_leaks_error_text(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    entrypoint,
) -> None:
    monkeypatch.setattr(desktop_overlay, "sys_platform_is_windows", lambda: True)

    def fail_detection():
        raise OSError("SYNTHETIC_PRIVATE_REGISTRY_DETAIL")

    monkeypatch.setattr(desktop_overlay, "detect_webview2_runtime", fail_detection)

    with pytest.raises(desktop_overlay.DesktopOverlayDependencyError) as caught:
        entrypoint(_settings(tmp_path))

    assert caught.value.reason_code == "webview2_runtime_unverified"
    assert "SYNTHETIC_PRIVATE_REGISTRY_DETAIL" not in str(caught.value)
    assert caught.value.__cause__ is None
