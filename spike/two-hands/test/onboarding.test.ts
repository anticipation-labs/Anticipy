// The connect-nudge suite.
//
// Two things it is really testing, under all the branches:
//
//  1. That every hold reason actually holds. Each one of them is a recorded
//     complaint shape from this repo's own history — the 15-texts-in-65-seconds
//     burst, the 63-messages-in-a-day stuck loop, quiet hours. A hold reason
//     with no test is a comment.
//  2. That NOTHING here knows an app. The whole shouldNudge suite runs twice,
//     once for "gmail" and once for "zorptastic-9000", and the assertions are
//     identical. If anybody ever adds a list of app names, the second run is
//     where it dies.
//
// No network, no key, no account: every dependency is a literal in this file.

import { describe, it } from "node:test";
import assert from "node:assert/strict";

import type { ToolCandidate } from "../src/contract.ts";
import {
  GLOBAL_COOLDOWN_MS,
  MAX_SMS_CHARS,
  REASK_AFTER_MS,
  accountChoice,
  nudgeText,
  onConnected,
  onDeclined,
  onSent,
  onWouldHaveUsed,
  scopesFor,
  shouldNudge,
} from "../src/onboarding.ts";
import type { NudgeCtx, NudgeRecord, TaggedAccount } from "../src/onboarding.ts";

const OWNER = "owner-1";
const DAY = 24 * 60 * 60 * 1000;

/** A UTC instant on a fixed date, so "owner-local hour" is the only variable. */
function atUtc(hour: number, minute = 0): number {
  return Date.UTC(2026, 8, 7, hour, minute, 0);
}

function row(app: string, over: Partial<NudgeRecord> = {}): NudgeRecord {
  return {
    user_id: OWNER,
    app,
    state: "queued",
    sent_at: null,
    channel: null,
    tasks_that_would_have_used_it: 1,
    declined_at: null,
    ...over,
  };
}

function ctx(over: Partial<NudgeCtx> = {}): NudgeCtx {
  return {
    userId: OWNER,
    now: atUtc(10),
    ownerTimeZone: "UTC",
    taskRunning: false,
    lastNudgeAnyAppAt: null,
    ...over,
  };
}

function tool(over: Partial<ToolCandidate> = {}): ToolCandidate {
  return {
    toolSlug: "SOMEAPP_DO_THING",
    app: "someapp",
    score: 0.9,
    schema: {},
    description: "does the thing",
    ...over,
  };
}

function account(over: Partial<TaggedAccount> = {}): TaggedAccount {
  return {
    app: "someapp",
    accountId: "acct-1",
    label: "someapp",
    scopes: [],
    status: "active",
    ...over,
  };
}

