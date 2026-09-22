import { expect, test, type Page } from "@playwright/test";

async function prepareAndOpenReview(page: Page): Promise<void> {
  const prepare = page.getByRole("button", { name: "Prepare current reviewed requirements", exact: true });
  if (await prepare.count() > 0) await prepare.click();
  await page.locator("details").first().locator("summary").click();
  await page.getByRole("button", { name: "Read exact requirement", exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "Exact local requirement review", exact: true })).toBeVisible();
}

async function fitsViewport(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => ({
    width: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(overflow.width).toBeLessThanOrEqual(overflow.viewport);
}

test("records an explicit native human disposition after review", async ({ page }) => {
  await page.goto("/e2e/fixtures/requirement-verification.html?state=awaiting");
  await prepareAndOpenReview(page);
  await page.getByLabel("I have read this exact local requirement.").check();
  await page.getByRole("radio", { name: "accepted", exact: true }).check();
  await page.getByRole("button", { name: "Confirm human disposition", exact: true }).click();
  await expect(page.getByTestId("fixture-counters")).toContainText("Review reads: 1");
  await expect(page.getByTestId("fixture-counters")).toContainText("Acceptance invocations: 1");
  await expect(page.getByTestId("fixture-counters")).toContainText("Evidence refresh callbacks: 2");
  await expect(page.getByText("Recorded current native human disposition: accepted. The selected analysis snapshot remains unchanged.", { exact: true })).toBeVisible();
  await expect(page.getByText("2 requirements · 0 objective results · 0 native acceptances · revision 0", { exact: true })).toBeVisible();
});

test("cancelled review never records a native acceptance", async ({ page }) => {
  await page.goto("/e2e/fixtures/requirement-verification.html?state=awaiting");
  await prepareAndOpenReview(page);
  await page.getByRole("button", { name: "Cancel review", exact: true }).click();
  await expect(page.getByTestId("fixture-counters")).toContainText("Acceptance invocations: 0");
  await expect(page.getByTestId("fixture-counters")).toContainText("Evidence refresh callbacks: 1");
  await expect(page.getByRole("heading", { name: "Exact local requirement review", exact: true })).toHaveCount(0);
});

test("native-unavailable review remains fail-closed", async ({ page }) => {
  await page.goto("/e2e/fixtures/requirement-verification.html?state=native-unavailable");
  await page.locator("details").first().locator("summary").click();
  await expect(page.getByText("Native confirmation is unavailable in this local session.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Read exact requirement", exact: true }).first()).toBeDisabled();
  await expect(page.getByRole("button", { name: "Confirm human disposition", exact: true })).toHaveCount(0);
  await expect(page.getByTestId("fixture-counters")).toContainText("Review reads: 0");
  await expect(page.getByTestId("fixture-counters")).toContainText("Acceptance invocations: 0");
});

for (const state of ["mismatch", "stale"]) {
  test(`refuses ${state} review receipts without mutation`, async ({ page }) => {
    await page.goto(`/e2e/fixtures/requirement-verification.html?state=${state}`);
    await page.locator("details").first().locator("summary").click();
    await page.getByRole("button", { name: "Read exact requirement", exact: true }).first().click();
    await expect(page.getByRole("alert")).toContainText(/could not be opened|stale/i);
    await expect(page.getByTestId("fixture-counters")).toContainText("Review reads: 1");
    await expect(page.getByTestId("fixture-counters")).toContainText("Acceptance invocations: 0");
  });
}

test("review acceptance remains usable at 320px with keyboard entry", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 640 });
  await page.goto("/e2e/fixtures/requirement-verification.html?state=awaiting");
  const prepare = page.getByRole("button", { name: "Prepare current reviewed requirements", exact: true });
  await prepare.focus();
  await prepare.press("Enter");
  await page.locator("details").first().locator("summary").press("Enter");
  await page.getByRole("button", { name: "Read exact requirement", exact: true }).first().press("Enter");
  await page.getByLabel("I have read this exact local requirement.").check();
  await page.getByRole("radio", { name: "unknown", exact: true }).check();
  await expect(page.getByRole("button", { name: "Confirm human disposition", exact: true })).toBeEnabled();
  await fitsViewport(page);
});
