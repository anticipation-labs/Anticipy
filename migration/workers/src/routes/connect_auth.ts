/**
 * src/routes/connect_auth.ts — THE ONE-TAP PHONE CODE for a texted connect link.
 *
 *   GET  /c/{token}/code    the offer: "Anticipy will text you a code."
 *   POST /c/{token}/code    send it. ALWAYS the same answer, for every token.
 *   POST /c/{token}/verify  { code } → a session scoped to THIS TOKEN ONLY.
 *
 * WHY THIS FILE EXISTS AT ALL. routes/connect.ts requires a signed-in session on
 * every leg, and it is right to: a link in a text is not a credential, it lives
 * in a notification shade and a synced Messages database, and whoever reads it
 * over a shoulder must not be able to bind an account with it. But the auth
 * token lives on the PHONE, inside the app, and the connect page opens in
 * Safari from a text — so in practice the browser has no session and
 * connect.ts answers 401 for everybody. Measured today: every tapped link
 * answers 401. The spec's answer is "a signed-in session OR a one-tap phone
 * code", and this is the code half.
 *
 * WHAT A CODE PROVES, AND WHAT IT MUST NOT BUY. It proves the person holding
 * the browser also holds the phone number on the owner's account. That is
 * enough to finish ONE connect link and nothing else. So the session this file
 * mints is NOT a login: it is an HMAC over (owner, expiry, THIS token's handle),
 * it is refused by src/pb/auth.ts `verifyToken` on sight (four dot-separated
 * fields, not three, and a different key), and the cookie is Path-scoped to the
 * one link. A code texted to a phone that could read the owner's whole account
 * would be a password reset with none of the ceremony — and the number is a
 * ROUTING ADDRESS, not a credential (migration/d1/schema.sql, `owners.phone`:
 * US carriers reassign disconnected numbers after ~45 days).
 *
 * MIRRORED, NOT INVENTED. routes/password_reset.ts already does codes properly
 * and this file copies its discipline line for line: SHA-256 at rest and never
 * the code, a ten-minute life, five guesses, one live code at a time, a minimum
 * gap between texts, an hourly ceiling, SEND BEFORE INSERT so a code that never
 * left the building is never live in the table, and a text that EXPLAINS why it
 * arrived. That last one is not politeness — a bare code teaches people to act
 * on unexplained codes, which is the behaviour every account-takeover call
 * relies on (password_reset.ts, audit F39).
 *
 * AND IT IS NOT AN ORACLE. `POST /c/{token}/code` answers one thing — one
 * status, one body — whether the token is live, expired, already spent, forged,
 * malformed or somebody else's, and whether or not the owner has a phone. That
 * is the same rule connect.ts enforces on its own three legs, and it has to
 * hold here too or this endpoint becomes the string-sorter that file closed:
 * present a token, read the answer, learn whether the text you intercepted is
 * worth keeping. `POST /c/{token}/verify` is the same: one refusal for a wrong
 * code, an expired code, a spent code, a code that belongs to a different link,
 * and no code at all.
 *
 * THE RESIDUAL, WRITTEN DOWN RATHER THAN LEFT FOR SOMEBODY TO FIND. connect.ts
 * keeps the store out of the anonymous path entirely, so its answer cannot be
 * read off a stopwatch. This endpoint CANNOT do that: sending a text is the
 * whole job and it only happens for a live link, so a live token takes longer
 * than an invented one. Three things bound what that is worth. The token is 256
 * bits, so nobody guesses one. The prober therefore already holds an
 * intercepted link — and the only thing they learn is that it is still live,
 * while the code itself goes to the OWNER's phone and never to them. And the
 * rate limits below cap the whole exercise at three texts per link and five per
 * owner per hour. It is a real tell, it is smaller than the tell connect.ts
 * closed, and it is the price of the feature existing at all.
 *
 * HARNESS-LAWS LAW 1. Nothing here decides what a person MEANT. What is
 * pattern-matched is structure and transport only: the shape of a token, the
 * shape of an owner row id, six digits, 64 hex characters, a cookie name, an
 * Origin header. No prose is read anywhere in this file. Which app is being
 * connected arrives as a slug this file never chose, and its display NAME comes
 * from the catalog at run time — there is no app name in this source and there
 * must never be one.
 *
 * WHAT THIS FILE DOES NOT OWN, and must not grow into: the `connect_links`
 * store, the catalog, the connect page itself. They arrive injected, exactly as
 * they do for connect.ts.
 *
 * Spec: "Connections: how Anticipy asks, learns, and never says Composio",
 * 2026-09-05, page 26 — "needing a signed-in session or a one-tap phone code".
 */
import { sendText, type MessagingEnv } from "../messaging.ts";
import {
  tokenHandle, whoIsSignedIn,
  type ConnectEnv, type ConnectLinkStore, type OwnerId, type StoredLink,
} from "./connect.ts";

// ---------------------------------------------------------------------------
// ENV
// ---------------------------------------------------------------------------

/**
 * Everything connect.ts needs (D1 + the auth secret), plus the messaging
 * provider names src/messaging.ts chooses between. The code leaves through
 * `sendText` and no other path, so a deployment with no provider configured
 * sends nothing and says so in a log line rather than in the reply.
 */
export interface ConnectAuthEnv extends ConnectEnv, MessagingEnv {}

// ---------------------------------------------------------------------------
// CONSTANTS — every one of them mirrored from routes/password_reset.ts
// ---------------------------------------------------------------------------

/** Ten minutes, the same life the reset code and the connect link both have. */
export const CODE_TTL_MS = 10 * 60 * 1000;

/** Guesses per code. password_reset.ts MAX_ATTEMPTS. Six digits is a million
 *  values; five guesses makes a walk hopeless and a typo forgivable. */
export const MAX_ATTEMPTS = 5;

/** Between texts for ONE link. password_reset.ts MIN_GAP_SECONDS. */
export const MIN_GAP_MS = 60 * 1000;

/**
 * THE TWO CEILINGS, and they are two on purpose.
 *
 * Per link, because whoever intercepted one text holds exactly one token and
 * must not be able to make the owner's phone buzz all afternoon with it. Per
 * owner, because holding two stolen links must not double the spray — the
 * limit a person experiences is "how many texts can anyone make my phone
 * ring with", and that question is about the OWNER, not about a token.
 *
 * A link lives ten minutes, so three codes is already two more than anyone
 * needs; the per-link count is over the link's whole life, not a window.
 */
export const MAX_CODES_PER_LINK = 3;
export const MAX_CODES_PER_OWNER = 5;
export const OWNER_WINDOW_MS = 60 * 60 * 1000;

