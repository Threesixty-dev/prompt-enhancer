import { expect, test } from "@playwright/test";

async function openSettings(page: import("@playwright/test").Page, state = "ready", draft = ""): Promise<import("@playwright/test").Locator> {
  await page.goto(`/e2e/fixtures/workflow-panels.html?panel=agent-generation-settings&state=${state}`);
  await expect(page.getByRole("heading", { name: "Synthetic generation settings chat", level: 1 })).toBeVisible();
  if (draft) await page.getByRole("textbox", { name: "Message to the agent", exact: true }).fill(draft);
  await page.getByLabel(/Choose or start model|Model and context settings/u).click();
  const dialog = page.getByRole("dialog", { name: "Choose model and runtime settings", exact: true });
  await expect(dialog).toBeVisible();
  const disclosure = dialog.locator("summary", { hasText: "Generation settings" });
  await expect(disclosure).toHaveCount(1);
  await disclosure.click();
  return dialog;
}

test("edits idle model-neutral generation settings without sending or starting", async ({ page }) => {
  const dialog = await openSettings(page, "no-model", "Synthetic settings draft stays in place.");
  const settings = dialog.getByRole("group", { name: "Generation settings", exact: true });
  const composer = page.getByRole("textbox", { name: "Message to the agent", exact: true });
  const maxTokens = settings.getByLabel("Generation max tokens");
  const save = settings.getByRole("button", { name: "Save generation settings", exact: true });
  await maxTokens.fill("8192");
  await expect(settings.getByRole("button", { name: "Save generation settings", exact: true })).toBeEnabled();
  await maxTokens.press("Enter");
  await maxTokens.press("Control+Enter");
  await maxTokens.press("Meta+Enter");
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.generationSettingsSendAttempts)).toBe("0");
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.generationSettingsStartAttempts)).toBe("0");
  await maxTokens.fill("2048");
  await save.click();
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.generationSettingsSaves)).toBe("1");
  await expect(composer).toHaveValue("Synthetic settings draft stays in place.");
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.generationSettingsSendAttempts)).toBe("0");
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.generationSettingsStartAttempts)).toBe("0");
});

test("refuses a known-context budget before allowing an explicit lower save", async ({ page }) => {
  const dialog = await openSettings(page);
  const settings = dialog.getByRole("group", { name: "Generation settings", exact: true });
  await settings.getByLabel("Generation max tokens").fill("8192");
  await expect(settings).toHaveText(/must be below the 4,096-token context limit/u);
  await expect(settings.getByRole("button", { name: "Save generation settings", exact: true })).toBeDisabled();
  await settings.getByLabel("Generation max tokens").fill("2048");
  await settings.getByRole("button", { name: "Save generation settings", exact: true }).click();
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.generationSettingsSaves)).toBe("1");
});

test("preserves typed settings and draft after a revision conflict", async ({ page }) => {
  const dialog = await openSettings(page, "conflict", "Synthetic conflict draft.");
  const settings = dialog.getByRole("group", { name: "Generation settings", exact: true });
  const composer = page.getByRole("textbox", { name: "Message to the agent", exact: true });
  const maxTokens = settings.getByLabel("Generation max tokens");
  await expect(maxTokens).toHaveValue("1536");
  await settings.getByLabel("Generation thinking").check();
  await settings.getByRole("button", { name: "Save generation settings", exact: true }).click();
  await expect(settings).toHaveText(/could not be saved|conflict|changed|again/u);
  await expect(composer).toHaveValue("Synthetic conflict draft.");
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.generationSettingsAttempts)).toBe("1");
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.generationSettingsSaves)).toBe("0");
  await expect(settings.getByRole("button", { name: "Reload current settings", exact: true })).toBeVisible();
  await settings.getByRole("button", { name: "Reload current settings", exact: true }).click();
  await expect(maxTokens).toHaveValue("1536");
  await maxTokens.fill("2048");
  await settings.getByRole("button", { name: "Save generation settings", exact: true }).click();
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.generationSettingsSaves)).toBe("1");
  await expect(maxTokens).toHaveValue("2048");
});

test.describe("responsive settings editor", () => {
  for (const width of [320, 1440]) {
    test(`keeps settings keyboard reachable at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 720 });
      const dialog = await openSettings(page);
      const settings = dialog.getByRole("group", { name: "Generation settings", exact: true });
      const maxTokens = settings.getByLabel("Generation max tokens");
      const save = settings.getByRole("button", { name: "Save generation settings", exact: true });
      await maxTokens.focus();
      await expect(maxTokens).toBeFocused();
      await expect(save).toBeVisible();
      for (const control of [maxTokens, save]) {
        await control.scrollIntoViewIfNeeded();
        const box = await control.boundingBox();
        expect(box).not.toBeNull();
        expect(box!.x).toBeGreaterThanOrEqual(0);
        expect(box!.x + box!.width).toBeLessThanOrEqual(width);
      }
    });
  }
});