// ---------------------------------------------------------------------------
// shouldNudge — run once per app name, and the second app name is one this
// module has never seen and never will.
// ---------------------------------------------------------------------------
for (const APP of ["gmail", "zorptastic-9000"]) {
  describe(`shouldNudge (${APP})`, () => {
    it("asks when there is evidence, no history, and it is the middle of the day", () => {
      const a = shouldNudge(APP, row(APP, { tasks_that_would_have_used_it: 2 }), ctx());
      assert.equal(a.verdict, "ask");
      assert.equal(a.cause, "licensed");
    });

    it("holds during a run — the nudge lands after it, never inside it", () => {
      const a = shouldNudge(APP, row(APP), ctx({ taskRunning: true }));
      assert.equal(a.verdict, "hold");
      assert.equal(a.cause, "task-running");
    });

    it("holds with no evidence: a nudge no task has needed is an advertisement", () => {
      const a = shouldNudge(APP, row(APP, { tasks_that_would_have_used_it: 0 }), ctx());
      assert.equal(a.verdict, "hold");
      assert.equal(a.cause, "no-evidence");
    });

    it("holds when there is no row at all — no row means no task has needed it", () => {
      const a = shouldNudge(APP, null, ctx());
      assert.equal(a.verdict, "hold");
      assert.equal(a.cause, "no-evidence");
    });

    // Quiet hours, both ends. 22:00 is closed, 08:00 is open.
    it("holds at 22:00 owner-local exactly", () => {
      const a = shouldNudge(APP, row(APP), ctx({ now: atUtc(22, 0) }));
      assert.equal(a.verdict, "hold");
      assert.equal(a.cause, "quiet-hours");
    });

    it("holds at 21:59 is FALSE — 21:59 still asks", () => {
      const a = shouldNudge(APP, row(APP), ctx({ now: atUtc(21, 59) }));
      assert.equal(a.verdict, "ask");
    });

    it("holds at 07:59 owner-local", () => {
      const a = shouldNudge(APP, row(APP), ctx({ now: atUtc(7, 59) }));
      assert.equal(a.verdict, "hold");
      assert.equal(a.cause, "quiet-hours");
    });

    it("asks at 08:00 owner-local exactly", () => {
      const a = shouldNudge(APP, row(APP), ctx({ now: atUtc(8, 0) }));
      assert.equal(a.verdict, "ask");
    });

    it("holds at 03:00 owner-local even though the server clock says 10:00", () => {
      // The same instant that asks in UTC is 3am in Los Angeles. A server-local
      // hour check would text this owner at 3am and pass every UTC test.
      const a = shouldNudge(APP, row(APP), ctx({ now: atUtc(10), ownerTimeZone: "America/Los_Angeles" }));
      assert.equal(a.verdict, "hold");
      assert.equal(a.cause, "quiet-hours");
    });

    it("respects a half-hour timezone offset at the quiet-hours boundary", () => {
      // Kolkata is UTC+5:30, so 02:15Z is 07:45 local (quiet) and 02:45Z is
      // 08:15 local (awake). An offset rounded to whole hours gets one of these
      // wrong every single morning.
      const quiet = shouldNudge(APP, row(APP), ctx({ now: atUtc(2, 15), ownerTimeZone: "Asia/Kolkata" }));
      const awake = shouldNudge(APP, row(APP), ctx({ now: atUtc(2, 45), ownerTimeZone: "Asia/Kolkata" }));
      assert.equal(quiet.cause, "quiet-hours");
      assert.equal(awake.verdict, "ask");
    });

    it("holds when any other app was nudged inside 24h", () => {
      const a = shouldNudge(APP, row(APP), ctx({ lastNudgeAnyAppAt: atUtc(10) - (GLOBAL_COOLDOWN_MS - 1) }));
      assert.equal(a.verdict, "hold");
      assert.equal(a.cause, "global-cooldown");
    });

    it("asks once the 24h global cooldown has passed", () => {
      const a = shouldNudge(APP, row(APP), ctx({ lastNudgeAnyAppAt: atUtc(10) - GLOBAL_COOLDOWN_MS }));
      assert.equal(a.verdict, "ask");
    });

    it("gives no verdict when the nudge history was never read", () => {
      // `undefined` is "did not look", not "never nudged". Three browser tasks
      // in a row must not become three connect texts because a lookup was
      // skipped.
      const c = ctx();
      delete (c as Record<string, unknown>).lastNudgeAnyAppAt;
      const a = shouldNudge(APP, row(APP), c);
      assert.equal(a.verdict, "no-verdict");
      assert.equal(a.cause, "unknown-nudge-history");
    });

    it("gives no verdict with no timezone rather than falling back to UTC", () => {
      const a = shouldNudge(APP, row(APP), ctx({ ownerTimeZone: null }));
      assert.equal(a.verdict, "no-verdict");
      assert.equal(a.cause, "unknown-timezone");
    });

    it("gives no verdict on an unusable timezone string", () => {
      const a = shouldNudge(APP, row(APP), ctx({ ownerTimeZone: "Not/AZone" }));
      assert.equal(a.verdict, "no-verdict");
      assert.equal(a.cause, "unknown-timezone");
    });

    it("gives no verdict with no usable clock", () => {
      const a = shouldNudge(APP, row(APP), ctx({ now: Number.NaN }));
      assert.equal(a.verdict, "no-verdict");
      assert.equal(a.cause, "unknown-clock");
    });

    it("gives no verdict when the row is for a different app", () => {
      const a = shouldNudge(APP, row("some-other-app"), ctx());
      assert.equal(a.verdict, "no-verdict");
      assert.equal(a.cause, "row-mismatch");
    });

    it("gives no verdict when the row belongs to another owner", () => {
      const a = shouldNudge(APP, row(APP, { user_id: "owner-2" }), ctx());
      assert.equal(a.verdict, "no-verdict");
      assert.equal(a.cause, "row-mismatch");
    });

    it("gives no verdict on an unreadable nudge state", () => {
      const a = shouldNudge(APP, row(APP, { state: "sorta-queued" as never }), ctx());
      assert.equal(a.verdict, "no-verdict");
      assert.equal(a.cause, "malformed-state");
    });

    it("never asks again once the app is connected", () => {
      const a = shouldNudge(APP, row(APP, { state: "connected" }), ctx());
      assert.equal(a.verdict, "never-again");
      assert.equal(a.cause, "already-connected");
    });

    it("holds inside the 14-day window after a decline", () => {
      const now = atUtc(10);
      const a = shouldNudge(
        APP,
        row(APP, { state: "declined", declined_at: now - (REASK_AFTER_MS - 1), declines: 1 }),
        ctx({ now }),
      );
      assert.equal(a.verdict, "hold");
      assert.equal(a.cause, "declined-recently");
    });

    it("re-asks once, exactly 14 days after a single decline", () => {
      const now = atUtc(10);
      const a = shouldNudge(
        APP,
        row(APP, { state: "declined", declined_at: now - REASK_AFTER_MS, declines: 1 }),
        ctx({ now }),
      );
      assert.equal(a.verdict, "ask");
    });

    it("never asks again after a second decline", () => {
      const now = atUtc(10);
      const a = shouldNudge(
        APP,
        row(APP, { state: "declined", declined_at: now - 90 * DAY, declines: 2 }),
        ctx({ now }),
      );
      assert.equal(a.verdict, "never-again");
      assert.equal(a.cause, "declined-twice");
    });

    it("never asks again after two asks nobody answered", () => {
      const now = atUtc(10);
      const a = shouldNudge(APP, row(APP, { state: "sent", sent_at: now - 90 * DAY, asks: 2 }), ctx({ now }));
      assert.equal(a.verdict, "never-again");
      assert.equal(a.cause, "asked-twice");
    });

    it("holds inside the 14-day window after a single unanswered ask", () => {
      const now = atUtc(10);
      const a = shouldNudge(APP, row(APP, { state: "sent", sent_at: now - 3 * DAY, asks: 1 }), ctx({ now }));
      assert.equal(a.verdict, "hold");
      assert.equal(a.cause, "one-nudge-per-app");
    });

    it("uses the LATEST of sent_at and declined_at, so an old decline cannot re-open a fresh ask", () => {
      // The bare-contract-row shape: no counters, declined 20 days ago,
      // re-asked 2 days ago. Reading declined_at first and stopping there says
      // "ask" and nudges twice in a week.
      const now = atUtc(10);
      const bare = {
        user_id: OWNER,
        app: APP,
        state: "sent",
        sent_at: now - 2 * DAY,
        channel: "sms",
        tasks_that_would_have_used_it: 3,
        declined_at: now - 20 * DAY,
      } as NudgeRecord;
      const a = shouldNudge(APP, bare, ctx({ now }));
      assert.equal(a.verdict, "hold");
      assert.equal(a.cause, "one-nudge-per-app");
    });

    it("asks anyway when the OWNER asked — a solicited link is not an interruption", () => {
      // Declined twice, mid-run, 3am, no evidence, inside the global cooldown:
      // every gate is against it, and none of them are about this case.
      const now = atUtc(3);
      const a = shouldNudge(
        APP,
        row(APP, { state: "declined", declined_at: now - DAY, declines: 2, tasks_that_would_have_used_it: 0 }),
        ctx({ now, taskRunning: true, lastNudgeAnyAppAt: now - 60_000, ownerAskedFor: true }),
      );
      assert.equal(a.verdict, "ask");
      assert.equal(a.cause, "owner-asked");
    });

    it("refuses to nudge about a blank app name", () => {
      const a = shouldNudge("   ", row(APP), ctx());
      assert.equal(a.verdict, "no-verdict");
    });
  });
}

