// WHAT THESE TESTS ARE DEFENDING.
//
// Every assertion below is a statement about when Anticipy is allowed to
// interrupt a person. There are two ways to be wrong and they are not
// symmetric:
//
//   ASKING WHEN WE SHOULD NOT — a text at 2am, a second ask about an app they
//   already refused, three connect texts in one minute, an ask that lands
//   instead of the answer they were waiting for. The owner's fix for that is
//   Do Not Disturb, and a muted product hears nothing and catches nothing ever
//   again. This is the expensive direction and most of the file is about it.
//
//   NEVER ASKING — the failure that looks like caution and is actually a dead
//   feature. A policy that always holds passes every test above and ships a
//   product that never connects anything. So the CONTROL test comes first: a
//   clean, well-evidenced, in-hours, post-result moment must return "ask".
//
// No network, no key, no clock: every time in this file is a literal.
//   node --experimental-strip-types --test test/connections_policy.test.ts

import test from "node:test";
import assert from "node:assert/strict";
import {
  DefaultNudgePolicy,
  QUIET_HOURS_END,
  QUIET_HOURS_START,
  askIsLicensed,
  recordDecline,
  shouldAsk,
} from "../src/connections/policy.ts";
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
  type NudgeTrigger,
} from "../src/connections/contract.ts";

const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;
const NOW = Date.UTC(2026, 8, 5, 17, 0, 0);
const OWNER = ownerId("sxkotd1h02qb6gw");

/** A row for an owner nobody has ever asked about anything. */
function row(over: Record<string, unknown> = {}): ConnectNudge {
  return {
    user_id: OWNER,
    toolkit: "notion",
    state: "never_asked",
    level: 0,
    snooze_until: null,
    trigger: null,
    sent_at: null,
    acted_at: null,
    channel: null,
    ...over,
  } as unknown as ConnectNudge;
}

/** The good moment: mid-afternoon, nothing running, the result already in their
 *  hand, three real tasks that would have used the connection, and no ask to
 *  anybody about anything in living memory. Every test below changes exactly
 *  one thing about it, so a failure names its own cause. */
function moment(over: Record<string, unknown> = {}): NudgeContext {
  return {
    now: NOW,
    trigger: "in_task",
    localHour: 14,
    taskInFlight: false,
    resultDelivered: true,
    tasksThatWouldHaveUsedIt: 3,
    lastAskAnyAppAt: null,
    ...over,
  } as unknown as NudgeContext;
}

function decisionOf(n: ConnectNudge, c: NudgeContext): string {
  return shouldAsk(n, c).decision;
}

// ---------------------------------------------------------------------------
// THE CONTROL — a policy that never asks is not cautious, it is broken.
// ---------------------------------------------------------------------------

test("CONTROL: a clean, evidenced, in-hours, post-result moment asks", () => {
  const v = shouldAsk(row(), moment());
  assert.equal(v.decision, "ask");
  assert.ok(v.reason.length > 0, "every verdict carries a reason for the log");
});

test("CONTROL: every trigger the contract knows can ask a never-asked owner", () => {
  // Level 0's threshold is 0.5 and the weakest trigger scores 0.6, so at level
  // zero the score never blocks. If this goes red, either the score table or
  // the threshold moved and the first ask has silently become unreachable for
  // some real moment.
  for (const trigger of Object.keys(TRIGGER_SCORE) as NudgeTrigger[]) {
    assert.equal(decisionOf(row(), moment({ trigger })), "ask", `trigger ${trigger}`);
  }
});

test("the class adapter and the free function are the same policy", () => {
  const policy = new DefaultNudgePolicy();
  assert.deepEqual(policy.shouldAsk(row(), moment()), shouldAsk(row(), moment()));
});

// ---------------------------------------------------------------------------
// THE POLARITY. A floor: anything that is not "ask" is do-not-ask.
// ---------------------------------------------------------------------------

test("only an explicit ask is a licence to interrupt", () => {
  assert.equal(askIsLicensed({ decision: "ask", reason: "" }), true);
  assert.equal(askIsLicensed({ decision: "hold", reason: "" }), false);
  assert.equal(askIsLicensed({ decision: "never-again", reason: "" }), false);
  assert.equal(askIsLicensed({ decision: "no-verdict", reason: "" }), false);
  // The shapes a caller hits when something upstream broke. If any of these
  // were licences, a crash upstream would become a text message.
  assert.equal(askIsLicensed(null), false);
  assert.equal(askIsLicensed(undefined), false);
});

