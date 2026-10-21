/** Automated UI inspection: every view × viewport × role.
 * Flags banned mode words in visible text, nested scrollbars, horizontal overflow,
 * desktop page scroll, broken images and console errors. Writes artifacts/ui-inspect/report.json.
 * Usage: DONE_URL=http://127.0.0.1:8099 node scripts/ui-inspect.mjs
 */
import { chromium } from "@playwright/test";
import { mkdir, readFile, writeFile } from "node:fs/promises";

const base = process.env.DONE_URL || "http://127.0.0.1:8099";
const creds = JSON.parse(await readFile((process.env.DATA_DIR || ".local") + "/access.json", "utf8"));
const out = "artifacts/ui-inspect";
await mkdir(out, { recursive: true });
const pages = ["overview", "replay", "contracts", "studio", "alexa", "incidents", "evidence", "settings", "today"];
const sizes = [
  [1440, 900],
  [1100, 800],
  [900, 700],
  [390, 844],
];
const banned = /\b(simulat\w*|synthetic|virtual|recorded demo|not live ring)\b/i;
const browser = await chromium.launch({ headless: true });
const findings = [];

async function login(page, user) {
  await page.goto(base);
  const r = await page.request.post(base + "/api/auth/login", {
    data: { username: user, password: creds[user] },
    headers: { "Idempotency-Key": crypto.randomUUID() },
  });
  if (!r.ok()) throw new Error("login failed " + user);
  await page.reload();
}

for (const user of ["demo-admin", "owner"]) {
  for (const [w, h] of sizes) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h } });
    const page = await ctx.newPage();
    const errors = [];
    page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
    page.on("pageerror", (e) => errors.push(String(e)));
    await login(page, user);
    if (user === "demo-admin" && w === 1440) {
      const k = () => ({ "Idempotency-Key": crypto.randomUUID() });
      await page.request.post(base + "/api/admin/reset", { data: {}, headers: k() });
      for (const [i, b] of [[1, "deposit"], [2, "deposit"], [3, "disengaged"], [4, "unknown"], [5, "empty"], [6, "deposit"]])
        await page.request.post(base + `/api/admin/scenarios/${i}/run`, { data: { branch: b }, headers: k() });
    }
    for (const id of pages) {
      await page.goto(`${base}/?page=${id}`);
      await page.waitForTimeout(900);
      const r = await page.evaluate((bannedSrc) => {
        const re = new RegExp(bannedSrc, "i");
        const visible = (el) => {
          const s = getComputedStyle(el);
          const b = el.getBoundingClientRect();
          return s.visibility !== "hidden" && s.display !== "none" && b.width > 0 && b.height > 0;
        };
        const words = [];
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        while (walker.nextNode()) {
          const n = walker.currentNode;
          const el = n.parentElement;
          if (!el || !visible(el) || el.closest("pre, code, .event-scroll, .alexa-rpc, [data-raw]")) continue;
          const m = n.textContent.match(re);
          if (m) words.push(n.textContent.trim().slice(0, 90));
        }
        for (const el of document.querySelectorAll("[title],[alt],[aria-label]"))
          for (const a of ["title", "alt", "aria-label"]) {
            const v = el.getAttribute(a);
            if (v && re.test(v) && !el.closest("pre, code, .event-scroll, .alexa-rpc")) words.push(`${a}="${v.slice(0, 80)}"`);
          }
        const scrollers = [...document.querySelectorAll("*")].filter((el) => {
          const s = getComputedStyle(el);
          return /(auto|scroll)/.test(s.overflowY) && el.scrollHeight > el.clientHeight + 2 && visible(el);
        });
        const nested = scrollers.filter((el) => scrollers.some((o) => o !== el && o.contains(el)))
          .filter((el) => !el.closest(".event-scroll, .alexa-rpc, pre"))
          .map((el) => el.className.toString().slice(0, 40) || el.tagName);
        const doc = document.scrollingElement;
        const content = document.querySelector(".content");
        const imgs = [...document.images].filter((i) => visible(i) && i.complete && i.naturalWidth === 0).map((i) => i.alt || i.src.slice(-40));
        return {
          words: [...new Set(words)].slice(0, 12),
          nested: [...new Set(nested)],
          hOverflow: doc.scrollWidth > innerWidth + 1,
          pageScroll: doc.scrollHeight > innerHeight + 1 || (content && content.scrollHeight > content.clientHeight + 2),
          brokenImages: imgs,
        };
      }, banned.source);
      const issues = [];
      if (r.words.length) issues.push({ kind: "banned-words", detail: r.words });
      if (r.nested.length) issues.push({ kind: "nested-scroll", detail: r.nested });
      if (r.hOverflow) issues.push({ kind: "horizontal-overflow" });
      if (w >= 1280 && r.pageScroll && !["settings"].includes(id)) issues.push({ kind: "desktop-page-scroll" });
      if (r.brokenImages.length) issues.push({ kind: "broken-images", detail: r.brokenImages });
      if (issues.length) findings.push({ user, size: `${w}x${h}`, page: id, issues });
      await page.screenshot({ path: `${out}/${user}-${w}-${id}.png` });
    }
    const errs = [...new Set(errors)].filter((e) => !/401|Failed to load resource/.test(e));
    if (errs.length) findings.push({ user, size: `${w}x${h}`, page: "*", issues: [{ kind: "console-errors", detail: errs.slice(0, 5) }] });
    await ctx.close();
  }
}
await browser.close();
await writeFile(`${out}/report.json`, JSON.stringify(findings, null, 2));
console.log(findings.length ? JSON.stringify(findings, null, 1) : "NO FINDINGS");
