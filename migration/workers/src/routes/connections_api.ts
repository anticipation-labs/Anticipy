/**
 * src/routes/connections_api.ts — the routes Settings → Connected Apps and
 * onboarding call, and the last link in the connect chain.
 *
 * THE CLIENT IS THE SPEC. Every path, every query name, every field name below
 * is read off app/ios/Anticipy/Backend/ConnectedAppsClient.swift, which was
 * written first and declares its own contract at lines 38-61. That file is not
 * edited to fit this one; this one is written to satisfy it. Until these
 * existed, every call it makes failed the way an unreachable server fails, and
 * the screen showed "I couldn't read your connected apps" to everybody.
 *
 *   GET  /me/connections                   -> { "items": [connection row, …] }
 *   GET  /me/connections/catalog?q=…       -> { "items": [toolkit row, …] }
 *   GET  /me/connections/catalog?slugs=a,b -> { "items": [toolkit row, …] }
 *   POST /me/connections/writes            -> { "ok": true, … }
 *   POST /me/connections/disconnect        -> { "revoked", "deleted",
 *                                               "revoke_unavailable", "app_name" }
 *   POST /me/connections/sentences         -> { "sentences": [ …, …, … ] }
 *   POST /me/connections/link              -> { "url": "https://…/c/{token}" }
 *   POST /me/connections/skip              -> { "ok": true, "state", "level",
 *                                               "snooze_until" }
 *   GET  /me/connections/signals           -> { "items": [ranked app row, …],
 *                                               "state" }
 *
 * ── AND THE SEVENTH IS THE ONE NOBODY COULD REACH ───────────────────────────
 *
 * `/skip` is new on 2026-09-06 and it exists because a person could not say no.
 * Onboarding's own Skip wrote a flag into UserDefaults ON THE DEVICE, so the
 * server never heard it: the ask engine's `connect_nudges` row stayed exactly
 * as it was, the snooze ladder was never entered, and the same person was asked
 * again at the next moment that scored high enough — on a second phone, or
 * after a reinstall, from the first minute. A refusal that lives only on the
 * glass is not a refusal; it is a preference the product cannot read.
 *
 * IT IS THE SAME WRITE THE CONNECT PAGE MAKES. `recordSkip` is imported from
 * routes/connect.ts rather than repeated, so the browser's "Skip for now" and
 * the phone's Skip walk one ladder. Two writers would be two ladders, and the
 * one nobody was looking at would be the wrong one.
 *
 * ── AND THE EIGHTH IS THE ONE THE PHONE HAD NO WAY TO ASK ───────────────────
 *
 * `/signals` is new on 2026-09-06. Spec page 45, onboarding step 2: "Which apps
 * do you live in?" with "detected apps pre-selected from the email domain
 * signal". `app_usage_signals` has held that evidence since the sweep landed
 * and `rankedApps` (src/connections/signals.ts) has ranked it; there was no
 * door between the two and the phone, so `OnboardingConnectStep` passed literal
 * empty arrays and pre-selected nothing. The screen whose whole job is "we
 * already know what you use" said nothing to anybody.
 *
 * IT ANSWERS THE QUESTION IN ONE ROUND TRIP. Each line carries the ranked
 * evidence AND the catalog row for that app, in the same field names `?slugs=`
 * uses, so the phone draws a name, a logo and a checkbox with one decoder and
 * one request.
 *
 * AND IT IS HONEST ABOUT THREE DIFFERENT EMPTIES, because the screen draws them
 * three ways. See `handleSignals`.
 *
 * ── THE OWNER COMES FROM THE TOKEN. ALWAYS. ─────────────────────────────────
 *
 * There is no parameter anywhere in this file through which a caller can name
 * an owner: not a path segment, not a query key, not a body field. `whoIsAsking`
 * resolves the owner ROW id from the `Authorization` header through the same
 * `verifyToken` /me/delete uses, and every store and provider call below is
 * scoped by THAT value.
 *
 * This is not caution about a hypothetical. During the spike one operator's own
 * mailbox was connected by hand under the `user_id` "omar" — a display name —
 * and one person's tokens served everybody; it had to be revoked and deleted
 * (spike/two-hands/src/connections/contract.ts opens on it). The phone's own
 * client carries the other half of the same rule and puts NO owner on the wire
 * (ConnectedAppsClient.swift:15-30). Both halves have to hold, because either
 * one alone is a promise rather than a shape.
 *
 * ── AN EMPTY LIST IS NEVER A FAILURE MODE ───────────────────────────────────
 *
 * Every route that cannot reach D1, the catalog or the model answers a NON-2XX
 * with `{ ok: false }`. It never answers `{ items: [] }` or `{ sentences: [] }`.
 * The client throws on a non-2xx and the screen renders "could not reach
 * Anticipy" (ConnectedAppsClient.swift:335-347); an empty list would instead
 * paint a confident empty state over somebody's four connected apps and invite
 * them to connect what they already have.
 *
 * ── THE REGISTER ────────────────────────────────────────────────────────────
 *
 * The person never reads "authorize", "permissions", "integration", "API",
 * "OAuth" or the vendor's name. No app is named in this file either: names,
 * logos and descriptions come from the catalog at run time and the three
 * permission sentences come from the same `makePermissionWords` path
 * routes/connect.ts uses, so the page and the phone cannot describe one app two
 * ways. test/connections-api.test.ts scans every body this file can produce
 * against words.ts's own `FORBIDDEN_TERMS`.
 *
 * ── HARNESS-LAWS LAW 1 ──────────────────────────────────────────────────────
 *
 * Nothing here decides what anybody MEANT. The search box's letters are handed
 * to the catalog byte for byte — no filter, no ranking, no local list of app
 * names, no "did you mean". What this file pattern-matches is structure only: a
 * path, an HTTP method, the shape of an owner row id, the shape of a slug, and
 * a strict JSON boolean. The one meaning question in the feature — what three
 * sentences describe this app's scopes — is a model asked one question on its
 * own, audited by words.ts, exactly as the connect page asks it.
 *
 * ── LAW 3 ───────────────────────────────────────────────────────────────────
 *
 * Repo-green is not done. These routes are live when
 * `GET https://api.anticipy.ai/me/connections` answers 401 with no credential
 * and a signed-in owner's own token answers 200 — not when this suite passes.
 *
 * ── WHAT IS NOT DONE HERE, WRITTEN DOWN RATHER THAN LEFT TO BE FOUND ────────
 *
 * 1. `?q=`'s BUDGET IS PER ISOLATE, NOT PER ACCOUNT. See `SEARCH_WINDOW_MS`.
 *    (The search itself is wired: `connectionsApiDeps` fills
 *    `ConnectionsApiDeps.search` from the provider's own catalog search.)
 * 2. `/link` MINTS ON A HOST THE PHONE REFUSES. See `handleLink`.
 * 3. `?slugs=`, `/sentences` AND `/signals` ARE STILL UNBUDGETED. A signed-in
 *    caller can drive `?slugs=` (up to `MAX_CATALOG_SLUGS` vendor round trips a
 *    request), `/signals` (up to `MAX_SIGNAL_APPS` of them, plus one D1 read)
 *    and `/sentences` (one MODEL call a request, which costs money) as fast as
 *    they like. Both are authenticated and attributable and neither writes
 *    anything; the budget shape to copy is `spendSearch` below, and the durable
 *    substrate both want is the one in item 1.
 * 4. `/writes` CAN RESURRECT A ROW under one race. The stored row is read, then
 *    written, and `putConnection` is an upsert: a disconnect landing between
 *    those two re-inserts the connection. It self-heals — the vendor no longer
 *    holds the account, so the next disconnect takes the stale-row branch and
 *    clears it — and closing it properly needs an UPDATE-only method on the
 *    store, which is not this change's file.
 * 5. `/skip` IS UNBUDGETED, and deliberately so for now. It is one D1 read and
 *    at most one upsert of the caller's OWN row, keyed (user_id, toolkit), and
 *    the second call in a snooze window writes nothing at all — so hammering it
 *    costs a row that already exists and reaches nobody else. What a budget
 *    would buy here is protection from an authenticated owner spending their
 *    own quota, and what it would risk is a person's "no" being refused because
 *    their client retried; between those two, refusing a decline is the worse
 *    failure. The shape to copy if that changes is `handleLink`'s, which counts
 *    rows in D1 rather than in an isolate.
 */
import { verifyToken, type AuthEnv } from "../pb/auth.ts";
import {
  createD1Store,
  ownerId,
  type ConnectionsStore,
  type StoredConnection,
  type StoredLink,
  type StoredSignal,
} from "../connections/store.ts";
import {
  connectionsFromEnv,
  MAX_SEARCH_RESULTS,
  type ConnectionsEnv,
} from "../connections/provider.ts";
import {
  rankedApps,
  type RankedApp,
  type SignalStore,
} from "../connections/signals.ts";
import { makePermissionWords } from "../connections/words.ts";
import { makeSentenceWriter } from "../connections/wiring.ts";
import {
  mintConnectPage,
  LINK_TTL_MS,
  type MintedLink,
  type NudgeDeps,
  type NudgeEnv,
} from "../connections/nudge.ts";
// `MAX_PAGE_APPS` is routes/connect.ts's number — it is the reader's ceiling on
// how many apps one connect page may carry, and this route refuses a longer
// request with the caller's own status code rather than letting the minter
// throw it into a 503.
import { MAX_PAGE_APPS, recordSkip, type DeclineStore } from "./connect.ts";
import type {
  Connection,
  DisconnectResult,
  OwnerId,
  ToolkitMeta,
} from "../../../../spike/two-hands/src/connections/contract.ts";

