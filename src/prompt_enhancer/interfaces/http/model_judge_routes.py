"""Model-judge lane: judge one session, sweep the calibration sample, agreement."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path

from ...application.analysis.model_judge import (
    JudgeAgreementReport,
    JudgeOutcome,
    JudgeSweepStatus,
    ModelJudgeError,
    ModelJudgeService,
)
from ...domain import PSEUDONYM_PATTERN


_STATUS = {"no_active_model": 409, "session_not_found": 404, "consent_required": 403, "window_unavailable": 409,
           "model_unreachable": 502, "model_not_active": 409, "model_error": 502, "model_reply_invalid": 502}


def create_model_judge_router(
    require_local_auth: Callable[..., None],
    service: ModelJudgeService,
    sample_session_ids: Callable[[], tuple[str, ...]],
) -> APIRouter:
    router = APIRouter(prefix="/v1/model-judge", tags=["model-judge"], dependencies=[Depends(require_local_auth)])

    @router.post("/sessions/{session_id}", response_model=JudgeOutcome)
    def judge_session(session_id: Annotated[str, Path(pattern=PSEUDONYM_PATTERN.pattern)]) -> JudgeOutcome:
        try:
            return service.judge(session_id)
        except ModelJudgeError as error:
            raise HTTPException(status_code=_STATUS.get(error.code, 500), detail={"code": error.code}) from None

    @router.post("/sweep", response_model=JudgeSweepStatus)
    def sweep() -> JudgeSweepStatus:
        try:
            return service.start_sweep(sample_session_ids())
        except ModelJudgeError as error:
            raise HTTPException(status_code=_STATUS.get(error.code, 500), detail={"code": error.code}) from None

    @router.get("/sweep", response_model=JudgeSweepStatus)
    def sweep_status() -> JudgeSweepStatus:
        return service.sweep_status()

    @router.get("/agreement", response_model=JudgeAgreementReport)
    def agreement() -> JudgeAgreementReport:
        return service.agreement()

    return router


__all__ = ("create_model_judge_router",)
