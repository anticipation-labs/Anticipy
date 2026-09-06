/**
 * test/connections-nudge.test.ts — the ask: minting our link and sending the
 * one text that carries it.
 *
 *   node --experimental-strip-types migration/workers/test/connections-nudge.test.ts
 *
 * WHAT IS REAL HERE AND WHAT IS NOT. The policy, the mint, the containment, the
 * sweep, the store (`createMemoryStore` out of src/connections/store.ts, with
 * its own owner guards and its own compare-and-sets) and `sendText` out of
 * src/messaging.ts are all the SHIPPED code. `redeem` and `parseConnectPath`
 * out of src/routes/connect.ts are the shipped code too, and they are used
 * deliberately: a token this file mints is handed to the route's own redeemer,
 * so "the link works" is measured rather than asserted. Two things are fakes,
 * because they are two other systems: the catalog (a vendor HTTP client) and
 * the model that writes the text. `fetch` is stubbed at the global, exactly as
 * test/messaging.test.ts does it, so the real provider selection, the real
 * request shape and the real "what does sent mean" all run.
 *
 * THE FAILURES THIS FILE EXISTS TO CATCH:
 *
 *   THE LINK THAT WAS NEVER MINTED. Before src/connections/nudge.ts, nothing in
 *   this repository ever inserted a `connect_links` row, so `/c/{token}` had
 *   nothing to look up and no person could connect anything. The chain checks
 *   below mint a token and drive it through the route's own `redeem` and
 *   `parseConnectPath`.
 *
 *   THE 3AM TEXT. Every hold in the policy is a moment somebody would have been
 *   interrupted. Quiet hours are pinned at both ends, mid-step and
 *   before-the-result are pinned, zero evidence is pinned, and every missing
 *   input answers `no-verdict` — the FLOOR — rather than sending.
 *
 *   THREE TEXTS IN ONE MINUTE. The 7-day cap is global across ALL apps, and it
 *   is computed here from this owner's own rows rather than taken from a
 *   caller. A row for a DIFFERENT toolkit closes the gate.
 *
 *   TWO TICKS, TWO TEXTS, ONE ROW. Driven on 2026-09-06: two sweeps in flight
 *   together both read the same absent row, both cleared the 7-day cap because
 *   neither had written, and both sent — and the upsert then collapsed them
 *   into one row, so nothing afterwards could say it had happened. Three checks
 *   run the real `sendConnectAsk` concurrently against node:sqlite loaded with
 *   the real schema: a fresh owner, an owner whose row already says `asked`
 *   (where only `sent_at` can tell the two apart), and a Skip landing mid-ask.
 *
 *   TWO TICKS, TWO APPS, TWO TEXTS. The round-2 audit, same day, on that fix:
 *   the lease it added is keyed (user_id, toolkit), and the cap it enforces is
 *   keyed by PERSON — "one connect ask per user per 7 days ACROSS ALL APPS"
 *   (page 24). Two ticks about DIFFERENT apps take DIFFERENT rows, so neither
 *   predicate is false and one owner gets two texts. The sequential version of
 *   that check passed throughout, which is the whole lesson: the cap was true
 *   under sequence and false under overlap. Four checks: the race itself, two
 *   owners at once (the cap is one PERSON's, not the fleet's), the week's far
 *   edge (the lease and the policy must end it at the same instant), and the
 *   whole thing again over a table missing its optional columns.
 *
 *   THE VENDOR LINK IN A TEXT. Four raw vendor links went into messages on
 *   2026-09-05 and all four were dead before they were tapped. The containment
 *   refuses a second URL — including a SCHEMELESS one, which every phone
 *   linkifies — and refuses a link that merely contains our token.
 *
 *   THE RAW TOKEN AT REST. The store holds sha256(token). Every stored row and
 *   every log line this file provokes is scanned for the token itself.
 *
 *   THE WRONG PERSON. A display name where an owner id belongs, and a nudge row
 *   belonging to somebody else, both refuse rather than send.
 *
 * MUTATIONS THIS FILE MUST GO RED ON (run by hand; see the report):
 *   see the list at the bottom of the file, each anchored on a unique string.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import {
  ASK_MESSAGE_MAX_CHARS,
  GLOBAL_ASK_INTERVAL_DAYS,
  LEVEL_THRESHOLD,
  MAX_ASKS_PER_SWEEP,
  ONBOARDING_SKIP_SNOOZE_DAYS,
  QUIET_HOURS_END,
  QUIET_HOURS_START,
  SILENCE_IS_A_SOFT_NO_HOURS,
  SNOOZE_DAYS,
  TRIGGER_SCORE,
  askIsLicensed,
  askMessage,
  connectNudgeSweep,
  freshNudge,
  installNudgeWiring,
  maturedBySilence,
  mintConnectLink,
  nudgeWiringInstalled,
  recordDecline,
  sendConnectAsk,
  shouldAsk,
  type AskClaim,
  type NudgeDeps,
  type NudgeEnv,
  type NudgeMoment,
} from "../src/connections/nudge.ts";
import { createD1Store, createMemoryStore, type ConnectionsStore, type StoreEnv }
  from "../src/connections/store.ts";
import {
  CONNECT_URL_BASE, LINK_TTL_MS, TOKEN_CHARS,
  parseConnectPath, redeem, tokenHandle,
} from "../src/routes/connect.ts";
import { CONNECT_LINK_PREFIX, FORBIDDEN_TERMS, MAX_ASK_SEGMENTS } from "../src/connections/words.ts";
import type { ConnectNudge, NudgeContext, NudgeTrigger, ToolkitMeta }
  from "../../../spike/two-hands/src/connections/contract.ts";
import { FakeD1, asD1 } from "./fake-d1.ts";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..", "..", "..");
const SOURCE = readFileSync(join(here, "..", "src", "connections", "nudge.ts"), "utf8");
const WORDS_SOURCE = readFileSync(join(here, "..", "src", "connections", "words.ts"), "utf8");
const CONTRACT_SOURCE = readFileSync(
  join(repoRoot, "spike", "two-hands", "src", "connections", "contract.ts"), "utf8",
);
const POLICY_SOURCE = readFileSync(
  join(repoRoot, "spike", "two-hands", "src", "connections", "policy.ts"), "utf8",
);

let failures = 0;
let passes = 0;
async function check(what: string, fn: () => void | Promise<void>): Promise<void> {
  try { await fn(); passes++; }
  catch (err) { failures++; console.error("FAIL " + what + "\n     " + (err as Error).message); }
}

// ---------------------------------------------------------------------------
// FIXTURES
// ---------------------------------------------------------------------------

const NOW = 1_757_000_000_000;
const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;

const OWNER = "ownerrefaaaaaa1";      // 15 lowercase alphanumerics, as D1 mints
const STRANGER = "strangerowner12";
const TO = "+15557654321";

// TWO INVENTED SLUGS. Neither exists in any catalog, neither is mentioned in
// nudge.ts, and every scenario below is swept through both: "NO APP IS
// HARDCODED" made behavioural rather than promised.
const SLUG_A = "zzquixotic";
const SLUG_B = "wobblefish";

const SENDBLUE: NudgeEnv = {
  SENDBLUE_API_KEY_ID: "sbkid-test",
  SENDBLUE_API_SECRET_KEY: "sbsecret-test",
  SENDBLUE_FROM_NUMBER: "+15550001111",
};

function meta(slug: string): ToolkitMeta {
  return {
    slug,
    name: slug === SLUG_A ? "Quixotic" : "Wobblefish",
    logo: null,
    description: null,
    appUrl: null,
    scopes: ["read"],
  };
}

/** A well-evidenced post-result moment: the one shape that is allowed to send. */
function goodMoment(over: Partial<NudgeMoment> = {}): NudgeMoment {
  return {
    localHour: 14,
    taskInFlight: false,
    resultDelivered: true,
    tasksThatWouldHaveUsedIt: 3,
    alias: null,
    whatHappened: "that ran in the browser and took 40 seconds",
    browserMs: 40_000,
    ...over,
  };
}

function ctxOf(over: Partial<NudgeContext> = {}): NudgeContext {
  return {
    now: NOW,
    trigger: "in_task",
    localHour: 14,
    taskInFlight: false,
    resultDelivered: true,
    tasksThatWouldHaveUsedIt: 3,
    lastAskAnyAppAt: null,
    ...over,
  };
}

function nudgeOf(over: Partial<ConnectNudge> = {}): ConnectNudge {
  return { ...freshNudge(OWNER, SLUG_A), ...over };
}

/**
 * A draft in this product's voice, carrying our link once.
 *
 * ALL ASCII ON PURPOSE. One curly apostrophe forces the whole message to UCS-2,
 * where two segments hold 134 units rather than 306 septets, and this text plus
 * a 69-character link is over that — which is the containment working, not a
 * bug, and is pinned by its own check below.
 */
function goodDraft(link: string): string {
  return "That one took 40 seconds in the browser. Connect your Quixotic and Anticipy can "
    + `do it straight away: ${link}. Totally up to you - it works fine without it.`;
}

// --- the fetch stub, exactly as test/messaging.test.ts drives it -------------
interface Captured { url: string; body: string }
let calls: Captured[] = [];
let reply: () => Response = () => new Response(
  JSON.stringify({ message_handle: "mh-1", status: "QUEUED" }), { status: 200 },
);
/** EVERY message this suite ever sent, surviving the per-check `reset()` — the
 *  two whole-suite scans at the bottom read this, not `calls`, so a check added
 *  later cannot shrink what they cover by resetting after itself. */
const SENT: string[] = [];
const realFetch = globalThis.fetch;
globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
  const body = String(init?.body ?? "");
  calls.push({ url: String(input), body });
  try { SENT.push(String((JSON.parse(body) as { content: string }).content)); } catch { /* not ours */ }
  return reply();
}) as typeof fetch;

// Every log line and every message body, for the whole-suite scans at the end.
const LOGS: string[] = [];
const realLog = console.log;
console.log = ((...args: unknown[]) => { LOGS.push(args.map(String).join(" ")); }) as typeof console.log;

/** The token out of a link we minted. Used only by the leak scans. */
const MINTED_TOKENS: string[] = [];
function tokenOf(url: string): string {
  const token = url.slice(CONNECT_URL_BASE.length + 1);
  MINTED_TOKENS.push(token);
  return token;
}

// --- a rig: a real memory store, fake catalog, scripted writer ---------------
interface Rig {
  env: NudgeEnv;
  store: ConnectionsStore;
  deps: NudgeDeps;
  /** Every `AskInput` the writer was handed. */
  drafted: { link: string; slug: string; moment: string }[];
}

