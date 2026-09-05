// THE ROUTER — which hand takes this step, and why.
//
// Two hands: the browser (drive the owner's own signed-in browser) and the API
// (call the vendor's endpoint with a token the owner connected). This file
// decides, for ONE step, which one runs. It is the only place in the spike
// where that is decided, so it is the only place the decision can go wrong.
//
// THE POLARITY, WHICH IS THE WHOLE DESIGN.
//
// The browser hand is the DEFAULT and the API hand is the PRIVILEGE. Every
// branch below is written so that a missing answer lands on the browser: no
// candidate, no judge verdict, an unreachable judge, an unreachable vendor, an
// unreachable ledger, a connection that expired. HARNESS-LAWS law 1 calls that
// a FLOOR — "does anything AUTHORIZE this?" must refuse when nobody answered,
// or it lifts itself. The concrete failure being prevented is an API call the
// owner never licensed firing against his real account, which is the one
// mistake here that cannot be undone by trying again.
//
// THIS FILE MAY NEVER NAME AN APP.
//
// Not in a condition, not in a constant, not in a comment. `router.test.ts`
// reads this source back and fails if a known app name appears in it. That leg
// exists because the failure mode is invisible to behaviour tests: the day a
// routing outcome depends on the literal string of some vendor's name, every
// test still passes and the no-hardcoding claim is quietly dead. The router
// sees a signature, a candidate's opaque slug, a rung and a row of counts.
//
// WHAT THE NUMBERS BELOW ARE AND ARE NOT.
//
// There are constants in this file — a candidate cap, a latency weight, three
// rung boundaries. None of them reads a human's words. They order two hands by
// their own MEASURED outcomes and they bound how much a task may spend before
// it answers. Law 1 forbids a threshold deciding what a sentence MEANS; the one
// question of meaning here — "does this tool do this step?" — is asked of a
// model, once per candidate, and only its verdict of exactly "yes" can put a
// step on the API hand.

import { judgeLicensesApi, SIDE_EFFECT_ORDER, tightenSideEffect } from "./contract.ts";
import { verifySignatureHash } from "./signature.ts";
import type {
  CapabilitySignature,
  CapabilityStats,
  ConnectedApp,
  Decision,
  ExecErrorKind,
  Ledger,
  MatchJudge,
  Provider,
  Router,
  Rung,
  SideEffect,
  ToolCandidate,
  UserCtx,
} from "./contract.ts";

// ---------------------------------------------------------------------------
// The decision this router actually returns.
// ---------------------------------------------------------------------------
// `Decision` in contract.ts is fixed and must not be edited, so the three
// things the five rules produce that it has no room for are added here by
// extension. A caller that only knows `Decision` still reads this correctly;
// a caller that knows this type gets the extra facts it needs to act.
export interface RouteDecision extends Decision {
  /** Rule 2. The judge vouched for a tool in an app the owner has not
   *  connected (or whose token has died). Onboarding owns the nudge itself —
   *  this only surfaces that there is one worth sending, and for which app.
   *  Without it the owner is silently routed to the slow hand forever and
   *  never told that one tap would fix it. */
  nudgeApp?: string;
  /** Rule 5's other half. The browser hand needs the owner's browser to be
   *  reachable; when it is not, the step is not refused, it is parked. A
   *  caller that treats this as an ordinary browser decision will dispatch
   *  into a machine that is asleep and report a failure the owner did not
   *  cause. */
  queued?: boolean;
  /** Rule 4. An irreversible step confirms with the owner REGARDLESS of rung,
   *  hand, or how good the numbers look. A rung is evidence that a step tends
   *  to work; it is not consent to do something that cannot be taken back. */
  requiresConfirmation?: boolean;
}

// ---------------------------------------------------------------------------
// Constants. Every one of them is a budget or a measurement weight.
// ---------------------------------------------------------------------------

/** How many candidates the judge is asked about. This is a BUDGET, not a
 *  threshold on meaning: each ask is a model call inside a task the owner is
 *  waiting on, and asking about forty retrieval hits would cost him a minute
 *  to answer a question the first few almost always settle. Nothing about the
 *  sixth candidate makes it wrong — it is only unasked, and it is unasked
 *  because the vendor's score ranked it sixth, which is the one thing a
 *  retrieval score is good for. */
const CANDIDATE_LIMIT = 5;

/** Rule 3's ladder. Rung 1 runs BOTH hands so the verifier can compare them;
 *  from rung 2 the API hand runs alone. Below rung 1 the pair has no evidence
 *  at all and the browser keeps the step. */
const SHADOW_RUNG = 1;
const API_ALONE_MIN_RUNG = 2;

/** Rule 4. A step that changes the world needs more evidence than one that
 *  reads it, and evidence alone is still not enough — the owner must also have
 *  said yes to writes for this app. Both, or the browser takes it. */
const WRITE_MIN_RUNG = 3;

