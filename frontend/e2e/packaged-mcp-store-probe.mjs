/** Packaged MCP Store browse/search/review with an injected fictional registry. */
import { chromium } from "playwright";
import { win32 as windowsPath } from "node:path";

const CONTRACT = "packaged-mcp-store-browser-probe.v2";
const ERRORS = new Set([
  "invalid_environment", "browser_launch_failed", "context_create_failed",
  "page_create_failed", "agent_page_failed", "store_open_failed",
  "catalog_response_failed", "catalog_display_failed", "search_response_failed",
  "search_display_failed", "review_response_failed", "review_display_failed",
  "install_boundary_failed", "return_failed", "request_boundary_failed",
  "cached_delivery_failed", "cached_age_failed", "review_refusal_failed",
  "uncached_query_failed",
  "browser_cleanup_failed", "probe_failed",
]);
const report = {
  contract: CONTRACT, passed: false, browser_started: false, browser_closed: false,
  agent_page_loaded: false, store_opened: false, initial_catalog_verified: false,
  initial_tiles_visible: false, search_catalog_verified: false,
  search_result_visible: false, review_api_verified: false,
  provenance_visible: false, review_boundary_visible: false,
  setup_plan_disabled: false, returned_to_catalog: false,
  live_review_rendered: false, cached_delivery_verified: false,
  cached_age_visible: false, exact_review_unavailable: false,
  uncached_query_refused: false,
  initial_tiles: 0, searched_tiles: 0, catalog_response_events: 0,
  review_response_events: 0, forbidden_mutations: 0, external_requests: 0,
  page_errors: 0, server_failures: 0, managed_lifecycle_mutations: 0,
  model_mutations: 0, native_confirmation_mutations: 0, settings_locator_count: 0,
  expected_outage_responses: 0,
  agent_navigation_status: null, initial_catalog_status: null,
  search_catalog_status: null, review_status: null, uncached_catalog_status: null,
  journey_phase: null,
  error_code: null, exception_kind: null,
};
let browser;
let phase = "invalid_environment";
let selectedCatalogId = null;
let selectedPresentationRevision = null;

function fail(code) { const error = new Error(code); error.probeCode = code; throw error; }
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
function exactServerIdentity(server) {
  return server && typeof server === "object"
    && typeof server.catalog_id === "string" && /^[a-f0-9]{32}$/u.test(server.catalog_id)
    && typeof server.presentation_revision === "string" && /^[a-f0-9]{64}$/u.test(server.presentation_revision)
    && typeof server.name === "string" && typeof server.title === "string"
    && server.version === "1.2.3";
}
async function boundedJson(response, code) {
  const rawLength = response.headers()["content-length"];
  const encoding = (response.headers()["content-encoding"] ?? "identity").toLowerCase();
  const length = Number(rawLength);
  requireCondition(rawLength !== undefined && Number.isInteger(length)
    && length >= 2 && length <= 65_536 && ["identity", "gzip"].includes(encoding), code);
  let body;
  try { body = await response.text(); } catch { fail(code); }
  const decoded = new TextEncoder().encode(body).length;
  requireCondition(decoded >= 2 && decoded <= 65_536
    && (encoding === "gzip" || decoded === length), code);
  try { return JSON.parse(body); } catch { fail(code); }
}

