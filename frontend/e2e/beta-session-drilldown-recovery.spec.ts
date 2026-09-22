import { expect, test, type Page } from "@playwright/test";

const FIXTURE = "/e2e/fixtures/session-drilldown-recovery.html";
const diagnostics = new WeakMap<Page, { consoleErrors: number; pageErrors: number }>();

test.beforeEach(async ({ page }) => {
  const counts = { consoleErrors: 0, pageErrors: 0 };
  diagnostics.set(page, counts);
  page.on("console", (message) => { if (message.type() === "error") counts.consoleErrors += 1; });
  page.on("pageerror", () => { counts.pageErrors += 1; });
});

test.afterEach(async ({ page }) => {
  const counts = diagnostics.get(page)!;
  expect(counts.consoleErrors, "drilldown fixture console errors").toBe(0);
  expect(counts.pageErrors, "drilldown fixture page errors").toBe(0);
});
async function open(page: Page, mode = "metrics") { await page.goto(`${FIXTURE}?mode=${mode}`); }
async function legacy(page: Page) { await page.getByText("Optional legacy view", { exact: true }).click(); }
async function noOverflow(page: Page) { expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true); }

test.describe("session drilldown recovery", () => {
  test("cancels and keyboard-retries stored metrics", async ({ page }) => {
    await open(page); await page.getByRole("button", { name: "Cancel stored metrics loading", exact: true }).click();
    await page.getByRole("button", { name: "Enable drilldown recovery", exact: true }).click();
    await page.getByRole("button", { name: "Retry stored metrics", exact: true }).press("Enter");
    await expect(page.getByText("No stored metrics in this category", { exact: true })).toBeVisible();
  });
  test("defers both legacy reads until disclosure", async ({ page }) => {
    await open(page, "both"); await expect(page.getByText("Optional legacy view", { exact: true })).toBeVisible();
    await expect(page.locator("html")).not.toHaveAttribute("data-quality-reads", /./);
    await expect(page.locator("html")).not.toHaveAttribute("data-readiness-reads", /./); await legacy(page);
    await expect(page.getByRole("button", { name: "Cancel quality loading", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Cancel readiness loading", exact: true })).toBeVisible();
  });
  test("preserves saved quality through readiness recovery", async ({ page }) => {
    await open(page, "readiness-fail"); await legacy(page);
    await expect(page.getByText("Coherent metric pack v3", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Enable drilldown recovery", exact: true }).click();
    await page.getByRole("button", { name: "Retry readiness", exact: true }).click();
    await expect(page.getByText("Coherent metric pack v3", { exact: true })).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("data-quality-reads", "1");
    await expect(page.locator("html")).toHaveAttribute("data-readiness-reads", "2");
  });
  test("cancels pending readiness without hiding the ready quality profile", async ({ page }) => {
    await open(page, "readiness"); await legacy(page);
    await expect(page.getByText("Coherent metric pack v3", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Cancel readiness loading", exact: true }).press("Enter");
    await expect(page.getByRole("button", { name: "Retry readiness", exact: true })).toBeVisible();
    await expect(page.getByText("Coherent metric pack v3", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Enable drilldown recovery", exact: true }).click();
    await page.getByRole("button", { name: "Retry readiness", exact: true }).press("Enter");
    await expect(page.locator("html")).toHaveAttribute("data-quality-reads", "1");
    await expect(page.locator("html")).toHaveAttribute("data-readiness-reads", "2");
    await expect(page.getByRole("button", { name: "Retry readiness", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Cancel readiness loading", exact: true })).toHaveCount(0);
  });
  test("recovers quality without leaving retry or loading state", async ({ page }) => {
    await open(page, "quality"); await legacy(page);
    await page.getByRole("button", { name: "Cancel quality loading", exact: true }).click();
    await page.getByRole("button", { name: "Enable drilldown recovery", exact: true }).click();
    await page.getByRole("button", { name: "Retry quality loading", exact: true }).click();
    await expect(page.getByText("Coherent metric pack v3", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Retry quality loading", exact: true })).toHaveCount(0);
  });
  test("times out quality after fifteen seconds and retries to a coherent profile", async ({ page }) => {
    await page.clock.install();
    await open(page, "quality");
    await legacy(page);
    await expect(page.locator("html")).toHaveAttribute("data-quality-reads", "1");
    await expect(page.locator("html")).toHaveAttribute("data-readiness-reads", "1");
    await page.clock.runFor(15_000);
    await expect(page.getByRole("button", { name: "Retry quality loading", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Enable drilldown recovery", exact: true }).click();
    await page.getByRole("button", { name: "Retry quality loading", exact: true }).click();
    await expect(page.getByText("Coherent metric pack v3", { exact: true })).toBeVisible();
  });
  for (const width of [360, 1440]) test(`activates stored metric recovery at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 }); await open(page);
    await page.getByRole("button", { name: "Cancel stored metrics loading", exact: true }).press("Enter");
    await page.getByRole("button", { name: "Enable drilldown recovery", exact: true }).click();
    await page.getByRole("button", { name: "Retry stored metrics", exact: true }).press("Enter");
    await expect(page.getByText("No stored metrics in this category", { exact: true })).toBeVisible(); await noOverflow(page);
  });
});
