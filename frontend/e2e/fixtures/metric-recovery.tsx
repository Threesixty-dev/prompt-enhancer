import { useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { MetricOperabilityPanel } from "../../src/features/research-lab/MetricOperabilityPanel";
import { MetricOperabilityDefinitionsOutOfDateError, createSyntheticMetricOperabilityCatalog, parseMetricOperabilityCatalog } from "../../src/shared/api/metricOperabilityContract";
import type { MetricOperabilityCatalog, PromptEnhancerTransport } from "../../src/shared/api/contracts";
import "../../src/styles.css";
import "../../src/app/theme.css";
import "../../src/app/palette.generated.css";
import "../../src/features/research-lab/MetricOperabilityPanel.css";

function Fixture() {
  const outOfDate = new URLSearchParams(window.location.search).get("state") === "out-of-date";
  const calls = useRef(0);
  const [requestCount, setRequestCount] = useState(0);
  const [validatedMap, setValidatedMap] = useState("none");
  const [unexpectedAccesses, setUnexpectedAccesses] = useState(0);
  const transport = useMemo(() => new Proxy({
    getMetricOperabilityCatalog: async (): Promise<MetricOperabilityCatalog> => {
      const call = ++calls.current;
      setRequestCount(call);
      if (outOfDate) throw new MetricOperabilityDefinitionsOutOfDateError();
      // The actual panel receives a real typed catalog. Calls 1 and 3 are
      // deliberately transient outages; calls 2 and 4 are current maps.
      if (call === 1 || call === 3) throw new Error("synthetic temporary catalog outage");
      setValidatedMap(call === 2 ? "initial" : "refreshed");
      return parseMetricOperabilityCatalog(createSyntheticMetricOperabilityCatalog());
    },
  }, {
    // The panel is intentionally given no session/model/mutation surface. Any
    // attempt to reach another transport method is visible to this fixture.
    get(target, property, receiver) {
      if (property !== "getMetricOperabilityCatalog") setUnexpectedAccesses((value) => value + 1);
      return Reflect.get(target, property, receiver);
    },
  }), [outOfDate]);
  return <main>
    <p data-testid="metric-recovery-counters">Catalog GETs: {requestCount} · Validated map: {validatedMap} · Unexpected transport method accesses: {unexpectedAccesses}</p>
    <MetricOperabilityPanel transport={transport as PromptEnhancerTransport} />
  </main>;
}

createRoot(document.getElementById("root")!).render(<Fixture />);
