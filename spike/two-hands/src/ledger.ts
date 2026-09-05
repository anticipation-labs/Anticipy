// THE LEDGER — the only thing in the two-hands spike that changes over time,
// and it changes from OUTCOMES, not from code.
//
// Everything else in this directory is a pure function of its inputs. This file
// is the memory: which capabilities the API hand has earned, for whom, and on
// what evidence. The whole no-hardcoding claim depends on the promotion ladder
// below being the ONLY way a step reaches the API hand — no app list, no verb
// list, no "gmail is fine, calendly is not". A pair climbs because runs
// happened and they were checked, or it does not climb.
//
// WHAT IS AND IS NOT A LAW-1 QUESTION IN HERE.
// Nothing in this file reads a sentence. The counts below (3 parity matches,
// 10 clean reads, 3 confirmed writes, 2 consecutive failures) are the owner's
// ladder, and they count OUTCOMES — runs that happened and were verified —
// not words. The one place a string arrives from outside is `failReason`, and
// the rule there is exact equality against the closed `ExecErrorKind` set the
// provider adapter already produces; there is no substring test, no regex, and
// no prose anywhere in a branch. See `asErrorKind` for why that distinction is
// load-bearing rather than fussy.
//
// ONE DEFINITION OF EVIDENCE, AND WHY IT IS WRITTEN DOWN.
// Every gate below is paid for in runs the VERIFIER vouched for, and exactly
// one predicate decides that (`isVerifierMismatch`, plus the `verified` line in
// `#applyEvidence`). This file failed that once, which is why it is stated
// here: the rung 2 -> 3 gate — the one that UNLOCKS WRITES — banked reads whose
// `verifierResult` was "unknown", while the 3 -> 4 gate directly underneath it
// refused the identical evidence and said in its own comment why. Two
// neighbouring gates disagreeing about what counts means one of them is wrong,
// and it was the one guarding the bigger privilege. Anything added here that
// moves a counter reads the same predicate or it is the same bug again.
//
// STORAGE. Week 2 puts these tables on D1. Everything the ledger stores goes
// through `LedgerStore`/`LedgerTable`, whose methods are all async even though
// the in-memory implementation answers instantly — a synchronous store
// interface would force the whole body of this file to be rewritten the day D1
// arrives, which is the exact seam this indirection exists to protect.

import {
  judgeLicensesApi,
  type ApiCandidate,
  type CapabilityStats,
  type ConnectNudge,
  type ExecErrorKind,
  type Hand,
  type Ledger,
  type NudgeState,
  type Outcome,
  type Rung,
  type ShadowRun,
} from "./contract.ts";

// ---------------------------------------------------------------------------
// THE LADDER, AS NUMBERS. Exported so the gate that measures week 1 reads the
// same constants the ledger enforces, instead of a second copy that drifts.
// ---------------------------------------------------------------------------
export const LADDER = {
  /** rung 1 -> 2: three CONSECUTIVE parity matches the VERIFIER vouched for. */
  PARITY_MATCHES_FOR_API_READS: 3,
  /** rung 2 -> 3: ten API reads whose effect the verifier actually saw, on top
   *  of the owner's write opt-in. Same quality of evidence as the gate above it
   *  and the gate below it — see `#applyEvidence`. */
  CLEAN_READS_FOR_ASSISTED_WRITES: 10,
  /** rung 3 -> 4: three writes whose effect the verifier actually saw. */
  CONFIRMED_WRITES_FOR_AUTO_WRITES: 3,
  /** Two in a row, and only failures that are the tool's fault. */
  CONSECUTIVE_API_FAILURES_TO_DEMOTE: 2,
  /** A user who has connected the app but never opted into writes may inherit
   *  the read half of the ladder and no more. */
  MAX_INHERITED_RUNG_WITHOUT_WRITE_CONSENT: 2,
  /** With their own write opt-in they may start at ASSISTED writes — every one
   *  confirmed — and never at auto writes, however well it works for others. */
  MAX_INHERITED_RUNG_WITH_WRITE_CONSENT: 3,
} as const;

// ---------------------------------------------------------------------------
// THE STORAGE SEAM
// ---------------------------------------------------------------------------
// Keys are hierarchical and joined with the ASCII unit separator, so a prefix
// scan is a real query on every backend we might use next (D1: `WHERE k LIKE
// ?||'%'`; KV: `list({prefix})`). Using "-" or ":" instead would break the day
// an app slug contains one, and `signature_hash` "abc" would match "abcd".
const SEP = "\u001f";

function rowKey(...parts: string[]): string {
  return parts.join(SEP);
}

/** A prefix that can only match whole key segments. The trailing separator is
 *  the point: without it, sig "abc" scans up rows belonging to sig "abcdef". */
function scanKey(...parts: string[]): string {
  return parts.join(SEP) + SEP;
}

export interface LedgerTable<Row> {
  get(key: string): Promise<Row | undefined>;
  put(key: string, row: Row): Promise<void>;
  prefix(prefix: string): Promise<Row[]>;
  /** The full scan. Used by ONE thing — the cross-user global prior — and
   *  called out here because on D1 it needs an index on (signature_hash, app)
   *  rather than a table walk. */
  all(): Promise<Row[]>;
}

/** Rows the ledger keeps that the spec's four tables have no column for. They
 *  are separate tables rather than extra columns because the four table shapes
 *  are fixed in contract.ts and a fifth column on capability_stats would make
 *  the contract and the store disagree about what a row is. */
