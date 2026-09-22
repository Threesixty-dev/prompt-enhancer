/**
 * Bounded packaged calibration browser probe.
 *
 * The server is pre-seeded through its public onboarding route with one
 * fictional, consented local-source session. This script reviews that session,
 * stores three human ratings, reloads, and verifies the saved UI state. It does
 * not start a model, test review expiry, or claim native/installer acceptance.
 */

import { chromium } from "playwright";
import { win32 as windowsPath } from "node:path";

const CONTRACT = "packaged-calibration-browser-probe.v1";
const RATER = "Example calibration rater";
const STEPS = new Set([
  "invalid_environment", "browser_launch_failed", "context_create_failed",
  "page_create_failed", "calibration_page_failed", "case_review_failed",
  "initial_review_response_failed", "evidence_container_failed",
  "evidence_content_failed", "reload_review_response_failed",
  "reload_evidence_container_failed", "reload_evidence_content_failed",
  "rating_input_failed", "rating_save_failed", "reload_failed",
  "request_boundary_failed", "browser_cleanup_failed", "probe_failed",
]);

const report = {
  contract: CONTRACT,
  passed: false,
  browser_started: false,
  browser_closed: false,
  calibration_page_loaded: false,
  case_reviewed: false,
  evidence_container_visible: false,
  expected_evidence_visible: false,
  reloaded_evidence_container_visible: false,
  reloaded_expected_evidence_visible: false,
  review_acknowledged: false,
  ratings_saved: false,
  reload_verified: false,
  rater_persisted: false,
  review_expiry_claimed: false,
  review_requests: 0,
  initial_review_status: null,
  reload_review_status: null,
  rating_mutations: 0,
  ratings_verified: 0,
  cannot_judge_verified: 0,
  reloads: 0,
  model_mutation_requests: 0,
  forbidden_mutations: 0,
  external_requests: 0,
  page_errors: 0,
  server_failures: 0,
  error_code: null,
  exception_kind: null,
};

let browser;
let phase = "invalid_environment";

function fail(code) {
  const error = new Error(code);
  error.probeCode = code;
  throw error;
}

function requireCondition(value, code) {
  if (!value) fail(code);
}

async function visible(locator, code) {
  try {
    await locator.waitFor({ state: "visible" });
  } catch {
    fail(code);
  }
}

function exceptionKind(error) {
  const name = error && typeof error === "object" && "name" in error ? error.name : "";
  if (name === "TimeoutError") return "timeout";
  if (name === "TargetClosedError") return "target_closed";
  if (error instanceof Error) return "playwright_error";
  return "unknown";
}

