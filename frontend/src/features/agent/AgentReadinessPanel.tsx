import {
  AGENT_LEGACY_PARITY,
  AGENT_PARITY_SUMMARY,
  AGENT_REQUESTED_CAPABILITIES,
  type AgentParityItem,
  type AgentRequestedCapability,
} from "./agentReleaseParity";

import "./AgentReadinessPanel.css";

type RequestedCapabilityState = Readonly<{
  automated: boolean;
  implementation: AgentParityItem["implementation"];
  ownerGate: AgentParityItem["ownerGate"];
}>;

function requestedCapabilityState(capability: AgentRequestedCapability): RequestedCapabilityState {
  const items = capability.parityKeys.map((key) => AGENT_LEGACY_PARITY.find((item) => item.key === key));
  if (items.some((item) => item === undefined)) {
    return { automated: false, implementation: "missing", ownerGate: "blocked" };
  }
  const evidence = items as AgentParityItem[];
  const implementation = evidence.some((item) => item.implementation === "missing")
    ? "missing"
    : evidence.some((item) => item.implementation === "partial")
      ? "partial"
      : "complete";
  const ownerGate = evidence.some((item) => item.ownerGate === "blocked")
    ? "blocked"
    : evidence.some((item) => item.ownerGate === "pending")
      ? "pending"
      : "not_required";
  return {
    automated: evidence.every((item) => item.automatedEvidence),
    implementation,
    ownerGate,
  };
}

function stateLabel(state: RequestedCapabilityState): string {
  if (state.implementation === "missing") return "Missing";
  if (state.implementation === "partial") return "Partial";
  if (!state.automated) return "Tests missing";
  if (state.ownerGate === "blocked") return "Platform blocked";
  if (state.ownerGate === "pending") return "Implemented · owner check pending";
  return "Implemented · automated evidence passed";
}

export function AgentReadinessPanel({
  onOpenConnections,
  onOpenOwnerChecks,
}: {
  onOpenConnections: () => void;
  onOpenOwnerChecks: () => void;
}) {
  return (
    <section aria-labelledby="agent-readiness-title" className="agent-readiness">
      <header>
        <span>
          <small>Current implementation snapshot</small>
          <h3 id="agent-readiness-title">Agent capability readiness</h3>
        </span>
        <span className="agent-readiness__state" data-state={AGENT_PARITY_SUMMARY.missing === 0 ? "implemented" : "incomplete"}>
          {AGENT_PARITY_SUMMARY.complete}/{AGENT_PARITY_SUMMARY.total} implemented
        </span>
      </header>

      <p className="agent-readiness__truth">
        This is implementation and synthetic-test evidence—not a claim that a real model, native confirmation,
        microphone, separate window, or GPU cleanup was exercised on this machine today.
      </p>

      <dl aria-label="Agent readiness summary" className="agent-readiness__facts">
        <div><dt>Implemented</dt><dd>{AGENT_PARITY_SUMMARY.complete}/{AGENT_PARITY_SUMMARY.total}</dd></div>
        <div><dt>Missing</dt><dd>{AGENT_PARITY_SUMMARY.missing}</dd></div>
        <div><dt>Platform blockers</dt><dd>{AGENT_PARITY_SUMMARY.platformBlocked}</dd></div>
        <div><dt>Owner checks</dt><dd>{AGENT_PARITY_SUMMARY.ownerPending} pending</dd></div>
      </dl>

      <div className="agent-readiness__section-head">
        <span>
          <small>Reconciled checklist</small>
          <strong>Requested Codex/Claude-style capabilities</strong>
        </span>
        <small>Automated and owner evidence stay separate.</small>
      </div>
      <ul aria-label="Requested Agent capabilities" className="agent-readiness__capabilities">
        {AGENT_REQUESTED_CAPABILITIES.map((capability) => {
          const state = requestedCapabilityState(capability);
          return (
            <li
              data-automated={state.automated ? "true" : "false"}
              data-implementation={state.implementation}
              data-owner-gate={state.ownerGate}
              key={capability.key}
            >
              <span>{capability.label}</span>
              <strong>{stateLabel(state)}</strong>
            </li>
          );
        })}
      </ul>

      <div className="agent-readiness__notes">
        <p>
          <strong>External orchestration:</strong> the loopback controller and MCP workflow are implemented and
          contract-tested. Creating a real one-time connection remains an explicit native-confirmed action in
          Connections; Prompt Enhancer never edits Codex or Claude configuration itself.
        </p>
        <p>
          <strong>Projects:</strong> the left rail contains editable Agent projects and chats. The application’s
          separate global Projects and Sessions pages remain read-only analytics catalogues for imported provider data.
        </p>
      </div>

      <div className="agent-readiness__actions">
        <button className="button button--ghost" onClick={onOpenConnections} type="button">Open connections</button>
        <button className="button button--primary" onClick={onOpenOwnerChecks} type="button">Open owner checks</button>
      </div>
    </section>
  );
}
