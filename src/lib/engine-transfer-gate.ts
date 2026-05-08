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
  // In production, refuse to fall through to the dev default — a 3-char
  // numeric passcode is brute-forceable on attempt one even with the
  // 10/min/IP limit. The deployment must explicitly set the env var.
  // The dev default stays for local work and CI where convenience wins.
  if (!env || env.length === 0) {
    if (process.env.NODE_ENV === "production") {
      throw new Error(
        "GATE_PASSCODE_TRANSFER must be set in production (refusing to use the dev default)"
      );
    }
    return "123";
  }
  // Length sanity for any environment: a passcode shorter than 6 chars
  // is brute-forceable in seconds even with a generous rate limit.
  if (env.length < 6 && process.env.NODE_ENV === "production") {
    throw new Error(
      "GATE_PASSCODE_TRANSFER must be at least 6 characters in production"
    );
  }
  return env;
}
