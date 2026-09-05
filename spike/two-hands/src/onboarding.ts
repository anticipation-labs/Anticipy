// CONNECT NUDGES — the ask that buys the second hand, priced as an interruption.
//
// The browser hand has free auth: the owner is already logged in, so the API
// hand's entire cost is one OAuth screen. Every one of those screens is a
// chance to lose them, and this product's whole value is trust under silence —
// it "destroys itself in any one moment it interrupts wrongly" (docs/BRIEF.html
// §1). So a connect nudge is not a growth loop. It is an interruption, and it
// has to be worth more than the silence it spends.
//
// WHAT IS NOT IN THIS FILE, ON PURPOSE: any list of app names, any list of
// verbs, any string that decides what an app IS. Which apps get nudged is
// whatever the router already found a licensed match for. Everything here is a
// clock rule (owner-local hour), a counter (how many times have we asked), or a
// structural fact the owner themselves told us (which account is the work one).
// None of it reads a sentence, so none of it can decide a meaning —
// HARNESS-LAWS law 1. `test/onboarding.test.ts` runs the whole suite a second
// time against an app name nobody has ever seen; if any of this started
// recognising apps, that run goes red.

import type { ConnectNudge, ConnectedApp, ToolCandidate } from "./contract.ts";

// ---------------------------------------------------------------------------
// THE POLICY NUMBERS, IN ONE PLACE.
// ---------------------------------------------------------------------------
// These are clock and counter thresholds, not meaning: no number below is ever
// compared against words. They are here rather than inline because the owner
// will want to argue with exactly these five, and a number argued with in one
// place stays argued with — a 22 buried in three branches drifts into three
// different quiet-hour policies (the shape research/2026-08-24-law1-audit.md
// found five times over).
export const QUIET_START_HOUR = 22; // owner-local; a connect link at 2am is spam
export const QUIET_END_HOUR = 8;
export const REASK_AFTER_MS = 14 * 24 * 60 * 60 * 1000;
export const GLOBAL_COOLDOWN_MS = 24 * 60 * 60 * 1000;
/** The first ask, plus exactly one re-ask. Nothing gets a third. */
export const MAX_ASKS = 2;
/** A second "no" is a real answer and is treated as one. */
export const MAX_DECLINES = 2;
/** Two GSM segments. A nudge that arrives as five segments is a wall of text
 *  wearing an SMS costume, and carriers truncate or reorder the tail — which
 *  is where the connect link lives. */
export const MAX_SMS_CHARS = 320;

// ---------------------------------------------------------------------------
// THE ROW, AND THE TWO COLUMNS THE CONTRACT DOES NOT HAVE.
// ---------------------------------------------------------------------------
// `ConnectNudge` carries `sent_at` and `declined_at` — one timestamp each. One
// timestamp cannot tell a first decline from a second, and "a second decline is
// never-again" is the rule that keeps this from becoming nagware. So the row is
// widened here, in the spike, with two counters. Both are optional and both
// degrade honestly when a caller hands us a bare contract row: an absent
// counter is reconstructed from the timestamp that is there (see `askCount` /
// `declineCount`), which under-counts at worst by nothing in the common case —
// a row with `sent_at` set has been asked once.
export interface NudgeRecord extends ConnectNudge {
  /** How many times we have actually sent this app's nudge. */
  asks?: number;
  /** How many times the owner has said no to it. */
  declines?: number;
}

export type NudgeVerdict = "ask" | "hold" | "never-again" | "no-verdict";

/** The structural reason behind the verdict. Callers and gates MAY branch on
 *  this — it is an enumerated fact about clocks and counters, not a reading of
 *  anybody's words. `reason` below is the prose twin, and nothing branches on
 *  that one (same rule as `MatchAnswer.reason` in the contract). */
export type NudgeCause =
  | "owner-asked"
  | "licensed"
  | "task-running"
  | "no-evidence"
  | "quiet-hours"
  | "global-cooldown"
  | "one-nudge-per-app"
  | "declined-recently"
  | "declined-twice"
  | "asked-twice"
  | "already-connected"
  | "unknown-clock"
  | "unknown-timezone"
  | "unknown-nudge-history"
  | "row-mismatch"
  | "malformed-state";