try {
  const base = process.env.PE_PACKAGED_BASE_URL ?? "";
  const executablePath = process.env.PE_PACKAGED_BROWSER_EXECUTABLE ?? "";
  let parsed;
  try { parsed = new URL(base); } catch { fail("invalid_environment"); }
  requireCondition(
    parsed.protocol === "http:"
      && parsed.hostname === "127.0.0.1"
      && parsed.username === ""
      && parsed.password === ""
      && parsed.port !== ""
      && Number.isInteger(Number(parsed.port))
      && Number(parsed.port) >= 1024
      && Number(parsed.port) <= 65535
      && !["8765", "8766"].includes(parsed.port)
      && parsed.pathname === "/"
      && parsed.search === ""
      && parsed.hash === ""
      && windowsPath.isAbsolute(executablePath),
    "invalid_environment",
  );
  const origin = parsed.origin;

  phase = "browser_launch_failed";
  browser = await chromium.launch({ executablePath, headless: true });
  report.browser_started = true;
  phase = "context_create_failed";
  const context = await browser.newContext({
    baseURL: origin,
    viewport: { width: 1280, height: 800 },
    serviceWorkers: "block",
  });
  context.setDefaultTimeout(5_000);
  context.setDefaultNavigationTimeout(10_000);
  await context.route("**/*", async (route) => {
    let allowed = false;
    let path = "";
    const method = route.request().method();
    try {
      const target = new URL(route.request().url());
      allowed = target.origin === origin;
      path = target.pathname;
    } catch { /* closed */ }
    if (!allowed) {
      report.external_requests += 1;
      await route.abort("blockedbyclient");
      return;
    }
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
      if (method === "POST" && path === "/v1/calibration/review" && report.review_requests < 2) {
        report.review_requests += 1;
      } else if (method === "PUT" && path === "/v1/calibration/ratings" && report.rating_mutations < 1) {
        report.rating_mutations += 1;
      } else {
        report.forbidden_mutations += 1;
        await route.abort("blockedbyclient");
        return;
      }
    }
    await route.continue();
  });

  phase = "page_create_failed";
  const page = await context.newPage();
  page.on("pageerror", () => { report.page_errors += 1; });
  page.on("response", (response) => {
    try {
      if (new URL(response.url()).origin === origin && response.status() >= 500) {
        report.server_failures += 1;
      }
    } catch { /* content-free accounting only */ }
  });
  page.on("request", (request) => {
    let path = "";
    try { path = new URL(request.url()).pathname; } catch { return; }
    if (!["GET", "HEAD", "OPTIONS"].includes(request.method())
      && path.startsWith("/v1/model-judge")) {
      report.model_mutation_requests += 1;
    }
  });

  phase = "calibration_page_failed";
  const navigation = await page.goto(`${origin}/calibration`, { waitUntil: "domcontentloaded" });
  requireCondition(navigation?.status() === 200, phase);
  await visible(page.getByRole("heading", { level: 1, name: "Rate sessions", exact: true }), phase);
  report.calibration_page_loaded = true;
  const rater = page.getByRole("textbox", { name: "Rater name", exact: true });
  await rater.fill(RATER);
  await rater.press("Enter");
  const initialReview = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "POST"
      && url.origin === origin && url.pathname === "/v1/calibration/review";
  });
  await page.getByRole("button", { name: "Next unrated", exact: true }).click();

  phase = "initial_review_response_failed";
  report.initial_review_status = (await initialReview).status();
  requireCondition(report.initial_review_status === 200, phase);
  const evidence = page.getByLabel("Redacted case evidence", { exact: true });
  phase = "evidence_container_failed";
  await visible(evidence, phase);
  report.evidence_container_visible = true;
  phase = "evidence_content_failed";
  await visible(evidence.getByText("Review the fictional module and report the checks performed.", { exact: true }), phase);
  report.expected_evidence_visible = true;
  report.case_reviewed = true;

  phase = "rating_input_failed";
  const choices = [
    ["Task definition", "high"],
    ["Context given", "cannot_judge"],
    ["Verification strategy", "medium"],
  ];
  for (const [groupName, value] of choices) {
    const radio = page.getByRole("radiogroup", { name: groupName, exact: true })
      .locator(`input[value="${value}"]`);
    await radio.check();
    requireCondition(await radio.isChecked(), phase);
  }
  const acknowledgment = page.getByRole("checkbox", { name: /I reviewed this case/u });
  await acknowledgment.check();
  requireCondition(await acknowledgment.isChecked(), phase);
  report.review_acknowledged = true;

  phase = "rating_save_failed";
  const save = page.getByRole("button", { name: "Save", exact: true });
  const savedResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "PUT"
      && url.origin === origin && url.pathname === "/v1/calibration/ratings";
  });
  await save.click();
  requireCondition((await savedResponse).status() === 200, phase);
  await visible(page.getByText("Saved.", { exact: true }), phase);
  report.ratings_saved = true;

  phase = "reload_failed";
  await page.reload({ waitUntil: "domcontentloaded" });
  report.reloads = 1;
  await visible(page.getByRole("heading", { level: 1, name: "Rate sessions", exact: true }), phase);
  requireCondition((await page.getByRole("textbox", { name: "Rater name", exact: true }).inputValue()) === RATER, phase);
  report.rater_persisted = true;
  const sample = page.getByRole("complementary", { name: "Calibration sample", exact: true });
  await visible(sample, phase);
  const reloadedReview = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "POST"
      && url.origin === origin && url.pathname === "/v1/calibration/review";
  });
  await sample.locator("li button").first().click();
  phase = "reload_review_response_failed";
  report.reload_review_status = (await reloadedReview).status();
  requireCondition(report.reload_review_status === 200, phase);
  const reloadedEvidence = page.getByLabel("Redacted case evidence", { exact: true });
  phase = "reload_evidence_container_failed";
  await visible(reloadedEvidence, phase);
  report.reloaded_evidence_container_visible = true;
  phase = "reload_evidence_content_failed";
  await visible(reloadedEvidence.getByText("Review the fictional module and report the checks performed.", { exact: true }), phase);
  report.reloaded_expected_evidence_visible = true;
  let verified = 0;
  let cannotJudge = 0;
  for (const [groupName, value] of choices) {
    const radio = page.getByRole("radiogroup", { name: groupName, exact: true })
      .locator(`input[value="${value}"]`);
    requireCondition(await radio.isChecked(), phase);
    verified += 1;
    if (value === "cannot_judge") cannotJudge += 1;
  }
  report.ratings_verified = verified;
  report.cannot_judge_verified = cannotJudge;
  report.reload_verified = true;

  requireCondition(report.review_requests === 2, "request_boundary_failed");
  requireCondition(report.rating_mutations === 1, "request_boundary_failed");
  requireCondition(report.model_mutation_requests === 0, "request_boundary_failed");
  requireCondition(report.forbidden_mutations === 0, "request_boundary_failed");
  requireCondition(report.external_requests === 0, "request_boundary_failed");
  requireCondition(report.page_errors === 0, "request_boundary_failed");
  requireCondition(report.server_failures === 0, "request_boundary_failed");
} catch (error) {
  const expected = error && typeof error === "object" && "probeCode" in error;
  const candidate = expected ? error.probeCode : phase;
  report.error_code = STEPS.has(candidate) ? candidate : "probe_failed";
  report.exception_kind = expected ? null : exceptionKind(error);
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
    report.error_code = "browser_cleanup_failed";
  }
}

report.passed = report.error_code === null
  && report.exception_kind === null
  && report.browser_started && report.browser_closed
  && report.calibration_page_loaded && report.case_reviewed
  && report.evidence_container_visible && report.expected_evidence_visible
  && report.reloaded_evidence_container_visible && report.reloaded_expected_evidence_visible
  && report.review_acknowledged && report.ratings_saved
  && report.reload_verified && report.rater_persisted
  && report.review_expiry_claimed === false
  && report.review_requests === 2 && report.rating_mutations === 1
  && report.initial_review_status === 200 && report.reload_review_status === 200
  && report.ratings_verified === 3 && report.cannot_judge_verified === 1
  && report.reloads === 1 && report.model_mutation_requests === 0
  && report.forbidden_mutations === 0
  && report.external_requests === 0 && report.page_errors === 0
  && report.server_failures === 0;

process.stdout.write(`PACKAGED_CALIBRATION_BROWSER_PROBE=${JSON.stringify(report)}\n`);
process.exitCode = report.passed ? 0 : 1;
