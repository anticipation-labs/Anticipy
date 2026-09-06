/**
 * store.ts — the four connections tables, and the only code that writes them.
 *
 * WHAT THIS IS FOR. "Connect your Notion." Every connection belongs to the
 * owner signed in, and the failure this whole feature is shaped around is a
 * connection bound to the wrong person: during the spike one operator's own
 * mailbox was connected by hand, and it had to be revoked and deleted
 * (research/2026-09-05-composio-connections.md, item 2). So every read and
 * every write below is scoped by the owner ROW id, and a result set that
 * carries somebody else's row is REFUSED rather than filtered.
 *
 * SHAPE COMES FROM THE CONTRACT, which is fixed and must not be edited:
 * spike/two-hands/src/connections/contract.ts. The tables are declared in
 * migration/d1/schema.sql section 5. test/connections-store.test.ts parses the
 * contract's own source and compares it to the shape schema.sql DECLARES (an
 * in-process SQLite loaded with that file), so the three declared deviations
 * below are the ONLY ones that can exist without a red test. That is a
 * repo-level proof, NOT a Law-3 one: whether the LIVE database has these
 * tables is answered only by the wrangler command below, run against it.
 *
 * THE STATEMENTS TO RUN AGAINST LIVE D1 (idempotent; re-running is a no-op):
 *
 *   wrangler d1 execute anticipy-backend --remote \
 *     --file=migration/d1/schema.sql
 *
 * or, to apply just this feature, run the four `CREATE TABLE IF NOT EXISTS`
 * statements and the three `CREATE INDEX IF NOT EXISTS` statements in section
 * 5 of that file (`app_usage_signals`, `connections`, `connect_nudges`,
 * `connect_links`, `idx_connections_owner`, `idx_connect_links_owner`,
 * `idx_connect_links_expiry`). They are not repeated here on purpose: a second
 * copy of the DDL is a second book, and the two disagree the first time one of
 * them is edited. Verify with, per LAW 3, against the LIVE database and not a
 * local one:
 *
 *   wrangler d1 execute anticipy-backend --remote --command \
 *     "SELECT name FROM sqlite_master WHERE type='table' AND name IN \
 *      ('app_usage_signals','connections','connect_nudges','connect_links')"
 *
 * THE 1101 THIS FILE IS BUILT AROUND. On 2026-09-05 the live `events` table
 * was missing two columns migration/d1/schema.sql declared, and every create
 * turned into a D1 1101 for two minutes — a Worker that INSERTs a column the
 * live table lacks fails EVERY write, not the one column. src/pb/records.ts
 * answered that with `liveColumns()` (pragma_table_info) + `fillEmpties()`
 * (fill only what exists). This file follows the same pattern with one
 * difference, stated because it is a difference and not an oversight:
 * records.ts DEGRADES on a missing column because its tables carry years of
 * PocketBase rows and a partial write beats no write. These four tables are
 * new, empty and have exactly one writer — this file — so a missing column
 * that carries a SAFETY property (owner scoping, the single-use gate, the
 * write opt-in, the snooze) makes the store REFUSE with the statement to run,
 * rather than write rows that are quietly wrong forever. Columns that only
 * carry tuning or a nicety degrade the way records.ts does. `REQUIRED` and
 * `OPTIONAL` below say which is which, per column, with the reason.
 */

/// <reference types="@cloudflare/workers-types" />

// ---------------------------------------------------------------------------
// THE CONTRACT. TYPES IMPORTED; THE ONE RUNTIME RULE RE-DECLARED AND PINNED.
// ---------------------------------------------------------------------------
// `import type` is ERASED before this file is bundled or run, so the deployed
// Worker carries no dependency on the spike tree — but the shapes are the
// contract's OWN declarations rather than a second copy of them. That matters
// more here than anywhere: a copied `OwnerId` would be a second `unique
// symbol` brand, and a row this store handed back would not assign to the
// `Connection` that commands.ts takes. One definition, no wall.
// (provider.ts and words.ts in this directory reach the contract the same way;
// when the Worker grows its own contract module this is one line to repoint.)
import type {
  AccountAlias,
  AppUsageSignal,
  Connection,
  ConnectNudge,
  NudgeState,
  NudgeTrigger,
  OwnerId,
  Toolkit,
} from "../../../../spike/two-hands/src/connections/contract.ts";

export type { AccountAlias, NudgeState, NudgeTrigger, OwnerId, Toolkit };

/** The closed sets, read off the contract's own interfaces rather than
 *  re-typed. A sixth signal source added there is a sixth one here. */
export type SignalSource = AppUsageSignal["source"];
export type ConnectionStatus = Connection["status"];
export type NudgeChannel = NonNullable<ConnectNudge["channel"]>;

/**
 * THE ONE THING THAT CANNOT BE IMPORTED: a runtime check.
 *
 * `ownerId` is a FUNCTION, so importing it would pull the spike's module into
 * the Worker's bundle. It is re-declared here, character for character, and
 * test/connections-store.test.ts asserts against the contract's own source
 * text that the rule has not drifted — which is the same treatment provider.ts
 * gives its copy of this rule.
 *
 * It has to be a call and not a signature: the brand above is erased before
 * this code runs, so a display name reaching a query is stopped HERE or
 * nowhere. One operator's mailbox served everybody once already.
 */
export function ownerId(raw: string): OwnerId {
  const id = String(raw ?? "").trim();
  // The ids this system mints are 15 lowercase alphanumerics. An email or a
  // human name reaching here means a caller has confused "who is this" with
  // "what do we call them", and the connection would bind to the wrong person.
  if (!/^[a-z0-9]{15}$/.test(id)) {
    throw new Error(
      `not an owner id: ${JSON.stringify(raw)} — connections bind to the owner ROW id, `
        + "never a name or an email",
    );
  }
  return id as OwnerId;
}

// The closed sets as VALUES, because `--experimental-strip-types` DELETES
// every annotation above before the first line runs. A row coming back from D1
// with a column renamed, or a caller in plain JS, arrives here as `any`; a
// union type stops precisely nobody at run time. Each list is pinned to the
// contract's source text by the test file, member for member.
export const SIGNAL_SOURCES: readonly SignalSource[] =
  ["said", "observer", "mx", "link", "connected", "asked"];
export const CONNECTION_STATUSES: readonly ConnectionStatus[] =
  ["connected", "needs_reconnect", "disconnected"];
export const NUDGE_STATES: readonly NudgeState[] =
  ["never_asked", "asked", "declined", "connected", "needs_reconnect"];
export const NUDGE_TRIGGERS: readonly NudgeTrigger[] =
  ["in_task", "repeated_use", "laptop_closed", "user_named_it", "onboarding"];
export const NUDGE_CHANNELS: readonly NudgeChannel[] = ["sms", "ios"];

// ---------------------------------------------------------------------------
// THE ROWS
// ---------------------------------------------------------------------------

/**
 * `app_usage_signals`. The contract's `AppUsageSignal` plus `alias`.
 *
 * DECLARED DEVIATION 1/3. The contract's row cannot say WHICH of the owner's
 * two accounts a piece of evidence was about, so work and personal would merge
 * into one row and the ask that came out of it could not name the account. The
 * spike added the column (signals.ts `StoredSignal`) and reported it back as a
 * contract problem rather than editing the fixed contract; this port carries
 * the same column for the same reason.
 *
 * `null` is the honest and by far the commonest value: "we have no idea which
 * account this was about". Nothing here ever turns a null into a guess.
 */
export interface StoredSignal extends AppUsageSignal {
  alias: AccountAlias | null;
}

/** The four columns that identify one signal row. `alias` is part of it: two
 *  accounts on one app are two piles of evidence, not one. */
