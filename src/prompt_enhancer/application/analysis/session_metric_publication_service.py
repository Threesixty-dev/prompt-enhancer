"""Read-only V2 publication of one persisted, immutable analysis run.

The persisted V1 run stays the source record and is never rewritten: this
service opens a read transaction, republishes the run against the V2 registry,
and returns a current projection.  Nothing here reads provider content, refreshes
a provider, retains a transcript, or writes a row, so the publication cannot
drift away from the receipt it was derived from — it is recomputed on demand and
disappears with the run when a privacy deletion cascades.

The typed objective-evidence lane is not persisted alongside a V1 run, so the
five evidence-lane contracts publish fail-closed here.  That is deliberate: a
stored conversational ratio must never become objective proof of task success.
"""

from __future__ import annotations

from pydantic import Field

from ...domain import Provider, StrictModel
from ..persistence import (
    AnalysisRunStatus,
    SessionAnalysisRunRepository,
)
from .coaching_baselines import (
    COACHING_METRIC_PACK_KEY,
    COACHING_METRIC_PACK_VERSION,
)
from .metric_publication_v2 import (
    MetricPublicationSource,
    MetricPublicationV2,
    publish_metric_states_v2,
    rehydrate_metric_states_v2,
)


SESSION_METRIC_PUBLICATION_KEY = "metric.contract-v2.publication.current"
SESSION_METRIC_PUBLICATION_VERSION = 1


class SessionMetricPublication(StrictModel):
    """Current projection identity plus the complete twenty-metric bundle."""

    projection_key: str = SESSION_METRIC_PUBLICATION_KEY
    projection_version: int = Field(
        default=SESSION_METRIC_PUBLICATION_VERSION, ge=1
    )
    run_id: str
    provider: Provider
    source_metric_pack_key: str
    source_metric_pack_version: int = Field(ge=1)
    source_result_count: int = Field(ge=0)
    publication: MetricPublicationV2


class SessionMetricPublicationError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class SessionMetricPublicationService:
    """Project a completed coaching-pack run onto the V2 publication contract."""

    def __init__(self, analyses: SessionAnalysisRunRepository) -> None:
        self._analyses = analyses

    def get(self, run_id: str) -> SessionMetricPublication | None:
        run = self._analyses.get(run_id)
        if run is None:
            return None
        if run.status is not AnalysisRunStatus.COMPLETED:
            raise SessionMetricPublicationError("publication_run_not_completed")
        draft = run.draft
        if (
            draft.metric_pack_key != COACHING_METRIC_PACK_KEY
            or draft.metric_pack_version != COACHING_METRIC_PACK_VERSION
        ):
            raise SessionMetricPublicationError("publication_pack_unsupported")
        results = self._analyses.get_results(run_id)
        return SessionMetricPublication(
            run_id=draft.run_id,
            provider=draft.provider,
            source_metric_pack_key=draft.metric_pack_key,
            source_metric_pack_version=draft.metric_pack_version,
            source_result_count=len(results),
            publication=publish_metric_states_v2(
                rehydrate_metric_states_v2(results),
                source=MetricPublicationSource.PERSISTED_RUN_REHYDRATION,
            ),
        )


__all__ = [
    "SESSION_METRIC_PUBLICATION_KEY",
    "SESSION_METRIC_PUBLICATION_VERSION",
    "SessionMetricPublication",
    "SessionMetricPublicationError",
    "SessionMetricPublicationService",
]
