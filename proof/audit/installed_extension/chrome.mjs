// Real Chrome, the UNPACKED extension exactly as it sits in extension/, and a
// production blackhole — the proof/audit/chrome_arm.mjs discipline over
// Playwright's persistent context instead of raw CDP. Every extension-side read
// or write runs inside the extension's own service worker (sw.evaluate), never
// as a page pretending. Loopback backends only; the production host is mapped
// to NOTFOUND for the life of the browser and that is VERIFIED before pairing.
//
// Used by run.mjs; can be imported by other scenarios. No model, no account,
// no production data: the backend is the local Worker from local_worker.py.
import { mkdtempSync, existsSync, readFileSync, readdirSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
export const REPO = join(here, "../../..");
export const EXT_DIR = join(REPO, "extension");

// Playwright is not a dependency of this repo and there is no single right
// place for it, so the path is named rather than guessed: an absolute path
// baked in here would publish one machine's home directory and would be wrong
// for everyone else. Same rule as proof/audit/check_popup_owner_boundary.mjs.
const candidates = [process.env.ANTICIPY_PLAYWRIGHT_MODULE,
  join(REPO, "node_modules/playwright/index.mjs")].filter(Boolean);
const pwPath = candidates.find(existsSync);
if (!pwPath) {
  throw new Error("Playwright module required: set ANTICIPY_PLAYWRIGHT_MODULE to an installed "
    + "playwright/index.mjs (this repo does not vendor one), or install playwright at the repo root");
}
const pw = await import(pathToFileURL(pwPath));

export function productionHost() {
  const src = readFileSync(join(EXT_DIR, "config.js"), "utf8");
  const m = src.match(/DEFAULT_BASE\s*=\s*["']([^"']+)["']/);
  if (!m) throw new Error("could not read DEFAULT_BASE out of extension/config.js");
  return new URL(m[1]).hostname;
}

// BRANDED CHROME 137+ IGNORES --load-extension, but exposes the unpacked
// loader over the DevTools pipe behind --enable-unsafe-extension-debugging
// (measured on Chrome 152.0.7977.83, 2026-09-14: `Extensions.loadUnpacked`
// starts the real background.js service worker; the same launch with
// `--disable-extensions-except` disables the loaded copy, and `--load-extension`
// alone loads nothing). Playwright launches over the pipe by default, so no
// Chrome for Testing download is needed. `Extensions.get/setStorageItems` are
// refused on the persistent context ("No associated browser context"), so every
// storage read or write below runs inside one of the extension's OWN pages,
// opened for the call and closed again — an open extension page pins the
// service worker alive and short-circuits the 30 s alarm floor, which is a
// timing a measurement must not silently assume (proof/audit/chrome_arm.mjs).
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const withTimeout = (p, ms, what) => Promise.race([p, new Promise((_, rej) => setTimeout(() => rej(new Error(`${what} timed out after ${ms} ms`)), ms))]);

export async function launch({ profile = "", headed = false, extDir = EXT_DIR } = {}) {
  const blocked = productionHost();
  const userDataDir = profile || mkdtempSync(join(tmpdir(), "anticipy-installed-"));
  const context = await pw.chromium.launchPersistentContext(userDataDir, {
    channel: "chrome", headless: !headed, ignoreDefaultArgs: ["--disable-extensions"],
    args: ["--enable-unsafe-extension-debugging",
      // THE SAFETY FLAG: the production host cannot resolve for the life of this browser.
      `--host-resolver-rules=MAP ${blocked} ~NOTFOUND`, "--no-first-run", "--no-default-browser-check",
      "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
      "--disable-backgrounding-occluded-windows",
      "--disable-features=CalculateNativeWinOcclusion,IntensiveWakeUpThrottling"],
  });
  const cdp = await context.browser().newBrowserCDPSession();
  const { id: extId } = await cdp.send("Extensions.loadUnpacked", { path: extDir });
  // The extension opens its own onboarding page on first install; leave it be
  // for a moment so its "anticipy-ping" fires, then close it so the worker is
  // not pinned awake for the rest of the run.
  await sleep(2500);
  for (const p of context.pages()) if (p.url().startsWith(`chrome-extension://${extId}/`)) await p.close().catch(() => {});
  // PROVE THE BLACKHOLE from inside the extension before anything else.
  const reach = await inExtension(context, extId, async (host) => {
    try { await fetch(`https://${host}/api/health`, { signal: AbortSignal.timeout(4000) }); return "REACHED"; }
    catch (e) { return "blocked: " + String(e).slice(0, 80); }
  }, blocked);
  if (reach === "REACHED") { await context.close(); throw new Error(`browser can still reach ${blocked}; refusing`); }
  return { context, userDataDir, extId, blocked, reach, bin: context.browser().version(), cdp };
}

// Run `fn` inside an extension page (popup.html): it has the extension's
// chrome.* bindings and its origin, and it wakes the service worker. Closed
// again immediately.
export async function inExtension(context, extId, fn, arg) {
  const page = await context.newPage();
  try {
    await withTimeout(page.goto(`chrome-extension://${extId}/popup.html`), 15_000, "open extension page");
    return await withTimeout(page.evaluate(fn, arg), 15_000, "evaluate in extension page");
  } finally { await page.close().catch(() => {}); }
}

export async function storage(context, extId, keys) {
  return inExtension(context, extId, (k) => chrome.storage.local.get(k), keys);
}

export async function setStorage(context, extId, values) {
  return inExtension(context, extId, (v) => chrome.storage.local.set(v), values);
}

export async function cdpTargets(cdp) {
  const { targetInfos } = await cdp.send("Target.getTargets");
  return targetInfos.map((t) => ({ type: t.type, url: t.url }));
}

// The extension registers itself when its setup page pings the worker
// (onboarding.js -> "anticipy-ping" -> poll -> heartbeat -> ensureRegistered).
export async function openSetup(context, extId, { keepOpen = false } = {}) {
  const page = await context.newPage();
  await page.goto(`chrome-extension://${extId}/onboarding.html`);
  if (!keepOpen) { await sleep(1500); await page.close(); return null; }
  return page;
}

export async function waitFor(context, extId, keys, predicate, { timeoutMs = 90_000, everyMs = 2000 } = {}) {
  const deadline = Date.now() + timeoutMs;
  let last = null;
  while (Date.now() < deadline) {
    try { last = await storage(context, extId, keys); if (predicate(last)) return last; } catch (e) { last = { error: String(e) }; }
    await sleep(everyMs);
  }
  return { timedOut: true, last };
}

// A popup, rendered by the real popup.js against the real storage; returns the
// text a person would see, so owner separation is judged on the surface.
export async function popupText(context, extId) {
  const page = await context.newPage();
  await page.goto(`chrome-extension://${extId}/popup.html`);
  await sleep(1200);
  const text = await page.evaluate(() => {
    const ids = ["jobheadtext", "jobdoing", "joberrand", "jobresult", "paircode", "status", "linked", "masthead"];
    const out = {};
    for (const id of ids) { const el = document.getElementById(id); if (el) out[id] = { text: el.textContent.trim(), hidden: el.hidden || el.hasAttribute("hidden") }; }
    out.body = document.body.innerText.replace(/\s+/g, " ").trim().slice(0, 800);
    return out;
  });
  await page.close();
  return text;
}