export interface SignalKey {
  user_id: OwnerId | string;
  toolkit: Toolkit;
  source: SignalSource;
  alias?: AccountAlias | null;
}

/** `connections`. Exactly the contract's `Connection` — the alias exists so
 *  every table in this file is named the same way, not to leave room for a
 *  divergence. THE WRITE OPT-IN (`writes_enabled`) is off by default: it is
 *  the Settings toggle "let Anticipy make changes", the Two Hands ladder
 *  cannot reach rung 3 without it, and reads never require it. */
export type StoredConnection = Connection;

/** `connect_nudges`. Exactly the contract's `ConnectNudge`. `level` is 0 while
 *  never declined; 1, 2, 3 as declines accumulate; level 3 stops. */
export type StoredNudge = ConnectNudge;

/**
 * `connect_links`. The contract's `ConnectLink` with two declared deviations,
 * both ported from spike/two-hands/src/connections/links.ts:
 *
 * DECLARED DEVIATION 2/3 — `token_handle` REPLACES `token`. The raw token is
 * never written down. D1 rows end up in backups, in `wrangler d1 execute`
 * output and in whatever a debugging session pastes into a terminal; a raw
 * single-use bearer token at rest means one database read is a live connect
 * link for every owner holding one. The handle is sha256(token) in hex and
 * cannot be redeemed — redeeming hashes what the caller presented and
 * compares. THIS FILE NEVER HASHES: the hash lives with the token minting in
 * links.ts, so there is one definition of what a handle is.
 *
 * DECLARED DEVIATION 3/3 — `completed_at` is new. It is the exactly-once gate
 * for the vendor callback, and without it a refresh of the done page records
 * the same connection twice.
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

// ---------------------------------------------------------------------------
// THE FAILURES, AS TYPES
// ---------------------------------------------------------------------------
// Distinct classes, not strings, because the callers must be able to tell
// "this database is not migrated" from "this query returned somebody else's
// rows". The second one is a page the owner must never see and an alert
// somebody must be woken by; the first is a deploy step nobody ran.

/** A result set carried a row belonging to another owner. */
export class MixedOwnerRows extends Error {
  readonly table: string;
  readonly expected: string;
  readonly found: readonly string[];
  constructor(table: string, expected: string, found: readonly string[]) {
    super(
      `${table} was asked for owner ${expected}'s rows and answered with ${found.length} other owner(s) `
        + `(${found.slice(0, 3).join(", ")}) — refusing rather than filtering, because filtering a `
        + "stray row out hides the query that produced it and stamping our owner over it LAUNDERS it",
    );
    this.name = "MixedOwnerRows";
    this.table = table;
    this.expected = expected;
    this.found = found;
  }
}

/** A write would have re-bound a row that belongs to another owner. */
export class CrossOwnerWrite extends Error {
  readonly table: string;
  readonly key: string;
  constructor(table: string, key: string) {
    super(
      `${table}: refusing to write ${key} — that row belongs to a different owner. `
        + "A silent re-bind here is the wrong-person failure with a green log line.",
    );
    this.name = "CrossOwnerWrite";
    this.table = table;
    this.key = key;
  }
}

/** The LIVE table is missing a column this code cannot do without. */
export class ConnectionsSchemaMissing extends Error {
  readonly table: string;
  readonly missing: readonly string[];
  constructor(table: string, missing: readonly string[]) {
    super(
      `the live "${table}" table is missing ${missing.join(", ")}. Nothing is written until it is `
        + "migrated: run migration/d1/schema.sql section 5 against the live database "
        + "(wrangler d1 execute anticipy-backend --remote --file=migration/d1/schema.sql). "
        + "Writing a column the live table lacks turns EVERY write on this table into a D1 1101.",
    );
    this.name = "ConnectionsSchemaMissing";
    this.table = table;
    this.missing = missing;
  }
}

/** A concurrent writer kept winning the signal compare-and-set. */
export class SignalContention extends Error {
  readonly key: string;
  readonly attempts: number;
  constructor(key: string, attempts: number) {
    super(
      `gave up merging a usage signal for ${key} after ${attempts} attempts — another writer won `
        + "every round. Nothing was written; the evidence is lost, not corrupted.",
    );
    this.name = "SignalContention";
    this.key = key;
    this.attempts = attempts;
  }
}

// ---------------------------------------------------------------------------
// THE SEAM
// ---------------------------------------------------------------------------

/**
 * Every accessor takes the owner. Not one of them derives it, defaults it or
 * remembers it from last time.
 *
 * `OwnerId | string` on the way in, exactly as the spike's modules do: the
 * brand is erased before this code runs, so the guard has to be a CALL —
 * `ownerId()` — and it is made on every entry point below, even where the
 * caller's type already says the value is an id.
 */
export interface ConnectionsStore {
  // -- app_usage_signals ----------------------------------------------------
  /** This owner's evidence rows. Ranking and decay live in signals.ts. */
  signalsForOwner(user: OwnerId | string): Promise<StoredSignal[]>;
  readSignal(key: SignalKey): Promise<StoredSignal | null>;
  /**
   * Merge one piece of evidence into this owner's row for (toolkit, source,
   * alias), atomically.
   *
   * THE ARITHMETIC IS THE CALLER'S. `merge` is handed the row as it stands
   * (or null) and returns the weight and timestamp it should now hold; decay,
   * the source weight bands and the sum-vs-max rule all live in signals.ts,
   * where the tests measure them. This file owns only the part signals.ts
   * cannot do from outside the database: making sure the row that is written
   * was computed from the row that was read.
   *
   * WHY IT IS NOT A PLAIN UPSERT. Read-then-write loses evidence: two observer
   * traces landing together both read the same prior, both compute
   * prior+one, and the second overwrites the first — one signal's worth of
   * weight silently gone, on the write path that runs most often. So the
   * update is CONDITIONAL on the row still holding what was read, and a loser
   * re-reads and re-merges rather than clobbering.
   */
  recordSignal(
    key: SignalKey,
    merge: (prior: StoredSignal | null) => { weight: number; last_seen_at: number },
  ): Promise<StoredSignal>;

  // -- connections ----------------------------------------------------------
  connectionsForOwner(user: OwnerId | string): Promise<StoredConnection[]>;
  readConnection(user: OwnerId | string, connectedAccountId: string): Promise<StoredConnection | null>;
  /** Insert or update. REFUSES a row whose `connected_account_id` already
   *  belongs to a different owner — see `CrossOwnerWrite`. */
  putConnection(row: StoredConnection): Promise<void>;
  /**
   * BOTH HALVES OF A FINISHED CONNECTION, IN ONE D1 BATCH: the `connections`
   * row upserted, and this owner's `connect_nudges` row for that toolkit
   * flipped to `connected`.
   *
   * WHY IT IS ONE METHOD AND NOT TWO CALLS. It is written under the connect
   * callback's exactly-once lease (routes/connect.ts `connectPageDone`), and
   * that lease is a promise about ONE write. Two calls are two failure modes
   * under one promise: the connections row lands, the nudge flip does not, the
   * lease is either burned or released, and whichever half failed is invisible
   * — the owner has connected the app and keeps being asked to connect it.
   *
   * IDEMPOTENT on (user_id, toolkit, connected_account_id), because the caller
   * is a browser and a browser refreshes: two runs leave ONE connections row
   * and ONE nudge row, and the second run is not an error.
   *
   * THE ASK'S OWN HISTORY IS NOT ERASED. `level`, `trigger`, `sent_at` and
   * `channel` are written only when the nudge row is CREATED here; a row that
   * already exists keeps them, because they are how the spec's timers get
   * tuned and how "this owner declined twice" survives a connect. Only `state`
   * and `acted_at` are this write's to set.
   *
   * REFUSES, ATOMICALLY, when `connected_account_id` belongs to another owner:
   * both statements no-op (the nudge insert is conditional on the connections
   * row being THIS owner's after the upsert), and `CrossOwnerWrite` is raised
   * with nothing written. Order matters — a nudge flipped for a connection
   * that was refused would tell the ask engine an app is connected that is not.
   */
  recordConnection(row: StoredConnection, connectedAt: number): Promise<void>;
  /** Delete THIS owner's connection. Returns false when there was no such row
   *  for this owner — which includes the case where it exists under somebody
   *  else, and that must read as "not yours", never as a delete. */
  deleteConnection(user: OwnerId | string, connectedAccountId: string): Promise<boolean>;