// ---------------------------------------------------------------------------
// LAW 1 — no app is hardcoded, and policy.ts cannot tell one from another.
// ---------------------------------------------------------------------------

test("the toolkit slug never changes a verdict, not even a slug invented today", () => {
  // The spec's rule is "NO APP IS HARDCODED": names, logos and the ask itself
  // come from the catalog at run time. Tested behaviourally rather than by
  // grepping the source, because the thing that matters is not whether the word
  // "gmail" appears in a comment — it is whether any branch can see it. The
  // reason strings are compared too: a per-app sentence in the log is a per-app
  // string table waiting to happen.
  const slugs = ["gmail", "notion", "slack", "a_toolkit_that_did_not_exist_yesterday"];
  const scenarios: Array<[ConnectNudge, NudgeContext]> = [
    [row(), moment()],
    [row({ state: "declined", level: 2, snooze_until: NOW + 5 * DAY }), moment()],
    [row({ state: "asked", sent_at: NOW - 80 * HOUR, trigger: "in_task" }), moment()],
    [row({ state: "connected" }), moment()],
    [row({ state: "declined", level: 3, snooze_until: NOW + 3000 * DAY }), moment()],
  ];
  for (const [n, c] of scenarios) {
    const verdicts = slugs.map((toolkit) => shouldAsk({ ...n, toolkit }, c));
    for (const v of verdicts) assert.deepEqual(v, verdicts[0]);
  }
});

// ---------------------------------------------------------------------------
// THE MOMENT FLOORS, each on its own.
// ---------------------------------------------------------------------------

test("never mid-step: taskInFlight holds", () => {
  assert.equal(decisionOf(row(), moment({ taskInFlight: true })), "hold");
});

test("never mid-step, even for the strongest possible moment", () => {
  // laptop_closed scores 1.0 and clears every threshold there is. If the score
  // could buy its way past the in-flight check, the strongest trigger would be
  // the one most likely to interrupt a running step.
  assert.equal(
    decisionOf(row(), moment({ taskInFlight: true, trigger: "laptop_closed" })),
    "hold",
  );
});

test("never before the task result: resultDelivered false holds", () => {
  assert.equal(decisionOf(row(), moment({ resultDelivered: false })), "hold");
});

test("quiet hours: 22:00 through 07:00 owner-local hold", () => {
  for (const localHour of [22, 23, 0, 1, 3, 6, 7]) {
    assert.equal(decisionOf(row(), moment({ localHour })), "hold", `${localHour}:00`);
  }
});

test("quiet hours: both boundaries, in the direction that costs sleep", () => {
  // Closed at the start, open at the end. 21:00 is the last hour we may ask and
  // 08:00 is the first — an off-by-one at either end is an hour of somebody's
  // night, every night, for as long as nobody checks.
  assert.equal(decisionOf(row(), moment({ localHour: QUIET_HOURS_START - 1 })), "ask");
  assert.equal(decisionOf(row(), moment({ localHour: QUIET_HOURS_START })), "hold");
  assert.equal(decisionOf(row(), moment({ localHour: QUIET_HOURS_END - 1 })), "hold");
  assert.equal(decisionOf(row(), moment({ localHour: QUIET_HOURS_END })), "ask");
});

test("evidence required: zero tasks is a hold, always", () => {
  assert.equal(decisionOf(row(), moment({ tasksThatWouldHaveUsedIt: 0 })), "hold");
});

test("evidence required: no trigger is strong enough to ask on a hunch", () => {
  for (const trigger of Object.keys(TRIGGER_SCORE) as NudgeTrigger[]) {
    assert.equal(
      decisionOf(row(), moment({ trigger, tasksThatWouldHaveUsedIt: 0 })),
      "hold",
      `trigger ${trigger} asked with no evidence`,
    );
  }
});

test("one evidenced task is enough", () => {
  assert.equal(decisionOf(row(), moment({ tasksThatWouldHaveUsedIt: 1 })), "ask");
});

// ---------------------------------------------------------------------------
// THE GLOBAL CAP — one ask per owner per 7 days, ACROSS ALL APPS.
// ---------------------------------------------------------------------------

