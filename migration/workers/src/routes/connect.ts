/**
 * src/routes/connect.ts — https://anticipy.ai/c/{token}, the connect page.
 *
 * This is the only screen in the product where a person hands Anticipy a key
 * to something of theirs, so every rule the Connections spec has is either
 * enforced here or is not enforced at all.
 *
 *   GET  /c/{token}        the page: the app's own name, logo and three plain
 *                          sentences, all read from the catalog at run time.
 *   POST /c/{token}/go     the tap: mints the vendor's link, spends our token,
 *                          redirects. THE ONLY PLACE A VENDOR URL IS PRODUCED.
 *   GET  /c/{token}/done   the vendor's callback, which is the ONLY signal a
 *                          connection exists — Composio publishes no success
 *                          webhook, only `expired`.
 *
 * WHY OUR OWN LINK EXISTS AT ALL, MEASURED. On 2026-09-05 four vendor connect
 * links were generated and handed to a person to tap later. The vendor's links
 * live ten minutes. All four were dead before they were tapped
 * (research/2026-09-05-composio-connections.md, item 3). So a text carries OUR
 * token, and the vendor link is minted the instant a finger touches the glass.
 * `connectPageGo` below is the only function in this file that asks the vendor
 * for anything, and the test suite pins that rather than trusting it.
 *
 * WHY A LINK IS NOT ENOUGH. A text message is not private and is not
 * phishing-resistant: it lives in a notification shade, in a synced Messages
 * database and in a carrier log. If the link alone could bind an account,
 * whoever reads the text over a shoulder could attach THEIR mailbox to somebody
 * else's Anticipy, or the owner's mailbox to their own. That is the failure
 * spike/two-hands/src/connections/contract.ts opens with — one operator's own
 * Gmail serving everybody, which happened, and was revoked and deleted —
 * reached from the other end. So every leg requires the signed-in session to BE
 * the owner the token was minted for.
 *
 * AND IT IS NOT AN ORACLE. A caller who has proved nothing is told nothing: not
 * the app, not the owner, not whether the token was ever real. `locate` settles
 * the session BEFORE it looks anything up, which collapses unknown, expired,
 * spent and not-yours into one byte-identical answer for an anonymous caller,
 * and keeps the store out of the anonymous path entirely so the same fact
 * cannot be read off the round trip with a stopwatch. The spike had exactly
 * this hole (a live token answered `sign-in-required`, an invented one answered
 * `expired`, so an interceptor could confirm a stolen text was worth keeping)
 * and closed it; this port does not reopen it.
 *
 * THE REGISTER, which is a product rule and not a preference. The person never
 * reads "authorize", "grant access", "permissions", "integration", "API",
 * "OAuth" or the vendor's name. It is "connect your Notion", and connecting is
 * always optional, said in one sentence, on the page. The three sentences come
 * from the catalog's own scopes through the injected `PermissionWords`, so a
 * new app in the catalog is a new app in Anticipy with ZERO code here. If a
 * list of app names ever appears in this file, it has become the thing the spec
 * forbids — the behavioural pin is the two-invented-toolkits test in the suite.
 *
 * HARNESS-LAWS LAW 1. Nothing here decides what a person MEANT. Which app
 * somebody wants is a model's answer (`ToolkitJudge` in the contract) and
 * arrives as a slug this file never chose. What this file pattern-matches is
 * structure only: the shape of a token, the shape of an owner row id, the
 * scheme of a URL, and one vendor status field compared against one configured
 * literal. That is the senses-and-transport clause. The day it starts reading
 * prose it has left it.
 *
 * PORTED FROM spike/two-hands/src/connections/links.ts (1006 tests, adversarial
 * pass). Behaviour and comments are carried across, not redesigned. The spike
 * runs on Node and hashes with `node:crypto`; a Worker has neither, so the
 * token plumbing below is WebCrypto and the store is an interface the Worker's
 * wiring fills. If migration/workers/src/connections/links.ts ever lands as a
 * shared module, THE PURE CORE SECTION BELOW IS DELETED AND IMPORTED INSTEAD —
 * two copies of this logic is a defect, and the tests are written against these
 * exported names so the swap is an import line.
 *
 * Spec: "Connections: how Anticipy asks, learns, and never says Composio",
 * 2026-09-05, page 26.
 */
import { verifyToken, type AuthEnv } from "../pb/auth.ts";

// ---------------------------------------------------------------------------
// ENV
// ---------------------------------------------------------------------------

export interface ConnectEnv extends AuthEnv {
  DB: D1Database;
  /**
   * Our own origin for the callback we hand the vendor, e.g.
   * "https://anticipy.ai/c". DELIBERATELY NOT DERIVED FROM THE REQUEST: a Host
   * header is attacker-controlled, and a callback built from one would hand the
   * vendor a URL on somebody else's host with the account id on it. Unset means
   * the production constant, which is right for production and is why a preview
   * deployment must set this rather than be silently pointed at prod.
   */
  CONNECT_BASE_URL?: string;
}

// ---------------------------------------------------------------------------
// CONSTANTS
// ---------------------------------------------------------------------------

/** Our origin, never the vendor's. The spec's rule is one line: "Never the raw
 *  Composio or Google URL in a text." */
// THE HOST THIS WORKER IS ACTUALLY ON, not the one the spec would prefer.
//
// The spec writes every link as `anticipy.ai/c/{token}`, and that is the nicer
// thing to receive in a text. But this Worker's only route is the custom domain
// `api.anticipy.ai` (wrangler.jsonc), and measured on 2026-09-06 the apex
// answers 301 and www answers 307 — neither reaches this code. A constant
// naming a host we are not on produces a texted link that 404s and a callback
// URL handed to the vendor that points somewhere we never see, which is the
// silent version of the feature not existing.
//
// To move it to the apex, add a route — `{ "pattern": "anticipy.ai/c/*",
// "zone_name": "anticipy.ai" }` — deploy, confirm the apex serves this code,
// and only then change this line. Doing it in the other order breaks every
// link already in somebody's message thread.
//
// CONNECT_BASE_URL overrides this for previews. It is deliberately NOT read
// from the Host header: a callback built from a header hands the vendor a URL
// on whatever host the request claimed to be.
export const CONNECT_URL_BASE = "https://api.anticipy.ai/c";

/** contract.ts LINK_TTL_MS. Ten minutes, matching the vendor's own link life
 *  and `ConnectHandoff.attemptLifetime` on the phone. */
export const LINK_TTL_MS = 10 * 60 * 1000;

/**
 * How long the CALLBACK may take, measured from the moment the link was
 * claimed — deliberately NOT LINK_TTL_MS.
 *
 * LINK_TTL_MS answers "how long may an UNTAPPED link sit in a text". The vendor
 * round trip is a different question and a much slower one: a password manager,
 * a 2FA push, a workspace picker, an account chooser, and in the Notion case a
 * login the person did not have. Ten minutes there is routinely not enough, and
 * expiring the callback would throw away a connection the person actually
 * completed — the account would exist at the vendor with no row here, and there
 * is no success webhook that would ever mention it again.
 */