/**
 * HOW LONG A CODE SESSION LIVES, and this is the real design decision in this
 * file, so it is written out rather than tuned.
 *
 * The obvious answer is "with the link" — ten minutes. It is wrong, and the
 * way it is wrong is silent and permanent. `/c/{token}/done` is the vendor's
 * callback and, because there is no success webhook, THE ONLY MOMENT WE EVER
 * LEARN A CONNECTION EXISTS. It needs a session too, and by then the person has
 * been away at the vendor: a password manager, a 2FA push, a workspace picker,
 * an account chooser, sometimes a login they did not have. connect.ts sizes
 * that round trip at an hour (`CALLBACK_WINDOW_MS`) for exactly this reason. A
 * ten-minute cookie means the browser comes back from a twelve-minute vendor
 * flow, is told to sign in, and the connection exists at the vendor with no row
 * here and nothing that will ever mention it again — the same permanent loss
 * `ConnectLinkStore.release` was added to prevent, reached from the other end.
 *
 * So the cookie expires at the last instant ANY leg of its token could still
 * act: the link's own `expires_at` plus the callback window. Not one second
 * longer, and it buys nothing extra in that time — every leg re-checks the link
 * for itself, so a replayed cookie meets `already-used` or `expired` exactly as
 * a signed-in browser would. The cookie says WHO, never WHAT.
 *
 * MUST EQUAL connect.ts CALLBACK_WINDOW_MS. It is written out here rather than
 * imported because connect.ts will import `connectSession` from this file, and
 * a module-level constant read across an import cycle is a temporal-dead-zone
 * ReferenceError at boot depending on which module the bundler loads first. The
 * suite pins the equality instead, which is the check that would have caught a
 * drift anyway.
 */
export const CODE_SESSION_GRACE_MS = 60 * 60 * 1000;

/**
 * The cookie's name, per link.
 *
 * `__Secure-` is a browser-enforced prefix: a cookie with this name is refused
 * unless it is set with `Secure` from a secure origin, so a network attacker
 * who can answer for http:// cannot plant one. It is compatible with a narrow
 * `Path` (unlike `__Host-`, which demands `Path=/` — the opposite of what this
 * cookie wants).
 *
 * The name carries the first 16 hex of the token's HANDLE, never the token: two
 * links being connected in one browser need two cookies, and a shared name
 * would make the second connect log the first one out. A handle prefix is the
 * same thing connect.ts already allows a log line to carry — enough to tell two
 * links apart, useless for redeeming either.
 */
export const SESSION_COOKIE_PREFIX = "__Secure-anticipy_c_";

/** The blob's version field. Bump it and every live code session is refused,
 *  which is the whole point of having one. */
const SESSION_VERSION = "1";

/** Domain separation for the HMAC key. A code session and an `owners` token are
 *  signed with keys that cannot collide even if the same secret is bound. */
const SESSION_KEY_SALT = "/anticipy/connect-code-session/v1";

/** Six digits, and the input is capped at that. Not a meaning rule — it is the
 *  length of the thing we generated. */
const CODE_DIGITS = 6;

// ---------------------------------------------------------------------------
// COPY — the register is a product rule, not a preference
// ---------------------------------------------------------------------------

/**
 * The text.
 *
 * The person never reads "authorize", "grant access", "permissions",
 * "integration", "API", "OAuth" or the vendor's name. It says which app, that
 * the code is for connecting that app, how long it lasts, and — the sentence
 * password_reset.ts calls "the standard phishing tell" — what to do if they did
 * not ask for it.
 *
 * `app` comes from the CATALOG at run time and is never typed into this file.
 * When the catalog cannot be reached the sentence still has to be honest, so
 * the app goes unnamed rather than guessed at: a code that names the wrong app
 * is worse than one that names none.
 */
export function connectCodeText(code: string, app: string | null): string {
  const what = app && app.trim() !== "" ? `your ${app.trim()}` : "the app you asked about";
  return `${code} is your Anticipy code to connect ${what}. It works for 10 minutes. `
    + `If you didn't ask to connect anything, ignore this and nothing changes.`;
}

/** Every page in this file, in one place, so they cannot drift apart in five. */
const ASK_HEADING = "Get a code by text";
const ASK_LINE =
  "Anticipy will text a 6-digit code to the phone number on your account, so it knows "
  + "it's you before it sets anything up.";
const ASK_BUTTON = "Text me a code";
const SENT_HEADING = "Check your phone";
/** Note what this does NOT say: not "we sent one", which would be a yes/no
 *  about the token. It is the same sentence for every token there is. */
const SENT_LINE =
  "If this link is still good, a 6-digit code is on its way to the phone number on your "
  + "Anticipy account. It works for 10 minutes.";
const SENT_BUTTON = "Continue";
const NOPE_LINE = "That code isn't right, or it has expired. Ask for a new one.";
const OPTIONAL_LINE =
  "This is optional — Anticipy works fine without it, and you can stop here.";
const CROSS_SITE_HEADING = "That didn't come from here";
const CROSS_SITE_LINE = "Open your Anticipy link again and start from the page itself.";
const UNWIRED_HEADING = "Connecting isn't switched on here";
const UNWIRED_LINE = "Anticipy can't set this up right now. Nothing has changed on your account.";

// ---------------------------------------------------------------------------
// THE SEAM — the code store, which is a table this file does not own
// ---------------------------------------------------------------------------

/**
 * One texted code. The CODE ITSELF IS NEVER HERE: only `sha256(code)` in hex,
 * exactly as `password_resets.code_hash` holds it. A dump of this table hands
 * the reader nothing they can present.
 */
export interface StoredConnectCode {
  id: string;
  token_handle: string;
  user_id: OwnerId;
  code_hash: string;
  expires_at: number;
  attempts: number;
  used_at: number | null;
  created_at: number;
}

/** What the two ceilings need, in one round trip. */
export interface CodeWindow {
  /** Codes ever minted for this link. */
  forLink: number;
  /** Codes minted for this OWNER inside `OWNER_WINDOW_MS`. */
  forOwner: number;
  /** When the newest code for this link was minted, for the minimum gap. */
  newestForLink: number | null;
}

/**
 * `charge` and `spend` are the reason this is an interface and not a map: they
 * are compare-and-sets, and their D1 spellings are written on each method. An
 * implementation that reads a row, decides in JavaScript and writes it back is
 * not an implementation of this interface — it is an attempt counter that two
 * concurrent guesses can both walk past, which is the ceiling deleted.
 */