export interface NudgeAnswer {
  verdict: NudgeVerdict;
  cause: NudgeCause;
  /** For the audit line a person reads. NOTHING branches on these words. */
  reason: string;
}

export interface NudgeCtx {
  userId: string;
  /** ms epoch. */
  now: number;
  /** IANA zone, e.g. "America/Los_Angeles". Quiet hours are OWNER-local; a
   *  server-local hour check ships the 2am text to everyone who is not in the
   *  server's timezone, which is nearly everyone. */
  ownerTimeZone: string | null;
  /** True while any run is in flight for this owner. The nudge lands AFTER a
   *  run, never inside one. */
  taskRunning: boolean;
  /** When this owner was last nudged about ANY app — null means never, and
   *  `undefined` means the caller did not look it up. Those are different and
   *  are treated differently: see the no-verdict floor below. */
  lastNudgeAnyAppAt: number | null;
  /** The owner asked for this themselves ("connect my gmail"). A solicited
   *  link is not an interruption, so it is not subject to the gates that exist
   *  to price interruptions. */
  ownerAskedFor?: boolean;
}

const NUDGE_STATES = new Set(["queued", "sent", "connected", "declined"]);

function askCount(state: NudgeRecord): number {
  if (Number.isInteger(state.asks) && (state.asks as number) >= 0) return state.asks as number;
  // Reconstructed for a bare contract row: a row that has been sent has been
  // asked. Guessing higher would silence a first re-ask the owner is owed;
  // guessing lower would buy a third interruption nobody authorised.
  return state.sent_at ? 1 : 0;
}

function declineCount(state: NudgeRecord): number {
  if (Number.isInteger(state.declines) && (state.declines as number) >= 0) {
    return state.declines as number;
  }
  return state.declined_at ? 1 : 0;
}

/** The owner's local hour, or null when we genuinely cannot tell. Reading an
 *  hour out of a timestamp is plumbing (HARNESS-LAWS law 1, "senses"): it
 *  decides nothing about what anybody meant. */
function ownerLocalHour(now: number, timeZone: string): number | null {
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone,
      hour: "2-digit",
      hour12: false,
    }).formatToParts(new Date(now));
    const raw = parts.find((p) => p.type === "hour")?.value;
    const h = Number(raw);
    if (!Number.isInteger(h) || h < 0 || h > 24) return null;
    // Some ICU builds render midnight as "24" under hour12:false. Left
    // unhandled, midnight reads as 24 >= QUIET_START_HOUR and stays quiet by
    // luck — and 24 < QUIET_END_HOUR is false, so the same value would report
    // the wrong hour to the audit line for the one hour of the night an owner
    // is most likely to complain about.
    return h === 24 ? 0 : h;
  } catch {
    // An unusable IANA zone throws RangeError here. We do not fall back to UTC:
    // that is how somebody in Auckland gets a connect link at 2am from a server
    // that thought it was lunchtime.
    return null;
  }
}

function inQuietHours(hour: number): boolean {
  // Closed at the start, open at the end: 22:00:00 is quiet, 08:00:00 is not.
  // Both ends are pinned in the tests because an off-by-one here is an hour of
  // the owner's sleep, every night, for as long as nobody checks.
  return hour >= QUIET_START_HOUR || hour < QUIET_END_HOUR;
}

function answer(verdict: NudgeVerdict, cause: NudgeCause, reason: string): NudgeAnswer {
  return { verdict, cause, reason };
}

/**
 * Four states, not a boolean, for the reason the house always gives: "no" and
 * "nobody could tell" are different facts and a bool carries two of three.
 *
 * The polarity is a FLOOR, matching `judgeLicensesApi` in the contract: the
 * silence is the default and the interruption is the privilege, so a missing
 * input produces `no-verdict` and NO nudge. Get this backwards — treat unknown
 * as permission — and the first owner whose timezone failed to load gets texted
 * at 3am, which is the single failure this whole file exists to prevent.
 */