// ---------------------------------------------------------------------------
// ENV
// ---------------------------------------------------------------------------

/**
 * `AuthEnv` for the token, `ConnectionsEnv` for the vendor secret, `NudgeEnv`
 * for `CONNECT_BASE_URL` — every field of the last two is optional, so nothing
 * new becomes mandatory by declaring them. The model keys arrive through
 * `makeSentenceWriter`'s own `LlmEnv`, which is a superset this object
 * satisfies structurally.
 */
export interface ConnectionsApiEnv extends AuthEnv, ConnectionsEnv, NudgeEnv {
  DB: D1Database;
  /** Read by `makeSentenceWriter` (src/connections/wiring.ts). */
  OPENROUTER_API_KEY?: string;
  GEMINI_API_KEY?: string;
  ANTICIPY_CONNECT_MODEL?: string;
}

// ---------------------------------------------------------------------------
// THE ROUTES, DECLARED ONCE
// ---------------------------------------------------------------------------

/**
 * Every path this file serves, in one list, because a path typed at a handler
 * is a path no census can find. The suite compares this list against the
 * `Route` enum in ConnectedAppsClient.swift — the phone and the server read the
 * same six strings out of two files, and a seventh added to either without the
 * other goes red.
 */
export const CONNECTIONS_API_ROUTES = {
  list: "/me/connections",
  catalog: "/me/connections/catalog",
  writes: "/me/connections/writes",
  disconnect: "/me/connections/disconnect",
  sentences: "/me/connections/sentences",
  link: "/me/connections/link",
  skip: "/me/connections/skip",
  signals: "/me/connections/signals",
} as const;

export type ConnectionsApiLeg = keyof typeof CONNECTIONS_API_ROUTES;

/** The two query names, from ConnectedAppsClient.Field. `q` carries the
 *  owner's own words untouched; `slugs` carries catalog keys we already hold. */
export const QUERY_SEARCH = "q";
export const QUERY_SLUGS = "slugs";

/** Which verb each leg takes. A GET on a state-changing route is not a route at
 *  all: a link prefetcher or an address-bar preload must not be able to spend a
 *  connect-link budget or flip a write toggle. */
const METHOD: Record<ConnectionsApiLeg, "GET" | "POST"> = {
  list: "GET",
  catalog: "GET",
  writes: "POST",
  disconnect: "POST",
  sentences: "POST",
  link: "POST",
  // A GET here would let a link prefetcher or an address-bar preload record a
  // decline nobody made, and a decline is the one write whose failure mode is
  // SILENCE — an app quietly snoozed for a fortnight and nobody to notice.
  skip: "POST",
  // A read of this owner's own evidence. It writes nothing, which is asserted
  // rather than promised: the reader handed to `rankedApps` below cannot
  // record a signal at all.
  signals: "GET",
};

/** Anchored exactly, so `/me/connectionsX` and `/me/connections/link/extra` are
 *  not routes. Returns null rather than throwing: an unroutable path is a 404. */
export function parseConnectionsApiPath(pathname: unknown): ConnectionsApiLeg | null {
  if (typeof pathname !== "string") return null;
  for (const [leg, path] of Object.entries(CONNECTIONS_API_ROUTES)) {
    if (pathname === path) return leg as ConnectionsApiLeg;
  }
  return null;
}

// ---------------------------------------------------------------------------
// LIMITS
// ---------------------------------------------------------------------------

/**
 * THE LINK BUDGET, per owner per hour.
 *
 * `/link` is the one route here that WRITES A ROW on every call, and the row it
 * writes is a live bearer credential for one of this person's own accounts. An
 * unbounded mint is a table anybody with a session can fill and a pile of live
 * links nobody asked for. Six an hour is far above a person genuinely
 * connecting a few apps in one sitting and far below anything that costs us.
 *
 * The window is counted in D1 rather than in a module-level Map, for the reason
 * src/do/PairCodeCounter.ts spells out: requests land in whichever isolate the
 * edge picks, so a per-isolate counter is a counter an attacker resets by
 * opening a connection. The shape is the one routes/connect_auth.ts already
 * uses for `MAX_CODES_PER_OWNER` — count this owner's own rows inside a window.
 */
export const MAX_LINKS_PER_OWNER = 6;
export const LINK_WINDOW_MS = 60 * 60 * 1000;

/** How many catalog rows one `?slugs=` may ask for. The phone asks about the
 *  toolkits it already has connections for, which is a handful; the ceiling is
 *  here because each slug is a separate vendor round trip and the query string
 *  is caller-controlled. */
export const MAX_CATALOG_SLUGS = 25;

/**
 * HOW MANY APPS `/signals` MAY HAND BACK, and it is two ceilings in one number.
 *
 * IT IS A SCREEN. Onboarding step 2 draws these rows PRE-TICKED under a single
 * Connect button. A pre-ticked list longer than one screen is consent by
 * fatigue: somebody reads the first four and taps the button that connects all
 * fourteen. Eight is about a phone screen's worth above the button, and the
 * ranked order means the ones that fall off the end are the ones with the least
 * behind them.
 *
 * IT IS ALSO A COST CEILING. Each line costs one vendor round trip to name, and
 * this route has no budget of its own (see item 3 at the top of the file), so
 * the cap is the only thing bounding what one call spends. It is deliberately
 * at or under `MAX_CATALOG_SLUGS`, which is what `?slugs=` — the other route
 * that fans out to the catalog — is already allowed; a check pins that
 * relationship so raising this one cannot quietly outgrow it.
 *
 * IT CUTS THE RANKED ORDER, and never chooses within it. Which app matters most
 * is signals.ts's question and it has already answered; this number only says
 * where the list stops.
 */
export const MAX_SIGNAL_APPS = 8;

/** How many rows one write batch may carry. `ConnectionsPolicy.writesTransition`
 *  produces one row per connection the screen just moved. */
export const MAX_WRITE_ROWS = 50;

/**
 * THE SEARCH BUDGET, per owner per hour — and READ THE SECOND HALF OF THIS.
 *
 * `?q=` is the one GET here that spends somebody else's money: every call is a
 * vendor round trip against the whole catalog, and the phone fires one per
 * pause in the typing (300 ms in SettingsConnectedAppsView, 250 ms in
 * OnboardingConnectStep). A person hunting for two apps in one sitting lands
 * well under a hundred; a stuck retry loop, a scripted client or a search box
 * wired to every keystroke does not, and nothing else would notice.
 *
 * 120 an hour is chosen to sit far above the first and to bound the second. It
 * is a COST CEILING, and the copy for it says "a lot of looking", not "no".
 *
 * WHAT IT IS NOT: a defence. The count lives in `searchBudget`, a module-level
 * Map, so it is PER WORKER ISOLATE — requests land in whichever isolate the edge
 * picks, and a caller who wants more searches gets them by opening more
 * connections. That is exactly the objection `MAX_LINKS_PER_OWNER` above avoids
 * by counting rows in D1, and it is avoidable there only because `/link` writes
 * a row anyway. A search writes nothing, so the honest options were a new D1
 * table or a Durable Object counter (src/do/PairCodeCounter.ts is the shape) —
 * both a schema or binding change, neither in this file. Until one of them
 * exists this brake stops an accident and not an adversary, and it is written
 * down here so nobody later reads it as the thing it is not.
 */
export const MAX_SEARCHES_PER_OWNER = 120;
export const SEARCH_WINDOW_MS = 60 * 60 * 1000;

/** How many owners one isolate tracks before it forgets all of them.
 *
 *  Same reasoning as `MAX_CACHED_SESSIONS` in the provider: an isolate lives for
 *  hours and serves everybody, so an unbounded owner→timestamps map is a slow
 *  leak in a 128 MB budget. Clearing forgives everyone, which is the safe
 *  direction for a cost brake — the failure of clearing is a few extra vendor
 *  calls, and the failure of NOT clearing is the Worker running out of memory
 *  and answering nothing at all.
 *
 *  The arithmetic, because a ceiling nobody multiplied out is not a ceiling: an
 *  owner's list stops growing at `MAX_SEARCHES_PER_OWNER` (nothing is pushed
 *  once they are refused), so the worst case is 1,000 × 120 timestamps. That is
 *  low six figures of numbers, which fits; the same table at five thousand
 *  owners does not obviously fit beside everything else in the isolate, and
 *  "obviously" is the whole standard for a number like this. */
export const MAX_TRACKED_SEARCHERS = 1000;

/** owner -> the times inside the window at which they searched. */
const searchBudget = new Map<string, number[]>();

/** Drop every owner's search history. For tests, which own time and must not
 *  inherit a budget spent by the check above them, and for a caller that wants
 *  a clean isolate. */
export function resetSearchBudget(): void {
  searchBudget.clear();
}

/** Spend one search from this owner's window, or refuse.
 *
 *  Same shape as `handleLink`'s counting: keep only what falls inside the
 *  window, compare against the ceiling, record the spend. A refusal records
 *  NOTHING — a caller already over the line must not be able to push their own
 *  window forward by hammering it, which would turn an hour's cooldown into a
 *  permanent one. */
