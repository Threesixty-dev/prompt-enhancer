import { expect, test, type Page } from "@playwright/test";

async function expectNoPageOverflow(page: Page): Promise<void> {
  const dimensions = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(dimensions.content, JSON.stringify(dimensions)).toBeLessThanOrEqual(dimensions.viewport);
}

for (const width of [360, 1440]) {
  test(`maximum loaded MCP catalog stays paged and operable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 360 ? 800 : 900 });
    await page.goto("/e2e/fixtures/workflow-panels.html?panel=agent-mcp-store&state=scale");

    await page.getByRole("button", { name: /Agent settings/ }).click();
    const settings = page.getByRole("dialog", { name: "Agent settings", exact: true });
    await settings.getByRole("tab", { name: "MCP Store", exact: true }).click();
    const store = settings.getByRole("region", { name: "MCP Store", exact: true });
    const cards = store.locator("article.agent-mcp-store__card");
    await expect(cards).toHaveCount(48);
    await expect(store.getByText("Showing 1–48 of 120", { exact: true })).toBeVisible();
    await expect(store.getByText("Synthetic scale server 000", { exact: true })).toBeVisible();
    await expect(store.getByText("Synthetic scale server 048", { exact: true })).toHaveCount(0);

    const pager = store.getByRole("navigation", { name: "Loaded MCP server pages", exact: true });
    await pager.getByRole("button", { name: "Later", exact: true }).click();
    await expect(cards).toHaveCount(48);
    await expect(store.getByText("Showing 49–96 of 120", { exact: true })).toBeVisible();
    await expect(store.getByText("Synthetic scale server 000", { exact: true })).toHaveCount(0);
    await expect(store.getByText("Synthetic scale server 048", { exact: true })).toBeVisible();
    await expectNoPageOverflow(page);
  });

  test(`maximum timeline bounds SVG nodes and reveals detail on zoom at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 360 ? 800 : 900 });
    await page.goto("/e2e/fixtures/workflow-panels.html?panel=scale-timeline");

    const timeline = page.getByRole("region", { name: "What happened, when", exact: true });
    await expect(timeline.locator(".session-timeline__turn")).toHaveCount(300);
    await expect(timeline.locator(".session-timeline__gap")).toHaveCount(300);
    await expect(timeline.locator(".session-timeline__tool")).toHaveCount(500);
    await expect(timeline.locator(".session-timeline__check")).toHaveCount(200);
    await expect(timeline.locator(".session-timeline__marker")).toHaveCount(200);
    await expect(timeline.locator("[data-bounded='true']")).toContainText("Drawing 1,500 of 8,000 timeline items");

    const zoomIn = timeline.getByRole("button", { name: "Zoom in", exact: true });
    for (let step = 0; step < 6; step += 1) await zoomIn.click();
    await expect(timeline.locator("[data-bounded='false']")).toContainText("Drawing all");
    await expectNoPageOverflow(page);
  });
}
