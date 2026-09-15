// Real Chrome rendering/interaction proof over the shipping popup files.
// Synthetic fixtures only: no installed MV3 worker, personal profile, provider,
// paid model, live account or external backend. Launch this inside an OS
// outbound-denied sandbox as a second boundary beyond the route allowlist.
//
// ANTICIPY_PLAYWRIGHT_MODULE=/absolute/path/to/playwright/index.mjs \
// ANTICIPY_POPUP_PROOF_OUT=/absolute/private/evidence/directory \
//   node proof/audit/check_popup_owner_boundary.mjs
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { resolve, join } from "node:path";
import { pathToFileURL } from "node:url";

const root = resolve(import.meta.dirname, "../..");
assert.ok(process.env.ANTICIPY_PLAYWRIGHT_MODULE, "explicit installed Playwright runtime required");
assert.ok(process.env.ANTICIPY_POPUP_PROOF_OUT, "explicit private evidence directory required");
const output = resolve(process.env.ANTICIPY_POPUP_PROOF_OUT);
mkdirSync(output, { recursive: true, mode: 0o700 });
const { chromium } = await import(pathToFileURL(resolve(process.env.ANTICIPY_PLAYWRIGHT_MODULE)));
const base = "https://popup.fixture.invalid";
const files = ["popup.html", "popup.js", "theme.js", "config.js", "workflow_state.js"];
const assets = new Map(files.map(name => [name, readFileSync(join(root, "extension", name))]));
const hashes = Object.fromEntries([...assets].map(([name, bytes]) =>
  [name, createHash("sha256").update(bytes).digest("hex")]));
const identity = (owner = "owner-a") => ({
  paired: true, ownerRef: owner, agentId: `fixture-agent-${owner}`,
  agentToken: `synthetic-token-${owner}`, recordId: `fixture-record-${owner}`,
  pairCode: "123456", backendUrl: base,
});
const task = (owner = "owner-a", id = "job-a") => ({
  id, ownerRef: owner, status: "running", doing: `${owner} synthetic errand`, result: "",
});
const results = [];
const browser = await chromium.launch({ channel: "chrome", headless: true });

