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
 *   POST /c/{token}/skip   the other answer: "Skip for now", which is a WRITE
 *                          and is the only way a person's NO is ever recorded.
 *   GET  /c/{token}/done   the vendor's callback, which is the ONLY signal a
 *                          connection exists — Composio publishes no success
 *                          webhook, only `expired`.
 *
 * NOBODY COULD SAY NO, AND THAT IS WHY /skip EXISTS. Until 2026-09-06 this page
 * offered "Skip for now" as a BARE ANCHOR to the marketing site. It navigated
 * away and wrote nothing: `recordDecline` (connections/nudge.ts) had no caller
 * anywhere in the Worker, the snooze ladder the spec spends a page on (14 days,
 * then 45, then stop — page 24) could not be ENTERED by a human action, and the
 * person who tapped it was asked again at the next moment that scored high
 * enough. Forever. The decline half of the state machine was a diagram.
 *
 * IT IS A POST, FOR THE SAME REASON /go IS. A GET that writes is a write a link
 * prefetcher, an `<img>` tag or an address-bar preload performs on the person's
 * behalf — and a decline fired by a prefetcher silences an app nobody refused.
 * So /skip takes POST only, answers 405 with `Allow: POST` on anything else,
 * and runs the same cross-site refusal /go runs before it reads a session.
 *
 * IT DOES NOT SPEND THE LINK. A decline is not a redemption: somebody who taps
 * Skip and thinks better of it inside the ten minutes must still be able to tap
 * Connect. Exactly-once comes from the LADDER instead — a second POST onto a
 * row that is already declined and still snoozed is a no-op, so a double tap, a
 * refresh or a retry cannot walk somebody from L1 to L3 and stop the asks for
 * ten years.
 *
 * AND THE WAY OUT OF THE WALL. Every leg here needs a signed-in session, and the
 * browser that matters arrived by tapping a text and holds nothing — so what a
 * real person met on 2026-09-06, on a link minted on production and opened in
 * Chrome, was a page reading "sign in to Anticipy in this browser" that linked
 * to NOTHING. There is no web sign-in on this Worker and they are holding a
 * phone. The refusal now carries the one door that exists: `/c/{token}/code`
 * (routes/connect_auth.ts), which texts a code to the number on the account.
 * It is offered on all three legs, `/done` included, and on that one it is
 * offered HONESTLY RATHER THAN HOPEFULLY. `checkCode` will not mint a session
 * for a link that has already been spent (connect_auth.ts, deliberately: a link
 * picked up AFTER the owner used it must not still be an account door for an
 * hour), so a browser that lost its cookie during the vendor round trip taps
 * the door, reads "check your phone" and no text arrives. That case is a real
 * remaining hole — the connection exists at the vendor, has no row here, and no
 * webhook will ever mention it again — and it belongs to whoever revisits that
 * rule, not to this page. The alternative here is a wall, which recovers
 * nothing either and says less.
 *
 * THE DOOR IS NOT AN ORACLE, and that is why it is drawn where it is. The offer
 * is minted from the token in the caller's own URL and from nothing else; it is
 * identical for a live link, an expired one, a spent one, a stranger's and a
 * string somebody invented, because `locate` has already settled the session
 * before anything is looked up and `/c/{token}/code` never reads the store
 * either. The suite pins that as five responses that are one response, byte for
 * byte once the caller's own token is normalised out.
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
import { FORBIDDEN_TERMS, forbiddenTermIn } from "../connections/words.ts";
import {
  waitBudgetMs, waitForConnection, type WaitEnv,
} from "../connections/wait.ts";
/**
 * THE LADDER, IMPORTED AND NEVER RE-IMPLEMENTED.
 *
 * `recordDecline` is the spec's state machine on page 24 — level 1 then 2 then
 * 3, 14 days then 45 then stop, and the onboarding exception that makes a
 * skipped setup card a SEVEN-day soft snooze instead of a real decline. It is
 * pure, it is nudge.ts's, and it stays nudge.ts's: a second copy of those
 * numbers in this file would be a second answer to "how long did they ask to be
 * left alone for", and the two would disagree the first time either was tuned.
 *
 * THE IMPORT RUNS BACKWARDS THROUGH AN EXISTING EDGE, deliberately and with the
 * reason written down. connections/nudge.ts already imports THIS file for the
 * token plumbing (`tokenHandle`, `connectUrl`, `LINK_TTL_MS`, `TOKEN_CHARS`),
 * so this line closes a cycle. It is safe because every one of nudge.ts's uses
 * of this file is INSIDE a function body — no top-level constant there is
 * computed from one of ours — so whichever module the entry point reaches
 * first, both are fully evaluated before any request runs. The suite loads
 * connect.ts first and nudge.ts first, in two different files, which is what
 * makes that a measured fact rather than a hope.
 */
import { recordDecline } from "../connections/nudge.ts";
// TYPE ONLY, and erased before this file is bundled or run — the same choice
// nudge.ts and store.ts make. `connect_nudges` rows have exactly one declared
// shape and it is the contract's.
import type { ConnectNudge } from "../../../../spike/two-hands/src/connections/contract.ts";

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
/** And the third one the phone already understands: `ConnectHandoff.parseDone`
 *  maps `status=cancelled` to `.cancelled`, so the Skip page can hand somebody
 *  who arrived from the app a way back into it with no iOS change at all. It is
 *  never "failed": a person answering "not now" did not hit an error. */
const APP_STATUS_CANCELLED = "cancelled";

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
/**
 * THE DECLINE HALF OF THE STORE, and the only two methods in this file that
 * touch a table that is not `connect_links`.
 *
 * BOTH ARE OPTIONAL, and read the polarity before changing it. The store the
 * production wiring hands this file is `createD1Store(env)` (see
 * connections/wiring.ts `connectDeps`), which is the whole `ConnectionsStore`
 * and HAS both of these — so on a real Worker they are present and a Skip is
 * recorded. They are declared optional because this interface is also
 * implemented by narrower fakes (the suite's link-only store,
 * routes/connect_auth.ts's `links` port), and a required method would make
 * those a type error for a capability they have no business having.
 *
 * A STORE WITHOUT THEM RECORDS NOTHING AND SAYS SO. `recordSkip` answers
 * `not-recorded`, the page tells the person their answer was not saved rather
 * than claiming it was, and the log line names the wiring. That is the honest
 * direction: the failure this whole leg exists to fix is a Skip that LOOKS
 * recorded and is not.
 */
