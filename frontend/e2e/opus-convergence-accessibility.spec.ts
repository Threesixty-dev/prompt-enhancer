import { expect, test, type Locator, type Page } from "@playwright/test";

// Independent acceptance matrix for keyboard, short-height, disabled-explanation
// and owner-scope recovery obligations that the existing Agent browser suites
// exercise only indirectly. Every state comes from the existing synthetic
// workflow-panels fixture; no real provider, model, transport or network call is
// involved, and no application file is modified by this suite.
const AGENT_SHELL = "/e2e/fixtures/workflow-panels.html?panel=agent-shell";
const CONTROLLER_OWNERSHIP = "/e2e/fixtures/workflow-panels.html?panel=agent-controller-ownership";

type BlockedControl = {
  control: string;
  explanation: string;
};

async function noHorizontalOverflow(page: Page): Promise<void> {
  const widths = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(widths.content).toBeLessThanOrEqual(widths.viewport);
}

// The accessible description a screen-reader user actually receives: referenced
// aria-describedby text first, then the title fallback.
async function describedText(locator: Locator): Promise<string> {
  return locator.evaluate((element) => {
    const referenced = (element.getAttribute("aria-describedby") ?? "")
      .split(/\s+/u)
      .filter(Boolean)
      .map((id) => document.getElementById(id)?.textContent?.trim() ?? "")
      .filter(Boolean)
      .join(" ");
    return referenced || (element.getAttribute("title") ?? "").trim();
  });
}

// Every unavailable control inside the reviewed container must carry its own
// reason; a control that is merely dimmed is not a truthful refusal.
async function blockedControls(container: Locator): Promise<BlockedControl[]> {
  return container
    .locator("button:disabled, select:disabled, input:disabled, textarea:disabled")
    .evaluateAll((elements) => elements.map((element) => {
      const referenced = (element.getAttribute("aria-describedby") ?? "")
        .split(/\s+/u)
        .filter(Boolean)
        .map((id) => document.getElementById(id)?.textContent?.trim() ?? "")
        .filter(Boolean)
        .join(" ");
      return {
        control: (element.getAttribute("aria-label")
          ?? element.textContent
          ?? element.tagName).trim(),
        explanation: (referenced || (element.getAttribute("title") ?? "")).trim(),
      };
    }));
}

async function openComposerRuntime(page: Page): Promise<{
  panel: Locator;
  runtime: Locator;
  summary: Locator;
}> {
  const runtime = page.getByRole("region", { name: "Shared local model runtime", exact: true });
  const summary = runtime.getByLabel(/Model and context settings\./u);
  await expect(summary).toBeVisible();
  await summary.focus();
  await expect(summary).toBeFocused();
  await page.keyboard.press("Enter");
  const panel = runtime.getByRole("dialog", { name: "Choose model and runtime settings", exact: true });
  await expect(panel).toBeVisible();
  return { panel, runtime, summary };
}

test("composer runtime overlay explains its already-applied refusal instead of dimming silently", async ({ page }) => {
  await page.goto(AGENT_SHELL);
  const { panel } = await openComposerRuntime(page);

  const apply = panel.getByRole("button", { name: "Applied", exact: true });
  await expect(apply).toBeDisabled();
  expect(await describedText(apply)).toBe(
    "These model, placement, and context settings are already applied.",
  );

  const decision = panel.locator(".agent-runtime__decision-note");
  await expect(decision).toHaveAttribute("data-state", "current");
  await expect(decision).toContainText(
    "This chat already uses this model, placement, and context configuration.",
  );

  // Controls that remain genuinely usable must not be blocked by the same state.
  await expect(panel.getByRole("button", { name: "Stop runtime", exact: true })).toBeEnabled();
  await expect(panel.getByRole("button", { name: "Refresh", exact: true })).toBeEnabled();
  await expect(panel.getByRole("combobox", { name: "Model", exact: true })).toBeEnabled();

  const blocked = await blockedControls(panel);
  expect(blocked.filter((entry) => entry.explanation === "")).toEqual([]);
});

