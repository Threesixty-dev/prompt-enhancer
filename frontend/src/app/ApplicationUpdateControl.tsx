import { useEffect, useRef, useState } from "react";
import type { ApplicationUpdateStatus, PromptEnhancerTransport } from "../shared/api/contracts";
import { Icon } from "../shared/ui/Icon";

type LoadState = "loading" | "ready" | "checking" | "unavailable";

function sizeLabel(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "";
  const mebibytes = bytes / (1024 ** 2);
  return `${mebibytes >= 10 ? Math.round(mebibytes) : mebibytes.toFixed(1)} MiB`;
}

function copyFor(status: ApplicationUpdateStatus | null, loadState: LoadState) {
  if (loadState === "loading") return { headline: "Software updates", detail: "Reading local update status" };
  if (loadState === "checking") return { headline: "Checking for updates", detail: "Signed release manifest only" };
  if (status === null) return { headline: "Update status unavailable", detail: "Retry the local status check" };
  switch (status.state) {
    case "unconfigured":
      return { headline: "Updates not connected", detail: `Version ${status.installed_version} · ${status.channel}` };
    case "ready_to_check":
      return { headline: "Check for updates", detail: `Version ${status.installed_version} · ${status.channel}` };
    case "checking":
      return { headline: "Checking for updates", detail: "Signed release manifest only" };
    case "current":
      return { headline: "Software is current", detail: `Version ${status.installed_version} · check again` };
    case "available":
      return {
        headline: `Version ${status.available_version} available`,
        detail: status.can_stage
          ? `${sizeLabel(status.artifact_size_bytes)} · signed release`
          : `${sizeLabel(status.artifact_size_bytes)} · download not connected`,
      };
    case "staging":
      return {
        headline: `Preparing version ${status.available_version}`,
        detail: `${sizeLabel(status.downloaded_bytes)} of ${sizeLabel(status.artifact_size_bytes)}`,
      };
    case "staged":
      return { headline: `Version ${status.available_version} ready`, detail: "Installation review required" };
    case "failed":
      return { headline: "Update check needs attention", detail: "No application changes were made" };
  }
}

export function ApplicationUpdateControl({
  transport,
  variant,
}: {
  transport: Pick<PromptEnhancerTransport, "getApplicationUpdateStatus" | "checkApplicationUpdate">;
  variant: "sidebar" | "drawer";
}) {
  const [status, setStatus] = useState<ApplicationUpdateStatus | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const requestRevision = useRef(0);
  const activeCheckController = useRef<AbortController | null>(null);

  useEffect(() => {
    const revision = ++requestRevision.current;
    const controller = new AbortController();
    const load = transport.getApplicationUpdateStatus;
    if (load === undefined) {
      setLoadState("unavailable");
      return () => {
        controller.abort();
        activeCheckController.current?.abort();
        requestRevision.current += 1;
      };
    }
    setLoadState("loading");
    void load(controller.signal).then(
      (next) => {
        if (!controller.signal.aborted && requestRevision.current === revision) {
          setStatus(next);
          setLoadState("ready");
        }
      },
      () => {
        if (!controller.signal.aborted && requestRevision.current === revision) {
          setStatus(null);
          setLoadState("unavailable");
        }
      },
    );
    return () => {
      controller.abort();
      activeCheckController.current?.abort();
      requestRevision.current += 1;
    };
  }, [transport]);

  function check(): void {
    const run = transport.checkApplicationUpdate;
    if (run === undefined || status?.can_check !== true || loadState === "checking") return;
    activeCheckController.current?.abort();
    const revision = ++requestRevision.current;
    const controller = new AbortController();
    activeCheckController.current = controller;
    setLoadState("checking");
    void run(controller.signal).then(
      (next) => {
        if (requestRevision.current === revision) {
          setStatus(next);
          setLoadState("ready");
          activeCheckController.current = null;
        }
      },
      () => {
        if (requestRevision.current === revision) {
          setLoadState("unavailable");
          activeCheckController.current = null;
        }
      },
    );
  }

  const copy = copyFor(status, loadState);
  const canCheck = loadState === "ready"
    && status?.can_check === true
    && status.state !== "available"
    && transport.checkApplicationUpdate !== undefined;
  const state = loadState === "ready" && status !== null ? status.state : loadState;

  return (
    <section
      aria-label="Software updates"
      className={`application-update application-update--${variant}`}
      data-update-state={state}
    >
      <button
        aria-busy={loadState === "loading" || loadState === "checking" || undefined}
        aria-describedby={`application-update-detail-${variant}`}
        disabled={!canCheck}
        onClick={check}
        type="button"
      >
        <span className="application-update__icon"><Icon name="refresh" /></span>
        <span className="application-update__copy">
          <strong>{copy.headline}</strong>
          <small id={`application-update-detail-${variant}`}>{copy.detail}</small>
        </span>
        {(status?.state === "available" || status?.state === "staged") && (
          <span className="application-update__badge">New</span>
        )}
      </button>
      <span aria-live="polite" className="sr-only">
        {copy.headline}. {copy.detail}.
      </span>
    </section>
  );
}
