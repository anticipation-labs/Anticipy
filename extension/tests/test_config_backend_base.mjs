// Proof for extension/config.js: what the ONE resolver answers when
// chrome.storage does not answer at all.
//
// test_config_base.mjs owns the drift proof — one literal, one reader, no
// second base URL anywhere in the import graph. This suite owns the other half,
// which that one never asked: a read can FAIL, and the answer it falls back to
// is the owner's real production backend. The hazard is not hypothetical and
// the cost is already being paid one directory over: proof/chrome_arm.mjs
// cannot launch a test browser at all without
// `--host-resolver-rules=MAP <production host> ~NOTFOUND`, and it VERIFIES the
// blackhole before it pairs anything, purely because a fresh profile POSTs
// /agent/register from onInstalled before any script can write
// chrome.storage.local.backendUrl. The mitigation lives in the harness; the
// hazard lives in config.js.
//
// So the rule under test is not "production is the default" — it is, correctly,
// and case 0 pins that. The rule is: production must never be the answer
// SILENTLY when the reason for it is a failed read, and an override that has
// been observed must survive one.
import assert from "node:assert/strict";

const PROD = "https://backend-production-61e0a.up.railway.app";
const OVERRIDE = "http://127.0.0.1:8090";

// A chrome.storage stand-in with a failure mode. test_config_base.mjs has a
// stub of its own and this is deliberately not shared with it: that one models
// a store that always answers (its interesting axis is WHEN), this one models
// one that refuses (`reject`) or throws the call straight back (`throw`, which
// is what an invalidated worker context does). Importing that suite to reuse
// its helper would run its assertions, since it asserts at module scope.
function installStorage(initial = {}, { fail = null, deferred = false } = {}) {
  const data = { ...initial };
  const listeners = [];
  let held = null;
  const announce = (changes) => { for (const fn of listeners) fn(changes, "local"); };
  const snapshot = (keys) => {
    const want = typeof keys === "string" ? [keys]
      : Array.isArray(keys) ? keys : Object.keys(keys || data);
    const out = {};
    for (const k of want) if (k in data) out[k] = data[k];
    return out;
  };
  globalThis.chrome = {
    storage: {
      local: {
        get: (keys) => {
          if (fail === "throw") throw new Error("Extension context invalidated");
          const out = snapshot(keys);
          if (fail === "reject") return Promise.reject(new Error("storage read failed"));
          if (!deferred) return Promise.resolve(out);
          return new Promise((resolve, reject) => {
            held = { ok: () => resolve(out), no: () => reject(new Error("storage read failed")) };
          });
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
  return {
    releaseRead: () => held && held.ok(),
    failRead: () => held && held.no(),
    breakReads: (mode = "reject") => { fail = mode; },
  };
}

// The whole point is what happens on a COLD module, and ES modules evaluate
// once per specifier, so the query string is load-bearing. Note that importing
// config.js starts a warm read by itself (the fire-and-forget at the bottom of
// the file), which is why the warning below is counted per module instance
// rather than per call.
const freshConfig = (tag) => import(`../config.js?failcase=${tag}`);

// A failed read has to be AUDIBLE, so the console is part of the contract and
// gets asserted on like any other output.
let warned = [];
const realWarn = console.warn;
console.warn = (...args) => { warned.push(args.map(String).join(" ")); };
const freshWarnings = () => { warned = []; };

// -------------------------------------------------- 0: the unchanged install
// A real install with nothing configured must reach production, and must do it
// without a word. Everything below has to stay true of this case or the fix is
// worse than the bug.
freshWarnings();
installStorage({});
{
  const { backendBase } = await freshConfig(0);
  assert.equal(await backendBase(), PROD, "no override resolves to production");
  assert.deepEqual(warned, [], "and says nothing about it: storage answered, the answer was 'no override'");
}
console.log("PASS 0: no override stored resolves to production, silently");

// ------------------------------------------------------------- 1: an override
freshWarnings();
installStorage({ backendUrl: OVERRIDE });
{
  const { backendBase, backendBaseSync } = await freshConfig(1);
  assert.equal(await backendBase(), OVERRIDE, "the stored override wins");
  assert.notEqual(await backendBase(), PROD, "and production is NOT what a dev gets");
  assert.equal(backendBaseSync(), OVERRIDE, "the sync reader agrees once a read has landed");
  assert.deepEqual(warned, [], "a successful read is not an event");
}
console.log("PASS 1: a stored override wins, and production is not served alongside it");

// ------------------------------------------------- 2: the read REJECTS, cold
// The case the harness's DNS blackhole exists for. Production stays the answer
// (a job must not die because a preference read glitched) but it is now an
// answer with a reason attached, and the failure is NOT cached as if storage
// had said "there is no override" — the retry proves that.
freshWarnings();
{
  const store = installStorage({ backendUrl: OVERRIDE }, { fail: "reject" });
  const { backendBase } = await freshConfig(2);
  assert.equal(await backendBase(), PROD,
    "a failed read still yields a usable URL rather than throwing at every call site");
  assert.equal(warned.length, 1,
    "and it is said out loud - once per worker, not once per poll, or a sustained "
    + "outage would bury the console it is trying to inform");
  assert.match(warned[0], /backendUrl/, "the notice names the key that could not be read");
  assert.match(warned[0], /NOT in effect/,
    "and says the consequence, because 'storage error' alone does not tell a dev "
    + "their override is being ignored");
  assert.ok(warned[0].includes(PROD), "and names the host it fell back to");

  // Not cached as an answer: the next call reads again, and the override that
  // was there all along arrives. A failure that poisoned the cache would pin
  // this install to production for the life of the worker.
  store.breakReads(null);
  assert.equal(await backendBase(), OVERRIDE,
    "a failed read must leave the cache UNRESOLVED so the override still lands");
}
console.log("PASS 2: a failed read falls back to production out loud, and does not poison the cache");

// -------------------------------------- 3: the read THROWS instead of rejecting
// chrome.storage.local.get does not always reject: an invalidated worker
// context throws the call straight back. That is the same "storage did not
// answer", so it must take the same path — not escape as a rejection from
// backendBase() into a fetch template string at a dozen call sites.
freshWarnings();
{
  const store = installStorage({ backendUrl: OVERRIDE }, { fail: "throw" });
  const { backendBase } = await freshConfig(3);
  assert.equal(await backendBase(), PROD,
    "a synchronous throw resolves to production instead of rejecting the caller");
  assert.equal(warned.length, 1, "and is just as audible as a rejection");
  store.breakReads(null);
  assert.equal(await backendBase(), OVERRIDE, "and it did not poison the cache either");
}
console.log("PASS 3: a get() that throws takes the same honest path as one that rejects");

// ------------------------- 4: an override already observed, then a failed read
// The silent revert. Once storage has said the override exists, no later
// failure may quietly put this browser back on the owner's production backend —
// that is the one outcome nobody notices until it appears in a real job row.
freshWarnings();
{
  const store = installStorage({ backendUrl: OVERRIDE });
  const { backendBase, backendBaseSync } = await freshConfig("4a");
  assert.equal(await backendBase(), OVERRIDE, "resolved to the override first");
  store.breakReads("throw");
  assert.equal(await backendBase(), OVERRIDE, "a later broken read keeps the override");
  assert.equal(backendBaseSync(), OVERRIDE, "including for the sync reader");
  assert.deepEqual(warned, [], "there is nothing to warn about: the override is still in effect");
}
// Same guarantee, but with the failure landing INSIDE the read that is already
// in flight, which is the only way to reach the fallback with an override
// already known. A read held open, an override written while it is held, then
// the read fails.
freshWarnings();
{
  const store = installStorage({}, { deferred: true });
  const { backendBase, backendBaseSync } = await freshConfig("4b");
  const inFlight = backendBase();
  await chrome.storage.local.set({ backendUrl: OVERRIDE });
  assert.equal(backendBaseSync(), OVERRIDE, "the change applies at once");
  store.failRead();                    // the held read now blows up
  assert.equal(await inFlight, OVERRIDE,
    "a read that FAILS after an override was observed must not revert to production");
  assert.equal(await backendBase(), OVERRIDE);
  assert.deepEqual(warned, [], "and it is not a fallback, so it is not announced as one");
}
console.log("PASS 4: an observed override survives a later failed read, silently and correctly");

// ------------------------------------------------------- 5: onChanged still bites
// A dev who sets the override and queues a job immediately cannot be told to
// reload the extension, so the change event has to invalidate the cache. This
// is the leg that the failure handling above must not have broken.
freshWarnings();
{
  installStorage({});
  const { backendBase, backendBaseSync } = await freshConfig(5);
  assert.equal(await backendBase(), PROD, "starts on production");
  await chrome.storage.local.set({ backendUrl: `${OVERRIDE}/` });
  assert.equal(await backendBase(), OVERRIDE,
    "the next resolve picks up the new value, trailing slash stripped");
  assert.equal(backendBaseSync(), OVERRIDE);
  await chrome.storage.local.remove("backendUrl");
  assert.equal(await backendBase(), PROD,
    "and removing it means production, not an empty host: Chrome sends no newValue");
}
console.log("PASS 5: a storage change still invalidates the cache in both directions");

// ------------------------------------------- 6: backendBaseSync before a resolve
// Its documented contract, asserted so the comment cannot rot: before the first
// read lands it returns production and cannot tell you that is what happened.
// That is why config.js says it is safe for a log line and unsafe for a request.
freshWarnings();
{
  const store = installStorage({ backendUrl: OVERRIDE }, { deferred: true });
  const { backendBase, backendBaseSync } = await freshConfig(6);
  assert.equal(backendBaseSync(), PROD,
    "before any read lands the sync reader returns production - the whole reason "
    + "a caller that must honour a dev override has to await backendBase()");
  const inFlight = backendBase();
  assert.equal(backendBaseSync(), PROD, "still production while the read is in flight");
  store.releaseRead();
  assert.equal(await inFlight, OVERRIDE);
  assert.equal(backendBaseSync(), OVERRIDE, "and the override the moment the read lands");
  assert.deepEqual(warned, [], "a slow read is not a failed read");
}
console.log("PASS 6: backendBaseSync returns production before the first resolve, by contract");

console.warn = realWarn;
console.log("test_config_backend_base: all passed");