export function shouldNudge(
  app: string,
  state: NudgeRecord | null | undefined,
  ctx: NudgeCtx,
): NudgeAnswer {
  if (typeof app !== "string" || app.trim() === "") {
    return answer("no-verdict", "malformed-state", "no app to nudge about");
  }
  if (!ctx || typeof ctx !== "object") {
    return answer("no-verdict", "malformed-state", "no context to judge against");
  }

  if (state != null) {
    if (typeof state !== "object") {
      return answer("no-verdict", "malformed-state", "nudge row is not a row");
    }
    if (!NUDGE_STATES.has(state.state as string)) {
      // An unrecognised state is not "probably queued". A row we cannot read
      // may be a row that already said no twice, and re-asking that owner is
      // the exact harm this module is for.
      return answer("no-verdict", "malformed-state", `unreadable nudge state ${String(state.state)}`);
    }
    if (normalizeApp(state.app) !== normalizeApp(app)) {
      // Applying Gmail's decline history to Slack silences a nudge nobody
      // refused; applying it the other way re-asks somebody who said no.
      return answer("no-verdict", "row-mismatch", `row is for ${String(state.app)}, asked about ${app}`);
    }
    if (state.user_id !== ctx.userId) {
      return answer("no-verdict", "row-mismatch", "nudge row belongs to another owner");
    }
  }

  // A solicited link is not an interruption. Every gate below prices an
  // interruption, so none of them apply — including quiet hours: an owner who
  // types "connect my gmail" at 2am is awake and is asking. It also outranks
  // `already-connected` on purpose, because "connect my gmail" from someone who
  // has one connected Gmail is usually the second account, or a re-auth, and
  // answering "you already did that" is the product arguing with its owner.
  //
  // NOTE ON THE BOUNDARY: `ownerAskedFor` is a fact the CALLER establishes —
  // the owner's request, judged by a model with the conversation in front of
  // it, exactly as `work_is_licensed` does in brain/orchestrator.py. This file
  // must never be given the sentence and asked to decide whether it was a
  // request; that is the Law-1 violation this whole spike is a rehearsal for.
  if (ctx.ownerAskedFor === true) {
    return answer("ask", "owner-asked", "the owner asked for this connection");
  }

  if (ctx.taskRunning === true) {
    // Mid-run is the worst possible moment: the owner is watching work happen
    // and we would interrupt it to sell them a faster version of itself. It
    // also races the run's own result text, so two messages land together and
    // the one that matters is the one underneath.
    return answer("hold", "task-running", "a run is in flight; the nudge lands after it");
  }

  if (state != null && state.state === "connected") {
    return answer("never-again", "already-connected", `${app} is already connected`);
  }

  if (state != null && declineCount(state) >= MAX_DECLINES) {
    // Two noes is an answer. Asking a third time is how a helpful product
    // becomes a thing people mute, and a muted product hears nothing.
    return answer("never-again", "declined-twice", `${app} was declined twice; only the owner reopens it`);
  }

  if (state != null && askCount(state) >= MAX_ASKS) {
    // Two asks ignored is also an answer, just a quieter one. Without this the
    // "one nudge per app, re-ask once" rule has no terminal state and a silent
    // owner gets nudged every fortnight forever.
    return answer("never-again", "asked-twice", `${app} was asked twice with no answer`);
  }

  if (!Number.isFinite(ctx.now)) {
    return answer("no-verdict", "unknown-clock", "no usable clock");
  }

  const evidence = state == null ? 0 : Number(state.tasks_that_would_have_used_it) || 0;
  if (evidence < 1) {
    // A nudge with no evidence is an advertisement. `tasks_that_would_have_used_it`
    // is incremented by the router when a step matched a tool this owner has not
    // connected — so the ask can always name a real task that already cost them
    // real time, which is the only thing that makes the OAuth screen worth
    // walking through.
    return answer("hold", "no-evidence", `no task has needed ${app} yet`);
  }

  // BOTH timestamps are considered, and the LATEST one owns the window. An
  // earlier draft checked `declined_at` and only fell through to `sent_at` when
  // there was no decline — which re-opened the ask for a row that was declined
  // 20 days ago and re-asked 2 days ago, i.e. it nudged twice in a week on the
  // exact history the rule exists to protect.
  const sentAt = state != null && typeof state.sent_at === "number" ? state.sent_at : null;
  const declinedAt = state != null && typeof state.declined_at === "number" ? state.declined_at : null;
  const lastTouch = Math.max(sentAt ?? -Infinity, declinedAt ?? -Infinity);
  if (Number.isFinite(lastTouch)) {
    const since = ctx.now - lastTouch;
    if (since < REASK_AFTER_MS) {
      const days = Math.floor(since / 86400000);
      // One nudge per app. A second text about the same app inside two weeks
      // reads as a bug to the owner, and it is one: nothing changed except that
      // we ran another task.
      return declinedAt !== null && declinedAt >= (sentAt ?? -Infinity)
        ? answer("hold", "declined-recently", `${app} was declined ${days}d ago`)
        : answer("hold", "one-nudge-per-app", `${app} was nudged ${days}d ago`);
    }
  }

  if (ctx.lastNudgeAnyAppAt === undefined) {
    // `null` means "looked, never nudged". `undefined` means "did not look".
    // Collapsing them is how somebody who just ran three browser tasks gets
    // three connect texts in a minute — the exact shape worker.py's stuck-ask
    // ceiling was fitted for after 63 messages in one day.
    return answer("no-verdict", "unknown-nudge-history", "nudge history was not read; refusing to guess");
  }
  if (ctx.lastNudgeAnyAppAt !== null) {
    const since = ctx.now - ctx.lastNudgeAnyAppAt;
    if (since < GLOBAL_COOLDOWN_MS) {
      return answer("hold", "global-cooldown", "another app was nudged inside 24h");
    }
  }

  if (typeof ctx.ownerTimeZone !== "string" || ctx.ownerTimeZone.trim() === "") {
    return answer("no-verdict", "unknown-timezone", "owner timezone unknown; cannot tell 2am from 2pm");
  }
  const hour = ownerLocalHour(ctx.now, ctx.ownerTimeZone);
  if (hour === null) {
    return answer("no-verdict", "unknown-timezone", `unusable timezone ${ctx.ownerTimeZone}`);
  }
  if (inQuietHours(hour)) {
    return answer("hold", "quiet-hours", `${hour}:00 owner-local is inside quiet hours`);
  }

  return answer("ask", "licensed", `${evidence} task(s) would have used ${app}; nothing blocks the ask`);
}

