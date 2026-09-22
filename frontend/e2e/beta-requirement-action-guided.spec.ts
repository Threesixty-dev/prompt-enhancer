import { expect, test, type Page } from "@playwright/test";

const FIXTURE = "/e2e/fixtures/requirement-action-guided.html";

async function openGuided(page: Page): Promise<void> {
  await expect(page.getByRole("button", { name: "Start guided action authoring", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Start guided action authoring", exact: true }).click();
  await page.getByRole("button", { name: "Open guided action review", exact: true }).click();
  await expect(page.getByText("Create the synthetic artifact.", { exact: true })).toBeVisible();
}

test("filters actions without changing original candidate indexes and creates an inert linked proposal", async ({ page }) => {
  await page.goto(`${FIXTURE}?state=ready`);
  await openGuided(page);
  await page.getByLabel("Link selected actions", { exact: true }).check();
  await page.getByLabel("Search actions", { exact: true }).fill("synthetic.test");
  await expect(page.getByRole("checkbox", { name: "Action 2", exact: true })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Action 1", exact: true })).toHaveCount(0);
  await page.getByRole("checkbox", { name: "Action 2", exact: true }).check();
  await expect(page.getByRole("button", { name: "Create unconfirmed proposal", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Create unconfirmed proposal", exact: true }).click();
  await expect(page.getByRole("list", { name: "Requirement-action proposal history" })
    .getByText(/Awaiting native decision/)).toBeVisible();
  await expect(page.getByTestId("created")).toHaveText("Created proposals: 1");
  await expect(page.getByTestId("submitted-indexes")).toHaveText("Submitted indexes: [1]");
  await expect(page.getByTestId("decision-count")).toHaveText("Native decisions: 0");
});

test("creates an explicit-none inert action proposal without automatic decision", async ({ page }) => {
  await page.goto(FIXTURE);
  await openGuided(page);
  await page.getByLabel("No matching action", { exact: true }).check();
  await page.getByRole("button", { name: "Create unconfirmed proposal", exact: true }).click();
  await expect(page.getByRole("list", { name: "Requirement-action proposal history" })
    .getByText(/0 linked · 1 explicit empty/)).toBeVisible();
  await expect(page.getByTestId("created")).toHaveText("Created proposals: 1");
  await expect(page.getByTestId("decision-count")).toHaveText("Native decisions: 0");
});

test("close and source change clear the guided action draft", async ({ page }) => {
  await page.goto(FIXTURE);
  await openGuided(page);
  await page.getByRole("button", { name: "Close and clear", exact: true }).click();
  await expect(page.getByText("Create the synthetic artifact.", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Start guided action authoring", exact: true }).click();
  await page.getByRole("button", { name: "Open guided action review", exact: true }).click();
  await page.getByRole("button", { name: "Switch synthetic source", exact: true }).click();
  await expect(page.getByText("Create the synthetic artifact.", { exact: true })).toHaveCount(0);
  await expect(page.getByTestId("created")).toHaveText("Created proposals: 0");
});

test("keeps guided action authoring disabled without native presence", async ({ page }) => {
  await page.goto(`${FIXTURE}?state=native-unavailable`);
  await expect(page.getByRole("button", { name: "Start guided action authoring", exact: true })).toBeDisabled();
  await expect(page.getByText(/native user presence is unavailable/i)).toBeVisible();
});

test("remains bounded at 390px", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 720 });
  await page.goto(FIXTURE);
  await openGuided(page);
  const dimensions = await page.evaluate(() => ({ documentWidth: document.documentElement.scrollWidth, viewportWidth: document.documentElement.clientWidth }));
  expect(dimensions.documentWidth).toBeLessThanOrEqual(dimensions.viewportWidth);
});
