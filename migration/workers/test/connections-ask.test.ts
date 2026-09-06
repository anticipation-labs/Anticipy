/**
 * test/connections-ask.test.ts — THE ASK ACTUALLY GOING OUT.
 *
 *   node --experimental-strip-types migration/workers/test/connections-ask.test.ts
 *
 * WHAT IS REAL HERE, because it is nearly everything. The D1 binding is
 * node:sqlite over the REAL migration/d1/schema.sql — every CHECK and every
 * partial-unique index is the database's own answer. The store, the policy, the
 * link mint, the judge, the sweep, the `who is due` SQL, the wiring and
 * `scheduled` out of src/cron.ts are the shipped modules, unmocked. The writer
 * under test is the REAL `makeAskWriter`, not a stub of it — the retry in
 * src/connections/wiring.ts was found to have never fired once precisely
 * because its suite drove a hand-built object instead of the shipped function.
 *
 * EXACTLY ONE THING IS FAKED: `globalThis.fetch`. Three hosts answer — the
 * vendor catalog, the model, and the messaging provider — and everything
 * between them is production code.
 *
 * THE FAILURES THIS FILE EXISTS TO CATCH:
 *
 *   NOTHING EVER ASKS. The whole reason this task existed: `AskWriter` was a
 *   type with no implementation and `installNudgeWiring` had zero callers, so
 *   a fully built feature asked nobody anything, forever. The CONTROL at the
 *   bottom drives `scheduled("*\/5 * * * *")` end to end and asserts ONE text
 *   left the building with ONE row flipped behind it.
 *
 *   A TEMPLATE. A model that will not write the sentence must produce SILENCE,
 *   never a house-written message. Three shapes are pinned: the model throws,
 *   the model returns nothing, and the model returns something the judge
 *   refuses. None of them may text anybody.
 *
 *   THE JUDGE BEING TALKED AROUND. The writer's own retry uses the SHIPPED
 *   judge (`askMessage`), so it cannot be tuned to pass itself; the checks
 *   below drive a stubborn model and assert the refusal still lands.
 *
 *   THREE TEXTS IN ONE MINUTE. The 7-day cap is GLOBAL — a nudge row for a
 *   DIFFERENT app closes the gate — and a second tick five minutes later must
 *   send nothing at all.
 *
 *   AN ASK MID-ERRAND, OR INSTEAD OF AN ANSWER. Both are read out of this
 *   owner's own `jobs` rows by the wiring, and both must hold.
 *
 *   A PART NOTHING CALLS, AGAIN. wrangler.jsonc must register the five-minute
 *   tick and src/cron.ts must route it; a leg that exists but is never
 *   dispatched fails here.
 *
 * NO APP IS HARDCODED, MADE BEHAVIOURAL. Every scenario runs on slugs that
 * exist in no catalog, and the last check greps the shipped sources for the
 * names of real apps.
 *
 * MUTATIONS THIS FILE MUST GO RED ON: see the list at the bottom.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import {
  ASK_ATTEMPTS,
  ASK_CEILING_CHARS,
  DEFAULT_ASK_MODEL,
  MODEL_FIXABLE,
  MOMENT_SENTENCE,
  askModel,
  askPrompt,
  judgeDraft,
  makeAskWriter,
  parseAsk,
  phrasingOf,
  type AskEnv,
} from "../src/connections/ask.ts";
import {
  FINISHED_JOB_STATUS,
  DEFAULT_CONNECT_MODEL,
  nudgeDeps,
  nudgeMomentFor,
  nudgeWiring,
  ownerLocalHour,
  ownerPhone,
  type NudgeWiringEnv,
} from "../src/connections/wiring.ts";
import {
  GLOBAL_ASK_INTERVAL_DAYS,
  MAX_ASKS_PER_SWEEP,
  connectNudgeSweep,
  type NudgeEnv,
} from "../src/connections/nudge.ts";
import { FORBIDDEN_TERMS, STIFF_FORMS, type AskInput } from "../src/connections/words.ts";
import { CONNECT_URL_BASE, TOKEN_CHARS } from "../src/routes/connect.ts";
import { COMPOSIO_BASE_URL, resetConnectionsProvider } from "../src/connections/provider.ts";
import { SENDBLUE_BASE } from "../src/messaging.ts";
import { NUDGE_TRIGGERS } from "../src/connections/store.ts";
import { scheduled, type CronEnv } from "../src/cron.ts";
import { FakeD1, asD1 } from "./fake-d1.ts";
import type { ToolkitMeta } from "../../../spike/two-hands/src/connections/contract.ts";

const here = dirname(fileURLToPath(import.meta.url));
const ASK_SOURCE = readFileSync(join(here, "..", "src", "connections", "ask.ts"), "utf8");
const WIRING_SOURCE = readFileSync(join(here, "..", "src", "connections", "wiring.ts"), "utf8");
const WORDS_SOURCE = readFileSync(join(here, "..", "src", "connections", "words.ts"), "utf8");
const NUDGE_SOURCE = readFileSync(join(here, "..", "src", "connections", "nudge.ts"), "utf8");
const CRON_SOURCE = readFileSync(join(here, "..", "src", "cron.ts"), "utf8");
const WRANGLER = readFileSync(join(here, "..", "wrangler.jsonc"), "utf8");
const PACKAGE_JSON = readFileSync(join(here, "..", "package.json"), "utf8");

let failures = 0;
let passes = 0;
async function check(what: string, fn: () => void | Promise<void>): Promise<void> {
  try { await fn(); passes++; }
  catch (err) { failures++; console.error("FAIL " + what + "\n     " + (err as Error).message); }
}

const LOGS: string[] = [];
const realLog = console.log;
console.log = ((...a: unknown[]) => { LOGS.push(a.map(String).join(" ")); }) as typeof console.log;

// ---------------------------------------------------------------------------
// FIXTURES
// ---------------------------------------------------------------------------

/**
 * THE CLOCK IS THE REAL ONE, and that is not laziness.
 *
 * `nudgeDeps` deliberately leaves `NudgeDeps.now` unset — "tests own the clock
 * and production passes nothing" — so the shipped wiring reads `Date.now()`.
 * The whole-chain checks drive `scheduled()` with nothing injected, which is
 * the point of them, and a fixture pinned to a literal timestamp would put
 * every seeded row a year in the past: `resultDelivered` reads a seven-day
 * window and would be false forever, so the suite would go green on a hold and
 * prove nothing. Every fixture below is therefore relative to now.
 */
const NOW = Date.now();
const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;

/** An instant with a known UTC hour, for the pure clock checks that must not
 *  move when the suite is run at a different time of day. */
const FIXED = Date.UTC(2026, 8, 4, 15, 33, 20);   // 2026-09-04T15:33:20Z

/**
 * A fixed-offset IANA zone in which the local hour right now is `want`.
 *
 * COMPUTED RATHER THAN NAMED, because a suite that hardcodes "Europe/London"
 * passes all morning and fails every evening — quiet hours are 22:00 to 08:00
 * OWNER-LOCAL, and the owner's local hour depends on when the tests run. The
 * `Etc/GMT±n` zones are fixed offsets with no daylight saving, so the answer
 * does not drift under the suite.
 */
function zoneWhereLocalHourIs(want: number): string {
  const utcHour = new Date(NOW).getUTCHours();
  const offset = ((want - utcHour) % 24 + 24) % 24;
  // Etc/GMT has the sign INVERTED by POSIX convention: Etc/GMT-5 is UTC+5.
  return offset <= 14 ? `Etc/GMT-${offset}` : `Etc/GMT+${24 - offset}`;
}

const OWNER = "ownerasksaaaa11";            // 15 lowercase alphanumerics, as D1 mints
const OTHER = "ownerasksbbbb22";
const TO = "+15557654321";
const OTHER_TO = "+15557654322";

