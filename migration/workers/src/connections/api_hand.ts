/**
 * api_hand.ts — THE API HAND ACTS, and the floors in front of it.
 *
 * The Two Hands spec (docs/spec-connections.txt, "Two Hands: the Overwatch
 * layer and the API hand", pages 4-37) gives the agent a second hand: when an
 * app has an official API and the owner has connected it, call the API and skip
 * the browser. The adapter next door (provider.ts) can now `tools()` and
 * `execute()`. This file is the ONLY thing allowed to call `execute()`, and it
 * calls it only after four floors have held — in this order, cheapest and
 * quietest first, so a refusal costs no vendor call it did not have to:
 *
 *   1. THE ROW. A `connections` row exists for (owner, toolkit) with status
 *      "connected". Read from D1, never from the vendor — the spec: "The router
 *      reads connections to answer 'connected?' and writes_enabled to answer
 *      'may write?'. It never calls Composio for that." No row, a
 *      needs_reconnect row, a row for another owner: refused.
 *
 *   2. THE WRITE OPT-IN. If the step's effect is a write or irreversible, that
 *      row's `writes_enabled` is true. That column is the spec's per-app "Let
 *      Anticipy make changes" toggle, off by default, "the write opt-in the Two
 *      Hands ladder needs for rung 3. Reads never need it." Until this file
 *      NOTHING read it: the Settings screen wrote it, the webhook preserved it,
 *      the provider pinned it false, and no code path anywhere asked it before
 *      acting. This is the first consumer.
 *
 *   3. THE ALLOW-LIST. The tool slug is the `slug` of a row `tools(toolkit)`
 *      returned — the vendor's own catalog, in the vendor's own spelling. A
 *      slug a model typed, however plausible, is refused before the vendor
 *      hears it. This floor costs one catalog read (cached per provider, ten
 *      minutes), and it is the floor that turns "the model hallucinated
 *      GMAIL_DELETE_EVERYTHING" from a 404 into a refusal.
 *
 *   4. THE HINT. The tool's own MCP-style tags (`readOnlyHint`,
 *      `destructiveHint`, `createHint`, `updateHint`, all measured live) may
 *      TIGHTEN the declared effect and never loosen it — spec page 29: "MCP
 *      tool annotations like readOnlyHint and destructiveHint exist but the
 *      spec says to treat them as untrusted, so they can only make a step
 *      stricter, never looser." A planner that calls CREATE_EVENT a read is
 *      corrected to a write, and floor 2 is re-applied to the corrected effect.
 *      An irreversible effect, declared or tightened, additionally needs the
 *      caller's `confirmed: true` — spec page 31: "Irreversible always
 *      confirms. Both hands." The hand cannot verify a confirmation; it can
 *      refuse a caller that never heard of one.
 *
 * WHAT A REFUSAL RETURNS. `runStep` never throws. It returns one of three
 * outcomes: `refused` (nothing was sent to the vendor's execute endpoint —
 * the reason is a closed enum and `catalogRead` says whether the one allowed
 * catalog GET happened), `ran` (the vendor said the tool ran, with its data),
 * or `failed` (the vendor was called and answered with a failure — typed by the
 * contract's four kinds plus the vendor's own error token, never a thrown
 * string). Every outcome is logged with the owner row id, the toolkit, the
 * tool and the reason, and NEVER the arguments: `args` can hold the text of a
 * person's mail, and a log line is the one place in a server guaranteed to be
 * read by somebody it was not addressed to.
 *
 * THE POLARITY. Every floor here is a FLOOR in HARNESS-LAWS law 1's sense —
 * "does anything authorize this?" — and every missing answer refuses: a store
 * that cannot be read, a catalog that cannot be fetched, an effect nobody
 * declared, a key nobody set. The API hand is the privilege and the browser is
 * the default; a refusal here is the router routing to the browser, which
 * costs the owner minutes. Waving through costs the owner an action against
 * their real account that nobody licensed, which cannot be taken back.
 *
 * WHAT THIS FILE MAY NOT DO. It names no app — test/connections-api-hand.test.ts
 * reads this source and fails on one. It reads no natural language: the only
 * string comparisons below are against vendor ENUMS (a tool slug, a tag name,
 * a status column, an error slug), which is the seatbelt's kind of pattern
 * match — what a plan TOUCHES, never how it was worded. Which tool does this
 * step is a model's question, asked upstream; this file only checks that the
 * answer is a tool that exists and that this owner licensed its effect.
 *
 * Spec: "Two Hands: the Overwatch layer and the API hand", 2026-09-05, pages
 * 4-37, and "Connections", page 26 (Settings) and page 27 (router reads).
 */

