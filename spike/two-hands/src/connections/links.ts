// OUR CONNECT LINK — the anticipy.ai/c/{token} half of connecting an app.
//
// WHY THIS FILE EXISTS, MEASURED. On 2026-09-05 four Composio connect links
// were generated and handed to a person to tap later. Composio's own links live
// ten minutes. All four were dead before they were tapped
// (research/2026-09-05-composio-connections.md, item 3). So the VENDOR link is
// minted at redeem time — the instant a finger touches the glass — and what we
// put in a text is our own token instead. `mint()` here never calls the
// provider; `connectPageGo()` is the only function in this module that does,
// and `test/connections_links.test.ts` pins that fact rather than trusting it.
//
// Our token also carries three things the vendor's link does not:
//   SINGLE USE  one redeem, decided by a compare-and-set at the store, never by
//               a read the caller then acts on.
//   BOUND       to one owner ROW ID and one toolkit, fixed at mint time.
//   SHORT       LINK_TTL_MS, dead at the instant it expires.
//
// THE FAILURE THIS MODULE IS AIMED AT. A text message is not private and is not
// phishing-resistant: it lives in a notification shade, in a synced Messages
// database and in a carrier log. If a link alone were enough to bind an
// account, whoever read the text over a shoulder could attach THEIR mailbox to
// somebody else's Anticipy, or attach the owner's mailbox to their own. That is
// the failure connections/contract.ts opens with — one operator's Gmail serving
// everybody — reached from the other end. So redeeming requires the signed-in
// session to BE the owner the token was minted for, and a caller who has not
// proved they are anybody is told NOTHING: not the toolkit, not the owner, not
// whether the token was ever real.
//
// That last clause was written before it was true. Until 2026-09-05 a signed-out
// request could sort strings into "a real Anticipy token" and "not one" — a live
// token answered `sign-in-required` and an invented one answered `expired` — so
// the routes confirmed an intercepted text was worth keeping, to a caller who
// had proved nothing. `locate` now settles the session BEFORE it looks anything
// up, which collapses unknown, expired, used and not-yours into one answer for
// an anonymous caller and takes the row lookup (and its round trip, which is the
// same oracle read off a stopwatch) out of the anonymous path entirely.
//
// HARNESS-LAWS LAW 1. Nothing here decides what a person MEANT. Which app
// somebody wants is a model's answer (contract.ts `ToolkitJudge`) and arrives
// as an argument. This file hashes bytes, compares timestamps, parses a token
// out of a path, and compares one vendor status field against one configured
// literal. All four are plumbing, and none of them reads a human sentence. If a
// list of app names ever appears below, this module has become the thing the
// law forbids — the behavioural pin is the "any slug, no code" test in the
// suite, which runs the whole flow on two invented toolkits.

import { Buffer } from "node:buffer";
import { createHash, randomBytes, timingSafeEqual } from "node:crypto";
import {
  LINK_TTL_MS,
  type AccountAlias,
  type ConnectLink,
  type Connection,
  type ConnectionProvider,
  type OwnerId,
  type PermissionWords,
  type Toolkit,
  type ToolkitMeta,
  ownerId,
} from "./contract.ts";

// ---------------------------------------------------------------------------
// CONSTANTS
// ---------------------------------------------------------------------------

/** Our origin, never the vendor's. The spec's rule is one line: "Never the raw
 *  Composio or Google URL in a text." */
export const CONNECT_URL_BASE = "https://anticipy.ai/c";

/** 32 bytes = 256 bits of `crypto.randomBytes`. The token is the ONLY secret in
 *  the flow, so it is sized for a world where someone is guessing at it. */
export const TOKEN_BYTES = 32;

/** 32 bytes of base64url, unpadded: ceil(32 * 4 / 3) = 43 characters. Written
 *  down because the route parser and the well-formedness guard both depend on
 *  it, and a token that is 44 characters long means somebody re-encoded it. */
export const TOKEN_CHARS = 43;

/** How long the CALLBACK may take, measured from the moment the link was
 *  claimed — deliberately NOT LINK_TTL_MS.
 *
 *  LINK_TTL_MS answers "how long may an UNTAPPED link sit in a text". The
 *  vendor round trip is a different question and a much slower one: a password
 *  manager, a 2FA push, a workspace picker, an account-chooser page, and in the
 *  Notion case a login the person did not have. Ten minutes there is routinely
 *  not enough, and expiring the callback would throw away a connection the
 *  person actually completed — the account exists at the vendor and Anticipy
 *  would have no row for it. Composio has no success webhook (only `expired`),
 *  so this callback is the ONLY signal; if it is refused, the connection is
 *  lost silently. */
export const CALLBACK_WINDOW_MS = 60 * 60 * 1000;

/** The one literal the callback's `status` may carry and still be believed.
 *  Overridable per call, because it is the vendor's spelling and not ours.
 *  Anything else — including a missing status — is not-connected: recording a
 *  connection is the privilege here, so it needs positive evidence rather than
 *  the absence of an objection (HARNESS-LAWS law 1, the FLOOR polarity). */
export const CALLBACK_SUCCESS = "success";

// ---------------------------------------------------------------------------
// TOKEN PLUMBING
// ---------------------------------------------------------------------------

/** Shape only. A token is 43 url-safe base64 characters; anything else never
 *  reaches the store.
 *
 *  This regex decides nothing about MEANING — it is the same class of check as
 *  parsing a port out of a URL. It matters for one concrete reason: the value
 *  arrives from a path segment an attacker controls, and everything downstream
 *  (the hash, the store key) is safer when the input has a fixed alphabet and a
 *  fixed length. */
function isWellFormedToken(token: unknown): token is string {
  return typeof token === "string" && /^[A-Za-z0-9_-]{43}$/.test(token);
}

