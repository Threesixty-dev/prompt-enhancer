import { expect, test, type Page } from "@playwright/test";

const CHILD_SESSION = "5".repeat(32);
const CHILD_ATTACHMENT = "0".repeat(31) + "1";
const PAYLOAD = "Synthetic branch attachment payload\n";

async function fitsViewport(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => ({
    width: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(overflow.width).toBeLessThanOrEqual(overflow.viewport);
}

async function prepare(page: Page, only = false, longName = false): Promise<void> {
  await page.goto(`/e2e/fixtures/workflow-panels.html?panel=agent-history&branchAttachments=1${only ? "&only=1" : ""}${longName ? "&longName=1" : ""}`);
  const source = page.getByRole("article", { name: "Saved restart chat", exact: true });
  await page.getByLabel("Turn 1 details", { exact: true }).click();
  await page.getByRole("button", { name: "Prepare regeneration with attachments", exact: true }).click();
  await expect(page.getByRole("region", { name: "Original attachments for this retry", exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.branchAttachmentUploads)).toBe("0");
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.branchManualSends)).toBe("0");
}

async function chooseDocument(page: Page, contents: string, name = "synthetic-branch.txt"): Promise<void> {
  await page.getByRole("button", { name: "Attach", exact: true }).click();
  await page.getByLabel("Choose documents", { exact: true }).setInputFiles({
    name,
    mimeType: "text/plain",
    buffer: Buffer.from(contents, "utf8"),
  });
}

test("prepares a child draft, reattaches the exact original, then sends manually", async ({ page }) => {
  await prepare(page);
  const composer = page.getByRole("textbox", { name: "Message to the agent", exact: true });
  await expect(composer).toHaveValue("Explain the retained synthetic module.");
  await expect(page.getByRole("button", { name: "Send", exact: true })).toBeDisabled();
  await chooseDocument(page, PAYLOAD);
  await expect(page.getByText("Exact file reattached", { exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.branchAttachmentUploads)).toBe("1");
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.branchManualSends)).toBe("0");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.branchManualSends)).toBe("1");
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.branchLastSendSession)).toBe(CHILD_SESSION);
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.branchLastSendAttachments)).toBe(CHILD_ATTACHMENT);
  await expect(page.getByRole("region", { name: "Original attachments for this retry", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Stop response", exact: true })).toHaveCount(0);
  await expect(page.getByText("Synthetic agent reply: no real files were read or changed.", { exact: true })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Message to the agent", exact: true })).toBeEnabled();
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.branchSourceEventCount)).toBe("4");
  const rail = page.getByRole("navigation", { name: "Agent projects and chats", exact: true });
  await rail.getByText("Saved restart chat", { exact: true }).click();
  const reopened = page.getByRole("article", { name: "Saved restart chat", exact: true });
  await expect(reopened).toContainText("Explain the retained synthetic module.");
  await expect(reopened).toContainText("synthetic-branch.txt");
  await expect(reopened).toContainText("35 projected characters");
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.branchSourceAttachmentDigest)).toBe("9a7bcb576476cceaf8c61ce60a3c69f193ee19d498aab873bb520d81cbae6f45");
  await fitsViewport(page);
});

test("keeps a mismatched file blocked until the owner explicitly omits the original", async ({ page }) => {
  await prepare(page);
  await chooseDocument(page, "Different synthetic bytes\n");
  await expect(page.getByText(/different file is never treated as the original/i)).toBeVisible();
  await expect(page.getByRole("button", { name: "Send", exact: true })).toBeDisabled();
  const checklist = page.getByRole("region", { name: "Original attachments for this retry", exact: true });
  await checklist.getByRole("button", { name: /^Omit original / }).click();
  await expect(checklist.getByText("Original omitted", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Send", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.branchLastSendSession)).toBe(CHILD_SESSION);
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.branchLastSendAttachments)).toBe(CHILD_ATTACHMENT);
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.branchManualSends)).toBe("1");
});

test("supports an attachment-only source turn without autosending", async ({ page }) => {
  await prepare(page, true);
  await expect(page.getByRole("textbox", { name: "Message to the agent", exact: true })).toHaveValue("");
  await chooseDocument(page, PAYLOAD);
  await expect(page.getByText("Exact file reattached", { exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.branchManualSends)).toBe("0");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.branchManualSends)).toBe("1");
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.branchLastSendSession)).toBe(CHILD_SESSION);
  await fitsViewport(page);
});

test("keeps the checklist usable at 320px with keyboard focus", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await prepare(page, false, true);
  const checklist = page.getByRole("region", { name: "Original attachments for this retry", exact: true });
  const omit = checklist.getByRole("button", { name: /^Omit original / });
  await chooseDocument(page, "Different synthetic bytes\n", "synthetic-branch-attachment-with-a-deliberately-long-fictional-name.txt");
  await omit.focus();
  await omit.press("Enter");
  const requireOriginal = checklist.getByRole("button", { name: /^Require original / });
  await expect(requireOriginal).toBeFocused();
  await requireOriginal.press("Enter");
  await expect(checklist.getByRole("button", { name: /^Omit original / })).toBeFocused();
  await fitsViewport(page);
});
