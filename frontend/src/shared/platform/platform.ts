export type AppRoute =
  | { name: "discovery" }
  | { name: "local_sources" }
  | { name: "task"; taskId: string; revision: number };

export interface PlatformAdapter {
  currentRoute(): AppRoute;
  navigate(route: AppRoute): void;
  subscribe(listener: (route: AppRoute) => void): () => void;
}

const PSEUDONYM = /^[a-f0-9]{64}$/;

export function parseRoute(pathname: string): AppRoute {
  if (/^\/local-sources\/?$/.test(pathname)) return { name: "local_sources" };
  const match = pathname.match(/^\/tasks\/([a-f0-9]{64})\/revisions\/(\d+)\/?$/);
  if (match && PSEUDONYM.test(match[1])) {
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
  return `/tasks/${route.taskId}/revisions/${route.revision}`;
}
