import { useMemo, useRef } from "react";
import { createRoot } from "react-dom/client";
import { ProjectWorkspace } from "../../src/features/project-workspace/ProjectWorkspace";
import type { CodexSession, PromptEnhancerTransport } from "../../src/shared/api/contracts";
import { createSyntheticTransport } from "../../src/shared/api/syntheticTransport";
import { SYNTHETIC_CURRENT_SESSION_QUALITY_RUN, SYNTHETIC_QUALITY_PROJECT_ID, SYNTHETIC_QUALITY_SESSION_ID, SYNTHETIC_SESSION_METRIC_READINESS } from "../../src/shared/api/syntheticFixtures";
import "../../src/styles.css"; import "../../src/app/theme.css"; import "../../src/app/palette.generated.css";
const projectId = SYNTHETIC_QUALITY_PROJECT_ID, sessionId = SYNTHETIC_QUALITY_SESSION_ID;
const session: CodexSession = { adapter_version: "synthetic-cp19-v1", ended_at: null, events_complete: false, installation_id: "d".repeat(64), project_display_name: "Drilldown project", project_display_name_origin: "provider", project_id: projectId, project_manual_label_revision: 0, provider: "synthetic", provider_version: "synthetic-cp19-v1", session_display_name: "Drilldown session", session_display_name_origin: "provider", session_id: sessionId, session_manual_label_revision: 0, source_schema_version: "synthetic-cp19-v1", started_at: "2042-01-01T00:00:00Z", terminal_state: "unknown" };
function Fixture() {
  const mode = new URLSearchParams(location.search).get("mode") ?? "metrics";
  const recovered = useRef(false);
  const qualityReads = useRef(0);
  const readinessReads = useRef(0);
  const transport = useMemo<PromptEnhancerTransport>(() => {
    const base = createSyntheticTransport();
    const hang = <T,>(signal: AbortSignal | undefined) => new Promise<T>((_, reject) => {
      signal?.addEventListener("abort", () => reject(new DOMException("cancel", "AbortError")), { once: true });
    });
    return {
      ...base,
      listProjectSessions: async () => ({ sessions: [session], limit: 100, offset: 0, total: 1, has_more: false }),
      getSessionMetrics: async (_id, signal) => {
        document.documentElement.dataset.metricReads = String(Number(document.documentElement.dataset.metricReads ?? 0) + 1);
        return recovered.current ? { session_id: sessionId, metrics: [] } : hang(signal);
      },
      getLatestSessionQualityAnalysis: async (_id, signal) => {
        qualityReads.current += 1; document.documentElement.dataset.qualityReads = String(qualityReads.current);
        return (mode === "quality" || mode === "both") && !recovered.current ? hang(signal) : SYNTHETIC_CURRENT_SESSION_QUALITY_RUN;
      },
      getSessionMetricReadiness: async (_id, _preset, signal) => {
        readinessReads.current += 1; document.documentElement.dataset.readinessReads = String(readinessReads.current);
        if ((mode === "readiness" || mode === "both") && !recovered.current) return hang(signal);
        if (mode === "readiness-fail" && !recovered.current) throw new Error("synthetic readiness failure");
        return SYNTHETIC_SESSION_METRIC_READINESS;
      },
    };
  }, [mode]);
  return (
    <main>
      <button onClick={() => { recovered.current = true; }} type="button">
        Enable drilldown recovery
      </button>
      <ProjectWorkspace
        coverageProvider="synthetic"
        navigate={() => undefined}
        route={{ name: "session_metrics", projectId, sessionId, category: mode === "metrics" ? "tools" : "prompt-quality" }}
        transport={transport}
      />
    </main>
  );
}
createRoot(document.getElementById("root")!).render(<Fixture />);
