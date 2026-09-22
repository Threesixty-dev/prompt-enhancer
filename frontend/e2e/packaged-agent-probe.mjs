/**
 * Bounded packaged Agent browser probe.
 *
 * Scope: render the real packaged /agent UI, create one fictional project and
 * one empty retained no-model chat, type (but never send) a fictional draft,
 * inspect the model chooser at three viewport sizes, clear the ephemeral draft,
 * reload, and reopen the catalog chat. This does not claim draft/message
 * persistence, model execution, native acceptance, or installer acceptance.
 */

import { chromium } from "playwright";

const CONTRACT = "packaged-agent-browser-probe.v1";
const PROJECT = "Synthetic packaged browser project";
const DRAFT = "Synthetic unsent packaged browser draft";
const STEP_CODES = new Set([
  "invalid_environment",
  "browser_launch_failed",
  "context_create_failed",
  "page_create_failed",
  "agent_page_unavailable",
  "project_create_ui_failed",
  "chat_create_ui_failed",
  "composer_unavailable",
  "model_dialog_failed",
  "model_selection_failed",
  "model_start_control_failed",
  "model_dialog_compact_failed",
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
  composer_drafts_typed: 0,
  draft_send_requests: 0,
  draft_cleared_before_reload: false,
  draft_persistence_claimed: false,
  model_dialog_viewports_verified: 0,
  model_start_requests: 0,
  compact_check: null,
  compact_dialog_bounds: null,
  compact_occluder: null,
  compact_hit_classes: null,
  compact_hit_tag: null,
  compact_hit_state: null,
  reloads: 0,
  catalog_reopens: 0,
  external_requests: 0,
  page_errors: 0,
  server_failures: 0,
  browser_closed: false,
  exception_kind: null,
  error_code: null,
};

let browser;
let phase = "invalid_environment";
let compactCheck = null;

function fail(code) {
  const error = new Error(code);
  error.probeCode = code;
  throw error;
}

function requireCondition(condition, code) {
  if (!condition) fail(code);
}

async function requireVisible(locator, code) {
  try {
    await locator.waitFor({ state: "visible" });
  } catch {
    fail(code);
  }
}

async function requireEnabled(locator, code) {
  await requireVisible(locator, code);
  if (!(await locator.isEnabled())) fail(code);
}

async function requireDisabled(locator, code) {
  await requireVisible(locator, code);
  if (await locator.isEnabled()) fail(code);
}

async function requireInViewport(locator, code) {
  await requireVisible(locator, code);
  const inside = await locator.evaluate((element) => {
    const box = element.getBoundingClientRect();
    return box.width > 0
      && box.height > 0
      && box.left >= 0
      && box.top >= 0
      && box.right <= window.innerWidth
      && box.bottom <= window.innerHeight;
  });
  if (!inside) fail(code);
}

async function requireHitTestable(locator, code) {
  await requireVisible(locator, code);
  const result = await locator.evaluate((element) => {
    const box = element.getBoundingClientRect();
    const bounds = {
      x: box.x,
      y: box.y,
      width: box.width,
      height: box.height,
      viewport_width: window.innerWidth,
      viewport_height: window.innerHeight,
    };
    const target = box.width > 0 && box.height > 0
      ? document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2)
      : null;
    const allowedClasses = new Set([
      "agent", "agent__compose", "agent__compose-footer", "agent__head", "agent__layout",
      "agent__layout--session", "agent__layout--window", "agent__main", "agent__workbench",
      "agent-runtime", "agent-runtime--composer",
      "agent-runtime__composer-actions", "agent-runtime__composer-close",
      "agent-runtime__composer-disclosure", "agent-runtime__composer-panel",
      "agent-runtime__composer-panel-actions", "agent-runtime__composer-panel-head",
      "agent-runtime__head", "app-shell", "app-shell--agent-focus", "brand", "brand__mark",
      "button", "button--ghost", "mobile-runtime-marker", "mobile-runtime-marker__icon",
      "mobile-shell-header", "mobile-shell-header__actions", "mobile-shell-header__identity",
      "mobile-shell-header__menu", "primary-nav", "sidebar", "topbar", "ui-dialog",
      "ui-dialog__panel", "ui-dialog__scrim", "workspace",
    ]);
    const allowedTags = new Set([
      "aside", "body", "button", "details", "div", "header", "html", "label", "main",
      "nav", "option", "p", "path", "section", "select", "small", "span", "strong",
      "summary", "svg",
    ]);
    const hitClasses = [];
    for (let node = target; node instanceof Element && hitClasses.length < 8; node = node.parentElement) {
      for (const className of node.classList) {
        if (allowedClasses.has(className) && !hitClasses.includes(className)) {
          hitClasses.push(className);
          if (hitClasses.length === 8) break;
        }
      }
    }
    const hitTagName = target?.tagName.toLowerCase() ?? "none";
    const hitTag = allowedTags.has(hitTagName) ? hitTagName : hitTagName === "none" ? "none" : "other";
    const pointerEvents = (node) => {
      if (!(node instanceof Element)) return "unavailable";
      const value = getComputedStyle(node).pointerEvents;
      return value === "auto" || value === "none" ? value : "other";
    };
    const visibility = (node) => {
      if (!(node instanceof Element)) return "unavailable";
      const value = getComputedStyle(node).visibility;
      return value === "visible" || value === "hidden" || value === "collapse" ? value : "other";
    };
    const position = (node) => {
      if (!(node instanceof Element)) return "unavailable";
      const value = getComputedStyle(node).position;
      return ["static", "relative", "absolute", "fixed", "sticky"].includes(value) ? value : "other";
    };
    const numericZIndex = (node) => {
      if (!(node instanceof Element)) return null;
      const value = getComputedStyle(node).zIndex;
      if (value === "auto") return null;
      const numeric = Number(value);
      return Number.isFinite(numeric) && Math.abs(numeric) <= 10_000 ? numeric : null;
    };
    let hitAncestorZIndex = null;
    for (let node = target; node instanceof Element; node = node.parentElement) {
      hitAncestorZIndex = numericZIndex(node);
      if (hitAncestorZIndex !== null) break;
    }
    const panel = element.closest(".agent-runtime__composer-panel");
    const hitState = {
      target_pointer_events: pointerEvents(target),
      control_pointer_events: pointerEvents(element),
      panel_pointer_events: pointerEvents(panel),
      target_visibility: visibility(target),
      control_visibility: visibility(element),
      panel_visibility: visibility(panel),
      target_position: position(target),
      hit_ancestor_z_index: hitAncestorZIndex,
      panel_z_index: numericZIndex(panel),
    };
    const diagnostic = { bounds, hitClasses, hitTag, hitState };
    if (box.width <= 0 || box.height <= 0) {
      return { hit: false, occluder: "other_outside", ...diagnostic };
    }
    if (target === element || (target !== null && element.contains(target))) {
      return { hit: true, occluder: null, ...diagnostic };
    }
    if (target?.closest(".agent-runtime__composer-panel-head")) {
      return { hit: false, occluder: "header", ...diagnostic };
    }
    if (target?.closest(".agent-runtime__composer-actions")) {
      return { hit: false, occluder: "actions", ...diagnostic };
    }
    if (target !== null && panel?.contains(target)) {
      return { hit: false, occluder: "panel", ...diagnostic };
    }
    if (target?.closest(".topbar")) {
      return { hit: false, occluder: "topbar", ...diagnostic };
    }
    if (target?.closest(".sidebar, .primary-nav")) {
      return { hit: false, occluder: "sidebar", ...diagnostic };
    }
    if (target?.closest(".agent__head")) {
      return { hit: false, occluder: "agent_header", ...diagnostic };
    }
    if (target === document.body || target === document.documentElement) {
      return { hit: false, occluder: "body", ...diagnostic };
    }
    return { hit: false, occluder: "other_outside", ...diagnostic };
  });
  if (!result.hit) {
    if (
      Object.values(result.bounds).some(
        (value) => typeof value !== "number" || !Number.isFinite(value) || Math.abs(value) > 100_000,
      )
    ) fail(code);
    report.compact_dialog_bounds = result.bounds;
    report.compact_occluder = result.occluder;
    report.compact_hit_classes = result.hitClasses;
    report.compact_hit_tag = result.hitTag;
    report.compact_hit_state = result.hitState;
    fail(code);
  }
}

