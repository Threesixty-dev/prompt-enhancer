import { expect, test, type Page } from "@playwright/test";

const FIXTURE = "/e2e/fixtures/workspace-navigation.html";
const TARGET_LINE = 1000;
const FAR_RIGHT_MATCH = "SYNTHETIC_FAR_RIGHT_MATCH";
const LOCAL_MATCH = "SYNTHETIC_LOCAL_MATCH";
const diagnostics = new WeakMap<Page, { consoleErrors: number; pageErrors: number }>();

async function open(page: Page, mode?: "dialog") {
  await page.goto(mode === undefined ? FIXTURE : `${FIXTURE}?mode=${mode}`);
}

async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

async function openSearchResult(page: Page) {
  await page.getByText("Workspace tools & safety", { exact: true }).click();
  const discovery = page.getByRole("region", { name: "Workspace discovery", exact: true });
  await discovery.getByLabel("Search workspace contents", { exact: true }).fill(FAR_RIGHT_MATCH);
  await discovery.getByRole("button", { name: "Search", exact: true }).click();
  await discovery.getByRole("button", { name: `Open search result navigation.ts line ${TARGET_LINE}`, exact: true }).click();
}

function editor(page: Page) {
  return page.getByRole("textbox", { name: "Workspace file editor", exact: true });
}

test.beforeEach(async ({ page }) => {
  const counts = { consoleErrors: 0, pageErrors: 0 };
  diagnostics.set(page, counts);
  page.on("console", (message) => { if (message.type() === "error") counts.consoleErrors += 1; });
  page.on("pageerror", () => { counts.pageErrors += 1; });
});

test.afterEach(async ({ page }) => {
  const counts = diagnostics.get(page)!;
  expect(counts.consoleErrors, "workspace navigation fixture console errors").toBe(0);
  expect(counts.pageErrors, "workspace navigation fixture page errors").toBe(0);
  await expect(page.locator("html")).not.toHaveAttribute("data-write-attempts", /[1-9]/);
});