try {
  const base = process.env.PE_PACKAGED_BASE_URL ?? "";
  const executablePath = process.env.PE_PACKAGED_BROWSER_EXECUTABLE ?? "";
  const journeyPhase = process.env.PE_PACKAGED_MCP_STORE_PHASE ?? "";
  requireCondition(["live", "cached"].includes(journeyPhase));
  report.journey_phase = journeyPhase;
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
    try { const target = new URL(request.url()); local = target.origin === origin; path = target.pathname; }
    catch { /* closed accounting */ }
    if (!local) { report.external_requests += 1; await route.abort("blockedbyclient"); return; }
    if (!["GET", "HEAD", "OPTIONS"].includes(request.method())) {
      report.forbidden_mutations += 1;
      if (path.startsWith("/v1/integrations/mcp-store/managed")) report.managed_lifecycle_mutations += 1;
      if (path.startsWith("/v1/local-model") || path.startsWith("/v1/model")) report.model_mutations += 1;
      if (path.includes("user-presence") || path.includes("native")) report.native_confirmation_mutations += 1;
      await route.abort("blockedbyclient"); return;
    }
    await route.continue();
  });

  phase = "page_create_failed";
  const page = await context.newPage();
  page.on("pageerror", () => { report.page_errors += 1; });
  page.on("response", (response) => {
    try {
      const target = new URL(response.url());
      if (target.origin === origin && target.pathname === "/v1/integrations/mcp-store/catalog") report.catalog_response_events += 1;
      if (target.origin === origin && /^\/v1\/integrations\/mcp-store\/servers\/[a-f0-9]{32}\/review$/u.test(target.pathname)) report.review_response_events += 1;
      if (target.origin === origin && response.status() >= 500) {
        const expectedReview = journeyPhase === "cached" && response.status() === 503
          && response.request().method() === "GET"
          && selectedCatalogId !== null
          && target.pathname === `/v1/integrations/mcp-store/servers/${selectedCatalogId}/review`
          && target.searchParams.get("name") === "com.example/synthetic-files"
          && target.searchParams.get("version") === "1.2.3"
          && selectedPresentationRevision !== null
          && target.searchParams.get("presentation_revision") === selectedPresentationRevision
          && [...target.searchParams.keys()].sort().join(",") === "name,presentation_revision,version";
        const expectedUncached = journeyPhase === "cached" && response.status() === 503
          && response.request().method() === "GET"
          && target.pathname === "/v1/integrations/mcp-store/catalog"
          && target.searchParams.get("search") === "uncached example"
          && target.searchParams.get("cursor") === null
          && target.searchParams.get("limit") === "24"
          && [...target.searchParams.keys()].sort().join(",") === "limit,search";
        if (expectedReview || expectedUncached) report.expected_outage_responses += 1;
        else report.server_failures += 1;
      }
    } catch { /* content-free accounting */ }
  });

  phase = "agent_page_failed";
  const navigation = await page.goto(`${origin}/agent`, { waitUntil: "domcontentloaded" });
  report.agent_navigation_status = navigation?.status() ?? null;
  requireCondition(report.agent_navigation_status === 200);
  const closeSetup = page.getByRole("button", { name: "Close new chat setup", exact: true });
  try {
    await closeSetup.waitFor({ state: "visible", timeout: 1_500 });
    await closeSetup.click();
    await closeSetup.waitFor({ state: "hidden" });
  } catch { /* setup is optional when a retained catalog already exists */ }
  const settingsTrigger = page.getByRole("button", { name: /^Agent settings(?:\s|$)/u });
  await visible(settingsTrigger);
  report.settings_locator_count = await settingsTrigger.count();
  requireCondition(report.settings_locator_count === 1
    && await settingsTrigger.getAttribute("aria-controls") === "agent-settings-drawer");
  report.agent_page_loaded = true;

  phase = "store_open_failed";
  await settingsTrigger.click();
  const initialPromise = page.waitForResponse((response) => {
    const target = new URL(response.url());
    return response.request().method() === "GET" && target.origin === origin
      && target.pathname === "/v1/integrations/mcp-store/catalog";
  });
  await page.getByRole("tab", { name: "MCP Store", exact: true }).click();
  const initial = await initialPromise;
  report.initial_catalog_status = initial.status();
  requireCondition(initial.status() === 200, "catalog_response_failed");
  const initialPayload = await boundedJson(initial, "catalog_response_failed");
  requireCondition(initialPayload?.management_truth === "registry_only_no_install_authority"
    && initialPayload?.search === "" && Array.isArray(initialPayload?.servers)
    && initialPayload.servers.length === 2, "catalog_response_failed");
  const initialIdentities = initialPayload.servers.map((server) => {
    requireCondition(exactServerIdentity(server), "catalog_response_failed");
    return `${server.name}\u0000${server.title}\u0000${server.version}`;
  }).sort();
  requireCondition(initialIdentities.join("\n") === [
    "com.example/synthetic-browser\u0000Synthetic Browser\u00001.2.3",
    "com.example/synthetic-files\u0000Synthetic Files\u00001.2.3",
  ].join("\n"), "catalog_response_failed");
  if (journeyPhase === "live") requireCondition(initialPayload?.source?.delivery === "live", "catalog_response_failed");
  else {
    phase = "cached_delivery_failed";
    requireCondition(initialPayload?.source?.delivery === "cached"
      && Number.isInteger(initialPayload?.source?.cache_age_seconds)
      && initialPayload.source.cache_age_seconds >= 0
      && initialPayload.source.cache_age_seconds <= 86_400);
    report.cached_delivery_verified = true;
  }
  report.initial_catalog_verified = true;
  const store = page.getByRole("region", { name: "MCP Store", exact: true });
  await visible(store);
  await visible(store.getByText("Synthetic Files", { exact: true }));
  await visible(store.getByText("Synthetic Browser", { exact: true }));
  const cards = store.getByRole("article");
  report.initial_tiles = await cards.count();
  requireCondition(report.initial_tiles === 2, "catalog_display_failed");
  report.initial_tiles_visible = true;
  report.store_opened = true;
  if (journeyPhase === "cached") {
    phase = "cached_age_failed";
    await visible(store.getByText("Cached", { exact: true }));
    await visible(store.getByText(`Offline fallback · ${initialPayload.source.cache_age_seconds}s old · exact review may need the Registry`, { exact: true }));
    report.cached_age_visible = true;
  }

  phase = "search_response_failed";
  await store.getByLabel("Search MCP servers", { exact: true }).fill("  fictional   files  ");
  const searchPromise = page.waitForResponse((response) => {
    const target = new URL(response.url());
    return response.request().method() === "GET" && target.origin === origin
      && target.pathname === "/v1/integrations/mcp-store/catalog"
      && target.searchParams.get("search") === "fictional files";
  });
  await store.getByRole("button", { name: "Search", exact: true }).click();
  const searched = await searchPromise;
  report.search_catalog_status = searched.status();
  requireCondition(searched.status() === 200, phase);
  const searchPayload = await boundedJson(searched, phase);
  requireCondition(searchPayload?.management_truth === "registry_only_no_install_authority"
    && searchPayload?.search === "fictional files" && Array.isArray(searchPayload?.servers)
    && searchPayload.servers.length === 1, phase);
  requireCondition(searchPayload?.source?.delivery === journeyPhase, phase);
  const selected = searchPayload.servers[0];
  requireCondition(exactServerIdentity(selected)
    && selected.name === "com.example/synthetic-files"
    && selected.title === "Synthetic Files", phase);
  selectedCatalogId = selected.catalog_id;
  selectedPresentationRevision = selected.presentation_revision;
  if (journeyPhase === "cached") {
    requireCondition(Number.isInteger(searchPayload?.source?.cache_age_seconds)
      && searchPayload.source.cache_age_seconds >= 0
      && searchPayload.source.cache_age_seconds <= 86_400, phase);
  }
  report.search_catalog_verified = true;
  await visible(store.getByText("Search: “fictional files”", { exact: true }), "search_display_failed");
  await visible(store.getByText("Synthetic Files", { exact: true }), "search_display_failed");
  if (journeyPhase === "cached") {
    await visible(store.getByText(`Offline fallback · ${searchPayload.source.cache_age_seconds}s old · exact review may need the Registry`, { exact: true }), "search_display_failed");
  }
  report.searched_tiles = await store.getByRole("article").count();
  requireCondition(report.searched_tiles === 1, "search_display_failed");
  requireCondition(await store.getByText("Synthetic Browser", { exact: true }).count() === 0, "search_display_failed");
  report.search_result_visible = true;

  phase = "review_response_failed";
  const reviewPromise = page.waitForResponse((response) => {
    const target = new URL(response.url());
    return response.request().method() === "GET" && target.origin === origin
      && target.pathname === `/v1/integrations/mcp-store/servers/${selectedCatalogId}/review`
      && target.searchParams.get("presentation_revision") === selectedPresentationRevision;
  });
  await store.getByRole("button", { name: "Review Synthetic Files", exact: true }).click();
  const review = await reviewPromise;
  report.review_status = review.status();
  if (journeyPhase === "live") {
    requireCondition(review.status() === 200, phase);
    const reviewPayload = await boundedJson(review, phase);
    requireCondition(reviewPayload?.install_action === "unavailable"
      && reviewPayload?.server?.title === "Synthetic Files"
      && reviewPayload?.provenance?.publisher_namespace === "com.example"
      && Array.isArray(reviewPayload?.versions) && reviewPayload.versions.length === 2
      && Array.isArray(reviewPayload?.options) && reviewPayload.options.length >= 1, phase);
    report.review_api_verified = true;
    phase = "review_display_failed";
    await visible(store.getByText("Read-only server review", { exact: true }));
    await visible(store.getByRole("heading", { name: "Publisher and source provenance", exact: true }));
    await visible(store.getByText("Registry record · not a security approval", { exact: true }));
    await visible(store.locator("dt", { hasText: /^Registry security review$/u }).locator("..").locator("dd").filter({ hasText: /^Not claimed$/u }));
    await visible(store.locator("dt", { hasText: /^License$/u }).locator("..").locator("dd").filter({ hasText: /^Not declared by Registry contract$/u }));
    report.provenance_visible = true;
    await visible(store.getByText("Preview only. This review cannot install or run code, connect an endpoint, collect a credential, or edit an MCP client configuration.", { exact: true }));
    report.review_boundary_visible = true;
    phase = "install_boundary_failed";
    const save = store.getByRole("button", { name: "Save setup plan", exact: true });
    await visible(save);
    requireCondition(await save.isDisabled());
    report.setup_plan_disabled = true;
    report.live_review_rendered = true;
  } else {
    phase = "review_refusal_failed";
    requireCondition(review.status() === 503);
    await visible(store.getByText("The official Registry could not provide this exact review.", { exact: true }));
    requireCondition(await store.getByRole("button", { name: "Save setup plan", exact: true }).count() === 0);
    report.review_api_verified = true;
    report.setup_plan_disabled = true;
    report.exact_review_unavailable = true;
  }

  phase = "return_failed";
  await store.getByRole("button", { name: "Back to catalog", exact: true }).click();
  await visible(store.getByText("Search: “fictional files”", { exact: true }));
  await visible(store.getByText("Synthetic Files", { exact: true }));
  report.returned_to_catalog = true;

  if (journeyPhase === "cached") {
    phase = "uncached_query_failed";
    await store.getByLabel("Search MCP servers", { exact: true }).fill("uncached example");
    const uncachedPromise = page.waitForResponse((response) => {
      const target = new URL(response.url());
      return response.request().method() === "GET" && target.origin === origin
        && target.pathname === "/v1/integrations/mcp-store/catalog"
        && target.searchParams.get("search") === "uncached example";
    });
    await store.getByRole("button", { name: "Search", exact: true }).click();
    const uncached = await uncachedPromise;
    report.uncached_catalog_status = uncached.status();
    requireCondition(uncached.status() === 503);
    await visible(store.getByText("The official Registry and an exact cached result were unavailable.", { exact: true }));
    requireCondition(await store.getByText("Synthetic Files", { exact: true }).count() === 0);
    report.uncached_query_refused = true;
  }

  phase = "request_boundary_failed";
  requireCondition(report.catalog_response_events >= 2 && report.catalog_response_events <= 10
    && report.review_response_events >= 1 && report.review_response_events <= 5
    && report.forbidden_mutations === 0 && report.external_requests === 0
    && report.page_errors === 0 && report.server_failures === 0
    && report.managed_lifecycle_mutations === 0 && report.model_mutations === 0
    && report.native_confirmation_mutations === 0
    && report.expected_outage_responses === (journeyPhase === "cached" ? 2 : 0));
} catch (error) {
  const code = error && typeof error === "object" && "probeCode" in error ? error.probeCode : phase;
  report.error_code = ERRORS.has(code) ? code : "probe_failed";
  report.exception_kind = exceptionKind(error);
} finally {
  if (browser) {
    try { await browser.close(); report.browser_closed = true; }
    catch { report.error_code ??= "browser_cleanup_failed"; }
  }
}
report.passed = report.error_code === null && report.exception_kind === null
  && report.browser_started && report.browser_closed && report.agent_page_loaded
  && report.store_opened && report.initial_catalog_verified && report.initial_tiles_visible
  && report.search_catalog_verified && report.search_result_visible
  && report.review_api_verified
  && report.setup_plan_disabled && report.returned_to_catalog
  && report.initial_tiles === 2 && report.searched_tiles === 1
  && report.settings_locator_count === 1 && report.agent_navigation_status === 200
  && report.catalog_response_events >= 2 && report.review_response_events >= 1
  && report.forbidden_mutations === 0 && report.external_requests === 0
  && report.page_errors === 0 && report.server_failures === 0
  && report.managed_lifecycle_mutations === 0 && report.model_mutations === 0
  && report.native_confirmation_mutations === 0
  && report.initial_catalog_status === 200 && report.search_catalog_status === 200
  && report.agent_navigation_status === 200;
if (report.journey_phase === "live") {
  report.passed = report.passed && report.live_review_rendered
    && report.provenance_visible && report.review_boundary_visible
    && !report.cached_delivery_verified && !report.cached_age_visible
    && !report.exact_review_unavailable && !report.uncached_query_refused
    && report.expected_outage_responses === 0 && report.uncached_catalog_status === null;
} else if (report.journey_phase === "cached") {
  report.passed = report.passed && !report.live_review_rendered
    && !report.provenance_visible && !report.review_boundary_visible
    && report.cached_delivery_verified && report.cached_age_visible
    && report.exact_review_unavailable && report.uncached_query_refused
    && report.review_status === 503 && report.uncached_catalog_status === 503
    && report.expected_outage_responses === 2;
}
process.stdout.write(`PACKAGED_MCP_STORE_BROWSER_PROBE=${JSON.stringify(report)}\n`);
