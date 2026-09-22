import { expect, test, type Locator, type Page } from "@playwright/test";

const widths = [320, 1440] as const;

async function openWebSetup(page: Page, width: number, query: string): Promise<Locator> {
  await page.setViewportSize({ width, height: 900 });
  await page.goto(`/e2e/fixtures/workflow-panels.html?panel=agent-web-fetch&${query}`);
  const rail = page.getByRole("navigation", { name: "Agent projects and chats", exact: true });
  await expect(rail).toContainText("Example coding project");
  await rail.locator(".agent-rail__project-pick").filter({ hasText: "Example coding project" }).click();
  await rail.getByRole("button", { name: "New chat", exact: true }).click();
  const setup = page.getByRole("dialog", { name: "New session", exact: true });
  await expect(setup).toBeVisible();
  return setup;
}

async function fitsViewport(page: Page): Promise<void> {
  const dimensions = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: document.documentElement.clientWidth,
  }));
  expect(dimensions.documentWidth, "the governed web-fetch setup must not overflow").toBeLessThanOrEqual(dimensions.viewportWidth);
}

for (const width of widths) {
  test.describe(`governed web-fetch setup at ${width}px`, () => {
    test("verified capability is visible but opt-in remains off", async ({ page }) => {
      const setup = await openWebSetup(page, width, "native=available&state=ready");
      const web = setup.getByRole("checkbox", { name: /May fetch approved public HTTPS URLs/i });
      await expect(web).toBeVisible();
      await expect(web).toBeEnabled();
      await expect(web).not.toBeChecked();
      await expect(setup).toContainText(/each request leaves this machine.*no cookies, credentials, or redirects/i);
      await expect(page.locator("html")).toHaveAttribute("data-web-fetch-capability-reads", "1");
      await fitsViewport(page);
    });

    test("explicit opt-in is recorded on model-free session creation", async ({ page }) => {
      const setup = await openWebSetup(page, width, "native=available&state=ready");
      const web = setup.getByRole("checkbox", { name: /May fetch approved public HTTPS URLs/i });
      await web.check();
      await setup.getByLabel("Workspace folder", { exact: true }).fill("D:\\synthetic-web-fetch");
      await setup.getByRole("button", { name: /Open (?:read-only )?chat without model/u }).click();
      await expect(page.getByRole("textbox", { name: "Message to the agent", exact: true })).toBeVisible();
      await expect(page.locator("html")).toHaveAttribute("data-web-fetch-create-allow-web", "true");
      await expect(page.locator("html")).toHaveAttribute("data-web-fetch-create-allow-writes", "false");
      await expect(page.locator("html")).toHaveAttribute("data-web-fetch-create-allow-commands", "false");
      await fitsViewport(page);
    });

    test("native confirmation unavailable keeps the web opt-in disabled", async ({ page }) => {
      const setup = await openWebSetup(page, width, "native=unavailable&state=ready");
      const web = setup.getByRole("checkbox", { name: /Web fetch unavailable until native confirmation/i });
      await expect(web).toBeDisabled();
      await expect(web).not.toBeChecked();
      await expect(setup).toContainText(/Web fetch is unavailable until native confirmation is available/i);
      await fitsViewport(page);
    });

    test("a rejected capability read has an explicit retry and never opts in automatically", async ({ page }) => {
      const setup = await openWebSetup(page, width, "native=available&state=reject-retry");
      const unavailable = setup.getByRole("checkbox", { name: /Web fetch unavailable \(capability could not be verified\)/i });
      await expect(unavailable).toBeDisabled();
      await expect(unavailable).not.toBeChecked();
      await expect(setup.getByRole("button", { name: "Retry governed web fetch check", exact: true })).toBeVisible();
      await setup.getByRole("button", { name: "Retry governed web fetch check", exact: true }).click();

      const web = setup.getByRole("checkbox", { name: /May fetch approved public HTTPS URLs/i });
      await expect(web).toBeEnabled();
      await expect(web).not.toBeChecked();
      await expect(page.locator("html")).toHaveAttribute("data-web-fetch-capability-reads", "2");
      await fitsViewport(page);
    });
  });
}
