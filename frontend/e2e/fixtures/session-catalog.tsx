import { useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { SessionsPage } from "../../src/features/session-catalog/SessionsPage";
import type { CodexSession, PromptEnhancerTransport } from "../../src/shared/api/contracts";
import { createSyntheticTransport } from "../../src/shared/api/syntheticTransport";
import "../../src/styles.css";
import "../../src/app/theme.css";
import "../../src/app/palette.generated.css";

const PAGE_SIZE = 100;
const id = (value: number) => value.toString(16).padStart(64, "0");

function catalog(scope: "primary" | "replacement"): CodexSession[] {
  return Array.from({ length: PAGE_SIZE + 1 }, (_, index) => ({
    adapter_version: "synthetic-cp16-v1",
    ended_at: null,
    events_complete: false,
    installation_id: id(scope === "primary" ? 1 : 2),
    project_display_name: `${scope === "primary" ? "Session catalog" : "Replacement scope"} project ${String(index + 1).padStart(3, "0")}`,
    project_display_name_origin: "provider",
    project_id: id((scope === "primary" ? 1_000 : 2_000) + index),
    project_manual_label_revision: 0,
    provider: index % 2 === 0 ? "codex" : "claude_code",
    provider_version: "synthetic-cp16-v1",
    session_display_name: `${scope === "primary" ? "Session catalog" : "Replacement scope"} ${String(index + 1).padStart(3, "0")}`,
    session_display_name_origin: "provider",
    session_id: id((scope === "primary" ? 10_000 : 20_000) + index),
    session_manual_label_revision: 0,
    source_schema_version: "synthetic-cp16-v1",
    started_at: new Date(Date.parse("2041-01-01T00:00:00Z") - index * 60_000).toISOString(),
    terminal_state: "unknown",
  }));
}

type Mode = "normal" | "page-failure" | "slow-page";

function Fixture() {
  const mode = (new URLSearchParams(window.location.search).get("mode") as Mode | null) ?? "normal";
  const [scope, setScope] = useState<"primary" | "replacement">("primary");
  const attempts = useRef(0);
  const requests = useRef<string[]>([]);
  const publish = () => document.documentElement.setAttribute("data-session-catalog-requests", requests.current.join(","));
  const transport = useMemo<PromptEnhancerTransport>(() => {
    const base = createSyntheticTransport();
    const records = catalog(scope);
    return {
      ...base,
      listCodexSessions: async (limit = PAGE_SIZE, offset = 0, signal) => {
        requests.current.push(`${scope}:${limit}:${offset}`);
        publish();
        if (offset === PAGE_SIZE) {
          attempts.current += 1;
          if (mode === "page-failure" && attempts.current === 1) throw new Error("synthetic next-page outage");
          if (mode === "slow-page") {
            return new Promise((_, reject) => {
              signal?.addEventListener("abort", () => {
                document.documentElement.setAttribute("data-session-catalog-cancelled", "true");
                reject(new DOMException("Synthetic cancellation", "AbortError"));
              }, { once: true });
            });
          }
        }
        return { sessions: records.slice(offset, offset + limit), limit, offset };
      },
    };
  }, [mode, scope]);

  return <main>
    <button onClick={() => setScope("replacement")} type="button">Replace session catalog scope</button>
    <p aria-live="polite">Synthetic session scope: {scope}</p>
    <SessionsPage navigate={() => undefined} transport={transport} />
  </main>;
}

createRoot(document.getElementById("root")!).render(<Fixture />);