function spendSearch(owner: string, now: number): boolean {
  const since = now - SEARCH_WINDOW_MS;
  const kept = (searchBudget.get(owner) ?? []).filter((at) => at >= since);
  if (kept.length >= MAX_SEARCHES_PER_OWNER) {
    searchBudget.set(owner, kept);
    return false;
  }
  if (!searchBudget.has(owner) && searchBudget.size >= MAX_TRACKED_SEARCHERS) {
    searchBudget.clear();
  }
  kept.push(now);
  searchBudget.set(owner, kept);
  return true;
}

// ---------------------------------------------------------------------------
// THE SEAM
// ---------------------------------------------------------------------------

/** The store methods these routes touch, and no others. Still narrowed: nothing
 *  in this file can record a usage signal or spend a token. It CAN now read and
 *  write this owner's `connect_nudges` row, and only through `recordSkip` — the
 *  two methods arrive from `DeclineStore` (routes/connect.ts), which is the one
 *  declaration of that capability, so widening it here would widen it there
 *  too and a reviewer looking at either sees the whole of it.
 *  `createD1Store(env)` satisfies all of this structurally. */
export interface ConnectionsApiStore extends DeclineStore {
  /** READ ONLY, and the narrowing is enforced rather than promised: the reader
   *  `handleSignals` builds from this refuses `recordSignal` by name, so a
   *  route that answers a question about somebody's evidence cannot add to it. */
  signalsForOwner(user: OwnerId | string): Promise<StoredSignal[]>;
  connectionsForOwner(user: OwnerId | string): Promise<StoredConnection[]>;
  readConnection(user: OwnerId | string, accountId: string): Promise<StoredConnection | null>;
  putConnection(row: StoredConnection): Promise<void>;
  deleteConnection(user: OwnerId | string, accountId: string): Promise<boolean>;
  linksForOwner(user: OwnerId | string): Promise<StoredLink[]>;
  put(row: StoredLink): Promise<void>;
  /** A whole connect page, in ONE transaction. `handleLink` mints a page of N
   *  apps on one token (spec page 25) and a page half-written is a person
   *  looking at fewer apps than they ticked, with nothing anywhere saying so. */
  putAll(rows: readonly StoredLink[]): Promise<void>;
}

/** The vendor calls these routes make. `authorize` is deliberately absent:
 *  a vendor connect URL is produced in exactly one place in this Worker
 *  (routes/connect.ts `connectPageGo`) and this file must not be a second. */
export interface ConnectionsApiProvider {
  toolkit(slug: string): Promise<ToolkitMeta>;
  connections(user: OwnerId): Promise<Connection[]>;
  disconnect(user: OwnerId, connectedAccountId: string): Promise<DisconnectResult>;
}

export interface ConnectionsApiDeps {
  store: ConnectionsApiStore;
  provider: ConnectionsApiProvider;
  /** The connect page's own sentence writer, so the page and the phone cannot
   *  describe one app two ways. */
  words: { sentences(meta: ToolkitMeta): Promise<string[]> };
  /**
   * THE CATALOG SEARCH.
   *
   * `?q=` is a free-text search over the WHOLE catalog — how somebody connects
   * an app nobody ever asked them about (ConnectedAppsModel.search,
   * OnboardingConnectStep.askTheCatalog). `connectionsApiDeps` fills this from
   * the vendor adapter's own `search()`, which puts the typed letters in a
   * query string and returns the vendor's rows in the vendor's order.
   *
   * IT IS THE PORT AND NOT THE IMPLEMENTATION, for the same reason `provider`
   * is: what somebody meant is the catalog's question, and this file must have
   * no way to answer it. Nothing here reads the query, ranks the answer or
   * knows an app's name — HARNESS-LAWS law 1, in the one place the spec spends
   * a paragraph forbidding it ("no local list to match against, no ranking, no
   * did-you-mean").
   *
   * STILL OPTIONAL, deliberately. A caller injecting a narrower deps object —
   * the suite does, to pin the branch — gets the honest 503 that the screen
   * renders as "could not reach Anticipy", never `[]`, which would tell
   * somebody the catalog holds nothing. Both branches are pinned in the suite.
   */
  search?(query: string): Promise<ToolkitMeta[]>;
  /** Injectable clock. Tests own time; production passes nothing. */
  now?(): number;
}

// ---------------------------------------------------------------------------
// WIRING
// ---------------------------------------------------------------------------

/**
 * The real ports, built from the real modules.
 *
 * This lives here rather than in src/connections/wiring.ts only because that
 * file is not this change's to edit; it is the same three constructions
 * `connectDeps` makes, in the same order, from the same functions — the store
 * is D1, the catalog is the vendor adapter, and the sentences come from the
 * writer built one line below, which is the expression wiring.ts uses character
 * for character. The suite asserts the two files still agree on it, because a
 * second sentence writer would be a second answer to what an app is allowed to
 * say about itself.
 *
 * ONLY `DB` IS A HARD PRECONDITION, and that is deliberate. `connectDeps`
 * refuses without the vendor secret or a model key because a connect PAGE
 * cannot be drawn without either. Four of these seven routes can: listing this
 * owner's connections, flipping the write toggle, minting our own link and
 * recording a decline are all pure D1. Gating them on the model key would tell somebody with four
 * connected apps that Anticipy could not read them because a text-generation
 * secret was unset. Each route answers for its OWN missing configuration
 * instead — `connectionsFromEnv` returns an adapter whose every method throws
 * `ConnectionsUnconfigured` without issuing a request, and the sentence writer
 * throws by name, so both arrive here as the clean failure below.
 */
export function connectionsApiDeps(env: ConnectionsApiEnv): ConnectionsApiDeps | null {
  if (!env || !env.DB) {
    console.log(
      "me/connections: the DB binding is unset on this Worker, so no connection can be read "
        + "or written. Set it and redeploy.",
    );
    return null;
  }
  const store: ConnectionsStore = createD1Store(env);
  // ONE adapter, used as two ports. `connectionsFromEnv` is memoised per key, so
  // this is the isolate's single provider either way; naming it here makes it
  // visible that the catalog the search box asks is the same catalog the
  // disconnect confirmation reads a name out of.
  const provider = connectionsFromEnv(env);
  return {
    store,
    provider,
    words: makePermissionWords(makeSentenceWriter(env)),
    // The cap is the provider's own `MAX_SEARCH_RESULTS` and is not passed from
    // here: one constant, so the number the vendor is asked for and the number
    // the route will hand back cannot drift into two answers.
    search: (query: string) => provider.search(query),
  };
}

// ---------------------------------------------------------------------------
// ANSWERS
// ---------------------------------------------------------------------------

/**
 * Every response this file makes.
 *
 *   no-store        a connections list names somebody's accounts and the link
 *                   answer carries a live single-use credential. Neither may
 *                   sit in a cache, a proxy or a shared browser.
 *   nosniff         a JSON body must never be sniffed into something runnable.
 *   no-referrer     for the one answer that carries a token in its body; set on
 *                   all of them so no future route can forget it.
 */
function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
      "referrer-policy": "no-referrer",
      "x-robots-tag": "noindex, nofollow",
    },
  });
}

/**
 * The sentences this file is allowed to say.
 *
 * They are for a log, a curl and a developer — the phone writes its own copy
 * from `ConnectedAppsModel.Copy` and never renders a server message. They are
 * still held to the register: no vendor name, and none of the consent-screen
 * vocabulary, because a sentence that leaks into a screenshot or a support
 * transcript is a sentence the product said.
 */
const SIGN_IN_FIRST = "Sign in first.";
const NOT_A_ROUTE = "There's nothing at this address.";
const BAD_REQUEST = "That request wasn't a shape I could read.";
const NOT_YOURS = "That isn't connected to your account.";
const COULD_NOT_READ = "I couldn't read your connected apps just now. Nothing has changed.";
const COULD_NOT_SAVE = "I couldn't save that just now. Nothing has changed.";
const COULD_NOT_DISCONNECT = "I couldn't disconnect that just now, so nothing has changed.";
const CATALOG_UNREACHABLE = "I couldn't look that up just now. Nothing has changed.";
const NO_SENTENCES = "I couldn't get that ready just now. Nothing has changed.";
const TOO_MANY_LINKS = "That's a lot of tries in one go. Give it an hour and ask me again.";
const TOO_MANY_LOOKUPS = "That's a lot of looking in one go. Give it an hour and ask me again.";

/**
 * A failure, and optionally WHICH failure.
 *
 * `state` exists because two of this file's outages are both 503 and the phone
 * draws them differently — "I could not read your evidence" and "I know your
 * apps and could not name any of them" are the same status code and a different
 * screen. The message is for a log and a curl; the state is the field a client
 * may branch on, so the copy can be rewritten without breaking a phone.
 */
const refuse = (status: number, message: string, state?: string): Response =>
  json(status, state === undefined ? { ok: false, message } : { ok: false, state, message });

// ---------------------------------------------------------------------------
// WHO IS ASKING
// ---------------------------------------------------------------------------

