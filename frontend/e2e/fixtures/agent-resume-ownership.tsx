import { StrictMode, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { App } from "../../src/app/App";
import type {
  AgentArtifactList,
  AgentCatalogSession,
  AgentEvents,
  AgentProject,
  AgentSessionView,
  LocalModelsOverview,
  LocalRuntimeCoordinatorStatus,
} from "../../src/shared/api/contracts";
import { TransportError } from "../../src/shared/api/httpTransport";
import { createSyntheticTransport } from "../../src/shared/api/syntheticTransport";
import { createBrowserPlatform } from "../../src/shared/platform/browserPlatform";
import { createRuntimeComposition, type SyntheticRuntimeTransport } from "../../src/shared/platform/runtimeMode";
import "../../src/styles.css";
import "../../src/app/theme.css";
import "../../src/app/palette.generated.css";

const FIXTURE_MODE = (() => {
  const value = new URLSearchParams(window.location.search).get("mode");
  return value === "normal" || value === "deferred-failure" ? value : "deferred-success";
})();
window.history.replaceState(null, "", "/agent");

const PROJECT_ID = "c".repeat(32);
const SESSION_A = "a".repeat(32);
const SESSION_B = "b".repeat(32);
const SYNTHETIC_TIME = "2040-01-01T10:00:00Z";

type ResumeMode = "normal" | "deferred-success" | "deferred-failure";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((accept, decline) => {
    resolve = accept;
    reject = decline;
  });
  return { promise, resolve, reject };
}

const project: AgentProject = {
  contract_version: "agent-catalog.v2",
  project_id: PROJECT_ID,
  name: "Synthetic resume project",
  created_at: SYNTHETIC_TIME,
  updated_at: SYNTHETIC_TIME,
  revision: 1,
  pinned: false,
  archived_at: null,
  session_count: 2,
  is_default: false,
};

function catalogSession(sessionId: string, title: string): AgentCatalogSession {
  return {
    contract_version: "agent-catalog.v2",
    session_id: sessionId,
    project_id: PROJECT_ID,
    title,
    workspace: "D:/synthetic/resume-workspace",
    model_alias: null,
    created_at: SYNTHETIC_TIME,
    updated_at: SYNTHETIC_TIME,
    last_opened_at: SYNTHETIC_TIME,
    revision: 1,
    pinned: false,
    archived_at: null,
    history_state: "durable_local",
    retention_policy: "local_history",
    history_revision: 1,
    last_event_seq: 0,
    turn_count: 0,
    conversation_available: true,
    lineage: null,
  };
}

const sessionA = catalogSession(SESSION_A, "Saved resume A");
const sessionB = catalogSession(SESSION_B, "Saved resume B");

function sessionView(sessionId: string, title: string): AgentSessionView {
  return {
    contract_version: "local-agent.v9",
    cleanup_unconfirmed: false,
    closing: false,
    stopping: false,
    session_id: sessionId,
    running: false,
    pending_approval_id: null,
    last_seq: 0,
    turns: 0,
    history_revision: 1,
    model_alias: null,
    created_at: SYNTHETIC_TIME,
    recovered: true,
    authority_revalidated: false,
    history_write_failed: false,
    recovery_state: "recovered",
    settings: {
      workspace: "D:/synthetic/resume-workspace",
      project_id: PROJECT_ID,
      model_alias: null,
      parameters: {
        temperature: 0.2,
        top_p: 0.9,
        max_tokens: 120,
        enable_thinking: false,
      },
      instructions: null,
      allow_writes: false,
      allow_commands: false,
      allow_web: false,
      max_steps: 1,
      command_timeout_seconds: 1,
      title,
      retention_policy: "local_history",
    },
  };
}

const viewA = sessionView(SESSION_A, sessionA.title);
const viewB = sessionView(SESSION_B, sessionB.title);

const idleRuntime: LocalRuntimeCoordinatorStatus = {
  contract_version: "local-runtime-coordinator.v2",
  revision: 1,
  state: "idle",
  requested: null,
  served: null,
  active_requests: 0,
  cleanup: {
    state: "not_required",
    process_exit_confirmed: true,
    gpu_memory_free_before_mb: null,
    gpu_memory_free_after_mb: null,
    gpu_memory_released_mb: null,
  },
  capabilities: {
    probe_version: "local-runtime-multimodal-probe.v2",
    state: "not_probed",
    text: false,
    tools: false,
    structured_output: false,
    vision: false,
    audio: false,
    recording: false,
    error_code: "no_model_selected",
  },
  context: {
    state: "unknown",
    used_tokens: null,
    limit_tokens: null,
    requested_output_tokens: null,
    available_output_tokens: null,
    source: "runtime_limit_only",
    scope: "runtime_limit",
    policy: "runtime_enforced",
    compacted_messages: 0,
    reason_code: "no_request_measured",
  },
  last_error_code: null,
};

const noModels: LocalModelsOverview = {
  contract_version: "local-models.v1",
  runtime_available: true,
  storage_root: "D:/synthetic/models",
  storage_free_bytes: null,
  download_reserve_bytes: 0,
  download_ledger_error_code: null,
  models: [],
  downloads: [],
  hardware: {
    gpu_name: null,
    gpu_memory_mb: null,
    gpu_memory_free_mb: null,
    ram_mb: null,
    llama_server_path: null,
    llama_server_version: null,
  },
};