/**
 * THE LEASE THE IN-MEMORY STORE DOES NOT HAVE.
 *
 * `createMemoryStore` has compare-and-sets for `connect_links` and none for
 * `connect_nudges`, so this stands in for the one store.ts will grow. It is
 * honest rather than decorative: the whole body runs inside a promise chain,
 * which is real mutual exclusion in ONE isolate — and one isolate is all an
 * in-memory store has ever been.
 *
 * It reads `this`, so a test that deletes a method off a COPY of the store
 * breaks this too, the way a real store method would break.
 *
 * IT IS NOT WHAT PRODUCTION USES. The shipped lease is `d1ClaimAsk` in
 * src/connections/nudge.ts, one conditional statement against a real
 * `connect_nudges` primary key; the check that reproduces the overlapping-tick
 * defect drives THAT, over node:sqlite and the real schema.
 */
function memoryClaim(): AskClaim {
  let queue: Promise<unknown> = Promise.resolve();
  return function (this: ConnectionsStore, expect, write, budget) {
    const store = this;
    const run = queue.then(async () => {
      const cur = await store.readNudge(write.user_id, write.toolkit);
      const state = cur === null ? "never_asked" : cur.state;
      const sentAt = cur === null ? null : cur.sent_at;
      if (state !== expect.state || sentAt !== expect.sent_at) return false;
      // BOTH PREDICATES, because a lease that enforces only the row half is the
      // round-2 defect: two ticks about two apps take two rows and both win.
      // The whole body is inside the queue, so this read-then-write is as
      // atomic here as the SQL is over D1.
      if (budget !== null) {
        const others = (await store.nudgesForOwner(budget.owner))
          .filter((r) => r.toolkit !== write.toolkit)
          .filter((r) => typeof r.sent_at === "number" && r.sent_at > budget.noAskSince);
        if (others.length > 0) return false;
      }
      await store.putNudge(write);
      return true;
    });
    queue = run.catch(() => undefined);
    return run;
  };
}

function rig(over: Partial<NudgeDeps> = {}, env: NudgeEnv = SENDBLUE, moment?: NudgeMoment): Rig {
  const store = { ...createMemoryStore(), claimAsk: memoryClaim() } as ConnectionsStore;
  const drafted: Rig["drafted"] = [];
  const deps: NudgeDeps = {
    store,
    catalog: { toolkit: async (slug) => meta(slug) },
    write: (input) => {
      const i = input as { evidence: { link: string }; meta: ToolkitMeta; moment: string };
      drafted.push({ link: i.evidence.link, slug: i.meta.slug, moment: i.moment });
      return goodDraft(i.evidence.link);
    },
    moment: async () => moment ?? goodMoment(),
    phone: async () => TO,
    due: async () => [],
    now: () => NOW,
    ...over,
  };
  return { env, store, deps, drafted };
}

/**
 * THE SAME RIG OVER A REAL DATABASE — the shipped `createD1Store` on top of
 * node:sqlite loaded with migration/d1/schema.sql, so the exactly-once lease
 * below is SQLite's own answer about a real `connect_nudges` primary key
 * rather than a fixture agreeing with itself.
 */
interface D1Rig extends Rig { d1: FakeD1 }

function d1Rig(over: Partial<NudgeDeps> = {}, moment?: NudgeMoment): D1Rig {
  const d1 = new FakeD1();
  const env = { ...SENDBLUE, DB: asD1(d1) } as NudgeEnv;
  const store = createD1Store(env as unknown as StoreEnv);
  const drafted: Rig["drafted"] = [];
  const deps: NudgeDeps = {
    store,
    catalog: { toolkit: async (slug) => meta(slug) },
    write: (input) => {
      const i = input as { evidence: { link: string }; meta: ToolkitMeta; moment: string };
      drafted.push({ link: i.evidence.link, slug: i.meta.slug, moment: i.moment });
      return goodDraft(i.evidence.link);
    },
    moment: async () => moment ?? goodMoment(),
    phone: async () => TO,
    due: async () => [],
    now: () => NOW,
    ...over,
  };
  return { d1, env, store, deps, drafted };
}

function reset(): void {
  calls = [];
  reply = () => new Response(
    JSON.stringify({ message_handle: "mh-1", status: "QUEUED" }), { status: 200 },
  );
}

// ===========================================================================
// 1. THE CONSTANTS ARE THE CONTRACT'S
// ===========================================================================

await check("every constant is the contract's own, read from its source", () => {
  const block = CONTRACT_SOURCE.match(
    /TRIGGER_SCORE:\s*Record<NudgeTrigger,\s*number>\s*=\s*\{([^}]*)\}/,
  );
  assert.ok(block, "the contract no longer declares TRIGGER_SCORE as a Record<NudgeTrigger, number>");
  const pairs = [...block[1].matchAll(/(\w+):\s*([0-9.]+)/g)];
  assert.equal(pairs.length, 5, "the contract declares five triggers");
  const fromContract = Object.fromEntries(pairs.map(([, k, v]) => [k, Number(v)]));
  assert.deepEqual(TRIGGER_SCORE, fromContract,
    "nudge.ts and the contract disagree about which moments are real, or about their scores");

  const levels = CONTRACT_SOURCE.match(
    /LEVEL_THRESHOLD:\s*Record<0 \| 1 \| 2 \| 3,\s*number>\s*=\s*\{([\s\S]*?)\n\};/,
  );
  assert.ok(levels, "the contract no longer declares LEVEL_THRESHOLD");
  assert.ok(/0:\s*0\.5/.test(levels[1]) && /1:\s*0\.8/.test(levels[1])
    && /2:\s*0\.95/.test(levels[1]) && /3:\s*Number\.POSITIVE_INFINITY/.test(levels[1]),
    "the contract's thresholds moved and nudge.ts was not told");
  assert.deepEqual(LEVEL_THRESHOLD, { 0: 0.5, 1: 0.8, 2: 0.95, 3: Number.POSITIVE_INFINITY });

  assert.ok(CONTRACT_SOURCE.includes("SNOOZE_DAYS: Record<1 | 2 | 3, number> = { 1: 14, 2: 45, 3: 3650 }"),
    "the contract's snooze ladder moved");
  assert.deepEqual(SNOOZE_DAYS, { 1: 14, 2: 45, 3: 3650 });
  assert.ok(CONTRACT_SOURCE.includes("GLOBAL_ASK_INTERVAL_DAYS = 7"));
  assert.equal(GLOBAL_ASK_INTERVAL_DAYS, 7);
  assert.ok(CONTRACT_SOURCE.includes("SILENCE_IS_A_SOFT_NO_HOURS = 72"));
  assert.equal(SILENCE_IS_A_SOFT_NO_HOURS, 72);
  assert.ok(CONTRACT_SOURCE.includes("ONBOARDING_SKIP_SNOOZE_DAYS = 7"));
  assert.equal(ONBOARDING_SKIP_SNOOZE_DAYS, 7);
  assert.ok(CONTRACT_SOURCE.includes("LINK_TTL_MS = 10 * 60 * 1000"));
  assert.equal(LINK_TTL_MS, 10 * 60 * 1000);
});

await check("quiet hours are the spike's own numbers, both ends", () => {
  assert.ok(POLICY_SOURCE.includes("QUIET_HOURS_START = 22"));
  assert.ok(POLICY_SOURCE.includes("QUIET_HOURS_END = 8"));
  assert.equal(QUIET_HOURS_START, 22);
  assert.equal(QUIET_HOURS_END, 8);
});

// ===========================================================================
// 2. THE LINK
// ===========================================================================

await check("a minted link is a route the Worker actually serves", async () => {
  for (const slug of [SLUG_A, SLUG_B]) {
    const r = rig();
    const minted = await mintConnectLink(r.env, OWNER, slug, null, r.deps);
    assert.ok(minted.url.startsWith(CONNECT_URL_BASE + "/"),
      `a link on ${minted.url} is not on the host this Worker is routed to`);
    const route = parseConnectPath(new URL(minted.url).pathname);
    assert.ok(route, "routes/connect.ts does not route the link this file mints — a 404 in "
      + "somebody's message thread, forever");
    assert.equal(route.leg, "view");
    assert.equal(route.token.length, TOKEN_CHARS);
    tokenOf(minted.url);
  }
});

await check("the token is 32 bytes of crypto random, not a counter", async () => {
  const r = rig();
  const seen = new Set<string>();
  for (let i = 0; i < 40; i++) {
    const minted = await mintConnectLink(r.env, OWNER, SLUG_A, null, r.deps);
    const token = tokenOf(minted.url);
    assert.ok(/^[A-Za-z0-9_-]{43}$/.test(token), `not base64url-43: ${token}`);
    assert.ok(!seen.has(token), "two mints produced the same token");
    seen.add(token);
  }
});

await check("the stored row holds sha256(token) and NEVER the token", async () => {
  const r = rig();
  const minted = await mintConnectLink(r.env, OWNER, SLUG_B, "work", r.deps);
  const token = tokenOf(minted.url);
  const rows = await r.store.linksForOwner(OWNER);
  assert.equal(rows.length, 1);
  const row = rows[0];
  assert.equal(row.token_handle, await tokenHandle(token),
    "the store key is not sha256(token) in hex, so redeeming can never find this row");
  assert.equal(row.user_id, OWNER);
  assert.equal(row.toolkit, SLUG_B);
  assert.equal(row.alias, "work");
  assert.equal(row.expires_at, NOW + LINK_TTL_MS);
  assert.equal(row.used_at, null);
  assert.equal(row.completed_at, null);
  assert.ok(!JSON.stringify(row).includes(token),
    "the raw token is in the stored row — one database read would then be a live connect "
      + "link for every owner holding one");
  assert.ok(!minted.fingerprint.includes(token) && minted.fingerprint.startsWith("link:"),
    "the log-safe fingerprint carries the token");
});

await check("the mint and the route's own redeem agree: mint, tap, spent", async () => {
  const r = rig();
  const minted = await mintConnectLink(r.env, OWNER, SLUG_A, null, r.deps);
  const token = tokenOf(minted.url);

  const first = await redeem(token, { signedInAs: OWNER, store: r.store, now: NOW });
  assert.equal(first.outcome, "ok", "a freshly minted token does not redeem — the chain is broken");
  if (first.outcome === "ok") {
    assert.equal(first.link.user_id, OWNER);
    assert.equal(first.link.toolkit, SLUG_A);
  }
  const second = await redeem(token, { signedInAs: OWNER, store: r.store, now: NOW });
  assert.equal(second.outcome, "already-used", "single use is not single use");
});

await check("a minted link is dead ten minutes later, and dead to a stranger now", async () => {
  const r = rig();
  const minted = await mintConnectLink(r.env, OWNER, SLUG_A, null, r.deps);
  const token = tokenOf(minted.url);
  assert.equal(
    (await redeem(token, { signedInAs: OWNER, store: r.store, now: NOW + LINK_TTL_MS })).outcome,
    "expired", "the link outlives LINK_TTL_MS");
  assert.equal(
    (await redeem(token, { signedInAs: STRANGER, store: r.store, now: NOW })).outcome,
    "wrong-user", "another owner can spend this owner's link");
});