// TYPES ONLY, erased before bundling; the Worker carries no runtime edge into
// the spike tree. The one runtime rule this file needs from the Two Hands
// contract — `tightenSideEffect` — is re-declared below and pinned to the
// contract's source by the test, the way provider.ts pins the owner-id shape.
import type {
  AccountAlias,
  OwnerId,
  Toolkit,
} from "../../../../spike/two-hands/src/connections/contract.ts";
import type { ExecErrorKind, SideEffect } from "../../../../spike/two-hands/src/contract.ts";

import { createD1Store, type ConnectionsStore, type StoredConnection, type StoreEnv } from "./store.ts";
import {
  ComposioConnections,
  ConnectionsBadArgument,
  ConnectionsExecuteFailed,
  ConnectionsOwnerRequired,
  ConnectionsRequestFailed,
  ConnectionsToolFailed,
  ConnectionsUnconfigured,
  connectionsFromEnv,
  requireOwner,
  toolkitSlug,
  type CatalogTool,
  type ConnectionsEnv,
} from "./provider.ts";

// ---------------------------------------------------------------------------
// THE STEP AND ITS OUTCOMES
// ---------------------------------------------------------------------------

/** The Worker bindings this file needs: the database the row is read from and
 *  the vendor key. Structurally satisfied by the Worker's `Env`. */
export interface ApiHandEnv extends StoreEnv, ConnectionsEnv {}

/** One step, described the way the router hands it over. */
export interface ApiHandStep {
  /** The owner ROW id. Re-validated at runtime — the brand is erased before
   *  this code runs, and a display name here is a step run against a
   *  stranger's account. It comes from the session or a stored row, never
   *  from a request body. */
  owner: OwnerId | string;
  /** The toolkit the connection row is keyed by. */
  toolkit: Toolkit;
  /** The tool the router chose. Must be a slug `tools(toolkit)` returned. */
  tool: string;
  /** The tool's arguments, a plain JSON object. NEVER logged. */
  args: Record<string, unknown>;
  /** The planner's declared effect, tightened here by the tool's own hints.
   *  A step with no declared effect is refused: silence licenses nothing. */
  effect: SideEffect;
  /** Which of the owner's accounts on this app, when they have more than one
   *  connected. Absent with two connected accounts is a refusal, not a guess. */
  alias?: AccountAlias | null;
  /** The caller's assertion that the owner confirmed THIS payload. Required
   *  for an irreversible effect; the hand cannot verify it, only demand it. */
  confirmed?: boolean;
}

/** Why the hand did not call the vendor's execute endpoint. A closed set, so
 *  the router can branch on it (nudge, browser, ask) without reading prose. */
export type ApiHandRefusal =
  | "owner_required"
  | "toolkit_required"
  | "tool_required"
  | "args_required"
  | "effect_required"
  | "not_connected"
  | "account_ambiguous"
  | "writes_not_enabled"
  | "confirmation_required"
  | "tool_unknown"
  | "catalog_unavailable"
  | "store_unavailable"
  | "unconfigured";

export interface ApiHandRefused {
  outcome: "refused";
  reason: ApiHandRefusal;
  /** A sentence for the audit line. Nothing branches on it, and it never
   *  carries an argument value. */
  detail: string;
  /** The effect the floors were applied to: the declared one, or the
   *  tightened one once the catalog had been read. Null when the refusal came
   *  before an effect could be validated. */
  effect: SideEffect | null;
  /** Whether the one permitted pre-execute vendor call — the catalog GET —
   *  happened before this refusal. The execute endpoint was NOT called; that
   *  is what "refused" means. */
  catalogRead: boolean;
}