export interface ConnectCodeStore {
  /** The one live code for a link: newest, unspent. Expiry is the caller's to
   *  judge, so the boundary is decided in one place. */
  newest(tokenHandle: string): Promise<StoredConnectCode | null>;
  window(tokenHandle: string, user: OwnerId, since: number): Promise<CodeWindow>;
  /**
   * ONE CODE AT A TIME, as a database fact rather than a query convention: this
   * spends every unspent code for the link and inserts the new one, in ONE
   * batch. Two statements outside a transaction would leave a window in which
   * the link has no live code, or two.
   */
  insert(row: StoredConnectCode): Promise<void>;
  /**
   * THE GUESS CEILING. One statement, no read-then-write:
   *    UPDATE connect_codes SET attempts = ?1
   *     WHERE id = ?2 AND used_at IS NULL AND attempts = ?3
   * with `?3` the attempts the caller read and `?1` one more. `won = changes
   * === 1`, and a LOSER IS NOT RETRIED — a concurrent guess that lost the race
   * is refused, which is the direction a ceiling must fail in.
   */
  charge(id: string, from: number, to: number): Promise<boolean>;
  /** THE SINGLE-USE GATE, same shape:
   *    UPDATE connect_codes SET used_at = ?1 WHERE id = ?2 AND used_at IS NULL */
  spend(id: string, at: number): Promise<boolean>;
}

/**
 * The `connect_codes` table.
 *
 * IT IS DECLARED HERE AND IT DOES NOT BELONG HERE. migration/d1/schema.sql owns
 * the schema and section 5 of it already holds the other four connections
 * tables; this constant exists because this file could be written and this
 * table could not be added in the same change, and shipping a store whose SQL
 * had never met a real SQLite would have been the worse half.
 *
 * WHAT IS OWED, and it is one paste: this statement and its two indexes go into
 * migration/d1/schema.sql section 5.5, `wrangler d1 execute anticipy-backend
 * --remote --file=migration/d1/schema.sql` applies it, and
 * `connectCodesTableReady()` below is the check that says it landed. On the day
 * that happens THIS CONSTANT IS DELETED and the suite loads the DDL from
 * schema.sql like every other table's tests do. Until then the store is real
 * and tested against these exact bytes, and the feature is repo-green and NOT
 * Law-3 done.
 *
 * IT IS NOT TAPE, and the distinction is deliberate rather than convenient.
 * HARNESS-LAWS law 2 is about a string-level PATCH that decides behaviour and
 * needs an expiry the tape_gate registry can hold. This is a schema statement
 * that has not reached the file which owns schemas, in a change that was not
 * allowed to edit it. Giving it a `TAPE:` comment pointing at a gate leg that
 * tracks something else is audit item #21 exactly — a comment that reads as
 * compliant and enforces nothing. `connectCodesTableReady()` is the honest
 * instrument instead: it asks the LIVE database, which is the only thing law 3
 * counts.
 */
export const CONNECT_CODES_DDL = `
CREATE TABLE IF NOT EXISTS "connect_codes" (
  "id"           TEXT PRIMARY KEY NOT NULL,
  "token_handle" TEXT NOT NULL CHECK (length("token_handle") = 64),
      -- sha256(token) in hex, the same handle "connect_links" is keyed by. The
      -- raw token is never written down here either.
  "user_id"      TEXT NOT NULL CHECK (length("user_id") = 15),
      -- The owner ROW id. The length CHECK is the database's own copy of the
      -- rule: a name or an email is refused HERE, not only in TypeScript.
  "code_hash"    TEXT NOT NULL CHECK (length("code_hash") = 64),
      -- SHA-256 of the six digits, hex. The code itself is NEVER stored, the
      -- same way "password_resets"."code_hash" holds only a digest.
  "expires_at"   REAL NOT NULL,
  "attempts"     INTEGER NOT NULL DEFAULT 0 CHECK ("attempts" >= 0),
  "used_at"      REAL NULL,
      -- NULL = live. The single-use gate, and the reason it is NULL and not 0:
      --   UPDATE "connect_codes" SET "used_at" = ?1
      --    WHERE "id" = ?2 AND "used_at" IS NULL
  "created_at"   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS "idx_connect_codes_link"
  ON "connect_codes" ("token_handle", "created_at");
CREATE INDEX IF NOT EXISTS "idx_connect_codes_owner"
  ON "connect_codes" ("user_id", "created_at");
`;

/**
 * Has the table landed on the database this Worker is actually talking to?
 *
 * A gate leg's question, and it needs to be asked out loud: every failure on
 * the send path is swallowed into the one identical answer (it has to be, or
 * the answer becomes an oracle), so a missing table is a feature that is dead
 * and looks fine. This is the instrument that tells the difference.
 */
export async function connectCodesTableReady(env: { DB: D1Database }): Promise<boolean> {
  try {
    const row = await env.DB.prepare(
      `SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'connect_codes' LIMIT 1`,
    ).first<{ name: string }>();
    return !!row;
  } catch {
    return false;
  }
}

