import type { AnalysisResult } from "../../shared/api/contracts";
import { formatPercent, titleFromKey } from "../../shared/lib/format";
import { CoverageBar } from "../../shared/ui/CoverageBar";
import { Icon } from "../../shared/ui/Icon";
import { StatusPill, type PillTone } from "../../shared/ui/StatusPill";

const statePresentation: Record<
  AnalysisResult["value_state"],
  { label: string; detail: string; tone: PillTone }
> = {
  known: { label: "Known", detail: "Computed from available evidence", tone: "positive" },
  unknown: { label: "Unknown", detail: "Evidence is insufficient", tone: "neutral" },
  not_applicable: { label: "Not applicable", detail: "This metric does not apply", tone: "info" },
  abstained: { label: "Abstained", detail: "The calculator did not make a claim", tone: "warning" },
  execution_error: { label: "Execution error", detail: "The calculation did not complete", tone: "danger" },
};

function formatMetricValue(result: AnalysisResult): string {
  if (result.value_state !== "known") return statePresentation[result.value_state].label;
  if (result.numeric_value !== null) {
    if (result.unit === "ratio") return formatPercent(result.numeric_value);
    return `${new Intl.NumberFormat("en", { maximumFractionDigits: 2 }).format(result.numeric_value)} ${result.unit}`;
  }
  return result.text_value ? titleFromKey(result.text_value) : "Known";
}

export function MetricObservationCard({ result }: { result: AnalysisResult }) {
  const state = statePresentation[result.value_state];
  return (
    <article className={`metric-card metric-card--${result.value_state}`}>
      <div className="metric-card__header">
        <span className="metric-card__icon"><Icon name="activity" /></span>
        <StatusPill tone={state.tone}>{state.label}</StatusPill>
      </div>
      <div>
        <p className="metric-card__eyebrow">{titleFromKey(result.source)}</p>
        <h3>{titleFromKey(result.key)}</h3>
      </div>
      <p className="metric-card__value">{formatMetricValue(result)}</p>
      <p className="metric-card__detail">{state.detail}</p>
      <CoverageBar
        coverage={result.coverage}
        eligible={result.eligible_count}
        observed={result.observed_count}
      />
      <dl className="metric-card__footer">
        <div><dt>Definition</dt><dd>v{result.version}</dd></div>
        <div><dt>Evidence</dt><dd>{result.evidence_event_ids.length} refs</dd></div>
        <div><dt>Confidence</dt><dd>{result.confidence == null ? "Unknown" : formatPercent(result.confidence)}</dd></div>
      </dl>
    </article>
  );
}