/** Rule 5's latency term: score_h = LB95 - 0.15*log2(1 + p50/5000ms) - w*cost.
 *  Log-shaped on purpose. A hand that answers in 200ms and one that answers in
 *  400ms are the same hand to a person waiting; 3 seconds versus 30 is not. A
 *  straight-line penalty would let a millisecond of jitter outrank a real
 *  difference in whether the step works. */
const LATENCY_WEIGHT = 0.15;
const LATENCY_REFERENCE_MS = 5000;

/** Cost is dollars PER RUN, so at weight 1 a cent of spend cancels one point of
 *  success rate. It is a dial the owner turns when a vendor's pricing changes,
 *  and no branch in this file reads it except the comparison in rule 5. */
export const DEFAULT_COST_WEIGHT = 1;

/** Two-sided 95% normal quantile. Named rather than inlined because the test
 *  that pins Wilson against published values has to use the same one — a
 *  one-sided 1.6449 here and a two-sided 1.96 in the test would make the test
 *  agree with itself and with nothing else. */
const Z_95 = 1.959963984540054;

// ---------------------------------------------------------------------------
// Rule 5, part 1: the Wilson lower bound.
// ---------------------------------------------------------------------------
/**
 * LB95 of a success rate: the low end of the 95% Wilson interval.
 *
 * The naive alternative — successes/n — is what makes a hand with two lucky
 * runs beat a hand with forty steady ones (2/2 = 1.00 versus 38/40 = 0.95),
 * and the router would then promote a hand it has almost no evidence about and
 * demote the one it does. Wilson charges for ignorance: 2/2 scores 0.34,
 * 38/40 scores 0.83. It also behaves at the edges where the normal
 * approximation does not — p = 0 and p = 1 give finite, sane bounds instead of
 * a zero-width interval.
 *
 * n = 0 returns 0 rather than NaN. A hand nobody has ever run is not evidence
 * of anything, and a NaN here would poison every comparison downstream and
 * silently pick whichever branch `>` happens to take with a NaN operand.
 */
export function wilsonLowerBound(successes: number, n: number, z: number = Z_95): number {
  if (!Number.isFinite(n) || n <= 0) return 0;
  const runs = Math.floor(n);
  const wins = Math.min(Math.max(Number.isFinite(successes) ? successes : 0, 0), runs);
  const p = wins / runs;
  const z2 = z * z;
  const centre = p + z2 / (2 * runs);
  const margin = z * Math.sqrt((p * (1 - p)) / runs + z2 / (4 * runs * runs));
  const lb = (centre - margin) / (1 + z2 / runs);
  // Clamped because the algebra can produce -1e-17 at p = 0, and a negative
  // "success rate" in the audit line reads as a bug to whoever is on call.
  return lb < 0 ? 0 : lb > 1 ? 1 : lb;
}

// ---------------------------------------------------------------------------
// Rule 5, part 2: one hand's score.
// ---------------------------------------------------------------------------
/**
 * score_h = LB95(success_h) - 0.15*log2(1 + p50_h/5000ms) - cost_weight*cost_h
 *
 * `cost_h` is dollars per run, derived from the ledger's running total, because
 * a hand that has run 200 times legitimately has a bigger total than one that
 * ran twice and comparing totals would punish the hand that did the work.
 *
 * A hand with no rows scores 0, which is deliberately NOT -Infinity: rule 5 is
 * a demotion mechanism, and an unrun hand should lose to a hand with a record
 * without being permanently unreachable.
 */
export function handScore(
  stats: CapabilityStats | null | undefined,
  costWeight: number = DEFAULT_COST_WEIGHT,
): number {
  const n = stats && Number.isFinite(stats.n) ? Math.max(0, stats.n) : 0;
  if (n <= 0) return 0;
  const lb = wilsonLowerBound(stats!.successes, n);
  const p50 = Math.max(0, Number.isFinite(stats!.p50_ms) ? stats!.p50_ms : 0);
  const latency = LATENCY_WEIGHT * Math.log2(1 + p50 / LATENCY_REFERENCE_MS);
  const total = Math.max(0, Number.isFinite(stats!.cost_usd_total) ? stats!.cost_usd_total : 0);
  return lb - latency - costWeight * (total / n);
}

// ---------------------------------------------------------------------------
// Ledger rows -> one row per hand.
// ---------------------------------------------------------------------------
// `prior()` can return several rows for one hand (one per tool slug the pair
// has tried). Summing counts is right; averaging p50s is an approximation and
// is labelled as one below, because a mean of percentiles is not a percentile.
// It is used ONLY to order two hands against each other; the ledger's own p50
// stays the number anyone reports.
function foldRows(rows: CapabilityStats[]): CapabilityStats | null {
  if (rows.length === 0) return null;
  if (rows.length === 1) return rows[0];
  const n = rows.reduce((a, r) => a + Math.max(0, r.n || 0), 0);
  const weighted = rows.reduce((a, r) => a + Math.max(0, r.p50_ms || 0) * Math.max(0, r.n || 0), 0);
  return {
    ...rows[0],
    n,
    successes: rows.reduce((a, r) => a + Math.max(0, r.successes || 0), 0),
    cost_usd_total: rows.reduce((a, r) => a + Math.max(0, r.cost_usd_total || 0), 0),
    p50_ms: n > 0 ? weighted / n : 0,
  };
}