/**
 * The store key: sha256 of the token, hex.
 *
 * WHY THE STORE NEVER HOLDS THE TOKEN. `connect_links` is a D1 table; D1 rows
 * end up in backups, in `wrangler d1 execute` output, and in whatever a future
 * debugging session pastes into a terminal. A raw single-use bearer token at
 * rest means a database read is a live link for every owner who has one
 * outstanding — which is exactly the "a link alone must never be enough" rule,
 * failed at the other end. A handle is not a link: it cannot be redeemed,
 * because redeeming hashes what the caller presented and compares.
 *
 * It also means untrusted input never reaches the query. Whatever a person puts
 * in the path, the value handed to the store is 64 hex characters — no quote,
 * no `%`, no case-folding trick.
 */
export function tokenHandle(token: string): string {
  return createHash("sha256").update(token, "utf8").digest("hex");
}

/**
 * What a log line is allowed to say about a token: the first 12 hex characters
 * of its handle. Enough to correlate two lines about the same link, useless for
 * redeeming one, and irreversible.
 *
 * NEVER log the token itself. A support transcript, a Sentry breadcrumb or a
 * Worker tail with a whole token in it hands the reader an account binding.
 */
export function tokenFingerprint(token: string): string {
  if (typeof token !== "string" || token === "") return "link:none";
  return `link:${tokenHandle(token).slice(0, 12)}`;
}

/**
 * Constant-time equality for two ASCII strings of the same expected length.
 *
 * `timingSafeEqual` throws on a length mismatch, so the length is compared
 * first and a mismatch is simply false — for the two uses here (a 64-character
 * handle, a 15-character owner id) the lengths are structurally fixed, so the
 * early return leaks nothing an attacker did not already supply.
 *
 * Looking up a row BY handle makes this compare look redundant. It is not: the
 * store is an interface and week 2 puts it on D1, where the row that comes back
 * is whatever the query matched — a `COLLATE NOCASE` column, a `LIKE`, a
 * trimmed key or a cache that returns a near neighbour all produce a row whose
 * handle is not the one asked for. This is the line that refuses it.
 */
function constantTimeEqual(a: string, b: string): boolean {
  if (typeof a !== "string" || typeof b !== "string") return false;
  if (a.length !== b.length) return false;
  const ab = Buffer.from(a, "utf8");
  const bb = Buffer.from(b, "utf8");
  if (ab.length !== bb.length) return false;
  return timingSafeEqual(ab, bb);
}

/** Our link, per the spec: `anticipy.ai/c/{token}`. */
export function connectUrl(token: string, base: string = CONNECT_URL_BASE): string {
  return `${base.replace(/\/+$/, "")}/${token}`;
}

/** Where the vendor sends the browser back. The token is on it because the
 *  callback is the only success signal Composio offers, and by then the token
 *  is already spent — `connectPageGo` claims it BEFORE the vendor ever sees it,
 *  so a copy of this URL in a vendor log or a Referer header cannot start a
 *  connection, only finish the one it belongs to, and only in the owner's own
 *  signed-in session. */
export function callbackUrl(token: string, base: string = CONNECT_URL_BASE): string {
  return `${connectUrl(token, base)}/done`;
}

/** The three page routes, as a path parse. HTTP lives in the Worker; these are
 *  the pure halves it calls. */
export type ConnectLeg = "view" | "go" | "done";

export interface ConnectRoute {
  leg: ConnectLeg;
  token: string;
}

/**
 * `/c/{token}` → view, `/c/{token}/go` → go, `/c/{token}/done` → done.
 *
 * Anchored at both ends and restricted to the token alphabet, so `/c/../../x`
 * and a token with a slash in it are not routes at all. Returns null rather
 * than throwing: an unroutable path is a 404, not a 500.
 */
export function parseConnectPath(pathname: unknown): ConnectRoute | null {
  if (typeof pathname !== "string") return null;
  const m = /^\/c\/([A-Za-z0-9_-]{43})(?:\/(go|done))?$/.exec(pathname);
  if (!m) return null;
  const leg: ConnectLeg = m[2] === "go" ? "go" : m[2] === "done" ? "done" : "view";
  return { leg, token: m[1] as string };
}

// ---------------------------------------------------------------------------
// THE STORE SEAM
// ---------------------------------------------------------------------------

/**
 * The `connect_links` row as it is actually persisted.
 *
 * Two deliberate differences from the contract's `ConnectLink`, both flagged in
 * this module's return value to the caller who commissioned it:
 *
 *   `token_handle` REPLACES `token`. See `tokenHandle` for why the raw token is
 *   never written down. `ConnectLink.token` is still what callers get back,
 *   because the raw token is the thing they already hold.
 *
 *   `completed_at` is new. Without it the callback cannot be exactly-once, and
 *   a refresh of the done page would record the same connection twice.
 */
export interface StoredLink {
  token_handle: string;
  user_id: OwnerId;
  toolkit: Toolkit;
  alias: AccountAlias | null;
  expires_at: number;
  used_at: number | null;
  completed_at: number | null;
}

/** The result of a compare-and-set. `won` is true for exactly one caller. */
export interface ClaimOutcome {
  won: boolean;
  /** The row as it stands after the attempt, or null if there is no such row.
   *  Never the raw token — there is none stored. */
  row: StoredLink | null;
}

/**
 * Behind an interface so week 2 can put it on D1 without touching this file.
 *
 * `claim` and `complete` are the whole reason this is an interface rather than
 * a Map: they are the two atomic writes, and their D1 spellings are written on
 * each method. Anything that implements this by reading a row, deciding in
 * JavaScript, and writing it back is not an implementation of this interface —
 * it is the double-redeem bug with extra steps.
 */
