import { expect, test, type Page } from "@playwright/test";

const FIXTURE = "/e2e/fixtures/requirement-plan-guided.html";

async function openGuided(page: Page): Promise<void> {
  await expect(page.getByRole("button", { name: "Start guided authoring", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Start guided authoring", exact: true }).click();
  await page.getByRole("button", { name: "Open guided clause review", exact: true }).click();
  await expect(page.getByText("Create the synthetic output.", { exact: true })).toBeVisible();
}

async function advanceToPlan(page: Page): Promise<void> {
  await page.getByLabel("Active requirement", { exact: true }).check();
  await page.getByLabel("linked", { exact: true }).check();
  await page.getByRole("button", { name: "Next", exact: true }).click();

  await page.getByLabel("Exclude", { exact: true }).check();
  const selects = page.getByRole("combobox");
  await selects.nth(0).selectOption("duplicate");
  await selects.nth(1).selectOption("1:0");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.getByText("Implement the synthetic output.", { exact: true })).toBeVisible();
}

async function completeAuthoring(page: Page): Promise<void> {
  await advanceToPlan(page);
  await page.getByLabel("Include", { exact: true }).check();
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await page.getByLabel("Link message 2, clause 0", { exact: true }).check();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: "Next", exact: true }).click();
}

async function fitsViewport(page: Page): Promise<void> {
  const dimensions = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: document.documentElement.clientWidth,
  }));
  expect(dimensions.documentWidth).toBeLessThanOrEqual(dimensions.viewportWidth);
}

test("creates a typed inert proposal from an exact native-faked source read without JSON or automatic decision", async ({ page }) => {
  await page.goto(`${FIXTURE}?state=ready`);
  await openGuided(page);
  await completeAuthoring(page);

  await expect(page.getByRole("button", { name: "Create unconfirmed proposal", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Create unconfirmed proposal", exact: true }).click();
  await expect(page.getByText(/Locally authored unconfirmed proposal created\./)).toBeVisible();
  await expect(page.getByRole("list", { name: "Requirement-plan proposals awaiting native decision" }).getByRole("listitem")).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Open exact local clause review", exact: true })).toBeVisible();
  await expect(page.getByTestId("fixture-counters")).toContainText("Guided reads: 1");
  await expect(page.getByTestId("fixture-counters")).toContainText("Guided proposals: 1");
  await expect(page.getByTestId("fixture-counters")).toContainText("Native decisions: 0");
  await expect(page.getByTestId("fixture-counters")).toContainText("File previews: 0");
  await expect(page.getByTestId("fixture-counters")).toContainText("File imports: 0");
  await expect(page.getByTestId("last-guided-command")).toContainText('"complete_user_clause_classification_acknowledged":true');
  await expect(page.getByTestId("last-guided-command")).toContainText('"plan_items":[{"message_sequence":2,"clause_index":0}]');
  await expect(page.getByRole("button", { name: "Apply native confirmation", exact: true })).toHaveCount(0);
});

test("keeps proposal creation blocked until every classification, disposition, link, and required exclusion basis is complete", async ({ page }) => {
  await page.goto(FIXTURE);
  await openGuided(page);
  const create = page.getByRole("button", { name: "Create unconfirmed proposal", exact: true });
  await expect(create).toBeDisabled();
  await page.getByLabel("Active requirement", { exact: true }).check();
  await expect(create).toBeDisabled();
  await page.getByLabel("linked", { exact: true }).check();
  await expect(create).toBeDisabled();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByLabel("Exclude", { exact: true }).check();
  await page.getByRole("combobox").nth(0).selectOption("duplicate");
  await expect(create).toBeDisabled();
  await expect(page.getByRole("combobox").nth(1)).toHaveValue("");
  await expect(page.getByTestId("fixture-counters")).toContainText("Guided proposals: 0");
});

test("close and clear abandons the exact source draft before it can submit", async ({ page }) => {
  await page.goto(FIXTURE);
  await openGuided(page);
  await page.getByLabel("Active requirement", { exact: true }).check();
  await page.getByRole("button", { name: "Close and clear", exact: true }).click();
  await expect(page.getByText("Create the synthetic output.", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Start guided authoring", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Start guided authoring", exact: true }).click();
  await page.getByRole("button", { name: "Open guided clause review", exact: true }).click();
  await expect(page.getByLabel("Active requirement", { exact: true })).not.toBeChecked();
  await expect(page.getByTestId("fixture-counters")).toContainText("Guided proposals: 0");
});

test("ignores a late native-faked source response after the selected source context changes", async ({ page }) => {
  await page.goto(`${FIXTURE}?state=late`);
  await expect(page.getByRole("button", { name: "Start guided authoring", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Start guided authoring", exact: true }).click();
  await page.getByRole("button", { name: "Open guided clause review", exact: true }).click();
  await expect(page.getByTestId("fixture-counters")).toContainText("Guided reads: 1");
  await page.getByRole("button", { name: "Switch synthetic source window", exact: true }).click();
  await page.getByRole("button", { name: "Resolve late source read", exact: true }).click();
  await expect(page.getByText("Create the synthetic output.", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Open guided clause review", exact: true })).toHaveCount(0);
  await expect(page.getByTestId("fixture-counters")).toContainText("Guided proposals: 0");
});

test("keeps guided authoring disabled when native presence is unavailable", async ({ page }) => {
  await page.goto(`${FIXTURE}?state=native-unavailable`);
  await expect(page.getByRole("button", { name: "Start guided authoring", exact: true })).toBeDisabled();
  await expect(page.getByText(/Owned native user presence is unavailable/)).toBeVisible();
  await expect(page.getByTestId("fixture-counters")).toContainText("Guided reads: 0");
  await expect(page.getByTestId("fixture-counters")).toContainText("Guided proposals: 0");
});

test("remains keyboard-usable and bounded at a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 720 });
  await page.goto(FIXTURE);
  const start = page.getByRole("button", { name: "Start guided authoring", exact: true });
  await start.focus();
  await start.press("Enter");
  const open = page.getByRole("button", { name: "Open guided clause review", exact: true });
  await open.focus();
  await open.press("Enter");
  await expect(page.getByText("Create the synthetic output.", { exact: true })).toBeVisible();
  await fitsViewport(page);
  await page.getByLabel("Active requirement", { exact: true }).check();
  await page.getByLabel("linked", { exact: true }).check();
  await expect(page.getByRole("button", { name: "Next", exact: true })).toBeEnabled();
  await fitsViewport(page);
});
