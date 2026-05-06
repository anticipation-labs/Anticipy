/**
 * Server-side helpers for the /crm session cookie.
 *
 * The cookie carries an authenticated user identity (id + admin flag) and is
 * HMAC-signed with a secret derived from the service role key. Anyone with
 * a valid cookie has both passed the password check and is acting as a
 * specific user, which the API routes use for attribution and access control.
 */
import { createHmac, timingSafeEqual } from "crypto";

export const CRM_GATE_COOKIE = "anticipy_crm_gate";
export const CRM_GATE_TTL_SECONDS = 60 * 60 * 24 * 30;
export const CRM_PATH_PREFIX = "/crm";

export type CrmSession = {
  user_id: string;
  is_admin: boolean;
  exp: number;
};

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
  return s + ":crm-v2";
}

function encodePayload(s: { u: string; a: 0 | 1; e: number }): string {
  return Buffer.from(JSON.stringify(s), "utf8").toString("base64url");
}

function sign(b64: string): string {
  return createHmac("sha256", secret()).update(b64).digest("hex");
}

export function signCrmSession(session: CrmSession): string {
  const b64 = encodePayload({
    u: session.user_id,
    a: session.is_admin ? 1 : 0,
    e: session.exp,
  });
  return `${b64}.${sign(b64)}`;
}

export function verifyCrmGate(value: string | undefined | null): CrmSession | null {
  if (!value || typeof value !== "string") return null;
  const dot = value.lastIndexOf(".");
  if (dot < 0) return null;
  const b64 = value.slice(0, dot);
  const sig = value.slice(dot + 1);
  if (!b64 || !sig) return null;
  let a: Buffer;
  let b: Buffer;
  try {
    a = Buffer.from(sig, "hex");
    b = Buffer.from(sign(b64), "hex");
  } catch {
    return null;
  }
  if (a.length !== b.length) return null;
  if (!timingSafeEqual(a, b)) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(Buffer.from(b64, "base64url").toString("utf8"));
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== "object") return null;
  const p = parsed as { u?: unknown; a?: unknown; e?: unknown };
  if (typeof p.u !== "string" || typeof p.e !== "number") return null;
  if (p.e < Math.floor(Date.now() / 1000)) return null;
  return {
    user_id: p.u,
    is_admin: p.a === 1,
    exp: p.e,
  };
}

export function buildSetCrmGateHeader(session: { user_id: string; is_admin: boolean }): string {
  const exp = Math.floor(Date.now() / 1000) + CRM_GATE_TTL_SECONDS;
  const value = signCrmSession({ ...session, exp });
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

export function readCrmSessionFromRequest(req: Request): CrmSession | null {
  const c = req.headers
    .get("cookie")
    ?.split(";")
    .find((s) => s.trim().startsWith(`${CRM_GATE_COOKIE}=`))
    ?.split("=")[1]
    ?.trim();
  return verifyCrmGate(c);
}