// TWO INVENTED SLUGS, in no catalog and named nowhere in src/connections/
// ask.ts or the nudge half of wiring.ts. "NO APP IS HARDCODED" made
// behavioural rather than promised.
const APP_A: ToolkitMeta = {
  slug: "zzquixotic",
  name: "Quixotic",
  logo: "https://cdn.example.invalid/q.png",
  description: "Where a team keeps its notes.",
  appUrl: "https://quixotic.example.invalid",
  scopes: ["notes.read", "notes.write"],
};
const APP_B: ToolkitMeta = {
  slug: "wobblefish",
  name: "Wobblefish",
  logo: null,
  description: null,
  appUrl: null,
  scopes: ["things.read"],
};

/** A zone whose local hour right now is inside the ask window (08:00-22:00),
 *  and one whose local hour is inside quiet hours at the same instant. Both are
 *  far enough from a boundary that a suite crossing one mid-run stays valid. */
const AWAKE_HOUR = 14;
const ASLEEP_HOUR = 3;
const AWAKE_TZ = zoneWhereLocalHourIs(AWAKE_HOUR);
const ASLEEP_TZ = zoneWhereLocalHourIs(ASLEEP_HOUR);

/**
 * A draft in this product's voice, carrying our link exactly once.
 *
 * ALL ASCII ON PURPOSE. One curly apostrophe forces the whole message to UCS-2,
 * where two segments hold 134 units rather than 306 septets, and this text plus
 * a 69-character link is over that — which is the containment working.
 *
 * BUILT FROM THE CATALOG NAME rather than a literal, so a check that swaps the
 * app swaps the copy with it.
 */
function goodDraft(link: string, name = APP_A.name): string {
  return `That one went through your browser just now. Connect your ${name} and I can do `
    + `it straight away next time: ${link}. Up to you - the browser works fine too.`;
}

function askInput(link: string, over: Partial<AskInput> = {}): AskInput {
  return {
    moment: "in_task",
    meta: APP_A,
    evidence: {
      link,
      resultDelivered: true,
      tasksThatWouldHaveUsedIt: 2,
    },
    ...over,
  } as AskInput;
}

/** A link shaped exactly as `mintConnectLink` produces one. */
function fakeLink(seed = "a"): string {
  return `${CONNECT_URL_BASE}/${seed.repeat(TOKEN_CHARS)}`;
}

// ---------------------------------------------------------------------------
// THE ONE FAKE: globalThis.fetch. Three hosts, everything else is real.
// ---------------------------------------------------------------------------

interface Call { url: string; body: string }

interface Socket {
  calls: Call[];
  /** What the model says next. A function so a check can answer differently per
   *  turn; it is handed the request body so it can read the link out of the
   *  prompt, which is the only way to write a draft carrying a token nobody
   *  knew in advance. */
  model: (body: string, turn: number) => string;
  modelStatus: number;
  /** Slug -> the catalog row the vendor answers with. */
  catalog: Map<string, ToolkitMeta>;
  catalogFails: boolean;
  sendStatus: number;
}

const socket: Socket = {
  calls: [],
  model: (body) => JSON.stringify({ message: goodDraft(linkIn(body)) }),
  modelStatus: 200,
  catalog: new Map([[APP_A.slug, APP_A], [APP_B.slug, APP_B]]),
  catalogFails: false,
  sendStatus: 200,
};

function resetSocket(): void {
  socket.calls = [];
  socket.model = (body) => JSON.stringify({ message: goodDraft(linkIn(body)) });
  socket.modelStatus = 200;
  socket.catalogFails = false;
  socket.sendStatus = 200;
}

/** The connect link out of whatever the writer was sent. */
function linkIn(body: string): string {
  const m = new RegExp(
    `${CONNECT_URL_BASE.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}/[A-Za-z0-9_-]{${TOKEN_CHARS}}`,
  ).exec(body);
  return m ? m[0] : "";
}

function modelCalls(): Call[] {
  return socket.calls.filter((c) => c.url.includes("openrouter.ai") || c.url.includes("googleapis"));
}
function sentTexts(): string[] {
  return socket.calls
    .filter((c) => c.url.startsWith(SENDBLUE_BASE))
    .map((c) => {
      try { return String((JSON.parse(c.body) as { content?: unknown }).content ?? ""); }
      catch { return ""; }
    });
}

let modelTurn = 0;
globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = String((input as { url?: string })?.url ?? input);
  const body = String(init?.body ?? "");
  socket.calls.push({ url, body });
  const json = (status: number, value: unknown): Response =>
    new Response(JSON.stringify(value), { status, headers: { "content-type": "application/json" } });

  if (url.startsWith(COMPOSIO_BASE_URL)) {
    if (socket.catalogFails) return json(500, { error: "the vendor is down" });
    const slug = decodeURIComponent(url.split("/toolkits/")[1] ?? "");
    const row = socket.catalog.get(slug);
    if (!row) return json(404, { error: "no such toolkit" });
    return json(200, {
      slug: row.slug,
      name: row.name,
      meta: { logo: row.logo, description: row.description, app_url: row.appUrl },
      scopes: row.scopes,
    });
  }
  if (url.startsWith(SENDBLUE_BASE)) {
    if (socket.sendStatus !== 200) return json(socket.sendStatus, { error_code: 400 });
    return json(200, { message_handle: "mh-1", status: "QUEUED" });
  }
  // Both model paths land here; the reply shape is the chat-completions one,
  // which is what src/llm.ts's OpenRouter leg returns unchanged.
  if (socket.modelStatus !== 200) return json(socket.modelStatus, { error: { message: "upstream" } });
  modelTurn += 1;
  return json(200, { choices: [{ message: { content: socket.model(body, modelTurn) } }] });
}) as typeof fetch;

// The vendor adapter binds globalThis.fetch when it is CONSTRUCTED and the
// isolate caches one adapter, so a stub installed after that would never be
// reached.
resetConnectionsProvider();

// ---------------------------------------------------------------------------
// A WORKER, CONFIGURED THE WAY A DEPLOYED ONE IS
// ---------------------------------------------------------------------------

interface Rig {
  d1: FakeD1;
  env: NudgeWiringEnv & CronEnv;
}

function rig(over: Record<string, unknown> = {}): Rig {
  const d1 = new FakeD1();
  const env = {
    DB: asD1(d1),
    COMPOSIO_API_KEY: "ck_test_not_a_real_key",
    OPENROUTER_API_KEY: "or_test_not_a_real_key",
    SENDBLUE_API_KEY_ID: "sbkid-test",
    SENDBLUE_API_SECRET_KEY: "sbsecret-test",
    SENDBLUE_FROM_NUMBER: "+15550001111",
    ...over,
  } as unknown as NudgeWiringEnv & CronEnv;
  resetSocket();
  modelTurn = 0;
  return { d1, env };
}

const PB_NOW = "2026-09-04 00:00:00.000Z";

function owner(r: Rig, id = OWNER, phone = TO, timezone: string | null = AWAKE_TZ): void {
  r.d1.db.prepare(
    `INSERT INTO owners (id, created, updated, email, emailVisibility, verified,
       password, tokenKey, phone, legacy_uuid) VALUES (?,?,?,?,0,0,'',?,?,'')`,
  ).run(id, PB_NOW, PB_NOW, `${id}@anticipy-test.invalid`, `key-${id}`, phone);
  if (timezone !== null) {
    r.d1.db.prepare(
      `INSERT INTO owner_profile (id, created, updated, owner_id, phone, name, first_name,
         last_name, email, birthday, facts, owner_ref, timezone)
       VALUES (?,?,?,?,'','','','','','','',?,?)`,
    ).run(`prof${id}`.slice(0, 15), PB_NOW, PB_NOW, id, id, timezone);
  }
}

/** A job of this owner's, in a status and on a date. */
function job(r: Rig, id: string, status: string, at = NOW - HOUR, who = OWNER): void {
  r.d1.db.prepare(
    `INSERT INTO jobs (id, created, updated, goal, status, owner_ref)
     VALUES (?,?,?,'a small errand',?,?)`,
  ).run(id, new Date(at).toISOString(), new Date(at).toISOString(), status, who);
}

function signal(
  r: Rig, toolkit: string, source = "observer", who = OWNER, weight = 3, alias = "",
): void {
  r.d1.db.prepare(
    `INSERT INTO app_usage_signals (user_id, toolkit, source, alias, weight, last_seen_at)
     VALUES (?,?,?,?,?,?)`,
  ).run(who, toolkit, source, alias, weight, NOW - HOUR);
}