// ---------------------------------------------------------------------------
// THE COPY.
// ---------------------------------------------------------------------------

export interface NudgeEvidence {
  /** What the step was, in the owner's frame — `CapabilitySignature.expected_effect`
   *  reads well here. Optional: an absent one costs a clause, an invented one
   *  costs the owner's trust. */
  what_it_would_do?: string | null;
  /** MEASURED browser time for the run that just finished. */
  browser_ms: number;
  /** MEASURED or vendor-quoted API time. null when we have never timed it —
   *  and then no number is promised. A "2 seconds" we never measured is a lie
   *  the owner can catch with a stopwatch on day one. */
  api_ms_estimate?: number | null;
  /** How many real tasks would already have used this connection. */
  tasks_that_would_have_used_it: number;
  connectUrl: string;
  scopes: ScopeRequest;
}

/** Google writes its scopes as URLs. Printed whole in an SMS, every one of them
 *  becomes a SECOND tappable link in a message whose entire job is to get one
 *  specific link tapped — and the wrong tap lands on a googleapis 404, which
 *  the owner reads as "this is broken" and declines. So a URL-shaped scope is
 *  displayed as its last path segment.
 *
 *  This is display plumbing on a machine-issued identifier — the same class as
 *  parsing a host out of a URL. It changes no verdict: `scopesFor` still hands
 *  the full strings to the connect link, and this is only what the owner reads. */
