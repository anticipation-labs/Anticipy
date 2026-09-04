/**
 * src/pb/auth.ts — the `owners` auth collection, reimplemented.
 *
 * WHAT MUST NOT BREAK
 * -------------------
 * Nobody is logged out and nobody has to reset a password. That means three
 * separate carry-across obligations, and skipping any one of them is
 * discovered by customers, not by tests:
 *
 *   1. `owners.password` — Go bcrypt digests. Verified, not re-hashed.
 *   2. `owners.tokenKey` — the per-record salt mixed into every issued JWT.
 *      Carry it or every live phone/Mac session dies at cutover.
 *      migration/d1/schema.sql:444-448.
 *   3. Neither column is exportable over REST (schema.sql:437-443). The
 *      cutover needs a NATIVE PocketBase archive as well as a REST export, or
 *      it looks like a clean run and locks everyone out.
 *
 * BCRYPT ON WORKERD: SETTLED
 * --------------------------
 * The library is **`bcryptjs`** (pure JS, no WASM, no native module), already
 * a dependency of this repo at package.json:20 with @types at :16.
 * migration/spike/bcrypt-on-workerd.md ran it on a real workerd
 * (`wrangler dev --local`, wrangler 4.129.0, compatibility_flags
 * ["nodejs_compat"]) against both `$2a$` and `$2b$` digests:
 *
 *     verify_2a_correct: true    verify_2a_wrong: false
 *     verify_2b_correct: true    verify_2b_wrong: false
 *
 * So this is VERIFIED, not assumed. What came with it is a hard constraint:
 * ~50 ms of CPU per verify at cost factor 10 (Go's bcrypt.DefaultCost, which
 * wrote the production hashes). The Workers FREE plan caps CPU at 10 ms per
 * request, so login does not merely run slowly there — it fails, every time,
 * with an exceeded-CPU error. Workers Paid is a precondition for this file.
 * DO NOT lower the cost factor to fit: that silently downgrades every stored
 * password and cannot be undone without the plaintext.
 *
 * WHAT THE SPIKE DID NOT PROVE, and this file therefore has to earn:
 * token issue/refresh keyed on tokenKey, invalidation on delete, and
 * `@request.auth.id` rule semantics.
 */
import bcrypt from "bcryptjs";
import { json, refuse, rowToRecord, pbNow } from "./wire.ts";
import { COLLECTIONS } from "./schema.ts";

export interface AuthEnv {
  DB: D1Database;
  /**
   * The server-side half of the token signature. PocketBase mixes its
   * `settings.recordAuthToken.secret` with the record's own `tokenKey`;
   * rotating either invalidates tokens. Named here, never printed.
   */
  ANTICIPY_AUTH_SECRET: string;
}

/** PocketBase's default record-auth token lifetime: 7 days, in seconds. */
const TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60;

// ---------------------------------------------------------------------------
// Token format
// ---------------------------------------------------------------------------

/**
 * A PocketBase-shaped JWT: HS256 over {id, type, collectionId, exp}.
 *
 * THE KEY IS PER-RECORD. `HMAC(secret ‖ tokenKey)` — so changing a person's
 * `tokenKey` invalidates every token ever issued to them, which is exactly
 * what "log out everywhere", a password change and an account deletion have
 * to do. That property is the entire reason `tokenKey` exists and is why it
 * has to survive the import.
 *
 * DELIBERATE DIVERGENCE: PocketBase's own signing key derivation is an
 * internal of the Go binary and was not read (it is fetched at image build
 * time, backend/Dockerfile:3-6, and is not in this tree). So tokens minted by
 * PocketBase will NOT verify here, and vice versa. That is a cutover event,
 * not a bug — see ARCHITECTURE.md §4.3 "the one thing that does log people
 * out", and the mitigation: the phone and the Mac both re-authenticate from
 * stored credentials, so the visible cost is one silent re-login.
 */
async function hmacKey(env: AuthEnv, tokenKey: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(env.ANTICIPY_AUTH_SECRET + tokenKey),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
}

