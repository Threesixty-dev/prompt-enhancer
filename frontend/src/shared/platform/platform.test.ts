import { describe, expect, it } from "vitest";
import {
  METRIC_ROUTE_CATEGORIES,
  parseRoute,
  routePath,
} from "./platform";

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

  it("round-trips the content-free research lab route", () => {
    const route = { name: "research" } as const;
    expect(parseRoute(routePath(route))).toEqual(route);
  });

  it("round-trips project catalog and project workspace views", () => {
    const projectId = "a".repeat(64);
    expect(parseRoute(routePath({ name: "projects" }))).toEqual({ name: "projects" });
    expect(parseRoute(routePath({ name: "project_overview", projectId }))).toEqual({
      name: "project_overview",
      projectId,
    });
    expect(parseRoute(routePath({ name: "project_sessions", projectId }))).toEqual({
      name: "project_sessions",
      projectId,
    });
  });

  it.each(METRIC_ROUTE_CATEGORIES)(
    "round-trips project and session metric routes for %s",
    (category) => {
      const projectId = "b".repeat(64);
      const sessionId = "c".repeat(64);
      const projectRoute = { name: "project_metrics", projectId, category } as const;
      const sessionRoute = {
        name: "session_metrics",
        projectId,
        sessionId,
        category,
      } as const;
      expect(parseRoute(routePath(projectRoute))).toEqual(projectRoute);
      expect(parseRoute(routePath(sessionRoute))).toEqual(sessionRoute);
    },
  );

  it.each([
    `/projects/${"A".repeat(64)}/overview`,
    `/projects/${"d".repeat(63)}/sessions`,
    `/projects/${"d".repeat(64)}/metrics/not-registered`,
    `/projects/${"d".repeat(64)}/sessions/${"e".repeat(63)}/metrics/tools`,
    `/projects/${"d".repeat(64)}/sessions/${"e".repeat(64)}/metrics/tools/extra`,
  ])("rejects unsafe or non-allowlisted project routes: %s", (path) => {
    expect(parseRoute(path)).toEqual({ name: "discovery" });
  });

  it("does not permit a display label to be interpolated into a project URL", () => {
    expect(() =>
      routePath({
        name: "project_overview",
        projectId: "example-project-label",
      }),
    ).toThrow(/pseudonyms/i);
  });

  it.each([
    "/tasks/not-an-id/revisions/1",
    `/tasks/${"d".repeat(64)}/revisions/0`,
    "/unexpected",
  ])("falls back to discovery for %s", (path) => {
    expect(parseRoute(path)).toEqual({ name: "discovery" });
  });
});