test.describe("workspace navigation", () => {
  test("opens a distant recorded search result with a focused, visible whole-line selection", async ({ page }) => {
    await open(page);
    await openSearchResult(page);
    const workspaceEditor = editor(page);
    await expect(workspaceEditor).toBeFocused();
    await expect(page.getByRole("status")).toHaveText(`Recorded search position line ${TARGET_LINE} selected; match text was not rechecked.`);

    const selection = await workspaceEditor.evaluate((element) => {
      const textarea = element as HTMLTextAreaElement;
      const lineStart = textarea.value.lastIndexOf("\n", textarea.value.indexOf("SYNTHETIC_FAR_RIGHT_MATCH")) + 1;
      const lineEnd = textarea.value.indexOf("\n", lineStart);
      const lineHeight = Number.parseFloat(getComputedStyle(textarea).lineHeight);
      const fontSize = Number.parseFloat(getComputedStyle(textarea).fontSize);
      const resolvedLineHeight = Number.isFinite(lineHeight) && lineHeight > 0
        ? lineHeight < 4 ? lineHeight * fontSize : lineHeight
        : fontSize * 1.5;
      const targetTop = (1000 - 1) * resolvedLineHeight;
      return {
        end: textarea.selectionEnd,
        horizontalAtLineStart: textarea.scrollLeft === 0,
        start: textarea.selectionStart,
        verticalVisible: targetTop >= textarea.scrollTop
          && targetTop + resolvedLineHeight <= textarea.scrollTop + textarea.clientHeight,
        wholeLine: textarea.value.slice(textarea.selectionStart, textarea.selectionEnd),
        expectedEnd: lineEnd,
        expectedStart: lineStart,
      };
    });
    expect(selection.start).toBe(selection.expectedStart);
    expect(selection.end).toBe(selection.expectedEnd);
    expect(selection.wholeLine).toContain(FAR_RIGHT_MATCH);
    expect(selection.horizontalAtLineStart).toBe(true);
    expect(selection.verticalVisible).toBe(true);
  });

  test("finds next and previous local matches without reading the file again", async ({ page }) => {
    await open(page);
    await page.getByRole("button", { name: "navigation.ts", exact: true }).click();
    const workspaceEditor = editor(page);
    await workspaceEditor.press("Control+f");
    const find = page.getByRole("searchbox", { name: "Find in open file", exact: true });
    await expect(find).toBeFocused();
    await find.fill(LOCAL_MATCH);
    await find.press("Shift+Enter");
    await expect(page.getByRole("status")).toHaveText("Match 2 of 2 selected.");
    await expect(workspaceEditor).toBeFocused();
    expect(await workspaceEditor.evaluate((element) => (element as HTMLTextAreaElement).value.slice((element as HTMLTextAreaElement).selectionStart, (element as HTMLTextAreaElement).selectionEnd))).toBe(LOCAL_MATCH);
    await workspaceEditor.press("Control+f");
    await find.press("Enter");
    await expect(page.getByRole("status")).toHaveText("Match 1 of 2 selected.");
    await workspaceEditor.press("Control+f");
    await page.getByRole("button", { name: "Find previous", exact: true }).click();
    await expect(page.getByRole("status")).toHaveText("Match 2 of 2 selected.");
    await workspaceEditor.press("Control+f");
    await page.getByRole("button", { name: "Find next", exact: true }).click();
    await expect(page.getByRole("status")).toHaveText("Match 1 of 2 selected.");
    await expect(page.locator("html")).toHaveAttribute("data-file-reads", "1");
  });

  test("keeps a local far-right match visible, then returns to a short line at column one", async ({ page }) => {
    await open(page);
    await page.getByRole("button", { name: "navigation.ts", exact: true }).click();
    const workspaceEditor = editor(page);
    await workspaceEditor.press("Control+f");
    await page.getByRole("searchbox", { name: "Find in open file", exact: true }).fill(FAR_RIGHT_MATCH);
    await page.getByRole("button", { name: "Find next", exact: true }).click();
    await expect(page.getByRole("status")).toHaveText("Match 1 of 1 selected.");

    const selectedRangeIsVisible = await workspaceEditor.evaluate((element) => {
      const textarea = element as HTMLTextAreaElement;
      const textBeforeSelection = textarea.value.slice(0, textarea.selectionStart);
      const selectedText = textarea.value.slice(textarea.selectionStart, textarea.selectionEnd);
      const canvas = document.createElement("canvas");
      const context = canvas.getContext("2d");
      if (context === null) return false;
      context.font = getComputedStyle(textarea).font;
      const currentLine = textBeforeSelection.slice(textBeforeSelection.lastIndexOf("\n") + 1);
      const start = context.measureText(currentLine).width;
      const end = start + context.measureText(selectedText).width;
      return start >= textarea.scrollLeft && end <= textarea.scrollLeft + textarea.clientWidth;
    });
    expect(selectedRangeIsVisible).toBe(true);

    await workspaceEditor.press("Control+g");
    await page.getByRole("spinbutton", { name: "Go to line", exact: true }).fill("1001");
    await page.getByRole("button", { name: "Go to line", exact: true }).click();
    await expect(page.getByRole("status")).toHaveText("Line 1001 selected.");
    expect(await workspaceEditor.evaluate((element) => {
      const textarea = element as HTMLTextAreaElement;
      const lineStart = textarea.value.lastIndexOf("\n", textarea.selectionStart - 1) + 1;
      return textarea.selectionStart === lineStart && textarea.scrollLeft === 0;
    })).toBe(true);
  });

  test("goes to a whole line", async ({ page }) => {
    await open(page);
    await page.getByRole("button", { name: "navigation.ts", exact: true }).click();
    const workspaceEditor = editor(page);
    await workspaceEditor.press("Control+g");
    const line = page.getByRole("spinbutton", { name: "Go to line", exact: true });
    await expect(line).toBeFocused();
    await line.fill("1001");
    await page.getByRole("button", { name: "Go to line", exact: true }).click();
    await expect(page.getByRole("status")).toHaveText("Line 1001 selected.");
    await expect(page.getByLabel("Cursor position: line 1001, column 1; 1101 lines", { exact: true })).toBeVisible();
  });

  test("keeps the parent workspace dialog open when Escape closes local tools", async ({ page }) => {
    await open(page, "dialog");
    const dialog = page.getByRole("dialog", { name: "Synthetic workspace dialog", exact: true });
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "navigation.ts", exact: true }).click();
    const workspaceEditor = dialog.getByRole("textbox", { name: "Workspace file editor", exact: true });
    await workspaceEditor.press("Control+f");
    await dialog.getByRole("searchbox", { name: "Find in open file", exact: true }).fill(LOCAL_MATCH);
    await dialog.getByRole("button", { name: "Find next", exact: true }).click();
    await expect(workspaceEditor).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(dialog).toBeVisible();
    await expect(dialog.locator("details").filter({ hasText: "Find & go to line" })).not.toHaveAttribute("open", "");
    await expect(workspaceEditor).toBeFocused();
  });

  test("keeps a same-file dirty draft when a recorded search result is opened", async ({ page }) => {
    await open(page);
    await page.getByRole("button", { name: "navigation.ts", exact: true }).click();
    const workspaceEditor = editor(page);
    await workspaceEditor.fill("Synthetic unsaved workspace draft\n");
    await openSearchResult(page);
    await expect(workspaceEditor).toHaveValue("Synthetic unsaved workspace draft\n");
    await expect(page.locator("html")).toHaveAttribute("data-file-reads", "1");
  });

  test("keeps or explicitly discards a dirty draft before opening another file", async ({ page }) => {
    await open(page);
    await page.getByRole("button", { name: "navigation.ts", exact: true }).click();
    const workspaceEditor = editor(page);
    await workspaceEditor.fill("Synthetic dirty draft\n");
    await page.getByRole("button", { name: "notes.txt", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Discard workspace changes?", exact: true });
    await dialog.getByRole("button", { name: "Keep draft", exact: true }).click();
    await expect(workspaceEditor).toHaveValue("Synthetic dirty draft\n");
    await page.getByRole("button", { name: "notes.txt", exact: true }).click();
    await dialog.getByRole("button", { name: "Discard and open file", exact: true }).click();
    await expect(workspaceEditor).toHaveValue("Synthetic second file.\n");
  });

  for (const width of [360, 1440]) {
    test(`keeps keyboard navigation responsive at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await open(page);
      await page.getByRole("button", { name: "navigation.ts", exact: true }).click();
      const workspaceEditor = editor(page);
      await workspaceEditor.press("Control+f");
      await expect(page.getByRole("searchbox", { name: "Find in open file", exact: true })).toBeFocused();
      await noOverflow(page);
    });
  }
});
