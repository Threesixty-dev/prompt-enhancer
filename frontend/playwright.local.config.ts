import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "local-real.spec.ts",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:4175",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium-local-real",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "npm run dev:local -- --port 4175",
    url: "http://127.0.0.1:4175",
    reuseExistingServer: false,
  },
});
