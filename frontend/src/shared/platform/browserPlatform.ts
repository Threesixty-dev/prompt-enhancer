import type { AppRoute, PlatformAdapter } from "./platform";
import { parseRoute, routePath } from "./platform";

/** Browser-only navigation. A future desktop host implements PlatformAdapter. */
export function createBrowserPlatform(browserWindow: Window = window): PlatformAdapter {
  const listeners = new Set<(route: AppRoute) => void>();
  const comparablePath = (path: string) =>
    path !== "/" && path.endsWith("/") && !path.endsWith("//") ? path.slice(0, -1) : path;
  const emit = () => {
    const route = parseRoute(browserWindow.location.pathname);
    listeners.forEach((listener) => listener(route));
  };
  browserWindow.addEventListener("popstate", emit);

  return {
    currentRoute: () => parseRoute(browserWindow.location.pathname),
    navigate(route) {
      const nextPath = routePath(route);
      if (comparablePath(browserWindow.location.pathname) === comparablePath(nextPath)) return;
      browserWindow.history.pushState(null, "", nextPath);
      emit();
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}