/**
 * The owner ROW id, from the request's own credential, or null.
 *
 * The phone sends the bare `owners` auth token in `Authorization`
 * (AnticipyBackend.swift:189-192) and `verifyToken` accepts it with or without
 * a `Bearer ` prefix. Nothing else is accepted: not a cookie (these routes are
 * the app's, never a browser's), and above all not a query parameter — a
 * credential in a URL is a credential in browser history, in our own request
 * logs and in every screenshot of the address bar.
 *
 * FAILS CLOSED AND NEVER THROWS. A route that 500s on a malformed header is a
 * denial of service handed to whoever can set one.
 *
 * AND THIS IS WHY THERE IS NO CROSS-SITE GUARD HERE, unlike routes/connect.ts,
 * which needs one. That file accepts a session COOKIE, because a browser
 * opening a texted link cannot set a header — so any page anywhere can make the
 * owner's browser POST to it with their session attached. These routes accept
 * only the `Authorization` header, and a cross-site form post cannot set one
 * while a cross-site `fetch` that sets one is a preflighted request this Worker
 * answers 405 to with no CORS headers at all. The absence of the cookie IS the
 * guard, and it stops being one the moment somebody adds cookie support here.
 */
async function whoIsAsking(request: Request, env: ConnectionsApiEnv): Promise<string | null> {
  const raw = request.headers.get("Authorization");
  if (!raw || raw.trim() === "") return null;
  try {
    const v = await verifyToken(env, raw);
    if (!v) return null;
    // `verifyToken` already refuses a token minted for another collection; this
    // is the second lock on the one claim that decides whose accounts these are.
    if (v.claims.collectionName !== "owners") return null;
    const id = String((v.row as Record<string, unknown>).id ?? "");
    // 15 lowercase alphanumerics — src/pb/wire.ts ID_ALPHABET. The brand on
    // `OwnerId` is erased before this line runs, so a display name reaching a
    // query is stopped by a CALL or by nothing at all.
    return /^[a-z0-9]{15}$/.test(id) ? id : null;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// READING WHAT ARRIVED
// ---------------------------------------------------------------------------

/** A JSON body, or null. A body that is not JSON is not a 500. */
async function jsonBody(request: Request): Promise<Record<string, unknown> | null> {
  try {
    const parsed: unknown = await request.json();
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) return null;
    return parsed as Record<string, unknown>;
  } catch {
    return null;
  }
}

/**
 * A toolkit slug as the store spells one: trimmed and lowercased, and NOTHING
 * else. Identical rule to store.ts `checkedToolkit` and nudge.ts `checkedSlug`.
 *
 * THE LINE, because it is one character from a law-1 violation. Legal: case and
 * padding, so a catalog yielding "Notion" and one yielding "notion" are not two
 * connections for one app. Illegal and deliberately absent: any mapping between
 * DIFFERENT slugs — `google_drive` and `google-drive` stay two apps, because a
 * slug is a vendor's primary key and guessing they are the same connects the
 * wrong one.
 */
function slugOf(raw: unknown): string | null {
  const slug = typeof raw === "string" ? raw.trim().toLowerCase() : "";
  return slug === "" ? null : slug;
}

/** A non-empty opaque vendor account id. Compared case-SENSITIVELY everywhere
 *  below: it is a primary key, and folding `CA_X` onto `ca_x` invents a match. */
function accountIdOf(raw: unknown): string | null {
  const id = typeof raw === "string" ? raw.trim() : "";
  return id === "" ? null : id;
}

// ---------------------------------------------------------------------------
// WHAT GOES ON THE WIRE
// ---------------------------------------------------------------------------

/**
 * One connection row, in the column names D1 and contract.ts use, because
 * `Connection(row:)` on the phone reads exactly these and DROPS a row it cannot
 * read whole (ConnectionsPolicy.swift:272-288). Written out field by field
 * rather than spread, so a column added to the table later has to be added here
 * deliberately instead of leaking to every phone on the next deploy.
 */
function connectionRow(c: StoredConnection): Record<string, unknown> {
  return {
    user_id: c.user_id,
    toolkit: c.toolkit,
    connected_account_id: c.connected_account_id,
    alias: c.alias,
    status: c.status,
    // A real JSON boolean. `ConnectionsPolicy.writesOptedIn` accepts `true` and
    // `1` and nothing else, and this is the field that decides whether Anticipy
    // may CHANGE something of theirs.
    writes_enabled: c.writes_enabled === true,
    last_used_at: c.last_used_at,
  };
}

/**
 * One catalog row. `app_url` is snake_case because the phone reads
 * `row["app_url"]` (ConnectedAppsClient.swift:368) while the provider's
 * `ToolkitMeta` spells it `appUrl` — this is the boundary where that is
 * translated, and it is the only place it may be.
 *
 * `mail_hosts` is the same translation for the column the adapter builds beside
 * the contract's fields (`CatalogToolkit` in src/connections/provider.ts). The
 * phone matches a resolved mail exchanger against it — spec page 42's
 * medium-weight signal, matched against the catalog's own entry and never a
 * domain list of ours — and it is the seam that made onboarding step 2 pre-tick
 * nothing while it was missing. AGAINST THE LIVE VENDOR IT IS EMPTY ON EVERY
 * ROW, measured 2026-09-06; the receipt is in the adapter's header. This route
 * carries what the catalog says and decides nothing about it.
 *
 * THE COLUMN IS ALWAYS PRESENT, empty included: a row with no mail hosts and a
 * server too old to know about them are different facts, and a missing key
 * makes the phone guess which one it is holding.
 */
function catalogRow(meta: ToolkitMeta): Record<string, unknown> {
  // Typed as the contract's `ToolkitMeta`, which does not declare this column,
  // and read at run time the way every other field crossing this boundary is —
  // types are stripped before any of this executes, so the only thing standing
  // between a malformed row and the phone is the check below. A blank is not a
  // host and neither is a number: both would reach the phone's `hostLabels()`
  // as a line that can never match, and the second would not even decode.
  const mail = (meta as { mailHosts?: unknown }).mailHosts;
  const mail_hosts: string[] = [];
  if (Array.isArray(mail)) {
    for (const raw of mail) {
      const host = typeof raw === "string" ? raw.trim() : "";
      if (host !== "") mail_hosts.push(host);
    }
  }
  return {
    slug: meta.slug,
    name: meta.name,
    logo: meta.logo ?? null,
    description: meta.description ?? null,
    app_url: meta.appUrl ?? null,
    scopes: Array.isArray(meta.scopes) ? meta.scopes : [],
    mail_hosts,
  };
}

// ===========================================================================
// 1. GET /me/connections
// ===========================================================================

/**
 * This owner's connections, and nobody else's.
 *
 * The store's own `refuseMixedOwners` runs over the answer, so a query that
 * returned a stray row raises instead of being filtered — and it arrives here
 * as the clean failure rather than as a shorter list. A shorter list is the
 * shape that hides the bug; a failure is the shape somebody investigates.
 */
async function handleList(owner: string, deps: ConnectionsApiDeps): Promise<Response> {
  let rows: StoredConnection[];
  try {
    rows = await deps.store.connectionsForOwner(owner);
  } catch (err) {
    // NEVER `{ items: [] }`. Somebody who has connected two apps must not be
    // told they have none because a database was slow.
    console.log(`me/connections: could not read this owner's connections — ${named(err)}`);
    return refuse(503, COULD_NOT_READ);
  }
  return json(200, { items: rows.map(connectionRow) });
}

// ===========================================================================
// 2. GET /me/connections/catalog
// ===========================================================================

async function handleCatalog(
  url: URL, owner: string, deps: ConnectionsApiDeps, now: number,
): Promise<Response> {
  const slugs = url.searchParams.get(QUERY_SLUGS);
  if (slugs !== null) return await describeSlugs(slugs, deps);

  const query = url.searchParams.get(QUERY_SEARCH);
  if (query !== null) return await searchCatalog(query, owner, deps, now);

  return refuse(400, BAD_REQUEST);
}

/** The rows for toolkits this owner already has. */
async function describeSlugs(raw: string, deps: ConnectionsApiDeps): Promise<Response> {
  // Splitting on the separator the client joined with is transport, not
  // meaning: `wanted.joined(separator: ",")` at ConnectedAppsClient.swift:142.
  const asked = [...new Set(
    raw.split(",").map((s) => slugOf(s)).filter((s): s is string => s !== null),
  )];
  // Nothing was asked about, so nothing came back. This is the one empty list
  // in the file that is an answer rather than a failure, and the client never
  // sends it (`guard !wanted.isEmpty`).
  if (asked.length === 0) return json(200, { items: [] });
  if (asked.length > MAX_CATALOG_SLUGS) return refuse(400, BAD_REQUEST);

  const items: Record<string, unknown>[] = [];
  let failures = 0;
  for (const slug of asked) {
    try {
      items.push(catalogRow(await deps.provider.toolkit(slug)));
    } catch {
      // A slug the catalog cannot name is simply not returned; the phone falls
      // back to the slug the connection itself carries. One unknown app must
      // not cost the other three their names.
      failures++;
    }
  }
  // EVERY lookup failed and something was asked: that is the catalog being
  // unreachable, not a catalog with nothing in it. Answering `{ items: [] }`
  // here would tell a screen with four connected apps that none of them has a
  // name, which looks like data rather than like an outage.
  if (items.length === 0 && failures > 0) {
    console.log(`me/connections/catalog: ${failures} of ${asked.length} slugs unreadable`);
    return refuse(503, CATALOG_UNREACHABLE);
  }
  return json(200, { items });
}

/**
 * The whole catalog, searched AS TYPED.
 *
 * The query is handed to the port byte for byte — not trimmed, not lowercased,
 * not tokenised, not matched against anything here. Which app somebody meant is
 * the catalog's question and a model's; a local list would be the thing the
 * spec forbids outright ("a new app in the catalog is a new app in Anticipy
 * with zero code"). The one thing this function knows how to ask about a query
 * is whether there IS one, which is a shape and not a meaning.
 *
 * THE ORDER OF THE THREE GATES IS THE POINT. A malformed ask is refused before
 * a budget is spent on it; an unwired port is reported before a budget is spent
 * on a call that will not happen; the budget is spent last, immediately before
 * the vendor round trip it exists to bound.
 */
async function searchCatalog(
  query: string, owner: string, deps: ConnectionsApiDeps, now: number,
): Promise<Response> {
  // NOTHING WAS TYPED, and both halves of that were MEASURED against the vendor
  // on 2026-09-06 rather than assumed. `?q=` with an empty value becomes
  // `search=` at the far end, which answers 200 with the first page of the whole
  // catalog — 1,505 toolkits, in no relation to anything anybody asked; `?q=`
  // with nothing but spaces is a vendor 400, which would arrive here as an
  // exception and leave the screen saying it could not reach Anticipy. Neither
  // is a lookup failure, so this is a 400 rather than the 503 that means outage.
  //
  // MEASURING EMPTINESS IS NOT READING MEANING, and the line is exactly here: a
  // query with letters in it is passed on untouched, spaces and all, because
  // the phone already trims before it asks (ConnectOnboardingPolicy.searchQuery,
  // ConnectedAppsModel.search — both refuse to send a blank) and its client
  // deliberately does not (ConnectedAppsClientTests pins "  work mail  " going
  // out with its spaces). So this branch is unreachable from the app and exists
  // for everything else that can reach a URL.
  if (query.trim() === "") return refuse(400, BAD_REQUEST);

  if (typeof deps.search !== "function") {
    console.log(
      "me/connections/catalog?q: 503 — no catalog search port is wired on these deps. "
        + "connectionsApiDeps fills it from the provider's own catalog search; a caller "
        + "injecting its own deps must pass one or the search box cannot work.",
    );
    return refuse(503, CATALOG_UNREACHABLE);
  }

  if (!spendSearch(owner, now)) {
    console.log(
      `me/connections/catalog?q: 429 — this owner is over ${MAX_SEARCHES_PER_OWNER} `
        + "searches in the window on this isolate",
    );
    return refuse(429, TOO_MANY_LOOKUPS);
  }

  let hits: unknown;
  try {
    hits = await deps.search(query);
  } catch (err) {
    console.log(`me/connections/catalog?q: the catalog did not answer — ${named(err)}`);
    return refuse(503, CATALOG_UNREACHABLE);
  }
  // A port that answered something other than a list has not told us the
  // catalog is empty; it has told us nothing.
  if (!Array.isArray(hits)) return refuse(503, CATALOG_UNREACHABLE);
  // THE CAP, AGAIN, and not because the provider's is in doubt. This is the
  // seam a port that is not the provider comes through, and a phone rendering
  // one scrolling list must not be handed 1,505 rows by anything. It is the
  // provider's own constant, so there is one number and not two — and it CUTS
  // the vendor's order rather than choosing within it.
  //
  // The mapping is guarded because it is the last place a port's answer is
  // touched: an array holding a null or a string reaches `catalogRow`, which
  // reads fields off it, and an uncaught TypeError out of a route handler is a
  // 500 with a stack in it. 503 is the same thing this function says about
  // every other unusable answer, and the screen already knows how to render it.
  try {
    return json(200, {
      items: hits.slice(0, MAX_SEARCH_RESULTS).map((m) => catalogRow(m as ToolkitMeta)),
    });
  } catch (err) {
    console.log(`me/connections/catalog?q: the answer could not be read — ${named(err)}`);
    return refuse(503, CATALOG_UNREACHABLE);
  }
}

// ===========================================================================
// 3. POST /me/connections/writes
// ===========================================================================

interface AskedWrite {
  toolkit: string;
  connected_account_id: string;
  writes_enabled: boolean;
}

/**
 * One row of a write batch, or null.
 *
 * `writes_enabled` MUST be a real JSON boolean. `"false"` is truthy in
 * JavaScript, and this is the one field on the wire whose value decides whether
 * Anticipy may act on somebody's mailbox — a coercion bug here is an action,
 * not a display defect. The store's own `checkedBool` accepts `0`/`1` because
 * that is how the column comes back out of D1; nothing arriving from a network
 * gets that latitude.
 */
function askedWrite(raw: unknown): AskedWrite | null {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) return null;
  const r = raw as Record<string, unknown>;
  const toolkit = slugOf(r.toolkit);
  const account = accountIdOf(r.connected_account_id);
  const on = r.writes_enabled;
  if (toolkit === null || account === null) return null;
  if (on !== true && on !== false) return null;
  return { toolkit, connected_account_id: account, writes_enabled: on };
}

