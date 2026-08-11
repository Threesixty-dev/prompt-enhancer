import type { SessionQualityAnalysisRequest } from "../../shared/api/contracts";

/**
 * The default UI deliberately exposes one stable server-owned preset instead
 * of asking people to configure metric semantics before every run.
 */
export const COACHING_ANALYSIS_PRESET = Object.freeze({
  key: "coaching_profile_v1" as const,
  label: "Coaching profile",
  version: 1,
  metricAttempts: 20,
  maxMessages: 100,
  maxCharacters: 100_000,
});

export const COACHING_ANALYSIS_REQUEST = Object.freeze({
  preset_id: COACHING_ANALYSIS_PRESET.key,
  confirmation: "analyze_selected_redacted_text" as const,
}) satisfies Readonly<SessionQualityAnalysisRequest>;