test("an ask about ANY app inside 7 days holds this one", () => {
  // The row here is about Notion and has never been asked; the cap is about the
  // owner. Three browser tasks against three unconnected apps must not produce
  // three connect texts.
  for (const daysAgo of [0, 1, 3, 6]) {
    assert.equal(
      decisionOf(row(), moment({ lastAskAnyAppAt: NOW - daysAgo * DAY })),
      "hold",
      `${daysAgo}d ago`,
    );
  }
});

test("the 7-day cap opens exactly at 7 days", () => {
  const justInside = NOW - (GLOBAL_ASK_INTERVAL_DAYS * DAY - 1);
  const exactly = NOW - GLOBAL_ASK_INTERVAL_DAYS * DAY;
  assert.equal(decisionOf(row(), moment({ lastAskAnyAppAt: justInside })), "hold");
  assert.equal(decisionOf(row(), moment({ lastAskAnyAppAt: exactly })), "ask");
});

test("a last-ask timestamp in the FUTURE holds rather than opens", () => {
  // Clock skew between the Worker and D1 is real. Skew must never be the thing
  // that authorises an interruption.
  assert.equal(decisionOf(row(), moment({ lastAskAnyAppAt: NOW + 2 * DAY })), "hold");
});

// ---------------------------------------------------------------------------
// THE LADDER: 14 days, 45 days, stop.
// ---------------------------------------------------------------------------

const declinedL1 = () =>
  row({ state: "declined", level: 1, snooze_until: NOW + 10 * DAY, trigger: "in_task" });
const declinedL2 = () =>
  row({ state: "declined", level: 2, snooze_until: NOW + 20 * DAY, trigger: "in_task" });

test("level 1: inside the 14-day snooze, an ordinary trigger holds", () => {
  assert.equal(decisionOf(declinedL1(), moment({ trigger: "in_task" })), "hold");
  assert.equal(decisionOf(declinedL1(), moment({ trigger: "repeated_use" })), "hold");
  assert.equal(decisionOf(declinedL1(), moment({ trigger: "user_named_it" })), "hold");
});

test("level 1: a closed laptop overrides the snooze", () => {
  // The one moment where the ask is not a pitch: the task cannot run in the
  // browser at all, so we are naming something that is failing right now.
  assert.equal(decisionOf(declinedL1(), moment({ trigger: "laptop_closed" })), "ask");
});

test("level 1: the laptop-closed override fires ONCE", () => {
  // Once the override has been spent, the row's own trigger records that the
  // last thing this owner refused was exactly this pitch. Re-running it inside
  // the same snooze is asking a question they just answered.
  const spent = row({
    state: "declined",
    level: 1,
    snooze_until: NOW + 10 * DAY,
    trigger: "laptop_closed",
  });
  assert.equal(decisionOf(spent, moment({ trigger: "laptop_closed" })), "hold");
});

test("level 2: a closed laptop does NOT override the 45-day snooze", () => {
  // The override is a level-1 privilege. At level 2 the snooze is the answer.
  assert.equal(decisionOf(declinedL2(), moment({ trigger: "laptop_closed" })), "hold");
});

test("the override still obeys every moment floor", () => {
  // A floor that the strongest trigger can walk through is not a floor. Each of
  // these is the override arriving at a moment we may not interrupt.
  const l1 = declinedL1();
  assert.equal(decisionOf(l1, moment({ trigger: "laptop_closed", localHour: 3 })), "hold");
  assert.equal(decisionOf(l1, moment({ trigger: "laptop_closed", taskInFlight: true })), "hold");
  assert.equal(decisionOf(l1, moment({ trigger: "laptop_closed", resultDelivered: false })), "hold");
  assert.equal(
    decisionOf(l1, moment({ trigger: "laptop_closed", tasksThatWouldHaveUsedIt: 0 })),
    "hold",
  );
  assert.equal(
    decisionOf(l1, moment({ trigger: "laptop_closed", lastAskAnyAppAt: NOW - 2 * DAY })),
    "hold",
  );
});

test("level 1 after the snooze: only a moment that clears 0.8 may ask", () => {
  const expired = row({ state: "declined", level: 1, snooze_until: NOW - 1, trigger: "in_task" });
  assert.equal(decisionOf(expired, moment({ trigger: "repeated_use" })), "hold"); // 0.6
  assert.equal(decisionOf(expired, moment({ trigger: "onboarding" })), "hold"); // 0.7
  assert.equal(decisionOf(expired, moment({ trigger: "user_named_it" })), "ask"); // 0.9
  assert.equal(decisionOf(expired, moment({ trigger: "laptop_closed" })), "ask"); // 1.0
});