type ControlledFixture = {
  transport: SyntheticRuntimeTransport;
  releaseA: () => void;
  failA: () => void;
  counters: { resume: number; activate: number; send: number };
};

function createFixtureTransport(mode: ResumeMode): ControlledFixture {
  const base = createSyntheticTransport();
  const gate = deferred<AgentSessionView>();
  const counters = { resume: 0, activate: 0, send: 0 };
  const liveSessions = new Map<string, AgentSessionView>();
  let released = false;
  const publishResolution = (value: "success" | "failure") => {
    document.documentElement.dataset.resumeOwnershipResolution = value;
  };
  const releaseA = () => {
    if (released) return;
    released = true;
    publishResolution("success");
    liveSessions.set(SESSION_A, viewA);
    gate.resolve(viewA);
  };
  const failA = () => {
    if (released) return;
    released = true;
    publishResolution("failure");
    gate.reject(new TransportError("Synthetic candidate A resume failed", 503));
  };
  const publishCounters = () => {
    document.documentElement.dataset.resumeOwnershipResume = String(counters.resume);
    document.documentElement.dataset.resumeOwnershipActivate = String(counters.activate);
    document.documentElement.dataset.resumeOwnershipSend = String(counters.send);
  };
  const transport: SyntheticRuntimeTransport = {
    ...base,
    listAgentProjects: async () => ({ contract_version: "agent-catalog.v2", projects: [project] }),
    listAgentCatalogSessions: async () => ({
      contract_version: "agent-catalog.v2",
      sessions: [sessionA, sessionB],
    }),
    listAgentSessions: async () => [...liveSessions.values()],
    getAgentCatalogSession: async (sessionId) => {
      if (sessionId === SESSION_A) return sessionA;
      if (sessionId === SESSION_B) return sessionB;
      throw new TransportError("Synthetic catalog session not found", 404);
    },
    getAgentPersistedEvents: async (_projectId, sessionId): Promise<AgentEvents> => ({
      contract_version: "local-agent.v9",
      cleanup_unconfirmed: false,
      closing: false,
      stopping: false,
      session_id: sessionId,
      events: [],
      running: false,
      pending_approval_id: null,
      first_seq: 0,
      last_seq: 0,
    }),
    listAgentArtifacts: async (projectId, sessionId, view = "active"): Promise<AgentArtifactList> => ({
      contract_version: "agent-artifact.v3",
      project_id: projectId,
      session_id: sessionId,
      view,
      counts: { active: 0, archived: 0, removed: 0, total: 0 },
      artifacts: [],
    }),
    getAgentEvents: async (sessionId): Promise<AgentEvents> => ({
      contract_version: "local-agent.v9",
      cleanup_unconfirmed: false,
      closing: false,
      stopping: false,
      session_id: sessionId,
      events: [],
      running: false,
      pending_approval_id: null,
      first_seq: 0,
      last_seq: 0,
    }),
    getLocalModels: async () => noModels,
    getLocalRuntime: async () => idleRuntime,
    resumeAgentSession: async (_projectId, sessionId) => {
      counters.resume += 1;
      publishCounters();
      if (sessionId === SESSION_A && mode !== "normal") return gate.promise;
      const resumed = sessionId === SESSION_B ? viewB : viewA;
      liveSessions.set(sessionId, resumed);
      return resumed;
    },
    activateLocalModel: async (...args) => {
      counters.activate += 1;
      publishCounters();
      return base.activateLocalModel(...args);
    },
    sendAgentMessage: async (...args) => {
      counters.send += 1;
      publishCounters();
      return base.sendAgentMessage(...args);
    },
  };
  publishCounters();
  return { transport, releaseA, failA, counters };
}

function ResumeOwnershipFixture() {
  const mode = FIXTURE_MODE;
  const first = useRef<ControlledFixture | null>(null);
  if (first.current === null) first.current = createFixtureTransport(mode);
  const initial = first.current!;
  const fixtures = useRef<ControlledFixture[]>([initial]);
  const [mounted, setMounted] = useState(true);
  const [fixture, setFixture] = useState<ControlledFixture>(initial);
  const replaceTransport = () => {
    const replacement = createFixtureTransport(mode);
    fixtures.current.push(replacement);
    setFixture(replacement);
  };
  return (
    <>
      <aside
        aria-label="Synthetic resume ownership harness"
        data-testid="synthetic-resume-harness"
        style={{ background: "#32120f", border: "4px solid #ffb000", color: "#fff", padding: "12px", position: "relative", zIndex: 20 }}
      >
        <strong>FICTIONAL SYNTHETIC DATA — RESUME OWNERSHIP HARNESS</strong>
        <span style={{ display: "block" }}>No provider, model, tool, native, or durable side effect is used.</span>
        <button onClick={() => fixtures.current.forEach((item) => item.releaseA())} type="button">Release deferred resume A</button>{" "}
        <button onClick={() => fixtures.current.forEach((item) => item.failA())} type="button">Fail deferred resume A</button>{" "}
        <button onClick={replaceTransport} type="button">Replace transport with same synthetic IDs</button>{" "}
        <button onClick={() => setMounted(false)} type="button">Unmount Agent page</button>{" "}
        {!mounted && <button onClick={() => setMounted(true)} type="button">Mount Agent page</button>}
      </aside>
      {mounted && (
        <App
          platform={createBrowserPlatform()}
          runtime={createRuntimeComposition("synthetic_demo", fixture.transport)}
        />
      )}
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ResumeOwnershipFixture />
  </StrictMode>,
);