function nudgeRow(
  r: Rig, toolkit: string,
  row: { state?: string; level?: number; snooze_until?: number | null; sent_at?: number | null },
  who = OWNER,
): void {
  r.d1.db.prepare(
    `INSERT INTO connect_nudges (user_id, toolkit, state, level, snooze_until, trigger,
       sent_at, acted_at, channel) VALUES (?,?,?,?,?,NULL,?,NULL,NULL)`,
  ).run(who, toolkit, row.state ?? "never_asked", row.level ?? 0,
    row.snooze_until ?? null, row.sent_at ?? null);
}

/** One owner who is due, awake, idle, with a delivered result behind them and
 *  one browser run's worth of evidence: the ONLY shape allowed to send. */
function dueOwner(r: Rig, toolkit = APP_A.slug): void {
  owner(r);
  job(r, "jobdoneaaaaaaa1", "done", NOW - 2 * HOUR);
  signal(r, toolkit);
}

function nudgeOf(r: Rig, toolkit: string, who = OWNER): Record<string, unknown> | undefined {
  return r.d1.rows<Record<string, unknown>>(
    `SELECT * FROM connect_nudges WHERE user_id = ? AND toolkit = ?`, who, toolkit)[0];
}

/** The Worker's own dispatch, plus the waitUntil the runtime would have
 *  awaited. Rejections are captured rather than thrown. */
async function runCron(env: CronEnv, cron = "*/5 * * * *"): Promise<PromiseSettledResult<unknown>[]> {
  const waited: Promise<unknown>[] = [];
  const ctx = { waitUntil: (p: Promise<unknown>) => { waited.push(p); }, passThroughOnException() {} };
  await scheduled(
    { cron, scheduledTime: NOW, noRetry() {} } as unknown as ScheduledController,
    env, ctx as unknown as ExecutionContext,
  );
  return Promise.allSettled(waited);
}

// ===========================================================================
// 1. THE WRITER — the real one, against a stubbed model
// ===========================================================================

await check("THE CONTROL: the writer returns the model's own sentence, and the judge passes it",
  async () => {
    const r = rig();
    const link = fakeLink();
    const write = makeAskWriter(r.env as AskEnv);
    const out = await write(askInput(link));
    assert.equal(typeof out, "string", "the writer did not hand back a message");
    assert.equal(out, goodDraft(link), "the writer altered what the model wrote");
    assert.equal(await judgeDraft(out, askInput(link)), null,
      "the shipped judge refused a draft this suite calls good; the fixture is wrong or the "
        + "judge moved");
    assert.equal(modelCalls().length, 1,
      `a good first answer cost ${modelCalls().length} model calls`);
  });

await check("a model that will not answer sends NOTHING, and never a template", async () => {
  // Three shapes of nobody-answered, and none of them may produce words.
  for (const shape of ["throws", "empty", "no-json"] as const) {
    const r = rig();
    const link = fakeLink();
    if (shape === "throws") socket.modelStatus = 503;
    if (shape === "empty") socket.model = () => "";
    if (shape === "no-json") socket.model = () => "   ";
    const write = makeAskWriter(r.env as AskEnv);
    const err = await write(askInput(link)).then(() => null, (e: Error) => e);
    assert.ok(err instanceof Error, `${shape}: the writer invented a message`);
    assert.equal(sentTexts().length, 0, `${shape}: something was texted`);
  }
});

await check("a stubborn model is asked again with the rule it broke, then refused", async () => {
  const r = rig();
  const link = fakeLink();
  // "permission" is in words.ts's own FORBIDDEN_TERMS, which is the list this
  // writer's prompt is built from.
  const banned = `Connect it and give Anticipy permission to help: ${link}. Up to you.`;
  socket.model = () => JSON.stringify({ message: banned });

  const write = makeAskWriter(r.env as AskEnv);
  const out = await write(askInput(link));

  assert.equal(modelCalls().length, ASK_ATTEMPTS,
    `the writer made ${modelCalls().length} model calls; the bound is ${ASK_ATTEMPTS}`);
  assert.ok(modelCalls().length > 1, "the retry never fired");

  // WHAT THE SECOND REQUEST CARRIED. Asking again identically is pointless; the
  // retry is only worth a subrequest if it NAMES the failure.
  const second = modelCalls()[1]!.body;
  assert.ok(second.includes(banned), "the retry did not show the model the draft it wrote");
  assert.ok(second.includes("permission"), "the retry did not name the word that broke it");

  // AND THE LIMIT DOES NOT MOVE. The second answer is still bad, so it is
  // handed on unrepaired and the shipped judge still refuses it.
  assert.equal(out, banned, "the writer repaired the draft instead of handing it to the judge");
  const refusal = await judgeDraft(out, askInput(link));
  assert.equal(refusal?.cause, "forbidden-word",
    "the judge stopped refusing the register the spec forbids");
});

await check("a failure the MODEL cannot fix is not retried", async () => {
  // A link that is not ours is the CALLER's fault. Asking the model again
  // spends a subrequest to be told the same thing.
  const r = rig();
  const write = makeAskWriter(r.env as AskEnv);
  const notOurs = "https://connect.example.invalid/link/abc";
  await write(askInput(notOurs));
  assert.equal(modelCalls().length, 1,
    `a caller-side refusal cost ${modelCalls().length} model calls`);
  // THE CONTROL: the same writer DOES retry a model-side failure.
  assert.ok(MODEL_FIXABLE.includes("forbidden-word"));
  assert.ok(!MODEL_FIXABLE.includes("bad-link"));
});

await check("the prompt is built from words.ts's own lists, never a second copy", async () => {
  const messages = askPrompt(askInput(fakeLink()));
  const system = String(messages[0]?.content ?? "");
  for (const term of FORBIDDEN_TERMS) {
    assert.ok(system.includes(term),
      `the writer is never told "${term}" is forbidden, so it will write it and be refused`);
  }
  for (const form of STIFF_FORMS) {
    assert.ok(system.includes(form), `the writer is never told to contract "${form}"`);
  }
  // Derived, not typed: a second copy of the list would pass the loop above and
  // then stop matching the judge the day words.ts changes.
  assert.ok(ASK_SOURCE.includes("FORBIDDEN_TERMS.join("),
    "the forbidden list was re-typed into the prompt instead of imported");
  assert.ok(ASK_SOURCE.includes("STIFF_FORMS.join("),
    "the stiff-form list was re-typed into the prompt instead of imported");
});

await check("the prompt carries the moment, the catalog entry and the link, and no app name",
  async () => {
    const messages = askPrompt(askInput(fakeLink(), { meta: APP_B, moment: "laptop_closed" }));
    const user = String(messages[1]?.content ?? "");
    assert.ok(user.includes(MOMENT_SENTENCE.laptop_closed), "the moment did not reach the model");
    assert.ok(user.includes(APP_B.name), "the app's name did not reach the model");
    assert.ok(user.includes(APP_B.slug), "the app's id did not reach the model");
    assert.ok(user.includes(fakeLink()), "the link did not reach the model");
    // NO APP IS HARDCODED: both invented slugs travel the whole path, and
    // neither appears in the shipped source.
    for (const slug of [APP_A.slug, APP_B.slug, APP_A.name, APP_B.name]) {
      assert.ok(!ASK_SOURCE.includes(slug), `ask.ts names ${slug}`);
      assert.ok(!WIRING_SOURCE.includes(slug), `wiring.ts names ${slug}`);
    }
  });

await check("a catalog description carrying a forbidden word is DROPPED, not paraphrased", () => {
  // Measured on the live catalog 2026-09-06: four of eight descriptions carry
  // "integration". Feeding one to the model is asking it to echo the exact word
  // the surface exists to avoid, and then refusing the answer for doing so.
  const dirty = { ...APP_A, description: "The integration your team already uses." };
  const messages = askPrompt(askInput(fakeLink(), { meta: dirty as ToolkitMeta }));
  const user = String(messages[1]?.content ?? "");
  assert.ok(!user.includes("integration"), "a forbidden term reached the writer's prompt");
  // THE CONTROL: a clean description still gets through, because dropping every
  // description would cost the model the one sentence about what the app IS.
  const clean = askPrompt(askInput(fakeLink(), { meta: APP_A }));
  assert.ok(String(clean[1]?.content ?? "").includes(APP_A.description as string),
    "a clean catalog description was dropped too");
});