await check("a display name where an owner id belongs is refused, not bound", async () => {
  const r = rig();
  for (const bad of ["omar", "jose@anticipy.ai", "", "OWNERREFAAAAAA1"]) {
    await assert.rejects(
      () => mintConnectLink(r.env, bad, SLUG_A, null, r.deps),
      /not an owner id/,
      `minting bound a connect link to ${JSON.stringify(bad)}`,
    );
  }
  assert.equal((await r.store.linksForOwner(OWNER)).length, 0, "a refused mint wrote a row");
});

await check("no store wired: the mint says so rather than inventing one", async () => {
  await assert.rejects(
    () => mintConnectLink(SENDBLUE, OWNER, SLUG_A),
    /installNudgeWiring/,
  );
});

await check("CONNECT_BASE_URL moves the link, matching routes/connect.ts precedence", async () => {
  const r = rig({}, { ...SENDBLUE, CONNECT_BASE_URL: "https://preview.example/c" });
  const minted = await mintConnectLink(r.env, OWNER, SLUG_A, null, r.deps);
  assert.ok(minted.url.startsWith("https://preview.example/c/"),
    "a preview deployment mints links pointing at production");
});

// ===========================================================================
// 3. THE POLICY — every hold, and the floor
// ===========================================================================

await check("the moment floors: mid-step, before the result, quiet hours, no evidence", () => {
  for (const slug of [SLUG_A, SLUG_B]) {
    const asking = { owner: OWNER, toolkit: slug };
    const row = nudgeOf({ toolkit: slug });
    const hold = (ctx: Partial<NudgeContext>, why: string) => {
      const v = shouldAsk(row, ctxOf(ctx), asking);
      assert.equal(v.decision, "hold", `${why} did not hold (${v.decision}: ${v.reason})`);
      assert.equal(askIsLicensed(v), false);
    };
    hold({ taskInFlight: true }, "mid-step");
    hold({ resultDelivered: false }, "before the result");
    hold({ tasksThatWouldHaveUsedIt: 0 }, "no evidence");
    // Both ends of quiet hours, closed at the start and open at the end.
    hold({ localHour: 22 }, "22:00");
    hold({ localHour: 23 }, "23:00");
    hold({ localHour: 0 }, "midnight");
    hold({ localHour: 7 }, "07:00");
    // THE CONTROL for the two boundaries: one hour either side must ask.
    for (const hour of [8, 21]) {
      const v = shouldAsk(row, ctxOf({ localHour: hour }), asking);
      assert.equal(v.decision, "ask", `${hour}:00 is inside the day and must be askable`);
    }
  }
});

await check("the 7-day cap is global across ALL apps, and skew does not open it", () => {
  const row = nudgeOf();
  const asking = { owner: OWNER, toolkit: SLUG_A };
  const at = (lastAskAnyAppAt: number | null) => shouldAsk(row, ctxOf({ lastAskAnyAppAt }), asking);

  assert.equal(at(NOW - 6 * DAY).decision, "hold", "asked six days ago and asked again");
  assert.equal(at(NOW - 7 * DAY + 1).decision, "hold", "the cap is off by a millisecond");
  assert.equal(at(NOW - 7 * DAY).decision, "ask", "seven days is seven days");
  // A last-ask in the FUTURE is clock skew between the Worker and D1. Negative
  // elapsed time is less than the interval, so it holds. Skew must never open.
  assert.equal(at(NOW + DAY).decision, "hold", "clock skew opened the 7-day gate");
  assert.equal(at(null).decision, "ask", "an owner nobody has ever asked is askable");
});

await check("the ladder: level 3 stops, level 2 admits only in_task or laptop_closed", () => {
  const asking = { owner: OWNER, toolkit: SLUG_A };
  const three = nudgeOf({ state: "declined", level: 3, snooze_until: NOW - DAY });
  const v3 = shouldAsk(three, ctxOf({ trigger: "laptop_closed" }), asking);
  assert.equal(v3.decision, "never-again", "three noes did not stop the asking");

  const two = nudgeOf({ state: "declined", level: 2, snooze_until: NOW - DAY });
  for (const trigger of ["repeated_use", "user_named_it", "onboarding"] as NudgeTrigger[]) {
    assert.equal(shouldAsk(two, ctxOf({ trigger }), asking).decision, "hold",
      `level 2 admitted ${trigger}`);
  }
  assert.equal(shouldAsk(two, ctxOf({ trigger: "laptop_closed" }), asking).decision, "ask");
  // in_task is on the allowlist and is then refused by the SCORE (0.8 < 0.95).
  // Both guards are load-bearing and the test says which is which.
  assert.equal(shouldAsk(two, ctxOf({ trigger: "in_task" }), asking).decision, "hold");
  assert.equal(LEVEL_THRESHOLD[2], 0.95, "retuning this threshold makes the level-2 allowlist "
    + "the only thing between a twice-refused owner and a third text");
});

await check("the score is STRICTLY above the threshold; the tie goes to the person", () => {
  const asking = { owner: OWNER, toolkit: SLUG_A };
  const one = nudgeOf({ state: "declined", level: 1, snooze_until: NOW - DAY, trigger: "in_task" });
  assert.equal(TRIGGER_SCORE.in_task, LEVEL_THRESHOLD[1], "the tie this check exists for is gone");
  assert.equal(shouldAsk(one, ctxOf({ trigger: "in_task" }), asking).decision, "hold");
  assert.equal(shouldAsk(one, ctxOf({ trigger: "user_named_it" }), asking).decision, "ask");
});

await check("a snooze is honoured, and the closed laptop overrides it once", () => {
  const asking = { owner: OWNER, toolkit: SLUG_A };
  const snoozed = (trigger: NudgeTrigger | null) =>
    nudgeOf({ state: "declined", level: 1, snooze_until: NOW + 5 * DAY, trigger });

  assert.equal(shouldAsk(snoozed("in_task"), ctxOf({ trigger: "user_named_it" }), asking).decision,
    "hold", "a live snooze was ignored");
  assert.equal(shouldAsk(snoozed("in_task"), ctxOf({ trigger: "laptop_closed" }), asking).decision,
    "ask", "the level-1 closed-laptop override never fires");
  // The refused ask WAS a laptop_closed ask: re-running the identical pitch
  // inside the snooze is asking a question this owner just answered.
  assert.equal(
    shouldAsk(snoozed("laptop_closed"), ctxOf({ trigger: "laptop_closed" }), asking).decision,
    "hold", "the override is available twice");
  // Level 2 never gets it.
  const two = nudgeOf({ state: "declined", level: 2, snooze_until: NOW + 5 * DAY, trigger: "in_task" });
  assert.equal(shouldAsk(two, ctxOf({ trigger: "laptop_closed" }), asking).decision, "hold");
});

await check("an open ask holds; 72 hours of silence is a decline with a 14-day snooze", () => {
  const asking = { owner: OWNER, toolkit: SLUG_A };
  const asked = nudgeOf({ state: "asked", trigger: "in_task", sent_at: NOW - 10 * HOUR });
  assert.equal(shouldAsk(asked, ctxOf(), asking).decision, "hold",
    "a second ask went out while the first was still open");

  const stale = nudgeOf({ state: "asked", trigger: "in_task", sent_at: NOW - 100 * HOUR });
  const matured = maturedBySilence(stale, NOW);
  assert.equal(matured.state, "declined");
  assert.equal(matured.level, 1);
  assert.equal(matured.acted_at, null, "silence stamped acted_at, claiming an action nobody took");
  assert.equal(matured.snooze_until,
    (stale.sent_at as number) + SILENCE_IS_A_SOFT_NO_HOURS * HOUR + 14 * DAY,
    "the snooze restarts at now rather than at the moment the silence matured");
  // And the verdict agrees with the record: level 1 needs more than 0.8.
  assert.equal(shouldAsk(stale, ctxOf({ trigger: "in_task" }), asking).decision, "hold");
  assert.equal(shouldAsk(stale, ctxOf({ trigger: "user_named_it" }), asking).decision, "hold",
    "the fresh 14-day snooze from the silence was not applied");
});

await check("an onboarding skip snoozes 7 days, not 14, and only at level 1", () => {
  const skipped = nudgeOf({ state: "asked", trigger: "onboarding", sent_at: NOW });
  const one = recordDecline(skipped, NOW, "said_no");
  assert.equal(one.snooze_until, NOW + ONBOARDING_SKIP_SNOOZE_DAYS * DAY);
  assert.equal(one.acted_at, NOW, "a tapped skip is an action and must be recorded as one");
  const two = recordDecline(one, NOW, "said_no");
  assert.equal(two.level, 2);
  assert.equal(two.snooze_until, NOW + SNOOZE_DAYS[2] * DAY,
    "the onboarding exception applied twice");
});

await check("connected holds, and needs_reconnect is weekly at most", () => {
  const asking = { owner: OWNER, toolkit: SLUG_A };
  assert.equal(shouldAsk(nudgeOf({ state: "connected" }), ctxOf(), asking).decision, "hold",
    "an owner who already connected this app was asked to connect it");
  const fresh = nudgeOf({ state: "needs_reconnect", sent_at: NOW - 2 * DAY });
  assert.equal(shouldAsk(fresh, ctxOf(), asking).decision, "hold");
  const old = nudgeOf({ state: "needs_reconnect", sent_at: NOW - 8 * DAY });
  assert.equal(shouldAsk(old, ctxOf(), asking).decision, "ask");
  // The ladder does not gate a reconnect — but the snooze still does.
  const l3 = nudgeOf({ state: "needs_reconnect", level: 3, sent_at: NOW - 8 * DAY });
  assert.equal(shouldAsk(l3, ctxOf(), asking).decision, "ask");
  const snoozed = nudgeOf({ state: "needs_reconnect", sent_at: NOW - 8 * DAY, snooze_until: NOW + DAY });
  assert.equal(shouldAsk(snoozed, ctxOf(), asking).decision, "hold",
    "a reconnect walked past a live snooze");
});