describe("shouldNudge behaves identically for an app it has never seen", () => {
  it("produces the same verdict and cause for gmail and for a made-up app", () => {
    // The suite above proves it case by case; this proves it as a whole, so a
    // future app-name special case cannot hide inside one branch.
    const cases: Array<[NudgeRecord | null, Partial<NudgeCtx>]> = [
      [null, {}],
      [row("X", { tasks_that_would_have_used_it: 4 }), {}],
      [row("X"), { taskRunning: true }],
      [row("X"), { now: atUtc(23) }],
      [row("X", { state: "connected" }), {}],
      [row("X", { state: "declined", declined_at: atUtc(10) - DAY, declines: 1 }), {}],
    ];
    for (const [template, over] of cases) {
      const known = template === null ? null : { ...template, app: "gmail" };
      const alien = template === null ? null : { ...template, app: "qqq-never-heard-of-it" };
      const a = shouldNudge("gmail", known, ctx(over));
      const b = shouldNudge("qqq-never-heard-of-it", alien, ctx(over));
      assert.equal(a.verdict, b.verdict);
      assert.equal(a.cause, b.cause);
    }
  });
});

// ---------------------------------------------------------------------------
// nudgeText
// ---------------------------------------------------------------------------
describe("nudgeText", () => {
  const scopes = { scopes: ["https://www.googleapis.com/auth/gmail.send"], toolsWithoutDeclaredScopes: [], minimal: true };
  const base = {
    what_it_would_do: "sending that note to Sam",
    browser_ms: 252_000,
    api_ms_estimate: 2_000,
    tasks_that_would_have_used_it: 4,
    connectUrl: "https://connect.example/c/abc123",
    scopes,
  };

  it("names what the browser hand cost, in real units", () => {
    const text = nudgeText("gmail", base);
    assert.ok(text.includes("4m 12s"), text);
  });

  it("carries the connect link intact", () => {
    assert.ok(nudgeText("gmail", base).includes(base.connectUrl));
  });

  it("says what it gets and that it gets nothing else", () => {
    const text = nudgeText("gmail", base);
    assert.ok(text.includes("gmail.send"), text);
    assert.ok(text.includes("nothing else"), text);
  });

  it("puts exactly one tappable link in the message", () => {
    // A URL-shaped Google scope printed whole is a second link in a message
    // whose only job is to get the first one tapped, and the wrong tap is a
    // googleapis 404 that reads as "this is broken".
    const text = nudgeText("gmail", base);
    assert.equal(text.split("https://").length - 1, 1, text);
  });

  it("drops the scope list rather than print two scopes that read as one", () => {
    const text = nudgeText("gmail", {
      ...base,
      scopes: {
        scopes: [
          "https://www.googleapis.com/auth/gmail.send",
          "https://example.test/other/gmail.send",
        ],
        toolsWithoutDeclaredScopes: [],
        minimal: true,
      },
    });
    assert.ok(!text.includes("nothing else"), text);
    assert.ok(text.includes("consent screen"), text);
  });

  it("is one message", () => {
    assert.ok(nudgeText("gmail", base).length <= MAX_SMS_CHARS, nudgeText("gmail", base));
  });

  it("still fits one message with a real four-scope Google set", () => {
    const text = nudgeText("gmail", {
      ...base,
      scopes: {
        scopes: [
          "https://www.googleapis.com/auth/gmail.send",
          "https://www.googleapis.com/auth/gmail.compose",
          "https://www.googleapis.com/auth/gmail.modify",
          "https://www.googleapis.com/auth/contacts.readonly",
        ],
        toolsWithoutDeclaredScopes: [],
        minimal: true,
      },
    });
    assert.ok(text.length <= MAX_SMS_CHARS, `${text.length}: ${text}`);
    assert.ok(text.includes("contacts.readonly"), text);
  });

  it("falls back to the consent screen, link intact, when the list cannot fit", () => {
    const text = nudgeText("gmail", {
      ...base,
      scopes: {
        scopes: ["one.long.scope.name.that.will.not.fit", "another.long.scope.name.also", "a.third.one.here.too"],
        toolsWithoutDeclaredScopes: [],
        minimal: true,
      },
    });
    assert.ok(text.length <= MAX_SMS_CHARS, `${text.length}: ${text}`);
    assert.ok(text.includes(base.connectUrl), text);
    // The consent screen is the authoritative list, so pointing at it is true
    // even when the message has no room to print it.
    assert.ok(text.includes("consent screen"), text);
  });

  it("does not claim narrowness when a matched tool declared no scopes", () => {
    const text = nudgeText("gmail", {
      ...base,
      scopes: { scopes: [], toolsWithoutDeclaredScopes: ["GMAIL_SEND_EMAIL"], minimal: false },
    });
    assert.ok(!text.includes("nothing else"), text);
    assert.ok(text.includes("consent screen"), text);
  });

  it("never invents an API time it has not measured", () => {
    const text = nudgeText("gmail", { ...base, api_ms_estimate: null });
    assert.ok(!text.includes("about "), text);
    assert.ok(text.includes("one call instead of a browser session"), text);
  });

  it("drops the task count rather than the link when it has to shed characters", () => {
    const text = nudgeText("gmail", {
      ...base,
      connectUrl: `https://connect.example/c/${"z".repeat(120)}`,
      scopes: { scopes: ["a".repeat(80)], toolsWithoutDeclaredScopes: [], minimal: true },
    });
    assert.ok(text.includes(`https://connect.example/c/${"z".repeat(120)}`), text);
  });

  it("reads the same for an app it has never seen", () => {
    const known = nudgeText("gmail", base);
    const alien = nudgeText("zorptastic-9000", base);
    assert.equal(alien, known.replace("gmail —", "zorptastic-9000 —"));
  });

  it("is not a wall of text and not a form", () => {
    const text = nudgeText("gmail", base);
    assert.ok(!text.includes("\n"), text);
    // Sentence enders only — a dot inside "gmail.send" or a URL is not a
    // sentence, and counting it as one is how a four-sentence message reads as
    // a nine-sentence one.
    const sentences = text.match(/[.?!](\s|$)/g) ?? [];
    assert.ok(sentences.length <= 5, `${sentences.length}: ${text}`);
  });

  it("leaves no punctuation stuck to the end of the connect link", () => {
    // A trailing "." is inside the anchor for several SMS clients' link
    // detectors, and a 404 is a decline with extra steps.
    const text = nudgeText("gmail", base);
    const at = text.indexOf(base.connectUrl);
    assert.ok(at >= 0);
    const after = text[at + base.connectUrl.length];
    assert.ok(after === undefined || after === " ", JSON.stringify(after));
  });
});

