import { expect, test, type Page } from "@playwright/test";

const FIXTURE = "/e2e/fixtures/project-catalog.html";

async function open(page: Page, mode = "normal"): Promise<void> {
  await page.goto(`${FIXTURE}?mode=${mode}`);
  await expect(page.getByRole("heading", { level: 1, name: "Projects", exact: true })).toBeVisible();
  await expect(page.getByRole("status", { name: "Loaded catalog coverage", exact: true })).toContainText("Loaded index coverage: 100 projects from 100 sessions.");
}

async function noOverflow(page: Page): Promise<void> {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
}

test.describe("project catalog paging", () => {
  test("loads beyond the first 100 and keeps a selected project through append and filtering", async ({ page }) => {
    await open(page);
    const selected = page.getByRole("checkbox", { name: "Select Catalog page 001 for combined profile", exact: true });
    await selected.check();
    await page.getByRole("searchbox").fill("Catalog page 101");
    await expect(page.getByRole("heading", { name: "No matching projects", exact: true })).toBeVisible();
    await expect(page.getByText("No matches in the loaded index. Load the next page or try a different local label.", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Load next 100 sessions", exact: true }).click();
    await expect(page.getByText("Catalog page 101", { exact: true })).toBeVisible();
    await expect(page.getByRole("status", { name: "Loaded catalog coverage", exact: true })).toContainText("Loaded index coverage: 101 projects from 101 sessions.");
    await expect(page.getByRole("complementary", { name: "Project aggregate selection", exact: true })).toContainText("1 hidden by the current filter");
    await page.getByRole("searchbox").fill("");
    await expect(selected).toBeChecked();
    await expect(page.locator("html")).toHaveAttribute("data-catalog-requests", /0:100:0,0:100:100/);
  });

  test("is honest about next-page failure and retries without replacing loaded records", async ({ page }) => {
    await open(page, "page-failure");
    await page.getByRole("searchbox").fill("Catalog page 101");
    await page.getByRole("button", { name: "Load next 100 sessions", exact: true }).click();
    const failure = page.getByRole("alert");
    await expect(failure).toContainText("More catalog data needs attention");
    await expect(page.getByRole("status", { name: "Loaded catalog coverage", exact: true })).toContainText("Loaded index coverage: 100 projects from 100 sessions.");
    await page.getByRole("searchbox").fill("Catalog page 001");
    await expect(page.getByText("Catalog page 001", { exact: true })).toBeVisible();
    await expect(page.getByText("Catalog page 101", { exact: true })).toHaveCount(0);
    await page.getByRole("searchbox").fill("Catalog page 101");
    await failure.getByRole("button", { name: "Retry next page", exact: true }).click();
    await expect(page.getByText("Catalog page 101", { exact: true })).toBeVisible();
    await expect(page.getByRole("status", { name: "Loaded catalog coverage", exact: true })).toContainText("End of the current index reached. Reload catalog to refresh it.");
  });

  test("cancels a pending page without presenting unreceived records", async ({ page }) => {
    await open(page, "slow-page");
    await page.getByRole("button", { name: "Load next 100 sessions", exact: true }).click();
    await expect(page.getByRole("button", { name: "Cancel catalog request", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Cancel catalog request", exact: true }).click();
    await expect(page.locator("html")).toHaveAttribute("data-catalog-cancelled", "true");
    await expect(page.getByText("Catalog page 101", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("status", { name: "Loaded catalog coverage", exact: true })).toContainText("Loaded index coverage: 100 projects from 100 sessions.");
  });

  test("clears a scoped selection when its catalog transport is replaced", async ({ page }) => {
    await open(page);
    const selected = page.getByRole("checkbox", { name: "Select Catalog page 001 for combined profile", exact: true });
    await selected.check();
    await expect(page.getByRole("complementary", { name: "Project aggregate selection", exact: true })).toContainText("1 project selected");
    await page.getByRole("button", { name: "Replace catalog transport", exact: true }).click();
    await expect(page.getByText("Synthetic catalog transport revision 1", { exact: true })).toBeVisible();
    await expect(page.getByRole("complementary", { name: "Project aggregate selection", exact: true })).toHaveCount(0);
    await expect(selected).not.toBeChecked();
  });

  for (const width of [360, 1440]) {
    test(`keeps catalog paging and keyboard controls reachable at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await open(page);
      const loadMore = page.getByRole("button", { name: "Load next 100 sessions", exact: true });
      await loadMore.focus();
      await expect(loadMore).toBeFocused();
      await page.getByRole("searchbox").fill("Catalog page 101");
      await loadMore.focus();
      await expect(loadMore).toBeFocused();
      await loadMore.press("Enter");
      await expect(page.getByText("Catalog page 101", { exact: true })).toBeVisible();
      await noOverflow(page);
    });
  }
});