test("composer runtime overlay opens, tabs and closes by keyboard with focus restored", async ({ page }) => {
  await page.goto(AGENT_SHELL);
  const { panel, summary } = await openComposerRuntime(page);

  await page.keyboard.press("Tab");
  await expect(panel.getByRole("button", { name: "Close model and context settings", exact: true }))
    .toBeFocused();
  await page.keyboard.press("Tab");
  await expect(panel.getByRole("combobox", { name: "Model", exact: true })).toBeFocused();

  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  await expect(summary).toBeFocused();
});

test("Escape inside the nested runtime evidence disclosure closes the whole overlay once", async ({ page }) => {
  await page.goto(AGENT_SHELL);
  const { panel, summary } = await openComposerRuntime(page);

  const evidence = panel.getByText("Context, compatibility & runtime evidence", { exact: true });
  await expect(panel.getByText("Offload evidence", { exact: true })).toBeHidden();
  await evidence.click();
  const runtimeEvidence = panel.getByText("Runtime evidence & capabilities", { exact: true });
  await runtimeEvidence.click();
  await expect(panel.getByText("Offload evidence", { exact: true })).toBeVisible();

  await runtimeEvidence.focus();
  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  await expect(summary).toBeFocused();
});

test("pointer dismissal outside the runtime overlay closes it without pulling focus back", async ({ page }) => {
  await page.goto(AGENT_SHELL);
  const { panel, summary } = await openComposerRuntime(page);

  const heading = page.locator("h1#agent-title");
  await expect(heading).toBeVisible();
  await heading.click();
  await expect(panel).toBeHidden();
  await expect(summary).not.toBeFocused();
  const focusInsideDisclosure = await page.evaluate(() => {
    const active = document.activeElement;
    return active instanceof Element
      && active.closest(".agent-runtime__composer-disclosure") !== null;
  });
  expect(focusInsideDisclosure).toBe(false);
});

test("560px-tall window keeps the runtime overlay and its primary action inside the viewport", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 560 });
  await page.goto(AGENT_SHELL);
  const { panel, summary } = await openComposerRuntime(page);

  await expect(summary).toBeInViewport();
  const geometry = await panel.evaluate((element) => {
    const box = element.getBoundingClientRect();
    return {
      bottom: box.bottom,
      height: box.height,
      scrollable: element.scrollHeight > element.clientHeight,
      top: box.top,
      viewportHeight: window.innerHeight,
    };
  });
  expect(geometry.top, JSON.stringify(geometry)).toBeGreaterThanOrEqual(0);
  expect(geometry.bottom, JSON.stringify(geometry)).toBeLessThanOrEqual(geometry.viewportHeight);
  expect(geometry.height, JSON.stringify(geometry)).toBeGreaterThan(0);

  // The sticky action row must stay reachable even when the panel scrolls.
  await expect(panel.getByRole("button", { name: "Applied", exact: true })).toBeInViewport();
  await expect(panel.getByRole("button", { name: "Stop runtime", exact: true })).toBeInViewport();
  await noHorizontalOverflow(page);
});

test("browser-only chat setup names the exact native gate for its blocked protected actions", async ({ page }) => {
  await page.goto(AGENT_SHELL);
  const newChat = page.getByRole("button", { name: "New chat", exact: true });
  await newChat.click();
  const setup = page.getByRole("dialog", { name: "New session", exact: true });
  await expect(setup).toBeVisible();

  const protectedActions = setup.getByRole("group", { name: "Protected actions", exact: true });
  await expect(protectedActions).toHaveAttribute("disabled", "");
  const explanation = await describedText(protectedActions);
  expect(explanation).toContain("read-only sessions");
  expect(explanation).toContain("prompt-enhancer agent-desktop");

  const writes = protectedActions.getByRole("checkbox", { name: /^May write files/u });
  await expect(writes).toBeDisabled();
  await expect(writes).not.toBeChecked();
  const webFetch = protectedActions.getByRole("checkbox", { name: /^Web fetch unavailable/u });
  await expect(webFetch).toBeDisabled();
  await expect(webFetch).toHaveAccessibleName(/no governed fetcher is installed/u);

  await page.keyboard.press("Escape");
  await expect(setup).toBeHidden();
  await expect(newChat).toBeFocused();
});

