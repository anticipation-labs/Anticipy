/**
 * src/connections/wait.ts — the background poll that stops a connection
 * existing at the vendor and nowhere here.
 *
 * WHY THIS FILE EXISTS, and it is not a nice-to-have.
 *
 * The vendor publishes NO success webhook — only `expired`
 * (research/2026-09-05-composio-connections.md, "what the spec requires that
 * does not exist yet"). So until this file, `/c/{token}/done` was the ONLY way
 * a connection was ever learned about, and `/done` is a page in the person's
 * browser. If that browser dies between the consent screen and our done page —
 * they close the tab, the phone sleeps, mobile data drops, they tapped a link
 * in a text and the code cookie was never minted — then the account is bound AT
 * THE VENDOR and there is no row here, no nudge flip, and nothing that will
 * ever mention it again. The person believes they connected. Anticipy keeps
 * asking them to connect. Nothing arrives later to repair it.
 *
 * The spec's own line, verbatim: "There is no 'connected' webhook on their
 * side, only 'expired,' so completion comes from the callback plus a background
 * wait_for_connection." And in the facts table: "Poll with wait_for_connection
 * as backup."
 *
 * THE BACKUP, NOT THE PATH. The callback is still the primary and still writes
 * the normal case. This poll exists for the case where the callback never
 * arrives, and it must be invisible when the callback does arrive: it takes THE
 * SAME exactly-once lease `/done` takes (`store.complete`, and `store.release`
 * when the write fails), so the callback and the poll can never both write.
 * Whichever gets there first wins; the other finds the lease taken and does
 * nothing. There is no second mechanism here, on purpose — a second "have we
 * recorded this" would be a second answer, and the day the two disagreed the
 * owner would get two connections or none.
 *
 * WHOSE CONNECTION IT IS COMES FROM THE STORED ROW. `owner` and `toolkit` are
 * arguments, and they are CHECKED against `connect_links` rather than trusted:
 * the row was bound at mint time to an id that passed the owner-row-id check,
 * and it is the only thing here that has ever been authoritative about who this
 * is. A caller that named the wrong owner gets a refusal, not a connection.
 * Same failure as routes/connect.ts's callback, arrived at from the other end —
 * one operator's own mailbox serving everybody.
 *
 * WHAT IS NOT EVIDENCE, and this is the one judgement in the file. An account
 * that was ALREADY ACTIVE at the moment the person tapped is not evidence that
 * this attempt landed: an owner connecting their work mailbox already has a
 * personal one, and recording the old one would bind the wrong account under
 * this link's alias and flip the nudge on a connect that never finished. So the
 * first vendor read is a BASELINE and nothing more, and only an account that
 * was not in it can be recorded. A FLOOR: no positive evidence, no write.
 *
 * The cost of that floor, written down rather than left to be discovered: this
 * poll will NOT repair a connection that was already active before its own
 * attempt began — the person whose browser died last week is repaired by their
 * next successful callback, or by a reconciliation sweep over the owner's
 * accounts, which is a different job and not this one's.
 *
 * HARNESS-LAWS LAW 1. Nothing here decides what a person MEANT. What it
 * compares is structure: a 64-hex handle, a 15-character owner row id, a
 * toolkit slug against the slug the link was minted with, and one status field
 * out of a machine's closed enum. No prose is read anywhere in this file.
 *
 * HARNESS-LAWS LAW 3, stated against this file rather than assumed. Everything
 * below is repo-green. It is live only when `/go` runs on a Worker whose entry
 * point hands `connectRoute` an `ExecutionContext`, because a Worker cancels
 * background work the moment a response is returned unless `waitUntil` holds
 * it open. routes/connect.ts logs, once per redirect, which of those two worlds
 * it is in.
 *
 * Spec: "Connections: how Anticipy asks, learns, and never says Composio",
 * 2026-09-05, page 26.
 */
import type {
  CatalogProvider,
  ConnectLinkStore,
  Connection,
  OwnerId,
  StoredLink,
} from "../routes/connect.ts";