export const CALLBACK_WINDOW_MS = 60 * 60 * 1000;

/** The one literal the callback's `status` may carry and still be believed.
 *  Overridable per call, because it is the vendor's spelling and not ours.
 *  Anything else — including a missing status — is not-connected: recording a
 *  connection is the privilege here, so it needs positive evidence rather than
 *  the absence of an objection (HARNESS-LAWS law 1, the FLOOR polarity). */
export const CALLBACK_SUCCESS = "success";

/**
 * The browser's half of a signed-in session.
 *
 * The iPhone holds an `owners` auth token and sends it in `Authorization`; a
 * browser opening a texted link has no way to set a header, so it presents the
 * same token in a cookie. WHOEVER MINTS THIS COOKIE OWNS ITS FLAGS — it must be
 * HttpOnly, Secure, SameSite=Lax and scoped to the apex. This file only ever
 * READS it, and reads it through the same `verifyToken` the data API uses, so a
 * forged or stale cookie is exactly as good as no cookie at all.
 */
export const SESSION_COOKIE = "anticipy_session";

/** The deep link home. `anticipy://connected/{toolkit}` — the scheme is
 *  registered in app/ios/Anticipy/Info.plist and parsed by
 *  ConnectHandoff.parseDone, whose four states this page mints the tokens for. */
const APP_SCHEME = "anticipy";
const APP_CALLBACK_HOST = "connected";

/** The status tokens OUR page mints and the phone reads
 *  (ConnectHandoff.statusConnected / statusFailed). They are transport, not
 *  language: our page writes them and our app parses them. */
const APP_STATUS_CONNECTED = "connected";
const APP_STATUS_FAILED = "failed";

// ---------------------------------------------------------------------------
// THE SEAM — what this file must NOT own
// ---------------------------------------------------------------------------
// Three things belong to other modules and arrive injected: the `connect_links`
// store (D1 tables and their migration), the catalog/vendor client, and the
// model that writes the permission sentences. A route file that reached into
// any of them would own the whole feature; a route file that guesses at them
// would be the wrong-person failure with extra steps.

/** The owner's row id as stored in D1's `owners` table: 15 lowercase
 *  alphanumerics (src/pb/wire.ts newRecordId). NOT an email, NOT a name. */
export type OwnerId = string;

export type AccountAlias = "work" | "personal";

/**
 * The `connect_links` row as it is persisted.
 *
 * `token_handle` REPLACES the token: `connect_links` is a D1 table, and D1 rows
 * end up in backups, in `wrangler d1 execute` output and in whatever a future
 * debugging session pastes into a terminal. A raw single-use bearer token at
 * rest means a database read is a live link for every owner holding one — the
 * "a link alone is never enough" rule, failed at the other end.
 *
 * `completed_at` is the callback's exactly-once lease. Without it a refresh of
 * the done page records the same connection twice.
 */
export interface StoredLink {
  token_handle: string;
  user_id: OwnerId;
  toolkit: string;
  alias: AccountAlias | null;
  expires_at: number;
  used_at: number | null;
  completed_at: number | null;
}

/** The result of a compare-and-set. `won` is true for exactly one caller. */
export interface ClaimOutcome {
  won: boolean;
  /** The row as it stands after the attempt, or null if there is no such row.
   *  Never a raw token — there is none stored. */
  row: StoredLink | null;
}

/**
 * `claim`, `complete` and `release` are the whole reason this is an interface
 * and not a map: they are atomic writes, and their D1 spellings are written on
 * each method. Anything that implements one by reading a row, deciding in
 * JavaScript and writing it back is not an implementation of this interface —
 * it is the double-redeem bug with extra steps.
 */
export interface ConnectLinkStore {
  read(handle: string): Promise<StoredLink | null>;
  /** THE SINGLE-USE GATE. One statement, no read-then-write:
   *    UPDATE connect_links SET used_at = ?1
   *     WHERE token_handle = ?2 AND used_at IS NULL
   *  and `won = (changes === 1)`. */
  claim(handle: string, usedAt: number): Promise<ClaimOutcome>;
  /** THE EXACTLY-ONCE GATE for the callback, same shape on `completed_at`.
   *  Read it as taking a LEASE, not filing a receipt: it says "I am the one who
   *  will write this connection", and `release` hands it back if the write does
   *  not happen. */
  complete(handle: string, completedAt: number): Promise<ClaimOutcome>;
  /**
   * GIVE THE LEASE BACK when the write it was taken for failed. Conditional,
   * like every other write here, so a stale caller cannot re-open the
   * exactly-once window under a connection somebody else already recorded:
   *    UPDATE connect_links SET completed_at = NULL
   *     WHERE token_handle = ?1 AND completed_at = ?2
   *
   * WHY IT EXISTS: in the spike, `complete` was burned before `onConnected`, so
   * one failed write left the token completed with no row anywhere — the page
   * said "connected" on every refresh, the account existed at the vendor, and
   * no webhook would ever mention it again. Permanent silent data loss, one
   * `throw` away at all times.
   */
  release(handle: string, completedAt: number): Promise<ClaimOutcome>;
}

/** Name, logo, description and required scopes, so the page and its sentences
 *  are generic. NO APP IS HARDCODED — this shape is why. */
export interface ToolkitMeta {
  slug: string;
  name: string;
  logo: string | null;
  description: string | null;
  appUrl: string | null;
  scopes: string[];
}

export interface Connection {
  user_id: OwnerId;
  toolkit: string;
  connected_account_id: string;
  alias: AccountAlias | null;
  status: "connected" | "needs_reconnect" | "disconnected";
  /** THE WRITE OPT-IN, off by default. The Settings toggle "let Anticipy make
   *  changes"; the Two Hands ladder cannot reach rung 3 without it. */
  writes_enabled: boolean;
  last_used_at: number | null;
}

/** The three vendor calls this page makes, and no others. `disconnect` and
 *  `session` belong to Settings and to the provider module. */
export interface CatalogProvider {
  toolkit(slug: string): Promise<ToolkitMeta>;
  authorize(
    user: OwnerId,
    toolkit: string,
    opts: { callbackUrl: string; alias?: AccountAlias | null },
  ): Promise<{ redirectUrl: string }>;
  /** The vendor's own list for ONE owner. The only thing that can turn the
   *  account id on a query string from a claim into a fact. */
  connections(user: OwnerId): Promise<Connection[]>;
}

/** Turns a toolkit's own metadata into the three plain sentences the page
 *  shows. A model writes them (words.ts audits the register); this file only
 *  refuses to publish silence. */
export interface PermissionWords {
  sentences(meta: ToolkitMeta): Promise<string[]>;
}

