import { expect, test, type Page } from "@playwright/test";

async function noOverflow(page: Page): Promise<void> {
  const size = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, viewport: document.documentElement.clientWidth }));
  expect(size.width).toBeLessThanOrEqual(size.viewport);
}

test("recovers a failed initial metric-map GET by keyboard retry without other transport access", async ({ page }) => {
  await page.goto("/e2e/fixtures/metric-recovery.html");
  await expect(page.getByRole("alert")).toContainText("Metric operability could not be loaded");
  const retry = page.getByRole("button", { name: "Retry", exact: true });
  await retry.focus();
  await retry.press("Enter");
  await expect(page.getByRole("heading", { name: "What can produce measured evidence today", exact: true })).toBeVisible();
  await expect(page.getByTestId("metric-recovery-counters")).toContainText("Catalog GETs: 2 · Validated map: initial · Unexpected transport method accesses: 0");
});

test("retains the labelled last validated map when refresh fails, then replaces it on retry", async ({ page }) => {
  await page.goto("/e2e/fixtures/metric-recovery.html");
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(page.getByRole("button", { name: "Refresh metric map", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Refresh metric map", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Refresh failed; showing the last validated metric map.");
  await expect(page.getByTestId("metric-recovery-counters")).toContainText("Validated map: initial");
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(page.getByTestId("metric-recovery-counters")).toContainText("Catalog GETs: 4 · Validated map: refreshed · Unexpected transport method accesses: 0");
});

test("requires an app update for out-of-date metric definitions and does not invent zero values", async ({ page }) => {
  await page.goto("/e2e/fixtures/metric-recovery.html?state=out-of-date");
  await expect(page.getByRole("alert")).toContainText("Metric definitions are newer than this app");
  await expect(page.getByRole("alert")).toContainText("No session was read.");
  await expect(page.getByText("Measured paths shipped", { exact: true })).toHaveCount(0);
  await expect(page.getByTestId("metric-recovery-counters")).toContainText("Catalog GETs: 1 · Validated map: none · Unexpected transport method accesses: 0");
});

for (const width of [390, 1280]) {
  test(`metric recovery stays within the ${width}px viewport`, async ({ page }) => {
    await page.setViewportSize({ width, height: 720 });
    await page.goto("/e2e/fixtures/metric-recovery.html");
    await page.getByRole("button", { name: "Retry", exact: true }).click();
    await noOverflow(page);
  });
}
