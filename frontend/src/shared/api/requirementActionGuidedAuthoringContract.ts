import type {
  RequirementActionEvidenceContract,
  RequirementActionGuidedAuthoringCommand,
  RequirementActionGuidedAuthoringReview,
  RequirementActionProposal,
} from "./contracts";
import {
  parseRequirementActionProposal,
  parseRequirementActionReviewSurface,
  requirementActionProposalMatchesContract,
} from "./requirementActionEvidenceContract";

export class RequirementActionGuidedAuthoringPayloadError extends Error {}

const id = (value: unknown): value is string => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
const row = (value: unknown): Record<string, unknown> => {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new RequirementActionGuidedAuthoringPayloadError();
  return value as Record<string, unknown>;
};
const exact = (value: Record<string, unknown>, keys: readonly string[]) => {
  if (Object.keys(value).length !== keys.length || keys.some((key) => !(key in value))) throw new RequirementActionGuidedAuthoringPayloadError();
};
const utc = (value: unknown): value is string => typeof value === "string"
  && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|\+00:00)$/.test(value)
  && Number.isFinite(Date.parse(value));

export function parseRequirementActionGuidedAuthoringReview(
  value: unknown,
  expected: { sessionId: string; contract: RequirementActionEvidenceContract },
): RequirementActionGuidedAuthoringReview {
  const item = row(value);
  exact(item, [
    "contract_version", "session_id", "source_run_id", "source_window_fingerprint",
    "requirement_plan_confirmation_id", "requirement_plan_evidence_fingerprint",
    "candidate_manifest_fingerprint", "expected_predecessor_confirmation_id",
    "authoring_receipt_id", "descriptor_set_fingerprint", "requirements", "candidates",
    "candidate_memberships", "review_context_expires_at", "authoring_receipt_expires_at",
    "all_requirements_and_candidates_included", "raw_text_persisted", "local_only",
  ]);
  const contract = expected.contract;
  if (
    item.contract_version !== "requirement-action-guided-authoring-v1"
    || item.session_id !== expected.sessionId
    || item.source_run_id !== contract.expected_source_run_id
    || item.source_window_fingerprint !== contract.source_window_fingerprint
    || item.requirement_plan_confirmation_id !== contract.requirement_plan_confirmation_id
    || item.requirement_plan_evidence_fingerprint !== contract.requirement_plan_evidence_fingerprint
    || item.candidate_manifest_fingerprint !== contract.candidate_manifest.manifest_fingerprint
    || item.expected_predecessor_confirmation_id !== contract.expected_predecessor_confirmation_id
    || !id(item.authoring_receipt_id) || !id(item.descriptor_set_fingerprint)
    || !utc(item.review_context_expires_at) || !utc(item.authoring_receipt_expires_at)
    || Date.parse(item.authoring_receipt_expires_at) <= Date.now()
    || Date.parse(item.authoring_receipt_expires_at) > Date.parse(item.review_context_expires_at)
    || item.all_requirements_and_candidates_included !== true
    || item.raw_text_persisted !== false || item.local_only !== true
  ) throw new RequirementActionGuidedAuthoringPayloadError();
  try {
    const surface = parseRequirementActionReviewSurface(
      item.requirements, item.candidates, item.candidate_memberships,
      {
        requirements: contract.requirements,
        candidates: contract.candidate_manifest.actions,
        linkedActionIds: contract.requirements.map(() => []),
        candidateMetadataFingerprintVersion: contract.candidate_metadata_fingerprint_version,
      },
    );
    return {
      ...item,
      requirements: surface.requirements,
      candidates: surface.candidates,
      candidate_memberships: surface.candidateMemberships,
    } as unknown as RequirementActionGuidedAuthoringReview;
  } catch {
    throw new RequirementActionGuidedAuthoringPayloadError();
  }
}

export function parseRequirementActionGuidedAuthoringProposal(
  value: unknown,
  expected: {
    sessionId: string;
    contract: RequirementActionEvidenceContract;
    command: RequirementActionGuidedAuthoringCommand;
  },
): { proposal: RequirementActionProposal; applied: boolean } {
  const item = row(value);
  exact(item, ["proposal", "applied"]);
  const proposal = parseRequirementActionProposal(item.proposal);
  const { command, contract } = expected;
  const linked = command.links.map((link) => link.action_candidate_indexes.map(
    (index) => contract.candidate_manifest.actions[index]?.action_id,
  ).sort());
  if (
    typeof item.applied !== "boolean"
    || proposal.session_id !== expected.sessionId
    || proposal.source_run_id !== command.expected_source_run_id
    || proposal.source_window_fingerprint !== command.source_window_fingerprint
    || proposal.requirement_plan_confirmation_id !== command.requirement_plan_confirmation_id
    || proposal.requirement_plan_evidence_fingerprint !== command.requirement_plan_evidence_fingerprint
    || proposal.candidate_manifest_fingerprint !== command.candidate_manifest_fingerprint
    || proposal.expected_predecessor_confirmation_id !== command.expected_predecessor_confirmation_id
    || proposal.status !== "proposed" || proposal.decision !== null
    || proposal.decision_id !== null || proposal.confirmation_authority !== null
    || proposal.producer_receipt.kind !== "local_review_ui"
    || proposal.producer_receipt.authority !== "untrusted_local_authoring_commitment"
    || !requirementActionProposalMatchesContract(proposal, contract)
    || command.links.length !== contract.requirements.length
    || command.links.some((link, index) => link.requirement_index !== index || linked[index].some((id) => typeof id !== "string"))
    || proposal.links.length !== contract.requirements.length
    || proposal.links.some((link, index) => link.requirement_id !== contract.requirements[index]?.requirement_id
      || JSON.stringify(link.action_ids) !== JSON.stringify(linked[index]))
  ) throw new RequirementActionGuidedAuthoringPayloadError();
  return { proposal, applied: item.applied };
}
