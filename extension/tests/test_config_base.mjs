// Proof for extension/config.js: ONE resolver for the backend base URL.
//
// The defect this defends against never crashed anything. background.js held
// its own production literal plus its own `backendUrl` read for job polling,
// and agent_loop.js held a second, independent literal and read for the model
// proxy. Pointing an install at a local rig therefore moved job polling to the
// rig and left every model call on production: half a run in each world, with
// nothing in either console saying so. So the rule under test is not "the URL
// is right", it is "there is exactly one place that knows it".
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ext = join(dirname(fileURLToPath(import.meta.url)), "..");
// PRODUCTION IS api.anticipy.ai since the 2026-09-05 cutover (Worker + D1;
// research/2026-09-05-cloudflare-era-plan.md). This literal is the pin that the
// extension's DEFAULT really is the backend that serves users — it must not be
// imported from config.js, or "no override resolves to production" proves
// nothing.
const PROD = "https://api.anticipy.ai";
const read = (f) => readFileSync(join(ext, f), "utf8");

// A chrome.storage stand-in that fires onChanged the way Chrome does — the
// no-op listener in chrome_mock.mjs cannot express the cases below. `deferred`
// holds a read open, which is the only way to test what happens when a value
// lands AFTER the override that supersedes it.
function installStorage(initial = {}, { deferred = false } = {}) {
  const data = { ...initial };
  const listeners = [];
  let release = null;
  const announce = (changes) => { for (const fn of listeners) fn(changes, "local"); };
  globalThis.chrome = {
    storage: {
      local: {
        get: async (keys) => {
          const want = typeof keys === "string" ? [keys]
            : Array.isArray(keys) ? keys : Object.keys(keys || data);
          const out = {};
          for (const k of want) if (k in data) out[k] = data[k];
          if (!deferred) return out;
          // `out` is snapshotted here, at call time, exactly like a real read
          // already in flight when someone else writes the key.
          return new Promise((resolve) => { release = () => resolve(out); });
        },
        set: async (obj) => {
          const changes = {};
          for (const [k, v] of Object.entries(obj)) {
            changes[k] = { oldValue: data[k], newValue: v };
            data[k] = v;
          }
          announce(changes);
        },
        remove: async (keys) => {
          const changes = {};
          for (const k of (Array.isArray(keys) ? keys : [keys])) {
            changes[k] = { oldValue: data[k] };   // no newValue, like Chrome
            delete data[k];
          }
          announce(changes);
        },
      },
      onChanged: { addListener: (fn) => listeners.push(fn) },
    },
  };
  return { releaseRead: () => release && release() };
}

// Each case needs a module instance that has not resolved yet, and ES modules
// are evaluated once per specifier — so the query string is load-bearing.
const freshConfig = (tag) => import(`../config.js?case=${tag}`);

// ------------------------------------------------------------- 0: no browser
// This module is imported by agent_loop.js, which several suites import purely
// to source-scan it or to call a pure function in it — no browser involved. The
// first version of config.js touched chrome during module EVALUATION and nine
// such suites died at import with "chrome is not defined". A URL resolver must
// be importable without a browser.
delete globalThis.chrome;
{
  const { backendBase, backendBaseSync, DEFAULT_BASE } = await freshConfig("nochrome");
  assert.equal(DEFAULT_BASE, PROD, "the literal is readable with no chrome at all");
  assert.equal(await backendBase(), PROD, "and resolving falls back instead of throwing");
  assert.equal(backendBaseSync(), PROD);
}
console.log("PASS 0: importable and resolvable with no chrome present");

// ---------------------------------------------------------------- 1: default
installStorage({});
{
  const { backendBase, backendBaseSync, DEFAULT_BASE } = await freshConfig(1);
  assert.equal(DEFAULT_BASE, PROD, "the shipped default is production");
  assert.equal(await backendBase(), PROD, "no override resolves to production");
  assert.equal(backendBaseSync(), PROD, "the sync reader agrees");
}
console.log("PASS 1: with no override every caller gets production");

// --------------------------------------------------------------- 2: override
installStorage({ backendUrl: "http://127.0.0.1:8090" });
{
  const { backendBase, backendBaseSync } = await freshConfig(2);
  assert.equal(await backendBase(), "http://127.0.0.1:8090", "backendUrl wins");
  assert.equal(backendBaseSync(), "http://127.0.0.1:8090",
    "the sync reader must not keep serving production after a resolve");
}
console.log("PASS 2: a stored backendUrl override wins over the default");

// ---------------------------------------------------------- 3: trailing slash
// A trailing slash makes every `${base}/api/...` into `//api/...`, which
// PocketBase answers with a redirect that fetch follows without our headers —
// a 403 that looks like a stale credential rather than a typo.
installStorage({ backendUrl: "http://127.0.0.1:8090/" });
{
  const { backendBase } = await freshConfig(3);
  assert.equal(await backendBase(), "http://127.0.0.1:8090", "trailing slash stripped");
}
console.log("PASS 3: a trailing slash is stripped once, centrally");