await check("the ceiling the model is told is the smaller of the two the judge enforces", () => {
  const system = String(askPrompt(askInput(fakeLink()))[0]?.content ?? "");
  assert.ok(system.includes(String(ASK_CEILING_CHARS)),
    "the writer is never told how long one text is");
  assert.equal(ASK_CEILING_CHARS, 306,
    "two GSM-7 segments hold 306 septets; if this moved, the prompt and the judge disagree");
  // COMPUTED, never typed — so raising MAX_ASK_SEGMENTS moves both together.
  assert.ok(ASK_SOURCE.includes("Math.min(MAX_ASK_CHARS_GSM7, ASK_MESSAGE_MAX_CHARS - 1)"),
    "the ceiling was hardcoded, so the prompt can rot into a limit nothing enforces");
});

await check("MOMENT_SENTENCE covers every trigger the contract has, and only those", () => {
  assert.deepEqual(Object.keys(MOMENT_SENTENCE).sort(), [...NUDGE_TRIGGERS].sort(),
    "a moment the policy can score has no sentence, or a sentence names a moment "
      + "the policy cannot score");
  for (const [trigger, sentence] of Object.entries(MOMENT_SENTENCE)) {
    assert.ok(sentence.trim().length > 20, `${trigger} has no real description`);
    // The moment description is fed to the model. A forbidden term in it is the
    // prompt teaching the writer the exact register it is about to be refused for.
    for (const term of FORBIDDEN_TERMS) {
      assert.ok(!new RegExp(`(?<![a-z0-9])${term}(?![a-z0-9])`, "i").test(sentence),
        `the ${trigger} sentence says "${term}"`);
    }
  }
});

await check("parseAsk reads three wrappers and hands back what it cannot read", () => {
  assert.equal(parseAsk(JSON.stringify({ message: "hello" })), "hello");
  assert.equal(parseAsk(JSON.stringify({ text: "hello" })), "hello");
  assert.equal(parseAsk(JSON.stringify("hello")), "hello");
  assert.equal(parseAsk("```json\n" + JSON.stringify({ message: "hello" }) + "\n```"), "hello");
  // Unreadable comes back AS ITSELF, for words.ts to call malformed-reply. It is
  // never turned into a message by this file.
  assert.equal(parseAsk("I'd be happy to help with that."), "I'd be happy to help with that.");
  assert.equal(parseAsk(JSON.stringify({ sentences: ["a"] })), JSON.stringify({ sentences: ["a"] }));
});

await check("the model id is the connect page's, and the two defaults cannot drift", () => {
  assert.equal(DEFAULT_ASK_MODEL, DEFAULT_CONNECT_MODEL,
    "the ask and the connect page disagree about which model this Worker can afford to "
      + "reach; one of them needs a secret nobody set");
  assert.equal(askModel({} as AskEnv), DEFAULT_ASK_MODEL);
  assert.equal(askModel({ ANTICIPY_CONNECT_MODEL: "  google/gemini-3.1-pro-preview " } as AskEnv),
    "google/gemini-3.1-pro-preview", "the override is not read, or is not trimmed");
  assert.equal(askModel({ ANTICIPY_CONNECT_MODEL: "   " } as AskEnv), DEFAULT_ASK_MODEL,
    "a blank override became the model name");
});

await check("a google/ model needs the Gemini key and never silently runs on OpenRouter",
  async () => {
    // src/llm.ts rule 8. "Whichever key exists" once made a DeepSeek request run
    // on Gemini while the audit row still said DeepSeek.
    const r = rig({ ANTICIPY_CONNECT_MODEL: "google/gemini-3.1-pro-preview" });
    const write = makeAskWriter(r.env as AskEnv);
    const err = await write(askInput(fakeLink())).then(() => null, (e: Error) => e);
    assert.match(String(err?.message), /GEMINI_API_KEY/);
    assert.equal(modelCalls().length, 0, "a Gemini model was sent to OpenRouter");
  });

// ---------------------------------------------------------------------------
// THE THIRD INPUT — the spec's "user's own phrasing history"
// ---------------------------------------------------------------------------

await check("the owner's own phrasing reaches the prompt when it is supplied", () => {
  const lines = ["shove that in my notes thing", "chuck it on the board"];
  const withHistory = { ...askInput(fakeLink()), phrasing: lines } as AskInput;
  assert.deepEqual(phrasingOf(withHistory), lines);
  const user = String(askPrompt(withHistory, phrasingOf(withHistory))[1]?.content ?? "");
  for (const line of lines) assert.ok(user.includes(line), `"${line}" did not reach the model`);

  // The other landing spot, so whichever seam grows the field is honoured.
  const onEvidence = {
    ...askInput(fakeLink()),
    evidence: { ...askInput(fakeLink()).evidence, phrasing: lines },
  } as AskInput;
  assert.deepEqual(phrasingOf(onEvidence), lines);

  // THE CONTROL: absent, the prompt simply has no such section — it is never
  // filled with an invented voice.
  const bare = String(askPrompt(askInput(fakeLink()))[1]?.content ?? "");
  assert.ok(!bare.includes("HOW THEY TALK"), "an empty phrasing history drew a section anyway");
  assert.deepEqual(phrasingOf(askInput(fakeLink())), []);
  assert.deepEqual(phrasingOf(null), []);
  assert.deepEqual(phrasingOf({ phrasing: ["", "  ", 7] } as unknown as AskInput), []);
});

await check("the seam now CARRIES the phrasing history, in all three files", () => {
  // THE GAP CLOSED, 2026-09-06, and this is the regression pin that replaced
  // the expiry check that tracked it. The three edits the old check named have
  // landed: words.ts declares the field, nudge.ts carries it from the moment
  // into the evidence, and wiring.ts fills it from this owner's own rows.
  //
  // ANCHORED ON A LITERAL THAT OCCURS EXACTLY ONCE PER FILE, and the count is
  // asserted, because a scan that silently matches nothing reads as a pass.
  const declared = "phrasing?: readonly string[];";
  assert.equal(WORDS_SOURCE.split(declared).length - 1, 1,
    "words.ts must declare `phrasing` on AskEvidence exactly once");
  assert.equal(NUDGE_SOURCE.split(declared).length - 1, 1,
    "nudge.ts must declare `phrasing` on NudgeMoment exactly once");
  assert.equal(NUDGE_SOURCE.split("phrasing: moment.phrasing").length - 1, 1,
    "nudge.ts must carry the moment's phrasing into the evidence exactly once");
  // The owner filter is the whole privacy model of this field: one person's
  // words may never write another person's text.
  assert.equal(WIRING_SOURCE.split('"owner_ref" = ?1 AND "speaker" = \'owner\'').length - 1, 1,
    "wiring.ts must read the phrasing from THIS owner's own spoken rows");
  assert.equal(WIRING_SOURCE.split("phrasing,").length - 1, 1,
    "nudgeMomentFor must return the phrasing it read");
});

// ===========================================================================
// 2. THE WIRING — the six ports, against the real schema
// ===========================================================================

await check("a Worker missing a piece of config asks nobody, and names the piece", () => {
  const cases: [Record<string, unknown>, RegExp][] = [
    [{ DB: undefined }, /DB binding/],
    [{ COMPOSIO_API_KEY: "" }, /COMPOSIO_API_KEY/],
    [{ OPENROUTER_API_KEY: "" }, /OPENROUTER_API_KEY/],
    [{ ANTICIPY_CONNECT_MODEL: "google/x" }, /GEMINI_API_KEY/],
    [{ SENDBLUE_API_KEY_ID: "", SENDBLUE_API_SECRET_KEY: "" }, /messaging provider/],
  ];
  for (const [over, named] of cases) {
    LOGS.length = 0;
    const r = rig(over);
    assert.equal(nudgeDeps(r.env), null, `${JSON.stringify(over)} was wired anyway`);
    assert.ok(LOGS.some((l) => named.test(l)),
      `the log did not name what is missing for ${JSON.stringify(over)}: ${LOGS.join(" | ")}`);
  }
  // THE CONTROL: a fully configured Worker wires all six ports.
  const good = nudgeDeps(rig().env);
  assert.ok(good, "a correctly configured Worker was not wired");
  for (const port of ["store", "catalog", "write", "moment", "phone", "due"]) {
    assert.ok((good as unknown as Record<string, unknown>)[port], `port ${port} is missing`);
  }
});

