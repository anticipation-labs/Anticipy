/**
 * Shared surface for the fellowship routes — fellowship.pb.js and
 * fellowship_guardian.pb.js, recovered from a backup archive
 * (migration/recovered/, see that README).
 *
 * Every fellows* handler codes against exactly these helpers so 17 routes ported
 * in parallel compose into one module without redefining a thing. The recovered
 * source is the most-recent-committed ancestor of what Railway runs, so each
 * handler's UNAUTHENTICATED contract was diffed against production; the
 * authenticated / email / oembed / payout paths ship UNPROVEN, exactly as HQ's
 * did, and are flagged per route.
 */
import { sha256Hex as _sha256Hex } from "../llm.ts";
import { newRecordId, pbNow } from "../pb/wire.ts";

export interface FellowsEnv {
  DB: D1Database;
  RESEND_API_KEY?: string;
  OPENROUTER_API_KEY?: string;
  ANTICIPY_FELLOW_SALT?: string;
  ANTICIPY_FELLOW_EMAIL_CEILING?: string;
  ANTICIPY_INTERNAL_KEY?: string;
  ANTICIPY_SITE_URL?: string;
  ANTICIPY_FELLOWSHIP_URL?: string;
  ANTICIPY_INTERNAL_MODEL?: string;
  ANTICIPY_FELLOW_TERMS_VERSION?: string;
  ANTICIPY_FELLOW_LLM_CEILING?: string;
  ANTICIPY_FELLOW_MODEL?: string;
}

export { newRecordId, pbNow };
export const sha256Hex = _sha256Hex;

export const json = (status: number, body: unknown, extra?: Record<string, string>) =>
  new Response(JSON.stringify(body), {
    status, headers: { "content-type": "application/json", ...(extra ?? {}) },
  });

export async function readBody(req: Request): Promise<Record<string, unknown>> {
  try { return (await req.json()) as Record<string, unknown>; } catch { return {}; }
}

/** $security.equal — length is not secret, the bytes are. */
export function timingEqual(a: string, b: string): boolean {
  let d = a.length === b.length ? 0 : 1;
  for (let i = 0; i < a.length && i < b.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

/** T-format ISO, matching what the source writes with new Date().toISOString(). */
export function isoNow(at: Date = new Date()): string {
  return at.toISOString();
}

/**
 * X-Forwarded-For[0] first, CF-Connecting-IP second. The pages are served from
 * anticipy.ai through a Vercel rewrite, so the request is forwarded twice and
 * the peer address is Vercel for everyone — the leftmost XFF entry is the real
 * client. fellowship.pb.js:105-128 explains the trade in full.
 */
export function resolveClientIP(req: Request): string {
  const xff = String(req.headers.get("X-Forwarded-For") || "");
  if (xff) return xff.split(",")[0].trim();
  return String(req.headers.get("CF-Connecting-IP") || "");
}

/** The $http.send to api.resend.com, as a fetch. */
export async function sendResendEmail(
  env: FellowsEnv, to: string, subject: string, text: string,
  from = "Anticipy Fellowships <notifications@aevoy.com>",
): Promise<boolean> {
  const rk = env.RESEND_API_KEY || "";
  if (!rk || !to) return false;
  try {
    const res = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: "Bearer " + rk, "Content-Type": "application/json" },
      body: JSON.stringify({ from, to: [to], subject, text }),
      signal: AbortSignal.timeout(20_000),
    });
    return res.status >= 200 && res.status < 300;
  } catch { return false; }
}

/** crypto-based, replacing Math.floor(100000 + Math.random()*900000). */
export function randomDigits(n: number): string {
  const bytes = crypto.getRandomValues(new Uint8Array(n));
  let out = "";
  for (const b of bytes) out += String(b % 10);
  return out;
}

export function randomHex(n: number): string {
  const bytes = crypto.getRandomValues(new Uint8Array(Math.ceil(n / 2)));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("").slice(0, n);
}

/**
 * D1 INTEGER/text -> bool. PocketBase's `record.get("x") !== false` is TRUE for
 * a D1 0, so it is never transcribed literally; this is what the ported code
 * calls instead. Treats 0, "", "0", "false", null, undefined as false.
 */
export function boolTrue(v: unknown): boolean {
  return !(v === 0 || v === false || v === "" || v === "0" || v === "false"
           || v === null || v === undefined);
}
