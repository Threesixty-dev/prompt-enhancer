import { expect, test, type Page } from "@playwright/test";

/** Visible text nodes below the requested floor and horizontal overflow, scoped to one root. */
async function layoutAudit(page: Page, rootSelector: string, minimumFontSize: number) {
  return page.evaluate(({ selector, minimum }) => {
    const root = document.querySelector<HTMLElement>(selector);
    if (root === null) throw new Error(`synthetic root ${selector} missing`);
    const textSelectors = "small,span,p,strong,button,select,dt,dd,b,td,th,li,summary,h1,h2,h3,h4";
    const tooSmall = [...root.querySelectorAll<HTMLElement>(textSelectors)]
      .filter((element) => {
        const style = getComputedStyle(element);
        return style.display !== "none"
          && style.visibility !== "hidden"
          && element.getClientRects().length > 0
          && Number.parseFloat(style.fontSize) < minimum;
      })
      .map((element) => `${element.tagName.toLowerCase()}.${element.className}`);
    return {
      documentWidth: document.documentElement.scrollWidth,
      viewportWidth: document.documentElement.clientWidth,
      tooSmall,
    };
  }, { selector: rootSelector, minimum: minimumFontSize });
}

async function installClsObserver(page: Page) {
  await page.addInitScript(() => {
    const state = { value: 0 };
    const observer = new PerformanceObserver((list) => {
      for (const rawEntry of list.getEntries()) {
        const entry = rawEntry as PerformanceEntry & { hadRecentInput: boolean; value: number };
        if (!entry.hadRecentInput) state.value += entry.value;
      }
    });
    observer.observe({ type: "layout-shift", buffered: true });
    Object.assign(window, { __syntheticClsState: state, __syntheticClsObserver: observer });
  });
}

async function currentCls(page: Page): Promise<number> {
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  return page.evaluate(() => (window as typeof window & { __syntheticClsState: { value: number } }).__syntheticClsState.value);
}

test.describe("team analytics scopes", () => {
  test("renders permission-aware scopes, honest readiness, and an aggregate-only table", async ({ page }) => {
    await installClsObserver(page);
    await page.goto("/team");
    await expect(page.getByRole("heading", { name: "Me · Team · Organization" })).toBeVisible();
    const scopes = page.getByRole("group", { name: "Analytics scope" });
    await expect(scopes.getByRole("button", { name: /^Team/ })).toHaveAttribute("aria-pressed", "true");
    await expect(scopes.getByRole("button", { name: /^Organization/ })).toHaveAttribute("aria-disabled", "true");
    await expect(page.getByRole("list", { name: "Scopes not available" })).toContainText("Organization");

    const readiness = page.getByRole("list", { name: "Capability readiness" });
    await expect(readiness.locator("[data-card='team_sync']")).toHaveAttribute("data-state", "unavailable");
    await expect(readiness.locator("[data-card='billing']")).toHaveAttribute("data-state", "unavailable");
    await expect(readiness.locator("[data-card='billing']")).toContainText("Nothing is metered or charged");
    await expect(readiness.locator("[data-card='local']")).toContainText("Fictional in-memory fixtures");

    const table = page.getByRole("table");
    await expect(table).toBeVisible();
    await expect(table.getByRole("columnheader")).toHaveText(["Metric", "Value & uncertainty", "Cohort", "Missingness", "Comparability", "Freshness"]);
    const suppressed = table.getByRole("row", { name: /Constraint precision/ });
    await expect(suppressed).toHaveAttribute("data-status", "suppressed");
    await expect(suppressed.locator(".team-interval__point")).toHaveCount(0);
    await expect(suppressed.locator(".team-interval__state")).toHaveText("suppressed · small contributing cohort");
    await expect(page.locator("polygon, polyline")).toHaveCount(0);

    const memberSlot = page.getByLabel("Reserved member visibility region");
    await expect(memberSlot).toHaveAttribute("data-member-panel", "active");
    const teamSlotHeight = await memberSlot.evaluate((element) => element.getBoundingClientRect().height);
    await memberSlot.evaluate((element) => { element.setAttribute("data-e2e-stable-node", "true"); });
    await scopes.getByRole("button", { name: /^Me/ }).click();
    await expect(memberSlot).toHaveAttribute("data-member-panel", "reserved");
    await expect(memberSlot).toHaveAttribute("data-e2e-stable-node", "true");
    expect(await memberSlot.evaluate((element) => element.getBoundingClientRect().height)).toBe(teamSlotHeight);
    await scopes.getByRole("button", { name: /^Team/ }).click();
    await expect(memberSlot).toHaveAttribute("data-member-panel", "active");
    expect(await memberSlot.evaluate((element) => element.getBoundingClientRect().height)).toBe(teamSlotHeight);

    const currentTable = page.getByRole("table");
    const trigger = currentTable.getByRole("button", { name: /Task definition coverage/ });
    await trigger.focus();
    const card = page.getByRole("tooltip");
    await expect(card).toBeVisible();
    await expect(card).toContainText("Meaning");
    await expect(card).toContainText("Next action");
    await expect(card).toContainText("Measured · typed evidence");
    expect((await layoutAudit(page, ".metric-explainer-card", 14)).tooSmall).toEqual([]);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("tooltip")).toHaveCount(0);

    await page.getByRole("button", { name: "Reveal individual members" }).click();
    await expect(page.getByText("Member 01")).toBeVisible();
    await expect(page.getByText("Member 05")).toHaveCount(0);
    await expect(page.getByText(/withheld consent and is not listed/)).toBeVisible();

    const layout = await layoutAudit(page, ".team-analytics", 14);
    expect(layout.documentWidth).toBeLessThanOrEqual(layout.viewportWidth);
    expect(layout.tooSmall).toEqual([]);
    expect(await currentCls(page)).toBeLessThan(0.02);
  });

  test("keeps scope buttons focus-visible in forced-colors and reduced-motion modes", async ({ page }) => {
    await page.emulateMedia({ forcedColors: "active", reducedMotion: "reduce" });
    await page.goto("/team");
    const organization = page.getByRole("group", { name: "Analytics scope" }).getByRole("button", { name: /^Organization/ });
    await organization.focus();
    await expect(organization).toBeFocused();
    const styles = await organization.evaluate((element) => {
      const style = getComputedStyle(element);
      return { outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth, transitionDuration: style.transitionDuration };
    });
    expect(styles.outlineStyle).not.toBe("none");
    expect(Number.parseFloat(styles.outlineWidth)).toBeGreaterThanOrEqual(3);
    expect(styles.transitionDuration).toMatch(/^(0s|0ms)$/);
  });
});

