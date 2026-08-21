from __future__ import annotations

import hashlib
from prompt_enhancer.interfaces.http.user_presence import (
    UserPresenceApprovalManager,
)


SESSION = "a" * 64
PROPOSAL = "b" * 64


def _path() -> str:
    return (
        f"/v1/sessions/{SESSION}/metric-lifecycle-evidence/"
        f"proposals/{PROPOSAL}/decision"
    )


def test_user_presence_is_one_shot_and_bound_to_exact_body_and_path() -> None:
    manager = UserPresenceApprovalManager()
    body = b'{"decision":"confirm"}'
    token = manager.issue(
        method="POST",
        path=_path(),
        body_sha256=hashlib.sha256(body).hexdigest(),
    )

    assert manager.consume(
        token=token,
        method="POST",
        path=_path(),
        body=body,
    ) is True
    assert manager.consume(
        token=token,
        method="POST",
        path=_path(),
        body=body,
    ) is False


def test_mismatch_burns_capability_and_unknown_actions_are_rejected() -> None:
    manager = UserPresenceApprovalManager()
    body = b'{"decision":"reject"}'
    token = manager.issue(
        method="POST",
        path=_path(),
        body_sha256=hashlib.sha256(body).hexdigest(),
    )
    assert manager.consume(
        token=token,
        method="POST",
        path=_path(),
        body=b'{"decision":"confirm"}',
    ) is False
    assert manager.consume(
        token=token,
        method="POST",
        path=_path(),
        body=body,
    ) is False

    assert manager.action_label("POST", "/v1/unreviewed/action") is None
    try:
        manager.issue(
            method="POST",
            path="/v1/unreviewed/action",
            body_sha256="0" * 64,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("unreviewed action received an approval")
