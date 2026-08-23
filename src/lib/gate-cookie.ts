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
// 30 days. The journey here: 15 minutes (sane for a demo link, absurd for
// a workplace), then 12 hours — which still meant re-typing the passcode
// every single morning before the actual sign-in. HQ now has real identity
// behind this gate (Clerk + per-person sessions); this cookie's only job is
// keeping drive-by strangers off the URL, and 30 days of that costs nothing.
export const GATE_TTL_SECONDS = 30 * 24 * 60 * 60; // 30 days

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
