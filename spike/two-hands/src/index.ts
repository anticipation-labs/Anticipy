// THE SPIKE, ASSEMBLED. The first place the seven parts meet.
//
// Every other module in this directory was written on its own against
// contract.ts. That is the right way to build seven things at once and it has
// one guaranteed cost: the seams. This file is where the seams are, and three
// of them are load-bearing enough that the second hand does not work at all
// without the wiring below. They are named where they are fixed, and the ones
// that could NOT be fixed here are named in RESULTS.md as findings rather than
// quietly worked around.
//
// SEAM 1 — NOBODY TELLS THE LEDGER WHAT THE JUDGE SAID.
// The ledger's rung 0 -> 1 gate is "a candidate the judge vouched for, on an
// app the owner connected", and it fires from `noteCandidate`. The router
// never calls it — it holds a `Ledger`, and `Ledger` has no writer for
// `api_candidates` (ledger.ts contract problem 3). So in the unassembled
// spike every pair sits at rung 0 forever, rule 3 sends every read to the
// browser, and the API hand is unreachable no matter how well it works.
// Fixed here by `recordingJudge`, which wraps the caller's judge and writes
// the candidate row it was just asked about.
//
// SEAM 2 — `ExecResult.error.kind` NEVER REACHES `Outcome.failKind`.
// The contract's `Outcome` carries only free-text `failReason`, and the ledger
// refuses (rightly) to sniff prose for "401". If the executor drops the kind,
// an expired refresh token is recorded as "other", two of them demote a
// working capability, shadow re-opens, and the agent drives the browser for a
// week re-earning ground it never lost. `apiOutcome()` below is the one
// translation point and it carries the kind across.
//
// SEAM 3 — THE OWNER CONNECTING AN APP NEVER REACHES THE LADDER.
// `onboarding` decides when to ask and returns a state machine; `ledger`
// holds `app_consent`; nothing joined them. `onboarding.markConnected` here
// does both, because a connection the ladder never hears about is a connection
// that leaves the pair at rung 0.
//
// WHAT THIS FILE MAY NOT DO: decide anything. It moves facts between modules
// that already own their decisions. The one meaning question in the spike —
// "does this tool do this step?" — is asked of the caller's `MatchJudge` and
// read only through the contract's `judgeLicensesApi`. There is no app list,
// no verb list and no threshold here, and there must never be one: this is the
// file where a "just map google.com to gmail" would look harmless.

import { judgeLicensesApi } from "./contract.ts";
import type {
  ApiCandidate,
  CapabilitySignature,
  ConnectedApp,
  ConnectNudge,
  ExecResult,
  MatchAnswer,
  MatchJudge,
  Provider,
  ToolCandidate,
  UserCtx,
} from "./contract.ts";
import { createRouter } from "./router.ts";
import type { RouteDecision, TwoHandRouter } from "./router.ts";
import { InMemoryLedger } from "./ledger.ts";
import type { LedgerOutcome } from "./ledger.ts";
import { createObserver, TraceObserver } from "./observer.ts";
import {
  accountChoice,
  nudgeText,
  onConnected,
  onDeclined,
  onSent,
  onWouldHaveUsed,
  scopesFor,
  shouldNudge,
} from "./onboarding.ts";
import type {
  AccountChoice,
  NudgeAnswer,
  NudgeCtx,
  NudgeEvidence,
  NudgeRecord,
  ScopeRequest,
  TaggedAccount,
} from "./onboarding.ts";

// ---------------------------------------------------------------------------
// The assembled thing.
// ---------------------------------------------------------------------------

export interface TwoHandsDeps {
  /** Composio in production, the fake in every test. Swapping vendors is this
   *  one field — that is what the `Provider` interface bought. */
  provider: Provider;
  /** THE ONLY THING IN THE SPIKE THAT DECIDES A MEANING, and nothing here
   *  implements it: a judge is a model call, and a model call needs a key.
   *  The caller supplies one (tasks/run_ten.ts builds the real one over
   *  OpenRouter; tests build a stub). Required rather than defaulted, because
   *  a default judge would have to answer without a model, and a judge that
   *  answers without a model is the pattern-match this spike exists to delete. */
  judge: MatchJudge;
  ledger?: InMemoryLedger;
  observer?: TraceObserver;
  costWeight?: number;
  candidateLimit?: number;
  /** Injected clock, so a replay of a recorded run produces the same rows. */
  now?: () => number;
}

