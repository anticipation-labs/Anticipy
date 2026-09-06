/**
 * signals.ts — HOW ANTICIPY KNOWS WHAT YOU USE.
 *
 * The spec (page 42, "How it knows what you use"): "Signals, not a
 * questionnaire. Each one adds weight to app_usage_signals(user, toolkit). The
 * LLM turns the top entries into a natural ask. Signals decay so an app you
 * stopped using stops coming up."
 *
 * WHY THIS FILE EXISTS, MEASURED. On 2026-09-06 the whole ask half of
 * Connections was built and tested — the state machine, the right-time score,
 * the snooze ladder (nudge.ts, 53 checks), and the index of who is due
 * (due.ts) — and `app_usage_signals` had ZERO ROWS on production. Every one of
 * those parts reads this table. With nothing in it the sweep is a correct,
 * well-tested machine that asks nobody about anything, forever. store.ts:294
 * has said "Ranking and decay live in signals.ts" since the day it was
 * written, and there was no signals.ts. This is that file.
 *
 * THE DIVISION OF LABOUR, so a policy does not end up duplicated and drift:
 *
 *   this file    WHAT EVIDENCE EXISTS. Six doors, one per row of the spec's
 *                signal table, each turning a thing that happened into weight
 *                on one (owner, toolkit, alias, source) row. Plus the decay
 *                and the ranking, which is the only definition of "which app
 *                does this person live in most".
 *   store.ts     the row: the SQL, the owner scoping, the compare-and-set.
 *                It refuses to invent a weight; the arithmetic is handed in.
 *   due.ts       which owners are worth handing to the policy at all.
 *   nudge.ts     whether this owner may be interrupted, and with what words.
 *
 * Nothing here decides whether to interrupt anybody. Ranking answers "which
 * apps does this person live in"; "may we say something about it" is a
 * different question with a different owner and a four-state verdict.
 *
 * ---------------------------------------------------------------------------
 * HARNESS-LAWS LAW 1 — THE BOUNDARY THIS FILE SITS EXACTLY ON.
 * ---------------------------------------------------------------------------
 * Read this before adding anything. Two of the spec's six signals are made of
 * human sentences, and those are the ones a hurried edit turns into a word
 * list.
 *
 * A LOOKUP, and legal here:
 *   - Comparing an observed HOST against a catalog entry's OWN url
 *     (`meta.appUrl`). Both strings come from somewhere else — one from the
 *     sense that observed it, one from the vendor's catalog at run time — and
 *     the comparison is equality over dot-separated labels. It cannot express
 *     "this app in particular", because this file has no app's name to reach
 *     for. The spec asks for exactly this in its own words: "Host matched to a
 *     catalog toolkit through the toolkit's meta.app_url. No domain list of
 *     our own." `hostToToolkit` below is that, and it is the reason a new app
 *     in the catalog is a new app in Anticipy with zero code here.
 *   - Decay arithmetic over timestamps, and validating a closed enum the
 *     contract declares. Senses and structure, both named in law 1.
 *
 * A JUDGEMENT, and forbidden here:
 *   - Deciding that a person naming a product out loud meant a particular
 *     toolkit. No list holds the ways somebody refers to the app they live in,
 *     and a list that half-holds them is worse than none: it is confidently
 *     wrong on the owner whose wording is not in it. That question goes to a
 *     model with the catalog in front of it (the contract's `ToolkitJudge`),
 *     and this file takes its VERDICT as an input — `saidSignal` never sees
 *     the sentence. There is no phrase, no verb list and no `includes()` over
 *     prose anywhere below.
 *   - Reading a transcript for links. `linkSignals` takes URLs the sense layer
 *     already isolated; it never scans prose for one. A regex that finds a URL
 *     inside a sentence is one edit away from a regex that decides what the
 *     sentence was about.
 *
 * THE POLARITY IS A FLOOR, deliberately. A signal ADDS weight, weight is what
 * eventually licenses interrupting somebody, and a privilege needs something
 * positive to license it. So only `{ kind: "toolkit" }` becomes a signal:
 * `unclear`, `none`, no verdict at all, and a judge that could not be reached
 * add NOTHING. Silence must not be able to nudge.
 *
 * NO APP IS NAMED IN THIS FILE — not a slug, not a name, not a host, not in
 * prose. test/connections-signals.test.ts reads this source back and fails on
 * either, in code AND in comments, because a name in a comment is where the
 * next agent's branch on that name starts.
 *
 * ---------------------------------------------------------------------------
 * LAW 3 — WHAT IS WIRED AND WHAT IS A PORT. Measured 2026-09-06.
 * ---------------------------------------------------------------------------
 * WIRED, in the sense that its input is a thing production already produces:
 * `sweepConnectedSignals`. It reads the live `connections` table — which the
 * live connect page has been filling since the /c/ routes went up — and turns
 * every connected account into the spec's CERTAIN signal. It needs ONE call
 * site, and it belongs on the nightly `17 4 * * *` leg src/cron.ts already
 * dispatches and production already registers (due.ts's header records that
 * the five-minute leg is dispatched but NOT registered). It writes evidence
 * and sends nothing, so an unsociable hour costs nobody a text:
 *
 *     await sweepConnectedSignals(env, Date.now());
 *
 * PORTS, waiting on a sense that does not report here yet, each honest about
 * what it needs rather than faked:
 *   - `observedHostSignal` needs the browser hand to report the host a run
 *     ended on. This is the most valuable of the six: it is the in-task moment
 *     the whole ask is built around, and due.ts already maps `observer` to
 *     that trigger.
 *   - `saidSignal` needs the judge's verdict from wherever the owner's words
 *     are already being read.
 *   - `signUpDomainSignals` needs the mail-exchanger lookup at sign-up.
 *   - `linkSignals` needs whatever isolates URLs out of a conversation.
 *   - `askedSignal` needs the ask engine to say it asked.
 * Every one of them is a function call away from a caller that has the input.
 *
 * Spec: docs/spec-connections.txt, PDF pages 41-47 (the surface table, the
 * signal weights, and the module list that names this file).
 */

/// <reference types="@cloudflare/workers-types" />

import type {
  AccountAlias,
  OwnerId,
  Toolkit,
  ToolkitMeta,
  ToolkitVerdict,
} from "../../../../spike/two-hands/src/connections/contract.ts";
import {
  ConnectionsSchemaMissing,
  SIGNAL_SOURCES,
  createD1Store,
  liveColumns,
  ownerId,
  type ConnectionsStore,
  type SignalSource,
  type StoreEnv,
  type StoredSignal,
} from "./store.ts";

export type { SignalSource, StoredSignal };