  // -- connect_nudges -------------------------------------------------------
  nudgesForOwner(user: OwnerId | string): Promise<StoredNudge[]>;
  readNudge(user: OwnerId | string, toolkit: Toolkit): Promise<StoredNudge | null>;
  putNudge(row: StoredNudge): Promise<void>;

  // -- connect_links --------------------------------------------------------
  /** Insert. MUST reject a handle that already exists rather than overwrite:
   *  an overwrite would silently re-bind a live link to a different owner. */
  put(row: StoredLink): Promise<void>;
  read(handle: string): Promise<StoredLink | null>;
  /** THE SINGLE-USE GATE. One statement, no read-then-write:
   *    UPDATE connect_links SET used_at = ?1
   *     WHERE token_handle = ?2 AND used_at IS NULL
   *  and `won = (changes === 1)`. */
  claim(handle: string, usedAt: number): Promise<ClaimOutcome>;
  /** THE EXACTLY-ONCE GATE for the callback, same shape. Read it as taking a
   *  LEASE, not as filing a receipt: it says "I am the one who will write this
   *  connection", and `release` gives it back if the write does not happen. */
  complete(handle: string, completedAt: number): Promise<ClaimOutcome>;
  /**
   * GIVE THE LEASE BACK when the write it was taken for failed. Conditional,
   * like every other write here, so a stale caller cannot re-open the
   * exactly-once window under a connection somebody else has already recorded.
   *
   * WHY IT EXISTS. `complete` used to be burned before the connection was
   * written, so one failed write left the token completed with no row
   * anywhere: the page said "connected" on every refresh, the account existed
   * at the vendor, and Composio publishes NO success webhook — nothing would
   * ever mention it again. Permanent, silent data loss, one `throw` away.
   */
  release(handle: string, completedAt: number): Promise<ClaimOutcome>;
  linksForOwner(user: OwnerId | string): Promise<StoredLink[]>;
}

export interface StoreEnv {
  DB: D1Database;
}

// ---------------------------------------------------------------------------
// RUNTIME GUARDS — because types are stripped, not checked.
// ---------------------------------------------------------------------------

function checkedOwner(raw: unknown): OwnerId {
  // Delegated to the contract's own constructor: one definition of what an
  // owner id looks like, in the place that explains why it exists.
  return ownerId(typeof raw === "string" ? raw : String(raw ?? ""));
}

/**
 * A toolkit slug, trimmed and lowercased.
 *
 * THE LINE, because it is one character away from a law-1 violation. Legal:
 * case and surrounding whitespace, so a catalog yielding "Notion" and one
 * yielding "notion" do not become two connections for one app. Illegal and
 * deliberately absent: any mapping between DIFFERENT slugs. `google_drive` and
 * `google-drive` stay two different apps — the slug is a vendor's primary key,
 * and guessing that they are the same connects the wrong one.
 */
function checkedToolkit(raw: unknown): Toolkit {
  const slug = typeof raw === "string" ? raw.trim().toLowerCase() : "";
  if (slug === "") {
    throw new Error(`a connections row needs a toolkit slug; got ${JSON.stringify(raw)}`);
  }
  return slug;
}

/** One of a closed set the contract declares, or a loud throw. Never a
 *  default: an unrecognised value given a default is the value nobody has
 *  thought about the consequences of, silently taking the consequences of one
 *  somebody did. */
function checkedEnum<T extends string>(raw: unknown, allowed: readonly T[], what: string): T {
  if (typeof raw === "string" && (allowed as readonly string[]).includes(raw)) return raw as T;
  throw new Error(
    `not a ${what}: ${JSON.stringify(raw)} — expected one of ${allowed.join(", ")}`,
  );
}

function checkedAlias(raw: unknown): AccountAlias | null {
  if (raw === undefined || raw === null || raw === "") return null;
  // A closed two-value enum from the contract. Comparing against it is
  // structure, not meaning: it says which ACCOUNT a row is about, and never
  // what a person's words meant.
  if (raw === "work" || raw === "personal") return raw;
  throw new Error(
    `not an account alias: ${JSON.stringify(raw)} — a row is about one of the owner's named `
      + "accounts, or about none",
  );
}

function checkedTime(raw: unknown, field: string): number {
  const t = Number(raw);
  if (!Number.isFinite(t)) {
    throw new Error(`${field} must be a finite epoch-ms number; got ${JSON.stringify(raw)}`);
  }
  return t;
}

function checkedNullableTime(raw: unknown, field: string): number | null {
  if (raw === undefined || raw === null) return null;
  return checkedTime(raw, field);
}

function checkedWeight(raw: unknown): number {
  const w = Number(raw);
  // Never negative. A negative weight lets one piece of evidence SUBTRACT
  // another and push an app below apps with no evidence at all — a "never ask
  // about this" reached through arithmetic, invisible to the nudge state
  // machine that is supposed to own that decision.
  if (!Number.isFinite(w) || w < 0) {
    throw new Error(`a signal weight must be a finite non-negative number; got ${JSON.stringify(raw)}`);
  }
  return w;
}

function checkedLevel(raw: unknown): 0 | 1 | 2 | 3 {
  const n = Number(raw);
  // LEVEL_THRESHOLD is indexed by exactly 0..3 and LEVEL_THRESHOLD[3] is
  // +Infinity — level 3 stops. A level of 4 indexes that table as `undefined`,
  // every comparison against it is false, and the owner who said no three
  // times starts being asked again.
  if (n !== 0 && n !== 1 && n !== 2 && n !== 3) {
    throw new Error(`a nudge level is 0, 1, 2 or 3; got ${JSON.stringify(raw)}`);
  }
  return n;
}

function checkedHandle(raw: unknown): string {
  // sha256 hex. THE POINT IS WHAT IT REFUSES: a raw connect token is 43
  // url-safe base64 characters, and this check means one cannot be stored by
  // mistake. schema.sql carries the same rule as a CHECK so the database
  // refuses it too — two locks, because the thing behind the door is a live
  // link to somebody's mailbox.
  if (typeof raw !== "string" || !/^[0-9a-f]{64}$/.test(raw)) {
    throw new Error(
      `not a connect-link handle: ${JSON.stringify(raw)} — the store holds sha256(token) in hex, `
        + "never the token itself",
    );
  }
  return raw;
}

function checkedAccountId(raw: unknown): string {
  const id = typeof raw === "string" ? raw.trim() : "";
  if (id === "") {
    throw new Error(`a connection needs the provider's connected_account_id; got ${JSON.stringify(raw)}`);
  }
  return id;
}

// Validation of a whole row, in one place per table, so the memory store and
// the D1 store cannot drift into accepting different things. A test that
// passes against the fake and fails against D1 is worse than no test.

function checkedSignal(row: unknown): StoredSignal {
  const r = (row ?? {}) as Record<string, unknown>;
  return {
    user_id: checkedOwner(r.user_id),
    toolkit: checkedToolkit(r.toolkit),
    source: checkedEnum(r.source, SIGNAL_SOURCES, "signal source"),
    alias: checkedAlias(r.alias),
    weight: checkedWeight(r.weight),
    last_seen_at: checkedTime(r.last_seen_at, "last_seen_at"),
  };
}