await check("the owner-local hour is read from their own timezone, or refused", () => {
  // A REAL ZONE AT A FIXED INSTANT, so this check measures the clock and not
  // the hour the suite happened to run at.
  assert.equal(ownerLocalHour("UTC", FIXED), 15);
  assert.equal(ownerLocalHour("Asia/Kolkata", FIXED), 21);      // +05:30, a half-hour offset
  assert.equal(ownerLocalHour("Pacific/Auckland", FIXED), 3);   // the next day, +12
  assert.equal(ownerLocalHour("America/Los_Angeles", FIXED), 8);
  // Midnight is 0 and never 24 — an off-by-a-day-boundary here is an hour of
  // somebody's sleep every night for as long as nobody checks.
  assert.equal(ownerLocalHour("UTC", Date.UTC(2026, 8, 4, 0, 0, 0)), 0);
  assert.equal(ownerLocalHour("UTC", Date.UTC(2026, 8, 4, 23, 59, 59)), 23);
  // And the two zones the rest of this suite leans on really do say what it
  // claims they say.
  assert.equal(ownerLocalHour(AWAKE_TZ, NOW), AWAKE_HOUR);
  assert.equal(ownerLocalHour(ASLEEP_TZ, NOW), ASLEEP_HOUR);
  // NO TIMEZONE, NO ASK. UTC is how somebody in Auckland gets a connect link at
  // 2am from a server that thought it was lunchtime.
  assert.equal(ownerLocalHour("", FIXED), null);
  assert.equal(ownerLocalHour("Not/AZone", FIXED), null);
  assert.equal(ownerLocalHour(AWAKE_TZ, NaN), null);
});

await check("the moment is read from this owner's own rows", async () => {
  const r = rig();
  dueOwner(r);
  const moment = nudgeMomentFor(r.env);
  const m = await moment(OWNER as never, APP_A.slug, "in_task", NOW);
  assert.ok(m, "a well-evidenced owner produced no moment");
  assert.equal(m.localHour, AWAKE_HOUR);
  assert.equal(m.taskInFlight, false);
  assert.equal(m.resultDelivered, true);
  assert.equal(m.tasksThatWouldHaveUsedIt, 1);
  assert.equal(m.alias, null);
  // NEVER INVENTED. Neither is recorded anywhere this can read, and a writer
  // handed "that took 40 seconds" is a writer handed a fact nobody measured.
  assert.equal(m.whatHappened, undefined);
  assert.equal(m.browserMs, undefined);
});

await check("an owner with no timezone gets no moment, and therefore no ask", async () => {
  const r = rig();
  owner(r, OWNER, TO, null);
  job(r, "jobdoneaaaaaaa1", "done");
  signal(r, APP_A.slug);
  assert.equal(await nudgeMomentFor(r.env)(OWNER as never, APP_A.slug, "in_task", NOW), null);
  // And an owner who does not exist at all.
  assert.equal(await nudgeMomentFor(r.env)(OTHER as never, APP_A.slug, "in_task", NOW), null);
});

await check("a job still running is mid-step, and an unknown status counts as running",
  async () => {
    for (const status of ["queued", "running", "awaiting_confirm", "needs_user", "handling",
      "some_state_nobody_has_written_yet"]) {
      const r = rig();
      dueOwner(r);
      job(r, "jobopenaaaaaaa1", status);
      const m = await nudgeMomentFor(r.env)(OWNER as never, APP_A.slug, "in_task", NOW);
      assert.equal(m?.taskInFlight, true, `status ${status} did not read as in flight`);
      assert.equal(m?.resultDelivered, false,
        `status ${status}: an ask would have landed mid-errand`);
    }
    // THE CONTROL: every status this file calls finished reads as finished.
    for (const status of FINISHED_JOB_STATUS) {
      const r = rig();
      owner(r);
      signal(r, APP_A.slug);
      job(r, "jobendedaaaaaa1", status);
      const m = await nudgeMomentFor(r.env)(OWNER as never, APP_A.slug, "in_task", NOW);
      assert.equal(m?.taskInFlight, false, `status ${status} read as in flight`);
      assert.equal(m?.resultDelivered, true, `status ${status} produced no delivered result`);
    }
  });

await check("an owner Anticipy has finished nothing for lately is not asked", async () => {
  // `resultDelivered` needs BOTH halves: nothing of theirs is unfinished, AND
  // something of theirs actually finished inside the cap's own window. An owner
  // with no jobs at all, or only ancient ones, has had no result for this ask
  // to come after.
  const r = rig();
  owner(r);
  signal(r, APP_A.slug);
  const empty = await nudgeMomentFor(r.env)(OWNER as never, APP_A.slug, "in_task", NOW);
  assert.equal(empty?.resultDelivered, false, "an owner with no jobs at all read as delivered");

  job(r, "jobancientaaaa1", "done", NOW - (GLOBAL_ASK_INTERVAL_DAYS + 2) * DAY);
  const stale = await nudgeMomentFor(r.env)(OWNER as never, APP_A.slug, "in_task", NOW);
  assert.equal(stale?.resultDelivered, false, "a job from last fortnight read as a fresh result");

  // THE CONTROL, one row different.
  job(r, "jobfreshaaaaaa1", "done", NOW - HOUR);
  const fresh = await nudgeMomentFor(r.env)(OWNER as never, APP_A.slug, "in_task", NOW);
  assert.equal(fresh?.resultDelivered, true);
});

await check("both spellings of a timestamp are read, because this tree holds both", async () => {
  // src/pb/wire.ts pbNow writes "2026-09-06 12:00:00.000Z" (a SPACE) and
  // Date#toISOString writes "2026-09-06T12:00:00.000Z" (a T), and this database
  // holds rows from both. A recency window that answered differently for the
  // two would make "has Anticipy finished anything for them lately" depend on
  // which writer made the row — invisible, and wrong for half the table. This
  // drives one job in each spelling through the real query.
  for (const stamp of [
    new Date(NOW - HOUR).toISOString(),
    new Date(NOW - HOUR).toISOString().replace("T", " "),
  ]) {
    const r = rig();
    owner(r);
    signal(r, APP_A.slug);
    r.d1.db.prepare(
      `INSERT INTO jobs (id, created, updated, goal, status, owner_ref)
       VALUES ('jobspellingaa1',?,?,'a small errand','done',?)`,
    ).run(stamp, stamp, OWNER);
    const m = await nudgeMomentFor(r.env)(OWNER as never, APP_A.slug, "in_task", NOW);
    assert.equal(m?.resultDelivered, true,
      `a job stamped ${JSON.stringify(stamp)} was not read as a delivered result`);
  }
});

await check("the evidence count is this app's own, and a tie on accounts is not guessed",
  async () => {
    const r = rig();
    dueOwner(r);
    signal(r, APP_A.slug, "said");
    signal(r, APP_B.slug, "observer");        // another app, must not be counted
    signal(r, APP_A.slug, "mx");              // not a moment, must not be counted
    const m = await nudgeMomentFor(r.env)(OWNER as never, APP_A.slug, "in_task", NOW);
    assert.equal(m?.tasksThatWouldHaveUsedIt, 2,
      "the count is not this owner's moment-bearing evidence for THIS app");

    // ONE alias is an answer; two is ambiguity, and the spec answers ambiguity
    // by ASKING ("work or personal for this?"), never by picking.
    const one = rig();
    dueOwner(one);
    signal(one, APP_A.slug, "said", OWNER, 2, "work");
    assert.equal(
      (await nudgeMomentFor(one.env)(OWNER as never, APP_A.slug, "in_task", NOW))?.alias, "work");
    signal(one, APP_A.slug, "observer", OWNER, 2, "personal");
    assert.equal(
      (await nudgeMomentFor(one.env)(OWNER as never, APP_A.slug, "in_task", NOW))?.alias, null,
      "two accounts were resolved by picking one");
  });

