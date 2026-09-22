import type { AppRoute, PlatformAdapter, PlatformNavigationAttempt } from "./platform";
import { parseRoute, routePath } from "./platform";

const HISTORY_INDEX = "__prompt_enhancer_route_index_v1";
const HISTORY_CHAIN = "__prompt_enhancer_route_chain_v1";
const CHAIN = /^pe-[a-f0-9]{32}$/u;

function indexedState(state: unknown, chain: string, index: number): Record<string, unknown> | null {
  if (state !== null && (typeof state !== "object" || Array.isArray(state))) return null;
  const record = state as Record<string, unknown> | null;
  if (record !== null && (HISTORY_INDEX in record || HISTORY_CHAIN in record)) return null;
  return { ...record, [HISTORY_CHAIN]: chain, [HISTORY_INDEX]: index };
}

function readEntry(state: unknown): { chain: string; index: number } | null {
  if (typeof state !== "object" || state === null || Array.isArray(state)) return null;
  const record = state as Record<string, unknown>;
  const index = record[HISTORY_INDEX];
  const chain = record[HISTORY_CHAIN];
  return typeof chain === "string" && CHAIN.test(chain) && typeof index === "number" && Number.isSafeInteger(index)
    ? { chain, index }
    : null;
}

/** Browser-only navigation with a content-free, reversible history guard. */
export function createBrowserPlatform(browserWindow: Window = window): PlatformAdapter {
  const listeners = new Set<(route: AppRoute) => void>();
  const attemptListeners = new Set<(attempt: PlatformNavigationAttempt) => boolean>();
  let popstateAttached = false;
  let current = readEntry(browserWindow.history.state);
  let replay: { kind: "restore" | "resume"; expected: { chain: string; index: number } } | null = null;
  let generation = 0;
  let blocked: { generation: number; index: number | null; route: AppRoute; resumeQueued: boolean } | null = null;
  const comparablePath = (path: string) =>
    path !== "/" && path.endsWith("/") && !path.endsWith("//") ? path.slice(0, -1) : path;
  let committedPath = comparablePath(browserWindow.location.pathname);
  const newChain = () => {
    const bytes = new Uint8Array(16);
    browserWindow.crypto.getRandomValues(bytes);
    return `pe-${[...bytes].map((value) => value.toString(16).padStart(2, "0")).join("")}`;
  };
  const emit = () => {
    const route = parseRoute(browserWindow.location.pathname);
    listeners.forEach((listener) => listener(route));
    committedPath = comparablePath(browserWindow.location.pathname);
  };
  const stampCurrent = () => {
    if (current !== null) return;
    const chain = newChain();
    const state = indexedState(browserWindow.history.state, chain, 0);
    if (state === null) return;
    browserWindow.history.replaceState(state, "", browserWindow.location.href);
    current = { chain, index: 0 };
  };
  const hasSubscribers = () => listeners.size > 0 || attemptListeners.size > 0;
  const resumeBlocked = () => {
    const pending = blocked;
    if (pending === null || current === null || pending.index === null) return;
    blocked = null;
    replay = { kind: "resume", expected: { chain: current.chain, index: pending.index } };
    browserWindow.history.go(pending.index - current.index);
  };

  const onPopstate = (event: PopStateEvent) => {
    const target = readEntry(event.state);
    if (replay !== null && target?.chain === replay.expected.chain && target.index === replay.expected.index) {
      const completed = replay;
      replay = null;
      current = target;
      if (completed.kind === "resume") emit();
      else if (blocked?.resumeQueued) resumeBlocked();
      return;
    }
    // A different rapid pop supersedes the pending restoration/replay rather
    // than being mistaken for its completion.
    replay = null;
    blocked = null;
    const route = parseRoute(browserWindow.location.pathname);
    if (target !== null && current !== null && target.chain === current.chain && target.index === current.index && comparablePath(browserWindow.location.pathname) === committedPath) {
      blocked = null;
      current = target;
      emit();
      return;
    }
    const attemptGeneration = generation + 1;
    generation = attemptGeneration;
    const candidate: PlatformNavigationAttempt = {
      route,
      source: "history",
      canRestore: target !== null && current !== null && target.chain === current.chain && target.index !== current.index,
      resume: () => {
        if (blocked?.generation !== attemptGeneration) return;
        if (blocked.index === null || current === null) {
          blocked = null;
          emit();
          return;
        }
        if (replay?.kind === "restore") {
          blocked.resumeQueued = true;
          return;
        }
        resumeBlocked();
      },
    };
    const allowed = [...attemptListeners].every((listener) => listener(candidate));
    if (allowed) {
      blocked = null;
      if (target !== null && current !== null && target.chain === current.chain) current = target;
      else current = null;
      committedPath = comparablePath(browserWindow.location.pathname);
      emit();
      return;
    }
    const blockedIndex = target !== null && current !== null && target.chain === current.chain && target.index !== current.index
      ? target.index
      : null;
    blocked = { generation: attemptGeneration, index: blockedIndex, route, resumeQueued: false };
    if (blocked.index === null || current === null) {
      current = null;
      return;
    }
    replay = { kind: "restore", expected: current };
    browserWindow.history.go(current.index - blocked.index);
  };

  const attachPopstate = () => {
    if (popstateAttached || !hasSubscribers()) return;
    stampCurrent();
    browserWindow.addEventListener("popstate", onPopstate);
    popstateAttached = true;
  };
  const detachPopstate = () => {
    if (!popstateAttached || hasSubscribers()) return;
    browserWindow.removeEventListener("popstate", onPopstate);
    popstateAttached = false;
    blocked = null;
    replay = null;
    generation += 1;
  };

  return {
    currentRoute: () => parseRoute(browserWindow.location.pathname),
    navigate(route) {
      const nextPath = routePath(route);
      if (comparablePath(browserWindow.location.pathname) === comparablePath(nextPath)) return;
      generation += 1;
      blocked = null;
      replay = null;
      stampCurrent();
      const next = current === null ? { chain: newChain(), index: 0 } : { chain: current.chain, index: current.index + 1 };
      const state = { [HISTORY_CHAIN]: next.chain, [HISTORY_INDEX]: next.index };
      browserWindow.history.pushState(state, "", nextPath);
      current = next;
      committedPath = comparablePath(nextPath);
      emit();
    },
    subscribe(listener) {
      listeners.add(listener);
      attachPopstate();
      return () => {
        listeners.delete(listener);
        detachPopstate();
      };
    },
    subscribeNavigationAttempt(listener) {
      attemptListeners.add(listener);
      attachPopstate();
      return () => {
        attemptListeners.delete(listener);
        generation += 1;
        blocked = null;
        replay = null;
        detachPopstate();
      };
    },
  };
}
