import { expect, test } from "@playwright/test";

async function counter(page: import("@playwright/test").Page, name: string): Promise<number> {
  const attribute = name.replace(/[A-Z]/gu, (letter) => `-${letter.toLowerCase()}`);
  const value = await page.locator("html").getAttribute(`data-models-recovery-${attribute}`);
  expect(value).not.toBeNull();
  const parsed = Number(value);
  expect(Number.isFinite(parsed)).toBe(true);
  return parsed;
}

async function openRecovery(page: import("@playwright/test").Page, testCase: string, width?: number) {
  if (width !== undefined) await page.setViewportSize({ width, height: 720 });
  await page.goto(`/e2e/fixtures/workflow-panels.html?panel=models-recovery&case=${testCase}`);
  await expect(page.getByRole("heading", { name: "Models", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Chat", exact: true })).toBeVisible();
}

async function refreshRuntime(page: import("@playwright/test").Page) {
  await page.getByRole("button", { name: "Inject runtime read failure", exact: true }).click();
  await page.getByRole("button", { name: "Refresh runtime status", exact: true }).click();
  await expect(page.getByText("Shared runtime status is unavailable", { exact: false })).toBeVisible();
}

async function recoverRuntime(page: import("@playwright/test").Page) {
  await page.getByRole("button", { name: "Allow runtime read recovery", exact: true }).click();
  await page.getByRole("button", { name: "Refresh runtime status", exact: true }).click();
}

test("keeps the valid catalogue and acquisition surface when the initial runtime read fails", async ({ page }) => {
  await openRecovery(page, "initial");
  await expect(page.getByRole("heading", { name: "Add a model", exact: true })).toBeVisible();
  await expect(page.getByText("Shared runtime status is unavailable", { exact: false })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Message", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Send", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Start shared runtime", exact: true })).toBeDisabled();
  const composer = page.getByRole("textbox", { name: "Message", exact: true });
  await composer.fill("Synthetic draft before runtime recovery.");
  expect(await counter(page, "runtimeReads")).toBeGreaterThan(0);
  expect(await counter(page, "streamAttempts")).toBe(0);
  expect(await counter(page, "starts")).toBe(0);

  await page.getByRole("button", { name: "Allow runtime read recovery", exact: true }).click();
  await recoverRuntime(page);
  await expect(page.getByText("Runtime status is unverified", { exact: false })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Send", exact: true })).toBeEnabled();
  await expect(composer).toHaveValue("Synthetic draft before runtime recovery.");
  expect(await counter(page, "streamAttempts")).toBe(0);
});

test("preserves a completed turn, next draft and model choice through a runtime-read outage", async ({ page }) => {
  await openRecovery(page, "completed");
  const chat = page.getByRole("region", { name: "Chat", exact: true });
  const composer = chat.getByRole("textbox", { name: "Message", exact: true });
  const model = chat.getByRole("combobox", { name: "Chat model", exact: true });
  await composer.fill("Synthetic completed request.");
  await chat.getByRole("button", { name: "Send", exact: true }).click();
  await expect(chat.getByText("Synthetic reply: the example is ready to review.", { exact: true })).toBeVisible();
  await composer.fill("Synthetic next draft kept during outage.");
  await chat.getByRole("checkbox").check();
  const aliasBefore = await model.inputValue();
  expect(aliasBefore).toBe("example-small-cpu");
  await refreshRuntime(page);
  await expect(composer).toHaveValue("Synthetic next draft kept during outage.");
  await expect(model).toHaveValue(aliasBefore);
  await expect(chat.getByText("Synthetic reply: the example is ready to review.", { exact: true })).toBeVisible();
  await expect(chat.getByRole("button", { name: "Send", exact: true })).toBeDisabled();
  await expect(chat.getByRole("checkbox")).toBeChecked();
  expect(await counter(page, "streamAttempts")).toBe(1);
  expect(await counter(page, "starts")).toBe(0);
  await recoverRuntime(page);
  await expect(chat.getByRole("button", { name: "Send", exact: true })).toBeEnabled();
  await expect(composer).toHaveValue("Synthetic next draft kept during outage.");
  await expect(chat.getByRole("checkbox")).toBeChecked();
  expect(await counter(page, "streamAttempts")).toBe(1);
});

test("keeps an in-flight reply and next draft through a runtime outage and explicit Stop", async ({ page }) => {
  await openRecovery(page, "stream");
  const chat = page.getByRole("region", { name: "Chat", exact: true });
  const composer = chat.getByRole("textbox", { name: "Message", exact: true });
  await composer.fill("Synthetic streaming request.");
  await chat.getByRole("button", { name: "Send", exact: true }).click();
  await expect(chat.getByText("Synthetic partial reply before the runtime outage.", { exact: true })).toBeVisible();
  await composer.fill("Synthetic next draft while streaming.");
  await refreshRuntime(page);
  await expect(composer).toHaveValue("Synthetic next draft while streaming.");
  expect(await counter(page, "streamAborts")).toBe(0);
  expect(await counter(page, "streamAttempts")).toBe(1);
  await chat.getByRole("button", { name: "Stop", exact: true }).click();
  await expect.poll(() => counter(page, "streamAborts")).toBe(1);
  await page.getByRole("button", { name: "Release late stream", exact: true }).click();
  await expect(chat.getByText("Synthetic partial reply before the runtime outage.", { exact: true })).toBeVisible();
  await expect(chat.getByText("Synthetic late reply that must be ignored.", { exact: true })).toHaveCount(0);
  await expect(composer).toHaveValue("Synthetic next draft while streaming.");
  expect(await counter(page, "streamAttempts")).toBe(1);
});

test("keeps runtime-read error guidance and controls within a 320px viewport", async ({ page }) => {
  await openRecovery(page, "initial", 320);
  const controls = [
    page.getByRole("alert").filter({ hasText: "Shared runtime status is unavailable" }),
    page.getByRole("button", { name: "Refresh runtime status", exact: true }),
    page.getByRole("textbox", { name: "Message", exact: true }),
    page.getByRole("button", { name: "Send", exact: true }),
  ];
  for (const control of controls) {
    await control.scrollIntoViewIfNeeded();
    const box = await control.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(320);
  }
  await expect(page.getByRole("button", { name: "Send", exact: true })).toBeDisabled();
  expect(await counter(page, "starts")).toBe(0);
  expect(await counter(page, "streamAttempts")).toBe(0);
});