// The API row for the EXACT tool we matched is the honest one — a different
// slug in the same app is a different endpoint with its own failure rate. Rows
// for other slugs are folded in only when the matched slug has no history of
// its own, so a brand-new tool in a well-worn app starts from what is known
// about that app rather than from nothing.
function apiRowFor(rows: CapabilityStats[], toolSlug: string): CapabilityStats | null {
  const api = rows.filter((r) => r.hand === "api");
  const exact = api.filter((r) => r.tool_slug === toolSlug);
  return foldRows(exact.length > 0 ? exact : api);
}

function browserRowFrom(rows: CapabilityStats[]): CapabilityStats | null {
  return foldRows(rows.filter((r) => r.hand === "browser"));
}

// ---------------------------------------------------------------------------
// The audit sentence.
// ---------------------------------------------------------------------------
// "API, connected, rung 2, LB95 0.94 over 27 runs." Written for a person
// reading a log at 2am. NOTHING in this file or downstream may branch on it —
// that is why every fact it carries (hand, rung, score, nudgeApp, queued,
// requiresConfirmation) is also a structured field on the decision.
function runsLabel(stats: CapabilityStats | null): string {
  const n = stats?.n ?? 0;
  if (n <= 0) return "no runs yet";
  return `LB95 ${wilsonLowerBound(stats!.successes, n).toFixed(2)} over ${n} run${n === 1 ? "" : "s"}`;
}

// ---------------------------------------------------------------------------
// Rule 1: search, then ask.
// ---------------------------------------------------------------------------
/**
 * Connected apps first, then the whole catalog, deduped by slug, capped.
 *
 * Two searches rather than one, because the vendor's broad search ranks by
 * text similarity across its entire catalog and can bury the tool in the app
 * the owner has ALREADY connected below four he has never heard of. The
 * connected-only pass gives that tool its own shot at the list.
 *
 * The ordering handed to the judge is: connected candidates by score, then the
 * rest by score. Sorting the merged list purely by score would let a
 * higher-scored tool in an unconnected app win the first "yes" and turn a step
 * that could have run right now into a connect nudge and a browser run. The
 * score still does all the ordering — it just does it inside each group, which
 * is what "connected apps first, then the whole catalog" asks for.
 *
 * A vendor that throws returns an empty list, not an exception: the vendor
 * being down is not a reason to fail the owner's task, it is a reason to use
 * the hand that does not need the vendor.
 */
async function gatherCandidates(
  provider: Provider,
  sig: CapabilitySignature,
  userId: string,
  connectedApps: Set<string>,
  limit: number,
): Promise<ToolCandidate[]> {
  const search = async (connectedOnly: boolean): Promise<ToolCandidate[]> => {
    try {
      const found = await provider.search(sig, userId, { connectedOnly, limit });
      return Array.isArray(found) ? found : [];
    } catch {
      return [];
    }
  };
  const [connectedFirst, wholeCatalog] = await Promise.all([search(true), search(false)]);

  const seen = new Set<string>();
  const deduped: ToolCandidate[] = [];
  for (const c of [...connectedFirst, ...wholeCatalog]) {
    // A candidate with no slug or no app is dropped rather than carried. It
    // cannot be executed, it cannot be found in the connection list, and rule
    // 2 would surface a connect nudge for an app with no name — which reaches
    // the owner as a text asking him to connect "undefined".
    if (!c || typeof c.toolSlug !== "string" || typeof c.app !== "string") continue;
    if (seen.has(c.toolSlug)) continue;
    seen.add(c.toolSlug);
    deduped.push(c);
  }

  const byScore = (a: ToolCandidate, b: ToolCandidate) => (b.score ?? 0) - (a.score ?? 0);
  // Connectedness is taken from `connections()`, never from which search
  // returned the row: the connected-only flag is the vendor's claim about its
  // own index, and a stale index would sort a dead connection to the front.
  const connected = deduped.filter((c) => connectedApps.has(c.app)).sort(byScore);
  const rest = deduped.filter((c) => !connectedApps.has(c.app)).sort(byScore);
  return [...connected, ...rest].slice(0, limit);
}

/** Severity of a declared effect, in the contract's own ordering. An effect
 *  nobody recognises is read as the most severe one there is, so a garbled
 *  value cannot make a step look gentle. */
function severityOf(effect: SideEffect): number {
  return SIDE_EFFECT_ORDER[effect] ?? SIDE_EFFECT_ORDER.irreversible;
}

