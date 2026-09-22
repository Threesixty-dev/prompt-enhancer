#!/usr/bin/env node
/** Report and enforce the manifest-backed Agent bundle budget. */
import fs from "node:fs";
import path from "node:path";

const repositoryRoot = path.resolve(import.meta.dirname, "../..");
const reportOnly = process.argv.includes("--report-only");
const positional = process.argv.slice(2).filter((arg) => arg !== "--report-only");
const manifestPath = positional[0] ?? path.join(repositoryRoot, "src", "prompt_enhancer", "_resources", "dashboard", ".vite", "manifest.json");
const budgetPath = reportOnly ? undefined : (positional[1] ?? path.join(repositoryRoot, "frontend", "agent-bundle-budget.json"));
const REQUIRED_DEFERRED = ["AgentArtifactsPanel", "AgentChangeSetPanel", "AgentControllerPanel", "AgentMcpProjectToolsPanel", "AgentMcpStorePanel", "AgentNativeAcceptancePanel", "AgentReadinessPanel", "AgentWorkspacePane", "TeamFoldersPanel", "AgentPdfPreview"];
const BUDGET_KEYS = ["shell", "agentIncremental", "initialAgent"];

process.on("uncaughtException", (error) => {
  const message = String(error?.message ?? error);
  const code = message.includes("deferred") ? "E_BOUNDARY" : message.includes("missing") ? "E_MISSING" : message.includes("budget") ? "E_BUDGET" : "E_INVALID";
  // Keep failures content-free: generated paths and file names do not belong in logs.
  console.error(`[bundle-budget] ${code}`);
  process.exitCode = 1;
});

function fail(message) { throw new Error(message); }
function isPlainObject(value) { return value !== null && typeof value === "object" && !Array.isArray(value); }
function loadJson(file, kind) {
  if (!fs.existsSync(file)) fail(`missing ${kind}`);
  try { return JSON.parse(fs.readFileSync(file, "utf8")); } catch { fail(`invalid ${kind}`); }
}
function normalizeManifest(raw) {
  const entries = raw?.entries ?? raw;
  if (!isPlainObject(entries) || Object.values(entries).some((entry) => !isPlainObject(entry))) fail("invalid manifest entries");
  return entries;
}
function entryName(entries, predicate, label, boundary = false) {
  const names = Object.entries(entries).filter(([name, entry]) => predicate(name, entry)).map(([name]) => name);
  if (names.length !== 1) fail(boundary ? "deferred boundary is missing or ambiguous" : `${label} entry is missing or ambiguous`);
  return names[0];
}
function validateEdges(entry, name) {
  for (const field of ["imports", "dynamicImports", "css", "assets"]) {
    if (entry[field] !== undefined && !Array.isArray(entry[field])) fail("invalid manifest edge");
    if ((entry[field] ?? []).some((value) => typeof value !== "string" || value.length === 0)) fail(`invalid manifest edge from ${name}`);
  }
  if (typeof entry.file !== "string" || entry.file.length === 0) fail("invalid manifest asset");
}
function staticClosure(entries, start) {
  const seen = new Set(); const stack = [start];
  while (stack.length) {
    const name = stack.pop(); if (seen.has(name)) continue;
    const entry = entries[name]; if (!entry) fail("missing manifest dependency");
    validateEdges(entry, name); seen.add(name); stack.push(...(entry.imports ?? []));
  }
  return seen;
}
/** Traverse both kinds of edges and retain whether a dynamic edge was crossed. */
function dynamicReachability(entries, start) {
  const reached = new Map(); const stack = [[start, false]];
  while (stack.length) {
    const [name, crossedDynamic] = stack.pop(); const previous = reached.get(name);
    if (previous === true || previous === crossedDynamic) continue;
    const entry = entries[name]; if (!entry) fail("missing manifest dependency");
    validateEdges(entry, name); reached.set(name, crossedDynamic);
    for (const dependency of entry.imports ?? []) stack.push([dependency, crossedDynamic]);
    for (const dependency of entry.dynamicImports ?? []) stack.push([dependency, true]);
  }
  return reached;
}
function isInside(root, candidate) {
  const relative = path.relative(root, candidate);
  return relative !== "" && relative !== ".." && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative);
}
function assetPath(distRoot, realDistRoot, file) {
  if (typeof file !== "string" || file.length === 0 || path.isAbsolute(file) || file.includes("\\") || file.split("/").includes("..")) fail("invalid manifest asset path");
  const candidate = path.resolve(distRoot, file);
  if (!isInside(distRoot, candidate) || !fs.existsSync(candidate)) fail("missing manifest asset");
  let resolved; try { resolved = fs.realpathSync(candidate); } catch { fail("missing manifest asset"); }
  if (!isInside(realDistRoot, resolved)) fail("invalid manifest asset path");
  return resolved;
}
function assetFiles(entries, names, distRoot, realDistRoot) {
  const files = new Map();
  for (const name of names) {
    const entry = entries[name]; if (!entry) fail("missing manifest dependency"); validateEdges(entry, name);
    for (const file of [entry.file, ...(entry.css ?? []), ...(entry.assets ?? [])]) files.set(file, assetPath(distRoot, realDistRoot, file));
  }
  return files;
}
function totalsForFiles(files) {
  const totals = { bytes: 0, js: 0, css: 0, files: [...files.keys()].sort() };
  for (const [file, resolved] of files) {
    const stat = fs.statSync(resolved); if (!stat.isFile()) fail("invalid manifest asset");
    totals.bytes += stat.size;
    if (/\.css$/u.test(file)) totals.css += stat.size;
    else if (/\.(?:m?js)$/u.test(file)) totals.js += stat.size;
  }
  return totals;
}
function subtractFiles(files, excluded) { return new Map([...files].filter(([file]) => !excluded.has(file))); }
function mergeFiles(...groups) { return new Map(groups.flatMap((group) => [...group])); }
function validateBudget(raw) {
  if (!isPlainObject(raw)) fail("invalid budget");
  const keys = Object.keys(raw).sort(); const expected = [...BUDGET_KEYS].sort();
  if (keys.length !== expected.length || keys.some((key, index) => key !== expected[index])) fail("invalid budget keys");
  if (BUDGET_KEYS.some((key) => !Number.isSafeInteger(raw[key]) || raw[key] <= 0)) fail("invalid budget value");
  return raw;
}

