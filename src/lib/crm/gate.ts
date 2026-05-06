/**
 * Server-side helpers for the /crm password gate.
 *
 * Same construction as src/lib/gate-cookie.ts but a different cookie name and
 * longer TTL so the CRM only asks for the password once per device per month.
 * Mirroring the existing engine gate pattern keeps verification consistent.
 */
import { createHmac, timingSafeEqual } from "crypto";

export const CRM_GATE_COOKIE = "anticipy_crm_gate";
export const CRM_GATE_TTL_SECONDS = 60 * 60 * 24 * 30;
export const CRM_PATH_PREFIX = "/crm";

function secret(): string {
  const s =
    process.env.GATE_COOKIE_SECRET ||
    process.env.SUPABASE_SERVICE_ROLE_KEY ||
    "";
  if (!s) {
    throw new Error(
      "Neither GATE_COOKIE_SECRET nor SUPABASE_SERVICE_ROLE_KEY is set"
    );
  }
  return s + ":crm";
}

export function getExpectedPassword(): string {
  return process.env.CRM_PASSWORD || "123";
}

export function signCrmGate(expirySeconds: number): string {
  const sig = createHmac("sha256", secret())
    .update(String(expirySeconds))
    .digest("hex");
  return `${expirySeconds}.${sig}`;
}

export function verifyCrmGate(value: string | undefined | null): boolean {
  if (!value || typeof value !== "string") return false;
  const [expStr, sig] = value.split(".");
  if (!expStr || !sig) return false;
  const exp = Number(expStr);
  if (!Number.isFinite(exp)) return false;
  if (exp < Math.floor(Date.now() / 1000)) return false;
  const expected = createHmac("sha256", secret())
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

export function buildSetCrmGateHeader(): string {
  const exp = Math.floor(Date.now() / 1000) + CRM_GATE_TTL_SECONDS;
  const value = signCrmGate(exp);
  const isProd = process.env.NODE_ENV === "production";
  return [
    `${CRM_GATE_COOKIE}=${value}`,
    `Max-Age=${CRM_GATE_TTL_SECONDS}`,
    "Path=/",
    "HttpOnly",
    "SameSite=Lax",
    isProd ? "Secure" : "",
  ]
    .filter(Boolean)
    .join("; ");
}

export function buildClearCrmGateHeader(): string {
  return [
    `${CRM_GATE_COOKIE}=`,
    "Max-Age=0",
    "Path=/",
    "HttpOnly",
    "SameSite=Lax",
  ].join("; ");
}