/**
 * The Settings toggle, "let Anticipy make changes".
 *
 * A ROW BELONGING TO ANYBODY ELSE IS A REFUSAL, NOT A FILTER, and the whole
 * batch stops. Dropping a foreign row would write a smaller batch than the
 * screen just moved, and the switch would read ON over an account nobody wrote
 * — the client makes the same choice at the same seam for the same reason
 * (ConnectedAppsClient.swift:165-189).
 *
 * ONLY `writes_enabled` IS THIS REQUEST'S TO SET. Every other field is taken
 * from the STORED row: the body cannot change a status, re-bind an account to
 * another app or resurrect a deleted connection. The body's `toolkit` is read
 * only to be COMPARED against the stored one, so a batch built against a stale
 * screen is refused rather than applied to the wrong app.
 *
 * VALIDATED IN FULL BEFORE ANYTHING IS WRITTEN. A batch that is half this
 * owner's would otherwise leave the first rows flipped and the screen showing a
 * state the database does not hold.
 */
async function handleWrites(
  request: Request, owner: string, deps: ConnectionsApiDeps,
): Promise<Response> {
  const body = await jsonBody(request);
  const raw = body?.rows;
  if (!Array.isArray(raw)) return refuse(400, BAD_REQUEST);
  if (raw.length === 0) return json(200, { ok: true, updated: 0 });
  if (raw.length > MAX_WRITE_ROWS) return refuse(400, BAD_REQUEST);

  const asked: AskedWrite[] = [];
  const seen = new Set<string>();
  for (const entry of raw) {
    const row = askedWrite(entry);
    if (row === null) return refuse(400, BAD_REQUEST);
    // The same account twice with two answers has no correct outcome, and
    // whichever one won would be arbitrary.
    if (seen.has(row.connected_account_id)) return refuse(400, BAD_REQUEST);
    seen.add(row.connected_account_id);
    asked.push(row);
  }

  const toWrite: StoredConnection[] = [];
  for (const row of asked) {
    let mine: StoredConnection | null;
    try {
      // SCOPED BY THE TOKEN'S OWNER. A connection that exists under somebody
      // else reads as null here — "not yours", never as a row to write.
      mine = await deps.store.readConnection(owner, row.connected_account_id);
    } catch (err) {
      console.log(`me/connections/writes: could not read a connection — ${named(err)}`);
      return refuse(503, COULD_NOT_SAVE);
    }
    if (mine === null) return refuse(403, NOT_YOURS);
    if (mine.toolkit !== row.toolkit) return refuse(409, NOT_YOURS);
    toWrite.push({ ...mine, writes_enabled: row.writes_enabled });
  }

  for (const row of toWrite) {
    try {
      await deps.store.putConnection(row);
    } catch (err) {
      // The toggle is idempotent, so a retry finishes what this stopped. Saying
      // it did not save is the honest half even when some of it did.
      console.log(`me/connections/writes: could not save a toggle — ${named(err)}`);
      return refuse(503, COULD_NOT_SAVE);
    }
  }
  return json(200, { ok: true, updated: toWrite.length });
}

// ===========================================================================
// 4. POST /me/connections/disconnect
// ===========================================================================

/**
 * REVOKE, THEN DELETE, and report only what actually happened.
 *
 * The three booleans are read by `ConnectionsPolicy.disconnectConfirmation`,
 * which turns them into the one sentence the person sees:
 *
 *   revoked && deleted   "Done. X disconnected and access revoked."
 *   revoked only         "X access is revoked — nothing can use it from here.
 *                         Its entry is still on file on my side…"
 *   deleted only         "Done. X is disconnected here. X may still list
 *                         Anticipy in its own settings…"
 *   neither              "I couldn't disconnect X just now, so nothing has
 *                         changed."
 *
 * So `deleted` means OUR record is gone — that is what "on file on my side"
 * refers to — and it is reported true only when the vendor's account row AND
 * this owner's D1 row are both gone. `revoked` means the token is genuinely
 * dead at the far end and is the only thing that licenses the word "revoked";
 * telling somebody their access was revoked when it was not is a lie they
 * cannot detect until it matters.
 *
 * THE ORDER OF THE GATES IS THE SECURITY. The local row is read first, scoped
 * by the token's owner, so an account id belonging to somebody else never
 * reaches the vendor's `revoke` and `DELETE` endpoints — which take an account
 * id and no user scoping whatsoever.
 */
