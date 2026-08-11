import { formatPercent } from "../lib/format";

export function CoverageBar({
  coverage,
  observed,
  eligible,
  compact = false,
}: {
  coverage: number;
  observed: number;
  eligible: number;
  compact?: boolean;
}) {
  const boundedCoverage = Math.max(0, Math.min(1, coverage));
  const ariaPercent =
    boundedCoverage === 0
      ? 0
      : Number((boundedCoverage * 100).toPrecision(6));
  const label =
    eligible === 0
      ? "No eligible evidence"
      : `${observed} of ${eligible} observations (${formatPercent(boundedCoverage)})`;

  return (
    <div className={`coverage ${compact ? "coverage--compact" : ""}`}>
      <div className="coverage__label">
        <span>Coverage</span>
        <span>{eligible === 0 ? "Not observed" : formatPercent(boundedCoverage)}</span>
      </div>
      <div
        aria-label={label}
        aria-valuemax={100}
        aria-valuemin={0}
        aria-valuenow={ariaPercent}
        className="coverage__track"
        role="progressbar"
      >
        <span className="coverage__fill" style={{ width: `${boundedCoverage * 100}%` }} />
      </div>
      {!compact && <span className="coverage__caption">{label}</span>}
    </div>
  );
}