const b64u = (bytes: Uint8Array): string =>
  btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

const b64uDecode = (s: string): Uint8Array => {
  const padded = s.replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(padded + "=".repeat((4 - (padded.length % 4)) % 4));
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
};

export interface Claims {
  id: string;
  type: "auth";
  collectionName: string;
  exp: number;
}

export async function issueToken(env: AuthEnv, id: string, tokenKey: string): Promise<string> {
  const header = b64u(new TextEncoder().encode(JSON.stringify({ alg: "HS256", typ: "JWT" })));
  const claims: Claims = {
    id, type: "auth", collectionName: "owners",
    exp: Math.floor(Date.now() / 1000) + TOKEN_TTL_SECONDS,
  };
  const payload = b64u(new TextEncoder().encode(JSON.stringify(claims)));
  const signing = `${header}.${payload}`;
  const key = await hmacKey(env, tokenKey);
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(signing)));
  return `${signing}.${b64u(sig)}`;
}

/**
 * Verify a token and return its claims, or null.
 *
 * THE ORDER HERE IS THE SECURITY. The signature cannot be checked without the
 * record's `tokenKey`, and the record cannot be found without trusting the
 * unverified `id` claim to look it up. So: read the id from the UNVERIFIED
 * payload, use it only as a database key, then verify the signature with the
 * key that lookup returned. An attacker who edits the id claim gets a
 * different tokenKey and the signature fails. Nothing is trusted before the
 * HMAC check passes.
 */
export async function verifyToken(
  env: AuthEnv, raw: string,
): Promise<{ claims: Claims; row: Record<string, unknown> } | null> {
  // The iPhone sends the bare token with no scheme
  // (clients/ios/Anticipy/Backend/AnticipyBackend.swift:191). PocketBase also
  // accepts "Bearer <token>". Both must work.
  const token = raw.replace(/^Bearer\s+/i, "").trim();
  const parts = token.split(".");
  if (parts.length !== 3) return null;

  let claims: Claims;
  try {
    claims = JSON.parse(new TextDecoder().decode(b64uDecode(parts[1])));
  } catch { return null; }
  if (!claims || typeof claims.id !== "string" || claims.type !== "auth") return null;
  if (typeof claims.exp !== "number" || claims.exp * 1000 <= Date.now()) return null;
  if (claims.collectionName !== "owners") return null;

  const row = await env.DB.prepare(
    `SELECT * FROM "owners" WHERE "id" = ?1 LIMIT 1`,
  ).bind(claims.id).first<Record<string, unknown>>();
  // A DELETED account's token stops working here, with no revocation list:
  // the row is gone, so there is no tokenKey, so nothing verifies. That is the
  // invalidation-on-delete requirement, and it is a property of the design
  // rather than a sweep somebody has to remember to run.
  if (!row) return null;

  const tokenKey = String(row.tokenKey ?? "");
  if (!tokenKey) return null;

  const key = await hmacKey(env, tokenKey);
  const ok = await crypto.subtle.verify(
    "HMAC", key, b64uDecode(parts[2]),
    new TextEncoder().encode(`${parts[0]}.${parts[1]}`),
  );
  if (!ok) return null;

  return { claims, row };
}

// ---------------------------------------------------------------------------
// POST /api/collections/owners/auth-with-password
// ---------------------------------------------------------------------------

/**
 * guard.pb.js:367-370 keeps this route open for everyone, deliberately: it is
 * how an unauthenticated person introduces themselves, and gating it once made
 * every sign-in return the guard's own {"error":"forbidden"}.
 *
 * Response shape: {token, record}. clients/ios/.../AnticipyBackend.swift:468-478
 * reads exactly those two keys.
 */
