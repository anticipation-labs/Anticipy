// Where the backend lives. One resolver, one literal, for the whole extension.
//
// This file exists because there were TWO of them. background.js held its own
// `DEFAULT_BASE` and its own `chrome.storage.local.backendUrl` read for job
// polling; agent_loop.js held an independent `DEFAULT_LLM_BASE` and a second
// read for the `/agent/llm` proxy. Two literals drift, and the drift is
// invisible in the worst possible way: pointing an install at a local rig made
// job polling talk to the rig while every model call kept going to production,
// so half a run happened in one world and half in another and neither console
// said a word about it. A dev override has to be in effect everywhere or
// nowhere, which means exactly one place may know the URL.
// CUTOVER 2026-09-05: production is the Cloudflare Worker at api.anticipy.ai
// (Worker + D1; research/2026-09-05-cloudflare-era-plan.md). The Railway host
// stays up only for installs older than this line. A fresh install pairs with
// a phone that is itself api-pointed, and pairing needs both halves on one
// backend. Proven before this flip: proof/extension_smoke.mjs against
// api.anticipy.ai, 10/10, on the real 0.13.0 install.
export const DEFAULT_BASE = "https://api.anticipy.ai";

// A trailing slash turns every `${base}/api/...` into `//api/...`, which
// PocketBase answers with a redirect the fetch then follows without the
// headers — a 403 that reads like a stale credential rather than a typo.
// Strip it once, here, instead of at each of the dozen call sites.
const strip = (u) => String(u || "").replace(/\/$/, "");

// Last value we actually resolved. Seeded with production so a caller that
// runs before the first storage read still gets a working URL rather than "".
let cached = DEFAULT_BASE;
let resolved = false;
// The in-flight read, shared: a service worker wakes several paths at once
// (alarm + message + boot poll) and each would otherwise open its own
// storage read on a cold start.
let inFlight = null;
// Bumped by every storage change. An in-flight read that started BEFORE a
// change must not commit its now-stale value on top of the new one — that
// would silently revert an override the owner just set.
let generation = 0;
let listening = false;
// A read that FAILED is not an answer, and the fallback it forces has to be
// audible. Said once per worker: after any successful read `resolved` is true
// and the failure path below is unreachable for the rest of this worker's life.
let warnedFailedRead = false;

// `chrome` is genuinely absent in situations that matter, and none of them is a
// bug: the offline suites import parts of this module graph before installing
// their chrome stub, and several import a module purely to source-scan it or to
// call a pure function in it. Touching chrome during module EVALUATION turns
// every one of those into a load-time ReferenceError — the moment agent_loop.js
// started importing this file, nine suites died at import, none of which had any
// business needing a browser to read a URL. So every access goes through here.
const storageArea = () => (typeof chrome !== "undefined" && chrome.storage) || null;

// Attached on first use rather than at load, for the same reason: whenever
// chrome does show up, the next resolve attaches the watcher.
function watchOverride(store) {
  if (listening || typeof store.onChanged?.addListener !== "function") return;
  listening = true;
  // An override written while the worker is alive has to take effect without a
  // reload. The event payload is authoritative, so this refills the cache
  // rather than merely clearing it — but `newValue` is ABSENT when the key is
  // removed, and no override means production, not an empty host.
  store.onChanged.addListener((changes, area) => {
    if (area !== "local" || !changes.backendUrl) return;
    generation++;
    cached = strip(changes.backendUrl.newValue) || DEFAULT_BASE;
    resolved = true;
  });
}

// Both shapes of "storage did not answer" land here: a read that rejects, and
// a `get` that throws straight back at the caller instead of returning a
// promise (an invalidated worker context does exactly that). Neither is an
// ANSWER, so neither may be cached as one — `resolved` stays false and the
// next call retries.
function failedRead(e) {
  // An override, once observed, is never reverted by a later failed read:
  // `resolved` is true from then on and backendBase() returns at its first line
  // without reading again. Written out rather than left implicit because that
  // guarantee currently rests entirely on that early return, and a silent
  // revert to production is the one failure in this file nobody notices until
  // it turns up in a real job row.
  if (resolved) return cached;
  // The evidence that this hazard is real and not theoretical:
  // proof/chrome_arm.mjs cannot launch a test browser at all without
  // `--host-resolver-rules=MAP <production host> ~NOTFOUND`, because a fresh
  // profile POSTs /agent/register from onInstalled before any script can write
  // chrome.storage. Production is still the correct answer for a real install
  // with nothing configured, so it stays the answer here — but a dev whose
  // override vanished into a failed read finds out in the worker console
  // instead of in a production job row.
  if (!warnedFailedRead) {
    warnedFailedRead = true;
    console.warn("Anticipy: could not read backendUrl from storage "
      + `(${String(e).slice(0, 160)}) - falling back to ${DEFAULT_BASE}. `
      + "any dev override is NOT in effect until a read succeeds");
  }
  return DEFAULT_BASE;
}

export async function backendBase() {
  if (resolved) return cached;
  const store = storageArea();
  // No chrome: production is the only truthful answer, and the cache stays
  // UNRESOLVED so the same caller reads for real once a browser exists.
  if (typeof store?.local?.get !== "function") return cached;
  watchOverride(store);
  if (!inFlight) {
    const gen = generation;
    // `get` is called synchronously, inside the try rather than behind a
    // then(): the snapshot a read commits has to be the one taken when the
    // read STARTED, which is what makes the generation check above meaningful.
    try {
      inFlight = store.local.get("backendUrl")
        .then(({ backendUrl }) => {
          if (gen !== generation) return cached;
          cached = strip(backendUrl) || DEFAULT_BASE;
          resolved = true;
          return cached;
        })
        // Storage unreachable is not a reason to fail a job: keep serving a
        // usable URL rather than throwing at every call site that builds a
        // request out of one.
        .catch(failedRead)
        .finally(() => { inFlight = null; });
    } catch (e) {
      return failedRead(e);
    }
  }
  return inFlight;
}

// For the few places that cannot await — a synchronous log line, a template
// built inside a non-async callback. Best-effort by construction, and the
// contract is exactly this: before the first read lands it returns
// DEFAULT_BASE, i.e. PRODUCTION, and it cannot tell a caller that that is what
// happened. It is safe for a log line and unsafe for a request, so a caller
// that must honour a dev override has to await backendBase() instead — the
// warm read at the bottom of this file makes that await cheap after boot.
// Nothing in the extension calls this today (background.js, agent_loop.js,
// popup.js and onboarding.js all await backendBase()); it exists for the
// non-async callback case, and a new caller should read the two sentences
// above before becoming the first one.
export function backendBaseSync() {
  return cached;
}

// Warm the cache at load, fire-and-forget. Deliberately NOT a top-level await:
// an MV3 service worker that awaits during module evaluation delays its own
// registration, and Chrome has been seen to run a stale cached worker graph
// rather than wait. Same shape background.js used before this file existed.
backendBase().catch(() => {});
