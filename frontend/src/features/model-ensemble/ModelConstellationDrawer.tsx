import { useEffect, useState } from "react";
import type {
  ModelEnsembleAttemptStage,
  ModelEnsembleRun,
} from "../../shared/api/contracts";
import { moveRovingFocus } from "../../shared/ui/rovingFocus";
import {
  MODEL_ENSEMBLE_STAGE_GROUPS,
  formatStageResource,
  modelEnsembleStageSummaryLabel,
  modelEnsembleStagesFor,
  shortIdentity,
} from "./modelStages";

/**
 * Model-stage provenance drawer: grouped stage nodes with a roving-focus row and
 * an `aria-live` inspector for the selected stage. Stage rows and grouping come
 * from `modelStages`; this component only renders them and never invents case
 * counts for receipts that do not expose them.
 */
export function ModelConstellationDrawer({ run, attemptStages, compact }: {
  run: ModelEnsembleRun | null;
  attemptStages: readonly ModelEnsembleAttemptStage[];
  compact: boolean;
}) {
  const stageSet = modelEnsembleStagesFor(run, attemptStages);
  const { stages } = stageSet;
  const [selectedKey, setSelectedKey] = useState(stages[0]?.modelKey ?? "");
  const selected = stages.find((stage) => stage.modelKey === selectedKey) ?? stages[0];
  useEffect(() => {
    if (stages.length > 0 && !stages.some((stage) => stage.modelKey === selectedKey)) {
      setSelectedKey(stages[0].modelKey);
    }
  }, [selectedKey, stages]);
  return (
    <details className="metric-workspace__drawer model-constellation">
      <summary>
        <span>Models</span>
        <small>{modelEnsembleStageSummaryLabel(stageSet)}</small>
      </summary>
      <div className="model-constellation__body">
        {stages.length === 0 && <p>Model stage details are not exposed for this sealed receipt.</p>}
        {MODEL_ENSEMBLE_STAGE_GROUPS.map((group) => {
          const groupStages = stages.filter((stage) => stage.group === group);
          if (groupStages.length === 0) return null;
          return (
            <section key={group}>
              <strong>{group}</strong>
              <div
                className="model-constellation__nodes"
                onKeyDown={(event) => moveRovingFocus(event)}
              >
                {groupStages.map((stage) => (
                  <button
                    aria-label={`${stage.repositoryId} · ${stage.role} · ${stage.status.replaceAll("_", " ")}`}
                    aria-pressed={stage.modelKey === selected?.modelKey}
                    data-status={stage.status}
                    key={stage.modelKey}
                    onClick={() => setSelectedKey(stage.modelKey)}
                    title={`${stage.repositoryId} · ${stage.role}`}
                    type="button"
                  >
                    <i aria-hidden="true" />
                    <span>{stage.repositoryId.split("/").at(-1)}</span>
                    <small>{stage.status.replaceAll("_", " ")}</small>
                  </button>
                ))}
              </div>
            </section>
          );
        })}
        {selected !== undefined && (
          <aside aria-live="polite" className="model-constellation__inspector">
            <header><strong>{selected.repositoryId}</strong><span>{selected.role}</span></header>
            <dl>
              <div><dt>Status</dt><dd>{selected.status.replaceAll("_", " ")}</dd></div>
              <div><dt>Device</dt><dd>{selected.device?.toUpperCase() ?? "none"}</dd></div>
              <div><dt>Quantization</dt><dd>{selected.quantization.replaceAll("_", " ")}</dd></div>
              <div><dt>Latency</dt><dd>{selected.latency === null ? "not recorded" : `${selected.latency} ms`}</dd></div>
              {!compact && <div><dt>Peak VRAM</dt><dd>{formatStageResource(selected.acceleratorMemory)}</dd></div>}
              {!compact && <div><dt>Peak RAM</dt><dd>{formatStageResource(selected.rss)}</dd></div>}
              <div><dt>Released</dt><dd>{selected.unloaded ? "yes" : "not confirmed"}</dd></div>
              <div><dt>Revision</dt><dd>{shortIdentity(selected.revision)}</dd></div>
              <div><dt>Evaluated</dt><dd>{selected.evaluatedCases ?? "unavailable"}</dd></div>
              <div><dt>Contributed</dt><dd>{selected.contributedCases ?? "unavailable"}</dd></div>
            </dl>
            {selected.errorCode !== null && <p role="alert">{selected.errorCode.replaceAll("_", " ")}</p>}
            {(selected.evaluatedCases === null || selected.contributedCases === null) && <p>Case counts are unavailable for this stage receipt; they are not zero. Current v1 receipts identify the stage without trustworthy per-metric contribution counts.</p>}
          </aside>
        )}
      </div>
    </details>
  );
}
