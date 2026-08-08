import { expect, test } from "@playwright/test";

test("reviews synthetic discovery and inspects generic metrics", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Discovery inbox" })).toBeVisible();
  await expect(page.getByText("Local - synthetic data")).toBeVisible();
  await expect(page.getByRole("button", { name: /Candidate aaaaaa/ })).toBeVisible();
  await expect(page.getByLabel("2 candidates need review")).toBeVisible();

  await page.getByRole("combobox", { name: "Task category" }).selectOption("feature_implementation");
  await page.getByRole("button", { name: "Accept as one task" }).click();
  await expect(page.getByLabel("1 candidate needs review")).toBeVisible();
  await page.getByRole("button", { name: "Analyze task" }).click();
  await expect(page.getByRole("heading", { name: "Feature Implementation" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Workflow Session Count" })).toBeVisible();
  await expect(page.getByText("3 count", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Verification Pass Rate" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Usage Input Tokens" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Analysis provenance" })).toBeVisible();
});

for (const width of [900, 600]) {
  test(`keeps the discovery workspace within a ${width}px viewport`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Discovery inbox" })).toBeVisible();

    const dimensions = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      document: document.documentElement.scrollWidth,
    }));
    expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport);
  });
}
