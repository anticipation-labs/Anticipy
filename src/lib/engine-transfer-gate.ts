import crypto from "crypto";

export const GATE_COOKIE_NAME = "engine_transfer_gate";
export const GATE_COOKIE_TTL_SECONDS = 15 * 60; // 15 minutes

function getSecret(): string {
  // Reuse JWT_SECRET if available; otherwise a per-process default.
  // The signed value is just "valid" — the secret prevents forgery, not secrecy.
  return (
    process.env.GATE_COOKIE_SECRET ||
    process.env.JWT_SECRET ||
    "anticipy-engine-transfer-gate-default-secret"
  );
}

export function signGateCookie(value: string): string {
  const sig = crypto.createHmac("sha256", getSecret()).update(value).digest("hex");
  return `${value}.${sig}`;
}

export function verifyGateCookie(token: string | undefined): boolean {
  if (!token || typeof token !== "string") return false;
  const dot = token.lastIndexOf(".");
  if (dot < 1) return false;
  const value = token.slice(0, dot);
  const provided = token.slice(dot + 1);
  if (value !== "valid") return false;
  const expected = crypto.createHmac("sha256", getSecret()).update(value).digest("hex");
  if (provided.length !== expected.length) return false;
  try {
    return crypto.timingSafeEqual(
      Buffer.from(provided, "hex"),
      Buffer.from(expected, "hex"),
    );
  } catch {
    return false;
  }
}

export function getExpectedPasscode(): string {
  const env = process.env.GATE_PASSCODE_TRANSFER;
  // In production, refuse to fall through to the dev default. A 3-char
  // numeric passcode is brute-forceable on attempt one even with the
  // 10/min/IP limit. The deployment must explicitly set the env var.
  // Return a 64-byte random sentinel instead of throwing, so a wrong
  // passcode comes back as a clean 401 (fail-secure, constant-time
  // compare always returns false). Throwing leaked a stack trace via
  // the 500 and signaled the config gap to attackers.
  if (!env || env.length === 0) {
    if (process.env.NODE_ENV === "production") {
      return crypto.randomBytes(64).toString("hex");
    }
    return "123";
  }
  // Length sanity for any environment: a passcode shorter than 6 chars
  // is brute-forceable in seconds even with a generous rate limit.
  if (env.length < 6 && process.env.NODE_ENV === "production") {
    // Same fail-secure posture for a misconfigured (too-short) value.
    return crypto.randomBytes(64).toString("hex");
  }
  return env;
}
