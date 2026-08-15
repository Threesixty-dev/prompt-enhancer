import type { ModelEnsembleRun } from "../../shared/api/contracts";
import type { MetricCategory } from "../../shared/platform/platform";
import { QUALITY_ANALYSIS_DEFINITIONS } from "../quality-profile/qualityProfile";

export function ModelEnsembleRadar({
  run,
  category,
  compact = false,
}: {
  run: ModelEnsembleRun;
  category: MetricCategory;
  compact?: boolean;
}) {
  const kind = category === "prompt-quality" ? "prompt" : "logic";
  const metrics = new Map(run.metrics.map((metric) => [metric.metric_key, metric]));
  const axes = QUALITY_ANALYSIS_DEFINITIONS
    .filter((definition) => definition.kind === kind)
    .map((definition) => {
      const metric = metrics.get(definition.key);
      const raw = metric?.value_state === "known" && metric.numeric_value != null
        ? metric.numeric_value
        : null;
      return {
        definition,
        metric,
        plotted: raw == null ? null : definition.direction === "lower_is_better" ? 1 - raw : raw,
      };
    });
  const size = compact ? 300 : 360;
  const center = size / 2;
  const radius = compact ? 92 : 112;
  const point = (index: number, magnitude: number) => {
    const angle = -Math.PI / 2 + (Math.PI * 2 * index) / axes.length;
    return [
      center + Math.cos(angle) * radius * magnitude,
      center + Math.sin(angle) * radius * magnitude,
    ] as const;
  };
  const allKnown = axes.length >= 3 && axes.every((axis) => axis.plotted !== null);
  const polygon = allKnown
    ? axes.map((axis, index) => point(index, axis.plotted!).join(",")).join(" ")
    : null;
  return (
    <figure className={`model-ensemble__radar${compact ? " model-ensemble__radar--compact" : ""}`}>
      <svg aria-label="Direction-adjusted shadow model radar with fixed axes" role="img" viewBox={`0 0 ${size} ${size}`}>
        {[0.25, 0.5, 0.75, 1].map((level) => (
          <polygon
            className="model-ensemble__radar-ring"
            key={level}
            points={axes.map((_, index) => point(index, level).join(",")).join(" ")}
          />
        ))}
        {axes.map((axis, index) => {
          const end = point(index, 1);
          const label = point(index, compact ? 1.22 : 1.28);
          const value = axis.plotted === null ? null : point(index, axis.plotted);
          return (
            <g key={axis.definition.key}>
              <line className="model-ensemble__radar-axis" x1={center} x2={end[0]} y1={center} y2={end[1]} />
              <text className="model-ensemble__radar-label" textAnchor="middle" x={label[0]} y={label[1]}>
                {axis.definition.shortLabel}
              </text>
              {value !== null && <circle className="model-ensemble__radar-point" cx={value[0]} cy={value[1]} r="4" />}
            </g>
          );
        })}
        {polygon !== null && <polygon className="model-ensemble__radar-value" points={polygon} />}
      </svg>
      <figcaption>
        Axes stay fixed between updates. Unknown and unsupported values keep their
        spoke but are not placed at zero; dots show known values and a filled shape
        appears only when every axis in this lens is known.
      </figcaption>
    </figure>
  );
}
