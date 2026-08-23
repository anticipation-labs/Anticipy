/**
 * Server-side helpers for signed httpOnly internal-gate cookies.
 *
 * Used by /demo and /internal to keep their hardcoded "123" passcode
 * but move the comparison server-side and prevent client-side bypass.
 *
 * The cookie value is `<expirySeconds>.<hmacSha256(secret, expirySeconds)>`.
 * It is httpOnly + SameSite=Lax + Secure (in production).
 *
 * TODO: rotate GATE_PASSCODE_INTERNAL post-launch — alpha only.
 */
import { createHmac, timingSafeEqual } from "crypto";

export const GATE_COOKIE_NAME = "anticipy_internal_gate";
// 12 hours. It was 15 minutes, which is a sane number for a one-off demo
// link and a miserable one for /internal, where people now work all day:
// HQ would drop them mid-sentence four times an hour and the cookie is
// httpOnly, so nothing in the page can even see it coming. This is a
// passcode gate on internal docs, not an identity session — the thing it
// protects against is a stranger with the URL, and 12 hours does that.
export const GATE_TTL_SECONDS = 12 * 60 * 60; // 12 hours

function getSecret(): string {
  // Reuse SUPABASE_SERVICE_ROLE_KEY for HMAC unless GATE_COOKIE_SECRET is set.
  // The service role key is already required and is a sufficiently long secret;
  // a dedicated GATE_COOKIE_SECRET should be set in production.
  const secret =
    process.env.GATE_COOKIE_SECRET ||
    process.env.SUPABASE_SERVICE_ROLE_KEY ||
    "";
  if (!secret) {
    throw new Error(
      "Neither GATE_COOKIE_SECRET nor SUPABASE_SERVICE_ROLE_KEY is set"
    );
  }
  return secret;
}

export function signGateCookie(expirySeconds: number): string {
  const sig = createHmac("sha256", getSecret())
    .update(String(expirySeconds))
    .digest("hex");
  return `${expirySeconds}.${sig}`;
}

export function verifyGateCookie(value: string | undefined | null): boolean {
  if (!value || typeof value !== "string") return false;
  const [expStr, sig] = value.split(".");
  if (!expStr || !sig) return false;
  const exp = Number(expStr);
  if (!Number.isFinite(exp)) return false;
  if (exp < Math.floor(Date.now() / 1000)) return false;

  const expected = createHmac("sha256", getSecret())
    .update(String(exp))
    .digest("hex");
  try {
    const a = Buffer.from(sig, "hex");
    const b = Buffer.from(expected, "hex");
    if (a.length !== b.length) return false;
    return timingSafeEqual(a, b);
  } catch {
    return false;
  }
}

export function buildSetCookieHeader(): string {
  const exp = Math.floor(Date.now() / 1000) + GATE_TTL_SECONDS;
  const value = signGateCookie(exp);
  const isProd = process.env.NODE_ENV === "production";
  // Path=/ so /demo and /internal both see it.
  return [
    `${GATE_COOKIE_NAME}=${value}`,
    `Max-Age=${GATE_TTL_SECONDS}`,
    "Path=/",
    "HttpOnly",
    "SameSite=Lax",
    isProd ? "Secure" : "",
  ]
    .filter(Boolean)
    .join("; ");
}