export interface ConnectDeps {
  store: ConnectLinkStore;
  provider: CatalogProvider;
  words: PermissionWords;
  /**
   * Where a finished connection is written. A callback, not an import: the
   * `connections` and `connect_nudges` tables belong to another module and this
   * one must not own them.
   *
   * ITS CONTRACT, because the lease above is a promise about it. One
   * implementation, ONE D1 batch, doing both halves the spec asks for: upsert
   * the `connections` row AND flip that owner's `connect_nudges` row for this
   * toolkit to `connected`. Two callbacks would be two failure modes under one
   * lease, and the half that failed would be invisible.
   *
   * It MUST BE IDEMPOTENT on (user_id, toolkit, connected_account_id): a write
   * that committed and then failed (a timeout after the commit) will be
   * attempted again by the person's refresh. Delivering the same connection
   * twice is a repaired row; delivering it zero times is a connection that
   * exists at the vendor and nowhere here.
   */
  onConnected(connection: Connection): Promise<void>;
  /** The vendor's spelling of success. Config, not code. */
  successStatus?: string;
  /** Injectable clock. Tests own time; production passes nothing. */
  now?(): number;
  /** Our callback origin. Defaults to `CONNECT_URL_BASE`. */
  baseUrl?: string;
}

/**
 * THE WIRING SEAM, and why a missing wiring is a 503 rather than a 404.
 *
 * The three ports above are built by whichever module owns the store, the
 * vendor client and the sentence writer. Until that wiring calls
 * `installConnectWiring`, every /c/ route answers 503 with a sentence naming
 * what is missing — the same choice /sms/sendblue makes for an unset secret
 * (routes/sendblue.ts): a configuration problem must never wear the costume of
 * a forged request or of a feature that does not exist, because both hide a
 * dead product behind a plausible status code. It never answers 200: an
 * unwired Worker must not be able to draw a consent page.
 */
export type ConnectWiring = (env: ConnectEnv) => ConnectDeps | null;

let WIRING: ConnectWiring = () => null;
let WIRED = false;

export function installConnectWiring(wiring: ConnectWiring): void {
  WIRING = wiring;
  WIRED = true;
}

/** For a gate leg, and for the suite: has anything been wired at all? A Worker
 *  that answers `false` here cannot serve a connect page, and the honest place
 *  to notice that is a deploy check, not an owner tapping a dead link. */
export function connectWiringInstalled(): boolean {
  return WIRED;
}

// ---------------------------------------------------------------------------
// TOKEN PLUMBING
// ---------------------------------------------------------------------------

/** 32 bytes of base64url, unpadded: ceil(32 * 4 / 3) = 43 characters. Written
 *  down because the route parser and the well-formedness guard both depend on
 *  it, and a 44-character token means somebody re-encoded it. */
export const TOKEN_CHARS = 43;

/** Shape only. This regex decides nothing about MEANING — it is the same class
 *  of check as parsing a port out of a URL. It matters for one concrete reason:
 *  the value arrives from a path segment an attacker controls, and everything
 *  downstream (the hash, the store key) is safer when the input has a fixed
 *  alphabet and a fixed length. */
function isWellFormedToken(token: unknown): token is string {
  return typeof token === "string" && /^[A-Za-z0-9_-]{43}$/.test(token);
}

/** 15 lowercase alphanumerics — src/pb/wire.ts ID_ALPHABET. An email or a human
 *  name reaching an owner slot means a caller has confused "who is this" with
 *  "what do we call them", and the connection would bind to the wrong person. */
function isOwnerRowId(raw: unknown): raw is OwnerId {
  return typeof raw === "string" && /^[a-z0-9]{15}$/.test(raw);
}

/**
 * The store key: sha256 of the token, hex. WebCrypto, because a Worker has no
 * `node:crypto` — the spike's `createHash` is the one line of that file that
 * cannot cross.
 *
 * It also means untrusted input never reaches the query. Whatever a person puts
 * in the path, the value handed to the store is 64 hex characters — no quote,
 * no `%`, no case-folding trick.
 */
export async function tokenHandle(token: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token));
  let out = "";
  for (const b of new Uint8Array(digest)) out += b.toString(16).padStart(2, "0");
  return out;
}

/**
 * What a log line is allowed to say about a token: the first 12 hex characters
 * of its handle. Enough to correlate two lines about the same link, useless for
 * redeeming one, irreversible.
 *
 * NEVER log the token itself. A support transcript, a Sentry breadcrumb or a
 * `wrangler tail` with a whole token in it hands the reader an account binding.
 */
export async function tokenFingerprint(token: string): Promise<string> {
  if (typeof token !== "string" || token === "") return "link:none";
  return `link:${(await tokenHandle(token)).slice(0, 12)}`;
}

/**
 * Constant-time equality for two ASCII strings, byte-wise over the longer of
 * the two so the answer does not depend on WHERE the first difference is. The
 * same loop as index.ts `timingSafeEqual`; the lengths compared here are
 * structurally fixed (64 hex, 15 id characters), so nothing is learned from
 * the length term.
 *
 * Looking a row up BY handle makes this look redundant. It is not: the store is
 * an interface over D1, where the row that comes back is whatever the query
 * matched — a COLLATE NOCASE column, a stray LIKE, a trimmed key or a cache
 * returning a near neighbour all produce a row whose handle is not the one
 * asked for. This is the line that refuses it.
 */
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

/** Our link, per the spec: `anticipy.ai/c/{token}`. */
export function connectUrl(token: string, base: string = CONNECT_URL_BASE): string {
  return `${base.replace(/\/+$/, "")}/${token}`;
}

/**
 * Where the vendor sends the browser back.
 *
 * The token is on it because the callback is the only success signal the vendor
 * offers, and by then the token is already spent — `/go` claims it BEFORE the
 * vendor ever sees this URL, so a copy of it in a vendor log or a Referer
 * header cannot START a connection, only finish the one it belongs to, and only
 * inside the owner's own signed-in session.
 *
 * `state` is the phone's opaque attempt id (ConnectHandoff.callbackURL). It
 * rides out and back so the app can bind the callback to the one attempt it
 * started; it is never the owner id, an email or an alias, because another
 * company's server reads this URL.
 */
export function callbackUrl(
  token: string, base: string = CONNECT_URL_BASE, state?: string | null,
): string {
  const url = `${connectUrl(token, base)}/done`;
  return state ? `${url}?state=${encodeURIComponent(state)}` : url;
}

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

/**
 * The phone's opaque-token alphabet, copied from ConnectHandoff.isOpaqueToken
 * so the two halves agree about what a `state` may be. A UUID is the normal
 * value. It is validated because it is reflected into a hidden form field, into
 * a URL another company reads, and into a deep link — three places where an
 * unvalidated string is somebody else's injection point.
 */