await check("an alias D1 would refuse is refused here too, not passed on", async () => {
  // NOT REACHABLE THROUGH THE SCHEMA, and that is the point of testing it at
  // the binding. `app_usage_signals.alias` CHECKs ('', 'work', 'personal'), so
  // the only way a junk alias arrives is a CHECK somebody dropped, a restored
  // backup, or a hand-edited row — and by then the value would ride into
  // `connect_links.alias`, fail THAT check, and surface as "could not mint a
  // link" rather than as a bad alias. The binding is faked here so the guard
  // itself is measured.
  // THE FAKE MUST ANSWER THE QUERY THE CODE ACTUALLY RUNS. On 2026-09-06 the
  // evidence read stopped saying `AND "weight" > 0` in SQL and started filtering
  // in JS with signals.ts's own `decayedWeight` against `ALIVE_WEIGHT_FLOOR`, so
  // it now selects "alias", "source", "weight", "last_seen_at". A fake that
  // returns only `alias` hands the filter `Number(undefined)` — NaN — and every
  // comparison against NaN is false, so the row falls out and the CONTROL below
  // failed with "work was dropped": the test was measuring its own stale fake,
  // not the guard it names. The row is fresh (`last_seen_at: NOW`) and carries a
  // real source, so only the ALIAS is under test here.
  const rows: { alias: unknown; source: string; weight: number; last_seen_at: number }[] =
    [{ alias: "Work ", source: "said", weight: 0.8, last_seen_at: NOW }];
  const DB = {
    prepare(sql: string) {
      return {
        bind() {
          return {
            async first() {
              return sql.includes("owner_profile")
                ? { owner_phone: TO, profile_phone: "", timezone: AWAKE_TZ }
                : { unfinished: 0, finished_recently: 1 };
            },
            async all() { return { results: rows }; },
          };
        },
      };
    },
  };
  const env = { ...rig().env, DB } as unknown as NudgeWiringEnv;
  assert.equal((await nudgeMomentFor(env)(OWNER as never, APP_A.slug, "in_task", NOW))?.alias, null,
    "an alias the database would refuse was passed on to the link mint");
  // THE CONTROL: the two the contract really has still come through.
  for (const good of ["work", "personal"]) {
    rows[0] = { alias: good, source: "said", weight: 0.8, last_seen_at: NOW };
    assert.equal(
      (await nudgeMomentFor(env)(OWNER as never, APP_A.slug, "in_task", NOW))?.alias, good,
      `${good} was dropped`);
  }
});

await check("the text goes to this owner's own number, and never to a guess", async () => {
  const r = rig();
  owner(r, OWNER, TO);
  assert.equal(await ownerPhone(r.env)(OWNER as never), TO);

  // The account column is empty and the profile's is not: a real shape in this
  // database, and taking only one column makes the ask unreachable for whichever
  // half of the table stored it elsewhere.
  const p = rig();
  p.d1.db.prepare(
    `INSERT INTO owners (id, created, updated, email, emailVisibility, verified,
       password, tokenKey, phone, legacy_uuid) VALUES (?,?,?,?,0,0,'',?,'','')`,
  ).run(OTHER, PB_NOW, PB_NOW, `${OTHER}@x.invalid`, "k2");
  p.d1.db.prepare(
    `INSERT INTO owner_profile (id, created, updated, owner_id, phone, name, first_name,
       last_name, email, birthday, facts, owner_ref, timezone)
     VALUES (?,?,?,?,?,'','','','','','',?,?)`,
  ).run("profotheraaaa11", PB_NOW, PB_NOW, OTHER, OTHER_TO, OTHER, AWAKE_TZ);
  assert.equal(await ownerPhone(p.env)(OTHER as never), OTHER_TO);

  // Nobody's number is a hold, never another row's.
  const none = rig();
  owner(none, OWNER, "", AWAKE_TZ);
  assert.equal(await ownerPhone(none.env)(OWNER as never), null);
  assert.equal(await ownerPhone(none.env)(OTHER as never), null);
});

// ===========================================================================
// 3. THE ASK GOING OUT — the whole chain, only fetch faked
// ===========================================================================

await check("THE CONTROL: a due owner gets exactly one text and one row flip", async () => {
  const r = rig();
  dueOwner(r);

  const report = await connectNudgeSweep(r.env as NudgeEnv, nudgeWiring(r.env as NudgeEnv));
  assert.equal(report.wired, true, "the production wiring refused to build");
  assert.equal(report.considered, 1, `${report.considered} candidates, expected 1`);
  assert.equal(report.sent, 1,
    `nobody was asked: quiet=${report.quiet} refused=${report.refused} skipped=${report.skipped}`);

  const texts = sentTexts();
  assert.equal(texts.length, 1, `${texts.length} texts left the building`);
  const text = texts[0]!;
  assert.ok(text.includes(APP_A.name), "the text does not name the app");
  assert.ok(new RegExp(`${CONNECT_URL_BASE.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}/[A-Za-z0-9_-]{${TOKEN_CHARS}}`)
    .test(text), "the text carries no connect link of ours");

  // AND THE ROW. An ask nobody wrote down is an ask that gets sent again on the
  // next sweep.
  const row = nudgeOf(r, APP_A.slug);
  assert.equal(row?.state, "asked");
  assert.equal(row?.trigger, "in_task");
  assert.equal(row?.channel, "sms");
  assert.ok(Number(row?.sent_at) > 0, "the ask was not stamped");

  // AND THE LINK IS BOUND TO THIS OWNER AND THIS APP, single use, ten minutes.
  const links = r.d1.rows<Record<string, unknown>>(`SELECT * FROM connect_links`);
  assert.equal(links.length, 1);
  assert.equal(links[0]!.user_id, OWNER);
  assert.equal(links[0]!.toolkit, APP_A.slug);
  assert.equal(links[0]!.used_at, null);
  // THE RAW TOKEN IS NEVER WRITTEN DOWN: the row holds sha256 in hex.
  assert.equal(String(links[0]!.token_handle).length, 64);
  assert.ok(!text.includes(String(links[0]!.token_handle)), "the handle was texted");
});

await check("the 7-day cap holds ACROSS DIFFERENT APPS", async () => {
  const r = rig();
  dueOwner(r, APP_A.slug);
  signal(r, APP_B.slug, "observer", OWNER, 9);   // heavier, so it would win the pick
  // They were asked about a DIFFERENT app two days ago. A per-app counter
  // cannot see that; the cap is global by construction.
  nudgeRow(r, "someotherapp", { state: "asked", sent_at: NOW - 2 * DAY });

  const report = await connectNudgeSweep(r.env as NudgeEnv, nudgeWiring(r.env as NudgeEnv));
  assert.equal(sentTexts().length, 0,
    "a second app got its own text inside the 7-day window");
  assert.equal(report.sent, 0);

  // THE CONTROL: the same rows with the previous ask outside the window.
  const ok = rig();
  dueOwner(ok, APP_A.slug);
  nudgeRow(ok, "someotherapp",
    { state: "asked", sent_at: NOW - (GLOBAL_ASK_INTERVAL_DAYS + 1) * DAY });
  await connectNudgeSweep(ok.env as NudgeEnv, nudgeWiring(ok.env as NudgeEnv));
  assert.equal(sentTexts().length, 1, "an owner past the window was never asked again");
});

await check("nothing is sent mid-step, and nothing before the result", async () => {
  for (const status of ["running", "queued"]) {
    const r = rig();
    dueOwner(r);
    job(r, "jobopenaaaaaaa1", status);
    const report = await connectNudgeSweep(r.env as NudgeEnv, nudgeWiring(r.env as NudgeEnv));
    assert.equal(sentTexts().length, 0, `an ask landed while a job was ${status}`);
    assert.equal(report.quiet, 1, "the sweep did not record a policy hold");
    assert.equal(nudgeOf(r, APP_A.slug), undefined, "a nudge row was written for a held ask");
  }
  // NO RESULT BEHIND THEM AT ALL: nothing has finished, so there is nothing for
  // the ask to come after.
  const fresh = rig();
  owner(fresh);
  signal(fresh, APP_A.slug);
  await connectNudgeSweep(fresh.env as NudgeEnv, nudgeWiring(fresh.env as NudgeEnv));
  assert.equal(sentTexts().length, 0, "an ask arrived before this owner had ever had a result");
});

