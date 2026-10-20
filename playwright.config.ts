import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "tests/e2e",
  timeout: 60000,
  expect: { timeout: 10000 },
  fullyParallel: false,
  workers: 1,
  outputDir: "artifacts/playwright",
  reporter: [
    ["list"],
    ["junit", { outputFile: "artifacts/playwright/results.xml" }],
  ],
  use: {
    baseURL: "http://127.0.0.1:8091",
    browserName: "chromium",
    headless: true,
    viewport: { width: 1440, height: 1080 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    launchOptions: process.env.CI
      ? {}
      : { executablePath: "/usr/bin/chromium", args: ["--no-sandbox"] },
  },
  webServer: {
    command:
      "DATA_DIR=.local/e2e DEMO_ADMIN_PASSWORD=e2e-private-password OWNER_PASSWORD=e2e-owner-password PORT=8091 ./scripts/start-local.sh",
    url: "http://127.0.0.1:8091/health/ready",
    reuseExistingServer: false,
    timeout: 30000,
  },
});