function checkedState(raw: unknown): string | null {
  if (typeof raw !== "string") return null;
  const s = raw.trim();
  if (s === "" || s.length > 128) return null;
  return /^[A-Za-z0-9._~:%-]+$/.test(s) ? s : null;
}

// ===========================================================================
// THE PURE CORE — ported from spike/two-hands/src/connections/links.ts.
// If a shared connections module lands, this section is DELETED and imported.
// ===========================================================================

type Located =
  | { kind: "row"; row: StoredLink }
  | { kind: "dead" }
  | { kind: "signed-out" }
  | { kind: "wrong-user" };

// FROZEN, and shared. These are returned to callers, and ESM is always strict
// mode, so a handler that tried to patch a field on the answer it got back
// would throw instead of quietly rewriting the answer every LATER caller
// receives. A shared mutable "expired" object is a one-line path to a redeem
// that returns "ok".
const DEAD: Located = Object.freeze({ kind: "dead" });
const SIGNED_OUT: Located = Object.freeze({ kind: "signed-out" });
const WRONG_USER: Located = Object.freeze({ kind: "wrong-user" });

/**
 * THE ORDER OF THESE CHECKS IS THE PRIVACY MODEL. Read it before changing one.
 *
 * 1. NO SESSION, NO ANSWER — and this check comes first, before the token is
 *    even parsed. A caller who has not proved they are anybody gets
 *    `signed-out` for every token there is: live, expired, spent, forged,
 *    malformed, or somebody else's. Nothing else in this function runs for
 *    them, so the STORE stays out of the anonymous path and the same fact
 *    cannot be read off the round trip with a stopwatch instead of a status
 *    code.
 *
 * 2. NOT-A-TOKEN, NO-SUCH-ROW and EXPIRED collapse into one answer, `dead`.
 *    That is what keeps a SIGNED-IN caller from being told which strings are
 *    real either: a genuine expired token and a made-up one give back the
 *    identical object.
 *
 * 3. Expiry is checked BEFORE the owner. If the owner check came first, a
 *    real-but-expired token would answer "wrong-user" forever, which tells an
 *    interceptor the token was genuine — permanently, and long after it could
 *    do anything. The cost is small and is paid by the owner, not by an
 *    attacker: a link they used and come back to an hour later reads "expired"
 *    rather than "already used".
 *
 * 4. `already-used` is NOT decided here at all. The used bit is the one field
 *    that changes under a race, so reading it and acting on it is exactly the
 *    bug this module exists to avoid. `redeem` asks the store's compare-and-set
 *    and believes only that; the view reads it only to draw a page it is not
 *    going to consume.
 *
 * A SIGNED-IN STRANGER still gets `wrong-user` rather than `dead`, deliberately:
 * they have proved which owner they are, so the fact leaks to a known,
 * revocable account rather than to nobody — and the page has to be able to say
 * "you're signed in as someone else" or a household sharing a laptop can never
 * be told why the link failed.
 */
async function locate(
  token: unknown,
  signedInAs: unknown,
  now: number,
  store: ConnectLinkStore,
  deadline: (row: StoredLink) => number,
): Promise<Located> {
  if (!isOwnerRowId(signedInAs)) return SIGNED_OUT;

  if (!isWellFormedToken(token)) return DEAD;
  const handle = await tokenHandle(token);
  const row = await store.read(handle);
  if (!row) return DEAD;
  if (!constantTimeEqual(handle, row.token_handle)) return DEAD;
  if (now >= deadline(row)) return DEAD;

  if (!constantTimeEqual(signedInAs, row.user_id)) return WRONG_USER;

  return { kind: "row", row };
}

/**
 * Is the row a WRITE handed back the row the write was aimed at?
 *
 * The handle is the primary key, so it is the answer on its own; the owner and
 * the toolkit are checked too because a store that assembles a row from a join
 * can get the key right and the payload wrong, and those are the two fields
 * that decide whose account gets connected to what.
 */
function isTheSameRow(asked: StoredLink, answered: StoredLink): boolean {
  if (!constantTimeEqual(asked.token_handle, answered.token_handle)) return false;
  if (!constantTimeEqual(asked.user_id, answered.user_id)) return false;
  return asked.toolkit === answered.toolkit;
}

/** The deadline for every leg except the callback: the link's own TTL. Dead AT
 *  the instant, not after it — `>` would leave a one-millisecond live window no
 *  test would cover and no reader would expect. */
const ttlDeadline = (row: StoredLink): number => row.expires_at;

/** The callback's deadline. An UNCLAIMED row is already dead here: a `/done`
 *  for a token that never went through `/go` is either out of order or forged,
 *  and either way there is no vendor round trip it could be completing. It
 *  collapses into `dead` with the unknown tokens, so it is not an oracle. */
const callbackDeadline = (row: StoredLink): number =>
  row.used_at === null ? Number.NEGATIVE_INFINITY : row.used_at + CALLBACK_WINDOW_MS;

export interface ConnectLink {
  token: string;
  user_id: OwnerId;
  toolkit: string;
  alias: AccountAlias | null;
  expires_at: number;
  used_at: number | null;
}

/**
 * Four states, and only the first carries anything.
 *
 * `wrong-user`, `expired` and `already-used` are deliberately empty. Attaching
 * the toolkit to `wrong-user` — so the page could say "this Notion link isn't
 * yours" — would tell whoever intercepted the text which app the owner is
 * connecting, which is a fact about the owner they were not given a link for.
 */
export type RedeemResult =
  | { outcome: "ok"; link: ConnectLink }
  | { outcome: "expired" }
  | { outcome: "already-used" }
  | { outcome: "wrong-user" };

const EXPIRED: RedeemResult = Object.freeze({ outcome: "expired" });
const ALREADY_USED: RedeemResult = Object.freeze({ outcome: "already-used" });
const WRONG_USER_RESULT: RedeemResult = Object.freeze({ outcome: "wrong-user" });

/**
 * Spend the token. The only function that consumes one.
 *
 * SIGNED OUT IS `wrong-user`, on purpose: nobody is not the owner. The route
 * answers a missing session with the sign-in page before it ever gets here, so
 * the person sees an instruction rather than a rejection — and, critically, an
 * unauthenticated request never reaches the compare-and-set, so it cannot burn
 * a link somebody else is about to tap.
 *
 * THE USED BIT IS NOT READ. Not once. The row `locate` returned is advisory
 * about it: on D1 that read may be served by a replica seconds behind, and a
 * redeem trusting a stale `used_at: null` would hand out a second "ok" for a
 * spent token, while one trusting a stale `used_at: <time>` would refuse a
 * token nobody used. The compare-and-set is the only authority, and it is the
 * same authority for both mistakes.
 */
