import { describe, expect, it } from "vitest";
import { resolveRuntimeDataMode } from "./runtimeMode";

describe("runtime data mode", () => {
  it("keeps ordinary Vite development synthetic", () => {
    expect(
      resolveRuntimeDataMode({ development: true, viteMode: "development" }),
    ).toBe("synthetic");
  });

  it("allows an explicit local-backend development mode", () => {
    expect(resolveRuntimeDataMode({ development: true, viteMode: "real" })).toBe(
      "local",
    );
  });

  it("keeps production builds on the integrated local backend", () => {
    expect(
      resolveRuntimeDataMode({ development: false, viteMode: "production" }),
    ).toBe("local");
  });
});
