import { expect, test, type Locator, type Page } from "@playwright/test";

const FIXTURE = "/e2e/fixtures/agent-exit-refresh.html";

function counter(page: Page, name: string) {
  return page.locator("html").getAttribute(`data-agent-refresh-${name}`);
}

async function openAgent(page: Page, options = "") {
  await page.goto(`${FIXTURE}${options}`);
  await expect(page.locator("[data-route='agent'], [data-layout='agent-window']").first()).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Message to the agent", exact: true })).toBeVisible();
  await expect(page.getByRole("status", { name: "Interface refresh available" })).toBeVisible();
}

async function expectNoAgentEffects(page: Page) {
  for (const name of ["create", "send", "stop", "delete", "modelstart"]) {
    await expect.poll(() => counter(page, name)).toBe("0");
  }
}

function agentWarning(page: Page) {
  return page.getByRole("dialog", { name: "Keep Agent changes?", exact: true });
}

test.describe("Agent exit refresh guard", () => {
  test("keeps a no-model draft through sidebar navigation, Escape, then confirms one discard", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openAgent(page);
    const composer = page.getByRole("textbox", { name: "Message to the agent", exact: true });
    await composer.fill("synthetic Agent draft");
    const refresh = page.getByRole("button", { name: "Refresh interface", exact: true });
    await expect(refresh).toBeDisabled();
    await expectNoAgentEffects(page);

    await page.getByRole("button", { name: "Open navigation", exact: true }).click();
    await page.getByRole("dialog", { name: "Navigate Prompt Enhancer", exact: true })
      .getByRole("button", { name: "Overview", exact: true }).click();
    await agentWarning(page).getByRole("button", { name: "Keep Agent changes", exact: true }).click();
    await expect(composer).toHaveValue("synthetic Agent draft");
    await expect(page.getByRole("button", { name: "Open navigation", exact: true })).toBeFocused();

    await page.getByRole("button", { name: "Open navigation", exact: true }).click();
    await page.getByRole("dialog", { name: "Navigate Prompt Enhancer", exact: true })
      .getByRole("button", { name: "Overview", exact: true }).click();
    await agentWarning(page).press("Escape");
    await expect(composer).toHaveValue("synthetic Agent draft");

    await page.getByRole("button", { name: "Open navigation", exact: true }).click();
    await page.getByRole("dialog", { name: "Navigate Prompt Enhancer", exact: true })
      .getByRole("button", { name: "Overview", exact: true }).click();
    await agentWarning(page).getByRole("button", { name: "Discard Agent changes and continue", exact: true }).click();
    await expect(page).toHaveURL(/\/overview$/u);
    await expectNoAgentEffects(page);
  });

  test("guards managed Back and Forward, then recovers an unindexed foreign entry", async ({ page }) => {
    await openAgent(page);
    const composer = page.getByRole("textbox", { name: "Message to the agent", exact: true });
    await page.getByRole("button", { name: "Overview", exact: true }).click();
    await expect(page).toHaveURL(/\/overview$/u);
    await page.getByRole("button", { name: "Agent", exact: true }).click();
    await composer.fill("synthetic history draft");

    await page.goBack();
    await agentWarning(page).getByRole("button", { name: "Keep Agent changes", exact: true }).click();
    await expect(page).toHaveURL(/\/agent$/u);
    await expect(composer).toHaveValue("synthetic history draft");
    await page.goBack();
    await agentWarning(page).getByRole("button", { name: "Discard Agent changes and continue", exact: true }).click();
    await expect(page).toHaveURL(/\/overview$/u);

    await openAgent(page);
    await page.getByRole("button", { name: "Overview", exact: true }).click();
    await expect(page).toHaveURL(/\/overview$/u);
    await page.goBack();
    await expect(page).toHaveURL(/\/agent$/u);
    await composer.fill("synthetic forward draft");
    await page.goForward();
    await agentWarning(page).getByRole("button", { name: "Keep Agent changes", exact: true }).click();
    await expect(composer).toHaveValue("synthetic forward draft");
    await page.goForward();
    await agentWarning(page).getByRole("button", { name: "Discard Agent changes and continue", exact: true }).click();
    await expect(page).toHaveURL(/\/overview$/u);

    await openAgent(page);
    await composer.fill("synthetic foreign draft");
    await page.evaluate(() => {
      history.pushState({ fixtureForeign: "agent-route" }, "", "/overview");
      dispatchEvent(new PopStateEvent("popstate", { state: history.state }));
    });
    await expect(agentWarning(page)).toContainText(/cannot be restored automatically/i);
    await agentWarning(page).getByRole("button", { name: "Return to Agent", exact: true }).click();
    await expect(page).toHaveURL(/\/agent$/u);
    await expect(composer).toHaveValue("synthetic foreign draft");
    await expectNoAgentEffects(page);
  });

  test("enables a verified interface refresh only after the draft clears, without automatic reload", async ({ page }) => {
    await openAgent(page);
    const composer = page.getByRole("textbox", { name: "Message to the agent", exact: true });
    const refresh = page.getByRole("button", { name: "Refresh interface", exact: true });
    await composer.fill("synthetic refresh draft");
    await expect(refresh).toBeDisabled();
    await composer.fill("");
    await expect(refresh).toBeEnabled();
    await expect.poll(() => counter(page, "reload")).toBe("0");
    await refresh.click();
    await expect.poll(() => counter(page, "reload")).toBe("1");
    await expect(composer).toHaveValue("");
    await expect(page.getByRole("button", { name: "Refresh interface", exact: true })).toHaveCount(0);
    await expectNoAgentEffects(page);
  });

  test("blocks refresh while the current observed Agent session is active", async ({ page }) => {
    await openAgent(page, "?active=1");
    const refresh = page.getByRole("button", { name: "Refresh interface", exact: true });
    await expect(refresh).toBeDisabled();
    await expect(page.getByText(/temporary work may be lost/i)).toBeVisible();
    await expect.poll(() => counter(page, "reload")).toBe("0");
    await expectNoAgentEffects(page);
  });

  for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 844 }]) {
    test(`keeps refresh notice and Agent composer reachable at ${viewport.width}px`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await openAgent(page);
      const notice = page.getByRole("status", { name: "Interface refresh available" });
      const refresh = page.getByRole("button", { name: "Refresh interface", exact: true });
      const composer = page.getByRole("textbox", { name: "Message to the agent", exact: true });
      const send = page.getByRole("button", { name: "Send", exact: true });
      for (const control of [notice, composer, send] satisfies Locator[]) {
        await control.scrollIntoViewIfNeeded();
        const box = await control.boundingBox();
        expect(box).not.toBeNull();
        expect(box!.x).toBeGreaterThanOrEqual(0);
        expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width);
        expect(box!.y).toBeGreaterThanOrEqual(0);
        // Browser layout may end on a fractional device-pixel boundary; one CSS
        // pixel keeps that rounding separate from a genuinely clipped control.
        expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height + 1);
        expect(await control.evaluate((element) => {
          const box = element.getBoundingClientRect();
          const top = document.elementFromPoint(box.left + (box.width / 2), box.top + (box.height / 2));
          return top !== null && (top === element || element.contains(top) || top.contains(element));
        })).toBe(true);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      expect((await refresh.boundingBox())!.height).toBeGreaterThanOrEqual(44);
      await composer.click();
      await expect(composer).toBeFocused();
    });
  }

  test("keeps the dedicated Agent window visibly guarded", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await openAgent(page, "?dedicated=1");
    const composer = page.getByRole("textbox", { name: "Message to the agent", exact: true });
    const send = page.getByRole("button", { name: "Send", exact: true });
    const geometry = await page.evaluate(() => ({
      body: document.body.scrollHeight,
      document: document.documentElement.scrollHeight,
      viewport: window.innerHeight,
    }));
    expect(geometry.body, JSON.stringify(geometry)).toBeLessThanOrEqual(geometry.viewport + 1);
    expect(geometry.document, JSON.stringify(geometry)).toBeLessThanOrEqual(geometry.viewport + 1);
    for (const control of [composer, send] satisfies Locator[]) {
      const box = await control.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.y).toBeGreaterThanOrEqual(0);
      expect(box!.y + box!.height).toBeLessThanOrEqual(901);
      expect(await control.evaluate((element) => {
        const box = element.getBoundingClientRect();
        const top = document.elementFromPoint(box.left + (box.width / 2), box.top + (box.height / 2));
        return top !== null && (top === element || element.contains(top) || top.contains(element));
      })).toBe(true);
    }
    await composer.fill("synthetic dedicated draft");
    await expect(page.getByRole("button", { name: "Refresh interface", exact: true })).toBeDisabled();
  });

  test("keeps the dedicated mobile composer reachable with the refresh notice", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openAgent(page, "?dedicated=1");
    const composer = page.getByRole("textbox", { name: "Message to the agent", exact: true });
    const send = page.getByRole("button", { name: "Send", exact: true });
    for (const control of [composer, send] satisfies Locator[]) {
      await control.scrollIntoViewIfNeeded();
      const box = await control.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.y).toBeGreaterThanOrEqual(0);
      expect(box!.y + box!.height).toBeLessThanOrEqual(845);
      expect(await control.evaluate((element) => {
        const box = element.getBoundingClientRect();
        const top = document.elementFromPoint(box.left + (box.width / 2), box.top + (box.height / 2));
        return top !== null && (top === element || element.contains(top) || top.contains(element));
      })).toBe(true);
    }
  });

  test("keeps dedicated Agent controls uncovered while a foreign history warning offers Return to Agent", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await openAgent(page, "?dedicated=1");
    const composer = page.getByRole("textbox", { name: "Message to the agent", exact: true });
    await composer.fill("synthetic dedicated foreign draft");
    await page.evaluate(() => {
      history.pushState({ fixtureForeign: "dedicated-agent-route" }, "", "/overview");
      dispatchEvent(new PopStateEvent("popstate", { state: history.state }));
    });
    await agentWarning(page).getByRole("button", { name: "Keep Agent changes", exact: true }).click();
    const returnToAgent = page.getByRole("button", { name: "Return to Agent", exact: true });
    await expect(returnToAgent).toBeVisible();
    const send = page.getByRole("button", { name: "Send", exact: true });
    for (const control of [composer, send] satisfies Locator[]) {
      const box = await control.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.y).toBeGreaterThanOrEqual(0);
      expect(box!.y + box!.height).toBeLessThanOrEqual(901);
      expect(await control.evaluate((element) => {
        const box = element.getBoundingClientRect();
        const top = document.elementFromPoint(box.left + (box.width / 2), box.top + (box.height / 2));
        return top !== null && (top === element || element.contains(top) || top.contains(element));
      })).toBe(true);
    }
  });
});
