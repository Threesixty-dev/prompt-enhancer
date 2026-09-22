import { useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { ProjectCatalog } from "../../src/features/project-catalog";
import type { CodexSession, PromptEnhancerTransport } from "../../src/shared/api/contracts";
import { createSyntheticTransport } from "../../src/shared/api/syntheticTransport";
import "../../src/styles.css";
import "../../src/app/theme.css";
import "../../src/app/palette.generated.css";

const PAGE_SIZE = 100;
const ids = (value: number) => value.toString(16).padStart(64, "0");
const records: CodexSession[] = Array.from({ length: PAGE_SIZE + 1 }, (_, index) => ({
  adapter_version: "synthetic-cp15-v1",
  ended_at: null,
  events_complete: false,
  installation_id: ids(1),
  project_display_name: `Catalog page ${String(index + 1).padStart(3, "0")}`,
  project_display_name_origin: "provider",
  project_id: ids(index + 1000),
  project_manual_label_revision: 0,
  provider: "synthetic",
  provider_version: "synthetic-cp15-v1",
  session_display_name: `Catalog session ${String(index + 1).padStart(3, "0")}`,
  session_display_name_origin: "provider",
  session_id: ids(index + 10_000),
  session_manual_label_revision: 0,
  source_schema_version: "synthetic-cp15-v1",
  started_at: new Date(Date.parse("2041-01-01T00:00:00Z") - (index * 60_000)).toISOString(),
  terminal_state: "unknown",
}));

type Mode = "normal" | "page-failure" | "slow-page";

function Fixture() {
  const mode = new URLSearchParams(window.location.search).get("mode") as Mode | null ?? "normal";
  const [transportRevision, setTransportRevision] = useState(0);
  const pageAttempts = useRef(0);
  const requests = useRef<string[]>([]);
  const publish = () => document.documentElement.setAttribute("data-catalog-requests", requests.current.join(","));
  const transport = useMemo<PromptEnhancerTransport>(() => {
    const base = createSyntheticTransport();
    return {
      ...base,
      listCodexSessions: async (limit = PAGE_SIZE, offset = 0, signal) => {
        requests.current.push(`${transportRevision}:${limit}:${offset}`);
        publish();
        if (offset === PAGE_SIZE) {
          pageAttempts.current += 1;
          if (mode === "page-failure" && pageAttempts.current === 1) {
            throw new Error("synthetic next-page outage");
          }
          if (mode === "slow-page") {
            return new Promise((_, reject) => {
              signal?.addEventListener("abort", () => {
                document.documentElement.setAttribute("data-catalog-cancelled", "true");
                reject(new DOMException("Synthetic cancellation", "AbortError"));
              }, { once: true });
            });
          }
          return { sessions: [records[PAGE_SIZE]], limit, offset };
        }
        return { sessions: records.slice(offset, offset + limit), limit, offset };
      },
    };
  }, [mode, transportRevision]);
  return <main>
    <button onClick={() => setTransportRevision((value) => value + 1)} type="button">
      Replace catalog transport
    </button>
    <p aria-live="polite">Synthetic catalog transport revision {transportRevision}</p>
    <ProjectCatalog coverageProvider="synthetic" navigate={() => undefined} transport={transport} />
  </main>;
}

createRoot(document.getElementById("root")!).render(<Fixture />);