// NOTE ON THE IMPORT ABOVE: it is `import type`, and it has to be. Node's type
// stripping and tsc both erase it entirely, so routes/connect.ts → wait.ts is
// the only edge that exists at run time and the module graph stays acyclic.
// Turning any of those into a value import makes it a real cycle.

// ---------------------------------------------------------------------------
// THE BOUND, AND WHY IT IS THIS BOUND
// ---------------------------------------------------------------------------

/**
 * How long the poll may run, measured from the redirect.
 *
 * FIVE MINUTES, for three reasons and against one constraint.
 *
 * 1. It covers the round trip that actually loses connections. The consent trip
 *    is a password manager, a 2FA push, an account chooser and a workspace
 *    picker; measured on 2026-09-05 it was also a Notion login the person did
 *    not have. Five minutes is comfortably past the normal case.
 * 2. Past it, the person is not at the screen any more. A poll that outlives
 *    the human is spending the owner's vendor quota on an empty room.
 * 3. A `waitUntil` is a request context held open. It is not a cron and it is
 *    not a queue, and a Worker request context is not a place to sleep for an
 *    hour. Whatever the platform's exact ceiling is on any given day, five
 *    minutes is well inside it and an hour plainly is not.
 *
 * What it does NOT cover is stated so nobody reads more into it: somebody who
 * takes longer than the budget is still covered by the callback, which has the
 * full `CALLBACK_WINDOW_MS` hour, and by their own refresh of the done page.
 * This is the backup for a browser that DIED, not a second primary.
 */
export const WAIT_BUDGET_MS = 5 * 60 * 1000;

/**
 * The hard ceiling on any budget, however it is configured.
 *
 * TEN MINUTES BECAUSE THE VENDOR'S OWN CONNECT LINK LIVES TEN MINUTES — the
 * measured fact that made `anticipy.ai/c/{token}` exist at all
 * (research/2026-09-05-composio-connections.md, item 3: four links generated,
 * all four dead before they were tapped). Once the vendor's link has expired,
 * THIS attempt can no longer produce an account, so every further poll is a
 * request spent on an impossibility. It is not a preference; it is the point
 * past which there is nothing left to see.
 */
export const WAIT_CEILING_MS = 10 * 60 * 1000;

/** The first gap. Nobody finishes a consent screen in under five seconds, so
 *  polling sooner buys nothing and costs a vendor call. */
export const POLL_FIRST_DELAY_MS = 5_000;

/** The gap stops growing here. A minute is short enough that a connection is
 *  recorded while the person is still plausibly looking at their phone. */
export const POLL_MAX_DELAY_MS = 60_000;

/** Backoff. Gentle on purpose: the interesting window is the first ninety
 *  seconds, and an aggressive factor would spend the budget's polls before
 *  the person had finished typing a password. */
export const POLL_BACKOFF = 1.6;

/**
 * The ceiling on vendor calls, baseline included.
 *
 * The budget already bounds the loop in wall-clock terms, so under a moving
 * clock this never binds (five minutes on the schedule above is nine calls).
 * It exists for the clock that does NOT move: an injected `now` frozen by a
 * caller — every test rig in this repo freezes one — would leave `now <
 * deadline` true forever, and a loop whose only exit is a clock is a loop with
 * no exit. This is the second exit.
 */
export const MAX_VENDOR_CALLS = 16;

/**
 * The one environment knob, and the only reason this function takes an `env`.
 *
 * `CONNECT_WAIT_MS` overrides the budget, clamped to `[0, WAIT_CEILING_MS]`.
 * Zero turns the backup OFF — an operator switch that matters because this poll
 * spends the owner's vendor quota in the background, and stopping that must not
 * require a deploy. Anything unreadable falls back to the DEFAULT rather than
 * to off: a typo in a dashboard field must not silently delete a feature whose
 * whole job is to notice silence.
 */
export interface WaitEnv {
  CONNECT_WAIT_MS?: unknown;
}

