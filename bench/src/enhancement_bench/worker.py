"""Bounded serial admission with durable attempts and conservative recovery."""

from __future__ import annotations

import errno
import sys
import threading
import time
from contextlib import contextmanager

from .client import CoreClient
from .errors import BenchError
from .protocol import CORE_TERMINAL, Contracts
from .store import Store


@contextmanager
def exclusive_worker(store: Store):
    with store.path.with_suffix(".worker-lock").open("a+b") as lock:
        if sys.platform == "win32":
            import msvcrt

            # Windows permits a byte-range lock beyond the empty file's end.
            lock.seek(0)
            acquire = lambda: msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            release = lambda: msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            acquire = lambda: fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            release = lambda: fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        try:
            acquire()
        except OSError as error:
            if error.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                raise BenchError("worker_already_active", 503) from None
            raise BenchError("worker_lock_unavailable", 503) from None
        try:
            yield
        finally:
            release()


class Worker:
    def __init__(self, store: Store, contracts: Contracts, runtime, *,
                 client_factory=CoreClient, poll_seconds=0.5, ready_seconds=30,
                 run_seconds=1800, cancel_seconds=15, admission_check=None):
        self.store, self.contracts, self.runtime = store, contracts, runtime
        self.client_factory = client_factory
        self.poll_seconds, self.ready_seconds = poll_seconds, ready_seconds
        self.run_seconds, self.cancel_seconds = run_seconds, cancel_seconds
        self.admission_check = admission_check
        self.stop = threading.Event()

    def reconcile(self):
        self.store.recover()
        self.recover_cleanup()

    def recover_cleanup(self):
        row = self.store.claim_cleanup_check()
        if row is not None:
            self._cleanup(row["id"], row["container_name"])

    def _cleanup(self, run_id, container_name):
        try:
            self.runtime.cleanup(run_id, container_name)
            self.store.cleanup_confirmed(run_id)
            return True
        except BenchError as error:
            self.store.cleanup_failed(run_id, error.code)
        except Exception:
            self.store.cleanup_failed(run_id, "container_cleanup_unconfirmed")
        return False

    def serve(self):
        with exclusive_worker(self.store):
            self.reconcile()
            while not self.stop.is_set():
                if not self.step():
                    self.stop.wait(self.poll_seconds)

    def _cancel_requested(self, run_id):
        return self.stop.is_set() or self.store.run(run_id)["cancel_requested"]

    def _await_ready(self, client, run, deadline):
        ready_deadline = min(deadline, time.monotonic() + self.ready_seconds)
        while time.monotonic() < ready_deadline:
            if self._cancel_requested(run["id"]):
                raise BenchError("cancelled_before_submission")
            try:
                client.ready(run["effective"]["enhancerVersion"])
                return
            except BenchError as error:
                if error.code not in {"core_transport_uncertain", "core_not_ready"}:
                    raise
            self.stop.wait(self.poll_seconds)
        raise BenchError("core_readiness_timeout")

    def step(self) -> bool:
        self.recover_cleanup()
        if self.admission_check is not None and not self.admission_check():
            return False
        run = self.store.claim()
        if run is None:
            return False
        client, state, code = None, "succeeded", None
        outcomes, attempt = [], None
        deadline = time.monotonic() + self.run_seconds
        try:
            # Validate every unit before pulling an image or admitting a consumer call.
            requests = [(item, self.contracts.request(run, item)) for item in run["attempts"]]
            if self._cancel_requested(run["id"]):
                raise BenchError("cancelled_before_submission")
            endpoint = self.runtime.launch(run)
            client = self.client_factory(endpoint, self.contracts)
            self._await_ready(client, run, deadline)
            capabilities = client.capabilities()
            if capabilities.get("core_version") != run["effective"]["enhancerVersion"]:
                raise BenchError("core_version_mismatch")
            reference = run["effective"].get("workflow")
            if reference and not any(all(manifest.get(key) == value for key, value in reference.items())
                                     for manifest in capabilities.get("workflows", [])):
                raise BenchError("core_workflow_unsupported")
            for item, request in requests:
                if self._cancel_requested(run["id"]):
                    state, code = "cancelled", "cancelled_before_submission"
                    break
                if time.monotonic() >= deadline:
                    raise BenchError("run_deadline_exceeded")
                self.store.attempt_started(run["id"], item["id"], request)
                attempt = item
                # Never automatically submit again after a lost acknowledgement.
                progress = client.submit(request)
                sequence, cancellation_deadline = -1, None
                timed_out = False
                deadline_cancelled = False
                while True:
                    if progress["sequence"] < sequence:
                        raise BenchError("core_progress_regressed")
                    sequence = progress["sequence"]
                    self.store.attempt_progress(item["id"], progress)
                    if progress["status"] in CORE_TERMINAL:
                        break
                    now = time.monotonic()
                    timed_out = timed_out or now >= deadline
                    cancel_requested = self._cancel_requested(run["id"])
                    if (cancel_requested or timed_out) and cancellation_deadline is None:
                        client.cancel(request)
                        deadline_cancelled = timed_out and not cancel_requested
                        cancellation_deadline = now + self.cancel_seconds
                    if cancellation_deadline is not None and now >= cancellation_deadline:
                        raise BenchError("core_cancellation_unconfirmed")
                    time.sleep(self.poll_seconds)
                    progress = client.progress(request)
                result = client.result(request, run["effective"]["enhancerVersion"])
                if result["status"] != progress["status"]:
                    raise BenchError("core_terminal_state_mismatch")
                status = {"timed_out": "failed", "uncertain": "interrupted"}.get(result["status"], result["status"])
                self.store.attempt_finished(run["id"], item["id"], status, result)
                attempt = None
                outcomes.append(result["assertion_outcome"])
                # The complete result is durable before releasing ephemeral retention.
                client.forget(request)
                if status != "succeeded":
                    state = status
                    code = "run_deadline_exceeded" if deadline_cancelled else "core_" + result["status"]
                    break
                if timed_out:
                    state, code = "failed", "run_deadline_exceeded"
                    break
        except BenchError as error:
            code = error.code
            state = "cancelled" if code == "cancelled_before_submission" else "failed"
            if attempt is not None:
                # Any unconfirmed transport/protocol state after admission is uncertain.
                state = "failed" if code in {"core_rejected", "core_admission_denied"} else "interrupted"
                self.store.attempt_finished(run["id"], attempt["id"], state, error=code)
        except Exception:
            state, code = "interrupted", "worker_internal_failure"
            if attempt is not None:
                self.store.attempt_finished(run["id"], attempt["id"], state, error=code)
        finally:
            if client is not None:
                client.close()
            if not self._cleanup(run["id"], run["container_name"]):
                state, code = "interrupted", "container_cleanup_unconfirmed"
            assertion = ("failed" if "failed" in outcomes else "unknown" if "unknown" in outcomes
                         or len(outcomes) != len(run["attempts"]) else "passed" if "passed" in outcomes
                         else "not_evaluated")
            self.store.finish(run["id"], state, code, assertion)
        return True
