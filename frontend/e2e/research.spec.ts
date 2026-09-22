import { expect, test } from "@playwright/test";

test("shows the exact v6 all-twenty metric operability gate", async ({ page }) => {
  await page.goto("/research/methods");

  await expect(page.getByRole("heading", {
    name: "What can produce measured evidence today",
  })).toBeVisible();
  await expect(page.getByText("All-20 release gate · metric-operability-v6", { exact: true })).toBeVisible();
  const summary = page.getByLabel("Metric operability summary");
  await expect(summary.getByText("Measured paths shipped").locator("..")).toContainText("18");
  await expect(summary.getByText("Need project profile").locator("..")).toContainText("0");
  await expect(summary.getByText("Need source adapter").locator("..")).toContainText("2");
  await expect(summary.getByText("Model-authored metrics").locator("..")).toContainText("0");
  await expect(page.locator("[data-operability-state]")).toHaveCount(20);
  await expect(page.locator('[data-operability-state="available_when_evidence_exists"]')).toHaveCount(18);
  await expect(page.locator('[data-operability-state="task_profile_configuration_required"]')).toHaveCount(0);
  await expect(page.locator('[data-operability-state="provider_adapter_required"]')).toHaveCount(2);
  const action = page.locator('[data-operability-state="available_when_evidence_exists"]').filter({ hasText: "Requirement action traceability" });
  await expect(action).toContainText("complete compatible Claude transcript");
  await expect(action).toContainText("confirmed requirement plan");
  await expect(action).toContainText("reviewed requirement-action links with native confirmation");
  await expect(action).toContainText("Hook-only and incomplete histories are not admitted");
  await expect(action).toContainText(/traceability is not proof of task success/i);
  await expect(action).toContainText("No model estimate is used");
  const verification = page.locator('[data-operability-state="available_when_evidence_exists"]').filter({ hasText: "Verified requirement coverage" });
  await expect(verification).toContainText("native-reviewed plan");
  await expect(verification).toContainText("observed check");
  await expect(verification).toContainText("fresh analysis");
  await expect(page.getByText("Models never author measured values")).toBeVisible();
});

test("keeps the operability map readable at 360px", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 760 });
  await page.goto("/research/methods");
  await expect(page.getByRole("heading", {
    name: "What can produce measured evidence today",
  })).toBeVisible();

  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    document: document.documentElement.scrollWidth,
  }));
  expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport);
});