await check("THE FLOOR: every missing or unreadable input is no-verdict, never an ask", () => {
  const asking = { owner: OWNER, toolkit: SLUG_A };
  const no = (nudge: unknown, ctx: unknown, ask: unknown, why: string) => {
    const v = shouldAsk(nudge as ConnectNudge, ctx as NudgeContext, ask as { owner: string });
    assert.equal(v.decision, "no-verdict", `${why} produced ${v.decision}`);
    assert.equal(askIsLicensed(v), false);
  };
  no(null, ctxOf(), asking, "a missing nudge row");
  no(nudgeOf(), null, asking, "a missing context");
  no(nudgeOf(), ctxOf(), null, "nobody saying whose row this is");
  no(nudgeOf(), ctxOf(), { owner: "omar" }, "an owner NAME instead of a row id");
  no(nudgeOf({ user_id: STRANGER as never }), ctxOf(), asking, "a row belonging to another owner");
  no(nudgeOf({ toolkit: SLUG_B }), ctxOf(), asking, "a row about a different app");
  no(nudgeOf({ state: "declined_l2" as never }), ctxOf(), asking, "an unreadable state");
  no(nudgeOf({ level: 4 as never }), ctxOf(), asking, "a level of 4");
  no(nudgeOf({ state: "declined", level: 0 }), ctxOf(), asking, "declined at level 0");
  no(nudgeOf({ state: "asked", sent_at: null }), ctxOf(), asking, "asked with no sent_at");
  no(nudgeOf({ state: "asked", sent_at: NOW - 100 * HOUR, acted_at: NOW }), ctxOf(), asking,
    "asked with an unrecorded answer");
  no(nudgeOf({ trigger: "vibes" as never }), ctxOf(), asking, "an invented trigger on the row");
  no(nudgeOf(), ctxOf({ trigger: "vibes" as never }), asking, "an invented moment");
  no(nudgeOf(), ctxOf({ trigger: "constructor" as never }), asking, "a prototype key as a moment");
  no(nudgeOf(), ctxOf({ localHour: -1 }), asking, "an impossible hour");
  no(nudgeOf(), ctxOf({ localHour: undefined as never }), asking, "an unknown hour");
  no(nudgeOf(), ctxOf({ taskInFlight: undefined as never }), asking, "not knowing about a step");
  no(nudgeOf(), ctxOf({ resultDelivered: undefined as never }), asking, "not knowing about a result");
  no(nudgeOf(), ctxOf({ tasksThatWouldHaveUsedIt: -1 }), asking, "a negative evidence count");
  no(nudgeOf(), ctxOf({ lastAskAnyAppAt: undefined as never }), asking, "an unread ask history");
  no(nudgeOf(), ctxOf({ now: NaN }), asking, "an unusable clock");
});

// ===========================================================================
// 4. THE WORDS
// ===========================================================================

const LINK = `${CONNECT_URL_BASE}/${"a".repeat(TOKEN_CHARS)}`;
const EVIDENCE = { link: LINK, resultDelivered: true, tasksThatWouldHaveUsedIt: 3 };

async function drafted(text: unknown, over: Partial<typeof EVIDENCE> = {}) {
  return await askMessage("in_task", meta(SLUG_A), { ...EVIDENCE, ...over }, () => text);
}

await check("THE CONTROL: a good draft is sent through unchanged", async () => {
  const text = goodDraft(LINK);
  const out = await drafted(text);
  assert.ok(out.ok, `a well-formed ask was refused: ${out.ok ? "" : out.refusal}`);
  if (out.ok) assert.equal(out.text, text, "the containment rewrote the model's copy");
});

await check("our own host contains 'api' and that must not refuse every ask", async () => {
  assert.ok(CONNECT_URL_BASE.includes("api."), "the host stopped being api.anticipy.ai and this "
    + "check no longer proves the link is lifted out before the vocabulary scan");
  assert.ok(FORBIDDEN_TERMS.includes("api"), "'api' left the forbidden list");
  const out = await drafted(goodDraft(LINK));
  assert.ok(out.ok, "the ask was refused for a word that is inside our own URL");
});

await check("the register: six forbidden words, each refused on its own", async () => {
  const cases: [string, string][] = [
    ["authorize", `Tap to authorize your Quixotic here: ${LINK}. Up to you.`],
    ["permissions", `Quixotic permissions needed: ${LINK}. Up to you.`],
    ["integration", `Set up the Quixotic integration: ${LINK}. Up to you.`],
    ["api", `Connect the Quixotic API: ${LINK}. Up to you.`],
    ["oauth", `One OAuth step for Quixotic: ${LINK}. Up to you.`],
    ["composio", `Composio can link your Quixotic: ${LINK}. Up to you.`],
  ];
  for (const [term, text] of cases) {
    const out = await drafted(text);
    assert.equal(out.ok, false, `"${term}" reached a person's phone`);
    if (!out.ok) assert.equal(out.cause, "forbidden-word", `"${term}" was refused for the wrong reason`);
  }
});

await check("no exclamation marks, and no consent-form stiffness", async () => {
  const bang = await drafted(`That was slow. Connect your Quixotic: ${LINK}. Up to you!`);
  assert.equal(bang.ok, false);
  if (!bang.ok) assert.equal(bang.cause, "exclamation");
  const stiff = await drafted(
    `That was slow. Connect your Quixotic: ${LINK}. It is not required and you do not have to.`,
  );
  assert.equal(stiff.ok, false);
  if (!stiff.ok) assert.equal(stiff.cause, "stiff");
});

await check("THE ONLY URL IN THE MESSAGE IS OURS — including schemeless vendor links", async () => {
  // A phone linkifies `connect.vendor.dev/link/abc` exactly as it linkifies the
  // https form, and the person taps whichever is nearer their thumb. The
  // schemeless case is the one that shipped four dead links on 2026-09-05.
  const schemeless = await drafted(
    `That was slow. Connect your Quixotic: ${LINK}. Or go to connect.vendor.dev/link/abc9. Up to you.`,
  );
  assert.equal(schemeless.ok, false, "a schemeless vendor link rode along beside ours");
  if (!schemeless.ok) assert.equal(schemeless.cause, "extra-link");

  const withScheme = await drafted(
    `That was slow. Connect your Quixotic: ${LINK} or https://connect.vendor.dev/link/abc9. Up to you.`,
  );
  assert.equal(withScheme.ok, false);
  if (!withScheme.ok) assert.equal(withScheme.cause, "extra-link");

  // The vendor's link INSTEAD of ours: refused before the model is even called.
  const instead = await askMessage(
    "in_task", meta(SLUG_A),
    { ...EVIDENCE, link: "https://connect.vendor.dev/link/abc9" },
    () => { throw new Error("the writer must not be called for a link that is not ours"); },
  );
  assert.equal(instead.ok, false);
  if (!instead.ok) assert.equal(instead.cause, "bad-link");

  // A link on the host words.ts still names, which this Worker does not serve.
  const wrongHost = await askMessage(
    "in_task", meta(SLUG_A),
    { ...EVIDENCE, link: `${CONNECT_LINK_PREFIX}${"a".repeat(TOKEN_CHARS)}` },
    () => "unused",
  );
  assert.equal(wrongHost.ok, false, "a link on a host this Worker is not routed to was accepted");
});

await check("a link with characters welded on is a 404, and a 404 is a decline", async () => {
  const mangled = await drafted(`Slow again. Connect your Quixotic: ${LINK}-evil.example/x. Up to you.`);
  assert.equal(mangled.ok, false, "a token with a domain welded onto it was sent");
  if (!mangled.ok) assert.ok(mangled.cause === "mangled-link" || mangled.cause === "extra-link");

  const twice = await drafted(`Connect your Quixotic: ${LINK} or ${LINK}. Up to you.`);
  assert.equal(twice.ok, false);
  if (!twice.ok) assert.equal(twice.cause, "extra-link");

  const none = await drafted("Connect your Quixotic sometime. Up to you.");
  assert.equal(none.ok, false);
  if (!none.ok) assert.equal(none.cause, "no-link");
});

await check("why, then the link, then the sentence saying it is optional", async () => {
  const opens = await drafted(`${LINK} — connect your Quixotic.`);
  assert.equal(opens.ok, false, "the ask opened on the link with no reason given");
  if (!opens.ok) assert.equal(opens.cause, "nothing-before-link");
  const ends = await drafted(`That was slow. Connect your Quixotic here: ${LINK}`);
  assert.equal(ends.ok, false, "the line saying it is optional was dropped");
  if (!ends.ok) assert.equal(ends.cause, "nothing-after-link");
});

await check("one text as a carrier counts it, not as a character counter does", async () => {
  const filler = "Connecting saves about a minute every time you ask for this. ".repeat(5);
  const long = `${filler}Connect your Quixotic: ${LINK}. Up to you.`;
  const out = await drafted(long);
  assert.equal(out.ok, false, `a ${long.length}-character ask went out in three pieces`);
  if (!out.ok) assert.equal(out.cause, "too-long");

  // A SINGLE curly apostrophe forces UCS-2, where two segments hold 134 units.
  const curly = goodDraft(LINK).replace("it works", "it\u2019s ok and works");
  const ucs2 = await drafted(curly);
  assert.equal(ucs2.ok, false, "a UCS-2 draft was measured as though it were GSM-7");
  if (!ucs2.ok) assert.equal(ucs2.cause, "too-long");

  // The spec's 320 is kept and is currently subsumed. If MAX_ASK_SEGMENTS is
  // ever raised, this pin is what makes the character ceiling load-bearing.
  assert.ok(MAX_ASK_SEGMENTS * 153 < ASK_MESSAGE_MAX_CHARS,
    "the segment ceiling now exceeds the spec's character ceiling; ASK_MESSAGE_MAX_CHARS has "
      + "become load-bearing and needs a case of its own");
});

await check("a writer that says nothing, throws, or answers in the wrong shape", async () => {
  for (const [reply, cause] of [
    [null, "no-verdict"], [undefined, "no-verdict"], [42, "malformed-reply"],
    ["", "malformed-reply"], ["   ", "malformed-reply"],
  ] as [unknown, string][]) {
    const out = await drafted(reply);
    assert.equal(out.ok, false, `a reply of ${JSON.stringify(reply)} was sent`);
    if (!out.ok) assert.equal(out.cause, cause);
  }
  const threw = await askMessage("in_task", meta(SLUG_A), EVIDENCE, () => {
    throw new Error("model down");
  });
  assert.equal(threw.ok, false);
  if (!threw.ok) assert.equal(threw.cause, "no-verdict");
});

await check("no moment, no metadata, no evidence, no result: refused before the writer", async () => {
  const never = () => { throw new Error("the writer must not be called"); };
  const nom = await askMessage("vibes" as NudgeTrigger, meta(SLUG_A), EVIDENCE, never);
  assert.equal(nom.ok, false);
  if (!nom.ok) assert.equal(nom.cause, "no-moment");

  const nometa = await askMessage("in_task", { slug: "", name: "" } as ToolkitMeta, EVIDENCE, never);
  assert.equal(nometa.ok, false);
  if (!nometa.ok) assert.equal(nometa.cause, "malformed-meta");

  const noev = await askMessage("in_task", meta(SLUG_A), null as never, never);
  assert.equal(noev.ok, false);
  if (!noev.ok) assert.equal(noev.cause, "malformed-evidence");

  const early = await askMessage(
    "in_task", meta(SLUG_A), { ...EVIDENCE, resultDelivered: false }, never,
  );
  assert.equal(early.ok, false, "an ask arrived instead of the answer");
  if (!early.ok) assert.equal(early.cause, "result-not-delivered");
});

// ===========================================================================
// 5. THE ASK, END TO END
// ===========================================================================

