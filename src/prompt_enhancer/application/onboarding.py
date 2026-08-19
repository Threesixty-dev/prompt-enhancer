"""First-run detection, one consent, and automatic refresh for local sources.

The owner's direction: when Codex or Claude Code is present on this machine,
the app should ask once and then load every project and session - and keep
them current - without further clicks.  When neither is present it says so and
lets the person point at a transcript folder.

Detection reads nothing private: it asks whether the Codex CLI is on PATH and
whether a Claude Code transcript root directory exists (and how many transcript
files it holds).  Accepting grants the ordinary per-provider consent and runs
the first index; the refresh worker then re-indexes consented providers on a
timer, swallowing provider errors so a flaky source never takes the app down.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
import shutil
import threading
from pathlib import Path
from typing import Literal

from pydantic import Field

from ..domain import DataTier, Provider, StrictModel


ONBOARDING_CONTRACT_VERSION = "onboarding.v1"
DEFAULT_REFRESH_INTERVAL_SECONDS = 600
MAX_TRANSCRIPT_COUNT_SCAN = 20_000


class DetectionSignal(StrEnum):
    CODEX_CLI_ON_PATH = "codex_cli_on_path"
    CLAUDE_TRANSCRIPT_ROOT = "claude_transcript_root"
    NOT_FOUND = "not_found"


class ProviderDetection(StrictModel):
    provider: Literal["codex", "claude_code"]
    installed: bool
    signal: DetectionSignal
    consent_active: bool
    indexed_sessions: int = Field(ge=0)
    transcript_files: int | None = Field(default=None, ge=0)


class OnboardingStatus(StrictModel):
    contract_version: Literal[ONBOARDING_CONTRACT_VERSION] = ONBOARDING_CONTRACT_VERSION
    providers: tuple[ProviderDetection, ...]
    any_installed: bool
    needs_onboarding: bool
    refresh_interval_seconds: int = Field(ge=60)
    last_refresh_at: datetime | None = None
    last_refresh_error: bool = False
    claude_home_override_supported: bool = True


class OnboardingAccept(StrictModel):
    providers: frozenset[Literal["codex", "claude_code"]] = Field(min_length=1)
    # Optional folder the person points at when Claude Code was not found.
    claude_home: str | None = Field(default=None, max_length=1024)


class OnboardingResult(StrictModel):
    granted: tuple[Literal["codex", "claude_code"], ...]
    indexed_sessions: int = Field(ge=0)
    status: OnboardingStatus


class OnboardingError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def detect_codex(which: Callable[[str], str | None] = shutil.which) -> bool:
    return any(which(name) is not None for name in ("codex", "codex.cmd", "codex.exe"))


def count_transcripts(claude_home: Path) -> int | None:
    projects = claude_home / "projects"
    if not projects.is_dir():
        return None
    count = 0
    try:
        for project_dir in projects.iterdir():
            if not project_dir.is_dir() or project_dir.is_symlink():
                continue
            for candidate in project_dir.glob("*.jsonl"):
                if candidate.is_file() and not candidate.is_symlink():
                    count += 1
                    if count >= MAX_TRANSCRIPT_COUNT_SCAN:
                        return count
    except OSError:
        return None
    return count


class OnboardingService:
    """Detection, one consent, first index, and the periodic refresh."""

    _TIER = DataTier.REDACTED_CONTENT

    def __init__(
        self,
        repository,
        *,
        claude_home: Callable[[], Path],
        set_claude_home: Callable[[Path], None] | None,
        index_codex: Callable[[], int],
        index_claude: Callable[[], int],
        which: Callable[[str], str | None] | None = None,
        refresh_interval_seconds: int = DEFAULT_REFRESH_INTERVAL_SECONDS,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repository = repository
        self._claude_home = claude_home
        self._set_claude_home = set_claude_home
        self._index = {Provider.CODEX: index_codex, Provider.CLAUDE_CODE: index_claude}
        # Resolved at call time so tests can pin PATH detection deterministically.
        self._which = which if which is not None else (lambda name: shutil.which(name))
        self._interval = max(60, int(refresh_interval_seconds))
        self._clock = clock
        self._lock = threading.Lock()
        self._last_refresh_at: datetime | None = None
        self._last_refresh_error = False

    def _counts(self, provider: Provider) -> int:
        try:
            return int(self._repository.provider_catalog_summary(provider)["sessions"])
        except Exception:
            return 0

    def status(self) -> OnboardingStatus:
        codex_installed = detect_codex(self._which)
        transcripts = count_transcripts(self._claude_home())
        claude_installed = transcripts is not None
        providers = (
            ProviderDetection(
                provider="codex",
                installed=codex_installed,
                signal=DetectionSignal.CODEX_CLI_ON_PATH if codex_installed else DetectionSignal.NOT_FOUND,
                consent_active=self._repository.has_active_consent(Provider.CODEX, self._TIER),
                indexed_sessions=self._counts(Provider.CODEX),
            ),
            ProviderDetection(
                provider="claude_code",
                installed=claude_installed,
                signal=DetectionSignal.CLAUDE_TRANSCRIPT_ROOT if claude_installed else DetectionSignal.NOT_FOUND,
                consent_active=self._repository.has_active_consent(Provider.CLAUDE_CODE, self._TIER),
                indexed_sessions=self._counts(Provider.CLAUDE_CODE),
                transcript_files=transcripts,
            ),
        )
        any_installed = any(p.installed for p in providers)
        needs = any(p.installed and not p.consent_active for p in providers) or not any_installed
        return OnboardingStatus(
            providers=providers,
            any_installed=any_installed,
            needs_onboarding=needs,
            refresh_interval_seconds=self._interval,
            last_refresh_at=self._last_refresh_at,
            last_refresh_error=self._last_refresh_error,
            claude_home_override_supported=self._set_claude_home is not None,
        )

    def accept(self, request: OnboardingAccept) -> OnboardingResult:
        if request.claude_home is not None:
            if self._set_claude_home is None:
                raise OnboardingError("claude_home_override_unsupported")
            candidate = Path(request.claude_home).expanduser()
            if not candidate.is_dir() or not (candidate / "projects").is_dir():
                raise OnboardingError("claude_home_invalid")
            self._set_claude_home(candidate)
        status = self.status()
        installed = {p.provider for p in status.providers if p.installed}
        granted: list[Literal["codex", "claude_code"]] = []
        for key in sorted(request.providers):
            if key not in installed:
                raise OnboardingError(f"{key}_not_installed")
            self._repository.grant_consent(Provider(key), self._TIER)
            granted.append(key)
        indexed = self.refresh(only=frozenset(Provider(k) for k in granted))
        return OnboardingResult(granted=tuple(granted), indexed_sessions=indexed, status=self.status())

    def refresh(self, only: frozenset[Provider] | None = None) -> int:
        """Index every consented (or selected) provider; errors are swallowed per provider."""

        if not self._lock.acquire(blocking=False):
            return 0
        try:
            total = 0
            failed = False
            for provider, index in self._index.items():
                if only is not None and provider not in only:
                    continue
                if not self._repository.has_active_consent(provider, self._TIER):
                    continue
                try:
                    total += int(index())
                except Exception:
                    failed = True
            self._last_refresh_at = self._clock()
            self._last_refresh_error = failed
            return total
        finally:
            self._lock.release()

    @property
    def refresh_interval_seconds(self) -> int:
        return self._interval


class LocalSourceRefreshWorker:
    """Daemon thread: refresh at startup, then every interval; stops cleanly."""

    def __init__(self, service: OnboardingService, *, initial_delay_seconds: float = 5.0) -> None:
        self._service = service
        self._initial_delay = initial_delay_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="local-source-refresh", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        if self._stop.wait(self._initial_delay):
            return
        while not self._stop.is_set():
            try:
                self._service.refresh()
            except Exception:
                pass
            if self._stop.wait(self._service.refresh_interval_seconds):
                return


__all__ = (
    "DEFAULT_REFRESH_INTERVAL_SECONDS",
    "DetectionSignal",
    "LocalSourceRefreshWorker",
    "ONBOARDING_CONTRACT_VERSION",
    "OnboardingAccept",
    "OnboardingError",
    "OnboardingResult",
    "OnboardingService",
    "OnboardingStatus",
    "ProviderDetection",
    "count_transcripts",
    "detect_codex",
)