// ---------------------------------------------------------------------------
// State transitions
// ---------------------------------------------------------------------------
describe("nudge state transitions", () => {
  it("onWouldHaveUsed opens a row and counts the evidence", () => {
    const first = onWouldHaveUsed("zorptastic-9000", null, OWNER);
    assert.equal(first.state, "queued");
    assert.equal(first.tasks_that_would_have_used_it, 1);
    const second = onWouldHaveUsed("zorptastic-9000", first, OWNER);
    assert.equal(second.tasks_that_would_have_used_it, 2);
  });

  it("onSent stamps the send and increments the ask counter", () => {
    const sent = onSent("gmail", row("gmail"), atUtc(10), "sms", OWNER);
    assert.equal(sent.state, "sent");
    assert.equal(sent.sent_at, atUtc(10));
    assert.equal(sent.channel, "sms");
    assert.equal(sent.asks, 1);
  });

  it("onDeclined stamps the decline and counts it", () => {
    const declined = onDeclined("gmail", row("gmail"), atUtc(10), OWNER);
    assert.equal(declined.state, "declined");
    assert.equal(declined.declined_at, atUtc(10));
    assert.equal(declined.declines, 1);
  });

  it("onConnected is terminal and keeps the decline history for audit", () => {
    const declined = onDeclined("gmail", row("gmail"), atUtc(10) - 30 * DAY, OWNER);
    const connected = onConnected("gmail", declined, atUtc(10), OWNER);
    assert.equal(connected.state, "connected");
    assert.equal(connected.declined_at, atUtc(10) - 30 * DAY);
    assert.equal(shouldNudge("gmail", connected, ctx()).verdict, "never-again");
  });

  it("the full sequence — ask, decline, re-ask 14 days later, decline again — ends in never-again", () => {
    const t0 = atUtc(10);
    let r: NudgeRecord = onWouldHaveUsed("gmail", null, OWNER);
    assert.equal(shouldNudge("gmail", r, ctx({ now: t0 })).verdict, "ask");

    r = onSent("gmail", r, t0, "sms", OWNER);
    assert.equal(shouldNudge("gmail", r, ctx({ now: t0 + DAY })).cause, "one-nudge-per-app");

    r = onDeclined("gmail", r, t0 + 60_000, OWNER);
    assert.equal(shouldNudge("gmail", r, ctx({ now: t0 + 7 * DAY })).cause, "declined-recently");
    assert.equal(shouldNudge("gmail", r, ctx({ now: t0 + 15 * DAY })).verdict, "ask");

    r = onSent("gmail", r, t0 + 15 * DAY, "sms", OWNER);
    r = onDeclined("gmail", r, t0 + 15 * DAY + 60_000, OWNER);
    const after = shouldNudge("gmail", r, ctx({ now: t0 + 400 * DAY }));
    assert.equal(after.verdict, "never-again");
    assert.equal(after.cause, "declined-twice");

    // ...and the owner can still reopen it themselves.
    assert.equal(
      shouldNudge("gmail", r, ctx({ now: t0 + 400 * DAY, ownerAskedFor: true })).verdict,
      "ask",
    );
  });
});