await check("quiet hours are the OWNER's, not the server's", async () => {
  const r = rig();
  owner(r, OWNER, TO, ASLEEP_TZ);              // 02:13 local at NOW
  job(r, "jobdoneaaaaaaa1", "done", NOW - 2 * HOUR);
  signal(r, APP_A.slug);
  await connectNudgeSweep(r.env as NudgeEnv, nudgeWiring(r.env as NudgeEnv));
  assert.equal(sentTexts().length, 0, "a connect link was sent at 2am somebody's time");
});

await check("a model that refuses to write it sends NOTHING, and never a template", async () => {
  // The single most important behaviour in this file. A broken draft spends the
  // one interruption this product gets per owner per week, for nothing.
  for (const how of ["down", "silent", "unusable"] as const) {
    const r = rig();
    dueOwner(r);
    if (how === "down") socket.modelStatus = 500;
    if (how === "silent") socket.model = () => "";
    if (how === "unusable") socket.model = () => JSON.stringify({ message: "Sure, happy to help." });

    const report = await connectNudgeSweep(r.env as NudgeEnv, nudgeWiring(r.env as NudgeEnv));
    assert.equal(sentTexts().length, 0, `${how}: a message went out anyway`);
    assert.equal(report.refused, 1, `${how}: the sweep did not record a refusal`);
    assert.equal(report.sent, 0);
    // The ask was never RECORDED either, so a later moment can still use it.
    assert.equal(nudgeOf(r, APP_A.slug), undefined,
      `${how}: an ask nobody received was written down as sent`);
  }
});

await check("a catalog that cannot name the app sends nothing and mints no link", async () => {
  const r = rig();
  dueOwner(r);
  socket.catalogFails = true;
  await connectNudgeSweep(r.env as NudgeEnv, nudgeWiring(r.env as NudgeEnv));
  assert.equal(sentTexts().length, 0, "a text was sent about an app we could not name");
  assert.equal(r.d1.rows(`SELECT * FROM connect_links`).length, 0,
    "a link was minted that nobody could ever be given");
});

await check("the sweep is idempotent across two ticks", async () => {
  const r = rig();
  dueOwner(r);
  await connectNudgeSweep(r.env as NudgeEnv, nudgeWiring(r.env as NudgeEnv));
  assert.equal(sentTexts().length, 1, "the first tick did not ask");
  const first = nudgeOf(r, APP_A.slug);

  const second = await connectNudgeSweep(r.env as NudgeEnv, nudgeWiring(r.env as NudgeEnv));
  assert.equal(sentTexts().length, 1, "the second tick asked the same person again");
  assert.equal(second.considered, 0,
    "the same owner was still a candidate five minutes after being asked");
  assert.deepEqual(nudgeOf(r, APP_A.slug), first, "the second tick rewrote the ask record");
  assert.equal(r.d1.rows(`SELECT * FROM connect_links`).length, 1,
    "a second link was minted for an ask that was never sent");
});

await check("one owner gets at most one ask per tick however many apps are due", async () => {
  const r = rig();
  dueOwner(r, APP_A.slug);
  signal(r, APP_B.slug, "observer", OWNER, 9);
  const report = await connectNudgeSweep(r.env as NudgeEnv, nudgeWiring(r.env as NudgeEnv));
  assert.equal(sentTexts().length, 1, `${sentTexts().length} texts in one tick`);
  assert.ok(report.sent <= MAX_ASKS_PER_SWEEP);
});

await check("an owner with no number is a hold, and their link is not minted", async () => {
  const r = rig();
  owner(r, OWNER, "", AWAKE_TZ);
  job(r, "jobdoneaaaaaaa1", "done", NOW - 2 * HOUR);
  signal(r, APP_A.slug);
  await connectNudgeSweep(r.env as NudgeEnv, nudgeWiring(r.env as NudgeEnv));
  assert.equal(sentTexts().length, 0);
  assert.equal(r.d1.rows(`SELECT * FROM connect_links`).length, 0,
    "a link was minted for somebody with nowhere to send it");
});

await check("a send that fails hands the week back rather than spending it", async () => {
  const r = rig();
  dueOwner(r);
  socket.sendStatus = 502;
  const report = await connectNudgeSweep(r.env as NudgeEnv, nudgeWiring(r.env as NudgeEnv));
  assert.equal(report.sent, 0);
  const row = nudgeOf(r, APP_A.slug);
  assert.equal(row?.state, "never_asked",
    "an owner who never received anything was charged a week of silence");
  assert.equal(row?.sent_at, null, "an ask nobody got was stamped as sent");
});

await check("a raw connect token never reaches a log line", async () => {
  const r = rig();
  LOGS.length = 0;
  dueOwner(r);
  await connectNudgeSweep(r.env as NudgeEnv, nudgeWiring(r.env as NudgeEnv));
  const token = sentTexts()[0]!.match(new RegExp(`/c/([A-Za-z0-9_-]{${TOKEN_CHARS}})`))?.[1];
  assert.ok(token, "no token was minted, so this check measured nothing");
  for (const line of LOGS) {
    assert.ok(!line.includes(token!),
      "a raw connect token reached a log line — a support transcript or a `wrangler tail` "
        + "is then a live link for whoever reads it");
  }
});

// ===========================================================================
// 4. THE CRON — the tick production actually runs
// ===========================================================================

await check("wrangler.jsonc registers the five-minute tick this whole feature rides on", () => {
  // HARNESS-LAWS law 3's precondition. Everything above is repo-green and NONE
  // of it runs on api.anticipy.ai unless production dispatches this schedule.
  // It was absent for a week on purpose — PocketBase's own sweep was still
  // running — and that ended when Railway was stopped on 2026-09-05.
  const crons = /"crons"\s*:\s*\[([^\]]*)\]/.exec(WRANGLER)?.[1] ?? "";
  assert.ok(/"\*\/5 \* \* \* \*"/.test(crons),
    "wrangler.jsonc does not register \"*/5 * * * *\", so connectNudgeSweep is dispatched by "
      + "code production never invokes and nobody is ever asked anything");
  assert.ok(/"17 4 \* \* \*"/.test(crons), "the nightly prune was dropped");
  // The comment above it must not still say the trigger is off.
  assert.equal(/DELIBERATELY OFF UNTIL CUTOVER/.test(WRANGLER), false,
    "wrangler.jsonc still says the tick is off while it is on");
});

