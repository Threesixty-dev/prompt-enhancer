import { describe, expect, it } from "vitest";
import type { ApplicationUpdateStatus } from "./contracts";
import {
  ApplicationUpdatePayloadError,
  parseApplicationUpdateStatus,
} from "./applicationUpdateContract";

const CURRENT: ApplicationUpdateStatus = {
  contract_version: "application-update-status.v1",
  contains_private_data: false,
  installed_version: "1.2.3",
  channel: "stable",
  state: "current",
  available_version: null,
  artifact_size_bytes: null,
  downloaded_bytes: null,
  last_checked_at: "2040-01-02T03:04:05Z",
  reason_code: null,
  verification_code: null,
  can_check: true,
  can_stage: false,
  can_cancel: false,
  can_apply: false,
};

describe("parseApplicationUpdateStatus", () => {
  it("accepts one exact content-free status", () => {
    expect(parseApplicationUpdateStatus(structuredClone(CURRENT))).toEqual(CURRENT);
  });

  it.each([
    ["unknown field", { ...CURRENT, source_url: "https://example.invalid" }],
    ["private marker", { ...CURRENT, contains_private_data: true }],
    ["boolean byte count", { ...CURRENT, artifact_size_bytes: true }],
    ["bad timestamp", { ...CURRENT, last_checked_at: "tomorrow" }],
    ["invented action", { ...CURRENT, can_apply: true }],
    ["invented release", { ...CURRENT, available_version: "2.0.0" }],
  ])("rejects %s", (_label, value) => {
    expect(() => parseApplicationUpdateStatus(value)).toThrow(ApplicationUpdatePayloadError);
  });

  it("rejects progress beyond the signed artifact size", () => {
    expect(() => parseApplicationUpdateStatus({
      ...CURRENT,
      state: "staging",
      available_version: "2.0.0",
      artifact_size_bytes: 10,
      downloaded_bytes: 11,
      can_check: false,
      can_cancel: true,
    })).toThrow(ApplicationUpdatePayloadError);
  });

  it("accepts the content-free in-flight state", () => {
    expect(parseApplicationUpdateStatus({
      ...CURRENT,
      state: "checking",
      last_checked_at: null,
      can_check: false,
    })).toMatchObject({ state: "checking", verification_code: null });
  });

  it("requires a bounded verifier code only for a rejected manifest", () => {
    const failed = {
      ...CURRENT,
      state: "failed",
      reason_code: "manifest_rejected",
      verification_code: "bad_signature",
    };
    expect(parseApplicationUpdateStatus(failed)).toMatchObject(failed);
    expect(() => parseApplicationUpdateStatus({
      ...failed,
      reason_code: "release_feed_unavailable",
    })).toThrow(ApplicationUpdatePayloadError);
  });
});