// ---------------------------------------------------------------------------
// scopesFor
// ---------------------------------------------------------------------------
describe("scopesFor", () => {
  it("takes the union of what the matched tools themselves declared, deduped and sorted", () => {
    const req = scopesFor([
      tool({ toolSlug: "A", schema: { scopes: ["b.write", "a.read"] } }),
      tool({ toolSlug: "B", schema: { scopes: ["a.read"] } }),
    ]);
    assert.deepEqual(req.scopes, ["a.read", "b.write"]);
    assert.equal(req.minimal, true);
  });

  it("reads the several key spellings the vendors actually use", () => {
    assert.deepEqual(scopesFor([tool({ schema: { required_scopes: ["x"] } })]).scopes, ["x"]);
    assert.deepEqual(scopesFor([tool({ schema: { "x-scopes": ["y"] } })]).scopes, ["y"]);
    assert.deepEqual(scopesFor([tool({ schema: { auth: { scopes: ["z"] } } })]).scopes, ["z"]);
  });

  it("reports a tool that declared nothing instead of pretending the set is minimal", () => {
    const req = scopesFor([
      tool({ toolSlug: "A", schema: { scopes: ["a.read"] } }),
      tool({ toolSlug: "MYSTERY", schema: {} }),
    ]);
    assert.deepEqual(req.scopes, ["a.read"]);
    assert.deepEqual(req.toolsWithoutDeclaredScopes, ["MYSTERY"]);
    assert.equal(req.minimal, false);
  });

  it("treats an explicitly empty declaration as a real answer", () => {
    const req = scopesFor([tool({ toolSlug: "A", schema: { scopes: [] } })]);
    assert.deepEqual(req.scopes, []);
    assert.equal(req.minimal, true);
  });

  it("asks for nothing, and claims nothing, when no tool was matched", () => {
    const req = scopesFor([]);
    assert.deepEqual(req.scopes, []);
    assert.equal(req.minimal, false);
  });

  it("does not invent a subsumption rule between vendor scope strings", () => {
    // `chat:write` is NARROWER than `chat:write.public`, so the obvious
    // prefix rule would drop the one that is actually needed — or keep the
    // broad one and ask for more than the step requires.
    const req = scopesFor([
      tool({ toolSlug: "A", schema: { scopes: ["chat:write"] } }),
      tool({ toolSlug: "B", schema: { scopes: ["chat:write.public"] } }),
    ]);
    assert.deepEqual(req.scopes, ["chat:write", "chat:write.public"]);
  });

  it("only ever returns what it was handed — an unseen app is no different", () => {
    const req = scopesFor([tool({ app: "zorptastic-9000", schema: { scopes: ["zorp.read"] } })]);
    assert.deepEqual(req.scopes, ["zorp.read"]);
  });
});