/**
 * The GENTLEST candidate the judge licensed — not the first one it licensed.
 *
 * `unclear`, `no-verdict`, and a judge that throws are all NOT a licence —
 * `judgeLicensesApi` is the only reader of the verdict, so this cannot drift.
 * A verdict of "yes" is a licence and a licence is not improved by collecting
 * more of them; what a second licence changes is not WHETHER the API hand may
 * run, but WHICH tool it runs.
 *
 * WHY THIS IS NOT "THE FIRST YES", WHICH IS WHAT IT USED TO BE.
 *
 * Candidates arrive in the vendor's score order. Returning on the first "yes"
 * therefore let the retrieval score decide which tool executes whenever more
 * than one would have been licensed — and a lower-scored candidate declaring a
 * gentler effect on the world was never even shown to the judge. contract.ts's
 * LAW1 note allows that score to ORDER and forbids it to DECIDE, and "which of
 * two licensed tools touches the owner's account" is a decision. The concrete
 * failure: a step planned as a write retrieves a tool that declares itself
 * irreversible above a tool that declares a plain write, the judge licenses
 * both, and a similarity number sends the one that cannot be undone.
 *
 * So the tie-break among licensed candidates is the SEATBELT, not the score:
 * the gentlest declared effect after `tightenSideEffect` wins. HARNESS-LAWS
 * law 1 names effect-channel checks as legitimate structure — this asks what a
 * tool TOUCHES, never how a sentence was worded — and the ordering is
 * `SIDE_EFFECT_ORDER` from the contract rather than a second one invented here.
 * Preferring the gentler tool is also the recoverable direction: if the judge
 * was too generous, running the gentler tool under-does the step and the
 * verifier catches it, while running the harsher one cannot be taken back.
 *
 * WHAT THIS STILL DOES NOT DO, WRITTEN DOWN SO NOBODY DISCOVERS IT LATER.
 * Two licensed candidates that declare the SAME effect are still ordered by
 * the vendor's score. The seatbelt sees no difference between them, a model
 * with the signature in front of it licensed both, and choosing among
 * equally-licensed, equally-consequential candidates is the one job a
 * retrieval score is fit for. The pair this spike is most afraid of — archive
 * against permanent destruction — is exactly that shape, because the
 * destructive tool declares itself an ordinary write; what saves it is the
 * judge's verdict, which is the design and not an accident.
 *
 * WHY THE LOOP MAY STILL STOP EARLY. `tightenSideEffect` only ever ratchets
 * UP, so no candidate can be gentler than the step as planned. The moment a
 * licence lands on that floor, nothing later can beat it, and asking on would
 * spend another model call inside a task the owner is waiting on to answer a
 * question whose answer cannot change. The extra asks are paid only while the
 * licence in hand is MORE dangerous than the step was planned to be — the one
 * time looking further is worth his seconds.
 *
 * A THROW stops the loop and keeps whatever licence is already in hand. The
 * judge being unreachable is a property of the judge, not of candidate #1;
 * asking about the other four would cost four more timeouts and land on the
 * same floor. A verdict already given is not withdrawn by a later timeout —
 * an unreachable judge must not be able to revoke a "yes" it has said.
 */
async function gentlestJudgedMatch(
  judge: MatchJudge,
  sig: CapabilitySignature,
  candidates: ToolCandidate[],
): Promise<ToolCandidate | null> {
  const floor = severityOf(sig.side_effect);
  let best: ToolCandidate | null = null;
  let bestSeverity = Number.POSITIVE_INFINITY;

  for (const candidate of candidates) {
    let answer;
    try {
      answer = await judge.matches(sig, candidate);
    } catch {
      // Stop asking, keep what is already licensed. Four more timeouts inside
      // a task the owner is watching buy the same floor, and a judge that has
      // gone down cannot revoke a "yes" it has already said.
      break;
    }
    if (!judgeLicensesApi(answer)) continue;
    const severity = severityOf(tightenSideEffect(sig.side_effect, candidate.sideEffectHint));
    // STRICTLY less, so a tie keeps the earlier — which is the higher-scored —
    // candidate. See the note above on what that does and does not concede.
    if (severity < bestSeverity) {
      best = candidate;
      bestSeverity = severity;
    }
    if (bestSeverity <= floor) break;
  }
  return best;
}

// ---------------------------------------------------------------------------
// Rule 5's other half: what happens after the API hand fails.
// ---------------------------------------------------------------------------
/** A verifier mismatch is not a transport error, so it is not one of the
 *  contract's `ExecErrorKind`s — but it must fall back exactly like one. The
 *  API said it worked and the world disagreed; that is the most serious of
 *  these, not the least. */
export type ApiFailureKind = ExecErrorKind | "verifier";

export interface ApiFailure {
  kind: ApiFailureKind;
  message?: string;
  /** Rate limits get ONE retry before they count as a failure. Without this
   *  flag the router cannot tell "we were told to slow down" from "we slowed
   *  down and were told again", and a single burst would fall back to the
   *  browser and, on the second burst, walk the pair down the ladder for
   *  something that was never the API's fault. */
  retried?: boolean;
}