/** The onboarding hand, bound to this owner's ledger.
 *
 *  onboarding.ts is deliberately pure — every function takes a row and returns
 *  a row. That makes it testable and leaves somebody to own the storage. This
 *  is that somebody: each method reads the row, applies onboarding's own
 *  transition, and writes it back through the ledger's `connect_nudges` table,
 *  so there is exactly one definition of each transition and exactly one place
 *  the row lives. */
export interface OnboardingHand {
  /** The stored row, or undefined when this app has never come up. */
  row(userId: string, app: string): Promise<NudgeRecord | undefined>;
  /** "Should we ask him to connect this?" — reads the row itself, so a caller
   *  cannot accidentally judge against a row it forgot to load. */
  shouldNudge(app: string, ctx: NudgeCtx): Promise<NudgeAnswer>;
  /** One more task that would have used this app. This is the ONLY way
   *  evidence accrues; without it `shouldNudge` holds on `no-evidence` for
   *  ever and the second hand is never offered to anyone. */
  wouldHaveUsed(userId: string, app: string): Promise<NudgeRecord>;
  markSent(userId: string, app: string, now: number, channel: "sms" | "ios"): Promise<NudgeRecord>;
  markConnected(userId: string, app: string, now: number): Promise<NudgeRecord>;
  markDeclined(userId: string, app: string, now: number): Promise<NudgeRecord>;
  /** The SMS copy. Pure — it is here so a caller holding the hand does not
   *  have to import onboarding.ts as well and get the two out of step. */
  text(app: string, evidence: NudgeEvidence): string;
  scopesFor(candidates: ToolCandidate[] | null | undefined): ScopeRequest;
  accountChoice(
    candidates: ToolCandidate[] | null | undefined,
    accountHint: "work" | "personal" | null | undefined,
    connected: TaggedAccount[] | null | undefined,
  ): AccountChoice;
  /** The link the text carries. Goes to the vendor, so it lives on the hand
   *  that has a provider rather than in the pure module. */
  connectLink(userId: string, app: string, scopes?: string[]): Promise<{ url: string }>;
}

export interface TwoHands {
  router: TwoHandRouter;
  ledger: InMemoryLedger;
  provider: Provider;
  observer: TraceObserver;
  onboarding: OnboardingHand;
}

