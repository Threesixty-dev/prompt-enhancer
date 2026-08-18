/**
 * Determinate progress primitive with an explicit `state` channel. The bar is
 * always the same height, so pause/resume/complete transitions never shift
 * layout; the state word is rendered as visible text (never colour-only or
 * hover-only) and echoed in `aria-valuetext`.
 */
export type ProgressMeterState = "idle" | "active" | "paused" | "complete" | "stopped";

export function ProgressMeter({
  label,
  value,
  max = 100,
  state,
  detail,
  compact = false,
}: {
  label: string;
  /** Completed units; `null` means the amount is not known and is not drawn as zero. */
  value: number | null;
  max?: number;
  state: ProgressMeterState;
  /** Visible detail such as "12.4 MB of 40 MB · paused". */
  detail: string;
  compact?: boolean;
}) {
  const bounded = value === null ? null : Math.max(0, Math.min(max, value));
  const percent = bounded === null || max <= 0 ? null : (bounded / max) * 100;
  return (
    <div className={`ui-progress${compact ? " ui-progress--compact" : ""}`} data-state={state}>
      <div className="ui-progress__label">
        <span>{label}</span>
        <span>{percent === null ? "Unknown" : `${Math.round(percent)}%`}</span>
      </div>
      <div
        aria-label={label}
        aria-valuemax={100}
        aria-valuemin={0}
        aria-valuenow={percent === null ? undefined : Math.round(percent)}
        aria-valuetext={percent === null ? `${detail} · amount unknown` : `${Math.round(percent)}% · ${detail}`}
        className="ui-progress__track"
        data-unknown={percent === null ? "true" : undefined}
        role="progressbar"
      >
        <span className="ui-progress__fill" style={{ width: percent === null ? "0%" : `${percent}%` }} />
      </div>
      <span className="ui-progress__detail">{detail}</span>
    </div>
  );
}
