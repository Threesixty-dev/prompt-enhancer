/**
 * Bounded packaged Agent streaming browser probe.
 *
 * Scope: use the real packaged /agent UI with a harness-provided, already
 * running offline synthetic model. Create one retained chat, observe two
 * incremental replies, cancel one response, complete a later response, then
 * reload and reopen the saved chat. The probe does not start a model, exercise
 * native approvals, restart the server, or claim draft persistence.
 */

import { chromium } from "playwright";

const CONTRACT = "packaged-agent-streaming-probe.v1";
const OUTPUT_PREFIX = "PACKAGED_AGENT_STREAMING_PROBE=";
const PROJECT = "Synthetic packaged streaming project";
const FIRST_PROMPT = "Synthetic streaming acceptance.";
const CANCEL_PROMPT = "Synthetic cancellation acceptance.";
const RETAINED_PROMPT = "Synthetic retained-history acceptance.";
const SYNTHETIC_CHUNK = "Synthetic chunk. ";
const COMPLETE_REPLY = SYNTHETIC_CHUNK.repeat(3);
const STEP_CODES = new Set([
  "invalid_environment",
  "browser_launch_failed",
  "context_create_failed",
  "page_create_failed",
  "agent_page_unavailable",
  "project_create_ui_failed",
  "chat_create_ui_failed",
  "model_selection_failed",
  "composer_unavailable",
  "first_send_failed",
  "first_stream_increment_failed",
  "first_completion_failed",
  "cancellation_send_failed",
  "cancellation_stream_failed",
  "cancellation_stop_failed",
  "cancellation_settle_failed",
  "retained_send_failed",
  "retained_stream_failed",
  "retained_completion_failed",
  "reload_reopen_failed",
  "browser_cleanup_unconfirmed",
  "browser_probe_failed",
]);

const report = {
  contract: CONTRACT,
  passed: false,
  browser_started: false,
  agent_page_loaded: false,
  projects_created: 0,
  chats_created: 0,
  retained_chat_verified: false,
  model_alias_selected: false,
  message_send_requests: 0,
  stop_requests: 0,
  model_mutation_requests: 0,
  incremental_turns_verified: 0,
  incremental_deltas_verified: 0,
  completed_turns_verified: 0,
  completed_chunks_verified: 0,
  cancellations_verified: 0,
  composer_ready_after_turns: 0,
  reloads: 0,
  catalog_reopens: 0,
  retained_user_messages_verified: 0,
  retained_assistant_messages_verified: 0,
  draft_persistence_claimed: false,
  server_restart_claimed: false,
  external_requests: 0,
  page_errors: 0,
  server_failures: 0,
  browser_closed: false,
  exception_kind: null,
  error_code: null,
};

let browser;
let phase = "invalid_environment";

function fail(code) {
  const error = new Error(code);
  error.probeCode = code;
  throw error;
}

function requireCondition(condition, code) {
  if (!condition) fail(code);
}

async function requireVisible(locator, code, timeout = 5_000) {
  try {
    await locator.waitFor({ state: "visible", timeout });
  } catch {
    fail(code);
  }
}

async function requireHidden(locator, code, timeout = 10_000) {
  try {
    await locator.waitFor({ state: "hidden", timeout });
  } catch {
    fail(code);
  }
}

async function requireEnabled(locator, code, timeout = 10_000) {
  await requireVisible(locator, code, timeout);
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (await locator.isEnabled()) return;
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  fail(code);
}

async function requireDisabled(locator, code, timeout = 10_000) {
  await requireVisible(locator, code, timeout);
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (!(await locator.isEnabled())) return;
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  fail(code);
}

async function selectProject(page, name, code) {
  const rail = page.getByRole("navigation", {
    name: "Agent projects and chats",
    exact: true,
  });
  const project = rail.locator(".agent-rail__project-pick").filter({ hasText: name });
  await requireVisible(project, code);
  await project.click();
}

async function selectChat(page, title, code) {
  const rail = page.getByRole("navigation", {
    name: "Agent projects and chats",
    exact: true,
  });
  const chat = rail.locator(".agent-rail__session-pick").filter({ hasText: title });
  await requireVisible(chat, code);
  await chat.click();
}

function safeChatTitle(workspace) {
  const parts = workspace.split(/[\\/]/u).filter(Boolean);
  const title = parts.at(-1) ?? "";
  if (!title || title.length > 120) fail("invalid_environment");
  return title;
}

