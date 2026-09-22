import { expect, test, type Page } from "@playwright/test";

async function noPageOverflow(page: Page): Promise<void> {
  const sizes = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(sizes.content, "The compact drafting journey must not create page overflow").toBeLessThanOrEqual(sizes.viewport);
}

test.describe("checkpoint 05 · model-independent drafting", () => {
  test("stopped model keeps a draft editable, blocks sends, then sends after explicit start", async ({ page }) => {
    await page.goto("/e2e/fixtures/workflow-panels.html?panel=agent-drafting&state=stopped");

    const composer = page.getByRole("textbox", { name: "Message to the agent", exact: true });
    const send = page.getByRole("button", { name: "Send", exact: true });
    const sessionId = await page.locator("html").getAttribute("data-drafting-session-id");
    expect(sessionId).toBe("a".repeat(32));
    await expect(composer).toBeEnabled();
    await expect(send).toBeDisabled();

    const draft = "Synthetic draft retained while the fictional model is stopped.";
    await composer.fill(draft);
    await composer.press("Control+Enter");
    await expect(send).toBeDisabled();
    await expect(composer).toHaveValue(draft);
    await expect(page.locator("html")).toHaveAttribute("data-drafting-manual-sends", "0");
    await expect(page.locator("html")).toHaveAttribute("data-drafting-runtime-starts", "0");

    const runtime = page.getByRole("region", { name: "Shared local model runtime", exact: true });
    await runtime.getByLabel(/Model and context settings\./u).click();
    const runtimeDialog = runtime.getByRole("dialog", { name: "Choose model and runtime settings", exact: true });
    await runtimeDialog.getByRole("button", { name: "Start model", exact: true }).click();
    await expect(page.locator("html")).toHaveAttribute("data-drafting-runtime-starts", "1");
    await expect(page.locator("html")).toHaveAttribute("data-drafting-bound-model-alias", "example-small-cpu");
    await expect(page.getByRole("region", { name: "Shared local model runtime", exact: true })).toContainText("Ready");
    await expect(composer).toHaveValue(draft);
    await expect(send).toBeEnabled();

    await send.click();
    await expect(page.getByText("Synthetic drafting response returned from the in-memory transport.", { exact: true })).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("data-drafting-manual-sends", "1");
    await expect(page.locator("html")).toHaveAttribute("data-drafting-last-send-session", sessionId!);
    await expect(page.locator("html")).toHaveAttribute("data-drafting-last-send-text", draft);
    await expect(composer).toHaveValue("");
    await noPageOverflow(page);
  });

  test("no-model chat preserves typing while choosing and starting a model in the runtime popover", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 720 });
    await page.goto("/e2e/fixtures/workflow-panels.html?panel=agent-drafting&state=no-model");

    await page.getByRole("textbox", { name: "Workspace folder", exact: true }).fill("D:\\example\\drafting");
    await page.getByRole("button", { name: /chat without model/u }).click();
    const composer = page.getByRole("textbox", { name: "Message to the agent", exact: true });
    const draft = "Synthetic no-model draft typed before runtime selection.";
    await composer.fill(draft);
    await expect(composer).toBeEnabled();
    await expect(page.getByRole("button", { name: "Send", exact: true })).toBeDisabled();
    await expect(page.locator("html")).toHaveAttribute("data-drafting-runtime-starts", "0");
    await expect(page.locator("html")).toHaveAttribute("data-drafting-manual-sends", "0");

    const runtime = page.getByRole("region", { name: "Shared local model runtime", exact: true });
    await runtime.getByLabel(/Model and context settings\./u).click();
    const dialog = runtime.getByRole("dialog", { name: "Choose model and runtime settings", exact: true });
    await dialog.getByRole("combobox", { name: "Model", exact: true }).selectOption("example-small-cpu");
    await expect(composer).toHaveValue(draft);
    await dialog.getByRole("button", { name: "Start model", exact: true }).click();
    await expect(page.locator("html")).toHaveAttribute("data-drafting-runtime-starts", "1");
    await expect(page.locator("html")).toHaveAttribute("data-drafting-bound-model-alias", "example-small-cpu");
    await expect(runtime).toContainText("Ready");
    await expect(composer).toHaveValue(draft);

    await dialog.getByRole("button", { name: "Close model and context settings", exact: true }).click();
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(page.getByText("Synthetic drafting response returned from the in-memory transport.", { exact: true })).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("data-drafting-last-send-session", "a".repeat(32));
    await expect(page.locator("html")).toHaveAttribute("data-drafting-last-send-text", draft);
    await expect(page.locator("html")).toHaveAttribute("data-drafting-manual-sends", "1");
    await noPageOverflow(page);
  });
});