export interface ApiHandRan {
  outcome: "ran";
  toolkit: Toolkit;
  /** The catalog's spelling of the slug, which is what went on the wire. */
  tool: string;
  /** The connected account the step ran against. */
  account: string;
  /** The effect after tightening — what the ledger should record. */
  effect: SideEffect;
  data: unknown;
  logId: string | null;
  ms: number;
}

export interface ApiHandFailed {
  outcome: "failed";
  toolkit: Toolkit;
  tool: string;
  account: string;
  effect: SideEffect;
  error: {
    /** The contract's kind: auth / rate / schema / other. */
    kind: ExecErrorKind;
    /** HTTP status; 0 for a transport failure or a 2xx whose body was the failure. */
    status: number;
    /** The vendor's error slug, or "". */
    token: string;
    /** Whether an UNCHANGED retry could plausibly work. Advice for the
     *  router, which owns the one rate-limit retry; this file never retries. */
    retryable: boolean;
    message: string;
  };
  /** Whether the step may have landed anyway. auth, rate and schema are the
   *  vendor's promise that nothing ran; everything else is unknown, and an
   *  unknown write is the router's "ask the owner" branch, never a re-run. */
  mayHaveLanded: boolean;
  ms: number;
}

export type ApiHandOutcome = ApiHandRefused | ApiHandRan | ApiHandFailed;

/** Seams for tests and for a caller that already holds a store or adapter.
 *  Production passes nothing and gets D1 and the isolate's memoised adapter. */
export interface ApiHandDeps {
  store?: ConnectionsStore;
  provider?: ComposioConnections;
  clock?: () => number;
}

// ---------------------------------------------------------------------------
// THE EFFECT LADDER — re-declared from the Two Hands contract, pinned by test.
// ---------------------------------------------------------------------------

export const SIDE_EFFECT_ORDER: Record<SideEffect, number> = {
  read: 0,
  write: 1,
  irreversible: 2,
};

/** The contract's `tightenSideEffect`, character for character: a hint may
 *  only make a step STRICTER. A tool that calls itself read-only cannot turn a
 *  declared write into a read. */
export function tightenSideEffect(planned: SideEffect, hint?: SideEffect | null): SideEffect {
  if (!hint) return planned;
  return SIDE_EFFECT_ORDER[hint] > SIDE_EFFECT_ORDER[planned] ? hint : planned;
}

/** The MCP-style hint tags the live catalog was measured to carry on
 *  2026-09-06 (provider.ts header has the per-tool receipt). Exact identifier
 *  matches against vendor tag strings — no word inside a description is read. */
export const READ_ONLY_HINT = "readOnlyHint";
export const DESTRUCTIVE_HINT = "destructiveHint";
export const CREATE_HINT = "createHint";
export const UPDATE_HINT = "updateHint";

/** What the tool says about its own effect, or null when it says nothing.
 *
 *  The strictest tag wins: `destructiveHint` is irreversible (spec page 31
 *  names deletions irreversible, and that tag is the vendor's spelling of
 *  "may delete"); `createHint` and `updateHint` are writes; `readOnlyHint`
 *  alone is a read. A row carrying `readOnlyHint` beside a write hint is
 *  contradicting itself and is read as the stricter of the two.
 *
 *  NULL IS NOT "READ". A toolkit whose rows carry no hint tags at all says
 *  nothing, and nothing tightens nothing — the planner's declaration stands,
 *  as the spec's "tightened by the tool's own metadata" requires. Reading
 *  silence as read-only would loosen; reading it as write would be this file
 *  inventing a fact about a tool nobody measured. */
export function sideEffectHint(tags: readonly string[]): SideEffect | null {
  let hint: SideEffect | null = null;
  for (const tag of tags) {
    if (tag === DESTRUCTIVE_HINT) return "irreversible";
    if (tag === CREATE_HINT || tag === UPDATE_HINT) hint = "write";
    else if (tag === READ_ONLY_HINT && hint === null) hint = "read";
  }
  return hint;
}

/** The contract's `apiFailureMayHaveLanded`, for the three kinds that are the
 *  vendor's promise nothing ran. Everything else is unknown. */
