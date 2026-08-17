"""Configuration with an enforced zero-cost, loopback-only Phase 1 profile."""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path
import stat
import sys
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .domain import CostMode, DataTier


class ConfigurationError(RuntimeError):
    """Raised when configuration would weaken a Phase 1 invariant."""


def lexical_absolute_path(value: Path) -> Path:
    """Make a path absolute without resolving symlink components."""

    expanded = value.expanduser()
    return Path(os.path.abspath(os.fspath(expanded)))


def path_has_symlink_component(value: Path) -> bool:
    """Detect symlinks and Windows reparse points in existing components."""

    absolute = lexical_absolute_path(value)
    for candidate in (absolute, *absolute.parents):
        try:
            metadata = candidate.lstat()
        except FileNotFoundError:
            continue
        is_symlink = stat.S_ISLNK(metadata.st_mode)
        is_reparse_point = bool(
            getattr(metadata, "st_file_attributes", 0) & 0x400
        )
        if is_symlink or is_reparse_point:
            return True
    return False


def default_app_home(environment: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environment is None else environment
    explicit = env.get("PROMPT_ENHANCER_HOME")
    if explicit:
        return Path(explicit).expanduser()

    if sys.platform == "win32":
        base = env.get("LOCALAPPDATA")
        if base:
            return Path(base) / "PromptEnhancer"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "PromptEnhancer"
    else:
        base = env.get("XDG_DATA_HOME")
        if base:
            return Path(base) / "prompt-enhancer"
        return Path.home() / ".local" / "share" / "prompt-enhancer"

    return Path.home() / ".prompt-enhancer"


def is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class AppSettings(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )

    home: Path = Field(default_factory=default_app_home)
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1024, le=65535)
    cost_mode: CostMode = CostMode.OFFLINE_ONLY
    data_tier: DataTier = DataTier.METADATA
    control_plane_development_api: bool = Field(
        default=False,
        description=(
            "Expose the in-memory team control-plane development routes on the "
            "loopback API. Off by default; it stores nothing durably, serves "
            "synthetic tenants only, and is not a team deployment."
        ),
    )

    @field_validator("home")
    @classmethod
    def normalize_home(cls, value: Path) -> Path:
        return lexical_absolute_path(value)

    @model_validator(mode="after")
    def enforce_phase_one_profile(self) -> AppSettings:
        if not is_loopback_host(self.host):
            raise ValueError("Phase 1 services must bind to a loopback address")
        if self.cost_mode is not CostMode.OFFLINE_ONLY:
            raise ValueError("Phase 1 permits only offline_only cost mode")
        if self.data_tier is not DataTier.METADATA:
            raise ValueError("Phase 1 permits only metadata storage")
        if self.control_plane_development_api and not is_loopback_host(self.host):
            raise ValueError("the control-plane development API stays on loopback")
        return self

    @property
    def database_path(self) -> Path:
        return self.home / "metrics.sqlite3"

    @property
    def pseudonym_key_path(self) -> Path:
        return self.home / "pseudonym.key"

    @property
    def api_token_path(self) -> Path:
        return self.home / "api.token"

    @classmethod
    def from_env(cls, environment: Mapping[str, str] | None = None) -> AppSettings:
        env = os.environ if environment is None else environment
        host = env.get("PROMPT_ENHANCER_HOST", "127.0.0.1")
        raw_port = env.get("PROMPT_ENHANCER_PORT", "8765")
        try:
            port = int(raw_port)
        except ValueError as exc:
            raise ConfigurationError("PROMPT_ENHANCER_PORT must be an integer") from exc
        # Only the exact opt-in string enables the development control plane, so
        # a stray value such as "0", "false", or "maybe" leaves it disabled.
        control_plane = (
            env.get("PROMPT_ENHANCER_CONTROL_PLANE_DEV_API", "") == "enabled"
        )
        return cls(
            home=default_app_home(env),
            host=host,
            port=port,
            control_plane_development_api=control_plane,
        )


def prepare_app_home(settings: AppSettings) -> None:
    """Create private local state without revealing its absolute path."""

    try:
        if path_has_symlink_component(settings.home):
            raise ConfigurationError(
                "application home cannot contain a symlink or reparse point"
            )
        settings.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path_has_symlink_component(settings.home):
            raise ConfigurationError(
                "application home cannot contain a symlink or reparse point"
            )
        settings.home.chmod(0o700)
    except ConfigurationError:
        raise
    except OSError as exc:
        raise ConfigurationError("could not securely prepare application home") from exc