export async function authWithPassword(env: AuthEnv, body: Record<string, unknown>): Promise<Response> {
  const identity = String(body.identity ?? "").trim();
  const password = String(body.password ?? "");
  if (!identity || !password) {
    return json(400, {
      code: 400, message: "Failed to authenticate.",
      data: { identity: { code: "validation_required", message: "Missing required value." } },
    });
  }

  // `email` carries a UNIQUE index (schema.sql:454) so this is a point lookup.
  // PocketBase would also match any other field named in `authFields`; owners
  // declares none, so email is the whole identity surface.
  const row = await env.DB.prepare(
    `SELECT * FROM "owners" WHERE "email" = ?1 LIMIT 1`,
  ).bind(identity).first<Record<string, unknown>>();

  // A MISSING ACCOUNT AND A WRONG PASSWORD GET THE SAME ANSWER, and the same
  // approximate timing. Returning early on a missing row turns this endpoint
  // into an account-existence oracle; the tree already treats six-digit
  // guessability as a real threat (guard.pb.js:56-115).
  const hash = String(row?.password ?? "");
  const ok = hash
    ? await bcrypt.compare(password, hash)
    : await bcrypt.compare(password, DUMMY_HASH).then(() => false);

  if (!row || !ok) {
    return json(400, {
      code: 400, message: "Failed to authenticate.", data: {},
    });
  }

  const token = await issueToken(env, String(row.id), String(row.tokenKey ?? ""));
  return json(200, {
    token,
    record: rowToRecord("owners", row, COLLECTIONS.owners.boolColumns),
  });
}

/**
 * A real bcrypt digest of a value nobody knows, at the same cost factor as the
 * production hashes, so the no-such-account path spends the same ~50 ms of CPU
 * as the wrong-password path.
 *
 * NOTE THE COST: this doubles the CPU of a failed login against a nonexistent
 * account. On Workers Paid that is fine. It is another reason the free plan is
 * not an option here.
 */
const DUMMY_HASH = "$2a$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWy";

// ---------------------------------------------------------------------------
// POST /api/collections/owners/auth-refresh
// ---------------------------------------------------------------------------

export async function authRefresh(env: AuthEnv, authHeader: string): Promise<Response> {
  const v = await verifyToken(env, authHeader);
  if (!v) return refuse(401, "The request requires valid record authorization token.");
  const token = await issueToken(env, String(v.row.id), String(v.row.tokenKey ?? ""));
  return json(200, {
    token,
    record: rowToRecord("owners", v.row, COLLECTIONS.owners.boolColumns),
  });
}

// ---------------------------------------------------------------------------
// Invalidation
// ---------------------------------------------------------------------------

/**
 * "Log out everywhere." Rotating tokenKey is the whole mechanism; there is no
 * token blocklist to keep, and there is nothing to expire.
 *
 * CALL THIS FROM: a password change, /me/delete (account_delete.pb.js:57), and
 * the reset-confirm path (password_reset.pb.js:182). A password change that
 * does not rotate the key leaves a stolen session alive after the person has
 * changed their password *because* it was stolen.
 */
export async function rotateTokenKey(env: AuthEnv, ownerId: string): Promise<string> {
  const bytes = crypto.getRandomValues(new Uint8Array(30));
  const key = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  await env.DB.prepare(
    `UPDATE "owners" SET "tokenKey" = ?1, "updated" = ?2 WHERE "id" = ?3`,
  ).bind(key, pbNow(), ownerId).run();
  return key;
}

/**
 * Set a NEW password. bcrypt.hash at cost 10 — the same cost Go wrote with, so
 * a re-hashed password is not weaker than the one it replaced.
 *
 * Rotates tokenKey in the same call, because forgetting to is the bug and a
 * separate function is a thing somebody forgets to call.
 */
export async function setPassword(
  env: AuthEnv, ownerId: string, plaintext: string,
): Promise<void> {
  const hash = await bcrypt.hash(plaintext, 10);
  const bytes = crypto.getRandomValues(new Uint8Array(30));
  const key = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  await env.DB.prepare(
    `UPDATE "owners" SET "password" = ?1, "tokenKey" = ?2, "updated" = ?3 WHERE "id" = ?4`,
  ).bind(hash, key, pbNow(), ownerId).run();
}
