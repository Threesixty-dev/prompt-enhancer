import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { SessionMetric } from "../../shared/api/contracts";
import { SessionMetricCard } from "./SessionMetricCard";

const UNKNOWN_METRIC: SessionMetric = {
  key: "fictional.future.observation",
  version: 3,
  dimension: "future",
  display_name: "Fictional observation",
  numeric_value: null,
  text_value: null,
  unit: null,
  source: "synthetic_fixture",
  observed_count: 0,
  eligible_count: 2,
  coverage: 0,
  confidence: null,
  metric_pack_key: "example.metadata.session",
  metric_pack_version: 4,
  metric_engine_version: "example-engine-1",
  redactor_version: null,
  model_id: null,
  model_revision: null,
  tokenizer_id: null,
  prompt_version: null,
  rubric_version: null,
  computed_at: "2040-02-01T12:00:00Z",
};

describe("SessionMetricCard", () => {
  it("shows missing observations as unknown and preserves provenance", () => {
    render(<SessionMetricCard metric={UNKNOWN_METRIC} />);

    expect(screen.getByText("Unknown", { selector: "strong" })).toBeVisible();
    expect(screen.getByText(/no usable observations/i)).toBeVisible();
    expect(screen.getByRole("meter")).toHaveAccessibleName(
      "0 of 2 observations (0%)",
    );

    const provenance = screen.getByText("Definition and provenance");
    provenance.click();
    expect(screen.getByText("example-engine-1")).toBeVisible();
    expect(screen.getAllByText("Not reported")).toHaveLength(6);
  });
});
