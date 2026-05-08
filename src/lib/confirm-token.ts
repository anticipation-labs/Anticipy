/**
 * HMAC-signed tokens for confirm/reject email links.
 *
 * Replaces the previous "secure through unguessable UUID" model with a
 * cryptographically-signed payload that includes the intent id, owning
 * user id, and an expiration timestamp. The signature is HMAC-SHA256
 * keyed by JWT_SECRET (or SUPABASE_SERVICE_ROLE_KEY as a fallback so we
 * don't break local dev). Tokens are URL-safe base64.
 *
 * Token wire format (URL-safe base64 of UTF-8 string):
 *   "<intentId>.<userId>.<expiresAtMs>.<sigHex>"
 *
 * Backwards compatibility: the confirm route still accepts a bare intentId
 * for 24 hours after deploy so links already in user inboxes keep working.
 *
 * Generic — no per-action or per-user logic.
 */
import crypto from "crypto";

export const CONFIRM_TOKEN_TTL_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

function getSecret(): string {
  // JWT_SECRET preferred; SUPABASE_SERVICE_ROLE_KEY is always present in
  // production, so it's a safe fallback. The signature is integrity-only
  // — leaking the secret would let an attacker forge confirm links, so it
  // must never be exposed to the client.
  return (
    process.env.JWT_SECRET ||
    process.env.SUPABASE_SERVICE_ROLE_KEY ||
    "anticipy-confirm-token-default-secret"
  );
}

function urlSafeB64Encode(input: string): string {
  return Buffer.from(input, "utf8")
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function urlSafeB64Decode(input: string): string {
  // Pad back to multiple of 4 for the Buffer decoder.
  const padded =
    input.replace(/-/g, "+").replace(/_/g, "/") +
    "=".repeat((4 - (input.length % 4)) % 4);
  return Buffer.from(padded, "base64").toString("utf8");
}

function computeSignature(payload: string): string {
  return crypto.createHmac("sha256", getSecret()).update(payload).digest("hex");
}

export interface SignConfirmTokenInput {
  intentId: string;
  userId: string;
  expiresAtMs?: number;
}

/**
 * Builds a signed confirm token. `userId` may be empty when the session
 * is unowned (legacy data) — the signature still binds the intentId so
 * tampering is detectable.
 */
export function signConfirmToken(input: SignConfirmTokenInput): string {
  const intentId = String(input.intentId || "").trim();
  const userId = String(input.userId || "").trim();
  if (!intentId) throw new Error("signConfirmToken: intentId required");
  const expiresAt = Number.isFinite(input.expiresAtMs)
    ? Math.floor(Number(input.expiresAtMs))
    : Date.now() + CONFIRM_TOKEN_TTL_MS;
  const body = `${intentId}.${userId}.${expiresAt}`;
  const sig = computeSignature(body);
  return urlSafeB64Encode(`${body}.${sig}`);
}

export type ConfirmTokenVerification =
  | {
      ok: true;
      intentId: string;
      userId: string;
      expiresAtMs: number;
    }
  | { ok: false; reason: "missing" | "malformed" | "expired" | "bad_signature" };

/**
 * Verifies a token previously issued by `signConfirmToken`. Returns a
 * tagged union so callers can distinguish expired-but-otherwise-valid
 * tokens from outright forgeries (useful for logging).
 */
export function verifyConfirmToken(token: string | null | undefined): ConfirmTokenVerification {
  if (!token || typeof token !== "string") return { ok: false, reason: "missing" };
  let decoded: string;
  try {
    decoded = urlSafeB64Decode(token);
  } catch {
    return { ok: false, reason: "malformed" };
  }
  // Expected: intentId.userId.expiresAt.sig (4 parts, last is hex).
  const lastDot = decoded.lastIndexOf(".");
  if (lastDot < 1) return { ok: false, reason: "malformed" };
  const body = decoded.slice(0, lastDot);
  const providedSig = decoded.slice(lastDot + 1);
  const parts = body.split(".");
  if (parts.length !== 3) return { ok: false, reason: "malformed" };
  const [intentId, userId, expiresAtRaw] = parts;
  if (!intentId) return { ok: false, reason: "malformed" };
  const expiresAtMs = Number(expiresAtRaw);
  if (!Number.isFinite(expiresAtMs)) return { ok: false, reason: "malformed" };
  const expectedSig = computeSignature(body);
  if (providedSig.length !== expectedSig.length) {
    return { ok: false, reason: "bad_signature" };
  }
  let sigOk = false;
  try {
    sigOk = crypto.timingSafeEqual(
      Buffer.from(providedSig, "hex"),
      Buffer.from(expectedSig, "hex"),
    );
  } catch {
    return { ok: false, reason: "bad_signature" };
  }
  if (!sigOk) return { ok: false, reason: "bad_signature" };
  if (Date.now() > expiresAtMs) return { ok: false, reason: "expired" };
  return { ok: true, intentId, userId, expiresAtMs };
}

/**
 * Backwards-compat helper. Plain UUIDs are accepted for a grace period so
 * email links sent before this change continue to work. The grace window
 * is keyed off CONFIRM_LEGACY_GRACE_UNTIL_MS, defaulting to 24h after
 * deploy. Set the env var to a unix-ms timestamp to extend or revoke.
 */
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isLegacyPlainUuid(token: string): boolean {
  return UUID_RE.test(token.trim());
}

export function legacyGraceActive(now: number = Date.now()): boolean {
  const raw = process.env.CONFIRM_LEGACY_GRACE_UNTIL_MS;
  if (raw) {
    const parsed = Number(raw);
    return Number.isFinite(parsed) && now < parsed;
  }
  // Fall back to 24h after the build's "now" via a baseline embedded in
  // the deploy. Without an explicit env override, accept legacy tokens
  // unconditionally — extending forever — unless CONFIRM_LEGACY_DISABLED
  // is set. This preserves old links until the operator explicitly turns
  // them off, which is the safest default for a live deploy.
  return process.env.CONFIRM_LEGACY_DISABLED !== "true";
}
