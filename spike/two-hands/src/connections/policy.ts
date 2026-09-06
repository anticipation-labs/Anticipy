// THE NUDGE POLICY — may we interrupt this person, right now, about this app?
//
// One question, answered in four states, by comparing facts about a MOMENT
// against a record of what this owner has already been asked. Nothing in this
// file reads a sentence anybody said, and nothing in it knows the name of a
// single app.
//
// WHY IT IS THIS PARANOID. The product is trust under silence. It earns its
// keep in the few moments a day it catches something real, and it destroys
// itself in any ONE moment it interrupts wrongly — because the owner's fix for
// a product that pesters is not a settings change, it is Do Not Disturb, and a
// muted product hears nothing and catches nothing ever again. A connect ask is
// an interruption. Every gate below prices one.
//
// THE POLARITY IS A FLOOR, AND THIS IS THE MOST IMPORTANT LINE IN THE FILE.
// The caller treats anything that is not exactly `"ask"` as do-not-ask
// (`askIsLicensed` below is that rule, executable, so it cannot be paraphrased
// at a call site). So a missing input returns `"no-verdict"` and NOBODY IS
// TEXTED. An interruption needs a LICENCE, not merely the absence of an
// objection: if unknown meant "go ahead", then the first owner whose local hour
// failed to load gets a connect link at 3am, and every future bug in every
// caller upstream of this file converts directly into a message. Silence is the
// default; the ask is the privilege. Same shape and same reasoning as
// `judgeLicensesApi` in ../contract.ts and `shouldNudge` in ../onboarding.ts.
//
// LAW 1 (HARNESS-LAWS). Nothing here decides what words MEAN:
//   - `NudgeTrigger` is a closed enum of things that HAPPENED — a step routed
//     to the browser, a Mac lid closing — established by the caller from
//     events, never by this file from prose. Deciding WHICH app a person meant
//     is a model's job and lives behind `ToolkitJudge` in ./contract.ts.
//   - `TRIGGER_SCORE` and `LEVEL_THRESHOLD` are contract config keyed on that
//     enum. A number attached to "the lid is shut" is not a threshold deciding
//     meaning; it is a rank over event types, which is what law 1 permits.
//   - clocks, hours and elapsed-time comparisons are plumbing ("senses").
//   - `nudge.toolkit` is read in exactly ONE place and only ever compared
//     against a slug the CALLER supplied, to refuse a row that is not the row
//     the caller asked about. No branch anywhere compares it against a literal,
//     so a slug shipped a year ago and one invented tomorrow get identical
//     treatment — the spec's "NO APP IS HARDCODED" made structural rather than
//     promised. `test/connections_policy.test.ts` pins that behaviourally, by
//     sweeping slugs through every scenario and demanding identical verdicts.
//
// Spec: "Connections: how Anticipy asks, learns, and never says Composio",
// 2026-09-05, page 24 (the state machine) and pages 25-26 (the right-time
// score). Contract: ./contract.ts — fixed, not edited by this file.

import {
  GLOBAL_ASK_INTERVAL_DAYS,
  LEVEL_THRESHOLD,
  ONBOARDING_SKIP_SNOOZE_DAYS,
  SILENCE_IS_A_SOFT_NO_HOURS,
  SNOOZE_DAYS,
  TRIGGER_SCORE,
  ownerId,
  type ConnectNudge,
  type NudgeContext,
  type NudgePolicy,
  type NudgeVerdict,
  type OwnerId,
  type Toolkit,
} from "./contract.ts";

const HOUR_MS = 60 * 60 * 1000;
const DAY_MS = 24 * HOUR_MS;

/** Quiet hours, owner-local: 22:00 is quiet, 08:00 is not. Closed at the start,
 *  open at the end — both ends are pinned in the tests, because an off-by-one
 *  here is an hour of somebody's sleep every night for as long as nobody
 *  checks. These two numbers are spec constants with no home in contract.ts;
 *  they live here rather than inline in a branch because a `22` buried in three
 *  branches drifts into three different quiet-hour policies. */