function scopeLabel(scope: string): string {
  if (!scope.startsWith("https://") && !scope.startsWith("http://")) return scope;
  const tail = scope.replace(/\/+$/, "").split("/").pop();
  return tail !== undefined && tail !== "" ? tail : scope;
}

function humanMs(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "";
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  return r === 0 ? `${m}m` : `${m}m ${r}s`;
}

/**
 * One SMS. It earns the ask by naming what the browser hand just cost, it
 * carries the link, and it says what the connection does and does not get.
 *
 * The app name is printed exactly as the catalog gave it. Title-casing it here
 * would be a cosmetic rule that renders `github` as `Github` — a typo to the
 * one owner who would notice — and it would be the first line of code in this
 * file that knew something about a specific app.
 */
export function nudgeText(app: string, evidence: NudgeEvidence): string {
  const cost = humanMs(evidence?.browser_ms as number);
  const what = typeof evidence?.what_it_would_do === "string"
    ? evidence.what_it_would_do.trim()
    : "";
  // A long clause here is what pushes the link into a second segment, so the
  // subject only survives while it is short enough to be a subject.
  const subject = what !== "" && what.length <= 60 ? what : "that";
  const opener = cost === ""
    ? `${app} — ${subject} went through the browser`
    : `${app} — ${subject} took ${cost} in the browser`;

  const n = Number(evidence?.tasks_that_would_have_used_it) || 0;
  const evidenceClause = n > 1 ? `, and ${n} tasks so far would have used it` : "";

  const est = evidence?.api_ms_estimate;
  const speed = Number.isFinite(est as number) && (est as number) >= 0
    ? `about ${humanMs(est as number)}`
    : "one call instead of a browser session";

  const url = typeof evidence?.connectUrl === "string" ? evidence.connectUrl : "";
  const scopes = evidence?.scopes;
  const list = scopes != null && Array.isArray(scopes.scopes) ? scopes.scopes : [];
  // The narrow claim is only made when it is provably true. `minimal` is false
  // the moment one matched tool failed to declare its scopes, because then the
  // link is built from the vendor's default set and "and nothing else" would be
  // a promise about a set we never saw.
  // Shortened labels are deduped, and if two different scopes collapse onto the
  // same label the narrow claim is dropped entirely: a list that reads as one
  // permission while two are being granted is worse than no list at all.
  const labels = [...new Set(list.map(scopeLabel))];
  const narrow = scopes?.minimal === true && list.length > 0 && labels.length === list.length
    ? `It asks for ${labels.join(", ")} and nothing else.`
    : "";
  const broad = "The consent screen lists exactly what it gets, and it gets nothing outside that list.";
  const tail = "Not worth it? Say so and I'll stop asking.";

  // The link ends its clause with NO trailing punctuation, deliberately: several
  // SMS clients' link detectors swallow a trailing "." into the URL, and a 404
  // is a decline with extra steps — on the one nudge this app ever gets.
  const build = (scopeClause: string, withEvidence: boolean) =>
    [
      `${opener}${withEvidence ? evidenceClause : ""}.`,
      `Connect it once and the same step is ${speed}: ${url}`,
      scopeClause,
      tail,
    ]
      .filter((part) => part !== "")
      .join(" ");

  // Shed in the order the owner would shed it: the exact scope list first (the
  // consent screen shows it anyway, verbatim and authoritatively), then the
  // count of past tasks. The URL is never touched — a truncated link is a dead
  // link, and a dead link turns the one nudge this app ever gets into a
  // guaranteed decline.
  const attempts = [
    build(narrow !== "" ? narrow : broad, true),
    build(broad, true),
    build(broad, false),
  ];
  for (const text of attempts) {
    if (text.length <= MAX_SMS_CHARS) return text;
  }
  return attempts[attempts.length - 1];
}

