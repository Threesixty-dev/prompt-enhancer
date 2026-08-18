import type {
  ModelEnsembleOutcome,
  ModelEnsembleRun,
} from "./contracts";
import { MetricDefinitionsOutOfDateError, parseMetricPublicationV2 } from "./metricPublicationV2Contract";

export class ModelEnsemblePayloadError extends Error {
  constructor() {
    super("Local model ensemble response was invalid");
    this.name = "ModelEnsemblePayloadError";
  }
}

type Row = Record<string, unknown>;
type EnsembleMetric = ModelEnsembleRun["metrics"][number];
type TypedMetric = ModelEnsembleRun["typed_metrics"][number];
type PredictiveMetric = ModelEnsembleRun["predictive_metrics"][number];

const HEX_64 = /^[0-9a-f]{64}$/;
const SAFE_LABEL = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

function record(value: unknown): Row {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new ModelEnsemblePayloadError();
  }
  return value as Row;
}

function exact(value: Row, keys: readonly string[]): void {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    throw new ModelEnsemblePayloadError();
  }
}

function integer(value: unknown, minimum: number, maximum: number): number {
  if (!Number.isInteger(value) || (value as number) < minimum || (value as number) > maximum) {
    throw new ModelEnsemblePayloadError();
  }
  return value as number;
}

function finite(value: unknown, minimum = 0, maximum = Number.MAX_SAFE_INTEGER): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < minimum || value > maximum) {
    throw new ModelEnsemblePayloadError();
  }
  return value;
}

function optionalFinite(value: unknown, minimum = 0, maximum = Number.MAX_SAFE_INTEGER): number | null {
  return value === null ? null : finite(value, minimum, maximum);
}

function label(value: unknown): string {
  if (typeof value !== "string" || !SAFE_LABEL.test(value)) {
    throw new ModelEnsemblePayloadError();
  }
  return value;
}

function oneOf<T extends string>(value: unknown, choices: readonly T[]): T {
  if (typeof value !== "string" || !choices.includes(value as T)) {
    throw new ModelEnsemblePayloadError();
  }
  return value as T;
}

function utcTimestamp(value: unknown): string {
  if (
    typeof value !== "string" ||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$/.test(value)
  ) {
    throw new ModelEnsemblePayloadError();
  }
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/.exec(value);
  const parsed = new Date(value);
  if (
    match === null ||
    Number.isNaN(parsed.getTime()) ||
    parsed.getUTCFullYear() !== Number(match[1]) ||
    parsed.getUTCMonth() + 1 !== Number(match[2]) ||
    parsed.getUTCDate() !== Number(match[3]) ||
    parsed.getUTCHours() !== Number(match[4]) ||
    parsed.getUTCMinutes() !== Number(match[5]) ||
    parsed.getUTCSeconds() !== Number(match[6])
  ) {
    throw new ModelEnsemblePayloadError();
  }
  return value;
}

const VOTE_STATES = ["present", "absent", "abstain", "unsupported", "failed"] as const;
const VALUE_STATES = ["known", "unknown", "not_applicable", "abstained", "execution_error"] as const;
const EXPERT_ROLES = ["retrieval", "reranking", "scope_nli", "structured_rubric"] as const;
const EXPERT_STATUSES = ["completed", "unavailable", "resource_exhausted", "failed"] as const;
const PREDICTIVE_STATES = [
  "unavailable", "experimental", "calibrated", "out_of_distribution", "execution_error",
] as const;

/**
 * Validate one content-free aggregate metric against its enclosing chunk bound.
 * Structural graph cells do not count as eligible metric observations, so the
 * receipt total may be smaller than the physical chunk count.
 * Kept public so the slim trajectory boundary can reuse the exact same trust
 * rules without accepting the much larger run graph.
 */
