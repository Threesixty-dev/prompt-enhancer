import type {
  ModelEnsembleOutcome,
  ModelEnsembleRun,
} from "./contracts";

export class ModelEnsemblePayloadError extends Error {
  constructor() {
    super("Local model ensemble response was invalid");
    this.name = "ModelEnsemblePayloadError";
  }
}

type Row = Record<string, unknown>;

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

export function parseModelEnsembleRun(value: unknown): ModelEnsembleRun {
  const run = record(value);
  exact(run, [
    "run_id", "plan_version", "plan_fingerprint", "source_coverage_state",
    "chunk_count", "model_count", "chunks", "experts", "votes", "chunk_metrics",
    "metrics", "completed_at", "local_only", "content_persisted", "calibration_state",
    "product_metric_eligible",
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
    const metric = record(candidate);
    exact(metric, [
      "metric_key", "value_state", "numerator", "denominator", "numeric_value",
      "known_chunk_count", "abstained_chunk_count", "unsupported_chunk_count",
      "failed_chunk_count", "total_chunk_count", "explanation_code",
      "calibration_state", "product_metric_eligible",
    ]);
    const key = label(metric.metric_key);
    if (metricKeys.has(key)) throw new ModelEnsemblePayloadError();
    metricKeys.add(key);
    const state = oneOf(metric.value_state, VALUE_STATES);
    const known = integer(metric.known_chunk_count, 0, chunkCount);
    const abstained = integer(metric.abstained_chunk_count, 0, chunkCount);
    const unsupported = integer(metric.unsupported_chunk_count, 0, chunkCount);
    const failed = integer(metric.failed_chunk_count, 0, chunkCount);
    if (metric.total_chunk_count !== chunkCount || known + abstained + unsupported + failed !== chunkCount) {
      throw new ModelEnsemblePayloadError();
    }
    label(metric.explanation_code);
    if (metric.calibration_state !== "not_assessed" || metric.product_metric_eligible !== false) {
      throw new ModelEnsemblePayloadError();
    }
    const numerator = metric.numerator === null ? null : integer(metric.numerator, 0, chunkCount);
    const denominator = metric.denominator === null ? null : integer(metric.denominator, 1, chunkCount);
    const numeric = optionalFinite(metric.numeric_value, 0, 1);
    if (state === "known") {
      if (denominator !== known || numerator === null || numeric === null || Math.abs(numeric - numerator / denominator) > 1e-12) {
        throw new ModelEnsemblePayloadError();
      }
    } else if (numerator !== null || denominator !== null || numeric !== null) {
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