export interface LadderState {
  user_id: string;
  signature_hash: string;
  app: string;
  /** The rung this pair stands on. `Ledger.rung()` may report lower — see
   *  `shadow_required`. */
  rung: Rung;
  /**
   * How far this pair could have climbed FROM RUNG 0 on nothing but its own
   * verified outcomes — one rung per gate it actually passed. The only number
   * that may travel to a stranger through `globalRung`.
   *
   * `rung` is not that number. It is also where an operator override put the
   * pair (`setRung`), and where an inherited prior left it, and neither is
   * evidence about the tool. Exporting `rung` is how one line typed at 2am to
   * work around the write-ladder gap (RESULTS.md FINDING 1) becomes the
   * starting rung of every other user who connected that app.
   *
   * Read "one rung per gate" literally: a pair stood up at rung 3 by hand that
   * then passes the 3 -> 4 gate has earned ONE rung, not four. `#promote` adds
   * one; it never lifts this up to `rung`, because doing so would let the given
   * rung act as a floor under the earned one — which is the same leak wearing a
   * different hat.
   */
  evidence_rung: Rung;
  /** Zero means nothing has ever moved this pair on its own evidence, which is
   *  what makes it eligible to inherit the global prior. Unlike
   *  `evidence_rung`, an operator override DOES count here: an override that
   *  was silently recomputed back into an inheritance would not be one. */
  own_ladder_events: number;
  parity_streak: number;
  /** Cumulative, for the audit line. Deliberately NOT a gate: see `climb`. */
  parity_mismatches: number;
  clean_reads: number;
  confirmed_writes: number;
  consecutive_api_failures: number;
  /** Set by every demotion. While it is true the pair routes as shadow whatever
   *  rung it has earned — that is the "re-opens shadow" half of a demotion. */
  shadow_required: boolean;
  last_change_at: number;
  /** For a human reading the audit log. NOTHING branches on these words. */
  last_change_reason: string;
}

export interface AppConsent {
  user_id: string;
  app: string;
  connected: boolean;
  /** Per (user, app). There is no global version of this field and there must
   *  never be one: consent is the one thing a prior may not carry across. */
  writes_opted_in: boolean;
  writes_opted_in_at: number | null;
}

/** p50/p95 cannot be maintained from a running mean, and capability_stats has
 *  nowhere to put the raw sample, so it lives beside it under the same key. */
export interface LatencySample {
  key: string;
  ms: number[];
}

/** A ShadowRun carries `run_id`/`step_id` and no owner, so it cannot be joined
 *  back to a (user, signature_hash, app) pair. The join key is stored beside
 *  the contract row rather than inside it, because contract.ts is fixed. */
export interface ShadowRunRow {
  run: ShadowRun;
  user_id: string | null;
  signature_hash: string | null;
  app: string | null;
  at: number;
}

export interface LedgerStore {
  capability_stats: LedgerTable<CapabilityStats>;
  api_candidates: LedgerTable<ApiCandidate>;
  connect_nudges: LedgerTable<ConnectNudge>;
  shadow_runs: LedgerTable<ShadowRunRow>;
  ladder_state: LedgerTable<LadderState>;
  app_consent: LedgerTable<AppConsent>;
  latency_samples: LedgerTable<LatencySample>;
}

export class MemoryTable<Row> implements LedgerTable<Row> {
  #rows = new Map<string, Row>();

  // Rows go in and come out as copies. A caller that kept the object it got
  // back and edited a counter would be changing the ladder without an outcome,
  // which is the single thing this whole file exists to prevent.
  async get(key: string): Promise<Row | undefined> {
    const row = this.#rows.get(key);
    return row === undefined ? undefined : (structuredClone(row) as Row);
  }

  async put(key: string, row: Row): Promise<void> {
    this.#rows.set(key, structuredClone(row) as Row);
  }

  async prefix(prefix: string): Promise<Row[]> {
    const out: Row[] = [];
    for (const [key, row] of this.#rows) {
      if (key.startsWith(prefix)) out.push(structuredClone(row) as Row);
    }
    return out;
  }