test("level 1 boundary: a trigger that only TIES the threshold does not ask", () => {
  // in_task scores 0.80 and level 1 requires more than 0.80. The contract says
  // "above"; the tie goes to the person who already said no once. This single
  // assertion is the whole difference between `>` and `>=`, and it is the one
  // place in the file where that choice is visible.
  const expired = row({ state: "declined", level: 1, snooze_until: NOW - 1, trigger: "onboarding" });
  assert.equal(TRIGGER_SCORE.in_task, 0.8);
  assert.equal(decisionOf(expired, moment({ trigger: "in_task" })), "hold");
});

test("level 2 after the snooze: repeated_use may NEVER ask again", () => {
  const expired = row({ state: "declined", level: 2, snooze_until: NOW - 1, trigger: "in_task" });
  assert.equal(decisionOf(expired, moment({ trigger: "repeated_use" })), "hold");
});

test("level 2 after the snooze: only in_task or laptop_closed are admitted at all", () => {
  const expired = row({ state: "declined", level: 2, snooze_until: NOW - 1, trigger: "in_task" });
  assert.equal(decisionOf(expired, moment({ trigger: "user_named_it" })), "hold");
  assert.equal(decisionOf(expired, moment({ trigger: "onboarding" })), "hold");
  assert.equal(decisionOf(expired, moment({ trigger: "laptop_closed" })), "ask");
  // in_task is on the state machine's allowlist and still cannot clear 0.95.
  // That is the contract tension recorded with this module: where the allowlist
  // and the score table disagree, the stricter one wins.
  assert.equal(decisionOf(expired, moment({ trigger: "in_task" })), "hold");
});

test("level 2 never admits repeated_use, even if the thresholds are retuned", () => {
  // WHY THIS TEST REACHES INTO CONFIG. Under today's numbers the level-2
  // allowlist is redundant: LEVEL_THRESHOLD[2] is 0.95 and only laptop_closed
  // (1.0) clears it, so deleting the allowlist changes no reachable outcome and
  // a mutation of policy.ts that removed it passed the whole suite. A guard no
  // test can kill is indistinguishable from dead code — so this test creates
  // the condition under which it is the ONLY guard: the contract calls these
  // values config ("Values are config, not code"), and the day somebody lowers
  // level 2 to buy back some conversions, "never repeated_use" must still hold.
  // It is page 24's sentence, and it is about the owner, not about a number.
  const original = LEVEL_THRESHOLD[2];
  try {
    (LEVEL_THRESHOLD as Record<number, number>)[2] = 0.5;
    const expired = row({ state: "declined", level: 2, snooze_until: NOW - 1, trigger: "in_task" });
    assert.equal(decisionOf(expired, moment({ trigger: "repeated_use" })), "hold");
    assert.equal(decisionOf(expired, moment({ trigger: "user_named_it" })), "hold");
    // ...and the two the state machine does admit come back the moment the
    // threshold allows them, so this is an allowlist and not a second stop.
    assert.equal(decisionOf(expired, moment({ trigger: "in_task" })), "ask");
  } finally {
    (LEVEL_THRESHOLD as Record<number, number>)[2] = original;
  }
  assert.equal(LEVEL_THRESHOLD[2], 0.95);
});

test("level 3 stops, whatever the moment looks like", () => {
  const stopped = row({ state: "declined", level: 3, snooze_until: NOW + 3000 * DAY });
  for (const trigger of Object.keys(TRIGGER_SCORE) as NudgeTrigger[]) {
    assert.equal(decisionOf(stopped, moment({ trigger })), "never-again", `trigger ${trigger}`);
  }
});

test("level 3 reports 'never-again' rather than a hold that invites a retry", () => {
  // The distinction is operational: a caller may use never-again to stop
  // scheduling this row at all, while a hold says "try again tomorrow". An
  // owner who is done being asked must not be re-queued nightly forever.
  const stopped = row({ state: "declined", level: 3, snooze_until: NOW + 3000 * DAY });
  assert.equal(decisionOf(stopped, moment({ localHour: 3 })), "never-again");
  assert.equal(decisionOf(stopped, moment({ taskInFlight: true })), "never-again");
});