export function waitBudgetMs(env: WaitEnv | null | undefined): number {
  const raw = env?.CONNECT_WAIT_MS;
  if (raw === undefined || raw === null || raw === "") return WAIT_BUDGET_MS;
  const n = typeof raw === "number" ? raw : Number(String(raw).trim());
  if (!Number.isFinite(n) || n < 0) return WAIT_BUDGET_MS;
  return Math.min(Math.floor(n), WAIT_CEILING_MS);
}

// ---------------------------------------------------------------------------
// THE CALL
// ---------------------------------------------------------------------------

export interface WaitOptions {
  /** WHO WE THINK THIS IS. Checked against the stored row, never trusted. */
  owner: OwnerId;
  /** WHICH APP WE THINK THIS IS. Checked against the stored row too. */
  toolkit: string;
  /** sha256 of the link token, hex — the `connect_links` primary key. The raw
   *  token never reaches this file, which is why it can be safe in a log. */
  handle: string;
  /** Absolute epoch ms. Clamped to `WAIT_CEILING_MS` from the first tick. */
  deadline: number;

  /** The same store `/done` leases through. Not a copy of it. */
  store: ConnectLinkStore;
  /** The vendor's list for ONE owner — the only thing that can turn "they
   *  tapped connect" into "an account exists". */
  provider: Pick<CatalogProvider, "connections">;
  /** Where a finished connection is written, exactly as the callback writes it:
   *  one implementation, one D1 batch, the `connections` row and the
   *  `connect_nudges` flip together. */
  onConnected(connection: Connection): Promise<void>;

  /** Injectable clock and sleep. Tests own time; production passes neither. */
  now?(): number;
  sleep?(ms: number): Promise<void>;
}

/**
 * Eight outcomes, because collapsing any two of them would hide a different
 * failure behind a word that already means something else.
 */
export type WaitOutcome =
  /** THE POLL WON. It took the lease and wrote the connection. */
  | { state: "recorded"; connection: Connection }
  /** The lease was already taken — the callback got there first, or a second
   *  poll did. Nothing was written by us, and that is the correct answer. */
  | { state: "already-recorded" }
  /** We took the lease and `onConnected` threw. The lease has been handed BACK,
   *  so the person's refresh of the done page still writes it. */
  | { state: "not-recorded" }
  /** The deadline passed with no account this attempt could claim. Nothing
   *  written — the ordinary answer for somebody who changed their mind. */
  | { state: "never-appeared" }
  /** More than one new active account for this toolkit inside the window.
   *  Which one this link's alias belongs to is not a thing to guess, so
   *  nothing is written and the callback keeps the job. */
  | { state: "ambiguous" }
  /** The `connect_links` row vanished, or stopped matching the owner and
   *  toolkit we were started for, while the poll was running. */
  | { state: "link-gone" }
  /** Refused before a single vendor call: a malformed handle, an owner or
   *  toolkit the stored row disagrees with, an unclaimed row, a deadline
   *  already in the past, or the budget switched off. */
  | { state: "not-started" }
  /** Something threw that this file did not plan for. It is reported rather
   *  than propagated: this runs in `waitUntil`, where an unhandled rejection
   *  is an error on a request that has already been answered. */
  | { state: "failed" };

const ALREADY_RECORDED: WaitOutcome = Object.freeze({ state: "already-recorded" });
const NOT_RECORDED: WaitOutcome = Object.freeze({ state: "not-recorded" });
const NEVER_APPEARED: WaitOutcome = Object.freeze({ state: "never-appeared" });
const AMBIGUOUS: WaitOutcome = Object.freeze({ state: "ambiguous" });
const LINK_GONE: WaitOutcome = Object.freeze({ state: "link-gone" });
const NOT_STARTED: WaitOutcome = Object.freeze({ state: "not-started" });
const FAILED: WaitOutcome = Object.freeze({ state: "failed" });

/** 64 lowercase hex — routes/connect.ts `tokenHandle`'s own output shape. This
 *  value reaches a D1 query, so its alphabet is checked before it does. */
function isHandle(raw: unknown): raw is string {
  return typeof raw === "string" && /^[0-9a-f]{64}$/.test(raw);
}

