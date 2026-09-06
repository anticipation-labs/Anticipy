/**
 * src/connections/nudge.ts — THE ASK. The half of connecting that reaches a
 * person: minting our own single-use link and sending the one text that carries
 * it, at a moment this owner has licensed.
 *
 * WHY THIS FILE EXISTS AT ALL, and it is not a small reason. Until it was
 * written, NOTHING in this repository ever inserted a `connect_links` row.
 * routes/connect.ts can read, redeem and complete a token; store.ts can persist
 * one; words.ts can audit the copy that carries one. No token was ever created,
 * so `GET /c/{token}` had nothing to look up and no person could connect
 * anything. The chain was: mint → text → tap → vendor → callback, and the first
 * link was missing.
 *
 * THE FOUR RULES THIS FILE IS ACCOUNTABLE FOR, from the spec ("Connections: how
 * Anticipy asks, learns, and never says Composio", 2026-09-05, pages 20-31):
 *
 *   1. EVERY LINK IS OURS. `api.anticipy.ai/c/{token}`, single use, ten
 *      minutes, bound to one owner and one toolkit. The VENDOR's link is minted
 *      only when the token is redeemed (routes/connect.ts `connectPageGo`),
 *      because the vendor's own link also lives ten minutes — four were sent
 *      ahead of a tap on 2026-09-05 and four were dead on arrival
 *      (research/2026-09-05-composio-connections.md, item 3).
 *   2. THE RAW TOKEN IS NEVER STORED AND NEVER LOGGED. The store holds
 *      sha256(token) in hex; the raw token exists in exactly one place, the URL
 *      this file returns, and from there in exactly one text message.
 *   3. THE ASK IS A PRIVILEGE, NOT A DEFAULT. `shouldAsk` is a FLOOR: anything
 *      that is not exactly `"ask"` sends nobody anything. A missing input is
 *      `no-verdict` and silence, because if unknown meant "go ahead" then the
 *      first owner whose local hour failed to load gets a connect link at 3am.
 *   4. THE PERSON NEVER READS THE VENDOR'S NAME, and never "authorize",
 *      "permissions", "integration", "API" or "OAuth". A model writes the text;
 *      this file contains it and REFUSES a draft that breaks a rule rather than
 *      repairing one. A mangled ask is worse than no ask: an ask is the single
 *      interruption this product gets per owner per week, and spending it on a
 *      broken message spends it for nothing.
 *
 * HARNESS-LAWS LAW 1. Nothing here decides what a human's words MEAN.
 *   - `NudgeTrigger` is a closed enum of things that HAPPENED — a step routed
 *     to the browser, a Mac lid closing — established by the caller from
 *     events. `TRIGGER_SCORE` ranks those event types; a number attached to
 *     "the lid is shut" is a rank over an enum, not a reading of prose.
 *   - Which app a person meant is a model's answer (`ToolkitJudge` in the
 *     contract) and arrives here as a slug this file never chose. No branch
 *     below compares a slug against a literal — NO APP IS HARDCODED, made
 *     structural rather than promised, and the test sweeps invented slugs
 *     through every path to prove it.
 *   - The word lists in `askMessage` read text WE are about to send, drafted by
 *     OUR model, and the only outcome any of them can produce is "do not send
 *     this draft". That is a style gate on our own copy — a CEILING whose
 *     failure mode is silence — which is the same argument words.ts makes in
 *     its own header, at greater length.
 *   - Clocks, hours, hashes and segment arithmetic are senses and transport.
 *
 * WHAT IS PORTED AND FROM WHERE.
 *   - The policy (`shouldAsk`, `recordDecline`, the constants) is ported from
 *     spike/two-hands/src/connections/policy.ts, which went through an
 *     adversarial pass. Behaviour is carried across, not redesigned. The
 *     constants are RE-DECLARED rather than imported, exactly as store.ts,
 *     provider.ts and words.ts re-declare theirs, so the deployed Worker holds
 *     no runtime edge into the spike tree; test/connections-nudge.test.ts reads
 *     contract.ts's own source and goes red if the two ever disagree.
 *   - `maturedBySilence` is new, and it is a REFACTOR of the spike rather than
 *     an addition: the spike computed the 72-hour silence decline inside
 *     `shouldAsk` and threw it away, so a caller that then wrote its own
 *     "asked" row lost the decline and could ask that owner forever at level 0.
 *     One function, called by the verdict and by the writer.
 *
 * THE ONE PLACE THIS FILE DUPLICATES ANOTHER, DELIBERATELY AND WITH AN EXPIRY.
 * words.ts `askText` is the shared containment and this file would call it, but
 * words.ts pins `CONNECT_LINK_PREFIX = "https://anticipy.ai/c/"` while the
 * Worker's only route is `api.anticipy.ai` (routes/connect.ts CONNECT_URL_BASE,
 * with the measurement beside it: on 2026-09-06 the apex answered 301 and www
 * answered 307, so neither reaches this code). `askText` therefore refuses
 * every link that actually resolves, which would make this feature ship dead.
 * So `askMessage` below is `askText` with ONE difference — the link is checked
 * against the base the mint actually used, rather than against a constant
 * naming a host we are not on. It returns words.ts's own `AskResult` and
 * `WordsRefusalCause` so it is a drop-in. THE DAY THE TWO CONSTANTS AGREE,
 * DELETE `askMessage` AND CALL `askText`: the check named
 * "askMessage exists only because the two link constants disagree" in
 * test/connections-nudge.test.ts goes RED on that day and says so.
 *
 * WHERE THE SWEEP IS CALLED. `connectNudgeSweep(env)` is the entry point for
 * the five-minute Cron Trigger. It is NOT wired here — src/cron.ts belongs to
 * another agent this session. See the note above `connectNudgeSweep`.
 */

/// <reference types="@cloudflare/workers-types" />

// TYPES ONLY from the contract, which is fixed and is not edited by this file.
// `import type` is erased before this file is bundled or run, so the deployed
// Worker carries no dependency on the spike tree while the shapes stay the
// contract's own declarations rather than a second copy of them.
import type {
  AccountAlias,
  ConnectNudge,
  NudgeContext,
  NudgeDecision,
  NudgeTrigger,
  NudgeVerdict,
  OwnerId,
  Toolkit,
  ToolkitMeta,
} from "../../../../spike/two-hands/src/connections/contract.ts";

import { ownerId } from "./store.ts";
import type { StoredLink } from "./store.ts";
import {
  CONNECT_URL_BASE,
  LINK_TTL_MS,
  TOKEN_CHARS,
  connectUrl,
  tokenFingerprint,
  tokenHandle,
} from "../routes/connect.ts";
import {
  FORBIDDEN_TERMS,
  MAX_ASK_SEGMENTS,
  STIFF_FORMS,
  smsShape,
} from "./words.ts";
import type {
  AskEvidence,
  AskResult,
  AskWriter,
  Refusal,
  WordsRefusalCause,
} from "./words.ts";
import { sendText } from "../messaging.ts";
import type { MessagingEnv } from "../messaging.ts";

export { LINK_TTL_MS };
export type { AccountAlias, ConnectNudge, NudgeTrigger, OwnerId, Toolkit };

// ---------------------------------------------------------------------------
// THE CONSTANTS. Every one of them is the contract's, re-declared for the
// reason in the header and pinned to contract.ts's source by the test.
// ---------------------------------------------------------------------------

const HOUR_MS = 60 * 60 * 1000;
const DAY_MS = 24 * HOUR_MS;

/** Quiet hours, owner-local: 22:00 is quiet, 08:00 is not. Closed at the start,
 *  open at the end — both ends are pinned, because an off-by-one here is an
 *  hour of somebody's sleep every night for as long as nobody checks. */
export const QUIET_HOURS_START = 22;
export const QUIET_HOURS_END = 8;

/** The right-time score per the spec. Config keyed on a closed enum of things
 *  that happened, never on anything anybody said. */
export const TRIGGER_SCORE: Record<NudgeTrigger, number> = {
  laptop_closed: 1.0,
  user_named_it: 0.9,
  in_task: 0.8,
  onboarding: 0.7,
  repeated_use: 0.6,
};

