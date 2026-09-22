import type {
  ObservedCheckCandidate,
  ObservedCheckAuthorityProvenance,
  ObservedCheckCandidateManifest,
  ObservedCheckCriterionReview,
} from "./contracts";

const HEX_64 = /^[a-f0-9]{64}$/u;
const MAX_SEQUENCE = 4_000_000_000;
const MAX_REVISION = 32_000;
const MAX_CANDIDATES = 4_000;
const MAX_TEXT = 32_000;
const MAX_PREVIEW = 16_384;

export class ObservedCheckPayloadError extends Error {
  constructor() {
    super("Observed verification check response was invalid");
    this.name = "ObservedCheckPayloadError";
  }
}

type JsonRecord = Record<string, unknown>;

function fail(): never {
  throw new ObservedCheckPayloadError();
}

function record(value: unknown): JsonRecord {
  if (typeof value !== "object" || value === null || Array.isArray(value)) fail();
  return value as JsonRecord;
}

function exactKeys(value: JsonRecord, expected: readonly string[]): void {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index])) fail();
}

function id(value: unknown): value is string {
  return typeof value === "string" && HEX_64.test(value);
}

function integer(value: unknown, minimum: number, maximum: number): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= minimum && value <= maximum;
}

function boundedText(value: unknown, maximum: number, nonEmpty = false): value is string {
  return typeof value === "string" && value.length <= maximum && (!nonEmpty || value.length > 0);
}

function parseCandidate(value: unknown): ObservedCheckCandidate {
  const candidate = record(value);
  exactKeys(candidate, [
    "candidate_id", "observed_sequence", "check_kind", "observed_outcome",
    "provider_execution_status", "exit_code", "source_completion_schema_version",
    "outcome_interpreter_version", "classifier_version", "normalizer_version",
    "rule_id", "local_only", "content_persisted",
  ]);
  if (
    !id(candidate.candidate_id)
    || !integer(candidate.observed_sequence, 0, MAX_SEQUENCE)
    || candidate.check_kind !== "test"
    || (candidate.observed_outcome !== "passed" && candidate.observed_outcome !== "check_failed")
    || candidate.provider_execution_status !== "completed"
    || (candidate.exit_code !== 0 && candidate.exit_code !== 1)
    || candidate.source_completion_schema_version !== "observed-check-completion-v1"
    || candidate.outcome_interpreter_version !== "pytest-exit-status-v1"
    || candidate.classifier_version !== "local-command-rules-v1"
    || candidate.normalizer_version !== "strict-shell-free-v2"
    || (candidate.rule_id !== "test.pytest" && candidate.rule_id !== "test.py_test")
    || candidate.local_only !== true
    || candidate.content_persisted !== false
    || ((candidate.exit_code === 0) !== (candidate.observed_outcome === "passed"))
  ) fail();
  return candidate as unknown as ObservedCheckCandidate;
}

function parseManifest(value: unknown, sessionId: string): ObservedCheckCandidateManifest {
  const manifest = record(value);
  exactKeys(manifest, [
    "session_id", "opportunity_set_fingerprint", "opportunity_id", "requirement_id",
    "expected_source_run_id", "source_window_fingerprint", "requirement_plan_confirmation_id",
    "requirement_plan_proposal_id", "expected_predecessor_authority_id", "through_revision",
    "candidate_manifest_fingerprint", "candidates", "schema_version", "local_only",
    "content_persisted",
  ]);
  if (
    manifest.session_id !== sessionId
    || !id(sessionId)
    || !id(manifest.opportunity_set_fingerprint)
    || !id(manifest.opportunity_id)
    || !id(manifest.requirement_id)
    || !id(manifest.expected_source_run_id)
    || !id(manifest.source_window_fingerprint)
    || !id(manifest.requirement_plan_confirmation_id)
    || !id(manifest.requirement_plan_proposal_id)
    || (manifest.expected_predecessor_authority_id !== null && !id(manifest.expected_predecessor_authority_id))
    || !integer(manifest.through_revision, 0, MAX_REVISION)
    || !id(manifest.candidate_manifest_fingerprint)
    || !Array.isArray(manifest.candidates)
    || manifest.candidates.length > MAX_CANDIDATES
    || manifest.schema_version !== "requirement-observed-check-review-v1"
    || manifest.local_only !== true
    || manifest.content_persisted !== false
  ) fail();
  const candidates = manifest.candidates.map(parseCandidate);
  const candidateIds = new Set<string>();
  for (let index = 1; index < candidates.length; index += 1) {
    if (candidates[index - 1].observed_sequence >= candidates[index].observed_sequence) fail();
  }
  for (const candidate of candidates) {
    if (candidateIds.has(candidate.candidate_id)) fail();
    candidateIds.add(candidate.candidate_id);
  }
  return { ...manifest, candidates } as ObservedCheckCandidateManifest;
}

export function parseObservedCheckCandidateManifest(
  value: unknown,
  sessionId: string,
): ObservedCheckCandidateManifest {
  return parseManifest(value, sessionId);
}