function classifyException(error) {
  if (!error || typeof error !== "object") return "unknown";
  const name = typeof error.constructor?.name === "string" ? error.constructor.name : "";
  const message = typeof error.message === "string" ? error.message : "";
  if (
    name === "TargetClosedError"
    || /Target page, context or browser has been closed/iu.test(message)
    || /Browser has been closed/iu.test(message)
  ) return "target_closed";
  if (name === "TimeoutError" || /^Timeout \d+ms exceeded/iu.test(message)) return "timeout";
  if (
    name === "Error"
    || name === "PlaywrightException"
    || /^(?:browser|browserType|browserContext|page)\.(?:launch|newContext|newPage|goto):/u.test(message)
  ) return "playwright_error";
  return "unknown";
}

async function waitForIncrementalDeltas(page, code) {
  const live = page.getByLabel("Agent response streaming", { exact: true });
  await requireVisible(live, code, 12_000);
  const lengths = new Set();
  const deadline = Date.now() + 12_000;
  while (Date.now() < deadline) {
    const count = await live.count();
    if (count === 0) break;
    const content = await live.last().locator(".agent-markdown").textContent();
    const length = typeof content === "string" ? content.length : 0;
    if (length > 0 && length <= 100_000) lengths.add(length);
    if (lengths.size >= 2) return 2;
    await page.waitForTimeout(25);
  }
  fail(code);
}

async function waitForCompletedReply(page, ordinal, code) {
  const complete = page.locator('[data-stream-status="complete"]').filter({ hasText: "Synthetic chunk." });
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    if ((await complete.count()) >= ordinal) {
      const content = await complete.nth(ordinal - 1).locator(".agent-markdown").textContent();
      const normalized = content ?? "";
      if (normalized === COMPLETE_REPLY || normalized.trimEnd() === COMPLETE_REPLY.trimEnd()) return;
    }
    await page.waitForTimeout(50);
  }
  fail(code);
}

async function sendDraft(page, text, code) {
  const composer = page.getByRole("form", { name: "Message composer", exact: true });
  const input = composer.getByRole("textbox", { name: "Message to the agent", exact: true });
  await requireEnabled(input, code);
  await input.fill(text);
  requireCondition((await input.inputValue()) === text, code);
  const send = composer.getByRole("button", { name: "Send", exact: true });
  await requireEnabled(send, code);
  await send.click();
}

async function requireComposerReady(composer, input, code) {
  await requireHidden(composer.getByRole("button", { name: "Stop response", exact: true }), code);
  await requireHidden(composer.getByRole("button", { name: "Stopping…", exact: true }), code);
  await requireEnabled(input, code);
  await requireDisabled(composer.getByRole("button", { name: "Send", exact: true }), code);
}

