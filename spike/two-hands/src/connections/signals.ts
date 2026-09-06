// SIGNALS — how Anticipy learns which apps somebody lives in, without asking.
//
// The spec's rule (page 22) is that we never hand a new owner a questionnaire.
// Evidence arrives from things that actually happened — they said it, a browser
// run ended on a site, the sign-up address' mail exchanger points somewhere, a
// message carried a link, a connection already exists, we already asked — and
// each piece adds weight to one row of `app_usage_signals(user, toolkit)`.
// Weight DECAYS, so an app they left behind stops climbing to the top of the
// table, and the top of the table is what a nudge is allowed to ask about.
//
// THE FAILURE THIS FILE IS BUILT AGAINST. Two of them, and they are different.
//
//   1. WRONG PERSON. During the spike one operator's own mailbox was connected
//      by hand and served everybody; it had to be revoked and deleted. Every
//      row here is keyed by the owner ROW id, and `record` re-checks it through
//      the contract's `ownerId()` at RUNTIME — types are stripped by the
//      runtime this ships on, so a display name or an email flowing in from a
//      caller that confused "who is this" with "what do we call them" would
//      otherwise be stored happily and ranked for the wrong human being.
//
//   2. A LIST OF APP NAMES. The whole promise is that a new app in the catalog
//      is a new app in Anticipy with zero code. So this file knows no app: not
//      a name, not a domain, not a slug. `hostToToolkit` reaches an app only
//      through the catalog entry's OWN url, and `test/connections_signals.test.ts`
//      reads this source back and fails if a domain or an app name appears in
//      it — in code or in prose, because a name in a comment is where the next
//      agent's branch on that name starts.
//
// ---------------------------------------------------------------------------
// LAW 1 BOUNDARY — the line this module sits exactly on. Read before editing.
// ---------------------------------------------------------------------------
// PLUMBING, and legal here:
//   - comparing an observed host against a catalog entry's own url. That is
//     string equality over dot-separated labels. It cannot express "this app in
//     particular" because the only strings it compares are two hosts somebody
//     else supplied, one of them by the catalog at run time.
//   - decay arithmetic over timestamps, and validating a closed enum that the
//     contract declares.
//
// MEANING, and forbidden here:
//   - deciding that a person saying "my work email" or naming a product out
//     loud meant a particular toolkit. No word list holds the ways somebody
//     refers to the app they live in, and a list that half-holds them is worse
//     than none: it is confidently wrong on the owner whose wording is not in
//     it. HARNESS-LAWS law 1 gives that question to a model — the contract's
//     `ToolkitJudge` — and this module takes its VERDICT as an input
//     (`saidSignal`) instead of re-reading the sentence.
//
// The polarity of that input is a FLOOR, deliberately: a signal ADDS weight,
// weight is what eventually licenses interrupting somebody, and a privilege
// needs something positive to license it. So only `{ kind: "toolkit" }` becomes
// a signal. `unclear`, `none` and `no-verdict` — including the judge being
// unreachable — add nothing at all. Silence must not be able to nudge.

import { ownerId } from "./contract.ts";
import type {
  AccountAlias,
  AppUsageSignal,
  OwnerId,
  Toolkit,
  ToolkitMeta,
  ToolkitVerdict,
} from "./contract.ts";

export type SignalSource = AppUsageSignal["source"];

// ---------------------------------------------------------------------------
// WEIGHTS — config, from the spec's own three bands.
// ---------------------------------------------------------------------------
// "said" and an observed host after a browser run are HIGH: both are the owner
// doing something, now. A mail-exchanger lookup and a link in a conversation
// are MEDIUM: real evidence, but about an address or a message rather than
// about a habit. An existing connection and an ask that was answered are
// CERTAIN, because they are facts about our own records rather than inferences
// about the owner.
//
// The numbers are ordering, not scores anyone should read as probabilities.
// Nothing in this file compares one against a threshold — `rank` sorts, the
// caller takes the top, and the decision to interrupt belongs to the nudge
// policy with its own four-state verdict.
export const SOURCE_WEIGHT: Readonly<Record<SignalSource, number>> = Object.freeze({
  connected: 1,
  asked: 1,
  said: 0.7,
  observer: 0.7,
  mx: 0.4,
  link: 0.4,
});