export interface ConnectLinkStore {
  /** Insert. MUST reject a handle that already exists rather than overwrite:
   *  an overwrite would silently re-bind a live link to a different owner. */
  put(row: StoredLink): Promise<void>;
  read(handle: string): Promise<StoredLink | null>;
  /** THE SINGLE-USE GATE. One statement, no read-then-write:
   *    UPDATE connect_links SET used_at = ?1
   *     WHERE token_handle = ?2 AND used_at IS NULL
   *  and `won = (changes === 1)`. */
  claim(handle: string, usedAt: number): Promise<ClaimOutcome>;
  /** THE EXACTLY-ONCE GATE for the callback, same shape:
   *    UPDATE connect_links SET completed_at = ?1
   *     WHERE token_handle = ?2 AND completed_at IS NULL
   *
   *  Read this as taking a LEASE, not as filing a receipt: it says "I am the
   *  one who will write this connection", and `release` below gives it back if
   *  the write does not happen. */
  complete(handle: string, completedAt: number): Promise<ClaimOutcome>;
  /**
   * GIVE THE LEASE BACK when the write it was taken for failed. Conditional,
   * like every other write here, so a stale caller cannot re-open the
   * exactly-once window under a connection somebody else has already recorded:
   *    UPDATE connect_links SET completed_at = NULL
   *     WHERE token_handle = ?1 AND completed_at = ?2
   *
   * WHY IT EXISTS. `complete` used to be burned before `onConnected`, so one
   * failed write left the token completed with no row anywhere: the page said
   * "connected" on every refresh, the account existed at the vendor, and
   * Composio publishes no success webhook — nothing would ever mention it
   * again. Permanent, silent data loss, one `throw` away at all times.
   */
  release(handle: string, completedAt: number): Promise<ClaimOutcome>;
}

/**
 * The week-1 store. In memory, no dependencies, no network.
 *
 * ATOMICITY, PRECISELY. Both compare-and-sets below have NO `await` between the
 * read and the write. An async function body runs synchronously until its first
 * await, so on one event loop the check and the set cannot be interleaved by
 * another redeem. That is what "atomic-ish" means here, and it is the exact
 * property D1's single-statement UPDATE gives for real.
 *
 * Rows go in and come out as copies. A caller that mutated a row it was handed
 * would otherwise be editing the database — and the row it is most likely to
 * mutate is `used_at`, which is the one field the whole module refuses to
 * decide anywhere but here.
 */
export class MemoryConnectLinkStore implements ConnectLinkStore {
  #rows = new Map<string, StoredLink>();

  async put(row: StoredLink): Promise<void> {
    if (this.#rows.has(row.token_handle)) {
      // 256 bits do not collide; a duplicate handle means the same token was
      // minted twice, and overwriting would re-bind a link somebody is holding.
      throw new Error(`connect link already exists: ${row.token_handle.slice(0, 12)}`);
    }
    this.#rows.set(row.token_handle, { ...row });
  }

  async read(handle: string): Promise<StoredLink | null> {
    const row = this.#rows.get(handle);
    return row ? { ...row } : null;
  }

  async claim(handle: string, usedAt: number): Promise<ClaimOutcome> {
    const row = this.#rows.get(handle);
    if (!row) return { won: false, row: null };
    if (row.used_at !== null) return { won: false, row: { ...row } };
    const claimed: StoredLink = { ...row, used_at: usedAt };
    this.#rows.set(handle, claimed);
    return { won: true, row: { ...claimed } };
  }

  async complete(handle: string, completedAt: number): Promise<ClaimOutcome> {
    const row = this.#rows.get(handle);
    if (!row) return { won: false, row: null };
    if (row.completed_at !== null) return { won: false, row: { ...row } };
    const done: StoredLink = { ...row, completed_at: completedAt };
    this.#rows.set(handle, done);
    return { won: true, row: { ...done } };
  }

  async release(handle: string, completedAt: number): Promise<ClaimOutcome> {
    const row = this.#rows.get(handle);
    if (!row) return { won: false, row: null };
    // Only the caller HOLDING the lease may hand it back. Unconditional, this
    // would let a late retry clear the completion of a connection another
    // callback already wrote, and the next refresh would write it twice.
    if (row.completed_at !== completedAt) return { won: false, row: { ...row } };
    const open: StoredLink = { ...row, completed_at: null };
    this.#rows.set(handle, open);
    return { won: true, row: { ...open } };
  }

