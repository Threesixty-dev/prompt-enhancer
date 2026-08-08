import { describe, expect, it } from "vitest";
import { parseRoute, routePath } from "./platform";

describe("platform routes", () => {
  it("round-trips a safe task revision route", () => {
    const taskId = "d".repeat(64);
    const route = { name: "task", taskId, revision: 2 } as const;
    expect(parseRoute(routePath(route))).toEqual(route);
  });

  it("round-trips the local-sources route", () => {
    const route = { name: "local_sources" } as const;
    expect(parseRoute(routePath(route))).toEqual(route);
  });

  it.each([
    "/tasks/not-an-id/revisions/1",
    `/tasks/${"d".repeat(64)}/revisions/0`,
    "/unexpected",
  ])("falls back to discovery for %s", (path) => {
    expect(parseRoute(path)).toEqual({ name: "discovery" });
  });
});
