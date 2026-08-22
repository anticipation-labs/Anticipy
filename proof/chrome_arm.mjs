#!/usr/bin/env node
// THE BROWSER ARM, STOOD UP BY A SCRIPT INSTEAD OF BY HAND.
//
//   sh proof/local_rig.sh up            # PocketBase + the brain
//   node proof/chrome_arm.mjs up        # this: launch Chrome, point it at the
//                                       # rig, register, pair, prove it is live
//   node proof/chrome_arm.mjs status    # what the arm looks like right now
//   node proof/chrome_arm.mjs down      # kill it and take its jobs with it
//
// WHY THIS EXISTS. Every note in the repo about the browser arm ends with "do
// this by hand": load unpacked, open the options page, paste the backend URL,
// read a 6-digit code off the screen, type it into a phone. That is five
// minutes of clicking before a single measurement, it cannot be repeated
// inside a loop, and — the part that actually costs — it is impossible to be
// sure WHICH build you just measured. proof/browser_battery.py already knew
// the trick (launch, find the service worker, write chrome.storage), it just
// never became a thing you could run on its own.
//
// THE SAFETY PROBLEM, and it is the reason this file is careful.
//
// extension/config.js:12 defaults to PRODUCTION:
//
//     export const DEFAULT_BASE = "https://backend-production-61e0a.up.railway.app";
//
// A fresh profile has no `backendUrl` override, and chrome.runtime.onInstalled
// (background.js:1358) calls ensureRegistered() immediately — before any
// script can possibly write storage. So the naive "launch it and then set the
// URL" sequence posts /agent/register TO THE OWNER'S REAL BACKEND on every
// single launch, and this file is meant to be launched hundreds of times. Junk
// agents rows in production are the mild version; a test browser that pairs
// itself to a real person's queue and starts claiming their errands is the
// version that matters.
//
// The fix is not a code change — the extension under test must stay byte for
// byte the extension that ships. It is a launch flag:
//
//     --host-resolver-rules=MAP <production host> ~NOTFOUND
//
// Chrome then cannot resolve production AT ALL, from any surface, for the life
// of the process. The race is still there and it still fires; it just lands on
// a DNS failure instead of a real person's data. `up` VERIFIES the blackhole
// before it pairs anything, and refuses to continue if the flag ever stops
// working (a Chrome release renaming it would otherwise silently re-arm the
// hazard).
//
// THE PROFILE IS FRESH EVERY TIME, and that is not tidiness either. An MV3
// service worker's MODULE GRAPH is cached in the profile: restarting Chrome,
// or even chrome.runtime.reload(), can re-run the OLD agent_loop.js while
// fetch(getURL('agent_loop.js')) happily returns the new file. Four rounds of
// fixes on 2026-08-20 were verified green in unit tests and invisible in the
// live run for exactly this reason. A throwaway --user-data-dir is the only
// reliable way to know which code you are measuring, so `up` makes one unless
// you insist otherwise with --profile.
//
// Flags:
//   --base=URL          PocketBase (default http://127.0.0.1:8090)
//   --owner-ref=ID      default: ~/.anticipy-rig/state/owner_ref
//   --port=N            remote debugging port (default 29344)
//   --chrome=PATH       Chrome for Testing binary (default: newest in
//                       ~/.cache/puppeteer). Branded stable Chrome 151 ignores
//                       --load-extension, so it is not a fallback.
//                       KNOWN GOOD: 148.0.7778.97. Both 147.0.7727.117 and
//                       148.0.7778.178 leave Emulation.setFocusEmulationEnabled
//                       unanswered, which used to fail every run at step zero
//                       (agent_loop.js now survives it, but typing is degraded).
//                       Install with: npx @puppeteer/browsers install chrome@148.0.7778.97
//   --profile=PATH      reuse a profile (DEFAULT IS A FRESH ONE — see above)
//   --headed            show the window (default is --headless=new)
//   --keep-jobs         `down` leaves this owner's unfinished jobs alone
//   --timeout=S         how long to wait for pairing to land (default 90)
//   --ping-page         leave the setup page open. It pins the service worker
//                       alive and turns the 30s alarm floor into ~200ms, which
//                       is a real production state (the owner watching the
//                       popup) but NOT the one a timing measurement should
//                       assume. Off by default for that reason.
import { spawn, execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, existsSync, readFileSync, readdirSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repo = join(here, "..");

// Accepts --name=value and --name value; a misspelled flag is a typo, and a
// typo that silently changes what a measurement measured is worse than a crash
// (same lesson as proof/extension_smoke.mjs:45).
const KNOWN = ["base", "owner-ref", "port", "chrome", "profile", "headed",
  "keep-jobs", "timeout", "ping-page"];
const argv = process.argv.slice(2);
const cmd = (argv[0] && !argv[0].startsWith("--")) ? argv[0] : "up";
for (const a of argv) {
  if (!a.startsWith("--")) continue;
  const name = a.slice(2).split("=")[0];
  if (!KNOWN.includes(name)) {
    console.error(`unknown flag --${name}\nknown: ${KNOWN.map((k) => `--${k}`).join(" ")}`);
    process.exit(2);
  }
}
const arg = (name, fallback) => {
  const eq = argv.find((a) => a.startsWith(`--${name}=`));
  if (eq) return eq.slice(name.length + 3);
  const at = argv.indexOf(`--${name}`);
  if (at >= 0) {
    const next = argv[at + 1];
    if (next && !next.startsWith("--")) return next;
  }
  return fallback;
};
const flag = (name) => argv.includes(`--${name}`);

const RIG = process.env.ANTICIPY_RIG_DIR || join(homedir(), ".anticipy-rig");
const BASE = (arg("base", "http://127.0.0.1:8090")).replace(/\/$/, "");
const PORT = Number(arg("port", "29344"));
const TIMEOUT_S = Number(arg("timeout", "90"));
const HEADED = flag("headed");

// LOOPBACK ONLY. This script pairs a browser to a queue and then lets that
// browser act. Pointed at production it would pair a disposable test Chrome to
// a real person's errands, which is the one outcome the whole file is built to
// prevent — so it is a refusal, not a warning.
{
  const host = new URL(BASE).hostname;
  if (!["127.0.0.1", "localhost", "::1", "[::1]"].includes(host)) {
    console.error(`refusing to pair a test browser to ${host}: this rig is loopback-only`);
    process.exit(2);
  }
}

const ownerRef = arg("owner-ref", "")
  || (existsSync(join(RIG, "state/owner_ref"))
    ? readFileSync(join(RIG, "state/owner_ref"), "utf8").trim() : "");
if (!ownerRef) {
  console.error("no owner_ref: pass --owner-ref=ID or run `sh proof/local_rig.sh up` first");
  process.exit(2);
}

// The production host is read OUT OF THE EXTENSION rather than pasted here, so
// the blackhole cannot drift away from the literal it is meant to neutralise.
// If config.js stops having a parseable DEFAULT_BASE, that is a hard stop: a
// silently-empty blocklist is the exact failure this guards against.
function productionHost() {
  const src = readFileSync(join(repo, "extension/config.js"), "utf8");
  const m = src.match(/DEFAULT_BASE\s*=\s*["']([^"']+)["']/);
  if (!m) {
    console.error("could not read DEFAULT_BASE out of extension/config.js — refusing to "
      + "launch a browser whose production blackhole cannot be verified");
    process.exit(2);
  }
  return new URL(m[1]).hostname;
}

function newestChrome() {
  const explicit = arg("chrome", "");
  if (explicit) return explicit;
  const root = join(homedir(), ".cache/puppeteer/chrome");
  if (!existsSync(root)) return "";
  const builds = readdirSync(root).filter((d) => d.startsWith("mac_") || d.startsWith("linux"));
  if (!builds.length) return "";
  // Highest major version wins; these directories sort as mac_arm-147.0.x.
  builds.sort((a, b) => {
    const n = (s) => Number((s.match(/-(\d+)\./) || [])[1] || 0);
    return n(b) - n(a);
  });
  const dir = join(root, builds[0]);
  for (const rel of [
    "chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
    "chrome-mac-x64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
    "chrome-linux64/chrome",
  ]) {
    if (existsSync(join(dir, rel))) return join(dir, rel);
  }
  return "";
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function pb(method, path, body) {
  const r = await fetch(`${BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const text = await r.text();
  let json = null;
  try { json = text ? JSON.parse(text) : null; } catch (_) { /* not json */ }
  return { ok: r.ok, status: r.status, json, text };
}

// ------------------------------------------------------------------ CDP
// Node 22+ ships a WebSocket client, so the whole debugger conversation is
// twenty lines and no dependency. Everything this script does to the extension
// goes through the service worker's own Runtime.evaluate, which means it runs
// as the extension, with the extension's chrome.* — not as a page pretending.
async function cdpTargets() {
  const r = await fetch(`http://127.0.0.1:${PORT}/json/list`);
  return r.json();
}

async function evalInTarget(wsUrl, expression, { timeoutMs = 30000 } = {}) {
  const ws = new WebSocket(wsUrl);
  try {
    await new Promise((res, rej) => {
      ws.addEventListener("open", res, { once: true });
      ws.addEventListener("error", () => rej(new Error("cdp socket failed")), { once: true });
    });
    const id = Math.floor(Math.random() * 1e9);
    const done = new Promise((res, rej) => {
      const timer = setTimeout(() => rej(new Error("cdp evaluate timed out")), timeoutMs);
      ws.addEventListener("message", (ev) => {
        let msg;
        try { msg = JSON.parse(ev.data); } catch (_) { return; }
        if (msg.id !== id) return;
        clearTimeout(timer);
        if (msg.error) return rej(new Error(msg.error.message || "cdp error"));
        const r = msg.result?.result;
        if (msg.result?.exceptionDetails) {
          return rej(new Error(msg.result.exceptionDetails.exception?.description
            || msg.result.exceptionDetails.text || "evaluate threw"));
        }
        res(r?.value);
      });
    });
    ws.send(JSON.stringify({
      id,
      method: "Runtime.evaluate",
      params: { expression, awaitPromise: true, returnByValue: true },
    }));
    return await done;
  } finally {
    try { ws.close(); } catch (_) { /* already gone */ }
  }
}

// THE SERVICE WORKER IS A MOVING TARGET, and this is the single thing that
// makes driving an MV3 extension over CDP different from driving a page.
//
// It is LAZY: it does not start until the browser has something to do, so a
// browser that opened no page may show no service_worker target at all.
// It is also MORTAL: Chrome stops it after ~30s idle and respawns it on the
// next alarm or message, WITH A NEW TARGET ID. A socket opened against the
// previous incarnation stays open and simply never answers — which is exactly
// how the first version of this file hung on its very first evaluate, thirty
// seconds after launch, with a perfectly healthy browser on the other end.
//
// So: never hold a target across calls. Re-resolve every time, and treat a
// silent socket as churn rather than as failure.
// One nudge per process, and we remember the page so it can be closed the
// moment the worker is up.
let woken = false;
let wakePageId = "";
async function closeWakePage() {
  if (!wakePageId) return;
  const id = wakePageId;
  wakePageId = "";
  await fetch(`http://127.0.0.1:${PORT}/json/close/${id}`).catch(() => {});
}
async function serviceWorker({ waitS = 45 } = {}) {
  const deadline = Date.now() + waitS * 1000;
  while (Date.now() < deadline) {
    let targets = [];
    try { targets = await cdpTargets(); } catch (_) { await sleep(500); continue; }
    // MATCH OUR EXTENSION BY ID, never "the first service worker". Chrome runs
    // its own COMPONENT extensions with service workers of their own, and on a
    // cold start one of those is routinely listed before ours. The first
    // version of this took whatever came first, latched onto a component
    // worker, and died on `chrome.storage` being undefined — which reads as a
    // broken extension and is in fact the wrong browser tab.
    const sw = targets.find((t) => t.type === "service_worker"
      && String(t.url).startsWith(`chrome-extension://${EXT_ID}/`));
    if (sw?.webSocketDebuggerUrl) { await closeWakePage(); return sw; }
    // No worker listed means it is stopped, not absent. Loading one of the
    // extension's OWN pages is the documented way to wake it: the page's
    // runtime connection starts the worker. about:blank cannot do it — it
    // belongs to no extension.
    //
    // CLOSE IT AGAIN, and only ever keep one. `wokeIt` was function-local, but
    // evalInSW calls this up to four times and up() calls it as well, so a
    // browser that was slow to boot collected a fresh popup on every attempt —
    // five orphaned extension pages in one launch, each pinning a renderer
    // process on a machine that was already at load 19. The waker is a nudge,
    // not a tab the run should keep.
    if (!woken) {
      woken = true;
      const page = await fetch(
        `http://127.0.0.1:${PORT}/json/new?chrome-extension://${EXT_ID}/popup.html`,
        { method: "PUT" }).then((r) => r.json()).catch(() => null);
      if (page?.id) wakePageId = page.id;
    }
    await sleep(500);
  }
  return null;
}

// Every extension-side call goes through here. Re-resolves the worker, and
// retries a socket that went quiet because the worker was recycled underneath
// it. `tries` is small on purpose: a genuinely broken expression should fail
// fast and loudly, not be masked by three more attempts.
// AN UNPACKED EXTENSION'S ID IS A PURE FUNCTION OF ITS ABSOLUTE PATH, so it
// can be known before Chrome has even started: Chrome takes the first 128 bits
// of the SHA-256 of the path and maps each hex nibble onto a..p. Deriving it
// beats discovering it, because discovery has to pick between our worker and
// Chrome's own component workers at exactly the moment ours may not have
// started yet. (This is also why extension/sync-to-chrome.sh refuses to
// re-point Chrome at a different folder: a new path is a new id, and a new id
// breaks the phone pairing.)
const EXT_ID = (() => {
  const hex = createHash("sha256").update(join(repo, "extension"), "utf8")
    .digest("hex").slice(0, 32);
  return [...hex].map((c) => String.fromCharCode(97 + parseInt(c, 16))).join("");
})();
// A LISTED WORKER IS NOT A LIVE WORKER, and this is the second way MV3 lies
// about its own state. When Chrome has stopped the worker the target STAYS in
// /json/list and still accepts a CDP connection — but the context it hands you
// has no extension bindings, so the very first `chrome.storage` reference dies
// with "ReferenceError: chrome is not defined". Read literally that says the
// extension is broken; it means the worker is asleep.
//
// So liveness is asked, not assumed, and a sleeping worker is woken the same
// way a person wakes one: load one of the extension's own pages.
async function wakeWorker() {
  const page = await fetch(
    `http://127.0.0.1:${PORT}/json/new?chrome-extension://${EXT_ID}/onboarding.html`,
    { method: "PUT" }).then((r) => r.json()).catch(() => null);
  await sleep(1500);
  if (page?.id) {
    await fetch(`http://127.0.0.1:${PORT}/json/close/${page.id}`).catch(() => {});
  }
}

async function evalInSW(expression, { timeoutMs = 20000, tries = 5 } = {}) {
  let last = null;
  for (let i = 0; i < tries; i++) {
    const sw = await serviceWorker({ waitS: 20 });
    if (!sw) { last = new Error("no service worker target"); await wakeWorker(); continue; }
    try {
      const alive = await evalInTarget(sw.webSocketDebuggerUrl,
        `typeof chrome !== "undefined" && !!chrome.storage`, { timeoutMs: 8000 });
      if (!alive) throw new Error("service worker is asleep (no chrome bindings)");
      return await evalInTarget(sw.webSocketDebuggerUrl, expression, { timeoutMs });
    } catch (e) {
      last = e;
      const churn = /timed out|socket|asleep|chrome is not defined/i.test(String(e.message));
      // An expression that genuinely THREW is a real answer about the
      // extension; do not paper over it by retrying.
      if (!churn) throw e;
      await wakeWorker();
    }
  }
  throw last || new Error("evaluate failed");
}

function chromeIsUp() {
  return fetch(`http://127.0.0.1:${PORT}/json/version`, { signal: AbortSignal.timeout(1500) })
    .then((r) => r.json()).catch(() => null);
}

function killChrome() {
  // Only ever THIS rig's browsers. `pkill -f chrome` on a developer's Mac is
  // how you close the twelve windows they were working in.
  //
  // TWO PATTERNS, because one is not enough. Only the browser PROCESS carries
  // --remote-debugging-port; its renderers, GPU and utility children do not,
  // and on macOS they do not reliably die with the parent. Measured
  // 2026-08-21: repeated `up` on one port left 290 Chrome processes alive at
  // roughly 70MB each — about 20GB — and the machine went to load 984. Nothing
  // failed outright; the whole rig just got slower and slower, browser tasks
  // started timing out at their budget, and those timeouts score as ENGINE
  // failures. A leak that fabricates red results is worse than a crash.
  //
  // The profile path is the reliable handle: every child of a browser launched
  // by this file carries --user-data-dir=<tmp>/anticipy-arm-<PORT>-*, so that
  // reaches the children the port pattern cannot. Profiles are ours by
  // construction (mkdtemp under the temp dir with that prefix), so this can
  // never touch a browser somebody is using.
  let hit = false;
  for (const pattern of [`--remote-debugging-port=${PORT}`, `anticipy-arm-${PORT}-`]) {
    try {
      execFileSync("pkill", ["-f", pattern], { stdio: "ignore" });
      hit = true;
    } catch (_) { /* nothing matched, which is fine */ }
  }
  return hit;
}

// Orphans from earlier runs of this file, whatever port they were on. `up`
// calls this before launching: a fresh browser is worthless if six dead ones
// are still holding the memory.
function reapOrphans() {
  try {
    // `pgrep -c` is a Linux extension; macOS pgrep does not have it and
    // answers with its usage block on stderr instead of a count.
    const out = execFileSync("pgrep", ["-f", `anticipy-arm-${PORT}-`], { encoding: "utf8" });
    const n = String(out).trim().split("\n").filter(Boolean).length;
    if (n > 0) {
      execFileSync("pkill", ["-9", "-f", `anticipy-arm-${PORT}-`], { stdio: "ignore" });
      console.log(`reaped        ${n} orphaned Chrome process(es) from earlier runs on :${PORT}`);
    }
  } catch (_) { /* none */ }
}

// ------------------------------------------------------------------ up
async function up() {
  const bin = newestChrome();
  if (!bin || !existsSync(bin)) {
    console.error("no Chrome for Testing found under ~/.cache/puppeteer/chrome.\n"
      + "  npx @puppeteer/browsers install chrome@stable\n"
      + "Branded Chrome 151 ignores --load-extension, so it cannot stand in.");
    process.exit(2);
  }
  const health = await pb("GET", "/api/health");
  if (!health.ok) {
    console.error(`backend ${BASE} is not answering — run: sh proof/local_rig.sh up`);
    process.exit(2);
  }

  reapOrphans();
  if (await chromeIsUp()) {
    console.log(`a browser is already on :${PORT} — replacing it`);
    killChrome();
    await sleep(1500);
  }

  // THE PORT IS IN THE PROFILE NAME, and that is load-bearing. The reaper and
  // killChrome both match on this prefix, and a prefix shared by every lane
  // means starting lane 2 kills lane 1. That happened: three arms were launched
  // in sequence and only the last survived, because each launch reaped its
  // siblings' profiles. Scoping the name to the port makes "mine" precise.
  const profile = arg("profile", "")
    || mkdtempSync(join(tmpdir(), `anticipy-arm-${PORT}-`));
  const ext = join(repo, "extension");
  const blocked = productionHost();
  const args = [
    `--user-data-dir=${profile}`,
    `--load-extension=${ext}`,
    `--disable-extensions-except=${ext}`,
    `--remote-debugging-port=${PORT}`,
    // THE SAFETY FLAG. See the header. Everything else here is convenience.
    `--host-resolver-rules=MAP ${blocked} ~NOTFOUND`,
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
    // A frozen tab stops running the agent's own content scripts, and the job
    // simply stalls with no error anywhere.
    "--disable-features=CalculateNativeWinOcclusion,IntensiveWakeUpThrottling",
  ];
  if (!HEADED) args.push("--headless=new");
  args.push("about:blank");

  const child = spawn(bin, args, { detached: true, stdio: "ignore" });
  child.unref();

  console.log(`chrome        ${bin.split("/").slice(-1)[0]} (${HEADED ? "headed" : "headless"})`);
  console.log(`profile       ${profile}`);
  console.log(`blackholed    ${blocked}  <- production cannot be reached from this browser`);

  const sw = await serviceWorker({ waitS: 45 });
  if (!sw) {
    console.error("the extension's service worker never started. Chrome for Testing honours "
      + "--load-extension; branded Chrome does not. Check the binary above.");
    process.exit(2);
  }
  console.log(`extension     ${EXT_ID}`);

  // PROVE THE BLACKHOLE before trusting it with anything. A Chrome release
  // that renamed --host-resolver-rules would re-arm the exact hazard this file
  // exists to remove, and it would do it silently.
  const reach = await evalInSW(`
    (async () => {
      try {
        await fetch("https://${blocked}/api/health",
                    { signal: AbortSignal.timeout(4000) });
        return "REACHED";
      } catch (e) { return "blocked: " + String(e).slice(0, 80); }
    })()
  `);
  if (reach === "REACHED") {
    console.error(`\nREFUSING TO CONTINUE: this browser can still reach ${blocked}.\n`
      + "--host-resolver-rules did not take effect, so a test run could pair itself to\n"
      + "the owner's real queue. Kill it and fix the flag before measuring anything.");
    killChrome();
    process.exit(2);
  }
  console.log(`blackhole ok  ${reach}`);

  // Point it at the rig. From here on every fetch in the extension — job
  // polling AND the /agent/llm proxy — resolves through this one override
  // (extension/config.js exists so those cannot drift apart).
  await evalInSW(
    `chrome.storage.local.set({ backendUrl: ${JSON.stringify(BASE)} })`);

  // Register AGAINST THE RIG. The onInstalled attempt already fired and died
  // on the blackhole; this is the real one.
  //
  // NOT by calling ensureRegistered() over CDP: `import()` is disallowed on
  // ServiceWorkerGlobalScope by the HTML spec, so a module's exports simply
  // cannot be reached from outside the worker. Which is just as well — the
  // honest way is to make the extension do it ITSELF, by the same route a
  // person triggers: open the setup page. onboarding.js:151 sends
  // `anticipy-ping`, and that handler (background.js:1307) re-asserts the
  // alarms and polls on the spot; poll() -> heartbeat() -> ensureRegistered().
  // Measured 194ms versus the 30s alarm floor.
  //
  // The page is CLOSED again immediately. Leaving it open pins the worker
  // alive and short-circuits every subsequent poll, which would quietly make
  // this rig faster than any real install — pass --ping-page if you want that
  // on purpose.
  const setup = await fetch(
    `http://127.0.0.1:${PORT}/json/new?chrome-extension://${EXT_ID}/onboarding.html`,
    { method: "PUT" }).then((r) => r.json()).catch(() => null);

  const regDeadline = Date.now() + 90_000;
  let info = {};
  while (Date.now() < regDeadline) {
    const raw = await evalInSW(
      `chrome.storage.local.get(["recordId","agentId","pairCode"]).then(s => JSON.stringify(s))`
    ).catch(() => null);
    info = raw ? JSON.parse(raw) : {};
    if (info.recordId) break;
    await sleep(2000);
  }
  if (setup?.id && !flag("ping-page")) {
    await fetch(`http://127.0.0.1:${PORT}/json/close/${setup.id}`).catch(() => {});
  }
  if (!info.recordId) {
    console.error(`the extension never registered against ${BASE} within 90s. `
      + `Is the backend up, and does POST /agent/register answer?`);
    process.exit(2);
  }
  console.log(`registered    ${info.recordId}  pair code ${info.pairCode}`);

  // SIMULATE THE PHONE. This is the same write the iPhone app makes when the
  // owner types the 6-digit code: claim a not-yet-paired record by flipping
  // owner/owner_ref/paired exactly once (backend/pb_hooks/guard.pb.js:213).
  const claim = await pb("PATCH", `/api/collections/agents/records/${info.recordId}`,
    { owner: ownerRef, owner_ref: ownerRef, paired: true });
  if (!claim.ok) {
    console.error(`pairing PATCH failed ${claim.status}: ${claim.text.slice(0, 200)}`);
    process.exit(2);
  }

  // Wait for the EXTENSION to notice, rather than declaring victory on our own
  // write. The heartbeat is what teaches it its owner (background.js:262-284)
  // and nothing it does is owner-scoped until that lands. Alarms are on a 30s
  // period, so this legitimately takes half a minute.
  const deadline = Date.now() + TIMEOUT_S * 1000;
  let state = null;
  while (Date.now() < deadline) {
    const raw = await evalInSW(
      `chrome.storage.local.get(["ownerRef","paired","openrouterKey","agentModel"])
         .then(s => JSON.stringify(s))`).catch(() => null);
    state = raw ? JSON.parse(raw) : null;
    if (state?.ownerRef && state?.paired && state?.openrouterKey) break;
    await sleep(3000);
  }
  if (!state?.ownerRef || !state?.paired) {
    console.error(`the extension never picked up its owner within ${TIMEOUT_S}s `
      + `(storage: ${JSON.stringify(state)})`);
    process.exit(2);
  }
  console.log(`paired        owner_ref ${state.ownerRef}`);
  if (!state.openrouterKey) {
    console.error("paired, but the backend handed out no model key: every job this browser "
      + "claims will die at 'no LLM key'. Start PocketBase with OPENROUTER_API_KEY set.");
    process.exit(2);
  }
  console.log(`model         ${state.agentModel} via ${state.openrouterKey}`);
  console.log(`\nthe arm is live. Queue work with: node proof/battery/run.mjs`);
  return 0;
}

// ------------------------------------------------------------------ status
async function status() {
  const v = await chromeIsUp();
  if (!v) { console.log(`no browser on :${PORT}`); return 1; }
  console.log(`browser       ${v.Browser}`);
  const sw = await serviceWorker({ waitS: 5 });
  if (!sw) { console.log("service worker  NOT RUNNING"); return 1; }
  const raw = await evalInSW(
    `chrome.storage.local.get(["backendUrl","ownerRef","paired","agentId","recordId",
       "openrouterKey","agentModel","currentJob"]).then(s => JSON.stringify(s))`);
  const s = JSON.parse(raw || "{}");
  console.log(`backend       ${s.backendUrl}`);
  console.log(`owner_ref     ${s.ownerRef || "(unpaired)"}`);
  console.log(`paired        ${s.paired}`);
  console.log(`model         ${s.agentModel || "(none)"} via ${s.openrouterKey || "(none)"}`);
  console.log(`current job   ${s.currentJob ? s.currentJob.id : "(idle)"}`);
  const q = await pb("GET", `/api/collections/jobs/records?filter=${
    encodeURIComponent(`status="queued" && owner_ref="${s.ownerRef || ownerRef}"`)}&perPage=1`);
  console.log(`queued for it ${q.json?.totalItems ?? "?"}`);
  return 0;
}

// ------------------------------------------------------------------ down
async function down() {
  // A queued browser job is not litter, it is an errand that fires later — and
  // the browser that would have run it is about to stop existing. Cancel this
  // owner's unfinished work unless explicitly told to leave it.
  if (!flag("keep-jobs")) {
    for (const st of ["queued", "running"]) {
      const r = await pb("GET", `/api/collections/jobs/records?filter=${
        encodeURIComponent(`status="${st}" && owner_ref="${ownerRef}"`)}&perPage=200`);
      for (const j of r.json?.items || []) {
        await pb("PATCH", `/api/collections/jobs/records/${j.id}`,
          { status: "cancelled", result: "chrome_arm down: the browser that held this is gone" });
        console.log(`cancelled     ${j.id} (${st}) ${String(j.goal || "").slice(0, 50)}`);
      }
    }
  }
  console.log(killChrome() ? `stopped the browser on :${PORT}` : `nothing was on :${PORT}`);
  return 0;
}

const table = { up, status, down };
if (!table[cmd]) {
  console.error(`usage: node proof/chrome_arm.mjs [up|status|down] [flags]`);
  process.exit(2);
}
process.exit(await table[cmd]());