export function failureMayHaveLanded(kind: ExecErrorKind): boolean {
  return kind !== "auth" && kind !== "rate" && kind !== "schema";
}

// ---------------------------------------------------------------------------
// THE CATALOG CACHE — per adapter instance, so one isolate's owners share it
// and two adapters (two keys, two tests) never see each other's list.
// ---------------------------------------------------------------------------

/** How long a toolkit's tool list is trusted before it is fetched again. A
 *  tool the vendor removed inside this window costs one vendor 404, typed as
 *  `schema`; a tool the vendor added is unknown for at most this long. */
export const CATALOG_TTL_MS = 10 * 60 * 1000;

/** How many toolkits' lists one adapter keeps before forgetting all of them.
 *  Cleared whole rather than LRU, for the reason provider.ts gives for its
 *  session cache: the cost of a miss is one GET, the cost of an LRU is code. */
export const MAX_CACHED_CATALOGS = 200;

interface CachedCatalog {
  at: number;
  tools: CatalogTool[];
}

const catalogs = new WeakMap<ComposioConnections, Map<string, CachedCatalog>>();

async function catalogFor(
  provider: ComposioConnections,
  toolkit: Toolkit,
  now: number,
): Promise<CatalogTool[]> {
  let mine = catalogs.get(provider);
  if (!mine) {
    mine = new Map();
    catalogs.set(provider, mine);
  }
  const hit = mine.get(toolkit);
  if (hit && now - hit.at < CATALOG_TTL_MS) return hit.tools;
  const tools = await provider.tools(toolkit);
  if (mine.size >= MAX_CACHED_CATALOGS) mine.clear();
  mine.set(toolkit, { at: now, tools });
  return tools;
}

/** Forget every cached tool list for this adapter. For tests, and for a caller
 *  that has just learned the catalog changed. */
export function forgetCatalogs(provider: ComposioConnections): void {
  catalogs.delete(provider);
}

// ---------------------------------------------------------------------------
// STRUCTURAL HELPERS. None reads prose.
// ---------------------------------------------------------------------------

const EFFECTS: readonly SideEffect[] = ["read", "write", "irreversible"];

