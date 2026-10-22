import { defineConfig } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
const port = process.env.E2E_PORT ?? "8091";
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
    baseURL: `http://127.0.0.1:${port}`,
    browserName: "chromium",
    headless: true,
    viewport: { width: 1440, height: 1080 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    launchOptions:
      process.env.CI || !fs.existsSync("/usr/bin/chromium")
        ? {}
        : { executablePath: "/usr/bin/chromium", args: ["--no-sandbox"] },
  },
  webServer: {
    // Shell-agnostic (works from cmd.exe on Windows as well as POSIX shells).
    command: `uv run --frozen uvicorn done_irl.api:app --host 127.0.0.1 --port ${port}`,
    env: {
      DATA_DIR: ".local/e2e",
      JUDGE_PASSWORD: "e2e-private-password",
      OWNER_PASSWORD: "e2e-owner-password",
      DONE_IRL_WARM_SCENES: "0",
      PYTHONPATH: path.resolve("apps/mcp-orchestrator"),
    },
    url: `http://127.0.0.1:${port}/health/ready`,
    reuseExistingServer: false,
    timeout: 30000,
  },
});