export function makeTwoHands(deps: TwoHandsDeps): TwoHands {
  // Types are stripped, not checked. A caller that forgets the judge would
  // otherwise get "cannot read properties of undefined" from inside the
  // router's candidate loop — which the router catches and turns into a
  // browser decision, so the spike would look like it worked and would simply
  // never use the API hand again. Loud beats silent.
  if (!deps || typeof deps !== "object") throw new TypeError("makeTwoHands needs a deps object");
  if (!deps.provider || typeof deps.provider.search !== "function") {
    throw new TypeError("makeTwoHands needs a Provider");
  }
  if (!deps.judge || typeof deps.judge.matches !== "function") {
    throw new TypeError("makeTwoHands needs a MatchJudge: nothing else may license the API hand");
  }

  const now = typeof deps.now === "function" ? deps.now : () => Date.now();
  const ledger = deps.ledger ?? new InMemoryLedger({ now });
  const observer = deps.observer ?? createObserver();
  const provider = deps.provider;

  const onboarding = makeOnboardingHand(ledger, provider);

  const router: TwoHandRouter = {
    async decide(sig: CapabilitySignature, ctx: UserCtx): Promise<RouteDecision> {
      // A fresh scope per decision, and a fresh router bound to it.
      //
      // The scope memoises `connections()` for the length of ONE decision: the
      // router asks for it, and so does the recording judge, and one decision
      // must not cost the owner two round trips to the vendor. It is per-call
      // rather than per-process because the owner connects an app in the
      // middle of a session and a cached "not connected" would tell him to
      // connect what he just connected.
      //
      // The judge has to be built per decision because `MatchJudge.matches`
      // carries no userId (contract gap, see RESULTS.md) and the candidate row
      // it writes is keyed by one. A module-level "current owner" would work
      // in a test and cross two owners' rows the first time two tasks
      // interleave inside one Worker.
      const scope = callScope(provider);
      const recording = recordingJudge(deps.judge, ledger, ctx, scope, provider.name);
      const bound = createRouter({
        provider: scope.provider,
        judge: recording,
        ledger,
        ...(typeof deps.costWeight === "number" ? { costWeight: deps.costWeight } : {}),
        ...(typeof deps.candidateLimit === "number" ? { candidateLimit: deps.candidateLimit } : {}),
      });

      const decision = await bound.decide(sig, ctx);

      // Rule 2 fired: a tool the judge vouched for, in an app he has not
      // connected. That is the evidence the connect nudge is built from, and
      // it is counted HERE rather than inside onboarding because onboarding
      // never sees a routing decision. A retried step counts twice; the
      // counter is "tasks that would have used it" and a retry is one more
      // task that would have, so the small inflation is in the honest
      // direction and is cheaper than deduplicating on a step id the router
      // does not carry.
      if (typeof decision.nudgeApp === "string" && decision.nudgeApp !== "") {
        try {
          await onboarding.wouldHaveUsed(ctx.userId, decision.nudgeApp);
        } catch {
          // Bookkeeping. A ledger that cannot write must not turn a routing
          // decision the owner is waiting on into a thrown error.
        }
      }
      return decision;
    },
  };

  return { router, ledger, provider, observer, onboarding };
}

// ---------------------------------------------------------------------------
// SEAM 1: the judge, wrapped so the ledger hears the verdict.
// ---------------------------------------------------------------------------
/**
 * Ask the caller's judge, then write what it said to `api_candidates`.
 *
 * This is the only writer of that table in the assembled system, and the table
 * pays for three separate things:
 *   - the ladder's rung 0 -> 1 gate (a vouched candidate on a connected app),
 *   - the nudge's evidence that an API existed for a step we ran in the browser,
 *   - the measurement contract.ts LAW1 promises: how often the vendor's
 *     retrieval score agreed with the judge. That is the evidence for or
 *     against ever trusting a score on its own, and it cannot be collected
 *     retrospectively.
 *
 * THE VERDICT IS PASSED THROUGH UNTOUCHED, including a throw. The router reads
 * a throw as "the judge is unreachable" and stops asking; swallowing it here
 * would make an unreachable judge look like four "no"s and cost the owner four
 * timeouts inside a task he is watching.
 */
function recordingJudge(
  inner: MatchJudge,
  ledger: InMemoryLedger,
  ctx: UserCtx,
  scope: CallScope,
  providerName: Provider["name"],
): MatchJudge {
  return {
    async matches(sig: CapabilitySignature, candidate: ToolCandidate): Promise<MatchAnswer> {
      const answer = await inner.matches(sig, candidate);
      try {
        await noteVerdict(ledger, ctx, scope, providerName, sig, candidate, answer);
      } catch {
        // An api_candidates write is bookkeeping. Failing the ask because the
        // bookkeeping failed would take the API hand down for a full disk, and
        // the safe direction is already covered: an unwritten candidate leaves
        // the pair at rung 0, which routes to the browser.
      }
      return answer;
    },
  };
}