// ---------------------------------------------------------------------------
// SNOOZE ARITHMETIC — 14 / 45 / stop, and the onboarding exception.
// ---------------------------------------------------------------------------

test("each decline moves one rung and sets that rung's snooze", () => {
  const first = recordDecline(row({ trigger: "in_task", state: "asked" }), NOW, "said_no");
  assert.equal(first.state, "declined");
  assert.equal(first.level, 1);
  assert.equal(first.snooze_until, NOW + SNOOZE_DAYS[1] * DAY);
  assert.equal(SNOOZE_DAYS[1], 14);

  const second = recordDecline(first, NOW, "said_no");
  assert.equal(second.level, 2);
  assert.equal(second.snooze_until, NOW + SNOOZE_DAYS[2] * DAY);
  assert.equal(SNOOZE_DAYS[2], 45);

  const third = recordDecline(second, NOW, "said_no");
  assert.equal(third.level, 3);
  assert.equal(third.snooze_until, NOW + SNOOZE_DAYS[3] * DAY);

  // The ladder has a top. A fourth decline cannot mint a level 4 that no
  // threshold in the contract knows what to do with.
  assert.equal(recordDecline(third, NOW, "said_no").level, 3);
});

test("skipping an onboarding card snoozes 7 days, not 14", () => {
  // Somebody skipping a card during setup has refused a form, not an app.
  const skipped = recordDecline(row({ trigger: "onboarding", state: "asked" }), NOW, "said_no");
  assert.equal(skipped.snooze_until, NOW + ONBOARDING_SKIP_SNOOZE_DAYS * DAY);
  assert.notEqual(ONBOARDING_SKIP_SNOOZE_DAYS, SNOOZE_DAYS[1]);
});

test("the onboarding exception applies once; a second no is a second no", () => {
  const l1 = row({ trigger: "onboarding", state: "declined", level: 1 });
  assert.equal(recordDecline(l1, NOW, "said_no").snooze_until, NOW + SNOOZE_DAYS[2] * DAY);
});

test("a silent decline never claims the owner acted", () => {
  // acted_at is what the spec's timers get tuned from. Stamping it on somebody
  // who said nothing records an action that did not happen.
  assert.equal(recordDecline(row({ state: "asked" }), NOW, "silence").acted_at, null);
  assert.equal(recordDecline(row({ state: "asked" }), NOW, "said_no").acted_at, NOW);
});

test("recording a decline mutates nothing", () => {
  const original = row({ state: "asked", trigger: "in_task" });
  const frozen = Object.freeze({ ...original });
  const after = recordDecline(frozen as ConnectNudge, NOW, "said_no");
  assert.equal(frozen.level, 0);
  assert.equal(frozen.state, "asked");
  assert.notEqual(after.level, frozen.level);
});

// ---------------------------------------------------------------------------
// 72 HOURS OF SILENCE IS AN ANSWER.
// ---------------------------------------------------------------------------

const asked = (sentAt: number, over: Record<string, unknown> = {}) =>
  row({ state: "asked", sent_at: sentAt, trigger: "in_task", ...over });

test("an open ask holds every other ask while it is still open", () => {
  assert.equal(decisionOf(asked(NOW - 1 * HOUR), moment()), "hold");
  assert.equal(decisionOf(asked(NOW - 71 * HOUR), moment({ trigger: "laptop_closed" })), "hold");
});

test("at exactly 72 hours the silence becomes a decline", () => {
  // The same trigger flips from hold to ask across the boundary, and the reason
  // it flips is that the row is now a LEVEL 1 DECLINE — so the level-1
  // laptop-closed override is what licenses this ask, not the open question.
  const boundary = NOW - SILENCE_IS_A_SOFT_NO_HOURS * HOUR;
  assert.equal(SILENCE_IS_A_SOFT_NO_HOURS, 72);
  assert.equal(decisionOf(asked(boundary + 1), moment({ trigger: "laptop_closed" })), "hold");
  assert.equal(decisionOf(asked(boundary), moment({ trigger: "laptop_closed" })), "ask");
});

