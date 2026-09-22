const UI_REVISION_PATH = "/app-revision.json";
const UI_REVISION_INTERVAL_MS = 5_000;
const HASHED_JAVASCRIPT_REVISION =
  /^assets\/[A-Za-z0-9][A-Za-z0-9._-]*-[A-Za-z0-9_-]{8,}\.js$/;

type RevisionResponse = {
  readonly ok: boolean;
  json(): Promise<unknown>;
};

type RevisionFetch = (input: string, init: RequestInit) => Promise<RevisionResponse>;

type RevisionWindow = Pick<
  Window,
  "addEventListener" | "removeEventListener" | "setInterval" | "clearInterval" | "fetch"
>;

type RevisionDocument = Pick<Document, "addEventListener" | "removeEventListener" | "visibilityState">;

export interface UiRevisionGuardOptions {
  /** Keep synthetic and development previews completely inert. */
  readonly enabled: boolean;
  /** Pass the caller's `import.meta.url`; no build-time global is inspected here. */
  readonly moduleUrl: string;
  readonly fetchImpl?: RevisionFetch;
  readonly reload?: () => void;
  readonly browserWindow?: RevisionWindow;
  readonly browserDocument?: RevisionDocument;
}

export interface UiRevisionSnapshot {
  readonly status: "idle" | "available" | "reload_requested" | "reload_failed";
  readonly reloadBlocked: boolean;
}

export interface DisposableUiRevisionGuard {
  getSnapshot(): UiRevisionSnapshot;
  subscribe(listener: () => void): () => void;
  setReloadBlocked(blocked: boolean): void;
  requestReload(): boolean;
  dispose(): void;
}

/**
 * Return the exact revision shape emitted by the production asset build.
 *
 * The parser intentionally rejects query strings, fragments, traversal, source
 * module names, and unhashed files. An unknown build layout disables the guard
 * instead of guessing and creating a reload loop.
 */
export function deriveLoadedUiRevision(moduleUrl: string): string | null {
  let parsedUrl: URL;
  try {
    parsedUrl = new URL(moduleUrl);
  } catch {
    return null;
  }

  if (parsedUrl.search !== "" || parsedUrl.hash !== "") return null;

  const match = parsedUrl.pathname.match(/(?:^|\/)(assets\/[^/]+\.js)$/);
  const revision = match?.[1] ?? null;
  return revision !== null && HASHED_JAVASCRIPT_REVISION.test(revision) ? revision : null;
}

function revisionFromPayload(payload: unknown): string | null {
  if (payload === null || typeof payload !== "object" || Array.isArray(payload)) return null;
  const keys = Object.keys(payload);
  if (keys.length !== 1 || keys[0] !== "revision") return null;
  const revision = (payload as Record<string, unknown>).revision;
  return typeof revision === "string" && HASHED_JAVASCRIPT_REVISION.test(revision)
    ? revision
    : null;
}

function inertGuard(): DisposableUiRevisionGuard {
  const snapshot = Object.freeze<UiRevisionSnapshot>({ status: "idle", reloadBlocked: false });
  return Object.freeze({
    getSnapshot: () => snapshot,
    subscribe: () => () => {},
    setReloadBlocked: () => {},
    requestReload: () => false,
    dispose: () => {},
  });
}

const INERT_GUARD = inertGuard();

/**
 * Observe the same-origin build revision and offer, but never automatically
 * perform, a one-shot interface refresh when the loaded asset is stale.
 */
export function startUiRevisionGuard(options: UiRevisionGuardOptions): DisposableUiRevisionGuard {
  if (!options.enabled) return INERT_GUARD;

  const loadedRevision = deriveLoadedUiRevision(options.moduleUrl);
  if (loadedRevision === null) return INERT_GUARD;

  const browserWindow = options.browserWindow ?? window;
  const browserDocument = options.browserDocument ?? document;
  const fetchImpl = options.fetchImpl ?? browserWindow.fetch.bind(browserWindow);
  const reload = options.reload ?? (() => window.location.reload());
  const listeners = new Set<() => void>();
  let disposed = false;
  let checkingStopped = false;
  let checkInFlight = false;
  let intervalId: ReturnType<RevisionWindow["setInterval"]> | null = null;
  let snapshot = Object.freeze<UiRevisionSnapshot>({ status: "idle", reloadBlocked: false });

  const notify = () => {
    for (const listener of listeners) listener();
  };
  const updateSnapshot = (next: UiRevisionSnapshot) => {
    if (snapshot.status === next.status && snapshot.reloadBlocked === next.reloadBlocked) return;
    snapshot = Object.freeze(next);
    notify();
  };
  const stopChecking = () => {
    if (checkingStopped) return;
    checkingStopped = true;
    if (intervalId !== null) browserWindow.clearInterval(intervalId);
    browserWindow.removeEventListener("focus", onFocus);
    browserDocument.removeEventListener("visibilitychange", onVisibilityChange);
  };
  const checkRevision = async () => {
    if (disposed || checkingStopped || checkInFlight) return;
    checkInFlight = true;
    try {
      const response = await fetchImpl(UI_REVISION_PATH, { cache: "no-store", credentials: "same-origin" });
      if (disposed || !response.ok) return;
      const currentRevision = revisionFromPayload(await response.json());
      if (disposed || currentRevision === null || currentRevision === loadedRevision) return;
      stopChecking();
      if (!disposed) updateSnapshot({ status: "available", reloadBlocked: snapshot.reloadBlocked });
    } catch {
      // Offline, malformed, and transient local-server responses remain unknown.
    } finally {
      checkInFlight = false;
    }
  };
  const onFocus = () => { void checkRevision(); };
  const onVisibilityChange = () => {
    if (browserDocument.visibilityState === "visible") void checkRevision();
  };

  intervalId = browserWindow.setInterval(() => {
    if (browserDocument.visibilityState === "visible") void checkRevision();
  }, UI_REVISION_INTERVAL_MS);
  browserWindow.addEventListener("focus", onFocus);
  browserDocument.addEventListener("visibilitychange", onVisibilityChange);
  void checkRevision();

  return {
    getSnapshot: () => snapshot,
    subscribe(listener) {
      if (disposed) return () => {};
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    setReloadBlocked(blocked) {
      if (disposed || snapshot.reloadBlocked === blocked) return;
      updateSnapshot({ status: snapshot.status, reloadBlocked: blocked });
    },
    requestReload() {
      if (disposed || snapshot.status !== "available" || snapshot.reloadBlocked) return false;
      // Recheck at the one explicit action boundary before invoking reload.
      if (snapshot.reloadBlocked) return false;
      updateSnapshot({ status: "reload_requested", reloadBlocked: false });
      // Subscribers run synchronously. A newly reported exit risk or disposal
      // must win over this request before the browser action is invoked.
      if (disposed || snapshot.reloadBlocked) {
        if (!disposed) updateSnapshot({ status: "available", reloadBlocked: snapshot.reloadBlocked });
        return false;
      }
      try {
        reload();
      } catch {
        if (!disposed) updateSnapshot({ status: "reload_failed", reloadBlocked: false });
      }
      return true;
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      stopChecking();
      listeners.clear();
    },
  };
}
