import { expect, test } from "@playwright/test";

test("controller fixture blocks direct connection creation behind native presence", async ({ page }) => {
  await page.goto("/e2e/fixtures/workflow-panels.html?panel=agent-controller-ownership");
  await page.getByRole("button", { name: /Agent settings/ }).click();
  await page.getByRole("tab", { name: "Connections", exact: true }).click();

  const controller = page.getByRole("region", { name: "Controller API", exact: true });
  await expect(controller).toBeVisible();
  const create = controller.getByRole("button", { name: "Create direct connection", exact: true });
  await expect(create).toBeDisabled();
  await expect(create).toHaveAttribute("aria-describedby", "agent-mcp-create-disabled");
  await expect(page.locator("#agent-mcp-create-disabled")).toHaveText(
    "Owner presence is unproven, so this app cannot create a connection. Focus the owned native app window and try again.",
  );
  await expect(create).toHaveAccessibleDescription(/Owner presence is unproven, so this app cannot create a connection/);

  // The fixture exposes only active connections, so replacement is not an
  // available action; no native takeover or implicit replacement authority is
  // presented for either active credential.
  await expect(controller.getByRole("button", { name: "Prepare replacement", exact: true })).toHaveCount(0);
});