/** The production store. Every write is one statement or one batch. */
export function createD1ConnectCodeStore(env: { DB: D1Database }): ConnectCodeStore {
  const db = env.DB;
  return {
    async newest(tokenHandle: string): Promise<StoredConnectCode | null> {
      const row = await db.prepare(
        `SELECT "id", "token_handle", "user_id", "code_hash", "expires_at",
                "attempts", "used_at", "created_at"
           FROM "connect_codes"
          WHERE "token_handle" = ?1 AND "used_at" IS NULL
          ORDER BY "created_at" DESC LIMIT 1`,
      ).bind(tokenHandle).first<Record<string, unknown>>();
      if (!row) return null;
      return {
        id: String(row.id),
        token_handle: String(row.token_handle),
        user_id: String(row.user_id) as OwnerId,
        code_hash: String(row.code_hash),
        expires_at: Number(row.expires_at),
        attempts: Number(row.attempts ?? 0),
        used_at: row.used_at === null || row.used_at === undefined ? null : Number(row.used_at),
        created_at: Number(row.created_at),
      };
    },

    async window(tokenHandle: string, user: OwnerId, since: number): Promise<CodeWindow> {
      const row = await db.prepare(
        `SELECT
           (SELECT COUNT(*) FROM "connect_codes" WHERE "token_handle" = ?1) AS for_link,
           (SELECT COUNT(*) FROM "connect_codes"
             WHERE "user_id" = ?2 AND "created_at" >= ?3) AS for_owner,
           (SELECT MAX("created_at") FROM "connect_codes"
             WHERE "token_handle" = ?1) AS newest_for_link`,
      ).bind(tokenHandle, user, since).first<Record<string, unknown>>();
      const newest = row?.newest_for_link;
      return {
        forLink: Number(row?.for_link ?? 0),
        forOwner: Number(row?.for_owner ?? 0),
        newestForLink: newest === null || newest === undefined ? null : Number(newest),
      };
    },

    async insert(row: StoredConnectCode): Promise<void> {
      // ONE BATCH. The spend of the previous codes and the insert of the new
      // one are one transaction, so the link is never briefly codeless and
      // never briefly holds two live codes.
      await db.batch([
        db.prepare(
          `UPDATE "connect_codes" SET "used_at" = ?1
            WHERE "token_handle" = ?2 AND "used_at" IS NULL`,
        ).bind(row.created_at, row.token_handle),
        db.prepare(
          `INSERT INTO "connect_codes"
             ("id","token_handle","user_id","code_hash","expires_at","attempts","used_at","created_at")
           VALUES (?1,?2,?3,?4,?5,0,NULL,?6)`,
        ).bind(row.id, row.token_handle, row.user_id, row.code_hash,
               row.expires_at, row.created_at),
      ]);
    },

    async charge(id: string, from: number, to: number): Promise<boolean> {
      const r = await db.prepare(
        `UPDATE "connect_codes" SET "attempts" = ?1
          WHERE "id" = ?2 AND "used_at" IS NULL AND "attempts" = ?3`,
      ).bind(to, id, from).run();
      return (r?.meta?.changes ?? 0) === 1;
    },

    async spend(id: string, at: number): Promise<boolean> {
      const r = await db.prepare(
        `UPDATE "connect_codes" SET "used_at" = ?1 WHERE "id" = ?2 AND "used_at" IS NULL`,
      ).bind(at, id).run();
      return (r?.meta?.changes ?? 0) === 1;
    },
  };
}

/**
 * An in-memory store with the SAME atomicity rule: `charge` and `spend` run
 * their check and their write with no `await` between them, so on one event
 * loop they cannot interleave. A fake that read, awaited, then wrote would let
 * every concurrent guess win and a suite using it would call a deleted ceiling
 * a pass.
 */
export function createMemoryConnectCodeStore(): ConnectCodeStore & {
  rows: Map<string, StoredConnectCode>;
} {
  const rows = new Map<string, StoredConnectCode>();
  return {
    rows,
    async newest(tokenHandle: string): Promise<StoredConnectCode | null> {
      let best: StoredConnectCode | null = null;
      for (const r of rows.values()) {
        if (r.token_handle !== tokenHandle || r.used_at !== null) continue;
        if (!best || r.created_at > best.created_at) best = r;
      }
      return best ? { ...best } : null;
    },
    async window(tokenHandle: string, user: OwnerId, since: number): Promise<CodeWindow> {
      let forLink = 0, forOwner = 0, newestForLink: number | null = null;
      for (const r of rows.values()) {
        if (r.token_handle === tokenHandle) {
          forLink++;
          if (newestForLink === null || r.created_at > newestForLink) newestForLink = r.created_at;
        }
        if (r.user_id === user && r.created_at >= since) forOwner++;
      }
      return { forLink, forOwner, newestForLink };
    },
    async insert(row: StoredConnectCode): Promise<void> {
      for (const [k, r] of rows) {
        if (r.token_handle === row.token_handle && r.used_at === null) {
          rows.set(k, { ...r, used_at: row.created_at });
        }
      }
      rows.set(row.id, { ...row });
    },
    async charge(id: string, from: number, to: number): Promise<boolean> {
      const r = rows.get(id);
      if (!r || r.used_at !== null || r.attempts !== from) return false;
      rows.set(id, { ...r, attempts: to });
      return true;
    },
    async spend(id: string, at: number): Promise<boolean> {
      const r = rows.get(id);
      if (!r || r.used_at !== null) return false;
      rows.set(id, { ...r, used_at: at });
      return true;
    },
  };
}

// ---------------------------------------------------------------------------
// THE WIRING SEAM — the same shape, and the same 503, as connect.ts
// ---------------------------------------------------------------------------

export interface ConnectAuthDeps {
  /** The SAME `connect_links` store connect.ts is wired with. Two stores would
   *  be two answers to "is this link live". */
  links: ConnectLinkStore;
  codes: ConnectCodeStore;
  /**
   * The app's own display name, for the text. NO APP IS HARDCODED: this is the
   * catalog, injected, and it may answer null — a catalog blip must cost the
   * app's name in one sentence, never the whole code.
   */
  toolkitName(slug: string): Promise<string | null>;
  /** Injectable clock. Tests own time; production passes nothing. */
  now?(): number;
  /** Injectable id mint, for the same reason. */
  newId?(): string;
}

export type ConnectAuthWiring = (env: ConnectAuthEnv) => ConnectAuthDeps | null;

let WIRING: ConnectAuthWiring = () => null;
let WIRED = false;

export function installConnectAuthWiring(wiring: ConnectAuthWiring): void {
  WIRING = wiring;
  WIRED = true;
}

/** For a gate leg: can this Worker text a code at all? */
export function connectAuthWiringInstalled(): boolean {
  return WIRED;
}

// ---------------------------------------------------------------------------
// SHAPE CHECKS — structure and transport, never meaning
// ---------------------------------------------------------------------------

/** 15 lowercase alphanumerics, src/pb/wire.ts ID_ALPHABET. */
function isOwnerRowId(raw: unknown): raw is OwnerId {
  return typeof raw === "string" && /^[a-z0-9]{15}$/.test(raw);
}

/** Constant-time equality over the longer of the two, so the answer does not
 *  depend on WHERE the first difference is. Same loop as connect.ts. */
function constantTimeEqual(a: unknown, b: unknown): boolean {
  if (typeof a !== "string" || typeof b !== "string") return false;
  const enc = new TextEncoder();
  const ab = enc.encode(a);
  const bb = enc.encode(b);
  let diff = ab.byteLength ^ bb.byteLength;
  const n = Math.max(ab.byteLength, bb.byteLength);
  for (let i = 0; i < n; i++) diff |= (ab[i] ?? 0) ^ (bb[i] ?? 0);
  return diff === 0;
}

