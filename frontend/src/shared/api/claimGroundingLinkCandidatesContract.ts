import type {
  ClaimGroundingLinkCandidateManifest,
  ClaimGroundingLinkMaterialCandidate,
  ClaimGroundingLinkObservedCheckMetadata,
} from "./contracts";

export class ClaimGroundingLinkCandidatesPayloadError extends Error {
  constructor() {
    super("Claim-grounding link candidates response was invalid");
    this.name = "ClaimGroundingLinkCandidatesPayloadError";
  }
}

type JsonRecord = Record<string, unknown>;
const ID = /^[a-f0-9]{64}$/u;
const MAX_MATERIAL = 12_800;
const MAX_CHECKS = 4_000;
const MAX_SEQUENCE = 4_000_000_000;
const TOP_KEYS = ["session_id", "census_id", "source_run_id", "source_window_fingerprint", "census_fingerprint", "manifest_fingerprint", "observed_set_fingerprint", "source_schema_version", "text_adapter_version", "observed_set_schema_version", "observed_set_policy_version", "material_candidates", "observed_checks", "proposal_only", "measured", "metric_authority_established", "content_persisted"] as const;
const MATERIAL_KEYS = ["candidate_id", "message_id", "message_sequence", "clause_index"] as const;
const CHECK_KEYS = ["source_reference_id", "observed_sequence", "provider", "check_kind", "outcome", "provider_execution_status", "exit_code", "source_completion_schema_version", "outcome_interpreter_version", "classifier_version", "normalizer_version", "rule_id"] as const;

function fail(): never { throw new ClaimGroundingLinkCandidatesPayloadError(); }
function record(value: unknown): JsonRecord {
  if (typeof value !== "object" || value === null || Array.isArray(value)) fail();
  return value as JsonRecord;
}
function exactKeys(value: JsonRecord, keys: readonly string[]): void {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) fail();
}
function id(value: unknown): value is string { return typeof value === "string" && ID.test(value); }
function safeNonNegativeInteger(value: unknown): value is number { return typeof value === "number" && Number.isSafeInteger(value) && value >= 0; }
function safeVersion(value: unknown): value is string { return typeof value === "string" && /^[A-Za-z0-9][A-Za-z0-9._+:/-]{0,127}$/u.test(value); }

function parseMaterial(value: unknown): ClaimGroundingLinkMaterialCandidate {
  const candidate = record(value); exactKeys(candidate, MATERIAL_KEYS);
  if (!id(candidate.candidate_id) || !id(candidate.message_id) || !safeNonNegativeInteger(candidate.message_sequence) || !safeNonNegativeInteger(candidate.clause_index) || candidate.clause_index >= 128) fail();
  return { candidate_id: candidate.candidate_id, message_id: candidate.message_id, message_sequence: candidate.message_sequence, clause_index: candidate.clause_index };
}

function parseCheck(value: unknown): ClaimGroundingLinkObservedCheckMetadata {
  const check = record(value); exactKeys(check, CHECK_KEYS);
  if (!id(check.source_reference_id) || !safeNonNegativeInteger(check.observed_sequence) || check.observed_sequence > MAX_SEQUENCE || (check.provider !== "codex" && check.provider !== "claude_code" && check.provider !== "synthetic") || check.check_kind !== "test" || (check.outcome !== "passed" && check.outcome !== "check_failed") || check.provider_execution_status !== "completed" || (check.exit_code !== 0 && check.exit_code !== 1) || ((check.exit_code === 0) !== (check.outcome === "passed")) || check.source_completion_schema_version !== "observed-check-completion-v1" || check.outcome_interpreter_version !== "pytest-exit-status-v1" || check.classifier_version !== "local-command-rules-v1" || check.normalizer_version !== "strict-shell-free-v2" || (check.rule_id !== "test.pytest" && check.rule_id !== "test.py_test")) fail();
  return { source_reference_id: check.source_reference_id, observed_sequence: check.observed_sequence, provider: check.provider, check_kind: "test", outcome: check.outcome, provider_execution_status: "completed", exit_code: check.exit_code, source_completion_schema_version: "observed-check-completion-v1", outcome_interpreter_version: "pytest-exit-status-v1", classifier_version: "local-command-rules-v1", normalizer_version: "strict-shell-free-v2", rule_id: check.rule_id };
}

export function parseClaimGroundingLinkCandidateManifest(value: unknown, expected: { sessionId: string; censusId: string; sourceRunId: string; sourceWindowFingerprint: string; censusFingerprint: string; manifestFingerprint: string }): ClaimGroundingLinkCandidateManifest {
  const manifest = record(value); exactKeys(manifest, TOP_KEYS);
  if (!id(expected.sessionId) || !id(expected.censusId) || !id(expected.sourceRunId) || !id(expected.sourceWindowFingerprint) || !id(expected.censusFingerprint) || !id(expected.manifestFingerprint) || manifest.session_id !== expected.sessionId || manifest.census_id !== expected.censusId || manifest.source_run_id !== expected.sourceRunId || manifest.source_window_fingerprint !== expected.sourceWindowFingerprint || manifest.census_fingerprint !== expected.censusFingerprint || manifest.manifest_fingerprint !== expected.manifestFingerprint || !id(manifest.observed_set_fingerprint) || !safeVersion(manifest.source_schema_version) || !safeVersion(manifest.text_adapter_version) || manifest.observed_set_schema_version !== "claim-grounding-observed-set-v1" || manifest.observed_set_policy_version !== "native-reviewed-claim-link-coverage-v1" || !Array.isArray(manifest.material_candidates) || manifest.material_candidates.length > MAX_MATERIAL || !Array.isArray(manifest.observed_checks) || manifest.observed_checks.length > MAX_CHECKS || manifest.proposal_only !== true || manifest.measured !== false || manifest.metric_authority_established !== false || manifest.content_persisted !== false) fail();
  const materialCandidates = manifest.material_candidates.map(parseMaterial);
  const observedChecks = manifest.observed_checks.map(parseCheck);
  if (new Set(materialCandidates.map((candidate) => candidate.candidate_id)).size !== materialCandidates.length || new Set(materialCandidates.map((candidate) => `${candidate.message_id}:${candidate.clause_index}`)).size !== materialCandidates.length || new Set(observedChecks.map((check) => check.source_reference_id)).size !== observedChecks.length) fail();
  return { session_id: manifest.session_id, census_id: manifest.census_id, source_run_id: manifest.source_run_id, source_window_fingerprint: manifest.source_window_fingerprint, census_fingerprint: manifest.census_fingerprint, manifest_fingerprint: manifest.manifest_fingerprint, observed_set_fingerprint: manifest.observed_set_fingerprint, source_schema_version: manifest.source_schema_version, text_adapter_version: manifest.text_adapter_version, observed_set_schema_version: "claim-grounding-observed-set-v1", observed_set_policy_version: "native-reviewed-claim-link-coverage-v1", material_candidates: materialCandidates, observed_checks: observedChecks, proposal_only: true, measured: false, metric_authority_established: false, content_persisted: false };
}
