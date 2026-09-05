// A 503 USED TO END THE ERRAND.
//
// Fifteen call sites reach the model through modelFetch and none retried. On
// the step call a transport blip became `throw new Error("model unavailable
// (503)")`, which propagates out of runAgentGoal and fails the whole job — the
// tab abandoned mid-form, the owner told the browser could not do it.
// brain/llm.py had the identical hole and the identical fix on 2026-09-04.
//
// The polarity is the whole test. Retrying everything is how a wallet empties:
// the backend proxy's own 429 is an HOURLY CEILING (400 calls, resumes at the
// top of the hour), and retrying it spends three more calls against a limit
// that already tripped. So transients retry, refusals and the ceiling do not,
// the caller's abort is honoured between attempts, and all four are pinned.
//
// Run: node extension/tests/test_model_fetch_retries_transients.mjs
import { installChrome } from "./chrome_mock.mjs";

const harness = installChrome();
const { modelFetch, MODEL_RETRY_ATTEMPTS } = await import("../agent_loop.js");

let failures = 0;
const check = (name, ok) => { console.log(`${ok ? "PASS" : "FAIL"}: ${name}`); if (!ok) failures++; };

// Speed: patch the backoff so the suite does not sleep. Done by monkeying
// setTimeout for the duration of this file — the retry sleeps through it.
const realSetTimeout = globalThis.setTimeout;
globalThis.setTimeout = (fn, ms, ...a) => realSetTimeout(fn, Math.min(ms, 2), ...a);

// A fetch that answers with a scripted sequence of responses, then 200s.
function scripted(sequence) {
  const q = [...sequence]; const calls = [];
  globalThis.fetch = async (url, opts = {}) => {
    calls.push({ url: String(url), signal: opts.signal });
    const next = q.length ? q.shift() : { status: 200 };
    if (next instanceof Error) throw next;
    const bodyText = next.body ?? JSON.stringify({ choices: [{ message: { content: "{}" } }] });
    return { ok: next.status < 400, status: next.status, headers: {},
      text: async () => bodyText, json: async () => JSON.parse(bodyText) };
  };
  return calls;
}
const PAYLOAD = { model: "m", messages: [{ role: "user", content: "x" }] };

// ------------------------------------------------ transients retry and succeed
for (const status of [500, 502, 503, 504]) {
  const calls = scripted([{ status }, { status }]);
  const r = await modelFetch("test-key", PAYLOAD);
  check(`a ${status} is retried and the call succeeds`, r.ok === true && calls.length === 3);
}
{
  const calls = scripted([{ status: 429, body: '{"error":"rate limited"}' }]);
  const r = await modelFetch("test-key", PAYLOAD);
  check("a bare provider 429 (slow down) is retried", r.ok === true && calls.length === 2);
}
{
  const calls = scripted([new TypeError("fetch failed"), new TypeError("fetch failed")]);
  const r = await modelFetch("test-key", PAYLOAD);
  check("a transport error (connection refused / DNS) is retried", r.ok === true && calls.length === 3);
}

// ------------------------------------------------ refusals are NOT retried
for (const status of [400, 401, 403, 404]) {
  const calls = scripted([{ status, body: "nope" }, { status }, { status }]);
  const r = await modelFetch("test-key", PAYLOAD);
  check(`a ${status} is handed straight back — llmStep must see it to refresh the key`, r.status === status && calls.length === 1);
}

// ------------------------------------------------ THE CEILING is not a transient
{
  const ceiling = JSON.stringify({ error: "too many model calls in the last hour",
    detail: "this browser hit its hourly limit; it resumes at the top of the hour" });
  const calls = scripted([{ status: 429, body: ceiling }, { status: 200 }, { status: 200 }]);
  const r = await modelFetch("test-key", PAYLOAD);
  check("the proxy's hourly-ceiling 429 is NOT retried — that is a wallet, not a blip", r.status === 429 && calls.length === 1);
  check("...and the body survives the check, so the caller can read why", (await r.text()).includes("hourly limit"));
}

// ------------------------------------------------ bounded
{
  const calls = scripted(Array(10).fill({ status: 503 }));
  const r = await modelFetch("test-key", PAYLOAD);
  check(`a provider that stays down gets exactly ${MODEL_RETRY_ATTEMPTS} attempts, then its real status comes back`,
    r.status === 503 && calls.length === MODEL_RETRY_ATTEMPTS);
}
{
  const calls = scripted(Array(10).fill(new TypeError("fetch failed")));
  let threw = null;
  try { await modelFetch("test-key", PAYLOAD); } catch (e) { threw = e; }
  check("a transport that never answers throws after the bound, not forever", threw !== null && calls.length === MODEL_RETRY_ATTEMPTS);
}

// ------------------------------------------------ the caller's deadline wins
{
  const ctl = new AbortController();
  const calls = scripted([{ status: 503 }, { status: 503 }, { status: 200 }]);
  // Abort after the first failure lands: the retry loop must see it and stop.
  const origFetch = globalThis.fetch;
  globalThis.fetch = async (u, o) => { const r = await origFetch(u, o); if (calls.length === 1) ctl.abort(); return r; };
  let threw = null;
  try { await modelFetch("test-key", PAYLOAD, ctl.signal); } catch (e) { threw = e; }
  check("an aborted signal stops the retries — a retry never outlives the caller's deadline", calls.length === 1 && threw !== null);
}

// ------------------------------------------------ the happy path pays nothing
{
  const calls = scripted([]);
  const r = await modelFetch("test-key", PAYLOAD);
  check("a healthy call is one call, no delay, no retry", r.ok === true && calls.length === 1);
}

globalThis.setTimeout = realSetTimeout;
if (failures) { console.log(`test_model_fetch_retries_transients: ${failures} FAILED`); process.exit(1); }
console.log("test_model_fetch_retries_transients: all passed");
