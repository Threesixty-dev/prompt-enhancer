import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

const checker = path.join(import.meta.dirname, "check-agent-bundle-budget.mjs");
const deferred = ["AgentArtifactsPanel", "AgentChangeSetPanel", "AgentControllerPanel", "AgentMcpProjectToolsPanel", "AgentMcpStorePanel", "AgentNativeAcceptancePanel", "AgentReadinessPanel", "AgentWorkspacePane", "TeamFoldersPanel", "AgentPdfPreview"];
const budget = { shell: 1_180_000, agentIncremental: 575_000, initialAgent: 1_750_000 };

function fixture() {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "agent-budget-"));
  const realDirectory = fs.realpathSync(directory);
  return {
    directory,
    dispose() {
      assert.equal(fs.realpathSync(directory), realDirectory);
      assert.equal(path.basename(realDirectory).startsWith("agent-budget-"), true);
      assert.equal(path.dirname(realDirectory), fs.realpathSync(os.tmpdir()));
      fs.rmSync(directory, { force: true, recursive: true });
      assert.equal(fs.existsSync(directory), false);
    },
  };
}
function graph({ agentName = "src/features/agent/AgentPage.tsx", agentFile = "assets/AgentPage-a.js", staticBoundary, malformedEdge } = {}) {
  const entries = {
    "app/index.html": { file: "assets/index.js", imports: ["shell.js"] },
    "shell.js": { file: "assets/shell.js", css: ["assets/shared.css"] },
    [agentName]: { file: agentFile, imports: ["agent-shared.js"], dynamicImports: deferred.map((label) => `src/features/agent/${label}.tsx`) },
    "agent-shared.js": { file: "assets/agent-shared.js", imports: [agentName], css: ["assets/shared.css", "assets/agent.css"] },
  };
  for (const label of deferred) entries[`src/features/agent/${label}.tsx`] = { file: `assets/${label}.js`, imports: ["shell.js"], css: [`assets/${label}.css`] };
  if (staticBoundary) entries[agentName].imports.push(`src/features/agent/${staticBoundary}.tsx`);
  if (malformedEdge) entries[agentName].imports = "agent-shared.js";
  return entries;
}
function filesFor(entries) {
  const files = new Set();
  for (const entry of Object.values(entries)) {
    if (!entry || typeof entry !== "object") continue;
    if (typeof entry.file === "string") files.add(entry.file);
    for (const file of entry.css ?? []) files.add(file);
    for (const file of entry.assets ?? []) files.add(file);
  }
  return Object.fromEntries([...files].map((file, index) => [file, index + 3]));
}
function run(entries, { files = filesFor(entries), limit = budget } = {}) {
  const owned = fixture();
  try {
    const dist = path.join(owned.directory, "dist");
    fs.mkdirSync(path.join(dist, ".vite"), { recursive: true });
    for (const [name, bytes] of Object.entries(files)) {
      const target = path.join(dist, name);
      fs.mkdirSync(path.dirname(target), { recursive: true });
      fs.writeFileSync(target, Buffer.alloc(bytes));
    }
    const manifest = path.join(dist, ".vite", "manifest.json");
    const budgetFile = path.join(owned.directory, "budget.json");
    fs.writeFileSync(manifest, JSON.stringify(entries));
    fs.writeFileSync(budgetFile, JSON.stringify(limit));
    return execFileSync(process.execPath, [checker, manifest, budgetFile], { cwd: owned.directory, encoding: "utf8", windowsHide: true });
  } finally {
    owned.dispose();
  }
}

test("measures renamed Agent entry with a static cycle and shared CSS exactly once", () => {
  const entries = graph({ agentName: "src/features/agent/agent-entry.tsx", agentFile: "assets/AgentPage-hash.js" });
  const report = JSON.parse(run(entries));
  assert.equal(report.deferredEntries.length, deferred.length);
  assert.equal(report.shell.css, 5);
  assert.equal(report.agentIncremental.files.includes("assets/shared.css"), false);
  assert.equal(report.initialAgent.files.filter((file) => file === "assets/shared.css").length, 1);
});

test("fails closed for missing generated assets", () => {
  const entries = graph(); const files = filesFor(entries); delete files["assets/AgentPdfPreview.css"];
  assert.throws(() => run(entries, { files }), /E_MISSING/);
});

test("rejects every mandatory deferred boundary becoming static", () => {
  for (const label of deferred) assert.throws(() => run(graph({ staticBoundary: label })), /E_BOUNDARY/, label);
});

test("rejects missing mandatory boundaries and malformed graph edges", () => {
  const missing = graph(); delete missing["src/features/agent/TeamFoldersPanel.tsx"];
  missing["src/features/agent/AgentPage.tsx"].dynamicImports = missing["src/features/agent/AgentPage.tsx"].dynamicImports.filter((name) => !name.includes("TeamFoldersPanel"));
  assert.throws(() => run(missing), /E_BOUNDARY/);
  assert.throws(() => run(graph({ malformedEdge: true })), /E_INVALID/);
});

test("enforces budgets and rejects empty, array, and extra budget keys", () => {
  const entries = graph();
  assert.throws(() => run(entries, { limit: { shell: 1, agentIncremental: 1, initialAgent: 1 } }), /E_BUDGET/);
  assert.throws(() => run(entries, { limit: {} }), /E_BUDGET/);
  assert.throws(() => run(entries, { limit: [] }), /E_BUDGET/);
  assert.throws(() => run(entries, { limit: { ...budget, extra: 1 } }), /E_BUDGET/);
});

test("rejects asset path escape before reading outside the generated tree", () => {
  const entries = graph(); entries["shell.js"].css = ["../outside.css"];
  assert.throws(() => run(entries), /E_INVALID/);
});