async function handleDisconnect(
  request: Request, owner: string, deps: ConnectionsApiDeps,
): Promise<Response> {
  const body = await jsonBody(request);
  const account = accountIdOf(body?.connected_account_id);
  if (account === null) return refuse(400, BAD_REQUEST);

  let mine: StoredConnection | null;
  try {
    mine = await deps.store.readConnection(owner, account);
  } catch (err) {
    console.log(`me/connections/disconnect: could not read the connection — ${named(err)}`);
    return refuse(503, COULD_NOT_DISCONNECT);
  }
  // Not this owner's — which includes "it exists under somebody else". The
  // answer is the same either way and discloses nothing about which.
  if (mine === null) return refuse(404, NOT_YOURS);

  const who = ownerId(owner);

  // The app's NAME, from the catalog, read BEFORE anything is removed: after
  // the delete there is no toolkit left to look it up by. A catalog blip costs
  // the name in one sentence, never the disconnect — the phone's own
  // `appName(nil, fallback:)` handles an empty one.
  let appName = "";
  try {
    appName = (await deps.provider.toolkit(mine.toolkit))?.name ?? "";
  } catch {
    appName = "";
  }
  if (typeof appName !== "string") appName = "";

  // DOES THE VENDOR STILL HOLD THIS ACCOUNT FOR THIS OWNER? Asked as a
  // question with a positive answer rather than inferred from an exception.
  // The list is owner-scoped and the adapter refuses one carrying a stray
  // owner, so a successful answer is real evidence.
  let held: Connection[];
  try {
    held = await deps.provider.connections(who);
  } catch (err) {
    // No evidence either way. NOTHING is deleted: the account id is the only
    // handle we will ever have for revoking this token, and destroying it while
    // the token may still be live at the far end is the one irreversible
    // mistake this route can make.
    console.log(`me/connections/disconnect: the catalog did not answer — ${named(err)}`);
    return refuse(503, COULD_NOT_DISCONNECT);
  }

  const vendorHolds = Array.isArray(held) && held.some(
    (c) => typeof c?.connected_account_id === "string"
      && c.connected_account_id.trim() === account,
  );

  if (!vendorHolds) {
    // A STALE ROW, AND THE SELF-HEAL FOR OUR OWN PARTIAL FAILURE. The vendor
    // answered for this owner and does not hold this account: the commonest way
    // that happens is a previous disconnect that revoked and deleted at the far
    // end and then failed to delete here. There is nothing left to revoke, so
    // clearing our own row is the whole of what is left to do — and without
    // this branch the row could never leave the person's screen.
    const deleted = await safeDelete(deps, owner, account);
    console.log("me/connections/disconnect: cleared a row the catalog no longer holds");
    return json(200, {
      revoked: false, deleted, revoke_unavailable: false, app_name: appName,
    });
  }

  let out: DisconnectResult;
  try {
    out = await deps.provider.disconnect(who, account);
  } catch (err) {
    console.log(`me/connections/disconnect: the disconnect failed — ${named(err)}`);
    return refuse(503, COULD_NOT_DISCONNECT);
  }

  const localDeleted = await safeDelete(deps, owner, account);
  return json(200, {
    // EACH FIELD IS A FLOOR: anything that is not exactly `true` is false.
    // "Nobody said yes" and "somebody said no" are the same answer when the
    // question is whether to tell a person their access is gone.
    revoked: out?.revoked === true,
    deleted: out?.deleted === true && localDeleted,
    revoke_unavailable: out?.revokeUnavailable === true,
    app_name: appName,
  });
}

/** Remove this owner's row, reporting whether it went. A failure here is never
 *  an exception out of the route: the far end has already been changed, and the
 *  person is owed the truth about that half rather than a 500. */
async function safeDelete(
  deps: ConnectionsApiDeps, owner: string, account: string,
): Promise<boolean> {
  try {
    return await deps.store.deleteConnection(owner, account) === true;
  } catch (err) {
    console.log(`me/connections/disconnect: our own row survived — ${named(err)}`);
    return false;
  }
}

// ===========================================================================
// 5. POST /me/connections/sentences
// ===========================================================================

/**
 * The three plain sentences, from the toolkit's own scopes.
 *
 * SAME PATH AS THE CONNECT PAGE. `deps.words` is built from the same two
 * functions in the same order that `connectDeps` hands routes/connect.ts, and
 * the suite pins the expression in both files — so the disclosure sheet on the phone
 * and the page in Safari cannot describe one app two different ways. words.ts
 * audits the register at that end; ConnectedAppsClient puts the answer through
 * the register gate again at the phone's end, because "a model wrote a bad
 * sentence" and "a bad sentence arrived on this phone from anywhere at all" are
 * different failures.
 *
 * IT NEVER ANSWERS `{ "sentences": [] }`. A blank disclosure is not a
 * disclosure, and neither is a partial one: showing two of three claims asks
 * somebody to agree to less than they are agreeing to, which is the same defect
 * with better manners.
 */
async function handleSentences(
  request: Request, deps: ConnectionsApiDeps,
): Promise<Response> {
  const body = await jsonBody(request);
  const slug = slugOf(body?.toolkit);
  if (slug === null) return refuse(400, BAD_REQUEST);

  let meta: ToolkitMeta;
  try {
    meta = await deps.provider.toolkit(slug);
  } catch (err) {
    console.log(`me/connections/sentences: no catalog row — ${named(err)}`);
    return refuse(503, NO_SENTENCES);
  }

  let lines: unknown;
  try {
    lines = await deps.words.sentences(meta);
  } catch (err) {
    // `PermissionWordsRefused` and a dead model both land here, and both are
    // retryable rather than a verdict about this app.
    console.log(`me/connections/sentences: refused — ${named(err)}`);
    return refuse(503, NO_SENTENCES);
  }

  const clean = Array.isArray(lines)
    ? lines.filter((s): s is string => typeof s === "string" && s.trim() !== "")
    : [];
  // A blank among good ones is refused too, not filtered. HOW MANY there should
  // be is deliberately not checked here — that is words.ts's question, and a
  // count rule at this seam would be an outage the first time a one-scope
  // toolkit arrives.
  if (!Array.isArray(lines) || clean.length === 0 || clean.length !== lines.length) {
    return refuse(503, NO_SENTENCES);
  }
  return json(200, { sentences: clean });
}

// ===========================================================================
// 6. POST /me/connections/link
// ===========================================================================

/**
 * OUR single-use link, minted now, bound to this owner and this app.
 *
 * ONE MINTER. `mintConnectLink` (src/connections/nudge.ts) is the only function
 * in this Worker that creates a `connect_links` row, and this route calls it
 * rather than repeating it: two minters would be two answers to what a token is
 * worth, and they would disagree the first time one of them was edited. The raw
 * token exists in that function's locals and in the URL below; the row holds
 * sha256(token) and the log line holds twelve hex characters of the handle,
 * which cannot be redeemed.
 *
 * THE HOST THIS MINTS ON IS NOT THE HOST THE PHONE ACCEPTS, TODAY. `baseUrl` is
 * left unset so the base is `env.CONNECT_BASE_URL ?? CONNECT_URL_BASE`, exactly
 * routes/connect.ts's own precedence — a link minted on one base and a callback
 * built on another is a broken connect. That constant is
 * `https://api.anticipy.ai/c` (measured: the apex answers 301 and www answers
 * 307, so neither reaches this Worker), while
 * `ConnectHandoff.connectLinkHosts` on the phone is `["anticipy.ai"]`. The
 * client therefore refuses what this route mints, loudly and by code, rather
 * than opening it — ConnectedAppsClientTests pins that refusal by name. The fix
 * is one route on the apex plus one constant, in files this change does not
 * own; it is written here so the next reader does not rediscover it as a bug.
 */
