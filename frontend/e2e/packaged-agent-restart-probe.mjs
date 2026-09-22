/** Real restarted packaged UI; no model activation, messages, or protected effects. */
import { chromium } from "playwright";

const report = {
  contract: "packaged-agent-restart-probe.v1", passed: false,
  browser_started: false, browser_closed: false, history_verified: false,
  resumed_readonly: false, draft_cleared: false, reopened_verified: false,
  user_messages: 0, complete_replies: 0, stopped_replies: 0,
  resume_requests: 0, forbidden_mutations: 0, external_requests: 0,
  page_errors: 0, server_failures: 0, auth_responses: 0, error_code: null,
};
const users = ["Synthetic streaming acceptance.", "Synthetic cancellation acceptance.", "Synthetic retained-history acceptance."];
const reply = "Synthetic chunk. Synthetic chunk. Synthetic chunk.";
let browser;
let phase = "invalid_environment";
function requireValue(value) { if (!value) throw new Error("synthetic-check-failed"); }
async function visible(locator) { await locator.waitFor({ state: "visible", timeout: 10000 }); }
async function history(page) {
  for (const text of users) {
    const locator = page.locator(".agent__turn--user").getByText(text, { exact: true });
    await visible(locator);
    requireValue(await locator.count() === 1);
  }
  requireValue(await page.locator(".agent__turn--user").count() === 3);
  const complete = page.locator('.agent__turn--assistant[data-stream-status="complete"]');
  requireValue(await complete.count() === 2);
  for (let index = 0; index < 2; index++) {
    requireValue((await complete.nth(index).locator(".agent-markdown").textContent())?.trim() === reply);
  }
  requireValue(await page.locator('.agent__turn--assistant[data-stream-status="stopped"]').count() === 1);
  requireValue(await page.locator(".agent__turn--assistant").count() === 3);
}
try {
  const base = new URL(process.env.PE_PACKAGED_BASE_URL ?? "");
  const executablePath = process.env.PE_PACKAGED_BROWSER_EXECUTABLE ?? "";
  requireValue(base.protocol === "http:" && base.hostname === "127.0.0.1" && base.port
    && !["8765", "8766"].includes(base.port) && !base.username && !base.password
    && base.pathname === "/" && !base.search && !base.hash && executablePath);
  phase = "browser_launch_failed";
  browser = await chromium.launch({ executablePath, headless: true });
  report.browser_started = true;
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, serviceWorkers: "block" });
  context.setDefaultTimeout(10000);
  await context.route("**/*", async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== base.origin) {
      report.external_requests++;
      return route.abort("blockedbyclient");
    }
    if (!["GET", "HEAD", "OPTIONS"].includes(request.method())) {
      if (request.method() === "POST" && /^\/v1\/agent\/projects\/[0-9a-f]{32}\/sessions\/[0-9a-f]{32}\/resume$/u.test(url.pathname)) {
        let revisions;
        try { revisions = request.postDataJSON(); } catch { revisions = null; }
        if (!revisions || Object.keys(revisions).length !== 2
          || ![revisions.expected_catalog_revision, revisions.expected_history_revision].every(value => Number.isSafeInteger(value) && value > 0)) {
          report.forbidden_mutations++;
          return route.abort("blockedbyclient");
        }
        report.resume_requests++;
        if (report.resume_requests > 1) return route.abort("blockedbyclient");
      } else {
        report.forbidden_mutations++;
        return route.abort("blockedbyclient");
      }
    }
    return route.continue();
  });
  const page = await context.newPage();
  page.on("pageerror", () => { report.page_errors++; });
  page.on("response", response => {
    const url = new URL(response.url());
    if (url.origin === base.origin && response.status() >= 500) report.server_failures++;
    if (url.origin === base.origin && url.pathname === "/auth/session" && response.status() === 200) report.auth_responses++;
  });
  phase = "catalog_open_failed";
  requireValue((await page.goto(`${base.origin}/agent`, { waitUntil: "domcontentloaded", timeout: 15000 }))?.status() === 200);
  const rail = page.getByRole("navigation", { name: "Agent projects and chats", exact: true });
  await visible(rail);
  await rail.locator(".agent-rail__project-pick").filter({ hasText: "Synthetic packaged streaming project" }).click();
  const chat = rail.locator(".agent-rail__session-pick").filter({ hasText: "example-workspace" });
  await visible(chat);
  await chat.click();
  phase = "retained_history_failed";
  await history(page);
  report.history_verified = true;
  report.user_messages = 3; report.complete_replies = 2; report.stopped_replies = 1;
  phase = "resume_ui_failed";
  const resume = page.getByRole("button", { name: "Resume chat", exact: true });
  await visible(resume);
  requireValue(await resume.isEnabled());
  await resume.click();
  const recovery = page.getByRole("heading", { name: "Revalidate this workspace before changing it", exact: true });
  await visible(recovery);
  const native = page.getByRole("button", { name: "Native confirmation required", exact: true });
  requireValue(!(await native.isEnabled()));
  for (const label of ["File writes", "Commands"]) {
    const control = page.getByRole("checkbox", { name: label, exact: true });
    requireValue(!(await control.isChecked()) && !(await control.isEnabled()));
  }
  const web = page.getByRole("checkbox", { name: "Web fetch stays off until explicitly enabled with a fresh native confirmation", exact: true });
  requireValue(!(await web.isChecked()) && !(await web.isEnabled()));
  report.resumed_readonly = true;
  phase = "composer_guard_failed";
  const composer = page.getByRole("form", { name: "Message composer", exact: true });
  const input = composer.getByRole("textbox", { name: "Message to the agent", exact: true });
  await visible(input);
  requireValue(await input.isEnabled());
  await input.fill("Synthetic unsent restart draft.");
  requireValue(await input.inputValue() === "Synthetic unsent restart draft.");
  requireValue(!(await composer.getByRole("button", { name: "Send", exact: true }).isEnabled()));
  await input.fill("");
  requireValue(await input.inputValue() === "");
  report.draft_cleared = true;
  phase = "reopen_failed";
  await page.reload({ waitUntil: "domcontentloaded" });
  await visible(rail);
  await rail.locator(".agent-rail__project-pick").filter({ hasText: "Synthetic packaged streaming project" }).click();
  await chat.click();
  await history(page);
  await visible(recovery);
  report.reopened_verified = true;
} catch {
  report.error_code = phase;
} finally {
  if (browser) {
    try { await browser.close(); report.browser_closed = true; }
    catch { report.error_code ??= "browser_cleanup_failed"; }
  }
}
report.passed = report.error_code === null && report.browser_started && report.browser_closed
  && report.history_verified && report.resumed_readonly && report.draft_cleared && report.reopened_verified
  && report.resume_requests === 1 && report.auth_responses >= 1
  && [report.forbidden_mutations, report.external_requests, report.page_errors, report.server_failures].every(value => value === 0);
if (!report.passed && report.error_code === null) report.error_code = "request_boundary_failed";
process.stdout.write(`PACKAGED_AGENT_RESTART_PROBE=${JSON.stringify(report)}\n`);
process.exitCode = report.passed ? 0 : 1;