await check("THE CONTROL: a well-evidenced post-result moment sends exactly one text",
  async () => {
    for (const slug of [SLUG_A, SLUG_B]) {
      reset();
      const r = rig();
      const out = await sendConnectAsk(r.env, OWNER, slug, "in_task", r.deps);
      assert.equal(out.sent, true, `nothing was sent: ${out.cause} — ${out.reason}`);
      assert.equal(out.cause, "sent");
      assert.equal(out.decision, "ask");

      assert.equal(calls.length, 1, `${calls.length} texts went out, not one`);
      assert.equal(calls[0].url, "https://api.sendblue.com/api/send-message",
        "the ask did not go through src/messaging.ts's provider");
      const body = JSON.parse(calls[0].body) as { number: string; content: string };
      assert.equal(body.number, TO);

      // The link in the text is the link that was minted, once, and it is ours.
      assert.equal(r.drafted.length, 1, "the model was asked more than once");
      const link = r.drafted[0].link;
      assert.equal(r.drafted[0].slug, slug, "the model was told about a different app");
      assert.equal(r.drafted[0].moment, "in_task");
      assert.equal(body.content, goodDraft(link), "the text is not the draft that was contained");
      assert.ok(body.content.startsWith("That one took"), "the text does not open on why");
      const token = tokenOf(link);

      // The row the tap will look up exists, bound to this owner and this app.
      const rows = await r.store.linksForOwner(OWNER);
      assert.equal(rows.length, 1);
      assert.equal(rows[0].token_handle, await tokenHandle(token));
      assert.equal(rows[0].toolkit, slug);
      assert.equal(
        (await redeem(token, { signedInAs: OWNER, store: r.store, now: NOW })).outcome, "ok",
        "the token in the text does not redeem");

      // And the ask is written down, so the next sweep can see it.
      const nudge = await r.store.readNudge(OWNER, slug);
      assert.ok(nudge, "the ask was sent and never recorded — the next sweep sends it again");
      assert.equal(nudge.state, "asked");
      assert.equal(nudge.sent_at, NOW);
      assert.equal(nudge.trigger, "in_task");
      assert.equal(nudge.channel, "sms");
      assert.equal(nudge.acted_at, null);
    }
  });

await check("a second ask, straight after the first, does not go out", async () => {
  reset();
  const r = rig();
  assert.equal((await sendConnectAsk(r.env, OWNER, SLUG_A, "in_task", r.deps)).sent, true);
  tokenOf(r.drafted[0].link);
  // A DIFFERENT app, which is the whole point of the cap being global.
  const second = await sendConnectAsk(r.env, OWNER, SLUG_B, "laptop_closed", r.deps);
  assert.equal(second.sent, false, "the same owner got two connect texts");
  assert.equal(second.cause, "hold");
  assert.match(second.reason, /across all apps/);
  assert.equal(calls.length, 1, "a second text left the Worker");
  assert.equal((await r.store.linksForOwner(OWNER)).length, 1, "a link was minted for a held ask");
});

await check("TWO TICKS AT ONCE: one text, one row, and the loser says so", async () => {
  // Cloudflare can have two five-minute invocations in flight together, and a
  // manual sweep beside the scheduled one certainly can. Both read the same
  // absent `connect_nudges` row, both clear the 7-day cap BECAUSE NEITHER HAS
  // WRITTEN YET, and before the lease both sent a text carrying a live link —
  // two interruptions, and one row afterwards, so nothing could ever tell.
  reset();
  const r = d1Rig();
  const both = await Promise.all([
    sendConnectAsk(r.env, OWNER, SLUG_A, "in_task", r.deps),
    sendConnectAsk(r.env, OWNER, SLUG_A, "in_task", r.deps),
  ]);
  for (const d of r.drafted) tokenOf(d.link);

  assert.equal(calls.length, 1,
    `${calls.length} connect texts left the Worker for one owner in one moment`);
  assert.equal(both.filter((o) => o.sent).length, 1,
    "two ticks both believed they had asked this owner");

  const rows = r.d1.rows<Record<string, unknown>>(`SELECT * FROM "connect_nudges"`);
  assert.equal(rows.length, 1, "one owner, one app, one row");
  assert.equal(rows[0].sent_at, NOW);
  assert.equal(rows[0].state, "asked");

  // THE LOSER IS QUIET, AND NAMED. Not "hold" and not "no-verdict": nothing
  // about this owner was wrong, another tick simply got there first, and a
  // sweep report that cannot count that separately cannot tell an overlap from
  // a policy refusing.
  const loser = both.find((o) => !o.sent)!;
  assert.equal(loser.cause, "lost-race",
    `the tick that lost reported ${loser.cause}: ${loser.reason}`);
  assert.equal(loser.decision, "ask");
});

await check("TWO TICKS, TWO DIFFERENT APPS, ONE OWNER: one text", async () => {
  // THE HOLE THE PER-APP LEASE LEFT OPEN, driven 2026-09-06 (round-2 finding 1).
  // The lease above is keyed (user_id, toolkit) — it is a promise about ONE
  // ROW. The 7-day cap it sits under is a promise about a PERSON, across all
  // their apps. Two ticks about DIFFERENT apps therefore claim DIFFERENT rows,
  // and neither predicate is false: both read an ask history in which nobody
  // has been sent anything, both clear the cap because neither has written
  // yet, both win their own row's lease, and one person gets two connect texts
  // with two live links.
  //
  // The sequential version of this is already pinned ("a second ask, straight
  // after the first, does not go out"), and it passed throughout — which is
  // the point: the cap was true under sequence and false under overlap, and
  // Cloudflare overlaps five-minute invocations.
  //
  // TWO DIFFERENT TRIGGERS on purpose, so the winner is not decided by the
  // policy: `in_task` (0.8) and `laptop_closed` (1.0) both clear level 0's
  // 0.5, so both ticks reach the lease and exactly one of them may pass it.
  reset();
  const r = d1Rig();
  const both = await Promise.all([
    sendConnectAsk(r.env, OWNER, SLUG_A, "in_task", r.deps),
    sendConnectAsk(r.env, OWNER, SLUG_B, "laptop_closed", r.deps),
  ]);
  for (const d of r.drafted) tokenOf(d.link);

  assert.equal(calls.length, 1,
    `${calls.length} connect texts left the Worker for one owner in one moment: the 7-day `
      + "cap is global across all apps and the lease that enforces it is not");
  assert.equal(both.filter((o) => o.sent).length, 1,
    "two ticks about two apps both believed they had spent this owner's week");

  // AND THE LOSER IS THE SAME KIND OF QUIET as a same-app overlap: nothing
  // about this owner or this moment was wrong, so it is neither `hold` nor
  // `no-verdict`.
  const lost = both.find((o) => !o.sent)!;
  assert.equal(lost.cause, "lost-race", `the tick that lost reported ${lost.cause}: ${lost.reason}`);
  assert.equal(lost.decision, "ask");

  // ONE ROW CARRIES A sent_at, AND ONLY ONE. The loser must not leave a row
  // saying it asked — that would spend a second week of this owner's silence
  // for a text nobody received.
  const sent = r.d1.rows<Record<string, unknown>>(
    `SELECT * FROM "connect_nudges" WHERE "sent_at" IS NOT NULL`);
  assert.equal(sent.length, 1,
    `${sent.length} rows say an ask went out and only one text did`);
  assert.equal(sent[0].state, "asked");

  // AND THE LOSER MINTED NOTHING IT LEFT LYING AROUND that a person could be
  // handed later: the link it minted before the lease is unreachable, and the
  // one link anybody was given is the winner's.
  assert.equal((await r.store.linksForOwner(OWNER)).length, 2,
    "the loser's link was minted before the lease, which is the known cost of "
      + "ordering the copy before the claim; if that changes, say so here");
});

await check("CONTROL: the weekly budget is one PERSON's, so two owners at once get two texts",
  async () => {
    // The predicate that closes the check above is a `NOT EXISTS` over
    // `connect_nudges`. Written without its `user_id` bound — or bound to the
    // wrong column — it becomes a cap over the whole FLEET: the first owner
    // asked in any week silences everybody else, and every check above still
    // passes because they all use one owner.
    //
    // TWO DIFFERENT APPS, and this is not incidental. The predicate also reads
    // `toolkit <> ?`, so two owners asked about the SAME app would pass a
    // fleet-wide cap by accident — measured: that version of this check let a
    // dropped `user_id` survive. Different owner AND different app is the only
    // shape in which the owner scoping is the thing being asked about.
    reset();
    const r = d1Rig();
    const both = await Promise.all([
      sendConnectAsk(r.env, OWNER, SLUG_A, "in_task", r.deps),
      sendConnectAsk(r.env, STRANGER, SLUG_B, "in_task", r.deps),
    ]);
    for (const d of r.drafted) tokenOf(d.link);
    assert.equal(both.filter((o) => o.sent).length, 2,
      `one owner's ask silenced another owner's: ${both.map((o) => `${o.cause}:${o.reason}`).join(" | ")}`);
    assert.equal(calls.length, 2, "two different people, two texts");
    const rows = r.d1.rows<Record<string, unknown>>(
      `SELECT * FROM "connect_nudges" WHERE "sent_at" IS NOT NULL ORDER BY "user_id"`);
    assert.equal(rows.length, 2);
    assert.deepEqual(rows.map((x) => x.user_id).sort(), [OWNER, STRANGER].sort(),
      "both rows belong to one owner");
  });

await check("the lease still holds over a live table missing its optional columns", async () => {
  // THE LIVE TABLE IS THE AUTHORITY, NOT schema.sql — on 2026-09-05 the live
  // `events` table was missing two columns this repo declared and every write
  // became a D1 1101. `d1ClaimAsk` answers that by projecting onto whatever
  // columns exist, which means the statement's parameter NUMBERS shift with the
  // table: the row is ?1..?n, the row predicate is ?n+1 and ?n+2, and the
  // budget is ?n+3..?n+5. Get that arithmetic wrong on a narrower table and the
  // predicate silently compares the wrong values — a lease that is a decoration
  // on exactly the databases most likely to be skewed.
  reset();
  const r = d1Rig();
  for (const gone of ["trigger", "acted_at", "channel"]) {
    r.d1.db.exec(`ALTER TABLE "connect_nudges" DROP COLUMN "${gone}"`);
  }
  // THE CROSS-APP RACE, run over the narrower table: the budget predicate is
  // the one whose parameters sit furthest from ?1, so it is the one a shifted
  // `n` breaks first, and an overlap is the only shape in which it decides
  // anything (sequentially the policy refuses before the lease is reached).
  const both = await Promise.all([
    sendConnectAsk(r.env, OWNER, SLUG_A, "in_task", r.deps),
    sendConnectAsk(r.env, OWNER, SLUG_B, "laptop_closed", r.deps),
  ]);
  for (const d of r.drafted) tokenOf(d.link);
  assert.equal(both.filter((o) => o.sent).length, 1,
    `a table missing three columns sent ${both.filter((o) => o.sent).length} texts: `
      + both.map((o) => `${o.cause}:${o.reason}`).join(" | "));
  assert.equal(calls.length, 1);
  const rows = r.d1.rows<Record<string, unknown>>(
    `SELECT * FROM "connect_nudges" WHERE "sent_at" IS NOT NULL`);
  assert.equal(rows.length, 1, "the loser recorded an ask nobody received");
  assert.equal(rows[0].sent_at, NOW, "the ask was recorded with the wrong parameter");
  assert.equal(rows[0].state, "asked");
});

