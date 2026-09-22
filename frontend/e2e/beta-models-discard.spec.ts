import { expect, test, type Locator, type Page } from "@playwright/test";

const FIXTURE = "/e2e/fixtures/models-agent-handoff.html";

function counter(page: Page, name: string) {
  return page.locator("html").getAttribute(`data-handoff-${name.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)}`);
}

async function openModels(page: Page, width = 1440): Promise<void> {
  await page.setViewportSize({ width, height: 800 });
  await page.goto(`${FIXTURE}#/models`);
  await expect(page.locator("[data-route='models']")).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Message", exact: true })).toBeVisible();
}

function navigationDialog(page: Page) {
  return page.getByRole("dialog", { name: "Keep temporary Models chat?", exact: true });
}

async function createPartialReplyAndNextDraft(page: Page, nextDraft = "synthetic next draft"): Promise<Locator> {
  const composer = page.getByRole("textbox", { name: "Message", exact: true });
  await composer.fill("synthetic stream prompt");
  await composer.press("Control+Enter");
  await expect(page.getByText("Synthetic temporary reply.", { exact: true })).toBeVisible();
  await composer.fill(nextDraft);
  return composer;
}

async function expectTemporaryContent(page: Page, composer: Locator, nextDraft: string): Promise<void> {
  await expect(page.getByText("Synthetic temporary reply.", { exact: true })).toBeVisible();
  await expect(composer).toHaveValue(nextDraft);
  await expect.poll(() => counter(page, "streamAbort")).toBe("0");
}

