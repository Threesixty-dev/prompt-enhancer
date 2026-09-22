import { expect, test } from "@playwright/test";

for (const width of [320, 1440]) {
  test(`runtime read recovery preserves draft and pending choices at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 720 });
    await page.goto("/e2e/fixtures/workflow-panels.html?panel=agent-runtime-recovery");

    const html = page.locator("html");
    const composer = page.getByRole("textbox", { name: "Message to the agent", exact: true });
    const draft = "Synthetic draft retained during a runtime status outage.";
    await composer.fill(draft);
    await expect(html).toHaveAttribute("data-runtime-recovery-starts", "0");
    await expect(html).toHaveAttribute("data-runtime-recovery-stops", "0");

    const runtime = page.getByRole("region", { name: "Shared local model runtime", exact: true });
    await expect(runtime).toContainText("Ready");
    const readsBeforeFailure = Number(await html.getAttribute("data-runtime-recovery-reads"));
    await runtime.getByLabel(/Model and context settings\./u).click();
    const dialog = runtime.getByRole("dialog", { name: "Choose model and runtime settings", exact: true });
    const modelSelect = dialog.getByRole("combobox", { name: "Model", exact: true });
    const placementSelect = dialog.getByRole("combobox", { name: "Model placement", exact: true });
    const contextSelect = dialog.getByRole("combobox", { name: "Context limit", exact: true });
    await modelSelect.selectOption("example-medium-split");
    await placementSelect.selectOption("cpu");
    await contextSelect.selectOption("4096");
    await expect(composer).toHaveValue(draft);
    await dialog.getByRole("button", { name: "Close model and context settings", exact: true }).click();
    await page.getByRole("button", { name: "Inject runtime read failure", exact: true }).click();
    // Reopen the explicitly dismissed chooser for the Refresh action that
    // exercises the failed read.
    await runtime.getByLabel(/Model and context settings\./u).click();
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "Refresh", exact: true }).click();
    await expect.poll(async () => Number(await html.getAttribute("data-runtime-recovery-reads"))).toBeGreaterThan(readsBeforeFailure);
    await expect(html).toHaveAttribute("data-runtime-recovery-starts", "0");
    await expect(html).toHaveAttribute("data-runtime-recovery-stops", "0");
    await expect(runtime.getByRole("alert")).toContainText("Runtime status is unavailable");
    await expect(runtime.getByLabel(/Model and context settings\./u)).toContainText("Status unverified");
    await expect(dialog.locator(".agent-runtime__decision-note")).toHaveAttribute("data-state", "blocked");
    await expect(runtime.getByLabel(/Model and context settings\./u)).toHaveAttribute("data-pending-selection", "true");
    await expect(dialog.getByRole("button", { name: /Switch model|Start model/u })).toBeDisabled();
    await expect(modelSelect).toHaveValue("example-medium-split");
    await expect(placementSelect).toHaveValue("cpu");
    await expect(contextSelect).toHaveValue("4096");
    await expect(composer).toHaveValue(draft);

    const readsAfterFailure = Number(await html.getAttribute("data-runtime-recovery-reads"));
    await dialog.getByRole("button", { name: "Refresh", exact: true }).click();
    await expect.poll(async () => Number(await html.getAttribute("data-runtime-recovery-reads"))).toBeGreaterThan(readsAfterFailure);
    await expect(dialog).not.toContainText("could not be refreshed");
    await expect(dialog.getByRole("button", { name: "Switch model", exact: true })).toBeEnabled();
    await expect(modelSelect).toHaveValue("example-medium-split");
    await expect(placementSelect).toHaveValue("cpu");
    await expect(contextSelect).toHaveValue("4096");
    await expect(composer).toHaveValue(draft);
    await dialog.getByRole("button", { name: "Switch model", exact: true }).click();
    await expect(html).toHaveAttribute("data-runtime-recovery-starts", "1");
    await expect(html).toHaveAttribute("data-runtime-recovery-last-start-alias", "example-medium-split");
    await expect(composer).toHaveValue(draft);
    await expect(html).toHaveAttribute("data-runtime-recovery-stops", "0");
    await expect(html).toHaveAttribute("data-runtime-recovery-sends", "0");
  });

  test(`runtime read recovery retains an exact last-confirmed Stop target at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 720 });
    await page.goto("/e2e/fixtures/workflow-panels.html?panel=agent-runtime-recovery");

    const html = page.locator("html");
    const composer = page.getByRole("textbox", { name: "Message to the agent", exact: true });
    await composer.fill("Synthetic draft retained for the exact Stop target.");
    const runtime = page.getByRole("region", { name: "Shared local model runtime", exact: true });
    const summary = runtime.getByLabel(/Model and context settings\./u);
    await summary.click();
    const dialog = runtime.getByRole("dialog", { name: "Choose model and runtime settings", exact: true });

    await dialog.getByRole("button", { name: "Close model and context settings", exact: true }).click();
    await page.getByRole("button", { name: "Inject runtime read failure", exact: true }).click();
    await summary.click();
    await dialog.getByRole("button", { name: "Refresh", exact: true }).click();
    await expect(runtime.getByRole("alert")).toContainText("Runtime status is unavailable");
    await expect(summary).toHaveAttribute("data-pending-selection", "false");
    await expect(dialog.getByRole("button", { name: /Switch model|Start model/u })).toBeDisabled();
    await expect(dialog.getByRole("button", { name: "Stop runtime", exact: true })).toBeEnabled();
    await expect(html).toHaveAttribute("data-runtime-recovery-starts", "0");
    await expect(html).toHaveAttribute("data-runtime-recovery-sends", "0");
    await expect(composer).toHaveValue("Synthetic draft retained for the exact Stop target.");

    await dialog.getByRole("button", { name: "Stop runtime", exact: true }).click();
    await expect(html).toHaveAttribute("data-runtime-recovery-stops", "1");
    await expect(html).toHaveAttribute("data-runtime-recovery-stop-alias", "example-small-cpu");
    await expect(html).toHaveAttribute("data-runtime-recovery-stop-revision", "7");
    await expect(html).toHaveAttribute("data-runtime-recovery-starts", "0");
    await expect(html).toHaveAttribute("data-runtime-recovery-sends", "0");
    await expect(composer).toHaveValue("Synthetic draft retained for the exact Stop target.");
  });
}

