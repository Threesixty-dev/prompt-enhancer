import { useEffect, useState } from "react";
import type {
  ModelPredictiveMetricDetail,
  PromptEnhancerTransport,
} from "../../shared/api/contracts";
import type { ModelEnsembleRadarAxis } from "./metricAxisModel";

export type PredictiveMetricDetailState = "idle" | "loading" | "failed";

export interface PredictiveMetricDetailResult {
  detail: ModelPredictiveMetricDetail | null;
  state: PredictiveMetricDetailState;
}

/**
 * Loads the content-free factor distribution for the selected axis, and only
 * when an informative experimental estimate is actually visible for it: a
 * withheld or absent estimate never triggers a request. Responses are admitted
 * only for the requested metric key; a superseded request is aborted and its
 * abort is not reported as a failure.
 */
export function usePredictiveMetricDetail({
  transport,
  runId,
  axis,
}: {
  transport?: Pick<PromptEnhancerTransport, "getModelPredictiveMetricDetail">;
  runId?: string;
  axis: ModelEnsembleRadarAxis | undefined;
}): PredictiveMetricDetailResult {
  const [detail, setDetail] = useState<ModelPredictiveMetricDetail | null>(null);
  const [state, setState] = useState<PredictiveMetricDetailState>("idle");
  const metricKey = axis?.key;
  const prediction = axis?.prediction;
  const predictiveMedian = axis?.predictiveMedian;
  useEffect(() => {
    const load = transport?.getModelPredictiveMetricDetail;
    if (
      load === undefined
      || runId === undefined
      || metricKey === undefined
      || prediction === null || prediction === undefined
      || predictiveMedian === null || predictiveMedian === undefined
    ) {
      setDetail(null);
      setState("idle");
      return undefined;
    }
    const controller = new AbortController();
    setDetail(null);
    setState("loading");
    void load(runId, metricKey, controller.signal)
      .then((loaded) => {
        if (loaded.metric.metric_key !== metricKey) throw new Error("predictive detail metric mismatch");
        setDetail(loaded);
        setState("idle");
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setDetail(null);
        setState("failed");
      });
    return () => controller.abort();
  }, [runId, transport, metricKey, prediction, predictiveMedian]);
  return { detail, state };
}