// ------------------------------------------------------- 4: live invalidation
{
  installStorage({});
  const { backendBase, backendBaseSync } = await freshConfig(4);
  assert.equal(await backendBase(), PROD, "starts on production");

  await chrome.storage.local.set({ backendUrl: "http://127.0.0.1:8090/" });
  assert.equal(await backendBase(), "http://127.0.0.1:8090",
    "a storage change must invalidate the cache — a dev who sets the override " +
    "and queues a job immediately cannot be told to reload the extension");
  assert.equal(backendBaseSync(), "http://127.0.0.1:8090");

  // Clearing the override means production, not an empty host: Chrome sends no
  // newValue at all on a removal.
  await chrome.storage.local.remove("backendUrl");
  assert.equal(await backendBase(), PROD, "removing the override returns to production");
}
console.log("PASS 4: a storage change invalidates the cache, and clearing it returns to production");

// --------------------------------------------------- 5: a stale read in flight
// The cold-start read and an override can overlap. If the read committed its
// snapshot unconditionally it would silently revert the override the owner just
// set — the same drift bug, one worker generation later.
{
  const store = installStorage({ backendUrl: "http://old.rig:8090" }, { deferred: true });
  const { backendBase, backendBaseSync } = await freshConfig(5);
  const inFlight = backendBase();               // still held open
  await chrome.storage.local.set({ backendUrl: "http://new.rig:9090" });
  assert.equal(backendBaseSync(), "http://new.rig:9090", "the change applies at once");
  store.releaseRead();                          // the OLD value lands now
  assert.equal(await inFlight, "http://new.rig:9090",
    "a read that started before the change must not commit over it");
  assert.equal(await backendBase(), "http://new.rig:9090");
}
console.log("PASS 5: a read already in flight cannot overwrite a newer override");

// ------------------------------------------------------------- 6: source scan
// The regression that matters. Every assertion above passes just as happily
// with a second literal sitting in background.js — that is precisely how the
// original bug survived: both halves worked, separately.
const bg = read("background.js");
// Comment lines are dropped for the checks below that ask "does this code DO
// the thing": background.js still explains in prose why the master-token header
// was removed, and that explanation is the opposite of a regression.
const code = bg.split("\n").filter((l) => !/^\s*\/\//.test(l)).join("\n");
assert.equal(bg.split(PROD).length - 1, 0,
  "background.js must not contain the production backend URL — it lives in config.js");
assert.equal(/https?:\/\/[^"'`\s]*railway\.app/.test(bg), false,
  "background.js must not name the backend host at all, under any spelling");
assert.equal(/https?:\/\/api\.anticipy\.ai/.test(bg), false,
  "background.js must not name the Cloudflare backend host either — it lives in config.js");
assert.match(bg, /import \{ backendBase \} from "\.\/config\.js";/,
  "background.js must consume the shared resolver");
assert.equal(/^\s*(const|let|var)\s+(DEFAULT_BASE|BASE|DEFAULT_LLM_BASE)\b/m.test(bg), false,
  "background.js must not declare a base-URL binding of its own");

const cfg = read("config.js");
assert.equal(cfg.split(PROD).length - 1, 1,
  "config.js states the production URL exactly once");
assert.match(cfg, /^export const DEFAULT_BASE = "/m, "and exports it");

// Self-extending, with no allowlist to rot: a module that imports the shared
// resolver and ALSO keeps its own literal is the drift bug by definition. As
// popup.js, onboarding.js and agent_loop.js are cut over, this covers them
// without an edit here.
const importers = readdirSync(ext)
  .filter((f) => f.endsWith(".js") && f !== "config.js")
  .filter((f) => /from ["']\.\/config\.js["']/.test(read(f)));
assert.ok(importers.includes("background.js"),
  "background.js must be in the config.js import graph, or this check is vacuous");
for (const f of importers) {
  assert.equal(read(f).includes(PROD), false,
    `${f} imports the shared resolver and still carries its own literal`);
}
console.log(`PASS 6: one literal, in config.js; ${importers.length} importer(s) carry none`);

// ------------------------------------------------- 7: what came out with it
// The legacy ACTIONS table (prefilled Gmail/Calendar/search URLs ending at
// awaiting_confirm) was unreachable — workflow rows are rewritten to
// agent_goal, non-workflow rows are refused at claim — and it skipped the
// verification the agent_goal path applies. It must not come back by copy.
assert.equal(/^const ACTIONS\b/m.test(bg), false, "the dead ACTIONS table must stay deleted");
// The server's master credential has no business in a browser. /agent/key has
// returned service_token: "" since the migration ended, so the header could
// only ever have been empty anyway.
assert.equal(code.includes("X-Anticipy-Token"), false,
  "the extension must never send the server's master token");
console.log("PASS 7: the dead ACTIONS table and the master-token header are gone");

console.log("test_config_base: all passed");
