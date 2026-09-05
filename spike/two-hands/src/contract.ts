// THE INTERFACES THE SECOND HAND IS WRITTEN AGAINST.
//
// Fixed before any part was built, because seven parts are being built beside
// each other and a contract discovered halfway through is a rewrite of all of
// them. Everything below is either in the owner's spec verbatim or is a
// correction to it that is called out by name in `LAW1` at the bottom of this
// file.
//
// Nothing here imports from brain/, extension/, migration/ or backend/. Week 1
// is a spike; `test/no_production_imports.test.ts` fails if that stops being
// true.

// ---------------------------------------------------------------------------
// CAPABILITY SIGNATURE — one step, described without naming a hand.
// ---------------------------------------------------------------------------
// The planner emits this, the router searches with it, the ledger is keyed by
// a hash of its stable fields. The whole no-hardcoding claim rests on the
// signature never saying HOW, only WHAT.
export type SideEffect = "read" | "write" | "irreversible";
export type Verb = "read" | "create" | "update" | "send" | "delete" | "pay" | "book";

export interface CapabilitySignature {
  /** The planner's guess at the app. ADVISORY ONLY — never a routing key, and
   *  never part of the hash. If it disagrees with the catalog match or the
   *  Observer's host, the trace wins and the planner is told. */
  app_hint: string | null;
  verb: Verb;
  object: string;
  inputs: Record<string, unknown>;
  /** What the verifier will check, phrased as an observable effect on the
   *  world. Parity between hands is judged on THIS, never on matching output. */
  expected_effect: string;
  side_effect: SideEffect;
  account_hint: "work" | "personal" | null;
  /** sha1(verb + object + sorted input KEY names). Values are deliberately
   *  excluded: "email Sam" and "email Dana" are the same capability and must
   *  share a rung, or every new recipient would re-open shadow mode. */
  signature_hash: string;
}

// ---------------------------------------------------------------------------
// PROVIDER — the only thing the router knows about a vendor.
// ---------------------------------------------------------------------------
// Pipedream was acquired, Klavis pivoted, Browser Use retired Skills with a 410
// inside a year. The router sees four methods; swapping Composio for Nango is a
// new file in this directory, not a rewrite.
export interface ToolCandidate {
  toolSlug: string;
  app: string;
  /** The vendor's own retrieval score. RANKS candidates. Never decides whether
   *  one is right — see LAW1 below. */
  score: number;
  /** The tool's self-declared side effect. MCP says annotations are untrusted,
   *  so this may only make a step STRICTER, never looser. `tightenSideEffect`
   *  is the only legal way to apply it. */
  sideEffectHint?: SideEffect;
  schema: Record<string, unknown>;
  description: string;
}

export interface ConnectedApp {
  app: string;
  accountId: string;
  label: string;
  scopes: string[];
  status: "active" | "expired" | "revoked";
}

export type ExecErrorKind = "auth" | "rate" | "schema" | "other";

export interface ExecResult {
  ok: boolean;
  data?: unknown;
  error?: { kind: ExecErrorKind; message: string };
  ms: number;
  costUsd?: number;
}

export interface Provider {
  name: "composio" | "mcp" | "webmcp" | "fake";
  search(
    sig: CapabilitySignature,
    userId: string,
    opts: { connectedOnly: boolean; limit: number },
  ): Promise<ToolCandidate[]>;
  connections(userId: string): Promise<ConnectedApp[]>;
  connectLink(userId: string, app: string, scopes?: string[]): Promise<{ url: string }>;
  execute(
    userId: string,
    toolSlug: string,
    args: Record<string, unknown>,
    accountId?: string,
  ): Promise<ExecResult>;
}

// ---------------------------------------------------------------------------
// THE MATCH JUDGE — the correction to the spec. Read LAW1 first.
// ---------------------------------------------------------------------------
// One question, asked on its own, answered in four states. The caller compares
// the verdict; it never re-reads the sentence.
export type MatchVerdict = "yes" | "no" | "unclear" | "no-verdict";