/** What a log line may say about a link: the first twelve hex of its handle.
 *  Byte-identical to routes/connect.ts `tokenFingerprint` for the same link, so
 *  the redirect line and the outcome line below correlate in `wrangler tail`
 *  without either of them ever carrying a token. */
export function linkFingerprint(handle: unknown): string {
  // ONLY A REAL HANDLE IS ECHOED. Everything else is `link:none`, including a
  // string that merely looks close — because this value comes from a caller,
  // and the one thing a log line must never do is reprint whatever it was
  // handed. A raw token here would put twelve characters of a live credential
  // in `wrangler tail`; a newline would let the caller write log lines of
  // their own.
  return isHandle(handle) ? `link:${handle.slice(0, 12)}` : "link:none";
}

/** 15 lowercase alphanumerics — src/pb/wire.ts ID_ALPHABET, the same guard
 *  routes/connect.ts applies. An email or a display name in an owner slot is
 *  the wrong-person failure with extra steps. */
function isOwnerRowId(raw: unknown): raw is OwnerId {
  return typeof raw === "string" && /^[a-z0-9]{15}$/.test(raw);
}

const errText = (err: unknown): string =>
  (err as { message?: unknown } | null)?.message ? String((err as Error).message) : "unknown";

/**
 * WAIT FOR THE CONNECTION, or for the deadline, whichever comes first.
 *
 * Safe to hand straight to `ctx.waitUntil`: it never throws, it never awaits
 * anything the caller is waiting on, and every exit is bounded by both the
 * deadline and `MAX_VENDOR_CALLS`.
 */
export async function waitForConnection(
  env: WaitEnv | null | undefined,
  opts: WaitOptions,
): Promise<WaitOutcome> {
  try {
    const outcome = await poll(env, opts);
    console.log(`connect wait: ${linkFingerprint(opts?.handle)} ${outcome.state}`);
    return outcome;
  } catch (err) {
    // The whole point of catching here: this promise is usually nobody's to
    // await. An unhandled rejection in a Worker is an error logged against a
    // request that was answered minutes ago, and it tells the operator nothing
    // about which link it was.
    console.log(
      `connect wait: ${linkFingerprint(opts?.handle)} failed — ${errText(err)}`,
    );
    return FAILED;
  }
}