/** Ask only if the moment scores above the snooze level's threshold. Level 3
 *  is +Infinity — it stops, and only the owner reopening it counts. */
export const LEVEL_THRESHOLD: Record<0 | 1 | 2 | 3, number> = {
  0: 0.5,
  1: 0.8,
  2: 0.95,
  3: Number.POSITIVE_INFINITY,
};

/** Snooze after each decline, in days. 14, then 45, then never. */
export const SNOOZE_DAYS: Record<1 | 2 | 3, number> = { 1: 14, 2: 45, 3: 3650 };

export const GLOBAL_ASK_INTERVAL_DAYS = 7;
export const SILENCE_IS_A_SOFT_NO_HOURS = 72;
export const ONBOARDING_SKIP_SNOOZE_DAYS = 7;

/** The contract's closed enums AT RUN TIME. `--experimental-strip-types` and
 *  the Worker's bundler both DELETE the annotations above, so a row read from
 *  D1 with a state of `"declined_l2"` would fall through every `===` below and
 *  land on `ask` — re-asking somebody who already said no twice. Membership
 *  checks over enums declared next door; not a word list reading anybody. */
const NUDGE_STATES: readonly string[] = [
  "never_asked",
  "asked",
  "declined",
  "connected",
  "needs_reconnect",
];

/** The state machine's level-2 allowlist, verbatim from page 24: "only in_task
 *  or laptop_closed may ever ask again, never repeated_use". */
const LEVEL_2_TRIGGERS: readonly string[] = ["in_task", "laptop_closed"];

/**
 * The spec's own ceiling on one ask, in characters.
 *
 * SUBSUMED TODAY, AND KEPT ON PURPOSE — the same argument words.ts makes for
 * its level-2 allowlist. The real ceiling is the carrier's: two GSM-7 segments
 * hold 306 septets and two UCS-2 segments hold 134 units, so nothing 320
 * characters long has ever reached this line. It stays because it is the
 * number the spec states, and because `MAX_ASK_SEGMENTS` is declared config —
 * the day somebody raises it to three, this is the only thing between an owner
 * and a five-part text. The test pins that it is currently subsumed, so it
 * cannot rot into a lie about what is enforced.
 */
export const ASK_MESSAGE_MAX_CHARS = 320;

/**
 * How many asks one sweep may send.
 *
 * Each send is a subrequest and a tick has a budget (cron.ts header, item 3).
 * More than this in five minutes is also not a product that asks rarely; it is
 * a product mid-incident, and the right behaviour mid-incident is to send less,
 * not more. What is skipped is skipped, not queued: the next tick is five
 * minutes away and the moment it would have named will have passed.
 */
export const MAX_ASKS_PER_SWEEP = 20;

// ---------------------------------------------------------------------------
// THE SEAM — what this file must NOT own
// ---------------------------------------------------------------------------
// Four things belong to other modules and arrive injected: the store (D1 and
// its migration), the catalog (the vendor client), the model that writes the
// text, and the facts about the MOMENT. A file that reached into any of them
// would own the whole feature; a file that guessed at any of them would be the
// 3am connect link with extra steps.

export interface NudgeEnv extends MessagingEnv {
  /** Present in production (index.ts / cron.ts Env). Optional here because the
   *  store is injected and this file never queries D1 itself. */
  DB?: D1Database;
  /** Our own origin for the link a person receives. Unset means the production
   *  constant. DELIBERATELY NOT DERIVED FROM A REQUEST — see routes/connect.ts. */
  CONNECT_BASE_URL?: string;
}

/** The subset of `ConnectionsStore` an ask needs. Narrowed on purpose: this
 *  file can create a link and record an ask, and cannot touch `connections`,
 *  cannot spend a token and cannot record a signal. `createD1Store(env)`
 *  satisfies it structurally. */
export interface NudgeStore {
  readNudge(user: OwnerId | string, toolkit: Toolkit): Promise<ConnectNudge | null>;
  nudgesForOwner(user: OwnerId | string): Promise<ConnectNudge[]>;
  putNudge(row: ConnectNudge): Promise<void>;
  /** Insert. MUST reject a handle that already exists rather than overwrite. */
  put(row: StoredLink): Promise<void>;
}

/**
 * The facts about THIS moment, stated by the caller.
 *
 * Not one of them is derivable here, and every one of them is a floor input:
 * absent, the answer is `no-verdict` and nobody is texted. `localHour` in
 * particular has no safe default — UTC is how somebody in Auckland gets a
 * connect link at 2am from a server that thought it was lunchtime.
 */
export interface NudgeMoment {
  /** Owner-local hour, 0-23. */
  localHour: number;
  /** A nudge NEVER lands mid-step. */
  taskInFlight: boolean;
  /** And never before the task's own result. */
  resultDelivered: boolean;
  /** How many of this owner's tasks would have used the connection. Zero holds:
   *  an ask with no evidence is an advertisement. */
  tasksThatWouldHaveUsedIt: number;
  /** Which of the owner's accounts, when the caller knows. `null` is the honest
   *  and commonest value and is never turned into a guess. */
  alias?: AccountAlias | null;
  /** What just happened, in the system's own words, for the model to draw the
   *  why-sentence from. Passed to the writer; nothing here pattern-matches it. */
  whatHappened?: string;
  /** What the browser hand cost, in ms. */
  browserMs?: number;
}

/** One (owner, app, moment) the sweep should consider. */
export interface NudgeCandidate {
  owner: OwnerId | string;
  toolkit: Toolkit;
  trigger: NudgeTrigger;
}

export interface NudgeDeps {
  store: NudgeStore;
  /** Name, logo, description and scopes, read at RUN TIME so a new app in the
   *  catalog is a new app in Anticipy with zero code here. */
  catalog: { toolkit(slug: Toolkit): Promise<ToolkitMeta> };
  /** ONE question, asked on its own: "write the one text that asks." */
  write: AskWriter;
  /** The moment, or null when the caller cannot establish it. */
  moment(
    owner: OwnerId, toolkit: Toolkit, trigger: NudgeTrigger, now: number,
  ): Promise<NudgeMoment | null>;
  /** Where the text goes. Returning null or "" is an owner with no number, and
   *  that is a hold, never a guess at another column. */
  phone(owner: OwnerId): Promise<string | null>;
  /**
   * WHO IS DUE, for the sweep. Not derivable here: it is a question about
   * `app_usage_signals`, about which steps just fell back to the browser, and
   * about whether a laptop is shut — three things this file does not and must
   * not read. A sweep with no `due` asks nobody, which is the correct amount of
   * asking for a Worker that cannot tell who needs anything.
   */
  due(now: number): Promise<NudgeCandidate[]>;
  /** Injectable clock. Tests own time; production passes nothing. */
  now?(): number;
  /** Our link origin. Defaults to `env.CONNECT_BASE_URL`, then to
   *  `CONNECT_URL_BASE`, matching routes/connect.ts's own precedence exactly —
   *  a mint and a callback built from different bases is a link that 404s. */
  baseUrl?: string;
}

/**
 * THE WIRING SEAM, and why an unwired sweep is silent rather than loud.
 *
 * routes/connect.ts answers 503 when nothing is wired, because a person is
 * standing in front of that page waiting. Nobody is waiting on this one: an
 * unwired sweep has no owner to disappoint, and the only honest behaviour is to
 * send nothing and say so in the log with the name of the missing wiring. It
 * never invents a store, a catalog or a writer.
 */
export type NudgeWiring = (env: NudgeEnv) => NudgeDeps | null;

let WIRING: NudgeWiring = () => null;
let WIRED = false;

export function installNudgeWiring(wiring: NudgeWiring): void {
  WIRING = wiring;
  WIRED = true;
}

/** For a gate leg and for the suite: has anything been wired at all? A Worker
 *  that answers `false` here can never send a connect ask, and the honest place
 *  to notice that is a deploy check, not an owner who was never asked. */
export function nudgeWiringInstalled(): boolean {
  return WIRED;
}

// ===========================================================================
// 1. THE LINK
// ===========================================================================