// ---------------------------------------------------------------------------
// THE WEIGHTS — the spec's own three bands, in the spec's own words.
// ---------------------------------------------------------------------------
// Page 42 gives each of the six signals a band and nothing finer, so the bands
// are the constants and the per-source table is a lookup into them. Writing
// six numbers instead would let two sources the spec calls the same thing
// drift apart in a later edit with nobody able to say which one was intended.
//
// The numbers are ORDERING, not probabilities. Nothing in this file compares
// one against a threshold: `rankRows` sorts, the caller takes the top, and the
// decision to interrupt belongs to the policy with its own four-state verdict.

/** Spec page 42, "High": the owner doing something, now — they named it, or a
 *  run of ours ended on it. */
export const WEIGHT_HIGH = 0.7;

/** Spec page 42, "Medium": real evidence, but about an address or a message
 *  rather than about a habit. */
export const WEIGHT_MEDIUM = 0.4;

/** Spec page 42, "Certain": a fact about our own records rather than an
 *  inference about the owner. */
export const WEIGHT_CERTAIN = 1;

/**
 * Every source the spec lists, and no other. The keys are exactly the
 * contract's closed enum (`SIGNAL_SOURCES` in store.ts, which the database's
 * own CHECK repeats), so a seventh source cannot be invented here without the
 * contract, the schema and this table all being edited together — and the test
 * compares the key sets rather than trusting that sentence.
 *
 * Frozen because a mutated entry is a band this file no longer means: raise
 * `link` to CERTAIN at run time and every message anybody ever pasted outranks
 * the app they actually opened.
 */
export const SOURCE_WEIGHT: Readonly<Record<SignalSource, number>> = Object.freeze({
  // "The user says it" — spec page 42, High.
  said: WEIGHT_HIGH,
  // "The browser hand saw it" — High.
  observer: WEIGHT_HIGH,
  // "Sign-up email domain" — Medium.
  mx: WEIGHT_MEDIUM,
  // "Links in conversations" — Medium.
  link: WEIGHT_MEDIUM,
  // "Already connected apps" — Certain.
  connected: WEIGHT_CERTAIN,
  // "Asking" — Certain.
  asked: WEIGHT_CERTAIN,
});

/**
 * WHICH SOURCES DECAY, and why the certain two do not.
 *
 * Decay answers "does this person still live here?", which is a question about
 * evidence going stale. A connection that exists and an ask that was answered
 * are not evidence going stale — they are the state of our own relationship
 * with this owner, and they are as true a year later. Letting them decay would
 * quietly re-open a settled question: an app connected last spring would sink
 * under an app touched last week, and a caller reading the top of the table
 * would ask somebody to connect a thing they already connected. That ask reads
 * as "Anticipy forgot", and it is the one thing a product built on silent
 * trust cannot afford to look like.
 */
export const SOURCE_DECAYS: Readonly<Record<SignalSource, boolean>> = Object.freeze({
  said: true,
  observer: true,
  mx: true,
  link: true,
  connected: false,
  asked: false,
});

/**
 * Half-life of an observational signal, in ms. Thirty days.
 *
 * WHAT IT BUYS, and it is the spec's own sentence: "Signals decay so an app you
 * stopped using stops coming up." At thirty days a signal is worth half, at
 * ninety an eighth, at a year about a four-thousandth — so a habit dropped in
 * the spring is out-ranked by anything touched last week, and ONE FRESH MEDIUM
 * SIGNAL OVERTAKES A HIGH ONE FROM THREE MONTHS AGO. That crossover is the
 * behaviour the spec asks for and the test pins it by name.
 *
 * WHAT IT COSTS, said plainly because it is a real cost and not a rounding
 * error: an app used honestly but RARELY — the payroll thing once a month, the
 * tax thing once a year — decays below apps touched daily and can fall off the
 * end of the table, so we will never ask about it. That is the deliberate
 * trade: better to miss an ask than to spend one of the owner's seven-day ask
 * budget on an app nobody has opened since the spring. The repeated-use
 * trigger catches the rare app instead, at the moment it is actually used.
 *
 * A parameter everywhere below, never a hidden constant, so the number can be
 * tuned from what converts rather than argued about here.
 */
export const DEFAULT_HALF_LIFE_MS = 30 * 24 * 60 * 60 * 1000;

/**
 * Two weights are the same weight when they differ by less than this,
 * relatively. Float addition of the same numbers in a different order lands a
 * few ulps apart, and that must not reorder the table under an owner nothing
 * about whom has changed. THIS EPSILON DECIDES ORDER, NEVER MEANING.
 */
const TIE_EPSILON = 1e-12;

// ---------------------------------------------------------------------------
// SHAPES
// ---------------------------------------------------------------------------

/** What a caller hands to `record`. `weight` is optional because the source
 *  already implies its band; a caller passing one is overriding the band on
 *  purpose (a backfill of half-confidence rows, say). */
export interface SignalInput {
  user_id: OwnerId | string;
  toolkit: Toolkit;
  source: SignalSource;
  last_seen_at: number;
  weight?: number;
  alias?: AccountAlias | null;
}

/** One line of the ranked table: an app, the account the evidence was about
 *  when it said, and what that evidence is worth right now. */
export interface RankedApp {
  toolkit: Toolkit;
  alias: AccountAlias | null;
  /** Summed decayed weight at the `now` that was passed in. */
  weight: number;
  /** Newest contributing signal, so a caller can say "seen last Tuesday"
   *  without going back to the rows. */
  lastSeenAt: number;
  /** Which sources fed this line, sorted. A caller may filter on these — a
   *  line carrying `connected` is an app to leave alone — but this file does
   *  not filter for it: that is the policy's decision, not the table's. */
  sources: SignalSource[];
}

export interface RankOptions {
  halfLifeMs?: number;
}

/** The half of the store this file needs. Narrow on purpose: a module that
 *  can reach `deleteConnection` from a signal ingest is a module one typo away
 *  from removing somebody's connection while recording evidence about it. */
export type SignalStore = Pick<ConnectionsStore, "recordSignal" | "signalsForOwner">;

// ---------------------------------------------------------------------------
// RUNTIME GUARDS — because types are stripped, not checked.
// ---------------------------------------------------------------------------
// Everything below runs after `--experimental-strip-types` has deleted every
// annotation above. A caller in plain JS, or a row read back with a column
// renamed, arrives here as `any`; a union type stops precisely nobody at run
// time. Each guard names the failure it stands in front of.

function checkedOwner(raw: unknown): OwnerId {
  // Delegated to the store's own constructor, which is the contract's rule
  // character for character: one definition of what an owner id looks like.
  // The failure it stands in front of is the worst this feature has — during
  // the spike one operator's own mailbox was connected by hand and served
  // everybody, and it had to be revoked and deleted.
  return ownerId(typeof raw === "string" ? raw : String(raw ?? ""));
}