async function poll(
  env: WaitEnv | null | undefined,
  opts: WaitOptions,
): Promise<WaitOutcome> {
  const now = opts.now ?? Date.now;
  const sleep = opts.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));

  // Shape first, and before anything is asked of the store or the vendor. Each
  // of these being wrong means the CALLER is confused, and a confused caller is
  // exactly who must not be allowed to bind an account.
  if (!isHandle(opts.handle) || !isOwnerRowId(opts.owner)) return NOT_STARTED;
  const toolkit = typeof opts.toolkit === "string" ? opts.toolkit.trim().toLowerCase() : "";
  if (toolkit === "") return NOT_STARTED;
  if (typeof opts.store?.read !== "function" || typeof opts.store?.complete !== "function") {
    return NOT_STARTED;
  }
  if (typeof opts.provider?.connections !== "function") return NOT_STARTED;
  if (typeof opts.onConnected !== "function") return NOT_STARTED;

  const started = now();
  if (!Number.isFinite(opts.deadline)) return NOT_STARTED;
  // THE CEILING IS APPLIED HERE, not trusted from the caller. A caller asking
  // for an hour gets ten minutes, because after ten minutes the vendor's own
  // link is dead and this attempt cannot produce an account any more.
  const deadline = Math.min(opts.deadline, started + WAIT_CEILING_MS);
  if (deadline <= started) return NOT_STARTED;

  // THE ROW IS THE AUTHORITY. Not the arguments — they are a claim, and this is
  // where it is checked.
  const first = await opts.store.read(opts.handle);
  if (!matches(first, opts.handle, opts.owner, toolkit)) return NOT_STARTED;
  // An unclaimed row means `/go` never spent this token, so there is no vendor
  // round trip in flight for this poll to be the backup for.
  if (first.used_at === null) return NOT_STARTED;
  if (first.completed_at !== null) return ALREADY_RECORDED;

  const row: StoredLink = first;
  let calls = 0;

  /** One vendor read, as a set of account ids ACTIVE for this owner on this
   *  toolkit — or null for "could not be read", which is never a verdict. */
  const list = async (): Promise<Set<string> | null> => {
    calls++;
    try {
      return activeAccountIds(await opts.provider.connections(row.user_id), row);
    } catch {
      // The vendor's error text is theirs and may name them. The count of
      // attempts is the whole of what this path needs to remember.
      return null;
    }
  };

  // THE BASELINE, taken before the person can plausibly have finished. What is
  // in it is what was already theirs; only what is NOT in it is evidence about
  // this attempt. A read that fails leaves the baseline unset and the next
  // successful read takes it instead — late, which costs this poll its chance
  // and is the safe direction to be wrong in.
  let baseline: Set<string> | null = await list();

  let delay = POLL_FIRST_DELAY_MS;
  // TICKS AS WELL AS CALLS, and the difference is a hang. Not every turn of
  // this loop reaches the vendor — a store read that throws is retried without
  // one — so `calls` alone leaves an iteration that costs nothing and is
  // therefore never counted. Under an injected clock that does not move (every
  // rig in this repo freezes one) a permanently failing store would spin
  // forever on a promise nobody awaits. One tick is one turn, whatever it
  // managed to do.
  let ticks = 0;
  while (now() < deadline && calls < MAX_VENDOR_CALLS && ticks < MAX_VENDOR_CALLS) {
    ticks++;
    const gap = Math.min(delay, deadline - now());
    if (gap > 0) await sleep(gap);
    delay = Math.min(POLL_MAX_DELAY_MS, Math.round(delay * POLL_BACKOFF));

    // THE LEASE IS CHECKED BEFORE THE VENDOR IS ASKED, every tick. The normal
    // case is that the callback landed while we were asleep, and in that case
    // this poll must cost the vendor nothing at all.
    let fresh: StoredLink | null;
    try {
      fresh = await opts.store.read(opts.handle);
    } catch {
      // A store blip is not a verdict about a link either.
      continue;
    }
    if (!matches(fresh, opts.handle, row.user_id, row.toolkit)) return LINK_GONE;
    if (fresh.completed_at !== null) return ALREADY_RECORDED;

    const seen = await list();
    if (seen === null) continue;
    if (baseline === null) { baseline = seen; continue; }

    const news = [...seen].filter((id) => !baseline!.has(id));
    if (news.length === 0) continue;
    // Two accounts on one toolkit inside one window. Both are the owner's, and
    // which one this link's alias belongs to is not readable from here. More
    // polling cannot make it readable, so stop rather than guess.
    if (news.length > 1) return AMBIGUOUS;
    return await record(opts, row, news[0] as string, now());
  }

  return NEVER_APPEARED;
}

/**
 * Is this the row this poll was started for?
 *
 * The handle is the primary key, so it answers on its own; the owner and the
 * toolkit are checked as well because a store that assembles a row from a join
 * can get the key right and the payload wrong, and those are the two fields
 * that decide whose account gets bound to what. It is the same check
 * routes/connect.ts makes with `isTheSameRow`, asked of the row rather than of
 * a write's echo.
 *
 * Plain comparison, not constant-time, and the difference is deliberate: this
 * function answers to nobody. There is no requester holding a stopwatch on a
 * background poll, so there is no channel for a timing difference to leave by.
 */
function matches(
  row: StoredLink | null,
  handle: string,
  owner: string,
  toolkit: string,
): row is StoredLink {
  if (row === null || typeof row !== "object") return false;
  if (row.token_handle !== handle) return false;
  if (row.user_id !== owner) return false;
  return row.toolkit === toolkit;
}