export function parseModelEnsembleMetricReceipt(
  value: unknown,
  chunkCount: number,
): EnsembleMetric {
  const metric = record(value);
  exact(metric, [
    "metric_key", "value_state", "numerator", "denominator", "numeric_value",
    "known_chunk_count", "abstained_chunk_count", "unsupported_chunk_count",
    "failed_chunk_count", "total_chunk_count", "explanation_code",
    "calibration_state", "product_metric_eligible",
  ]);
  const state = oneOf(metric.value_state, VALUE_STATES);
  const known = integer(metric.known_chunk_count, 0, chunkCount);
  const abstained = integer(metric.abstained_chunk_count, 0, chunkCount);
  const unsupported = integer(metric.unsupported_chunk_count, 0, chunkCount);
  const failed = integer(metric.failed_chunk_count, 0, chunkCount);
  const total = integer(metric.total_chunk_count, 1, chunkCount);
  if (known + abstained + unsupported + failed !== total) {
    throw new ModelEnsemblePayloadError();
  }
  label(metric.metric_key);
  label(metric.explanation_code);
  if (metric.calibration_state !== "not_assessed" || metric.product_metric_eligible !== false) {
    throw new ModelEnsemblePayloadError();
  }
  const numerator = metric.numerator === null ? null : integer(metric.numerator, 0, total);
  const denominator = metric.denominator === null ? null : integer(metric.denominator, 1, total);
  const numeric = optionalFinite(metric.numeric_value, 0, 1);
  if (state === "known") {
    if (denominator !== known || numerator === null || numeric === null || Math.abs(numeric - numerator / denominator) > 1e-12) {
      throw new ModelEnsemblePayloadError();
    }
  } else if (numerator !== null || denominator !== null || numeric !== null) {
    throw new ModelEnsemblePayloadError();
  }
  return value as EnsembleMetric;
}

export function parseModelEnsembleTypedMetricReceipt(value: unknown): TypedMetric {
  const metric = record(value);
  exact(metric, [
    "metric_key", "metric_version", "value_state", "numerator", "denominator",
    "numeric_value", "observed_message_count", "eligible_message_count", "coverage",
    "explanation_code", "error_code", "projection_source", "metric_schema_version",
    "engine_version", "algorithm_id", "algorithm_version", "rubric_version",
    "calibration_state", "product_metric_eligible",
  ]);
  label(metric.metric_key);
  integer(metric.metric_version, 1, 1_000_000);
  const state = oneOf(metric.value_state, VALUE_STATES);
  const observed = integer(metric.observed_message_count, 0, 100);
  const eligible = integer(metric.eligible_message_count, 0, 10_000_000);
  const coverage = finite(metric.coverage, 0, 1);
  const expectedCoverage = eligible === 0 ? 0 : observed / eligible;
  if (observed > eligible || Math.abs(coverage - expectedCoverage) > 1e-12) {
    throw new ModelEnsemblePayloadError();
  }
  const numerator = metric.numerator === null
    ? null
    : integer(metric.numerator, 0, 1_000_000);
  const denominator = metric.denominator === null
    ? null
    : integer(metric.denominator, 1, 1_000_000);
  const numeric = optionalFinite(metric.numeric_value, 0, 1);
  const errorCode = metric.error_code === null ? null : label(metric.error_code);
  if (state === "known") {
    if (
      numerator === null || denominator === null || numerator > denominator
      || numeric === null || errorCode !== null
      || Math.abs(numeric - numerator / denominator) > 1e-12
    ) {
      throw new ModelEnsemblePayloadError();
    }
  } else if (
    numerator !== null || denominator !== null || numeric !== null
    || ((state === "execution_error") !== (errorCode !== null))
  ) {
    throw new ModelEnsemblePayloadError();
  }
  label(metric.explanation_code);
  if (
    metric.projection_source !== "deterministic_typed_contract"
    || metric.calibration_state !== "not_assessed"
    || metric.product_metric_eligible !== false
  ) {
    throw new ModelEnsemblePayloadError();
  }
  integer(metric.metric_schema_version, 1, 1_000_000);
  label(metric.engine_version);
  label(metric.algorithm_id);
  label(metric.algorithm_version);
  label(metric.rubric_version);
  return value as TypedMetric;
}

