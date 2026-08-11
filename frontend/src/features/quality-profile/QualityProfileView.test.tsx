import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ProviderCompatibilityStatus } from "../../shared/api/contracts";
import {
  SYNTHETIC_QUALITY_SESSION_ID,
  SYNTHETIC_SESSION_QUALITY_RUN,
} from "../../shared/api/syntheticFixtures";
import { createQualityMetricProfile } from "./qualityProfile";
import { QualityProfileView } from "./QualityProfileView";

function promptProfile() {
  return createQualityMetricProfile(
    "prompt-quality",
    structuredClone(SYNTHETIC_SESSION_QUALITY_RUN),
    SYNTHETIC_QUALITY_SESSION_ID,
  )!;
}

const EXACT_COMPATIBILITY: ProviderCompatibilityStatus = {
  provider: "codex",
  capability: "session_text_analysis",
  state: "exact",
  capability_state: "supported",
  provider_family: "codex_app_server",
  provider_version: "1.2.3",
  adapter_family: "codex_app_server",
  adapter_version: "2.0.0",
  source_schema_family: "codex_thread",
  source_schema_version: "1",
  content_schema_family: "codex_thread_items",
  content_schema_version: "1",
  reason_code: "exact_match",
  checked_at: "2040-01-01T10:00:00Z",
  update_support: "unsupported",
  update_target: null,
};