/** What the caller gets back. NOT the token, and not the handle: the URL is the
 *  one carrier of the raw token, and it goes into one text. */
export interface MintedLink {
  /** `https://api.anticipy.ai/c/{token}` — what the person receives. */
  url: string;
  expires_at: number;
  /** What a log line MAY say about this link: the first 12 hex characters of
   *  its handle. Enough to correlate two lines, useless for redeeming one. */
  fingerprint: string;
}

/**
 * 32 bytes of crypto random, base64url, unpadded: 43 characters.
 *
 * `TOKEN_CHARS` in routes/connect.ts is that 43, and the route parser and the
 * well-formedness guard both depend on it — so the length is asserted here
 * rather than assumed. A 44-character token means somebody re-encoded it, and
 * the failure would be a link that parses as no route at all: a 404 in
 * somebody's message thread, forever, with nothing in a log to say why.
 */
function newToken(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  const token = btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  if (token.length !== TOKEN_CHARS) {
    throw new Error(
      `minted a ${token.length}-character connect token; routes/connect.ts routes exactly `
        + `${TOKEN_CHARS}, so this link would 404 in somebody's messages`,
    );
  }
  return token;
}

/** The base the link is built on. Same precedence as routes/connect.ts's own
 *  `wired.baseUrl ?? env.CONNECT_BASE_URL ?? CONNECT_URL_BASE`, because a link
 *  minted on one base and a callback built on another is a broken connect. */
function baseOf(env: NudgeEnv | null | undefined, deps?: NudgeDeps | null): string {
  return deps?.baseUrl ?? env?.CONNECT_BASE_URL ?? CONNECT_URL_BASE;
}

/**
 * Mint one link: single use, ten minutes, bound to this owner and this app.
 *
 * THE RAW TOKEN IS NEVER WRITTEN DOWN. `connect_links` holds sha256(token) in
 * hex and nothing else — D1 rows end up in backups, in `wrangler d1 execute`
 * output and in whatever a debugging session pastes into a terminal, so a raw
 * single-use bearer token at rest means one database read is a live link for
 * every owner holding one. It is not logged either: the log line carries
 * `fingerprint`, which is 12 hex characters of the HANDLE and cannot be
 * redeemed. The token exists in this function's locals and in the returned URL.
 *
 * IT THROWS RATHER THAN RETURNING NULL. A mint that cannot happen is a wiring
 * or a schema fault (`ConnectionsSchemaMissing` names the migration), and it
 * must reach an operator. `sendConnectAsk` catches it, so no sweep dies of it.
 */
export async function mintConnectLink(
  env: NudgeEnv,
  owner: OwnerId | string,
  toolkit: Toolkit,
  alias: AccountAlias | null = null,
  injected?: NudgeDeps | null,
): Promise<MintedLink> {
  const deps = injected ?? WIRING(env);
  if (!deps || !deps.store || typeof deps.store.put !== "function") {
    throw new Error(
      "no connect-link store wired: a link cannot be minted without somewhere to bind it, "
        + "and a link nobody bound is a token that redeems to nothing. See installNudgeWiring().",
    );
  }
  // The owner ROW id, checked by a CALL because the brand is erased before this
  // runs. A display name reaching here binds the connection to the wrong
  // person, which is the worst failure this product has and has happened once.
  const who = ownerId(typeof owner === "string" ? owner : String(owner ?? ""));
  const slug = checkedSlug(toolkit);

  const now = deps.now ? deps.now() : Date.now();
  const token = newToken();
  const row: StoredLink = {
    token_handle: await tokenHandle(token),
    user_id: who,
    toolkit: slug,
    alias: alias ?? null,
    expires_at: now + LINK_TTL_MS,
    used_at: null,
    completed_at: null,
  };
  await deps.store.put(row);

  return {
    url: connectUrl(token, baseOf(env, deps)),
    expires_at: row.expires_at,
    fingerprint: await tokenFingerprint(token),
  };
}

/** A slug as stored. Case and padding are plumbing; NO mapping between
 *  different slugs, ever — `google_drive` and `google-drive` stay two apps,
 *  because a slug is a vendor's primary key and guessing they are the same
 *  connects the wrong one. Identical rule to store.ts `checkedToolkit`. */
function checkedSlug(raw: unknown): Toolkit {
  const slug = typeof raw === "string" ? raw.trim().toLowerCase() : "";
  if (slug === "") {
    throw new Error(`a connect link needs a toolkit slug; got ${JSON.stringify(raw)}`);
  }
  return slug;
}

// ===========================================================================
// 2. THE POLICY — ported from spike/two-hands/src/connections/policy.ts
// ===========================================================================

/**
 * WHOSE ROW THIS IS, and about what — stated by the caller, because nothing in
 * the inputs can establish it.
 *
 * THE HOLE THIS CLOSES. `whatIsMissing` checks that `nudge.user_id` has the
 * SHAPE of an owner row id; without this argument it has nothing to compare it
 * against, so a perfectly well-formed row belonging to somebody else reads
 * cleanly and asks cleanly. A D1 read bound to the wrong variable, a cache
 * keyed by the previous request, or a batch loop reusing the last iteration's
 * id would each send this owner a connect link about another person's app.
 */
export interface AskingFor {
  owner: OwnerId | string;
  /** Optional because a caller sweeping an owner's rows has no single answer to
   *  state. The owner half is never optional. */
  toolkit?: Toolkit | null;
}

function slugOf(raw: unknown): string {
  return typeof raw === "string" ? raw.trim().toLowerCase() : "";
}

function hold(reason: string): NudgeVerdict {
  return { decision: "hold", reason };
}
function noVerdict(reason: string): NudgeVerdict {
  return { decision: "no-verdict", reason };
}

function isInt(x: unknown): boolean {
  return typeof x === "number" && Number.isInteger(x);
}

/** `null` is an ANSWER ("looked, nothing there"); `undefined` is "did not
 *  look". Anything else is a malformed row. */
function isNullableTimestamp(x: unknown): boolean {
  return x === null || (typeof x === "number" && Number.isFinite(x));
}

/**
 * Everything `shouldAsk` needs and did not get, in one sentence, or null when
 * the inputs are complete. Kept as one function so "what would make this
 * decidable" is answerable by reading it, and so that adding an input without
 * teaching this function about it shows up as a hole rather than as a default.
 */