// WHICH SOURCES DECAY, and why the certain two do not.
//
// Decay answers "does this person still live here?", which is a question about
// evidence going stale. An existing connection and an answered ask are not
// evidence going stale — they are the state of our own relationship with this
// owner, and they are as true a year later. Letting them decay would quietly
// re-open a settled question: an app connected last spring would sink under an
// app touched last week, and the caller reading the top of the table would ask
// somebody to connect a thing they already connected. That ask reads as
// "Anticipy forgot", and it is the one thing a product built on silent trust
// cannot afford to look like.
export const SOURCE_DECAYS: Readonly<Record<SignalSource, boolean>> = Object.freeze({
  connected: false,
  asked: false,
  said: true,
  observer: true,
  mx: true,
  link: true,
});

/**
 * Half-life of an observational signal, in ms. Thirty days.
 *
 * WHAT IT BUYS: an app somebody stopped using stops coming up on its own, with
 * nobody deleting a row and no rule anywhere saying "stale". At thirty days a
 * signal is worth half, at ninety an eighth, at a year about a four-thousandth
 * — so a habit they dropped in the spring is out-ranked by anything they
 * touched last week, and one fresh MEDIUM signal overtakes a HIGH one from
 * three months ago. That crossover is the behaviour the spec asks for and
 * `test/connections_signals.test.ts` pins it.
 *
 * WHAT IT COSTS, said plainly because it is a real cost and not a rounding
 * error: an app used honestly but RARELY — the payroll thing once a month, the
 * tax thing once a year — decays below apps touched daily and can fall off the
 * end of the table, so we will never ask about it. That is the deliberate
 * trade: this file would rather miss an ask than spend one of the owner's
 * seven-day ask budget on an app they have not opened since the spring. The
 * repeated-use trigger in the nudge policy is what catches the rare app
 * instead, at the moment it is actually being used.
 *
 * It is a parameter and not a constant in the code below, so the number can be
 * tuned from what converts rather than argued about here.
 */
export const DEFAULT_HALF_LIFE_MS = 30 * 24 * 60 * 60 * 1000;

/** Ordering ties are broken by NAME, never by arrival order — a rank that
 *  depends on the order rows came back from storage is a rank that changes
 *  under the owner without anything about the owner changing. Two weights are
 *  the same weight when they differ by less than this, relatively; float
 *  addition of the same numbers in a different order lands a few ulps apart and
 *  that must not reorder the table. This epsilon decides ORDER, never meaning. */
const TIE_EPSILON = 1e-12;

// ---------------------------------------------------------------------------
// ROWS
// ---------------------------------------------------------------------------

/**
 * A stored `app_usage_signals` row: the contract's shape, plus the account this
 * evidence was about.
 *
 * WHY `alias` IS HERE AND NOT IN THE CONTRACT. The spec's normal case is the
 * same person holding two accounts on one provider, work and personal, and the
 * contract's `Connection` carries an `AccountAlias` for exactly that. Its
 * `AppUsageSignal` does not, so the table as declared cannot say WHICH of the
 * two accounts a signal was about — the evidence would be merged into one row
 * and the ask that came out of it could not name the account. This module
 * carries the column as an optional extra rather than editing the fixed
 * contract; it is reported back as a contract problem.
 *
 * `null` is the honest and by far the commonest value: it means "we have no
 * idea which account this was about", and NOTHING in this file ever turns a
 * null into a guess. Inventing that a second account is the personal one is the
 * same class of mistake as inventing which app somebody meant.
 */
export interface StoredSignal extends AppUsageSignal {
  alias: AccountAlias | null;
}

/** What a caller hands to `record`. `weight` is optional because the source
 *  already implies it; a caller that passes one is overriding the band on
 *  purpose (a backfill with half-confidence rows, say). */
export interface SignalInput {
  user_id: OwnerId | string;
  toolkit: Toolkit;
  source: SignalSource;
  last_seen_at: number;
  weight?: number;
  alias?: AccountAlias | null;
}