export async function redeem(
  token: string,
  opts: { signedInAs: unknown; store: ConnectLinkStore; now: number },
): Promise<RedeemResult> {
  const found = await locate(token, opts.signedInAs, opts.now, opts.store, ttlDeadline);
  if (found.kind === "dead") return EXPIRED;
  if (found.kind === "signed-out") return WRONG_USER_RESULT;
  if (found.kind === "wrong-user") return WRONG_USER_RESULT;

  const claim = await opts.store.claim(found.row.token_handle, opts.now);
  if (!claim.won) {
    // No row at all means it went away between the read and the write; that is
    // the unknown-token answer, not the used-token answer.
    return claim.row === null ? EXPIRED : ALREADY_USED;
  }

  // THE STORE WON — BUT ON WHICH ROW? The same D1 reasons `locate` checks for
  // do not stop applying because the statement was an UPDATE, and this is the
  // path whose answer decides which owner `/go` opens a vendor flow for — an
  // unchecked neighbouring row here is a vendor authorization in a stranger's
  // name, started from the owner's own browser. The claim already wrote, so a
  // refusal leaves the link spent: a store answering wrongly is not a reason to
  // hand out a second live link.
  if (claim.row !== null && !isTheSameRow(found.row, claim.row)) return EXPIRED;

  // Every field but `used_at` comes from the row LOCATE verified, not from the
  // row the write handed back, so a store that wins without returning a row is
  // still serviceable.
  return {
    outcome: "ok",
    link: {
      token,
      user_id: found.row.user_id,
      toolkit: found.row.toolkit,
      alias: found.row.alias,
      expires_at: found.row.expires_at,
      used_at: claim.row?.used_at ?? opts.now,
    },
  };
}

/** GET /c/{token}. NOTHING here consumes the token: a person who opens the page
 *  and thinks better of it must still be able to tap it later, and a link
 *  prefetcher must not be able to burn it. */
export type ConnectPageView =
  | {
      state: "ok";
      toolkit: ToolkitMeta;
      alias: AccountAlias | null;
      sentences: string[];
      expires_at: number;
    }
  /** Carries NOTHING. Before a session exists we cannot tell the owner from
   *  whoever is holding their phone, so naming the app here would print the
   *  answer above the lock screen. It is also the answer to EVERY token a
   *  signed-out caller can present. */
  | { state: "sign-in-required" }
  | { state: "expired" }
  | { state: "already-used" }
  | { state: "wrong-user" };

