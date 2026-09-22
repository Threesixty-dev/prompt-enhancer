import { expect, test, type Locator, type Page } from "@playwright/test";

const BASE_URL = process.env.PE_CONVERGENCE_BASE_URL!;
const WORKSPACE = process.env.PE_CONVERGENCE_WORKSPACE!;
const CP34_VERIFICATION_SESSION = process.env.PE_CP34_VERIFICATION_SESSION!;
const CP34_VERIFICATION_PROJECT = process.env.PE_CP34_VERIFICATION_PROJECT!;
const RECOVERY_PROJECT = "Recovery example project";
const RECOVERY_CHAT = "Recovered example chat";
const PROJECT = "Loopback example project";
const CHAT = "example-workspace";
const RENAMED_CHAT = "Loopback verified chat";
const DISPOSABLE_PROJECT = "Disposable example project";

interface Diagnostics {
  consoleErrors: Array<{ location: string; text: string }>;
  externalRequests: number;
  expectedAbsenceResponses: Map<string, number>;
  pageErrors: number;
  serverFailures: string[];
}

const diagnosticsByPage = new WeakMap<Page, Diagnostics>();
const expectedAbsencesByPage = new WeakMap<Page, readonly string[]>();

function endpointFamily(rawUrl: string): string {
  const path = new URL(rawUrl).pathname;
  return path
    .replace(/[a-f0-9]{64}/giu, ":digest")
    .replace(/[a-f0-9]{32}/giu, ":id")
    .replace(/[0-9a-f]{8}-[0-9a-f-]{27,36}/giu, ":uuid");
}

test.beforeEach(async ({ page }) => {
  const diagnostics: Diagnostics = {
    consoleErrors: [],
    externalRequests: 0,
    expectedAbsenceResponses: new Map(),
    pageErrors: 0,
    serverFailures: [],
  };
  diagnosticsByPage.set(page, diagnostics);
  page.on("console", (message) => {
    if (message.type() === "error") {
      diagnostics.consoleErrors.push({ location: message.location().url, text: message.text() });
    }
  });
  page.on("pageerror", () => {
    diagnostics.pageErrors += 1;
  });
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.protocol.startsWith("http") && url.origin !== BASE_URL) {
      diagnostics.externalRequests += 1;
    }
  });
  page.on("requestfailed", (request) => {
    const reason = request.failure()?.errorText ?? "network";
    if (/ERR_ABORTED|NS_BINDING_ABORTED|cancelled/iu.test(reason)) return;
    if (new URL(request.url()).origin === BASE_URL) {
      diagnostics.serverFailures.push(`${request.method()} ${endpointFamily(request.url())} network`);
    }
  });
  page.on("response", (response) => {
    const expectedAbsences = expectedAbsencesByPage.get(page) ?? [];
    if (
      expectedAbsences.includes(response.url()) &&
      response.status() === 404 && response.request().method() === "GET"
    ) {
      diagnostics.expectedAbsenceResponses.set(
        response.url(),
        (diagnostics.expectedAbsenceResponses.get(response.url()) ?? 0) + 1,
      );
    }
    if (new URL(response.url()).origin === BASE_URL && response.status() >= 500) {
      diagnostics.serverFailures.push(`${response.request().method()} ${endpointFamily(response.url())} ${response.status()}`);
    }
  });
});

test.afterEach(async ({ page }) => {
  const diagnostics = diagnosticsByPage.get(page);
  expect(diagnostics, "diagnostics were installed before navigation").toBeDefined();
  expect(diagnostics!.externalRequests, "the disposable gate made no off-origin request").toBe(0);
  expect(diagnostics!.pageErrors, "the built dashboard raised no page exception").toBe(0);
  const expectedAbsences = expectedAbsencesByPage.get(page) ?? [];
  if (expectedAbsences.length === 0) {
    expect(diagnostics!.consoleErrors, "the built dashboard raised no console error").toEqual([]);
  } else {
    expect(diagnostics!.consoleErrors, "only documented cold-state absences reached browser diagnostics")
      .toHaveLength(expectedAbsences.length);
    for (const expectedAbsence of expectedAbsences) {
      expect(
        diagnostics!.expectedAbsenceResponses.get(expectedAbsence) ?? 0,
        `the expected absence returned once: ${new URL(expectedAbsence).pathname}`,
      ).toBe(1);
      const errors = diagnostics!.consoleErrors.filter((error) => error.location === expectedAbsence);
      expect(errors, `expected absence console location: ${new URL(expectedAbsence).pathname}`).toHaveLength(1);
      expect(errors[0]!.text, "expected absence resource error").toMatch(/Failed to load resource.*404/iu);
    }
  }
  expect(diagnostics!.serverFailures, "the real API returned no network/5xx failure").toEqual([]);
});

async function openAgent(page: Page): Promise<Locator> {
  await page.goto("/agent");
  const rail = page.getByRole("navigation", { name: "Agent projects and chats", exact: true });
  await expect(rail).toBeVisible();
  return rail;
}

async function selectProject(page: Page, name: string): Promise<void> {
  const rail = page.getByRole("navigation", { name: "Agent projects and chats", exact: true });
  const project = rail.locator(".agent-rail__project-pick").filter({ hasText: name });
  await expect(project).toBeVisible();
  await project.click();
}

async function selectChat(page: Page, title: string): Promise<void> {
  const rail = page.getByRole("navigation", { name: "Agent projects and chats", exact: true });
  const chat = rail.locator(".agent-rail__session-pick").filter({ hasText: title });
  await expect(chat).toBeVisible();
  await chat.click();
}

async function openLoopbackChat(page: Page): Promise<void> {
  await openAgent(page);
  await selectProject(page, PROJECT);
  await selectChat(page, RENAMED_CHAT);
  await expect(page.getByRole("heading", { level: 1, name: RENAMED_CHAT })).toBeVisible();
}

