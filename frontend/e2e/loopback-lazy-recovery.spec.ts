import { expect, test, type Page } from "@playwright/test";

const BASE_URL = process.env.PE_CONVERGENCE_BASE_URL!;
const WORKSPACE = process.env.PE_CONVERGENCE_WORKSPACE!;
const PROJECT = "Lazy recovery example project";

async function createReadOnlyChat(page: Page): Promise<void> {
  await page.goto("/agent");
  const rail = page.getByRole("navigation", { name: "Agent projects and chats", exact: true });
  await expect(rail).toBeVisible();
  await rail.getByRole("button", { name: "Create project", exact: true }).click();
  const project = page.getByRole("dialog", { name: "Create project", exact: true });
  await project.getByLabel("Project name", { exact: true }).fill(PROJECT);
  await project.getByRole("button", { name: "Save", exact: true }).click();
  await rail.locator(".agent-rail__project-pick").filter({ hasText: PROJECT }).click();
  await rail.getByRole("button", { name: "New chat", exact: true }).click();
  const setup = page.getByRole("dialog", { name: "New session", exact: true });
  await setup.getByLabel("Workspace folder", { exact: true }).fill(WORKSPACE);
  const created = page.waitForResponse((response) => (
    response.request().method() === "POST"
    && new URL(response.url()).origin === BASE_URL
    && new URL(response.url()).pathname === "/v1/agent/sessions"
    && response.ok()
  ));
  await setup.getByRole("button", { name: "Open read-only chat without model", exact: true }).click();
  const response = await created;
  const receipt = await response.json() as { session_id: string };
  expect(receipt.session_id).toMatch(/^[a-f0-9]{32}$/u);
  await expect(setup).toBeHidden();
  await expect(rail.getByRole("region", { name: "Chats", exact: true }).locator("[data-current='true']")).toHaveCount(1);
  await expect(page.getByRole("textbox", { name: "Message to the agent", exact: true })).toHaveValue("");
}

test("contains a blocked production optional chunk without discarding the active Agent draft", async ({ page }) => {
  let armFailure = false;
  let blockedAssetUrl: string | undefined;
  await page.route(/\/assets\/AgentReadinessPanel-[\w-]+\.js$/u, async (route) => {
    const request = route.request();
    if (armFailure && blockedAssetUrl === undefined) {
      blockedAssetUrl = request.url();
      await route.abort("failed");
      return;
    }
    await route.continue();
  });

  await createReadOnlyChat(page);
  const composer = page.getByRole("textbox", { name: "Message to the agent", exact: true });
  await composer.fill("Synthetic draft survives optional chunk containment.");
  await expect(composer).toHaveValue("Synthetic draft survives optional chunk containment.");

  armFailure = true;
  await page.getByRole("button", { name: /Agent settings/ }).click();
  const failure = page.getByRole("alert").filter({ hasText: "Unable to load readiness" });
  await expect(failure).toBeVisible();
  expect(blockedAssetUrl, "the deliberate fault aborted a real production asset request").toBeDefined();
  await expect(failure).toContainText("Preserve or copy unsent drafts and unsaved file work before explicitly reloading the app.");
  await expect(failure.getByRole("button")).toHaveCount(0);
  await expect(composer).toHaveValue("Synthetic draft survives optional chunk containment.");
  await expect(page.getByRole("dialog", { name: "Agent settings", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Close agent settings", exact: true }).click();
  await expect(composer).toBeEnabled();
  await expect(page.getByRole("button", { name: "Send", exact: true })).toBeDisabled();
  await expect(page).toHaveURL(/\/agent$/u);
  expect(new URL(blockedAssetUrl!).origin).toBe(BASE_URL);
});