function checkedConnection(row: unknown): StoredConnection {
  const r = (row ?? {}) as Record<string, unknown>;
  return {
    user_id: checkedOwner(r.user_id),
    toolkit: checkedToolkit(r.toolkit),
    connected_account_id: checkedAccountId(r.connected_account_id),
    alias: checkedAlias(r.alias),
    status: checkedEnum(r.status, CONNECTION_STATUSES, "connection status"),
    // Strictly a boolean on the way in. `writes_enabled: "false"` is truthy in
    // JavaScript, and the value decides whether Anticipy may act on somebody's
    // mailbox — the one field in this file where a coercion bug is an action.
    writes_enabled: checkedBool(r.writes_enabled, "writes_enabled"),
    last_used_at: checkedNullableTime(r.last_used_at, "last_used_at"),
  };
}

function checkedBool(raw: unknown, field: string): boolean {
  if (raw === true || raw === false) return raw;
  // 0/1 are how the column comes back out of D1, and nothing else is accepted.
  if (raw === 1) return true;
  if (raw === 0) return false;
  throw new Error(`${field} must be a boolean; got ${JSON.stringify(raw)}`);
}

function checkedNudge(row: unknown): StoredNudge {
  const r = (row ?? {}) as Record<string, unknown>;
  return {
    user_id: checkedOwner(r.user_id),
    toolkit: checkedToolkit(r.toolkit),
    state: checkedEnum(r.state, NUDGE_STATES, "nudge state"),
    level: checkedLevel(r.level),
    snooze_until: checkedNullableTime(r.snooze_until, "snooze_until"),
    trigger: r.trigger === undefined || r.trigger === null || r.trigger === ""
      ? null
      : checkedEnum(r.trigger, NUDGE_TRIGGERS, "nudge trigger"),
    sent_at: checkedNullableTime(r.sent_at, "sent_at"),
    acted_at: checkedNullableTime(r.acted_at, "acted_at"),
    channel: r.channel === undefined || r.channel === null || r.channel === ""
      ? null
      : checkedEnum(r.channel, NUDGE_CHANNELS, "nudge channel"),
  };
}

function checkedLink(row: unknown): StoredLink {
  const r = (row ?? {}) as Record<string, unknown>;
  return {
    token_handle: checkedHandle(r.token_handle),
    user_id: checkedOwner(r.user_id),
    toolkit: checkedToolkit(r.toolkit),
    alias: checkedAlias(r.alias),
    expires_at: checkedTime(r.expires_at, "expires_at"),
    used_at: checkedNullableTime(r.used_at, "used_at"),
    completed_at: checkedNullableTime(r.completed_at, "completed_at"),
  };
}

/**
 * THE REFUSAL. Every owner-scoped read runs its answer through this.
 *
 * The `WHERE user_id = ?` above it is the guard; this is the check that the
 * guard fired. Two failures live here and they are not the same:
 *
 *   FAN-OUT — two people's rows in one answer, from a dropped WHERE or a join
 *   that multiplied. Visible in the rows, and refused below.
 *
 *   SWAP — ONE person's rows, whole and perfectly readable, selected for
 *   somebody else: a WHERE bound to the wrong variable, a cache keyed by the
 *   previous request, a loop reusing the last iteration's id. Nothing in the
 *   rows can show it, which is why the expected owner is an ARGUMENT and not
 *   an inference.
 *
 * IT THROWS RATHER THAN FILTERS, and that is the whole point. Filtering the
 * stray row out hides the query that produced it, so the bug ships. Stamping
 * our own owner over it — the tempting "fix" — LAUNDERS another person's row
 * into this person's account, which is the wrong-person failure arriving
 * through the code that was supposed to prevent it.
 */
function refuseMixedOwners<T extends { user_id: string }>(
  table: string,
  expected: OwnerId,
  rows: readonly T[],
): readonly T[] {
  const strays = new Set<string>();
  for (const row of rows) {
    const owner = String((row as { user_id?: unknown })?.user_id ?? "");
    if (owner !== expected) strays.add(owner);
  }
  if (strays.size > 0) throw new MixedOwnerRows(table, expected, [...strays]);
  return rows;
}

// ---------------------------------------------------------------------------
// LIVE COLUMNS — the 1101 guard, ported from src/pb/records.ts.
// ---------------------------------------------------------------------------

/** Columns without which a SAFETY property of this feature silently fails. A
 *  live table missing one of these makes the store refuse, naming the
 *  migration, rather than write rows that are quietly wrong forever. */
const REQUIRED: Record<string, readonly string[]> = {
  // user_id: owner scoping. toolkit/source: the identity of the evidence.
  // weight/last_seen_at: without them there is no evidence, only a row.
  app_usage_signals: ["user_id", "toolkit", "source", "weight", "last_seen_at"],
  // status decides whether the app is offered at all; writes_enabled is the
  // opt-in that lets Anticipy CHANGE things — a toggle that silently does not
  // persist is a settings screen that lies about what it may do.
  connections: ["connected_account_id", "user_id", "toolkit", "status", "writes_enabled"],
  // snooze_until is required, not optional: without it an owner who said no is
  // asked again on the next sweep, which is the one thing the level ladder
  // exists to prevent. sent_at is required for the same class of reason one
  // table over: "one ask per owner per 7 days across ALL apps" is a MAX(sent_at)
  // over this owner's rows, and a column that silently does not persist makes
  // that budget blind — somebody who just ran three browser tasks gets three
  // connect texts, which is precisely the spam the spec forbids.
  connect_nudges: ["user_id", "toolkit", "state", "level", "snooze_until", "sent_at"],
  // used_at IS the single-use gate; completed_at IS the exactly-once gate;
  // expires_at is the ten minutes. None of the three has a safe absence.
  connect_links: ["token_handle", "user_id", "toolkit", "expires_at", "used_at", "completed_at"],
};

/**
 * Columns whose absence DEGRADES rather than breaks, and what it costs. These
 * are dropped from writes and read back as null, exactly the way
 * `fillEmpties(def, body, live)` skips a column the live table lacks.
 *
 * `alias` is the exception inside the exception: it is dropped only when the
 * value is null. A NON-null alias with no column to hold it is refused,
 * because writing "work" into a table that cannot store it merges the owner's
 * two accounts into one pile of evidence — and the next sentence out of this
 * product is "connect your work Gmail" pointing at the personal one.
 *
 * `trigger` missing costs the onboarding exception: a skipped onboarding card
 * would snooze 14 days instead of 7. That errs toward asking LESS, which is
 * the safe direction, so it degrades.
 *
 * `acted_at` missing costs the log the difference between a said-no and a
 * silence, which is what the spec's timers get tuned from — real, but it does
 * not change who is asked or when, because the level ladder does that.
 * `channel` missing costs the same kind of line. `last_used_at` missing costs
 * "last used Tuesday" on the settings screen. All three err toward a worse
 * report, never toward a wrong action, which is the test for this list.
 */
const OPTIONAL: Record<string, readonly string[]> = {
  app_usage_signals: ["alias"],
  connections: ["alias", "last_used_at"],
  connect_nudges: ["trigger", "acted_at", "channel"],
  connect_links: ["alias"],
};

/**
 * The live table's columns, asked of SQLite once per database per table.
 *
 * KEYED BY THE DATABASE, not by table name alone (records.ts:116 uses a global
 * Map). One isolate has one DB in production so the difference does not show
 * there — but a cache that survives across databases is a cache that answers
 * for the wrong one, and it is exactly what makes a "the live table is missing
 * a column" test unwritable. Free correctness; take it.
 */
