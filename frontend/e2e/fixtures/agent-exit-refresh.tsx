import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "../../src/app/App";
import { TransportError } from "../../src/shared/api/httpTransport";
import type { AgentSessionView } from "../../src/shared/api/contracts";
import { createSyntheticTransport } from "../../src/shared/api/syntheticTransport";
import { createBrowserPlatform } from "../../src/shared/platform/browserPlatform";
import { createRuntimeComposition, type SyntheticRuntimeTransport } from "../../src/shared/platform/runtimeMode";
import { startUiRevisionGuard } from "../../src/shared/platform/uiRevisionGuard";
import { UiRevisionNotice } from "../../src/shared/ui/UiRevisionNotice";
import "../../src/styles.css";
import "../../src/app/theme.css";
import "../../src/app/palette.generated.css";
import "../../src/app/interfaceRefresh.css";

const active = new URL(window.location.href).searchParams.has("active");
const dedicated = new URL(window.location.href).searchParams.has("dedicated");
const closeMode = new URL(window.location.href).searchParams.get("close") ?? "success";
const fallbackRail = new URL(window.location.href).searchParams.has("fallback");
window.history.replaceState(null, "", dedicated ? "/agent/window" : "/agent");

let settleDeferredClose: ((outcome: "resolve" | "reject") => void) | null = null;
if (closeMode === "deferred") {
  for (const [outcome, label] of [
    ["resolve", "Resolve synthetic close"],
    ["reject", "Fail synthetic close"],
  ] as const) {
    const control = document.createElement("button");
    control.type = "button";
    control.textContent = label;
    control.setAttribute("data-synthetic-close-control", outcome);
    control.style.cssText = `position:fixed;right:0;top:${outcome === "resolve" ? "0" : "40px"};z-index:1000`;
    control.addEventListener("click", () => settleDeferredClose?.(outcome));
    document.body.append(control);
  }
}

const COUNTERS = ["create", "send", "stop", "delete", "modelstart", "reload"] as const;
const counters = Object.fromEntries(COUNTERS.map((name) => [name, 0])) as Record<(typeof COUNTERS)[number], number>;
const publish = () => {
  for (const name of COUNTERS) document.documentElement.setAttribute(`data-agent-refresh-${name}`, String(counters[name]));
  document.documentElement.setAttribute("data-agent-refresh-live-sessions", String(sessions.length));
};
const count = (name: (typeof COUNTERS)[number]) => { counters[name] += 1; publish(); };

const primarySession: AgentSessionView = {
  contract_version: "local-agent.v9", cleanup_unconfirmed: false, closing: false, stopping: false,
  session_id: "f".repeat(32), running: active, pending_approval_id: null, last_seq: 0, turns: 0, history_revision: 0,
  model_alias: null, created_at: "2040-01-01T00:00:00Z", recovered: false, authority_revalidated: true,
  history_write_failed: false, recovery_state: "current",
  settings: {
    workspace: "D:/synthetic/agent", project_id: null, model_alias: null,
    parameters: { temperature: 0.2, top_p: 0.9, max_tokens: 100, enable_thinking: false },
    instructions: null, allow_writes: false, allow_commands: false, allow_web: false,
    max_steps: 1, command_timeout_seconds: 1, title: "Synthetic idle Agent", retention_policy: "metadata_only",
  },
};
const secondarySession: AgentSessionView = {
  ...primarySession,
  session_id: "e".repeat(32),
  settings: {
    ...primarySession.settings,
    title: "Synthetic second Agent",
  },
};
let sessions: AgentSessionView[] = [primarySession, secondarySession];
let closeAttempts = 0;
const base = createSyntheticTransport();
// The close-draft fixture selects the real fallback live-session rail. Catalog
// rows have a separate durable attestation contract and cannot represent these
// in-memory live ids truthfully.
const transportTarget: SyntheticRuntimeTransport = {
  ...base,
  listAgentSessions: async () => sessions,
  getAgentEvents: async (sessionId) => ({ contract_version: "local-agent.v9", cleanup_unconfirmed: false, closing: false, stopping: false, session_id: sessionId, events: [], running: sessions.find((session) => session.session_id === sessionId)?.running ?? false, pending_approval_id: null, last_seq: 0, first_seq: 0 }),
  createAgentSession: async (settings, signal) => { count("create"); return base.createAgentSession(settings, signal); },
  sendAgentMessage: async (sessionId, text, attachmentIds, signal) => { count("send"); return base.sendAgentMessage(sessionId, text, attachmentIds, signal); },
  stopAgentSession: async (sessionId, signal) => { count("stop"); return base.stopAgentSession(sessionId, signal); },
  deleteAgentSession: async (sessionId) => {
    count("delete");
    closeAttempts += 1;
    if (closeMode === "failure" || (closeMode === "fail-once" && closeAttempts === 1)) {
      throw new TransportError("Synthetic close failure", 503);
    }
    if (closeMode === "deferred") {
      await new Promise<void>((resolve, reject) => {
        settleDeferredClose = (outcome) => {
          settleDeferredClose = null;
          if (outcome === "reject") {
            reject(new TransportError("Synthetic deferred close failure", 503));
            return;
          }
          sessions = sessions.filter((session) => session.session_id !== sessionId);
          publish();
          resolve();
        };
      });
      return;
    }
    sessions = sessions.filter((session) => session.session_id !== sessionId);
    publish();
    if (closeMode === "404") throw new TransportError("Synthetic authoritative absence", 404);
  },
  activateLocalModel: async (alias, request, signal) => { count("modelstart"); return base.activateLocalModel(alias, request, signal); },
};
const transport = fallbackRail
  ? new Proxy(transportTarget, {
    get(target, property, receiver) {
      if (property === "listAgentProjects") return undefined;
      return Reflect.get(target, property, receiver);
    },
  })
  : transportTarget;
const guard = startUiRevisionGuard({
  enabled: true,
  moduleUrl: "http://127.0.0.1:4173/assets/fixture-AbCdEf12.js",
  fetchImpl: async () => ({ ok: true, json: async () => ({ revision: "assets/fixture-ZyXwVu98.js" }) }),
  reload: () => count("reload"),
});

publish();
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App
      interfaceRefreshNotice={<UiRevisionNotice guard={guard} />}
      onReloadBlockedChange={guard.setReloadBlocked}
      platform={createBrowserPlatform()}
      runtime={createRuntimeComposition("synthetic_demo", transport)}
    />
  </StrictMode>,
);
