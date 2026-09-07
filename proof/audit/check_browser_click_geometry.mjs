// Isolated real-Chrome transport proof. No model or third-party website.
// The shipped page mapper chooses coordinates; CDP clicks those coordinates.
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, mkdirSync, readdirSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { resolve, join } from "node:path";
import { pathToFileURL } from "node:url";
const root = resolve(import.meta.dirname, "../..");
const candidates = [process.env.ANTICIPY_PLAYWRIGHT_MODULE,
  join(root, "node_modules/playwright/index.mjs"),
  ...readdirSync(join(homedir(), ".npm/_npx")).map(name =>
    join(homedir(), ".npm/_npx", name, "node_modules/playwright/index.mjs"))].filter(Boolean);
const runtime = candidates.find(existsSync);
if (!runtime) throw new Error("Playwright runtime is required for this real DOM proof");
const { chromium } = await import(pathToFileURL(runtime));
const browser = await chromium.launch({ channel: "chrome", headless: true });
const output = join(root, "output/playwright/browser-click-geometry");
mkdirSync(output, { recursive: true });
const results = [];
try {
  const context = await browser.newContext({ viewport: { width: 1000, height: 700 } });
  // Reject every network request. These pages have only synthetic HTML.
  await context.route("**/*", route => route.abort());
  for (const nested of [false, true]) {
    const page = await context.newPage();
    await page.setContent(`<style>
      html, .pane { scroll-behavior:smooth }
      body {margin:0;padding:20px}
      .pane { ${nested ? "height:500px;overflow:auto" : ""} }
      button {display:block;margin-top:2400px;width:200px;height:64px}
      .tail {height:1200px}
      </style><div class="pane"><button id="target">Record fixture click</button>
      <div class="tail"></div></div>
      <script>window.clicked=0;document.querySelector('#target').onclick=()=>window.clicked++</script>`);
    await page.evaluate(readFileSync(process.argv[2] || join(root, "extension/page_map.js"), "utf8"));
    const center = await page.evaluate(() => {
      window.__anticipyMapPage();
      const entry = Object.entries(window.__anticipyMap).find(([,node]) => node.id === "target");
      if (!entry) throw new Error("Fixture button missing from actual page map");
      return window.__anticipyCenter(Number(entry[0]));
    });
    const cdp = await context.newCDPSession(page);
    for (const type of ["mousePressed", "mouseReleased"]) {
      await cdp.send("Input.dispatchMouseEvent", { type, ...center, button: "left", clickCount: 1 });
    }
    const clicks = await page.evaluate(() => window.clicked);
    const detached = await page.evaluate(() => {
      const entry = Object.entries(window.__anticipyMap).find(([,node]) => node.id === "target");
      entry[1].remove();
      return window.__anticipyCenter(Number(entry[0]));
    });
    results.push({ scenario: nested ? "nested smooth scroll" : "document smooth scroll", center, clicks,
      detached, passed: clicks === 1 && detached === null });
    await page.screenshot({ path: join(output, `${nested ? "nested" : "document"}.png`) });
    await page.close();
  }
} finally { await browser.close(); }
writeFileSync(join(output, "results.json"), JSON.stringify(results, null, 2));
console.log(JSON.stringify(results, null, 2));
assert.ok(results.every(row => row.passed), "mapped coordinates must land one click and refuse stale nodes");