test("silence puts the owner in a 14-day snooze, not back at the start", () => {
  // Without the promotion, an unanswered ask would sit in `asked` forever and
  // every fresh trigger would look like a first ask. With it, the ordinary
  // triggers are snoozed exactly as if they had tapped skip.
  const silent = asked(NOW - 80 * HOUR);
  assert.equal(decisionOf(silent, moment({ trigger: "in_task" })), "hold");
  assert.equal(decisionOf(silent, moment({ trigger: "repeated_use" })), "hold");
  assert.equal(decisionOf(silent, moment({ trigger: "user_named_it" })), "hold");
});

test("the silence snooze is counted from when the silence matured", () => {
  // Not from `now`. A policy consulted a month late must not restart a 14-day
  // clock that has already run out.
  const sent = NOW - (SILENCE_IS_A_SOFT_NO_HOURS * HOUR + SNOOZE_DAYS[1] * DAY);
  assert.equal(decisionOf(asked(sent), moment({ trigger: "user_named_it" })), "ask");
  assert.equal(decisionOf(asked(sent + 2 * HOUR), moment({ trigger: "user_named_it" })), "hold");
});

test("silence at level 2 reaches the end of the ladder", () => {
  const silentAtL2 = asked(NOW - 80 * HOUR, { level: 2 });
  assert.equal(decisionOf(silentAtL2, moment({ trigger: "laptop_closed" })), "never-again");
});

test("an 'asked' row with no sent_at is undecidable, not fresh", () => {
  assert.equal(decisionOf(row({ state: "asked", sent_at: null }), moment()), "no-verdict");
});

test("an 'asked' row that was acted on is undecidable, not fresh", () => {
  // They did something and nobody wrote down what. One of the two possibilities
  // makes asking again a repeat of a question already answered.
  assert.equal(
    decisionOf(asked(NOW - 80 * HOUR, { acted_at: NOW - 79 * HOUR }), moment()),
    "no-verdict",
  );
});

// ---------------------------------------------------------------------------
// CONNECTED AND NEEDS_RECONNECT.
// ---------------------------------------------------------------------------

test("a connected app is held, never stopped forever", () => {
  // `hold` and not `never-again`: the next transition in the state machine is
  // connected -> expired -> needs_reconnect, and a row marked never-again is a
  // row nothing reopens. Getting this wrong makes an expired token permanently
  // unmentionable.
  assert.equal(decisionOf(row({ state: "connected" }), moment()), "hold");
});

test("a broken connection gets one gentle ask", () => {
  const stale = row({ state: "needs_reconnect", sent_at: NOW - 60 * DAY, trigger: "in_task" });
  assert.equal(decisionOf(stale, moment()), "ask");
  assert.equal(decisionOf(row({ state: "needs_reconnect", sent_at: null }), moment()), "ask");
});

test("after the gentle ask, a reconnect is weekly at most", () => {
  const justAsked = row({ state: "needs_reconnect", sent_at: NOW - 2 * DAY });
  assert.equal(decisionOf(justAsked, moment()), "hold");
  const aWeekAgo = row({ state: "needs_reconnect", sent_at: NOW - 7 * DAY });
  assert.equal(decisionOf(aWeekAgo, moment()), "ask");
});

test("a reconnect ask obeys every moment floor", () => {
  const stale = row({ state: "needs_reconnect", sent_at: NOW - 60 * DAY });
  assert.equal(decisionOf(stale, moment({ localHour: 2 })), "hold");
  assert.equal(decisionOf(stale, moment({ taskInFlight: true })), "hold");
  assert.equal(decisionOf(stale, moment({ resultDelivered: false })), "hold");
  assert.equal(decisionOf(stale, moment({ tasksThatWouldHaveUsedIt: 0 })), "hold");
  assert.equal(decisionOf(stale, moment({ lastAskAnyAppAt: NOW - DAY })), "hold");
});

test("a reconnect is not sold by the ladder: an old decline does not silence it", () => {
  // The ladder governs "will you connect an app you have not connected". This
  // owner already chose the app; the connection broke. Reaching a connected
  // state at all is the owner reopening it, which is the only thing the spec
  // says counts at the top of the ladder — so level 3, which stops a connect
  // ask forever, does not stop a repair.
  const repaired = row({
    state: "needs_reconnect",
    level: 3,
    snooze_until: null,
    sent_at: NOW - 60 * DAY,
  });
  assert.equal(decisionOf(repaired, moment()), "ask");
  assert.equal(decisionOf({ ...repaired, snooze_until: NOW - DAY }, moment()), "ask");
});

