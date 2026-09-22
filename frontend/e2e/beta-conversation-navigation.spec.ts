import { expect, test, type Locator, type Page } from "@playwright/test";

const FIXTURE = "/e2e/fixtures/conversation-navigation.html";
const FIND_TEXT = "SYNTHETIC_CONVERSATION_MATCH";
const diagnostics = new WeakMap<Page, { consoleErrors: number; pageErrors: number }>();

async function open(page: Page, query = "") {
  await page.goto(`${FIXTURE}${query}`);
  await expect(page.locator("html")).toHaveAttribute(
    "data-conversation-navigation-event-count",
    query === "?events=201" ? "201" : "260",
  );
  await expect(page.getByText("Current synthetic conversation", { exact: true }).last()).toBeVisible();
  const latest = query === "?events=201"
    ? statusEvent(page, "Synthetic status filler 201.")
    : page.getByText("Synthetic loaded message 260.", { exact: true });
  await expect(latest).toBeVisible();
}

function conversation(page: Page) {
  return page.getByRole("log");
}

function selectedEvent(page: Page, text: string) {
  return page.getByText(text, { exact: true })
    .locator("xpath=ancestor::div[@tabindex='-1'][1]");
}

function statusEvent(page: Page, text: string) {
  return conversation(page).locator(".agent__activity-event").filter({
    hasText: new RegExp(`^Status\\s*${text.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&")}$`, "u"),
  });
}

async function openFind(page: Page) {
  const summary = conversation(page).locator("summary").filter({ hasText: /^Find in conversation$/u });
  await clickWithGeometry(page, summary, "find-summary");
  return page.getByRole("searchbox", { name: "Find in conversation", exact: true });
}

function findStatus(page: Page) {
  return conversation(page).locator(".agent-conversation-find").getByRole("status");
}

async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

async function clickWithGeometry(page: Page, locator: Locator, action: string) {
  try {
    await locator.click({ timeout: 5_000 });
  } catch (error) {
    let diagnostic = JSON.stringify({ diagnostic: "unavailable" });
    try {
      const geometry = await page.evaluate(() => {
        const rect = (element: Element | null, includeComputed = false) => {
          if (!(element instanceof HTMLElement)) return null;
          const bounds = element.getBoundingClientRect();
          const top = document.elementFromPoint(bounds.left + bounds.width / 2, bounds.top + bounds.height / 2);
          const computed = getComputedStyle(element);
          return {
            className: element.className,
            scrollTop: element.scrollTop,
            topElement: top instanceof HTMLElement
              ? { ariaLabel: top.getAttribute("aria-label"), className: top.className, role: top.getAttribute("role"), tag: top.tagName }
              : null,
            x: bounds.x,
            y: bounds.y,
            width: bounds.width,
            height: bounds.height,
            ...(includeComputed ? {
              computedHeight: computed.height,
              computedMaxHeight: computed.maxHeight,
              computedOverflowY: computed.overflowY,
              clientHeight: element.clientHeight,
              scrollHeight: element.scrollHeight,
            } : {}),
          };
        };
        const findPanel = document.querySelector(".agent-conversation-find");
        const next = findPanel === null
          ? null
          : Array.from(findPanel.querySelectorAll("button")).find(
            (button) => button.textContent?.trim() === "Find next",
          ) ?? null;
        const log = document.querySelector("[role='log']");
        const logStyle = log instanceof HTMLElement ? getComputedStyle(log) : null;
        return {
          body: rect(document.body),
          find: rect(findPanel, true),
          finderBody: rect(findPanel?.querySelector(".agent-conversation-find__body") ?? null),
          next: rect(next),
          findSummary: rect(findPanel?.querySelector("summary") ?? null),
          jump: rect(document.querySelector(".agent__jump-latest")),
          log: log === null ? null : {
            rect: rect(log),
            containerType: logStyle?.getPropertyValue("container-type") ?? null,
            clientHeight: log instanceof HTMLElement ? log.clientHeight : null,
            scrollHeight: log instanceof HTMLElement ? log.scrollHeight : null,
            scrollTop: log instanceof HTMLElement ? log.scrollTop : null,
          },
          pager: rect(document.querySelector(".agent__transcript-window")),
          composer: rect(document.querySelector(".agent__compose")),
        };
      });
      diagnostic = JSON.stringify(geometry);
      await test.info().attach(`pointer-geometry-${action}`, {
        body: diagnostic,
        contentType: "application/json",
      });
    } catch {
      // Preserve the original pointer failure as the cause if diagnostics fail.
    }
    const originalMessage = error instanceof Error ? error.message : String(error);
    throw new Error(`${action} pointer click failed: ${originalMessage}\nPointer geometry: ${diagnostic}`, { cause: error });
  }
}

