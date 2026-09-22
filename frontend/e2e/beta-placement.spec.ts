import { expect, test, type Page } from "@playwright/test";

async function openRuntime(page: Page) {
  const runtime = page.getByRole("region", { name: "Shared local model runtime", exact: true });
  await runtime.getByLabel(/Model and context settings\./u).click();
  return runtime.getByRole("dialog", { name: "Choose model and runtime settings", exact: true });
}

async function resolveLivePlacement(page: Page): Promise<void> {
  await page.evaluate(() => window.dispatchEvent(new Event("synthetic-placement-resolve")));
}

test("live placement refusal keeps unsafe GPU choices unavailable at a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto("/e2e/fixtures/workflow-panels.html?panel=agent-placement&state=blocked");

  const runtime = await openRuntime(page);
  await expect(runtime.getByText("Checking verified placement admission. Apply stays disabled until it returns.")).toBeVisible();
  await expect(runtime.getByRole("button", { name: "Start model", exact: true })).toBeDisabled();

  await resolveLivePlacement(page);
  const evidence = runtime.getByText("Context, compatibility & runtime evidence", { exact: true });
  await evidence.click();
  const placement = runtime.getByRole("combobox", { name: "Model placement", exact: true });
  const gpu = placement.getByRole("option", { name: "GPU · unavailable", exact: true });
  const split = placement.getByRole("option", { name: "GPU + CPU · unavailable", exact: true });
  await expect(gpu).toHaveAttribute("disabled", "");
  await expect(gpu).toHaveJSProperty("disabled", true);
  await expect(split).toHaveAttribute("disabled", "");
  await expect(split).toHaveJSProperty("disabled", true);
  await expect(placement).toHaveValue("cpu");
  await expect(placement.getByRole("option", { name: "CPU", exact: true })).toHaveJSProperty("disabled", false);
  await expect(runtime.getByText(/Estimated weights, context and safety headroom exceed free VRAM/u)).toBeVisible();
  await expect(runtime.getByText(/No layer fits after context and safety headroom/u)).toBeVisible();
  await expect(runtime.getByRole("button", { name: "Start model", exact: true })).toBeEnabled();
  await expect(page.locator("html")).toHaveAttribute("data-agent-placement-starts", "0");

  const width = await page.evaluate(() => ({ content: document.documentElement.scrollWidth, viewport: document.documentElement.clientWidth }));
  expect(width.content).toBeLessThanOrEqual(width.viewport);
});

test("live placement failure remains blocked, then Refresh retries and recovers", async ({ page }) => {
  await page.goto("/e2e/fixtures/workflow-panels.html?panel=agent-placement&state=failure");

  const runtime = await openRuntime(page);
  await expect(runtime.getByText("Checking verified placement admission. Apply stays disabled until it returns.")).toBeVisible();
  await resolveLivePlacement(page);

  await expect(runtime.getByText("Placement admission could not be refreshed. Apply stays disabled; use Refresh to retry the check.")).toBeVisible();
  const apply = runtime.getByRole("button", { name: "Start model", exact: true });
  await expect(apply).toBeDisabled();
  await expect(apply).toHaveAccessibleDescription(/verified placement admission or retry/i);
  await runtime.getByText("Context, compatibility & runtime evidence", { exact: true }).click();
  await expect(runtime.getByText("Placement admission could not be refreshed; Apply stays disabled.")).toBeVisible();

  await runtime.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(runtime.getByText("Checking verified placement admission. Apply stays disabled until it returns.")).toBeVisible();
  await expect(apply).toBeDisabled();
  await resolveLivePlacement(page);

  await expect(runtime.getByText("Ready to start this model and bind it to this chat after startup succeeds.")).toBeVisible();
  await expect(runtime.getByText(/CPU execution is available without GPU offload/u)).toBeVisible();
  await expect(apply).toBeEnabled();
  await expect(page.locator("html")).toHaveAttribute("data-agent-placement-starts", "0");
});
