import { expect, test, type Locator } from "@playwright/test";

async function assertBoundedViewer(viewer: Locator): Promise<Locator> {
  const body = viewer.locator(".agent-artifacts__viewer-body");
  const metrics = await viewer.evaluate((dialog) => {
    const body = dialog.querySelector<HTMLElement>(".agent-artifacts__viewer-body")!;
    const style = getComputedStyle(body);
    const bounds = dialog.getBoundingClientRect();
    return {
      bodyOverflowY: style.overflowY,
      gutter: style.scrollbarGutter,
      overscrollY: style.overscrollBehaviorY,
      bodyClientHeight: body.clientHeight,
      bodyScrollHeight: body.scrollHeight,
      left: bounds.left,
      right: bounds.right,
      top: bounds.top,
      bottom: bounds.bottom,
      viewportWidth: document.documentElement.clientWidth,
      viewportHeight: document.documentElement.clientHeight,
    };
  });
  expect(metrics.gutter).toBe("stable");
  expect(metrics.overscrollY).toBe("contain");
  expect(metrics.bodyOverflowY).toMatch(/auto|scroll/u);
  expect(metrics.left).toBeGreaterThanOrEqual(0);
  expect(metrics.top).toBeGreaterThanOrEqual(0);
  expect(metrics.right).toBeLessThanOrEqual(metrics.viewportWidth + 1);
  expect(metrics.bottom).toBeLessThanOrEqual(metrics.viewportHeight + 1);
  expect(metrics.bodyClientHeight).toBeGreaterThan(0);
  expect(metrics.bodyScrollHeight).toBeGreaterThanOrEqual(metrics.bodyClientHeight);
  for (const name of ["Close artifact viewer", "Zoom in PDF"]) {
    const control = viewer.getByRole("button", { name, exact: true });
    await expect(control, `${name} should be present`).toHaveCount(1);
    expect((await control.boundingBox())?.height, `${name} should remain touchable`).toBeGreaterThanOrEqual(44);
  }
  return body;
}

test.describe("beta artifact viewer layout", () => {
  test("keeps the desktop viewer body stable and the zoomed PDF in its own scroll port", async ({ page }) => {
    await page.goto("/e2e/fixtures/workflow-panels.html?panel=artifact-viewers");
    const preview = page.getByRole("button", { name: "Preview synthetic-report.pdf", exact: true });
    await preview.click();
    const viewer = page.getByRole("dialog", { name: "synthetic-report.pdf", exact: true });
    await expect(viewer.getByRole("region", { name: "PDF preview of synthetic-report.pdf v1", exact: true }))
      .toHaveAttribute("data-state", "ready");
    await assertBoundedViewer(viewer);

    const stage = viewer.getByRole("group", { name: "Scrollable PDF page area", exact: true });
    await viewer.getByRole("button", { name: "Zoom in PDF", exact: true }).click();
    await expect.poll(() => stage.evaluate((node) => node.scrollWidth > node.clientWidth)).toBe(true);
    await expect(stage).toHaveAttribute("tabindex", "0");
    await stage.focus();
    await stage.press("ArrowRight");
    await expect.poll(() => stage.evaluate((node) => node.scrollLeft)).toBeGreaterThan(0);
  });

  test.describe("narrow and short viewport", () => {
    test.use({ viewport: { width: 390, height: 540 } });

    test("keeps controls usable while the viewer body owns vertical scrolling", async ({ page }) => {
      await page.goto("/e2e/fixtures/workflow-panels.html?panel=artifact-viewers");
      await page.getByRole("button", { name: "Preview synthetic-report.pdf", exact: true }).click();
      const viewer = page.getByRole("dialog", { name: "synthetic-report.pdf", exact: true });
      await expect(viewer.getByRole("region", { name: "PDF preview of synthetic-report.pdf v1", exact: true }))
        .toHaveAttribute("data-state", "ready");
      const body = await assertBoundedViewer(viewer);
      await expect(viewer.getByRole("button", { name: "Close artifact viewer", exact: true })).toBeVisible();

      const before = await body.evaluate((node) => ({
        top: node.scrollTop,
        max: node.scrollHeight - node.clientHeight,
        pageTop: document.scrollingElement?.scrollTop ?? 0,
        bounds: node.getBoundingClientRect().toJSON(),
      }));
      expect(before.max, "short viewer should expose a bounded body scroll port").toBeGreaterThan(0);
      // Wheel in the body's left padding, outside nested content, so this
      // proves the viewer body—not the document—owns the scroll.
      await page.mouse.move(before.bounds.x + 6, before.bounds.y + before.bounds.height / 2);
      await page.mouse.wheel(0, 240);
      await expect.poll(() => body.evaluate((node) => node.scrollTop)).toBeGreaterThan(before.top);
      await expect.poll(() => page.evaluate(() => document.scrollingElement?.scrollTop ?? 0)).toBe(before.pageTop);
      await page.keyboard.press("Escape");
      await expect(viewer).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Preview synthetic-report.pdf", exact: true })).toBeFocused();
    });
  });
});