await check("CONTROL: the budget ENDS, and the lease and the policy end it at the same instant",
  async () => {
    // The other direction, and the one a floor gets wrong silently: a cap with
    // no upper edge is the feature switched off, and nobody would notice for a
    // week at a time. `shouldAsk` holds while `now - lastAsk < 7 days`, so an
    // ask EXACTLY seven days old is licensed — and the lease's own predicate is
    // `sent_at > now - 7 days`, which is false at exactly that instant. The two
    // have to agree to the millisecond or the lease refuses asks the policy
    // allowed and reports them as an overlap that never happened.
    for (const [why, age, sent] of [
      ["a day inside the week", DAY, false],
      ["exactly seven days old", GLOBAL_ASK_INTERVAL_DAYS * DAY, true],
      ["eight days old", 8 * DAY, true],
    ] as [string, number, boolean][]) {
      reset();
      const r = d1Rig();
      // A DIFFERENT app, which is the only kind of row the budget predicate
      // looks at, carrying the last ask this owner had.
      r.d1.db.prepare(
        `INSERT INTO "connect_nudges"
           ("user_id","toolkit","state","level","snooze_until","trigger","sent_at","acted_at","channel")
         VALUES (?, ?, 'declined', 1, NULL, 'in_task', ?, NULL, 'sms')`,
      ).run(OWNER, SLUG_B, NOW - age);
      const out = await sendConnectAsk(r.env, OWNER, SLUG_A, "laptop_closed", r.deps);
      for (const d of r.drafted) tokenOf(d.link);
      assert.equal(out.sent, sent,
        `an ask ${why} answered ${out.cause}: ${out.reason}`);
      if (sent) {
        assert.equal(calls.length, 1, `${why}: the ask was licensed and no text went out`);
      } else {
        // AND IT IS THE POLICY THAT REFUSED, not the lease: an ask inside the
        // week must never reach the claim, or the report cannot tell somebody
        // being protected from two ticks colliding.
        assert.equal(out.cause, "hold", `${why} answered ${out.cause}`);
        assert.match(out.reason, /across all apps/);
        assert.equal(calls.length, 0);
      }
    }
  });

await check("nothing is minted until the policy, the catalog and the number all answer", async () => {
  const cases: [string, Partial<NudgeDeps>, NudgeMoment | undefined, string][] = [
    ["a held moment", {}, goodMoment({ taskInFlight: true }), "hold"],
    ["no moment at all", { moment: async () => null }, undefined, "no-moment"],
    ["a moment reader that threw", { moment: async () => { throw new Error("x"); } }, undefined,
      "no-moment"],
    ["a catalog that did not answer",
      { catalog: { toolkit: async () => { throw new Error("502"); } } }, undefined, "no-catalog"],
    ["an owner with no number", { phone: async () => null }, undefined, "no-phone"],
    ["an owner whose number is blank", { phone: async () => "   " }, undefined, "no-phone"],
  ];
  for (const [why, over, moment, cause] of cases) {
    reset();
    const r = rig(over, SENDBLUE, moment);
    const out = await sendConnectAsk(r.env, OWNER, SLUG_A, "in_task", r.deps);
    assert.equal(out.sent, false, `${why} still sent a text`);
    assert.equal(out.cause, cause, `${why} answered ${out.cause}`);
    assert.equal(calls.length, 0, `${why} sent a text`);
    assert.equal((await r.store.linksForOwner(OWNER)).length, 0,
      `${why} minted a link nobody can ever redeem`);
    assert.equal(await r.store.readNudge(OWNER, SLUG_A), null,
      `${why} wrote an ask row for an ask that never happened`);
  }
});

await check("a failed read is not a fresh owner; a missing row is", async () => {
  reset();
  const r = rig();
  const broken: NudgeDeps = {
    ...r.deps,
    store: { ...r.store, readNudge: async () => { throw new Error("D1 1101"); } },
  };
  const out = await sendConnectAsk(r.env, OWNER, SLUG_A, "in_task", broken);
  assert.equal(out.sent, false, "a failed read was treated as an owner nobody has asked");
  assert.equal(out.cause, "no-verdict");
  assert.equal(calls.length, 0);

  // The CONTROL: readNudge returning null IS a fresh owner, and they get asked.
  reset();
  const fresh = rig();
  assert.equal((await sendConnectAsk(fresh.env, OWNER, SLUG_A, "in_task", fresh.deps)).sent, true);
  tokenOf(fresh.drafted[0].link);
});

await check("an unreadable ask history refuses rather than guessing at the cap", async () => {
  // Two shapes, and neither may collapse into "nobody has ever been asked
  // anything": a read that THREW, and a store that answered with something
  // that is not a list of rows.
  for (const [why, nudgesForOwner] of [
    ["a read that threw", async () => { throw new Error("D1 1101"); }],
    ["an answer that is not a list", (async () => null) as never],
    ["an answer that is a string", (async () => "rows") as never],
  ] as [string, () => Promise<never>][]) {
    reset();
    const r = rig();
    const broken: NudgeDeps = { ...r.deps, store: { ...r.store, nudgesForOwner } };
    const out = await sendConnectAsk(r.env, OWNER, SLUG_A, "in_task", broken);
    assert.equal(out.sent, false, `${why}: the 7-day cap was guessed at`);
    assert.equal(out.cause, "no-verdict", `${why} answered ${out.cause}`);
    assert.equal(calls.length, 0, `${why} sent a text`);
    assert.equal((await r.store.linksForOwner(OWNER)).length, 0, `${why} minted a link`);
  }
});

await check("a store missing a method is a wiring fault, not a text", async () => {
  // Types are stripped before any of this runs, so a wiring that handed over
  // three of the four methods would reach production and fail per-owner. Every
  // shape below must refuse rather than throw out of the sweep.
  for (const missing of ["readNudge", "nudgesForOwner", "putNudge", "put"] as const) {
    reset();
    const r = rig();
    const store = { ...r.store } as Record<string, unknown>;
    delete store[missing];
    const out = await sendConnectAsk(
      r.env, OWNER, SLUG_A, "in_task", { ...r.deps, store: store as never },
    );
    assert.equal(out.sent, false, `a store with no ${missing} still sent a text`);
    assert.equal(calls.length, 0);
  }
  // And with no catalog, no writer and no phone reader at all.
  for (const missing of ["catalog", "write", "phone", "moment"] as const) {
    reset();
    const r = rig();
    const deps = { ...r.deps } as Record<string, unknown>;
    delete deps[missing];
    const out = await sendConnectAsk(r.env, OWNER, SLUG_A, "in_task", deps as never);
    assert.equal(out.sent, false, `a wiring with no ${missing} still sent a text`);
    assert.equal(calls.length, 0);
  }
});

await check("TWO TICKS ON A ROW THAT ALREADY SAYS asked: still one text", async () => {
  // THE CASE THE `state` HALF OF THE LEASE CANNOT SEE. This owner was asked
  // twenty days ago and never answered, so the silence has matured into a
  // decline and the snooze it earned has run out. Both ticks read a row whose
  // state is `asked` — and the row they each want to write says `asked` too,
  // so a predicate on the state alone matches for both of them. Only `sent_at`
  // tells the ask that was sent from the ask that is being sent.
  reset();
  const r = d1Rig();
  r.d1.db.prepare(
    `INSERT INTO "connect_nudges"
       ("user_id","toolkit","state","level","snooze_until","trigger","sent_at","acted_at","channel")
     VALUES (?, ?, 'asked', 0, NULL, 'in_task', ?, NULL, 'sms')`,
  ).run(OWNER, SLUG_A, NOW - 20 * DAY);

  const both = await Promise.all([
    sendConnectAsk(r.env, OWNER, SLUG_A, "laptop_closed", r.deps),
    sendConnectAsk(r.env, OWNER, SLUG_A, "laptop_closed", r.deps),
  ]);
  for (const d of r.drafted) tokenOf(d.link);

  assert.equal(both.filter((o) => o.sent).length, 1,
    `neither or both ticks sent: ${both.map((o) => `${o.cause}:${o.reason}`).join(" | ")}`);
  assert.equal(calls.length, 1, `${calls.length} texts left the Worker for one owner`);
  assert.equal(both.find((o) => !o.sent)!.cause, "lost-race");

  // AND THE DECLINE THE SILENCE EARNED SURVIVED the re-ask: the winner wrote
  // level 1, not level 0.
  const rows = r.d1.rows<Record<string, unknown>>(`SELECT * FROM "connect_nudges"`);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].sent_at, NOW);
  assert.equal(rows[0].level, 1, "the re-ask erased the decline the silence earned");
});

await check("a NO that lands while the ask is being written is not written over", async () => {
  // The sweep is not the only writer of `connect_nudges`: routes/connect.ts
  // `/skip` records a decline the moment somebody taps it, and it does not
  // touch `sent_at` on a row nobody has ever been sent. So a lease that
  // compared only `sent_at` would still hold — and this ask would overwrite a
  // "no" this owner had just given, with `state: "asked"`.
  //
  // The decline is injected from inside the writer, which is where the real
  // gap is: the read happened three awaits ago and the send has not happened
  // yet.
  reset();
  let landed = false;
  const r = d1Rig({
    write: (input) => {
      if (!landed) {
        landed = true;
        r.d1.db.prepare(
          `INSERT INTO "connect_nudges"
             ("user_id","toolkit","state","level","snooze_until","trigger","sent_at","acted_at","channel")
           VALUES (?, ?, 'declined', 1, ?, NULL, NULL, ?, NULL)`,
        ).run(OWNER, SLUG_A, NOW + 14 * DAY, NOW);
      }
      const i = input as { evidence: { link: string }; meta: ToolkitMeta; moment: string };
      r.drafted.push({ link: i.evidence.link, slug: i.meta.slug, moment: i.moment });
      return goodDraft(i.evidence.link);
    },
  });

  const out = await sendConnectAsk(r.env, OWNER, SLUG_A, "in_task", r.deps);
  for (const d of r.drafted) tokenOf(d.link);
  assert.equal(landed, true, "the decline never landed, so this check measured nothing");
  assert.equal(out.sent, false, "a text went out over a no this owner had just given");
  assert.equal(out.cause, "lost-race", `the ask answered ${out.cause}: ${out.reason}`);
  assert.equal(calls.length, 0);

  const rows = r.d1.rows<Record<string, unknown>>(`SELECT * FROM "connect_nudges"`);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].state, "declined", "the ask overwrote the decline");
  assert.equal(rows[0].level, 1, "the decline ladder was reset by an ask nobody received");
});