const LIVE_COLUMNS = new WeakMap<D1Database, Map<string, Set<string>>>();

export async function liveColumns(env: StoreEnv, table: string): Promise<Set<string>> {
  let perDb = LIVE_COLUMNS.get(env.DB);
  if (!perDb) { perDb = new Map(); LIVE_COLUMNS.set(env.DB, perDb); }
  const cached = perDb.get(table);
  if (cached) return cached;
  const res = await env.DB.prepare(`SELECT name FROM pragma_table_info(?1)`)
    .bind(table).all<{ name: string }>();
  const set = new Set((res.results ?? []).map((r) => String(r.name)));
  // An EMPTY set means the table does not exist at all. Not cached: caching it
  // would make the store permanently refuse a database that is about to be
  // migrated, and the fix would be "restart every isolate".
  if (set.size) perDb.set(table, set);
  return set;
}

/** Forget what we learned about this database's shape. For the migration path
 *  and for tests that alter a table mid-run; production never calls it. */
export function forgetLiveColumns(env: StoreEnv): void {
  LIVE_COLUMNS.delete(env.DB);
}

async function requireColumns(env: StoreEnv, table: string): Promise<Set<string>> {
  const live = await liveColumns(env, table);
  const missing = (REQUIRED[table] ?? []).filter((c) => !live.has(c));
  if (missing.length > 0) throw new ConnectionsSchemaMissing(table, missing);
  return live;
}

/** Only the columns that exist live, in a stable order, so the statement built
 *  from them is the statement the table can take. */
function project(
  live: Set<string>,
  row: Record<string, unknown>,
): { cols: string[]; vals: unknown[] } {
  const cols: string[] = [];
  const vals: unknown[] = [];
  for (const [k, v] of Object.entries(row)) {
    if (!live.has(k)) continue;
    cols.push(k);
    vals.push(v);
  }
  return { cols, vals };
}

/** `alias` is the one optional column with a non-degradable value. */
function refuseUnstorableAlias(table: string, live: Set<string>, alias: AccountAlias | null): void {
  if (alias !== null && !live.has("alias")) {
    throw new ConnectionsSchemaMissing(table, ["alias"]);
  }
}

const q = (name: string) => `"${name.replace(/"/g, '""')}"`;

// The stored spelling of "no alias". `''`, not NULL, because `alias` is part
// of app_usage_signals' PRIMARY KEY and SQLite counts NULLs in a unique index
// as distinct from each other: two "account unknown" rows for one app would
// both insert, the merge below would never find its prior, and the evidence
// would double every time the observer ran. All four tables spell it the same
// way so there is one answer to "what does no-alias look like", and the store
// maps it back to the contract's `null` at the boundary. The spike's own key
// function already collapses it identically (`alias ?? ""`, signals.ts keyOf).
const aliasOut = (a: AccountAlias | null): string => a ?? "";

// ---------------------------------------------------------------------------
// THE D1 STORE
// ---------------------------------------------------------------------------