const entries = normalizeManifest(loadJson(manifestPath, "manifest"));
const shell = entryName(entries, (name) => name === "index.html" || /(?:^|\/)index\.html$/u.test(name), "shell");
const agent = entryName(entries, (name, entry) => /(?:^|\/)AgentPage\.(?:tsx?|jsx?)$/u.test(name) || /(?:^|\/)AgentPage-[^/]+\.js$/u.test(entry.file), "AgentPage");
const distRoot = path.resolve(path.dirname(path.resolve(manifestPath)), "..");
if (!fs.existsSync(distRoot)) fail("missing build root");
const realDistRoot = fs.realpathSync(distRoot);
const shellStatic = staticClosure(entries, shell); const agentStatic = staticClosure(entries, agent);
const initialStatic = new Set([...shellStatic, ...agentStatic]);
const shellFiles = assetFiles(entries, shellStatic, distRoot, realDistRoot);
const agentFiles = assetFiles(entries, agentStatic, distRoot, realDistRoot);
const dynamic = dynamicReachability(entries, agent);
const deferred = REQUIRED_DEFERRED.map((label) => entryName(entries, (name) => name.includes(`/agent/${label}.`), label, true));
for (const name of deferred) {
  if (initialStatic.has(name)) fail("deferred boundary became static");
  if (dynamic.get(name) !== true) fail("deferred boundary is not dynamically reachable");
  assetFiles(entries, staticClosure(entries, name), distRoot, realDistRoot);
}
const report = {
  manifest: path.relative(repositoryRoot, manifestPath),
  shell: totalsForFiles(shellFiles),
  agentIncremental: totalsForFiles(subtractFiles(agentFiles, shellFiles)),
  initialAgent: totalsForFiles(mergeFiles(shellFiles, agentFiles)),
  deferredEntries: deferred.sort(),
  deferredTotals: Object.fromEntries(deferred.sort().map((name) => [name, totalsForFiles(subtractFiles(assetFiles(entries, staticClosure(entries, name), distRoot, realDistRoot), shellFiles))])),
};
if (budgetPath !== undefined) {
  const budget = validateBudget(loadJson(budgetPath, "budget"));
  for (const key of BUDGET_KEYS) if (report[key].bytes > budget[key]) fail("bundle budget exceeded");
}
console.log(JSON.stringify(report, null, 2));