test("an active snooze silences a reconnect too", () => {
  // The level ladder does not reach the reconnect path; a DATE does. This was a
  // real hole in the first draft: a row left dirty by the caller, or one
  // deliberately quietened, would have been texted every week regardless of
  // what the row said. Where a stale snooze and a broken connection disagree,
  // the unsent ask costs a fallback to the browser and the unwanted one costs
  // the owner's attention.
  const snoozed = row({
    state: "needs_reconnect",
    snooze_until: NOW + 3 * DAY,
    sent_at: NOW - 60 * DAY,
  });
  assert.equal(decisionOf(snoozed, moment()), "hold");
});

// ---------------------------------------------------------------------------
// NO-VERDICT — every input that must not be guessed at.
// ---------------------------------------------------------------------------

test("a missing nudge record is not a fresh owner", () => {
  assert.equal(decisionOf(null as unknown as ConnectNudge, moment()), "no-verdict");
  assert.equal(decisionOf(undefined as unknown as ConnectNudge, moment()), "no-verdict");
});

test("a missing moment cannot be judged", () => {
  assert.equal(decisionOf(row(), null as unknown as NudgeContext), "no-verdict");
});

test("a nudge row addressed to a NAME is unreadable, not askable", () => {
  // The exact spike failure: `user_id` was "omar" and a connection bound to one
  // operator's mailbox. A row that cannot name an owner ROW id must not produce
  // a connect link, because the link binds to whoever the row says.
  for (const bad of ["omar", "jose@anticipy.ai", "", "SXKOTD1H02QB6GW", "short", 12345, null]) {
    assert.equal(decisionOf(row({ user_id: bad }), moment()), "no-verdict", JSON.stringify(bad));
  }
});

test("an unknown local hour is never assumed", () => {
  for (const localHour of [undefined, null, NaN, -1, 24, 25, 12.5, "14"]) {
    assert.equal(decisionOf(row(), moment({ localHour })), "no-verdict", JSON.stringify(localHour));
  }
});

test("an unknown trigger has no score and buys no ask", () => {
  for (const trigger of [undefined, null, "", "laptop-closed", "IN_TASK", 1]) {
    assert.equal(decisionOf(row(), moment({ trigger })), "no-verdict", JSON.stringify(trigger));
  }
});

test("a trigger borrowed from Object.prototype is not a trigger", () => {
  // `TRIGGER_SCORE["constructor"]` is a function, not undefined. A membership
  // test written as `!== undefined` would call this a known trigger and then
  // compare a function against a number.
  for (const trigger of ["constructor", "toString", "__proto__", "hasOwnProperty"]) {
    assert.equal(decisionOf(row(), moment({ trigger })), "no-verdict", trigger);
  }
});

test("an unreadable state is not 'probably never asked'", () => {
  for (const state of ["declined_l2", "DECLINED", "", null, undefined, 3]) {
    assert.equal(decisionOf(row({ state }), moment()), "no-verdict", JSON.stringify(state));
  }
});

test("an unreadable decline level is not level 0", () => {
  for (const level of [-1, 4, 1.5, "1", null, undefined, NaN]) {
    assert.equal(decisionOf(row({ level }), moment()), "no-verdict", JSON.stringify(level));
  }
});

test("a declined row still sitting at level 0 is undecidable", () => {
  // The caller failed to advance the ladder. Read as level 0 it re-asks at the
  // next trigger, ignoring a no this system was actually told.
  assert.equal(decisionOf(row({ state: "declined", level: 0 }), moment()), "no-verdict");
});

test("unreadable timestamps on the row are undecidable", () => {
  assert.equal(decisionOf(row({ sent_at: "yesterday" }), moment()), "no-verdict");
  assert.equal(decisionOf(row({ acted_at: NaN }), moment()), "no-verdict");
  assert.equal(decisionOf(row({ snooze_until: Infinity }), moment()), "no-verdict");
  assert.equal(decisionOf(row({ trigger: "in_taskk" }), moment()), "no-verdict");
});