export const QUIET_HOURS_START = 22;
export const QUIET_HOURS_END = 8;

// The contract's closed enums, at RUN TIME.
//
// `node --experimental-strip-types` deletes type annotations; it does not check
// them. `nudge.state` being typed `NudgeState` stops precisely nobody, so a row
// read from D1 with a state of `"declined_l2"` would fall through every
// `===` below and land on `ask` — re-asking somebody who already said no twice.
// These are membership checks over enums declared next door, not a word list
// deciding what anybody meant.
const NUDGE_STATES: readonly string[] = [
  "never_asked",
  "asked",
  "declined",
  "connected",
  "needs_reconnect",
];

/** The state machine's level-2 allowlist, verbatim from page 24: "only in_task
 *  or laptop_closed may ever ask again, never repeated_use". Two enum members
 *  of `NudgeTrigger`, not two words from a sentence. */
const LEVEL_2_TRIGGERS: readonly string[] = ["in_task", "laptop_closed"];

/**
 * WHOSE ROW THIS MUST BE, and about what — stated by the caller, because
 * nothing in the inputs can establish it.
 *
 * THE HOLE THIS CLOSES. `whatIsMissing` checks that `nudge.user_id` has the
 * SHAPE of an owner row id, and until this argument existed it had nothing to
 * compare it against: `NudgeContext` carries no owner and no toolkit, so a
 * perfectly well-formed row belonging to somebody else read cleanly and asked
 * cleanly. A D1 read bound to the wrong variable, a cache keyed by the previous
 * request, or a batch loop reusing the last iteration's id would each send this
 * owner a connect link about another person's app — the spike's own recorded
 * catastrophe (research/2026-09-05-composio-connections.md, item 2) reached by
 * a query instead of by a constant.
 *
 * CONTRACT NOTE, reported rather than patched: the right home for these two is
 * `NudgeContext` in ./contract.ts, which this module may not edit. Until they
 * live there, `NudgePolicy.shouldAsk` — a two-argument interface — cannot carry
 * them, so `DefaultNudgePolicy` takes them at construction instead. The sibling
 * ../onboarding.ts has both already (`ctx.userId` and the `app` argument), and
 * cross-checks the row against both.
 */
export interface AskingFor {
  /** The owner this ask would be SENT to. The row must belong to them. */
  owner: OwnerId | string;
  /** The app this ask would be ABOUT, when the caller knows it. Optional
   *  because a caller sweeping an owner's rows is asking "which of these", and
   *  has no single answer to state; the owner half is never optional. */
  toolkit?: Toolkit | null;
}

/** A slug as stored, for comparing one against another. Lowercasing is
 *  plumbing — the contract says slugs are lowercase, and two spellings of one
 *  slug reading as two different apps would refuse a row that is in fact the
 *  row the caller asked for. It compares two strings somebody else supplied and
 *  cannot express "this app in particular". */
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
 * Everything `shouldAsk` needs and did not get, named in one sentence, or null
 * when the inputs are complete. Kept as one function so that "what would make
 * this decidable" is answerable by reading twenty lines, and so that adding an
 * input to `NudgeContext` without teaching this function about it shows up as
 * a hole rather than as a default.
 */
