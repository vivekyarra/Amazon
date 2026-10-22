import { test, expect } from "@playwright/test";

test("one click opens a private guided day without a password", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Try Muni live" }).click();
  await expect(
    page.getByRole("heading", { name: "Mission control." }),
  ).toBeVisible();
  const state = await page.request.get("/api/state");
  expect((await state.json()).state.household_id).toMatch(/^guest_/);
});
