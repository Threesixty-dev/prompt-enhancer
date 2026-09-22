import { expect, test } from "@playwright/test";

const HANDOFF_FIXTURE = "/e2e/fixtures/models-agent-handoff.html";

function counter(page: import("@playwright/test").Page, name: string) {
  return page.locator("html").getAttribute(`data-handoff-${name.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)}`);
}

async function expectNoMutations(page: import("@playwright/test").Page) {
  for (const name of ["createAgentSession", "activateLocalModel", "switchLocalRuntime", "switchAgentSessionModel", "sendAgentMessage", "resumeAgentSession"]) {
    await expect.poll(() => counter(page, name)).toBe("0");
  }
}

test.describe("Models to Agent handoff", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${HANDOFF_FIXTURE}#/models`);
    await expect(page.locator("[data-route='models']")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Chat", exact: true })).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("data-handoff-create-agent-session", "0");
  });

  test("keeps a temporary draft and active partial reply isolated while opening Agent explicitly", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 760 });
    const composer = page.getByRole("textbox", { name: "Message", exact: true });
    await composer.fill("synthetic temporary handoff draft");
    await expect(composer).toHaveValue("synthetic temporary handoff draft");
    await expect(page.getByRole("button", { name: "Send", exact: true })).toBeEnabled();
    await composer.press("Control+Enter");
    await expect(page.getByText("Synthetic temporary reply.", { exact: true })).toBeVisible();
    await composer.fill("synthetic next draft");
    await page.getByRole("button", { name: "Open saved Agent chat", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Open a saved Agent chat?" });
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Open saved Agent chat", exact: true })).toBeFocused();
    await expect(page.getByText("Synthetic temporary reply.", { exact: true })).toBeVisible();
    await expect(composer).toHaveValue("synthetic next draft");
    await expect.poll(() => counter(page, "streamAbort")).toBe("0");
    await expectNoMutations(page);
    await page.getByRole("button", { name: "Open saved Agent chat", exact: true }).click();
    await page.getByRole("dialog", { name: "Open a saved Agent chat?" }).press("Escape");
    await expect(page.getByRole("dialog", { name: "Open a saved Agent chat?" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Open saved Agent chat", exact: true })).toBeFocused();
    await expect(page.getByText("Synthetic temporary reply.", { exact: true })).toBeVisible();
    await expect(composer).toHaveValue("synthetic next draft");
    await expect.poll(() => counter(page, "streamAbort")).toBe("0");
    await expectNoMutations(page);
    await page.getByRole("button", { name: "Open saved Agent chat", exact: true }).click();
    await page.getByRole("dialog", { name: "Open a saved Agent chat?" }).getByRole("button", { name: "Continue to Agent", exact: true }).click();
    await expect(page).toHaveURL(/\/agent$/u);
    await expect(page.locator("#agent-new-chat-drawer")).toBeVisible();
    await expect(page.getByRole("combobox", { name: "Agent model", exact: true })).toHaveValue("example-small-cpu");
    await expect(page.getByRole("textbox", { name: "Workspace folder", exact: true })).toHaveValue("");
    await expect(page.getByRole("radio", { name: /Save locally/i })).toBeChecked();
    await expect.poll(() => counter(page, "streamAbort")).toBe("1");
    await expect.poll(() => counter(page, "streamLocalModelChat")).toBe("1");
    await expect(page.getByText("synthetic next draft", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Synthetic temporary reply.", { exact: true })).toHaveCount(0);
    await expectNoMutations(page);
  });

  test("uses the explicit Agent setup bridge without transcript transfer", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.getByRole("button", { name: "Open saved Agent chat", exact: true }).click();
    const setup = page.getByRole("dialog", { name: "Open a saved Agent chat?" });
    await setup.getByRole("button", { name: "Continue to Agent", exact: true }).click();
    await expect(page).toHaveURL(/\/agent$/u);
    const agentSetup = page.locator("#agent-new-chat-drawer");
    await expect(agentSetup).toBeVisible();
    await expect(agentSetup.getByRole("combobox", { name: "Agent model", exact: true })).toHaveValue("example-small-cpu");
    await agentSetup.getByRole("textbox", { name: "Workspace folder", exact: true }).fill("D:\\synthetic-workspace");
    await expectNoMutations(page);
    await expect(page).not.toHaveURL(/temporary%20handoff|synthetic/u);
    await expect(agentSetup.getByRole("button", { name: /Open .*chat/u })).toBeEnabled();
  });

  test("keeps the handoff controls inside a narrow viewport", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 760 });
    const composer = page.getByRole("textbox", { name: "Message", exact: true });
    await composer.fill("synthetic narrow draft");
    const cta = page.getByRole("button", { name: "Open saved Agent chat", exact: true });
    for (const control of [composer, cta]) {
      await control.scrollIntoViewIfNeeded();
      const box = await control.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(360);
    }
  });
});