async function expectCenterUnobscured(locator: Locator, action: string) {
  const geometry = await locator.evaluate((element) => {
    const rect = (candidate: Element | null) => {
      if (!(candidate instanceof HTMLElement)) return null;
      const bounds = candidate.getBoundingClientRect();
      return {
        x: bounds.x,
        y: bounds.y,
        top: bounds.top,
        right: bounds.right,
        bottom: bounds.bottom,
        width: bounds.width,
        height: bounds.height,
        scrollTop: candidate.scrollTop,
      };
    };
    const bounds = element.getBoundingClientRect();
    const top = document.elementFromPoint(bounds.left + bounds.width / 2, bounds.top + bounds.height / 2);
    return {
      target: {
        x: bounds.x,
        y: bounds.y,
        top: bounds.top,
        right: bounds.right,
        bottom: bounds.bottom,
        width: bounds.width,
        height: bounds.height,
      },
      visible: bounds.width > 0 && bounds.height > 0
        && bounds.top >= 0 && bounds.bottom <= window.innerHeight,
      center: { x: bounds.left + bounds.width / 2, y: bounds.top + bounds.height / 2 },
      topIsTarget: top === element || (top instanceof Node && element.contains(top)),
      topElement: top instanceof HTMLElement
        ? { ariaLabel: top.getAttribute("aria-label"), className: top.className, role: top.getAttribute("role"), tag: top.tagName }
        : null,
      log: rect(document.querySelector("[role='log']")),
      composer: rect(document.querySelector(".agent__compose")),
    };
  });
  const diagnostic = JSON.stringify(geometry);
  expect(geometry.visible, `${action} is visible in the viewport: ${diagnostic}`).toBe(true);
  expect(geometry.topIsTarget, `${action} center is not obscured: ${diagnostic}`).toBe(true);
}

test.beforeEach(async ({ page }) => {
  const counts = { consoleErrors: 0, pageErrors: 0 };
  diagnostics.set(page, counts);
  page.on("console", (message) => { if (message.type() === "error") counts.consoleErrors += 1; });
  page.on("pageerror", () => { counts.pageErrors += 1; });
});

test.afterEach(async ({ page }) => {
  const counts = diagnostics.get(page)!;
  expect(counts.consoleErrors, "conversation navigation fixture console errors").toBe(0);
  expect(counts.pageErrors, "conversation navigation fixture page errors").toBe(0);
  await expect(page.locator("html")).toHaveAttribute("data-conversation-navigation-model-actions", "0");
  await expect(page.locator("html")).toHaveAttribute("data-conversation-navigation-mutation-actions", "0");
  await expect(page.locator("html")).toHaveAttribute("data-conversation-navigation-saved-searches", "0");
  await expect(page.locator("html")).toHaveAttribute("data-conversation-navigation-sent-messages", "0");
});