export function parseModelPredictiveMetricSummary(value: unknown): PredictiveMetric {
  const metric = record(value);
  exact(metric, [
    "metric_key", "target", "state", "mean", "median", "q05", "q25", "q75", "q95",
    "applicability_probability", "pending_probability", "model_disagreement",
    "effective_observation_count", "model_set_version", "calibration_version",
    "contract_version", "contract_fingerprint", "product_metric_eligible",
  ]);
  label(metric.metric_key);
  oneOf(metric.target, ["metric_value", "outcome_forecast"] as const);
  const state = oneOf(metric.state, PREDICTIVE_STATES);
  const mean = optionalFinite(metric.mean, 0, 1);
  const median = optionalFinite(metric.median, 0, 1);
  const q05 = optionalFinite(metric.q05, 0, 1);
  const q25 = optionalFinite(metric.q25, 0, 1);
  const q75 = optionalFinite(metric.q75, 0, 1);
  const q95 = optionalFinite(metric.q95, 0, 1);
  const applicability = optionalFinite(metric.applicability_probability, 0, 1);
  const pending = optionalFinite(metric.pending_probability, 0, 1);
  optionalFinite(metric.model_disagreement, 0, 1);
  const observations = integer(metric.effective_observation_count, 0, 10_000_000);
  label(metric.model_set_version);
  label(metric.calibration_version);
  label(metric.contract_version);
  if (typeof metric.contract_fingerprint !== "string" || !HEX_64.test(metric.contract_fingerprint)) {
    throw new ModelEnsemblePayloadError();
  }
  if (metric.product_metric_eligible !== false) throw new ModelEnsemblePayloadError();
  const hasDistribution = ["experimental", "calibrated", "out_of_distribution"].includes(state);
  if (hasDistribution) {
    if (
      mean === null || median === null || q05 === null || q25 === null || q75 === null || q95 === null
      || applicability === null || pending === null || observations < 1
      || !(q05 <= q25 && q25 <= median && median <= q75 && q75 <= q95)
      || (state === "experimental" && metric.calibration_version !== "not-calibrated-v1")
    ) {
      throw new ModelEnsemblePayloadError();
    }
  } else if (
    mean !== null || median !== null || q05 !== null || q25 !== null || q75 !== null || q95 !== null
    || applicability !== null || pending !== null || metric.model_disagreement !== null
    || observations !== 0
  ) {
    throw new ModelEnsemblePayloadError();
  }
  return value as PredictiveMetric;
}