async function sha256Hex(s: string): Promise<string> {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Six digits from a CSPRNG, rejection-sampled so the digits stay uniform.
 *  Verbatim from routes/password_reset.ts — a modulo over the whole byte range
 *  would make 0-5 more likely than 6-9. */
function sixDigits(): string {
  const out: string[] = [];
  while (out.length < CODE_DIGITS) {
    for (const b of crypto.getRandomValues(new Uint8Array(16))) {
      if (b < 250 && out.length < CODE_DIGITS) out.push(String(b % 10));
    }
  }
  return out.join("");
}

/** 15-char ids, the shape D1 already holds. */
function newId(): string {
  const A = "abcdefghijklmnopqrstuvwxyz0123456789";
  return [...crypto.getRandomValues(new Uint8Array(15))].map((b) => A[b % A.length]).join("");
}

const b64u = (bytes: Uint8Array): string =>
  btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

export type ConnectAuthLeg = "offer" | "send" | "check";

export interface ConnectAuthRoute {
  leg: ConnectAuthLeg;
  token: string;
  /** The path segment, so a 405 can name what it wanted. */
  segment: "code" | "verify";
}

/**
 * `/c/{token}/code` and `/c/{token}/verify`, anchored at both ends and
 * restricted to the token alphabet — so `/c/../../x/code` is not a route at
 * all. Returns null for everything else, INCLUDING connect.ts's own three legs,
 * which is what lets the two files share the `/c/` prefix without either one
 * having to know the other's paths.
 */
export function parseConnectAuthPath(pathname: unknown): ConnectAuthRoute | null {
  if (typeof pathname !== "string") return null;
  const m = /^\/c\/([A-Za-z0-9_-]{43})\/(code|verify)$/.exec(pathname);
  if (!m) return null;
  const segment = m[2] as "code" | "verify";
  return { leg: segment === "verify" ? "check" : "offer", token: m[1] as string, segment };
}

/** The token out of any /c/ path, for `connectSession`. It is deliberately the
 *  REQUEST's own token: a code session is honoured only on the link it was
 *  minted for, and that binding is checked against the URL the browser actually
 *  asked for rather than against anything the cookie claims. */
function tokenFromPath(pathname: string): string | null {
  const m = /^\/c\/([A-Za-z0-9_-]{43})(?:\/(?:go|done|code|verify))?$/.exec(pathname);
  return m ? (m[1] as string) : null;
}

// ---------------------------------------------------------------------------
// THE CODE SESSION — an HMAC, not a login
// ---------------------------------------------------------------------------

/**
 * The signing key.
 *
 * FAILS CLOSED ON AN UNSET SECRET, and that is not the same choice
 * src/pb/auth.ts makes. An `owners` token is signed with
 * `ANTICIPY_AUTH_SECRET ‖ tokenKey`, so even an unset secret leaves a
 * per-record random half and forging one still needs that row. This blob has no
 * such half: with the secret unset the key would be a constant anybody reading
 * this file could reproduce, and a forged cookie would name any owner they
 * liked on any link they held. So an unbound secret means NO CODE SESSION
 * EXISTS — the person is told to sign in, which is a working product minus one
 * convenience, rather than a lock anyone can pick.
 */
async function sessionKey(env: ConnectAuthEnv): Promise<CryptoKey | null> {
  const secret = typeof env?.ANTICIPY_AUTH_SECRET === "string"
    ? env.ANTICIPY_AUTH_SECRET.trim() : "";
  if (secret === "") return null;
  return crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret + SESSION_KEY_SALT),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
}

/**
 * The MAC covers the FULL token handle, which is what makes "a code for link A
 * cannot open link B" a property of the signature rather than a comparison
 * somebody could forget to write. The handle is not in the cookie: it is
 * recomputed from the token in the request path, so a cookie presented on
 * another link simply does not verify.
 */
async function sessionMac(
  env: ConnectAuthEnv, owner: string, exp: string, handle: string,
): Promise<string | null> {
  const key = await sessionKey(env);
  if (!key) return null;
  const sig = await crypto.subtle.sign(
    "HMAC", key,
    new TextEncoder().encode(`${SESSION_VERSION}.${owner}.${exp}.${handle}`),
  );
  return b64u(new Uint8Array(sig));
}

/** `1.<owner>.<expiry ms>.<mac>` — FOUR dot-separated fields, deliberately.
 *  src/pb/auth.ts `verifyToken` refuses anything that is not three, so this
 *  value can never be mistaken for an account token even if somebody pasted it
 *  into the `anticipy_session` cookie. */
export async function mintCodeSession(
  env: ConnectAuthEnv, owner: OwnerId, handle: string, expiresAt: number,
): Promise<string | null> {
  if (!isOwnerRowId(owner)) return null;
  const exp = String(Math.floor(expiresAt));
  const mac = await sessionMac(env, owner, exp, handle);
  return mac ? `${SESSION_VERSION}.${owner}.${exp}.${mac}` : null;
}

function sessionCookieName(handle: string): string {
  return SESSION_COOKIE_PREFIX + handle.slice(0, 16);
}

/** One cookie out of the header, by exact name. Split on ";" and compare the
 *  WHOLE name: a substring match would read `evil___Secure-anticipy_c_x` as
 *  ours. Same rule as connect.ts's own reader. */
function cookieByName(request: Request, name: string): string | null {
  const header = request.headers.get("Cookie");
  if (!header) return null;
  for (const part of header.split(";")) {
    const eq = part.indexOf("=");
    if (eq < 0) continue;
    if (part.slice(0, eq).trim() !== name) continue;
    const value = part.slice(eq + 1).trim();
    return value === "" ? null : value;
  }
  return null;
}

/**
 * The code session for THIS request's token, or null.
 *
 * Never throws and never reads the database: a cookie a browser can set must
 * not be able to 500 the page or cost a query. The whole check is a MAC and a
 * clock.
 *
 * WHAT IT CANNOT DO, BY CONSTRUCTION: it cannot be revoked. There is no per-row
 * key mixed in, so a password change does not kill it the way it kills an
 * `owners` token. The bound is its LIFE instead — ten minutes plus the callback
 * window, stamped into the signed blob at mint time — and its REACH: one link,
 * whose every leg re-checks the link for itself.
 */
async function codeSessionOwner(
  request: Request, env: ConnectAuthEnv, token: string, now: number,
): Promise<OwnerId | null> {
  try {
    const handle = await tokenHandle(token);
    const raw = cookieByName(request, sessionCookieName(handle));
    if (!raw) return null;
    const parts = raw.split(".");
    if (parts.length !== 4) return null;
    const [version, owner, exp, mac] = parts as [string, string, string, string];
    if (version !== SESSION_VERSION) return null;
    if (!isOwnerRowId(owner)) return null;
    const want = await sessionMac(env, owner, exp, handle);
    // No key (no secret bound) means no session, not a session that verifies
    // against `null`.
    if (want === null || !constantTimeEqual(mac, want)) return null;
    const until = Number(exp);
    if (!Number.isFinite(until) || now >= until) return null;
    return owner as OwnerId;
  } catch {
    return null;
  }
}