test.describe("task flow", () => {
  test("shows candidate and confirmed columns plus a two-lane timeline", async ({ page }) => {
    await page.goto("/tasks/flow");
    await expect(page.getByRole("heading", { name: "Task flow" })).toBeVisible();
    const board = page.getByRole("group", { name: "Task flow board" });
    await expect(board.getByRole("region")).toHaveCount(4);
    await expect(board.getByRole("region", { name: "Proposed candidates" }).getByRole("article")).toHaveCount(2);
    await expect(board.getByRole("region", { name: "Analyzed tasks" }).getByRole("article")).toHaveCount(1);
    await expect(page.getByRole("region", { name: /Candidates \(proposed/ }).getByRole("button")).toHaveCount(3);
    await page.getByRole("combobox", { name: "Kind" }).selectOption("confirmed");
    await expect(board.getByRole("region", { name: "Proposed candidates" }).getByRole("article")).toHaveCount(0);
    const layout = await layoutAudit(page, ".task-flow", 14);
    expect(layout.documentWidth).toBeLessThanOrEqual(layout.viewportWidth);
    expect(layout.tooSmall).toEqual([]);
  });
});

for (const viewport of [
  { width: 360, height: 500 },
  { width: 420, height: 620 },
]) {
  test(`keeps the current V2 overlay readable at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/overlay/model-ensemble");
    await expect(page.getByRole("heading", { name: "Live metric watch" })).toBeVisible();
    await expect(page.locator(".model-ensemble-overlay__connection")).toHaveText("No active watch");
    await expect(page.getByRole("region", { name: "Live watch scope" })).toBeVisible();
    const drawer = page.locator("details.team-context-drawer");
    await expect(drawer).toBeVisible();
    await expect(drawer).not.toHaveAttribute("open", "");
    await expect(drawer.locator("summary")).toContainText("Team context");
    await expect(drawer.locator("summary")).toContainText("Synthetic platform guild");
    await drawer.locator("summary").click();
    const list = drawer.getByRole("list", { name: /Task framing/ });
    await expect(list).toBeVisible();
    await expect(list.getByRole("listitem")).toHaveCount(6);
    await expect(list.locator("li[data-status='suppressed'] .team-interval__point")).toHaveCount(0);
    await list.getByRole("button", { name: /^Task/ }).first().focus();
    const card = page.getByRole("tooltip");
    await expect(card).toBeVisible();
    await expect(card).toHaveClass(/metric-explainer-card--compact/);
    expect((await layoutAudit(page, ".metric-explainer-card", 12)).tooSmall).toEqual([]);
    await page.keyboard.press("Escape");

    const layout = await layoutAudit(page, ".model-ensemble-overlay", 12);
    expect(layout.documentWidth).toBeLessThanOrEqual(layout.viewportWidth);
    expect(layout.tooSmall).toEqual([]);
  });
}

test("keeps global navigation text at 12px on a 360px viewport", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 720 });
  await page.goto("/team");
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
  expect((await layoutAudit(page, ".primary-nav", 12)).tooSmall).toEqual([]);
});