for (const width of [320, 1440]) {
  for (const contextMode of ["pending", "hung"] as const) {
    test(`exact context ${contextMode} timeout recovers only after explicit Refresh at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 720 });
      await page.clock.install();
      await page.goto(`/e2e/fixtures/workflow-panels.html?panel=agent-runtime-recovery&context=${contextMode}`);

      const html = page.locator("html");
      const runtime = page.getByRole("region", { name: "Shared local model runtime", exact: true });
      await expect(runtime).toContainText("Ready");
      await expect(html).toHaveAttribute("data-runtime-recovery-context-reads", "1");
      await expect(html).toHaveAttribute("data-runtime-recovery-starts", "0");
      await expect(html).toHaveAttribute("data-runtime-recovery-stops", "0");
      await expect(html).toHaveAttribute("data-runtime-recovery-sends", "0");

      await page.clock.runFor(1_000);
      const readsBeforeExpiry = Number(await html.getAttribute("data-runtime-recovery-context-reads"));
      if (contextMode === "pending") {
        expect(readsBeforeExpiry).toBeGreaterThan(1);
      } else {
        expect(readsBeforeExpiry).toBe(1);
      }
      await expect(runtime).not.toContainText("preflight did not settle");

      await page.clock.runFor(9_500);
      await expect(runtime).toContainText(/Exact context preflight did not settle within 10 seconds.*Refresh to retry/u);
      await expect(runtime).toHaveAttribute("aria-busy", "false");
      const readsAfterExpiry = Number(await html.getAttribute("data-runtime-recovery-context-reads"));
      await page.clock.runFor(5_000);
      await expect(html).toHaveAttribute("data-runtime-recovery-context-reads", String(readsAfterExpiry));

      await runtime.getByLabel(/Model and context settings\./u).click();
      const dialog = runtime.getByRole("dialog", { name: "Choose model and runtime settings", exact: true });
      await dialog.getByRole("button", { name: "Refresh", exact: true }).click();
      await expect(runtime).toContainText(/640 input.*4,096.*3,456 available.*turn 1/u);
      await expect(runtime).toContainText("Exact runtime preflight");
      await expect(runtime).not.toContainText("preflight did not settle");
      await expect(html).toHaveAttribute("data-runtime-recovery-context-reads", String(readsAfterExpiry + 1));
      await expect(html).toHaveAttribute("data-runtime-recovery-starts", "0");
      await expect(html).toHaveAttribute("data-runtime-recovery-stops", "0");
      await expect(html).toHaveAttribute("data-runtime-recovery-sends", "0");
    });
  }
}