async function handleLink(
  request: Request, env: ConnectionsApiEnv, owner: string,
  deps: ConnectionsApiDeps, now: number,
): Promise<Response> {
  const body = await jsonBody(request);
  const slugs = pageOf(body);
  if (slugs === null) return refuse(400, BAD_REQUEST);

  let held: StoredLink[];
  try {
    held = await deps.store.linksForOwner(owner);
  } catch (err) {
    console.log(`me/connections/link: could not count this owner's links — ${named(err)}`);
    return refuse(503, COULD_NOT_READ);
  }
  // Every row carries its expiry rather than its birthday, and the TTL is the
  // one constant both halves share, so `expires_at - LINK_TTL_MS` IS the moment
  // it was minted. Reading the window off the same constant the mint uses means
  // there is no second answer to how long a link lives.
  //
  // THE BUDGET COUNTS LINKS, NOT ROWS, and the difference arrived with the
  // multi-app page. A page of four apps writes four `connect_links` rows on ONE
  // token, so counting rows charged this ceiling four times for one tap of one
  // Connect button — somebody who ticked four apps, changed their mind and
  // ticked four again would be locked out of connecting anything for an hour.
  // That is an outage wearing a rate limit's clothes, and it would have shipped
  // on the exact flow the spec asks for.
  //
  // A PAGE IS ITS MINT INSTANT. Every row of one page is written with a single
  // `expires_at` computed once (`mintConnectPage`), so the distinct expiries in
  // the window ARE the mints in the window. The one shape where that undercounts
  // is two separate pages minted in the same millisecond for one owner, which
  // costs that owner one extra mint out of six and cannot be provoked usefully:
  // this is a courtesy ceiling on top of an authenticated route, not a defence.
  // The alternative — a group id column — needs a schema change and an index to
  // answer a question the clock already answers.
  const since = now - LINK_WINDOW_MS;
  const mints = new Set<number>();
  for (const row of held) {
    const mintedAt = Number(row?.expires_at) - LINK_TTL_MS;
    if (Number.isFinite(mintedAt) && mintedAt >= since) mints.add(mintedAt);
  }
  if (mints.size >= MAX_LINKS_PER_OWNER) {
    console.log(`me/connections/link: 429 — ${mints.size} links already minted in the window`);
    return refuse(429, TOO_MANY_LINKS);
  }

  let minted: MintedLink;
  try {
    minted = await mintConnectPage(env, owner, slugs, null, linkOnlyDeps(deps));
  } catch (err) {
    console.log(`me/connections/link: could not mint — ${named(err)}`);
    return refuse(503, COULD_NOT_READ);
  }

  // The fingerprint, NEVER the token and never the URL. A support transcript, a
  // breadcrumb or a `wrangler tail` carrying a whole token hands its reader an
  // account binding. The COUNT of apps is safe and worth having: it is the one
  // number that says whether the page the phone asked for is the page it got.
  console.log(`me/connections/link: minted ${minted.fingerprint}, ${minted.toolkits.length} app(s)`);
  return json(200, {
    url: minted.url,
    expires_at: minted.expires_at,
    // ECHOED BACK, IN THE ORDER THE PAGE WILL DRAW THEM. The phone ticked a set
    // and gets told which set this link actually carries — so a mint that
    // silently dropped one is visible on the client rather than only at the
    // moment somebody notices an app missing from the page. Catalog slugs
    // carry no token material.
    toolkits: minted.toolkits,
  });
}

/**
 * WHICH APPS THIS LINK IS FOR — one, or the whole set somebody ticked.
 *
 * TWO SHAPES, ONE MEANING, and the older one is not deprecated by accident:
 *   `{ "toolkit": "slack" }`             every build in the wild today
 *   `{ "toolkits": ["slack", "notion"] }` the setup card's one Connect button
 *
 * Both are accepted and both go down the same path — a page of one is a page.
 * A body naming BOTH is refused rather than reconciled: two fields disagreeing
 * about what somebody ticked is a client bug, and picking a winner would connect
 * a set nobody chose.
 *
 * `null` IS THE ONLY REFUSAL and it is a 400. There is no partial read: a list
 * with one unusable entry is refused whole, because filtering it would mint a
 * page silently shorter than the one the person is about to be shown.
 *
 * THE CEILING IS CHECKED HERE TOO, AND THAT IS NOT A DUPLICATE BY ACCIDENT.
 * `mintConnectPage` refuses a page past `MAX_PAGE_APPS` as a library invariant
 * and THROWS, which this route can only turn into a 503 — "we are broken, try
 * again later" for a body that will never be acceptable, which a client then
 * retries forever. A request naming thirteen apps is the caller's mistake and
 * gets the caller's status code. The number is imported from the one file that
 * declares it, so the two cannot disagree about it; only about whose fault it
 * is, which is the whole point.
 */
function pageOf(body: Record<string, unknown> | null): string[] | null {
  const many = body?.toolkits;
  const one = body?.toolkit;
  if (many !== undefined && many !== null) {
    if (one !== undefined && one !== null) return null;
    if (!Array.isArray(many) || many.length === 0) return null;
    if (many.length > MAX_PAGE_APPS) return null;
    const slugs: string[] = [];
    for (const raw of many) {
      const slug = slugOf(raw);
      if (slug === null) return null;
      // A set the person ticked cannot contain the same box twice, so a repeat
      // is a client that lost track rather than a preference to honour.
      if (slugs.includes(slug)) return null;
      slugs.push(slug);
    }
    return slugs;
  }
  const slug = slugOf(one);
  return slug === null ? null : [slug];
}

// ===========================================================================
// 7. POST /me/connections/skip
// ===========================================================================

/**
 * NO, RECORDED ON THE SERVER, where the ask engine can read it.
 *
 * The body is `{ "toolkit": "<slug>", "onboarding": true|false }`. That is the
 * whole shape and every other field is ignored — there is no owner on it, and
 * there is no level, no snooze and no state either: what a decline COSTS is the
 * ladder's answer (connections/nudge.ts `recordDecline`), not a number a client
 * may name. A client that could set the snooze could set it to zero.
 *
 * `onboarding` IS A SURFACE, NOT A MEANING. It says which screen the person was
 * looking at — the setup card, or anything else — and page 21 gives the setup
 * card a seven-day soft snooze rather than a real decline. It is read as a
 * strict JSON boolean, exactly as `writes_enabled` is, because a string
 * `"false"` is truthy in JavaScript and this field shortens how long somebody
 * is left alone.
 *
 * ABSENT MEANS THE ORDINARY DECLINE, and that default points the safe way.
 * Not-stated becomes the FOURTEEN-day L1, which is the longer quiet: a client
 * that forgets the field leaves the person alone for longer than the spec
 * requires, and the failure this route exists to fix is being asked again too
 * soon. A field that is present and is not a boolean is a 400 rather than a
 * guess — a malformed claim is not evidence of either answer.
 *
 * AND THE STORED ROW STILL WINS. `recordSkip` only ever uses `onboarding` to
 * SEED a nudge row that does not exist yet; a row the ask engine already wrote
 * keeps its own trigger. Without that asymmetry a client could send
 * `onboarding` on every skip and shorten every snooze it ever wrote.
 */
async function handleSkip(
  request: Request, owner: string, deps: ConnectionsApiDeps, now: number,
): Promise<Response> {
  const body = await jsonBody(request);
  const slug = slugOf(body?.toolkit);
  if (slug === null) return refuse(400, BAD_REQUEST);

  const raw = body?.onboarding;
  if (raw !== undefined && raw !== null && raw !== true && raw !== false) {
    return refuse(400, BAD_REQUEST);
  }

  // SCOPED BY THE TOKEN'S OWNER, like every other write in this file. There is
  // no field on the body through which a caller could decline on somebody
  // else's behalf, and `ownerId` is called rather than assumed because the
  // brand on `OwnerId` is erased before this line runs.
  const outcome = await recordSkip(
    deps.store,
    { user_id: ownerId(owner), toolkit: slug, at: now },
    { onboarding: raw === true },
  );

  if (outcome.state === "not-recorded") {
    // NEVER `{ ok: true }`. A phone told its skip landed will not send it again,
    // and the person is then asked again by a server that never heard them.
    console.log(`me/connections/skip: nothing was written — ${outcome.why}`);
    return refuse(503, COULD_NOT_SAVE);
  }
  if (outcome.state === "nothing-to-decline") {
    // Honest and not an error: they already have this one connected, so there
    // was no ask to turn down and no row to move.
    return json(200, { ok: true, state: outcome.state });
  }
  return json(200, {
    ok: true,
    state: outcome.state,
    level: outcome.level,
    snooze_until: outcome.snooze_until,
    /**
     * WAS THIS THE SEVEN-DAY SHRUG OR A RUNG ON THE LADDER? The two are
     * different things to have done to somebody and the phone acts on the
     * difference — `ConnectOnboardingPolicy.serverAgreedWithSkip` refuses to
     * believe a skip landed unless the far end recorded what the card means.
     *
     * It is `recordDecline`'s own answer about the row it wrote, carried
     * through `recordSkip`, and NOT re-derived from the request's `onboarding`
     * flag. Deriving it here would report a level-2 decline as soft whenever
     * the ask that produced it happened to have come from a setup card.
     *
     * `false` on `already-declined`, which is honest rather than lossy: that
     * branch wrote NOTHING, so no soft snooze was recorded by this call. The
     * level and the date beside it say what is standing.
     */
    soft: outcome.state === "recorded" ? outcome.soft : false,
  });
}

// ===========================================================================
// 8. GET /me/connections/signals
// ===========================================================================

/**
 * THE FOUR THINGS THIS ROUTE CAN SAY, named once so the phone branches on a
 * field and never on our copy.
 *
 *   ranked              here is the evidence, best first.
 *   none                we looked, and this owner has none yet.
 *   unreadable          we could not look.
 *   catalog-unreadable  we looked, found apps, and could not name one of them.
 *
 * THREE OF THEM COME BACK EMPTY AND THE SCREEN DRAWS THEM THREE WAYS: nothing
 * pre-ticked and a search box; "ask me again in a moment"; and "I know what you
 * use and cannot describe it right now". Collapsing any two would be the
 * confident empty this file's header refuses — a person with months of evidence
 * shown a clean blank list on the one screen that then asks them to connect
 * what they already live in.
 */
export const SIGNALS_ANSWER = {
  ranked: "ranked",
  none: "none",
  unreadable: "unreadable",
  catalogUnreadable: "catalog-unreadable",
} as const;

