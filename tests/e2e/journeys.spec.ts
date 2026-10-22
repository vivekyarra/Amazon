import { test, expect } from "@playwright/test";
import fs from "node:fs";

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

test("canonical full day updates shared ledger, keeps uncertainty and verifies 15 cycles", async ({
  page,
}) => {
  // The squat replay is paced by the app (~150 frame steps); under machine load it can need
  // well over a minute, so wait on the app's own completion state rather than a tight clock.
  test.setTimeout(180000);
  fs.mkdirSync("artifacts/screenshots", { recursive: true });
  await page.screenshot({
    path: "artifacts/screenshots/01-mission-control.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Run the full day", exact: true })
    .click();
  // Six scenes replay before the studio opens; a cold data dir renders clips on first run.
  await expect(
    page.getByRole("heading", { name: "Reality-Lock studio." }),
  ).toBeVisible({ timeout: 20000 });
  await expect(page.getByText("Promise kept. Evidence saved.")).toBeVisible({
    timeout: 120000,
  });
  await page.screenshot({
    path: "artifacts/screenshots/02-studio-verified.png",
    fullPage: true,
  });
  const state = (await (await page.request.get("/api/state")).json()).state;
  expect(state.contracts.find((c: any) => c.key === "squats").status).toBe(
    "VERIFIED",
  );
  expect(state.contracts.find((c: any) => c.key === "drinks").status).toBe(
    "ACTIVE",
  );
  expect(state.contracts.find((c: any) => c.key === "sister").status).toBe(
    "MISSED",
  );
  expect(state.incidents[0].status).toBe("AWAITING_HUMAN_DECISION");
  expect(state.studio.count).toBe(15);
  await page.getByRole("button", { name: "Evidence & incidents" }).click();
  await expect(
    page.getByRole("heading", { name: "A package moved. Was it authorized?" }),
  ).toBeVisible();
  await expect(
    page.getByText("15s clip available.", { exact: false }),
  ).toBeVisible();
  await page.screenshot({
    path: "artifacts/screenshots/03-incident-review.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Review evidence / Prepare report" })
    .click();
  await page.getByRole("button", { name: "Review report" }).click();
  await page.getByLabel("Type APPROVE REPORT").fill("APPROVE REPORT");
  await page.getByRole("button", { name: "Approve this packet" }).click();
  await page
    .getByRole("button", { name: "Send to local receiver only" })
    .click();
  await expect(
    page.getByText("Local receiver — not sent to police"),
  ).toBeVisible();
});

test("manual scenario branches, contract provenance, and private notifications", async ({
  page,
}) => {
  await page.getByRole("button", { name: "Judge replay" }).click();
  await page.getByRole("button", { name: "1. 08:15 Morning promises" }).click();
  await expect(
    page.getByText("Attend nephew’s teacher meeting", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Courier", { exact: true }).selectOption("false_claim");
  await page
    .getByRole("button", { name: "2. 14:10 Trust, then verify" })
    .click();
  await expect(
    page.getByText("Keep parcel in safe custody", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Open notifications" }).click();
  await expect(
    page.getByText(
      "Courier said the package was left, but I could not confirm a deposit. Review the camera evidence.",
      { exact: true },
    ),
  ).toBeVisible();
  await page.getByRole("button", { name: "Close notifications" }).click();
  await page
    .getByRole("button", { name: "Commitment ledger", exact: true })
    .click();
  await page
    .getByRole("button", { name: /Keep parcel in safe custody/ })
    .click();
  await expect(page.getByText("Custody: unconfirmed")).toBeVisible();
});

test("mobile layout, consent pause, and TV keyboard navigation", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "artifacts/screenshots/04-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Connections & privacy" }).click();
  await page.getByRole("button", { name: "Pause all collection" }).click();
  await expect(
    page.getByText("Collection paused.", { exact: false }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Restore guided consent", exact: true })
    .first()
    .click();
  await page.goto("/?tv=1&page=overview");
  await expect(
    page.getByRole("heading", { name: "Mission control." }),
  ).toBeVisible();
  await page.keyboard.press("ArrowDown");
  expect(await page.evaluate(() => document.activeElement?.tagName)).toBe(
    "BUTTON",
  );
  await page
    .getByRole("button", { name: "Reality-Lock studio", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Reality-Lock studio." }),
  ).toBeVisible();
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.screenshot({
    path: "artifacts/screenshots/05-tv-web-preview.png",
    fullPage: true,
  });
});

test("another authenticated TV tab sees the same contract state", async ({
  page,
  context,
}) => {
  const tv = await context.newPage();
  await tv.goto("/?tv=1&page=contracts");
  await expect(
    tv.getByRole("heading", { name: "Commitment ledger." }),
  ).toBeVisible();
  await page.getByRole("button", { name: "1. 08:15 Morning promises" }).click();
  await expect(
    tv.getByRole("button", { name: /Call your sister/ }),
  ).toBeVisible();
  await expect(
    tv.getByRole("button", { name: /15 squats before TV/ }),
  ).toBeVisible();
  await tv
    .getByRole("button", { name: "Evidence & incidents", exact: true })
    .click();
  await expect(
    tv.getByRole("heading", { name: "No incidents to review." }),
  ).toBeVisible();
  await tv
    .getByRole("button", { name: "Reality-Lock studio", exact: true })
    .click();
  await expect(
    tv.getByRole("heading", { name: "Reality-Lock studio." }),
  ).toBeVisible();
  await tv.close();
});
