/**
 * Server-side password hashing using Node's built-in scrypt.
 *
 * Stored format: scrypt$N$r$p$<salt-base64url>$<hash-base64url>
 * (no external dependency required, deliberately node-only).
 */
import { randomBytes, scrypt as scryptCb, timingSafeEqual } from "crypto";

const N = 16384;
const r = 8;
const p = 1;
const KEY_LEN = 64;
const SALT_BYTES = 16;

function scrypt(password: string, salt: Buffer): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    scryptCb(password, salt, KEY_LEN, { N, r, p }, (err, derived) => {
      if (err) reject(err);
      else resolve(derived as Buffer);
    });
  });
}

export async function hashPassword(password: string): Promise<string> {
  if (typeof password !== "string" || password.length < 4) {
    throw new Error("Password must be at least 4 characters");
  }
  if (password.length > 200) {
    throw new Error("Password too long");
  }
  const salt = randomBytes(SALT_BYTES);
  const hash = await scrypt(password, salt);
  return [
    "scrypt",
    String(N),
    String(r),
    String(p),
    salt.toString("base64url"),
    hash.toString("base64url"),
  ].join("$");
}

export async function verifyPassword(
  password: string,
  stored: string | null | undefined
): Promise<boolean> {
  if (!stored || typeof stored !== "string") return false;
  const parts = stored.split("$");
  if (parts.length !== 6 || parts[0] !== "scrypt") return false;
  const salt = Buffer.from(parts[4], "base64url");
  const expected = Buffer.from(parts[5], "base64url");
  let derived: Buffer;
  try {
    derived = await scrypt(password, salt);
  } catch {
    return false;
  }
  if (derived.length !== expected.length) return false;
  return timingSafeEqual(derived, expected);
}