function whatIsMissing(
  nudge: ConnectNudge,
  ctx: NudgeContext,
  asking: AskingFor | null | undefined,
): string | null {
  if (nudge === null || typeof nudge !== "object") {
    // An absent nudge row is not "never asked". It is a read that failed, or a
    // row for an owner whose D1 shard was unreachable — and treating it as
    // never_asked re-asks somebody who declined three times, which is the one
    // outcome the level ladder exists to make impossible.
    return "no nudge record: a missing row is not a fresh owner";
  }
  if (ctx === null || typeof ctx !== "object") {
    return "no moment to judge: without a context there is no such thing as a good time";
  }

  // WHO THE CALLER IS ABOUT TO TEXT. Not knowing cannot mean "go ahead": this
  // is a floor, so an ask needs a licence rather than merely the absence of an
  // objection. A caller that never said whose row this is has not established
  // one, and the first bug upstream would otherwise convert straight into a
  // message about somebody else's app.
  let expected: string;
  try {
    expected = ownerId((asking ?? ({} as AskingFor)).owner as unknown as string);
  } catch {
    return "nobody said whose nudge this is: an ask needs the owner it would be sent to, as a ROW id";
  }

  // THE ROW'S OWN OWNER ID. This is the spike's catastrophic failure in
  // miniature: a connection bound to "omar" rather than to `sxkotd1h02qb6gw` is
  // one operator's mailbox serving everybody, and it happened for real on
  // 2026-09-05 (research/2026-09-05-composio-connections.md, item 2). A nudge
  // row carrying a display name would send a connect link that binds to the
  // wrong person, so it is not askable — it is unreadable.
  try {
    ownerId(nudge.user_id as unknown as string);
  } catch {
    return `nudge row has no owner ROW id (got ${JSON.stringify(nudge.user_id)}): a name cannot be asked`;
  }

  // AND THEY MUST BE THE SAME PERSON. Two well-formed ids that disagree is the
  // SWAP: a row that reads perfectly and belongs to somebody else. Nothing in
  // the row can show it, which is why the caller has to say.
  if (String(nudge.user_id) !== expected) {
    return `this nudge row belongs to another owner (row ${JSON.stringify(nudge.user_id)}, asking for ${JSON.stringify(expected)})`;
  }

  // THE APP, WHEN THE CALLER NAMED ONE. Applying one app's decline history to
  // another silences a nudge nobody refused, or re-asks somebody who already
  // said no — the same check ../onboarding.ts makes against its `app` argument.
  // A named app that is not a slug is a caller bug, and guessing which app was
  // meant is the judge's question, never this file's.
  const named = (asking as AskingFor).toolkit;
  if (named !== undefined && named !== null) {
    const want = slugOf(named);
    if (want === "") {
      return `the caller named an app that is not a slug: ${JSON.stringify(named)}`;
    }
    if (slugOf(nudge.toolkit) !== want) {
      return `this nudge row is about a different app (row ${JSON.stringify(nudge.toolkit)}, asking about ${JSON.stringify(named)})`;
    }
  }

  if (!NUDGE_STATES.includes(nudge.state as unknown as string)) {
    return `unreadable nudge state ${JSON.stringify(nudge.state)}`;
  }
  if (!isInt(nudge.level) || (nudge.level as number) < 0 || (nudge.level as number) > 3) {
    return `unreadable decline level ${JSON.stringify(nudge.level)}`;
  }
  if (nudge.state === "declined" && nudge.level === 0) {
    // A decline that never incremented the level is a caller bug, and the cost
    // of guessing is asymmetric: read as level 0 it re-asks at the next
    // trigger, ignoring a "no" this system was told and recorded.
    return "row says declined but level is 0: the ladder was not advanced, so the decline cannot be honoured";
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
  // "constructor" or "toString" reaches the prototype and comes back truthy,
  // and `TRIGGER_SCORE["constructor"] > 0.5` is a comparison against a
  // function — false, but by luck rather than by design. Own-property only.
  if (typeof ctx.trigger !== "string" || !Object.hasOwn(TRIGGER_SCORE, ctx.trigger)) {
    return `unknown trigger ${JSON.stringify(ctx.trigger)}: no moment, no score, no ask`;
  }
  if (!isInt(ctx.localHour) || ctx.localHour < 0 || ctx.localHour > 23) {
    // An unknown local hour is the 3am text. There is no safe default: UTC is
    // how somebody in Auckland gets a connect link at 2am from a server that
    // thought it was lunchtime.
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
    // `undefined` here means the caller never read the ask history. Collapsing
    // it into `null` ("never asked anyone anything") is how an owner who just
    // ran three browser tasks gets three connect texts in one minute — the
    // 7-day cap would be reading a field nobody filled in.
    return "ask history was not read; refusing to guess at the 7-day cap";
  }
  return null;
}

/**
 * The record as it stands AFTER a decline, including the snooze the spec owes
 * this owner. Pure: it returns a new row and mutates nothing.
 *
 * `how` is not decoration. "They tapped skip" and "they never answered" are
 * different facts about a person, they are the difference between `acted_at`
 * set and `acted_at` null, and the log is what the spec's timers get tuned
 * from. A silent decline that stamps `acted_at` claims an action nobody took.
 *
 * Exported because the nudge writer needs the SAME arithmetic. Two
 * implementations of "how long is the snooze" is how an owner gets re-asked on
 * day 14 by one code path while the other believes it is day 45.
 */
export function recordDecline(
  nudge: ConnectNudge,
  at: number,
  how: "said_no" | "silence",
): ConnectNudge {
  const level = Math.min(nudge.level + 1, 3) as 1 | 2 | 3;
  // The onboarding exception, from the spec's own constant: somebody skipping a
  // card during setup has not refused the app, they have refused a form. Held
  // for the full 14 days it would look like a "no" we never actually got — so
  // the first decline of an ONBOARDING ask snoozes 7 days, not 14. It applies
  // once, at level 1: a second decline is a second decline whatever the first
  // one was.
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
 * MAY WE ASK? Four states, because "no" and "nobody could tell" are different
 * facts and a boolean carries two of three.
 *
 * `asking` is REQUIRED even though its type allows the absence: this function
 * never throws, so a caller that omits it is answered `no-verdict` rather than
 * with an exception. It is the only way this file can tell a row that IS this
 * owner's from a row that merely looks like one — see `AskingFor` above.
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
    // `hold`, not `never-again`: the state machine's very next transition is
    // `connected -> expired -> needs_reconnect`, and a row marked never-again
    // is a row nothing ever re-opens. An owner whose Gmail token expired would
    // then be permanently unable to be told, and every task needing it would
    // quietly fall back to the browser forever.
    return hold("this owner already has this app connected");
  }

  // ---- 2. An ask is already out ------------------------------------------
  let record = nudge;
  if (nudge.state === "asked") {
    if (nudge.sent_at === null) {
      // Without a send time there is no way to tell "asked ten minutes ago"
      // from "asked in March", and those two need opposite answers.
      return noVerdict("row says asked but has no sent_at: cannot tell a fresh ask from a stale one");
    }
    if (nudge.acted_at !== null) {
      // They acted and the row was never advanced. Whether that action was a
      // connect or a refusal is exactly what is unknown, and one of those two
      // makes asking again a repeat of a question already answered.
      return noVerdict("row says asked but acted_at is set: the answer was never recorded");
    }
    const softNoAt = nudge.sent_at + SILENCE_IS_A_SOFT_NO_HOURS * HOUR_MS;
    if (ctx.now < softNoAt) {
      // A second ask while the first is still open is the product talking over
      // itself. Nothing changed except that we ran another task.
      const hours = Math.floor((ctx.now - nudge.sent_at) / HOUR_MS);
      return hold(`an ask sent ${hours}h ago is still open (silence becomes a no at ${SILENCE_IS_A_SOFT_NO_HOURS}h)`);
    }
    // 72 hours of silence IS an answer, just a quieter one, and the spec counts
    // it as a decline. Without this the ladder has no terminal state for the
    // owner who never replies: they would sit in `asked` forever and every
    // trigger would look fresh. The snooze starts at the moment the silence
    // matured, not at `now` — otherwise a policy consulted a month late would
    // restart a 14-day clock that has already run.
    record = recordDecline(nudge, softNoAt, "silence");
  }

  const reconnect = nudge.state === "needs_reconnect";

  // ---- 3. The end of the ladder ------------------------------------------
  if (!reconnect && record.level === 3) {
    // Three noes is an answer. Only the owner reopening it counts, and that
    // arrives as an owner request, not as a trigger. This is checked BEFORE the
    // moment floors on purpose: an owner who is done being asked should read
    // "stop", not "quiet hours" — the caller may use `never-again` to stop
    // scheduling this row at all, and a `hold` invites it back tomorrow.
    return {
      decision: "never-again",
      reason: "declined three times: only the owner reopening this counts",
    };
  }

  // ---- 4. The moment floors ----------------------------------------------
  // These are facts about NOW, and they apply to a first ask, a re-ask and a
  // reconnect alike.
  if (ctx.taskInFlight) {
    // Mid-step is the worst available moment: the owner is watching work happen
    // and we would interrupt it to advertise a faster version of itself. It
    // also races the run's own result, so two messages land together and the
    // one that matters is underneath.
    return hold("a step is still running; an ask must never land mid-step");
  }
  if (!ctx.resultDelivered) {
    // An ask that arrives INSTEAD OF the answer spends the exact trust the
    // answer was about to earn. The result first, always.
    return hold("the task result has not been delivered yet");
  }
  if (ctx.localHour >= QUIET_HOURS_START || ctx.localHour < QUIET_HOURS_END) {
    // A connect link at 2am is spam whatever the right-time score says, and it
    // is the kind of spam that gets an app's notifications turned off for good.
    return hold(
      `${ctx.localHour}:00 owner-local is inside quiet hours (${QUIET_HOURS_START}:00-${QUIET_HOURS_END}:00)`,
    );
  }
  if (ctx.tasksThatWouldHaveUsedIt === 0) {
    // An ask with no evidence is an advertisement. This counter is incremented
    // by the router when a real step would have used a connection this owner
    // does not have — so the ask can always name a task that already cost them
    // real time, which is the only thing that makes an OAuth screen worth
    // walking through. Zero is a hold ALWAYS: there is no trigger strong enough
    // to license asking about an app on a hunch.
    return hold("no task has needed this app yet; an ask with no evidence is an advertisement");
  }
  if (ctx.lastAskAnyAppAt !== null) {
    const since = ctx.now - ctx.lastAskAnyAppAt;
    // Note the direction: a `lastAskAnyAppAt` in the FUTURE (clock skew between
    // the Worker and D1) yields a negative `since`, which is < the interval and
    // therefore holds. Skew must never open the gate.
    if (since < GLOBAL_ASK_INTERVAL_DAYS * DAY_MS) {
      // ACROSS ALL APPS. Somebody who just ran three browser tasks against
      // three unconnected apps must not receive three connect texts; per-app
      // counters cannot see each other, so the cap is global by construction.
      const days = Math.floor(since / DAY_MS);
      return hold(
        `this owner was asked about some app ${days}d ago (cap: one ask per ${GLOBAL_ASK_INTERVAL_DAYS} days across all apps)`,
      );
    }
  }

  // ---- 5. The snooze, and the one override --------------------------------
  // Checked for EVERY state, including needs_reconnect. A snooze is a promise
  // about a date, and the reconnect path skipping it was a real hole: a row
  // left dirty (or deliberately quietened) would have been texted weekly
  // regardless. Where a stale snooze and a broken connection disagree, the
  // floor decides — an unsent reconnect degrades to the browser hand, an
  // unwanted one is the interruption this file exists to prevent.
  if (record.snooze_until !== null && ctx.now < record.snooze_until) {
    // THE LEVEL-1 OVERRIDE, ONCE. A closed laptop is the one moment where the
    // pitch is not a pitch: the task cannot run in the browser at all, so the
    // ask names a thing that is failing right now rather than a thing that
    // could be faster. The spec lets it jump one snooze, at level 1 only.
    //
    // "Once" is inferred from the trigger of the ask that WAS declined, because
    // `ConnectNudge` has no field recording that the override was spent (see
    // the note in the return value of this task). If the refused ask was itself
    // a laptop_closed ask, re-running the identical pitch inside the snooze is
    // asking a question this owner just answered — so it holds. That reading
    // over-refuses in exactly one shape (level 1 reached by declining a
    // laptop_closed ask that was NOT an override) and over-refusing is the
    // direction a floor is allowed to be wrong in.
    const overrideAvailable =
      record.level === 1 && ctx.trigger === "laptop_closed" && record.trigger !== "laptop_closed";
    if (!overrideAvailable) {
      const days = Math.ceil((record.snooze_until - ctx.now) / DAY_MS);
      return hold(`snoozed for another ${days}d at decline level ${record.level}`);
    }
  }

  // ---- 6. The reconnect cadence -------------------------------------------
  if (reconnect) {
    // "One gentle ask, then weekly at most." The level LADDER deliberately does
    // not apply here — no threshold, no allowlist, no level-3 stop: the ladder
    // governs "will you connect an app you have not connected", and a reconnect
    // is the repair of a thing this owner already chose. Reaching a connected
    // state at all IS the owner reopening it, which is the one thing the spec
    // says counts at the top of the ladder. Someone whose Gmail token expired
    // is not being sold anything.
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
  // REDUNDANT UNDER TODAY'S NUMBERS, AND KEPT ON PURPOSE. `LEVEL_THRESHOLD[2]`
  // is 0.95 and the only trigger that clears it is `laptop_closed`, which is on
  // this list — so removing these four lines changes no outcome the contract
  // can currently produce. A guard that cannot change an outcome is normally
  // dead code pretending to enforce a rule, which is the shape HARNESS-LAWS law
  // 2 warns about, so it earns its place one way only: the numbers above it are
  // declared config ("Values are config, not code"), and the day somebody
  // retunes them this list is the only thing standing between an owner who has
  // said no twice and a third "you keep doing this in the browser" text. The
  // test `level 2 never admits repeated_use, even if the thresholds are
  // retuned` holds the config at the value that makes it load-bearing, so it
  // fails if this is deleted.
  if (record.level === 2 && !LEVEL_2_TRIGGERS.includes(ctx.trigger)) {
    // Page 24: after two noes only a task actually needing it, or a laptop
    // actually shut, may ask again — never `repeated_use`. "You keep doing this
    // in the browser" is precisely the argument this owner has now rejected
    // twice, and repeating it is how a product gets muted.
    return hold(`decline level 2 admits only ${LEVEL_2_TRIGGERS.join(" or ")}; this moment is ${ctx.trigger}`);
  }

  // ---- 8. The right-time score --------------------------------------------
  const score = TRIGGER_SCORE[ctx.trigger];
  const threshold = LEVEL_THRESHOLD[record.level as 0 | 1 | 2 | 3];
  // STRICTLY above, per the contract's own wording ("Ask only if the moment
  // scores above the snooze level's threshold"). It bites at exactly one place
  // — `in_task` (0.80) at level 1 (0.80) — and the tie goes to the person who
  // already said no once. See the contract note returned with this module: the
  // score table and the level-2 allowlist do not fully agree, and where they
  // disagree this file takes the stricter of the two.
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
 * The FLOOR, executable. The caller asks this, never `decision !== "hold"` —
 * because that phrasing lets `no-verdict` through, and `no-verdict` is the
 * state we are in when a bug upstream handed us half a row.
 */
export function askIsLicensed(verdict: NudgeVerdict | null | undefined): boolean {
  return verdict?.decision === "ask";
}

/** The contract's interface, for callers that inject a policy. The free
 *  function above is the implementation; this is a thin adapter so that nothing
 *  has to construct an object to ask a pure question.
 *
 *  IT HOLDS THE EXPECTATION because the interface cannot: `NudgePolicy.shouldAsk`
 *  takes two arguments and ./contract.ts is fixed, so an injected policy has
 *  nowhere else to put "whose nudges am I deciding". One instance per owner is
 *  the shape a request-scoped caller already has. */
export class DefaultNudgePolicy implements NudgePolicy {
  readonly asking: AskingFor;

  constructor(asking: AskingFor) {
    // Refused at WIRING time rather than at decision time. A policy object that
    // could not say whose nudges it decides would answer `no-verdict` to
    // everything, and a product that has quietly stopped asking looks exactly
    // like a product nobody has needed to ask anything — it would ship.
    this.asking = {
      owner: ownerId((asking ?? ({} as AskingFor)).owner as unknown as string),
      toolkit: asking?.toolkit ?? null,
    };
  }

  shouldAsk(nudge: ConnectNudge, ctx: NudgeContext): NudgeVerdict {
    return shouldAsk(nudge, ctx, this.asking);
  }
}