function isEffect(v: unknown): v is SideEffect {
  return typeof v === "string" && (EFFECTS as readonly string[]).includes(v);
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

/** The vendor's slugs are uppercase identifiers; a caller may not spell one
 *  identically. Case-folding an IDENTIFIER for comparison is plumbing — the
 *  spelling that goes on the wire is always the catalog's own. */
function sameSlug(a: string, b: string): boolean {
  return a.trim().toUpperCase() === b.trim().toUpperCase();
}

/** The one connected row this step runs against, or a refusal reason.
 *
 *  `rows` is already this owner's — the store refused anything else. A
 *  `needs_reconnect` row is not connected: its credential is dead and the
 *  spec's answer is a re-auth nudge, not an execute that 401s. Two connected
 *  rows and no alias is a refusal, not a guess: "If ambiguous, ask once and
 *  remember" is the asker's job, and the wrong account is a step run against
 *  the owner's work mail when they meant personal. */
function pickConnection(
  rows: readonly StoredConnection[],
  toolkit: Toolkit,
  alias: AccountAlias | null | undefined,
): { row: StoredConnection } | { reason: "not_connected" | "account_ambiguous"; detail: string } {
  const onApp = rows.filter((r) => r.toolkit === toolkit);
  const connected = onApp.filter((r) => r.status === "connected");
  const wanted = alias === undefined || alias === null
    ? connected
    : connected.filter((r) => r.alias === alias);
  if (wanted.length === 1) return { row: wanted[0]! };
  if (wanted.length === 0) {
    if (onApp.length === 0) {
      return { reason: "not_connected", detail: "no connection row exists for this owner and toolkit" };
    }
    if (connected.length === 0) {
      return {
        reason: "not_connected",
        detail: `the owner's ${onApp.length} row(s) for this toolkit are ${
          onApp.map((r) => r.status).join(", ")
        }, none connected`,
      };
    }
    return {
      reason: "not_connected",
      detail: `no connected account on this toolkit carries the alias ${JSON.stringify(alias)}`,
    };
  }
  return {
    reason: "account_ambiguous",
    detail: `${wanted.length} connected accounts on this toolkit and no alias to choose by`,
  };
}

/** A log line and an outcome, together, so no refusal goes unlogged. */
function refuse(
  who: string,
  reason: ApiHandRefusal,
  detail: string,
  effect: SideEffect | null,
  catalogRead: boolean,
): ApiHandRefused {
  console.log(`api hand: ${who} refused — ${reason}: ${detail}`);
  return { outcome: "refused", reason, detail, effect, catalogRead };
}

/** Error text for a log line: the class name and a bounded slice of the
 *  message. Adapter and store messages carry no argument values by
 *  construction; the bound is for the unknown throw. */
function describe(err: unknown): string {
  const name = (err as { name?: unknown })?.name;
  const message = (err as { message?: unknown })?.message;
  const head = typeof name === "string" && name ? name : "Error";
  const body = typeof message === "string" ? message : String(err ?? "");
  return `${head}: ${body}`.slice(0, 200);
}

// ---------------------------------------------------------------------------
// runStep — THE ENTRY POINT THE ROUTER CALLS
// ---------------------------------------------------------------------------

/**
 * Run one step on the API hand, or say why not.
 *
 * Order of checks, and why: the shape checks first because they cost nothing
 * and a malformed step must not reach a database read; the connection row
 * next because a refusal there is the common case (rule 2, "not connected:
 * browser now and a nudge") and must cost no vendor call; the write opt-in
 * before the catalog, so an unlicensed write is refused without the vendor
 * learning the step existed; the catalog last of the floors because it is the
 * one that costs a request; then the hint re-check, then the confirmation for
 * an irreversible effect, and only then the one execute.
 */
export async function runStep(
  env: ApiHandEnv,
  step: ApiHandStep,
  deps: ApiHandDeps = {},
): Promise<ApiHandOutcome> {
  const clock = deps.clock ?? (() => Date.now());
  const toolkit = toolkitSlug(step?.toolkit);
  const toolAsked = typeof step?.tool === "string" ? step.tool.trim() : "";
  const toolIsIdentifier = toolAsked.length > 0 && toolAsked.length <= 200 && !/\s/.test(toolAsked);

  // -- Shape. Nothing below runs on a step that is not one. -----------------
  //
  // THE LOG LABEL IS BUILT FROM VALIDATED VALUES ONLY. A caller that passed
  // an email as the owner, or a sentence as the tool, passed something that
  // must not be written down — the adapter's own refusal deliberately reports
  // the SHAPE of a bad owner id and never the value, and this label keeps
  // that promise. Until each part is validated it is a "?".
  let owner: OwnerId;
  try {
    owner = requireOwner("api hand", step?.owner);
  } catch (err) {
    return refuse(`? ${toolkit || "?"} ${toolIsIdentifier ? toolAsked : "?"}`, "owner_required", describe(err), null, false);
  }
  const who = `${owner} ${toolkit || "?"} ${toolIsIdentifier ? toolAsked : "?"}`;
  if (toolkit.length === 0) {
    return refuse(who, "toolkit_required", "no toolkit slug was given", null, false);
  }
  if (!toolIsIdentifier) {
    return refuse(who, "tool_required", "no tool slug was given, or it is not an identifier", null, false);
  }
  if (!isPlainObject(step.args)) {
    return refuse(who, "args_required", "arguments must be a plain JSON object", null, false);
  }
  try {
    JSON.stringify(step.args);
  } catch {
    return refuse(who, "args_required", "arguments are not JSON-serialisable", null, false);
  }
  if (!isEffect(step.effect)) {
    // A FLOOR. An undeclared effect is not a read; it is nobody having said
    // what this step touches, and the ladder's whole write rule hangs on that
    // declaration.
    return refuse(who, "effect_required", "the step declares no effect (read, write or irreversible)", null, false);
  }
  const declared: SideEffect = step.effect;

  // -- 1. The row, from D1 and never from the vendor. -----------------------
  const store = deps.store ?? createD1Store(env);
  let rows: StoredConnection[];
  try {
    rows = await store.connectionsForOwner(owner);
  } catch (err) {
    // "The database could not answer" is not "this owner connected nothing".
    return refuse(who, "store_unavailable", describe(err), declared, false);
  }
  const picked = pickConnection(rows, toolkit, step.alias);
  if ("reason" in picked) return refuse(who, picked.reason, picked.detail, declared, false);
  const row = picked.row;

  // -- 2. The write opt-in, on the declared effect, before any vendor call. --
  if (declared !== "read" && row.writes_enabled !== true) {
    return refuse(
      who,
      "writes_not_enabled",
      `the step is a ${declared} and this owner has not switched on changes for this app`,
      declared,
      false,
    );
  }

  // -- 3. The allow-list. The one catalog GET. ------------------------------
  const provider = deps.provider ?? connectionsFromEnv(env);
  let catalog: CatalogTool[];
  try {
    catalog = await catalogFor(provider, toolkit, clock());
  } catch (err) {
    if (err instanceof ConnectionsUnconfigured) {
      return refuse(who, "unconfigured", describe(err), declared, false);
    }
    return refuse(who, "catalog_unavailable", describe(err), declared, true);
  }
  const tool = catalog.find((t) => sameSlug(t.slug, toolAsked));
  if (tool === undefined) {
    return refuse(
      who,
      "tool_unknown",
      `the vendor lists ${catalog.length} tool(s) for this toolkit and the one asked for is not among them`,
      declared,
      true,
    );
  }

  // -- 4. The hint tightens; floor 2 again on the tightened effect. ---------
  const effect = tightenSideEffect(declared, sideEffectHint(tool.tags));
  if (effect !== "read" && row.writes_enabled !== true) {
    return refuse(
      who,
      "writes_not_enabled",
      `the step was declared a ${declared} but the tool's own metadata makes it a ${effect}, and this `
        + "owner has not switched on changes for this app",
      effect,
      true,
    );
  }
  if (effect === "irreversible" && step.confirmed !== true) {
    return refuse(
      who,
      "confirmation_required",
      "an irreversible step runs only after the owner has confirmed the exact payload, and the "
        + "caller did not say they had",
      effect,
      true,
    );
  }

  // -- The one execute. ----------------------------------------------------
  const startedAt = clock();
  const elapsed = (): number => Math.max(0, Math.round(clock() - startedAt));
  const account = row.connected_account_id;
  try {
    const receipt = await provider.execute(owner, tool.slug, step.args, account);
    const ms = elapsed();
    console.log(`api hand: ${who} ran — ${effect}, ${ms}ms`);
    return {
      outcome: "ran",
      toolkit,
      tool: tool.slug,
      account,
      effect,
      data: receipt.data,
      logId: receipt.logId,
      ms,
    };
  } catch (err) {
    const ms = elapsed();
    if (err instanceof ConnectionsBadArgument || err instanceof ConnectionsOwnerRequired) {
      // Refused by the adapter's own guards before a byte left. Cannot happen
      // after the checks above; reported honestly as a refusal if it does.
      return refuse(who, err instanceof ConnectionsOwnerRequired ? "owner_required" : "args_required", describe(err), effect, true);
    }
    let error: ApiHandFailed["error"];
    if (err instanceof ConnectionsExecuteFailed) {
      error = { kind: err.kind, status: err.status, token: err.token, retryable: err.retryable, message: err.message };
    } else if (err instanceof ConnectionsToolFailed) {
      error = { kind: err.kind, status: err.status, token: err.token, retryable: false, message: err.message };
    } else if (err instanceof ConnectionsRequestFailed) {
      // Transport, or no fetch: the request may have left. `other`.
      error = { kind: "other", status: err.status, token: "", retryable: err.retryable, message: err.message };
    } else {
      // A shape refusal on the reply, or something nobody typed. The vendor
      // was called; the outcome is unknown.
      error = { kind: "other", status: 0, token: "", retryable: false, message: describe(err) };
    }
    console.log(`api hand: ${who} failed — ${error.kind} HTTP ${error.status}${error.token ? ` ${error.token}` : ""}`);
    return {
      outcome: "failed",
      toolkit,
      tool: tool.slug,
      account,
      effect,
      error,
      mayHaveLanded: failureMayHaveLanded(error.kind),
      ms,
    };
  }
}