try {
  const rawBase = process.env.PE_PACKAGED_BASE_URL ?? "";
  const workspace = process.env.PE_PACKAGED_WORKSPACE ?? "";
  const executablePath = process.env.PE_PACKAGED_BROWSER_EXECUTABLE ?? "";
  const modelAlias = process.env.PE_PACKAGED_MODEL_ALIAS ?? "";
  let parsedBase;
  try {
    parsedBase = new URL(rawBase);
  } catch {
    fail("invalid_environment");
  }
  requireCondition(
    parsedBase.protocol === "http:"
      && parsedBase.hostname === "127.0.0.1"
      && parsedBase.port !== ""
      && !["8765", "8766"].includes(parsedBase.port)
      && parsedBase.username === ""
      && parsedBase.password === ""
      && parsedBase.pathname === "/"
      && parsedBase.search === ""
      && parsedBase.hash === ""
      && workspace.length > 0
      && workspace.length <= 1024
      && executablePath.length > 0
      && modelAlias.length > 0
      && modelAlias.length <= 80
      && /^[a-z0-9][a-z0-9._-]*$/u.test(modelAlias),
    "invalid_environment",
  );
  const baseOrigin = parsedBase.origin;
  const chatTitle = safeChatTitle(workspace);

  phase = "browser_launch_failed";
  browser = await chromium.launch({ executablePath, headless: true });
  report.browser_started = true;

  phase = "context_create_failed";
  const context = await browser.newContext({
    baseURL: baseOrigin,
    viewport: { width: 1280, height: 800 },
    serviceWorkers: "block",
  });
  context.setDefaultTimeout(5_000);
  context.setDefaultNavigationTimeout(10_000);
  await context.route("**/*", async (route) => {
    let allowed = false;
    try {
      allowed = new URL(route.request().url()).origin === baseOrigin;
    } catch {
      allowed = false;
    }
    if (!allowed) {
      report.external_requests += 1;
      await route.abort("blockedbyclient");
      return;
    }
    await route.continue();
  });

  phase = "page_create_failed";
  const page = await context.newPage();
  page.on("pageerror", () => { report.page_errors += 1; });
  page.on("response", (response) => {
    try {
      if (new URL(response.url()).origin === baseOrigin && response.status() >= 500) {
        report.server_failures += 1;
      }
    } catch {
      // URL details are intentionally neither retained nor reported.
    }
  });
  page.on("request", (request) => {
    let path = "";
    try {
      path = new URL(request.url()).pathname;
    } catch {
      return;
    }
    if (request.method() === "POST" && /\/v1\/agent\/sessions\/[^/]+\/messages$/u.test(path)) {
      report.message_send_requests += 1;
    }
    if (request.method() === "POST" && /\/v1\/agent\/sessions\/[^/]+\/stop$/u.test(path)) {
      report.stop_requests += 1;
    }
    if (
      !["GET", "HEAD", "OPTIONS"].includes(request.method())
      && /^\/v1\/local-models(?:\/|$)/u.test(path)
    ) {
      report.model_mutation_requests += 1;
    }
  });

  phase = "agent_page_unavailable";
  const navigation = await page.goto(`${baseOrigin}/agent`, { waitUntil: "domcontentloaded" });
  requireCondition(navigation?.status() === 200, phase);
  const rail = page.getByRole("navigation", {
    name: "Agent projects and chats",
    exact: true,
  });
  await requireVisible(rail, phase);
  report.agent_page_loaded = true;

  phase = "project_create_ui_failed";
  await rail.getByRole("button", { name: "Create project", exact: true }).click();
  const createProject = page.getByRole("dialog", { name: "Create project", exact: true });
  await requireVisible(createProject, phase);
  await createProject.getByLabel("Project name", { exact: true }).fill(PROJECT);
  const projectResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "POST"
      && url.origin === baseOrigin
      && url.pathname === "/v1/agent/projects";
  });
  await createProject.getByRole("button", { name: "Save", exact: true }).click();
  requireCondition((await projectResponse).status() === 201, phase);
  await requireVisible(rail.getByText(PROJECT, { exact: true }), phase);
  report.projects_created = 1;

  phase = "chat_create_ui_failed";
  await selectProject(page, PROJECT, phase);
  await rail.getByRole("button", { name: "New chat", exact: true }).click();
  const setup = page.getByRole("dialog", { name: "New session", exact: true });
  await requireVisible(setup, phase);
  const modelSelect = setup.getByLabel("Agent model", { exact: true });
  await requireVisible(modelSelect, phase);
  phase = "model_selection_failed";
  try {
    await modelSelect.selectOption(modelAlias);
  } catch {
    fail(phase);
  }
  requireCondition((await modelSelect.inputValue()) === modelAlias, phase);
  report.model_alias_selected = true;

  phase = "chat_create_ui_failed";
  await setup.getByLabel("Workspace folder", { exact: true }).fill(workspace);
  const retain = setup.getByRole("radio", { name: /^Save locally/u });
  requireCondition(await retain.isChecked(), phase);
  const protectedActions = setup.getByRole("group", { name: "Protected actions", exact: true });
  requireCondition((await protectedActions.getAttribute("disabled")) !== null, phase);
  const openChat = setup.getByRole("button", { name: "Open read-only chat", exact: true });
  await requireEnabled(openChat, phase);
  const chatResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "POST"
      && url.origin === baseOrigin
      && url.pathname === "/v1/agent/sessions";
  });
  await openChat.click();
  requireCondition((await chatResponse).status() === 201, phase);
  await requireVisible(page.getByRole("heading", { level: 1, name: chatTitle }), phase);
  report.chats_created = 1;
  report.retained_chat_verified = true;

  phase = "composer_unavailable";
  const composer = page.getByRole("form", { name: "Message composer", exact: true });
  const input = composer.getByRole("textbox", { name: "Message to the agent", exact: true });
  await requireEnabled(input, phase);
  await requireDisabled(composer.getByRole("button", { name: "Send", exact: true }), phase);

  phase = "first_send_failed";
  await sendDraft(page, FIRST_PROMPT, phase);
  phase = "first_stream_increment_failed";
  report.incremental_deltas_verified += await waitForIncrementalDeltas(page, phase);
  report.incremental_turns_verified += 1;
  phase = "first_completion_failed";
  await waitForCompletedReply(page, 1, phase);
  await requireComposerReady(composer, input, phase);
  report.completed_turns_verified += 1;
  report.completed_chunks_verified += 3;
  report.composer_ready_after_turns += 1;

  phase = "cancellation_send_failed";
  await sendDraft(page, CANCEL_PROMPT, phase);
  phase = "cancellation_stream_failed";
  report.incremental_deltas_verified += await waitForIncrementalDeltas(page, phase);
  report.incremental_turns_verified += 1;
  phase = "cancellation_stop_failed";
  const stop = composer.getByRole("button", { name: "Stop response", exact: true });
  await requireEnabled(stop, phase);
  await stop.click();
  phase = "cancellation_settle_failed";
  await requireVisible(page.locator('[data-stream-status="stopped"]').last(), phase, 15_000);
  await requireComposerReady(composer, input, phase);
  report.cancellations_verified = 1;
  report.composer_ready_after_turns += 1;

  phase = "retained_send_failed";
  await sendDraft(page, RETAINED_PROMPT, phase);
  phase = "retained_stream_failed";
  await requireVisible(page.getByLabel("Agent response streaming", { exact: true }), phase, 12_000);
  phase = "retained_completion_failed";
  await waitForCompletedReply(page, 2, phase);
  await requireComposerReady(composer, input, phase);
  report.completed_turns_verified += 1;
  report.completed_chunks_verified += 3;
  report.composer_ready_after_turns += 1;

  phase = "reload_reopen_failed";
  await page.reload({ waitUntil: "domcontentloaded" });
  report.reloads = 1;
  await requireVisible(rail, phase);
  await selectProject(page, PROJECT, phase);
  await selectChat(page, chatTitle, phase);
  await requireVisible(page.getByRole("heading", { level: 1, name: chatTitle }), phase);
  await requireVisible(page.getByText(FIRST_PROMPT, { exact: true }), phase, 10_000);
  report.retained_user_messages_verified += 1;
  await requireVisible(page.getByText(RETAINED_PROMPT, { exact: true }), phase, 10_000);
  report.retained_user_messages_verified += 1;
  const retainedReplies = page.locator('[data-stream-status="complete"]').filter({ hasText: "Synthetic chunk." });
  requireCondition((await retainedReplies.count()) === 2, phase);
  for (let index = 0; index < 2; index += 1) {
    const content = await retainedReplies.nth(index).locator(".agent-markdown").textContent();
    const normalized = content ?? "";
    requireCondition(
      normalized === COMPLETE_REPLY || normalized.trimEnd() === COMPLETE_REPLY.trimEnd(),
      phase,
    );
    report.retained_assistant_messages_verified += 1;
  }
  await requireEnabled(page.getByRole("textbox", { name: "Message to the agent", exact: true }), phase);
  report.catalog_reopens = 1;

  requireCondition(report.message_send_requests === 3, "browser_probe_failed");
  requireCondition(report.stop_requests === 1, "browser_probe_failed");
  requireCondition(report.model_mutation_requests === 0, "browser_probe_failed");
  requireCondition(report.external_requests === 0, "browser_probe_failed");
  requireCondition(report.page_errors === 0, "browser_probe_failed");
  requireCondition(report.server_failures === 0, "browser_probe_failed");
} catch (error) {
  const expectedFailure = error && typeof error === "object" && "probeCode" in error;
  const candidate = expectedFailure ? error.probeCode : phase;
  report.exception_kind = expectedFailure ? null : classifyException(error);
  report.error_code = STEP_CODES.has(candidate) ? candidate : "browser_probe_failed";
} finally {
  if (browser) {
    try {
      await browser.close();
      report.browser_closed = true;
    } catch {
      report.browser_closed = false;
    }
  }
  if (report.error_code === null && !report.browser_closed) {
    report.error_code = "browser_cleanup_unconfirmed";
  }
}

report.passed = report.error_code === null
  && report.exception_kind === null
  && report.browser_started
  && report.agent_page_loaded
  && report.projects_created === 1
  && report.chats_created === 1
  && report.retained_chat_verified
  && report.model_alias_selected
  && report.message_send_requests === 3
  && report.stop_requests === 1
  && report.model_mutation_requests === 0
  && report.incremental_turns_verified === 2
  && report.incremental_deltas_verified === 4
  && report.completed_turns_verified === 2
  && report.completed_chunks_verified === 6
  && report.cancellations_verified === 1
  && report.composer_ready_after_turns === 3
  && report.reloads === 1
  && report.catalog_reopens === 1
  && report.retained_user_messages_verified === 2
  && report.retained_assistant_messages_verified === 2
  && report.draft_persistence_claimed === false
  && report.server_restart_claimed === false
  && report.external_requests === 0
  && report.page_errors === 0
  && report.server_failures === 0
  && report.browser_closed;

process.stdout.write(`${OUTPUT_PREFIX}${JSON.stringify(report)}\n`);
process.exitCode = report.passed ? 0 : 1;