function whatIsMissing(
  nudge: ConnectNudge,
  ctx: NudgeContext,
  asking: AskingFor | null | undefined,
): string | null {
  if (nudge === null || typeof nudge !== "object") {
    // An absent nudge row is not "never asked". It is a read that failed, or a
    // row for an owner whose D1 shard was unreachable — and treating that as
    // never_asked re-asks somebody who declined three times, the one outcome
    // the level ladder exists to make impossible. The CALLER distinguishes
    // "the read succeeded and there is no row" (a fresh owner: see
    // `freshNudge`) from "the read failed"; from in here they look identical.
    return "no nudge record: a missing row is not a fresh owner";
  }
  if (ctx === null || typeof ctx !== "object") {
    return "no moment to judge: without a context there is no such thing as a good time";
  }

  let expected: string;
  try {
    expected = ownerId((asking ?? ({} as AskingFor)).owner as unknown as string);
  } catch {
    return "nobody said whose nudge this is: an ask needs the owner it would be sent to, as a ROW id";
  }

  try {
    ownerId(nudge.user_id as unknown as string);
  } catch {
    return `nudge row has no owner ROW id (got ${JSON.stringify(nudge.user_id)}): a name cannot be asked`;
  }

  // AND THEY MUST BE THE SAME PERSON. Two well-formed ids that disagree is the
  // SWAP: a row that reads perfectly and belongs to somebody else.
  if (String(nudge.user_id) !== expected) {
    return `this nudge row belongs to another owner (row ${JSON.stringify(nudge.user_id)}, `
      + `asking for ${JSON.stringify(expected)})`;
  }

  const named = (asking as AskingFor).toolkit;
  if (named !== undefined && named !== null) {
    const want = slugOf(named);
    if (want === "") {
      return `the caller named an app that is not a slug: ${JSON.stringify(named)}`;
    }
    // Applying one app's decline history to another silences a nudge nobody
    // refused, or re-asks somebody who already said no.
    if (slugOf(nudge.toolkit) !== want) {
      return `this nudge row is about a different app (row ${JSON.stringify(nudge.toolkit)}, `
        + `asking about ${JSON.stringify(named)})`;
    }
  }

  if (!NUDGE_STATES.includes(nudge.state as unknown as string)) {
    return `unreadable nudge state ${JSON.stringify(nudge.state)}`;
  }
  if (!isInt(nudge.level) || (nudge.level as number) < 0 || (nudge.level as number) > 3) {
    return `unreadable decline level ${JSON.stringify(nudge.level)}`;
  }
  if (nudge.state === "declined" && nudge.level === 0) {
    // Read as level 0 it re-asks at the next trigger, ignoring a "no" this
    // system was told and recorded.
    return "row says declined but level is 0: the ladder was not advanced, so the decline "
      + "cannot be honoured";
  }
  if (nudge.trigger !== null && !Object.hasOwn(TRIGGER_SCORE, nudge.trigger as unknown as string)) {
    return `unreadable trigger on the row: ${JSON.stringify(nudge.trigger)}`;
  }
  if (!isNullableTimestamp(nudge.sent_at)) return "unreadable sent_at on the nudge row";
  if (!isNullableTimestamp(nudge.acted_at)) return "unreadable acted_at on the nudge row";
  if (!isNullableTimestamp(nudge.snooze_until)) return "unreadable snooze_until on the nudge row";

  if (typeof ctx.now !== "number" || !Number.isFinite(ctx.now)) {
    return "no usable clock";
  }
  // `Object.hasOwn`, not `TRIGGER_SCORE[t] !== undefined`: a trigger of
  // "constructor" reaches the prototype and comes back truthy.
  if (typeof ctx.trigger !== "string" || !Object.hasOwn(TRIGGER_SCORE, ctx.trigger)) {
    return `unknown trigger ${JSON.stringify(ctx.trigger)}: no moment, no score, no ask`;
  }
  if (!isInt(ctx.localHour) || ctx.localHour < 0 || ctx.localHour > 23) {
    return `unknown owner-local hour ${JSON.stringify(ctx.localHour)}: cannot tell 2am from 2pm`;
  }
  if (typeof ctx.taskInFlight !== "boolean") {
    return "unknown whether a step is in flight";
  }
  if (typeof ctx.resultDelivered !== "boolean") {
    return "unknown whether the owner has their result yet";
  }
  if (!isInt(ctx.tasksThatWouldHaveUsedIt) || ctx.tasksThatWouldHaveUsedIt < 0) {
    return `unreadable evidence count ${JSON.stringify(ctx.tasksThatWouldHaveUsedIt)}`;
  }
  if (!isNullableTimestamp(ctx.lastAskAnyAppAt)) {
    // `undefined` means the caller never read the ask history. Collapsing it
    // into `null` ("never asked anyone anything") is how an owner who just ran
    // three browser tasks gets three connect texts in one minute.
    return "ask history was not read; refusing to guess at the 7-day cap";
  }
  return null;
}

/**
 * The record as it stands AFTER a decline, including the snooze the spec owes
 * this owner. Pure: it returns a new row and mutates nothing.
 *
 * `how` is not decoration. "They tapped skip" and "they never answered" are
 * different facts about a person; they are the difference between `acted_at`
 * set and `acted_at` null, and the spec's timers get tuned from that log. A
 * silent decline that stamps `acted_at` claims an action nobody took.
 */
export function recordDecline(
  nudge: ConnectNudge,
  at: number,
  how: "said_no" | "silence",
): ConnectNudge {
  const level = Math.min(nudge.level + 1, 3) as 1 | 2 | 3;
  // The onboarding exception, from the spec's own constant: somebody skipping a
  // card during setup has refused a form, not an app. It applies once, at level
  // 1 — a second decline is a second decline whatever the first one was.
  const days =
    level === 1 && nudge.trigger === "onboarding" ? ONBOARDING_SKIP_SNOOZE_DAYS : SNOOZE_DAYS[level];
  return {
    ...nudge,
    state: "declined",
    level,
    snooze_until: at + days * DAY_MS,
    acted_at: how === "said_no" ? at : null,
  };
}

/**
 * The row as it stands once silence has matured into a decline.
 *
 * 72 hours of silence IS an answer, just a quieter one, and the spec counts it
 * as a decline. Without it the ladder has no terminal state for the owner who
 * never replies: they sit in `asked` forever and every trigger looks fresh.
 *
 * THE SNOOZE STARTS WHEN THE SILENCE MATURED, not at `now` — otherwise a policy
 * consulted a month late restarts a 14-day clock that has already run.
 *
 * EXPORTED, AND THIS IS THE POINT OF EXTRACTING IT. The spike computed this
 * inside `shouldAsk` and threw the result away. `sendConnectAsk` then writes a
 * row saying "asked", and if it wrote `{...theRowItRead, state: "asked"}` the
 * decline would be lost: the owner who has ignored three asks would still be at
 * level 0 and would be asked forever. One function, two callers, one answer.
 */
export function maturedBySilence(nudge: ConnectNudge, now: number): ConnectNudge {
  if (nudge?.state !== "asked") return nudge;
  if (!isNullableTimestamp(nudge.sent_at) || nudge.sent_at === null) return nudge;
  if (nudge.acted_at !== null) return nudge;
  const softNoAt = nudge.sent_at + SILENCE_IS_A_SOFT_NO_HOURS * HOUR_MS;
  if (now < softNoAt) return nudge;
  return recordDecline(nudge, softNoAt, "silence");
}

/**
 * MAY WE ASK? Four states, because "no" and "nobody could tell" are different
 * facts and a boolean carries two of three.
 *
 * Pure, synchronous, and it never throws: a policy that throws is a policy
 * every caller wraps in a try/catch, and the only honest thing to do in that
 * catch is what this function already does — decline to ask.
 */