export interface MatchAnswer {
  verdict: MatchVerdict;
  /** For the audit line only. NOTHING may branch on these words. */
  reason: string;
}

export interface MatchJudge {
  /** "Does this tool do this step?" Asked once per candidate, about one
   *  candidate, with the signature in front of it. */
  matches(sig: CapabilitySignature, candidate: ToolCandidate): Promise<MatchAnswer>;
}

// ---------------------------------------------------------------------------
// LEDGER — the only thing that changes over time, and it changes from
// outcomes, not from code.
// ---------------------------------------------------------------------------
export type Hand = "api" | "browser";
export type Rung = 0 | 1 | 2 | 3 | 4;

export interface CapabilityStats {
  user_id: string;
  signature_hash: string;
  app: string;
  hand: Hand;
  tool_slug: string;
  n: number;
  successes: number;
  p50_ms: number;
  p95_ms: number;
  cost_usd_total: number;
  rung: Rung;
  last_fail_reason: string;
  last_run_at: number;
}

export interface ApiCandidate {
  user_id: string;
  signature_hash: string;
  app: string;
  tool_slug: string;
  match_score: number;
  /** The judge's verdict, kept so a later reader can tell "no tool existed"
   *  from "a tool existed and the judge would not vouch for it". */
  match_verdict: MatchVerdict;
  connected: boolean;
  first_seen_at: number;
  source: "composio" | "mcp" | "webmcp";
}

export type NudgeState = "queued" | "sent" | "connected" | "declined";

export interface ConnectNudge {
  user_id: string;
  app: string;
  state: NudgeState;
  sent_at: number | null;
  channel: "sms" | "ios" | null;
  tasks_that_would_have_used_it: number;
  declined_at: number | null;
}

export interface ShadowRun {
  run_id: string;
  step_id: string;
  api_result_hash: string;
  browser_result_hash: string;
  /** Parity is against the VERIFIER's ground truth — did the expected effect
   *  happen — never against the other hand's output. A wrong browser run must
   *  not certify a wrong API run for matching it. */
  parity: boolean;
  verifier_notes: string;
  api_ms: number;
  browser_ms: number;
  api_cost: number;
  browser_cost: number;
}

export interface Outcome {
  user_id: string;
  signature_hash: string;
  app: string;
  hand: Hand;
  tool_slug: string;
  ok: boolean;
  ms: number;
  cost: number;
  verifierResult: "verified" | "unverified" | "unknown";
  parity?: boolean;
  failReason?: string;
}

export interface Ledger {
  prior(userId: string, sigHash: string, app: string): Promise<CapabilityStats[]>;
  record(outcome: Outcome): Promise<void>;
  candidates(userId: string, sigHash: string): Promise<ApiCandidate[]>;
  rung(userId: string, sigHash: string, app: string): Promise<Rung>;
  setRung(userId: string, sigHash: string, app: string, rung: Rung): Promise<void>;
  writesOptedIn(userId: string, app: string): Promise<boolean>;
}

// ---------------------------------------------------------------------------
// ROUTER
// ---------------------------------------------------------------------------
export interface UserCtx {
  userId: string;
  /** Whether the owner's Chrome is reachable right now. Reads may go API with
   *  the laptop shut; writes may not, unless the owner opted in. */
  deviceOnline: boolean;
  now: number;
}

export interface Decision {
  hand: "api" | "browser" | "shadow";
  tool?: ToolCandidate;
  accountId?: string;
  rung: Rung;
  score: number;
  /** A sentence a person can read in the audit log: "API, connected, rung 2,
   *  LB95 0.94 over 27 runs." Written for a human; nothing branches on it. */
  reason: string;
}

export interface Router {
  decide(sig: CapabilitySignature, ctx: UserCtx): Promise<Decision>;
}

