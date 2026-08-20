import { useEffect, useState } from "react";
import type { PromptEnhancerTransport } from "../../shared/api/contracts";
import { PromptMetricRadar } from "../prompt-check/promptCheckPlots";
import "./SessionRadarCard.css";

const SHORT: Record<string, string> = {
  "prompt.task_definition_coverage": "Task definition",
  "prompt.problem_evidence_quality": "Problem evidence",
  "prompt.context_sufficiency": "Context",
  "prompt.constraint_precision": "Constraints",
  "prompt.acceptance_testability": "Acceptance",
  "prompt.deliverable_contract": "Deliverable",
  "collaboration.ambiguity_resolution": "Ambiguity resolved",
  "logic.requirement_action_traceability": "Req → action",
  "logic.open_loop_closure": "Loops closed",
  "outcome.first_pass_verification": "First-pass checks",
  "outcome.verification_strategy_adequacy": "Verification",
  "outcome.agent_claim_grounding": "Claims grounded",
};
const AXES = Object.keys(SHORT);
const LOWER_IS_BETTER = new Set<string>([]);

type MetricRow = { key?: unknown; numeric_value?: unknown };

/**
 * One radar of this session's stored metric values - the same numbers as the
 * metric deck, drawn as a shape. Metrics without a measured value sit at the
 * centre marked n/a; nothing here is a model judgment.
 */
export function SessionRadarCard({
  sessionId,
  transport,
}: {
  sessionId: string;
  transport: Pick<PromptEnhancerTransport, "getSessionMetrics">;
}) {
  const [rows, setRows] = useState<MetricRow[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setRows(null);
    setFailed(false);
    transport.getSessionMetrics(sessionId, controller.signal)
      .then((value) => { if (!controller.signal.aborted) setRows(Array.isArray(value.metrics) ? (value.metrics as MetricRow[]) : []); })
      .catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => controller.abort();
  }, [sessionId, transport]);

  if (failed || rows === null) return null;
  const byKey = new Map<string, number>();
  for (const row of rows) {
    const key = typeof row.key === "string" ? row.key : "";
    if (AXES.includes(key) && typeof row.numeric_value === "number" && !byKey.has(key)) byKey.set(key, row.numeric_value);
  }
  const readings = AXES.map((key) => ({ key, label: SHORT[key], value: byKey.has(key) ? Math.max(0, Math.min(1, byKey.get(key) as number)) : null, higherIsBetter: !LOWER_IS_BETTER.has(key) }));
  const known = readings.filter((r) => r.value !== null).length;
  if (known === 0) return null;

  return (
    <section aria-labelledby="session-radar-title" className="session-radar">
      <header>
        <div>
          <p className="eyebrow">Measured values · same numbers as the metric deck</p>
          <h3 id="session-radar-title">Session radar</h3>
        </div>
        <span className="session-radar__count">{known} of {readings.length} measurable</span>
      </header>
      <PromptMetricRadar readings={readings} />
    </section>
  );
}