async function fixture(name, storage, run, readJob) {
  const context = await browser.newContext({ viewport: { width: 360, height: 760 },
    reducedMotion: "reduce", serviceWorkers: "block" });
  const requests = [], errors = [], blocked = [];
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  page.on("pageerror", error => errors.push(error.message));
  page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
  await context.route("**/*", async route => {
    const request = route.request(), url = new URL(request.url());
    if (request.method() !== "GET" || url.origin !== base) {
      blocked.push({ method: request.method(), url: request.url() });
      return route.abort();
    }
    const asset = url.pathname.slice(1);
    if (assets.has(asset)) return route.fulfill({ status: 200,
      contentType: asset.endsWith(".html") ? "text/html; charset=utf-8" : "text/javascript; charset=utf-8",
      body: assets.get(asset) });
    if (url.pathname === "/favicon.ico") return route.fulfill({ status: 204 });
    if (url.pathname === "/api/health") return route.fulfill({ status: 200, json: { ok: true } });
    if (url.pathname.startsWith("/api/collections/jobs/records/")) {
      requests.push(url.pathname);
      const id = decodeURIComponent(url.pathname.split("/").at(-1));
      const row = readJob ? await readJob(id) : {
        id, owner_ref: storage.ownerRef, params: { _doing: `${storage.ownerRef} synthetic live step` },
      };
      return route.fulfill({ status: 200, json: row });
    }
    blocked.push({ method: request.method(), url: request.url() });
    return route.abort();
  });
  await page.addInitScript(initial => {
    const state = structuredClone(initial), listeners = [], messages = [];
    window.__fixture = {
      state, messages, closes: 0,
      change(values, notify = true) {
        const changes = {};
        for (const [key, value] of Object.entries(values)) {
          changes[key] = { oldValue: state[key], newValue: value };
          state[key] = structuredClone(value);
        }
        if (notify) for (const callback of listeners) callback(changes, "local");
      },
    };
    // A close attempt is itself a failed assertion, even though this tab is
    // not an MV3 popup. The spy avoids losing diagnostic evidence on failure.
    window.close = () => { window.__fixture.closes++; };
    window.chrome = {
      storage: {
        local: { async get(keys) {
          if (typeof keys === "string") keys = [keys];
          return structuredClone(Object.fromEntries(keys.map(key => [key, state[key]])));
        } },
        onChanged: { addListener(callback) { listeners.push(callback); } },
      },
      runtime: { async sendMessage(message) {
        messages.push(structuredClone(message));
        // Refusal lets the test prove controls are not latched on a fake OK.
        return { ok: message.type === "anticipy-ping" };
      } },
    };
  }, storage);
  try {
    await page.goto(`${base}/popup.html`, { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => document.getElementById("linktext").textContent !== "Checking…");
    await run({ page, requests });
    assert.deepEqual(errors, [], "shipping popup must produce no browser errors");
    assert.deepEqual(blocked, [], "every application request must match the fixed fixture allowlist");
    await page.screenshot({ path: join(output, `${name}.png`), fullPage: true });
    results.push({ name, passed: true, jobReads: requests.length, browserErrors: errors.length });
    console.log(`PASS ${name}`);
  } catch (error) {
    results.push({ name, passed: false, error: String(error.message), browserErrors: errors });
    throw error;
  } finally { await context.close(); }
}

try {
  await fixture("same-owner-stop-and-refused-handback", {
    ...identity(), currentJob: task(), handBacks: {
      7: { ownerRef: "owner-a", at: 1 }, 8: { ownerRef: "owner-b", at: 9 }, 9: { at: 10 },
    },
  }, async ({ page }) => {
    await page.waitForFunction(() => document.getElementById("jobdoing").textContent === "owner-a synthetic live step");
    assert.ok(await page.locator("#jobbox").isVisible());
    await page.getByRole("button", { name: "Stop", exact: true }).click();
    await page.waitForFunction(() => window.__fixture.messages.some(m => m.type === "anticipy-stop"));
    assert.deepEqual(await page.evaluate(() => window.__fixture.messages.filter(m => m.type === "anticipy-stop")),
      [{ type: "anticipy-stop", id: "job-a", ownerRef: "owner-a" }]);
    await page.waitForFunction(() => !document.getElementById("jobdoing").textContent.includes("Stopping"));
    assert.ok(await page.locator("#stop").isVisible(), "refused Stop must restore the control");
    await page.getByRole("button", { name: "Open the page", exact: true }).click();
    await page.waitForFunction(() => window.__fixture.messages.some(m => m.type === "anticipy-open-handback"));
    assert.deepEqual(await page.evaluate(() => window.__fixture.messages.filter(m => m.type === "anticipy-open-handback")),
      [{ type: "anticipy-open-handback", tabId: "7", ownerRef: "owner-a" }]);
    assert.equal(await page.evaluate(() => window.__fixture.closes), 0);
    assert.ok(!page.isClosed() && await page.locator("#openhb").isVisible());
  });

  for (const [name, state] of [
    ["unlinked-retained-history", { ...identity(), ownerRef: "", paired: false }],
    ["foreign-retained-history", identity("owner-b")],
    ["legacy-unowned-history", identity()],
  ]) {
    const stored = task();
    if (name === "legacy-unowned-history") delete stored.ownerRef;
    await fixture(name, { ...state, currentJob: stored,
      handBacks: { 7: { ownerRef: "owner-a", at: 1 } } }, async ({ page, requests }) => {
      assert.ok(await page.locator("#jobbox").isHidden(), "actual CSS must hide retained history");
      assert.ok(await page.locator("#openhb").isHidden());
      assert.equal((await page.locator("body").innerText()).includes("owner-a synthetic errand"), false);
      assert.equal(requests.length, 0, "hidden history must not trigger an owner job read");
      assert.equal(await page.evaluate(() => window.__fixture.state.currentJob.doing), stored.doing,
        "the UI hides history without destroying recovery evidence");
    });
  }

  let releaseOld, oldRead;
  const oldRequested = new Promise(resolve => { oldRead = resolve; });
  const oldResult = new Promise(resolve => { releaseOld = resolve; });
  await fixture("owner-switch-delayed-narration", { ...identity(), currentJob: task() },
    async ({ page }) => {
      await Promise.race([oldRequested, new Promise((_, reject) =>
        setTimeout(() => reject(new Error("old-owner fixture read was not reached")), 10000))]);
      assert.ok(await page.locator("#jobbox").isVisible());
      await page.evaluate(values => window.__fixture.change(values), { ...identity("owner-b"), currentJob: null });
      await page.waitForFunction(() => document.getElementById("jobbox").hidden);
      const response = page.waitForResponse(r => r.url().endsWith("/records/job-a"));
      releaseOld({ id: "job-a", owner_ref: "owner-a", params: { _doing: "owner-a stale synthetic narration" } });
      await (await response).finished();
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      assert.ok(await page.locator("#jobbox").isHidden());
      for (const id of ["jobdoing", "joberrand", "jobresult"]) assert.equal(await page.locator(`#${id}`).textContent(), "");
      assert.equal((await page.locator("body").innerText()).includes("owner-a stale synthetic narration"), false);
    }, async () => { oldRead(); return oldResult; });

  await fixture("stale-stop-cannot-switch-owner", { ...identity(), currentJob: task() }, async ({ page }) => {
    await page.waitForFunction(() => document.getElementById("jobdoing").textContent === "owner-a synthetic live step");
    await page.evaluate(values => window.__fixture.change(values, false),
      { ...identity("owner-b"), currentJob: task("owner-b", "job-b") });
    // No storage event: this is a real click on the still-displayed A card.
    await page.getByRole("button", { name: "Stop", exact: true }).click();
    await page.waitForFunction(() => document.getElementById("jobdoing").textContent.includes("owner-b"));
    assert.deepEqual(await page.evaluate(() => window.__fixture.messages.filter(m => m.type === "anticipy-stop")), []);
  }, async id => ({ id, owner_ref: id === "job-a" ? "owner-a" : "owner-b",
    params: { _doing: `${id === "job-a" ? "owner-a" : "owner-b"} synthetic live step` } }));
} finally {
  await browser.close();
  writeFileSync(join(output, "results.json"), JSON.stringify({
    observedAt: new Date().toISOString(), sourceHashes: hashes, results,
    boundaries: "Real Chrome page rendering; synthetic storage/runtime/backend; not installed MV3 or Google/device acceptance",
    visualBaseline: "No prior screenshot baseline: regression comparison inconclusive",
  }, null, 2));
}
assert.equal(results.length, 6);
assert.ok(results.every(row => row.passed));
console.log(`${results.length}/${results.length} real-Chrome popup owner-boundary scenarios passed`);
