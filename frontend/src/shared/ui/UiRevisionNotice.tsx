import { useSyncExternalStore } from "react";
import type { DisposableUiRevisionGuard } from "../platform/uiRevisionGuard";
import "./UiRevisionNotice.css";

/** A compact, non-modal manual refresh affordance for a newer local UI build. */
export function UiRevisionNotice({ guard }: { guard: DisposableUiRevisionGuard }) {
  const snapshot = useSyncExternalStore(guard.subscribe, guard.getSnapshot, guard.getSnapshot);

  if (snapshot.status === "idle") return null;

  if (snapshot.status === "reload_requested") {
    return <p className="ui-revision-notice" role="status">Interface refresh requested. If your browser cancels it, this page stays open.</p>;
  }

  if (snapshot.status === "reload_failed") {
    return <p className="ui-revision-notice ui-revision-notice--failed" role="status">Interface refresh could not start.</p>;
  }

  const blockedMessage = "Refresh is unavailable while temporary work may be lost.";
  return (
    <section aria-label="Interface refresh available" className="ui-revision-notice" role="status">
      <span>Interface refresh available</span>
      <button
        aria-describedby={snapshot.reloadBlocked ? "ui-revision-notice-blocked" : undefined}
        disabled={snapshot.reloadBlocked}
        onClick={() => { guard.requestReload(); }}
        title={snapshot.reloadBlocked ? blockedMessage : undefined}
        type="button"
      >
        Refresh interface
      </button>
      <small id={snapshot.reloadBlocked ? "ui-revision-notice-blocked" : undefined}>
        {snapshot.reloadBlocked
          ? blockedMessage
          : "Refreshing only reloads this interface; it does not install anything."}
      </small>
    </section>
  );
}