test.describe("temporary Models chat navigation protection", () => {
  test("sidebar Overview keeps the partial reply and next draft until one explicit discard", async ({ page }) => {
    await openModels(page);
    const composer = await createPartialReplyAndNextDraft(page);

    await page.getByRole("button", { name: "Overview", exact: true }).click();
    const dialog = navigationDialog(page);
    await dialog.getByRole("button", { name: "Keep temporary chat", exact: true }).click();
    await expect(page).toHaveURL(/\/models$/u);
    await expectTemporaryContent(page, composer, "synthetic next draft");
    await expect(page.getByRole("button", { name: "Overview", exact: true })).toBeFocused();

    await page.getByRole("button", { name: "Overview", exact: true }).click();
    await navigationDialog(page).press("Escape");
    await expect(navigationDialog(page)).toHaveCount(0);
    await expect(page).toHaveURL(/\/models$/u);
    await expectTemporaryContent(page, composer, "synthetic next draft");

    await page.getByRole("button", { name: "Overview", exact: true }).click();
    await navigationDialog(page).getByRole("button", { name: "Discard temporary chat and continue", exact: true }).click();
    await expect(page).toHaveURL(/\/overview$/u);
    await expect(page.locator("[data-route='overview']")).toBeVisible();
    await expect.poll(() => counter(page, "streamAbort")).toBe("1");
    await expect(page.getByText("Synthetic temporary reply.", { exact: true })).toHaveCount(0);
    await expect(page.getByText("synthetic next draft", { exact: true })).toHaveCount(0);
  });

  test("Back keeps the dirty Models URL and history position, then confirms Overview", async ({ page }) => {
    await openModels(page);
    await page.getByRole("button", { name: "Overview", exact: true }).click();
    await expect(page).toHaveURL(/\/overview$/u);
    await page.getByRole("button", { name: "Models", exact: true }).click();
    await expect(page).toHaveURL(/\/models$/u);
    const composer = page.getByRole("textbox", { name: "Message", exact: true });
    await composer.fill("synthetic history draft");
    const historyLength = await page.evaluate(() => window.history.length);

    await page.goBack();
    await navigationDialog(page).getByRole("button", { name: "Keep temporary chat", exact: true }).click();
    await expect(page).toHaveURL(/\/models$/u);
    await expect(composer).toHaveValue("synthetic history draft");
    await expect(page.evaluate(() => window.history.length)).resolves.toBe(historyLength);

    await page.goBack();
    await navigationDialog(page).getByRole("button", { name: "Discard temporary chat and continue", exact: true }).click();
    await expect(page).toHaveURL(/\/overview$/u);
  });

  test("Forward is separately guarded after the Models draft becomes dirty", async ({ page }) => {
    await openModels(page);
    await page.getByRole("button", { name: "Overview", exact: true }).click();
    await expect(page).toHaveURL(/\/overview$/u);
    await page.goBack();
    await expect(page).toHaveURL(/\/models$/u);
    const composer = page.getByRole("textbox", { name: "Message", exact: true });
    await composer.fill("synthetic forward draft");

    await page.goForward();
    await navigationDialog(page).getByRole("button", { name: "Keep temporary chat", exact: true }).click();
    await expect(page).toHaveURL(/\/models$/u);
    await expect(composer).toHaveValue("synthetic forward draft");

    await page.goForward();
    await navigationDialog(page).getByRole("button", { name: "Discard temporary chat and continue", exact: true }).click();
    await expect(page).toHaveURL(/\/overview$/u);
  });

  test("New conversation keeps partial data through Cancel and Escape, then aborts once on confirmation", async ({ page }) => {
    await openModels(page, 360);
    const composer = await createPartialReplyAndNextDraft(page, "synthetic reset draft");
    const trigger = page.getByRole("button", { name: "New conversation", exact: true });
    const dialog = page.getByRole("dialog", { name: "Start a new conversation?", exact: true });

    await trigger.click();
    await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
    await expectTemporaryContent(page, composer, "synthetic reset draft");
    await expect(trigger).toBeFocused();

    await trigger.click();
    await dialog.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expectTemporaryContent(page, composer, "synthetic reset draft");
    await expect(trigger).toBeFocused();

    await trigger.click();
    await dialog.getByRole("button", { name: "Start new conversation", exact: true }).click();
    await expect(composer).toHaveValue("");
    await expect(page.getByText("Synthetic temporary reply.", { exact: true })).toHaveCount(0);
    await expect(page.getByText("synthetic reset draft", { exact: true })).toHaveCount(0);
    await expect.poll(() => counter(page, "streamAbort")).toBe("1");
  });

  for (const width of [360, 1440]) {
    test(`dismissed browser beforeunload at ${width}px preserves the temporary draft`, async ({ page }) => {
      await openModels(page, width);
      const composer = page.getByRole("textbox", { name: "Message", exact: true });
      const draft = `synthetic unload draft ${width}`;
      await composer.fill(draft);
      const fixtureIdentity = await counter(page, "createAgentSession");
      const beforeUnload = page.waitForEvent("dialog");
      await page.evaluate(() => {
        window.setTimeout(() => window.location.reload(), 0);
      });
      const dialog = await beforeUnload;
      expect(dialog.type()).toBe("beforeunload");
      await dialog.dismiss();
      await expect(page).toHaveURL(/\/models$/u);
      await expect(composer).toHaveValue(draft);
      await expect.poll(() => counter(page, "createAgentSession")).toBe(fixtureIdentity);

      await page.getByRole("button", { name: "New conversation", exact: true }).click();
      await page.getByRole("dialog", { name: "Start a new conversation?", exact: true })
        .getByRole("button", { name: "Start new conversation", exact: true }).click();
    });
  }

  test("clean Models navigation leaves without a discard dialog", async ({ page }) => {
    await openModels(page);
    await page.getByRole("button", { name: "Overview", exact: true }).click();
    await expect(page).toHaveURL(/\/overview$/u);
    await expect(navigationDialog(page)).toHaveCount(0);
  });

  test("an unindexed foreign history attempt keeps the chat and Return to Models recovers without rewriting that entry", async ({ page }) => {
    await openModels(page);
    const composer = page.getByRole("textbox", { name: "Message", exact: true });
    await composer.fill("synthetic foreign history draft");
    await page.evaluate(() => {
      window.history.pushState({ fixtureForeign: "synthetic-route" }, "", "/overview");
      window.dispatchEvent(new PopStateEvent("popstate", { state: window.history.state }));
    });

    const dialog = navigationDialog(page);
    await expect(dialog).toContainText(/cannot be restored automatically/u);
    await expect(composer).toHaveValue("synthetic foreign history draft");
    await expect(page.evaluate(() => window.history.state)).resolves.toMatchObject({ fixtureForeign: "synthetic-route" });
    await dialog.getByRole("button", { name: "Return to Models", exact: true }).click();
    await expect(page).toHaveURL(/\/models$/u);
    await expect(composer).toHaveValue("synthetic foreign history draft");
  });
});