// ---------------------------------------------------------------------------
// accountChoice
// ---------------------------------------------------------------------------
describe("accountChoice", () => {
  const candidates = [tool({ app: "someapp" })];

  it("resolves when there is one connected account and nothing to contradict it", () => {
    const choice = accountChoice(candidates, null, [account({ accountId: "a1" })]);
    assert.equal(choice.kind, "resolved");
    assert.equal(choice.kind === "resolved" && choice.accountId, "a1");
  });

  it("resolves from the hint when exactly one account carries that tag", () => {
    const choice = accountChoice(candidates, "work", [
      account({ accountId: "a1", label: "personal", kind: "personal" }),
      account({ accountId: "a2", label: "acme", kind: "work" }),
    ]);
    assert.equal(choice.kind, "resolved");
    assert.equal(choice.kind === "resolved" && choice.accountId, "a2");
  });

  it("must ask when two accounts are connected and there is no hint", () => {
    const choice = accountChoice(candidates, null, [
      account({ accountId: "a1", label: "one" }),
      account({ accountId: "a2", label: "two" }),
    ]);
    assert.equal(choice.kind, "must-ask");
  });

  it("NEVER reads the label: two untagged accounts named 'Work' and 'Personal' still must-ask", () => {
    // This is the Law-1 test for this file. The labels say it plainly in
    // English and that is exactly why they must not be consulted: the day
    // someone's business runs out of a gmail.com address, a label reader sends
    // an invoice from the family account.
    const choice = accountChoice(candidates, "work", [
      account({ accountId: "a1", label: "Work Gmail" }),
      account({ accountId: "a2", label: "Personal Gmail" }),
    ]);
    assert.equal(choice.kind, "must-ask");
    assert.ok(choice.kind === "must-ask" && choice.reason.includes("label is not evidence"));
  });

  it("must ask when the owner has two accounts tagged the same way", () => {
    const choice = accountChoice(candidates, "work", [
      account({ accountId: "a1", label: "acme", kind: "work" }),
      account({ accountId: "a2", label: "acme-eu", kind: "work" }),
    ]);
    assert.equal(choice.kind, "must-ask");
  });

  it("must ask when the hint contradicts the only connected account", () => {
    const choice = accountChoice(candidates, "work", [
      account({ accountId: "a1", label: "home", kind: "personal" }),
    ]);
    assert.equal(choice.kind, "must-ask");
  });

  it("says needs-reauth rather than picking a dead connection", () => {
    // A 401 in the middle of the errand reads to the owner as "it failed".
    const choice = accountChoice(candidates, null, [account({ accountId: "a1", status: "expired" })]);
    assert.equal(choice.kind, "needs-reauth");
  });

  it("says none-connected when nothing for this app is connected", () => {
    const choice = accountChoice(candidates, null, [account({ app: "another-app" })]);
    assert.equal(choice.kind, "none-connected");
  });

  it("must ask when the matched tools span two connected apps", () => {
    const choice = accountChoice(
      [tool({ app: "someapp" }), tool({ app: "otherapp" })],
      null,
      [account({ app: "someapp", accountId: "a1" }), account({ app: "otherapp", accountId: "b1" })],
    );
    assert.equal(choice.kind, "must-ask");
  });

  it("matches app slugs case-insensitively", () => {
    const choice = accountChoice([tool({ app: "SomeApp" })], null, [account({ app: "someapp", accountId: "a1" })]);
    assert.equal(choice.kind, "resolved");
  });

  it("gives no verdict rather than guessing on malformed input", () => {
    assert.equal(accountChoice([], null, []).kind, "no-verdict");
    assert.equal(accountChoice(candidates, null, null).kind, "no-verdict");
    assert.equal(accountChoice(candidates, "wrok" as never, [account()]).kind, "no-verdict");
  });

  it("behaves identically for an app it has never seen", () => {
    const choice = accountChoice(
      [tool({ app: "zorptastic-9000" })],
      "work",
      [
        account({ app: "zorptastic-9000", accountId: "z1", label: "one", kind: "personal" }),
        account({ app: "zorptastic-9000", accountId: "z2", label: "two", kind: "work" }),
      ],
    );
    assert.equal(choice.kind, "resolved");
    assert.equal(choice.kind === "resolved" && choice.accountId, "z2");
  });
});
