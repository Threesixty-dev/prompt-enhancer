import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  MetricOperabilityCatalog,
  MetricOperabilityEntry,
  PromptEnhancerTransport,
} from "../../shared/api/contracts";
import {
  MetricOperabilityDefinitionsOutOfDateError,
  MetricOperabilityPayloadError,
} from "../../shared/api/metricOperabilityContract";
import { TransportError } from "../../shared/api/httpTransport";
import "./MetricOperabilityPanel.css";

type CatalogState =
  | { kind: "loading" }
  | { kind: "ready"; catalog: MetricOperabilityCatalog; owner: PromptEnhancerTransport }
  | { kind: "refreshing"; catalog: MetricOperabilityCatalog; owner: PromptEnhancerTransport }
  | { kind: "transient_failed_load"; catalog?: MetricOperabilityCatalog; owner?: PromptEnhancerTransport }
  | { kind: "definitions_out_of_date"; owner: PromptEnhancerTransport }
  | { kind: "unavailable"; reason: "endpoint_absent" | "invalid_payload"; owner: PromptEnhancerTransport };

type ShippedState = MetricOperabilityEntry["shipped_path_state"];

const GROUPS: ReadonlyArray<{
  state: ShippedState;
  title: string;
  explanation: string;
}> = [
  {
    state: "available_when_evidence_exists",
    title: "Measured path shipped",
    explanation: "These metrics resolve when the analyzed window contains the required reviewed evidence.",
  },
  {
    state: "task_profile_configuration_required",
    title: "Project profile needed",
    explanation: "Declare the expected constraints, outcomes and deliverables before these denominators exist.",
  },
  {
    state: "provider_adapter_required",
    title: "Unavailable pending provider adapter",
    explanation: "These contracts remain in their exact receipt but cannot produce a current value: the provider must expose typed opportunities, links or outcomes. Model prose cannot substitute for them.",
  },
];

const NEXT_STEP_LABELS: Record<MetricOperabilityEntry["next_step_code"], string> = {
  analyze_focus_request: "Analyze the focus request",
  declare_task_profile: "Review and declare the project task profile",
  confirm_lifecycle_evidence: "Review the lifecycle evidence proposal",
  record_documented_decision: "Record an explicit documented decision or strategy",
  link_plan_supersession: "Link the plan item to the action that superseded it",
  record_task_scoped_verification: "Attach a task-scoped verification receipt",
  add_objective_opportunity_link_adapter: "Add typed opportunity, link and outcome capture",
  add_requirement_plan_extractor: "Add a reviewed requirement-to-plan extractor",
  confirm_requirement_plan_evidence: "Confirm reviewed requirement-to-plan evidence",
  compose_requirement_action_evidence: "Compose and confirm reviewed requirement-to-action evidence",
  issue_reviewed_observed_check: "Issue a reviewed observed check, then run fresh analysis",
};

function metricLabel(metricKey: string): string {
  const leaf = metricKey.split(".").at(-1) ?? metricKey;
  const label = leaf.replaceAll("_", " ");
  return label.charAt(0).toUpperCase() + label.slice(1);
}

function evidenceScope(metricKey: string): string | undefined {
  if (metricKey === "logic.requirement_action_traceability") {
    return "Requires a complete compatible Claude transcript, a confirmed requirement plan, and reviewed requirement-action links with native confirmation. Hook-only and incomplete histories are not admitted; traceability is not proof of task success.";
  }
  if (metricKey === "outcome.verified_requirement_coverage") {
    return "Conditional path: a complete compatible Codex source, native-reviewed plan, and observed check must exist before a fresh analysis can measure coverage. A provider-reported check is not a human coverage acknowledgment.";
  }
  return undefined;
}