/**
 * WHO IS THIS BROWSER, for a /c/ page — the function connect.ts's three legs
 * call instead of `whoIsSignedIn`.
 *
 * THE SIGNED-IN SESSION WINS OUTRIGHT, and is checked first. If the phone's own
 * account token is present it is the answer even when it names a DIFFERENT
 * owner than a code session would: a household sharing a laptop has to be told
 * "you're signed in as someone else" rather than have a stale code cookie
 * quietly promote them into somebody else's link. A code session is the
 * fallback for the browser that has no session at all, which is the case this
 * whole file exists for.
 *
 * The token is taken from the REQUEST PATH, so a cookie can only ever answer
 * for the link the browser is actually on.
 */
export async function connectSession(
  request: Request, env: ConnectAuthEnv, now: number = Date.now(),
): Promise<OwnerId | null> {
  const signedIn = await whoIsSignedIn(request, env);
  if (signedIn) return signedIn;
  let token: string | null = null;
  try {
    token = tokenFromPath(new URL(request.url).pathname);
  } catch {
    return null;
  }
  if (!token) return null;
  return await codeSessionOwner(request, env, token, now);
}

// ---------------------------------------------------------------------------
// THE PAGES — same shell, same headers, same CSP as connect.ts
// ---------------------------------------------------------------------------