export interface DeclineStore {
  readNudge?(user: OwnerId | string, toolkit: string): Promise<ConnectNudge | null>;
  putNudge?(row: ConnectNudge): Promise<void>;
}

export interface ConnectLinkStore extends DeclineStore {
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

export type ConnectLeg = "view" | "go" | "skip" | "done";

export interface ConnectRoute {
  leg: ConnectLeg;
  token: string;
}

/** Which verb each leg takes. `go` and `skip` are the two that WRITE, and both
 *  are POST for the same reason: a GET that changes something is a change a
 *  prefetcher, an `<img>` tag or an address-bar preload makes on the person's
 *  behalf. Declared as a table rather than typed at each handler so a fourth
 *  leg cannot be added without answering the question. */
export const CONNECT_METHOD: Record<ConnectLeg, "GET" | "POST"> = {
  view: "GET",
  go: "POST",
  skip: "POST",
  done: "GET",
};

/**
 * `/c/{token}` → view, `/c/{token}/go` → go, `/c/{token}/skip` → skip,
 * `/c/{token}/done` → done.
 *
 * Anchored at both ends and restricted to the token alphabet, so `/c/../../x`
 * and a token with a slash in it are not routes at all. Returns null rather
 * than throwing: an unroutable path is a 404, not a 500.
 */
export function parseConnectPath(pathname: unknown): ConnectRoute | null {
  if (typeof pathname !== "string") return null;
  const m = /^\/c\/([A-Za-z0-9_-]{43})(?:\/(go|skip|done))?$/.exec(pathname);
  if (!m) return null;
  const leg: ConnectLeg = m[2] === "go" ? "go"
    : m[2] === "skip" ? "skip"
    : m[2] === "done" ? "done"
    : "view";
  return { leg, token: m[1] as string };
}

/**
 * The phone's opaque-token alphabet, copied from ConnectHandoff.isOpaqueToken
 * so the two halves agree about what a `state` may be. A UUID is the normal
 * value. It is validated because it is reflected into a hidden form field, into
 * a URL another company reads, and into a deep link — three places where an
 * unvalidated string is somebody else's injection point.
 *
 * EXPORTED, and it has to be. The state now crosses into routes/connect_auth.ts
 * — offer, send, box, redirect — and a second copy of this alphabet is a second
 * answer to "what may a state be": the day one of them drifts, a value one file
 * refuses is reflected by the other. connect_auth.ts imports THIS one, which is
 * the direction the dependency already runs.
 */
export function checkedState(raw: unknown): string | null {
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
  /**
   * `owner` and `toolkit` ride along ONLY so the background poll can be
   * started, and they come off the STORED ROW the redeem verified — never off
   * the request. Nothing renders them: the refusal states carry nothing on
   * purpose (naming the app to a caller who has not proved they are the owner
   * is the oracle this file exists to close), and the `ok` state is a 303 with
   * an empty body. They are here rather than re-read from the store in
   * `handleGo` because a second read is a second answer, and a link the poll
   * was started for must be the link that was actually spent.
   */
  | { state: "ok"; redirectUrl: string; owner: OwnerId; toolkit: string }
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

  return { state: "ok", redirectUrl, owner: link.user_id, toolkit: link.toolkit };
}

/**
 * ===========================================================================
 * THE DECLINE — "Skip for now", which is the only NO this product can hear.
 * ===========================================================================
 */

/**
 * What a decline does to the ladder, in four states, because "recorded",
 * "already recorded", "there was nothing to decline" and "we could not write it
 * down" are four different facts about somebody's answer and a boolean carries
 * two of them.
 *
 * `soft` is the spec's onboarding exception surfaced rather than inferred: page
 * 21 says a skipped setup card records a seven-day snooze and is "not a real
 * decline", and page 24 gives a real one fourteen days. They are different rows
 * and the caller must be able to tell which one it just wrote.
 */
export type DeclineOutcome =
  | { state: "recorded"; level: 1 | 2 | 3; snooze_until: number; soft: boolean }
  /** The ladder was already at this rung and the snooze is still running. A
   *  second tap, a refresh or a retry lands here and writes NOTHING. */
  | { state: "already-declined"; level: 1 | 2 | 3; snooze_until: number }
  /** This owner already has this app connected, so there is no ask to refuse.
   *  Declining here would replace a live `connected` row with `declined` and
   *  the router would stop using a connection the person still has. */
  | { state: "nothing-to-decline" }
  /** Nothing was written and the person must be told so. `why` is for the log
   *  and never for a page: it names our own wiring, not their account. */
  | { state: "not-recorded"; why: string };

/** The seed for an owner who has never been asked about this app at all —
 *  Settings' "Add an app", or an onboarding card for something no ask was ever
 *  sent about. `onboarding` is the SURFACE the skip came from, which is a fact
 *  about which screen was on the glass and not a reading of anything anybody
 *  said; it is the only thing that can make a seeded row a soft one. */
function seedNudge(user: OwnerId, toolkit: string, onboarding: boolean): ConnectNudge {
  return {
    user_id: user as ConnectNudge["user_id"],
    toolkit: toolkit as ConnectNudge["toolkit"],
    state: "never_asked",
    level: 0,
    snooze_until: null,
    trigger: onboarding ? "onboarding" : null,
    sent_at: null,
    acted_at: null,
    channel: null,
  };
}

/**
 * WRITE THE NO. One function, two surfaces — the connect page's Skip button and
 * the phone's own skip route (routes/connections_api.ts), which calls this
 * rather than repeating it. Two writers would be two ladders.
 *
 * THE MOMENT ON THE STORED ROW WINS, ALWAYS. `recordDecline` reads
 * `nudge.trigger` to decide whether this is the seven-day soft snooze or the
 * fourteen-day L1, and that trigger is what the ASK ENGINE wrote when it
 * decided to ask — never anything a client claimed. `onboarding` below can only
 * seed a row that does not exist yet; it cannot restamp one that does. That
 * asymmetry is the whole guard: without it a client could send `onboarding` on
 * every skip and shorten every snooze it ever wrote, which is an ask that comes
 * back sooner than the person asked for.
 *
 * AND THE OWNER IS AN ARGUMENT, NOT A FIELD ON THE ROW WE READ. The row that
 * comes back is compared to the owner it was asked for and to the app it was
 * asked about: a store that answered with a neighbouring row would otherwise
 * record one person's "no" against another person's app.
 */
export async function recordSkip(
  store: DeclineStore,
  who: { user_id: OwnerId; toolkit: string; at: number },
  opts: { onboarding: boolean },
): Promise<DeclineOutcome> {
  if (typeof store?.readNudge !== "function" || typeof store?.putNudge !== "function") {
    // A configuration failure, and it must never wear the costume of a recorded
    // decline. See DeclineStore.
    return {
      state: "not-recorded",
      why: "the store wired into this Worker cannot read or write a nudge row, so a "
        + "person's no has nowhere to go",
    };
  }

  let row: ConnectNudge | null;
  try {
    row = await store.readNudge(who.user_id, who.toolkit);
  } catch {
    return { state: "not-recorded", why: "the nudge row could not be read" };
  }

  if (row !== null && row !== undefined) {
    if (!constantTimeEqual(String(row.user_id ?? ""), who.user_id)) {
      return { state: "not-recorded", why: "the store answered with another owner's row" };
    }
    if (String(row.toolkit ?? "") !== who.toolkit) {
      return { state: "not-recorded", why: "the store answered with another app's row" };
    }
  }

  const current = row ?? seedNudge(who.user_id, who.toolkit, opts.onboarding);

  if (current.state === "connected") return { state: "nothing-to-decline" };

  // ALREADY SAID, STILL STANDING. The ladder advances once per ask, not once
  // per tap: a refresh, a double tap or a retried POST must not walk somebody
  // from "ask me in a fortnight" to "never ask me again".
  if (
    current.state === "declined"
    && current.acted_at !== null
    && typeof current.snooze_until === "number"
    && Number.isFinite(current.snooze_until)
    && who.at < current.snooze_until
    && current.level >= 1
  ) {
    return {
      state: "already-declined",
      level: current.level as 1 | 2 | 3,
      snooze_until: current.snooze_until,
    };
  }

  // "said_no", never "silence". They are different facts about a person and the
  // spec's timers get tuned from the difference: this one stamps `acted_at`
  // because somebody actually touched the glass.
  const next = recordDecline(current, who.at, "said_no");
  try {
    await store.putNudge(next);
  } catch {
    // The store refused the row — a bad level, an unreadable state, a missing
    // column. Nothing was written and the page must not pretend otherwise.
    return { state: "not-recorded", why: "the nudge row could not be written" };
  }
  return {
    state: "recorded",
    level: next.level as 1 | 2 | 3,
    snooze_until: Number(next.snooze_until),
    soft: next.trigger === "onboarding",
  };
}

/**
 * POST /c/{token}/skip.
 *
 * The same four refusals as every other leg and in the same order, because the
 * order IS the privacy model: a caller who has proved nothing gets
 * `sign-in-required` for every token there is, and expiry is settled before the
 * owner so a real-but-expired token never answers "wrong-user".
 *
 * THE USED BIT IS NOT CONSULTED. A link the owner already spent on Connect is
 * still their link, and a person who went to the vendor, backed out and came
 * back to tap Skip is telling us something we asked for. The idempotence that
 * matters is on the LADDER, not on the token.
 */
export type ConnectPageSkip =
  | { state: "noted"; toolkit: string; outcome: DeclineOutcome }
  | { state: "sign-in-required" }
  | { state: "expired" }
  | { state: "wrong-user" };

export async function connectPageSkip(
  token: string,
  opts: { signedInAs: unknown; store: ConnectLinkStore; now: number },
): Promise<ConnectPageSkip> {
  const found = await locate(token, opts.signedInAs, opts.now, opts.store, ttlDeadline);
  if (found.kind === "dead") return { state: "expired" };
  if (found.kind === "signed-out") return { state: "sign-in-required" };
  if (found.kind === "wrong-user") return { state: "wrong-user" };

  // THE OWNER AND THE APP COME OFF THE STORED ROW. There is no parameter on
  // this function through which a caller could name either.
  // NOT THE SETUP CARD, and this page can never claim to be one: onboarding's
  // own Skip is a card in the app and posts to its own route. A link minted FOR
  // an onboarding ask still gets the seven-day soft snooze — but because the
  // nudge row the ask engine wrote carries `trigger: onboarding`, not because
  // anything here said so. The row is the record of the moment; this is a page.
  const outcome = await recordSkip(
    opts.store,
    { user_id: found.row.user_id, toolkit: found.row.toolkit, at: opts.now },
    { onboarding: false },
  );
  return { state: "noted", toolkit: found.row.toolkit, outcome };
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
/**
 * WHO IS ASKING — the seam, and why it is a seam rather than an import.
 *
 * `whoIsSignedIn` below reads the account cookie, which is the only thing a
 * browser can have if it came from the iOS app. But the browser that matters
 * arrived by TAPPING A TEXT, in Safari, holding nothing — and for that one
 * there is a second way to be somebody: the phone code in
 * `routes/connect_auth.ts`, which mints a cookie scoped to a single link.
 *
 * That file imports THIS one (for the store types and the page shell), so this
 * one cannot import it back without a cycle. Hence a seam installed at start-up
 * from `index.ts`, exactly as `installConnectWiring` is: the reader defaults to
 * the account cookie alone, and the entry point widens it to "the account
 * cookie OR a code cookie for this very link".
 *
 * The default is the NARROW one on purpose. An entry point that forgets to
 * install the wider reader loses the phone-code path and keeps the account
 * path — a feature missing, which somebody notices. The other default would
 * lose the check itself.
 */
export type ConnectSessionReader =
  (request: Request, env: ConnectEnv) => Promise<OwnerId | null>;

let SESSION_READER: ConnectSessionReader | null = null;

export function installConnectSessionReader(reader: ConnectSessionReader): void {
  SESSION_READER = reader;
}

/**
 * THE QUESTION IS ABOUT THE LINK, NOT ABOUT THE LEG, and this function makes
 * that structural rather than hoped for.
 *
 * The installed reader is `connectSession` (routes/connect_auth.ts), which
 * honours a phone-code cookie ONLY on the link it was minted for — and it takes
 * that link from the REQUEST PATH, with a regex of its own that lists this
 * file's leg names. That is a second answer to "what does a /c/ path look
 * like", living in a file that cannot see this one's route table, and it drifts
 * the moment a leg is added here: measured on 2026-09-06, `/c/{token}/skip`
 * was not in its list, so a browser that arrived by TAPPING A TEXT — the one
 * that holds nothing but a code cookie, which is the whole population this
 * product texts — could tap Connect and could NOT tap Skip. Saying yes worked
 * and saying no answered "sign in to finish". That asymmetry is the exact harm
 * the decline leg was built to remove.
 *
 * So the reader is asked about `/c/{token}`, the one shape every /c/ path is
 * built on, with the query string dropped: nothing any reader needs to identify
 * a browser lives in a leg name or a query — the account token is a header or a
 * cookie, and the code cookie is bound to the TOKEN. The headers are carried
 * verbatim, which is the whole of what is being asked about. A leg added
 * tomorrow inherits this for free.
 *
 * IT IS NOT A WIDENING. The token in the fabricated URL is the one this request
 * is already on (it came out of `parseConnectPath`), so a cookie minted for
 * another link is refused exactly as before; the only thing removed is a
 * dependency on somebody else's spelling of our own paths.
 */
function asLinkRequest(request: Request, token: string): Request {
  const url = new URL(request.url);
  url.pathname = `/c/${token}`;
  url.search = "";
  // GET, no body: this is an identity question, and reading the body here would
  // consume the one the form post still needs.
  return new Request(url.toString(), { headers: request.headers });
}

async function whoIsAsking(
  request: Request, env: ConnectEnv, token: string,
): Promise<OwnerId | null> {
  if (!SESSION_READER) return whoIsSignedIn(request, env);
  return SESSION_READER(asLinkRequest(request, token), env);
}

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

/** A catalog description is PROSE ANOTHER COMPANY WROTE, on the one screen the
 *  register rule exists for, and it used to be rendered verbatim.
 *
 *  Measured against the live catalog on 2026-09-06: four of eight descriptions
 *  carry "integration" — gmail, googlecalendar, linear and github. Every
 *  sentence this product writes is screened by permissionSentences before a
 *  person sees it; this one walked straight past, so the page could say
 *  "integration", "api", or the vendor's own name while the copy beside it was
 *  forbidden from doing so.
 *
 *  A description that fails the screen is DROPPED, not rewritten. The three
 *  permission sentences are the consent; the description is decoration, and a
 *  page that silently paraphrases somebody else's blurb is inventing a claim
 *  about their product. The page reads fine without it — the app's name and
 *  logo are already there.
 *
 *  AND IT KEEPS THE WHOLE LIST WHILE THE NAME SCREEN TAKES HALF, deliberately.
 *  A description is PROSE, so a register word inside it reads as this page
 *  talking in permissions language, and the cost of being wrong is one dropped
 *  paragraph. A name is a proper noun with no substitute, and the cost of being
 *  wrong is the whole app — see `REGISTER_TERMS`. The price of the asymmetry,
 *  said out loud so nobody reads it as an oversight: an app whose own name
 *  carries a register word probably describes itself with it too, so its page
 *  arrives with a name, a logo and three sentences and no blurb. */
function describable(raw: unknown): string {
  const text = String(raw ?? "").trim();
  if (!text) return "";
  return forbiddenTermIn(text) === null ? text : "";
}

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
  button.go { font: inherit; font-weight: 600; padding: .85rem 1.25rem; width: 100%;
           border: 0; border-radius: 12px; cursor: pointer; }
  /* The decline is a BUTTON because it writes, and it is drawn as the quiet
     twin of the Connect button rather than as a second call to action: the
     spec's rule is one Connect button and a Skip that is "always visible and
     never buried" (page 25), which is neither shouting nor hiding. */
  button.later { font: inherit; font-weight: 400; background: none; border: 0;
           padding: .6rem 0; width: auto; margin-top: 1rem; cursor: pointer;
           color: inherit; text-decoration: underline; }
  form.later { margin: 0; }
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
 * THE HALF OF `FORBIDDEN_TERMS` THAT IS ONLY A REGISTER PROBLEM.
 *
 * words.ts's list does two different jobs under one name, and its own comment
 * says so about the one entry that is not like the others: the vendor's name is
 * "the one word in this list that is not a register problem but a promise".
 * Everything else in it is the vocabulary of a consent screen written by a legal
 * team — a rule about how THIS PRODUCT talks, applied to sentences this product
 * writes ("connect your Notion", never "authorize the Notion integration").
 *
 * Screening the catalog's display name against the whole list conflated the two
 * and cost real apps their consent page. Measured against the live catalog on
 * 2026-09-06: "AI/ML API", "API Labz" and "Moderation API" are somebody else's
 * registered product names, and all three answered 409 with no way forward. An
 * app whose own name contains "API" is not this product saying "API"; it is this
 * product quoting a proper noun, which is the only honest thing a consent page
 * can call an app (see the REWRITE THE NAME paragraph above
 * `UNSAYABLE_HEADING`, which is why dropping or rephrasing it is not on offer).
 *
 * WHICH WAY THE DEFAULT POINTS. This set is the EXEMPTION, so a term added to
 * `FORBIDDEN_TERMS` and not to this set refuses a name carrying it. A second
 * broker's name added over there therefore starts refusing here on the day it
 * lands, with nobody having to remember this file; a new register word added
 * over there costs an over-refusal until somebody adds it here, which is the
 * cheap failure and the visible one. Getting that polarity backwards would make
 * a promise the product could quietly stop keeping.
 *
 * Exported so the suite can hold it against `FORBIDDEN_TERMS` itself — every
 * entry here must exist there, and what is left over must be the promise. A copy
 * of a list is a list that drifts unless something compares them.
 *
 * THE SPLIT IS NOT FINISHED, AND THIS IS THE ONLY SURFACE IT REACHED. Two
 * screens outside this file still run the whole list over copy that NAMES the
 * app, and both belong to somebody else: connections/words.ts `styleProblem`
 * (via `permissionSentences`), so a permission sentence that names "Moderation
 * API" is refused and this page answers 503 instead; and connections/nudge.ts
 * `askMessage`, so the text that offers to connect it — the spec's own wording
 * is "Connect [app] and next time it is instant" — cannot be sent at all. So
 * such an app is connectable HERE, from Settings' Add-an-app and from a text
 * command, and Anticipy will never be the one to bring it up. Written down
 * rather than reached across for: the fix is theirs to make.
 */
export const REGISTER_TERMS: ReadonlySet<string> = new Set([
  "authorize",
  "authorise",
  "authorization",
  "authorisation",
  "grant access",
  "grants access",
  "granting access",
  "granted access",
  "permission",
  "permissions",
  "integration",
  "integrations",
  "api",
  "apis",
  "oauth",
]);

/** What is left of `FORBIDDEN_TERMS` once the register is taken out: the words a
 *  person was PROMISED they would never read. Derived, never typed — the vendor's
 *  name does not appear in this file's code, and the whole-suite scan over this
 *  source is what keeps it that way. */
const PROMISE_TERMS: readonly string[] = FORBIDDEN_TERMS.filter((t) => !REGISTER_TERMS.has(t));

/**
 * The promised-away word in a name, or null.
 *
 * WHY THIS IS NOT `forbiddenTermIn` WITH A FILTER ON THE RESULT. That function
 * returns the FIRST term in list order, and "composio" is last in it: a toolkit
 * called "Composio API" answers "api", which the register exemption would wave
 * through, and the page would print the one word this product promised never to
 * say. The question has to be asked over the promise terms alone, so it is.
 *
 * The boundary is words.ts's, character for character — "not a letter or a
 * digit" rather than `\b`, so "API-key" trips "api" while "capital" does not —
 * because the two matchers answering differently about the same string is the
 * only way this exemption could become a hole. words.ts keeps its matcher
 * private, so the suite pins the two against each other on a shared corpus
 * instead.
 *
 * Law 1: this reads a string the CATALOG registered, not a human's words, and it
 * decides what our own page may print rather than what anybody meant.
 */
export function promiseTermIn(text: string): string | null {
  const hay = String(text ?? "").replace(/\s+/g, " ").trim().toLowerCase();
  for (const term of PROMISE_TERMS) {
    const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    if (new RegExp(`(?<![a-z0-9])${escaped}(?![a-z0-9])`, "i").test(hay)) return term;
  }
  return null;
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
  // NO NAME, NO PAGE — and no fallback to the slug either. A slug is a vendor
  // primary key, not a display name, and a consent screen headed "Connect your
  // crm_manage_connections" over a button that hands somebody a key to their own
  // account is not a page anybody should be shown.
  //
  // This is a FLOOR on this file's own render contract and nothing more: it is
  // not reachable through the shipped wiring, and saying so is the point.
  // Both injected ports refuse a nameless row before this line runs, and
  // between them they cover both shapes of one: connections/provider.ts
  // `readToolkitMeta` returns null when `name` is absent or empty ("no name, or
  // no slug ... fatal to a row rather than cosmetic") so `toolkit()` throws and
  // this leg answers 503, and connections/words.ts `metaProblem` refuses to
  // write permission sentences for a name that is only whitespace, which the
  // provider's own `asString` lets through. What this guard buys is that a
  // THIRD port, wired tomorrow, cannot make this function draw a blank heading.
  // It replaced a slug fallthrough whose comment claimed behaviour no caller
  // could reach (round-2 finding 2, 2026-09-06).
  const name = typeof v.toolkit.name === "string" ? v.toolkit.name.trim() : "";
  if (name === "") {
    console.log(
      `connect view: the catalog row for ${JSON.stringify(v.toolkit.slug)} has no display `
        + "name, so there is nothing to head the page with. No page was drawn and the link "
        + "was not spent.",
    );
    return plainPage(409, UNSAYABLE_HEADING, UNSAYABLE_LINE);
  }

  // THE NAME IS SCREENED, AND NOT AGAINST THE SAME LIST THE DESCRIPTION IS.
  // The whole argument is above `UNSAYABLE_HEADING`; the short version is that
  // the register half of `FORBIDDEN_TERMS` is a rule about WORDS THIS PRODUCT
  // WRITES, and an app's own registered name is not this product writing. Only
  // the promise half — the words a person was told they would never read —
  // costs somebody their consent page.
  const unsayable = promiseTermIn(name);
  if (unsayable !== null) {
    // The slug and the term, for the one person who can fix it, and the fix is
    // a display name on the CATALOG ROW. A name typed into this file would be
    // the thing this file's header forbids.
    console.log(
      `connect view: the catalog draws ${JSON.stringify(v.toolkit.slug)} as `
        + `${JSON.stringify(name)}, which carries ${JSON.stringify(unsayable)} — a word this `
        + "screen may not print. No page was drawn and the link was not spent. Give that "
        + "toolkit a display name in the catalog.",
    );
    return plainPage(409, UNSAYABLE_HEADING, UNSAYABLE_LINE);
  }

  const logo = httpsOnly(v.toolkit.logo);
  const which = v.alias ? ` (your ${esc(v.alias)} account)` : "";
  const body = `<body>
${logo ? `<img class="logo" src="${esc(logo)}" alt="">` : ""}
<h1>Connect your ${esc(name)}${which}</h1>
${describable(v.toolkit.description) ? `<p>${esc(describable(v.toolkit.description))}</p>` : ""}
<p>Here's what Anticipy would be able to do:</p>
<ul>
${v.sentences.map((s) => `  <li>${esc(s)}</li>`).join("\n")}
</ul>
<form method="post" action="/c/${esc(token)}/go">
${state ? `  <input type="hidden" name="state" value="${esc(state)}">\n` : ""}  <button class="go" type="submit">Connect ${esc(name)}</button>
</form>
<form class="later" method="post" action="/c/${esc(token)}/skip">
${state ? `  <input type="hidden" name="state" value="${esc(state)}">\n` : ""}  <button class="later" type="submit">Skip for now</button>
</form>
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
  "Anticipy needs to know it's you before it sets anything up. It can text a code to the "
  + "phone number on your account — or you can sign in to Anticipy in this browser and open "
  + "this link again.";
/** The label on the door. The product's own words for it (routes/connect_auth.ts
 *  ASK_HEADING says the same thing at the top of the page it opens), so what the
 *  person taps and what they arrive at read as one thing. Never "authenticate",
 *  never "verify". */
const CODE_OFFER_LABEL = "Get a code by text";
const EXPIRED_HEADING = "That link has expired";
const EXPIRED_LINE = "Links last ten minutes. Ask Anticipy for a new one and it'll send another.";
const USED_HEADING = "That link has been used";
const USED_LINE = "Each link works once. Ask Anticipy for a new one and it'll send another.";
const WRONG_USER_HEADING = "You're signed in as someone else";
const WRONG_USER_LINE =
  "This link was made for a different Anticipy account. Sign in as that account and open it again.";

/**
 * THE SIXTH REFUSAL, AND THE ONLY ONE THAT IS ABOUT THE APP RATHER THAN THE
 * LINK: the catalog's name for this toolkit is a word this product PROMISED a
 * person would never read, so the screen is not drawn. It is also the page a
 * catalog row with no display name at all gets, for the reason in `viewPage`.
 *
 * MEASURED, NOT HYPOTHETICAL. The live catalog on 2026-09-06 holds toolkits
 * whose OWN names are the vendor's name and that name plus a word. The
 * catalog's DESCRIPTION was already screened (`describable`) and the NAME was
 * not, so the one screen the register rule exists for could print the one word
 * the spec treats not as a preference but as a promise: the person never hears
 * it.
 *
 * AND IT IS ONLY THAT WORD. The first version of this refusal screened the name
 * against all of `FORBIDDEN_TERMS`, which is two rules wearing one name, and it
 * took the wrong one out on real apps: "AI/ML API", "API Labz" and "Moderation
 * API" are live catalog rows, and all three became unconnectable — 409, no
 * button, no way forward, for the crime of a name their own makers chose. The
 * register is a rule about the sentences THIS PRODUCT writes; it was never a
 * rule about proper nouns. `REGISTER_TERMS` above is where that line is drawn
 * and the suite is what holds the two halves apart. An over-refusal on this page
 * is not a safe failure: it is an app somebody wanted, permanently unreachable,
 * with a page that does not even say why.
 *
 * THREE ANSWERS WERE AVAILABLE AND THIS IS THE THIRD.
 *
 *   DROP THE NAME, the way the description is dropped. Refused: the description
 *   is decoration and the name is the subject of the only sentence on the page
 *   that matters. "Connect your ___" over a button that hands somebody's key to
 *   an unnamed thing is not a consent screen, it is a trick, and it looks
 *   exactly like a page that finished loading — which is the same failure
 *   `checkedSentences` refuses for the permission list.
 *
 *   REWRITE THE NAME. The worst of the three, and worth naming because it is the
 *   one that looks helpful. A consent page presenting somebody's app under a
 *   name its own maker does not use is the shape of a phishing page; and
 *   choosing that name is a meaning question, which HARNESS-LAWS law 1 reserves
 *   for a model with full context and forbids to a rule in a render function.
 *
 *   DON'T DRAW THE PAGE. What is left, and it is honest at every layer. Nothing
 *   is consumed — the view leg never spends the token, so the same link works
 *   the moment the catalog row is fixed — nothing is written, no vendor call is
 *   made, and the person reads one plain sentence instead of a screen carrying
 *   the word we promised they would never read. The cost is real and it is the
 *   small one: this app cannot be connected today, and connecting was never the
 *   product — the browser hand does the job either way, which is the sentence
 *   every ask in this system already carries.
 *
 * THE WAY OUT IS THE CATALOG, NEVER THIS FILE. A toolkit that needs a different
 * display name gets one where its name lives. A list of app names here is the
 * exact thing this file's header and the spec's register rule both forbid, and
 * the invented-toolkit tests in the suite are the pin on that.
 *
 * WHY 409 AND NOT 503. A 503 promises a retry, and no retry can help: the name
 * will be the same name next minute. 409 is the one code in this file's
 * vocabulary that says the request was fine and the state it landed in is not,
 * and it keeps this refusal countable in a log separately from the catalog blip
 * two functions up, which really is a retry.
 */
const UNSAYABLE_HEADING = "Anticipy can't set this one up";
const UNSAYABLE_LINE =
  "Something's off with how this app is listed, so nothing has changed on your account. "
  + "Anticipy will keep doing this in your browser, which works fine.";

/**
 * WHAT A PERSON READS WHEN THEY SAY NO, and it is a promise this Worker has to
 * keep. It may only be shown over a decline that was actually WRITTEN — the
 * whole defect being closed here is a Skip that looked like it landed and did
 * not, so a page saying "I won't ask again" over an unwritten row would be the
 * same failure with better manners.
 */
const SKIPPED_HEADING = "Noted.";
const SKIPPED_LINE =
  "I won't bring this one up again for a while. You can set it up whenever you like — "
  + "just ask me, or find it in Settings.";
/** The app is already connected, so there was no ask to refuse. Said plainly
 *  rather than as a decline, because nothing was written and claiming otherwise
 *  would be a lie about their own account. */
const NOTHING_HEADING = "That one's already set up";
const NOTHING_LINE =
  "This app is connected already, so there's nothing to turn down. You can switch it off "
  + "any time in Settings.";
/** THE HONEST FAILURE. The person said no and we could not write it down; they
 *  are owed that fact, because the consequence lands on them the next time
 *  Anticipy opens its mouth. */
const NOT_NOTED_HEADING = "I couldn't note that";
const NOT_NOTED_LINE =
  "Your answer didn't save just now, so I might ask again. Try once more in a moment, or "
  + "tell me and I'll leave it alone.";

/**
 * The door out of the signed-out page: the phone-code offer, carrying the
 * phone's attempt id when the request brought one.
 *
 * ROOT-RELATIVE, like every other link this file mints: the routes live on
 * whatever host is serving them, and an absolute URL built from a constant
 * would send a preview deployment's visitors to production.
 *
 * THE STATE IS ENCODED HERE AND DECODED THERE, which is what "carried verbatim"
 * means on a wire. `connectRoute` reads it back with `searchParams.get`, so a
 * state containing "%" — the phone's alphabet allows one — arrives as the
 * characters the phone minted. Writing it raw would corrupt that case; encoding
 * an already-encoded one would corrupt it the other way.
 *
 * It takes nothing but the caller's own URL. No store, no catalog, no session:
 * whatever this returns is the same offer for every token there is.
 */
function codeOfferUrl(token: string, state: string | null): string {
  return `/c/${token}/code${state ? `?state=${encodeURIComponent(state)}` : ""}`;
}

/**
 * The four states that must look the same to a stranger, drawn in one place so
 * they cannot drift apart in five.
 *
 * ONLY `sign-in-required` CARRIES THE DOOR, and only it may. The other three
 * are answers to a caller who has already proved they are somebody: expired and
 * already-used are the owner's own link, gone, and a code would open nothing;
 * wrong-user is a browser holding a DIFFERENT account's session, and
 * `connectSession` lets that session win outright, so a code could not promote
 * them anyway. Putting the offer on those pages would also put the token on
 * them — and the expired page is the one a signed-in stranger sees, which the
 * suite compares against an invented token byte for byte.
 */
function refusalPage(
  which: "sign-in-required" | "expired" | "already-used" | "wrong-user",
  token: string, state: string | null,
): Response {
  switch (which) {
    case "sign-in-required":
      return plainPage(401, SIGN_IN_HEADING, SIGN_IN_LINE,
        { href: codeOfferUrl(token, state), label: CODE_OFFER_LABEL });
    case "expired":          return plainPage(410, EXPIRED_HEADING, EXPIRED_LINE);
    case "already-used":     return plainPage(410, USED_HEADING, USED_LINE);
    case "wrong-user":       return plainPage(403, WRONG_USER_HEADING, WRONG_USER_LINE);
  }
}

const unwired = (): Response =>
  plainPage(503, "Connecting isn't switched on here",
    "Anticipy can't set this up right now. Nothing has changed on your account.");

/**
 * THE LIFETIME EXTENSION, and why it is a fourth parameter rather than
 * something this file can arrange for itself.
 *
 * `/go` starts a background poll (connections/wait.ts) the moment the vendor
 * link is minted, because the callback is the only success signal the vendor
 * offers and a browser that dies on the way back to it loses the connection
 * permanently. A Worker CANCELS outstanding work as soon as a response is
 * returned; the only thing that keeps it running is `ExecutionContext.waitUntil`,
 * and an ExecutionContext exists nowhere but the entry point's `fetch`.
 *
 * So the entry point has to hand it down: `connectRoute(request, env,
 * undefined, ctx)`. WITHOUT IT THE POLL IS NOT STARTED AT ALL, and `/go` says
 * so in one log line per redirect. Starting it anyway was tried and is wrong
 * twice over: on a Worker the runtime cancels it the moment the redirect is
 * returned, so it buys nothing; and off a Worker — in this repo's own suites —
 * it is a real timer nobody can join, which held test/connect-routes.test.ts
 * open for eleven minutes per redirect. A backup that only pretends to run is
 * the silent version of the feature not existing.
 */
export interface ConnectBackground {
  waitUntil(promise: Promise<unknown>): void;
}

/**
 * The entry point index.ts registers.
 *
 * `deps` is injectable so the suite can drive the real handlers with a store it
 * controls; production passes nothing and gets the installed wiring.
 */
export async function connectRoute(
  request: Request, env: ConnectEnv, deps?: ConnectDeps, ctx?: ConnectBackground,
): Promise<Response> {
  const url = new URL(request.url);
  const route = parseConnectPath(url.pathname);
  // Not one of our three shapes. 404, and nothing about tokens is implied: the
  // alphabet and the length are both public, so an attacker learns nothing here
  // they could not compute offline.
  if (!route) return plainPage(404, "Not found", "There's nothing at this address.");

  const method = request.method === "HEAD" ? "GET" : request.method;
  const wants = CONNECT_METHOD[route.leg];
  // A GET on /go would let a link prefetcher, an <img> tag or a browser's
  // address-bar preload SPEND the owner's single-use link before they ever tap
  // it; a GET on /skip would let the same three RECORD A DECLINE nobody made,
  // silencing an app the person never turned down. A POST on the page itself is
  // not a route at all.
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
  if (route.leg === "go") {
    return await handleGo(request, env, wired, route.token, now, baseUrl, ctx);
  }
  if (route.leg === "skip") return await handleSkip(request, env, wired, route.token, now);
  return await handleDone(request, env, wired, route.token, now, state, url);
}

async function handleView(
  request: Request, env: ConnectEnv, deps: ConnectDeps,
  token: string, now: number, state: string | null,
): Promise<Response> {
  const who = await whoIsAsking(request, env, token);
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
  if (view.state !== "ok") return refusalPage(view.state, token, state);
  return viewPage(token, view, state);
}

/**
 * START THE BACKUP AND WALK AWAY.
 *
 * The vendor publishes no success webhook, so `/done` in the person's own
 * browser is the only signal a connection exists — and a browser that dies
 * between the consent screen and that page loses the connection permanently:
 * bound at the vendor, no row here, no nudge flip, and nothing that will ever
 * mention it again. connections/wait.ts is the second signal, and THIS is the
 * moment to start it: the vendor link has just been minted, so a connect is in
 * flight for exactly this owner on exactly this toolkit.
 *
 * NOTHING HERE IS AWAITED. `tokenHandle` is a hash and would cost microseconds,
 * but it is inside the task rather than in front of it so that the redirect is
 * built from values this function already holds and the request path touches
 * the poll's promise exactly once — to hand it to `waitUntil`.
 *
 * THE OWNER AND THE TOOLKIT COME OFF THE SPENT LINK, which came off the stored
 * row: `connectPageGo` reads them from the row `redeem` verified, never from
 * the session and never from anything on the request. wait.ts checks them
 * against the row again anyway, which is the difference between "should never"
 * and "cannot".
 *
 * NO CONTEXT, NO POLL, and the log line names the one change that fixes it.
 * A Worker cancels background work when the response is returned unless
 * `waitUntil` holds it open, so an unheld promise finishes nothing in
 * production — and off a Worker it is worse than nothing: a real timer that
 * nobody holds a handle to, which is exactly what held a sibling test suite
 * open for eleven minutes per redirect. The redirect is unaffected either way;
 * only the backup is.
 */
function startWaiting(
  env: ConnectEnv & WaitEnv,
  deps: ConnectDeps,
  token: string,
  owner: OwnerId,
  toolkit: string,
  now: number,
  ctx: ConnectBackground | undefined,
): void {
  const budget = waitBudgetMs(env);
  if (budget <= 0) {
    // An operator turned it off. Say so once per redirect: a switched-off
    // backup and a broken one look identical from the outside, and only one of
    // them is somebody's decision.
    console.log("connect go: the connection backup is switched off "
      + "(CONNECT_WAIT_MS=0), so this connect is the callback's alone");
    return;
  }

  if (!ctx || typeof ctx.waitUntil !== "function") {
    console.log("connect go: the connection backup did NOT start — the entry point "
      + "passed no ExecutionContext, and without waitUntil a Worker cancels background "
      + "work the moment the redirect is returned. Pass ctx as connectRoute's fourth "
      + "argument. Until then this connect is the callback's alone.");
    return;
  }

  const task = (async (): Promise<void> => {
    await waitForConnection(env, {
      owner,
      toolkit,
      handle: await tokenHandle(token),
      deadline: now + budget,
      store: deps.store,
      provider: deps.provider,
      onConnected: deps.onConnected,
      // The caller's clock, so a test that owns time owns it end to end.
      // Production wires none and wait.ts uses Date.now.
      now: deps.now,
    });
  })().catch(() => {
    // `waitForConnection` does not throw; this is the belt for the hash and for
    // whatever a future edit puts above it. An unhandled rejection here would
    // land on a request that was answered minutes ago.
  });

  ctx.waitUntil(task);
}

/** The one sentence a POST from somebody else's page gets, on either writing
 *  leg. One copy, so the two cannot drift into two answers. */
function refuseCrossSite(): Response {
  return plainPage(403, "That didn't come from here",
    "Open your Anticipy link again and tap the button on the page itself.");
}

async function handleGo(
  request: Request, env: ConnectEnv, deps: ConnectDeps,
  token: string, now: number, baseUrl: string, ctx?: ConnectBackground,
): Promise<Response> {
  // Before the session is even read, and long before the compare-and-set.
  if (isCrossSitePost(request)) {
    console.log(`connect go: ${await tokenFingerprint(token)} refused — cross-site POST`);
    return refuseCrossSite();
  }

  const who = await whoIsAsking(request, env, token);
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
    // THE BACKUP, started at the one moment we know a connect is in flight and
    // AWAITED NOWHERE — see startWaiting. The redirect below is built and
    // returned without touching this promise.
    startWaiting(env, deps, token, go.owner, go.toolkit, now, ctx);
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
  // The state here is the one the PAGE posted, not one off the query: a
  // signed-out tap has to come back to a door that still knows which attempt
  // the phone is waiting on.
  return refusalPage(go.state, token, state);
}

/**
 * "Skip for now" — the tap that records a no.
 *
 * THE SAME THREE GUARDS /go RUNS, IN THE SAME ORDER: cross-site first, then the
 * session, then the row. A decline is a write, and every reason /go is defended
 * applies to it — with one extra: a decline fired by somebody else's page
 * SILENCES an app, and silence is the failure nobody reports.
 *
 * NO DEEP LINK WITHOUT AN ATTEMPT ID. `ConnectHandoff.parseDone` refuses a
 * callback carrying no `state` (it cannot bind it to the attempt it started),
 * so offering `anticipy://` to a browser that arrived from a text — which has
 * no state — would be a link that lands on an error. The text browser gets the
 * page and nothing else, which is all it needs.
 */
async function handleSkip(
  request: Request, env: ConnectEnv, deps: ConnectDeps,
  token: string, now: number,
): Promise<Response> {
  if (isCrossSitePost(request)) {
    console.log(`connect skip: ${await tokenFingerprint(token)} refused — cross-site POST`);
    return refuseCrossSite();
  }

  const who = await whoIsAsking(request, env, token);
  // From the BODY, like /go's, so it survives the form post: the state is the
  // phone's attempt id and it is how the app knows this attempt is over.
  const state = checkedState(await formField(request, "state"));

  const skipped = await connectPageSkip(token, {
    signedInAs: who, store: deps.store, now,
  });
  if (skipped.state !== "noted") return refusalPage(skipped.state, token, state);

  const outcome = skipped.outcome;
  const back = state
    ? { href: appLink(skipped.toolkit, APP_STATUS_CANCELLED, { state }), label: "Back to Anticipy" }
    : undefined;

  if (outcome.state === "not-recorded") {
    // LOUD, because this is a wiring failure and the person just paid for it
    // with an answer nobody kept.
    console.log(`connect skip: ${await tokenFingerprint(token)} NOT recorded — ${outcome.why}`);
    return plainPage(500, NOT_NOTED_HEADING, NOT_NOTED_LINE, back);
  }
  if (outcome.state === "nothing-to-decline") {
    console.log(`connect skip: ${await tokenFingerprint(token)} had nothing to decline`);
    return plainPage(200, NOTHING_HEADING, NOTHING_LINE, back);
  }
  console.log(`connect skip: ${await tokenFingerprint(token)} ${outcome.state} at level `
    + `${outcome.level}`);
  return plainPage(200, SKIPPED_HEADING, SKIPPED_LINE, back);
}

async function handleDone(
  request: Request, env: ConnectEnv, deps: ConnectDeps,
  token: string, now: number, state: string | null, url: URL,
): Promise<Response> {
  const who = await whoIsAsking(request, env, token);
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
      return refusalPage(done.state, token, state);
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
