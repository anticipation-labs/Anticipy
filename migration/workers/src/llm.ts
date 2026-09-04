/**
 * src/llm.ts — POST /agent/llm, the model proxy.
 * backend/pb_hooks/agent_key.pb.js:65-415. CONTRACT.md §6.4.
 *
 * ┌──────────────────────────────────────────────────────────────────────┐
 * │ THE ONE THAT NEEDED A REAL ANSWER: `timeout: 95`                     │
 * │                                                                      │
 * │ agent_key.pb.js:337 and :389 both pass `timeout: 95` to $http.send —  │
 * │ 95 SECONDS, waiting on Gemini or OpenRouter. That is a deliberate    │
 * │ ceiling on a slow model call, not a mistake.                         │
 * │                                                                      │
 * │ WHAT WORKERS ACTUALLY CONSTRAIN, and they are three different things │
 * │ that get conflated:                                                  │
 * │                                                                      │
 * │  1. CPU time. The Workers Paid default is 30s of CPU per invocation, │
 * │     raisable via `limits.cpu_ms`. Waiting on fetch() spends NO CPU,  │
 * │     so a 95-second model call costs a few milliseconds of it. This   │
 * │     is NOT the constraint people assume it is.                       │
 * │  2. Wall clock. A Worker may stay alive as long as the client stays  │
 * │     connected and it is doing I/O; there is no fixed request-duration │
 * │     cap on the fetch handler. So a 95s upstream is not obviously      │
 * │     refused — but see UNVERIFIED below.                              │
 * │  3. SUBREQUESTS. Each outbound fetch() is one. This handler makes at  │
 * │     most 1 (the provider) + a small number of D1 writes for the audit │
 * │     row. Free plan: 50. Paid: 1000. Not close on either.             │
 * │                                                                      │
 * │ UNVERIFIED, AND IT IS THE THING TO TEST BEFORE PHASE 5: whether      │
 * │ Cloudflare's edge terminates a *response that has not started* after  │
 * │ some interval shorter than 95s. This handler cannot start streaming   │
 * │ early — it must read the provider's whole JSON, transform it, and     │
 * │ write an audit row (agent_key.pb.js:129-146) — so a client-facing     │
 * │ idle timeout would bite. The spike is one line: point a Worker at a   │
 * │ deliberately slow endpoint and time the failure.                      │
 * │                                                                      │
 * │ MITIGATION IF IT DOES BITE, and it is cheap: cap the upstream at the  │
 * │ measured ceiling with AbortSignal.timeout() and return the SAME 502   │
 * │ this handler already returns for a provider that answers badly. The   │
 * │ extension already handles that path (agent_loop.js retries), so a     │
 * │ shorter ceiling degrades throughput, not correctness.                 │
 * └──────────────────────────────────────────────────────────────────────┘
 */

/** agent_key.pb.js:337,389. Kept as a named constant so it can be measured. */
export const UPSTREAM_TIMEOUT_MS = 95_000;

export interface LlmEnv {
  DB: D1Database;
  GOOGLE_API_KEY: string;
  OPENROUTER_API_KEY: string;
}

/** agent_key.pb.js:327 — the 900,000-character request ceiling. */
const MAX_REQUEST_CHARS = 900_000;

export async function callProvider(
  url: string, headers: Record<string, string>, serialized: string,
): Promise<{ ok: true; status: number; json: unknown } | { ok: false; why: string }> {
  if (serialized.length > MAX_REQUEST_CHARS) {
    return { ok: false, why: "model request too large" };
  }
  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...headers },
      body: serialized,
      // $http.send's `timeout: 95` has no fetch() equivalent; this is it.
      // WITHOUT IT a hung provider holds the invocation open indefinitely,
      // which on PocketBase was bounded by the option and here would not be.
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
  } catch (err) {
    // agent_key.pb.js answers 502 for "no JSON" and for a non-2xx; a timeout
    // is the same class of event to the caller and gets the same answer, so
    // the extension's existing retry path covers it unchanged.
    return { ok: false, why: `model provider did not answer: ${String(err)}` };
  }

  let body: unknown;
  try { body = await res.json(); }
  catch { return { ok: false, why: "model returned no JSON" }; }

  return { ok: true, status: res.status, json: body };
}

/**
 * agent_key.pb.js:129-146 writes an `agent_llm_audit` row with a request and
 * response SHA-256, for EXPLICITLY TAGGED certification runs only — ordinary
 * customer calls are not retained (1700000030_agent_llm_audit.js:4-5).
 *
 * `$security.sha256` is a hex digest. WebCrypto's is the same primitive; this
 * is the drop-in.
 *
 * KEEP audit_retention's sweep. That table filled the 5GB Railway volume and
 * took production down (1700000037_backup_footprint.js:13-14). D1 has its own
 * ceiling and no volume alarm.
 */
export async function sha256Hex(input: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(input));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}
