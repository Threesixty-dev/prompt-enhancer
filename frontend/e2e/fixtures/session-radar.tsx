import { useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import type { ComponentProps } from "react";
import { SessionRadarCard } from "../../src/features/session-radar/SessionRadarCard";
import { parseModelEnsembleRun } from "../../src/shared/api/modelEnsembleContract";
import { createSessionRadarRun } from "../../src/test/sessionRadarFixture";
import "../../src/styles.css";
import "../../src/app/theme.css";
import "../../src/app/palette.generated.css";

const SESSION_ID = "a".repeat(64);
type RadarTransport = ComponentProps<typeof SessionRadarCard>["transport"];
type LateResolver = (() => void) | null;

function parsedRun(source: "v2" | "typed" | "committee" = "v2") {
  return parseModelEnsembleRun(createSessionRadarRun({ source }));
}

function readCount(name: "latestReads" | "storedReads") {
  const current = Number(document.documentElement.dataset[name] ?? "0") + 1;
  document.documentElement.dataset[name] = String(current);
}

function Fixture() {
  const mode = new URLSearchParams(location.search).get("mode") ?? "canonical";
  const recovered = useRef(false);
  const [transportVersion, setTransportVersion] = useState(0);
  const lateResolver = useRef<LateResolver>(null);

  const transport = useMemo<RadarTransport>(() => ({
    getSessionMetrics: async () => {
      readCount("storedReads");
      return { session_id: SESSION_ID, metrics: [] };
    },
    getLatestModelEnsemble: async () => {
      readCount("latestReads");
      if (mode === "pending" && !recovered.current) {
        return new Promise<ReturnType<typeof parsedRun>>((resolve) => {
          lateResolver.current = () => resolve(parsedRun());
        });
      }
      if (mode === "empty") throw { status: 404 };
      if (mode === "error") throw { status: 500 };
      if (mode === "owner" && transportVersion === 0) {
        return new Promise<ReturnType<typeof parsedRun>>((resolve) => {
          lateResolver.current = () => resolve(parsedRun("committee"));
        });
      }
      return parsedRun();
    },
  }), [mode, transportVersion]);

  return (
    <main>
      <p className="eyebrow">Synthetic demo · parser-valid, content-free session radar receipt</p>
      {mode === "pending" && (
        <button onClick={() => { recovered.current = true; }} type="button">
          Enable session radar recovery
        </button>
      )}
      {mode === "owner" && (
        <>
          <button onClick={() => setTransportVersion((value) => value + 1)} type="button">
            Replace synthetic radar transport
          </button>
          <button onClick={() => lateResolver.current?.()} type="button">
            Resolve prior radar read
          </button>
        </>
      )}
      <SessionRadarCard sessionId={SESSION_ID} transport={transport} />
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<Fixture />);