  async all(): Promise<Row[]> {
    return [...this.#rows.values()].map((row) => structuredClone(row) as Row);
  }

  get size(): number {
    return this.#rows.size;
  }
}

export function memoryStore(): LedgerStore {
  return {
    capability_stats: new MemoryTable<CapabilityStats>(),
    api_candidates: new MemoryTable<ApiCandidate>(),
    connect_nudges: new MemoryTable<ConnectNudge>(),
    shadow_runs: new MemoryTable<ShadowRunRow>(),
    ladder_state: new MemoryTable<LadderState>(),
    app_consent: new MemoryTable<AppConsent>(),
    latency_samples: new MemoryTable<LatencySample>(),
  };
}

// ---------------------------------------------------------------------------
// PERCENTILES
// ---------------------------------------------------------------------------
/**
 * Nearest rank, never interpolated. p95 of two runs is the slower of the two,
 * not their average: the week-1 gate is "p50 under 3 seconds" measured against
 * runs that actually happened, and an interpolated percentile reports a latency
 * no call ever took.
 *
 * The rank is computed as `(n * pct) / 100` and not `(pct / 100) * n` because
 * the second form rounds: `(7/100)*100` is 7.000000000000001, which ceils to 8
 * and returns the wrong sample. p50 and p95 happen to be safe at every size
 * this spike will see, but the function takes an arbitrary percentile and the
 * integer-first form is free.
 */
export function percentile(samples: number[], pct: number): number {
  if (samples.length === 0) return 0;
  const sorted = [...samples].sort((a, b) => a - b);
  const rank = Math.ceil((sorted.length * pct) / 100);
  const index = Math.min(sorted.length - 1, Math.max(0, rank - 1));
  return sorted[index];
}

// Money is added in floating point and a hundred 0.0001 calls come to
// 0.009999999999999995. The week-1 table prints a cost per capability, and a
// number no invoice will ever match reads as a bug in the meter.
function addCost(total: number, add: number): number {
  const sum = total + (Number.isFinite(add) ? add : 0);
  return Math.round(sum * 1e6) / 1e6;
}

/**
 * The rung the router was actually given, which is the earned rung capped at
 * shadow while a demotion's shadow re-open is outstanding.
 *
 * Defined once and used in three places — `rung()`, the capability_stats
 * projection, and the read/write classifier — because when the classifier used
 * the EARNED rung instead, a pair demoted from 4 to 3 was told to run shadow
 * reads and had its shadow reads scored as writes: one disagreeing read then
 * read as "verifier mismatch on a write" and demoted it a second time for doing
 * exactly what it was told.
 */
function routableRung(earned: Rung, shadowRequired: boolean): Rung {
  return shadowRequired ? clampRung(Math.min(earned, 1)) : clampRung(earned);
}

function clampRung(n: number): Rung {
  if (n <= 0) return 0;
  if (n >= 4) return 4;
  return Math.floor(n) as Rung;
}

// ---------------------------------------------------------------------------
// WHAT THE CONTRACT'S `Outcome` CANNOT SAY, AND HOW THAT IS FILLED IN
// ---------------------------------------------------------------------------
// `Outcome` has no side_effect and no error kind, and the ladder needs both:
// "10 clean reads" and "3 confirmed writes" are different counters, and an
// expired token must not look like a broken tool. Both are OPTIONAL additions
// carried beside the contract's fields rather than inside them, so a caller
// holding a plain `Outcome` still works and a caller that knows more can say
// so. Where they are absent the fallbacks below are conservative in the
// direction that protects the owner.
export interface LedgerOutcome extends Outcome {
  /** The step's declared side effect. Absent -> inferred from the rung. */
  side_effect?: "read" | "write" | "irreversible";
  /** The provider's own `ExecResult.error.kind`. Absent -> read off
   *  `failReason` only when that string IS one of the four kinds exactly. */
  failKind?: ExecErrorKind;
  /** Injected clock for tests and for replaying a run. */
  at?: number;
  /** The step really ran, but its duration was NOT measured — the Observer had
   *  evicted its trace before anyone read it, so the summary's 0 means "we lost
   *  the tape", not "it took no time".
   *
   *  It matters because rule 5 prefers the faster hand. Feeding a fabricated 0
   *  into p50/p95 lets the browser hand look instantaneous, on evidence nobody
   *  gathered, and the ladder would then quietly campaign against the very hand
   *  that did the work. So an unmeasured run still counts toward n, successes
   *  and the rungs — it happened — and contributes no latency sample. */
  unmeasured?: boolean;
}

const EXEC_ERROR_KINDS: ReadonlySet<string> = new Set<string>([
  "auth",
  "rate",
  "schema",
  "other",
]);

/**
 * The only string this file inspects, and it is inspected by EXACT equality
 * against a closed set our own provider adapter produces — not by searching it
 * for "401" or "unauthor".
 *
 * A substring test would be a pattern deciding what a failure MEANS, and it
 * would be wrong in both directions on real vendor prose: "not authorized to
 * exceed your rate limit" contains both words, and a vendor that renames its
 * 401 body next quarter silently turns every token expiry back into a demotion.
 * Anything we do not recognise is "other" — which DEMOTES on the second one in
 * a row. That polarity is deliberate: the carve-out is the exception and has to
 * be claimed, because a ledger that treats unknown failures as excusable never
 * demotes anything and the ladder becomes decoration.
 */
export function asErrorKind(failReason: string | undefined): ExecErrorKind {
  if (typeof failReason === "string" && EXEC_ERROR_KINDS.has(failReason)) {
    return failReason as ExecErrorKind;
  }
  return "other";
}

/**
 * THE SINGLE MOST IMPORTANT DISTINCTION IN THIS FILE.
 *
 * A 401 or a 429 is not the tool being wrong. The token expired, or we went too
 * fast. Demoting for it would take a working capability away from the owner
 * because a refresh token aged out overnight, re-open shadow mode, and make the
 * agent drive the browser for a week to re-earn ground it never lost. It is
 * recorded as `last_fail_reason` — which is what the connect-nudge reads to ask
 * the owner to reconnect — and it moves no counter at all.
 *
 * It does not RESET the consecutive-failure counter either. If it did, a token
 * expiring between two genuine failures would launder them into "not
 * consecutive" and a broken tool would sit at rung 4 indefinitely.
 */
function isExcusedFailure(kind: ExecErrorKind): boolean {
  return kind === "auth" || kind === "rate";
}

/**
 * THE VERIFIER REFUSING A RUN, in the two forms an `Outcome` can carry it:
 * a shadow comparison that disagreed, and a verifier that looked at the effect
 * and did not find it.
 *
 * Defined once and read by BOTH the demotion trigger and the evidence
 * counters, because the defect this file was audited for was two neighbouring
 * gates holding two different opinions about what counts: the 2 -> 3 gate — the
 * one that unlocks writes — banked runs the 3 -> 4 gate refused, each with a
 * comment claiming it was strict. One predicate cannot disagree with itself.
 *
 * "unknown" is deliberately NOT in here. It is a no-verdict, and which way a
 * no-verdict falls depends on which way the check points (contract.ts LAW1):
 * as a FLOOR it licenses nothing, so it earns no counter; as a CEILING it
 * fences nothing, so it never demotes. Both halves are below.
 */
function isVerifierMismatch(o: LedgerOutcome): boolean {
  return o.parity === false || o.verifierResult === "unverified";
}

export class InMemoryLedger implements Ledger {
  #store: LedgerStore;
  #now: () => number;

  constructor(opts: { store?: LedgerStore; now?: () => number } = {}) {
    // Parameter properties are not erasable syntax, so this is assigned the
    // long way round: `node --experimental-strip-types` refuses the short one.
    this.#store = opts.store ?? memoryStore();
    this.#now = opts.now ?? (() => Date.now());
  }

  get store(): LedgerStore {
    return this.#store;
  }

  // -------------------------------------------------------------------------
  // Ledger interface
  // -------------------------------------------------------------------------

  /**
   * The owner's own rows for this pair — and, when they have none, the global
   * aggregate marked `user_id: "*"`.
   *
   * Returning an empty array for a capability that has worked two hundred times
   * for other people is how the second hand stays cold-start forever, which is
   * the whole reason a prior exists. The synthetic row's `rung` is the INHERITED
   * rung, already capped by this user's own connection and consent, so a router
   * that reads the rung straight off the prior can never act on somebody else's
   * permission.
   */
  async prior(userId: string, sigHash: string, app: string): Promise<CapabilityStats[]> {
    const mine = await this.#store.capability_stats.prefix(scanKey(userId, sigHash, app));
    if (mine.length > 0) return mine;

    const global = await this.globalStats(sigHash, app);
    if (global.n === 0) return [];
    return [
      {
        user_id: "*",
        signature_hash: sigHash,
        app,
        hand: "api",
        tool_slug: global.tool_slug,
        n: global.n,
        successes: global.successes,
        p50_ms: global.p50_ms,
        p95_ms: global.p95_ms,
        cost_usd_total: global.cost_usd_total,
        rung: await this.rung(userId, sigHash, app),
        last_fail_reason: "",
        last_run_at: global.last_run_at,
      },
    ];
  }

  /**
   * The rung the ROUTER should act on.
   *
   * It is the earned rung, capped at shadow while a demotion's shadow re-open
   * is outstanding. The contract gives the router exactly one number, so this
   * is the only channel through which "drops one rung AND re-opens shadow" can
   * reach it; a demotion that only moved a stored integer nobody reads would be
   * inert. `earnedRung` is the uncapped one, for anything that needs to know
   * what the pair had before it fell.
   */
  async rung(userId: string, sigHash: string, app: string): Promise<Rung> {
    const pair = await this.#pair(userId, sigHash, app);
    const earned = await this.#earnedRung(userId, sigHash, app, pair);
    return routableRung(earned, pair?.shadow_required === true);
  }