export function shouldAsk(
  nudge: ConnectNudge,
  ctx: NudgeContext,
  asking: AskingFor | null | undefined,
): NudgeVerdict {
  // ---- 0. NO GUESSING -----------------------------------------------------
  const missing = whatIsMissing(nudge, ctx, asking);
  if (missing !== null) return noVerdict(missing);

  // ---- 1. Nothing to ask about -------------------------------------------
  if (nudge.state === "connected") {
    // `hold`, not `never-again`: the very next transition is
    // connected -> expired -> needs_reconnect, and a row marked never-again is
    // a row nothing ever re-opens.
    return hold("this owner already has this app connected");
  }

  // ---- 2. An ask is already out ------------------------------------------
  let record = nudge;
  if (nudge.state === "asked") {
    if (nudge.sent_at === null) {
      return noVerdict(
        "row says asked but has no sent_at: cannot tell a fresh ask from a stale one",
      );
    }
    if (nudge.acted_at !== null) {
      return noVerdict("row says asked but acted_at is set: the answer was never recorded");
    }
    const softNoAt = nudge.sent_at + SILENCE_IS_A_SOFT_NO_HOURS * HOUR_MS;
    if (ctx.now < softNoAt) {
      // A second ask while the first is still open is the product talking over
      // itself. Nothing changed except that we ran another task.
      const hours = Math.floor((ctx.now - nudge.sent_at) / HOUR_MS);
      return hold(
        `an ask sent ${hours}h ago is still open (silence becomes a no at `
          + `${SILENCE_IS_A_SOFT_NO_HOURS}h)`,
      );
    }
    record = maturedBySilence(nudge, ctx.now);
  }

  const reconnect = nudge.state === "needs_reconnect";

  // ---- 3. The end of the ladder ------------------------------------------
  if (!reconnect && record.level === 3) {
    // Checked BEFORE the moment floors on purpose: an owner who is done being
    // asked should read "stop", not "quiet hours" — the caller may use
    // `never-again` to stop scheduling this row at all, and a `hold` invites it
    // back tomorrow.
    return {
      decision: "never-again",
      reason: "declined three times: only the owner reopening this counts",
    };
  }

  // ---- 4. The moment floors ----------------------------------------------
  if (ctx.taskInFlight) {
    return hold("a step is still running; an ask must never land mid-step");
  }
  if (!ctx.resultDelivered) {
    // An ask that arrives INSTEAD OF the answer spends the exact trust the
    // answer was about to earn.
    return hold("the task result has not been delivered yet");
  }
  if (ctx.localHour >= QUIET_HOURS_START || ctx.localHour < QUIET_HOURS_END) {
    return hold(
      `${ctx.localHour}:00 owner-local is inside quiet hours `
        + `(${QUIET_HOURS_START}:00-${QUIET_HOURS_END}:00)`,
    );
  }
  if (ctx.tasksThatWouldHaveUsedIt === 0) {
    // Zero is a hold ALWAYS: there is no trigger strong enough to license
    // asking about an app on a hunch.
    return hold("no task has needed this app yet; an ask with no evidence is an advertisement");
  }
  if (ctx.lastAskAnyAppAt !== null) {
    const since = ctx.now - ctx.lastAskAnyAppAt;
    // Note the direction: a `lastAskAnyAppAt` in the FUTURE (clock skew) yields
    // a negative `since`, which is < the interval and therefore holds. Skew must
    // never open the gate.
    if (since < GLOBAL_ASK_INTERVAL_DAYS * DAY_MS) {
      // ACROSS ALL APPS. Per-app counters cannot see each other, so the cap is
      // global by construction.
      const days = Math.floor(since / DAY_MS);
      return hold(
        `this owner was asked about some app ${days}d ago (cap: one ask per `
          + `${GLOBAL_ASK_INTERVAL_DAYS} days across all apps)`,
      );
    }
  }

  // ---- 5. The snooze, and the one override --------------------------------
  // Checked for EVERY state, including needs_reconnect: a snooze is a promise
  // about a date, and the reconnect path skipping it was a real hole.
  if (record.snooze_until !== null && ctx.now < record.snooze_until) {
    // THE LEVEL-1 OVERRIDE, ONCE. A closed laptop is the one moment where the
    // pitch is not a pitch: the task cannot run in the browser at all. "Once"
    // is inferred from the trigger of the ask that WAS declined, because
    // ConnectNudge has no field recording that the override was spent — which
    // over-refuses in exactly one shape, and over-refusing is the direction a
    // floor is allowed to be wrong in.
    const overrideAvailable =
      record.level === 1 && ctx.trigger === "laptop_closed" && record.trigger !== "laptop_closed";
    if (!overrideAvailable) {
      const days = Math.ceil((record.snooze_until - ctx.now) / DAY_MS);
      return hold(`snoozed for another ${days}d at decline level ${record.level}`);
    }
  }

  // ---- 6. The reconnect cadence -------------------------------------------
  if (reconnect) {
    // "One gentle ask, then weekly at most." The ladder deliberately does not
    // apply: it governs "will you connect an app you have not connected", and a
    // reconnect is the repair of a thing this owner already chose.
    if (nudge.sent_at !== null && ctx.now - nudge.sent_at < GLOBAL_ASK_INTERVAL_DAYS * DAY_MS) {
      const days = Math.floor((ctx.now - nudge.sent_at) / DAY_MS);
      return hold(`reconnect was already raised ${days}d ago; weekly at most`);
    }
    return {
      decision: "ask",
      reason: `this app needs reconnecting and ${ctx.tasksThatWouldHaveUsedIt} task(s) have needed it`,
    };
  }

  // ---- 7. What level 2 still admits ---------------------------------------
  // REDUNDANT UNDER TODAY'S NUMBERS AND KEPT ON PURPOSE: LEVEL_THRESHOLD[2] is
  // 0.95 and the only trigger clearing it is laptop_closed, which is on this
  // list. It earns its place because the numbers above it are declared config,
  // and the day somebody retunes them this list is the only thing between an
  // owner who has said no twice and a third "you keep doing this in the
  // browser" text. The test holds the config at the value that makes it
  // load-bearing, so it fails if this is deleted.
  if (record.level === 2 && !LEVEL_2_TRIGGERS.includes(ctx.trigger)) {
    return hold(
      `decline level 2 admits only ${LEVEL_2_TRIGGERS.join(" or ")}; this moment is ${ctx.trigger}`,
    );
  }

  // ---- 8. The right-time score --------------------------------------------
  const score = TRIGGER_SCORE[ctx.trigger];
  const threshold = LEVEL_THRESHOLD[record.level as 0 | 1 | 2 | 3];
  // STRICTLY above, per the contract's own wording. It bites at exactly one
  // place — in_task (0.80) at level 1 (0.80) — and the tie goes to the person
  // who already said no once.
  if (!(score > threshold)) {
    return hold(
      `this moment scores ${score} and level ${record.level} needs more than ${threshold}`,
    );
  }

  return {
    decision: "ask",
    reason: `${ctx.trigger} scores ${score} over level ${record.level}'s ${threshold}, `
      + `${ctx.tasksThatWouldHaveUsedIt} task(s) would have used it, and nothing blocks the ask`,
  };
}

/**
 * The FLOOR, executable. Callers ask this, never `decision !== "hold"` —
 * because that phrasing lets `no-verdict` through, and `no-verdict` is the
 * state we are in when a bug upstream handed us half a row.
 */
export function askIsLicensed(verdict: NudgeVerdict | null | undefined): boolean {
  return verdict?.decision === "ask";
}

/**
 * The row for an owner nobody has ever asked about this app.
 *
 * IT IS THE CALLER'S ANSWER, NOT THE POLICY'S. `shouldAsk` refuses a missing
 * row on purpose, because from inside it "no row" and "the read failed" are the
 * same value — and treating a failed read as a fresh owner re-asks somebody who
 * declined three times. Only the code that made the call knows which happened:
 * `readNudge` RETURNING null is a fresh owner, `readNudge` THROWING is a failed
 * read. `sendConnectAsk` keeps those apart and this is the first half.
 */
export function freshNudge(owner: OwnerId | string, toolkit: Toolkit): ConnectNudge {
  return {
    user_id: ownerId(typeof owner === "string" ? owner : String(owner ?? "")),
    toolkit: checkedSlug(toolkit),
    state: "never_asked",
    level: 0,
    snooze_until: null,
    trigger: null,
    sent_at: null,
    acted_at: null,
    channel: null,
  };
}

// ===========================================================================
// 3. THE WORDS — containment on a draft OUR model wrote
// ===========================================================================
// See the header for why this is not simply `askText` from words.ts, and for
// the test that goes red the day it can be.

function refuse(cause: WordsRefusalCause, refusal: string): Refusal {
  return { ok: false, cause, refusal };
}

function isNonEmptyString(v: unknown): v is string {
  return typeof v === "string" && v.trim() !== "";
}

/** Collapse runs of whitespace and trim. Scanning plumbing; it changes no
 *  verdict and no wording, and the text that gets SENT is never this copy. */
function tidy(s: string): string {
  return s.replace(/\s+/g, " ").trim();
}

/** A copy for scanning only: lowercased, curly apostrophes folded to straight
 *  ones so "doesn’t" and "doesn't" are the same string to the checks below. */
function forScan(s: string): string {
  return tidy(s).toLowerCase().replace(/[‘’ʼ]/g, "'");
}

function escapeForRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Whole-word / whole-phrase containment. The boundary is "not a letter or a
 *  digit" rather than `\b`, so "API-key" trips "api" (a hyphen is a boundary)
 *  while "capital" and "therapist" do not (a letter is not). */
function firstTermIn(text: string, terms: readonly string[]): string | null {
  const hay = forScan(text);
  for (const term of terms) {
    const re = new RegExp(`(?<![a-z0-9])${escapeForRegExp(term)}(?![a-z0-9])`, "i");
    if (re.test(hay)) return term;
  }
  return null;
}

