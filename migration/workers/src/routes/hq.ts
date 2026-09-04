/**
 * HQ's front door -- internal_hq.pb.js, CONTRACT.md §7.
 *
 * internal_hq.pb.js is 3,185 code lines, 38 routes, its own auth stack separate
 * from PocketBase's, a Clerk JWT exchange, an encrypted vault and an ICS feed.
 * This file is the DOOR, not the building: health, login, the session gate, CORS
 * and the retired AI surface. The 33 data routes behind it are still to come.
 *
 * HQ DOES NOT USE POCKETBASE AUTH AT ALL. It has:
 *   X-Internal-Key   a shared key, compared against ANTICIPY_INTERNAL_KEY
 *   X-HQ-Session     a per-person session token, stored as sha256 in
 *                    internal_sessions
 *   8-char login codes hashed into internal_people.code_hash
 *   a Clerk JWT exchange at /internal/clerk/exchange
 * Four ways in, none of them `owners`.
 */
const json = (status: number, body: unknown, extra?: Record<string, string>) =>
  new Response(JSON.stringify(body), {
    status, headers: { "content-type": "application/json", ...(extra ?? {}) },
  });

export interface HqEnv {
  DB: D1Database;
  ASSETS: Fetcher;
  ANTICIPY_INTERNAL_KEY?: string;
  ANTICIPY_HQ_ORIGIN?: string;
  ANTICIPY_HQ_LOGIN_CEILING?: string;
  ANTICIPY_PUBLIC_HOST?: string;
  CLERK_HQ_JWT_KEY?: string;
  ANTICIPY_INTERNAL_LLM_CEILING?: string;
  TWILIO_ACCOUNT_SID?: string;
  TWILIO_PHONE_NUMBER?: string;
  TWILIO_FROM?: string;
  ANTICIPY_VAULT_KEY?: string;
  RESEND_API_KEY?: string;
  TWILIO_AUTH_TOKEN?: string;
}

/**
 * CORS with an EXPLICIT origin, never "*".
 *
 * These routes carry a credential in a custom header. A wildcard origin plus a
 * custom header is the combination browsers refuse anyway, and relying on that
 * refusal for security would be relying on the client.
 */
export function hqCors(req: Request, env: HqEnv): Record<string, string> {
  const allowed = [env.ANTICIPY_HQ_ORIGIN || "https://www.anticipy.ai",
                   "https://anticipy.ai"];
  const origin = req.headers.get("Origin") || "";
  if (!origin || !allowed.includes(origin)) return {};
  return {
    "Access-Control-Allow-Origin": origin,
    "Vary": "Origin",
    "Access-Control-Allow-Headers": "X-Internal-Key, X-HQ-Session, Content-Type",
    "Access-Control-Allow-Methods": "GET, POST, PATCH, OPTIONS",
    "Access-Control-Max-Age": "86400",
  };
}

function keyOk(env: HqEnv, req: Request): boolean {
  const want = env.ANTICIPY_INTERNAL_KEY || "";
  const got = req.headers.get("X-Internal-Key") || "";
  if (!want || got.length !== want.length) return false;
  let d = 0;
  for (let i = 0; i < got.length; i++) d |= got.charCodeAt(i) ^ want.charCodeAt(i);
  return d === 0;
}

/**
 * §7.1 -- health LEAKS NOTHING AND DERIVES ITS BOOLEANS.
 *
 * Every value is computed from whether a credential is CONFIGURED, never from
 * the credential itself, and the key set is closed: the contract asserts
 * set(keys) <= {ok, gated, version, channels}, so adding a field here is a test
 * failure rather than a quiet disclosure. This route is deliberately unkeyed --
 * it is how the page knows the backend is alive before anyone signs in.
 */
export function hqHealth(req: Request, env: HqEnv): Response {
  return json(200, {
    ok: true,
    gated: !!(env.ANTICIPY_INTERNAL_KEY || ""),
    version: "hq-2",
    channels: {
      email: !!(env.RESEND_API_KEY || ""),
      sms: !!(env.TWILIO_AUTH_TOKEN || ""),
    },
  }, hqCors(req, env));
}

/** §7.2 -- one sentence for a wrong key, and a different one for none set. */
export function hqLogin(req: Request, env: HqEnv): Response {
  const cors = hqCors(req, env);
  if (!(env.ANTICIPY_INTERNAL_KEY || "")) {
    return json(503, { error: "internal HQ is not configured" }, cors);
  }
  if (!keyOk(env, req)) return json(401, { error: "wrong key" }, cors);
  // The gate screen validating a key before it stores it. Nothing more: the
  // key IS the credential, so a correct one has nothing left to prove.
  return json(200, { ok: true }, cors);
}

/** §7.3 -- the session gate in front of every data route. */
export function hqGate(req: Request, env: HqEnv): Response | null {
  const cors = hqCors(req, env);
  if (!(env.ANTICIPY_INTERNAL_KEY || "")) {
    return json(503, { error: "internal HQ is not configured" }, cors);
  }
  if (!keyOk(env, req)) return json(401, { error: "wrong key" }, cors);
  return null;
}

/**
 * §7.12 -- THE RETIRED AI SURFACE.
 *
 * 410 is the FIRST statement in each handler: no key is read, so no 503 is
 * possible and no auth check can turn it into a 401. GONE is the honest answer
 * -- these routes are not coming back, and a 404 would invite a retry.
 */
export const HQ_DEAD_ROUTES = ["/internal/router", "/internal/research",
                               "/internal/research/status"];
export function hqGone(req: Request, env: HqEnv): Response {
  return json(410, { error: "the AI surface was removed from HQ" }, hqCors(req, env));
}

/**
 * §7.13 -- the page SERVES OR FAILS VISIBLY.
 *
 * PocketBase read internal.html off disk with $os.readFile; here it is a static
 * asset. Either way the rule is the same: if the page cannot be produced, say so
 * in HTML the person can read, not a blank 200 that looks like a broken app.
 */
export async function hqPage(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  try {
    const res = await env.ASSETS.fetch(new URL("/internal.html", req.url).toString());
    if (res.ok) {
      const body = await res.text();
      return new Response(body, {
        status: 200,
        headers: {
          "content-type": "text/html; charset=utf-8",
          // Never indexed: it lists three people's phone numbers.
          "X-Robots-Tag": "noindex, nofollow",
          ...cors,
        },
      });
    }
  } catch { /* fall through to the visible failure */ }
  return new Response(
    "<!doctype html><meta charset=utf-8><title>HQ</title>"
    + "<p>HQ couldn't load its page. The backend is up; the page is not.</p>",
    { status: 503, headers: { "content-type": "text/html; charset=utf-8", ...cors } });
}
