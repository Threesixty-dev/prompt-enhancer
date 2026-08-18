import { describe, expect, it } from "vitest";

import {
  SOCIAL_SYNTHETIC_PRINCIPAL_ID,
  createSyntheticSocialSnapshot,
} from "../../../shared/api/socialHub";
import { SYNTHETIC_DIRECT_TRANSFER_OPT_IN } from "./directTransferProtocol";
import { syntheticDirectTransferPrototypeIsAvailable } from "./DirectTransferPrototypePanel";

describe("synthetic WebRTC prototype composition gate", () => {
  it("requires development, the exact opt-in, the registered synthetic origin, and fictional principal", () => {
    const snapshot = createSyntheticSocialSnapshot();
    expect(syntheticDirectTransferPrototypeIsAvailable({
      snapshot,
      development: true,
      buildOptIn: SYNTHETIC_DIRECT_TRANSFER_OPT_IN,
    })).toBe(true);
    expect(syntheticDirectTransferPrototypeIsAvailable({
      snapshot,
      development: false,
      buildOptIn: SYNTHETIC_DIRECT_TRANSFER_OPT_IN,
    })).toBe(false);
    expect(syntheticDirectTransferPrototypeIsAvailable({
      snapshot,
      development: true,
      buildOptIn: "enabled",
    })).toBe(false);
    expect(syntheticDirectTransferPrototypeIsAvailable({
      snapshot: { ...snapshot, origin: "local_loopback" },
      development: true,
      buildOptIn: SYNTHETIC_DIRECT_TRANSFER_OPT_IN,
    })).toBe(false);
    expect(syntheticDirectTransferPrototypeIsAvailable({
      snapshot: { ...snapshot, fictional: false },
      development: true,
      buildOptIn: SYNTHETIC_DIRECT_TRANSFER_OPT_IN,
    })).toBe(false);
    expect(syntheticDirectTransferPrototypeIsAvailable({
      snapshot: { ...snapshot, principal_id: "0".repeat(64) },
      development: true,
      buildOptIn: SYNTHETIC_DIRECT_TRANSFER_OPT_IN,
    })).toBe(false);
    expect(snapshot.principal_id).toBe(SOCIAL_SYNTHETIC_PRINCIPAL_ID);
  });
});

