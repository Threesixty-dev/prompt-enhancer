import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "../../src/app/App";
import type {
  AgentCatalogSession,
  AgentEvent,
  AgentProject,
  AgentSessionView,
} from "../../src/shared/api/contracts";
import { createSyntheticTransport } from "../../src/shared/api/syntheticTransport";
import { createBrowserPlatform } from "../../src/shared/platform/browserPlatform";
import { createRuntimeComposition, type SyntheticRuntimeTransport } from "../../src/shared/platform/runtimeMode";
import "../../src/styles.css";
import "../../src/app/theme.css";
import "../../src/app/palette.generated.css";

const fixtureQuery = window.location.search;
window.history.replaceState(null, "", "/agent");

const PROJECT_ID = "1".repeat(32);
const RETAINED_SESSION_ID = "2".repeat(32);
const METADATA_SESSION_ID = "3".repeat(32);
const BASE_TIME = "2040-01-01T00:00:00Z";
const FIND_TEXT = "SYNTHETIC_CONVERSATION_MATCH";
const EVENT_COUNT = new URLSearchParams(fixtureQuery).get("events") === "201" ? 201 : 260;

const counters = {
  modelActions: 0,
  mutationActions: 0,
  persistedReads: 0,
  savedSearches: 0,
  sentMessages: 0,
  liveEventReads: 0,
};

function publishCounters() {
  document.documentElement.dataset.conversationNavigationEventCount = String(EVENT_COUNT);
  for (const [name, value] of Object.entries(counters)) {
    document.documentElement.dataset[`conversationNavigation${name[0].toUpperCase()}${name.slice(1)}`] = String(value);
  }
}

function project(): AgentProject {
  return {
    contract_version: "agent-catalog.v2",
    project_id: PROJECT_ID,
    name: "Synthetic navigation project",
    created_at: BASE_TIME,
    updated_at: BASE_TIME,
    revision: 1,
    pinned: false,
    archived_at: null,
    session_count: 2,
    is_default: false,
  };
}

function catalog(
  sessionId: string,
  title: string,
  overrides: Partial<AgentCatalogSession> = {},
): AgentCatalogSession {
  return {
    contract_version: "agent-catalog.v2",
    session_id: sessionId,
    project_id: PROJECT_ID,
    title,
    workspace: "D:/synthetic/conversation-navigation",
    model_alias: null,
    created_at: BASE_TIME,
    updated_at: BASE_TIME,
    last_opened_at: BASE_TIME,
    revision: 1,
    pinned: false,
    archived_at: null,
    history_state: "durable_local",
    retention_policy: "local_history",
    history_revision: EVENT_COUNT,
    last_event_seq: EVENT_COUNT,
    turn_count: Math.ceil(EVENT_COUNT / 2),
    conversation_available: true,
    lineage: null,
    ...overrides,
  };
}

function event(
  seq: number,
  kind: AgentEvent["kind"],
  text: string | null,
  reasoning: string | null = null,
): AgentEvent {
  return {
    seq,
    at: BASE_TIME,
    kind,
    text,
    reasoning,
    attachments: [],
    tool: null,
    arguments: null,
    call_id: null,
    approval_id: null,
    ok: null,
    preview: null,
  };
}

const retainedEvents: AgentEvent[] = Array.from({ length: EVENT_COUNT }, (_, index) => {
  const sequence = index + 1;
  if (sequence === 7 || (EVENT_COUNT > 241 && sequence === 241)) {
    return event(sequence, sequence === 7 ? "user" : "assistant", `${FIND_TEXT} in visible message ${sequence}.`);
  }
  if (sequence === 30) return event(sequence, "tool_result", `${FIND_TEXT} tool output must not be searchable.`);
  if (sequence === 60) return event(sequence, "assistant", "Synthetic assistant text without the marker.", `${FIND_TEXT} reasoning must not be searchable.`);
  if (sequence === 90) return event(sequence, "assistant_delta", `${FIND_TEXT} incomplete delta must not be searchable.`);
  if (EVENT_COUNT === 201 || sequence % 9 === 0) return event(sequence, "status", `Synthetic status filler ${sequence}.`);
  return event(sequence, sequence % 2 === 0 ? "assistant" : "user", `Synthetic loaded message ${sequence}.`);
});

const sessions = [
  catalog(RETAINED_SESSION_ID, "Current synthetic conversation"),
  catalog(METADATA_SESSION_ID, "Metadata-only synthetic chat", {
    history_state: "memory_only",
    retention_policy: "metadata_only",
    history_revision: 0,
    last_event_seq: 0,
    turn_count: 0,
    conversation_available: false,
  }),
];

const liveSession: AgentSessionView = {
  contract_version: "local-agent.v9",
  cleanup_unconfirmed: false,
  closing: false,
  stopping: false,
  session_id: RETAINED_SESSION_ID,
  running: false,
  pending_approval_id: null,
  last_seq: EVENT_COUNT,
  turns: Math.ceil(EVENT_COUNT / 2),
  history_revision: EVENT_COUNT,
  model_alias: null,
  created_at: BASE_TIME,
  recovered: false,
  authority_revalidated: true,
  history_write_failed: false,
  recovery_state: "current",
  settings: {
    workspace: "D:/synthetic/conversation-navigation",
    project_id: PROJECT_ID,
    model_alias: null,
    parameters: { temperature: 0.2, top_p: 0.9, max_tokens: 100, enable_thinking: false },
    instructions: null,
    allow_writes: false,
    allow_commands: false,
    allow_web: false,
    max_steps: 1,
    command_timeout_seconds: 1,
    title: "Current synthetic conversation",
    retention_policy: "local_history",
  },
};

