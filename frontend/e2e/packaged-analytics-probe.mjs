/**
 * Read-only packaged analytics acceptance for one fictional Claude session.
 *
 * The runner indexes the consented fixture before this fresh browser starts.
 * This probe opens that catalog row and checks two stored metric categories.
 * It never starts analysis, a model, or any mutation.
 */
import { chromium } from "playwright";
import { win32 as windowsPath } from "node:path";

const CONTRACT = "packaged-analytics-browser-probe.v1";
const ERRORS = new Set([
  "invalid_environment", "browser_launch_failed", "context_create_failed",
  "page_create_failed", "sessions_page_failed", "catalog_open_failed",
  "model_usage_response_failed", "unknown_token_contract_failed",
  "unknown_token_display_failed", "token_coverage_failed", "provenance_failed",
  "outcome_response_failed", "claim_boundary_failed", "outcome_display_failed",
  "request_boundary_failed", "browser_cleanup_failed", "probe_failed",
]);
const report = {
  contract: CONTRACT, passed: false, browser_started: false, browser_closed: false,
  sessions_page_loaded: false, catalog_session_opened: false,
  model_usage_api_verified: false, unknown_token_displayed: false,
  token_coverage_displayed: false, provenance_displayed: false,
  outcome_api_verified: false, assistant_claim_not_verified: false,
  outcome_displayed: false, session_rows: 0, metric_response_events: 0,
  verified_category_responses: 0,
  forbidden_mutations: 0, external_requests: 0, page_errors: 0,
  server_failures: 0, model_mutation_requests: 0,
  model_usage_status: null, outcome_status: null,
  error_code: null, exception_kind: null,
};
let browser;
let phase = "invalid_environment";

function fail(code) {
  const error = new Error(code);
  error.probeCode = code;
  throw error;
}
function requireCondition(value, code = phase) { if (!value) fail(code); }
async function visible(locator, code = phase) {
  try { await locator.waitFor({ state: "visible" }); } catch { fail(code); }
}
function exceptionKind(error) {
  const name = error && typeof error === "object" && "name" in error ? error.name : "";
  if (name === "TimeoutError") return "timeout";
  if (name === "TargetClosedError") return "target_closed";
  if (error instanceof Error) return "playwright_error";
  return "unknown";
}
function metric(payload, key) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)
      || !Array.isArray(payload.metrics) || payload.metrics.length > 64) return null;
  const matches = payload.metrics.filter((item) => item && typeof item === "object"
    && !Array.isArray(item) && item.key === key);
  return matches.length === 1 ? matches[0] : null;
}
function categoryUrl(current, category) {
  const target = new URL(current);
  const parts = target.pathname.split("/");
  requireCondition(parts.length === 7 && parts[1] === "projects"
    && parts[3] === "sessions" && parts[5] === "metrics", "catalog_open_failed");
  parts[6] = category;
  target.pathname = parts.join("/");
  return target.href;
}
async function boundedJson(response, code) {
  const rawLength = response.headers()["content-length"];
  const encoding = (response.headers()["content-encoding"] ?? "identity").toLowerCase();
  const length = Number(rawLength);
  requireCondition(rawLength !== undefined && Number.isInteger(length)
    && length >= 2 && length <= 65_536
    && ["identity", "gzip"].includes(encoding), code);
  let text;
  try { text = await response.text(); } catch { fail(code); }
  const decodedLength = new TextEncoder().encode(text).length;
  requireCondition(decodedLength >= 2 && decodedLength <= 65_536
    && (encoding === "gzip" || decodedLength === length), code);
  try { return JSON.parse(text); } catch { fail(code); }
}