/**
 * Which accounts does the vendor itself hold, ACTIVE, for this owner on this
 * toolkit?
 *
 * A FLOOR, exactly like routes/connect.ts `vendorVouchesFor`: anything it
 * cannot read is not counted. A non-array answer is null — "the vendor did not
 * say" — rather than an empty set, because an empty set is a claim (they have
 * nothing) and a poll that read a 500 as "nothing" would poll on happily and
 * then report `never-appeared` about a connection that exists.
 *
 * IT ASKS ABOUT STATUS AND `vendorVouchesFor` DELIBERATELY DOES NOT, and that
 * asymmetry is the whole difference between the two questions. The callback
 * already carries the vendor's own word for success on the query string, so
 * matching status there would race the vendor against itself. Here there is no
 * callback and no word: the status IS the only evidence, and it is read through
 * the contract's mapped value — `provider.ts mapConnectionStatus` sets
 * `connected` for ACTIVE alone, and `needs_reconnect` for EXPIRED. Accepting
 * `needs_reconnect` would record a dead credential as a working one and the
 * owner would watch the first step that used it fail.
 */
function activeAccountIds(listed: unknown, row: StoredLink): Set<string> | null {
  if (!Array.isArray(listed)) return null;
  const out = new Set<string>();
  for (const entry of listed) {
    if (entry === null || typeof entry !== "object") continue;
    const item = entry as Partial<Connection>;
    if (typeof item.connected_account_id !== "string") continue;
    const id = item.connected_account_id.trim();
    if (id === "") continue;
    // The list was asked for BY OWNER, so a row bound to anybody else means the
    // scoping did not hold — and an unscoped list is not evidence about ours.
    if (typeof item.user_id !== "string" || item.user_id !== row.user_id) continue;
    if (typeof item.toolkit !== "string") continue;
    if (item.toolkit.trim().toLowerCase() !== row.toolkit) continue;
    if (item.status !== "connected") continue;
    out.add(id);
  }
  return out;
}

/**
 * Write it, under the callback's own lease.
 *
 * THE SEQUENCE IS `/done`'s SEQUENCE, statement for statement — `complete`,
 * then `onConnected`, then `release` if the write threw — and it is written out
 * here rather than shared because routes/connect.ts's callback is not this
 * task's to refactor. If those two ever drift, the drift is a defect: the lease
 * is a promise to write, never a receipt that the write happened, and reading
 * it as a receipt is what once left a token completed with no row anywhere,
 * a page saying "connected" on every refresh, and no webhook that would ever
 * mention it again.
 *
 * The connection is built from the STORED ROW and from the vendor's own list.
 * There is no argument on this path through which anything could name an owner,
 * and `writes_enabled` is false because it is always false for a new
 * connection: that is the Settings toggle "let Anticipy make changes", and a
 * connection that arrived write-enabled would let the first step that ever ran
 * against it send mail on behalf of somebody who agreed to no such thing.
 */
async function record(
  opts: WaitOptions,
  row: StoredLink,
  accountId: string,
  at: number,
): Promise<WaitOutcome> {
  const connection: Connection = {
    user_id: row.user_id,
    toolkit: row.toolkit,
    connected_account_id: accountId,
    alias: row.alias,
    status: "connected",
    writes_enabled: false,
    last_used_at: null,
  };

  const lease = await opts.store.complete(row.token_handle, at);
  // LOSING THE LEASE AND FINDING NO ROW ARE DIFFERENT FACTS. `redeem` in
  // routes/connect.ts draws the same line on `claim`: a write that changed
  // nothing because somebody else got there first is "already recorded", and a
  // write that changed nothing because the row went away between the read and
  // the write is not — reporting the second as the first would put "the
  // callback handled it" in the log for a link that no longer exists.
  if (!lease.won) return lease.row === null ? LINK_GONE : ALREADY_RECORDED;

  try {
    await opts.onConnected(connection);
  } catch {
    try {
      if (typeof opts.store.release === "function") {
        await opts.store.release(row.token_handle, at);
      }
    } catch {
      // Nothing to add. The lease stays taken and a fresh link is then the only
      // way through — which is exactly why `release` is on the store interface.
    }
    return NOT_RECORDED;
  }
  return { state: "recorded", connection };
}