/**
 * What a PHONE will treat as a link, not what a parser would. Carried from
 * words.ts `URL_LIKE`, which is not exported; the two must move together and
 * the test pins them against that file's source.
 *
 * `https?://` alone is blind to the shape that actually rides into a text: a
 * bare `connect.<vendor>.dev/link/abc`, which every messaging app on every
 * handset linkifies on sight. That blindness meant "exactly one URL and it must
 * be ours" could be satisfied by a message carrying two tappable links, one of
 * them the vendor's and already dead. The second alternative REQUIRES a slash
 * after the host, deliberately: without it "in the browser.Connect it once"
 * reads as a host, and refusing that good ask costs the one interruption this
 * app gets.
 */
const URL_LIKE = /https?:\/\/\S+|(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}\/\S*/gi;

function countOccurrences(hay: string, needle: string): number {
  if (needle === "") return 0;
  let n = 0;
  let i = 0;
  for (;;) {
    const j = hay.indexOf(needle, i);
    if (j < 0) return n;
    n += 1;
    i = j + needle.length;
  }
}

/** Is there really a sentence on this side of the link? `\p{L}` rather than
 *  `[a-z]`, because the first ask written in a language that is not English
 *  must not be refused for being unreadable to a character class. */
function hasWords(s: string): boolean {
  return /\p{L}/u.test(s);
}

/** Our link, and ours alone: the base the mint actually used, then exactly the
 *  token alphabet and length routes/connect.ts will route. */
function isOurLink(link: string, base: string): boolean {
  const prefix = `${base.replace(/\/+$/, "")}/`;
  if (!link.startsWith(prefix)) return false;
  if (/\s/.test(link)) return false;
  return new RegExp(`^[A-Za-z0-9_-]{${TOKEN_CHARS}}$`).test(link.slice(prefix.length));
}

export interface AskMessageOptions {
  /** The base the link was minted on. Defaults to the production constant. */
  base?: string;
}

/**
 * The one text message: one sentence on why, one link, one sentence saying it
 * is optional, in this product's voice, inside one text as a carrier counts it.
 *
 * THE PRECONDITIONS ARE CHECKED BEFORE THE MODEL IS CALLED, because none of
 * them can be argued out of by good copy: a beautiful ask at the wrong moment
 * is still the wrong moment, and a beautiful ask carrying a vendor link is the
 * failure of 2026-09-05 with better grammar.
 *
 * WHAT THIS HONESTLY CANNOT CHECK, said plainly so nobody later mistakes
 * silence for coverage: whether a sentence MEANS "this is optional". That is
 * meaning, and law 1 reserves it for the model that wrote it. What CAN be
 * checked is that the model left room for one — the shape is why → link →
 * optional, so a draft that ends on the link has dropped a line the spec
 * requires in every single ask, and that much is structural.
 *
 * EVERY REFUSAL IS A REFUSAL, NEVER A REPAIR. Nothing below rewrites, pads or
 * truncates a draft. A message this product did not write is a message this
 * product should not send.
 */