  /** The rung this pair has earned, ignoring an outstanding shadow re-open. */
  async earnedRung(userId: string, sigHash: string, app: string): Promise<Rung> {
    return this.#earnedRung(userId, sigHash, app, await this.#pair(userId, sigHash, app));
  }

  /**
   * A hand-set rung — an operator override, or a test. It clears the promotion
   * counters, because evidence gathered standing on one rung is not evidence
   * for the next one: three parity matches collected in shadow are not three
   * confirmed writes, and carrying them across an override would let a pair
   * skip a gate nobody ever ran. It also lifts an outstanding shadow re-open,
   * because an override that left the pair pinned to shadow would report a rung
   * the caller did not set and read as a bug in the ledger.
   */
  async setRung(userId: string, sigHash: string, app: string, rung: Rung): Promise<void> {
    const pair = await this.#ensurePair(userId, sigHash, app);
    pair.rung = clampRung(rung);
    // An override may only ever LOWER what this pair exports to strangers.
    // Raising it would let one number typed by an operator — or by a test —
    // become the starting rung of every other user who connected the app,
    // which is exactly what `globalRung` says "EARNED" rules out.
    pair.evidence_rung = clampRung(Math.min(pair.evidence_rung, pair.rung));
    pair.own_ladder_events += 1;
    pair.shadow_required = false;
    this.#resetCounters(pair);
    pair.last_change_at = this.#now();
    pair.last_change_reason = `rung set to ${pair.rung} by hand`;
    await this.#putPair(pair);
    await this.#projectRung(pair);
  }

  async candidates(userId: string, sigHash: string): Promise<ApiCandidate[]> {
    const rows = await this.#store.api_candidates.prefix(scanKey(userId, sigHash));
    // Ordering is the ONLY thing a vendor retrieval score is allowed to do
    // here (contract.ts LAW1). Nothing downstream may read row[0] as "the
    // right tool" — only a judge verdict of "yes" licenses the API hand.
    return rows.sort((a, b) => b.match_score - a.match_score);
  }

  async writesOptedIn(userId: string, app: string): Promise<boolean> {
    const consent = await this.#store.app_consent.get(rowKey(userId, app));
    return consent?.writes_opted_in === true;
  }

  /**
   * One outcome in; stats maintained, gates evaluated, at most one rung of
   * movement out.
   *
   * At most ONE rung either way, deliberately: climbing two on a single outcome
   * would skip a gate whose evidence was never collected, and falling two would
   * punish one bad afternoon twice.
   */
  async record(outcome: Outcome): Promise<void> {
    const o = outcome as LedgerOutcome;
    const at = typeof o.at === "number" ? o.at : this.#now();
    const kind = o.failKind ?? asErrorKind(o.failReason);

    await this.#updateStats(o, at, kind);

    const pair = await this.#ensurePair(o.user_id, o.signature_hash, o.app);
    const earned = await this.#earnedRung(o.user_id, o.signature_hash, o.app, pair);
    pair.rung = earned;

    // Classified against the rung the ROUTER was given, not the one the pair
    // has earned. They differ for exactly as long as a demotion's shadow
    // re-open is outstanding, and during that window every run is a supervised
    // shadow read however high the pair used to stand.
    const standingOn = routableRung(earned, pair.shadow_required);
    const isWrite = this.#isWriteRun(o, standingOn);
    const demoted = this.#applyDemotion(pair, o, kind, isWrite, at);
    if (!demoted) {
      this.#applyEvidence(pair, o, isWrite, standingOn, kind);
      // The rung-0 gate is checked here as well as on its own two writers,
      // because a pair can reach the two halves of it in either order. If it
      // fires, the counter gates are NOT also consulted on the same outcome.
      const left0 = await this.#climbFromZero(pair, at);
      if (!left0) this.#climb(pair, await this.writesOptedIn(o.user_id, o.app), at);
    }

    await this.#putPair(pair);
    await this.#projectRung(pair);
  }

  // -------------------------------------------------------------------------
  // Writers the contract has no room for. The router and the onboarding hand
  // call these; they are additions, not replacements.
  // -------------------------------------------------------------------------

  /**
   * A candidate the search turned up, with the judge's verdict on it.
   *
   * `connected: true` also marks the app connected for this user, because the
   * caller only knows that from the provider's own `connections()` reply. It is
   * a RATCHET — a candidate can assert a connection exists, never that one does
   * not — because two writers that can both clear the same flag is how a stale
   * search result revokes an account the owner connected a minute ago.
   */
  async noteCandidate(candidate: ApiCandidate): Promise<void> {
    const key = rowKey(candidate.user_id, candidate.signature_hash, candidate.tool_slug);
    const existing = await this.#store.api_candidates.get(key);
    await this.#store.api_candidates.put(key, {
      ...candidate,
      // first_seen_at is the FIRST sighting; re-searching the same tool every
      // run must not keep resetting the clock the nudge copy reads from.
      first_seen_at: existing?.first_seen_at ?? candidate.first_seen_at,
    });
    if (candidate.connected) await this.setConnection(candidate.user_id, candidate.app, true);

