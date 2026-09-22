import { expect, test, type Page } from "@playwright/test";

const FIXTURE = "/e2e/fixtures/agent-exit-refresh.html";
const PRIMARY = "Synthetic idle Agent";
const SECONDARY = "Synthetic second Agent";

function counter(page: Page, name: "delete" | "live-sessions") {
  return page.locator("html").getAttribute(`data-agent-refresh-${name}`);
}

async function openAgent(page: Page, close = "success") {
  await page.goto(`${FIXTURE}?close=${close}&fallback=1`);
  await expect(page.locator("[data-route='agent']")).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Message to the agent", exact: true })).toBeVisible();
}

async function selectChat(page: Page, title: string) {
  const chat = page.getByRole("button", { name: new RegExp(`^${title} ·`, "u") });
  if (!(await chat.isVisible())) {
    const expand = page.getByRole("button", { name: "Expand projects and chats", exact: true });
    await expect(expand).toBeVisible();
    await expand.click();
  }
  await chat.click();
  await expect(page.getByRole("textbox", { name: "Message to the agent", exact: true })).toBeVisible();
}

async function requestClose(page: Page, title: string) {
  await page.getByRole("button", { name: `Close session ${title}`, exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Close live chat?", exact: true });
  await expect(dialog).toBeVisible();
  return dialog;
}

async function navigateOverview(page: Page) {
  const trigger = page.getByRole("button", { name: "Overview", exact: true });
  if (await trigger.isVisible()) {
    await trigger.click();
    return;
  }
  await page.getByRole("button", { name: "Open navigation", exact: true }).click();
  await page.getByRole("dialog", { name: "Navigate Prompt Enhancer", exact: true })
    .getByRole("button", { name: "Overview", exact: true }).click();
}

function exitGuard(page: Page) {
  return page.getByRole("dialog", { name: "Keep Agent changes?", exact: true });
}

test.describe("Agent close discards only the closed chat draft", () => {
  test("pointer close treats authoritative absence as success and does not leave a false exit guard", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openAgent(page, "404");
    const composer = page.getByRole("textbox", { name: "Message to the agent", exact: true });

    await selectChat(page, SECONDARY);
    await composer.fill("synthetic draft to close");
    await selectChat(page, PRIMARY);
    await expect(composer).toHaveValue("");

    const dialog = await requestClose(page, SECONDARY);
    await expect(dialog).toContainText("unsent draft");
    await dialog.getByRole("button", { name: "Close chat", exact: true }).click();
    await expect.poll(() => counter(page, "delete")).toBe("1");
    await expect.poll(() => counter(page, "live-sessions")).toBe("1");
    await expect(page.getByRole("button", { name: `Close session ${SECONDARY}`, exact: true })).toHaveCount(0);

    await navigateOverview(page);
    await expect(page).toHaveURL(/\/overview$/u);
    await expect(exitGuard(page)).toHaveCount(0);
  });

  test("keyboard cancellation keeps the noncurrent draft protected at mobile width", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 844 });
    await openAgent(page);
    const composer = page.getByRole("textbox", { name: "Message to the agent", exact: true });

    await selectChat(page, SECONDARY);
    await composer.fill("synthetic retained second draft");
    await selectChat(page, PRIMARY);
    const close = page.getByRole("button", { name: `Close session ${SECONDARY}`, exact: true });
    if (!(await close.isVisible())) {
      await page.getByRole("button", { name: "Expand projects and chats", exact: true }).click();
    }
    await close.focus();
    await expect(close).toBeFocused();
    await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog", { name: "Close live chat?", exact: true });
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "Keep current state", exact: true }).press("Enter");
    await expect(dialog).toHaveCount(0);
    await expect.poll(() => counter(page, "delete")).toBe("0");

    await navigateOverview(page);
    await expect(exitGuard(page)).toBeVisible();
    await exitGuard(page).getByRole("button", { name: "Keep Agent changes", exact: true }).press("Enter");
    await expect(page).toHaveURL(/\/agent$/u);
    await selectChat(page, SECONDARY);
    await expect(composer).toHaveValue("synthetic retained second draft");
  });

  test("a row-local failed close retains its draft, then retry clears only that chat", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openAgent(page, "fail-once");
    const composer = page.getByRole("textbox", { name: "Message to the agent", exact: true });

    await selectChat(page, SECONDARY);
    await composer.fill("synthetic failed-close draft");
    await selectChat(page, PRIMARY);
    const dialog = await requestClose(page, SECONDARY);
    await dialog.getByRole("button", { name: "Close chat", exact: true }).click();
    await expect.poll(() => counter(page, "delete")).toBe("1");
    await expect.poll(() => counter(page, "live-sessions")).toBe("2");
    const close = page.getByRole("button", { name: `Close session ${SECONDARY}`, exact: true });
    const targetRow = close.locator("xpath=..");
    await expect(targetRow.getByRole("alert")).toHaveText("Close was not confirmed. Its draft was kept. Try closing this chat again.");
    await expect(composer).toHaveValue("");
    await expect(page.getByText("The session could not be closed.", { exact: true })).toHaveCount(0);

    await composer.fill("synthetic other-chat draft");
    const retryDialog = await requestClose(page, SECONDARY);
    await retryDialog.getByRole("button", { name: "Close chat", exact: true }).click();
    await expect.poll(() => counter(page, "delete")).toBe("2");
    await expect.poll(() => counter(page, "live-sessions")).toBe("1");
    await expect(close).toHaveCount(0);

    await navigateOverview(page);
    await expect(exitGuard(page)).toBeVisible();
    await exitGuard(page).getByRole("button", { name: "Keep Agent changes", exact: true }).click();
    await expect(composer).toHaveValue("synthetic other-chat draft");
  });

  test("a pending close locks only its chat's edits, remains copyable, and unlocks on failure", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openAgent(page, "deferred");
    const composer = page.getByRole("textbox", { name: "Message to the agent", exact: true });

    await composer.fill("synthetic pending-close draft");
    const dialog = await requestClose(page, PRIMARY);
    await dialog.getByRole("button", { name: "Close chat", exact: true }).click();
    await expect.poll(() => counter(page, "delete")).toBe("1");
    await expect(composer).toHaveJSProperty("readOnly", true);
    await expect(composer).toBeEnabled();
    await composer.selectText();
    await page.keyboard.press("Control+C");
    await expect(composer).toHaveJSProperty("selectionStart", 0);
    await expect(composer).toHaveJSProperty("selectionEnd", "synthetic pending-close draft".length);

    await selectChat(page, SECONDARY);
    await expect(composer).toBeEditable();
    await composer.fill("synthetic still-editable other draft");
    await selectChat(page, PRIMARY);
    await expect(composer).toHaveJSProperty("readOnly", true);
    await expect(composer).toHaveValue("synthetic pending-close draft");

    await page.getByRole("button", { name: "Fail synthetic close", exact: true }).click();
    await expect(composer).toBeEditable();
    await expect(composer).toHaveValue("synthetic pending-close draft");
    await selectChat(page, SECONDARY);
    await expect(composer).toHaveValue("synthetic still-editable other draft");
  });
});