/** One line of the ranked table: an app, an account when the evidence said, and
 *  what the evidence is worth right now. */
export interface RankedApp {
  toolkit: Toolkit;
  alias: AccountAlias | null;
  /** Summed decayed weight at the `now` that was passed in. */
  weight: number;
  /** Newest contributing signal, so a caller can show "seen last Tuesday"
   *  without going back to the rows. */
  lastSeenAt: number;
  /** Which sources fed this line, sorted. The caller filters on these — a line
   *  carrying `connected` is an app to leave alone, a line carrying `asked` is
   *  one the nudge state machine already owns. This module does not do that
   *  filtering itself: ranking answers "which apps does this person live in",
   *  and "may we interrupt them about it" is a different question with a
   *  different owner. */
  sources: SignalSource[];
}

// ---------------------------------------------------------------------------
// RUNTIME GUARDS — because types are stripped, not checked.
// ---------------------------------------------------------------------------
// Everything below runs on `node --experimental-strip-types`. The annotations
// above are removed before the first line executes, so a caller in plain JS, or
// a row read back out of D1 with a column renamed, arrives here as `any`. Each
// guard names the failure it is standing in front of.

function checkedOwner(raw: unknown): OwnerId {
  // Delegated to the contract's own constructor on purpose: one definition of
  // what an owner id looks like, in the file that explains why it exists.
  return ownerId(typeof raw === "string" ? raw : String(raw ?? ""));
}

function checkedSource(raw: unknown): SignalSource {
  // `hasOwnProperty`, never `in`: `"constructor" in SOURCE_WEIGHT` is true, and
  // a source called "constructor" would sail through to a weight of `undefined`
  // and poison every sum this owner has.
  if (typeof raw === "string" && Object.prototype.hasOwnProperty.call(SOURCE_WEIGHT, raw)) {
    return raw as SignalSource;
  }
  // Loudly, rather than defaulting: an unrecognised source given a default
  // weight would count as much as a certainty, and the source that gets added
  // next is exactly the one nobody has thought about the weight of yet.
  throw new Error(
    `not a signal source: ${JSON.stringify(raw)} — expected one of ${Object.keys(SOURCE_WEIGHT).sort().join(", ")}`,
  );
}

function checkedToolkit(raw: unknown): Toolkit {
  const slug = typeof raw === "string" ? raw.trim().toLowerCase() : "";
  // Lowercasing is plumbing: the contract says slugs are lowercase, and two
  // spellings of one slug would split one app's evidence across two rows and
  // sink both below an app with less behind it.
  if (slug === "") {
    throw new Error("a signal needs a toolkit slug; got " + JSON.stringify(raw));
  }
  return slug;
}