async function noteVerdict(
  ledger: InMemoryLedger,
  ctx: UserCtx,
  scope: CallScope,
  providerName: Provider["name"],
  sig: CapabilitySignature,
  candidate: ToolCandidate,
  answer: MatchAnswer,
): Promise<void> {
  if (!candidate || typeof candidate.toolSlug !== "string" || typeof candidate.app !== "string") return;

  const seen = await scope.activeApps(ctx.userId);
  // `ApiCandidate.connected` is a boolean and the vendor being unreachable is a
  // third state it cannot hold (see RESULTS.md). When we could not look, the
  // row says false — the direction that can only fail to promote a pair, never
  // promote one on a connection nobody confirmed.
  const connected = seen.known && seen.apps.has(candidate.app);

  const row: ApiCandidate = {
    user_id: ctx.userId,
    signature_hash: sig.signature_hash,
    app: candidate.app,
    tool_slug: candidate.toolSlug,
    // ORDERING ONLY, and it is written down precisely so that claim can be
    // audited later against `match_verdict` in the same row.
    match_score: typeof candidate.score === "number" ? candidate.score : 0,
    match_verdict: answer?.verdict ?? "no-verdict",
    connected,
    first_seen_at: ctx.now,
    // `ApiCandidate.source` has no member for a fake provider. Written as the
    // provider says it is rather than laundered into "composio": a fixture run
    // that files itself under the vendor's name is a results file nobody can
    // trust afterwards.
    source: providerName as ApiCandidate["source"],
  };
  await ledger.noteCandidate(row);

  // The vendor is the authority on whether an app is connected, and this is
  // the only place in the assembled system that hears the answer. `connections()`
  // returning without this app is a FACT (the owner revoked it, or never had
  // it); `connections()` throwing is not, and is skipped — a vendor outage must
  // not clear a consent flag that gates the inherited rung.
  if (!seen.known) return;
  const wasConnected = await ledger.connected(ctx.userId, candidate.app);
  if (wasConnected !== connected) {
    await ledger.setConnection(ctx.userId, candidate.app, connected);
  }
}

// ---------------------------------------------------------------------------
// One decision's worth of vendor calls.
// ---------------------------------------------------------------------------
interface CallScope {
  provider: Provider;
  activeApps(userId: string): Promise<{ apps: Set<string>; known: boolean }>;
}

function callScope(provider: Provider): CallScope {
  const inflight = new Map<string, Promise<ConnectedApp[]>>();

  const connections = (userId: string): Promise<ConnectedApp[]> => {
    const cached = inflight.get(userId);
    if (cached) return cached;
    // The promise is cached, not the result, so two callers that ask before
    // the first answer arrives still make one request.
    const p = Promise.resolve().then(() => provider.connections(userId));
    inflight.set(userId, p);
    return p;
  };

  const wrapped: Provider = {
    name: provider.name,
    search: (sig, userId, opts) => provider.search(sig, userId, opts),
    connections,
    connectLink: (userId, app, scopes) => provider.connectLink(userId, app, scopes),
    execute: (userId, toolSlug, args, accountId) => provider.execute(userId, toolSlug, args, accountId),
  };

  return {
    provider: wrapped,
    async activeApps(userId: string) {
      try {
        const rows = await connections(userId);
        if (!Array.isArray(rows)) return { apps: new Set<string>(), known: false };
        // "Connected" means USABLE. An expired token is listed and unusable,
        // and counting it would promote a pair on the strength of a connection
        // whose next call is a 401.
        return {
          apps: new Set(rows.filter((c) => c?.status === "active").map((c) => c.app)),
          known: true,
        };
      } catch {
        return { apps: new Set<string>(), known: false };
      }
    },
  };
}