function checkedSource(raw: unknown): SignalSource {
  // `hasOwnProperty`, never `in`: `"constructor" in SOURCE_WEIGHT` is true,
  // and a source called "constructor" would sail through to a weight of
  // `undefined` and poison every sum this owner has with a NaN.
  if (typeof raw === "string" && Object.prototype.hasOwnProperty.call(SOURCE_WEIGHT, raw)) {
    return raw as SignalSource;
  }
  // Loudly, rather than defaulting. An unrecognised source given a default
  // weight counts as much as a certainty, and the source somebody adds next is
  // exactly the one nobody has thought about the weight of yet.
  throw new Error(
    `not a signal source: ${JSON.stringify(raw)} — expected one of `
      + [...SIGNAL_SOURCES].sort().join(", "),
  );
}

function checkedToolkit(raw: unknown): Toolkit {
  const slug = typeof raw === "string" ? raw.trim().toLowerCase() : "";
  // Case and surrounding whitespace only. Two spellings of one slug would
  // split an app's evidence across two rows and sink both below an app with
  // less behind it. Any mapping between DIFFERENT slugs is deliberately
  // absent: a slug is the vendor's primary key, and guessing that two of them
  // are the same app is a judgement, not a normalisation.
  if (slug === "") {
    throw new Error("a signal needs a toolkit slug; got " + JSON.stringify(raw));
  }
  return slug;
}

function checkedAlias(raw: unknown): AccountAlias | null {
  if (raw === undefined || raw === null || raw === "") return null;
  // A closed two-value enum the contract declares. Comparing against it is
  // structure: it says which ACCOUNT a row is about and never what a person's
  // words meant.
  if (raw === "work" || raw === "personal") return raw;
  throw new Error(
    `not an account alias: ${JSON.stringify(raw)} — evidence is about one of the owner's `
      + "named accounts, or about none",
  );
}

function checkedTime(raw: unknown, field: string): number {
  const t = Number(raw);
  if (!Number.isFinite(t)) {
    throw new Error(`${field} must be a finite epoch-ms number; got ${JSON.stringify(raw)}`);
  }
  return t;
}

function checkedWeight(raw: unknown, source: SignalSource): number {
  if (raw === undefined || raw === null) return SOURCE_WEIGHT[source];
  const w = Number(raw);
  // Strictly positive. A zero adds nothing and is a caller bug worth hearing
  // about; a NEGATIVE weight would let one piece of evidence SUBTRACT another
  // and push an app below apps with no evidence at all — a "never ask about
  // this" reached through arithmetic, invisible to the state machine that is
  // supposed to own that decision.
  if (!Number.isFinite(w) || w <= 0) {
    throw new Error(`a signal weight must be a finite positive number; got ${JSON.stringify(raw)}`);
  }
  return w;
}

// ---------------------------------------------------------------------------
// DECAY
// ---------------------------------------------------------------------------

/**
 * A stored weight as it stands at `now`: `weight * 2^(-age / halfLife)`.
 *
 * Timestamp arithmetic is senses-and-plumbing, which law 1 permits by name.
 *
 * A signal stamped in the FUTURE — a handset with a wrong clock, a backfill
 * with a bad column — decays by zero rather than being amplified. Amplification
 * is the dangerous direction: one row carrying tomorrow's date would otherwise
 * out-weigh every honest signal an owner has and own the top of the table.
 */
export function decayedWeight(
  weight: number,
  lastSeenAt: number,
  now: number,
  halfLifeMs: number = DEFAULT_HALF_LIFE_MS,
): number {
  const w = Number(weight);
  if (!Number.isFinite(w)) return 0;
  const age = Number(now) - Number(lastSeenAt);
  if (!Number.isFinite(age) || age <= 0) return w;
  const half = Number(halfLifeMs);
  // A non-positive or non-finite half-life means "no decay configured". It must
  // not become a division that returns Infinity and zeroes every row: a broken
  // config should cost the freshness ordering, never the whole table.
  if (!Number.isFinite(half) || half <= 0) return w;
  return w * Math.pow(2, -age / half);
}

function decayedAt(row: StoredSignal, now: number, halfLifeMs: number): number {
  if (!SOURCE_DECAYS[row.source]) return Number(row.weight) || 0;
  return decayedWeight(row.weight, row.last_seen_at, now, halfLifeMs);
}

// ---------------------------------------------------------------------------
// THE MERGE — the arithmetic store.ts refuses to invent.
// ---------------------------------------------------------------------------

/**
 * The function `ConnectionsStore.recordSignal` is handed: given the row as it
 * stands (or null), what should it now hold?
 *
 * ACCUMULATION IS ORDER-INDEPENDENT. A repeat observation does not overwrite:
 * the stored weight is decayed forward to the newer of the two timestamps, the
 * incoming weight is decayed forward to the same instant, and the two are
 * added. That is what "each one adds weight" means once weights decay, and it
 * means a row that arrives late — a queued trace, a backfill — lands at the
 * value it would have had if it had arrived on time, instead of resetting an
 * app's whole history to one recent touch.
 *
 * OBSERVATIONS SUM; STATE IS SET. The same distinction that decides which
 * sources decay decides this, for the same reason: an observation is an event,
 * and two of them are more evidence than one; a connection that exists and an
 * ask that was answered are FACTS, and hearing a fact twice does not make it
 * truer. The concrete failure that prevents: `sweepConnectedSignals` runs on
 * every nightly tick. Summed, that row would grow without bound — a hundred
 * sweeps is a weight of a hundred — and one background job's schedule would
 * silently become the strongest signal an owner has. `max` also makes the
 * write idempotent, so a replayed sweep changes nothing at all.
 */
export function signalMerge(
  input: SignalInput,
  halfLifeMs: number = DEFAULT_HALF_LIFE_MS,
): (prior: StoredSignal | null) => { weight: number; last_seen_at: number } {
  const source = checkedSource(input?.source);
  const seenAt = checkedTime(input?.last_seen_at, "last_seen_at");
  const weight = checkedWeight(input?.weight, source);
  const decays = SOURCE_DECAYS[source];

  return (prior) => {
    const at = prior ? Math.max(Number(prior.last_seen_at), seenAt) : seenAt;
    const carried = prior
      ? (decays ? decayedWeight(prior.weight, prior.last_seen_at, at, halfLifeMs) : Number(prior.weight))
      : 0;
    const arriving = decays ? decayedWeight(weight, seenAt, at, halfLifeMs) : weight;
    return {
      weight: decays ? carried + arriving : Math.max(carried, arriving),
      last_seen_at: at,
    };
  };
}

/**
 * RECORD ONE PIECE OF EVIDENCE. The store owns the row and the race; this
 * function owns the band, the decay and the sum-vs-max rule.
 *
 * Returns the row as it now stands, so a caller can log what was actually
 * stored rather than what it thinks it sent.
 */