const metadataLiveSession: AgentSessionView = {
  ...liveSession,
  session_id: METADATA_SESSION_ID,
  settings: {
    ...liveSession.settings,
    title: "Metadata-only synthetic chat",
    retention_policy: "metadata_only",
  },
  last_seq: 1,
  turns: 1,
  history_revision: 1,
};

let appendListener: ((page: { events: AgentEvent[]; lastSeq: number }) => void) | null = null;
let appended = false;

const base = createSyntheticTransport();
const transport: SyntheticRuntimeTransport = {
  ...base,
  listAgentProjects: async () => ({ contract_version: "agent-catalog.v2", projects: [project()] }),
  listAgentCatalogSessions: async () => ({ contract_version: "agent-catalog.v2", sessions }),
  getAgentCatalogSession: async (sessionId) => {
    const found = sessions.find((item) => item.session_id === sessionId);
    if (found === undefined) throw new Error("synthetic session unavailable");
    return found;
  },
  getAgentPersistedEvents: async (_projectId, sessionId, after) => {
    counters.persistedReads += 1;
    publishCounters();
    const source = sessionId === RETAINED_SESSION_ID ? retainedEvents : [];
    return {
      contract_version: "local-agent.v9" as const,
      cleanup_unconfirmed: false,
      closing: false,
      stopping: false,
      session_id: sessionId,
      events: source.filter((item) => item.seq > after).slice(0, 100),
      running: false,
      pending_approval_id: null,
      first_seq: source[0]?.seq ?? 0,
      last_seq: source.at(-1)?.seq ?? 0,
    };
  },
  listAgentSessions: async () => [liveSession, metadataLiveSession],
  getAgentEvents: async (sessionId, after) => {
    counters.liveEventReads += 1;
    publishCounters();
    const source = sessionId === RETAINED_SESSION_ID ? retainedEvents : sessionId === METADATA_SESSION_ID
      ? [event(1, "user", "Metadata-only live conversation text.")]
      : [];
    return {
      contract_version: "local-agent.v9" as const,
      cleanup_unconfirmed: false,
      closing: false,
      stopping: false,
      session_id: sessionId,
      events: source.filter((item) => item.seq > after),
      running: false,
      pending_approval_id: null,
      first_seq: source[0]?.seq ?? 0,
      last_seq: source.at(-1)?.seq ?? 0,
    };
  },
  streamAgentEvents: async (sessionId, after, onPage, signal) => {
    counters.liveEventReads += 1;
    publishCounters();
    const source = sessionId === RETAINED_SESSION_ID ? retainedEvents : sessionId === METADATA_SESSION_ID
      ? [event(1, "user", "Metadata-only live conversation text.")]
      : [];
    onPage({
      contract_version: "local-agent.v9",
      cleanup_unconfirmed: false,
      closing: false,
      stopping: false,
      session_id: sessionId,
      events: source.filter((item) => item.seq > after),
      running: false,
      pending_approval_id: null,
      first_seq: source[0]?.seq ?? 0,
      last_seq: source.at(-1)?.seq ?? 0,
    });
    let listener: ((page: { events: AgentEvent[]; lastSeq: number }) => void) | null = null;
    if (sessionId === RETAINED_SESSION_ID) {
      listener = (page: { events: AgentEvent[]; lastSeq: number }) => onPage({
        contract_version: "local-agent.v9",
        cleanup_unconfirmed: false,
        closing: false,
        stopping: false,
        session_id: sessionId,
        events: page.events,
        running: false,
        pending_approval_id: null,
        first_seq: 1,
        last_seq: page.lastSeq,
      });
      appendListener = listener;
    }
    await new Promise<void>((resolve) => {
      if (signal === undefined || signal.aborted) resolve();
      else signal.addEventListener("abort", () => resolve(), { once: true });
    });
    if (listener !== null && appendListener === listener) appendListener = null;
  },
  searchAgentSavedMessages: async () => {
    counters.savedSearches += 1;
    publishCounters();
    throw new Error("local conversation navigation must not invoke saved search");
  },
  sendAgentMessage: async (...args) => {
    counters.sentMessages += 1;
    publishCounters();
    return base.sendAgentMessage(...args);
  },
  activateLocalModel: async (...args) => {
    counters.modelActions += 1;
    publishCounters();
    return base.activateLocalModel(...args);
  },
  applyAgentWorkspaceEdit: async (...args) => {
    counters.mutationActions += 1;
    publishCounters();
    return base.applyAgentWorkspaceEdit(...args);
  },
};

const platform = createBrowserPlatform();
const runtime = createRuntimeComposition("synthetic_demo", transport);

function ConversationNavigationFixture() {
  const appendActivity = () => {
    if (appended || appendListener === null) return;
    appended = true;
    const activity = event(261, "status", "Synthetic appended status activity.");
    appendListener({ events: [activity], lastSeq: activity.seq });
  };

  return (
    <>
      <div style={{ bottom: 4, position: "fixed", right: 4, zIndex: 1 }}>
        <button onClick={appendActivity} type="button">Append synthetic activity</button>
      </div>
      <App
        platform={platform}
        runtime={runtime}
      />
    </>
  );
}

publishCounters();
createRoot(document.getElementById("root")!).render(
  <StrictMode><ConversationNavigationFixture /></StrictMode>,
);