function StateGroup({
  entries,
  explanation,
  title,
}: {
  entries: readonly MetricOperabilityEntry[];
  explanation: string;
  title: string;
}) {
  return (
    <section className="metric-operability__group">
      <header>
        <span aria-hidden="true">{entries.length}</span>
        <div>
          <h3>{title}</h3>
          <p>{explanation}</p>
        </div>
      </header>
      <ul>
        {entries.map((entry) => (
          <li data-operability-state={entry.shipped_path_state} key={entry.metric_key}>
            <div>
              <strong>{metricLabel(entry.metric_key)}</strong>
              <code>{entry.metric_key}</code>
            </div>
            <p>{NEXT_STEP_LABELS[entry.next_step_code]}</p>
            <span>
              {entry.experimental_model_path
                ? "Separate experimental estimate may be available"
                : "No model estimate is used"}
            </span>
            {evidenceScope(entry.metric_key) && <small>{evidenceScope(entry.metric_key)}</small>}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function MetricOperabilityPanel({ transport }: { transport: PromptEnhancerTransport }) {
  const [state, setState] = useState<CatalogState>({ kind: "loading" });
  const requestRef = useRef(0);
  const controllerRef = useRef<AbortController | undefined>(undefined);
  const inFlightRef = useRef(false);
  const mountedRef = useRef(true);

  const requestCatalog = useCallback((mode: "initial" | "refresh") => {
    const load = transport.getMetricOperabilityCatalog;
    if (!load) {
      setState({ kind: "unavailable", reason: "endpoint_absent", owner: transport });
      return;
    }
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    if (controllerRef.current) controllerRef.current.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    const requestId = ++requestRef.current;
    setState((current) => {
      if (mode === "refresh" && (current.kind === "ready" || current.kind === "refreshing" || current.kind === "transient_failed_load") && current.catalog) {
        return { kind: "refreshing", catalog: current.catalog, owner: transport };
      }
      return { kind: "loading" };
    });
    let result: Promise<MetricOperabilityCatalog>;
    try {
      result = load(controller.signal);
    } catch (error) {
      result = Promise.reject(error);
    }
    void Promise.resolve(result)
      .then((catalog) => {
        if (mountedRef.current && requestRef.current === requestId && !controller.signal.aborted) {
          inFlightRef.current = false;
          setState({ kind: "ready", catalog, owner: transport });
        }
      })
      .catch((error: unknown) => {
        if (!mountedRef.current || requestRef.current !== requestId || controller.signal.aborted) return;
        inFlightRef.current = false;
        if (error instanceof MetricOperabilityDefinitionsOutOfDateError) {
          setState({ kind: "definitions_out_of_date", owner: transport });
        } else if (error instanceof MetricOperabilityPayloadError || (error instanceof TransportError && error.status === 200)) {
          setState({ kind: "unavailable", reason: "invalid_payload", owner: transport });
        } else {
          setState((current) => ({
            kind: "transient_failed_load",
            catalog: current.kind === "ready" || current.kind === "refreshing" || current.kind === "transient_failed_load" ? current.catalog : undefined,
            owner: transport,
          }));
        }
      });
  }, [transport]);

  useEffect(() => {
    mountedRef.current = true;
    requestCatalog("initial");
    return () => {
      mountedRef.current = false;
      inFlightRef.current = false;
      requestRef.current += 1;
      controllerRef.current?.abort();
    };
  }, [requestCatalog]);

  const owned = (state.kind === "ready" || state.kind === "refreshing" || state.kind === "transient_failed_load") && state.owner === transport;
  const boundaryOwned = (state.kind === "definitions_out_of_date" || state.kind === "unavailable") && state.owner === transport;
  const grouped = useMemo(() => {
    const catalog = state.kind === "ready" || state.kind === "refreshing" || state.kind === "transient_failed_load"
      ? state.catalog
      : undefined;
    if (!catalog || !owned) return [];
    return GROUPS.map((group) => ({
      ...group,
      entries: catalog.entries.filter(
        (entry) => entry.shipped_path_state === group.state,
      ),
    })).filter((group) => group.entries.length > 0);
  }, [owned, state]);

  if (state.kind === "loading" || (!owned && !boundaryOwned)) {
    return (
      <section className="metric-operability metric-operability--state" role="status">
        Checking all twenty measurement paths…
      </section>
    );
  }
  if (state.kind === "definitions_out_of_date" && boundaryOwned) {
    return (
      <section className="metric-operability metric-operability--state" role="alert">
        <strong>Metric definitions are newer than this app</strong>
        <span>Update Prompt Enhancer before using this operability map. No session was read.</span>
      </section>
    );
  }
  if (state.kind === "unavailable" && boundaryOwned) {
    return (
      <section className="metric-operability metric-operability--state" role="alert">
        <strong>Metric operability is unavailable</strong>
        <span>{state.reason === "endpoint_absent" ? "The metric map endpoint is unavailable." : "The metric map response was invalid."} No session was read; no model was called.</span>
      </section>
    );
  }

  if (state.kind === "transient_failed_load" && !state.catalog) {
    return (
      <section className="metric-operability metric-operability--state" role="alert">
        <strong>Metric operability could not be loaded</strong>
        <span>This may be temporary. No session or model was read.</span>
        <button type="button" onClick={() => requestCatalog("initial")}>Retry</button>
      </section>
    );
  }

  const catalog = owned && (state.kind === "ready" || state.kind === "refreshing" || state.kind === "transient_failed_load") ? state.catalog : undefined;
  if (!catalog) return null;
  return (
    <section className="metric-operability" aria-labelledby="metric-operability-title">
      {state.kind === "refreshing" && <p className="metric-operability__notice" role="status">Checking for an updated metric map. Showing the last validated map.</p>}
      {state.kind === "transient_failed_load" && <div className="metric-operability__notice" role="alert"><span>Refresh failed; showing the last validated metric map.</span><button type="button" onClick={() => requestCatalog("refresh")}>Retry</button></div>}
      <header className="metric-operability__intro">
        <div>
          <p className="eyebrow">All-20 release gate · {catalog.catalog_version}</p>
          <h2 id="metric-operability-title">What can produce measured evidence today</h2>
          <p>
            Every contract stays visible. {catalog.shipped_path_count} have a current measurement
            path; {catalog.provider_adapter_gap_count} are explicitly unavailable pending a
            provider adapter. A shipped path can still be Unknown, Pending or Not applicable when
            its evidence is absent; missing evidence is never converted to zero.
          </p>
        </div>
        <aside>
          <strong>Models never author measured values</strong>
          <span>
            Experimental estimates remain a separate, uncalibrated lane even when a larger local judge is active.
          </span>
        </aside>
      </header>

      <dl className="metric-operability__summary" aria-label="Metric operability summary">
        <div><dt>Measured paths shipped</dt><dd>{catalog.shipped_path_count}</dd></div>
        <div><dt>Need project profile</dt><dd>{catalog.task_profile_configuration_gap_count}</dd></div>
        <div><dt>Need source adapter</dt><dd>{catalog.provider_adapter_gap_count}</dd></div>
        <div><dt>Model-authored metrics</dt><dd>{catalog.model_authoritative_metric_count}</dd></div>
      </dl>

      <div className="metric-operability__groups">
        {grouped.map((group) => (
          <StateGroup
            entries={group.entries}
            explanation={group.explanation}
            key={group.state}
            title={group.title}
          />
        ))}
      </div>

      <footer>
        <span>{catalog.total_metric_count}/20 contracts bound to the current client</span>
        <span>{catalog.experimental_model_path_count} have a separate experimental model path</span>
      </footer>
      {state.kind === "ready" && <button className="metric-operability__refresh" type="button" onClick={() => requestCatalog("refresh")}>Refresh metric map</button>}
    </section>
  );
}