const esc = (raw: unknown): string =>
  String(raw ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

/**
 * DUPLICATED FROM connect.ts ON PURPOSE, and it is the same duplication that
 * file declares about its own pure core: `page`, `plainPage` and `esc` are not
 * exported there, and a person moving between /c/{token} and /c/{token}/code
 * must not watch the page change shape. When connect.ts exports its shell, THIS
 * FUNCTION IS DELETED AND IMPORTED — the headers below are the contract, not
 * the code.
 *
 *   Cache-Control: no-store   a code page left in a shared browser's cache is
 *                             the account screen handed to the next person.
 *   CSP default-src 'none'    no scripts, from anywhere, ever. form-action
 *                             'self' keeps the code pointed at us;
 *                             frame-ancestors 'none' is the clickjacking answer.
 *   Referrer-Policy           no-referrer, so our token does not travel.
 *   X-Robots-Tag              never indexed.
 */
function page(status: number, title: string, bodyHtml: string,
              extra: Record<string, string> = {}): Response {
  const html = `<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)}</title>
<style>
  :root { color-scheme: light dark; }
  body { margin: 0 auto; padding: 2rem 1.25rem; max-width: 30rem;
         font: 1rem/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; }
  h1 { font-size: 1.4rem; line-height: 1.25; margin: 0 0 .75rem; }
  p.fine { opacity: .7; font-size: .9rem; }
  p.wrong { font-weight: 600; }
  input { font: inherit; padding: .85rem 1rem; width: 100%; box-sizing: border-box;
          border-radius: 12px; border: 1px solid; letter-spacing: .35em; }
  button { font: inherit; font-weight: 600; padding: .85rem 1.25rem; width: 100%;
           border: 0; border-radius: 12px; cursor: pointer; margin-top: 1rem; }
  a.later { display: inline-block; margin-top: 1rem; }
</style>
${bodyHtml}
</html>`;
  return new Response(html, {
    status,
    headers: {
      ...extra,
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
      "referrer-policy": "no-referrer",
      "x-content-type-options": "nosniff",
      "x-frame-options": "DENY",
      "x-robots-tag": "noindex, nofollow",
      "content-security-policy":
        "default-src 'none'; img-src https:; style-src 'unsafe-inline'; "
        + "form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
    },
  });
}

function plainPage(status: number, heading: string, sentence: string): Response {
  return page(status, heading, `<body>
<h1>${esc(heading)}</h1>
<p>${esc(sentence)}</p>
</body>`);
}

/** The offer. It names NOTHING — not the app, not the owner, not whether the
 *  link is real — because it is drawn before anybody has proved anything, and
 *  it is drawn without touching the store for the same reason. */
function askPage(token: string): Response {
  return page(200, ASK_HEADING, `<body>
<h1>${esc(ASK_HEADING)}</h1>
<p>${esc(ASK_LINE)}</p>
<form method="post" action="/c/${esc(token)}/code">
  <button type="submit">${esc(ASK_BUTTON)}</button>
</form>
<p class="fine">${esc(OPTIONAL_LINE)}</p>
<a class="later" href="https://anticipy.ai/">Skip for now</a>
</body>`);
}

/**
 * The one answer `POST /c/{token}/code` gives, and the page a wrong code comes
 * back to. Every byte of it is the same for every token; only `wrong` changes,
 * and `wrong` is about the CODE the caller just typed, never about the token.
 */
function enterCodePage(token: string, wrong: boolean): Response {
  return page(wrong ? 400 : 200, SENT_HEADING, `<body>
<h1>${esc(SENT_HEADING)}</h1>
${wrong ? `<p class="wrong">${esc(NOPE_LINE)}</p>\n` : ""}<p>${esc(SENT_LINE)}</p>
<form method="post" action="/c/${esc(token)}/verify">
  <input type="text" name="code" inputmode="numeric" autocomplete="one-time-code"
         maxlength="6" pattern="[0-9]*" aria-label="6-digit code" autofocus>
  <button type="submit">${esc(SENT_BUTTON)}</button>
</form>
<p class="fine">Didn't get one? <a href="/c/${esc(token)}/code">Ask for another</a>. ${esc(OPTIONAL_LINE)}</p>
</body>`);
}

// ---------------------------------------------------------------------------
// REQUEST PLUMBING
// ---------------------------------------------------------------------------

/**
 * Is this POST from our own page?
 *
 * Same rule, same polarity as connect.ts: a `Sec-Fetch-Site: cross-site`, or an
 * `Origin` naming another site, is refused; ABSENT headers are allowed, because
 * a header that is not sent is not evidence of anything and refusing on absence
 * turns a client quirk into "connecting is broken for that person". Here it
 * stops a hidden form on any site from making somebody's phone buzz.
 */
function isCrossSitePost(request: Request): boolean {
  const site = request.headers.get("Sec-Fetch-Site");
  if (site && site.toLowerCase() === "cross-site") return true;
  const origin = request.headers.get("Origin");
  if (!origin || origin === "null") return false;
  try {
    return new URL(origin).origin !== new URL(request.url).origin;
  } catch {
    return true;
  }
}

/** One field out of a form post. Never throws: a body that is not a form is
 *  simply no field, and a POST with no code is a wrong code, not a 500. */
async function formField(request: Request, name: string): Promise<string> {
  const ct = request.headers.get("content-type") ?? "";
  if (!ct.includes("application/x-www-form-urlencoded") && !ct.includes("multipart/form-data")) {
    return "";
  }
  try {
    const form = await request.formData();
    const v = form.get(name);
    return typeof v === "string" ? v.trim() : "";
  } catch {
    return "";
  }
}

/** What a log line may say about a link: the first 12 hex of its handle. Never
 *  the token, never the code, never the phone. */
const fingerprint = (handle: string): string => `link:${handle.slice(0, 12)}`;

/**
 * The phone the code goes to.
 *
 * THE SAME RULE AS routes/password_reset.ts `phoneFor`, and it is copied rather
 * than imported because that function is not exported and that file is not this
 * change's to edit — extracting one shared helper is owed and is named in the
 * hand-off. Getting it wrong is not cosmetic: once a profile row exists it is
 * canonical INCLUDING an explicit empty phone, and falling back from that empty
 * to `owners.phone` would silently re-affiliate the immutable sign-up number
 * after the person removed it. Only an account with no profile row at all may
 * use the sign-up seed.
 */
async function phoneFor(db: D1Database, ownerId: string): Promise<string> {
  const owner = await db
    .prepare(`SELECT phone FROM owners WHERE id = ? LIMIT 1`)
    .bind(ownerId).first<{ phone: string | null }>();
  if (!owner) return "";
  const profile = await db
    .prepare(`SELECT phone FROM owner_profile WHERE owner_ref = ? ORDER BY updated DESC LIMIT 1`)
    .bind(ownerId).first<{ phone: string | null }>();
  if (profile) return String(profile.phone ?? "").trim();
  return String(owner.phone ?? "").trim();
}

// ---------------------------------------------------------------------------
// THE ROUTES
// ---------------------------------------------------------------------------

/**
 * The entry point index.ts registers, IN FRONT OF `connectRoute`.
 *
 * It answers `null` for every path that is not one of its two, including
 * connect.ts's own three legs, so the dispatch is two lines:
 *
 *     if (path.startsWith("/c/")) {
 *       const answered = await connectAuthRoute(request, env);
 *       if (answered) return answered;
 *       return connectRoute(request, env);
 *     }
 *
 * `deps` is injectable so the suite can drive the real handlers with stores it
 * controls; production passes nothing and gets the installed wiring.
 */
export async function connectAuthRoute(
  request: Request, env: ConnectAuthEnv, deps?: ConnectAuthDeps,
): Promise<Response | null> {
  let route: ConnectAuthRoute | null;
  try {
    route = parseConnectAuthPath(new URL(request.url).pathname);
  } catch {
    return null;
  }
  if (!route) return null;

  const method = request.method === "HEAD" ? "GET" : request.method;
  // GET draws the offer; POST does the thing. `/verify` has no GET at all: a
  // link prefetcher, an <img> or an address-bar preload must never be able to
  // spend a guess out of somebody's ceiling of five.
  const allow = route.segment === "code" ? "GET, POST" : "POST";
  if (method !== "POST" && !(method === "GET" && route.segment === "code")) {
    return new Response(null, { status: 405, headers: { allow, "cache-control": "no-store" } });
  }

  const wired = deps ?? WIRING(env);
  if (!wired) {
    console.log(`connect ${route.segment}: 503 — no connect-auth wiring installed on this `
      + "Worker; the link store, the code store and the catalog are all unset, so no code "
      + "can be sent. See installConnectAuthWiring().");
    return plainPage(503, UNWIRED_HEADING, UNWIRED_LINE);
  }

  if (method === "GET") return askPage(route.token);

  // Before anything is read and long before anything is sent.
  if (isCrossSitePost(request)) {
    return plainPage(403, CROSS_SITE_HEADING, CROSS_SITE_LINE);
  }

  const now = wired.now ? wired.now() : Date.now();
  if (route.segment === "code") return await handleSend(request, env, wired, route.token, now);
  return await handleCheck(request, env, wired, route.token, now);
}

/**
 * POST /c/{token}/code — text a code.
 *
 * ONE ANSWER. `enterCodePage(token, false)` is returned on every path out of
 * this function: a live link, a dead one, a spent one, an invented one, an
 * owner with no phone, a provider that refused, a database that could not be
 * read. Any difference — a status, a word, a redirect — is the string-sorter
 * connect.ts closed on its own legs, reopened here.
 *
 * The handle is computed and the store is asked for EVERY caller, so the shape
 * of the work is the same for a real token and an invented one; what cannot be
 * equalised is the send itself, and the header of this file writes down exactly
 * what that is worth.
 */
async function handleSend(
  request: Request, env: ConnectAuthEnv, deps: ConnectAuthDeps, token: string, now: number,
): Promise<Response> {
  try {
    await mintAndSend(env, deps, token, now);
  } catch (err) {
    // Swallowed on purpose, and logged where an operator sees it. A thrown
    // catalog, a missing `connect_codes` table or a refused D1 must not be
    // readable off the reply — but they must not be invisible either, which is
    // what `connectCodesTableReady` is for.
    console.log(`connect code: send path failed — ${(err as Error)?.message ?? "unknown"}`);
  }
  return enterCodePage(token, false);
}

async function mintAndSend(
  env: ConnectAuthEnv, deps: ConnectAuthDeps, token: string, now: number,
): Promise<void> {
  const handle = await tokenHandle(token);
  const row: StoredLink | null = await deps.links.read(handle);
  if (!row) return;
  // The row a store hands back is whatever its query matched. Same reason
  // connect.ts checks it: a COLLATE NOCASE column, a stray LIKE or a cache
  // returning a near neighbour all produce a row for a link nobody asked about,
  // and this one decides whose phone rings.
  if (!constantTimeEqual(handle, row.token_handle)) return;
  if (!isOwnerRowId(row.user_id)) return;
  // A DEAD LINK GETS NO CODE. Not because the code would be useless — because a
  // link that expired an hour ago must not still be able to text somebody.
  if (now >= row.expires_at) return;
  // A SPENT LINK GETS NO NEW CODE either. Everything before the tap is over,
  // and the only leg left (`/done`) belongs to the browser that already holds
  // the session it was given.
  if (row.used_at !== null) return;

  const phone = await phoneFor(env.DB, row.user_id);
  if (!phone) return;

  const w = await deps.codes.window(handle, row.user_id, now - OWNER_WINDOW_MS);
  if (w.newestForLink !== null && now - w.newestForLink < MIN_GAP_MS) return;
  if (w.forLink >= MAX_CODES_PER_LINK) return;
  if (w.forOwner >= MAX_CODES_PER_OWNER) return;

  // The catalog is asked for a NAME and nothing else, and a failure costs the
  // name rather than the code.
  let app: string | null = null;
  try {
    app = await deps.toolkitName(row.toolkit);
  } catch {
    app = null;
  }

  const code = sixDigits();
  // SEND FIRST, exactly as password_reset.ts does it: if the text cannot leave
  // the building, do not leave a live code in the database pretending it did.
  // `sendText` never throws — a hung or refused provider is `ok: false`.
  const sent = await sendText(env, phone, connectCodeText(code, app), { tag: "connect code" });
  if (!sent.ok) {
    console.log(`connect code: ${fingerprint(handle)} not sent (${sent.provider}/${sent.error})`);
    return;
  }

  await deps.codes.insert({
    id: deps.newId ? deps.newId() : newId(),
    token_handle: handle,
    user_id: row.user_id,
    code_hash: await sha256Hex(code),
    expires_at: now + CODE_TTL_MS,
    attempts: 0,
    used_at: null,
    created_at: now,
  });
  console.log(`connect code: ${fingerprint(handle)} texted`);
}

/**
 * POST /c/{token}/verify — spend a code, mint a session.
 *
 * ONE REFUSAL. A wrong code, an expired one, one that was already used, one
 * that belongs to a different link, a link that vanished, a caller past the
 * ceiling and an empty box all come back as the same page with the same
 * sentence and the same 400.
 *
 * THE ORDER IS THE SECURITY.
 *  1. The ceiling is CHARGED BEFORE THE CODE IS COMPARED. Charging after a
 *     failed compare would be identical for a guesser and free for a typo — but
 *     charging only on the compare's own path means any code that throws on the
 *     way (a store blip, a malformed row) costs nothing, and a walk that
 *     provokes one is a walk with no ceiling. It is charged first and the
 *     charge is a compare-and-set, so five is five even under a race.
 *  2. The code is spent BEFORE the session is minted, and the mint only happens
 *     if the spend won. Two browsers racing the same code get one session.
 *  3. The OWNER comes from the LINK ROW, re-read here, never from the code row
 *     alone and never from anything on the request. A session naming an owner a
 *     request chose is the wrong-person failure with a form field.
 */
async function handleCheck(
  request: Request, env: ConnectAuthEnv, deps: ConnectAuthDeps, token: string, now: number,
): Promise<Response> {
  const typed = await formField(request, "code");
  let cookie: string | null = null;
  try {
    cookie = await checkCode(env, deps, token, typed, now);
  } catch (err) {
    console.log(`connect check: failed — ${(err as Error)?.message ?? "unknown"}`);
    cookie = null;
  }
  if (!cookie) return enterCodePage(token, true);

  // 303 back to the page itself. The browser re-requests /c/{token} carrying
  // the new cookie, and connect.ts draws the consent page it could not draw a
  // moment ago. An empty body, so nothing about the session is rendered
  // anywhere.
  return new Response(null, {
    status: 303,
    headers: {
      location: `/c/${token}`,
      "set-cookie": cookie,
      "cache-control": "no-store",
      "referrer-policy": "no-referrer",
    },
  });
}

/** The whole check, returning the Set-Cookie value or null. Separated so the
 *  route above has exactly one refusal and cannot grow a second. */
async function checkCode(
  env: ConnectAuthEnv, deps: ConnectAuthDeps, token: string, typed: string, now: number,
): Promise<string | null> {
  const handle = await tokenHandle(token);
  const rec = await deps.codes.newest(handle);
  if (!rec) return null;
  if (!constantTimeEqual(rec.token_handle, handle)) return null;
  if (now >= rec.expires_at) return null;
  if (rec.attempts >= MAX_ATTEMPTS) return null;

  // THE CEILING, charged first and atomically. A loser in a race is refused
  // rather than retried.
  if (!(await deps.codes.charge(rec.id, rec.attempts, rec.attempts + 1))) return null;

  // Constant-time over the HASHES. Only a SHA-256 is ever stored, so a dump of
  // the table is useless, and the compare cannot be walked a character at a
  // time.
  if (!constantTimeEqual(await sha256Hex(typed), rec.code_hash)) return null;

  // SINGLE USE. Exactly one caller wins.
  if (!(await deps.codes.spend(rec.id, now))) return null;

  // The link, re-read now that a code has been proved. The session's owner and
  // its life both come from here.
  const row = await deps.links.read(handle);
  if (!row) return null;
  if (!constantTimeEqual(row.token_handle, handle)) return null;
  if (!isOwnerRowId(row.user_id)) return null;
  // A SPENT LINK MINTS NO NEW SESSION. Everything before the tap is finished,
  // and the one leg that is left (`/done`) belongs to the browser that already
  // holds the cookie it was handed — that cookie outlives the tap on purpose,
  // see CODE_SESSION_GRACE_MS. What this refuses is the other story: somebody
  // who picked the link up AFTER the owner used it, walking back in through the
  // code door. The cost is that a browser which lost its cookie mid-flow cannot
  // re-enter and the owner asks for a new link; the alternative is a spent link
  // that is still an account door for an hour.
  if (row.used_at !== null) return null;
  // The code was minted from this link; if the two disagree the row moved under
  // us and nobody gets a session out of it.
  if (!constantTimeEqual(row.user_id, rec.user_id)) return null;

  // The last instant any leg of this link can still act. See
  // CODE_SESSION_GRACE_MS for why it is not the link's ten minutes.
  const until = row.expires_at + CODE_SESSION_GRACE_MS;
  if (now >= until) return null;

  const value = await mintCodeSession(env, row.user_id, handle, until);
  if (!value) {
    console.log(`connect check: ${fingerprint(handle)} proved, but ANTICIPY_AUTH_SECRET is `
      + "unset — no code session can be signed, so the page will keep asking for a sign-in");
    return null;
  }

  // Path is the whole point: this cookie is sent to /c/{token} and its legs and
  // to nothing else in the product — not /api/collections, not /agent, not the
  // site. SameSite=Lax rather than Strict because the VENDOR redirects the
  // browser back to /c/{token}/done and Strict would withhold the cookie on
  // exactly the hop that has to work. HttpOnly so no script can read it, and
  // there are no scripts on these pages at all.
  const maxAge = Math.max(1, Math.floor((until - now) / 1000));
  console.log(`connect check: ${fingerprint(handle)} opened by phone code`);
  return `${sessionCookieName(handle)}=${value}; Path=/c/${token}; Max-Age=${maxAge}; `
    + "HttpOnly; Secure; SameSite=Lax";
}