test.describe.serial("built frontend with the disposable real loopback backend", () => {
  test("boots the production SPA, issues browser auth, and reports live workers", async ({ page }) => {
    const navigation = await page.goto("/overview");
    expect(navigation?.status()).toBe(200);
    expect(navigation?.headers()["content-security-policy"]).toContain("default-src 'self'");
    expect(navigation?.headers()["x-frame-options"]).toBe("DENY");
    expect(navigation?.headers()["cache-control"]).toContain("no-store");
    await expect(page.getByRole("heading", { level: 1, name: "Overview" })).toBeVisible();
    await expect(page.locator("script[type='module'][src^='/assets/']")).toHaveCount(1);
    await expect(page.locator("script[src*='@vite/client']")).toHaveCount(0);
    await expect(page.getByLabel("Runtime status: Local loopback service available", { exact: true }))
      .toHaveAttribute("data-service-state", "available");

    const auth = await page.request.get("/auth/session", {
      headers: { "Sec-Fetch-Site": "same-origin" },
    });
    expect(auth.status()).toBe(200);
    const authBody = await auth.json() as Record<string, unknown>;
    expect(authBody.user_presence_confirmation_available).toBe(false);
    expect(typeof authBody.csrf_token).toBe("string");

    const liveness = await page.request.get("/v1/runtime-liveness");
    expect(liveness.status()).toBe(200);
    const livenessBody = await liveness.json() as {
      status: string;
      components: Array<{ configured: boolean; alive: boolean | null }>;
    };
    expect(livenessBody.status).toBe("ok");
    expect(livenessBody.components).toHaveLength(4);
    expect(livenessBody.components.every((item) => !item.configured || item.alive === true)).toBe(true);
  });

  test("reports the governed web-fetch schema while native-unavailable UI stays disabled", async ({ page }) => {
    const rail = await openAgent(page);
    const capabilityResponse = await page.request.get("/v1/agent/web-fetch-capability");
    expect(capabilityResponse.status()).toBe(200);
    expect(capabilityResponse.headers()["cache-control"]).toContain("no-store");
    const capability = await capabilityResponse.json() as Record<string, unknown>;
    expect(Object.keys(capability).sort()).toEqual([
      "available",
      "contract_version",
      "network_scope",
      "policy_version",
      "reason_code",
      "requires_per_fetch_approval",
    ]);
    expect(capability.contract_version).toBe("agent-web-fetch-capability.v1");
    expect(typeof capability.available).toBe("boolean");
    expect(capability.policy_version).toBe("governed-web-fetch.v1");
    expect(capability.reason_code).toBe(capability.available ? "available" : "governed_fetcher_unavailable");
    expect(capability.requires_per_fetch_approval).toBe(true);
    expect(capability.network_scope).toBe("public_https");

    const mutations: string[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.origin !== BASE_URL || ["GET", "HEAD", "OPTIONS"].includes(request.method())) return;
      if (!/^\/auth\/(session|csrf)$/u.test(url.pathname)) mutations.push(`${request.method()} ${url.pathname}`);
    });
    await selectProject(page, RECOVERY_PROJECT);
    await rail.getByRole("button", { name: "New chat", exact: true }).click();
    const setup = page.getByRole("dialog", { name: "New session", exact: true });
    await expect(setup).toBeVisible();
    const web = setup.getByRole("checkbox", { name: /Web fetch/i });
    await expect(web).toBeDisabled();
    await expect(web).not.toBeChecked();
    await expect(setup).toContainText(/native confirmation/i);
    expect(mutations).toEqual([]);
  });

  test("renders the truthful disconnected updater state from the real API", async ({ page }) => {
    await page.goto("/overview");
    const updates = page.getByRole("region", { name: "Software updates", exact: true });
    await expect(updates).toHaveAttribute("data-update-state", "unconfigured");
    const control = updates.getByRole("button");
    await expect(control).toContainText("Updates not connected");
    await expect(control).toBeEnabled();
    await control.click();
    await expect(updates.getByText("Updates are not connected. Checking, downloading, and installation remain off.", { exact: true })).toBeVisible();
    await expect(updates.getByLabel("Update actions").locator("button")).toHaveCount(0);
  });

    test("publishes the canonical v6 twenty-metric operability inventory", async ({ page }) => {
    await page.setViewportSize({ width: 900, height: 900 });
    await page.goto("/research/methods");
    await expect(page.getByRole("heading", { name: "What can produce measured evidence today" })).toBeVisible();
    await expect(page.getByText("All-20 release gate · metric-operability-v6", { exact: true })).toBeVisible();
    const summary = page.getByLabel("Metric operability summary");
    await expect(summary.getByText("Measured paths shipped").locator("..")).toContainText("18");
    await expect(summary.getByText("Need project profile").locator("..")).toContainText("0");
    await expect(summary.getByText("Need source adapter").locator("..")).toContainText("2");
    await expect(page.locator("[data-operability-state]")).toHaveCount(20);
    const action = page.locator('[data-operability-state="available_when_evidence_exists"]').filter({ hasText: "Requirement action traceability" });
    await expect(action).toContainText("complete compatible Claude transcript");
    await expect(action).toContainText("confirmed requirement plan");
    await expect(action).toContainText("reviewed requirement-action links with native confirmation");
    await expect(action).toContainText("Hook-only and incomplete histories are not admitted");
    await expect(action).toContainText(/traceability is not proof of task success/i);
    const verification = page.locator('[data-operability-state="available_when_evidence_exists"]').filter({ hasText: "Verified requirement coverage" });
    await expect(verification).toContainText("native-reviewed plan");
    await expect(verification).toContainText("observed check");
    await expect(verification).toContainText("fresh analysis");

    // Observe only the explicit UI refresh: this map is catalog metadata, not
    // a session/model operation, and the built application must request it
    // again rather than presenting a locally invented refresh state.
    const refreshRequests: Array<{ method: string; path: string }> = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.origin === BASE_URL) refreshRequests.push({ method: request.method(), path: url.pathname });
    });
    const refreshedCatalog = page.waitForResponse((response) => (
      response.request().method() === "GET"
      && new URL(response.url()).origin === BASE_URL
      && new URL(response.url()).pathname === "/v1/metric-contracts/v2/operability-catalog"
      && response.ok()
    ));
    await page.getByRole("button", { name: "Refresh metric map", exact: true }).click();
    await refreshedCatalog;
    await expect(page.getByRole("button", { name: "Refresh metric map", exact: true })).toBeVisible();
    expect(refreshRequests.filter((request) => request.path === "/v1/metric-contracts/v2/operability-catalog" && request.method === "GET")).toHaveLength(1);
    expect(refreshRequests.filter((request) => request.method === "POST")).toEqual([]);
    expect(refreshRequests.filter((request) => /\/(?:sessions?|local-models)(?:\/|$)/u.test(request.path))).toEqual([]);

    const response = await page.request.get("/v1/metric-contracts/v2/operability-catalog");
    expect(response.status()).toBe(200);
    const body = await response.json() as Record<string, unknown>;
    expect(body).toMatchObject({
      catalog_version: "metric-operability-v6",
      total_metric_count: 20,
      shipped_path_count: 18,
      task_profile_configuration_gap_count: 0,
      provider_adapter_gap_count: 2,
      model_authoritative_metric_count: 0,
    });
  });

  test("keeps the model registry empty and the shared runtime stopped", async ({ page }) => {
    await page.goto("/models");
    await expect(page.getByRole("heading", { level: 1, name: "Models" })).toBeVisible();
    await expect(page.getByText("No model yet. Add one below.", { exact: true })).toBeVisible();
    const response = await page.request.get("/v1/local-models");
    expect(response.status()).toBe(200);
    const body = await response.json() as { runtime_available: boolean; models: unknown[] };
    expect(body.runtime_available).toBe(false);
    expect(body.models).toEqual([]);
  });

  test("pages the real metadata-only analytics project catalog beyond its first 100 records", async ({ page }) => {
    const catalogRequests: string[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.origin === BASE_URL && url.pathname === "/v1/sessions") {
        catalogRequests.push(`${request.method()} ${url.search}`);
      }
    });
    await page.goto("/projects");
    await expect(page.getByRole("heading", { level: 1, name: "Projects", exact: true })).toBeVisible();
    await expect(page.getByRole("status", { name: "Loaded catalog coverage", exact: true })).toContainText("Loaded index coverage: 100 projects from 100 sessions.");
    expect(catalogRequests).toContain("GET ?limit=100&offset=0");
    // StrictMode may cancel its first development-like effect before the
    // request leaves loopback. Once the initial page is stable, the explicit
    // append must issue exactly one real second-page GET. The two CP34 Codex
    // fixtures add one project and two sessions beyond the 101 synthetic rows.
    catalogRequests.splice(0);
    await page.getByRole("button", { name: "Load next 100 sessions", exact: true }).click();
    await expect(page.getByRole("status", { name: "Loaded catalog coverage", exact: true })).toContainText("Loaded index coverage: 102 projects from 103 sessions.");
    await page.getByRole("searchbox").fill("Catalog page 101");
    await expect(page.getByText("Catalog page 101", { exact: true })).toBeVisible();
    expect(catalogRequests).toEqual(["GET ?limit=100&offset=100"]);

    await page.getByRole("searchbox").fill("");
    await page.getByRole("checkbox", {
      name: "Select Catalog page 001 for combined profile",
      exact: true,
    }).check();
    await expect(page.getByRole("complementary", {
      name: "Project aggregate selection",
      exact: true,
    })).toContainText("1 project selected");
    catalogRequests.splice(0);
    await page.getByRole("button", { name: "Reload catalog", exact: true }).click();
    await expect(page.getByRole("status", { name: "Loaded catalog coverage", exact: true })).toContainText("Loaded index coverage: 100 projects from 100 sessions.");
    await expect(page.getByRole("complementary", {
      name: "Project aggregate selection",
      exact: true,
    })).toHaveCount(0);
    expect(catalogRequests).toEqual(["GET ?limit=100&offset=0"]);
  });

  test("opens one real fictional project session catalog without broad catalog or analysis requests", async ({ page }) => {
    await page.goto("/overview");
    await expect(page.getByRole("heading", { name: "Overview", exact: true })).toBeVisible();
    await expect(page.getByLabel("Runtime status: Local loopback service available", { exact: true }))
      .toHaveAttribute("data-service-state", "available");
    const first = await page.evaluate(async () => {
      const response = await fetch("/v1/sessions?limit=100&offset=0");
      const body: unknown = await response.json();
      if (!response.ok || typeof body !== "object" || body === null || !Array.isArray((body as { sessions?: unknown }).sessions)) return null;
      return (body as { sessions: Array<{ project_id: string; project_display_name: string | null; session_display_name: string | null }> }).sessions[0] ?? null;
    });
    expect(first, "loopback provides a fictional metadata session").not.toBeNull();
    const requests: string[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.origin === BASE_URL && url.pathname.startsWith("/v1/")) {
        requests.push(`${request.method()} ${url.pathname}${url.search}`);
      }
    });
    await page.goto(`/projects/${first!.project_id}/sessions`);
    await expect(page.getByRole("heading", { name: first!.project_display_name ?? "Unnamed project", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Sessions", exact: true })).toBeVisible();
    await expect(page.getByText(first!.session_display_name ?? "Unnamed session", { exact: true })).toBeVisible();
    await expect(page.getByText("1 indexed session", { exact: true })).toBeVisible();
    expect(requests.filter((request) => request === `GET /v1/projects/${first!.project_id}/sessions?limit=100&offset=0`)).toHaveLength(1);
    expect(requests.some((request) => request.startsWith("GET /v1/sessions"))).toBe(false);
    expect(requests.some((request) => /analysis|runtime|metrics\/run/u.test(request))).toBe(false);
  });

  test("opens one scoped fictional session drilldown without broad or mutating reads", async ({ page }) => {
    await page.goto("/overview");
    await expect(page.getByRole("heading", { name: "Overview", exact: true })).toBeVisible();
    await expect(page.getByLabel("Runtime status: Local loopback service available", { exact: true }))
      .toHaveAttribute("data-service-state", "available");
    const first = await page.evaluate(async () => {
      const response = await fetch("/v1/sessions?limit=100&offset=0");
      const body: unknown = await response.json();
      if (!response.ok || typeof body !== "object" || body === null) return null;
      const session = (body as { sessions?: Array<unknown> }).sessions?.[0];
      if (typeof session !== "object" || session === null) return null;
      const value = session as { project_id?: unknown; session_id?: unknown };
      return typeof value.project_id === "string" && typeof value.session_id === "string"
        ? { project_id: value.project_id, session_id: value.session_id }
        : null;
    });
    expect(first, "loopback provides fictional drilldown metadata").not.toBeNull();
    expectedAbsencesByPage.set(
      page,
      [`${BASE_URL}/v1/sessions/${first!.session_id}/model-ensemble-runs/latest`],
    );
    const requests: string[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.origin === BASE_URL && url.pathname.startsWith("/v1/")) {
        requests.push(`${request.method()} ${url.pathname}${url.search}`);
      }
    });
    await page.goto(`/projects/${first!.project_id}/sessions/${first!.session_id}/metrics/tools`);
    await expect(page.getByText("No stored metrics in this category", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Cancel stored metrics loading", exact: true })).toHaveCount(0);
    // The radar card and the drilldown both read the one stored metric response.
    expect(requests.filter((request) => request === `GET /v1/sessions/${first!.session_id}/metrics`)).toHaveLength(2);
    expect(requests.filter((request) => request === `GET /v1/projects/${first!.project_id}/sessions?limit=100&offset=0`)).toHaveLength(1);
    expect(requests.some((request) => request.startsWith("GET /v1/sessions?"))).toBe(false);
    expect(requests.some((request) => /^(POST|PUT|PATCH|DELETE) /u.test(request))).toBe(false);
    expect(requests.some((request) => /\/runtime\/(start|load)|\/analysis\/(start|load)/u.test(request))).toBe(false);
  });

  test("shows a sealed fictional verification binding while native result actions remain unavailable", async ({ page }) => {
    expect(CP34_VERIFICATION_SESSION).toMatch(/^[a-f0-9]{64}$/u);
    expect(CP34_VERIFICATION_PROJECT).toMatch(/^[a-f0-9]{64}$/u);
    const protectedPosts: string[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (
        url.origin === BASE_URL
        && request.method() === "POST"
        && /\/requirement-verification-evidence\/(?:opportunity-sets\/[^/]+\/opportunities\/[^/]+(?:\/review|\/observed-checks\/[^/]+\/(?:review|issue))|acceptances)$/u.test(url.pathname)
      ) protectedPosts.push(url.pathname);
    });

    // This cold bootstrap has no optional experiment and no ephemeral
    // requirement-plan source-review context. Both are explicit absences.
    expectedAbsencesByPage.set(
      page,
      [
        `${BASE_URL}/v1/sessions/${CP34_VERIFICATION_SESSION}/model-link-experiments/latest`,
        `${BASE_URL}/v1/sessions/${CP34_VERIFICATION_SESSION}/requirement-plan-evidence/contract`,
      ],
    );

    await page.goto(`/projects/${CP34_VERIFICATION_PROJECT}/sessions/${CP34_VERIFICATION_SESSION}/metrics/prompt-quality`);
    const workspace = page.locator(".metric-workspace");
    await expect(workspace.getByRole("button", { name: /Evidence lane lens/i })).toBeVisible();
    await workspace.getByRole("button", { name: /Evidence lane lens/i }).click();
    await workspace.getByRole("button", { name: /Verified requirement coverage/i }).click();

    const evidence = page.locator(".requirement-verification-evidence");
    await expect(evidence.getByRole("heading", { name: "Requirement verification evidence" })).toBeVisible();
    await expect(evidence.getByRole("heading", { name: "Reviewed requirements" })).toBeVisible();
    await expect(evidence.getByText("Native confirmation is unavailable in this local session.", { exact: true })).toBeVisible();
    const exactRequirement = evidence.getByRole("button", { name: "Read exact requirement" }).first();
    await expect(exactRequirement).toBeDisabled();
    await expect(evidence.getByText("Native review is unavailable in this local session. No alternate result path is offered.", { exact: true })).toBeVisible();
    await expect(evidence.getByRole("button", { name: "Find eligible direct-pytest checks" }).first()).toBeEnabled();
    const planEvidence = page.locator(
      'section.requirement-plan-evidence[aria-label="Review requirement-to-plan evidence"]',
    );
    await expect(planEvidence.getByRole("alert")).toHaveText(
      "The saved sealed analysis is retained, but its source-review context is unavailable or expired. Start a fresh explicit analysis to review requirements again.",
    );
    await expect(planEvidence.getByRole("button", { name: "Retry exact source contract" })).toHaveCount(0);
    await expect(planEvidence.getByRole("button", { name: "Start guided authoring" })).toHaveCount(0);
    expect(protectedPosts, "native-protected mutations are not attempted while presence is unavailable").toEqual([]);
  });

  test("pages the real metadata-only session catalog only on explicit demand", async ({ page }) => {
    const catalogRequests: string[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.origin === BASE_URL && url.pathname === "/v1/sessions") {
        catalogRequests.push(`${request.method()} ${url.search}`);
      }
    });
    await page.goto("/sessions");
    await expect(page.getByRole("heading", { level: 1, name: "Sessions", exact: true })).toBeVisible();
    await expect(page.locator(".sessions-list > li")).toHaveCount(50);
    await expect(page.getByRole("status", { name: "Loaded session catalog coverage", exact: true })).toContainText("100 sessions");
    expect(catalogRequests).toEqual(["GET ?limit=100&offset=0"]);

    catalogRequests.splice(0);
    await page.getByRole("searchbox").fill("Catalog session 101");
    await expect(page.getByText("No matches in the loaded batch. Load more sessions or change the search or source filter.", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Load next 100 sessions", exact: true }).click();
    await expect(page.getByText("Catalog session 101", { exact: true })).toBeVisible();
    await expect(page.getByRole("status", { name: "Loaded session catalog coverage", exact: true })).toContainText("103 sessions");
    expect(catalogRequests).toEqual(["GET ?limit=100&offset=100"]);

    catalogRequests.splice(0);
    await page.getByRole("searchbox").fill("");
    await page.getByRole("button", { name: "Reload catalog", exact: true }).click();
    await expect(page.getByText("100 of 100 sessions", { exact: false })).toBeVisible();
    await expect(page.getByRole("status", { name: "Loaded session catalog coverage", exact: true })).toContainText("100 sessions");
    expect(catalogRequests).toEqual(["GET ?limit=100&offset=0"]);
  });

  test("opens a blank saved Agent setup from temporary Models chat without mutations", async ({ page }) => {
    const mutations: string[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.origin !== BASE_URL || ["GET", "HEAD", "OPTIONS"].includes(request.method())) return;
      if (/^\/auth\/(session|csrf)$/u.test(url.pathname)) return;
      mutations.push(`${request.method()} ${url.pathname}`);
    });
    await page.goto("/models");
    await expect(page.getByText(/temporary and is not saved/iu)).toBeVisible();
    await page.getByRole("button", { name: "Open saved Agent chat", exact: true }).click();
    const handoff = page.getByRole("dialog", { name: "Open a saved Agent chat?", exact: true });
    await expect(handoff).toContainText("NEW Agent setup");
    await handoff.getByRole("button", { name: "Continue to Agent", exact: true }).click();

    await expect(page).toHaveURL(/\/agent$/u);
    const setup = page.locator("#agent-new-chat-drawer");
    await expect(setup).toBeVisible();
    await expect(setup.getByRole("combobox", { name: "Agent model", exact: true })).toHaveValue("");
    await expect(setup.getByLabel("Workspace folder", { exact: true })).toHaveValue("");
    await expect(setup.getByRole("radio", { name: /^Save locally/u })).toBeChecked();
    await expect(setup.getByRole("button", { name: "Close new chat setup", exact: true })).toBeVisible();
    expect(mutations).toEqual([]);
    await setup.getByRole("button", { name: "Close new chat setup", exact: true }).click();
    await expect(setup).toBeHidden();
  });

  test("keeps or explicitly discards a synthetic Models draft without model calls", async ({ page }) => {
    const mutations: string[] = [];
    const requests: string[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.origin !== BASE_URL) return;
      const observed = `${request.method()} ${url.pathname}`;
      requests.push(observed);
      if (["GET", "HEAD", "OPTIONS"].includes(request.method())) return;
      if (/^\/auth\/(session|csrf)$/u.test(url.pathname)) return;
      mutations.push(observed);
    });

    await page.goto("/models");
    const composer = page.getByRole("textbox", { name: "Message", exact: true });
    await composer.fill("synthetic disposable draft");
    await expect(page.getByRole("button", { name: "Send", exact: true })).toBeDisabled();
    await page.getByRole("button", { name: "Overview", exact: true }).click();

    const keep = page.getByRole("dialog", { name: "Keep temporary Models chat?", exact: true });
    await expect(keep).toBeVisible();
    await expect(page.getByRole("dialog", { name: /unsaved changes/iu })).toHaveCount(0);
    await keep.getByRole("button", { name: "Keep temporary chat", exact: true }).click();
    await expect(page).toHaveURL(/\/models$/u);
    await expect(composer).toHaveValue("synthetic disposable draft");
    await expect(page.getByRole("dialog")).toHaveCount(0);

    await page.getByRole("button", { name: "Overview", exact: true }).click();
    const discard = page.getByRole("dialog", { name: "Keep temporary Models chat?", exact: true });
    await discard.getByRole("button", { name: "Discard temporary chat and continue", exact: true }).click();
    await expect(page).toHaveURL(/\/overview$/u);
    await expect(page.locator("[data-route='overview']")).toHaveCount(1);
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(mutations).toEqual([]);
    expect(requests.some((request) => /\/v1\/local-models\/[^/]+\/chat\/completions$/u.test(request))).toBe(false);
  });

  test("reopens retained synthetic history through real catalog and event routes", async ({ page }) => {
    await openAgent(page);
    await selectProject(page, RECOVERY_PROJECT);
    await selectChat(page, RECOVERY_CHAT);
    await expect(page.getByRole("heading", { level: 2, name: RECOVERY_CHAT })).toBeVisible();
    await expect(page.getByText("Synthetic retained request from the disposable gate.", { exact: true })).toBeVisible();
    await expect(page.getByText("Synthetic retained answer from the disposable gate.", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Resume chat", exact: true })).toBeEnabled();
  });

  test("searches the disposable retained message by POST, then jumps to its exact event without mutation", async ({ page }) => {
    const searches: Array<{ url: string; body: string | null }> = [];
    const mutations: string[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.pathname === "/v1/agent/catalog/sessions/message-search") {
        searches.push({ url: request.url(), body: request.postData() });
      }
      if (url.origin === BASE_URL && !["GET", "HEAD", "OPTIONS"].includes(request.method())
        && url.pathname !== "/v1/agent/catalog/sessions/message-search" && !/^\/auth\/(session|csrf)$/u.test(url.pathname)) mutations.push(`${request.method()} ${url.pathname}`);
    });
    const responses: string[] = [];
    page.on("response", (response) => {
      if (new URL(response.url()).pathname === "/v1/agent/catalog/sessions/message-search") responses.push(response.headers()["cache-control"] ?? "");
    });
    await openAgent(page);
    await selectProject(page, RECOVERY_PROJECT);
    await page.getByRole("button", { name: "Search saved messages", exact: true }).click();
    const search = page.getByRole("dialog", { name: "Search saved messages", exact: true });
    await search.getByLabel("Saved-message phrase", { exact: true }).fill("retained request");
    await search.getByRole("button", { name: "Search saved messages", exact: true }).click();
    await expect(search).toContainText(RECOVERY_CHAT);
    await search.getByRole("button", { name: /Open matching saved message/u }).click();
    await expect(page.getByText("Synthetic retained request from the disposable gate.", { exact: true })).toBeVisible();
    expect(searches).toHaveLength(1);
    expect(searches[0].url).not.toContain("retained");
    expect(JSON.parse(searches[0].body ?? "null")).toMatchObject({ query: "retained request", include_archived: false, limit: 20, offset: 0 });
    expect(responses).toEqual([expect.stringContaining("no-store")]);
    expect(mutations).toEqual([]);
    await expect(page.getByRole("button", { name: "Resume chat", exact: true })).toBeEnabled();
  });

  test("creates a durable Agent project and preserves it across reload", async ({ page }) => {
    const rail = await openAgent(page);
    await rail.getByRole("button", { name: "Create project", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Create project", exact: true });
    await dialog.getByLabel("Project name", { exact: true }).fill(PROJECT);
    await dialog.getByRole("button", { name: "Save", exact: true }).click();
    await expect(rail.getByText(PROJECT, { exact: true })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("navigation", { name: "Agent projects and chats", exact: true })
      .getByText(PROJECT, { exact: true })).toBeVisible();
  });

  test("opens model-neutral setup before any model exists", async ({ page }) => {
    const rail = await openAgent(page);
    await selectProject(page, PROJECT);
    await rail.getByRole("button", { name: "New chat", exact: true }).click();
    const setup = page.getByRole("dialog", { name: "New session", exact: true });
    await expect(setup.getByLabel("Agent model", { exact: true })).toHaveValue("");
    await expect(setup.getByLabel("Agent model", { exact: true }).locator("option")).toHaveCount(1);
    await expect(setup).toContainText("no model or session is required");
    await expect(setup.getByRole("button", { name: "Choose workspace to open chat", exact: true })).toBeDisabled();
    await setup.getByLabel("Workspace folder", { exact: true }).fill(WORKSPACE);
    await expect(setup.getByRole("button", { name: "Open read-only chat without model", exact: true })).toBeEnabled();
    await setup.getByRole("button", { name: "Close new chat setup", exact: true }).click();
  });

  test("creates a saved read-only chat without loading a model", async ({ page }) => {
    const rail = await openAgent(page);
    await selectProject(page, PROJECT);
    await rail.getByRole("button", { name: "New chat", exact: true }).click();
    const setup = page.getByRole("dialog", { name: "New session", exact: true });
    await setup.getByLabel("Workspace folder", { exact: true }).fill(WORKSPACE);
    await expect(setup.getByRole("radio", { name: /^Save locally/u })).toBeChecked();
    const protectedActions = setup.getByRole("group", { name: "Protected actions", exact: true });
    await expect(protectedActions).toHaveAttribute("disabled", "");
    await expect(protectedActions.getByRole("checkbox", { name: /^May write files/u })).toBeDisabled();
    await setup.getByRole("button", { name: "Open read-only chat without model", exact: true }).click();

    await expect(page.getByRole("heading", { level: 1, name: CHAT })).toBeVisible();
    await expect(page.getByRole("region", { name: "Agent conversation", exact: true }))
      .toContainText("Session created without a model");
    await expect(page.getByRole("textbox", { name: "Message to the agent", exact: true })).toBeEnabled();
    await expect(page.getByRole("button", { name: "Send", exact: true })).toBeDisabled();
    await page.reload();
    await selectProject(page, PROJECT);
    await expect(page.getByRole("navigation", { name: "Agent projects and chats", exact: true })
      .getByText(CHAT, { exact: true })).toBeVisible();
  });

  test("edits and rereads generation settings for a saved model-neutral chat", async ({ page }) => {
    await openAgent(page);
    await selectProject(page, PROJECT);
    await selectChat(page, CHAT);
    const composer = page.getByRole("form", { name: "Message composer", exact: true });
    await composer.getByLabel(/Choose or start model|Model and context settings/u).click();
    const runtime = composer.getByRole("dialog", { name: "Choose model and runtime settings", exact: true });
    const disclosure = runtime.locator("summary", { hasText: "Generation settings" });
    await expect(disclosure).toHaveCount(1);
    await disclosure.click();
    const settings = runtime.getByRole("group", { name: "Generation settings", exact: true });
    await settings.getByLabel("Generation max tokens").fill("2048");
    const parameterResponse = page.waitForResponse((response) => response.request().method() === "PUT" && /\/v1\/agent\/sessions\/[^/]+\/parameters$/u.test(new URL(response.url()).pathname) && response.ok()),
      saveAction = settings.getByRole("button", { name: "Save generation settings", exact: true }).click();
    const [savedResponse] = await Promise.all([parameterResponse, saveAction]);
    expect(await savedResponse.json()).toMatchObject({ settings: { parameters: { max_tokens: 2048 } } });
    await expect(settings.getByLabel("Generation max tokens")).toHaveValue("2048");
    await page.reload();
    await selectProject(page, PROJECT);
    await selectChat(page, CHAT);
    await page.getByRole("form", { name: "Message composer", exact: true })
      .getByLabel(/Model and context settings\./u).click();
    const reopened = page.getByRole("dialog", { name: "Choose model and runtime settings", exact: true });
    const reopenedDisclosure = reopened.locator("summary", { hasText: "Generation settings" });
    await expect(reopenedDisclosure).toHaveCount(1);
    await reopenedDisclosure.click();
    await expect(reopened.getByRole("group", { name: "Generation settings", exact: true })
      .getByLabel("Generation max tokens")).toHaveValue("2048");
  });

  test("reads the selected real workspace file without mutation authority", async ({ page }) => {
    await openAgent(page);
    await selectProject(page, PROJECT);
    await selectChat(page, CHAT);
    await page.getByRole("button", { name: "Files & review", exact: true }).click();
    const workspace = page.getByRole("region", { name: "Files and reviewed changes", exact: true });
    await workspace.getByRole("button", { name: "example.txt", exact: true }).click();
    const editor = workspace.getByRole("textbox", { name: "Workspace file editor", exact: true });
    await expect(editor).toHaveValue("EXAMPLE_WORKSPACE_OK\n");
    await editor.fill("EXAMPLE_WORKSPACE_OK\nUNAPPLIED_REVIEW_ONLY\n");
    await workspace.getByText("Find & go to line", { exact: true }).click();
    await workspace.getByRole("searchbox", { name: "Find in open file", exact: true }).fill("UNAPPLIED_REVIEW_ONLY");
    await workspace.getByRole("button", { name: "Find next", exact: true }).click();
    await expect(workspace.getByRole("status")).toHaveText("Match 1 of 1 selected.");
    expect(await editor.evaluate((element) => {
      const textarea = element as HTMLTextAreaElement;
      return textarea.value.slice(textarea.selectionStart, textarea.selectionEnd);
    })).toBe("UNAPPLIED_REVIEW_ONLY");
    await workspace.getByRole("spinbutton", { name: "Go to line", exact: true }).fill("2");
    await workspace.getByRole("button", { name: "Go to line", exact: true }).click();
    await expect(workspace.getByRole("status")).toHaveText("Line 2 selected.");
    expect(await editor.evaluate((element) => {
      const textarea = element as HTMLTextAreaElement;
      return textarea.value.slice(textarea.selectionStart, textarea.selectionEnd);
    })).toBe("UNAPPLIED_REVIEW_ONLY");
    await expect(editor).toHaveValue("EXAMPLE_WORKSPACE_OK\nUNAPPLIED_REVIEW_ONLY\n");
    await workspace.getByRole("button", { name: "Review diff", exact: true }).click();
    await expect(workspace.getByRole("button", { name: "Apply reviewed edit", exact: true })).toBeDisabled();

    await page.reload();
    await selectProject(page, PROJECT);
    await selectChat(page, CHAT);
    await page.getByRole("button", { name: "Files & review", exact: true }).click();
    const reopened = page.getByRole("region", { name: "Files and reviewed changes", exact: true });
    await reopened.getByRole("button", { name: "example.txt", exact: true }).click();
    await expect(reopened.getByRole("textbox", { name: "Workspace file editor", exact: true }))
      .toHaveValue("EXAMPLE_WORKSPACE_OK\n");
  });

  test("keeps model selection, context, review, and send controls truthful", async ({ page }) => {
    await openAgent(page);
    await selectProject(page, PROJECT);
    await selectChat(page, CHAT);
    const composer = page.getByRole("form", { name: "Message composer", exact: true });
    const modelFreeComposer = composer.getByRole("textbox", { name: "Message to the agent", exact: true });
    await expect(modelFreeComposer).toBeEnabled();
    await expect(composer.getByRole("button", { name: "Review prompt without sending", exact: true })).toBeDisabled();
    await modelFreeComposer.fill("EXAMPLE_MODEL_FREE_DRAFT");
    await expect(modelFreeComposer).toHaveValue("EXAMPLE_MODEL_FREE_DRAFT");
    await expect(composer.getByRole("button", { name: "Send", exact: true })).toBeDisabled();
    await expect(composer.getByRole("button", { name: "Review prompt without sending", exact: true })).toBeEnabled();
    await expect(composer.getByRole("button", { name: "Send", exact: true })).toBeDisabled();

    const sendRequestsBeforeShortcut = { count: 0 };
    page.on("request", (request) => {
      if (request.method() === "POST" && /\/agent\/sessions\/[^/]+\/messages$/u.test(new URL(request.url()).pathname)) {
        sendRequestsBeforeShortcut.count += 1;
      }
    });
    await modelFreeComposer.press("Control+Enter");
    await expect(modelFreeComposer).toHaveValue("EXAMPLE_MODEL_FREE_DRAFT");
    expect(sendRequestsBeforeShortcut.count).toBe(0);

    await composer.getByLabel(/Model and context settings\. Choose a model\./u).click();
    const runtime = composer.getByRole("dialog", { name: "Choose model and runtime settings", exact: true });
    await expect(runtime.getByLabel("Model", { exact: true })).toHaveValue("");
    await expect(runtime.getByRole("button", { name: "Start model", exact: true })).toBeDisabled();
    await expect(runtime.getByRole("button", { name: "Stop runtime", exact: true })).toBeDisabled();
    await expect(runtime).toContainText("Nothing is loaded until you apply the selection");
  });

  test("renames and pins the chat with durable revision checks", async ({ page }) => {
    await openAgent(page);
    await selectProject(page, PROJECT);
    await selectChat(page, CHAT);
    await page.getByRole("button", { name: `Chat actions for ${CHAT}`, exact: true }).click();
    await page.getByRole("dialog", { name: `Chat actions for ${CHAT}`, exact: true })
      .getByRole("button", { name: "Rename", exact: true }).click();
    const rename = page.getByRole("dialog", { name: "Rename chat", exact: true });
    await rename.getByLabel("Chat name", { exact: true }).fill(RENAMED_CHAT);
    await rename.getByRole("button", { name: "Save", exact: true }).click();
    await page.getByRole("button", { name: `Chat actions for ${RENAMED_CHAT}`, exact: true }).click();
    await page.getByRole("dialog", { name: `Chat actions for ${RENAMED_CHAT}`, exact: true })
      .getByRole("button", { name: "Pin", exact: true }).click();
    await page.getByRole("button", { name: `Chat actions for ${RENAMED_CHAT}`, exact: true }).click();
    await expect(page.getByRole("dialog", { name: `Chat actions for ${RENAMED_CHAT}`, exact: true })
      .getByRole("button", { name: "Unpin", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Close actions", exact: true }).click();

    await page.reload();
    await selectProject(page, PROJECT);
    await page.getByRole("button", { name: `Chat actions for ${RENAMED_CHAT}`, exact: true }).click();
    await expect(page.getByRole("dialog", { name: `Chat actions for ${RENAMED_CHAT}`, exact: true })
      .getByRole("button", { name: "Unpin", exact: true })).toBeVisible();
  });

  test("archives and restores an inactive retained chat", async ({ page }) => {
    await openAgent(page);
    await selectProject(page, RECOVERY_PROJECT);
    await page.getByRole("button", { name: `Chat actions for ${RECOVERY_CHAT}`, exact: true }).click();
    await page.getByRole("dialog", { name: `Chat actions for ${RECOVERY_CHAT}`, exact: true })
      .getByRole("button", { name: "Archive", exact: true }).click();
    await expect(page.getByRole("button", { name: `Chat actions for ${RECOVERY_CHAT}`, exact: true })).toHaveCount(0);

    await page.getByLabel("Show archived", { exact: true }).check();
    await page.getByRole("button", { name: `Chat actions for ${RECOVERY_CHAT}`, exact: true }).click();
    await page.getByRole("dialog", { name: `Chat actions for ${RECOVERY_CHAT}`, exact: true })
      .getByRole("button", { name: "Restore", exact: true }).click();
    await page.getByLabel("Show archived", { exact: true }).uncheck();
    await expect(page.getByRole("button", { name: `Chat actions for ${RECOVERY_CHAT}`, exact: true })).toBeVisible();
  });

  test("shows artifact truth from the real empty artifact repository", async ({ page }) => {
    await openAgent(page);
    await selectProject(page, RECOVERY_PROJECT);
    await selectChat(page, RECOVERY_CHAT);
    const artifacts = page.getByRole("region", { name: "Artifacts", exact: true });
    await expect(artifacts).toBeVisible();
    await expect(artifacts).toContainText("No verified workspace output is recorded in Active");
    await expect(artifacts.getByRole("tab", { name: "Active 0", exact: true })).toBeVisible();
  });

  test("reports exact project MCP state without contacting a registry", async ({ page }) => {
    await openLoopbackChat(page);
    await page.getByRole("button", { name: "Project tools", exact: true }).click();
    const settings = page.getByRole("dialog", { name: "Agent settings", exact: true });
    const projectTools = settings.locator("details.agent-mcp-project-tools");
    await expect(projectTools).toContainText("No admitted tools");
    await projectTools.locator("summary").click();
    await expect(projectTools).toContainText("Admitted plans0");
    await expect(projectTools).toContainText("Ready hosts0");
    await expect(projectTools).toContainText("Ready tools0");
    await expect(projectTools).toContainText("No MCP tool is currently routed into this chat project");
  });

  test("refreshes real Codex coverage once without mixing it with the synthetic catalog", async ({ page }) => {
    const coverageGets: string[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.origin === BASE_URL && url.pathname === "/v1/metric-coverage") {
        coverageGets.push(`${request.method()} ${url.search}`);
      }
    });
    await page.goto("/projects");
    await expect(page.getByRole("heading", { name: "Coaching metric coverage", exact: true })).toBeVisible();
    await expect(page.getByLabel("Coverage snapshot counts").getByText("Indexed sessions").locator("..").locator("dd"))
      .toHaveText("2");
    // The two fictional Codex records support CP34. They remain separate
    // from the 101 synthetic-provider catalog rows; only this explicit
    // control counts after the initial coverage read.
    coverageGets.splice(0);
    const refreshed = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return response.request().method() === "GET" && url.origin === BASE_URL
        && url.pathname === "/v1/metric-coverage" && url.searchParams.get("provider") === "codex"
        && response.ok();
    });
    await page.getByRole("button", { name: "Refresh coverage", exact: true }).click();
    await refreshed;
    await expect(
      page.getByRole("region", { name: "Coaching metric coverage", exact: true }).getByRole("status"),
    ).toContainText("Last verified snapshot. Refresh to check for newer data.");
    expect(coverageGets).toEqual(["GET ?provider=codex"]);
  });

  test("defers an optional Agent settings module until the settings surface opens", async ({ page }) => {
    const readinessAssets: string[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.origin === BASE_URL && /^\/assets\/AgentReadinessPanel-[\w-]+\.js$/u.test(url.pathname)) {
        readinessAssets.push(request.url());
      }
    });

    await openLoopbackChat(page);
    expect(readinessAssets, "the closed settings drawer did not fetch its built readiness module").toEqual([]);
    const deferredAsset = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.origin === BASE_URL
        && /^\/assets\/AgentReadinessPanel-[\w-]+\.js$/u.test(url.pathname);
    });

    await page.getByRole("button", { name: /Agent settings/ }).click();
    const requested = await deferredAsset;
    await expect(page.getByRole("dialog", { name: "Agent settings", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Agent capability readiness", exact: true })).toBeVisible();
    expect(new URL(requested.url()).pathname).toMatch(/^\/assets\/AgentReadinessPanel-[\w-]+\.js$/u);
    expect(readinessAssets).toHaveLength(1);
  });

  test("deletes an empty disposable project and leaves other projects intact", async ({ page }) => {
    const rail = await openAgent(page);
    await rail.getByRole("button", { name: "Create project", exact: true }).click();
    const create = page.getByRole("dialog", { name: "Create project", exact: true });
    await create.getByLabel("Project name", { exact: true }).fill(DISPOSABLE_PROJECT);
    await create.getByRole("button", { name: "Save", exact: true }).click();
    await page.getByRole("button", { name: `Project actions for ${DISPOSABLE_PROJECT}`, exact: true }).click();
    await page.getByRole("dialog", { name: `Project actions for ${DISPOSABLE_PROJECT}`, exact: true })
      .getByRole("button", { name: "Delete", exact: true }).click();
    await page.getByRole("dialog", { name: "Delete project", exact: true })
      .getByRole("button", { name: "Delete", exact: true }).click();
    await expect(rail.getByText(DISPOSABLE_PROJECT, { exact: true })).toHaveCount(0);
    await expect(rail.getByText(PROJECT, { exact: true })).toBeVisible();
  });

  test("keeps one authenticated SPA session across core deep links", async ({ page }) => {
    for (const [path, title] of [
      ["/projects", "Projects"],
      ["/sessions", "Sessions"],
      ["/analysis-jobs", "Analysis jobs"],
    ] as const) {
      const response = await page.goto(path);
      expect(response?.status()).toBe(200);
      await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
      await expect(page.getByLabel("Runtime status: Local loopback service available", { exact: true }))
        .toHaveAttribute("data-service-state", "available");
    }
  });
});
