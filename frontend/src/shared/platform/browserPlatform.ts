import type { AppRoute, PlatformAdapter } from "./platform";
import { parseRoute, routePath } from "./platform";

/** Browser-only navigation. A future desktop host implements PlatformAdapter. */
export function createBrowserPlatform(browserWindow: Window = window): PlatformAdapter {
  const listeners = new Set<(route: AppRoute) => void>();
  const emit = () => {
    const route = parseRoute(browserWindow.location.pathname);
    listeners.forEach((listener) => listener(route));
  };
  browserWindow.addEventListener("popstate", emit);

  return {
    currentRoute: () => parseRoute(browserWindow.location.pathname),
    navigate(route) {
      browserWindow.history.pushState(null, "", routePath(route));
      emit();
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}
