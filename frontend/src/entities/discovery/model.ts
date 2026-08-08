import type { CandidateListItem, CandidateSignal } from "../../shared/api/contracts";

export type { CandidateListItem, CandidateSignal };

export function candidateLabel(candidateId: string): string {
  return `Candidate ${candidateId.slice(0, 6)}`;
}

export function evidenceDirectionLabel(direction: CandidateSignal["direction"]): string {
  if (direction === "supports_link") return "Supports grouping";
  if (direction === "supports_boundary") return "Supports a boundary";
  return "Unknown evidence";
}