function checkedAlias(raw: unknown): AccountAlias | null {
  if (raw === undefined || raw === null) return null;
  // A closed two-value enum the contract declares. Comparing against it is
  // structure, not meaning — it says which ACCOUNT a row is about, and never
  // what a person's words meant.
  if (raw === "work" || raw === "personal") return raw;
  throw new Error(
    `not an account alias: ${JSON.stringify(raw)} — evidence is about one of the owner's named accounts, or about none`,
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
  // this" reached through arithmetic, invisible to the nudge state machine that
  // is supposed to own that decision.
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
 * Timestamp arithmetic is senses-and-plumbing, which law 1 permits explicitly.
 *
 * A signal stamped in the FUTURE — a phone with a wrong clock, a backfill with
 * a bad column — decays by zero rather than being amplified. Amplification is
 * the dangerous direction: a single row with tomorrow's date would otherwise
 * out-weigh every honest signal the owner has and own the top of the table
 * outright.
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
  // config should lose the freshness ordering, never the whole table.
  if (!Number.isFinite(half) || half <= 0) return w;
  return w * Math.pow(2, -age / half);
}

function decayedAt(row: StoredSignal, now: number, halfLifeMs: number): number {
  if (!SOURCE_DECAYS[row.source]) return Number(row.weight) || 0;
  return decayedWeight(row.weight, row.last_seen_at, now, halfLifeMs);
}

// ---------------------------------------------------------------------------
// RANKING
// ---------------------------------------------------------------------------

export interface RankOptions {
  halfLifeMs?: number;
}

/** The identity of a row and of a ranked line. A NUL joiner, because a slug
 *  containing the separator would otherwise merge two apps into one row. */
function keyOf(user: string, toolkit: string, alias: AccountAlias | null, source?: string): string {
  return [user, toolkit, alias ?? "", source ?? ""].join("\u0000");
}

/**
 * THE ORDER, and the only definition of it: weight descending, then toolkit,
 * then alias, both ascending, with two weights inside `TIE_EPSILON` of each
 * other counting as equal. Exported for two reasons.
 *
 * IT IS THE PROMISE, SO IT MUST BE BREAKABLE BY A TEST. `rankRows` sums rows in
 * a sorted order (for float determinism), and that pre-sort happens to hand its
 * output array to a stable sort in tie order already — so on 2026-09-05 both
 * tie-break comparisons were deleted and the entire 890-test suite stayed
 * green. A promise no test can break is a promise nobody is keeping, and ties
 * are the NORMAL case here rather than an exotic one: every source band starts
 * several apps at the same weight, so a fresh owner is mostly ties. Keeping the
 * comparison here, reachable on its own, is what lets
 * `test/connections_signals.test.ts` hold it — see "order:" there.
 *
 * A CALLER THAT BUILDS ITS OWN LINES NEEDS IT. In production the rows come from
 * D1, and a caller that pages, merges or re-sorts lines outside this module
 * must reach for this rather than write the ordering a second time: two
 * definitions of "which app is first" is a table that reorders itself between
 * the screen and the text message about it.
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
 * Rank one owner's rows into the table a nudge is allowed to read from. PURE:
 * the D1-backed caller selects that owner's rows and calls exactly this, so the
 * ordering that ships is the ordering the tests measure.
 *
 * ORDER IS TOTAL AND DOES NOT DEPEND ON ARRIVAL — `compareRankedApps` above is
 * the whole definition. Rows are summed in a sorted order too, so the same
 * evidence arriving in a different order produces the same float, not one a few
 * ulps away that could reorder two neighbours.
 *
 * WORK AND PERSONAL STAY APART. Lines are keyed by (toolkit, alias), so the same
 * app held twice ranks twice and the caller can ask about the right account.
 * Evidence that did not say which account keeps `alias: null` and is its own
 * line: it is not folded into either named account, because folding it would be
 * this module deciding which of the owner's two accounts somebody meant, and
 * that is the judge's question, not ours.
 *
 * WHY THE OWNER IS AN ARGUMENT AND NOT AN INFERENCE. It is the caller's own
 * `WHERE user_id = ?` said out loud, and it is the only way the two different
 * ways a query goes wrong can be told apart. See the guard below.
 */
export function rankRows(
  owner: OwnerId | string,
  rows: readonly StoredSignal[],
  now: number,
  opts: RankOptions = {},
): RankedApp[] {
  const halfLifeMs = opts.halfLifeMs ?? DEFAULT_HALF_LIFE_MS;
  const at = checkedTime(now, "now");

  // WHOSE TABLE IS THIS. Two failures live here and only one of them used to be
  // catchable.
  //
  //   FAN-OUT — two people's rows in one call, from a dropped `WHERE` or a join
  //   that multiplied. Visible in the rows themselves, and refused below.
  //
  //   SWAP — ONE person's rows, whole, consistent and perfectly readable,
  //   selected for somebody else: a `WHERE user_id = ?` bound to the wrong
  //   variable, a cache keyed by the previous request, a batch loop reusing the
  //   last iteration's id. Nothing in the rows can show it. Without being told
  //   whose table this is meant to be, this function would rank another
  //   person's apps and the caller would text THIS owner about them — one
  //   operator's mailbox serving everybody, reached by a query instead of by a
  //   constant. That is why the expected owner is a required argument: an
  //   optional one is a check the production caller can forget exactly once.
  const expected = checkedOwner(owner);

  const owners = new Set((rows ?? []).map((r) => String(r?.user_id)));
  if (owners.size > 1) {
    throw new Error(
      `rankRows was given ${owners.size} owners' rows at once — signals rank per owner, and a mixed table would ask one person about another person's apps`,
    );
  }
  for (const only of owners) {
    if (only !== expected) {
      throw new Error(
        `rankRows was asked for owner ${expected}'s table and handed owner ${only}'s rows — ranking them would ask one person about another person's apps`,
      );
    }
  }

  // Code-unit order, never `localeCompare`: collation depends on the ICU data
  // the runtime was built with, so two deploys of the same code could sum the
  // same rows in different orders and disagree in the last bits.
  const sorted = [...(rows ?? [])].sort((a, b) => {
    const ka = keyOf(String(a.user_id), a.toolkit, a.alias ?? null, a.source);
    const kb = keyOf(String(b.user_id), b.toolkit, b.alias ?? null, b.source);
    return ka < kb ? -1 : ka > kb ? 1 : 0;
  });

  const lines = new Map<string, RankedApp>();
  for (const row of sorted) {
    const alias = row.alias ?? null;
    const key = keyOf("", row.toolkit, alias);
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

// ---------------------------------------------------------------------------
// THE TABLE
// ---------------------------------------------------------------------------

export interface SignalTable {
  /** Add evidence. Returns the row as it now stands, so a caller can log what
   *  it actually stored rather than what it thinks it sent. */
  record(input: SignalInput): StoredSignal;
  /** This owner's apps, most-lived-in first, decayed to `now`. */
  rank(user: OwnerId | string, now: number, opts?: RankOptions): RankedApp[];
  /** This owner's raw rows, for a caller that has to show its work. */
  rows(user: OwnerId | string): StoredSignal[];
}

export interface SignalTableOptions {
  halfLifeMs?: number;
}

/**
 * The spike's in-memory `app_usage_signals`. In production this is D1 and the
 * upsert below is one statement; the arithmetic and the ordering stay here, in
 * `rankRows` and `decayedWeight`, so that what the tests measure is what the
 * query returns.
 *
 * ONE ROW PER (owner, toolkit, alias, source), which is how the contract's row
 * shape reads — it carries `source` as a column, so a table keyed only by
 * (user, toolkit) could hold one source per app and would silently drop the
 * second kind of evidence.
 *
 * ACCUMULATION IS ORDER-INDEPENDENT. A repeat OBSERVATION does not overwrite: the
 * stored weight is decayed forward to the newer of the two timestamps, the
 * incoming weight is decayed forward to the same instant, and the two are
 * added. That is what "each signal adds weight" means once weights decay, and
 * it means a row that arrives late — a queued observer trace, a backfill —
 * lands at the value it would have had if it had arrived on time, instead of
 * resetting an app's whole history to one recent touch.
 */
export function createSignalTable(opts: SignalTableOptions = {}): SignalTable {
  const halfLifeMs = opts.halfLifeMs ?? DEFAULT_HALF_LIFE_MS;
  const table = new Map<string, StoredSignal>();

  function record(input: SignalInput): StoredSignal {
    const user = checkedOwner(input?.user_id);
    const toolkit = checkedToolkit(input?.toolkit);
    const source = checkedSource(input?.source);
    const alias = checkedAlias(input?.alias);
    const seenAt = checkedTime(input?.last_seen_at, "last_seen_at");
    const weight = checkedWeight(input?.weight, source);

    const key = keyOf(user, toolkit, alias, source);
    const prior = table.get(key);
    const decays = SOURCE_DECAYS[source];
    const at = prior ? Math.max(prior.last_seen_at, seenAt) : seenAt;

    // OBSERVATIONS SUM; STATE IS SET. The same distinction that decides which
    // sources decay decides this, and it is the same reason: an observation is
    // an event, and two of them are more evidence than one; a connection that
    // exists and an ask that was answered are FACTS, and hearing a fact twice
    // does not make it truer.
    //
    // The concrete failure this prevents: whatever loop syncs connections from
    // the provider records "connected" on every pass. Summed, that row grows
    // without bound — a hundred syncs is a weight of a hundred — and one
    // background job's schedule silently becomes the strongest signal this
    // owner has. `max` also makes the write idempotent and order-independent,
    // so a replayed sync changes nothing at all.
    const carried = prior
      ? (decays ? decayedWeight(prior.weight, prior.last_seen_at, at, halfLifeMs) : prior.weight)
      : 0;
    const arriving = decays ? decayedWeight(weight, seenAt, at, halfLifeMs) : weight;
    const merged = decays ? carried + arriving : Math.max(carried, arriving);

    const row: StoredSignal = {
      user_id: user,
      toolkit,
      source,
      alias,
      weight: merged,
      last_seen_at: at,
    };
    table.set(key, row);
    return { ...row };
  }

  function rows(user: OwnerId | string): StoredSignal[] {
    const id = checkedOwner(user);
    // Filtered by owner id and nothing else. One owner's evidence must never
    // reach another owner's ask — that is the same failure as one operator's
    // mailbox serving everybody, one table down.
    return [...table.values()].filter((r) => r.user_id === id).map((r) => ({ ...r }));
  }

  function rank(user: OwnerId | string, now: number, rankOpts: RankOptions = {}): RankedApp[] {
    // One id both selects the rows and is checked against them, so the filter
    // and the ranker cannot drift apart without one of them throwing.
    const id = checkedOwner(user);
    return rankRows(id, rows(id), now, { halfLifeMs, ...rankOpts });
  }

  return { record, rank, rows };
}

// ---------------------------------------------------------------------------
// HOSTS — the catalog's url is the only thing that names an app.
// ---------------------------------------------------------------------------
// A browser run ends and the sense layer hands back at most one host: the site
// the step was actually working in, already reduced to a registrable domain by
// the public-suffix logic that lives with the observer. This file does not
// repeat that work and MUST NOT: a second copy of a suffix list here is a list
// of domains of our own, which is precisely the hardcoding the spec forbids and
// the thing that makes a new app in the catalog cost code.
//
// So the comparison is between two hosts neither of which this file chose: the
// one that was observed, and the one the CATALOG ENTRY carries in its own
// metadata. Equality over dot-separated labels, plus the two containment
// readings. That is string plumbing; it cannot name an app because it has no
// name to reach for.
//
// THE KNOWN LIMIT, and what it costs, stated rather than papered over. Without
// a suffix list this file cannot tell a name somebody registered from a name a
// registry hands out — so the WEAKEST reading, where the observed host merely
// CONTAINS a catalog entry, is handed back as a SHORTLIST and never as a
// verdict, however few entries are on it.
//
// That is a real defect being closed, not a hypothetical. Measured 2026-09-05:
// with exactly ONE catalog entry under it, a bare registry suffix came back as
// a confident match and `observedHostSignal` turned that into a HIGH weight on
// an app the owner may never have opened — the top of the owner's table, and an
// ask. One entry is not less ambiguous than two; it is the same guess with
// nothing to compare it against, which is worse. The comment that used to sit
// here claimed a bare suffix "comes back ambiguous"; it did not, and a comment
// is not a guard.
//
// Whether a name sitting ABOVE an app's own url is that app is a question about
// what a name means, and law 1 gives those to a model: the caller may put the
// shortlist to the judge, which has the owner's context and this file does not.
// The cost is a missed signal whenever a one-app vendor's catalog url sits
// below the host the observer reduced to — real, and the cheap direction to be
// wrong in, because the expensive one is a text asking somebody to connect an
// app they do not use. A suffix list here would cost the no-hardcoding promise
// and would rot silently the first time a registry added an entry.

export type HostMatch =
  | { kind: "toolkit"; slug: Toolkit }
  /** Nothing in the catalog claims this host. Say so; do not fall back to the
   *  nearest entry, the first entry, or the highest-ranked one. */
  | { kind: "none" }
  /** A SHORTLIST, one entry or several, and never a pick. Two causes, and both
   *  are the same coin toss:
   *
   *  Several entries claim the host at the same strength — one vendor's several
   *  apps sharing a registrable domain, which is exactly what a host reduced to
   *  eTLD+1 cannot tell apart. Two candidates and a coin is a wrong answer half
   *  the time.
   *
   *  Or the observed host merely CONTAINS the entries, however few: with no
   *  suffix list this file cannot tell the vendor's own name from a name a
   *  registry hands out, so "one entry under it" is not evidence of anything.
   *
   *  The wrong answer here is a text asking somebody to connect an app they do
   *  not use, so the caller may put the shortlist to the judge; this file will
   *  not pick. */
  | { kind: "ambiguous"; slugs: Toolkit[] };

const NO_HOST_MATCH: HostMatch = { kind: "none" };

/** How the two hosts sit relative to one another, strongest first. */
type HostRelation = "exact" | "observed-under-catalog" | "catalog-under-observed";
const RELATION_STRENGTH: HostRelation[] = ["exact", "observed-under-catalog", "catalog-under-observed"];

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
    // with an "@" would otherwise parse with everything before it as
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
  // http(s) only. A catalog entry whose url is some other scheme carries no
  // host worth comparing, and a scheme that can carry code has no business
  // being reduced to a name here.
  if (url.protocol !== "http:" && url.protocol !== "https:") return null;

  let host = url.hostname;
  while (host.endsWith(".")) host = host.slice(0, -1);
  if (host === "") return null;
  // A bracketed literal address is one opaque label: it has no registrar inside
  // it, so only exact equality can ever mean anything.
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

/** True when `inner`'s trailing labels are exactly `outer` — i.e. `inner` is a
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
  // most dangerous readings — a single-label host swallowing every entry.
  if (observed.length < 2 || catalog.length < 2) return null;
  if (isUnder(observed, catalog)) return "observed-under-catalog";
  if (isUnder(catalog, observed)) return "catalog-under-observed";
  return null;
}

/**
 * Which toolkit is this observed host, judged only by what the catalog says
 * about itself.
 *
 * PRECEDENCE, strongest first, and only the strongest tier that matched is
 * considered:
 *   1. the same host — nothing beats it;
 *   2. the observed host is UNDER the catalog's url — a catalog entry usually
 *      points at the root of the product's site, and a page inside that site is
 *      that product;
 *   3. the catalog's url is under the OBSERVED host — the weak reading, and the
 *      one a host reduced to a registrable domain produces. It is kept because
 *      it is often right when a vendor has one app, and it is returned as a
 *      SHORTLIST rather than as a pick however many entries are on it: this
 *      tier is the one a bare registry suffix produces, and nothing available
 *      here can tell those two apart. See the note above this section.
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
    // The weak tier is a shortlist even at one candidate. A host that only
    // CONTAINS a catalog entry may be the vendor's own name or a name a
    // registry hands out, and this file has nothing to tell those apart with —
    // so it names no app, and the HIGH observer weight is never spent on the
    // guess. Comparing the relation is comparing a closed enum three lines up,
    // not reading a hostname for what it means.
    if (relation === "catalog-under-observed") return { kind: "ambiguous", slugs };
    if (slugs.length === 1) return { kind: "toolkit", slug: slugs[0] };
    return { kind: "ambiguous", slugs };
  }
  return NO_HOST_MATCH;
}

// ---------------------------------------------------------------------------
// THE TWO EVIDENCE DOORS
// ---------------------------------------------------------------------------
// Both return `null` rather than a hedged signal, and both are FLOORS: evidence
// has to be positively established to weigh anything. See the law 1 boundary at
// the top of this file.

/**
 * A signal from a browser run that ended on a known site. `null` unless exactly
 * one catalog entry NAMES the host — an ambiguous host (several entries, or a
 * host that merely contains one) must not silently become weight on whichever
 * app sorted first, because the weight it would add is HIGH and would carry
 * that app to the top of the table on no evidence at all.
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

/**
 * A signal from something the owner SAID, built from the judge's verdict.
 *
 * This function deliberately never sees the sentence. It takes the four-state
 * verdict and reads exactly one state as a licence — which is the whole reason
 * it exists as a function rather than as three lines at a call site, where the
 * next person in a hurry would be one `includes()` away from re-deciding the
 * question here with a word list.
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