try {
  const base = process.env.PE_PACKAGED_BASE_URL ?? "";
  const executablePath = process.env.PE_PACKAGED_BROWSER_EXECUTABLE ?? "";
  let parsed;
  try { parsed = new URL(base); } catch { fail("invalid_environment"); }
  requireCondition(parsed.protocol === "http:" && parsed.hostname === "127.0.0.1"
    && parsed.username === "" && parsed.password === "" && parsed.port !== ""
    && Number.isInteger(Number(parsed.port)) && Number(parsed.port) >= 1024
    && Number(parsed.port) <= 65535 && !["8765", "8766"].includes(parsed.port)
    && parsed.pathname === "/" && parsed.search === "" && parsed.hash === ""
    && windowsPath.isAbsolute(executablePath));
  const origin = parsed.origin;

  phase = "browser_launch_failed";
  browser = await chromium.launch({ executablePath, headless: true });
  report.browser_started = true;
  phase = "context_create_failed";
  const context = await browser.newContext({ baseURL: origin,
    viewport: { width: 1280, height: 800 }, serviceWorkers: "block" });
  context.setDefaultTimeout(5_000);
  context.setDefaultNavigationTimeout(10_000);
  await context.route("**/*", async (route) => {
    const request = route.request();
    let local = false;
    let path = "";
    try {
      const target = new URL(request.url());
      local = target.origin === origin;
      path = target.pathname;
    } catch { /* closed accounting */ }
    if (!local) {
      report.external_requests += 1;
      await route.abort("blockedbyclient");
      return;
    }
    if (!["GET", "HEAD", "OPTIONS"].includes(request.method())) {
      report.forbidden_mutations += 1;
      if (path.startsWith("/v1/model") || path.startsWith("/v1/local-model")) {
        report.model_mutation_requests += 1;
      }
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
      const target = new URL(response.url());
      if (target.origin === origin && response.request().method() === "GET"
          && /^\/v1\/sessions\/[a-f0-9]{64}\/metrics$/u.test(target.pathname)) {
        report.metric_response_events += 1;
      }
      if (target.origin === origin && response.status() >= 500) {
        report.server_failures += 1;
      }
    } catch { /* content-free accounting */ }
  });

  phase = "sessions_page_failed";
  const navigation = await page.goto(`${origin}/sessions`, { waitUntil: "domcontentloaded" });
  requireCondition(navigation?.status() === 200);
  await visible(page.getByRole("heading", { level: 1, name: "Sessions", exact: true }));
  const rows = page.locator("button.session-row");
  await visible(rows.first());
  report.session_rows = await rows.count();
  requireCondition(report.session_rows === 1);
  report.sessions_page_loaded = true;

  phase = "catalog_open_failed";
  await rows.first().click();
  await page.waitForURL(/\/projects\/[a-f0-9]{64}\/sessions\/[a-f0-9]{64}\/metrics\/readiness$/u);
  report.catalog_session_opened = true;

  phase = "model_usage_response_failed";
  const usageResponsePromise = page.waitForResponse((response) => {
    const target = new URL(response.url());
    return response.request().method() === "GET" && target.origin === origin
      && /^\/v1\/sessions\/[a-f0-9]{64}\/metrics$/u.test(target.pathname);
  });
  await page.goto(categoryUrl(page.url(), "model-usage"), { waitUntil: "domcontentloaded" });
  const usageResponse = await usageResponsePromise;
  report.model_usage_status = usageResponse.status();
  requireCondition(report.model_usage_status === 200);
  const usagePayload = await boundedJson(usageResponse, phase);
  const totalTokens = metric(usagePayload, "usage.total_tokens");
  phase = "unknown_token_contract_failed";
  requireCondition(totalTokens !== null && totalTokens.numeric_value === null
    && totalTokens.text_value === null && totalTokens.unit === "tokens"
    && totalTokens.observed_count === 0 && totalTokens.eligible_count === 1
    && totalTokens.coverage === 0 && totalTokens.confidence === null);
  report.model_usage_api_verified = true;
  report.verified_category_responses += 1;

  const tokenCard = page.locator("article.local-metric-card").filter({
    has: page.getByRole("heading", { level: 3, name: "Total tokens", exact: true }),
  });
  phase = "unknown_token_display_failed";
  await visible(tokenCard);
  await visible(tokenCard.locator("strong.local-metric-card__value").filter({ hasText: /^Unknown$/u }));
  requireCondition(await tokenCard.getByText("0 tokens", { exact: true }).count() === 0);
  report.unknown_token_displayed = true;
  phase = "token_coverage_failed";
  await visible(tokenCard.getByRole("meter", { name: "0 of 1 observations (0%)", exact: true }));
  await visible(tokenCard.getByText(
    "Eligible evidence exists, but no usable observations were available in this current snapshot.",
    { exact: true },
  ));
  report.token_coverage_displayed = true;
  phase = "provenance_failed";
  await tokenCard.getByText("Definition and provenance", { exact: true }).click();
  await visible(tokenCard.getByText("usage.total_tokens", { exact: true }));
  await visible(tokenCard.locator("dt", { hasText: /^Source$/u }).locator("..")
    .locator("dd").filter({ hasText: /^Provider Reported$/u }));
  await visible(tokenCard.locator("dt", { hasText: /^Definition$/u }).locator("..")
    .locator("dd").filter({ hasText: /^v2$/u }));
  report.provenance_displayed = true;

  phase = "outcome_response_failed";
  const outcomeResponsePromise = page.waitForResponse((response) => {
    const target = new URL(response.url());
    return response.request().method() === "GET" && target.origin === origin
      && /^\/v1\/sessions\/[a-f0-9]{64}\/metrics$/u.test(target.pathname);
  });
  await page.goto(categoryUrl(page.url(), "outcome"), { waitUntil: "domcontentloaded" });
  const outcomeResponse = await outcomeResponsePromise;
  report.outcome_status = outcomeResponse.status();
  requireCondition(report.outcome_status === 200);
  const outcomePayload = await boundedJson(outcomeResponse, phase);
  const verificationCount = metric(outcomePayload, "verification.verification_count");
  const passRate = metric(outcomePayload, "verification.pass_rate");
  phase = "claim_boundary_failed";
  requireCondition(verificationCount !== null && verificationCount.numeric_value === 0
    && verificationCount.observed_count === 1 && verificationCount.eligible_count === 1
    && verificationCount.coverage === 1
    && passRate !== null && passRate.numeric_value === null
    && passRate.observed_count === 0 && passRate.eligible_count === 0);
  report.outcome_api_verified = true;
  report.assistant_claim_not_verified = true;
  report.verified_category_responses += 1;

  phase = "outcome_display_failed";
  const countCard = page.locator("article.local-metric-card").filter({
    has: page.getByRole("heading", { level: 3, name: "Verification count", exact: true }),
  });
  const rateCard = page.locator("article.local-metric-card").filter({
    has: page.getByRole("heading", { level: 3, name: "Verification pass rate", exact: true }),
  });
  await visible(countCard.locator("strong.local-metric-card__value").filter({ hasText: /^0$/u }));
  await visible(rateCard.locator("strong.local-metric-card__value").filter({ hasText: /^Unknown$/u }));
  report.outcome_displayed = true;
  phase = "request_boundary_failed";
  requireCondition(report.verified_category_responses === 2
    && report.forbidden_mutations === 0
    && report.external_requests === 0 && report.page_errors === 0
    && report.server_failures === 0 && report.model_mutation_requests === 0);
} catch (error) {
  const code = error && typeof error === "object" && "probeCode" in error
    ? error.probeCode : phase;
  report.error_code = ERRORS.has(code) ? code : "probe_failed";
  report.exception_kind = exceptionKind(error);
} finally {
  if (browser) {
    try { await browser.close(); report.browser_closed = true; }
    catch { report.error_code ??= "browser_cleanup_failed"; }
  }
}
report.passed = report.error_code === null && report.exception_kind === null
  && report.browser_started && report.browser_closed && report.sessions_page_loaded
  && report.catalog_session_opened && report.model_usage_api_verified
  && report.unknown_token_displayed && report.token_coverage_displayed
  && report.provenance_displayed && report.outcome_api_verified
  && report.assistant_claim_not_verified && report.outcome_displayed
  && report.session_rows === 1 && report.verified_category_responses === 2
  && report.model_usage_status === 200 && report.outcome_status === 200
  && report.forbidden_mutations === 0 && report.external_requests === 0
  && report.page_errors === 0 && report.server_failures === 0
  && report.model_mutation_requests === 0;
process.stdout.write(`PACKAGED_ANALYTICS_BROWSER_PROBE=${JSON.stringify(report)}\n`);