export async function record(
  store: SignalStore,
  input: SignalInput,
  opts: RankOptions = {},
): Promise<StoredSignal> {
  const user = checkedOwner(input?.user_id);
  const toolkit = checkedToolkit(input?.toolkit);
  const source = checkedSource(input?.source);
  const alias = checkedAlias(input?.alias);
  const halfLifeMs = opts.halfLifeMs ?? DEFAULT_HALF_LIFE_MS;
  // Built BEFORE the store is touched, so a bad timestamp or a negative weight
  // is a throw with nothing written rather than a merge callback that throws
  // halfway through a compare-and-set loop.
  const merge = signalMerge({ ...input, user_id: user, toolkit, source, alias }, halfLifeMs);
  return store.recordSignal({ user_id: user, toolkit, source, alias }, merge);
}

// ---------------------------------------------------------------------------
// RANKING
// ---------------------------------------------------------------------------

/** The identity of a row and of a ranked line. A NUL joiner, because a slug
 *  containing the separator would otherwise merge two apps into one line. */
function keyOf(toolkit: string, alias: AccountAlias | null): string {
  return [toolkit, alias ?? ""].join("\u0000");
}

/** The sort key rows are summed in, so the same evidence arriving in a
 *  different order produces the same float rather than one a few ulps away. */
function rowKey(row: StoredSignal): string {
  return [String(row.user_id), row.toolkit, row.alias ?? "", String(row.source)].join("\u0000");
}

/**
 * THE ORDER, and the only definition of it: weight descending, then toolkit,
 * then alias, both ascending, with two weights inside `TIE_EPSILON` of each
 * other counting as equal. Exported for two reasons.
 *
 * IT IS THE PROMISE, SO IT MUST BE BREAKABLE BY A TEST. Ties are the NORMAL
 * case here, not an exotic one: every band starts several apps at the same
 * weight, so a fresh owner is mostly ties. A comparison reachable only through
 * `rankRows` — which pre-sorts its input for float determinism and then hands
 * that already-ordered array to a stable sort — can be deleted outright with
 * every test still green. That happened in the spike on 2026-09-05 across an
 * 890-check suite. Keeping it reachable is what lets a test hold it.
 *
 * A CALLER THAT BUILDS ITS OWN LINES NEEDS IT. Anything that pages, merges or
 * re-sorts lines outside this module must reach for this rather than write the
 * ordering a second time: two definitions of "which app is first" is a table
 * that reorders itself between the screen and the message about it.
 */
export function compareRankedApps(a: RankedApp, b: RankedApp): number {
  const d = b.weight - a.weight;
  const scale = Math.max(1, Math.abs(a.weight), Math.abs(b.weight));
  if (Math.abs(d) > TIE_EPSILON * scale) return d > 0 ? 1 : -1;
  if (a.toolkit !== b.toolkit) return a.toolkit < b.toolkit ? -1 : 1;
  const aliasA = a.alias ?? "";
  const aliasB = b.alias ?? "";
  if (aliasA !== aliasB) return aliasA < aliasB ? -1 : 1;
  return 0;
}

/**
 * Rank one owner's rows into the table an ask is allowed to read from. PURE:
 * the D1-backed reader below selects that owner's rows and calls exactly this,
 * so the ordering that ships is the ordering the tests measure.
 *
 * WORK AND PERSONAL STAY APART. Lines are keyed by (toolkit, alias), so the
 * same app held twice ranks twice and a caller can name the right account.
 * Evidence that did not say which account keeps `alias: null` and is its OWN
 * line: it is not folded into either named account, because folding it would
 * be this file deciding which of the owner's two accounts somebody meant —
 * the judge's question, not ours.
 *
 * WHY THE OWNER IS AN ARGUMENT AND NOT AN INFERENCE. It is the caller's own
 * `WHERE user_id = ?` said out loud, and it is the only way the two different
 * ways that query goes wrong can be told apart:
 *
 *   FAN-OUT — two people's rows in one call, from a dropped `WHERE` or a join
 *   that multiplied. Visible in the rows themselves, and refused below.
 *
 *   SWAP — ONE person's rows, whole, consistent and perfectly readable,
 *   selected for somebody else: a `WHERE` bound to the wrong variable, a cache
 *   keyed by the previous request, a loop reusing the last iteration's id.
 *   Nothing in the rows can show it. Without being told whose table this is
 *   meant to be, this function would rank another person's apps and the caller
 *   would text THIS owner about them. An optional owner argument is a check
 *   the production caller can forget exactly once.
 */
export function rankRows(
  owner: OwnerId | string,
  rows: readonly StoredSignal[],
  now: number,
  opts: RankOptions = {},
): RankedApp[] {
  const halfLifeMs = opts.halfLifeMs ?? DEFAULT_HALF_LIFE_MS;
  const at = checkedTime(now, "now");
  const expected = checkedOwner(owner);

  const owners = new Set((rows ?? []).map((r) => String(r?.user_id)));
  if (owners.size > 1) {
    throw new Error(
      `rankRows was given ${owners.size} owners' rows at once — signals rank per owner, and a `
        + "mixed table would ask one person about another person's apps",
    );
  }
  for (const only of owners) {
    if (only !== expected) {
      throw new Error(
        `rankRows was asked for owner ${expected}'s table and handed owner ${only}'s rows — `
          + "ranking them would ask one person about another person's apps",
      );
    }
  }

  // Code-unit order, never `localeCompare`: collation depends on the ICU data
  // the runtime was built with, so two deploys of the same code could sum the
  // same rows in different orders and disagree in the last bits.
  const sorted = [...(rows ?? [])].sort((a, b) => {
    const ka = rowKey(a);
    const kb = rowKey(b);
    return ka < kb ? -1 : ka > kb ? 1 : 0;
  });

  const lines = new Map<string, RankedApp>();
  for (const row of sorted) {
    const alias = row.alias ?? null;
    const key = keyOf(row.toolkit, alias);
    const line = lines.get(key) ?? {
      toolkit: row.toolkit,
      alias,
      weight: 0,
      lastSeenAt: Number.NEGATIVE_INFINITY,
      sources: [] as SignalSource[],
    };
    line.weight += decayedAt(row, at, halfLifeMs);
    line.lastSeenAt = Math.max(line.lastSeenAt, Number(row.last_seen_at));
    if (!line.sources.includes(row.source)) line.sources.push(row.source);
    lines.set(key, line);
  }

  const out = [...lines.values()];
  for (const line of out) line.sources.sort();
  out.sort(compareRankedApps);
  return out;
}