export interface FallbackCtx extends UserCtx {
  /** Failures in a row for this (signature, app) pair, THIS one included. The
   *  caller owns the counter and resets it on a success and on applying a
   *  demotion — without the reset the pair walks down one rung per failure
   *  instead of one rung per two. */
  consecutiveApiFailures?: number;
  /** The pair's rung right now, so the plan can name the rung to drop to
   *  rather than making the caller re-derive it. */
  rung?: Rung;
  /** What the step DOES, after `tightenSideEffect` — the same effect the
   *  routing decision was made on, not the planner's original guess. It decides
   *  whether running the step a second time on the other hand is free or is a
   *  duplicate the owner cannot undo. Read `reRunIsFree` for what happens when
   *  a caller does not declare it. */
  sideEffect?: SideEffect;
}

export interface FallbackPlan {
  /** "retry-api": the one rate-limit retry has not been spent yet.
   *  "browser": run the same step on the other hand, inside this same task.
   *  "queue": the browser is unreachable, so park it and tell the owner.
   *  "ask-owner": the step may ALREADY have happened and doing it again would
   *  change the world twice. Nothing runs; the owner is told what is unknown
   *  and decides. This is a distinct action rather than a flag on "browser" on
   *  purpose: a caller that has never heard of it falls through and does
   *  nothing, which is the safe outcome. A flag a caller can ignore is a
   *  duplicate send waiting for the first executor that forgets to read it. */
  action: "retry-api" | "browser" | "queue" | "ask-owner";
  /** null = no demotion this time. */
  demoteTo: Rung | null;
  /** A 401 is not a task failure and must not be reported as one. The token
   *  died; one tap fixes it. */
  reauthNudge: boolean;
  /** Goes to `capability_stats.last_fail_reason`. */
  failReason: string;
  /** Whether this failure leaves it UNKNOWN that the step happened. Structured
   *  because `reason` is prose and nothing may branch on prose — a caller
   *  deciding what to tell the owner needs the fact, not the sentence. */
  mayHaveLanded: boolean;
  reason: string;
}

/**
 * Did this failure leave the world possibly changed?
 *
 * Three kinds are a PROMISE the step did not happen, and they are the vendor's
 * promises rather than ours: a credential rejected at the door never reached
 * the owner's account, a schema the vendor refused was never executed, and a
 * 429 is documented as "not executed" — which is exactly why the adapter one
 * layer down retries that one status and nothing else.
 *
 * Everything else may already have landed. `other` is the bucket holding
 * timeouts, 5xx and dropped connections, and there is no field anywhere in
 * `ExecResult` that separates "the request never left" from "the response
 * never came back", so the honest answer for the whole bucket is "unknown".
 * `verifier` is the sharpest case of all: the call ran and returned ok, and
 * only the effect is in doubt — the verifier may simply be reading a world
 * that has not caught up.
 */
export function apiFailureMayHaveLanded(kind: ApiFailureKind): boolean {
  switch (kind) {
    case "auth":
    case "schema":
    case "rate":
      return false;
    default:
      return true;
  }
}

/**
 * Is running this step a second time, on the other hand, free?
 *
 * Only for a read. A write or an irreversible step that failed with its
 * outcome unknown is the one thing this whole file exists to avoid doing
 * twice.
 *
 * When the caller declares NOTHING, this does not read the silence as "read".
 * The floor points the same way as rule 1's: a missing declaration must not
 * buy a permission. It falls back to the one structural fact the ladder
 * guarantees — rule 4 will not put a write or an irreversible step on the API
 * hand below WRITE_MIN_RUNG, so a failure reported from a lower rung came from
 * a read and can be repeated. At or above that rung, or with no rung either,
 * the step could have been a write and the owner is asked.
 *
 * That inference is a floor and not a licence: it can only ever PERMIT the
 * fallback for rungs where a write was impossible, so a caller cannot widen it
 * by lying upward. Callers should declare `sideEffect` anyway — the inference
 * exists so that a caller written before the field cannot silently duplicate a
 * send, not so that declaring is optional.
 */
function reRunIsFree(ctx: FallbackCtx): boolean {
  if (ctx.sideEffect != null) return ctx.sideEffect === "read";
  const rung = ctx.rung;
  return typeof rung === "number" && Number.isFinite(rung) && rung < WRITE_MIN_RUNG;
}

/**
 * What to do when the API hand just failed.
 *
 * The rule the owner wrote: any API failure falls back to the browser inside
 * the SAME task when the device is online, else queues and tells him. Two
 * consecutive failures drop the pair one rung.
 *
 * Falling back inside the same task is the point. The failure the owner
 * actually experiences is not "the API returned 401", it is "the thing I asked
 * for did not happen"; a fallback he never sees costs him a second of latency
 * instead of an errand.
 *
 * WITH ONE EXCEPTION, WHICH IS THE WHOLE OF THE SECOND HALF OF THIS FUNCTION.
 *
 * "The thing I asked for did not happen" is an assumption, and on an ambiguous
 * failure it is one nobody checked. A timeout, a 5xx or a connection that
 * dropped after the request left may all sit on top of a step that ALREADY
 * RAN. The adapter one layer down knows this — it retries a 429 exactly once
 * and refuses to retry anything else, because the execute endpoint takes no
 * idempotency key and a retried send is a second send. Falling the same step
 * over to the browser hand is that second attempt wearing a different hat, and
 * it would undo the adapter's care one layer up.
 *
 * So: a read falls back freely, because doing it twice costs nothing and
 * refusing costs the owner the whole task. A write or an irreversible step
 * whose failure MAY have landed goes to him instead — one question beats a
 * second payment, a second message, or a second deletion.
 */