    // A vouched-for candidate on a connected app is the whole of the rung-0
    // gate, and it arrives here rather than through an outcome — a pair at rung
    // 0 has never run on the API hand, so waiting for `record()` to notice
    // would leave rung 0 permanently unreachable.
    const pair = await this.#ensurePair(
      candidate.user_id,
      candidate.signature_hash,
      candidate.app,
    );
    pair.rung = await this.#earnedRung(pair.user_id, pair.signature_hash, pair.app, pair);
    await this.#climbFromZero(pair, this.#now());
    await this.#putPair(pair);
    await this.#projectRung(pair);
  }

  async setConnection(userId: string, app: string, connected: boolean): Promise<void> {
    const consent = await this.#consent(userId, app);
    consent.connected = connected;
    await this.#store.app_consent.put(rowKey(userId, app), consent);
    await this.#reclimbApp(userId, app);
  }

  async connected(userId: string, app: string): Promise<boolean> {
    const consent = await this.#store.app_consent.get(rowKey(userId, app));
    return consent?.connected === true;
  }

  /**
   * The owner opting into writes for one app. Per (user, app) and stored
   * nowhere else: this is the field the global prior is forbidden to carry.
   */
  async setWritesOptIn(userId: string, app: string, optedIn: boolean): Promise<void> {
    const consent = await this.#consent(userId, app);
    consent.writes_opted_in = optedIn;
    consent.writes_opted_in_at = optedIn ? this.#now() : null;
    await this.#store.app_consent.put(rowKey(userId, app), consent);
    // The 2->3 gate can be completed by the opt-in itself, long after the
    // tenth clean read. Without this, a pair that already has the reads sits at
    // rung 2 until it happens to run once more.
    await this.#reclimbApp(userId, app);
  }

  /**
   * A shadow run, recorded as evidence and NOTHING ELSE.
   *
   * It deliberately does not touch the parity streak. The router records the
   * run and then records its outcome — the obvious thing to do — and if both
   * moved the streak the pair would promote after two shadow runs instead of
   * three. `record()` owns the ladder; every other writer in this class only
   * fills in a table.
   */
  async recordShadowRun(
    run: ShadowRun,
    pair?: { user_id: string; signature_hash: string; app: string },
  ): Promise<void> {
    await this.#store.shadow_runs.put(rowKey(run.run_id, run.step_id), {
      run,
      user_id: pair?.user_id ?? null,
      signature_hash: pair?.signature_hash ?? null,
      app: pair?.app ?? null,
      at: this.#now(),
    });
  }

  async shadowRuns(): Promise<ShadowRunRow[]> {
    return this.#store.shadow_runs.all();
  }

  /** connect_nudges, as storage. WHEN to nudge is onboarding's decision. */
  async noteNudge(
    userId: string,
    app: string,
    patch: Partial<Omit<ConnectNudge, "user_id" | "app">>,
  ): Promise<ConnectNudge> {
    const key = rowKey(userId, app);
    const existing = (await this.#store.connect_nudges.get(key)) ?? {
      user_id: userId,
      app,
      state: "queued" as NudgeState,
      sent_at: null,
      channel: null,
      tasks_that_would_have_used_it: 0,
      declined_at: null,
    };
    const row: ConnectNudge = { ...existing, ...patch, user_id: userId, app };
    await this.#store.connect_nudges.put(key, row);
    return row;
  }

  /**
   * One more task that would have used this app if it were connected. The
   * counter is the evidence the nudge copy is built from ("this would have
   * saved you four steps this week"), so it is incremented rather than set —
   * a setter would let a caller that reads-then-writes lose a concurrent bump.
   */
  async countMissedTask(userId: string, app: string): Promise<ConnectNudge> {
    const key = rowKey(userId, app);
    const existing = await this.#store.connect_nudges.get(key);
    return this.noteNudge(userId, app, {
      tasks_that_would_have_used_it: (existing?.tasks_that_would_have_used_it ?? 0) + 1,
    });
  }

  async nudge(userId: string, app: string): Promise<ConnectNudge | undefined> {
    return this.#store.connect_nudges.get(rowKey(userId, app));
  }

  async nudges(userId: string): Promise<ConnectNudge[]> {
    return this.#store.connect_nudges.prefix(scanKey(userId));
  }

  async stats(
    userId: string,
    sigHash: string,
    app: string,
    hand?: Hand,
    toolSlug?: string,
  ): Promise<CapabilityStats[]> {
    const rows = await this.#store.capability_stats.prefix(scanKey(userId, sigHash, app));
    return rows.filter(
      (r) => (hand === undefined || r.hand === hand) &&
        (toolSlug === undefined || r.tool_slug === toolSlug),
    );
  }

  async ladderState(
    userId: string,
    sigHash: string,
    app: string,
  ): Promise<LadderState | undefined> {
    return this.#pair(userId, sigHash, app);
  }

  // -------------------------------------------------------------------------
  // The global prior
  // -------------------------------------------------------------------------

  /** API-hand totals for this capability across every user. */
  async globalStats(
    sigHash: string,
    app: string,
  ): Promise<{
    n: number;
    successes: number;
    p50_ms: number;
    p95_ms: number;
    cost_usd_total: number;
    last_run_at: number;
    tool_slug: string;
    users: number;
    rung: Rung;
  }> {
    const rows = (await this.#store.capability_stats.all()).filter(
      (r) => r.signature_hash === sigHash && r.app === app && r.hand === "api",
    );
    const users = new Set(rows.map((r) => r.user_id));
    let n = 0;
    let successes = 0;
    let cost = 0;
    let lastRun = 0;
    let p50 = 0;
    let p95 = 0;
    let toolSlug = "";
    for (const row of rows) {
      n += row.n;
      successes += row.successes;
      cost = addCost(cost, row.cost_usd_total);
      // The newest row's percentiles stand in for the population's. A merged
      // percentile needs the merged sample, and the samples are per user; this
      // is a prior, not a measurement, and it is labelled as one in `prior()`.
      if (row.last_run_at >= lastRun) {
        lastRun = row.last_run_at;
        p50 = row.p50_ms;
        p95 = row.p95_ms;
        toolSlug = row.tool_slug;
      }
    }
    return {
      n,
      successes,
      p50_ms: p50,
      p95_ms: p95,
      cost_usd_total: cost,
      last_run_at: lastRun,
      tool_slug: toolSlug,
      users: users.size,
      rung: await this.globalRung(sigHash, app),
    };
  }

  /**
   * The highest rung anyone has EARNED for this capability.
   *
   * It reads `evidence_rung`, not `rung`, and the difference is the whole
   * point. `rung` is also where an inherited prior left a pair — user B
   * inherits 2 from A, C inherits from B, and a rung nobody ever earned becomes
   * everybody's default — and it is also where an operator override put one,
   * which is the absence of evidence rather than evidence. `evidence_rung`
   * rises in exactly one place: `#promote`, at a gate, by exactly one rung.
   *
   * "By exactly one" is load-bearing and not a detail of the arithmetic. While
   * `#promote` banked `max(evidence_rung, rung)` this method was still reading
   * the right column and still published the wrong number, because the given
   * rung was a floor under the earned one and one gate lifted the entire stack
   * beneath it into the export.
   */
  async globalRung(sigHash: string, app: string, excludeUser?: string): Promise<Rung> {
    const rows = await this.#store.ladder_state.all();
    let best = 0;
    for (const row of rows) {
      if (row.signature_hash !== sigHash || row.app !== app) continue;
      if (excludeUser !== undefined && row.user_id === excludeUser) continue;
      if (row.evidence_rung > best) best = row.evidence_rung;
    }
    return clampRung(best);
  }

  /**
   * What a user with no history of their own may start at.
   *
   * A rung is a claim about the TOOL and it travels. A connection and a write
   * opt-in are claims about the PERSON and they do not. So the global rung is
   * capped twice on the way in: to 0 without this user's own connection, to 2
   * without this user's own write opt-in, and to 3 — ASSISTED writes, every one
   * of them confirmed — even with it. Nobody is ever handed rung 4 by other
   * people's luck; auto-writes are earned on your own account or not at all.
   */
  async inheritedRung(userId: string, sigHash: string, app: string): Promise<Rung> {
    const global = await this.globalRung(sigHash, app, userId);
    if (global === 0) return 0;
    if (!(await this.connected(userId, app))) return 0;
    const cap = (await this.writesOptedIn(userId, app))
      ? LADDER.MAX_INHERITED_RUNG_WITH_WRITE_CONSENT
      : LADDER.MAX_INHERITED_RUNG_WITHOUT_WRITE_CONSENT;
    return clampRung(Math.min(global, cap));
  }

  // -------------------------------------------------------------------------
  // internals
  // -------------------------------------------------------------------------

  async #pair(userId: string, sigHash: string, app: string): Promise<LadderState | undefined> {
    return this.#store.ladder_state.get(rowKey(userId, sigHash, app));
  }

  async #ensurePair(userId: string, sigHash: string, app: string): Promise<LadderState> {
    const existing = await this.#pair(userId, sigHash, app);
    if (existing) return existing;
    const fresh: LadderState = {
      user_id: userId,
      signature_hash: sigHash,
      app,
      rung: await this.inheritedRung(userId, sigHash, app),
      // An inherited rung is somebody else's evidence. This pair has none of
      // its own until it passes a gate, which is what stops a prior being
      // re-exported as if it were a measurement.
      evidence_rung: 0,
      own_ladder_events: 0,
      parity_streak: 0,
      parity_mismatches: 0,
      clean_reads: 0,
      confirmed_writes: 0,
      consecutive_api_failures: 0,
      shadow_required: false,
      last_change_at: this.#now(),
      last_change_reason: "opened",
    };
    await this.#putPair(fresh);
    return fresh;
  }

  async #putPair(pair: LadderState): Promise<void> {
    await this.#store.ladder_state.put(
      rowKey(pair.user_id, pair.signature_hash, pair.app),
      pair,
    );
  }

  /**
   * The stored rung once this pair has moved on its own evidence; the inherited
   * prior until then, recomputed every time rather than frozen at first touch.
   *
   * Recomputed because inheritance depends on the user's connection and opt-in,
   * which arrive later than the first browser run. Frozen at first touch, a
   * pair that recorded one browser outcome before the owner connected the app
   * would sit at rung 0 forever and never inherit anything.
   */
  async #earnedRung(
    userId: string,
    sigHash: string,
    app: string,
    pair: LadderState | undefined,
  ): Promise<Rung> {
    if (pair && pair.own_ladder_events > 0) return clampRung(pair.rung);
    return this.inheritedRung(userId, sigHash, app);
  }

  async #consent(userId: string, app: string): Promise<AppConsent> {
    return (
      (await this.#store.app_consent.get(rowKey(userId, app))) ?? {
        user_id: userId,
        app,
        connected: false,
        writes_opted_in: false,
        writes_opted_in_at: null,
      }
    );
  }

  async #updateStats(o: LedgerOutcome, at: number, kind: ExecErrorKind): Promise<void> {
    const key = rowKey(o.user_id, o.signature_hash, o.app, o.hand, o.tool_slug);
    const row: CapabilityStats = (await this.#store.capability_stats.get(key)) ?? {
      user_id: o.user_id,
      signature_hash: o.signature_hash,
      app: o.app,
      hand: o.hand,
      tool_slug: o.tool_slug,
      n: 0,
      successes: 0,
      p50_ms: 0,
      p95_ms: 0,
      cost_usd_total: 0,
      rung: 0,
      last_fail_reason: "",
      last_run_at: 0,
    };
    row.n += 1;
    if (o.ok) row.successes += 1;
    row.cost_usd_total = addCost(row.cost_usd_total, o.cost);
    row.last_run_at = at;
    if (!o.ok) {
      // Kept even when the run was excused, because this is the field the
      // connect-nudge reads to tell the owner WHY it wants a reconnection.
      // Never cleared by a later success: clearing it would erase the only
      // record of why the owner was nudged, three green runs after the nudge
      // worked, and the nudge copy would have nothing to point at.
      row.last_fail_reason = o.failReason ?? kind;
    }

    // An unmeasured run contributes no latency sample. See `unmeasured` on
    // LedgerOutcome: its 0 is a lost measurement, and averaging it in would
    // make a hand look fast on evidence nobody collected. Everything else about
    // the run still counts — it happened.
    if (!o.unmeasured) {
      const sampleRow = (await this.#store.latency_samples.get(key)) ?? { key, ms: [] };
      sampleRow.ms.push(Number.isFinite(o.ms) ? o.ms : 0);
      await this.#store.latency_samples.put(key, sampleRow);
      row.p50_ms = percentile(sampleRow.ms, 50);
      row.p95_ms = percentile(sampleRow.ms, 95);
    }

    await this.#store.capability_stats.put(key, row);
  }

  /**
   * Which half of the ladder this run belongs to.
   *
   * The contract's Outcome cannot say, so when the caller does not declare it
   * the rung the pair was standing on decides: rungs 0-2 are the read half,
   * rungs 3-4 are the write half. Without a fallback, "10 clean reads" and "3
   * confirmed writes" would be the same counter and a pair would climb from
   * rung 2 to rung 4 on reads alone.
   */
  #isWriteRun(o: LedgerOutcome, standingOn: Rung): boolean {
    if (o.side_effect !== undefined) return o.side_effect !== "read";
    return standingOn >= 3;
  }

  #resetCounters(pair: LadderState): void {
    pair.parity_streak = 0;
    pair.clean_reads = 0;
    pair.confirmed_writes = 0;
    pair.consecutive_api_failures = 0;
  }

  /**
   * The two automatic demotions, and everything that deliberately is not one.
   *
   * Only the API hand can demote the API hand: a browser step that failed says
   * nothing about the tool, and demoting for it means a flaky website takes the
   * API hand away from a capability that was working.
   */
  #applyDemotion(
    pair: LadderState,
    o: LedgerOutcome,
    kind: ExecErrorKind,
    isWrite: boolean,
    at: number,
  ): boolean {
    if (o.hand !== "api") return false;

    // One verifier mismatch on a write is enough. A write that did not do what
    // it said is not a flaky read; there is no second chance to give it.
    // "unknown" is NOT a mismatch — the verifier could not look. Demoting on a
    // no-verdict punishes a capability for the verifier being down, which is
    // how a fence turns into a wall.
    const mismatch = isVerifierMismatch(o);
    if (isWrite && mismatch) {
      this.#demote(pair, at, "verifier mismatch on a write");
      return true;
    }

    if (o.ok) {
      // A 200 whose effect the verifier says did not happen is the tool
      // ANSWERING WRONGLY, not the tool working, so it may not hand the pair a
      // clean slate between two genuine failures — that is the same laundering
      // the excused-401 rule below refuses, arriving from the other side. It is
      // not a transport failure either, so it does not add to the count:
      // invisible, exactly like an excused 401.
      if (!mismatch) pair.consecutive_api_failures = 0;
      return false;
    }

    if (isExcusedFailure(kind)) return false;

    pair.consecutive_api_failures += 1;
    if (pair.consecutive_api_failures >= LADDER.CONSECUTIVE_API_FAILURES_TO_DEMOTE) {
      this.#demote(pair, at, `${pair.consecutive_api_failures} consecutive API failures`);
      return true;
    }
    return false;
  }

  #demote(pair: LadderState, at: number, reason: string): void {
    const from = pair.rung;
    pair.rung = clampRung(from - 1);
    // A pair cannot go on telling strangers it reached a rung it just fell off.
    pair.evidence_rung = clampRung(Math.min(pair.evidence_rung, pair.rung));
    // The second half of a demotion, and the half that does the work: the pair
    // routes as shadow until parity is proved again, whatever rung it kept.
    pair.shadow_required = true;
    this.#resetCounters(pair);
    pair.own_ladder_events += 1;
    pair.last_change_at = at;
    pair.last_change_reason = `demoted ${from} -> ${pair.rung}: ${reason}`;
  }

  /** Counters only. Nothing here moves a rung. */
  #applyEvidence(
    pair: LadderState,
    o: LedgerOutcome,
    isWrite: boolean,
    standingOn: Rung,
    kind: ExecErrorKind,
  ): void {
    if (o.hand !== "api") return;

    // Parity is a property of a shadow PAIR, and the API-side outcome is the
    // one that carries it. If the browser-side outcome counted too, three
    // matches would arrive after a run and a half.
    const refused = isVerifierMismatch(o);
    if (refused) {
      pair.parity_streak = 0;
      // The cumulative counter is about the parity COMPARISON specifically, so
      // only a comparison that disagreed moves it; the streak above is emptied
      // by either shape of refusal.
      if (o.parity === false) pair.parity_mismatches += 1;
    } else if (o.parity === true && o.ok && o.verifierResult === "verified") {
      // A parity claim beside "unknown" is a caller asserting a comparison
      // NOBODY PERFORMED — contract.ts defines parity as agreement with the
      // verifier's ground truth, never as the two hands matching each other. If
      // that counted, three shadow runs taken while the verifier was down would
      // buy the API read hand and switch off the browser supervision rung 1
      // exists to provide.
      pair.parity_streak += 1;
    } else if (!o.ok && !isExcusedFailure(kind)) {
      // "Three CONSECUTIVE parity matches" is a claim about a WINDOW OF RUNS,
      // and a broken API call inside the window ends it. Stepping over one
      // promotes a pair that errors one shadow run in three to reading the
      // owner's mail unsupervised. An excused 401 stays invisible here for the
      // same reason it is invisible to the demotion counter: a refresh token
      // ageing out is not the tool being wrong.
      pair.parity_streak = 0;
    }

    // ONE definition of evidence, read by both counters below.
    //
    // THE DEFECT THIS REPLACES: this predicate used to accept "unknown", so the
    // 2 -> 3 gate — the one that UNLOCKS WRITES — banked ten reads nobody had
    // checked, while the 3 -> 4 gate right underneath it refused the identical
    // evidence and said in its own comment why. The strict gate guarded the
    // smaller privilege. An unverified read is not a read that worked; it is a
    // read nobody looked at, and a FLOOR needs something to license it rather
    // than merely the absence of an objection (contract.ts LAW1).
    const verified = o.ok && !refused && o.verifierResult === "verified";

    // Reads gathered while the pair is actually using the API for reads. Shadow
    // reads at rung 1 ran under the browser's supervision and were already
    // spent on the rung-1 gate; counting them twice would buy the write gate
    // with evidence that was never about writing.
    if (verified && !isWrite && standingOn >= 2) pair.clean_reads += 1;

    // "Confirmed" is the owner's confirmation (assisted writes at rung 3) and
    // "verified effect" is the verifier's. Only "verified" counts: "unknown"
    // means nobody looked, and three writes nobody looked at are not evidence.
    if (verified && isWrite && standingOn >= 3) pair.confirmed_writes += 1;
  }

  /** Exactly one rung, if the gate for the rung it is on is satisfied. */
  #climb(pair: LadderState, writesOptedIn: boolean, at: number): void {
    // Shadow was re-opened by a demotion and is closed by the evidence that
    // re-earns the ground: three parity matches, the same price as rung 1.
    if (pair.shadow_required && pair.parity_streak >= LADDER.PARITY_MATCHES_FOR_API_READS) {
      pair.shadow_required = false;
      pair.parity_streak = 0;
      pair.own_ladder_events += 1;
      pair.last_change_at = at;
      pair.last_change_reason = "shadow re-proved after a demotion";
      return;
    }
    if (pair.shadow_required) return;

    switch (pair.rung) {
      case 0:
        // The gate is a STATE, not a counter: a candidate the judge vouched for
        // and an app the owner connected. Handled in #climbFromZero because it
        // needs a table read.
        return;
      case 1:
        // Three CONSECUTIVE matches. The cumulative mismatch count is recorded
        // and deliberately not gated on: one flaky afternoon would otherwise
        // lock a capability out of the API hand permanently. The streak IS the
        // window — a mismatch empties it — so "0 mismatches" holds over the
        // three runs that count.
        if (pair.parity_streak >= LADDER.PARITY_MATCHES_FOR_API_READS) {
          pair.parity_streak = 0;
          this.#promote(pair, at, "3 consecutive parity matches in shadow");
        }
        return;
      case 2:
        // Both halves, and the opt-in is the half that cannot be inherited,
        // bought, or inferred from usage.
        if (writesOptedIn && pair.clean_reads >= LADDER.CLEAN_READS_FOR_ASSISTED_WRITES) {
          pair.clean_reads = 0;
          this.#promote(pair, at, "owner opted into writes and 10 clean API reads");
        }
        return;
      case 3:
        if (pair.confirmed_writes >= LADDER.CONFIRMED_WRITES_FOR_AUTO_WRITES) {
          pair.confirmed_writes = 0;
          this.#promote(pair, at, "3 confirmed writes with a verified effect");
        }
        return;
      default:
        return;
    }
  }

  #promote(pair: LadderState, at: number, reason: string): void {
    const from = pair.rung;
    pair.rung = clampRung(from + 1);
    // The ONLY place this rises, and it rises by ONE — never up to `pair.rung`.
    //
    // THE DEFECT THIS REPLACES: this line read
    // `max(pair.evidence_rung, pair.rung)`, which made the pair's CURRENT rung
    // a FLOOR under its earned one — and the current rung is exactly where
    // `setRung` and `#ensurePair`'s inherited prior put a number. So an
    // operator standing a write pair up at rung 3 to get past the write-ladder
    // gap (RESULTS.md FINDING 1) was kept out of `globalRung` only until that
    // pair passed ONE more gate, at which point the three rungs underneath it —
    // which nobody had ever paid for — were exported to every stranger who had
    // connected the app. The inherited case is worse because it compounds: B
    // inherits 2 from A, passes one gate, exports 3, and C inherits 3 from a
    // pair that ran ten reads.
    //
    // One gate passed is one rung of credit. Anything below it belonged to
    // somebody else or to nobody, and `setRung`'s "an override may only ever
    // LOWER what this pair exports" is only true if this line agrees with it.
    //
    // On a pair that walked the ladder from 0 this is the SAME number it always
    // was: evidence_rung tracks `from`, so evidence_rung + 1 is the new rung.
    // The `min` cap holds the invariant `evidence_rung <= rung` that `#demote`
    // and `setRung` also maintain, so a pair can never export a rung it is not
    // standing on.
    pair.evidence_rung = clampRung(Math.min(pair.evidence_rung + 1, pair.rung));
    pair.own_ladder_events += 1;
    pair.last_change_at = at;
    pair.last_change_reason = `promoted ${from} -> ${pair.rung}: ${reason}`;
  }

  /**
   * rung 0 -> 1: a candidate the judge vouched for, on an app the owner
   * connected.
   *
   * It is separate from #climb because its evidence lives in a table and #climb
   * is synchronous bookkeeping. Every writer that can complete either half —
   * a new candidate, a new connection, an outcome — calls it, because the two
   * halves arrive in either order and whichever lands second has to be the one
   * that notices.
   */
  async #climbFromZero(pair: LadderState, at: number): Promise<boolean> {
    if (pair.rung !== 0) return false;
    if (!(await this.connected(pair.user_id, pair.app))) return false;
    const rows = await this.#store.api_candidates.prefix(
      scanKey(pair.user_id, pair.signature_hash),
    );
    // `judgeLicensesApi` is imported rather than reimplemented so there is
    // exactly ONE definition of "the judge vouched for it" in the spike. A
    // second copy here would be the place `unclear` quietly starts counting.
    const vouched = rows.some(
      (row) => row.app === pair.app && judgeLicensesApi({ verdict: row.match_verdict, reason: "" }),
    );
    if (!vouched) return false;
    // A pair that fell all the way to browser-only is NOT trapped there. Rung 1
    // is shadow, so promoting into it is what "re-open shadow" means; refusing
    // while the flag is set was a deadlock, because the only thing that clears
    // the flag is an API parity match and rung 0 never calls the API. The
    // demotion still bites — it emptied the parity streak, so the pair pays the
    // full three matches again before it touches the API hand for real.
    pair.shadow_required = false;
    this.#promote(pair, at, "a candidate the judge vouched for, on a connected app");
    return true;
  }

  /** Re-run the gates for every pair of one app after a consent change. */
  async #reclimbApp(userId: string, app: string): Promise<void> {
    const rows = await this.#store.ladder_state.prefix(scanKey(userId));
    const optedIn = await this.writesOptedIn(userId, app);
    for (const row of rows) {
      if (row.app !== app) continue;
      row.rung = await this.#earnedRung(row.user_id, row.signature_hash, row.app, row);
      const left0 = await this.#climbFromZero(row, this.#now());
      if (!left0) this.#climb(row, optedIn, this.#now());
      await this.#putPair(row);
      await this.#projectRung(row);
    }
  }

  /**
   * Copy the routable rung onto every capability_stats row for the pair.
   *
   * The ladder is keyed by (user, signature_hash, app) — a pair climbs as a
   * pair — while capability_stats is keyed per hand and tool. Two rows for one
   * pair disagreeing about the rung is a bug a reader would resolve by picking
   * whichever row they read first. The column carries the same number
   * `Ledger.rung()` returns, so the table and the method can never tell a
   * router two different stories; `ladder_state` keeps the earned rung.
   * On D1 this is one `UPDATE ... WHERE user_id=? AND signature_hash=? AND
   * app=?`, not a loop.
   */
  async #projectRung(pair: LadderState): Promise<void> {
    const routable = routableRung(pair.rung, pair.shadow_required);
    const prefix = scanKey(pair.user_id, pair.signature_hash, pair.app);
    const rows = await this.#store.capability_stats.prefix(prefix);
    for (const row of rows) {
      if (row.rung === routable) continue;
      row.rung = routable;
      await this.#store.capability_stats.put(
        rowKey(row.user_id, row.signature_hash, row.app, row.hand, row.tool_slug),
        row,
      );
    }
  }
}
