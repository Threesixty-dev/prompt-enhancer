"""Owned, isolated process and listener helpers for Agent MCP tests."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from prompt_enhancer import desktop_overlay
from prompt_enhancer.application.owned_process import (
    OwnedProcessResult,
    run_owned_process,
)
from prompt_enhancer.config import AppSettings


DEFAULT_STDOUT_LIMIT = 4 * 1024 * 1024
DEFAULT_STDERR_LIMIT = 256 * 1024


def isolated_child_environment(root: Path) -> dict[str, str]:
    """Return a minimal environment whose user and cache roots are synthetic."""

    keep = {"COMSPEC", "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR"}
    environment = {
        key: value for key, value in os.environ.items() if key.upper() in keep
    }
    user_root = root / "synthetic-user"
    temporary_root = root / "temporary"
    roaming_root = user_root / "appdata" / "roaming"
    local_root = user_root / "appdata" / "local"
    codex_root = user_root / "codex"
    huggingface_root = user_root / "huggingface"
    for directory in (
        user_root,
        temporary_root,
        roaming_root,
        local_root,
        codex_root,
        huggingface_root,
        user_root / "empty-provider",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    environment.update(
        {
            "HOME": os.fspath(user_root),
            "USERPROFILE": os.fspath(user_root),
            "APPDATA": os.fspath(roaming_root),
            "LOCALAPPDATA": os.fspath(local_root),
            "CODEX_HOME": os.fspath(codex_root),
            "HF_HOME": os.fspath(huggingface_root),
            "TEMP": os.fspath(temporary_root),
            "TMP": os.fspath(temporary_root),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONIOENCODING": "utf-8",
            "PROMPT_ENHANCER_CLAUDE_HOME": os.fspath(
                user_root / "empty-provider"
            ),
        }
    )
    return environment


def start_ephemeral_owned_server(
    *,
    home: Path,
) -> tuple[AppSettings, desktop_overlay._OwnedServer]:
    """Continuously own an OS-assigned loopback socket through server startup."""

    reserved = desktop_overlay._try_reserve_listener("127.0.0.1", 0)
    if reserved is None:
        raise AssertionError("test_loopback_reservation_failed")
    listener, endpoints, selected_port = reserved
    handed_off = False
    try:
        settings = AppSettings(
            home=home,
            host="127.0.0.1",
            port=selected_port,
            session_reader_enabled=False,
        )

        def handoff(
            requested: AppSettings,
            *,
            allow_ephemeral: bool,
        ):
            nonlocal handed_off
            assert handed_off is False
            assert requested is settings
            assert allow_ephemeral is False
            handed_off = True
            return listener, settings, endpoints

        with patch.object(desktop_overlay, "_reserve_owned_listener", handoff):
            owned = desktop_overlay._start_owned_server(settings)
        assert handed_off is True
    except BaseException:
        listener.close()
        raise
    return settings, owned


def run_bounded_owned_helper(
    argv: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    stdin_payload: bytes = b"",
    timeout: float = 30,
    stdout_limit: int = DEFAULT_STDOUT_LIMIT,
    stderr_limit: int = DEFAULT_STDERR_LIMIT,
) -> OwnedProcessResult:
    """Run one hidden child tree with bounded streams, time, and cleanup."""

    return run_owned_process(
        argv,
        cwd=cwd,
        env=environment,
        stdin_payload=stdin_payload,
        stdout_limit=stdout_limit,
        stderr_limit=stderr_limit,
        timeout=timeout,
        maximum_active_processes=4,
    )