async function compactBounds(locator, code) {
  await requireVisible(locator, code);
  const bounds = await locator.evaluate((element) => {
    const box = element.getBoundingClientRect();
    return {
      x: box.x,
      y: box.y,
      width: box.width,
      height: box.height,
      viewport_width: window.innerWidth,
      viewport_height: window.innerHeight,
    };
  });
  if (
    Object.values(bounds).some(
      (value) => typeof value !== "number" || !Number.isFinite(value) || Math.abs(value) > 100_000,
    )
  ) fail(code);
  return bounds;
}

function boundsAreInViewport(bounds) {
  return bounds.width > 0
    && bounds.height > 0
    && bounds.x >= 0
    && bounds.y >= 0
    && bounds.x + bounds.width <= bounds.viewport_width
    && bounds.y + bounds.height <= bounds.viewport_height;
}

async function requireCompactBounds(locator, code) {
  const bounds = await compactBounds(locator, code);
  if (!boundsAreInViewport(bounds)) {
    report.compact_dialog_bounds = bounds;
    fail(code);
  }
  return bounds;
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
  if (name === "TimeoutError" || /^Timeout \d+ms exceeded/iu.test(message)) {
    return "timeout";
  }
  if (
    name === "Error"
    || name === "PlaywrightException"
    || /^(?:browser|browserType|browserContext|page)\.(?:launch|newContext|newPage|goto):/u.test(message)
  ) return "playwright_error";
  return "unknown";
}

