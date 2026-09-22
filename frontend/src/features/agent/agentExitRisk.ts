export type AgentExitRisk = {
  hasUnsavedChanges: boolean;
  hasActiveWork: boolean;
};

export function agentExitRisk({
  hasDrafts,
  workspaceDirty,
  hasObservedWork,
}: {
  hasDrafts: boolean;
  workspaceDirty: boolean;
  hasObservedWork: boolean;
}): AgentExitRisk {
  return {
    hasUnsavedChanges: hasDrafts || workspaceDirty,
    hasActiveWork: hasObservedWork,
  };
}

export function sameAgentExitRisk(left: AgentExitRisk | null, right: AgentExitRisk): boolean {
  return left?.hasUnsavedChanges === right.hasUnsavedChanges
    && left?.hasActiveWork === right.hasActiveWork;
}
