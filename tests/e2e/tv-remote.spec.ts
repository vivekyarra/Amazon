import { test, expect, type Page } from "@playwright/test";

// F24_FIRETV_REMOTE_NAV (spec section 13): a D-pad sequence through the four TV views reaches
// every intended action with visible focus. This drives the same web HUD that the Fire OS APK
// loads (`/?tv=1&page=<view>`) using arrow keys only; native view switching, Back handling and
// the APK runtime are covered by scripts/firetv-emulator-check.py in the CI emulator job.
const VIEWS = [
  ["overview", "Mission control."],
  ["incidents", "A package moved. Was it authorized?"],
  ["evidence", "Private evidence"],
  ["studio", "Reality-Lock studio."],
] as const;

const FOCUSABLE = "button:not(:disabled),a,input,select,summary";

async function controls(page: Page): Promise<string[]> {
  return page.evaluate((selector) => {
    const items = [...document.querySelectorAll<HTMLElement>(selector)].filter(
      (el) => el.offsetParent !== null,
    );
    return items.map((el, i) => `${el.tagName}#${i}`);
  }, FOCUSABLE);
}

test("F24: every control in the four TV views is reachable by D-pad with visible focus", async ({
  page,
}) => {
  test.setTimeout(180000);
  await page.goto("/");
  await page
    .getByLabel("Password", { exact: true })
    .fill("e2e-private-password");
  await page.getByRole("button", { name: "Open mission control" }).click();
  await expect(
    page.getByRole("heading", { name: "Mission control." }),
  ).toBeVisible();
  let n = 0;
  for (const [path, data] of [
    ["/api/admin/reset", {}],
    ["/api/admin/scenarios/1/run", { branch: "deposit" }],
    ["/api/admin/scenarios/2/run", { branch: "deposit" }],
    ["/api/admin/scenarios/4/run", { branch: "unknown" }],
    ["/api/studio/sessions", {}],
  ] as const) {
    const r = await page.request.post(path, {
      data,
      headers: { "Idempotency-Key": `f24-${Date.now()}-${n++}` },
    });
    expect(r.ok(), path).toBeTruthy();
  }

  for (const [view, heading] of VIEWS) {
    await page.goto(`/?tv=1&page=${view}`);
    await expect(
      page.getByRole("heading", { name: heading }).first(),
    ).toBeVisible();
    const expected = await controls(page);
    expect(expected.length, `${view} has controls`).toBeGreaterThan(0);
    const reached = new Set<string>();
    for (
      let i = 0;
      i < expected.length * 3 + 40 && reached.size < expected.length;
      i++
    ) {
      await page.keyboard.press("ArrowDown");
      const focus = await page.evaluate((selector) => {
        const el = document.activeElement as HTMLElement | null;
        const items = [
          ...document.querySelectorAll<HTMLElement>(selector),
        ].filter((x) => x.offsetParent !== null);
        const index = el ? items.indexOf(el) : -1;
        if (!el || index < 0) return null;
        const style = getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return {
          key: `${el.tagName}#${index}`,
          visible:
            (style.outlineStyle !== "none" &&
              parseFloat(style.outlineWidth) > 0) ||
            style.boxShadow !== "none",
          inViewport: rect.bottom > 0 && rect.top < window.innerHeight,
        };
      }, FOCUSABLE);
      if (!focus) continue;
      expect(focus.visible, `visible focus on ${focus.key} (${view})`).toBe(
        true,
      );
      expect(focus.inViewport, `${focus.key} scrolled into view`).toBe(true);
      reached.add(focus.key);
    }
    const missing = expected.filter((key) => !reached.has(key));
    expect(missing, `unreachable controls in ${view}`).toEqual([]);
  }
});
