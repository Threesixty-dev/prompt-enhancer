"""Content-free, paired metric summaries of saved attempts."""

import hashlib
import json
import math

MAX_GROUPS = 200
PROVENANCE_KEYS = ("provider", "adapter_version", "model", "model_revision", "model_license",
                   "tokenizer_revision", "rubric_version", "metric_version", "redactor_version",
                   "identity_source", "reported_model", "reasoning_effort")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def identity(provenance):
    return {key: value for key, value in (provenance or {}).items() if key in PROVENANCE_KEYS}


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def comparisons(db, where, parameters):
    # Select only evaluation and identity fields; prompt, request and result text
    # never enters the history response or this aggregation.
    rows = db.execute(f"""SELECT r.stable_id,r.revision,a.unit_id,
      json_extract(a.result,'$.core_version') AS core_version,
      json_extract(a.result,'$.before') AS before_metrics,
      json_extract(a.result,'$.after') AS after_metrics,
      json_extract(a.result,'$.deltas') AS deltas,
      json_extract(a.result,'$.strategy') AS strategy,
      json_extract(a.result,'$.consumer_binding.binding_id') AS model,
      json_extract(a.result,'$.consumer_provenance') AS generation
      FROM runs r JOIN attempts a ON a.run_id=r.id
      WHERE {where} AND a.result IS NOT NULL ORDER BY r.created DESC,r.id DESC,a.position
    """, parameters)
    groups, truncated = {}, False
    for row in rows:
        before = json.loads(row["before_metrics"] or "[]")
        after = json.loads(row["after_metrics"] or "[]")
        deltas = json.loads(row["deltas"] or "[]")
        generation = identity(json.loads(row["generation"] or "null"))
        for evaluator in before:
            right = next((value for value in after if value["evaluator_id"] == evaluator["evaluator_id"]), None)
            for metric in evaluator.get("metrics", []):
                scope = {
                    "experiment": row["stable_id"], "revision": row["revision"],
                    "coreVersion": row["core_version"], "evaluator": evaluator["evaluator_id"],
                    "kind": evaluator["kind"], "metric": metric["key"],
                    "provenance": identity(evaluator.get("provenance")),
                }
                config = {**scope, "scopeKey": digest(scope), "variant": row["unit_id"],
                          "strategy": row["strategy"], "model": row["model"], "generation": generation}
                key = digest(config)
                if key not in groups:
                    if len(groups) >= MAX_GROUPS:
                        truncated = True
                        continue
                    groups[key] = {**config, "count": 0, "excluded": 0, "before": None, "after": None, "delta": None}
                group = groups[key]
                other = next((m for m in right.get("metrics", []) if m["key"] == metric["key"]), None) if right else None
                delta = next((d for d in deltas if d["evaluator_id"] == evaluator["evaluator_id"] and d["metric_key"] == metric["key"]), None)
                comparable = (right and other and delta and delta["state"] == "comparable"
                              and evaluator["kind"] == right["kind"]
                              and evaluator.get("provenance") is not None
                              and evaluator["provenance"] == right.get("provenance")
                              and metric["state"] == other["state"] == "known"
                              and all(numeric(value) for value in (metric.get("value"), other.get("value"), delta.get("value"))))
                if not comparable:
                    group["excluded"] += 1
                    continue
                group["count"] += 1
                for name, value in (("before", metric["value"]), ("after", other["value"]), ("delta", delta["value"])):
                    group[name] = value if group["count"] == 1 else group[name] * (1 - 1 / group["count"]) + value / group["count"]
    return {"groups": list(groups.values()), "truncated": truncated, "groupLimit": MAX_GROUPS}
