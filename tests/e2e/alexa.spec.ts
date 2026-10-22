import { test, expect, type Page } from "@playwright/test";
import fs from "node:fs";

// Typed-input journey for the Alexa+ web panel. Proves the browser issues real
// JSON-RPC to /mcp/ and that answers reflect the shared household ledger.

const mcpCall = (page: Page, tool: string) =>
  page.waitForResponse(
    (r) =>
      r.url().endsWith("/mcp/") &&
      r.request().method() === "POST" &&
      (r.request().postData() ?? "").includes(`"name":"${tool}"`),
  );

async function ask(page: Page, text: string, tool: string) {
  const panel = page.getByRole("region", { name: "Alexa+", exact: true });
  await panel.getByLabel("Ask Alexa+").fill(text);
  const [response] = await Promise.all([
    mcpCall(page, tool),
    panel.getByRole("button", { name: "Ask", exact: true }).click(),
  ]);
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body.jsonrpc).toBe("2.0");
  expect(body.result.isError).toBeFalsy();
  return panel;
}

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Owner sign-in" }).click();
  await page
    .getByLabel("Password", { exact: true })
    .fill("e2e-private-password");
  await page.getByRole("button", { name: "Open mission control" }).click();
  await expect(
    page.getByRole("heading", { name: "Mission control." }),
  ).toBeVisible();
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/admin/reset") && r.request().method() === "POST",
    ),
    page.getByRole("button", { name: "Reset day" }).click(),
  ]);
});

test("Alexa+ answers from real MCP tool calls over the shared ledger", async ({
  page,
}) => {
  await page.getByRole("button", { name: "Judge replay" }).click();
  const panel = page.getByRole("region", { name: "Alexa+", exact: true });
  await expect(panel).toBeVisible();

  await page.getByRole("button", { name: "1. 08:15 Morning promises" }).click();
  await expect(
    page.getByText("Attend nephew’s teacher meeting", { exact: true }),
  ).toBeVisible();

  await ask(page, "Alexa, what did I promise today?", "list_active_contracts");
  const ledger = (await (await page.request.get("/api/state")).json()).state;
  const reply = panel.getByTestId("alexa-reply").last();
  await expect(reply).toContainText(
    `You have ${ledger.contracts.length} tracked commitments`,
  );
  for (const c of ledger.contracts) await expect(reply).toContainText(c.title);
  await expect(
    panel
      .getByTestId("alexa-rpc-tool")
      .filter({ hasText: "list_active_contracts" })
      .first(),
  ).toBeVisible();
  await expect(panel.getByText("initialize", { exact: true })).toBeVisible();

  await page
    .getByRole("button", { name: "2. 14:10 Trust, then verify" })
    .click();
  await expect(
    page.getByText("Keep parcel in safe custody", { exact: true }),
  ).toBeVisible();
  await ask(page, "Alexa, is my parcel safe?", "get_watchdog_status");
  await expect(panel.getByTestId("alexa-reply").last()).toContainText(
    "Parcel was observed on your porch. PorchWatchdog is watching; custody is not yet complete.",
  );

  await page
    .getByRole("button", { name: "3. 15:00 A timely intervention" })
    .click();
  await expect(panel.locator(".alexa-whisper")).toContainText(
    "Your teacher meeting begins in 25 minutes, and I haven't confirmed you're preparing. Open meeting details?",
  );

  await ask(page, "Alexa, did I call my sister?", "request_user_verification");
  await expect(panel.getByTestId("alexa-reply").last()).toContainText(
    "Not yet verified",
  );
  await ask(page, "Alexa, start Reality-Lock", "bridge_ring_camera_to_firetv");
  await expect(panel.getByTestId("alexa-reply").last()).toContainText(
    "can't open a live Ring-to-Fire TV camera relay",
  );

  // Ledger untouched by the read-only questions: no contract became VERIFIED by voice.
  const after = (await (await page.request.get("/api/state")).json()).state;
  expect(
    after.contracts.find((c: { key: string }) => c.key === "sister").status,
  ).toBe("ACTIVE");

  await page
    .getByRole("button", { name: "5. 19:45 The doorway check" })
    .click();
  await expect(
    panel.locator(".alexa-whisper[data-kind=ARRIVAL_ITEM_CHECK]"),
  ).toContainText(
    "Your drinks weren't visible as you approached the door. Check whether you have them.",
  );

  fs.mkdirSync("artifacts/screenshots", { recursive: true });
  await panel.screenshot({ path: "artifacts/screenshots/alexa.png" });
});
