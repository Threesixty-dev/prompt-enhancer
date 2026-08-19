export type AppRoute =
  | { name: "discovery" }
  | { name: "local_sources" }
  | { name: "analysis_jobs" }
  | { name: "research" }
  | { name: "team" }
  | { name: "social" }
  | { name: "task_flow" }
  | { name: "projects" }
  | { name: "sessions" }
  | { name: "project_overview"; projectId: string }
  | { name: "project_sessions"; projectId: string }
  | { name: "project_automation"; projectId: string }
  | { name: "project_metrics"; projectId: string; category: MetricCategory }
  | {
      name: "session_metrics";
      projectId: string;
      sessionId: string;
      category: MetricCategory;
    }
  | { name: "task"; taskId: string; revision: number };

export interface PlatformAdapter {
  currentRoute(): AppRoute;
  navigate(route: AppRoute): void;
  subscribe(listener: (route: AppRoute) => void): () => void;
}

const PSEUDONYM = /^[a-f0-9]{64}$/;

export function isPseudonym(value: string): boolean {
  return PSEUDONYM.test(value);
}

export const METRIC_ROUTE_CATEGORIES = [
  "readiness",
  "execution",
  "tools",
  "model-usage",
  "outcome",
  "prompt-quality",
  "reasoning",
  "other",
] as const;

export type MetricCategory = (typeof METRIC_ROUTE_CATEGORIES)[number];

const METRIC_CATEGORY = new Set<string>(METRIC_ROUTE_CATEGORIES);

export function isMetricCategory(value: string): value is MetricCategory {
  return METRIC_CATEGORY.has(value);
}

export function parseRoute(pathname: string): AppRoute {
  if (/^\/local-sources\/?$/.test(pathname)) return { name: "local_sources" };
  if (/^\/analysis-jobs\/?$/.test(pathname)) return { name: "analysis_jobs" };
  if (/^\/research\/methods\/?$/.test(pathname)) return { name: "research" };
  if (/^\/team\/?$/.test(pathname)) return { name: "team" };
  if (/^\/social\/?$/.test(pathname)) return { name: "social" };
  if (/^\/tasks\/flow\/?$/.test(pathname)) return { name: "task_flow" };
  if (/^\/projects\/?$/.test(pathname)) return { name: "projects" };
  if (/^\/sessions\/?$/.test(pathname)) return { name: "sessions" };

  const sessionMetricMatch = pathname.match(
    /^\/projects\/([a-f0-9]{64})\/sessions\/([a-f0-9]{64})\/metrics\/([a-z-]+)\/?$/,
  );
  if (
    sessionMetricMatch &&
    isPseudonym(sessionMetricMatch[1]) &&
    isPseudonym(sessionMetricMatch[2]) &&
    isMetricCategory(sessionMetricMatch[3])
  ) {
    return {
      name: "session_metrics",
      projectId: sessionMetricMatch[1],
      sessionId: sessionMetricMatch[2],
      category: sessionMetricMatch[3],
    };
  }

  const projectMetricMatch = pathname.match(
    /^\/projects\/([a-f0-9]{64})\/metrics\/([a-z-]+)\/?$/,
  );
  if (
    projectMetricMatch &&
    isPseudonym(projectMetricMatch[1]) &&
    isMetricCategory(projectMetricMatch[2])
  ) {
    return {
      name: "project_metrics",
      projectId: projectMetricMatch[1],
      category: projectMetricMatch[2],
    };
  }

  const projectViewMatch = pathname.match(
    /^\/projects\/([a-f0-9]{64})\/(overview|sessions|automation)\/?$/,
  );
  if (projectViewMatch && isPseudonym(projectViewMatch[1])) {
    if (projectViewMatch[2] === "overview") {
      return { name: "project_overview", projectId: projectViewMatch[1] };
    }
    if (projectViewMatch[2] === "sessions") {
      return { name: "project_sessions", projectId: projectViewMatch[1] };
    }
    return { name: "project_automation", projectId: projectViewMatch[1] };
  }

  const match = pathname.match(/^\/tasks\/([a-f0-9]{64})\/revisions\/(\d+)\/?$/);
  if (match && isPseudonym(match[1])) {
    const revision = Number(match[2]);
    if (Number.isSafeInteger(revision) && revision > 0) {
      return { name: "task", taskId: match[1], revision };
    }
  }
  return { name: "discovery" };
}

export function routePath(route: AppRoute): string {
  if (route.name === "discovery") return "/";
  if (route.name === "local_sources") return "/local-sources";
  if (route.name === "analysis_jobs") return "/analysis-jobs";
  if (route.name === "research") return "/research/methods";
  if (route.name === "team") return "/team";
  if (route.name === "social") return "/social";
  if (route.name === "task_flow") return "/tasks/flow";
  if (route.name === "projects") return "/projects";
  if (route.name === "sessions") return "/sessions";
  if (route.name === "project_overview") {
    assertPseudonym(route.projectId);
    return `/projects/${route.projectId}/overview`;
  }
  if (route.name === "project_sessions") {
    assertPseudonym(route.projectId);
    return `/projects/${route.projectId}/sessions`;
  }
  if (route.name === "project_automation") {
    assertPseudonym(route.projectId);
    return `/projects/${route.projectId}/automation`;
  }
  if (route.name === "project_metrics") {
    assertPseudonym(route.projectId);
    assertMetricCategory(route.category);
    return `/projects/${route.projectId}/metrics/${route.category}`;
  }
  if (route.name === "session_metrics") {
    assertPseudonym(route.projectId);
    assertPseudonym(route.sessionId);
    assertMetricCategory(route.category);
    return `/projects/${route.projectId}/sessions/${route.sessionId}/metrics/${route.category}`;
  }
  return `/tasks/${route.taskId}/revisions/${route.revision}`;
}

function assertPseudonym(value: string): void {
  if (!isPseudonym(value)) {
    throw new TypeError("Route identifiers must be lowercase 64-character pseudonyms.");
  }
}

function assertMetricCategory(value: string): asserts value is MetricCategory {
  if (!isMetricCategory(value)) {
    throw new TypeError("Metric category is not allowlisted.");
  }
}