/**
 * This owner's apps, most-lived-in first, decayed to `now`.
 *
 * ONE ID both selects the rows and is checked against them, so the filter and
 * the ranker cannot drift apart without one of them throwing.
 *
 * A KNOWN DIVERGENCE FROM due.ts, written down rather than left to be
 * rediscovered: that file's SQL orders by the STORED weight, which is the
 * weight as of each row's own `last_seen_at`, because SQLite cannot do the
 * exponential. This function decays to `now`. The two therefore agree on which
 * rows are alive (a stored weight of 0 is dead in both) and can disagree on
 * the ORDER of two live rows of different ages. That costs the choice of which
 * of one owner's apps is offered first, never whether somebody is asked at all
 * — and the whole answer is one ask per owner per seven days either way.
 */
export async function rankedApps(
  store: SignalStore,
  user: OwnerId | string,
  now: number,
  opts: RankOptions = {},
): Promise<RankedApp[]> {
  const id = checkedOwner(user);
  const rows = await store.signalsForOwner(id);
  return rankRows(id, rows, now, opts);
}

// ---------------------------------------------------------------------------
// HOSTS — the catalog's own url is the only thing that names an app.
// ---------------------------------------------------------------------------
// THIS IS THE LOOKUP, NOT THE JUDGEMENT. See the law-1 boundary at the top of
// the file. A run ends, or a message carries a link, and the sense layer hands
// back a host — already reduced to a registrable name by the public-suffix
// logic that lives with it. This file does not repeat that work and MUST NOT:
// a second copy of a suffix list here is a list of names of our own, which is
// precisely the hardcoding the spec forbids and the thing that makes a new app
// in the catalog cost code.
//
// So the comparison is between two hosts NEITHER OF WHICH THIS FILE CHOSE: the
// one that was observed, and the one the catalog entry carries in its own
// metadata. Equality over dot-separated labels, plus the two containment
// readings. That is string plumbing; it cannot name an app because it has no
// name to reach for.
//
// THE KNOWN LIMIT, and what it costs, stated rather than papered over. Without
// a suffix list this file cannot tell a name somebody registered from a name a
// registry hands out — so the WEAKEST reading, where the observed host merely
// CONTAINS a catalog entry, comes back as a SHORTLIST and never as a verdict,
// however few entries are on it. Measured in the spike on 2026-09-05: with
// exactly ONE catalog entry under it, a bare registry suffix came back as a
// confident match and turned into a HIGH weight on an app the owner may never
// have opened — the top of the table, and an ask. One entry is not less
// ambiguous than two; it is the same guess with nothing to compare against.
//
// Whether a name sitting ABOVE an app's own url is that app is a question
// about what a name means, and law 1 gives those to a model: a caller holding
// a shortlist may put it to the judge, which has the owner's context and this
// file does not. The cost is a missed signal whenever a single-app vendor's
// catalog url sits below the host the sense layer reduced to — real, and the
// cheap direction to be wrong in, because the expensive one is a message
// asking somebody to connect an app they do not use.

export type HostMatch =
  | { kind: "toolkit"; slug: Toolkit }
  /** Nothing in the catalog claims this host. Say so; never fall back to the
   *  nearest entry, the first entry, or the highest-ranked one. */
  | { kind: "none" }
  /** A SHORTLIST, one entry or several, and never a pick. */
  | { kind: "ambiguous"; slugs: Toolkit[] };

const NO_HOST_MATCH: HostMatch = { kind: "none" };

/** How the two hosts sit relative to one another, strongest first. */
type HostRelation = "exact" | "observed-under-catalog" | "catalog-under-observed";
const RELATION_STRENGTH: readonly HostRelation[] =
  Object.freeze(["exact", "observed-under-catalog", "catalog-under-observed"]);

/**
 * The labels of a host, or null if there is not one. Accepts a bare host or an
 * absolute url, because the observed side arrives as a host and the catalog
 * side arrives as a url.
 */