export function createD1Store(env: StoreEnv): ConnectionsStore {
  // How many times a signal merge re-reads and retries before giving up. Small
  // on purpose: contention on ONE owner's ONE app's ONE source is rare, and a
  // loop that grinds is a Worker that times out holding a D1 connection.
  const MERGE_ATTEMPTS = 5;

  function rowToSignal(r: Record<string, unknown>): StoredSignal {
    return checkedSignal({ ...r, alias: checkedAlias(r.alias ?? null) });
  }
  function rowToConnection(r: Record<string, unknown>): StoredConnection {
    return checkedConnection({
      ...r,
      alias: checkedAlias(r.alias ?? null),
      writes_enabled: Number(r.writes_enabled) === 1,
      last_used_at: r.last_used_at ?? null,
    });
  }
  function rowToNudge(r: Record<string, unknown>): StoredNudge {
    return checkedNudge({
      ...r,
      // A live table missing an OPTIONAL column hands back `undefined`; the
      // checker turns that into the documented null rather than throwing,
      // which is what "degrades" means.
      trigger: r.trigger ?? null,
      sent_at: r.sent_at ?? null,
      acted_at: r.acted_at ?? null,
      channel: r.channel ?? null,
      snooze_until: r.snooze_until ?? null,
    });
  }
  function rowToLink(r: Record<string, unknown>): StoredLink {
    return checkedLink({
      ...r,
      alias: checkedAlias(r.alias ?? null),
      used_at: r.used_at ?? null,
      completed_at: r.completed_at ?? null,
    });
  }

  async function selectOwned<T extends { user_id: string }>(
    table: string,
    user: OwnerId | string,
    map: (r: Record<string, unknown>) => T,
  ): Promise<T[]> {
    const owner = checkedOwner(user);
    await requireColumns(env, table);
    // `SELECT *`, deliberately: a live table missing an optional column would
    // make an explicit column list a hard SQL error, and the mapper above
    // already turns a missing field into its documented default. The WHERE is
    // the guard; refuseMixedOwners is the proof it fired.
    const res = await env.DB
      .prepare(`SELECT * FROM ${q(table)} WHERE "user_id" = ?1`)
      .bind(owner)
      .all<Record<string, unknown>>();
    const rows = (res.results ?? []).map(map);
    refuseMixedOwners(table, owner, rows);
    return rows;
  }

  /** One row, by primary key, read back after a conditional write. */
  async function readByKey<T>(
    table: string,
    where: string,
    args: unknown[],
    map: (r: Record<string, unknown>) => T,
  ): Promise<T | null> {
    const row = await env.DB.prepare(`SELECT * FROM ${q(table)} WHERE ${where}`)
      .bind(...args).first<Record<string, unknown>>();
    return row ? map(row) : null;
  }

  /**
   * The three compare-and-sets on connect_links are the same shape, so they
   * are the same function: ONE conditional UPDATE, `won = changes === 1`, then
   * a read for the caller's benefit. There is no branch between the read and
   * the write because there is no read before the write — that is the whole
   * property, and it is why this is a helper and not three hand-written
   * statements that could drift.
   */
  async function compareAndSet(
    handle: string,
    setSql: string,
    whereSql: string,
    args: unknown[],
  ): Promise<ClaimOutcome> {
    const h = checkedHandle(handle);
    await requireColumns(env, "connect_links");
    const res = await env.DB.prepare(
      `UPDATE "connect_links" SET ${setSql} WHERE "token_handle" = ?1 AND ${whereSql}`,
    ).bind(h, ...args).run();
    const won = Number(res.meta?.changes ?? 0) === 1;
    const row = await readByKey("connect_links", `"token_handle" = ?1`, [h], rowToLink);
    return { won, row };
  }

  /**
   * THE ONE UPSERT INTO `connections`, and THE CROSS-OWNER GUARD that rides on
   * it. Built here rather than written twice because `putConnection` and
   * `recordConnection` must not be able to drift: the second copy of this
   * statement would be the copy somebody edits without the predicate.
   *
   * `connected_account_id` is the VENDOR's id and is unique ACROSS owners, so a
   * plain upsert on it can land on somebody else's row and re-bind their
   * account to this owner in one statement. The predicate on DO UPDATE makes
   * that a no-op instead; `changes === 0` is then the signal, and every caller
   * raises rather than swallowing it — a silent no-op would tell the settings
   * page the toggle saved when it did not.
   *
   * It returns the statement UNRUN so a caller can put it in a batch beside
   * another write that has to succeed or fail with it.
   */
  function connectionUpsert(live: Set<string>, conn: StoredConnection): D1PreparedStatement {
    refuseUnstorableAlias("connections", live, conn.alias);
    const body = project(live, {
      connected_account_id: conn.connected_account_id,
      user_id: conn.user_id,
      toolkit: conn.toolkit,
      alias: aliasOut(conn.alias),
      status: conn.status,
      writes_enabled: conn.writes_enabled ? 1 : 0,
      last_used_at: conn.last_used_at,
    });
    const setCols = body.cols.filter((c) => c !== "connected_account_id" && c !== "user_id");
    return env.DB.prepare(
      `INSERT INTO "connections" (${body.cols.map(q).join(", ")}) `
        + `VALUES (${body.vals.map((_, i) => `?${i + 1}`).join(", ")}) `
        + `ON CONFLICT("connected_account_id") DO UPDATE SET `
        + setCols.map((c) => `${q(c)} = excluded.${q(c)}`).join(", ")
        + ` WHERE "connections"."user_id" = excluded."user_id"`,
    ).bind(...body.vals);
  }

  /**
   * One signal row by its full key. A named local rather than a method on the
   * returned object, because `recordSignal` below re-reads through it and a
   * `this.` there breaks the first time a caller writes
   * `const { recordSignal } = store`.
   */
  async function readSignalImpl(key: SignalKey): Promise<StoredSignal | null> {
    const owner = checkedOwner(key?.user_id);
    const toolkit = checkedToolkit(key?.toolkit);
    const source = checkedEnum(key?.source, SIGNAL_SOURCES, "signal source");
    const alias = checkedAlias(key?.alias);
    const live = await requireColumns(env, "app_usage_signals");
    refuseUnstorableAlias("app_usage_signals", live, alias);
    const aliasClause = live.has("alias") ? ` AND "alias" = ?4` : "";
    const args: unknown[] = [owner, toolkit, source];
    if (live.has("alias")) args.push(aliasOut(alias));
    const row = await env.DB.prepare(
      `SELECT * FROM "app_usage_signals" `
        + `WHERE "user_id" = ?1 AND "toolkit" = ?2 AND "source" = ?3${aliasClause}`,
    ).bind(...args).first<Record<string, unknown>>();
    if (!row) return null;
    const signal = rowToSignal(row);
    // One row, and it must still be this owner's. A single stray row is the
    // same failure as a mixed page of them, caught in the same way.
    refuseMixedOwners("app_usage_signals", owner, [signal]);
    return signal;
  }

  return {
    // -- app_usage_signals --------------------------------------------------
    async signalsForOwner(user) {
      return selectOwned("app_usage_signals", user, rowToSignal);
    },

    readSignal: readSignalImpl,

    async recordSignal(key, merge) {
      const owner = checkedOwner(key?.user_id);
      const toolkit = checkedToolkit(key?.toolkit);
      const source = checkedEnum(key?.source, SIGNAL_SOURCES, "signal source");
      const alias = checkedAlias(key?.alias);
      const live = await requireColumns(env, "app_usage_signals");
      refuseUnstorableAlias("app_usage_signals", live, alias);
      if (typeof merge !== "function") {
        throw new TypeError(
          "recordSignal needs the merge function that owns the decay arithmetic; "
            + "this file must not invent a weight",
        );
      }

      const hasAlias = live.has("alias");
      const keyCols = ["user_id", "toolkit", "source", ...(hasAlias ? ["alias"] : [])];
      const keyVals: unknown[] = [owner, toolkit, source, ...(hasAlias ? [aliasOut(alias)] : [])];
      const keyWhere = keyCols.map((c, i) => `${q(c)} = ?${i + 1}`).join(" AND ");

      for (let attempt = 1; attempt <= MERGE_ATTEMPTS; attempt++) {
        const prior = await readSignalImpl({ user_id: owner, toolkit, source, alias });
        const merged = merge(prior ? { ...prior } : null);
        const weight = checkedWeight(merged?.weight);
        const lastSeenAt = checkedTime(merged?.last_seen_at, "last_seen_at");

        if (!prior) {
          // DO NOTHING, not DO UPDATE: losing the race here means somebody
          // else inserted the row we believed did not exist, and their value
          // must not be overwritten with one computed from `null`. We re-read
          // and merge onto theirs instead.
          const insert = project(live, {
            user_id: owner, toolkit, source, alias: aliasOut(alias),
            weight, last_seen_at: lastSeenAt,
          });
          const res = await env.DB.prepare(
            `INSERT INTO "app_usage_signals" (${insert.cols.map(q).join(", ")}) `
              + `VALUES (${insert.vals.map((_, i) => `?${i + 1}`).join(", ")}) `
              + `ON CONFLICT DO NOTHING`,
          ).bind(...insert.vals).run();
          if (Number(res.meta?.changes ?? 0) === 1) {
            return { user_id: owner, toolkit, source, alias, weight, last_seen_at: lastSeenAt };
          }
          continue;
        }

        // CONDITIONAL ON WHAT WE READ. If another writer moved the row between
        // the read above and this statement, `changes` is 0 and we merge again
        // onto the value they wrote. An unconditional UPDATE here would throw
        // their evidence away, which is the lost-update this whole loop is for.
        const res = await env.DB.prepare(
          `UPDATE "app_usage_signals" SET "weight" = ?${keyVals.length + 1}, `
            + `"last_seen_at" = ?${keyVals.length + 2} `
            + `WHERE ${keyWhere} AND "weight" = ?${keyVals.length + 3} `
            + `AND "last_seen_at" = ?${keyVals.length + 4}`,
        ).bind(...keyVals, weight, lastSeenAt, prior.weight, prior.last_seen_at).run();
        if (Number(res.meta?.changes ?? 0) === 1) {
          return { user_id: owner, toolkit, source, alias, weight, last_seen_at: lastSeenAt };
        }
      }
      throw new SignalContention(`${owner}/${toolkit}/${source}/${alias ?? ""}`, MERGE_ATTEMPTS);
    },

    // -- connections --------------------------------------------------------
    async connectionsForOwner(user) {
      return selectOwned("connections", user, rowToConnection);
    },

    async readConnection(user, connectedAccountId) {
      const owner = checkedOwner(user);
      const id = checkedAccountId(connectedAccountId);
      await requireColumns(env, "connections");
      const row = await env.DB.prepare(
        `SELECT * FROM "connections" WHERE "connected_account_id" = ?1 AND "user_id" = ?2`,
      ).bind(id, owner).first<Record<string, unknown>>();
      if (!row) return null;
      const conn = rowToConnection(row);
      refuseMixedOwners("connections", owner, [conn]);
      return conn;
    },

    async putConnection(row) {
      const conn = checkedConnection(row);
      const live = await requireColumns(env, "connections");
      const res = await connectionUpsert(live, conn).run();
      if (Number(res.meta?.changes ?? 0) !== 1) {
        throw new CrossOwnerWrite("connections", conn.connected_account_id);
      }
    },

    async recordConnection(row, connectedAt) {
      const conn = checkedConnection(row);
      const at = checkedTime(connectedAt, "connectedAt");
      const liveConn = await requireColumns(env, "connections");
      const liveNudge = await requireColumns(env, "connect_nudges");

      // The nudge row as it should look if this is the FIRST time this owner
      // has ever had one for this app. `level` and `snooze_until` are in the
      // INSERT and out of the DO UPDATE below on purpose: they are defaults for
      // a new row, and an existing row's ask history is not this write's to
      // erase.
      const nudge = project(liveNudge, {
        user_id: conn.user_id,
        toolkit: conn.toolkit,
        state: "connected",
        level: 0,
        snooze_until: null,
        acted_at: at,
      });
      // Only what a connect actually decides. `state` is REQUIRED so it is
      // always here; `acted_at` is OPTIONAL and degrades to a worse log line.
      const setCols = nudge.cols.filter((c) => c === "state" || c === "acted_at");
      const n = nudge.vals.length;
      // CONDITIONAL ON THE UPSERT ABOVE HAVING LANDED ON THIS OWNER'S ROW.
      // D1 runs a batch as one sequential transaction, so this statement sees
      // the previous one's effect: if `connected_account_id` belongs to
      // somebody else the upsert was a no-op, this EXISTS is false, and NOTHING
      // is written by either half. Checking in JavaScript afterwards could not
      // give that — the batch would already have committed the flip, and the
      // ask engine would believe an app is connected that is not.
      const nudgeStmt = env.DB.prepare(
        `INSERT INTO "connect_nudges" (${nudge.cols.map(q).join(", ")}) `
          + `SELECT ${nudge.vals.map((_, i) => `?${i + 1}`).join(", ")} `
          + `WHERE EXISTS (SELECT 1 FROM "connections" `
          + `WHERE "connected_account_id" = ?${n + 1} AND "user_id" = ?${n + 2}) `
          + `ON CONFLICT("user_id", "toolkit") DO UPDATE SET `
          + setCols.map((c) => `${q(c)} = excluded.${q(c)}`).join(", "),
      ).bind(...nudge.vals, conn.connected_account_id, conn.user_id);

      // ONE BATCH. D1's batch is a single transaction, which is the whole
      // reason this method exists rather than two awaited calls.
      const [connRes] = await env.DB.batch([connectionUpsert(liveConn, conn), nudgeStmt]);
      if (Number(connRes?.meta?.changes ?? 0) !== 1) {
        throw new CrossOwnerWrite("connections", conn.connected_account_id);
      }
    },

    async deleteConnection(user, connectedAccountId) {
      const owner = checkedOwner(user);
      const id = checkedAccountId(connectedAccountId);
      await requireColumns(env, "connections");
      // Scoped by BOTH. A delete by vendor id alone would let one owner remove
      // another's connection by guessing an id, and the vendor's ids are short.
      const res = await env.DB.prepare(
        `DELETE FROM "connections" WHERE "connected_account_id" = ?1 AND "user_id" = ?2`,
      ).bind(id, owner).run();
      return Number(res.meta?.changes ?? 0) > 0;
    },

    // -- connect_nudges -----------------------------------------------------
    async nudgesForOwner(user) {
      return selectOwned("connect_nudges", user, rowToNudge);
    },

    async readNudge(user, toolkit) {
      const owner = checkedOwner(user);
      const slug = checkedToolkit(toolkit);
      await requireColumns(env, "connect_nudges");
      const row = await env.DB.prepare(
        `SELECT * FROM "connect_nudges" WHERE "user_id" = ?1 AND "toolkit" = ?2`,
      ).bind(owner, slug).first<Record<string, unknown>>();
      if (!row) return null;
      const nudge = rowToNudge(row);
      refuseMixedOwners("connect_nudges", owner, [nudge]);
      return nudge;
    },

    async putNudge(row) {
      const nudge = checkedNudge(row);
      const live = await requireColumns(env, "connect_nudges");
      const body = project(live, {
        user_id: nudge.user_id,
        toolkit: nudge.toolkit,
        state: nudge.state,
        level: nudge.level,
        snooze_until: nudge.snooze_until,
        trigger: nudge.trigger,
        sent_at: nudge.sent_at,
        acted_at: nudge.acted_at,
        channel: nudge.channel,
      });
      const setCols = body.cols.filter((c) => c !== "user_id" && c !== "toolkit");
      // No cross-owner predicate needed here and none written: the primary key
      // IS (user_id, toolkit), so a conflict can only ever be this owner's own
      // row. Writing a guard that cannot fire would teach the next reader that
      // the one on `connections` is decoration too.
      await env.DB.prepare(
        `INSERT INTO "connect_nudges" (${body.cols.map(q).join(", ")}) `
          + `VALUES (${body.vals.map((_, i) => `?${i + 1}`).join(", ")}) `
          + `ON CONFLICT("user_id", "toolkit") DO UPDATE SET `
          + setCols.map((c) => `${q(c)} = excluded.${q(c)}`).join(", "),
      ).bind(...body.vals).run();
    },

    // -- connect_links ------------------------------------------------------
    async put(row) {
      const link = checkedLink(row);
      const live = await requireColumns(env, "connect_links");
      refuseUnstorableAlias("connect_links", live, link.alias);
      const body = project(live, {
        token_handle: link.token_handle,
        user_id: link.user_id,
        toolkit: link.toolkit,
        alias: aliasOut(link.alias),
        expires_at: link.expires_at,
        used_at: link.used_at,
        completed_at: link.completed_at,
      });
      // A PLAIN INSERT, with no ON CONFLICT of any kind. 256 bits do not
      // collide; a duplicate handle means the same token was minted twice, and
      // an upsert would re-bind a link somebody is already holding to a
      // different owner or a different app. The UNIQUE primary key raising is
      // the correct outcome.
      await env.DB.prepare(
        `INSERT INTO "connect_links" (${body.cols.map(q).join(", ")}) `
          + `VALUES (${body.vals.map((_, i) => `?${i + 1}`).join(", ")})`,
      ).bind(...body.vals).run();
    },

    async read(handle) {
      const h = checkedHandle(handle);
      await requireColumns(env, "connect_links");
      // NOT owner-scoped, and that is correct: the handle is what the redeemer
      // presented, and the owner it belongs to is the ANSWER, not the
      // question. links.ts compares it against the signed-in session — a link
      // alone must never be enough.
      return readByKey("connect_links", `"token_handle" = ?1`, [h], rowToLink);
    },

    // KEYED BY THE HANDLE, NOT BY AN OWNER, and that is deliberate. The handle
    // is sha256 of what the redeemer presented; the owner it belongs to is the
    // ANSWER (`row.user_id`), not the question. links.ts compares that against
    // the signed-in session before anything is connected — a link alone must
    // never be enough. Scoping the UPDATE by an owner the CALLER supplied
    // would be worse than useless: it would let a caller who guessed wrong
    // burn nothing and learn nothing, while a caller who guessed right is the
    // one we already trust.
    async claim(handle, usedAt) {
      const at = checkedTime(usedAt, "usedAt");
      return compareAndSet(handle, `"used_at" = ?2`, `"used_at" IS NULL`, [at]);
    },

    async complete(handle, completedAt) {
      const at = checkedTime(completedAt, "completedAt");
      return compareAndSet(handle, `"completed_at" = ?2`, `"completed_at" IS NULL`, [at]);
    },

    async release(handle, completedAt) {
      const at = checkedTime(completedAt, "completedAt");
      // Only the caller HOLDING the lease may hand it back. Unconditional,
      // this would let a late retry clear the completion of a connection
      // another callback already wrote, and the next refresh would write it
      // twice.
      return compareAndSet(handle, `"completed_at" = NULL`, `"completed_at" = ?2`, [at]);
    },

    async linksForOwner(user) {
      return selectOwned("connect_links", user, rowToLink);
    },
  };
}

