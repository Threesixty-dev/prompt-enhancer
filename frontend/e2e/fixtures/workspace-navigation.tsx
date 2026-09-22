import { useState } from "react";
import { createRoot } from "react-dom/client";
import type { PromptEnhancerTransport } from "../../src/shared/api/contracts";
import {
  parseAgentWorkspaceFile,
  parseAgentWorkspaceTree,
} from "../../src/shared/api/agentWorkspaceContract";
import { parseAgentWorkspaceDiscovery } from "../../src/shared/api/agentWorkspaceDiscoveryContract";
import { parseAgentWorkspaceSearchResult } from "../../src/shared/api/agentWorkspaceSearchContract";
import { AgentWorkspacePane } from "../../src/features/agent/AgentWorkspacePane";
import { Dialog } from "../../src/shared/ui/Dialog";
import "../../src/features/agent/AgentPage.css";
import "../../src/styles.css";
import "../../src/app/theme.css";
import "../../src/app/palette.generated.css";

const SESSION_ID = "a".repeat(32);
const NAVIGATION_PATH = "navigation.ts";
const NOTES_PATH = "notes.txt";
const TARGET_LINE = 1000;
const FAR_RIGHT_MATCH = "SYNTHETIC_FAR_RIGHT_MATCH";
const LOCAL_MATCH = "SYNTHETIC_LOCAL_MATCH";

const navigationContent = Array.from({ length: 1100 }, (_, index) => {
  const line = index + 1;
  if (line === 20 || line === 80) return `const marker${line} = "${LOCAL_MATCH}";`;
  if (line === TARGET_LINE) return `${" ".repeat(480)}${FAR_RIGHT_MATCH}`;
  if (line === TARGET_LINE + 1) return "const afterLongLine = true;";
  return `const syntheticLine${line} = ${line};`;
}).join("\n") + "\n";

const notesContent = "Synthetic second file.\n";

function increment(name: "discoveryReads" | "fileReads" | "searchReads" | "writeAttempts") {
  document.documentElement.dataset[name] = String(Number(document.documentElement.dataset[name] ?? "0") + 1);
}

const transport = {
  async getAgentWorkspaceTree(sessionId: string, path: string) {
    if (path !== ".") throw new Error("synthetic fixture only exposes the selected root");
    return parseAgentWorkspaceTree({
      contract_version: "local-agent-workspace.v1" as const,
      session_id: sessionId,
      path: ".",
      complete: true,
      entries: [
        { path: NAVIGATION_PATH, name: "navigation.ts", kind: "file" as const, byte_size: navigationContent.length, editable_candidate: true },
        { path: NOTES_PATH, name: "notes.txt", kind: "file" as const, byte_size: notesContent.length, editable_candidate: true },
      ],
    }, sessionId, path);
  },
  async getAgentWorkspaceDiscovery(sessionId: string) {
    increment("discoveryReads");
    return parseAgentWorkspaceDiscovery({
      contract_version: "local-agent-workspace-discovery.v1" as const,
      session_id: sessionId,
      scope: "selected_workspace" as const,
      inventory_coverage: "complete" as const,
      inventory_reasons: [],
      scanned_entry_count: 2,
      observed_file_count: 2,
      files: [
        { path: NAVIGATION_PATH, byte_size: navigationContent.length, editable_candidate: true },
        { path: NOTES_PATH, byte_size: notesContent.length, editable_candidate: true },
      ],
      git_state: "not_repository" as const,
      git_coverage: "not_applicable" as const,
      git_reasons: [],
      git_change_count: 0,
      git_changes: [],
    }, sessionId);
  },
  async getAgentWorkspaceSearch(sessionId: string) {
    increment("searchReads");
    return parseAgentWorkspaceSearchResult({
      contract_version: "local-agent-workspace-search.v1" as const,
      session_id: sessionId,
      scope: "application_readable_utf8_text" as const,
      coverage: "complete" as const,
      reasons: [],
      reason_code: null,
      scanned_entry_count: 2,
      inspected_byte_count: navigationContent.length + notesContent.length,
      skipped_entry_count: 0,
      match_count: 1,
      matches: [{ path: NAVIGATION_PATH, line_number: TARGET_LINE, preview: FAR_RIGHT_MATCH }],
    }, sessionId);
  },
  async getAgentWorkspaceFile(sessionId: string, path: string) {
    increment("fileReads");
    const content = path === NAVIGATION_PATH ? navigationContent : path === NOTES_PATH ? notesContent : null;
    if (content === null) throw new Error("synthetic fixture path is unavailable");
    return parseAgentWorkspaceFile({
      contract_version: "local-agent-workspace.v1" as const,
      session_id: sessionId,
      path,
      content,
      revision: path === NAVIGATION_PATH ? "b".repeat(64) : "c".repeat(64),
      byte_size: content.length,
      line_ending: "lf" as const,
      editable: true,
    }, sessionId, path);
  },
  async previewAgentWorkspaceEdit() {
    increment("writeAttempts");
    throw new Error("synthetic navigation fixture has no write authority");
  },
  async applyAgentWorkspaceEdit() {
    increment("writeAttempts");
    throw new Error("synthetic navigation fixture has no write authority");
  },
} satisfies Pick<PromptEnhancerTransport,
  | "getAgentWorkspaceTree"
  | "getAgentWorkspaceDiscovery"
  | "getAgentWorkspaceSearch"
  | "getAgentWorkspaceFile"
  | "previewAgentWorkspaceEdit"
  | "applyAgentWorkspaceEdit"
>;

function WorkspaceNavigationFixture() {
  const dialogMode = new URLSearchParams(window.location.search).get("mode") === "dialog";
  const [dialogOpen, setDialogOpen] = useState(dialogMode);
  const pane = <AgentWorkspacePane pendingWrite={null} sessionId={SESSION_ID} transport={transport} />;

  return (
    <main>
      <p className="eyebrow">Synthetic demo · in-memory files only; no native, write, network, or model action</p>
      {dialogMode ? (
        <>
          <button onClick={() => setDialogOpen(true)} type="button">Open workspace dialog</button>
          <Dialog onClose={() => setDialogOpen(false)} open={dialogOpen} title="Synthetic workspace dialog">
            {pane}
          </Dialog>
        </>
      ) : pane}
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<WorkspaceNavigationFixture />);