test("an unread ask history is not an empty ask history", () => {
  // `null` means "looked, never asked anyone". `undefined` means "did not
  // look". Collapsing them turns a forgotten query into three connect texts in
  // one minute.
  assert.equal(decisionOf(row(), moment({ lastAskAnyAppAt: undefined })), "no-verdict");
  assert.equal(decisionOf(row(), moment({ lastAskAnyAppAt: "2026-09-05" })), "no-verdict");
  assert.equal(decisionOf(row(), moment({ lastAskAnyAppAt: null })), "ask");
});

test("an unusable clock decides nothing", () => {
  for (const now of [undefined, null, NaN, Infinity, "now"]) {
    assert.equal(decisionOf(row(), moment({ now })), "no-verdict", JSON.stringify(now));
  }
});

test("unknown in-flight or delivery status decides nothing", () => {
  for (const bad of [undefined, null, 0, 1, "false"]) {
    assert.equal(decisionOf(row(), moment({ taskInFlight: bad })), "no-verdict", JSON.stringify(bad));
    assert.equal(
      decisionOf(row(), moment({ resultDelivered: bad })),
      "no-verdict",
      JSON.stringify(bad),
    );
  }
});

test("an unreadable evidence count is not zero and is not enough", () => {
  for (const n of [undefined, null, -1, 2.5, "3", NaN]) {
    assert.equal(
      decisionOf(row(), moment({ tasksThatWouldHaveUsedIt: n })),
      "no-verdict",
      JSON.stringify(n),
    );
  }
});

// ---------------------------------------------------------------------------
// INVARIANTS — swept over every combination the contract can produce.
// ---------------------------------------------------------------------------

test("the policy never mutates what it is handed", () => {
  // A policy that edits the row is a policy that has silently become the writer,
  // and the caller's next read would disagree with D1.
  const n = Object.freeze(row({ state: "asked", sent_at: NOW - 80 * HOUR, trigger: "in_task" }));
  const c = Object.freeze(moment({ trigger: "laptop_closed" }));
  const nBefore = JSON.stringify(n);
  const cBefore = JSON.stringify(c);
  shouldAsk(n as ConnectNudge, c as NudgeContext);
  assert.equal(JSON.stringify(n), nBefore);
  assert.equal(JSON.stringify(c), cBefore);
});

test("an ask is only ever returned when EVERY floor is clear", () => {
  // The sweep: 2,160 moments. It asserts the implication, not the outcome — the
  // point is that no combination of a strong trigger and a low level can buy a
  // way past a floor. A single missing `return` in policy.ts fails this.
  const triggers = Object.keys(TRIGGER_SCORE) as NudgeTrigger[];
  let asks = 0;
  let seen = 0;
  for (const trigger of triggers) {
    for (const level of [0, 1, 2] as const) {
      for (const localHour of [0, 7, 8, 14, 21, 22]) {
        for (const taskInFlight of [true, false]) {
          for (const resultDelivered of [true, false]) {
            for (const tasksThatWouldHaveUsedIt of [0, 2]) {
              for (const lastAskAnyAppAt of [null, NOW - DAY, NOW - 8 * DAY]) {
                seen += 1;
                const n = row(
                  level === 0 ? {} : { state: "declined", level, snooze_until: NOW - 1 },
                );
                const c = moment({
                  trigger,
                  localHour,
                  taskInFlight,
                  resultDelivered,
                  tasksThatWouldHaveUsedIt,
                  lastAskAnyAppAt,
                });
                const v = shouldAsk(n, c);
                assert.ok(
                  ["ask", "hold", "never-again", "no-verdict"].includes(v.decision),
                  `unknown decision ${v.decision}`,
                );
                if (v.decision !== "ask") continue;
                asks += 1;
                assert.equal(taskInFlight, false);
                assert.equal(resultDelivered, true);
                assert.ok(localHour >= QUIET_HOURS_END && localHour < QUIET_HOURS_START);
                assert.ok(tasksThatWouldHaveUsedIt > 0);
                assert.ok(
                  lastAskAnyAppAt === null || NOW - lastAskAnyAppAt >= GLOBAL_ASK_INTERVAL_DAYS * DAY,
                );
                assert.ok(TRIGGER_SCORE[trigger] > 0.5);
              }
            }
          }
        }
      }
    }
  }
  assert.equal(seen, 2160);
  // ...and the other half of the implication: the sweep must actually contain
  // asks, or it is 2,160 assertions about a function that always holds.
  assert.ok(asks > 0, "the sweep never asked once — a policy that never asks is broken");
});