await check("nothing to claim the ask with is silence, not a text", async () => {
  reset();
  const r = rig();
  // The store brings no lease of its own and this env has no D1 binding, so
  // there is no way to tell whether another tick is already sending. A floor
  // with no verdict refuses.
  const store = { ...r.store } as Record<string, unknown>;
  delete store.claimAsk;
  const out = await sendConnectAsk(
    r.env, OWNER, SLUG_A, "in_task", { ...r.deps, store: store as never },
  );
  assert.equal(out.sent, false, "an ask nothing could claim went out anyway");
  assert.equal(out.cause, "no-lease", `unclaimable ask answered ${out.cause}`);
  assert.equal(calls.length, 0);
  assert.equal(await r.store.readNudge(OWNER, SLUG_A), null,
    "a row was written for a text nobody received");
});

await check("a draft that breaks a rule is refused, not repaired, and no text goes out", async () => {
  reset();
  const r = rig({ write: (i) => `Authorize your app now: ${(i as { evidence: { link: string } }).evidence.link}. Up to you.` });
  const out = await sendConnectAsk(r.env, OWNER, SLUG_A, "in_task", r.deps);
  assert.equal(out.sent, false, "a message using the forbidden register was sent");
  assert.equal(out.cause, "refused-copy");
  assert.equal(calls.length, 0);
  assert.equal(await r.store.readNudge(OWNER, SLUG_A), null,
    "a refused draft spent this owner's one ask for the week");
  // The minted link is left to expire, unused and never given to anybody. That
  // is the documented cost of refusing rather than repairing.
  assert.equal((await r.store.linksForOwner(OWNER)).length, 1);
});

await check("a send that fails hands the ask back, so the interruption is not spent", async () => {
  reset();
  reply = () => new Response(
    JSON.stringify({ status: "ERROR", error_code: 4004, error_message: "no" }), { status: 200 },
  );
  const r = rig();
  const out = await sendConnectAsk(r.env, OWNER, SLUG_A, "in_task", r.deps);
  assert.equal(out.sent, false, "a 2xx carrying ERROR was read as sent");
  assert.equal(out.cause, "not-delivered");
  tokenOf(r.drafted[0].link);
  // The row is written back to exactly what it was before the lease was taken:
  // never_asked, with no sent_at. Recording this owner as asked would silence
  // them for a week over a message they never received.
  const handedBack = await r.store.readNudge(OWNER, SLUG_A);
  assert.ok(handedBack, "the hand-back wrote nothing at all");
  assert.equal(handedBack.state, "never_asked",
    "an owner who received nothing was recorded as asked, and is now silent for a week");
  assert.equal(handedBack.sent_at, null, "a sent_at was left behind for a text that never went");

  // And the next sweep may try again.
  reset();
  const again = await sendConnectAsk(r.env, OWNER, SLUG_A, "in_task", r.deps);
  assert.equal(again.sent, true, "a failed send silenced this owner permanently");
  tokenOf(r.drafted[1].link);
});

await check("a re-ask after 72 hours of silence does not erase the decline", async () => {
  reset();
  const r = rig();
  // The owner was asked about a DIFFERENT app 30 days ago and never answered,
  // so the global cap is open and the silence has matured into a decline.
  await r.store.putNudge({
    ...freshNudge(OWNER, SLUG_A), state: "asked", trigger: "in_task", sent_at: NOW - 30 * DAY,
  });
  const out = await sendConnectAsk(r.env, OWNER, SLUG_A, "laptop_closed", r.deps);
  assert.equal(out.sent, true, `the re-ask was blocked: ${out.cause} — ${out.reason}`);
  tokenOf(r.drafted[0].link);
  const row = await r.store.readNudge(OWNER, SLUG_A);
  assert.ok(row);
  assert.equal(row.level, 1,
    "the 72-hour silence decline was erased by the re-ask; this owner can now be asked forever");
  assert.equal(row.state, "asked");
  assert.equal(row.sent_at, NOW);
});

await check("an owner NAME never reaches a text, a link or a row", async () => {
  reset();
  const r = rig();
  const out = await sendConnectAsk(r.env, "omar", SLUG_A, "in_task", r.deps);
  assert.equal(out.sent, false);
  assert.equal(out.cause, "no-owner");
  assert.equal(calls.length, 0);
});

await check("a nudge row belonging to somebody else stops the ask", async () => {
  reset();
  const r = rig();
  const crossed: NudgeDeps = {
    ...r.deps,
    store: {
      ...r.store,
      readNudge: async () => ({ ...freshNudge(STRANGER, SLUG_A), state: "declined", level: 3 }),
    },
  };
  const out = await sendConnectAsk(r.env, OWNER, SLUG_A, "in_task", crossed);
  assert.equal(out.sent, false, "one owner's ask was decided by another owner's row");
  assert.equal(out.cause, "no-verdict");
  assert.equal(calls.length, 0);
});

await check("no wiring: sendConnectAsk says so and texts nobody", async () => {
  reset();
  assert.equal(nudgeWiringInstalled(), false,
    "something installed nudge wiring before this check; the unwired state is untestable");
  const out = await sendConnectAsk(SENDBLUE, OWNER, SLUG_A, "in_task");
  assert.equal(out.sent, false);
  assert.equal(out.cause, "no-wiring");
  assert.equal(calls.length, 0);
});

// ===========================================================================
// 6. THE SWEEP
// ===========================================================================

await check("an unwired sweep asks nobody and says which wiring is missing", async () => {
  reset();
  const report = await connectNudgeSweep(SENDBLUE);
  assert.equal(report.wired, false);
  assert.equal(report.sent, 0);
  assert.equal(calls.length, 0);
  assert.ok(LOGS.some((l) => l.includes("no wiring installed")));
});

await check("one owner gets at most one ask per tick, whatever is due", async () => {
  reset();
  const r = rig({
    due: async () => [
      { owner: OWNER, toolkit: SLUG_A, trigger: "in_task" },
      { owner: OWNER, toolkit: SLUG_B, trigger: "laptop_closed" },
      { owner: OWNER, toolkit: "thirdapp", trigger: "user_named_it" },
    ],
  });
  const report = await connectNudgeSweep(r.env, r.deps);
  assert.equal(report.considered, 3);
  assert.equal(report.sent, 1, "one owner received more than one connect text in one tick");
  assert.equal(report.skipped, 2);
  assert.equal(calls.length, 1);
  r.drafted.forEach((d) => tokenOf(d.link));
});

await check("a bad candidate does not stop the ones behind it", async () => {
  reset();
  const r = rig({
    due: async () => [
      { owner: "omar", toolkit: SLUG_A, trigger: "in_task" },
      { owner: OWNER, toolkit: SLUG_B, trigger: "in_task" },
    ],
  });
  const report = await connectNudgeSweep(r.env, r.deps);
  assert.equal(report.sent, 1, "one unusable row switched the feature off for everybody behind it");
  assert.equal(report.refused, 1);
  r.drafted.forEach((d) => tokenOf(d.link));
});

await check("the sweep never throws, whatever the due list does", async () => {
  reset();
  const r = rig({ due: async () => { throw new Error("D1 1101"); } });
  const report = await connectNudgeSweep(r.env, r.deps);
  assert.equal(report.wired, true);
  assert.equal(report.considered, 0);
  assert.equal(calls.length, 0);

  const notAList = rig({ due: (async () => "nope") as never });
  const second = await connectNudgeSweep(notAList.env, notAList.deps);
  assert.equal(second.considered, 0);
});

await check("the per-tick budget is a ceiling on subrequests, not a suggestion", async () => {
  reset();
  const many = Array.from({ length: MAX_ASKS_PER_SWEEP + 5 }, (_, i) => ({
    owner: `owner${String(i).padStart(10, "0")}`,
    toolkit: SLUG_A,
    trigger: "in_task" as NudgeTrigger,
  }));
  assert.ok(many.every((c) => /^[a-z0-9]{15}$/.test(c.owner)), "the fixture owners are not row ids");
  const r = rig({ due: async () => many });
  const report = await connectNudgeSweep(r.env, r.deps);
  assert.equal(report.sent, MAX_ASKS_PER_SWEEP, "the sweep sent past its own budget");
  assert.equal(report.skipped, 5);
  assert.equal(calls.length, MAX_ASKS_PER_SWEEP);
  r.drafted.forEach((d) => tokenOf(d.link));
});

// THIS ONE RUNS LAST IN ITS SECTION ON PURPOSE: `installNudgeWiring` flips a
// module-global for the life of the process, so every "nothing is wired" check
// above has to have run already.
await check("installed wiring is what production uses: no deps passed, one text out", async () => {
  reset();
  const r = rig({ due: async () => [{ owner: OWNER, toolkit: SLUG_B, trigger: "laptop_closed" }] });
  installNudgeWiring((env) => (env === r.env ? r.deps : null));
  assert.equal(nudgeWiringInstalled(), true);

  // No fifth argument, no injected deps: the path src/cron.ts would take.
  const report = await connectNudgeSweep(r.env);
  assert.equal(report.wired, true);
  assert.equal(report.sent, 1, "the installed wiring was not consulted");
  assert.equal(calls.length, 1);
  r.drafted.forEach((d) => tokenOf(d.link));

  // And a Worker whose env the wiring cannot serve still asks nobody.
  reset();
  const out = await sendConnectAsk({ ...SENDBLUE }, OWNER, SLUG_A, "in_task");
  assert.equal(out.cause, "no-wiring");
  assert.equal(calls.length, 0);
});

// ===========================================================================
// 7. WHOLE-SUITE SCANS
// ===========================================================================

await check("no raw token ever reached a log line or a message body", () => {
  assert.ok(MINTED_TOKENS.length >= 30, "too few tokens were minted for this scan to mean much");
  const haystack = LOGS.join("\n");
  for (const token of MINTED_TOKENS) {
    assert.ok(!haystack.includes(token),
      "a raw connect token reached a log line — a support transcript or a `wrangler tail` "
        + "would then hand its reader an account binding");
  }
});

await check("every message that left carries exactly one URL, and it is ours", () => {
  assert.ok(SENT.length >= 20, "too few messages were sent for this scan to mean much");
  const urlLike = /https?:\/\/\S+|(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}\/\S*/gi;
  for (const content of SENT) {
    const urls = content.match(urlLike) ?? [];
    assert.equal(urls.length, 1, `a message carried ${urls.length} links: ${content}`);
    assert.ok(urls[0].startsWith(CONNECT_URL_BASE + "/"),
      `a message carried a link that is not ours: ${urls[0]}`);
  }
});