export function parseObservedCheckCriterionReview(
  value: unknown,
  sessionId: string,
): ObservedCheckCriterionReview {
  const review = record(value);
  exactKeys(review, [
    "session_id", "opportunity_set_fingerprint", "opportunity_id", "requirement_id",
    "expected_source_run_id", "source_window_fingerprint", "requirement_plan_confirmation_id",
    "requirement_plan_proposal_id", "expected_predecessor_authority_id", "through_revision",
    "candidate_manifest_fingerprint", "candidate", "requirement_text", "check_tool_name",
    "check_invocation_preview", "check_effect_preview", "review_receipt_id", "review_fingerprint",
    "review_expires_at", "full_criterion_coverage_acknowledgement_required", "objective_result_issued",
    "schema_version", "local_only", "content_persisted",
  ]);
  const candidate = parseCandidate(review.candidate);
  const expiry = typeof review.review_expires_at === "string" ? Date.parse(review.review_expires_at) : Number.NaN;
  if (
    review.session_id !== sessionId
    || !id(sessionId)
    || !id(review.opportunity_set_fingerprint)
    || !id(review.opportunity_id)
    || !id(review.requirement_id)
    || !id(review.expected_source_run_id)
    || !id(review.source_window_fingerprint)
    || !id(review.requirement_plan_confirmation_id)
    || !id(review.requirement_plan_proposal_id)
    || (review.expected_predecessor_authority_id !== null && !id(review.expected_predecessor_authority_id))
    || !integer(review.through_revision, 0, MAX_REVISION)
    || !id(review.candidate_manifest_fingerprint)
    || !boundedText(review.requirement_text, MAX_TEXT, true)
    || !boundedText(review.check_tool_name, 512, true)
    || !boundedText(review.check_invocation_preview, MAX_PREVIEW, true)
    || !(review.check_effect_preview === null || boundedText(review.check_effect_preview, MAX_PREVIEW))
    || !id(review.review_receipt_id)
    || !id(review.review_fingerprint)
    || typeof review.review_expires_at !== "string"
    || !Number.isFinite(expiry)
    || expiry <= Date.now()
    || expiry > Date.now() + 10 * 60_000
    || review.full_criterion_coverage_acknowledgement_required !== true
    || review.objective_result_issued !== false
    || review.schema_version !== "requirement-observed-check-review-v1"
    || review.local_only !== true
    || review.content_persisted !== false
  ) fail();
  return { ...review, candidate } as ObservedCheckCriterionReview;
}

export function parseObservedCheckAuthorityProvenance(
  value: unknown,
  sessionId: string,
  authorityRecordId: string,
): ObservedCheckAuthorityProvenance {
  const provenance = record(value);
  exactKeys(provenance, [
    "authority_record_id", "session_id", "opportunity_set_fingerprint", "opportunity_id", "requirement_id",
    "source_run_id", "source_window_fingerprint", "requirement_plan_confirmation_id", "requirement_plan_proposal_id",
    "candidate_manifest_fingerprint", "source_reference_id", "coverage_review_reference_id", "observed_sequence",
    "check_kind", "provider_execution_status", "observed_outcome", "exit_code", "source_completion_schema_version",
    "outcome_interpreter_version", "classifier_version", "normalizer_version", "rule_id", "coverage_review_version",
    "full_criterion_coverage_acknowledged", "provenance_fingerprint", "schema_version", "local_only", "content_persisted",
  ]);
  if (
    provenance.authority_record_id !== authorityRecordId || provenance.session_id !== sessionId
    || !id(sessionId) || !id(authorityRecordId) || !id(provenance.opportunity_set_fingerprint)
    || !id(provenance.opportunity_id) || !id(provenance.requirement_id) || !id(provenance.source_run_id)
    || !id(provenance.source_window_fingerprint) || !id(provenance.requirement_plan_confirmation_id)
    || !id(provenance.requirement_plan_proposal_id) || !id(provenance.candidate_manifest_fingerprint)
    || !id(provenance.source_reference_id) || !id(provenance.coverage_review_reference_id)
    || !integer(provenance.observed_sequence, 0, MAX_SEQUENCE) || provenance.check_kind !== "test"
    || provenance.provider_execution_status !== "completed"
    || (provenance.observed_outcome !== "passed" && provenance.observed_outcome !== "check_failed")
    || (provenance.exit_code !== 0 && provenance.exit_code !== 1)
    || provenance.source_completion_schema_version !== "observed-check-completion-v1"
    || provenance.outcome_interpreter_version !== "pytest-exit-status-v1"
    || provenance.classifier_version !== "local-command-rules-v1"
    || provenance.normalizer_version !== "strict-shell-free-v2"
    || (provenance.rule_id !== "test.pytest" && provenance.rule_id !== "test.py_test")
    || provenance.coverage_review_version !== "native-full-criterion-coverage-v1"
    || provenance.full_criterion_coverage_acknowledged !== true || !id(provenance.provenance_fingerprint)
    || provenance.schema_version !== "observed-check-authority-provenance-v1"
    || provenance.local_only !== true || provenance.content_persisted !== false
    || ((provenance.exit_code === 0) !== (provenance.observed_outcome === "passed"))
  ) fail();
  return provenance as unknown as ObservedCheckAuthorityProvenance;
}