// ---------------------------------------------------------------------------
// STATE TRANSITIONS ON ConnectNudge.
// ---------------------------------------------------------------------------
// Pure: they take a row and return the next row. The caller persists it. A
// transition that wrote to the ledger itself could not be run twice in a test
// against the same fixture, and the counters here are the only thing standing
// between this feature and nagware — they get tested hard.

function blankRow(userId: string, app: string): NudgeRecord {
  return {
    user_id: userId,
    app,
    state: "queued",
    sent_at: null,
    channel: null,
    tasks_that_would_have_used_it: 0,
    declined_at: null,
    asks: 0,
    declines: 0,
  };
}

function rowFor(userId: string, app: string, state: NudgeRecord | null | undefined): NudgeRecord {
  if (state == null) return blankRow(userId, app);
  return {
    ...state,
    asks: askCount(state),
    declines: declineCount(state),
  };
}

/** The router found a licensed match for an app this owner has not connected.
 *  This is the only way evidence accrues — without it `shouldNudge` holds on
 *  `no-evidence` forever and the second hand is never offered to anyone. */
export function onWouldHaveUsed(
  app: string,
  state: NudgeRecord | null | undefined,
  userId: string,
): NudgeRecord {
  const row = rowFor(userId, app, state);
  return { ...row, tasks_that_would_have_used_it: (Number(row.tasks_that_would_have_used_it) || 0) + 1 };
}

/** Record the ask itself. `sent_at` alone cannot terminate the sequence — the
 *  ask counter is what makes "re-ask once" have a last time. */
export function onSent(
  app: string,
  state: NudgeRecord | null | undefined,
  now: number,
  channel: "sms" | "ios",
  userId?: string,
): NudgeRecord {
  const row = rowFor(userId ?? state?.user_id ?? "", app, state);
  return { ...row, state: "sent", sent_at: now, channel, asks: (row.asks || 0) + 1 };
}

/** Terminal, and deliberately does not clear `declined_at`: an owner who said
 *  no once and connected later is a fact worth keeping, because it is the
 *  evidence for or against ever having asked twice. */
export function onConnected(
  app: string,
  state: NudgeRecord | null | undefined,
  now: number,
  userId?: string,
): NudgeRecord {
  const row = rowFor(userId ?? state?.user_id ?? "", app, state);
  return { ...row, state: "connected", sent_at: row.sent_at ?? now };
}

/** A no. The counter is what turns the second one into `never-again`; without
 *  it two declines and one decline are the same row and the owner gets asked
 *  every fortnight until they mute us. */
export function onDeclined(
  app: string,
  state: NudgeRecord | null | undefined,
  now: number,
  userId?: string,
): NudgeRecord {
  const row = rowFor(userId ?? state?.user_id ?? "", app, state);
  return { ...row, state: "declined", declined_at: now, declines: (row.declines || 0) + 1 };
}

// ---------------------------------------------------------------------------
// SCOPES — the narrowest set the matched tools actually declared.
// ---------------------------------------------------------------------------

export interface ScopeRequest {
  /** Deduped and sorted, so the same match produces the same consent URL and
   *  two ledger rows can be compared. */
  scopes: string[];
  /** Matched tools whose payload declared no scopes at all. */
  toolsWithoutDeclaredScopes: string[];
  /** True only when every matched tool declared its own scopes and there was at
   *  least one tool. False means the link falls back to the vendor's default
   *  set, which we did not see and must not describe as minimal. */
  minimal: boolean;
}

/** Pull the scope list out of a vendor payload. Reading known keys out of a
 *  JSON blob is plumbing; it decides nothing about what any tool MEANS. The
 *  several key spellings are because Composio, raw MCP and the OpenAPI-derived
 *  entries disagree, and a single-key reader silently returns [] for two of the
 *  three — which reads as "this tool needs no permissions" and ships a connect
 *  link that asks for nothing. */
