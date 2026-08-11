import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { QualityMetricProfile, QualitySnapshotKind } from "./qualityProfile";
import {
  browserShareCardRuntime,
  createSafeShareSnapshot,
  type ShareCardAsset,
  type ShareCardRuntime,
} from "./qualityShareCard";

export function ProfileShareDialog({
  profile,
  snapshotKind,
  onClose,
  runtime = browserShareCardRuntime,
}: {
  profile: QualityMetricProfile;
  snapshotKind: QualitySnapshotKind;
  onClose: () => void;
  runtime?: ShareCardRuntime;
}) {
  const [asset, setAsset] = useState<ShareCardAsset | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const closeRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const appShell = document.querySelector<HTMLElement>(".app-shell");
    const wasInert = appShell?.inert ?? false;
    if (appShell) appShell.inert = true;
    closeRef.current?.focus();
    function keydown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
      if (event.key !== "Tab" || !panelRef.current) return;
      const focusable = Array.from(
        panelRef.current.querySelectorAll<HTMLElement>(
          "button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])",
        ),
      );
      const first = focusable[0];
      const last = focusable.at(-1);
      if (!first || !last) return;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    window.addEventListener("keydown", keydown);
    return () => {
      window.removeEventListener("keydown", keydown);
      if (appShell) appShell.inert = wasInert;
      previous?.focus();
    };
  }, [onClose]);

  useEffect(() => {
    let current: ShareCardAsset | null = null;
    let cancelled = false;
    setError("");
    let snapshot: ReturnType<typeof createSafeShareSnapshot>;
    try {
      snapshot = createSafeShareSnapshot(profile, snapshotKind);
    } catch {
      setError("This profile cannot be shared because its metric provenance is not coherent.");
      return () => {
        cancelled = true;
      };
    }
    void runtime
      .render(snapshot)
      .then((nextAsset) => {
        if (cancelled) {
          runtime.revoke(nextAsset);
          return;
        }
        current = nextAsset;
        setAsset(nextAsset);
      })
      .catch(() => {
        if (!cancelled) setError("The minimized local PNG preview could not be created.");
      });
    return () => {
      cancelled = true;
      if (current) runtime.revoke(current);
    };
  }, [profile, runtime, snapshotKind]);

  async function perform(action: "copy" | "share") {
    if (!asset) return;
    setError("");
    setNotice("");
    try {
      if (action === "copy") await runtime.copy(asset);
      else await runtime.share(asset);
      setNotice(action === "copy" ? "PNG copied to the clipboard." : "System share opened.");
    } catch {
      setError(action === "copy" ? "The PNG could not be copied." : "The system share was cancelled or unavailable.");
    }
  }

  return createPortal(
    <div aria-labelledby="share-profile-title" aria-modal="true" className="share-dialog" role="dialog">
      <div className="share-dialog__scrim" onPointerDown={onClose} />
      <section className="share-dialog__panel" ref={panelRef}>
        <header>
          <div>
            <p className="eyebrow">Privacy preview</p>
            <h2 id="share-profile-title">Share this metric profile</h2>
          </div>
          <button className="share-dialog__close" onClick={onClose} ref={closeRef} type="button">Close</button>
        </header>
        <div className="share-dialog__warning" role="note">
          <strong>Derived metrics can still be sensitive.</strong>
          <span>Review before sharing. The image excludes project and session names, IDs, evidence text, prompts, paths, and model-cache details.</span>
        </div>
        <div className="share-dialog__preview">
          {error ? (
            <p role="alert">{error}</p>
          ) : asset ? (
            <img alt={`Minimized local ${profile.title} share card preview`} src={asset.previewUrl} />
          ) : (
            <p role="status">Creating local PNG preview…</p>
          )}
        </div>
        <p aria-live="polite" className="share-dialog__notice">{notice}</p>
        <footer>
          <button className="button button--secondary" onClick={onClose} type="button">Cancel</button>
          <button
            className="button button--secondary"
            disabled={!asset || !runtime.canCopy()}
            onClick={() => void perform("copy")}
            title={runtime.canCopy() ? undefined : "Clipboard image copy is not supported by this browser"}
            type="button"
          >
            Copy image
          </button>
          <button
            className="button button--secondary"
            disabled={!asset || (asset ? !runtime.canShare(asset) : true)}
            onClick={() => void perform("share")}
            title={asset && runtime.canShare(asset) ? undefined : "System image sharing is not supported by this browser"}
            type="button"
          >
            Share…
          </button>
          <button
            className="button button--primary"
            disabled={!asset}
            onClick={() => asset && runtime.download(asset)}
            type="button"
          >
            Download PNG
          </button>
        </footer>
      </section>
    </div>,
    document.body,
  );
}
