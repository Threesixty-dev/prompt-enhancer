import { expect, test, type Page } from "@playwright/test";

const diagnostics = new WeakMap<Page, { consoleErrors: number; pageErrors: number }>();

async function noOverflow(page: Page): Promise<void> {
  const size = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, viewport: document.documentElement.clientWidth }));
  expect(size.width).toBeLessThanOrEqual(size.viewport);
}

test.beforeEach(async ({ page }) => {
  const value = { consoleErrors: 0, pageErrors: 0 };
  diagnostics.set(page, value);
  page.on("console", (message) => { if (message.type() === "error") value.consoleErrors += 1; });
  page.on("pageerror", () => { value.pageErrors += 1; });
});

test.afterEach(async ({ page }) => {
  const value = diagnostics.get(page)!;
  expect(value.consoleErrors, "coverage fixture console errors").toBe(0);
  expect(value.pageErrors, "coverage fixture page errors").toBe(0);
});

test("refresh makes one new synthetic coverage read and replaces its count and timestamp", async ({ page }) => {
  await page.goto("/e2e/fixtures/coverage-recovery.html");
  await expect(page.getByText("2040-01-03T09:13:00Z", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Refresh coverage", exact: true }).click();
  await expect(page.getByText("2040-01-04T10:14:00Z", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Coverage snapshot counts").getByText("Indexed sessions").locator("..").locator("dd")).toHaveText("2");
  await expect(page.getByTestId("coverage-calls")).toContainText("Coverage GETs: 2");
});

test("failed and cancelled refreshes retain labelled previous coverage", async ({ page }) => {
  for (const mode of ["refresh-failure", "refresh-cancel"]) {
    await page.goto(`/e2e/fixtures/coverage-recovery.html?mode=${mode}`);
    await expect(page.getByRole("button", { name: "Refresh coverage", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Refresh coverage", exact: true }).click();
    if (mode === "refresh-cancel") await page.getByRole("button", { name: "Cancel coverage request", exact: true }).click();
    await expect(page.getByRole("status")).toContainText(/stale/i);
    await expect(page.getByLabel("Coverage snapshot counts").getByText("Indexed sessions").locator("..").locator("dd")).toHaveText("1");
    await page.getByRole("button", { name: "Retry coverage", exact: true }).click();
    await expect(page.getByText("2040-01-04T10:14:00Z", { exact: true })).toBeVisible();
    await expect(page.getByTestId("coverage-calls")).toContainText("Coverage GETs: 3");
  }
});

test("initial cancellation offers keyboard retry and remains responsive at narrow and desktop widths", async ({ page }) => {
  for (const width of [360, 1440]) {
    await page.setViewportSize({ width, height: 760 });
    await page.goto("/e2e/fixtures/coverage-recovery.html?mode=initial-cancel");
    await page.getByRole("button", { name: "Cancel coverage request", exact: true }).focus();
    await page.keyboard.press("Enter");
    const retry = page.getByRole("button", { name: "Retry coverage", exact: true });
    await retry.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { name: "Coaching metric coverage", exact: true })).toBeVisible();
    await page.getByText("Metric-by-metric counts", { exact: true }).click();
    const tableWrap = page.locator(".metric-coverage-panel__table-wrap");
    await expect(tableWrap.locator("table")).toBeVisible();
    const widths = await tableWrap.evaluate((element) => ({ client: element.clientWidth, scroll: element.scrollWidth }));
    expect(widths.scroll).toBeGreaterThanOrEqual(widths.client);
    await noOverflow(page);
  }
});