describe("QualityProfileView", () => {
  it("shows every metric in one zero-configuration control deck", () => {
    const profile = promptProfile();
    const { container } = render(<QualityProfileView profile={promptProfile()} />);

    expect(screen.getByRole("heading", { name: "Prompt contract" })).toBeVisible();
    expect(screen.getByText("Not enough available axes")).toBeVisible();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Radar availability")).toHaveTextContent("2 omitted as unavailable");
    expect(screen.getByLabelText("Radar availability")).toHaveTextContent("2 plotted axes");
    const board = screen.getByRole("region", { name: "Prompt-quality candidates" });
    expect(board).toBeVisible();
    for (const metric of profile.latest.metrics) {
      expect(within(board).getByText(metric.definition.label)).toBeVisible();
    }
    expect(
      container.querySelectorAll(
        ".quality-board__track:not(.quality-board__track--missing)",
      ),
    ).toHaveLength(3);
    expect(container.querySelectorAll(".quality-board__metric")).toHaveLength(5);
    expect(container.querySelector("select")).not.toBeInTheDocument();
    expect(container.querySelector('input[type="checkbox"]')).not.toBeInTheDocument();
    expect(container.querySelectorAll(".quality-profile__radar-panel")).toHaveLength(1);
    expect(container.querySelectorAll(".quality-profile__method-boundary")).toHaveLength(1);
    expect(container.querySelectorAll(".quality-radar__inspector-details")).toHaveLength(1);
    const radarPanel = container.querySelector(".quality-profile__radar-panel");
    expect(radarPanel).toHaveAttribute("open");
    expect(screen.getByText("Prompt-quality radar")).toBeVisible();
    fireEvent.click(within(radarPanel as HTMLElement).getByText("Prompt-quality radar"));
    expect(radarPanel).not.toHaveAttribute("open");
    fireEvent.click(within(radarPanel as HTMLElement).getByText("Prompt-quality radar"));
    expect(radarPanel).toHaveAttribute("open");
    expect(screen.getByText("Methods & details")).toBeVisible();
    expect(screen.getByText("Broader value map")).toBeVisible();
    expect(screen.getByText("9 families")).toBeVisible();
    expect(
      screen.getByText(/0 assessable · 3 partial · 2 not measurable/),
    ).toBeVisible();
    const goalMetric = within(board)
      .getByText("Goal cue coverage")
      .closest(".quality-board__metric");
    expect(goalMetric).not.toBeNull();
    expect(
      goalMetric?.querySelector<HTMLElement>(".quality-board__track > span"),
    ).toHaveStyle({ width: "100%" });
    expect(screen.queryByText("Overall score")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("Methods & details"));
    expect(screen.getByText("Standard engineering v1")).toBeVisible();
    expect(screen.getByRole("heading", { name: "How these percentages are produced" })).toBeVisible();
    expect(screen.getByText(/Active coaching model: none/i)).toBeVisible();
    expect(screen.getByText(/Qwen3 Embedding 0.6B and BGE Reranker v2 M3/i)).toBeVisible();
    expect(screen.getByText(/3 of 3 metric-specific items/i)).toBeVisible();
    expect(screen.getAllByText(/8 of 10 eligible observations/i).length).toBeGreaterThan(0);
    expect(screen.getByText("Requested action cue")).toBeVisible();
    expect(screen.getAllByText("Detected")).toHaveLength(3);
    expect(screen.getByText(/lower is better only as a review cue/i)).toBeVisible();
  });

  it("keeps the absent initial snapshot disabled and exposes only an explicit run action", () => {
    render(
      <QualityProfileView
        analysisCapability={{
          available: true,
          reason_code: "available",
          data_tier: "redacted_content",
          content_persistence: false,
          network_inference: false,
          raw_transcripts: false,
        }}
        onAnalyzeLocally={vi.fn(async () => undefined)}
        providerCompatibility={EXACT_COMPATIBILITY}
        profile={promptProfile()}
      />,
    );

    expect(screen.queryByRole("button", { name: "Initial request" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyze locally" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Analyze locally" })).toBeEnabled();
    fireEvent.click(screen.getByText("Methods & details"));
    expect(screen.getByText("Exact match")).toBeVisible();
  });

  it("keeps results visible but analysis disabled until compatibility is checked", () => {
    const onCheck = vi.fn(async () => undefined);
    render(
      <QualityProfileView
        analysisCapability={{
          available: true,
          reason_code: "available",
          data_tier: "redacted_content",
          content_persistence: false,
          network_inference: false,
          raw_transcripts: false,
        }}
        onAnalyzeLocally={vi.fn(async () => undefined)}
        onCheckProviderCompatibility={onCheck}
        profile={promptProfile()}
      />,
    );

    expect(screen.getByRole("button", { name: "Analyze locally" })).toBeDisabled();
    expect(screen.getByText(/has not been checked/i)).toBeVisible();
    expect(
      within(screen.getByRole("region", { name: "Prompt-quality candidates" })).getByText(
        "Goal cue coverage",
      ),
    ).toBeVisible();
    fireEvent.click(screen.getByText("Methods & details"));
    expect(screen.getByText("Standard engineering v1")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Check provider" }));
    expect(onCheck).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: /continue/i })).not.toBeInTheDocument();
  });

  it("warns when a completed run has legacy or unknown preset provenance", () => {
    const detail = structuredClone(SYNTHETIC_SESSION_QUALITY_RUN);
    delete (detail.run as Partial<typeof detail.run>).analysis_profile_key;
    delete (detail.run as Partial<typeof detail.run>).analysis_profile_version;
    const profile = createQualityMetricProfile(
      "prompt-quality",
      detail,
      SYNTHETIC_QUALITY_SESSION_ID,
    )!;

    render(<QualityProfileView profile={profile} />);

    fireEvent.click(screen.getByText("Methods & details"));
    expect(screen.getByText("Legacy / unknown analysis profile")).toBeVisible();
    expect(screen.queryByText("Standard engineering v1")).not.toBeInTheDocument();
  });

  it("fails closed with a truthful capability reason", () => {
    render(
      <QualityProfileView
        analysisCapability={{
          available: false,
          reason_code: "local_source_unavailable",
          data_tier: null,
          content_persistence: false,
          network_inference: false,
          raw_transcripts: false,
        }}
        onAnalyzeLocally={vi.fn(async () => undefined)}
        profile={promptProfile()}
      />,
    );

    expect(screen.getByRole("button", { name: "Analyze locally" })).toBeDisabled();
    expect(screen.getByText(/local-source adapter is not active/i)).toBeVisible();
  });

  it("does not enable analysis before capability verification completes", () => {
    render(
      <QualityProfileView
        onAnalyzeLocally={vi.fn(async () => undefined)}
        profile={promptProfile()}
      />,
    );

    expect(screen.getByRole("button", { name: "Analyze locally" })).toBeDisabled();
    expect(screen.getByText(/checking whether this local installation/i)).toBeVisible();
  });

  it("blocks values and sharing when the immutable result contract is contradictory", () => {
    const detail = structuredClone(SYNTHETIC_SESSION_QUALITY_RUN);
    detail.results[0].coverage = 1;
    const profile = createQualityMetricProfile(
      "prompt-quality",
      detail,
      SYNTHETIC_QUALITY_SESSION_ID,
    )!;
    const { container } = render(<QualityProfileView profile={profile} />);

    expect(container.querySelector(".quality-profile__snapshot-alert")).toHaveTextContent(
      "Invalid metric contract",
    );
    expect(screen.getByRole("button", { name: "Share profile" })).toBeDisabled();
    expect(screen.getByText(/comparison and sharing are blocked/i)).toBeVisible();
    expect(container.querySelectorAll(".quality-board__metric--missing")).toHaveLength(5);
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("presents an older coaching pack as re-analysis work, not corruption", () => {
    const detail = structuredClone(SYNTHETIC_SESSION_QUALITY_RUN);
    detail.run.analysis_profile_key = "coaching_profile";
    detail.run.analysis_profile_version = 1;
    detail.run.metric_pack_key = "experimental.redacted-text.coaching";
    detail.run.metric_pack_version = 1;
    const profile = createQualityMetricProfile(
      "prompt-quality",
      detail,
      SYNTHETIC_QUALITY_SESSION_ID,
    )!;

    render(<QualityProfileView profile={profile} />);

    expect(screen.getByText(/re-analysis required/i)).toBeVisible();
    expect(screen.getByText(/older immutable metric pack/i)).toBeVisible();
    expect(screen.queryByText("Invalid metric contract")).not.toBeInTheDocument();
    expect(
      screen.queryByText(/profile comparison and sharing are blocked/i),
    ).not.toBeInTheDocument();
  });

  it("does not allow sharing a no-run profile", () => {
    const profile = createQualityMetricProfile(
      "reasoning",
      null,
      SYNTHETIC_QUALITY_SESSION_ID,
    )!;
    render(<QualityProfileView profile={profile} />);

    expect(screen.getByText(/no compatible Coaching v1 analysis run/i)).toBeVisible();
    const shareButton = screen.getByRole("button", { name: "Share profile" });
    expect(shareButton).toBeDisabled();
    expect(shareButton).toHaveAttribute(
      "title",
      "Run Coaching v1 analysis before sharing",
    );
    expect(
      screen.queryByText(/profile comparison and sharing are blocked/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
  });
});
