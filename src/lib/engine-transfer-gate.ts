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
  return process.env.GATE_PASSCODE_TRANSFER || "123";
}
