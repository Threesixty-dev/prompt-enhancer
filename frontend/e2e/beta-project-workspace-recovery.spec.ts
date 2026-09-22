import { expect, test, type Page } from "@playwright/test";

const FIXTURE = "/e2e/fixtures/project-workspace-recovery.html";
const diagnostics = new WeakMap<Page, { consoleErrors: number; pageErrors: number }>();

test.beforeEach(async ({ page }) => {
  const counts = { consoleErrors: 0, pageErrors: 0 };
  diagnostics.set(page, counts);
  page.on("console", (message) => { if (message.type() === "error") counts.consoleErrors += 1; });
  page.on("pageerror", () => { counts.pageErrors += 1; });
});
test.afterEach(async ({ page }) => {
  const counts = diagnostics.get(page)!;
  expect(counts.pageErrors, "fixture raised no page exceptions").toBe(0);
  expect(counts.consoleErrors, "fixture raised no console errors").toBe(0);
});
async function open(page: Page, mode: string) { await page.goto(`${FIXTURE}?mode=${mode}`); }
async function noOverflow(page: Page) { expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true); }
async function expectResolvedOlderSession(page: Page) {
  await expect(page.getByText("101 indexed sessions", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recovery session 101", exact: true })).toBeVisible();
}

test.describe("project workspace recovery", () => {
  test("cancels then retries the initial project session read", async ({ page }) => {
    await open(page, "initial");
    await page.getByRole("button", { name: "Cancel project session loading", exact: true }).click();
    await page.getByRole("button", { name: "Enable synthetic recovery", exact: true }).click();
    await page.getByRole("button", { name: "Retry project sessions", exact: true }).click();
    await expectResolvedOlderSession(page);
  });
  test("retries the rejected older page at offset 100 and resolves the selected session", async ({ page }) => {
    await open(page, "older-reject");
    await expect(page.getByRole("button", { name: "Retry older session lookup", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Enable synthetic recovery", exact: true }).click();
    await page.getByRole("button", { name: "Retry older session lookup", exact: true }).click();
    await expectResolvedOlderSession(page);
    await expect(page.locator("html")).toHaveAttribute("data-requests", "100:0,100:100,100:100");
  });
  test("cancels a hanging older lookup, then retries offset 100 without replaying page zero", async ({ page }) => {
    await open(page, "older-hang");
    await page.getByRole("button", { name: "Cancel older session lookup", exact: true }).click();
    await page.getByRole("button", { name: "Enable synthetic recovery", exact: true }).click();
    await page.getByRole("button", { name: "Retry older session lookup", exact: true }).click();
    await expectResolvedOlderSession(page);
    await expect(page.locator("html")).toHaveAttribute("data-requests", "100:0,100:100,100:100");
  });
  test("refreshes at offset zero after a malformed older total and resolves the new base", async ({ page }) => {
    await open(page, "older-malformed");
    await expect(page.getByRole("button", { name: "Refresh project sessions", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Enable synthetic recovery", exact: true }).click();
    await page.getByRole("button", { name: "Refresh project sessions", exact: true }).click();
    await expectResolvedOlderSession(page);
    await expect(page.locator("html")).toHaveAttribute("data-requests", "100:0,100:100,100:0,100:100");
  });
  for (const width of [360, 1440]) {
    test(`activates retry from the keyboard without overflow at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await open(page, "initial");
      await page.getByRole("button", { name: "Cancel project session loading", exact: true }).press("Enter");
      await page.getByRole("button", { name: "Enable synthetic recovery", exact: true }).click();
      const retry = page.getByRole("button", { name: "Retry project sessions", exact: true });
      await retry.focus(); await expect(retry).toBeFocused(); await retry.press("Enter");
      await expectResolvedOlderSession(page); await noOverflow(page);
    });
  }
});