export function parseModelEnsembleRun(value: unknown): ModelEnsembleRun {
  const run = record(value);
  exact(run, [
    "run_id", "plan_version", "plan_fingerprint", "source_coverage_state",
    "chunk_count", "model_count", "chunks", "experts", "votes", "chunk_metrics",
    "metrics", "metric_projection_version", "metric_projection_completed_at",
    "typed_metrics", "metric_publication_v2", "metric_evidence_readiness_v2",
    "predictive_projection_version", "predictive_projected_at",
    "predictive_metrics", "predictive_model_stages", "completed_at", "local_only", "content_persisted",
    "calibration_state", "product_metric_eligible",
  ]);
  if (
    typeof run.run_id !== "string" || !HEX_64.test(run.run_id) ||
    run.plan_version !== "local-shadow-ensemble-v1" ||
    typeof run.plan_fingerprint !== "string" || !HEX_64.test(run.plan_fingerprint) ||
    !["complete_window", "incomplete_source"].includes(String(run.source_coverage_state)) ||
    run.model_count !== 10 || run.local_only !== true || run.content_persisted !== false ||
    run.calibration_state !== "not_assessed" || run.product_metric_eligible !== false
  ) {
    throw new ModelEnsemblePayloadError();
  }
  const chunkCount = integer(run.chunk_count, 1, 8);
  utcTimestamp(run.completed_at);

  if (!Array.isArray(run.chunks) || run.chunks.length !== chunkCount) {
    throw new ModelEnsemblePayloadError();
  }
  run.chunks.forEach((candidate, ordinal) => {
    const chunk = record(candidate);
    exact(chunk, ["ordinal", "source_message_count", "fragment_count", "character_count"]);
    if (integer(chunk.ordinal, 0, 7) !== ordinal) throw new ModelEnsemblePayloadError();
    integer(chunk.source_message_count, 1, 100);
    integer(chunk.fragment_count, 1, 128);
    integer(chunk.character_count, 1, 100_000);
  });

  if (!Array.isArray(run.experts) || run.experts.length !== 10) {
    throw new ModelEnsemblePayloadError();
  }
  const expertRoles = new Map<string, string>();
  const roleCounts = new Map<string, number>();
  run.experts.forEach((candidate, ordinal) => {
    const expert = record(candidate);
    exact(expert, [
      "ordinal", "model_key", "role", "repository_id", "revision", "license_spdx",
      "contributes_to_decision", "status", "error_code", "device",
      "inference_latency_ms", "peak_accelerator_memory_mb", "process_rss_mb",
      "unloaded_after_stage",
    ]);
    if (integer(expert.ordinal, 0, 9) !== ordinal || expert.unloaded_after_stage !== true) {
      throw new ModelEnsemblePayloadError();
    }
    const modelKey = label(expert.model_key);
    const role = oneOf(expert.role, EXPERT_ROLES);
    if (expertRoles.has(modelKey)) throw new ModelEnsemblePayloadError();
    expertRoles.set(modelKey, role);
    roleCounts.set(role, (roleCounts.get(role) ?? 0) + 1);
    if (typeof expert.repository_id !== "string" || !/^[A-Za-z0-9._-]+\/[A-Za-z0-9._-]+$/.test(expert.repository_id)) {
      throw new ModelEnsemblePayloadError();
    }
    if (typeof expert.revision !== "string" || !/^[0-9a-f]{40}$/.test(expert.revision)) {
      throw new ModelEnsemblePayloadError();
    }
    oneOf(expert.license_spdx, ["MIT", "Apache-2.0"] as const);
    if (typeof expert.contributes_to_decision !== "boolean") throw new ModelEnsemblePayloadError();
    const status = oneOf(expert.status, EXPERT_STATUSES);
    const errorCode = expert.error_code === null ? null : label(expert.error_code);
    const device = expert.device === null ? null : oneOf(expert.device, ["cpu", "cuda", "mps"] as const);
    optionalFinite(expert.inference_latency_ms);
    optionalFinite(expert.peak_accelerator_memory_mb);
    optionalFinite(expert.process_rss_mb);
    if ((status === "completed") !== (errorCode === null && device !== null)) {
      throw new ModelEnsemblePayloadError();
    }
  });
  if (
    roleCounts.get("retrieval") !== 4 || roleCounts.get("reranking") !== 2 ||
    roleCounts.get("scope_nli") !== 3 || roleCounts.get("structured_rubric") !== 1
  ) {
    throw new ModelEnsemblePayloadError();
  }

  if (!Array.isArray(run.metrics) || run.metrics.length < 1 || run.metrics.length > 20) {
    throw new ModelEnsemblePayloadError();
  }
  const metricKeys = new Set<string>();
  run.metrics.forEach((candidate) => {
    const metric = parseModelEnsembleMetricReceipt(candidate, chunkCount);
    const key = metric.metric_key;
    if (metricKeys.has(key)) throw new ModelEnsemblePayloadError();
    metricKeys.add(key);
  });
  const projectionVersion = run.metric_projection_version;
  const projectionCompletedAt = run.metric_projection_completed_at;
  if (!Array.isArray(run.typed_metrics) || run.typed_metrics.length > 20) {
    throw new ModelEnsemblePayloadError();
  }
  if (
    (projectionVersion === null) !== (projectionCompletedAt === null)
    || (projectionVersion === null) !== (run.typed_metrics.length === 0)
    || (projectionVersion !== null && projectionVersion !== "coaching-typed-projection-v1")
  ) {
    throw new ModelEnsemblePayloadError();
  }
  if (projectionCompletedAt !== null) utcTimestamp(projectionCompletedAt);
  const typedKeys = new Set<string>();
  run.typed_metrics.forEach((candidate) => {
    const metric = parseModelEnsembleTypedMetricReceipt(candidate);
    if (!metricKeys.has(metric.metric_key) || typedKeys.has(metric.metric_key)) {
      throw new ModelEnsemblePayloadError();
    }
    typedKeys.add(metric.metric_key);
  });
  if (run.typed_metrics.length > 0 && typedKeys.size !== metricKeys.size) {
    throw new ModelEnsemblePayloadError();
  }
  if (run.metric_publication_v2 !== null) {
    let publication: ReturnType<typeof parseMetricPublicationV2>;
    try {
      publication = parseMetricPublicationV2(run.metric_publication_v2);
    } catch (error) {
      // Definitions out of date is a distinct client-update condition, not a
      // malformed run: surfaces show the update alert instead of "reconnecting".
      if (error instanceof MetricDefinitionsOutOfDateError) throw error;
      throw new ModelEnsemblePayloadError();
    }
    const publishedKeys = new Set(publication.metrics.map((item) => item.state.metric_key));
    if (
      publishedKeys.size !== metricKeys.size
      || [...metricKeys].some((metricKey) => !publishedKeys.has(metricKey))
    ) {
      throw new ModelEnsemblePayloadError();
    }
  }
  if (
    run.metric_evidence_readiness_v2 !== null
    && (
      typeof run.metric_evidence_readiness_v2 !== "object"
      || Array.isArray(run.metric_evidence_readiness_v2)
    )
  ) {
    throw new ModelEnsemblePayloadError();
  }
  if (run.metric_publication_v2 === null && run.metric_evidence_readiness_v2 !== null) {
    throw new ModelEnsemblePayloadError();
  }

  const predictiveVersion = run.predictive_projection_version;
  const predictiveProjectedAt = run.predictive_projected_at;
  if (!Array.isArray(run.predictive_metrics) || run.predictive_metrics.length > 20) {
    throw new ModelEnsemblePayloadError();
  }
  if (!Array.isArray(run.predictive_model_stages) || run.predictive_model_stages.length > 8) {
    throw new ModelEnsemblePayloadError();
  }
  if (
    (predictiveVersion === null) !== (predictiveProjectedAt === null)
    || (predictiveVersion === null) !== (run.predictive_metrics.length === 0)
    || (predictiveVersion === null) !== (run.predictive_model_stages.length === 0)
    || (predictiveVersion !== null && predictiveVersion !== "local-probabilistic-radar-v1")
  ) {
    throw new ModelEnsemblePayloadError();
  }
  if (predictiveProjectedAt !== null) utcTimestamp(predictiveProjectedAt);
  const predictiveKeys = new Set<string>();
  run.predictive_metrics.forEach((candidate) => {
    const metric = parseModelPredictiveMetricSummary(candidate);
    if (!metricKeys.has(metric.metric_key) || predictiveKeys.has(metric.metric_key)) {
      throw new ModelEnsemblePayloadError();
    }
    predictiveKeys.add(metric.metric_key);
  });
  if (run.predictive_metrics.length > 0 && predictiveKeys.size !== metricKeys.size) {
    throw new ModelEnsemblePayloadError();
  }
  const predictiveModels = new Set<string>();
  run.predictive_model_stages.forEach((candidate) => {
    const stage = record(candidate);
    exact(stage, [
      "model_key", "repository_id", "revision", "status", "error_code", "device",
      "quantization", "inference_latency_ms", "peak_accelerator_memory_mb", "process_rss_mb",
      "unloaded_after_stage",
    ]);
    const modelKey = label(stage.model_key);
    if (predictiveModels.has(modelKey) || stage.unloaded_after_stage !== true) {
      throw new ModelEnsemblePayloadError();
    }
    predictiveModels.add(modelKey);
    if (typeof stage.repository_id !== "string" || !/^[A-Za-z0-9._-]+\/[A-Za-z0-9._-]+$/.test(stage.repository_id)) {
      throw new ModelEnsemblePayloadError();
    }
    if (typeof stage.revision !== "string" || !/^[0-9a-f]{40}$/.test(stage.revision)) {
      throw new ModelEnsemblePayloadError();
    }
    const status = oneOf(stage.status, EXPERT_STATUSES);
    const errorCode = stage.error_code === null ? null : label(stage.error_code);
    const device = stage.device === null ? null : oneOf(stage.device, ["cpu", "cuda", "mps"] as const);
    oneOf(stage.quantization, ["none", "bitsandbytes_nf4"] as const);
    optionalFinite(stage.inference_latency_ms);
    optionalFinite(stage.peak_accelerator_memory_mb, 0, 6_144);
    optionalFinite(stage.process_rss_mb, 0, 8_192);
    if ((status === "completed") !== (errorCode === null && device !== null)) {
      throw new ModelEnsemblePayloadError();
    }
  });

  const expectedPairs = new Set<string>();
  for (let chunk = 0; chunk < chunkCount; chunk += 1) {
    for (const metric of metricKeys) expectedPairs.add(`${chunk}\u0000${metric}`);
  }
  if (!Array.isArray(run.chunk_metrics) || run.chunk_metrics.length !== expectedPairs.size) {
    throw new ModelEnsemblePayloadError();
  }
  const chunkPairs = new Set<string>();
  run.chunk_metrics.forEach((candidate) => {
    const metric = record(candidate);
    exact(metric, [
      "chunk_ordinal", "metric_key", "value_state", "numerator", "denominator",
      "rubric_vote", "contributing_nli_votes", "diagnostic_nli_votes", "reason_code",
    ]);
    const pair = `${integer(metric.chunk_ordinal, 0, chunkCount - 1)}\u0000${label(metric.metric_key)}`;
    if (!expectedPairs.has(pair) || chunkPairs.has(pair)) throw new ModelEnsemblePayloadError();
    chunkPairs.add(pair);
    const state = oneOf(metric.value_state, VALUE_STATES);
    const numerator = metric.numerator === null ? null : integer(metric.numerator, 0, 1);
    const denominator = metric.denominator === null ? null : integer(metric.denominator, 1, 1);
    oneOf(metric.rubric_vote, VOTE_STATES);
    integer(metric.contributing_nli_votes, 0, 2);
    integer(metric.diagnostic_nli_votes, 0, 1);
    label(metric.reason_code);
    if ((state === "known") !== (numerator !== null && denominator === 1)) {
      throw new ModelEnsemblePayloadError();
    }
  });

  if (!Array.isArray(run.votes) || run.votes.length !== expectedPairs.size * 4) {
    throw new ModelEnsemblePayloadError();
  }
  const votesByPair = new Map<string, Set<string>>();
  const voteRoleCounts = new Map<string, { nli: number; rubric: number }>();
  run.votes.forEach((candidate) => {
    const vote = record(candidate);
    exact(vote, [
      "chunk_ordinal", "metric_key", "model_key", "role", "state", "raw_score",
      "evidence_fragment_count", "reason_code",
    ]);
    const pair = `${integer(vote.chunk_ordinal, 0, chunkCount - 1)}\u0000${label(vote.metric_key)}`;
    const modelKey = label(vote.model_key);
    const role = oneOf(vote.role, ["scope_nli", "structured_rubric"] as const);
    if (!expectedPairs.has(pair) || expertRoles.get(modelKey) !== role) throw new ModelEnsemblePayloadError();
    const identities = votesByPair.get(pair) ?? new Set<string>();
    if (identities.has(modelKey)) throw new ModelEnsemblePayloadError();
    identities.add(modelKey);
    votesByPair.set(pair, identities);
    const counts = voteRoleCounts.get(pair) ?? { nli: 0, rubric: 0 };
    if (role === "scope_nli") {
      counts.nli += 1;
    } else {
      counts.rubric += 1;
    }
    voteRoleCounts.set(pair, counts);
    const state = oneOf(vote.state, VOTE_STATES);
    const raw = optionalFinite(vote.raw_score, 0, 1);
    if ((state === "present" || state === "absent") !== (raw !== null)) throw new ModelEnsemblePayloadError();
    integer(vote.evidence_fragment_count, 0, 8);
    label(vote.reason_code);
  });
  for (const pair of expectedPairs) {
    const counts = voteRoleCounts.get(pair);
    if (votesByPair.get(pair)?.size !== 4 || counts?.nli !== 3 || counts.rubric !== 1) {
      throw new ModelEnsemblePayloadError();
    }
  }
  return value as ModelEnsembleRun;
}

export function parseModelEnsembleOutcome(value: unknown): ModelEnsembleOutcome {
  const outcome = record(value);
  exact(outcome, ["run", "applied"]);
  if (typeof outcome.applied !== "boolean") throw new ModelEnsemblePayloadError();
  parseModelEnsembleRun(outcome.run);
  return value as ModelEnsembleOutcome;
}