export function fallbackAfterApiFailure(err: ApiFailure | null | undefined, ctx: FallbackCtx): FallbackPlan {
  const kind: ApiFailureKind = err?.kind ?? "other";
  const message = err?.message ? `: ${err.message}` : "";
  const failReason = `${kind}${message}`;
  const mayHaveLanded = apiFailureMayHaveLanded(kind);

  if (kind === "rate" && !err?.retried) {
    // Not yet a failure. Spending the retry is cheaper than a browser run, and
    // demoting a pair for one 429 would punish the hand for the vendor's
    // traffic shaping. Safe on a write too, and only because the vendor
    // documents a 429 as not executed — see `apiFailureMayHaveLanded`.
    return {
      action: "retry-api",
      demoteTo: null,
      reauthNudge: false,
      failReason,
      mayHaveLanded,
      reason: "API rate-limited, retrying once before switching hands",
    };
  }

  // A missing counter is treated as ONE failure, not two. Demoting a pair on a
  // caller's omission would quietly undo weeks of successful runs, and the
  // floor here points the other way from rule 1's: doing nothing is safe.
  const inARow = Math.max(1, Math.floor(ctx.consecutiveApiFailures ?? 1));
  const rung = ctx.rung;
  const demoteTo: Rung | null =
    inARow >= 2 && typeof rung === "number" && rung > 0 ? ((rung - 1) as Rung) : null;

  const online = ctx.deviceOnline === true;
  const demoteNote = demoteTo === null ? "" : `, dropping to rung ${demoteTo} after ${inARow} failures in a row`;
  // A 401 looks like a task failure to the owner, so it triggers a re-auth
  // nudge and a browser fallback, and is recorded as last_fail_reason rather
  // than as a demotion on its own.
  const reauthNudge = kind === "auth";

  if (mayHaveLanded && !reRunIsFree(ctx)) {
    // Note what this does NOT do: it does not queue. "Queue" means run it when
    // the browser comes back, which on a step that may already have happened
    // is a duplicate with a delay on it. The device being online or asleep
    // changes nothing here — what is missing is not a hand, it is the one fact
    // only the owner can settle.
    return {
      action: "ask-owner",
      // The hand still failed, so the ladder still moves. Needing his word is
      // not the same as forgiving the run.
      demoteTo,
      reauthNudge,
      failReason,
      mayHaveLanded,
      reason: `API failed with the step's outcome unknown (${failReason}); it may already have happened, so it waits for the owner instead of running again on the other hand${demoteNote}`,
    };
  }

  return {
    action: online ? "browser" : "queue",
    demoteTo,
    reauthNudge,
    failReason,
    mayHaveLanded,
    reason: online
      ? `API failed (${failReason}), same-task fallback to browser${demoteNote}`
      : `API failed (${failReason}) and the browser is unreachable, queued for the owner${demoteNote}`,
  };
}

// ---------------------------------------------------------------------------
// The router.
// ---------------------------------------------------------------------------
export interface RouterDeps {
  provider: Provider;
  judge: MatchJudge;
  ledger: Ledger;
  costWeight?: number;
  candidateLimit?: number;
}

export interface TwoHandRouter extends Router {
  decide(sig: CapabilitySignature, ctx: UserCtx): Promise<RouteDecision>;
}

