import { createRoot } from "react-dom/client";
import { useMemo, useRef, useState } from "react";
import { MetricCoveragePanel } from "../../src/features/metric-coverage/MetricCoveragePanel";
import type { MetricCoverageReport } from "../../src/shared/api/contracts";
import { SYNTHETIC_METRIC_COVERAGE } from "../../src/shared/api/syntheticFixtures";
import { createSyntheticTransport } from "../../src/shared/api/syntheticTransport";
import "../../src/styles.css";
import "../../src/app/theme.css";
import "../../src/app/palette.generated.css";
import "../../src/features/metric-coverage/MetricCoveragePanel.css";

function report(count: number, generatedAt: string): MetricCoverageReport {
  const value = structuredClone(SYNTHETIC_METRIC_COVERAGE);
  value.generated_at = generatedAt;
  value.indexed_session_count = count;
  value.latest_completed_snapshot_count = count;
  value.latest_profile_runs = { completed: count, running: 0, failed: 0, never_run: 0 };
  for (const metric of value.metrics) {
    metric.latest_completed_run_count = count;
    metric.selected_run_count = count;
    metric.completed_selected_run_count = count;
    metric.contract_compatible_result_states = { known: count, unknown: 0, not_applicable: 0, abstained: 0, execution_error: 0 };
    metric.compatible_provenance_cohort_count = count === 0 ? 0 : 1;
  }
  return value;
}

function Fixture() {
  const mode = new URLSearchParams(window.location.search).get("mode") ?? "success";
  const call = useRef(0);
  const [calls, setCalls] = useState(0);
  const transport = useMemo(() => {
    const value = createSyntheticTransport();
    value.getMetricCoverage = async (): Promise<MetricCoverageReport> => {
      const index = ++call.current;
      setCalls(index);
      if (mode === "initial-cancel" && index === 1) return new Promise(() => undefined);
      if (mode === "refresh-failure" && index === 2) throw new Error("synthetic fixture failure");
      if (mode === "refresh-cancel" && index === 2) return new Promise(() => undefined);
      return index === 1 ? report(1, "2040-01-03T09:13:00Z") : report(2, "2040-01-04T10:14:00Z");
    };
    return value;
  }, [mode]);
  return <main>
    <p data-testid="coverage-calls">Coverage GETs: {calls}</p>
    <MetricCoveragePanel provider="synthetic" transport={transport} />
  </main>;
}

createRoot(document.getElementById("root")!).render(<Fixture />);
