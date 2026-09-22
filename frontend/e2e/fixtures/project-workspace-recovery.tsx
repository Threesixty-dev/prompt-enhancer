import { useMemo, useRef } from "react";
import { createRoot } from "react-dom/client";
import { ProjectWorkspace } from "../../src/features/project-workspace/ProjectWorkspace";
import type { CodexSession, PromptEnhancerTransport } from "../../src/shared/api/contracts";
import { createSyntheticTransport } from "../../src/shared/api/syntheticTransport";
import "../../src/styles.css";
import "../../src/app/theme.css";
import "../../src/app/palette.generated.css";

const PROJECT_ID = "a".repeat(64);
const PAGE_SIZE = 100;
const id = (value: number) => value.toString(16).padStart(64, "0");
const sessions: CodexSession[] = Array.from({ length: 101 }, (_, index) => ({
  adapter_version: "synthetic-cp18-v1", ended_at: null, events_complete: false,
  installation_id: id(1), project_display_name: "Recovery project", project_display_name_origin: "provider",
  project_id: PROJECT_ID, project_manual_label_revision: 0, provider: "synthetic",
  provider_version: "synthetic-cp18-v1", session_display_name: `Recovery session ${index + 1}`,
  session_display_name_origin: "provider", session_id: id(index + 10), session_manual_label_revision: 0,
  source_schema_version: "synthetic-cp18-v1", started_at: new Date(Date.UTC(2042, 0, 1) - index * 60_000).toISOString(), terminal_state: "unknown",
}));
type Mode = "initial" | "older-reject" | "older-hang" | "older-malformed";

function Fixture() {
  const mode = (new URLSearchParams(location.search).get("mode") as Mode | null) ?? "initial";
  const recoveryEnabled = useRef(false);
  const calls = useRef<string[]>([]);
  const initialAttempts = useRef(0);
  const olderAttempts = useRef(0);
  const transport = useMemo<PromptEnhancerTransport>(() => {
    const base = createSyntheticTransport();
    return {
      ...base,
      getSessionMetrics: async (sessionId) => {
        if (sessionId !== sessions[100].session_id) throw new Error("synthetic session mismatch");
        return { session_id: sessionId, metrics: [] };
      },
      listProjectSessions: async (projectId, limit = PAGE_SIZE, offset = 0, signal) => {
        calls.current.push(`${limit}:${offset}`);
        document.documentElement.dataset.requests = calls.current.join(",");
        if (projectId !== PROJECT_ID) throw new Error("synthetic project mismatch");
        if (offset === 0 && mode === "initial" && initialAttempts.current++ === 0 && !recoveryEnabled.current) {
          return new Promise((_, reject) => signal?.addEventListener("abort", () => reject(new DOMException("cancel", "AbortError")), { once: true }));
        }
        if (offset === PAGE_SIZE) {
          const firstAttempt = olderAttempts.current++ === 0 && !recoveryEnabled.current;
          if (firstAttempt && mode === "older-reject") throw new Error("synthetic older outage");
          if (firstAttempt && mode === "older-hang") return new Promise((_, reject) => signal?.addEventListener("abort", () => reject(new DOMException("cancel", "AbortError")), { once: true }));
          const page = sessions.slice(offset, offset + limit);
          if (firstAttempt && mode === "older-malformed") return { sessions: page, limit, offset, total: 102, has_more: false };
          return { sessions: page, limit, offset, total: 101, has_more: false };
        }
        const page = sessions.slice(offset, offset + limit);
        return { sessions: page, limit, offset, total: 101, has_more: true };
      },
    };
  }, [mode]);
  return <main>
    <button onClick={() => { recoveryEnabled.current = true; }} type="button">Enable synthetic recovery</button>
    <ProjectWorkspace coverageProvider="synthetic" navigate={() => undefined} route={{ name: "session_metrics", projectId: PROJECT_ID, sessionId: sessions[100].session_id, category: "tools" }} transport={transport} />
  </main>;
}
createRoot(document.getElementById("root")!).render(<Fixture />);
