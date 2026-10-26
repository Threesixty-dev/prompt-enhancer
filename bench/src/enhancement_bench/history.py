"""Bounded history queries over saved Bench runs, without result or prompt output."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Literal

from pydantic import Field, model_validator

from .definitions import Identifier, StrictModel
from .comparisons import comparisons

RunStatus = Literal["queued", "running", "succeeded", "failed", "cancelled", "interrupted", "superseded"]
STATUSES = ("queued", "running", "succeeded", "failed", "cancelled", "interrupted", "superseded")
GENERATION_ALIAS = """COALESCE(json_extract(u.value,'$.stepSettings.review.binding.binding_id'),
    json_extract(u.value,'$.stepSettings.rewrite.binding.binding_id'),
    json_extract(u.value,'$.consumerBinding.binding_id'),
    json_extract(r.effective,'$.consumerBinding.binding_id'))"""
MODEL_STRATEGY = "(json_extract(u.value,'$.strategy') LIKE 'consumer.%' OR json_extract(u.value,'$.strategy')='prompt.check.v1')"


class RunFilters(StrictModel):
    status: RunStatus | None = None
    origin: Literal["gitops", "ui"] | None = None
    experiment: Identifier | None = None
    revision: Identifier | None = None
    model: str | None = Field(None, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
    fromDate: date | None = None
    toDate: date | None = None

    @model_validator(mode="after")
    def date_order(self):
        if self.fromDate and self.toDate and self.fromDate > self.toDate:
            raise ValueError("invalid_date_range")
        return self


def midnight(value: date) -> float:
    return datetime.combine(value, time.min, tzinfo=timezone.utc).timestamp()


def predicate(filters: RunFilters) -> tuple[str, list]:
    clauses, values = [], []
    for name, column in (("status", "status"), ("origin", "origin"), ("experiment", "stable_id"), ("revision", "revision")):
        value = getattr(filters, name)
        if value is not None:
            clauses.append(f"r.{column}=?")
            values.append(value)
    if filters.fromDate:
        clauses.append("r.created>=?")
        values.append(midnight(filters.fromDate))
    if filters.toDate:
        clauses.append("r.created<?")
        values.append(midnight(filters.toDate) + 86400)
    if filters.model:
        clauses.append(f"""(EXISTS (
          SELECT 1 FROM json_each(r.effective,'$.units') u
          WHERE {MODEL_STRATEGY} AND {GENERATION_ALIAS}=?
        ) OR EXISTS (
          SELECT 1 FROM json_each(r.effective,'$.evaluatorProfile.evaluators') e
          WHERE json_extract(e.value,'$.kind')<>'deterministic'
          AND json_extract(e.value,'$.binding_id')=?
        ))""")
        values.extend([filters.model, filters.model])
    return " AND ".join(clauses) or "1=1", values


def summarize(db, filters: RunFilters, where: str, parameters: list) -> dict:
    counts = {row["status"]: row["count"] for row in db.execute(
        f"SELECT r.status,COUNT(*) AS count FROM runs r WHERE {where} GROUP BY r.status", parameters)}
    totals = db.execute(f"""SELECT COUNT(*) AS total,
      SUM(json_array_length(r.effective,'$.subjects') * json_array_length(r.effective,'$.units')) AS attempts
      FROM runs r WHERE {where}""", parameters).fetchone()
    end = filters.toDate or max(datetime.now(timezone.utc).date(), filters.fromDate or date.min)
    start = max(date.fromordinal(max(1, end.toordinal() - 29)), filters.fromDate or date.min)
    activity = {row["day"]: row["count"] for row in db.execute(f"""
      SELECT strftime('%Y-%m-%d',r.created,'unixepoch') AS day,COUNT(*) AS count
      FROM runs r WHERE {where} AND r.created>=? AND r.created<? GROUP BY day
    """, [*parameters, midnight(start), midnight(end) + 86400])}
    days = [start + timedelta(days=i) for i in range(max(0, (end - start).days + 1))]
    experiments = [dict(row) for row in db.execute(f"""
      SELECT r.stable_id AS stableId, COUNT(*) AS runCount,
        SUM(CASE WHEN r.status='queued' THEN 1 ELSE 0 END) AS queuedRuns,
        SUM(CASE WHEN r.status='running' THEN 1 ELSE 0 END) AS runningRuns,
        SUM(json_array_length(r.effective,'$.subjects') * json_array_length(r.effective,'$.units')) AS total,
        SUM((SELECT COUNT(*) FROM attempts a WHERE a.run_id=r.id
             AND a.status IN ('succeeded','failed'))) AS finished
      FROM runs r WHERE {where} GROUP BY r.stable_id
    """, parameters)]
    return {
        "total": totals["total"], "plannedAttempts": totals["attempts"] if totals["total"] else 0,
        "experimentProgress": experiments,
        "statuses": [{"status": status, "count": counts.get(status, 0)} for status in STATUSES],
        "activity": [{"day": day.isoformat(), "count": activity.get(day.isoformat(), 0)} for day in days],
        "activityFrom": start.isoformat(), "activityTo": end.isoformat(),
        "comparisons": comparisons(db, where, parameters),
    }


def model_options(db, filters: RunFilters) -> list[str]:
    # Scope suggestions to the experiment/revision, never to a page or current status.
    where, parameters = predicate(RunFilters(experiment=filters.experiment, revision=filters.revision))
    rows = db.execute(f"""SELECT alias FROM (
      SELECT {GENERATION_ALIAS} AS alias
      FROM runs r,json_each(r.effective,'$.units') u
      WHERE {where} AND {MODEL_STRATEGY}
      UNION
      SELECT json_extract(e.value,'$.binding_id') AS alias
      FROM runs r,json_each(r.effective,'$.evaluatorProfile.evaluators') e
      WHERE {where} AND json_extract(e.value,'$.kind')<>'deterministic'
    ) WHERE alias IS NOT NULL ORDER BY alias LIMIT 200""", [*parameters, *parameters])
    return [row["alias"] for row in rows]