// ---------------------------------------------------------------------------
// SEAM 3: onboarding's pure state machine, given somewhere to live.
// ---------------------------------------------------------------------------
function makeOnboardingHand(ledger: InMemoryLedger, provider: Provider): OnboardingHand {
  const read = async (userId: string, app: string): Promise<NudgeRecord | undefined> =>
    (await ledger.nudge(userId, app)) as NudgeRecord | undefined;

  /**
   * Write the whole row back.
   *
   * `asks` and `declines` are NOT columns of the contract's `ConnectNudge`
   * (onboarding.ts contract problems 1 and 2) and they survive this round trip
   * only because the in-memory table stores whole objects. On D1 they are two
   * columns that have to exist, and without them "a second decline is
   * never-again" and "re-ask once" both silently become "ask every fortnight
   * for ever" — the feature turns into nagware while every test still passes.
   * test/integration.test.ts pins the round trip so the requirement is on a
   * leg rather than in a comment.
   */
  const write = async (row: NudgeRecord): Promise<NudgeRecord> => {
    const { user_id, app, ...patch } = row;
    return (await ledger.noteNudge(user_id, app, patch as Partial<ConnectNudge>)) as NudgeRecord;
  };

  return {
    row: read,

    async shouldNudge(app: string, ctx: NudgeCtx): Promise<NudgeAnswer> {
      const row = await read(ctx?.userId ?? "", app);
      return shouldNudge(app, row ?? null, ctx);
    },

    async wouldHaveUsed(userId: string, app: string): Promise<NudgeRecord> {
      return write(onWouldHaveUsed(app, await read(userId, app), userId));
    },

    async markSent(userId: string, app: string, at: number, channel: "sms" | "ios"): Promise<NudgeRecord> {
      return write(onSent(app, await read(userId, app), at, channel, userId));
    },

    async markConnected(userId: string, app: string, at: number): Promise<NudgeRecord> {
      const row = await write(onConnected(app, await read(userId, app), at, userId));
      // THE WIRE THAT MAKES THE LADDER START. The ledger's rung 0 -> 1 gate is
      // a vouched candidate AND a connection, and this is the moment the second
      // half arrives. Without it the owner taps the link, the vendor knows, and
      // the ladder does not — so every step stays on the browser hand and the
      // connect nudge he just accepted buys him nothing.
      await ledger.setConnection(userId, app, true);
      return row;
    },

    async markDeclined(userId: string, app: string, at: number): Promise<NudgeRecord> {
      return write(onDeclined(app, await read(userId, app), at, userId));
    },

    text: nudgeText,
    scopesFor,
    accountChoice,

    connectLink(userId: string, app: string, scopes?: string[]): Promise<{ url: string }> {
      return provider.connectLink(userId, app, scopes);
    },
  };
}

// ---------------------------------------------------------------------------
// SEAM 2: an ExecResult, or a browser step, becoming a ledger row.
// ---------------------------------------------------------------------------
// The executor does not exist in week 1 — nothing in this spike runs a step
// end to end. These two are the translation points it will need, exported so
// the harness and the tests use the same ones, because the failure they prevent
// is a caller writing the row by hand and dropping one field.

export interface ApiOutcomeInput {
  sig: CapabilitySignature;
  ctx: UserCtx;
  app: string;
  toolSlug: string;
  result: ExecResult;
  /** What the verifier saw. "unknown" is a no-verdict and never demotes; it is
   *  the honest answer when nobody looked, and it must not be dressed up as
   *  "verified" to make a table look complete. */
  verifierResult: "verified" | "unverified" | "unknown";
  /** Shadow runs only: did the API hand's effect match the verifier's ground
   *  truth. Absent on a solo run — `false` is a mismatch and demotes. */
  parity?: boolean;
  at?: number;
}

export function apiOutcome(input: ApiOutcomeInput): LedgerOutcome {
  const r = input.result ?? { ok: false, ms: 0 };
  const outcome: LedgerOutcome = {
    user_id: input.ctx.userId,
    signature_hash: input.sig.signature_hash,
    app: input.app,
    hand: "api",
    tool_slug: input.toolSlug,
    ok: r.ok === true,
    ms: Number.isFinite(r.ms) ? Math.max(0, r.ms) : 0,
    // An absent `costUsd` is UNKNOWN, not free (provider_composio contract
    // problem 4). `Outcome.cost` is a required number with no room for that, so
    // it lands as 0 — and RESULTS.md says so, because a ledger that totals
    // unknown as zero reports the API hand as free, which is the exact claim
    // the premium guard exists to stop us making.
    cost: typeof r.costUsd === "number" && Number.isFinite(r.costUsd) ? r.costUsd : 0,
    verifierResult: input.verifierResult,
    // The step's own declaration, so the ledger does not have to infer read vs
    // write from the rung the router happened to be standing on.
    side_effect: input.sig.side_effect,
    ...(typeof input.parity === "boolean" ? { parity: input.parity } : {}),
    ...(typeof input.at === "number" ? { at: input.at } : {}),
  };
  if (r.ok !== true) {
    // THE FIELD THAT DECIDES WHETHER A TOKEN EXPIRY COSTS THE OWNER A WEEK.
    // `failKind` is structure the provider already computed from an HTTP status;
    // dropping it here would leave the ledger with prose it is forbidden to
    // sniff, and an expired refresh token would demote a working capability.
    outcome.failKind = r.error?.kind ?? "other";
    outcome.failReason = outcome.failKind;
  }
  return outcome;
}

