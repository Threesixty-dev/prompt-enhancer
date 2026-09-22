from __future__ import annotations

from prompt_enhancer.application.jobs import AnalysisJobCancellationSignals


def test_stale_attempt_cleanup_cannot_remove_a_replacement_attempt() -> None:
    signals = AnalysisJobCancellationSignals()
    stale_scope = signals.admit(
        job_id="a" * 64,
        lease_owner="b" * 64,
        lease_token="c" * 64,
        automation_grant_id=None,
    )
    stale = stale_scope.__enter__()
    replacement_scope = signals.admit(
        job_id="a" * 64,
        lease_owner="b" * 64,
        lease_token="d" * 64,
        automation_grant_id=None,
    )
    replacement = replacement_scope.__enter__()
    try:
        # Lease recovery admits the new token before the stale handler's
        # finally runs. Its cleanup must leave the replacement registered.
        stale_scope.__exit__(None, None, None)
        assert signals.signal_job("a" * 64) == 1
        assert replacement.event.is_set()
    finally:
        replacement_scope.__exit__(None, None, None)

    assert not stale.event.is_set()
    assert signals.signal_job("a" * 64) == 0


def test_worker_and_grant_wakeups_do_not_cross_attempt_boundaries() -> None:
    signals = AnalysisJobCancellationSignals()
    with signals.admit(
        job_id="a" * 64,
        lease_owner="b" * 64,
        lease_token="c" * 64,
        automation_grant_id="d" * 64,
    ) as first, signals.admit(
        job_id="e" * 64,
        lease_owner="f" * 64,
        lease_token="0" * 64,
        automation_grant_id="1" * 64,
    ) as second:
        assert signals.signal_worker("b" * 64) == 1
        assert first.event.is_set()
        assert not second.event.is_set()

        assert signals.signal_automation_grant("1" * 64) == 1
        assert second.event.is_set()
