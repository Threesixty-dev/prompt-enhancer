import { expect, test, type Page } from "@playwright/test";

const FIXTURE = "/e2e/fixtures/session-radar.html";
const diagnostics = new WeakMap<Page, { consoleErrors: number; pageErrors: number }>();

async function open(page: Page, mode = "canonical") {
  await page.goto(`${FIXTURE}?mode=${mode}`);
}

async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

function canonicalSource(page: Page) {
  return page.locator(".session-radar .eyebrow");
}

test.beforeEach(async ({ page }) => {
  const counts = { consoleErrors: 0, pageErrors: 0 };
  diagnostics.set(page, counts);
  page.on("console", (message) => {
    if (message.type() === "error") counts.consoleErrors += 1;
  });
  page.on("pageerror", () => { counts.pageErrors += 1; });
});

test.afterEach(async ({ page }) => {
  const counts = diagnostics.get(page)!;
  expect(counts.consoleErrors, "session radar fixture console errors").toBe(0);
  expect(counts.pageErrors, "session radar fixture page errors").toBe(0);
});

test.describe("session radar", () => {
  test("uses canonical V2 evidence before conflicting typed and committee receipts", async ({ page }) => {
    await open(page);

    await expect(canonicalSource(page)).toContainText("Canonical V2 measured states");
    const taskStates = page.getByRole("list", { name: "Task framing metric states", exact: true });
    const taskRow = taskStates.locator("li").filter({ hasText: "Task" });
    const taskRadar = page.getByRole("img", { name: "Task framing session radar", exact: true });
    const taskTooltip = taskRadar.locator("circle title").filter({ hasText: "Task:" });
    await expect(taskRow).toContainText("75%");
    await expect(taskRow).not.toContainText("25%");
    await expect(taskTooltip).toHaveText("Task: 75%");
    await expect(page.locator("html")).toHaveAttribute("data-latest-reads", "1");
    await expect(page.locator("html")).not.toHaveAttribute("data-stored-reads", /./);
  });

  test("switches all four metric groups with the keyboard", async ({ page }) => {
    await open(page);
    const groups = ["Task framing", "Collaboration flow", "Reasoning trace", "Evidence lane"];

    for (let index = 0; index < groups.length - 1; index += 1) {
      const group = page.getByRole("button", { name: groups[index], exact: true });
      await group.focus();
      await page.keyboard.press("Tab");
      await expect(page.getByRole("button", { name: groups[index + 1], exact: true })).toBeFocused();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("button", { name: groups[index + 1], exact: true })).toHaveAttribute("aria-pressed", "true");
    }
  });

  test("keeps a measured zero numeric and leaves unknown values out of numeric dots", async ({ page }) => {
    await open(page);
    await page.getByRole("button", { name: "Collaboration flow", exact: true }).click();

    const collaborationStates = page.getByRole("list", { name: "Collaboration flow metric states", exact: true });
    const reworkRow = collaborationStates.locator("li").filter({ hasText: "Rework" });
    const collaborationRadar = page.getByRole("img", { name: "Collaboration flow session radar", exact: true });
    const reworkTooltip = collaborationRadar.locator("circle title").filter({ hasText: "Rework:" });
    await expect(reworkRow).toContainText("raw rate 0%");
    await expect(page.locator(".prompt-plot__dot")).toHaveCount(1);
    await expect(page.locator(".prompt-plot__dot--unknown")).toHaveCount(0);
    await expect(page.locator(".prompt-plot__area")).toHaveCount(0);
    await expect(reworkTooltip).toHaveText("Rework: 100% quality (raw 0%; lower is better)");
  });

  test("cancels a pending read and refreshes exactly one replacement read", async ({ page }) => {
    await open(page, "pending");
    await page.getByRole("button", { name: "Cancel session radar loading", exact: true }).press("Enter");
    await expect(page.getByRole("button", { name: "Retry session radar", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Enable session radar recovery", exact: true }).click();
    await page.getByRole("button", { name: "Retry session radar", exact: true }).press("Enter");
    await expect(canonicalSource(page)).toContainText("Canonical V2 measured states");
    await expect(page.locator("html")).toHaveAttribute("data-latest-reads", "2");
  });

  test("treats missing latest metadata as empty, not as a failed analysis", async ({ page }) => {
    await open(page, "empty");

    await expect(page.getByText("No local metric snapshot exists for this session yet.", { exact: true })).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("data-latest-reads", "1");
    await expect(page.locator("html")).toHaveAttribute("data-stored-reads", "1");
  });

  test("does not fall back after a latest metadata failure", async ({ page }) => {
    await open(page, "error");

    await expect(page.getByRole("alert")).toContainText("Session radar could not be loaded.");
    await expect(page.locator("html")).toHaveAttribute("data-latest-reads", "1");
    await expect(page.locator("html")).not.toHaveAttribute("data-stored-reads", /./);
  });

  test("fences a late result from a replaced transport", async ({ page }) => {
    await open(page, "owner");
    await page.getByRole("button", { name: "Replace synthetic radar transport", exact: true }).click();
    await expect(canonicalSource(page)).toContainText("Canonical V2 measured states");
    await page.getByRole("button", { name: "Resolve prior radar read", exact: true }).click();
    await expect(canonicalSource(page)).toContainText("Canonical V2 measured states");
    await expect(canonicalSource(page)).not.toContainText("Legacy committee shadow");
  });

  for (const width of [360, 1440]) {
    test(`keeps the session radar usable at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await open(page);
      await page.getByRole("button", { name: "Task framing", exact: true }).focus();
      await expect(page.getByRole("button", { name: "Task framing", exact: true })).toBeFocused();
      await expect(page.getByRole("img", { name: "Task framing session radar" })).toBeVisible();
      const provenance = page.getByText("Snapshot provenance", { exact: true });
      const disclosure = page.locator("details").filter({ hasText: "Snapshot provenance" });
      await expect(disclosure).not.toHaveAttribute("open", "");
      await provenance.focus();
      await expect(provenance).toBeFocused();
      await page.keyboard.press("Enter");
      await expect(disclosure).toHaveAttribute("open", "");
      await noOverflow(page);
    });
  }
});
