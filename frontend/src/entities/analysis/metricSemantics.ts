import type { PillTone } from "../../shared/ui/StatusPill";

export type MetricValueState =
  | "known"
  | "unknown"
  | "not_applicable"
  | "abstained"
  | "execution_error";

export interface MetricSemantics {
  label: string;
  detail: string;
  tone: PillTone;
  partial: boolean;
}

function hasIncompleteCoverage(
  observed: number,
  eligible: number,
  coverage: number,
): boolean {
  return eligible <= 0 || observed < eligible || coverage < 1;
}

export function describeMetricSemantics(input: {
  state: MetricValueState;
  numericValue: number | null;
  unit?: string | null;
  confidence?: number | null;
  observed: number;
  eligible: number;
  coverage: number;
}): MetricSemantics {
  if (input.state === "known") {
    const partial =
      input.confidence === null ||
      hasIncompleteCoverage(input.observed, input.eligible, input.coverage);
    const isRate = input.unit === "ratio";
    if (partial && input.numericValue === 0) {
      if (isRate) {
        return {
          label: "Partial",
          detail:
            "Observed rate - partial coverage. Zero applies only to usable evidence in this current snapshot; it does not confirm absence.",
          tone: "warning",
          partial: true,
        };
      }
      return {
        label: "Partial",
        detail:
          "Observed subtotal - partial. Zero means no matching evidence was observed in this current snapshot; it does not confirm absence.",
        tone: "warning",
        partial: true,
      };
    }
    if (partial) {
      if (isRate) {
        return {
          label: "Partial",
          detail:
            "Observed rate - partial coverage. Missing evidence or uncertain stream completeness may change this rate.",
          tone: "warning",
          partial: true,
        };
      }
      return {
        label: "Partial",
        detail:
          "Observed subtotal - partial. Missing evidence or uncertain stream completeness may change this value.",
        tone: "warning",
        partial: true,
      };
    }
    return {
      label: "Observed",
      detail: "Current snapshot - complete for this metric's eligible evidence.",
      tone: "info",
      partial: false,
    };
  }

  if (input.state === "unknown") {
    if (input.eligible <= 0) {
      return {
        label: "Unknown",
        detail:
          "No eligible evidence was available in this current snapshot, so no value was inferred.",
        tone: "unknown",
        partial: true,
      };
    }
    if (input.observed <= 0) {
      return {
        label: "Unknown",
        detail:
          "Eligible evidence exists, but no usable observations were available in this current snapshot.",
        tone: "unknown",
        partial: true,
      };
    }
    return {
      label: "Unknown",
      detail:
        "Available observations were insufficient to infer a value in this current snapshot.",
      tone: "unknown",
      partial: true,
    };
  }

  if (input.state === "not_applicable") {
    return {
      label: "Not applicable",
      detail: "This metric has no eligible evidence for the current snapshot.",
      tone: "info",
      partial: false,
    };
  }

  if (input.state === "abstained") {
    return {
      label: "Abstained",
      detail: "The calculator intentionally made no claim from the current snapshot.",
      tone: "warning",
      partial: true,
    };
  }

  return {
    label: "Execution error",
    detail: "The calculation did not complete; no metric value is available.",
    tone: "danger",
    partial: true,
  };
}
