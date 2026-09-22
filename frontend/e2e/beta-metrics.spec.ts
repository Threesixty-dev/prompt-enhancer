import { expect, test, type Page } from "@playwright/test";

async function fitsViewport(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => ({
    width: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(overflow.width).toBeLessThanOrEqual(overflow.viewport);
}

async function issueSyntheticObservedResult(page: Page): Promise<void> {
  await expect(page.getByRole("button", { name: "Find eligible direct-pytest checks", exact: true }).nth(1)).toBeVisible();
  await page.getByRole("button", { name: "Find eligible direct-pytest checks", exact: true }).nth(1).click();
  await page.getByRole("button", { name: "Review exact criterion", exact: true }).click();
  await page.getByRole("checkbox", { name: /acknowledge full-criterion coverage/i }).check();
  await page.getByRole("button", { name: "Issue server-derived observed result", exact: true }).click();
  await expect(page.getByText(/Recorded server-issued observed test result: passed/i)).toBeVisible();
}

test("requirement verification preparation is explicit and keyboard accessible", async ({ page }) => {
  await page.goto("/e2e/fixtures/requirement-verification.html?state=awaiting");
  await expect(page.getByTestId("fixture-counters")).toContainText("Issue invocations: 0");
  const prepare = page.getByRole("button", { name: "Prepare current reviewed requirements", exact: true });
  await prepare.focus();
  await prepare.press("Enter");
  await expect(page.getByTestId("fixture-counters")).toContainText("Issue invocations: 1");
  await expect(page.getByText(/Preparing a list is not a verified result/i)).toBeVisible();
  await expect(page.getByRole("button", { name: /accept/i })).toHaveCount(0);
  await fitsViewport(page);
});

test("persisted evidence reads the exact revision and separates authorities", async ({ page }) => {
  await page.goto("/e2e/fixtures/requirement-verification.html?state=persisted");
  await expect(page.getByTestId("fixture-counters")).toContainText("Issue invocations: 0");
  await expect(page.getByTestId("fixture-counters")).toContainText("Requested revision: 2");
  await expect(page.getByText("2 requirements · 1 objective results · 1 native acceptances · revision 2", { exact: true })).toBeVisible();
  const details = page.locator("details").filter({ has: page.getByText("Evidence identity and authority details", { exact: true }) });
  await expect(details).not.toHaveAttribute("open", "");
  await details.getByText("Evidence identity and authority details", { exact: true }).click();
  await expect(page.getByText(/objective static_check: passed/i)).toBeVisible();
  await expect(page.getByText(/Direct observed-check provenance is unavailable for this objective result; this is not a failed check\./i)).toBeVisible();
  await expect(page.getByText(/native acceptance: accepted/i)).toBeVisible();
  await expect(page.getByText("A human acceptance is separate from an objective passed check and does not change this selected analysis run.", { exact: true })).toBeVisible();
  await fitsViewport(page);
});

test("persisted evidence exposes a retry after a read failure", async ({ page }) => {
  await page.goto("/e2e/fixtures/requirement-verification.html?state=error");
  await expect(page.getByRole("alert")).toContainText("could not be loaded");
  await expect(page.getByRole("button", { name: "Retry exact read", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Retry exact read", exact: true }).click();
  await expect(page.getByText("2 requirements · 1 objective results · 1 native acceptances · revision 2", { exact: true })).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.getByTestId("fixture-counters")).toContainText("Snapshot reads: 2");
});

test("synthetic observed check review is native-gated and records a persistent server receipt", async ({ page }) => {
  await page.goto("/e2e/fixtures/requirement-verification.html?state=observed");
  await expect(page.getByText("2 requirements · 0 objective results · 0 native acceptances · revision 2", { exact: true })).toBeVisible();
  await expect(page.getByTestId("fixture-counters")).toContainText("Observed preflights: 0 · Observed reviews: 0 · Observed issues: 0");

  await page.getByRole("button", { name: "Find eligible direct-pytest checks", exact: true }).nth(1).click();
  await expect(page.getByText(/Observed sequence 3 · test\.pytest · provider-reported result: passed/)).toBeVisible();
  await page.getByRole("button", { name: "Review exact criterion", exact: true }).click();
  await expect(page.getByText("The response must include a bounded verification result.", { exact: true })).toBeVisible();

  const issue = page.getByRole("button", { name: "Issue server-derived observed result", exact: true });
  await expect(issue).toBeDisabled();
  await page.getByRole("checkbox", { name: /acknowledge full-criterion coverage/i }).check();
  await expect(issue).toBeEnabled();
  await issue.click();

  await expect(page.getByText(/Recorded server-issued observed test result: passed/i)).toBeVisible();
  await expect(page.getByText(/Current authority evidence is revision 3; the selected analysis remains revision 2/i)).toBeVisible();
  await expect(page.getByTestId("fixture-counters")).toContainText("Observed preflights: 1 · Observed reviews: 1 · Observed issues: 1");
  await expect(page.getByTestId("fixture-counters")).toContainText("Evidence refresh callbacks: 1");
  await expect(page.getByRole("radio")).toHaveCount(0);

  const evidenceDetails = page.locator("details").filter({ has: page.getByText("Evidence identity and authority details", { exact: true }) });
  await expect(evidenceDetails).not.toHaveAttribute("open", "");
  await evidenceDetails.getByText("Evidence identity and authority details", { exact: true }).click();
  const provenanceDetails = page.locator("details").filter({ has: page.getByText("Observed-check provenance", { exact: true }) }).last();
  await provenanceDetails.getByText("Observed-check provenance", { exact: true }).click();
  await expect(provenanceDetails.getByText("Provider-reported outcome", { exact: true })).toBeVisible();
  await expect(provenanceDetails.getByText("passed (exit code 0)", { exact: true })).toBeVisible();
  await expect(provenanceDetails).toContainText("Human full-criterion coverage acknowledged separately");
  await expect(provenanceDetails).toContainText("Source reference");
  await expect(provenanceDetails).toContainText("Coverage review reference");
  await expect(provenanceDetails).toContainText("observed-check-completion-v1");
  await expect(provenanceDetails).not.toContainText("pytest -q");
  await expect(page.getByTestId("fixture-counters")).toContainText("Observed provenance reads: 1");

  await page.getByRole("button", { name: "Find eligible direct-pytest checks", exact: true }).nth(1).click();
  await expect(page.getByTestId("fixture-counters")).toContainText("Observed preflights: 2 · Observed reviews: 1 · Observed issues: 1");
});

for (const width of [320, 1280]) {
  test(`expanded observed provenance stays usable without overflow at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 640 });
    await page.goto("/e2e/fixtures/requirement-verification.html?state=observed");
    await issueSyntheticObservedResult(page);
    const evidenceDetails = page.locator("details").filter({ has: page.getByText("Evidence identity and authority details", { exact: true }) });
    await evidenceDetails.getByText("Evidence identity and authority details", { exact: true }).click();
    const provenanceDetails = page.locator("details").filter({ has: page.getByText("Observed-check provenance", { exact: true }) }).last();
    await provenanceDetails.getByText("Observed-check provenance", { exact: true }).click();
    await expect(provenanceDetails.getByText("Provider-reported outcome", { exact: true })).toBeVisible();
    await expect(provenanceDetails.getByText("passed (exit code 0)", { exact: true })).toBeVisible();
    await expect(provenanceDetails).toContainText("Human full-criterion coverage acknowledged separately");
    await expect(page.getByTestId("fixture-counters")).toContainText("Observed provenance reads: 1");
    await fitsViewport(page);
  });
}

test("synthetic observed checks show provider results but no alternate path without native review", async ({ page }) => {
  await page.goto("/e2e/fixtures/requirement-verification.html?state=observed-native-unavailable");
  await page.getByRole("button", { name: "Find eligible direct-pytest checks", exact: true }).nth(1).click();
  await expect(page.getByText(/provider-reported result: passed/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Review exact criterion", exact: true })).toBeDisabled();
  await expect(page.getByText(/No alternate result path is offered/i)).toBeVisible();
  await expect(page.getByRole("button", { name: "Issue server-derived observed result", exact: true })).toHaveCount(0);
  await expect(page.getByTestId("fixture-counters")).toContainText("Observed preflights: 1 · Observed reviews: 0 · Observed issues: 0");
});

for (const width of [320, 768, 1280]) {
  test(`requirement verification remains readable without page overflow at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 640 });
    await page.goto("/e2e/fixtures/requirement-verification.html?state=persisted");
    await expect(page.getByRole("heading", { name: "Requirement verification evidence", exact: true })).toBeVisible();
    await page.getByText("Evidence identity and authority details", { exact: true }).click();
    await expect(page.getByText(/objective static_check: passed/i)).toBeVisible();
    await fitsViewport(page);
  });
}