export async function askMessage(
  moment: NudgeTrigger,
  meta: ToolkitMeta,
  evidence: AskEvidence,
  write: AskWriter,
  opts: AskMessageOptions = {},
): Promise<AskResult> {
  const base = opts.base ?? CONNECT_URL_BASE;

  if (meta === null || typeof meta !== "object") {
    return refuse("malformed-meta", "no toolkit metadata: there is nothing to name in the ask");
  }
  if (!isNonEmptyString(meta.slug) || !isNonEmptyString(meta.name)) {
    // A text that says "Connect your undefined" is, to the person reading it,
    // indistinguishable from a phishing message.
    return refuse(
      "malformed-meta",
      "the toolkit row has no slug or no name, so the ask cannot say which app this is",
    );
  }

  // Every ask is tied to a real moment; "never out of nowhere" is a rule with a
  // leg only if an absent or invented moment refuses.
  if (!Object.hasOwn(TRIGGER_SCORE, moment as unknown as string)) {
    return refuse(
      "no-moment",
      `"${String(moment)}" is not one of the moments an ask may come from; every ask is tied `
        + "to something that actually happened, never out of nowhere",
    );
  }

  if (evidence === null || typeof evidence !== "object") {
    return refuse(
      "malformed-evidence",
      "no evidence for the ask, so there is nothing for it to say why about",
    );
  }

  // THE SECOND GATE ON THE SAME RULE, and it is not redundant. `shouldAsk`
  // already holds when the result has not gone out, but that is a different
  // function reading a different input, and this one is the gate a caller that
  // composed an ask by hand still has to pass. Two independent floors on the
  // rule that an ask never arrives instead of an answer.
  if (evidence.resultDelivered !== true) {
    return refuse(
      "result-not-delivered",
      "the task's own answer has not gone out yet; the ask comes after the result, never "
        + "instead of it",
    );
  }

  const link = typeof evidence.link === "string" ? evidence.link.trim() : "";
  if (!isOurLink(link, base)) {
    // Ours, never the vendor's. The vendor's expires ten minutes after it is
    // minted, so a text carrying one is dead by the time it is read — four for
    // four on 2026-09-05.
    return refuse(
      "bad-link",
      `${JSON.stringify(link)} is not a single-use ${base.replace(/\/+$/, "")}/{token} link`,
    );
  }

  let reply: unknown;
  try {
    reply = await write({ moment, meta, evidence });
  } catch (err) {
    return refuse(
      "no-verdict",
      `nothing wrote the ask for ${meta.name}: ${String((err as Error)?.message ?? err)}`,
    );
  }

  if (reply === null || reply === undefined) {
    return refuse("no-verdict", `nothing wrote the ask for ${meta.name}`);
  }
  if (typeof reply !== "string") {
    return refuse(
      "malformed-reply",
      `the ask for ${meta.name} came back as ${typeof reply}, not a message`,
    );
  }

  // Ends trimmed only. Interior line breaks are the model's formatting and are
  // left alone; collapsing them would be this module rewriting copy.
  const text = reply.trim();
  if (text === "") {
    return refuse("malformed-reply", `the ask for ${meta.name} is empty`);
  }

  // Measured against the encoding the carrier will actually pick, not against a
  // character count: a single curly apostrophe forces UCS-2, where two parts
  // hold 134 units rather than 306 septets. The part that arrives second, or
  // not at all, is the part with the link in it.
  const sms = smsShape(text);
  if (sms.segments > MAX_ASK_SEGMENTS) {
    return refuse(
      "too-long",
      `the ask is ${sms.units} ${sms.encoding} units and would leave in ${sms.segments} `
        + `messages, over the ${sms.ceiling} that fit in ${MAX_ASK_SEGMENTS}`,
    );
  }
  // The spec's own number, subsumed by the line above under today's config —
  // see ASK_MESSAGE_MAX_CHARS for why it is kept anyway.
  if (text.length >= ASK_MESSAGE_MAX_CHARS) {
    return refuse(
      "too-long",
      `the ask is ${text.length} characters; the spec's ceiling is under ${ASK_MESSAGE_MAX_CHARS}`,
    );
  }

  // The vocabulary checks run over the WORDS, with the link lifted out. A token
  // is machine-issued and nobody reads it: `.../c/x-api-7…` is not the ask
  // saying "API", and refusing that ask would drop a good message because of
  // 43 random characters.
  const words = text.split(link).join(" ");

  if (words.includes("!")) {
    return refuse(
      "exclamation",
      "the ask used an exclamation mark; this product does not raise its voice at anybody",
    );
  }
  const forbidden = firstTermIn(words, FORBIDDEN_TERMS);
  if (forbidden !== null) {
    return refuse(
      "forbidden-word",
      `the ask used "${forbidden}", which is exactly the register the spec forbids`,
    );
  }
  const stiff = firstTermIn(words, STIFF_FORMS);
  if (stiff !== null) {
    return refuse(
      "stiff",
      `the ask wrote "${stiff}" where this product would contract it; the voice is a person `
        + "offering to help, not a consent form",
    );
  }

  const links = countOccurrences(text, link);
  if (links === 0) {
    return refuse("no-link", "the ask does not carry the connect link, so there is nothing to tap");
  }
  if (links > 1) {
    return refuse("extra-link", "the ask carries the connect link more than once");
  }
  const urls = text.match(URL_LIKE) ?? [];
  if (urls.length !== 1) {
    // A second URL in a connect text is, in every recorded case, the vendor's
    // own link riding along beside ours — the wrong link and a dead one. A
    // SCHEMELESS one counts: a phone linkifies `connect.x.dev/ab` exactly as it
    // linkifies `https://connect.x.dev/ab`, and the person taps whichever is
    // nearer their thumb.
    return refuse(
      "extra-link",
      "the ask carries a second link; the only URL in a connect text is ours",
    );
  }

  // The one URL has to BE our link, not merely contain it. `…/c/{token}-x.com`
  // contains the token, passes every count above, and resolves to nothing: the
  // owner taps, gets a 404, and reads it as "this is broken". Sentence-ending
  // punctuation is stripped first because a full stop belongs to the sentence,
  // not to the URL.
  const only = urls[0].replace(/[).,;:'"”’»]+$/, "");
  if (only !== link) {
    return refuse(
      "mangled-link",
      `the message carries ${JSON.stringify(only)}, not the single-use link it was given`,
    );
  }

  const at = text.indexOf(link);
  if (!hasWords(text.slice(0, at))) {
    return refuse(
      "nothing-before-link",
      "the ask opens on the link with no sentence saying why it is being sent",
    );
  }
  if (!hasWords(text.slice(at + link.length))) {
    return refuse(
      "nothing-after-link",
      "the ask ends on the link, so the line telling them this is optional is missing",
    );
  }

  return { ok: true, text };
}

// ===========================================================================
// 4. THE ASK, END TO END
// ===========================================================================

/** Enumerated, so callers and gates MAY branch on it. The three policy verdicts
 *  keep their own names, because "we held" and "we could not tell" are the two
 *  facts anybody tuning this needs to be able to count separately. */
export type AskCause =
  | "sent"
  | "hold"
  | "never-again"
  | "no-verdict"
  | "no-wiring"
  | "no-owner"
  | "no-toolkit"
  | "no-moment"
  | "no-catalog"
  | "no-phone"
  | "no-link"
  | "refused-copy"
  | "not-delivered"
  | "store-failed";

export interface AskOutcome {
  sent: boolean;
  /** The policy's four-state verdict, or null when we never got that far. */
  decision: NudgeDecision | null;
  cause: AskCause;
  /** Plain English for the log. NOTHING branches on these words, and they are
   *  never shown to the owner. */
  reason: string;
}

function outcome(cause: AskCause, reason: string, decision: NudgeDecision | null = null): AskOutcome {
  return { sent: cause === "sent", decision, cause, reason };
}

/**
 * The whole ask: decide, mint, write, send. One text or nothing.
 *
 * IT NEVER THROWS. Every failure is a returned outcome, because this runs from
 * a cron sweep over many owners and an exception on owner three is silence for
 * owners four through twenty — a whole feature switched off by one bad row.
 *
 * THE ORDER IS THE DESIGN. Nothing is minted and nothing is written until the
 * policy has licensed the ask, the catalog has answered with a real app, and
 * this owner has a number to text. Each of those can fail, and a link minted
 * before them is a `connect_links` row that can never be redeemed.
 *
 * THE ROW IS WRITTEN BEFORE THE SEND, AND HANDED BACK IF THE SEND FAILS —
 * the same shape as `store.release` in routes/connect.ts, and for the mirror
 * image of the same reason. Written after a successful send, a crash between
 * the two leaves an owner who was texted and a row that says never_asked: the
 * next sweep asks them again, which is the spam this whole module exists to
 * prevent. Written before, a failed send costs the owner one week of silence —
 * and if the hand-back write ALSO fails, the row stays `asked` and the owner
 * stays quiet, which is the direction a floor is allowed to be wrong in.
 *
 * WHAT IS NOT CLOSED, written down rather than left for somebody to find: two
 * sweeps running at once could both read `never_asked` and both send, because
 * `putNudge` is a plain upsert with no compare-and-set — the store interface
 * has no conditional write for `connect_nudges` the way it has for
 * `connect_links`. Cloudflare does not overlap a Cron Trigger with itself, so
 * the exposure is a manual sweep run beside the scheduled one. The fix is a
 * conditional `putNudge` in store.ts, which this file does not own.
 */
export async function sendConnectAsk(
  env: NudgeEnv,
  owner: OwnerId | string,
  toolkit: Toolkit,
  trigger: NudgeTrigger,
  injected?: NudgeDeps | null,
): Promise<AskOutcome> {
  const deps = injected ?? WIRING(env);
  if (!deps) {
    return outcome(
      "no-wiring",
      "no connect-nudge wiring installed on this Worker: no store, no catalog and nothing to "
        + "write the text, so nobody is asked anything. See installNudgeWiring().",
    );
  }

  const now = deps.now ? deps.now() : Date.now();

  let who: OwnerId;
  try {
    who = ownerId(typeof owner === "string" ? owner : String(owner ?? ""));
  } catch (err) {
    // A display name where an owner id belongs. Refused, never guessed at: this
    // is the one mistake that texts the wrong person.
    return outcome("no-owner", String((err as Error)?.message ?? err));
  }
  let slug: Toolkit;
  try {
    slug = checkedSlug(toolkit);
  } catch (err) {
    return outcome("no-toolkit", String((err as Error)?.message ?? err));
  }

  // 1. THE ROW. A THROW is a read that failed and the answer is `no-verdict`;
  //    a null is an owner nobody has ever asked about this app. Those two are
  //    the same value to `shouldAsk`, which is why they are separated here.
  let row: ConnectNudge;
  try {
    const found = await deps.store.readNudge(who, slug);
    row = found ?? freshNudge(who, slug);
  } catch (err) {
    return outcome(
      "no-verdict",
      `could not read this owner's nudge row, so a decline may exist that we cannot see: `
        + String((err as Error)?.message ?? err),
      "no-verdict",
    );
  }

  // 2. THE 7-DAY BUDGET, ACROSS ALL APPS — computed here, from this owner's own
  //    rows, and never taken from the caller. Somebody who just ran three
  //    browser tasks against three unconnected apps must not receive three
  //    connect texts, and a per-app counter cannot see the other two.
  let lastAskAnyAppAt: number | null;
  try {
    const history = await deps.store.nudgesForOwner(who);
    if (!Array.isArray(history)) {
      // A store that answered with something that is not a list has not
      // answered. Collapsing that into `null` ("never asked anybody anything")
      // is how an owner who just ran three browser tasks gets three connect
      // texts in one minute — the cap would be reading a field nobody filled in.
      throw new TypeError(`the store answered with ${typeof history}, not a list of nudge rows`);
    }
    lastAskAnyAppAt = latestSentAt(history);
  } catch (err) {
    return outcome(
      "no-verdict",
      "ask history could not be read; refusing to guess at the 7-day cap: "
        + String((err as Error)?.message ?? err),
      "no-verdict",
    );
  }

  // 3. THE MOMENT. Nothing here is inferred: an absent moment is silence.
  let moment: NudgeMoment | null = null;
  try {
    moment = await deps.moment(who, slug, trigger, now);
  } catch {
    moment = null;
  }
  if (moment === null || typeof moment !== "object") {
    return outcome(
      "no-moment",
      "nobody said what moment this is; an ask needs a real one and never invents it",
      "no-verdict",
    );
  }

  const ctx: NudgeContext = {
    now,
    trigger,
    localHour: moment.localHour,
    taskInFlight: moment.taskInFlight,
    resultDelivered: moment.resultDelivered,
    tasksThatWouldHaveUsedIt: moment.tasksThatWouldHaveUsedIt,
    lastAskAnyAppAt,
  };

  const verdict = shouldAsk(row, ctx, { owner: who, toolkit: slug });
  if (!askIsLicensed(verdict)) {
    // The FLOOR, executable: anything that is not exactly "ask" sends nothing.
    return outcome(verdict.decision as AskCause, verdict.reason, verdict.decision);
  }

  // 4. THE APP, from the catalog at run time. Before the mint, so a catalog
  //    blip does not leave a `connect_links` row nobody can ever redeem.
  let meta: ToolkitMeta;
  try {
    meta = await deps.catalog.toolkit(slug);
  } catch (err) {
    return outcome(
      "no-catalog",
      `the catalog did not answer for ${JSON.stringify(slug)}, so the ask cannot name the app: `
        + String((err as Error)?.message ?? err),
      "ask",
    );
  }

  // 5. WHERE IT GOES. Also before the mint, and for the same reason.
  let to = "";
  try {
    const raw = await deps.phone(who);
    to = typeof raw === "string" ? raw.trim() : "";
  } catch {
    to = "";
  }
  if (to === "") {
    return outcome("no-phone", "this owner has no number on file, so there is nowhere to ask", "ask");
  }

  // 6. THE LINK. Ours, single use, ten minutes, bound to this owner and app.
  let minted: MintedLink;
  try {
    minted = await mintConnectLink(env, who, slug, moment.alias ?? null, deps);
  } catch (err) {
    return outcome(
      "no-link",
      "could not mint a connect link: " + String((err as Error)?.message ?? err),
      "ask",
    );
  }

  // 7. THE WORDS. `resultDelivered` is carried from the moment rather than
  //    written as `true`: the policy already refused a false one, and hardcoding
  //    it here would be this file asserting a fact it did not check.
  const evidence: AskEvidence = {
    link: minted.url,
    resultDelivered: moment.resultDelivered,
    whatHappened: moment.whatHappened,
    tasksThatWouldHaveUsedIt: ctx.tasksThatWouldHaveUsedIt,
    browserMs: moment.browserMs,
  };
  const copy = await askMessage(trigger, meta, evidence, deps.write, { base: baseOf(env, deps) });
  if (!copy.ok) {
    // The link stays minted and expires in ten minutes, unused and unredeemable
    // by anyone — nobody was ever given it. That is the cheap half of the trade:
    // a refused draft costs one dead row, and a repaired draft costs the
    // interruption this owner only gets once a week.
    console.log(
      `connect ask: ${who} ${slug} not sent (${copy.cause}) — ${minted.fingerprint}`,
    );
    return outcome("refused-copy", copy.refusal, "ask");
  }

  // 8. THE ASK RECORD, taken as a lease BEFORE the send. `maturedBySilence` is
  //    what stops a re-ask from erasing the decline the previous silence earned.
  const before = maturedBySilence(row, now);
  const asked: ConnectNudge = {
    ...before,
    state: "asked",
    trigger,
    sent_at: now,
    acted_at: null,
    channel: "sms",
  };
  try {
    await deps.store.putNudge(asked);
  } catch (err) {
    return outcome(
      "store-failed",
      "could not record the ask, so it was not sent: an ask nobody wrote down is an ask that "
        + "gets sent again on the next sweep. " + String((err as Error)?.message ?? err),
      "ask",
    );
  }

  // 9. ONE TEXT, through src/messaging.ts, which owns the provider choice and
  //    logs neither the body nor a key.
  const res = await sendText(env, to, copy.text, { tag: "connect ask" });
  if (!res.ok) {
    // HAND THE LEASE BACK, so a real interruption is not spent on a message
    // nobody received.
    try {
      await deps.store.putNudge(before);
    } catch {
      // Nothing to add. The row stays `asked`, this owner stays quiet for a
      // week, and quiet is the safe direction.
    }
    console.log(`connect ask: ${who} ${slug} send failed (${res.error}) — ${minted.fingerprint}`);
    return outcome("not-delivered", `the text did not go out: ${res.error}`, "ask");
  }

  // The fingerprint, never the token and never the body.
  console.log(`connect ask: ${who} ${slug} sent — ${minted.fingerprint}`);
  return outcome("sent", verdict.reason, "ask");
}

/** The newest `sent_at` across ALL of this owner's nudge rows, or null when
 *  none of them has ever been sent. Rows with no `sent_at` are not zero: they
 *  are rows nobody has been asked about, and reading them as an ask at the
 *  epoch would open the 7-day gate for everybody. */
function latestSentAt(rows: readonly ConnectNudge[]): number | null {
  // The caller has already refused a non-list, loudly: this function must never
  // be the place where "the store did not answer" quietly becomes "nobody has
  // ever been asked anything", because those two produce opposite behaviour and
  // one of them is three connect texts in a minute.
  let latest: number | null = null;
  for (const row of rows) {
    const at = row?.sent_at;
    if (typeof at !== "number" || !Number.isFinite(at)) continue;
    if (latest === null || at > latest) latest = at;
  }
  return latest;
}

// ===========================================================================
// 5. THE SWEEP — how a nudge actually reaches somebody
// ===========================================================================

export interface SweepReport {
  wired: boolean;
  considered: number;
  sent: number;
  /** Held, never-again and no-verdict together: every way of not asking that
   *  the policy owns. Counted apart from `refused` so a log can tell "we chose
   *  not to" from "we could not write it". */
  quiet: number;
  /** The model's draft broke a rule, or the send failed. */
  refused: number;
  /** Over the per-tick budget, or this owner already got one this tick. */
  skipped: number;
}

/**
 * The cron entry point.
 *
 * WHERE THIS IS CALLED FROM, exactly, since src/cron.ts is not this file's to
 * edit: in `scheduled()`, the five-minute leg —
 *
 *     case "*\/5 * * * *":
 *       ctx.waitUntil(sweep(env));
 *       ctx.waitUntil(connectNudgeSweep(env));    // <- this line
 *       return;
 *
 * with `import { connectNudgeSweep } from "./connections/nudge.ts";` beside the
 * other imports. TWO SEPARATE `waitUntil` CALLS, not one chained promise: the
 * reminder sweep and this one must not be able to take each other down, and a
 * connect ask is the lower-priority half of that pair by a wide margin.
 *
 * FIVE MINUTES IS THE RIGHT CADENCE even though an owner is asked at most once
 * a week: the policy's whole point is that the ask lands at a MOMENT — just
 * after a result, with the laptop shut — and a nightly sweep would only ever
 * arrive long after every such moment had passed.
 *
 * ONE OWNER GETS AT MOST ONE ASK PER TICK, enforced here as well as by the
 * 7-day cap, because the cap reads `sent_at` off rows this same loop is writing
 * and belt-and-braces is cheap when the failure is a person receiving three
 * texts in one minute.
 */
export async function connectNudgeSweep(
  env: NudgeEnv,
  injected?: NudgeDeps | null,
): Promise<SweepReport> {
  const report: SweepReport = {
    wired: false, considered: 0, sent: 0, quiet: 0, refused: 0, skipped: 0,
  };
  const deps = injected ?? WIRING(env);
  if (!deps || typeof deps.due !== "function") {
    // Silent, not loud: nobody is standing in front of this waiting. The log
    // line names the missing wiring so a deploy check can see it.
    console.log("connect nudge sweep: no wiring installed; nobody was asked anything");
    return report;
  }
  report.wired = true;

  const now = deps.now ? deps.now() : Date.now();
  let due: NudgeCandidate[];
  try {
    const answered = await deps.due(now);
    due = Array.isArray(answered) ? answered : [];
  } catch (err) {
    console.log("connect nudge sweep: could not read who is due — "
      + String((err as Error)?.message ?? err));
    return report;
  }

  const askedThisTick = new Set<string>();
  for (const candidate of due) {
    report.considered += 1;
    const key = String(candidate?.owner ?? "");
    if (report.sent >= MAX_ASKS_PER_SWEEP || askedThisTick.has(key)) {
      report.skipped += 1;
      continue;
    }
    const out = await sendConnectAsk(
      env, candidate?.owner as OwnerId, candidate?.toolkit as Toolkit,
      candidate?.trigger as NudgeTrigger, deps,
    );
    if (out.sent) {
      report.sent += 1;
      askedThisTick.add(key);
    } else if (out.cause === "hold" || out.cause === "never-again" || out.cause === "no-verdict") {
      report.quiet += 1;
    } else {
      report.refused += 1;
    }
  }

  console.log(
    `connect nudge sweep: ${report.considered} considered, ${report.sent} sent, `
      + `${report.quiet} quiet, ${report.refused} refused, ${report.skipped} skipped`,
  );
  return report;
}