export function createRouter(deps: RouterDeps): TwoHandRouter {
  const costWeight = typeof deps.costWeight === "number" ? deps.costWeight : DEFAULT_COST_WEIGHT;
  const limit = typeof deps.candidateLimit === "number" ? deps.candidateLimit : CANDIDATE_LIMIT;

  // Every ledger read is wrapped. An unavailable ledger must land on the
  // browser, never on "we could not read the rung so assume it is high" — that
  // is the shape that turns an outage into an unlicensed write.
  const safeRung = async (userId: string, sigHash: string, app: string): Promise<Rung> => {
    try {
      const r = await deps.ledger.rung(userId, sigHash, app);
      return typeof r === "number" && r >= 0 && r <= 4 ? (r as Rung) : 0;
    } catch {
      return 0;
    }
  };
  const safeOptIn = async (userId: string, app: string): Promise<boolean> => {
    try {
      return (await deps.ledger.writesOptedIn(userId, app)) === true;
    } catch {
      return false;
    }
  };
  const safePrior = async (userId: string, sigHash: string, app: string): Promise<CapabilityStats[]> => {
    try {
      const rows = await deps.ledger.prior(userId, sigHash, app);
      return Array.isArray(rows) ? rows : [];
    } catch {
      return [];
    }
  };
  // `known` is not decoration. An empty list from a vendor that is DOWN and an
  // empty list from an owner who has connected NOTHING are the same array, and
  // treating them the same texts him "connect this app to make me faster" about
  // an app he connected last month — during an outage, for every task, while
  // onboarding counts each one as evidence he wants the nudge. The routing
  // floor is identical either way; only the nudge needs to tell them apart.
  const safeConnections = async (userId: string): Promise<{ rows: ConnectedApp[]; known: boolean }> => {
    try {
      const rows = await deps.provider.connections(userId);
      return Array.isArray(rows) ? { rows, known: true } : { rows: [], known: false };
    } catch {
      return { rows: [], known: false };
    }
  };

  // The browser is the hand that needs a machine. When that machine is asleep
  // the step is parked rather than dispatched, because dispatching into a
  // sleeping browser surfaces to the owner as "your errand failed" for a
  // reason that has nothing to do with his errand.
  const onBrowser = (
    ctx: UserCtx,
    rung: Rung,
    score: number,
    reason: string,
    extra: Partial<RouteDecision> = {},
  ): RouteDecision => {
    const queued = ctx.deviceOnline !== true;
    return {
      hand: "browser",
      rung,
      score,
      reason: queued ? `${reason}; browser unreachable, queued` : reason,
      ...(queued ? { queued: true } : {}),
      ...extra,
    };
  };

  return {
    async decide(sig: CapabilitySignature, ctx: UserCtx): Promise<RouteDecision> {
      // THE HASH IS CHECKED BEFORE IT IS TRUSTED.
      //
      // Everything below reads two fields off this object as though this
      // process computed them: `signature_hash` selects the ledger rung, and
      // `side_effect` decides whether the step confirms. But a signature
      // reaching `decide` may have crossed a process boundary — reloaded from
      // D1, returned by a model, handed back across the extension boundary —
      // and nothing about the object itself says where it came from.
      //
      // Swap the hash for that of a promoted READ pair and a delete arrives
      // wearing a read's track record: rung 4, no confirmation, executed
      // unattended with the laptop shut. That is the single outcome the whole
      // promotion ladder exists to make impossible, and every rung above it is
      // decoration if this field can be chosen by whoever last held the object.
      //
      // Re-deriving the hash costs a sha1 over three short strings. It is the
      // cheapest check in this file and it gates the most expensive mistake.
      //
      // The polarity is a FLOOR: a signature that does not verify does not get
      // a browser run "just to be safe with a lower rung" — it gets rung 0 and
      // the API hand is never considered, because a hash we cannot reproduce
      // means we do not know WHICH capability this is, and an unknown
      // capability cannot have earned anything. Irreversible still confirms,
      // read off the declared field, which is the strictest available reading
      // of an object we already distrust.
      if (!verifySignatureHash(sig)) {
        return onBrowser(ctx, 0, 0,
          "browser: signature_hash does not match this process's own derivation — "
            + "the capability is unidentified, so no rung and no API hand",
          { ...(sig?.side_effect === "irreversible" ? { requiresConfirmation: true } : {}) });
      }

      // The planner's `app_hint` is never read here. It is a guess made before
      // anyone looked at a catalog, and letting it pick the app would make the
      // planner's wording — not the world — decide which account gets touched.
      const { rows: connections, known: connectionsKnown } = await safeConnections(ctx.userId);
      const activeApps = new Set(connections.filter((c) => c.status === "active").map((c) => c.app));

      // ---- RULE 1: SEARCH FIRST, THEN ASK THE JUDGE -----------------------
      const candidates = await gatherCandidates(deps.provider, sig, ctx.userId, activeApps, limit);
      const matched = await gentlestJudgedMatch(deps.judge, sig, candidates);

      if (!matched) {
        // No licence. This covers "no tool exists", "the judge said no", "the
        // judge said unclear", "the judge returned no-verdict" and "the judge
        // is down" — deliberately one branch, because the router must not be
        // able to treat the absence of an objection as permission. There is no
        // pair here, so rung 0 is the honest rung: nothing has been earned.
        return onBrowser(ctx, 0, 0, `browser: ${candidates.length} candidate${candidates.length === 1 ? "" : "s"} found, none licensed by the judge`, {
          // Irreversible steps confirm on either hand. A step that cannot be
          // taken back is not made safe by being done slowly.
          ...(sig.side_effect === "irreversible" ? { requiresConfirmation: true } : {}),
        });
      }

      // The tool's self-declared side effect may only make this step STRICTER.
      // A tool that calls itself read-only cannot turn a write into a read —
      // MCP says annotations are untrusted, and the tool has every incentive
      // to look harmless.
      const effect: SideEffect = tightenSideEffect(sig.side_effect, matched.sideEffectHint);
      const irreversible = effect === "irreversible";
      const confirmFlag = irreversible ? { requiresConfirmation: true } : {};

      const [rung, prior] = await Promise.all([
        safeRung(ctx.userId, sig.signature_hash, matched.app),
        // Loaded before rule 2 branches so that a browser decision reports the
        // browser hand's real score. Reporting 0 for a hand with forty good
        // runs would make the audit line say the opposite of the truth to the
        // person reading it, and that line is the only account anyone gets of
        // why a step went the way it did.
        safePrior(ctx.userId, sig.signature_hash, matched.app),
      ]);
      const browserStats = browserRowFrom(prior);
      const browserScore = handScore(browserStats, costWeight);

      // ---- RULE 2: CONNECTED? ---------------------------------------------
      const connection = connections.find((c) => c.app === matched.app && c.status === "active");
      if (!connection) {
        // Expired and revoked land here too, on purpose. Executing against a
        // dead token buys a 401 that reaches the owner as a failed errand;
        // routing to the browser and asking him to reconnect costs him one tap
        // and no failed errand.
        return onBrowser(
          ctx,
          rung,
          browserScore,
          connectionsKnown
            ? `browser: a tool matched but its app is not connected (rung ${rung})`
            : `browser: a tool matched but the connection list is unavailable (rung ${rung})`,
          {
            ...(connectionsKnown ? { nudgeApp: matched.app } : {}),
            ...confirmFlag,
          },
        );
      }

      const apiStats = apiRowFor(prior, matched.toolSlug);
      const apiScore = handScore(apiStats, costWeight);

      // ---- RULE 5: where both hands are eligible, the numbers pick ---------
      // Browser must be STRICTLY better to take a step back from the API hand.
      // A tie is not evidence, and the ladder plus the judge's "yes" have
      // already licensed this hand; rule 5 is a demotion mechanism, not a
      // second licence gate. Treating a tie as a demotion would pin every
      // freshly promoted pair to the browser forever, since a pair with no API
      // rows and no browser rows ties at zero.
      const chooseBetweenHands = (why: string): RouteDecision => {
        if (browserScore > apiScore) {
          return onBrowser(
            ctx,
            rung,
            browserScore,
            `browser: ${why}, but browser scores higher (${browserScore.toFixed(2)} vs ${apiScore.toFixed(2)}), ${runsLabel(browserStats)}`,
            confirmFlag,
          );
        }
        return {
          hand: "api",
          tool: matched,
          accountId: connection.accountId,
          rung,
          score: apiScore,
          reason: `API, connected, rung ${rung}, ${runsLabel(apiStats)} (${why})`,
          ...confirmFlag,
        };
      };

      // ---- RULE 3: READ STEPS ---------------------------------------------
      if (effect === "read") {
        if (ctx.deviceOnline !== true) {
          // Reads may go API at ANY rung with the browser unreachable, because
          // the alternative is not a safer hand — it is no hand at all, and the
          // owner gets nothing. A read changes nothing in the world, so the
          // worst case is a wrong answer, which the verifier catches and which
          // costs a re-ask; refusing costs the whole task. The ladder exists to
          // protect against EFFECTS, and this step has none.
          return {
            hand: "api",
            tool: matched,
            accountId: connection.accountId,
            rung,
            score: apiScore,
            reason: `API, connected, rung ${rung}, read with the browser unreachable, ${runsLabel(apiStats)}`,
          };
        }
        if (rung === SHADOW_RUNG) {
          // Both hands run and the verifier compares them against the expected
          // effect — never against each other's output, or a wrong browser run
          // would certify a wrong API run for matching it.
          return {
            hand: "shadow",
            tool: matched,
            accountId: connection.accountId,
            rung,
            score: apiScore,
            reason: `shadow: rung ${rung}, both hands run and the verifier compares, ${runsLabel(apiStats)}`,
          };
        }
        if (rung >= API_ALONE_MIN_RUNG) {
          return chooseBetweenHands(`read at rung ${rung}`);
        }
        return onBrowser(ctx, rung, browserScore, `browser: read at rung ${rung}, the pair has not earned a shadow run yet`);
      }

      // ---- RULE 4: WRITE AND IRREVERSIBLE STEPS ----------------------------
      // NEVER shadow a write. A shadow run does the step TWICE; on a write that
      // is two messages sent, two payments made, two things deleted. There is
      // no rung at which that is acceptable, so this branch cannot reach the
      // shadow hand at all — it is not guarded by a condition, it is absent.
      const optedIn = await safeOptIn(ctx.userId, matched.app);
      const ladderAllows = rung >= WRITE_MIN_RUNG;
      if (ladderAllows && optedIn) {
        if (ctx.deviceOnline !== true) {
          // The owner opted in and the pair earned the rung; the API hand does
          // not need his browser, so a shut laptop is not a reason to park a
          // write he already authorised.
          return {
            hand: "api",
            tool: matched,
            accountId: connection.accountId,
            rung,
            score: apiScore,
            reason: `API, connected, rung ${rung}, ${effect} opted in with the browser unreachable, ${runsLabel(apiStats)}`,
            ...confirmFlag,
          };
        }
        return chooseBetweenHands(`${effect} at rung ${rung}, writes opted in`);
      }

      const why = !ladderAllows
        ? `${effect} at rung ${rung}, below the rung writes need`
        : `${effect} at rung ${rung}, writes not opted in for this app`;
      return onBrowser(ctx, rung, browserScore, `browser: ${why}`, confirmFlag);
    },
  };
}
