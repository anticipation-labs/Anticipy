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
export const DEFAULT_BASE = "https://backend-production-61e0a.up.railway.app";

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

export async function backendBase() {
  if (resolved) return cached;
  const store = storageArea();
  // No chrome: production is the only truthful answer, and the cache stays
  // UNRESOLVED so the same caller reads for real once a browser exists.
  if (typeof store?.local?.get !== "function") return cached;
  watchOverride(store);
  if (!inFlight) {
    const gen = generation;
    inFlight = store.local.get("backendUrl")
      .then(({ backendUrl }) => {
        if (gen !== generation) return cached;
        cached = strip(backendUrl) || DEFAULT_BASE;
        resolved = true;
        return cached;
      })
      // Storage unreachable is not a reason to fail a job: keep what we have and
      // leave the cache UNRESOLVED so the next call retries.
      .catch(() => cached)
      .finally(() => { inFlight = null; });
  }
  return inFlight;
}

// For the few places that cannot await — a synchronous log line, a template
// built inside a non-async callback. Best-effort by definition: it returns the
// last resolved value, or production before the first read lands. Never use it
// to build a request that a dev override must reach.
export function backendBaseSync() {
  return cached;
}

// Warm the cache at load, fire-and-forget. Deliberately NOT a top-level await:
// an MV3 service worker that awaits during module evaluation delays its own
// registration, and Chrome has been seen to run a stale cached worker graph
// rather than wait. Same shape background.js used before this file existed.
backendBase().catch(() => {});
