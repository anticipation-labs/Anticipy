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
// session to BE the owner the token was minted for, and a redeem by anybody
// else is told nothing: not the toolkit, not the owner, not whether the token
// was ever real.
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
   *     WHERE token_handle = ?2 AND completed_at IS NULL */
  complete(handle: string, completedAt: number): Promise<ClaimOutcome>;
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
 * 1. NOT-A-TOKEN, NO-SUCH-ROW and EXPIRED collapse into one answer, `dead`.
 *    That is what stops the endpoint being an oracle: a person who intercepted
 *    a text cannot use these routes to learn whether the string they have is a
 *    real Anticipy token, because a real expired one and a made-up one give
 *    back the identical object.
 *
 * 2. Expiry is checked BEFORE the owner. If the owner check came first, a
 *    real-but-expired token would answer "wrong-user" forever, which tells an
 *    interceptor the token was genuine — permanently, and long after it could
 *    do anything. The cost of this order is small and is paid by the owner, not
 *    by an attacker: a link the owner already used and comes back to an hour
 *    later reads "expired" rather than "already used".
 *
 * 3. `already-used` is NOT decided here at all. The used bit is the one field
 *    that changes under a race, so reading it and acting on it is exactly the
 *    bug this module exists to avoid. `redeem` asks the store's compare-and-set
 *    and believes only that; `connectPageView` reads it only to draw a page it
 *    is not going to consume.
 */
async function locate(
  token: unknown,
  signedInAs: unknown,
  now: number,
  store: ConnectLinkStore,
  deadline: (row: StoredLink) => number,
): Promise<Located> {
  if (!isWellFormedToken(token)) return DEAD;
  const handle = tokenHandle(token);
  const row = await store.read(handle);
  if (!row) return DEAD;
  if (!constantTimeEqual(handle, row.token_handle)) return DEAD;
  if (now >= deadline(row)) return DEAD;

  const who = asOwnerIdOrNull(signedInAs);
  if (who === null) return SIGNED_OUT;
  if (!constantTimeEqual(who, row.user_id)) return WRONG_USER;

  return { kind: "row", row };
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

  const row = claim.row ?? { ...found.row, used_at: now };
  return {
    outcome: "ok",
    link: {
      token,
      user_id: row.user_id,
      toolkit: row.toolkit,
      alias: row.alias,
      expires_at: row.expires_at,
      used_at: row.used_at,
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
   *  the answer above the lock screen. */
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
    sentences,
    expires_at: found.row.expires_at,
  };
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
      /** True for the caller whose compare-and-set won, i.e. the one call that
       *  recorded. A refresh of this page is `connected` with `recorded:
       *  false`, so the person sees the right page and the connection is
       *  written exactly once. */
      recorded: boolean;
    }
  /** The vendor came back without a success. Say the connection did not
   *  finish; do not guess at why. */
  | { state: "not-connected" }
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
  /** Where a finished connection is written. A callback, not an import: the
   *  `connections` table belongs to another module and this one must not own
   *  it. Called at most once per token. */
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
 * THE RESIDUAL RISK, WRITTEN DOWN RATHER THAN LEFT FOR SOMEBODY TO FIND. Both
 * facts below arrive on a query string the browser can edit, so a signed-in
 * owner holding their own spent token can hand themselves a `connected` row for
 * an account id that does not exist. The blast radius is their own account —
 * the owner is the stored row's, never the request's — so this cannot bind one
 * person's mailbox to another, which is the failure that matters. It still ends
 * in a step that fails against a connection that was never real.
 *
 * WHAT CLOSES IT: confirming with the provider before recording, which is what
 * Composio's `wait_for_connection` is for (they publish no success webhook,
 * only `expired`, so the callback plus a confirm is the whole signal). It is
 * not done here because `ConnectionProvider` in connections/contract.ts has no
 * method for it — `authorize` returns a `redirectUrl` and nothing to poll with,
 * so this module has nothing to ask. That is a contract gap, reported as one,
 * and it is the first thing to fix in this file when the seam grows the method.
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

  // Exactly-once. A callback URL gets refreshed, back-buttoned and prefetched;
  // without this the same connection is written as many times as the page is
  // opened.
  const first = await opts.store.complete(found.row.token_handle, now);
  if (!first.won) return { state: "connected", connection, recorded: false };

  await opts.onConnected(connection);
  return { state: "connected", connection, recorded: true };
}
