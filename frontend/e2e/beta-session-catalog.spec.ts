import { expect, test, type Page } from "@playwright/test";

const FIXTURE = "/e2e/fixtures/session-catalog.html";
const runtimeErrors = new WeakMap<Page, { consoleErrors: number; pageErrors: number }>();

test.beforeEach(async ({ page }) => {
  const diagnostics = { consoleErrors: 0, pageErrors: 0 };
  runtimeErrors.set(page, diagnostics);
  page.on("console", (message) => {
    if (message.type() === "error") diagnostics.consoleErrors += 1;
  });
  page.on("pageerror", () => { diagnostics.pageErrors += 1; });
});

test.afterEach(async ({ page }) => {
  const diagnostics = runtimeErrors.get(page);
  expect(diagnostics, "fixture diagnostics were installed").toBeDefined();
  expect(diagnostics!.pageErrors, "fixture raised no page exception").toBe(0);
  expect(diagnostics!.consoleErrors, "fixture raised no console error").toBe(0);
});

async function open(page: Page, mode = "normal"): Promise<void> {
  await page.goto(`${FIXTURE}?mode=${mode}`);
  await expect(page.getByRole("heading", { level: 1, name: "Sessions", exact: true })).toBeVisible();
  await expect(page.getByText("100 of 100 sessions", { exact: false })).toBeVisible();
  await expect(page.getByRole("status", { name: "Loaded session catalog coverage", exact: true })).toContainText("100 sessions");
}

async function noOverflow(page: Page): Promise<void> {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
}

test.describe("session catalog paging", () => {
  test("loads only the first 100 initially, renders 50, and finds a later record only after Load next", async ({ page }) => {
    await open(page);
    await expect(page.locator(".sessions-list > li")).toHaveCount(50);
    await expect(page.getByRole("navigation", { name: "Stored session pages", exact: true })).toContainText("Showing 1–50 of 100");
    await expect(page.locator("html")).toHaveAttribute("data-session-catalog-requests", "primary:100:0");
    await page.getByRole("searchbox").fill("Session catalog 101");
    await expect(page.getByText("No matches in the loaded batch. Load more sessions or change the search or source filter.", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Load next 100 sessions", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Load next 100 sessions", exact: true }).click();
    await expect(page.getByText("Session catalog 101", { exact: true })).toBeVisible();
    await expect(page.getByRole("status", { name: "Loaded session catalog coverage", exact: true })).toContainText("101 sessions");
    await expect(page.locator("html")).toHaveAttribute("data-session-catalog-requests", "primary:100:0,primary:100:100");
  });

  test("filters the loaded catalog by provider without fetching another page", async ({ page }) => {
    await open(page);
    await page.getByRole("button", { name: "Claude Code", exact: true }).click();
    await expect(page.getByText("50 of 100", { exact: false })).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("data-session-catalog-requests", "primary:100:0");
    await expect(page.locator(".sessions-list > li")).toHaveCount(50);
  });

  test("retains page one through next-page failure and retries the exact offset", async ({ page }) => {
    await open(page, "page-failure");
    await page.getByRole("searchbox").fill("Session catalog 101");
    await page.getByRole("button", { name: "Load next 100 sessions", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText("More sessions could not be loaded");
    await expect(page.getByText("0 of 100", { exact: false })).toBeVisible();
    await page.getByRole("searchbox").fill("Session catalog 001");
    await expect(page.getByText("Session catalog 001", { exact: true })).toBeVisible();
    await page.getByRole("searchbox").fill("Session catalog 101");
    await page.getByRole("alert").getByRole("button", { name: "Retry next page", exact: true }).click();
    await expect(page.getByText("Session catalog 101", { exact: true })).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("data-session-catalog-requests", "primary:100:0,primary:100:100,primary:100:100");
  });

  test("cancels a delayed page without replacing loaded data", async ({ page }) => {
    await open(page, "slow-page");
    await page.getByRole("button", { name: "Load next 100 sessions", exact: true }).click();
    await page.getByRole("button", { name: "Cancel catalog request", exact: true }).click();
    await expect(page.locator("html")).toHaveAttribute("data-session-catalog-cancelled", "true");
    await page.getByRole("searchbox").fill("Session catalog 101");
    await expect(page.getByText("0 of 100", { exact: false })).toBeVisible();
    await expect(page.getByText("Session catalog 101", { exact: true })).toHaveCount(0);
  });

  test("fences prior filters and records when the catalog scope changes", async ({ page }) => {
    await open(page);
    await page.getByRole("button", { name: "Codex", exact: true }).click();
    await page.getByRole("button", { name: "Replace session catalog scope", exact: true }).click();
    await expect(page.getByText("Synthetic session scope: replacement", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "All sources", exact: true })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByText("Replacement scope 001", { exact: true })).toBeVisible();
    await expect(page.getByText("Session catalog 001", { exact: true })).toHaveCount(0);
  });

  for (const width of [360, 1440]) {
    test(`keeps paging keyboard-reachable without overflow at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await open(page);
      const load = page.getByRole("button", { name: "Load next 100 sessions", exact: true });
      await load.focus();
      await expect(load).toBeFocused();
      await load.press("Enter");
      await expect(page.getByText("101 of 101 sessions", { exact: false })).toBeVisible();
      await page.getByRole("searchbox").fill("Session catalog 101");
      await expect(page.getByText("Session catalog 101", { exact: true })).toBeVisible();
      await noOverflow(page);
    });
  }
});