try {
  const rawBase = process.env.PE_PACKAGED_BASE_URL ?? "";
  const workspace = process.env.PE_PACKAGED_WORKSPACE ?? "";
  const executablePath = process.env.PE_PACKAGED_BROWSER_EXECUTABLE ?? "";
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
      && parsedBase.username === ""
      && parsedBase.password === ""
      && parsedBase.pathname === "/"
      && parsedBase.search === ""
      && parsedBase.hash === ""
      && workspace.length > 0
      && workspace.length <= 1024
      && executablePath.length > 0,
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
      report.draft_send_requests += 1;
    }
    if (
      !["GET", "HEAD", "OPTIONS"].includes(request.method())
      && /^\/v1\/local-models(?:\/|$)/u.test(path)
    ) {
      report.model_start_requests += 1;
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
  requireCondition((await modelSelect.inputValue()) === "", phase);
  await setup.getByLabel("Workspace folder", { exact: true }).fill(workspace);
  const retain = setup.getByRole("radio", { name: /^Save locally/u });
  requireCondition(await retain.isChecked(), phase);
  const protectedActions = setup.getByRole("group", {
    name: "Protected actions",
    exact: true,
  });
  requireCondition((await protectedActions.getAttribute("disabled")) !== null, phase);
  const openChat = setup.getByRole("button", {
    name: "Open read-only chat without model",
    exact: true,
  });
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
  await requireVisible(
    page.getByRole("region", { name: "Agent conversation", exact: true })
      .getByText("Session created without a model", { exact: false }),
    phase,
  );
  report.chats_created = 1;
  report.retained_chat_verified = true;

  phase = "composer_unavailable";
  const composer = page.getByRole("form", { name: "Message composer", exact: true });
  const draft = composer.getByRole("textbox", {
    name: "Message to the agent",
    exact: true,
  });
  await requireEnabled(draft, phase);
  await requireDisabled(composer.getByRole("button", { name: "Send", exact: true }), phase);
  await draft.fill(DRAFT);
  requireCondition((await draft.inputValue()) === DRAFT, phase);
  await requireDisabled(composer.getByRole("button", { name: "Send", exact: true }), phase);
  report.composer_drafts_typed = 1;

  phase = "model_dialog_failed";
  await composer.getByLabel(/Model and context settings|Choose or start model/u).click();
  const modelDialog = composer.getByRole("dialog", {
    name: "Choose model and runtime settings",
    exact: true,
  });
  await requireInViewport(modelDialog, phase);
  report.model_dialog_viewports_verified = 1;

  phase = "model_selection_failed";
  requireCondition(
    (await modelDialog.getByLabel("Model", { exact: true }).inputValue()) === "",
    phase,
  );

  phase = "model_start_control_failed";
  const startModel = modelDialog.getByRole("button", { name: "Start model", exact: true });
  await requireDisabled(
    startModel,
    phase,
  );

  phase = "model_dialog_compact_failed";
  compactCheck = "panel_720_bounds";
  await page.setViewportSize({ width: 720, height: 720 });
  await page.evaluate(() => new Promise((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(resolve));
  }));
  await requireCompactBounds(modelDialog, phase);
  const closeModelDialog = modelDialog.getByRole("button", {
    name: "Close model and context settings",
    exact: true,
  });
  const compactModelSelect = modelDialog.getByLabel("Model", { exact: true });
  compactCheck = "model_720_bounds";
  await compactModelSelect.scrollIntoViewIfNeeded();
  await requireCompactBounds(compactModelSelect, phase);
  compactCheck = "start_720_bounds";
  await startModel.scrollIntoViewIfNeeded();
  await requireCompactBounds(startModel, phase);
  compactCheck = "close_720_bounds";
  await closeModelDialog.scrollIntoViewIfNeeded();
  await requireCompactBounds(closeModelDialog, phase);
  compactCheck = "model_720_hit";
  await compactModelSelect.scrollIntoViewIfNeeded();
  await requireHitTestable(compactModelSelect, phase);
  compactCheck = "close_720_hit";
  await closeModelDialog.scrollIntoViewIfNeeded();
  await requireHitTestable(closeModelDialog, phase);
  compactCheck = "panel_scrolled_bounds";
  await page.evaluate(() => {
    window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "auto" });
  });
  await page.evaluate(() => new Promise((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(resolve));
  }));
  await requireCompactBounds(modelDialog, phase);
  compactCheck = "close_scrolled_bounds";
  await closeModelDialog.scrollIntoViewIfNeeded();
  await requireCompactBounds(closeModelDialog, phase);
  compactCheck = "close_scrolled_hit";
  await requireHitTestable(closeModelDialog, phase);
  report.model_dialog_viewports_verified = 2;

  compactCheck = "panel_480_bounds";
  await page.setViewportSize({ width: 480, height: 640 });
  await page.evaluate(() => new Promise((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(resolve));
  }));
  await requireCompactBounds(modelDialog, phase);
  compactCheck = "model_480_bounds";
  await compactModelSelect.scrollIntoViewIfNeeded();
  await requireCompactBounds(compactModelSelect, phase);
  compactCheck = "start_480_bounds";
  await startModel.scrollIntoViewIfNeeded();
  await requireCompactBounds(startModel, phase);
  compactCheck = "close_480_bounds";
  await closeModelDialog.scrollIntoViewIfNeeded();
  await requireCompactBounds(closeModelDialog, phase);
  compactCheck = "model_480_hit";
  await compactModelSelect.scrollIntoViewIfNeeded();
  await requireHitTestable(compactModelSelect, phase);
  compactCheck = "close_480_hit";
  await closeModelDialog.scrollIntoViewIfNeeded();
  await requireHitTestable(closeModelDialog, phase);
  report.model_dialog_viewports_verified = 3;
  compactCheck = null;
  await closeModelDialog.click();
  await page.setViewportSize({ width: 1280, height: 800 });
  await draft.fill("");
  requireCondition((await draft.inputValue()) === "", "composer_unavailable");
  report.draft_cleared_before_reload = true;

  phase = "reload_reopen_failed";
  await page.reload({ waitUntil: "domcontentloaded" });
  report.reloads = 1;
  await requireVisible(rail, phase);
  await selectProject(page, PROJECT, phase);
  await selectChat(page, chatTitle, phase);
  await requireVisible(page.getByRole("heading", { level: 1, name: chatTitle }), phase);
  const reopenedDraft = page.getByRole("textbox", {
    name: "Message to the agent",
    exact: true,
  });
  await requireEnabled(reopenedDraft, phase);
  requireCondition((await reopenedDraft.inputValue()) === "", phase);
  report.catalog_reopens = 1;

  requireCondition(report.external_requests === 0, "browser_probe_failed");
  requireCondition(report.page_errors === 0, "browser_probe_failed");
  requireCondition(report.server_failures === 0, "browser_probe_failed");
  requireCondition(report.draft_send_requests === 0, "browser_probe_failed");
  requireCondition(report.model_start_requests === 0, "browser_probe_failed");
} catch (error) {
  const expectedFailure = error && typeof error === "object" && "probeCode" in error;
  const candidate = expectedFailure ? error.probeCode : phase;
  report.exception_kind = expectedFailure ? null : classifyException(error);
  report.error_code = STEP_CODES.has(candidate) ? candidate : "browser_probe_failed";
  report.compact_check = candidate === "model_dialog_compact_failed"
    ? compactCheck
    : null;
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
  && report.composer_drafts_typed === 1
  && report.draft_send_requests === 0
  && report.draft_cleared_before_reload
  && report.draft_persistence_claimed === false
  && report.model_dialog_viewports_verified === 3
  && report.model_start_requests === 0
  && report.compact_check === null
  && report.compact_dialog_bounds === null
  && report.compact_occluder === null
  && report.compact_hit_classes === null
  && report.compact_hit_tag === null
  && report.compact_hit_state === null
  && report.reloads === 1
  && report.catalog_reopens === 1
  && report.external_requests === 0
  && report.page_errors === 0
  && report.server_failures === 0
  && report.browser_closed;

process.stdout.write(
  `PACKAGED_AGENT_BROWSER_PROBE=${JSON.stringify(report)}\n`,
);
process.exitCode = report.passed ? 0 : 1;