  /** Tests and the `/settings/connected` page both want to count outstanding
   *  links. Returns copies, and no raw tokens exist to leak. */
  all(): StoredLink[] {
    return [...this.#rows.values()].map((r) => ({ ...r }));
  }
}

// ---------------------------------------------------------------------------
// MINT
// ---------------------------------------------------------------------------

export interface MintOptions {
  store: ConnectLinkStore;
  /** Which of the owner's accounts this will be. The spec's normal case is two
   *  Google accounts, so this is a real name on a real connection. */
  alias?: AccountAlias | null;
  now?: number;
}

/** Runtime membership check on a closed enum from the contract. `--experimental
 *  -strip-types` DELETES the type annotation, so `alias: AccountAlias` stops
 *  precisely nobody at run time and a typo would be persisted as a third kind
 *  of account nothing can ever match. */
function checkedAlias(alias: unknown): AccountAlias | null {
  if (alias === undefined || alias === null) return null;
  if (alias === "work" || alias === "personal") return alias;
  throw new TypeError(
    `alias must be "work", "personal" or null, got ${JSON.stringify(alias)}`,
  );
}

/**
 * A toolkit slug, trimmed and lowercased.
 *
 * THE LINE, because it is one character away from a law-1 violation. Legal:
 * case and surrounding whitespace, so a catalog that yields "Notion" and one
 * that yields "notion" do not become two connections for one app. Illegal and
 * deliberately absent: any mapping between DIFFERENT slugs. Note this
 * intentionally does NOT collapse `-` and `_` the way src/signature.ts does —
 * there, both spellings are one planner word; here the slug is a vendor's
 * primary key and `google_drive` and `google-drive` are allowed to be two
 * different apps. Guessing that they are the same would connect the wrong one.
 */
function checkedToolkit(toolkit: unknown): Toolkit {
  if (typeof toolkit !== "string") {
    throw new TypeError(`toolkit must be a slug string, got ${typeof toolkit}`);
  }
  const slug = toolkit.trim().toLowerCase();
  if (slug === "") throw new TypeError("toolkit must not be empty");
  return slug;
}

/**
 * Mint OUR link. Nothing is asked of the vendor here — that is the entire point
 * of the file, and the four dead links of 2026-09-05 are the receipt.
 *
 * `user` goes through `ownerId()` on every call even when the caller's type
 * says it is already an `OwnerId`, because the brand is erased at run time and
 * this is the last place a display name can be caught before a token is bound
 * to it. A link minted for "omar" is a link that binds a real mailbox to a
 * string, and the spike has already had to revoke one connection made that way.
 */
export async function mint(
  user: OwnerId | string,
  toolkit: Toolkit,
  opts: MintOptions,
): Promise<ConnectLink> {
  const owner = ownerId(user as string);
  const slug = checkedToolkit(toolkit);
  const alias = checkedAlias(opts.alias);
  const now = opts.now ?? Date.now();

  const token = randomBytes(TOKEN_BYTES).toString("base64url");
  const expires_at = now + LINK_TTL_MS;

  await opts.store.put({
    token_handle: tokenHandle(token),
    user_id: owner,
    toolkit: slug,
    alias,
    expires_at,
    used_at: null,
    completed_at: null,
  });

  return { token, user_id: owner, toolkit: slug, alias, expires_at, used_at: null };
}

// ---------------------------------------------------------------------------
// LOCATING A LINK — the one place the four answers are decided
// ---------------------------------------------------------------------------

type Located =
  | { kind: "row"; row: StoredLink }
  | { kind: "dead" }
  | { kind: "signed-out" }
  | { kind: "wrong-user" };

// FROZEN, and shared. These are returned to callers, and ESM is always strict
// mode, so a route handler that tried to patch a field on the answer it got
// back would throw instead of quietly rewriting the answer every LATER caller
// receives. A shared mutable "expired" object is a one-line path to a redeem
// that returns "ok".
const DEAD: Located = Object.freeze({ kind: "dead" });
const SIGNED_OUT: Located = Object.freeze({ kind: "signed-out" });
const WRONG_USER: Located = Object.freeze({ kind: "wrong-user" });

/** A session id that is not a well-formed owner row id is not a session. It
 *  fails closed and it does NOT throw: a route that 500s on a malformed cookie
 *  is a denial-of-service handed to whoever can set one. */
function asOwnerIdOrNull(raw: unknown): OwnerId | null {
  if (typeof raw !== "string") return null;
  try {
    return ownerId(raw);
  } catch {
    return null;
  }
}

/**
 * THE ORDER OF THESE CHECKS IS THE PRIVACY MODEL. Read it before changing one.
 *
 * 1. NO SESSION, NO ANSWER — and this check comes first, before the token is
 *    even parsed. A caller who has not proved they are anybody gets `signed-out`
 *    for every token there is: live, expired, spent, forged, malformed, or
 *    somebody else's. Nothing else in this function runs for them.
 *
 *    This was the oracle. With the lookup first, a signed-out request could sort
 *    strings into "a real Anticipy token" (answered `sign-in-required`) and "not
 *    one" (answered `expired`), which is precisely the fact an intercepted text
 *    is worth checking — available to the anonymous reader the SMS threat model
 *    is about, for free, and without ever spending the link. Ordering it first
 *    also keeps the STORE out of the anonymous path, so the same fact cannot be
 *    read off the round trip with a stopwatch instead of a status code.
 *
 * 2. NOT-A-TOKEN, NO-SUCH-ROW and EXPIRED collapse into one answer, `dead`.
 *    That is what keeps a SIGNED-IN caller from being told which strings are
 *    real either: a genuine expired token and a made-up one give back the
 *    identical object.
 *
 * 3. Expiry is checked BEFORE the owner. If the owner check came first, a
 *    real-but-expired token would answer "wrong-user" forever, which tells an
 *    interceptor the token was genuine — permanently, and long after it could
 *    do anything. The cost of this order is small and is paid by the owner, not
 *    by an attacker: a link the owner already used and comes back to an hour
 *    later reads "expired" rather than "already used".
 *
 * 4. `already-used` is NOT decided here at all. The used bit is the one field
 *    that changes under a race, so reading it and acting on it is exactly the
 *    bug this module exists to avoid. `redeem` asks the store's compare-and-set
 *    and believes only that; `connectPageView` reads it only to draw a page it
 *    is not going to consume.
 *
 * A SIGNED-IN STRANGER still gets `wrong-user` rather than `dead`, and that is
 * deliberate rather than an oversight in step 1. They have proved which owner
 * they are, so the fact leaks to a known, revocable account rather than to
 * nobody — and the page has to be able to say "you are signed in as someone
 * else" or a household sharing a laptop can never be told why the link failed.
 */
async function locate(
  token: unknown,
  signedInAs: unknown,
  now: number,
  store: ConnectLinkStore,
  deadline: (row: StoredLink) => number,
): Promise<Located> {
  const who = asOwnerIdOrNull(signedInAs);
  if (who === null) return SIGNED_OUT;

  if (!isWellFormedToken(token)) return DEAD;
  const handle = tokenHandle(token);
  const row = await store.read(handle);
  if (!row) return DEAD;
  if (!constantTimeEqual(handle, row.token_handle)) return DEAD;
  if (now >= deadline(row)) return DEAD;

  if (!constantTimeEqual(who, row.user_id)) return WRONG_USER;

  return { kind: "row", row };
}

/**
 * Is the row a WRITE handed back the row the write was aimed at?
 *
 * The handle is the primary key, so it is the answer on its own; the owner and
 * the toolkit are checked too because a store that assembles a row from a join
 * can get the key right and the payload wrong, and those are the two fields
 * that decide whose account gets connected to what. Everything a caller is
 * handed is then built from the row `locate` verified, so this is a refusal,
 * never a repair.
 */
function isTheSameRow(asked: StoredLink, answered: StoredLink): boolean {
  if (!constantTimeEqual(asked.token_handle, answered.token_handle)) return false;
  if (!constantTimeEqual(asked.user_id, answered.user_id)) return false;
  return asked.toolkit === answered.toolkit;
}

/** The deadline for every leg except the callback: the link's own TTL. Dead AT
 *  the instant, not after it — `>` would leave a one-millisecond live window
 *  that no test would ever cover and no reader would ever expect. */
const ttlDeadline = (row: StoredLink): number => row.expires_at;

/** The callback's deadline. An UNCLAIMED row is already dead here: a `/done`
 *  for a token that never went through `/go` is either out of order or forged,
 *  and either way there is no vendor round trip it could be completing. It
 *  collapses into `dead` with the unknown tokens, so it is not an oracle
 *  either. */
const callbackDeadline = (row: StoredLink): number =>
  row.used_at === null ? Number.NEGATIVE_INFINITY : row.used_at + CALLBACK_WINDOW_MS;

// ---------------------------------------------------------------------------
// REDEEM
// ---------------------------------------------------------------------------

export interface RedeemOptions {
  /** The owner id from the signed-in session. `null` when nobody is signed in.
   *  NEVER a value from the request the token arrived on. */
  signedInAs: OwnerId | string | null;
  store: ConnectLinkStore;
  now?: number;
}

/**
 * Four states, and only the first carries anything.
 *
 * `wrong-user`, `expired` and `already-used` are deliberately empty objects.
 * Attaching the toolkit to `wrong-user` — so the page could say "this Notion
 * link isn't yours" — would tell whoever intercepted the text which app the
 * owner is connecting, which is a fact about the owner that they were not given
 * a link for.
 */
export type RedeemResult =
  | { outcome: "ok"; link: ConnectLink }
  | { outcome: "expired" }
  | { outcome: "already-used" }
  | { outcome: "wrong-user" };

// Frozen for the reason above: these three are handed to a caller.
const EXPIRED: RedeemResult = Object.freeze({ outcome: "expired" });
const ALREADY_USED: RedeemResult = Object.freeze({ outcome: "already-used" });
const WRONG_USER_RESULT: RedeemResult = Object.freeze({ outcome: "wrong-user" });

/**
 * Spend the token. This is the only function that consumes one.
 *
 * SIGNED OUT IS `wrong-user`, on purpose: nobody is not the owner, and this
 * function's four states are the whole surface. The page routes below answer a
 * missing session with `sign-in-required` before they ever get here, so the
 * person sees a sign-in page rather than a rejection — and, critically, an
 * unauthenticated request never reaches the compare-and-set, so it cannot burn
 * a link somebody else is about to tap.
 *
 * It is the SAME `wrong-user` for every token a signed-out caller can present,
 * because `locate` settles the session before it looks anything up. An
 * anonymous caller therefore cannot use this function to sort strings into real
 * tokens and invented ones, which is what it was doing until 2026-09-05.
 *
 * THE USED BIT IS NOT READ. Not once. The row that came back from `locate` is
 * advisory about it — on D1 that read may be served by a replica that is
 * seconds behind, and a redeem that trusted a stale `used_at: null` would hand
 * out a second "ok" for a spent token, while one that trusted a stale
 * `used_at: <time>` would refuse a token nobody has used. The compare-and-set
 * is the only authority, and it is the same authority for both mistakes.
 */
export async function redeem(token: string, opts: RedeemOptions): Promise<RedeemResult> {
  const now = opts.now ?? Date.now();
  const found = await locate(token, opts.signedInAs, now, opts.store, ttlDeadline);
  if (found.kind === "dead") return EXPIRED;
  if (found.kind === "signed-out") return WRONG_USER_RESULT;
  if (found.kind === "wrong-user") return WRONG_USER_RESULT;

  const claim = await opts.store.claim(found.row.token_handle, now);
  if (!claim.won) {
    // No row at all means it went away between the read and the write; that is
    // the unknown-token answer, not the used-token answer.
    return claim.row === null ? EXPIRED : ALREADY_USED;
  }

  // THE STORE WON — BUT ON WHICH ROW? `locate` runs exactly this check thirty
  // lines up, and for the same D1 reasons: a COLLATE NOCASE column, a stray
  // LIKE, a trimmed key or a cache returning a near neighbour all produce a row
  // that is not the one asked for. Those reasons do not stop applying because
  // the statement was an UPDATE. This was the one path in the module that took
  // the store's word for it, and it is the path whose answer decides which
  // owner `connectPageGo` then opens an OAuth flow for — so an unchecked
  // neighbouring row here is a vendor authorization in a stranger's name,
  // started from the owner's own browser.
  //
  // The claim already wrote, so a refusal leaves the link spent. That is the
  // correct direction to fail: a store answering wrongly is not a reason to
  // hand out a second live link.
  if (claim.row !== null && !isTheSameRow(found.row, claim.row)) return EXPIRED;

  // Every field but `used_at` comes from the row LOCATE verified, not from the
  // row the write handed back. A store that wins without returning a row is
  // still serviceable — `found.row` was checked against the handle that was
  // asked for — so the flow does not fall over on an implementation that
  // updates and re-reads instead of using RETURNING.
  return {
    outcome: "ok",
    link: {
      token,
      user_id: found.row.user_id,
      toolkit: found.row.toolkit,
      alias: found.row.alias,
      expires_at: found.row.expires_at,
      used_at: claim.row?.used_at ?? now,
    },
  };
}

// ---------------------------------------------------------------------------
// THE THREE PAGE ROUTES
// ---------------------------------------------------------------------------
// Pure functions. No HTTP, no framework, no rendering — the Worker turns these
// results into a status code and a template. Everything a page needs is in the
// result; nothing a page must not say is anywhere in it.

/** GET /c/{token}. NOTHING here consumes the token: a person who opens the page
 *  and thinks better of it must still be able to tap it later, and a link
 *  prefetcher must not be able to burn it. */
export type ConnectPageView =
  | {
      state: "ok";
      toolkit: ToolkitMeta;
      alias: AccountAlias | null;
      /** The three plain sentences, generated from the toolkit's own scopes by
       *  the injected `PermissionWords`. Never a per-app string table: a new
       *  app in the catalog is a new app in Anticipy with zero code here. */
      sentences: string[];
      expires_at: number;
    }
  /** Carries NOTHING. Before a session exists we cannot tell the owner from
   *  whoever is holding their phone, so naming the app on this page would print
   *  the answer above the lock screen. It is also the answer to EVERY token a
   *  signed-out caller can present — unknown, expired, spent, somebody else's —
   *  so the page cannot be asked which strings are real Anticipy tokens. */
  | { state: "sign-in-required" }
  | { state: "expired" }
  | { state: "already-used" }
  | { state: "wrong-user" };

export interface ViewOptions {
  signedInAs: OwnerId | string | null;
  store: ConnectLinkStore;
  /** Name, logo and scopes come from the catalog at run time. NO APP IS
   *  HARDCODED — this call is why. */
  provider: Pick<ConnectionProvider, "toolkit">;
  words: PermissionWords;
  now?: number;
}

export async function connectPageView(
  token: string,
  opts: ViewOptions,
): Promise<ConnectPageView> {
  const now = opts.now ?? Date.now();
  const found = await locate(token, opts.signedInAs, now, opts.store, ttlDeadline);
  if (found.kind === "dead") return { state: "expired" };
  if (found.kind === "signed-out") return { state: "sign-in-required" };
  if (found.kind === "wrong-user") return { state: "wrong-user" };
  // Read-only, so the used bit may be believed here: the worst a stale replica
  // can do is draw the wrong page for the owner, and the tap that follows still
  // goes through the compare-and-set in `redeem`.
  if (found.row.used_at !== null) return { state: "already-used" };

  // Deliberately NOT caught. Nothing has been consumed yet, so a provider blip
  // is a retry — and swallowing it into a "state" would teach the page to
  // render an app with no name. `connectPageGo` is the opposite case and says
  // why there.
  const meta = await opts.provider.toolkit(found.row.toolkit);
  const sentences = await opts.words.sentences(meta);

  return {
    state: "ok",
    toolkit: meta,
    alias: found.row.alias,
    sentences: checkedSentences(sentences, found.row.toolkit),
    expires_at: found.row.expires_at,
  };
}

/**
 * A consent page has to say what the person is agreeing to.
 *
 * `PermissionWords` is injected, so what comes back is whatever the caller
 * wired up, and `Promise<string[]>` has no way to say "I have nothing" — the
 * two values that fit the type are `[]` and a made-up sentence. This module
 * cannot audit the WORDS (that is words.ts's job, with a model), but it can
 * refuse to publish silence: an `ok` page carrying an empty list renders a
 * consent screen with a button and no claims above it, and it looks exactly
 * like a page that finished loading. A person cannot consent to nothing.
 *
 * A blank among good ones is refused too, not filtered: quietly dropping one of
 * three sentences shows the person less than they are about to agree to, which
 * is the same defect with better manners.
 *
 * It throws for the reason the catalog outage above throws — nothing has been
 * consumed, so this is a retry, and folding it into a `state` would teach the
 * page to render the empty list under a different name. HOW MANY sentences
 * there should be is deliberately not checked: that is the words module's
 * question, and a count rule here would be an outage the first time a toolkit
 * with one scope reaches the catalog.
 */
function checkedSentences(sentences: unknown, slug: Toolkit): string[] {
  const lines = Array.isArray(sentences)
    ? sentences.filter((s): s is string => typeof s === "string" && s.trim() !== "")
    : [];
  if (!Array.isArray(sentences) || lines.length === 0 || lines.length !== sentences.length) {
    throw new Error(
      `no permission sentences for ${JSON.stringify(slug)} — a connect page cannot ask `
        + "somebody to agree to a blank list",
    );
  }
  return lines;
}

/** POST /c/{token}/go. */
export type ConnectPageGo =
  | { state: "ok"; redirectUrl: string }
  | { state: "sign-in-required" }
  | { state: "expired" }
  | { state: "already-used" }
  | { state: "wrong-user" }
  /** The token was SPENT and the vendor did not answer. Say so plainly and
   *  offer a fresh link; do not offer this one again. */
  | { state: "provider-unavailable" };

export interface GoOptions {
  signedInAs: OwnerId | string | null;
  store: ConnectLinkStore;
  provider: Pick<ConnectionProvider, "authorize">;
  baseUrl?: string;
  now?: number;
}

/**
 * The tap. This is where — and the only place where — the vendor link is asked
 * for, which is the whole correction of 2026-09-05.
 *
 * CLAIM FIRST, THEN AUTHORIZE, and the order is not an accident. Reversed, two
 * concurrent taps would both open a connection request at the vendor and only
 * one would be handed back; the loser's request stays live at Composio with
 * nothing on our side tracking it. Claiming first guarantees exactly one
 * `authorize` per token, ever.
 *
 * The price is paid when the provider fails: the token is already spent and
 * stays spent. That is the correct direction to fail. Un-spending it on an
 * error would hand anyone who can make the vendor time out an unlimited number
 * of attempts at a link that was supposed to work once — and a spent link costs
 * the owner one tap on "send me a new one", while a re-usable one costs them an
 * account binding.
 */
export async function connectPageGo(
  token: string,
  opts: GoOptions,
): Promise<ConnectPageGo> {
  const now = opts.now ?? Date.now();

  // Before the compare-and-set, so an unauthenticated request cannot spend a
  // link. Otherwise anyone holding an intercepted token could burn it from a
  // signed-out browser and the owner's own tap would find it used.
  if (asOwnerIdOrNull(opts.signedInAs) === null) return { state: "sign-in-required" };

  const spent = await redeem(token, {
    signedInAs: opts.signedInAs,
    store: opts.store,
    now,
  });
  if (spent.outcome !== "ok") return { state: spent.outcome };

  const link = spent.link;
  let redirectUrl: unknown;
  try {
    const authorized = await opts.provider.authorize(link.user_id, link.toolkit, {
      callbackUrl: callbackUrl(token, opts.baseUrl ?? CONNECT_URL_BASE),
      alias: link.alias,
    });
    redirectUrl = authorized?.redirectUrl;
  } catch {
    // Swallowed deliberately: the vendor's error text is theirs, may name them,
    // and the person is owed one sentence, not a stack trace. The caller logs
    // with `tokenFingerprint`, never the token.
    return { state: "provider-unavailable" };
  }

  // A missing or empty URL is a failure that returned 200. Redirecting to
  // "undefined" would put the person on a broken page and burn the link with
  // no explanation.
  if (typeof redirectUrl !== "string" || redirectUrl.trim() === "") {
    return { state: "provider-unavailable" };
  }

  return { state: "ok", redirectUrl };
}

/** GET /c/{token}/done — the vendor's callback. Composio has no success
 *  webhook, only `expired`, so this is the ONLY moment we ever learn that a
 *  connection exists. */
export type ConnectPageDone =
  | {
      state: "connected";
      connection: Connection;
      /** True for the caller that actually WROTE the row. A refresh is
       *  `connected` with `recorded: false`, so the person sees the right page
       *  and the connection is written once. */
      recorded: boolean;
    }
  /** The vendor came back without a success, or the account it named is not one
   *  the vendor holds for this owner on this toolkit. Say the connection did
   *  not finish; do not guess at why, and offer another go — a vendor that has
   *  not yet listed a brand-new account is indistinguishable from a forged id,
   *  and nothing has been consumed either way. */
  | { state: "not-connected" }
  /** The vendor could not be ASKED whether the account is this owner's. Not a
   *  failed connect: the account may well exist, we simply have no evidence
   *  yet, and recording on no evidence is the failure below. Nothing is
   *  written, nothing is consumed, and a refresh retries. */
  | { state: "could-not-confirm" }
  /** The connection is real and confirmed, and OUR write of it failed. The
   *  exactly-once lease has been handed back, so a refresh retries; saying
   *  "connected" here is what used to lose the connection permanently. */
  | { state: "not-recorded" }
  | { state: "expired" }
  | { state: "sign-in-required" }
  | { state: "wrong-user" };

export interface DoneParams {
  /** The vendor's own status field, off the callback query string. */
  status: string | null;
  /** The vendor's id for the account that was just connected. */
  connectedAccountId: string | null;
}

export interface DoneOptions {
  signedInAs: OwnerId | string | null;
  store: ConnectLinkStore;
  /** WHOSE CREDENTIAL ANSWERED? `connections(user)` is the vendor's own list
   *  for one owner, and it is the only thing that can turn the account id on
   *  the query string from a claim into a fact. Required: recording a binding
   *  nobody confirmed is the highest-severity defect this file has. */
  provider: Pick<ConnectionProvider, "connections">;
  /** Where a finished connection is written. A callback, not an import: the
   *  `connections` table belongs to another module and this one must not own
   *  it.
   *
   *  Called at most once per successful completion, and it MUST BE IDEMPOTENT
   *  on (user_id, toolkit, connected_account_id). A write that throws hands the
   *  exactly-once lease back so the person's refresh can retry — which means a
   *  write that committed and THEN failed (a timeout after the commit) will be
   *  attempted again. Delivering the same connection twice is a repaired row;
   *  delivering it zero times is a connection that exists at the vendor and
   *  nowhere here, with no webhook that will ever mention it again. */
  onConnected: (connection: Connection) => Promise<void>;
  /** The vendor's spelling of success. Config, not code. */
  successStatus?: string;
  now?: number;
}

/**
 * Record the connection.
 *
 * THE WORST FAILURE IN THE PRODUCT IS HERE, so read the next sentence twice:
 * `user_id` comes from the STORED ROW — bound at mint time to an id that passed
 * `ownerId()` — and never from this request. There is no parameter on this
 * function through which a caller could name an owner, which is the structural
 * half; the signed-in session is compared to the row's owner rather than
 * trusted, which is the other half. A callback that could name its own owner is
 * one operator's mailbox serving everybody, arrived at through a query string.
 *
 * FAIL CLOSED. A missing status, an unrecognised status or a missing account id
 * are all `not-connected`, and nothing is written. Recording a connection that
 * did not happen leaves a row the router will route to and the ledger will
 * count, and the first the owner hears of it is a step that fails.
 *
 * AND `connected_account_id` IS CONFIRMED, NOT COPIED. This paragraph used to
 * say the opposite — that writing the id verbatim "cannot bind one person's
 * mailbox to another, which is the failure that matters" — and that was false,
 * which makes it worse than no comment at all. `user_id` says who WE think this
 * is; `connected_account_id` is the VENDOR's handle for whichever credential
 * actually answers, and it arrives on a query string a browser can edit. Copied
 * verbatim it writes "this owner's Gmail is <somebody else's account>", and the
 * first step that runs against that row reaches into another person's mailbox
 * holding our key. Same failure, other end of the same table.
 *
 * So the account is checked against the vendor's own list for THIS owner —
 * `connections(user)`, scoped by the row's owner and never by the request —
 * and it must appear there on this toolkit or nothing is written. Two shapes
 * are refused rather than filtered, for the reason `locate` refuses a wrong
 * row: an entry carrying a different `user_id` means the scoping did not hold,
 * and an entry on a different toolkit would file a calendar credential under
 * the mail row. Status is deliberately NOT matched — the vendor's own status
 * races with the callback that reports it, and the callback already carries the
 * vendor's word for success.
 *
 * THE RESIDUAL RISK, WRITTEN DOWN RATHER THAN LEFT FOR SOMEBODY TO FIND. A
 * concurrent refresh that loses the lease answers `connected, recorded: false`
 * on the winner's behalf; if the winner's write then fails, that one page said
 * "connected" about a row that does not exist yet. The lease is handed back, so
 * the next callback in the hour-long window writes it and the page self-heals —
 * which is the whole difference from the old behaviour, where the same sentence
 * was permanent and no later call could ever repair it.
 */
export async function connectPageDone(
  token: string,
  params: DoneParams,
  opts: DoneOptions,
): Promise<ConnectPageDone> {
  const now = opts.now ?? Date.now();
  const found = await locate(token, opts.signedInAs, now, opts.store, callbackDeadline);
  if (found.kind === "dead") return { state: "expired" };
  if (found.kind === "signed-out") return { state: "sign-in-required" };
  if (found.kind === "wrong-user") return { state: "wrong-user" };

  const success = opts.successStatus ?? CALLBACK_SUCCESS;
  const accountId = typeof params?.connectedAccountId === "string"
    ? params.connectedAccountId.trim()
    : "";
  // A string compare against ONE configured literal from a machine's closed
  // enum. This is not law 1's territory: no human wrote this word and nothing
  // about what a PERSON meant is being decided. The day it starts reading prose
  // it is a violation.
  if (params?.status !== success || accountId === "") {
    return { state: "not-connected" };
  }

  // A missing provider is a WIRING bug in the Worker, not a person's problem,
  // and it must not degrade into telling every owner "try again" forever. It
  // throws where an operator will see it, and only on the path that needs it,
  // so every refusal above still answers normally.
  if (typeof opts?.provider?.connections !== "function") {
    throw new TypeError(
      "connectPageDone needs a provider: the account id on the callback has to be "
        + "confirmed against this owner's own accounts before it is bound",
    );
  }

  // ASKED ABOUT THE STORED ROW'S OWNER. Not the session (which was only proved
  // equal to it), and not anything on the request.
  let listed: unknown;
  try {
    listed = await opts.provider.connections(found.row.user_id);
  } catch {
    // Nothing has been consumed, so this is a retry rather than a verdict. The
    // vendor's error text is theirs and may name them; the person is owed one
    // sentence. The caller logs with `tokenFingerprint`, never the token.
    return { state: "could-not-confirm" };
  }
  if (!vendorVouchesFor(listed, found.row, accountId)) {
    return { state: "not-connected" };
  }

  const connection: Connection = {
    user_id: found.row.user_id,
    toolkit: found.row.toolkit,
    connected_account_id: accountId,
    alias: found.row.alias,
    status: "connected",
    // OFF BY DEFAULT, always. This is the Settings toggle "let Anticipy make
    // changes" and the Two Hands ladder cannot reach rung 3 without it. A
    // connection that arrived write-enabled would let the first step that ever
    // ran against it send mail on the owner's behalf, having been asked for
    // nothing but a connection.
    writes_enabled: false,
    last_used_at: null,
  };

  // THE LEASE, NOT A RECEIPT. A callback URL gets refreshed, back-buttoned and
  // prefetched, so exactly one caller is allowed to do the writing — but taking
  // the lease is a promise to write, not proof that the write happened. Reading
  // it as proof is what turned one failed `onConnected` into a page that said
  // "connected" forever with no row anywhere: the account existed at the
  // vendor, Composio publishes no success webhook, and nothing would ever
  // mention it again.
  const lease = await opts.store.complete(found.row.token_handle, now);
  if (!lease.won) return { state: "connected", connection, recorded: false };

  try {
    await opts.onConnected(connection);
  } catch {
    // GIVE THE LEASE BACK so the person's next refresh is the one that writes.
    // Guarded rather than assumed: a store that shipped without `release`, or
    // whose release itself fails, must still get the honest answer below and
    // not a second exception thrown from inside the error path.
    try {
      if (typeof opts.store.release === "function") {
        await opts.store.release(found.row.token_handle, now);
      }
    } catch {
      // Nothing to add. The lease stays taken, refreshes will read as
      // `connected, recorded: false`, and a fresh link is then the only way
      // through — which is exactly why `release` is on the store interface.
    }
    return { state: "not-recorded" };
  }
  return { state: "connected", connection, recorded: true };
}

/**
 * Does the vendor itself say this account is this owner's, on this toolkit?
 *
 * Nothing here reads prose or guesses at an app from a name: it compares one
 * opaque vendor id against a list the vendor returned, and one slug against the
 * slug the link was minted with. Case and padding on the slug are plumbing —
 * a catalog that says "Notion" and one that says "notion" are one app, exactly
 * as `checkedToolkit` decides at mint time. The ACCOUNT ID is compared
 * case-sensitively: it is an opaque primary key, and folding `CA_X` onto `ca_x`
 * would be inventing a match.
 *
 * A FLOOR, so it answers false on anything it cannot read: a non-array, an
 * entry that is not an object, a missing field. "Nobody said yes" and "somebody
 * said no" are the same answer when the question is whether to bind a
 * stranger's mailbox.
 */
function vendorVouchesFor(listed: unknown, row: StoredLink, accountId: string): boolean {
  if (!Array.isArray(listed)) return false;
  return listed.some((entry) => {
    if (entry === null || typeof entry !== "object") return false;
    const item = entry as Partial<Connection>;
    if (typeof item.connected_account_id !== "string") return false;
    if (item.connected_account_id.trim() !== accountId) return false;
    // The list was asked for by owner, so a row bound to anybody else means the
    // scoping did not hold — and an unscoped list is not evidence about ours.
    if (typeof item.user_id !== "string") return false;
    if (!constantTimeEqual(item.user_id, row.user_id)) return false;
    if (typeof item.toolkit !== "string") return false;
    return item.toolkit.trim().toLowerCase() === row.toolkit;
  });
}