function hostLabels(raw: unknown): string[] | null {
  const s = (typeof raw === "string" ? raw : "").trim().toLowerCase();
  if (s === "") return null;

  let text = s;
  if (!s.includes("://")) {
    // A bare host has no path, no credentials and no whitespace. Refusing those
    // outright beats letting the url parser find a "host" inside them: a string
    // carrying an "@" would otherwise parse with everything before it as
    // credentials, and a completely unrelated tail would become the host.
    if (/[\s/@?#]/.test(s)) return null;
    text = `https://${s}`;
  }

  let url: URL;
  try {
    url = new URL(text);
  } catch {
    return null;
  }
  // Two schemes only. A catalog entry under some other scheme carries no host
  // worth comparing, and a scheme that can carry code has no business being
  // reduced to a name here.
  if (url.protocol !== "http:" && url.protocol !== "https:") return null;

  let host = url.hostname;
  while (host.endsWith(".")) host = host.slice(0, -1);
  if (host === "") return null;
  // A bracketed literal address is one opaque label: it has no registrar
  // inside it, so only exact equality can ever mean anything.
  if (host.startsWith("[")) return [host];

  const labels = host.split(".");
  if (labels.some((l) => l === "")) return null;
  return labels;
}

/** A dotted quad is an address, not a name with an owner inside it. Trimming
 *  labels off one produces another perfectly valid address belonging to
 *  somebody else entirely, so containment must never apply to it. */
function isNumericHost(labels: string[]): boolean {
  if (labels.length === 1) return labels[0].startsWith("[");
  return labels.every((l) => /^[0-9]+$/.test(l));
}

function sameLabels(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((l, i) => l === b[i]);
}

/** True when `inner`'s trailing labels are exactly `outer` — `inner` is a
 *  strict subdomain of `outer`. */
function isUnder(inner: string[], outer: string[]): boolean {
  if (inner.length <= outer.length) return false;
  return sameLabels(inner.slice(inner.length - outer.length), outer);
}

function relate(observed: string[], catalog: string[]): HostRelation | null {
  if (sameLabels(observed, catalog)) return "exact";
  if (isNumericHost(observed) || isNumericHost(catalog)) return null;
  // Two labels minimum on both sides before containment is allowed. It is the
  // only brake available without a suffix list, and it stops the shortest and
  // most dangerous reading — a single-label host swallowing every entry.
  if (observed.length < 2 || catalog.length < 2) return null;
  if (isUnder(observed, catalog)) return "observed-under-catalog";
  if (isUnder(catalog, observed)) return "catalog-under-observed";
  return null;
}

/**
 * Which toolkit is this observed host, judged only by what the catalog says
 * about itself. THE SPEC'S OWN RULE: "Host matched to a catalog toolkit
 * through the toolkit's meta.app_url. No domain list of our own."
 *
 * PRECEDENCE, strongest first, and only the strongest tier that matched is
 * considered:
 *   1. the same host — nothing beats it;
 *   2. the observed host is UNDER the catalog's url — a catalog entry usually
 *      points at the root of a product's site, and a page inside that site is
 *      that product;
 *   3. the catalog's url is under the OBSERVED host — the weak reading, and
 *      the one a host reduced to a registrable name produces. Kept because it
 *      is often right for a single-app vendor, and returned as a SHORTLIST
 *      however few entries are on it: this tier is what a bare registry suffix
 *      produces too, and nothing available here tells those apart.
 *
 * Two entries matching at the strongest tier is `ambiguous`, never a pick.
 */
export function hostToToolkit(host: string, catalog: readonly ToolkitMeta[]): HostMatch {
  const observed = hostLabels(host);
  if (!observed) return NO_HOST_MATCH;

  const byRelation = new Map<HostRelation, Set<Toolkit>>();
  for (const meta of catalog ?? []) {
    const slug = typeof meta?.slug === "string" ? meta.slug.trim().toLowerCase() : "";
    if (slug === "") continue;
    const theirs = hostLabels(meta?.appUrl);
    if (!theirs) continue;
    const relation = relate(observed, theirs);
    if (!relation) continue;
    const bucket = byRelation.get(relation) ?? new Set<Toolkit>();
    bucket.add(slug);
    byRelation.set(relation, bucket);
  }

  for (const relation of RELATION_STRENGTH) {
    const slugs = [...(byRelation.get(relation) ?? [])].sort();
    if (slugs.length === 0) continue;
    // Comparing the relation is comparing a closed enum declared four lines
    // up, not reading a hostname for what it means.
    if (relation === "catalog-under-observed") return { kind: "ambiguous", slugs };
    if (slugs.length === 1) return { kind: "toolkit", slug: slugs[0] };
    return { kind: "ambiguous", slugs };
  }
  return NO_HOST_MATCH;
}

// ===========================================================================
// THE SIX DOORS — one per row of the spec's signal table, page 42.
// ===========================================================================
// Every one of them is a FLOOR: it returns null (or an empty list) rather than
// a hedged signal, and evidence has to be positively established to weigh
// anything. Each `*Signal` function is pure and takes no store, so a caller
// can see what would be recorded before anything is written, and each
// `record*` companion writes it.

/**
 * 1. "THE USER SAYS IT" — spec page 42, High.
 *
 * Built from the JUDGE'S VERDICT, never from the sentence. This function
 * deliberately never sees a phrase: it takes the four-state answer and reads
 * exactly one state as a licence. That is why it exists as a function rather
 * than as three lines at a call site, where the next person in a hurry would
 * be one `includes()` away from re-deciding the question with a word list.
 *
 * `unclear`, `none`, `no-verdict`, a null (the judge was unreachable) and a
 * verdict whose slug is blank all record NOTHING. Silence must not nudge.
 */
export function saidSignal(
  user: OwnerId | string,
  verdict: ToolkitVerdict | null | undefined,
  saidAt: number,
  alias: AccountAlias | null = null,
): SignalInput | null {
  if (!verdict || verdict.kind !== "toolkit") return null;
  const slug = typeof verdict.slug === "string" ? verdict.slug.trim().toLowerCase() : "";
  if (slug === "") return null;
  return { user_id: user, toolkit: slug, source: "said", last_seen_at: saidAt, alias };
}

export async function recordUserSaidIt(
  store: SignalStore,
  user: OwnerId | string,
  verdict: ToolkitVerdict | null | undefined,
  saidAt: number,
  alias: AccountAlias | null = null,
  opts: RankOptions = {},
): Promise<StoredSignal | null> {
  const input = saidSignal(user, verdict, saidAt, alias);
  return input ? record(store, input, opts) : null;
}

/**
 * 2. "THE BROWSER HAND SAW IT" — spec page 42, High.
 *
 * A run ended on a site. `null` unless exactly one catalog entry NAMES the
 * host: an ambiguous host — several entries, or a host that merely contains
 * one — must not silently become weight on whichever app sorted first, because
 * the weight it would add is HIGH and would carry that app to the top of the
 * table on no evidence at all.
 *
 * This is the door due.ts turns into the in-task moment, and it is the most
 * valuable of the six for exactly that reason.
 */
export function observedHostSignal(
  user: OwnerId | string,
  host: string,
  catalog: readonly ToolkitMeta[],
  seenAt: number,
  alias: AccountAlias | null = null,
): SignalInput | null {
  const match = hostToToolkit(host, catalog);
  if (match.kind !== "toolkit") return null;
  return { user_id: user, toolkit: match.slug, source: "observer", last_seen_at: seenAt, alias };
}

export async function recordObservedHost(
  store: SignalStore,
  user: OwnerId | string,
  host: string,
  catalog: readonly ToolkitMeta[],
  seenAt: number,
  alias: AccountAlias | null = null,
  opts: RankOptions = {},
): Promise<StoredSignal | null> {
  const input = observedHostSignal(user, host, catalog, seenAt, alias);
  return input ? record(store, input, opts) : null;
}

/**
 * 3. "SIGN-UP EMAIL DOMAIN" — spec page 42, Medium. "DNS MX lookup at sign-up
 * ... Seeds the onboarding list before we know anything else. Consumer domains
 * map directly."
 *
 * TWO HOSTS, ONE LOOKUP, and both go through the catalog exactly the way an
 * observed host does. The domain the owner signed up under covers the spec's
 * "consumer domains map directly"; the mail exchangers cover hosted mail,
 * where the domain is the owner's own and only the exchanger says who runs it.
 *
 * IT DOES NOT DO THE LOOKUP. The DNS half is a sense and lives with whatever
 * performs it at sign-up; this function takes the answer. It also never sees
 * an email address — a caller passes the domain, because an address is a
 * person's identity and this table stores apps.
 *
 * Several exchangers can name several apps, so this one returns a LIST. It
 * de-duplicates by slug: three exchangers pointing at one app is one fact
 * about who runs the mail, not three.
 */
export function signUpDomainSignals(
  user: OwnerId | string,
  hosts: { emailDomain?: string | null; mxHosts?: readonly string[] },
  catalog: readonly ToolkitMeta[],
  seenAt: number,
): SignalInput[] {
  const seen = new Set<Toolkit>();
  const out: SignalInput[] = [];
  const candidates = [
    ...(typeof hosts?.emailDomain === "string" ? [hosts.emailDomain] : []),
    ...(Array.isArray(hosts?.mxHosts) ? hosts.mxHosts : []),
  ];
  for (const host of candidates) {
    const match = hostToToolkit(String(host ?? ""), catalog);
    if (match.kind !== "toolkit") continue;
    if (seen.has(match.slug)) continue;
    seen.add(match.slug);
    // No alias. Which of the owner's two accounts a mail exchanger belongs to
    // is not a thing an exchanger can say, and inventing that the sign-up one
    // is the work one is the same class of mistake as inventing which app
    // somebody meant.
    out.push({ user_id: user, toolkit: match.slug, source: "mx", last_seen_at: seenAt, alias: null });
  }
  return out;
}

export async function recordSignUpDomain(
  store: SignalStore,
  user: OwnerId | string,
  hosts: { emailDomain?: string | null; mxHosts?: readonly string[] },
  catalog: readonly ToolkitMeta[],
  seenAt: number,
  opts: RankOptions = {},
): Promise<StoredSignal[]> {
  const out: StoredSignal[] = [];
  for (const input of signUpDomainSignals(user, hosts, catalog, seenAt)) {
    out.push(await record(store, input, opts));
  }
  return out;
}

/**
 * 4. "LINKS IN CONVERSATIONS" — spec page 42, Medium. "Same host-to-toolkit
 * match as above."
 *
 * THE LINE THIS FUNCTION SITS ON, because it is the one most likely to be
 * crossed by a well-meaning edit. Turning a URL's host into a toolkit through
 * the catalog's own url is a LOOKUP and is what the spec asks for. Finding
 * which characters of a conversation were a URL is the sense layer's job and
 * happens before this call. Deciding what a sentence was ABOUT is a judgement
 * and belongs to a model. So this function takes URLs — already isolated,
 * already whole — and never a transcript, and there is no regex over prose
 * anywhere in this file.
 *
 * Returns a list, de-duplicated by slug: one message carrying four links to
 * one app is one piece of evidence about that app, not four.
 */
export function linkSignals(
  user: OwnerId | string,
  urls: readonly string[],
  catalog: readonly ToolkitMeta[],
  seenAt: number,
  alias: AccountAlias | null = null,
): SignalInput[] {
  const seen = new Set<Toolkit>();
  const out: SignalInput[] = [];
  for (const url of Array.isArray(urls) ? urls : []) {
    const match = hostToToolkit(String(url ?? ""), catalog);
    if (match.kind !== "toolkit") continue;
    if (seen.has(match.slug)) continue;
    seen.add(match.slug);
    out.push({ user_id: user, toolkit: match.slug, source: "link", last_seen_at: seenAt, alias });
  }
  return out;
}

export async function recordLinksSeen(
  store: SignalStore,
  user: OwnerId | string,
  urls: readonly string[],
  catalog: readonly ToolkitMeta[],
  seenAt: number,
  alias: AccountAlias | null = null,
  opts: RankOptions = {},
): Promise<StoredSignal[]> {
  const out: StoredSignal[] = [];
  for (const input of linkSignals(user, urls, catalog, seenAt, alias)) {
    out.push(await record(store, input, opts));
  }
  return out;
}

/**
 * 5. "ALREADY CONNECTED APPS" — spec page 42, Certain. "Also tells us which
 * account to use by default", which is why the alias rides along.
 *
 * A slug, not a host: by the time an account is connected the toolkit is a
 * fact we hold, so there is nothing to look up and nothing to judge.
 */
export function connectedSignal(
  user: OwnerId | string,
  toolkit: Toolkit,
  connectedAt: number,
  alias: AccountAlias | null = null,
): SignalInput {
  return { user_id: user, toolkit, source: "connected", last_seen_at: connectedAt, alias };
}

export async function recordConnectedApp(
  store: SignalStore,
  user: OwnerId | string,
  toolkit: Toolkit,
  connectedAt: number,
  alias: AccountAlias | null = null,
  opts: RankOptions = {},
): Promise<StoredSignal> {
  return record(store, connectedSignal(user, toolkit, connectedAt, alias), opts);
}

/**
 * 6. "ASKING" — spec page 42, Certain. "Onboarding question, or in
 * conversation when two candidates tie. Ask once, remember the answer."
 *
 * THIS IS THE ANSWER, NOT THE ASK. It is recorded when somebody TELLS us they
 * use an app — the onboarding list they ticked, the tie they broke — and never
 * when we asked and heard nothing. A row written on the asking would make our
 * own question the evidence for asking again, which is a machine talking
 * itself into a second message.
 */
export function askedSignal(
  user: OwnerId | string,
  toolkit: Toolkit,
  answeredAt: number,
  alias: AccountAlias | null = null,
): SignalInput {
  return { user_id: user, toolkit, source: "asked", last_seen_at: answeredAt, alias };
}

export async function recordAnswerToAsk(
  store: SignalStore,
  user: OwnerId | string,
  toolkit: Toolkit,
  answeredAt: number,
  alias: AccountAlias | null = null,
  opts: RankOptions = {},
): Promise<StoredSignal> {
  return record(store, askedSignal(user, toolkit, answeredAt, alias), opts);
}

// ===========================================================================
// THE SWEEP — the one door whose input production already produces.
// ===========================================================================

/**
 * How many connections one sweep turns into evidence. It bounds the work a
 * single tick does, the way src/cron.ts's prune does, so a backlog drains over
 * several nights instead of timing out forever on the first.
 *
 * NOBODY STARVES AT THE TAIL, which is the trap a capped sweep with a stable
 * ORDER BY walks into: the same first N rows every night and the tail never
 * reached. The query selects only connections that have NO signal row yet, so
 * a row that was processed LEAVES the candidate set and the next tick takes
 * the next N. In the steady state the sweep selects zero rows.
 */
export const CONNECTED_SWEEP_CAP = 200;

/** What each table must have live for this sweep to mean anything. The same
 *  discipline as store.ts's `REQUIRED` and due.ts's, for the same measured
 *  reason: on 2026-09-05 a live table was missing two columns schema.sql
 *  declared and every write turned into a D1 1101. A missing table does not
 *  throw in every SQLite — it throws in one and returns nothing in another,
 *  and "nothing" is indistinguishable from "nobody has connected anything". */
const SWEEP_REQUIRED: Readonly<Record<string, readonly string[]>> = Object.freeze({
  app_usage_signals: ["user_id", "toolkit", "source", "weight", "last_seen_at"],
  connections: ["user_id", "toolkit", "status"],
});

async function requireSweepTables(env: StoreEnv): Promise<void> {
  for (const table of Object.keys(SWEEP_REQUIRED)) {
    const live = await liveColumns(env, table);
    const missing = (SWEEP_REQUIRED[table] ?? []).filter((c) => !live.has(c));
    // An EMPTY set is the table not existing at all, which `filter` reports as
    // every column missing — the same error, naming the same migration.
    if (missing.length > 0) throw new ConnectionsSchemaMissing(table, missing);
  }
}

export interface ConnectedSweepResult {
  /** Connections with no evidence row yet that this tick looked at. */
  scanned: number;
  /** Rows written. */
  recorded: number;
  /** Rows the database held that could not be read as an owner and an app. */
  dropped: number;
}

interface ConnectionRow {
  user_id: unknown;
  toolkit: unknown;
  alias: unknown;
}

/**
 * The candidates: every CONNECTED account this owner holds that has no
 * `connected` evidence row yet.
 *
 * `NOT EXISTS` rather than `LEFT JOIN … IS NULL`, so a duplicate row on either
 * side cannot multiply the candidates. The alias is matched too: the same app
 * held twice is two piles of evidence, and the ask that comes out of one has
 * to be able to name the account.
 *
 * ORDER is deterministic so a capped tick is reproducible rather than
 * "whatever the b-tree walked into first".
 */
const CONNECTED_SWEEP_SQL = `
  SELECT c."user_id" AS "user_id", c."toolkit" AS "toolkit", c."alias" AS "alias"
    FROM "connections" c
   WHERE c."status" = 'connected'
     AND NOT EXISTS (
           SELECT 1 FROM "app_usage_signals" s
            WHERE s."user_id" = c."user_id"
              AND s."toolkit" = c."toolkit"
              AND s."alias"   = c."alias"
              AND s."source"  = 'connected')
   ORDER BY c."user_id" ASC, c."toolkit" ASC, c."alias" ASC
   LIMIT ?1`;

/**
 * TURN THE CONNECTIONS TABLE INTO EVIDENCE — the spec's CERTAIN signal, for
 * every account anybody has already connected.
 *
 * WHY THIS ONE IS THE CHEAP HONEST START. `app_usage_signals` had zero rows on
 * 2026-09-06 while the connect page had been live for a day, so the fact that
 * some owners use some apps was already sitting in `connections` with nothing
 * reading it across. This costs one bounded query a night and needs no sense
 * that does not exist.
 *
 * WHAT IT IS NOT ENOUGH FOR, said plainly so nobody reads a full table as a
 * working feature: a `connected` row is not a MOMENT, and due.ts will not turn
 * it into an ask — it selects only `observer` and `said`. What this sweep buys
 * is a table that is no longer empty, ranking that has something to rank, and
 * the second app in a ranked list being offered after the first is connected.
 * The ask itself still waits on the observer door being wired.
 *
 * IT NEVER DELETES. A disconnected app keeps its row, because "they used this
 * enough to connect it once" stays true, and `connected` does not decay.
 * Whether an app is connected RIGHT NOW is a question about the `connections`
 * table, which due.ts asks there directly.
 *
 * IT THROWS RATHER THAN RETURNING ZEROS when it cannot read the tables. Those
 * are opposite facts — "nothing to do" and "we could not tell" — and collapsing
 * them turns a missing migration into a permanently empty table with a green
 * log line, which is the shape of the failure that left the ears deaf for 30
 * hours.
 */
export async function sweepConnectedSignals(
  env: StoreEnv,
  now: number,
  opts: { cap?: number; signalStore?: SignalStore } & RankOptions = {},
): Promise<ConnectedSweepResult> {
  const at = checkedTime(now, "now");
  const cap = opts.cap ?? CONNECTED_SWEEP_CAP;
  if (typeof cap !== "number" || !Number.isFinite(cap) || cap < 0) {
    throw new TypeError(`sweepConnectedSignals was given ${JSON.stringify(cap)} as its cap`);
  }
  await requireSweepTables(env);
  const store = opts.signalStore ?? createD1Store(env);

  const res = await env.DB.prepare(CONNECTED_SWEEP_SQL)
    .bind(Math.floor(cap))
    .all<ConnectionRow>();
  const rows = res.results ?? [];

  const out: ConnectedSweepResult = { scanned: rows.length, recorded: 0, dropped: 0 };
  for (const row of rows) {
    // Re-checked on the way out, not trusted on the way in. A row that cannot
    // be read is DROPPED, not thrown on: one malformed row must not cost every
    // other owner their evidence, and dropping is the direction that records
    // less rather than records it against the wrong person.
    let owner: OwnerId;
    try {
      owner = checkedOwner(row?.user_id);
    } catch {
      out.dropped++;
      console.log("connected signal sweep: dropped a connection whose user_id is not an owner id");
      continue;
    }
    let toolkit: Toolkit;
    let alias: AccountAlias | null;
    try {
      toolkit = checkedToolkit(row?.toolkit);
      alias = checkedAlias(row?.alias);
    } catch {
      out.dropped++;
      console.log("connected signal sweep: dropped a connection with no readable app");
      continue;
    }
    // `at`, not the connection's own timestamp: what this row records is that
    // the connection EXISTS as of this sweep. `connected` does not decay, so
    // the stamp is a record and never an input to the arithmetic.
    await recordConnectedApp(store, owner, toolkit, at, alias, opts);
    out.recorded++;
  }
  if (out.scanned > 0) {
    console.log(
      `connected signal sweep: ${out.recorded} recorded, ${out.dropped} dropped, `
        + `${out.scanned} scanned`,
    );
  }
  return out;
}

// ---------------------------------------------------------------------------
// THE BOUND SEAM
// ---------------------------------------------------------------------------

/**
 * The six doors and the ranked read, bound to one live database, for a caller
 * that has an `env` and does not want to build a store.
 *
 *     const signals = createSignals(env);
 *     await signals.observedHost(owner, host, catalog, Date.now());
 */
export function createSignals(env: StoreEnv, opts: RankOptions = {}) {
  const store = createD1Store(env);
  return {
    store,
    record: (input: SignalInput) => record(store, input, opts),
    rank: (user: OwnerId | string, now: number, o: RankOptions = opts) =>
      rankedApps(store, user, now, o),
    said: (
      user: OwnerId | string, verdict: ToolkitVerdict | null | undefined,
      saidAt: number, alias: AccountAlias | null = null,
    ) => recordUserSaidIt(store, user, verdict, saidAt, alias, opts),
    observedHost: (
      user: OwnerId | string, host: string, catalog: readonly ToolkitMeta[],
      seenAt: number, alias: AccountAlias | null = null,
    ) => recordObservedHost(store, user, host, catalog, seenAt, alias, opts),
    signUpDomain: (
      user: OwnerId | string,
      hosts: { emailDomain?: string | null; mxHosts?: readonly string[] },
      catalog: readonly ToolkitMeta[], seenAt: number,
    ) => recordSignUpDomain(store, user, hosts, catalog, seenAt, opts),
    links: (
      user: OwnerId | string, urls: readonly string[], catalog: readonly ToolkitMeta[],
      seenAt: number, alias: AccountAlias | null = null,
    ) => recordLinksSeen(store, user, urls, catalog, seenAt, alias, opts),
    connected: (
      user: OwnerId | string, toolkit: Toolkit, connectedAt: number,
      alias: AccountAlias | null = null,
    ) => recordConnectedApp(store, user, toolkit, connectedAt, alias, opts),
    answered: (
      user: OwnerId | string, toolkit: Toolkit, answeredAt: number,
      alias: AccountAlias | null = null,
    ) => recordAnswerToAsk(store, user, toolkit, answeredAt, alias, opts),
    sweepConnected: (now: number, cap?: number) =>
      sweepConnectedSignals(env, now, { ...opts, cap, signalStore: store }),
  };
}