function declaredScopes(candidate: ToolCandidate): string[] | null {
  const schema = (candidate?.schema ?? {}) as Record<string, unknown>;
  const auth = (schema.auth ?? {}) as Record<string, unknown>;
  const sources = [
    schema.scopes,
    schema.required_scopes,
    schema["x-scopes"],
    auth.scopes,
    auth.required_scopes,
  ];
  for (const source of sources) {
    if (Array.isArray(source)) {
      const strings = source.filter((s) => typeof s === "string" && s.trim() !== "") as string[];
      if (strings.length > 0) return strings.map((s) => s.trim());
      // An explicitly empty array is a real declaration: this tool needs no
      // extra scope. Returning null there would report the tool as
      // undeclared and drop `minimal` for a payload that told us the truth.
      return [];
    }
  }
  return null;
}

/**
 * The MINIMUM scopes for the tools that were actually matched — and only those.
 *
 * The caller passes the candidates the MatchJudge said "yes" to, never the raw
 * retrieval hits: a user asked for full mailbox access in order to send one
 * email says no, correctly, and the retrieval list is where all the extra
 * mailbox tools are. Anything else this owner later needs arrives as a re-auth
 * nudge against a connection that has already proved its worth, which is an
 * ask with evidence behind it rather than one in front.
 *
 * There is deliberately NO subsumption rule collapsing "broad" scopes over
 * narrow ones. The obvious structural version — a scope string that is a prefix
 * of another is the broader one — gets Slack exactly backwards (`chat:write` is
 * NARROWER than `chat:write.public`), and being backwards here means asking for
 * more than we need on the one screen we cannot afford to lose. Knowing which
 * of two vendor strings implies the other requires knowing the vendor, and this
 * file knows no vendors.
 */
export function scopesFor(candidates: ToolCandidate[] | null | undefined): ScopeRequest {
  if (!Array.isArray(candidates) || candidates.length === 0) {
    return { scopes: [], toolsWithoutDeclaredScopes: [], minimal: false };
  }
  const seen = new Set<string>();
  const undeclared: string[] = [];
  for (const candidate of candidates) {
    const scopes = declaredScopes(candidate);
    if (scopes === null) {
      undeclared.push(String(candidate?.toolSlug ?? ""));
      continue;
    }
    for (const scope of scopes) seen.add(scope);
  }
  return {
    scopes: [...seen].sort(),
    toolsWithoutDeclaredScopes: undeclared,
    minimal: undeclared.length === 0,
  };
}

// ---------------------------------------------------------------------------
// WHICH ACCOUNT — asked once, remembered, never guessed.
// ---------------------------------------------------------------------------

/** A connected account plus the owner's OWN answer to "work or personal?",
 *  collected once at connect time and stored.
 *
 *  `kind` is NOT derived from `label`. Reading "work" out of "j.smith@acme.com"
 *  is a string deciding a meaning (HARNESS-LAWS law 1) and it is wrong for
 *  everybody who runs their business from a gmail.com address — and being wrong
 *  here sends the owner's dinner invitation from their work account, which is
 *  not an error anybody can un-send. */
export interface TaggedAccount extends ConnectedApp {
  kind?: "work" | "personal" | null;
}

export type AccountChoice =
  | { kind: "resolved"; accountId: string; account: TaggedAccount; reason: string }
  | { kind: "must-ask"; options: TaggedAccount[]; question: string; reason: string }
  | { kind: "needs-reauth"; options: TaggedAccount[]; reason: string }
  | { kind: "none-connected"; app: string | null; reason: string }
  | { kind: "no-verdict"; reason: string };

/** Case-folding an identifier is plumbing, the same as parsing a host out of a
 *  URL. It compares two machine-issued app slugs; it never touches a sentence. */
function normalizeApp(app: unknown): string {
  return typeof app === "string" ? app.trim().toLowerCase() : "";
}

/**
 * Work and personal Gmail both connected is normal, not an edge case.
 *
 * Resolve from the hint when the hint can only mean one connected account.
 * Otherwise return `must-ask` and let the owner answer once — "one short
 * question at the next quiet moment... One question. Never a form."
 * (docs/BRIEF.html, moment 19). Guessing costs strictly more than asking: the
 * ask is one message, the wrong guess is an email from the wrong identity.
 */