await check("the register held in every message that left", () => {
  assert.ok(SENT.length >= 20, "too few messages were sent for this scan to mean much");
  for (const content of SENT) {
    // The link is lifted out first, exactly as the containment does it: our own
    // host is `api.anticipy.ai`, and the token is 43 characters nobody reads.
    const words = content.replace(
      new RegExp(`${CONNECT_URL_BASE.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}/[A-Za-z0-9_-]+`, "g"),
      " ",
    );
    for (const term of FORBIDDEN_TERMS) {
      const re = new RegExp(`(?<![a-z0-9])${term.replace(/ /g, "\\s+")}(?![a-z0-9])`, "i");
      assert.ok(!re.test(words), `"${term}" reached a person's phone: ${content}`);
    }
    assert.ok(!content.includes("!"), `an exclamation mark reached a person's phone: ${content}`);
  }
});

// ===========================================================================
// 8. THE SOURCE ITSELF
// ===========================================================================

await check("nudge.ts names no app and never says the vendor's name in code", () => {
  const code = SOURCE
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((line) => !/^\s*\/\//.test(line))
    .join("\n");
  assert.ok(code.length > 4000, "the comment stripper ate the file; this scan proves nothing");
  assert.ok(!/composio/i.test(code), "nudge.ts carries the vendor's name outside a comment");
  for (const app of ["gmail", "notion", "slack", "googlecalendar", "outlook", "drive"]) {
    assert.ok(!new RegExp(`["'\`]${app}["'\`]`, "i").test(code),
      `nudge.ts hardcodes ${app}; the spec's rule is that a new app in the catalog is a new `
        + "app in Anticipy with zero code");
  }
});

await check("the phone's own idea of a link is words.ts's, character for character", () => {
  const mine = SOURCE.match(/^const URL_LIKE = (.+);$/m);
  const theirs = WORDS_SOURCE.match(/^const URL_LIKE = (.+);$/m);
  assert.ok(mine && theirs, "one of the two URL_LIKE declarations moved");
  assert.equal(mine[1], theirs[1],
    "nudge.ts and words.ts disagree about what a phone will linkify, so one of them will let "
      + "a vendor link through");
});

await check("askMessage exists only because the two link constants disagree", () => {
  // THE EXPIRY. words.ts `askText` is the shared containment and nudge.ts would
  // call it, but words.ts pins the link prefix to the apex while this Worker's
  // only route is `api.anticipy.ai` — so `askText` refuses every link that
  // actually resolves. The day somebody routes the apex and moves
  // CONNECT_LINK_PREFIX to match, THIS CHECK GOES RED: delete `askMessage`,
  // call `askText`, and delete this check with it.
  assert.notEqual(CONNECT_LINK_PREFIX, `${CONNECT_URL_BASE}/`,
    "words.ts CONNECT_LINK_PREFIX and routes/connect.ts CONNECT_URL_BASE now agree — "
      + "askMessage in src/connections/nudge.ts is a duplicate of askText in "
      + "src/connections/words.ts and must be deleted in favour of it");
});

// ---------------------------------------------------------------------------
// MUTATIONS RUN AGAINST src/connections/nudge.ts, 2026-09-06. Every one is
// anchored on a string that occurs EXACTLY ONCE in that file (the script
// refuses to run otherwise, because a regex that silently fails to match
// produces a false "it is tested" reading — that mistake was made twice on
// 2026-09-05). All twenty-nine went RED; the check each one killed is named.
//
//   1  `if (since < GLOBAL_ASK_INTERVAL_DAYS * DAY_MS) {` -> `if (false) {`
//      -> "the 7-day cap is global across ALL apps, and skew does not open it"
//   2  `token_handle: await tokenHandle(token),` -> `token_handle: token,`
//      -> "the stored row holds sha256(token) and NEVER the token"
//   3  `const words = text.split(link).join(" ");` -> `const words = text;`
//      -> "our own host contains 'api' and that must not refuse every ask"
//   4  `if (urls.length !== 1) {` -> `if (urls.length > 2) {`
//      -> "THE ONLY URL IN THE MESSAGE IS OURS"
//   5  `const before = maturedBySilence(row, now);` -> `const before = row;`
//      -> "a re-ask after 72 hours of silence does not erase the decline"
//   6  the hand-back `await claim(asked, before);` -> `void before;`
//      -> "a send that fails hands the ask back"
//   7  quiet hours `>= QUIET_HOURS_START` -> `> QUIET_HOURS_START`
//      -> "the moment floors: mid-step, before the result, quiet hours, no evidence"
//   8  `return verdict?.decision === "ask";` -> `!== "hold"`
//      -> "THE FLOOR: every missing or unreadable input is no-verdict"
//   9  `if (ctx.tasksThatWouldHaveUsedIt === 0) {` -> `if (false) {`
//      -> "the moment floors" (an ask with no evidence is an advertisement)
//  10  `if (!isOurLink(link, base)) {` -> `if (false) {`
//      -> "THE ONLY URL IN THE MESSAGE IS OURS" (a vendor link accepted)
//  11  `readNudge(who, slug)` -> `readNudge(who, slug).catch(() => null)`
//      -> "a failed read is not a fresh owner; a missing row is"
//  12  the mint moved ahead of the catalog call
//      -> "nothing is minted until the policy, the catalog and the number all answer"
//  13  `if (!copy.ok) {` -> `if (false && !copy.ok) {`
//      -> "a draft that breaks a rule is refused, not repaired"
//  14  the sweep's `|| askedThisTick.has(key)` deleted
//      -> "one owner gets at most one ask per tick, whatever is due"
//  15  `if (words.includes("!")) {` -> `if (false) {`
//      -> "no exclamation marks, and no consent-form stiffness"
//  16  `if (to === "") {` -> `if (false) {`
//      -> "nothing is minted until the policy, the catalog and the number all answer"
//  17  the lease write `won = await claim(row, asked);` made conditional on `0`
//      -> "THE CONTROL: a well-evidenced post-result moment sends exactly one text"
//  18  `if (!Array.isArray(history)) {` -> `if (false) {`
//      -> "an unreadable ask history refuses rather than guessing at the cap"
//  19  `expires_at: now + LINK_TTL_MS,` -> `LINK_TTL_MS * 1000`
//      -> "a minted link is dead ten minutes later, and dead to a stranger now"
//  20  `user_id: who,` in the minted row -> a hardcoded stranger's id
//      -> "the mint and the route's own redeem agree: mint, tap, spent"
//
// THE LEASE (section 3b), added 2026-09-06 when overlapping ticks were driven
// and two texts went to one owner. Nine more, all RED:
//
//  21  `if (!won) {` -> `if (false) {`
//      -> "TWO TICKS AT ONCE: one text, one row, and the loser says so"
//  22  the whole `WHERE … state IS … AND … sent_at IS …` predicate deleted,
//      leaving the plain upsert this replaced
//      -> "TWO TICKS AT ONCE: one text, one row, and the loser says so"
//  23  the STATE half of that predicate deleted
//      -> "a NO that lands while the ask is being written is not written over"
//  24  the SENT_AT half inverted (`IS` -> `IS NOT`)
//      -> "TWO TICKS ON A ROW THAT ALREADY SAYS asked: still one text"
//  25  `Number(res.meta?.changes ?? 0) === 1` -> `>= 0`
//      -> "TWO TICKS AT ONCE: one text, one row, and the loser says so"
//  26  `if (claim === null) {` -> `if (false as boolean) {`
//      -> "nothing to claim the ask with is silence, not a text"
//  27  `await claim(asked, before)` -> `await claim(before, asked)`
//      -> "a send that fails hands the ask back, so the interruption is not spent"
//  28  `won = await claim(row, asked)` -> `claim(asked, asked)`
//      -> "THE CONTROL: a well-evidenced post-result moment sends exactly one text"
//  29  `ON CONFLICT(…) DO UPDATE SET` -> `DO NOTHING`
//      -> "TWO TICKS AT ONCE: one text, one row, and the loser says so"
//
// THE WEEK (the `AskBudget` half of the lease), added 2026-09-06 when the
// round-2 audit found that the lease above is keyed (user_id, toolkit) while
// the cap it enforces is keyed by PERSON. Eight more, all RED, each anchored on
// a literal src/connections/nudge.ts carries exactly once (an anchor matching
// anything other than once refused to patch):
//
//  30  `if (budget !== null) {` -> `if (false as boolean) {`
//      -> "TWO TICKS, TWO DIFFERENT APPS, ONE OWNER: one text"
//  31  the budget's `b."user_id" = ?` made a tautology (a FLEET-wide cap)
//      -> "CONTROL: the weekly budget is one PERSON's, so two owners at once
//         get two texts"
//  32  the budget dropped from the INSERT half, kept in DO UPDATE — the shape
//      that misses the commonest race, two ticks about an owner with no rows
//      -> "TWO TICKS, TWO DIFFERENT APPS, ONE OWNER: one text"
//  33  `b."sent_at" > ?` -> `>=`, so the lease and the policy disagree by a
//      millisecond at the window's edge
//      -> "CONTROL: the budget ENDS, and the lease and the policy end it at
//         the same instant"
//  34  `noAskSince: now - GLOBAL_ASK_INTERVAL_DAYS * DAY_MS` -> `now`
//      -> "TWO TICKS, TWO DIFFERENT APPS, ONE OWNER: one text"
//  35  the same -> `0`, a window with no end
//      -> "CONTROL: the budget ENDS, and the lease and the policy end it at
//         the same instant"
//  36  `b."toolkit" <> ?` -> `=`, so the budget looks at the app it is about
//      -> "TWO TICKS, TWO DIFFERENT APPS, ONE OWNER: one text"
//  37  the ROW predicate deleted and the budget kept
//      -> "TWO TICKS AT ONCE: one text, one row, and the loser says so"
//
// A NINTH SURVIVED FIRST TIME and is recorded because the check it should have
// killed was wrong, not the code: #31 lived through a two-owner control that
// used the SAME app for both, where the budget's own `toolkit <> ?` clause
// hides a missing `user_id`. The control now uses two owners AND two apps.
// ---------------------------------------------------------------------------

console.log = realLog;
globalThis.fetch = realFetch;
await check("MAX_ASKS_PER_SWEEP is 20 — the number, not just the name", () => {
  // THE PER-TICK OUTBOUND-TEXT BUDGET, and it was asserted only against itself.
  // Raised 20 -> 2000 by an audit on 2026-09-06 with all 53 checks green, because
  // every assertion reads `report.sent === MAX_ASKS_PER_SWEEP`. This is how many
  // texts one sweep may send to one fleet of owners; at 2000 a single tick could
  // text everybody, which is the shape of the accident this budget exists to stop.
  assert.equal(MAX_ASKS_PER_SWEEP, 20,
    `MAX_ASKS_PER_SWEEP is now ${MAX_ASKS_PER_SWEEP}. If that is deliberate, say why here `
      + "and change this line; a ceiling must not move by accident.");
});


console.log(`connections-nudge: ${passes} checks passed, ${failures} failed`);
if (failures) process.exit(1);
