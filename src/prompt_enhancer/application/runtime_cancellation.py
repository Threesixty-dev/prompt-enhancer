"""Content-free cancellation ownership for one local runtime request/turn.

The event is scoped to its caller, not its model. Context propagation through
the ASGI thread pool keeps the existing two-argument model adapter interface.
Socket readers retain the event after response headers have been returned.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import math
from threading import Event, Lock
from time import monotonic
from typing import Callable


class RuntimeCooperativeStop(RuntimeError):
    """A caller stopped work; this is not a failed model observation."""

    def __init__(self, reason_code: str = "runtime_operation_cancelled") -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


class RuntimeCleanupUnconfirmed(RuntimeError):
    """Model resource ownership is uncertain; admitting more work is unsafe."""


MonotonicClock = Callable[[], float]


@dataclass(slots=True)
class _RuntimeDeadline:
    monotonic_cutoff: float
    clock: MonotonicClock
    reason_code: str
    _last_observed: float | None = None
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def remaining_seconds(self) -> float:
        try:
            observed = self.clock()
        except Exception:
            raise RuntimeCooperativeStop(self.reason_code) from None
        if (
            isinstance(observed, bool)
            or not isinstance(observed, (int, float))
            or not math.isfinite(observed)
        ):
            raise RuntimeCooperativeStop(self.reason_code)
        normalized = float(observed)
        with self._lock:
            if (
                self._last_observed is not None
                and normalized < self._last_observed
            ):
                raise RuntimeCooperativeStop(self.reason_code)
            self._last_observed = normalized
        return self.monotonic_cutoff - normalized


_request_cancellation: ContextVar[Event | None] = ContextVar("local_runtime_cancellation", default=None)
_request_deadlines: ContextVar[tuple[_RuntimeDeadline, ...]] = ContextVar(
    "local_runtime_deadline",
    default=(),
)


def current_runtime_cancellation() -> Event | None:
    return _request_cancellation.get()


def runtime_remaining_seconds() -> float | None:
    """Return the current scope's remaining budget in its own clock domain."""

    deadlines = _request_deadlines.get()
    if not deadlines:
        return None
    return min(deadline.remaining_seconds() for deadline in deadlines)


def raise_if_runtime_cancelled(reason: str = "runtime_operation_cancelled") -> None:
    """Stop at a cooperative boundary without exposing operation content.

    Background workers and request-owned adapters share this one content-free
    check.  Code that is not running inside ``runtime_request_scope`` remains
    unaffected, while a scoped shutdown can interrupt bounded provider reads
    before the desktop's cleanup deadline expires.
    """

    cancelled = current_runtime_cancellation()
    if cancelled is not None and cancelled.is_set():
        raise RuntimeCooperativeStop(reason)
    for deadline in _request_deadlines.get():
        if deadline.remaining_seconds() <= 0:
            raise RuntimeCooperativeStop(deadline.reason_code)


@contextmanager
def runtime_request_scope(
    cancelled: Event,
    *,
    deadline_monotonic: float | None = None,
    deadline_reason: str = "runtime_deadline_exceeded",
    monotonic_clock: MonotonicClock = monotonic,
) -> Iterator[None]:
    """Scope cancellation and, optionally, one caller-owned monotonic deadline.

    The deadline is intentionally relative to the supplied clock domain.  This
    lets a durable worker cutoff use its own reconstructed monotonic anchor
    without comparing it to a transport's independent clock origin.
    """

    deadline: _RuntimeDeadline | None = None
    if deadline_monotonic is not None:
        if (
            isinstance(deadline_monotonic, bool)
            or not isinstance(deadline_monotonic, (int, float))
            or not math.isfinite(deadline_monotonic)
        ):
            raise ValueError("runtime deadline must be finite")
        if not deadline_reason or len(deadline_reason) > 128:
            raise ValueError("runtime deadline reason must be bounded")
        deadline = _RuntimeDeadline(
            monotonic_cutoff=float(deadline_monotonic),
            clock=monotonic_clock,
            reason_code=deadline_reason,
        )
    token = _request_cancellation.set(cancelled)
    deadlines = _request_deadlines.get()
    deadline_token = _request_deadlines.set(
        deadlines if deadline is None else (*deadlines, deadline)
    )
    try:
        yield
    finally:
        _request_deadlines.reset(deadline_token)
        _request_cancellation.reset(token)


@contextmanager
def runtime_critical_cleanup_scope() -> Iterator[None]:
    """Finish a bounded safety cleanup after cooperative cancellation.

    A stop may interrupt new work, but it must not interrupt restoration that
    became necessary after a reviewed mutation was already published.
    """

    token = _request_cancellation.set(None)
    deadline_token = _request_deadlines.set(())
    try:
        yield
    finally:
        _request_deadlines.reset(deadline_token)
        _request_cancellation.reset(token)