test.describe("current conversation navigation", () => {
  test("keeps Jump to latest activity available after Earlier even when the older page fits", async ({ page }) => {
    await open(page, "?events=201");
    const timeline = conversation(page);
    await clickWithGeometry(page, timeline.getByRole("button", { name: /^Earlier /u }), "earlier");
    await expect(statusEvent(page, "Synthetic status filler 1.")).toBeVisible();
    await expect(statusEvent(page, "Synthetic status filler 201.")).not.toBeVisible();

    await expect(timeline.getByRole("button", { name: "Jump to latest activity", exact: true })).toBeVisible();
    await timeline.getByRole("button", { name: "Jump to latest activity", exact: true }).click();
    await expect(statusEvent(page, "Synthetic status filler 201.")).toBeVisible();
    await expect(statusEvent(page, "Synthetic status filler 1.")).not.toBeVisible();
  });

  test("finds only loaded user and assistant messages and opens the matching page", async ({ page }) => {
    await open(page);
    const readsBefore = await page.locator("html").getAttribute("data-conversation-navigation-persisted-reads");
    const liveReadsBefore = await page.locator("html").getAttribute("data-conversation-navigation-live-event-reads");
    const find = await openFind(page);
    await find.fill(FIND_TEXT);
    await expect(page.getByText("Synthetic loaded message 260.", { exact: true })).toBeVisible();
    await clickWithGeometry(page, page.getByRole("button", { name: "Find next", exact: true }), "find-next");
    await expect(findStatus(page)).toHaveText("Message 1 of 2 selected.");
    const first = selectedEvent(page, `${FIND_TEXT} in visible message 7.`);
    await expect(first).toBeFocused();
    await expect(page.getByText(`${FIND_TEXT} tool output must not be searchable.`, { exact: true })).not.toBeVisible();
    await expect(page.getByText(`${FIND_TEXT} reasoning must not be searchable.`, { exact: true })).not.toBeVisible();
    await expect(page.getByText(`${FIND_TEXT} incomplete delta must not be searchable.`, { exact: true })).not.toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("data-conversation-navigation-persisted-reads", readsBefore ?? "0");
    await expect(page.locator("html")).toHaveAttribute("data-conversation-navigation-live-event-reads", liveReadsBefore ?? "0");
  });

  test("supports next, previous, Enter, Shift+Enter, and case-aware local matching", async ({ page }) => {
    await open(page);
    const find = await openFind(page);
    await find.fill(FIND_TEXT);
    await find.press("Enter");
    await expect(findStatus(page)).toHaveText("Message 1 of 2 selected.");
    await find.press("Enter");
    await expect(findStatus(page)).toHaveText("Message 2 of 2 selected.");
    await find.press("Shift+Enter");
    await expect(findStatus(page)).toHaveText("Message 1 of 2 selected.");
    await page.getByRole("checkbox", { name: "Match case", exact: true }).check();
    await find.fill(FIND_TEXT.toLowerCase());
    await clickWithGeometry(page, page.getByRole("button", { name: "Find next", exact: true }), "find-next");
    await expect(findStatus(page)).toHaveText("No loaded user or assistant messages match this text.");
    await page.getByRole("checkbox", { name: "Match case", exact: true }).uncheck();
    await page.getByRole("button", { name: "Find previous", exact: true }).click();
    await expect(findStatus(page)).toHaveText("Message 2 of 2 selected.");
  });

  test("explains empty and absent local searches without changing the current page", async ({ page }) => {
    await open(page);
    const find = await openFind(page);
    await clickWithGeometry(page, page.getByRole("button", { name: "Find next", exact: true }), "find-next");
    await expect(findStatus(page)).toHaveText("Enter text to find in the loaded messages.");
    await find.fill("SYNTHETIC_ABSENT_TEXT");
    await clickWithGeometry(page, page.getByRole("button", { name: "Find next", exact: true }), "find-next");
    await expect(findStatus(page)).toHaveText("No loaded user or assistant messages match this text.");
    await expect(page.getByText("Synthetic loaded message 260.", { exact: true })).toBeVisible();
  });

  for (const viewport of [
    { name: "desktop extra-short", width: 1440, height: 420 },
    { name: "desktop compact", width: 1440, height: 600 },
    { name: "desktop work area", width: 1440, height: 720 },
    { name: "narrow short", width: 360, height: 420 },
  ]) {
    test(`keeps Find next unobscured after focus and scroll transitions at ${viewport.name}`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await open(page);
      const find = await openFind(page);
      const next = page.getByRole("button", { name: "Find next", exact: true });
      await clickWithGeometry(page, next, "find-next-empty");
      await expect(findStatus(page)).toHaveText("Enter text to find in the loaded messages.");
      await find.fill("SYNTHETIC_ABSENT_TEXT");
      await next.scrollIntoViewIfNeeded();
      await expectCenterUnobscured(next, "find-next-absent");
      await clickWithGeometry(page, next, "find-next-absent");
      await expect(findStatus(page)).toHaveText("No loaded user or assistant messages match this text.");

      await find.focus();
      await page.keyboard.press("Tab");
      await page.keyboard.press("Shift+Tab");
      await conversation(page).hover();
      await page.mouse.wheel(0, 500);
      await next.scrollIntoViewIfNeeded();
      await expectCenterUnobscured(next, "find-next-after-scroll");
      await clickWithGeometry(page, next, "find-next-after-scroll");
      await expect(findStatus(page)).toHaveText("No loaded user or assistant messages match this text.");
    });
  }

  test("keeps the resized composer and Find controls usable in the desktop work area", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await open(page);
    const draft = page.getByRole("textbox", { name: "Message to the agent", exact: true });
    const draftText = "Synthetic resizable conversation draft.";
    await draft.fill(draftText);
    const before = await draft.boundingBox();
    expect(before).not.toBeNull();
    await page.mouse.move(before!.x + before!.width - 4, before!.y + before!.height - 4);
    await page.mouse.down();
    await page.mouse.move(before!.x + before!.width - 4, before!.y + before!.height + 100, { steps: 5 });
    await page.mouse.up();
    const after = await draft.boundingBox();
    expect(after).not.toBeNull();
    expect(after!.height).toBeGreaterThan(before!.height + 40);

    const log = conversation(page);
    const composer = page.getByRole("form", { name: "Message composer", exact: true });
    const logBounds = await log.boundingBox();
    const composerBounds = await composer.boundingBox();
    expect(logBounds).not.toBeNull();
    expect(composerBounds).not.toBeNull();
    expect(logBounds!.height).toBeGreaterThan(100);
    expect(logBounds!.y + logBounds!.height).toBeLessThanOrEqual(composerBounds!.y);

    const find = await openFind(page);
    const next = page.getByRole("button", { name: "Find next", exact: true });
    await clickWithGeometry(page, next, "find-next-resized-empty");
    await expect(findStatus(page)).toHaveText("Enter text to find in the loaded messages.");
    await find.fill("SYNTHETIC_ABSENT_TEXT");
    await next.scrollIntoViewIfNeeded();
    await clickWithGeometry(page, next, "find-next-resized-absent");
    await expect(findStatus(page)).toHaveText("No loaded user or assistant messages match this text.");
    await expect(draft).toHaveValue(draftText);
  });

  test("resets local find state when the current chat changes to metadata-only", async ({ page }) => {
    await open(page);
    const find = await openFind(page);
    await find.fill(FIND_TEXT);
    await clickWithGeometry(page, page.getByRole("button", { name: "Find next", exact: true }), "find-next");
    await page.getByRole("button", { name: /^Metadata-only synthetic chat ·/u }).click();
    await expect(page.getByText("Metadata-only live conversation text.", { exact: true })).toBeVisible();
    const metadataFind = await openFind(page);
    await metadataFind.fill("Metadata-only live");
    await page.getByRole("button", { name: "Find next", exact: true }).click();
    await expect(findStatus(page)).toHaveText("Message 1 of 1 selected.");
    await expect(page.locator("html")).toHaveAttribute("data-conversation-navigation-saved-searches", "0");
  });

  test("does not leave an older local page when synthetic activity arrives", async ({ page }) => {
    await open(page);
    const timeline = conversation(page);
    await clickWithGeometry(page, timeline.getByRole("button", { name: /^Earlier /u }), "earlier");
    await expect(page.getByText(`${FIND_TEXT} in visible message 7.`, { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Append synthetic activity", exact: true }).click();
    await expect(page.getByText(`${FIND_TEXT} in visible message 7.`, { exact: true })).toBeVisible();
    await expect(statusEvent(page, "Synthetic appended status activity.")).not.toBeVisible();
    await expect(timeline.getByRole("button", { name: "Latest", exact: true })).toBeVisible();
  });

  test("keeps visible event rows separated and the log/composer in the 720px work area", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 720 });
    await open(page);
    const timeline = conversation(page);
    const rows = timeline.locator(".agent-conversation-navigation > [tabindex='-1']");
    const rowBounds = await rows.evaluateAll((elements) => elements.slice(0, 4).map((element) => {
      const bounds = element.getBoundingClientRect();
      return { bottom: bounds.bottom, top: bounds.top };
    }));
    expect(rowBounds).toHaveLength(4);
    for (let index = 1; index < rowBounds.length; index += 1) {
      expect(rowBounds[index].top).toBeGreaterThan(rowBounds[index - 1].bottom);
    }

    const [logBounds, composerBounds] = await Promise.all([
      timeline.boundingBox(),
      page.getByRole("textbox", { name: "Message to the agent", exact: true }).boundingBox(),
    ]);
    expect(logBounds).not.toBeNull();
    expect(composerBounds).not.toBeNull();
    expect(logBounds!.y).toBeGreaterThanOrEqual(0);
    expect(logBounds!.y).toBeLessThan(720);
    expect(composerBounds!.y).toBeGreaterThan(logBounds!.y);
    expect(composerBounds!.y + composerBounds!.height).toBeLessThanOrEqual(720);
  });

  for (const width of [360, 1440]) {
    test(`keeps collapsed find controls keyboard-accessible at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await open(page);
      const summary = conversation(page).locator("summary", { hasText: "Find in conversation" });
      await summary.focus();
      await summary.press("Enter");
      const find = page.getByRole("searchbox", { name: "Find in conversation", exact: true });
      await find.fill(FIND_TEXT);
      await find.focus();
      await page.keyboard.press("Tab");
      await page.keyboard.press("Tab");
      await expect(page.getByRole("button", { name: "Find next", exact: true })).toBeFocused();
      await page.keyboard.press("Enter");
      await expect(findStatus(page)).toHaveText("Message 1 of 2 selected.");
      await noOverflow(page);
    });
  }
});