export function accountChoice(
  candidates: ToolCandidate[] | null | undefined,
  accountHint: "work" | "personal" | null | undefined,
  connected: TaggedAccount[] | null | undefined,
): AccountChoice {
  if (!Array.isArray(candidates) || candidates.length === 0) {
    return { kind: "no-verdict", reason: "no matched tool to pick an account for" };
  }
  if (!Array.isArray(connected)) {
    return { kind: "no-verdict", reason: "connections were not read" };
  }
  const hint = accountHint ?? null;
  if (hint !== null && hint !== "work" && hint !== "personal") {
    // A hint we cannot read is not "no hint". Treating it as absent would send
    // from whichever account happened to be first.
    return { kind: "no-verdict", reason: `unreadable account hint ${String(accountHint)}` };
  }

  const apps = new Set(candidates.map((c) => normalizeApp(c?.app)).filter((a) => a !== ""));
  if (apps.size === 0) {
    return { kind: "no-verdict", reason: "matched tools name no app" };
  }

  const forApp = connected.filter((c) => apps.has(normalizeApp(c?.app)));
  const active = forApp.filter((c) => c?.status === "active");

  if (active.length === 0) {
    if (forApp.length > 0) {
      // Expired or revoked is not the same as absent. Picking one anyway
      // produces a 401 in the middle of the errand, which the owner reads as
      // "it failed", not as "it needs re-auth".
      return {
        kind: "needs-reauth",
        options: forApp,
        reason: `${forApp.length} connection(s) exist but none are active`,
      };
    }
    return {
      kind: "none-connected",
      app: [...apps][0] ?? null,
      reason: "no connected account for the matched tool's app",
    };
  }

  // Two different apps matched and both are connected: which app to act through
  // is itself the unanswered question, so it goes to the owner rather than to
  // whichever candidate the vendor happened to rank first.
  const activeApps = new Set(active.map((c) => normalizeApp(c.app)));
  if (activeApps.size > 1) {
    return {
      kind: "must-ask",
      options: active,
      question: `Which one should I use — ${active.map((c) => c.label).join(" or ")}?`,
      reason: "matched tools span more than one connected app",
    };
  }

  if (active.length === 1) {
    const only = active[0];
    if (hint !== null && only.kind != null && only.kind !== hint) {
      // The owner asked for the work one and the only connected account is the
      // personal one. Sending it anyway is the dinner-invitation-from-work
      // failure with an extra step.
      return {
        kind: "must-ask",
        options: active,
        question: `That was a ${hint} one — the only ${only.app} I have is ${only.label}. Use it, or connect the ${hint} account?`,
        reason: `hint ${hint} conflicts with the only connected account`,
      };
    }
    // One account and no conflict: there is no branch behind the question, and
    // a question with one possible answer is an interruption that buys nothing.
    return {
      kind: "resolved",
      accountId: only.accountId,
      account: only,
      reason: hint === null
        ? "one connected account and no hint to contradict it"
        : `one connected account, consistent with the ${hint} hint`,
    };
  }

  if (hint === null) {
    return {
      kind: "must-ask",
      options: active,
      question: `Which account — ${active.map((c) => c.label).join(" or ")}?`,
      reason: "more than one connected account and nothing to choose by",
    };
  }

  const tagged = active.filter((c) => c.kind === hint);
  if (tagged.length === 1) {
    return {
      kind: "resolved",
      accountId: tagged[0].accountId,
      account: tagged[0],
      reason: `exactly one account the owner tagged ${hint}`,
    };
  }
  // Zero tagged means nobody has ever answered the question, and two tagged
  // means the owner has two work accounts. Both are the same fact: the hint
  // does not pick out one account, so the owner does — once, and we keep it.
  return {
    kind: "must-ask",
    options: active,
    question: `Which ${hint} account — ${active.map((c) => c.label).join(" or ")}?`,
    reason: tagged.length === 0
      ? `no account is tagged ${hint}; the label is not evidence`
      : `${tagged.length} accounts are tagged ${hint}`,
  };
}
