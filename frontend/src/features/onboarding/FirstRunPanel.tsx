import { useEffect, useState } from "react";
import type { OnboardingStatus, PromptEnhancerTransport, ProviderDetection } from "../../shared/api/contracts";
import { TransportError } from "../../shared/api/httpTransport";
import type { AppRoute } from "../../shared/platform/platform";
import { Icon } from "../../shared/ui/Icon";
import { ProviderBadge } from "../../shared/ui/ProviderBadge";
import "./FirstRunPanel.css";

const DISMISS_KEY = "prompt-enhancer.first-run.dismissed";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function safeOnboardingStatus(value: unknown): value is OnboardingStatus {
  if (!isRecord(value) || value.contract_version !== "onboarding.v1") return false;
  if (!Array.isArray(value.providers) || value.providers.length !== 2) return false;
  return value.providers.every((p) =>
    isRecord(p)
    && (p.provider === "codex" || p.provider === "claude_code")
    && typeof p.installed === "boolean"
    && typeof p.consent_active === "boolean"
    && typeof p.indexed_sessions === "number",
  ) && typeof value.needs_onboarding === "boolean" && typeof value.any_installed === "boolean";
}

function detectionLine(p: ProviderDetection): string {
  if (!p.installed) return "Not found on this machine";
  if (p.provider === "claude_code") {
    const n = p.transcript_files ?? 0;
    return `${n} session${n === 1 ? "" : "s"} on disk${p.consent_active ? ` · ${p.indexed_sessions} loaded` : ""}`;
  }
  return `CLI found${p.consent_active ? ` · ${p.indexed_sessions} sessions loaded` : ""}`;
}

/**
 * First run: detect Codex and Claude Code, ask once, load everything.
 * If neither is found, say so and take a folder from the person.
 */
export function FirstRunPanel({
  transport,
  navigate,
}: {
  transport: Pick<PromptEnhancerTransport, "getOnboardingStatus" | "acceptOnboarding">;
  navigate: (route: AppRoute) => void;
}) {
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [hidden, setHidden] = useState<boolean>(() => {
    try { return sessionStorage.getItem(DISMISS_KEY) === "1"; } catch { return false; }
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [claudeHome, setClaudeHome] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    transport.getOnboardingStatus(controller.signal)
      .then((value) => { if (!controller.signal.aborted && safeOnboardingStatus(value)) setStatus(value); })
      .catch(() => { /* no panel when the runtime lacks onboarding */ });
    return () => controller.abort();
  }, [transport]);

  if (hidden || status === null || !status.needs_onboarding) return null;

  const installed = status.providers.filter((p) => p.installed && !p.consent_active).map((p) => p.provider);

  async function loadEverything() {
    setBusy(true);
    setError("");
    try {
      const providers = installed.length > 0 ? installed : (claudeHome.trim() ? ["claude_code" as const] : []);
      if (providers.length === 0) {
        setError("Nothing to load yet - install Codex or Claude Code, or point at a Claude Code folder below.");
        return;
      }
      const result = await transport.acceptOnboarding({
        providers,
        claude_home: claudeHome.trim() ? claudeHome.trim() : null,
      });
      setStatus(result.status);
      navigate({ name: "sessions" });
    } catch (caught) {
      if (caught instanceof TransportError && caught.status === 422) {
        setError(caught.message.includes("claude_home_invalid")
          ? "That folder does not look like a Claude Code home (it needs a projects/ directory)."
          : "That source is not installed here.");
      } else {
        setError("Loading could not start. Nothing was changed.");
      }
    } finally {
      setBusy(false);
    }
  }

  function dismiss() {
    try { sessionStorage.setItem(DISMISS_KEY, "1"); } catch { /* ignore */ }
    setHidden(true);
  }

  return (
    <section aria-labelledby="first-run-title" className="first-run" role="region">
      <div className="first-run__head">
        <span className="first-run__mark"><Icon name="layers" /></span>
        <div>
          <p className="eyebrow">First run</p>
          <h2 id="first-run-title">
            {status.any_installed ? "Load your projects and sessions" : "We could not find Codex or Claude Code"}
          </h2>
          <p className="first-run__lede">
            {status.any_installed
              ? "Everything stays on this machine. After one yes, Prompt Enhancer loads every project and session it can find and keeps them current automatically."
              : "Did you install them? Codex is detected from the CLI on your PATH; Claude Code from its transcript folder. You can point at a Claude Code folder below."}
          </p>
        </div>
      </div>

      <ul className="first-run__providers">
        {status.providers.map((p) => (
          <li key={p.provider} className={p.installed ? "is-found" : "is-missing"}>
            <ProviderBadge provider={p.provider} />
            <span>{detectionLine(p)}</span>
            <Icon name={p.installed ? "check" : "x"} />
          </li>
        ))}
      </ul>

      {(!status.any_installed || !status.providers[1].installed) && (
        <label className="first-run__path">
          <span>Claude Code folder (contains <code>projects/</code>)</span>
          <input
            aria-label="Claude Code folder"
            disabled={busy}
            onChange={(event) => setClaudeHome(event.currentTarget.value)}
            placeholder="for example C:\\Users\\you\\.claude"
            type="text"
            value={claudeHome}
          />
        </label>
      )}

      {error !== "" && <p className="first-run__error" role="alert">{error}</p>}

      <div className="first-run__actions">
        <button className="button button--primary" disabled={busy} onClick={() => void loadEverything()} type="button">
          {busy ? "Loading…" : "Yes, load everything"}
        </button>
        <button className="button button--ghost" disabled={busy} onClick={dismiss} type="button">Not now</button>
      </div>
      <p className="first-run__note">
        This grants local-history access for the sources above. Nothing is sent anywhere; you can revoke it on the Data source page at any time.
      </p>
    </section>
  );
}