test("external controller ownership explains every unavailable owner action and offers no native takeover", async ({ page }) => {
  await page.goto(CONTROLLER_OWNERSHIP);
  await page.getByRole("button", { name: /Agent settings/ }).click();
  await page.getByRole("tab", { name: "Connections", exact: true }).click();
  const controller = page.getByRole("region", { name: "Controller API", exact: true });
  await expect(controller).toBeVisible();

  await expect(controller.getByText(
    "Open the owned native app window to create, rotate, or revoke connections.",
    { exact: true },
  )).toBeVisible();
  // In a browser tab owner presence is unproven, and that gate blocks these
  // actions before connection state, transport support or settlement does. Each
  // button must announce the gate that actually stops it, not the panel-wide
  // note above and not a lower-priority reason it would report elsewhere.
  const rotateGate = "Owner presence is unproven, so this app cannot rotate a credential."
    + " Focus the owned native app window and try again.";
  const revokeGate = "Owner presence is unproven, so this app cannot revoke a credential."
    + " Focus the owned native app window and try again.";
  const releaseGate = "Owner presence is unproven, so this app cannot ask the backend to"
    + " release external control. Focus the owned native app window and try again.";

  const rotate = controller.getByRole("button", { name: "Rotate", exact: true });
  const revoke = controller.getByRole("button", { name: "Revoke", exact: true });
  await expect(rotate).toHaveCount(2);
  await expect(revoke).toHaveCount(2);
  for (const button of await rotate.all()) {
    await expect(button).toBeDisabled();
    expect(await describedText(button)).toBe(rotateGate);
  }
  for (const button of await revoke.all()) {
    await expect(button).toBeDisabled();
    expect(await describedText(button)).toBe(revokeGate);
  }

  const owner = controller.getByLabel("External control for Synthetic coding chat", { exact: true });
  const release = owner.getByRole("button", { name: "Release settled control", exact: true });
  await expect(release).toBeDisabled();
  // The settlement wording lives in this button's title fallback; the native
  // gate takes priority, so the announced description must be the gate itself.
  expect(await describedText(release)).toBe(releaseGate);
  await expect(owner).toContainText("Resolve the exact approval in the native Agent chat");

  // Nothing else inside the owner scope may be dimmed without its own reason.
  expect((await blockedControls(owner)).filter((entry) => entry.explanation === ""))
    .toEqual([]);

  // A handoff may only be accepted by the exact external client, so the native
  // surface must expose no control that could imply local acceptance.
  const incoming = controller.getByLabel("Incoming control handoff for Synthetic coding chat", { exact: true });
  await expect(incoming.locator("button, a[href], input, select, textarea")).toHaveCount(0);
});

test("560px-tall window keeps owner-scope recovery guidance readable and Escape-closable", async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 560 });
  await page.goto(CONTROLLER_OWNERSHIP);
  const settings = page.getByRole("button", { name: /Agent settings/ });
  await settings.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Agent settings", exact: true });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("tab", { name: "Connections", exact: true }).click();

  const owner = dialog.getByLabel("External control for Synthetic coding chat", { exact: true });
  await owner.scrollIntoViewIfNeeded();
  await expect(owner).toBeInViewport();
  await expect(owner).toContainText("Waiting for native approval");
  await expect(owner).toContainText("Observed cursor");

  const geometry = await dialog.evaluate((element) => {
    const box = element.getBoundingClientRect();
    const body = element.querySelector<HTMLElement>(".ui-dialog__body");
    return {
      bodyClipped: body === null ? false : body.scrollHeight > body.clientHeight + 1,
      bodyOverflowY: body === null ? "" : getComputedStyle(body).overflowY,
      bottom: box.bottom,
      top: box.top,
      viewportHeight: window.innerHeight,
    };
  });
  expect(geometry.top, JSON.stringify(geometry)).toBeGreaterThanOrEqual(0);
  expect(geometry.bottom, JSON.stringify(geometry)).toBeLessThanOrEqual(geometry.viewportHeight);
  if (geometry.bodyClipped) expect(geometry.bodyOverflowY).toMatch(/auto|scroll/u);
  await noHorizontalOverflow(page);

  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(settings).toBeFocused();
});