export async function connectPageView(
  token: string,
  opts: { signedInAs: unknown; store: ConnectLinkStore; provider: Pick<CatalogProvider, "toolkit">;
          words: PermissionWords; now: number },
): Promise<ConnectPageView> {
  const found = await locate(token, opts.signedInAs, opts.now, opts.store, ttlDeadline);
  if (found.kind === "dead") return { state: "expired" };
  if (found.kind === "signed-out") return { state: "sign-in-required" };
  if (found.kind === "wrong-user") return { state: "wrong-user" };
  // Read-only, so the used bit may be believed here: the worst a stale replica
  // can do is draw the wrong page for the owner, and the tap that follows still
  // goes through the compare-and-set in `redeem`.
  if (found.row.used_at !== null) return { state: "already-used" };

  // Deliberately NOT caught. Nothing has been consumed yet, so a catalog blip
  // is a retry — and swallowing it into a "state" would teach the page to
  // render an app with no name.
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
 * two values that fit the type are `[]` and a made-up sentence. This file
 * cannot audit the WORDS (that is the words module's job, with a model), but it
 * can refuse to publish silence: an `ok` page carrying an empty list renders a
 * consent screen with a button and no claims above it, and it looks exactly
 * like a page that finished loading. A person cannot consent to nothing.
 *
 * A blank among good ones is refused too, not filtered: quietly dropping one of
 * three sentences shows the person less than they are about to agree to, which
 * is the same defect with better manners. HOW MANY there should be is
 * deliberately not checked — that is the words module's question, and a count
 * rule here would be an outage the first time a one-scope toolkit arrives.
 */
function checkedSentences(sentences: unknown, slug: string): string[] {
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

/**
 * The tap. This is where — and the only place where — the vendor link is asked
 * for, which is the whole correction of 2026-09-05.
 *
 * CLAIM FIRST, THEN AUTHORIZE, and the order is not an accident. Reversed, two
 * concurrent taps would both open a connection request at the vendor and only
 * one would be handed back; the loser's request stays live at the vendor with
 * nothing on our side tracking it. Claiming first guarantees exactly one
 * `authorize` per token, ever.
 *
 * The price is paid when the vendor fails: the token is already spent and stays
 * spent. That is the correct direction to fail. Un-spending it on an error
 * would hand anyone who can make the vendor time out unlimited attempts at a
 * link that was supposed to work once — and a spent link costs the owner one
 * tap on "send me a new one", while a re-usable one costs them an account
 * binding.
 */
export async function connectPageGo(
  token: string,
  opts: { signedInAs: unknown; store: ConnectLinkStore; provider: Pick<CatalogProvider, "authorize">;
          baseUrl: string; state: string | null; now: number },
): Promise<ConnectPageGo> {
  // Before the compare-and-set, so an unauthenticated request cannot spend a
  // link. Otherwise anyone holding an intercepted token could burn it from a
  // signed-out browser and the owner's own tap would find it used.
  if (!isOwnerRowId(opts.signedInAs)) return { state: "sign-in-required" };

  const spent = await redeem(token, {
    signedInAs: opts.signedInAs, store: opts.store, now: opts.now,
  });
  if (spent.outcome !== "ok") return { state: spent.outcome };

  const link = spent.link;
  let redirectUrl: unknown;
  try {
    const authorized = await opts.provider.authorize(link.user_id, link.toolkit, {
      callbackUrl: callbackUrl(token, opts.baseUrl, opts.state),
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
  // "undefined" would put the person on a broken page and burn the link with no
  // explanation.
  if (typeof redirectUrl !== "string" || redirectUrl.trim() === "") {
    return { state: "provider-unavailable" };
  }

  return { state: "ok", redirectUrl };
}

/** GET /c/{token}/done — the vendor's callback, and the ONLY moment we ever
 *  learn that a connection exists. */
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
   *  not finish; do not guess at why. */
  | { state: "not-connected" }
  /** The vendor could not be ASKED whether the account is this owner's. Not a
   *  failed connect: the account may well exist, we simply have no evidence,
   *  and recording on no evidence is the failure below. Nothing is written,
   *  nothing is consumed, and a refresh retries. */
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

/**
 * Record the connection.
 *
 * THE WORST FAILURE IN THE PRODUCT IS HERE, so read the next sentence twice:
 * `user_id` comes from the STORED ROW — bound at mint time to an id that passed
 * the owner-row-id check — and never from this request. There is no parameter
 * on this function through which a caller could name an owner, which is the
 * structural half; the signed-in session is compared to the row's owner rather
 * than trusted, which is the other half. A callback that could name its own
 * owner is one operator's mailbox serving everybody, arrived at through a query
 * string.
 *
 * FAIL CLOSED. A missing status, an unrecognised status or a missing account id
 * are all `not-connected`, and nothing is written. Recording a connection that
 * did not happen leaves a row the router will route to and the ledger will
 * count, and the first the owner hears of it is a step that fails.
 *
 * AND `connected_account_id` IS CONFIRMED, NOT COPIED. The spike's own docstring
 * used to claim writing it verbatim "cannot bind one person's mailbox to
 * another" — that was false, which makes it worse than no comment at all.
 * `user_id` says who WE think this is; `connected_account_id` is the VENDOR's
 * handle for whichever credential actually answers, and it arrives on a query
 * string a browser can edit. Copied verbatim it writes "this owner's mail is
 * <somebody else's account>", and the first step that runs against that row
 * reaches into another person's mailbox holding our key. Same failure, other
 * end of the same table.
 *
 * So the account is checked against the vendor's own list for THIS owner —
 * `connections(user)`, scoped by the row's owner and never by the request — and
 * it must appear there on this toolkit or nothing is written. Two shapes are
 * refused rather than filtered: an entry carrying a different `user_id` means
 * the scoping did not hold, and an entry on a different toolkit would file a
 * calendar credential under the mail row. Status is deliberately NOT matched —
 * the vendor's own status races with the callback reporting it, and the
 * callback already carries the vendor's word for success.
 *
 * THE RESIDUAL RISK, WRITTEN DOWN RATHER THAN LEFT FOR SOMEBODY TO FIND. A
 * concurrent refresh that loses the lease answers `connected, recorded: false`
 * on the winner's behalf; if the winner's write then fails, that one page said
 * "connected" about a row that does not exist yet. The lease is handed back, so
 * the next callback in the hour-long window writes it and the page self-heals.
 */
export async function connectPageDone(
  token: string,
  params: DoneParams,
  opts: { signedInAs: unknown; store: ConnectLinkStore;
          provider: Pick<CatalogProvider, "connections">;
          onConnected: (c: Connection) => Promise<void>;
          successStatus?: string; now: number },
): Promise<ConnectPageDone> {
  const found = await locate(token, opts.signedInAs, opts.now, opts.store, callbackDeadline);
  if (found.kind === "dead") return { state: "expired" };
  if (found.kind === "signed-out") return { state: "sign-in-required" };
  if (found.kind === "wrong-user") return { state: "wrong-user" };

  const success = opts.successStatus ?? CALLBACK_SUCCESS;
  const accountId = typeof params?.connectedAccountId === "string"
    ? params.connectedAccountId.trim()
    : "";
  // A string compare against ONE configured literal from a machine's closed
  // enum. Not law 1's territory: no human wrote this word and nothing about
  // what a PERSON meant is being decided. The day it starts reading prose it is
  // a violation.
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
    // Nothing has been consumed, so this is a retry rather than a verdict.
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
  // prefetched, so exactly one caller may do the writing — but taking the lease
  // is a promise to write, not proof the write happened. Reading it as proof is
  // what turned one failed `onConnected` into a page that said "connected"
  // forever with no row anywhere.
  const lease = await opts.store.complete(found.row.token_handle, opts.now);
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
        await opts.store.release(found.row.token_handle, opts.now);
      }
    } catch {
      // Nothing to add. The lease stays taken, refreshes read as `connected,
      // recorded: false`, and a fresh link is then the only way through — which
      // is exactly why `release` is on the store interface.
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
 * slug the link was minted with. Case and padding on the slug are plumbing. The
 * ACCOUNT ID is compared case-sensitively: it is an opaque primary key, and
 * folding `CA_X` onto `ca_x` would be inventing a match.
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

// ===========================================================================
// THE HTTP HALF — this file's own work
// ===========================================================================

/**
 * Who is signed in, in this browser, right now?
 *
 * Two carriers, one verifier. The phone sends the `owners` auth token in
 * `Authorization`; a browser opening a texted link cannot set a header, so it
 * presents the same token in the session cookie. Both go through the same
 * `verifyToken` the data API uses, so a deleted account's token stops working
 * here for free (the row is gone, so there is no tokenKey, so nothing verifies).
 *
 * A TOKEN ON THE QUERY STRING IS NOT ACCEPTED, and that absence is the point:
 * `/c/{token}?s=<account token>` would put a live credential in browser
 * history, in our own request logs, and in any screenshot of the URL bar — and
 * this is the one page in the product that then redirects to another company.
 *
 * Fails closed and NEVER throws: a route that 500s on a malformed cookie is a
 * denial of service handed to whoever can set one.
 */
export async function whoIsSignedIn(request: Request, env: ConnectEnv): Promise<OwnerId | null> {
  const raw = bearerHeader(request) ?? sessionCookie(request);
  if (!raw) return null;
  try {
    const v = await verifyToken(env, raw);
    if (!v) return null;
    const id = String((v.row as Record<string, unknown>).id ?? "");
    return isOwnerRowId(id) ? id : null;
  } catch {
    return null;
  }
}

function bearerHeader(request: Request): string | null {
  const h = request.headers.get("Authorization");
  return h && h.trim() !== "" ? h : null;
}

/** One cookie out of the header, by exact name. Split on ";" and compare the
 *  whole name: a substring match would read `evil_anticipy_session` as ours. */
function sessionCookie(request: Request): string | null {
  const header = request.headers.get("Cookie");
  if (!header) return null;
  for (const part of header.split(";")) {
    const eq = part.indexOf("=");
    if (eq < 0) continue;
    if (part.slice(0, eq).trim() !== SESSION_COOKIE) continue;
    const value = part.slice(eq + 1).trim();
    return value === "" ? null : value;
  }
  return null;
}

/**
 * Is this POST from our own page?
 *
 * A single-use link is spendable by anybody who can make the owner's browser
 * POST to it while carrying their session — a hidden form on any site. Burning
 * it costs the owner the connect they were about to do, and starts a vendor
 * round trip they did not open. So a POST whose `Origin` names another site, or
 * whose `Sec-Fetch-Site` says cross-site, is refused BEFORE the compare-and-set.
 *
 * Absent headers are allowed rather than refused: a header that is simply not
 * sent is not evidence of anything, and refusing on absence turns a client
 * quirk into "connecting is broken for that person". The control for this
 * decision is in the suite — a same-origin POST with an Origin header still
 * works, or this guard would be an outage rather than a guard.
 */
function isCrossSitePost(request: Request): boolean {
  const site = request.headers.get("Sec-Fetch-Site");
  if (site && site.toLowerCase() === "cross-site") return true;
  const origin = request.headers.get("Origin");
  if (!origin || origin === "null") return false;
  try {
    return new URL(origin).origin !== new URL(request.url).origin;
  } catch {
    // An unparseable Origin is a claim we cannot read. On a state-changing POST
    // that is the refusing direction.
    return true;
  }
}

const esc = (raw: unknown): string =>
  String(raw ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

/** A catalog logo is a URL another company controls. https only, and no other
 *  scheme: `javascript:` and `data:` in an attribute on OUR origin — the origin
 *  the session cookie lives on — is somebody else's code running in the
 *  owner's session. A logo we cannot vouch for is simply not drawn. */
function httpsOnly(raw: unknown): string | null {
  if (typeof raw !== "string" || raw.trim() === "") return null;
  try {
    const u = new URL(raw.trim());
    return u.protocol === "https:" ? u.toString() : null;
  } catch {
    return null;
  }
}

/**
 * The shell. Every /c/ response is one of these, and every one of them carries
 * the same headers:
 *
 *   Cache-Control: no-store   a consent page left in a shared browser's cache
 *                             is the account-binding screen handed to the next
 *                             person to open that tab.
 *   CSP default-src 'none'    no scripts at all, from anywhere, ever. If the
 *                             escaping above were ever wrong, an injected
 *                             string still cannot run. form-action 'self' keeps
 *                             the Connect button pointed at us; frame-ancestors
 *                             'none' is the clickjacking answer — an invisible
 *                             framed connect page plus one tricked click is an
 *                             account binding.
 *   Referrer-Policy           no-referrer, so the token in our URL is not sent
 *                             to the vendor we redirect to.
 *   X-Robots-Tag              a connect page must never be indexed.
 */
function page(status: number, title: string, bodyHtml: string): Response {
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
  img.logo { width: 56px; height: 56px; border-radius: 12px; display: block; margin: 0 0 1rem; }
  ul { padding-left: 1.1rem; margin: 1rem 0; }
  li { margin: .4rem 0; }
  p.fine { opacity: .7; font-size: .9rem; }
  button { font: inherit; font-weight: 600; padding: .85rem 1.25rem; width: 100%;
           border: 0; border-radius: 12px; cursor: pointer; }
  a.later { display: inline-block; margin-top: 1rem; }
</style>
${bodyHtml}
</html>`;
  return new Response(html, {
    status,
    headers: {
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

/**
 * The one page that matters.
 *
 * Everything visible comes from the catalog row and the injected sentences:
 * there is no app name, no logo and no scope word typed into this file. The
 * optional line is not decoration — "connecting is always optional and every
 * ask says so in one sentence" is a product rule, and this is the sentence.
 */
function viewPage(token: string, v: Extract<ConnectPageView, { state: "ok" }>,
                  state: string | null): Response {
  const name = v.toolkit.name?.trim() ? v.toolkit.name : v.toolkit.slug;
  const logo = httpsOnly(v.toolkit.logo);
  const which = v.alias ? ` (your ${esc(v.alias)} account)` : "";
  const body = `<body>
${logo ? `<img class="logo" src="${esc(logo)}" alt="">` : ""}
<h1>Connect your ${esc(name)}${which}</h1>
${v.toolkit.description?.trim() ? `<p>${esc(v.toolkit.description)}</p>` : ""}
<p>Here's what Anticipy would be able to do:</p>
<ul>
${v.sentences.map((s) => `  <li>${esc(s)}</li>`).join("\n")}
</ul>
<form method="post" action="/c/${esc(token)}/go">
${state ? `  <input type="hidden" name="state" value="${esc(state)}">\n` : ""}  <button type="submit">Connect ${esc(name)}</button>
</form>
<a class="later" href="https://anticipy.ai/">Skip for now</a>
<p class="fine">This is optional — Anticipy works fine without it. You can turn it off any time in Settings. This link works for ten minutes and only for you.</p>
</body>`;
  return page(200, `Connect your ${name}`, body);
}

/** A page with no app on it: one heading, one sentence, nothing that names
 *  anything. Used for every state where telling the caller more would be
 *  telling a stranger more. */
function plainPage(status: number, heading: string, sentence: string,
                   back?: { href: string; label: string }): Response {
  const body = `<body>
<h1>${esc(heading)}</h1>
<p>${esc(sentence)}</p>
${back ? `<p><a href="${esc(back.href)}">${esc(back.label)}</a></p>` : ""}
</body>`;
  return page(status, heading, body);
}

/**
 * Back to the app, carrying what the app needs to stop waiting.
 *
 * The status tokens are OURS (ConnectHandoff.statusConnected / statusFailed) and
 * `state` is the phone's own attempt id, echoed so the callback binds to the one
 * attempt it started. The toolkit is taken from the STORED ROW, never from the
 * query string.
 *
 * It is offered ONLY on states where the session already proved it is the row's
 * owner. On `expired`, `wrong-user` and `sign-in-required` there is no deep link
 * at all: the toolkit is exactly the fact those pages must not disclose, and a
 * link naming it would put it in front of whoever intercepted the text.
 */
function appLink(toolkit: string, status: string,
                 extra: { state?: string | null; accountId?: string | null; reason?: string }): string {
  const q = new URLSearchParams();
  if (extra.state) q.set("state", extra.state);
  q.set("status", status);
  if (extra.accountId) q.set("connected_account_id", extra.accountId);
  if (extra.reason) q.set("reason", extra.reason);
  return `${APP_SCHEME}://${APP_CALLBACK_HOST}/${encodeURIComponent(toolkit)}?${q.toString()}`;
}

// The five sentences a person can be shown when a link does not work. They name
// no app, and the first three are identical for every token — which is the
// oracle rule, expressed as copy.
const SIGN_IN_HEADING = "Sign in to finish";
const SIGN_IN_LINE =
  "Sign in to Anticipy in this browser, then open this link again. It works for ten minutes.";
const EXPIRED_HEADING = "That link has expired";
const EXPIRED_LINE = "Links last ten minutes. Ask Anticipy for a new one and it'll send another.";
const USED_HEADING = "That link has been used";
const USED_LINE = "Each link works once. Ask Anticipy for a new one and it'll send another.";
const WRONG_USER_HEADING = "You're signed in as someone else";
const WRONG_USER_LINE =
  "This link was made for a different Anticipy account. Sign in as that account and open it again.";

/** The four states that must look the same to a stranger, drawn in one place so
 *  they cannot drift apart in five. */
function refusalPage(state: "sign-in-required" | "expired" | "already-used" | "wrong-user"): Response {
  switch (state) {
    case "sign-in-required": return plainPage(401, SIGN_IN_HEADING, SIGN_IN_LINE);
    case "expired":          return plainPage(410, EXPIRED_HEADING, EXPIRED_LINE);
    case "already-used":     return plainPage(410, USED_HEADING, USED_LINE);
    case "wrong-user":       return plainPage(403, WRONG_USER_HEADING, WRONG_USER_LINE);
  }
}

const unwired = (): Response =>
  plainPage(503, "Connecting isn't switched on here",
    "Anticipy can't set this up right now. Nothing has changed on your account.");

/**
 * The entry point index.ts registers.
 *
 * `deps` is injectable so the suite can drive the real handlers with a store it
 * controls; production passes nothing and gets the installed wiring.
 */
export async function connectRoute(
  request: Request, env: ConnectEnv, deps?: ConnectDeps,
): Promise<Response> {
  const url = new URL(request.url);
  const route = parseConnectPath(url.pathname);
  // Not one of our three shapes. 404, and nothing about tokens is implied: the
  // alphabet and the length are both public, so an attacker learns nothing here
  // they could not compute offline.
  if (!route) return plainPage(404, "Not found", "There's nothing at this address.");

  const method = request.method === "HEAD" ? "GET" : request.method;
  const wants = route.leg === "go" ? "POST" : "GET";
  // A GET on /go would let a link prefetcher, an <img> tag or a browser's
  // address-bar preload SPEND the owner's single-use link before they ever tap
  // it. A POST on the page itself is not a route at all.
  if (method !== wants) {
    return new Response(null, { status: 405, headers: { allow: wants, "cache-control": "no-store" } });
  }

  const wired = deps ?? WIRING(env);
  if (!wired) {
    console.log(`connect ${route.leg}: 503 — no connect wiring installed on this Worker; `
      + "the link store, the catalog and the sentence writer are all unset, so no "
      + "connect page can be drawn. See installConnectWiring().");
    return unwired();
  }

  const now = wired.now ? wired.now() : Date.now();
  const baseUrl = wired.baseUrl ?? env.CONNECT_BASE_URL ?? CONNECT_URL_BASE;
  const state = checkedState(url.searchParams.get("state"));

  if (route.leg === "view") return await handleView(request, env, wired, route.token, now, state);
  if (route.leg === "go")   return await handleGo(request, env, wired, route.token, now, baseUrl);
  return await handleDone(request, env, wired, route.token, now, state, url);
}

async function handleView(
  request: Request, env: ConnectEnv, deps: ConnectDeps,
  token: string, now: number, state: string | null,
): Promise<Response> {
  const who = await whoIsSignedIn(request, env);
  let view: ConnectPageView;
  try {
    view = await connectPageView(token, {
      signedInAs: who, store: deps.store, provider: deps.provider, words: deps.words, now,
    });
  } catch (err) {
    // The catalog was unreachable, or the sentences came back empty. Nothing has
    // been consumed, so this is a retry — and it must NOT degrade into a page
    // with an unnamed app or a blank list of claims above a Connect button.
    console.log(`connect view: ${await tokenFingerprint(token)} could not be drawn — `
      + `${(err as Error)?.message ?? "unknown"}`);
    return plainPage(503, "One moment",
      "Anticipy couldn't load this just now. Refresh in a moment — nothing has changed.");
  }
  if (view.state !== "ok") return refusalPage(view.state);
  return viewPage(token, view, state);
}

async function handleGo(
  request: Request, env: ConnectEnv, deps: ConnectDeps,
  token: string, now: number, baseUrl: string,
): Promise<Response> {
  // Before the session is even read, and long before the compare-and-set.
  if (isCrossSitePost(request)) {
    console.log(`connect go: ${await tokenFingerprint(token)} refused — cross-site POST`);
    return plainPage(403, "That didn't come from here",
      "Open your Anticipy link again and tap Connect on the page itself.");
  }

  const who = await whoIsSignedIn(request, env);
  // The hidden field the page rendered, carrying the phone's attempt id. Read
  // from the body rather than the query so it survives the form post; anything
  // that is not the phone's opaque-token shape is dropped rather than reflected.
  const state = checkedState(await formField(request, "state"));

  const go = await connectPageGo(token, {
    signedInAs: who, store: deps.store, provider: deps.provider, baseUrl, state, now,
  });

  if (go.state === "ok") {
    // 303, and an EMPTY BODY. The vendor's URL exists in exactly one place in
    // this Worker's output — this header — and never in a page, never in a text,
    // never in a log line. `Referrer-Policy: no-referrer` above keeps our own
    // token off the request the browser makes next.
    console.log(`connect go: ${await tokenFingerprint(token)} spent, redirecting`);
    return new Response(null, {
      status: 303,
      headers: {
        location: go.redirectUrl,
        "cache-control": "no-store",
        "referrer-policy": "no-referrer",
      },
    });
  }
  if (go.state === "provider-unavailable") {
    console.log(`connect go: ${await tokenFingerprint(token)} spent but the catalog did not answer`);
    // The token is gone and stays gone; say so rather than offering it again.
    return plainPage(503, "That didn't go through",
      "Ask Anticipy for a new link and give it another try. Nothing has changed on your account.");
  }
  return refusalPage(go.state);
}

async function handleDone(
  request: Request, env: ConnectEnv, deps: ConnectDeps,
  token: string, now: number, state: string | null, url: URL,
): Promise<Response> {
  const who = await whoIsSignedIn(request, env);
  const done = await connectPageDone(token, {
    status: url.searchParams.get("status"),
    connectedAccountId: url.searchParams.get("connected_account_id"),
  }, {
    signedInAs: who, store: deps.store, provider: deps.provider,
    onConnected: deps.onConnected, successStatus: deps.successStatus, now,
  });

  switch (done.state) {
    case "connected": {
      const c = done.connection;
      const href = appLink(c.toolkit, APP_STATUS_CONNECTED,
        { state, accountId: c.connected_account_id });
      console.log(`connect done: ${await tokenFingerprint(token)} connected `
        + `(recorded=${done.recorded})`);
      const body = `<body>
<h1>Connected.</h1>
<p>Anticipy can use it from now on. You can turn it off any time in Settings.</p>
<p><a href="${esc(href)}">Back to Anticipy</a></p>
</body>`;
      return page(200, "Connected", body);
    }
    case "not-connected":
      return plainPage(200, "That didn't finish",
        "Nothing's connected yet. Ask Anticipy for a new link and give it another try.");
    case "could-not-confirm":
      return plainPage(503, "One moment",
        "Anticipy couldn't check that just now. Refresh this page in a moment — nothing has changed.");
    case "not-recorded":
      return plainPage(500, "Almost there",
        "Anticipy couldn't save that just now. Refresh this page and it'll finish.");
    default:
      return refusalPage(done.state);
  }
}

/** One field out of a form post. Never throws: a body that is not a form is
 *  simply no field, and a `/go` with no state is a `/go` with a weaker binding,
 *  not a 500. */
async function formField(request: Request, name: string): Promise<string | null> {
  const ct = request.headers.get("content-type") ?? "";
  if (!ct.includes("application/x-www-form-urlencoded") && !ct.includes("multipart/form-data")) {
    return null;
  }
  try {
    const form = await request.formData();
    const v = form.get(name);
    return typeof v === "string" ? v : null;
  } catch {
    return null;
  }
}