// ---------------------------------------------------------------------------
// OBSERVER — runs inside the extension, during agent runs only in v1.
// ---------------------------------------------------------------------------
// Answers two questions after a browser step: which app was that, and was it a
// write. Hosts and counts only. No request bodies, no response bodies, no
// cookies, no page text, no titles.
export interface TraceSummary {
  run_id: string;
  step_id: string;
  /** AT MOST ONE registrable domain: the one site the step was working in, as
   *  `principalHost` picks it. Never a path, a query string, a fragment or a
   *  subdomain — `google.com`, not `mail.google.com`.
   *
   *  This doc used to say "eTLD+1 only. 'mail.google.com' is kept as the
   *  host", which was wrong twice over and is kept here as a warning. The
   *  example contradicted its own rule — the eTLD+1 of `mail.google.com` IS
   *  `google.com` — and the array was described as though it held every domain
   *  the step touched, which is a page fingerprint rather than "which app was
   *  that". An observer whose contract promises less than it collects is the
   *  failure a Limited Use disclosure exists to prevent, so this field says
   *  exactly what it carries. It is an array only so that "nothing identifiable
   *  here" has a representation (`[]`) that is not null. */
  hosts: string[];
  writes: number;
  reads: number;
  status: Record<string, number>;
  duration_ms: number;
}

export interface Observer {
  summarize(runId: string, stepId: string): TraceSummary;
}

// ---------------------------------------------------------------------------
// LAW1 — THE ONE PLACE THIS SPIKE DEPARTS FROM THE OWNER'S SPEC, AND WHY.
// ---------------------------------------------------------------------------
// The spec says:
//
//     "If no candidate scores above match_threshold (start at 0.75 after LLM
//      rerank), route to browser and stop."
//
// Taken literally that is a threshold deciding what a step MEANS — whether
// "send an email to Sam" and GMAIL_SEND_EMAIL are the same act. HARNESS-LAWS
// law 1 reserves that judgement for a model with full context, and the repo
// has the receipts for why: a 0.75 cosine cutoff cannot tell "archive the
// thread" from "delete the thread", and the second one is irreversible.
//
// So the shape here is the house one — ONE question, asked on its own, with a
// FOUR-STATE answer, and the caller compares the verdict:
//
//     vendor score        ranks the candidates and picks which few to ask about
//     MatchJudge.matches  decides, per candidate, whether it does this step
//     verdict === "yes"   is the ONLY thing that may put a step on the API hand
//
// `unclear`, `no-verdict` and an unreachable judge all route to the browser.
// That polarity is deliberate and it is a FLOOR: the browser hand is the
// default, the API hand is the privilege, and a privilege needs something to
// license it rather than merely the absence of an objection.
//
// The score is not deleted — it is demoted to what a retrieval score is
// actually good for, which is ordering. `match_score` is still written to
// `api_candidates` so we can measure, later, how well the vendor's retrieval
// agreed with the judge. That measurement is the point: it is the evidence for
// or against ever trusting the score on its own.
//
// The second, smaller departure: MCP tool annotations (`readOnlyHint`,
// `destructiveHint`) are untrusted per the MCP spec, so `tightenSideEffect`
// below can only ratchet a step stricter. A tool that calls itself read-only
// cannot turn a write into a read.
export const SIDE_EFFECT_ORDER: Record<SideEffect, number> = {
  read: 0,
  write: 1,
  irreversible: 2,
};

export function tightenSideEffect(planned: SideEffect, hint?: SideEffect): SideEffect {
  if (!hint) return planned;
  return SIDE_EFFECT_ORDER[hint] > SIDE_EFFECT_ORDER[planned] ? hint : planned;
}

/** The judge's verdict, as the router is allowed to read it. Anything that is
 *  not an explicit "yes" is not a licence. */
export function judgeLicensesApi(answer: MatchAnswer | null | undefined): boolean {
  return answer?.verdict === "yes";
}
