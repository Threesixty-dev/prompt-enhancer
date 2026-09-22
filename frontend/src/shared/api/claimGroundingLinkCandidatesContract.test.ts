import { describe, expect, it } from "vitest";
import {
  ClaimGroundingLinkCandidatesPayloadError,
  parseClaimGroundingLinkCandidateManifest,
} from "./claimGroundingLinkCandidatesContract";

const id = (value: string) => value.repeat(64).slice(0, 64);
const expected = { sessionId: id("a"), censusId: id("b"), sourceRunId: id("c"), sourceWindowFingerprint: id("d"), censusFingerprint: id("e"), manifestFingerprint: id("f") };

function manifest(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    session_id: expected.sessionId,
    census_id: expected.censusId,
    source_run_id: expected.sourceRunId,
    source_window_fingerprint: expected.sourceWindowFingerprint,
    census_fingerprint: expected.censusFingerprint,
    manifest_fingerprint: expected.manifestFingerprint,
    observed_set_fingerprint: id("0"),
    source_schema_version: "synthetic-source/v1",
    text_adapter_version: "synthetic-adapter+v1",
    observed_set_schema_version: "claim-grounding-observed-set-v1",
    observed_set_policy_version: "native-reviewed-claim-link-coverage-v1",
    material_candidates: [{ candidate_id: id("1"), message_id: id("2"), message_sequence: 3, clause_index: 0 }],
    observed_checks: [{ source_reference_id: id("3"), observed_sequence: 4_000_000_000, provider: "claude_code", check_kind: "test", outcome: "check_failed", provider_execution_status: "completed", exit_code: 1, source_completion_schema_version: "observed-check-completion-v1", outcome_interpreter_version: "pytest-exit-status-v1", classifier_version: "local-command-rules-v1", normalizer_version: "strict-shell-free-v2", rule_id: "test.py_test" }],
    proposal_only: true,
    measured: false,
    metric_authority_established: false,
    content_persisted: false,
    ...overrides,
  };
}

describe("claim grounding link candidate manifest contract", () => {
  it("accepts content-free material coordinates and check metadata", () => {
    expect(parseClaimGroundingLinkCandidateManifest(manifest(), expected).observed_checks[0].provider).toBe("claude_code");
  });

  it("accepts an empty check surface and material-only candidates", () => {
    const value = manifest({ observed_checks: [], material_candidates: [{ candidate_id: id("4"), message_id: id("5"), message_sequence: 0, clause_index: 2 }] });
    expect(parseClaimGroundingLinkCandidateManifest(value, expected).observed_checks).toEqual([]);
  });

  it.each([
    (value: Record<string, unknown>) => { value.raw_text = "not allowed"; },
    (value: Record<string, unknown>) => { (value.material_candidates as Record<string, unknown>[])[0].clause_index = 128; },
    (value: Record<string, unknown>) => { (value.observed_checks as Record<string, unknown>[])[0].exit_code = 0; },
    (value: Record<string, unknown>) => { (value.observed_checks as Record<string, unknown>[])[0].provider = "unknown"; },
    (value: Record<string, unknown>) => { (value.observed_checks as Record<string, unknown>[])[0].observed_sequence = 4_000_000_001; },
    (value: Record<string, unknown>) => { (value.observed_checks as Record<string, unknown>[])[0].tool_name = "never returned pre-native"; },
    (value: Record<string, unknown>) => { value.source_run_id = id("9"); },
  ])("rejects content, drift, and incoherent provenance", (alter) => {
    const value = structuredClone(manifest());
    alter(value);
    expect(() => parseClaimGroundingLinkCandidateManifest(value, expected)).toThrow(ClaimGroundingLinkCandidatesPayloadError);
  });
});
