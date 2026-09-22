import { expect, test, type Page } from "@playwright/test";

const FIXTURE = "/e2e/fixtures/agent-resume-ownership.html";
const HARNESS = "Synthetic resume ownership harness";

async function openFixture(page: Page, mode: "normal" | "deferred-success" | "deferred-failure") {
  await page.goto(`${FIXTURE}?mode=${mode}`);
  await expect(page.getByRole("complementary", { name: HARNESS, exact: true })).toBeVisible();
  // The fixture exposes one synthetic project and keeps it expanded at startup.
  const savedA = page.getByRole("button", { name: /^Saved resume A/u });
  await expect(savedA).toBeVisible();
  return { harness: page.getByRole("complementary", { name: HARNESS, exact: true }), savedA };
}

async function openSavedChat(page: Page, title: "A" | "B") {
  const row = page.getByRole("button", { name: new RegExp(`^Saved resume ${title}\\b`, "u") });
  await row.click();
  await expect(page.getByRole("heading", { level: 1, name: `Saved resume ${title}`, exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Resume chat", exact: true })).toBeEnabled();
}

async function expectNoImplicitAgentActions(page: Page, resumeCount: string) {
  await expect(page.locator("html")).toHaveAttribute("data-resume-ownership-resume", resumeCount);
  await expect(page.locator("html")).toHaveAttribute("data-resume-ownership-activate", "0");
  await expect(page.locator("html")).toHaveAttribute("data-resume-ownership-send", "0");
}

test.describe("Agent retained resume ownership", () => {
  test("normal retained resume opens a model-neutral composer", async ({ page }) => {
    await openFixture(page, "normal");
    await openSavedChat(page, "A");

    await page.getByRole("button", { name: "Resume chat", exact: true }).click();

    const composer = page.getByRole("textbox", { name: "Message to the agent", exact: true });
    await expect(composer).toBeVisible();
    await expect(composer).toBeEnabled();
    await expect(page.getByRole("button", { name: "Send", exact: true })).toBeDisabled();
    await expect(page.getByRole("region", { name: "Agent activity status", exact: true })).toContainText("No model");
    await expect(page.getByRole("link", { name: "Open Models", exact: true })).toBeVisible();
    await expectNoImplicitAgentActions(page, "1");
  });

  test("a late successful resume for A cannot replace the later selected B", async ({ page }) => {
    const { harness } = await openFixture(page, "deferred-success");
    await openSavedChat(page, "A");
    await page.getByRole("button", { name: "Resume chat", exact: true }).click();

    await openSavedChat(page, "B");
    await harness.getByRole("button", { name: "Release deferred resume A", exact: true }).click();

    await expect(page.locator("html")).toHaveAttribute("data-resume-ownership-resolution", "success");
    await expect(page.getByRole("heading", { level: 1, name: "Saved resume B", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { level: 1, name: "Saved resume A", exact: true })).toHaveCount(0);
    await expect(page.getByRole("textbox", { name: "Message to the agent", exact: true })).toHaveCount(0);
    await expectNoImplicitAgentActions(page, "1");
  });

  test("a late failed resume for A does not show its error on B", async ({ page }) => {
    const { harness } = await openFixture(page, "deferred-failure");
    await openSavedChat(page, "A");
    await page.getByRole("button", { name: "Resume chat", exact: true }).click();

    await openSavedChat(page, "B");
    await harness.getByRole("button", { name: "Fail deferred resume A", exact: true }).click();

    await expect(page.locator("html")).toHaveAttribute("data-resume-ownership-resolution", "failure");
    await expect(page.getByRole("heading", { level: 1, name: "Saved resume B", exact: true })).toBeVisible();
    await expect(page.getByText("The retained chat could not be resumed. Its saved history remains unchanged.", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Saved locally · 0 turns", { exact: true })).toBeVisible();
    await expectNoImplicitAgentActions(page, "1");
  });

  test("clicking the selected saved row twice keeps Resume ready without implicit actions", async ({ page }) => {
    await openFixture(page, "normal");
    await openSavedChat(page, "A");

    await page.getByRole("button", { name: /^Saved resume A/u }).click();
    await expect(page.getByRole("button", { name: "Resume chat", exact: true })).toBeEnabled();
    await expectNoImplicitAgentActions(page, "0");
  });

  test("keyboard resume remains usable at 360px without horizontal overflow", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 760 });
    await openFixture(page, "normal");
    const savedA = page.getByRole("button", { name: /^Saved resume A/u });
    await savedA.focus();
    await savedA.press("Enter");
    const resume = page.getByRole("button", { name: "Resume chat", exact: true });
    await resume.focus();
    await expect(resume).toBeFocused();
    await resume.press("Enter");

    const composer = page.getByRole("textbox", { name: "Message to the agent", exact: true });
    await expect(composer).toBeVisible();
    await composer.focus();
    const box = await composer.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(360);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await expectNoImplicitAgentActions(page, "1");
  });
});