await check("src/cron.ts routes that exact string, and installs the wiring", () => {
  assert.ok(CRON_SOURCE.includes('case "*/5 * * * *":'),
    "the schedule wrangler registers is not the string src/cron.ts dispatches on");
  assert.ok(CRON_SOURCE.includes("installNudgeWiring(nudgeWiring);"),
    "nothing installs the nudge wiring, so the sweep asks nobody — the exact failure this "
      + "task existed to fix");
  // Two independent legs: one chained promise would let the optional half take
  // the reminder half down.
  const tick = CRON_SOURCE.slice(CRON_SOURCE.indexOf('case "*/5 * * * *"'));
  const body = tick.slice(0, tick.indexOf("return;"));
  assert.equal((body.match(/ctx\.waitUntil\(/g) ?? []).length, 2);
});

await check("THE WHOLE CHAIN: scheduled() on the real tick texts a due owner", async () => {
  // The strongest check in this file. Nothing is injected: `scheduled` reads
  // the wiring src/cron.ts installed at module load, which builds the real
  // store, the real catalog client, the real writer and the real `due` query.
  const r = rig();
  dueOwner(r);
  const settled = await runCron(r.env);
  assert.deepEqual(settled.map((s) => s.status), ["fulfilled", "fulfilled"],
    "a rejected waitUntil marks the invocation failed, and a re-run re-sends reminders");
  assert.equal(sentTexts().length, 1,
    `the production tick sent ${sentTexts().length} texts; the wiring is not reached`);
  assert.equal(nudgeOf(r, APP_A.slug)?.state, "asked");
});

await check("the same tick on a Worker with no secrets asks nobody, loudly", async () => {
  LOGS.length = 0;
  const r = rig({ COMPOSIO_API_KEY: "", OPENROUTER_API_KEY: "" });
  dueOwner(r);
  const settled = await runCron(r.env);
  assert.deepEqual(settled.map((s) => s.status), ["fulfilled", "fulfilled"]);
  assert.equal(sentTexts().length, 0);
  assert.ok(LOGS.some((l) => /no wiring installed/.test(l)),
    "an unwired sweep must name the missing wiring in the log");
});

await check("the nightly trigger does NOT carry the connect ask", async () => {
  // An ask that lands at 04:17 UTC is the 3am text the policy exists to prevent.
  const r = rig();
  dueOwner(r);
  await runCron(r.env, "17 4 * * *");
  assert.equal(sentTexts().length, 0, "the connect ask was hung off the nightly trigger");
});

// ===========================================================================
// 5. THE SUITE ITSELF
// ===========================================================================

await check("NO APP IS HARDCODED, in the two files this task wrote", () => {
  // The rule is structural, not a promise: names, logos and slugs come from the
  // catalog at run time, so a new app in the catalog is a new app in Anticipy
  // with zero code. A single real app name in either of these files is the
  // first line of the per-app treadmill the spec exists to avoid.
  //
  // The NUDGE HALF of wiring.ts only. The connect half above it records a
  // measurement about Gmail's eleven scopes in a COMMENT, which is a finding
  // written down (law 4) and not a branch on an app.
  const marker = "// THE NUDGE HALF";
  assert.ok(WIRING_SOURCE.includes(marker), "the nudge half is no longer marked");
  const nudgeHalf = WIRING_SOURCE.slice(WIRING_SOURCE.indexOf(marker));
  const realApps = [
    "gmail", "googlecalendar", "google_drive", "notion", "slack", "outlook",
    "linear", "hubspot", "shopify", "github", "zoom", "teams", "dropbox", "asana",
  ];
  for (const app of realApps) {
    const named = new RegExp(`(?<![a-z0-9_])${app}(?![a-z0-9_])`, "i");
    assert.equal(named.test(ASK_SOURCE), false, `src/connections/ask.ts names ${app}`);
    assert.equal(named.test(nudgeHalf), false,
      `the nudge half of src/connections/wiring.ts names ${app}`);
  }
  // THE CONTROL: the check can see a name when there is one, so a typo in the
  // list above cannot make this pass over anything.
  assert.ok(/(?<![a-z0-9_])gmail(?![a-z0-9_])/i.test(WIRING_SOURCE),
    "the matcher found nothing in a file that demonstrably contains one of these words, so "
      + "it is measuring nothing");
});

await check("this suite runs in CI", () => {
  // Five suites were written and left out of package.json in one week; each time
  // hundreds of checks silently did not run.
  assert.ok(PACKAGE_JSON.includes("test/connections-ask.test.ts"),
    "connections-ask is not in the test script, so none of the above runs on anybody's machine "
      + "but the author's");
});

// ---------------------------------------------------------------------------
console.log = realLog;
console.log(`connections-ask: ${passes} checks passed, ${failures} failed`);
if (failures > 0) process.exit(1);

// ===========================================================================
// MUTATIONS RUN AGAINST src/connections/ask.ts, THE NUDGE HALF OF
// src/connections/wiring.ts, src/cron.ts AND wrangler.jsonc, 2026-09-06.
//
// Every one is anchored on a string that occurs EXACTLY ONCE in the file it
// mutates (the script refuses to run otherwise, because a regex that silently
// fails to match produces a false "it is tested" reading — that mistake was
// made twice on 2026-09-05). The check each one killed is named.
//
//  1. ask.ts   `return draft;` inside the MODEL_FIXABLE guard -> `return
//     goodEnough(draft)` (a house template).  RED: "a model that refuses to
//     write it sends NOTHING" and "a stubborn model is asked again".
//  2. ask.ts   `ASK_ATTEMPTS = 2` -> `1`.  RED: "a stubborn model is asked
//     again with the rule it broke".
//  3. ask.ts   `if (!MODEL_FIXABLE.includes(refusal.cause))` -> `if (false)`.
//     RED: "a failure the MODEL cannot fix is not retried".
//  4. ask.ts   `judgeDraft` -> a local always-null.  RED: "a stubborn model is
//     asked again" (the retry stops firing).
//  5. ask.ts   `FORBIDDEN_TERMS.join(", ")` -> `"authorize"`.  RED: "the prompt
//     is built from words.ts's own lists".
//  6. ask.ts   `STIFF_FORMS.join(", ")` -> `""`.  RED: same check.
//  7. ask.ts   `Math.min(MAX_ASK_CHARS_GSM7, ASK_MESSAGE_MAX_CHARS - 1)` ->
//     `320`.  RED: "the ceiling the model is told is the smaller of the two".
//  8. ask.ts   drop the `forbiddenTermIn(meta.description) === null` clause.
//     RED: "a catalog description carrying a forbidden word is DROPPED".
//  9. ask.ts   `MOMENT_SENTENCE.repeated_use` deleted.  RED (compile, then)
//     "MOMENT_SENTENCE covers every trigger the contract has".
// 10. ask.ts   `parseAsk` returns `""` instead of `text` on a parse failure.
//     RED: "parseAsk reads three wrappers and hands back what it cannot read".
// 11. ask.ts   `DEFAULT_ASK_MODEL` -> "google/gemini-3.1-pro-preview".  RED:
//     "the model id is the connect page's, and the two defaults cannot drift".
// 12. ask.ts   `model.startsWith("google/")` -> `false`.  RED: "a google/ model
//     needs the Gemini key".
// 13. ask.ts   `phrasingOf` returns `[]` always.  RED: "the owner's own
//     phrasing reaches the prompt when it is supplied".
// 14. wiring.ts  `ownerLocalHour` returns `new Date(now).getUTCHours()` when
//     the timezone is blank.  RED: "the owner-local hour is read from their own
//     timezone, or refused" and "quiet hours are the OWNER's".
// 15. wiring.ts  `FINISHED_JOB_STATUS` gains "queued".  RED: "a job still
//     running is mid-step".
// 16. wiring.ts  `resultDelivered: unfinished === 0` (the second half dropped).
//     RED: "an owner Anticipy has finished nothing for lately is not asked".
// 17. wiring.ts  `tasksThatWouldHaveUsedIt: 1` (a constant).  RED: "the
//     evidence count is this app's own".
// 18. wiring.ts  `aliases.size === 1` -> `>= 1`.  RED: "a tie on accounts is
//     not guessed".
// 25. wiring.ts  `ACCOUNT_ALIASES.includes(only)` -> `only !== ""`.  RED: "an
//     alias D1 would refuse is refused here too".
// 19. wiring.ts  `ownerPhone` falls back to any row's phone.  RED: "the text
//     goes to this owner's own number".
// 20. wiring.ts  `missingNudgeConfig` returns null always.  RED: "a Worker
//     missing a piece of config asks nobody, and names the piece".
// 21. wiring.ts  the messaging-provider clause removed.  RED: same check.
// 22. cron.ts    `installNudgeWiring(nudgeWiring);` deleted.  RED: "src/cron.ts
//     routes that exact string, and installs the wiring" and "THE WHOLE CHAIN".
// 23. wrangler.jsonc  "*/5 * * * *" removed.  RED: "wrangler.jsonc registers
//     the five-minute tick".
// 24. cron.ts    `case "*/5 * * * *"` -> `case "*/6 * * * *"`.  RED: "src/cron.ts
//     routes that exact string" and "THE WHOLE CHAIN".
//
// ALL 25 DIED, run 2026-09-06 from the runner in this session's scratchpad. Two
// anchors were rejected on the first pass and re-written rather than loosened:
// #20's first form matched `connectDeps` as well (two occurrences, so it was
// not run), and #13's first form was a syntax error rather than a behaviour
// change, which kills a suite without measuring it.
// ===========================================================================