// ---------------------------------------------------------------------------
// THE IN-MEMORY STORE
// ---------------------------------------------------------------------------

/**
 * The same interface with no database, so the modules above it (signals,
 * policy, links, commands) can be unit-tested the way the spike's 1006 tests
 * are — and so the conformance suite in test/connections-store.test.ts can run
 * the SAME assertions against both implementations. A fake that accepts what
 * D1 refuses is a test suite that passes on a product that does not work, so
 * every guard here is the shared one, called from the same helpers.
 *
 * ATOMICITY, PRECISELY. The compare-and-sets below have NO `await` between the
 * read and the write. An async function body runs synchronously until its
 * first await, so on one event loop the check and the set cannot be
 * interleaved by another redeem. That is what "atomic-ish" means here, and it
 * is the exact property D1's single-statement UPDATE gives for real.
 *
 * Rows go in and come out as copies. A caller that mutated a row it was handed
 * would otherwise be editing the database — and the field it is most likely to
 * mutate is `used_at`, the one field this module refuses to decide anywhere
 * else.
 */
export function createMemoryStore(): ConnectionsStore {
  const signals = new Map<string, StoredSignal>();
  const connections = new Map<string, StoredConnection>();
  const nudges = new Map<string, StoredNudge>();
  const links = new Map<string, StoredLink>();

  // A NUL joiner, because a slug containing the separator would otherwise
  // merge two apps into one row.
  const key = (...parts: (string | null)[]) => parts.map((p) => p ?? "").join("\u0000");

  return {
    async signalsForOwner(user) {
      const owner = checkedOwner(user);
      const rows = [...signals.values()].filter((r) => r.user_id === owner).map((r) => ({ ...r }));
      refuseMixedOwners("app_usage_signals", owner, rows);
      return rows;
    },

    async readSignal(k) {
      const owner = checkedOwner(k?.user_id);
      const toolkit = checkedToolkit(k?.toolkit);
      const source = checkedEnum(k?.source, SIGNAL_SOURCES, "signal source");
      const alias = checkedAlias(k?.alias);
      const row = signals.get(key(owner, toolkit, source, alias));
      if (!row) return null;
      refuseMixedOwners("app_usage_signals", owner, [row]);
      return { ...row };
    },

    async recordSignal(k, merge) {
      const owner = checkedOwner(k?.user_id);
      const toolkit = checkedToolkit(k?.toolkit);
      const source = checkedEnum(k?.source, SIGNAL_SOURCES, "signal source");
      const alias = checkedAlias(k?.alias);
      if (typeof merge !== "function") {
        throw new TypeError(
          "recordSignal needs the merge function that owns the decay arithmetic; "
            + "this file must not invent a weight",
        );
      }
      const id = key(owner, toolkit, source, alias);
      // No await between the read and the write, so no retry loop is needed —
      // and none is written, rather than a dead one kept for symmetry.
      const prior = signals.get(id) ?? null;
      const merged = merge(prior ? { ...prior } : null);
      const row: StoredSignal = {
        user_id: owner,
        toolkit,
        source,
        alias,
        weight: checkedWeight(merged?.weight),
        last_seen_at: checkedTime(merged?.last_seen_at, "last_seen_at"),
      };
      signals.set(id, row);
      return { ...row };
    },

    async connectionsForOwner(user) {
      const owner = checkedOwner(user);
      const rows = [...connections.values()].filter((r) => r.user_id === owner).map((r) => ({ ...r }));
      refuseMixedOwners("connections", owner, rows);
      return rows;
    },

    async readConnection(user, connectedAccountId) {
      const owner = checkedOwner(user);
      const id = checkedAccountId(connectedAccountId);
      const row = connections.get(id);
      // "not yours" reads as absent, exactly as the DELETE ... AND user_id
      // does. Answering with the row and letting the caller compare is how a
      // stranger's connection reaches a settings page.
      if (!row || row.user_id !== owner) return null;
      return { ...row };
    },

    async putConnection(row) {
      const conn = checkedConnection(row);
      const existing = connections.get(conn.connected_account_id);
      if (existing && existing.user_id !== conn.user_id) {
        throw new CrossOwnerWrite("connections", conn.connected_account_id);
      }
      connections.set(conn.connected_account_id, { ...conn });
    },

    async recordConnection(row, connectedAt) {
      const conn = checkedConnection(row);
      const at = checkedTime(connectedAt, "connectedAt");
      const existing = connections.get(conn.connected_account_id);
      // REFUSED BEFORE EITHER HALF IS WRITTEN, which is what D1's batch gives
      // for real: a nudge flipped for a connection that was refused would tell
      // the ask engine an app is connected that is not. A fake that wrote the
      // nudge anyway would pass a test the real store fails.
      if (existing && existing.user_id !== conn.user_id) {
        throw new CrossOwnerWrite("connections", conn.connected_account_id);
      }
      const id = key(conn.user_id, conn.toolkit);
      const prior = nudges.get(id) ?? null;
      // `level`, `snooze_until`, `trigger`, `sent_at` and `channel` are the
      // ask's own history: defaults on a NEW row, untouched on an existing one.
      const nudge: StoredNudge = prior
        ? { ...prior, state: "connected", acted_at: at }
        : {
            user_id: conn.user_id, toolkit: conn.toolkit, state: "connected",
            level: 0, snooze_until: null, trigger: null, sent_at: null,
            acted_at: at, channel: null,
          };
      // No await between the two writes, so nothing can observe one half.
      connections.set(conn.connected_account_id, { ...conn });
      nudges.set(id, checkedNudge(nudge));
    },

    async deleteConnection(user, connectedAccountId) {
      const owner = checkedOwner(user);
      const id = checkedAccountId(connectedAccountId);
      const row = connections.get(id);
      if (!row || row.user_id !== owner) return false;
      connections.delete(id);
      return true;
    },

    async nudgesForOwner(user) {
      const owner = checkedOwner(user);
      const rows = [...nudges.values()].filter((r) => r.user_id === owner).map((r) => ({ ...r }));
      refuseMixedOwners("connect_nudges", owner, rows);
      return rows;
    },

    async readNudge(user, toolkit) {
      const owner = checkedOwner(user);
      const slug = checkedToolkit(toolkit);
      const row = nudges.get(key(owner, slug));
      if (!row) return null;
      refuseMixedOwners("connect_nudges", owner, [row]);
      return { ...row };
    },

    async putNudge(row) {
      const nudge = checkedNudge(row);
      nudges.set(key(nudge.user_id, nudge.toolkit), { ...nudge });
    },

    async put(row) {
      const link = checkedLink(row);
      if (links.has(link.token_handle)) {
        // 256 bits do not collide; a duplicate handle means the same token was
        // minted twice, and overwriting would re-bind a link somebody holds.
        throw new Error(`connect link already exists: ${link.token_handle.slice(0, 12)}`);
      }
      links.set(link.token_handle, { ...link });
    },

    async read(handle) {
      const row = links.get(checkedHandle(handle));
      return row ? { ...row } : null;
    },

    async claim(handle, usedAt) {
      const h = checkedHandle(handle);
      const at = checkedTime(usedAt, "usedAt");
      const row = links.get(h);
      if (!row) return { won: false, row: null };
      if (row.used_at !== null) return { won: false, row: { ...row } };
      const claimed: StoredLink = { ...row, used_at: at };
      links.set(h, claimed);
      return { won: true, row: { ...claimed } };
    },

    async complete(handle, completedAt) {
      const h = checkedHandle(handle);
      const at = checkedTime(completedAt, "completedAt");
      const row = links.get(h);
      if (!row) return { won: false, row: null };
      if (row.completed_at !== null) return { won: false, row: { ...row } };
      const done: StoredLink = { ...row, completed_at: at };
      links.set(h, done);
      return { won: true, row: { ...done } };
    },

    async release(handle, completedAt) {
      const h = checkedHandle(handle);
      const at = checkedTime(completedAt, "completedAt");
      const row = links.get(h);
      if (!row) return { won: false, row: null };
      if (row.completed_at !== at) return { won: false, row: { ...row } };
      const open: StoredLink = { ...row, completed_at: null };
      links.set(h, open);
      return { won: true, row: { ...open } };
    },

    async linksForOwner(user) {
      const owner = checkedOwner(user);
      const rows = [...links.values()].filter((r) => r.user_id === owner).map((r) => ({ ...r }));
      refuseMixedOwners("connect_links", owner, rows);
      return rows;
    },
  };
}
