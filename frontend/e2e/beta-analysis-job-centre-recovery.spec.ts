import { expect, test, type Locator, type Page } from "@playwright/test";

const FIXTURE = "/e2e/fixtures/analysis-job-centre-recovery.html";
const ABSENCE_NOTICE = "This job record is no longer available. Refresh the queue to view its current receipts.";
const UNCONFIRMED_CANCEL = "Cancellation could not be confirmed. Refresh the job before issuing another action.";
const diagnostics = new WeakMap<Page, { consoleErrors: number; pageErrors: number }>();

async function open(page: Page, mode: string) {
  await page.goto(`${FIXTURE}?mode=${mode}`);
  await expect(page.getByText("2 on this page", { exact: true })).toBeVisible();
}

function cards(page: Page): Locator {
  return page.locator("button.analysis-job-card");
}

function detail(page: Page): Locator {
  return page.getByRole("complementary", { name: "Selected job detail", exact: true });
}

async function selectFirstJob(page: Page) {
  await cards(page).first().click();
  await expect(detail(page).getByText("a".repeat(64), { exact: true })).toBeVisible();
}

async function confirmCancellation(page: Page) {
  await detail(page).getByRole("button", { name: "Cancel job", exact: true }).click();
  await detail(page).getByRole("button", { name: "Confirm cancellation", exact: true }).click();
}

async function expectCounters(page: Page, list: number, detailReads: number, cancels: number) {
  await expect(page.getByTestId("analysis-job-list-count")).toHaveText(`List reads: ${list}`);
  await expect(page.getByTestId("analysis-job-detail-count")).toHaveText(`Detail reads: ${detailReads}`);
  await expect(page.getByTestId("analysis-job-cancel-count")).toHaveText(`Cancel requests: ${cancels}`);
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
  expect(counts.consoleErrors, "analysis-job recovery fixture has no console errors").toBe(0);
  expect(counts.pageErrors, "analysis-job recovery fixture has no page errors").toBe(0);
});

test.describe("analysis-job authoritative absence and cancellation recovery", () => {
  test("retires only the exact cancelled 404 job and keeps the other receipt", async ({ page }) => {
    await open(page, "cancel-absence");
    await selectFirstJob(page);
    await confirmCancellation(page);

    await expect(page.getByRole("alert")).toContainText(ABSENCE_NOTICE);
    await expect(cards(page)).toHaveCount(1);
    await expect(cards(page).first()).toContainText("Completed");
    await expect(detail(page).getByRole("heading", { name: "Select a job", exact: true })).toBeVisible();
    await expect(detail(page).getByRole("group", { name: "Confirm job cancellation" })).toHaveCount(0);
    await expect(detail(page).getByRole("button", { name: "Cancel job", exact: true })).toHaveCount(0);
    await expectCounters(page, 1, 1, 1);
  });

  test("retains a 503 receipt and retries cancellation only after another explicit confirmation", async ({ page }) => {
    await open(page, "cancel-fail-once");
    await selectFirstJob(page);
    await confirmCancellation(page);

    await expect(detail(page).getByRole("alert")).toHaveText(UNCONFIRMED_CANCEL);
    await expect(cards(page)).toHaveCount(2);
    await expect(detail(page).getByText("a".repeat(64), { exact: true })).toBeVisible();
    await expect(detail(page).getByRole("button", { name: "Confirm cancellation", exact: true })).toBeVisible();
    await expectCounters(page, 1, 1, 1);

    await detail(page).getByRole("button", { name: "Confirm cancellation", exact: true }).click();
    await expect(detail(page).getByText("Cancelled", { exact: true })).toBeVisible();
    await expect(detail(page).getByRole("alert")).toHaveCount(0);
    await expect(cards(page)).toHaveCount(2);
    await expectCounters(page, 1, 2, 2);
  });

  test("retires a detail 404 immediately, then permits an explicit refresh to show a current replacement receipt", async ({ page }) => {
    await open(page, "detail-absence");
    await cards(page).first().click();

    await expect(page.getByRole("alert")).toContainText(ABSENCE_NOTICE);
    await expect(cards(page)).toHaveCount(1);
    await expect(detail(page).getByRole("heading", { name: "Select a job", exact: true })).toBeVisible();
    await expect(detail(page).getByRole("button", { name: "Cancel job", exact: true })).toHaveCount(0);
    await expectCounters(page, 1, 1, 0);

    await page.getByRole("button", { name: "Restore synthetic current receipt", exact: true }).click();
    await expectCounters(page, 1, 1, 0);
    await page.getByRole("button", { name: "Refresh queue", exact: true }).click();
    await expect(cards(page)).toHaveCount(2);
    await cards(page).first().click();
    await expect(detail(page).getByText("Awaiting approval", { exact: true })).toBeVisible();
    await expectCounters(page, 2, 2, 0);
  });

  test("returns keyboard focus to refresh after a removed cancellation control at 360px", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 900 });
    await open(page, "cancel-absence");
    const first = cards(page).first();
    await first.focus();
    await expect(first).toBeFocused();
    await first.press("Enter");
    const cancel = detail(page).getByRole("button", { name: "Cancel job", exact: true });
    await cancel.focus();
    await cancel.press("Enter");
    const confirm = detail(page).getByRole("button", { name: "Confirm cancellation", exact: true });
    await confirm.focus();
    await confirm.press("Enter");

    const refresh = page.getByRole("button", { name: "Refresh queue", exact: true });
    await expect(page.getByRole("alert")).toContainText(ABSENCE_NOTICE);
    await expect(refresh).toBeFocused();
    await expect(cards(page)).toHaveCount(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expectCounters(page, 1, 1, 1);
  });

  test("does not steal focus from queue state when a deferred cancellation 404 retires its job", async ({ page }) => {
    await open(page, "cancel-deferred-absence");
    await selectFirstJob(page);
    await confirmCancellation(page);

    const queueState = page.getByRole("combobox", { name: "Queue state", exact: true });
    await expect(detail(page).getByRole("button", { name: "Cancelling…", exact: true })).toBeDisabled();
    await queueState.focus();
    await expect(queueState).toBeFocused();

    await page.getByRole("button", { name: "Release synthetic cancellation absence", exact: true })
      .dispatchEvent("click");

    await expect(page.getByRole("alert")).toContainText(ABSENCE_NOTICE);
    await expect(queueState).toBeFocused();
    await expect(cards(page)).toHaveCount(1);
    await expectCounters(page, 1, 1, 1);
  });
});