export interface BrowserOutcomeInput {
  sig: CapabilitySignature;
  ctx: UserCtx;
  /** The app this step was about.
   *
   *  IT IS SUPPLIED, NEVER DERIVED FROM `TraceSummary.hosts`. Turning
   *  "google.com" into an app slug requires a host -> app table, and the same
   *  host is Gmail, Calendar and Drive — so the table would not be a lookup, it
   *  would be a guess about what the step MEANT, written as a list of app
   *  names. That is the one thing this spike is forbidden to build. The caller
   *  knows the app because the router told it, or because the owner did. */
  app: string;
  observer: TraceObserver;
  runId: string;
  stepId: string;
  ok: boolean;
  verifierResult: "verified" | "unverified" | "unknown";
  parity?: boolean;
  failReason?: string;
  at?: number;
}

/**
 * The browser hand's row, timed by the Observer.
 *
 * Rule 5 compares the two hands on their own measured runs, and the Observer is
 * the only thing in the system that measures the browser one. Without this the
 * browser row stays empty, `handScore` returns 0 for it, and the comparison the
 * whole ladder is supposed to settle never has two numbers to settle it with.
 */
export function browserOutcome(input: BrowserOutcomeInput): LedgerOutcome {
  const summary = input.observer.summarize(input.runId, input.stepId);
  const outcome: LedgerOutcome = {
    user_id: input.ctx.userId,
    signature_hash: input.sig.signature_hash,
    app: input.app,
    hand: "browser",
    // The browser hand has no tool slug. A constant rather than "" so the
    // capability_stats key is readable in a dump; the router folds every
    // browser row together regardless, so nothing routes on this string.
    tool_slug: "browser",
    ok: input.ok === true,
    ms: Number.isFinite(summary.duration_ms) ? Math.max(0, summary.duration_ms) : 0,
    // The browser hand costs no vendor dollars. It costs the owner's machine
    // and his session, which `cost_usd_total` has no unit for.
    cost: 0,
    verifierResult: input.verifierResult,
    side_effect: input.sig.side_effect,
    ...(typeof input.parity === "boolean" ? { parity: input.parity } : {}),
    ...(typeof input.at === "number" ? { at: input.at } : {}),
  };
  if (input.ok !== true) {
    // No `failKind`: the four kinds are the API hand's transport errors and a
    // browser failure is not one of them. It lands as "other", which is what it
    // is, and the ledger's demotion rules only ever read API-hand rows anyway.
    outcome.failReason = typeof input.failReason === "string" ? input.failReason : "browser step failed";
  }
  return outcome;
}

// Re-exported so a caller that holds only this module still reads a verdict
// through the contract's single definition. A second copy of "the judge
// vouched for it" is where `unclear` quietly starts counting as a yes.
export { judgeLicensesApi };

// The other half of the executor's contract, re-exported for the same reason:
// what to do when the API hand just failed is a routing rule, it lives in
// router.ts, and a caller that reached for its own `if (err.kind === "auth")`
// would be writing a second, quieter copy of the demotion policy.
export { fallbackAfterApiFailure, handScore, wilsonLowerBound } from "./router.ts";
export type { ApiFailure, FallbackCtx, FallbackPlan, RouteDecision, TwoHandRouter } from "./router.ts";