/**
 * What `rankedApps` is handed: THIS OWNER'S EVIDENCE, READ AND NOT WRITTEN.
 *
 * `SignalStore` is `recordSignal` and `signalsForOwner` together, because the
 * six ingest doors in signals.ts need both. This route needs one of them, and
 * the other is supplied as a REFUSAL rather than passed through — the same
 * shape `linkOnlyDeps` uses below, for the same reason. A read route that could
 * also record evidence would let anybody with a session weight their own table,
 * and weight is what eventually licenses interrupting somebody.
 */
function signalReaderFor(deps: ConnectionsApiDeps): SignalStore {
  return {
    signalsForOwner: (user) => deps.store.signalsForOwner(user),
    recordSignal: (): never => {
      throw new Error(
        "me/connections/signals asked to RECORD a signal: this route answers a question "
          + "about an owner's evidence and must never be able to add to it",
      );
    },
  };
}

/**
 * One line of the answer: the ranked evidence, with the catalog's own row on it.
 *
 * THE CATALOG HALF IS `catalogRow` ITSELF, not a second spelling of it, so a
 * line here and a line from `?slugs=` are the same six fields in the same names
 * and the phone reads both with one decoder. The evidence half is three facts
 * and no verdict:
 *
 *   alias         which of this owner's accounts the strongest evidence was
 *                 about, or null when it did not say.
 *   last_seen_at  when, so a screen can say "seen last Tuesday".
 *   sources       which kinds of evidence fed the line, sorted.
 *
 * AND THE WEIGHT IS DELIBERATELY NOT ON THE WIRE. It is an ordering with no
 * unit — it decays between two calls, so the same evidence is a different
 * number this afternoon — and the ORDER is already the answer to every question
 * a client can honestly ask of it. A number on the wire is an invitation to
 * `if weight > 0.5` on the phone, which is a second policy about who gets asked
 * to connect what, written where nobody reviewing this feature would look.
 */
function signalRow(line: RankedApp, meta: ToolkitMeta): Record<string, unknown> {
  return {
    ...catalogRow(meta),
    alias: line.alias ?? null,
    last_seen_at: line.lastSeenAt,
    sources: line.sources,
  };
}

/**
 * THIS OWNER'S APPS, MOST-LIVED-IN FIRST, READY TO DRAW.
 *
 * The ranking is `rankedApps` and nothing here re-sorts it: two definitions of
 * which app is first would be a list that reorders itself between the screen
 * and the message about it (src/connections/signals.ts `compareRankedApps`).
 * This route does exactly three things to that list — one line per app, cut to
 * `MAX_SIGNAL_APPS`, name each one from the catalog.
 *
 * ONE LINE PER APP. The ranked table is keyed by (toolkit, account), so an
 * owner with two accounts on one app has two lines. A screen drawing them both
 * shows the same name, the same logo and two checkboxes. The STRONGEST line
 * represents the app — which is a cut of the existing order and not a merge:
 * summing two lines' weights here would be this file inventing ranking
 * arithmetic that signals.ts owns.
 *
 * A SLUG THE CATALOG CANNOT NAME IS DROPPED, exactly as `?slugs=` drops one:
 * a row with no name renders as a blank line with a checkbox on it. Every slug
 * failing is a different claim — that is the catalog being unreachable, not an
 * owner with unnameable apps — and it is answered as an outage that says so.
 */
async function handleSignals(
  owner: string, deps: ConnectionsApiDeps, now: number,
): Promise<Response> {
  let ranked: RankedApp[];
  try {
    // SCOPED BY THE TOKEN'S OWNER, and checked against the rows that come back:
    // `rankedApps` re-reads the id it was given against every row and raises on
    // a mixed or swapped table rather than ranking somebody else's apps.
    ranked = await rankedApps(signalReaderFor(deps), owner, now);
  } catch (err) {
    // NEVER `{ items: [] }`. "You have no apps" and "I could not look" are
    // different sentences, and only one of them is true here.
    console.log(`me/connections/signals: could not read this owner's evidence — ${named(err)}`);
    return refuse(503, COULD_NOT_READ, SIGNALS_ANSWER.unreadable);
  }

  const wanted: RankedApp[] = [];
  const seen = new Set<string>();
  for (const line of ranked) {
    if (seen.has(line.toolkit)) continue;
    seen.add(line.toolkit);
    wanted.push(line);
    // CUT BEFORE THE LOOKUPS, not after: the apps past the cut must cost no
    // vendor round trip, or the ceiling bounds the payload and not the spend.
    if (wanted.length >= MAX_SIGNAL_APPS) break;
  }

  // THE HONEST EMPTY, and the only one in this route that is an answer rather
  // than a failure: we read the table, and this owner has nothing in it yet.
  // The catalog is not asked, because there is nothing to name.
  if (wanted.length === 0) return json(200, { items: [], state: SIGNALS_ANSWER.none });

  const items: Record<string, unknown>[] = [];
  let failures = 0;
  for (const line of wanted) {
    try {
      items.push(signalRow(line, await deps.provider.toolkit(line.toolkit)));
    } catch {
      failures++;
    }
  }
  if (items.length === 0 && failures > 0) {
    console.log(`me/connections/signals: ${failures} of ${wanted.length} apps unnameable`);
    return refuse(503, CATALOG_UNREACHABLE, SIGNALS_ANSWER.catalogUnreadable);
  }
  return json(200, { items, state: SIGNALS_ANSWER.ranked });
}

/**
 * What `mintConnectLink` is handed.
 *
 * It reads three things off its deps — `store`, `now` and `baseUrl` — and the
 * other four ports on `NudgeDeps` belong to the ASK (`sendConnectAsk`,
 * `connectNudgeSweep`), which this route never runs. They are supplied as
 * REFUSALS rather than as a cast, so the day minting reaches for one it throws
 * a sentence naming the reason instead of reading `undefined` off an object
 * somebody promised was complete. `baseUrl` is deliberately left unset: nudge.ts
 * then falls back to `env.CONNECT_BASE_URL ?? CONNECT_URL_BASE`, which is
 * routes/connect.ts's own precedence, and setting it here would SHADOW the
 * variable a preview deployment sets.
 */
function linkOnlyDeps(deps: ConnectionsApiDeps): NudgeDeps {
  const notAnAsk = (port: string): never => {
    throw new Error(
      `me/connections/link asked for the nudge's ${port} port: this route mints a link and `
        + "never sends an ask, so nothing here can answer it",
    );
  };
  return {
    // `NudgeStore` is wider than `ConnectionsApiStore`: it can also read and
    // write `connect_nudges`, which minting never touches and this route must
    // not be able to. Only `put` is passed through; the three nudge methods
    // refuse, so the narrowing survives the call rather than being widened away
    // by it.
    store: {
      put: (row) => deps.store.put(row),
      putAll: (rows) => deps.store.putAll(rows),
      readNudge: () => notAnAsk("readNudge"),
      nudgesForOwner: () => notAnAsk("nudgesForOwner"),
      putNudge: () => notAnAsk("putNudge"),
    },
    catalog: { toolkit: () => notAnAsk("catalog") },
    write: () => notAnAsk("write"),
    moment: () => notAnAsk("moment"),
    phone: () => notAnAsk("phone"),
    due: () => notAnAsk("due"),
    now: deps.now,
  };
}

// ===========================================================================
// THE ENTRY POINT
// ===========================================================================

/** What a log line may say about a failure: the error's NAME, never its
 *  message. The vendor's error text is theirs, may name them, and may quote our
 *  own request — including a header — back at us. */
function named(err: unknown): string {
  const name = (err as { name?: unknown })?.name;
  return typeof name === "string" && name !== "" ? name : "unknown failure";
}

/**
 * The entry point src/index.ts registers.
 *
 * `deps` is injectable so the suite can drive the real handlers against a real
 * SQLite loaded with the real schema; production passes nothing and gets the
 * wiring above.
 */
export async function connectionsApiRoute(
  request: Request, env: ConnectionsApiEnv, deps?: ConnectionsApiDeps,
): Promise<Response> {
  const url = new URL(request.url);
  const leg = parseConnectionsApiPath(url.pathname);
  if (leg === null) return refuse(404, NOT_A_ROUTE);

  const method = request.method === "HEAD" ? "GET" : request.method;
  const wants = METHOD[leg];
  if (method !== wants) {
    return new Response(null, {
      status: 405,
      headers: { allow: wants, "cache-control": "no-store" },
    });
  }

  // BEFORE THE STORE, THE CATALOG AND THE MODEL ARE EVEN BUILT. A caller who
  // has proved nothing costs this Worker one HMAC verification and nothing
  // else: no D1 read, no vendor round trip, no model call.
  const owner = await whoIsAsking(request, env);
  if (owner === null) return refuse(401, SIGN_IN_FIRST);

  const wired = deps ?? connectionsApiDeps(env);
  if (!wired) return refuse(503, COULD_NOT_READ);

  const now = wired.now ? wired.now() : Date.now();

  switch (leg) {
    case "list": return await handleList(owner, wired);
    case "catalog": return await handleCatalog(url, owner, wired, now);
    case "writes": return await handleWrites(request, owner, wired);
    case "disconnect": return await handleDisconnect(request, owner, wired);
    case "sentences": return await handleSentences(request, wired);
    case "link": return await handleLink(request, env, owner, wired, now);
    case "skip": return await handleSkip(request, owner, wired, now);
    case "signals": return await handleSignals(owner, wired, now);
  }
}
