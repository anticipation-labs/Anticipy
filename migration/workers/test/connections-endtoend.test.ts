/**
 * test/connections-endtoend.test.ts — THE WHOLE CHAIN, ON ONE DATABASE.
 *
 * Four agents built four parts of the Connections spec and every one of them
 * finished with the same sentence in its report: it is repo-green and nothing
 * calls it. This suite is the answer to that. It does not test a module. It
 * asks ONE question, six times over:
 *
 *     a signal is recorded
 *       -> the sweep finds that owner due
 *         -> the writer writes an ask
 *           -> words.ts passes it
 *             -> a text goes out
 *               -> the row flips to `asked`
 *
 * WHAT IS REAL HERE. The schema is migration/d1/schema.sql, loaded verbatim
 * into node:sqlite. The store, the signal recorder, the due query, the moment
 * reader, the ask writer, the words judge, the nudge state machine, the link
 * mint, the messaging client, the SMS route, the text twin and `scheduled()`
 * itself are the SHIPPED modules, imported and run. Exactly two things are
 * faked, and both are outside this Worker: `globalThis.fetch` (the vendor's
 * catalog, the model, the messaging provider) and the clock the fixtures are
 * seeded relative to.
 *
 * NOTHING IS INJECTED INTO THE CHAIN. The headline check drives
 * `scheduled("*\/5 * * * *")` with a bare env and nothing else, so what it
 * measures is the wiring a deployed Worker would run: if `installNudgeWiring`
 * loses its caller, if the cron switch loses the case, if `nudgeDeps` refuses
 * on a missing secret, this suite goes red and names it.
 *
 * ── WHY THE HOPS ARE NAMED ONE AT A TIME ─────────────────────────────────
 *
 * "No text was sent" is true of a broken chain and of a working one on a quiet
 * night, and the difference is the whole of what this suite is for. So
 * `whereItStopped` walks the six hops in order against the same database and
 * returns the FIRST one that produced nothing, in that hop's own words. A
 * failure here says "hop 2 — nobody was due", never "expected 1, got 0".
 *
 * This is also why every hop below asserts something POSITIVE about the state
 * it produced rather than only about the state it consumed: a chain that is
 * green because every hop was skipped is the failure this suite exists to make
 * impossible.
 *
 * ── HARNESS-LAWS ─────────────────────────────────────────────────────────
 *
 * LAW 1: this is a deterministic gate, which is one of the three places
 * pattern-matching is legitimate — and even so, no rule here decides what any
 * human's words MEAN. The model is stubbed by which of OUR OWN prompts it was
 * handed (a string this repo wrote, matched against itself), never by reading
 * an owner's sentence.
 *
 * NO APP IS HARDCODED. Every scenario runs on two invented slugs under the
 * reserved `.example` TLD that appear in no catalog and in no source file.
 *
 * LAW 3: this suite is repo-green and says so. It proves the chain is
 * CONNECTED; it cannot prove production runs it. That is
 * overnight/is_connect_live.py leg 11's job, and section 6 pins the two so
 * they cannot drift.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { record, recordObservedHost, sweepConnectedSignals } from "../src/connections/signals.ts";
import { dueCandidates } from "../src/connections/due.ts";
import {
  connectNudgeSweep,
  nudgeWiringInstalled,
  ASK_MESSAGE_MAX_CHARS,
} from "../src/connections/nudge.ts";
import {
  handleInboundText,
  nudgeDeps,
  nudgeMomentFor,
  runTextCommandPlan,
  textCommandDeps,
  textReplySentences,
  TEXT_CATALOG_LIMIT,
  type NudgeWiringEnv,
} from "../src/connections/wiring.ts";
import { planTextCommand } from "../src/connections/text_commands.ts";
import { askMessage } from "../src/connections/nudge.ts";
import { FORBIDDEN_TERMS, forbiddenTermIn } from "../src/connections/words.ts";
import { createD1Store, ownerId } from "../src/connections/store.ts";
import { CONNECT_URL_BASE, TOKEN_CHARS } from "../src/routes/connect.ts";
import { COMPOSIO_BASE_URL, resetConnectionsProvider } from "../src/connections/provider.ts";
import { SENDBLUE_BASE } from "../src/messaging.ts";
import { sendblueInbound } from "../src/routes/sendblue.ts";
import { scheduled, type CronEnv } from "../src/cron.ts";
import { FakeD1, asD1 } from "./fake-d1.ts";
import type { ToolkitMeta } from "../../../spike/two-hands/src/connections/contract.ts";

const here = dirname(fileURLToPath(import.meta.url));
const PACKAGE_JSON = readFileSync(join(here, "..", "package.json"), "utf8");
const WRANGLER = readFileSync(join(here, "..", "wrangler.jsonc"), "utf8");
const CRON_SOURCE = readFileSync(join(here, "..", "src", "cron.ts"), "utf8");
const SMS_SOURCE = readFileSync(join(here, "..", "src", "routes", "sms.ts"), "utf8");
const SENDBLUE_SOURCE = readFileSync(join(here, "..", "src", "routes", "sendblue.ts"), "utf8");
const INDEX_SOURCE = readFileSync(join(here, "..", "src", "index.ts"), "utf8");
const GATE_SOURCE = readFileSync(
  join(here, "..", "..", "..", "overnight", "is_connect_live.py"), "utf8");

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

/** The real clock, for the reason connections-ask.test.ts gives: the shipped
 *  wiring leaves `NudgeDeps.now` unset, and a fixture pinned to a literal puts
 *  every seeded row outside the seven-day windows the policy reads. */
const NOW = Date.now();
const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;
const PB_NOW = new Date(NOW - DAY).toISOString().replace("T", " ");

/** 15 lowercase alphanumerics, which is what the schema's own CHECK requires
 *  and what D1 mints. A shorter one is refused by the database, not by us. */
const OWNER_ID = "ownerchainaa111";
const SECOND_OWNER = "ownerchainbb222";
const PHONE = "+15557770001";
const SECOND_PHONE = "+15557770002";
const OUR_NUMBER = "+15550009999";

/**
 * TWO INVENTED APPS, on the reserved `.example` TLD (RFC 2606), so a scan of
 * any shipped source for either name finds nothing and a scan of this file
 * finds only fiction. `appUrl` is what the observer door matches a host
 * against — through the catalog's OWN field, which is the lookup signals.ts
 * argues for and not a domain list of ours.
 */
const APP: ToolkitMeta = {
  slug: "zzhalcyon",
  name: "Halcyon",
  logo: null,
  description: "Where a team keeps its notes.",
  appUrl: "https://halcyon.example",
  scopes: ["notes.read"],
};
const OTHER_APP: ToolkitMeta = {
  slug: "zzmarrowfat",
  name: "Marrowfat",
  logo: null,
  description: null,
  appUrl: "https://marrowfat.example",
  scopes: ["things.read"],
};
const CATALOG = [APP, OTHER_APP];

/** A fixed-offset zone in which the owner's local hour right now is `want`.
 *  Computed, never named: quiet hours are owner-local and a hardcoded zone
 *  passes all morning and fails every evening. */
function zoneWhereLocalHourIs(want: number): string {
  const utcHour = new Date(NOW).getUTCHours();
  const offset = ((want - utcHour) % 24 + 24) % 24;
  return offset <= 14 ? `Etc/GMT-${offset}` : `Etc/GMT+${24 - offset}`;
}
const AWAKE_TZ = zoneWhereLocalHourIs(14);
const ASLEEP_TZ = zoneWhereLocalHourIs(3);

// ---------------------------------------------------------------------------
// THE ONE FAKE: globalThis.fetch. Three hosts; everything else is this repo.
// ---------------------------------------------------------------------------

interface Call { url: string; body: string }

interface Socket {
  calls: Call[];
  catalog: Map<string, ToolkitMeta>;
  /** What the vendor's own search answers, whatever it is asked. */
  searchAnswers: ToolkitMeta[];
  catalogFails: boolean;
  modelStatus: number;
  sendStatus: number;
  /** What the model answers, chosen by which of OUR prompts it was handed. */
  ask: (body: string) => string;
  command: (body: string) => string;
  match: (body: string) => string;
  disconnectRevokeUnavailable: boolean;
  /**
   * Run AT REVOKE TIME by the vendor stub, and its answer kept. It is the only
   * way to observe the ORDER of "revoke then delete" from outside: both calls
   * succeed either way, and a row deleted first leaves a live token at the far
   * end with nothing left pointing at it — invisible unless something looks
   * while the revoke is in flight. Mutation 11 survived until this existed.
   */
  rowProbe: (() => boolean) | null;
  revokeSawOurRow: boolean | null;
  /** What the VENDOR believes this owner holds. Separate from the `connections`
   *  table on purpose: `disconnect` proves ownership against the vendor's list
   *  before it touches anything, and a stub that answered from our own table
   *  could never show that guard working. */
  vendorAccounts: { id: string; user: string; toolkit: string }[];
}

const socket: Socket = {
  calls: [],
  catalog: new Map([[APP.slug, APP], [OTHER_APP.slug, OTHER_APP]]),
  searchAnswers: CATALOG,
  catalogFails: false,
  modelStatus: 200,
  sendStatus: 200,
  ask: (body) => JSON.stringify({ message: goodDraft(linkIn(body), nameIn(body)) }),
  command: () => JSON.stringify({ kind: "none" }),
  match: () => JSON.stringify({ kind: "unclear" }),
  disconnectRevokeUnavailable: false,
  rowProbe: null,
  revokeSawOurRow: null,
  vendorAccounts: [],
};

function resetSocket(): void {
  socket.calls = [];
  socket.catalog = new Map([[APP.slug, APP], [OTHER_APP.slug, OTHER_APP]]);
  socket.searchAnswers = CATALOG;
  socket.catalogFails = false;
  socket.modelStatus = 200;
  socket.sendStatus = 200;
  socket.ask = (body) => JSON.stringify({ message: goodDraft(linkIn(body), nameIn(body)) });
  socket.command = () => JSON.stringify({ kind: "none" });
  socket.match = () => JSON.stringify({ kind: "unclear" });
  socket.disconnectRevokeUnavailable = false;
  socket.rowProbe = null;
  socket.revokeSawOurRow = null;
  socket.vendorAccounts = [];
}

/**
 * A draft in this product's voice carrying our link exactly once.
 *
 * ALL ASCII, because one curly apostrophe forces the whole message to UCS-2 and
 * over the two-segment ceiling — which is the containment working, and not what
 * this suite is measuring.
 */
function goodDraft(link: string, name = APP.name): string {
  return `That one went through your browser just now. Connect your ${name} and I can do `
    + `it straight away next time: ${link}. Up to you - the browser works fine too.`;
}

/**
 * The app name out of the prompt the writer was handed — `ask.ts` renders it as
 * "Name, use exactly this spelling: X". The stub reads it back so a draft is
 * about the app the chain actually asked about; a stub that always wrote one
 * app's name would let a two-owner check pass while every ask named the same
 * app. That mistake was made on the first run of this suite.
 */
function nameIn(body: string): string {
  const m = /Name, use exactly this spelling: ([^\\"\n]+)/.exec(body);
  return m ? m[1].trim() : APP.name;
}

/** Our own sentence with our own link lifted out, which is how words.ts scans
 *  one: this deployment's base is `api.anticipy.ai` and `api` is a forbidden
 *  term, so a scan of the raw text reports our own hostname. */
function saidWords(text: string): string {
  const link = linkIn(text);
  return link === "" ? text : text.split(link).join(" ");
}

/** Our connect link out of whatever the writer was sent. */
function linkIn(body: string): string {
  const m = new RegExp(
    `${CONNECT_URL_BASE.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}/[A-Za-z0-9_-]{${TOKEN_CHARS}}`,
  ).exec(body);
  return m ? m[0] : "";
}

/**
 * WHICH PROMPT IS THIS? Matched against strings THIS REPO WROTE into its own
 * system prompts, never against anything a person said. Swapping every one of
 * them for a random integer would leave the stub's behaviour identical, which
 * is the test of whether a list is doing meaning's job.
 */
function promptKind(body: string): "ask" | "command" | "match" | "sentences" {
  if (body.includes("list_connected")) return "command";
  if (body.includes("THE APPS, id first")) return "match";
  if (body.includes("THE MOMENT")) return "ask";
  return "sentences";
}

globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = String((input as { url?: string })?.url ?? input);
  const body = String(init?.body ?? "");
  socket.calls.push({ url, body });
  const json = (status: number, value: unknown): Response =>
    new Response(JSON.stringify(value), { status, headers: { "content-type": "application/json" } });

  if (url.startsWith(COMPOSIO_BASE_URL)) {
    if (socket.catalogFails) return json(500, { error: "the vendor is down" });
    const row = (meta: ToolkitMeta) => ({
      slug: meta.slug,
      name: meta.name,
      meta: { logo: meta.logo, description: meta.description, app_url: meta.appUrl },
      scopes: meta.scopes,
    });
    if (url.includes("/toolkits?search=")) {
      return json(200, { items: socket.searchAnswers.map(row) });
    }
    if (url.includes("/connected_accounts")) {
      // THE THREE CALLS `disconnect` MAKES, in the order it makes them:
      //   GET  /connected_accounts?user_ids=X   the ownership proof
      //   POST /connected_accounts/{id}/revoke  kill the token at the far end
      //   DELETE /connected_accounts/{id}       and only then our bookkeeping
      // Each row echoes `user_id`, because provider.ts fails CLOSED on a row
      // that names no owner — the guard that stops a stranger's mailbox being
      // laundered into somebody's connections table.
      if (url.includes("?user_ids=")) {
        const asked = decodeURIComponent(url.split("?user_ids=")[1] ?? "");
        return json(200, {
          items: socket.vendorAccounts
            .filter((a) => a.user === asked)
            .map((a) => ({ id: a.id, user_id: a.user, toolkit: { slug: a.toolkit },
                           status: "ACTIVE" })),
        });
      }
      if (url.endsWith("/revoke")) {
        if (socket.rowProbe) socket.revokeSawOurRow = socket.rowProbe();
        // 409 is the measured shape for "this account is not in a revocable
        // state"; provider.ts turns it into `revokeUnavailable`, and the reply
        // must then not claim a revoke that did not happen.
        return socket.disconnectRevokeUnavailable
          ? json(409, { error: "not in a revocable state" })
          : json(200, { status: "success" });
      }
      return json(200, { status: "deleted" });
    }
    const slug = decodeURIComponent(url.split("/toolkits/")[1]?.split("?")[0] ?? "");
    const found = socket.catalog.get(slug);
    return found ? json(200, row(found)) : json(404, { error: "no such toolkit" });
  }
  if (url.startsWith(SENDBLUE_BASE)) {
    if (socket.sendStatus !== 200) return json(socket.sendStatus, { error_code: 400 });
    return json(200, { message_handle: "mh-e2e", status: "QUEUED" });
  }
  if (socket.modelStatus !== 200) return json(socket.modelStatus, { error: { message: "upstream" } });
  const kind = promptKind(body);
  const content = kind === "command" ? socket.command(body)
    : kind === "match" ? socket.match(body)
    : socket.ask(body);
  return json(200, { choices: [{ message: { content } }] });
}) as typeof fetch;

// The vendor adapter binds globalThis.fetch when it is CONSTRUCTED and the
// isolate caches one adapter, so a stub installed after that is never reached.
resetConnectionsProvider();

function sentTexts(): string[] {
  return socket.calls
    .filter((c) => c.url.startsWith(SENDBLUE_BASE))
    .map((c) => {
      try { return String((JSON.parse(c.body) as { content?: unknown }).content ?? ""); }
      catch { return ""; }
    });
}

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
    SENDBLUE_FROM_NUMBER: OUR_NUMBER,
    SENDBLUE_WEBHOOK_SECRET: "sb-webhook-secret",
    ...over,
  } as unknown as NudgeWiringEnv & CronEnv;
  resetSocket();
  LOGS.length = 0;
  return { d1, env };
}

function seedOwner(
  r: Rig, id = OWNER_ID, phone = PHONE, timezone: string | null = AWAKE_TZ,
): void {
  r.d1.db.prepare(
    `INSERT INTO owners (id, created, updated, email, emailVisibility, verified,
       password, tokenKey, phone, legacy_uuid) VALUES (?,?,?,?,0,0,'',?,?,'')`,
  ).run(id, PB_NOW, PB_NOW, `${id}@anticipy-test.invalid`, `key-${id}`, phone);
  if (timezone !== null) {
    r.d1.db.prepare(
      `INSERT INTO owner_profile (id, created, updated, owner_id, phone, name, first_name,
         last_name, email, birthday, facts, owner_ref, timezone)
       VALUES (?,?,?,?,?,'','','','','','',?,?)`,
    ).run(`prof${id}`.slice(0, 15), PB_NOW, PB_NOW, id, phone, id, timezone);
  }
}

function seedJob(r: Rig, id: string, status: string, at = NOW - 2 * HOUR, who = OWNER_ID): void {
  r.d1.db.prepare(
    `INSERT INTO jobs (id, created, updated, goal, status, owner_ref)
     VALUES (?,?,?,'a small errand',?,?)`,
  ).run(id, new Date(at).toISOString(), new Date(at).toISOString(), status, who);
}

function seedConnection(
  r: Rig, id: string, toolkit: string, who = OWNER_ID,
  status = "connected", alias = "",
): void {
  r.d1.db.prepare(
    `INSERT INTO connections (connected_account_id, user_id, toolkit, alias, status,
       writes_enabled, last_used_at) VALUES (?,?,?,?,?,0,NULL)`,
  ).run(id, who, toolkit, alias, status);
  socket.vendorAccounts.push({ id, user: who, toolkit });
}

/**
 * One line this owner said TO US, for the phrasing history — either a text they
 * sent this number (`sms_reply`, which is what src/pb/sender.ts lands) or a
 * spoken line the sense layer marked as addressed to the assistant.
 */
function seedSaidLine(
  r: Rig, id: string, text: string, at = NOW - HOUR, who = OWNER_ID,
  kind = "sms_reply", addressee = "",
): void {
  r.d1.db.prepare(
    `INSERT INTO events (id, created, updated, device_id, kind, text, speaker,
       addressee, owner_ref) VALUES (?,?,?,'phone',?,?,'owner',?,?)`,
  ).run(id, new Date(at).toISOString(), new Date(at).toISOString(), kind, text,
        addressee, who);
}

function nudgeOf(r: Rig, toolkit: string, who = OWNER_ID): Record<string, unknown> | undefined {
  return r.d1.rows<Record<string, unknown>>(
    `SELECT * FROM connect_nudges WHERE user_id = ? AND toolkit = ?`, who, toolkit)[0];
}

function signalRows(r: Rig, who = OWNER_ID): Record<string, unknown>[] {
  return r.d1.rows<Record<string, unknown>>(
    `SELECT * FROM app_usage_signals WHERE user_id = ?`, who);
}

/** The Worker's own dispatch plus the waitUntil the runtime would have awaited.
 *  Rejections are captured rather than thrown, exactly as Cloudflare does. */
async function runCron(env: CronEnv, cron = "*/5 * * * *"): Promise<PromiseSettledResult<unknown>[]> {
  const waited: Promise<unknown>[] = [];
  const ctx = { waitUntil: (p: Promise<unknown>) => { waited.push(p); }, passThroughOnException() {} };
  await scheduled(
    { cron, scheduledTime: NOW, noRetry() {} } as unknown as ScheduledController,
    env, ctx as unknown as ExecutionContext,
  );
  return Promise.allSettled(waited);
}

/**
 * ONE OWNER IN THE ONLY SHAPE THE POLICY WILL SEND TO, built through the
 * SHIPPED signal recorder rather than by seeding a row.
 *
 * That distinction is the whole point of hop 1: `INSERT INTO app_usage_signals`
 * proves the query reads a table, and proves nothing about whether anything in
 * this product can ever put a row in it. `recordObservedHost` is the door
 * signals.ts declares, it goes through `hostToToolkit` against the catalog's
 * own `meta.app_url`, through the band and the decay, through the store's
 * compare-and-set, and it is the one due.ts turns into the in-task moment.
 */
async function seedDueOwner(r: Rig, host = "halcyon.example"): Promise<unknown> {
  seedOwner(r);
  seedJob(r, "jobdonechain01", "done");
  return recordObservedHost(createD1Store(r.env), OWNER_ID, host, CATALOG, NOW - HOUR);
}

// ---------------------------------------------------------------------------
// WHERE DID IT STOP? — the diagnostic the whole suite is built around
// ---------------------------------------------------------------------------

/**
 * Walk the six hops against a database and name the FIRST one that produced
 * nothing, in that hop's own words.
 *
 * WHY THIS EXISTS. "No text was sent" is the true state of a broken chain AND
 * of a working one on a quiet night, and every failure this feature has had so
 * far looked like the second while being the first: `installConnectWiring` with
 * zero callers answered 503 to every token there had ever been; the ears went
 * deaf for thirty hours beside a green board. An assertion that reads
 * `assert.equal(texts.length, 1)` reports "0 !== 1" and sends the next reader
 * to the wrong module.
 *
 * It returns `null` when every hop is reachable — i.e. when a text went out and
 * the row flipped.
 */
async function whereItStopped(r: Rig): Promise<string | null> {
  // THE SUCCESS TEST FIRST, and it has to be: once an ask has gone out, the
  // seven-day global cap correctly excludes that owner from `due()`, so
  // re-walking the hops on a WORKING chain reports "nobody is due" — the very
  // sentence this function exists to stop being ambiguous.
  const already = sentTexts();
  if (already.length > 0) {
    const rows = r.d1.rows<Record<string, unknown>>(
      `SELECT * FROM connect_nudges WHERE state = 'asked'`);
    if (rows.length > 0) return null;
    return "hop 6 — A TEXT WENT OUT AND NO ROW FLIPPED. That is the worst state there "
      + "is: the next sweep asks again, and the seven-day cap is kept by this row.";
  }

  if (!nudgeWiringInstalled()) {
    return "hop 0 — NOTHING IS WIRED. `installNudgeWiring` has no caller, so "
      + "`connectNudgeSweep` asks nobody on every tick. src/cron.ts is where it goes.";
  }
  if (nudgeDeps(r.env) === null) {
    return "hop 0 — THE WIRING REFUSED this Worker's configuration: "
      + LOGS.filter((l) => l.includes("connect nudge wiring")).join(" | ");
  }
  const signals = signalRows(r);
  if (signals.length === 0) {
    return "hop 1 — NO SIGNAL WAS RECORDED. app_usage_signals is empty for this owner, "
      + "so there is no evidence anybody could be asked about. That is production's "
      + "state today: six ingest doors, one of them wired.";
  }
  let candidates;
  try {
    candidates = await dueCandidates(r.env, NOW);
  } catch (err) {
    return `hop 2 — THE DUE QUERY THREW: ${String((err as Error)?.message ?? err)}`;
  }
  if (candidates.length === 0) {
    const moments = signals.filter((s) => s.source === "observer" || s.source === "said");
    return "hop 2 — NOBODY IS DUE. "
      + `${signals.length} signal row(s) exist and ${moments.length} of them name a moment `
      + "(only `observer` and `said` do; `connected`, `asked`, `mx` and `link` add weight "
      + "and cannot name the moment an ask opens with).";
  }
  const moment = await nudgeMomentFor(r.env)(
    ownerId(OWNER_ID), candidates[0].toolkit, candidates[0].trigger, NOW);
  if (moment === null) {
    return "hop 3 — THE MOMENT COULD NOT BE ESTABLISHED. Every field of it is a floor "
      + "input: no timezone on the owner's profile, or no owner row at all, and nobody "
      + "is texted.";
  }
  const texts = sentTexts();
  if (texts.length === 0) {
    return "hop 4/5 — NO TEXT LEFT THE BUILDING. The candidate was found and the moment "
      + "was established, so the break is the writer, the words judge, the link mint or "
      + "the send: "
      + LOGS.filter((l) => l.includes("connect ask")).join(" | ");
  }
  const row = nudgeOf(r, candidates[0].toolkit);
  if (!row || row.state !== "asked") {
    return "hop 6 — A TEXT WENT OUT AND THE ROW DID NOT FLIP. That is the worst state "
      + "there is: the next sweep asks again, and the seven-day cap is kept by this row.";
  }
  return null;
}

// ===========================================================================
// 1. THE CHAIN — one owner, six hops, nothing injected
// ===========================================================================

await check("THE CHAIN: a recorded signal becomes a text, and the row flips to asked",
  async () => {
    const r = rig();
    const stored = await seedDueOwner(r);

    // HOP 1, asserted positively: the door wrote a row, and it wrote the row
    // the DATABASE's own CHECK constraints accept.
    assert.ok(stored, "recordObservedHost recorded nothing — the host matched no catalog row");
    const rows = signalRows(r);
    assert.equal(rows.length, 1, "the observer door did not write exactly one evidence row");
    assert.equal(rows[0].toolkit, APP.slug,
      "the host was matched to the wrong app, through the catalog's own app_url");
    assert.equal(rows[0].source, "observer");
    assert.ok(Number(rows[0].weight) > 0, "the row was written with no weight");

    // HOPS 2-6, through the Worker's own scheduled handler with NOTHING
    // injected: the real cron switch, the real installed wiring, the real deps.
    const settled = await runCron(r.env);
    for (const s of settled) {
      assert.equal(s.status, "fulfilled",
        `a cron leg rejected: ${String((s as PromiseRejectedResult).reason)}`);
    }

    const stopped = await whereItStopped(r);
    assert.equal(stopped, null, String(stopped));

    const texts = sentTexts();
    assert.equal(texts.length, 1, `exactly one text should have gone out; ${texts.length} did`);
    assert.ok(texts[0].includes(CONNECT_URL_BASE),
      "the text carried no connect link, so there is nothing for the person to do");
    assert.ok(texts[0].includes(APP.name),
      "the text did not name the app, so it reads as a message from a stranger");
    assert.ok(texts[0].length <= ASK_MESSAGE_MAX_CHARS,
      `the text was ${texts[0].length} characters, over the spec's ${ASK_MESSAGE_MAX_CHARS}`);

    const row = nudgeOf(r, APP.slug);
    assert.ok(row, "no connect_nudges row exists, so the seven-day cap is kept by nothing");
    assert.equal(row!.state, "asked");
    assert.equal(row!.trigger, "in_task",
      "the ask was recorded under a moment other than the one the evidence named");
    assert.ok(Number(row!.sent_at) > 0, "the ask has no sent_at, so the cap cannot be read");

    // AND THE LINK IS REDEEMABLE: a row in connect_links, bound to this owner
    // and this app, unspent. A text carrying a link nobody can redeem is worse
    // than no text.
    const links = r.d1.rows<Record<string, unknown>>(
      `SELECT * FROM connect_links WHERE user_id = ?`, OWNER_ID);
    assert.equal(links.length, 1, "the ask did not mint exactly one link");
    assert.equal(links[0].toolkit, APP.slug);
    assert.equal(links[0].used_at, null, "the minted link was already spent");
  });

await check("THE CHAIN: the ask is judged by the SHIPPED words.ts, not by the writer",
  async () => {
    // The writer's self-check calls `askMessage`, the same function
    // `sendConnectAsk` uses, so this drives that judge directly over the text
    // the chain actually produced and asserts it agrees.
    const r = rig();
    await seedDueOwner(r);
    await runCron(r.env);
    const text = sentTexts()[0];
    assert.ok(text, "no text to judge");
    const verdict = await askMessage(
      "in_task", APP,
      { link: linkIn(text), resultDelivered: true, tasksThatWouldHaveUsedIt: 1 },
      () => text,
      { base: CONNECT_URL_BASE },
    );
    assert.equal(verdict.ok, true,
      `words.ts refuses the message the chain sent: ${JSON.stringify(verdict)}`);
    assert.equal(forbiddenTermIn(saidWords(text)), null,
      "the text carried a term FORBIDDEN_TERMS names");
  });

await check("THE CHAIN: one owner, one ask, however many ticks", async () => {
  // The seven-day global cap is the whole reason the row is written before the
  // send. Two ticks five minutes apart is the shape production actually runs.
  const r = rig();
  await seedDueOwner(r);
  await runCron(r.env);
  await runCron(r.env);
  await runCron(r.env);
  assert.equal(sentTexts().length, 1,
    `three ticks sent ${sentTexts().length} texts; the cap is one per owner per seven days`);
});

// ===========================================================================
// 2. THE CONTROLS — each hop broken in turn, and NAMED
// ===========================================================================

await check("CONTROL hop 1: no signal, and the diagnostic says which hop", async () => {
  const r = rig();
  seedOwner(r);
  seedJob(r, "jobdonechain02", "done");
  await runCron(r.env);
  assert.equal(sentTexts().length, 0, "an owner with no evidence was texted anyway");
  const stopped = await whereItStopped(r);
  assert.ok(stopped?.startsWith("hop 1"), `expected hop 1, got: ${stopped}`);
  assert.ok(stopped!.includes("app_usage_signals is empty"));
});

await check("CONTROL hop 2: evidence that is not a MOMENT is not an ask", async () => {
  // The `connected` sweep fills this table and cannot by itself produce an ask.
  // due.ts selects `observer` and `said` only, and this is the check that says
  // so out loud — a full table read as a working feature is the exact mistake
  // signals.ts's own header warns about.
  const r = rig();
  seedOwner(r);
  seedJob(r, "jobdonechain03", "done");
  await record(createD1Store(r.env), {
    user_id: OWNER_ID, toolkit: APP.slug, source: "connected", last_seen_at: NOW - HOUR,
  });
  assert.equal(signalRows(r).length, 1, "the certain door wrote nothing");
  await runCron(r.env);
  assert.equal(sentTexts().length, 0, "a `connected` row produced an ask");
  const stopped = await whereItStopped(r);
  assert.ok(stopped?.startsWith("hop 2"), `expected hop 2, got: ${stopped}`);
  assert.ok(stopped!.includes("0 of them name a moment"),
    `the diagnostic should count the moments: ${stopped}`);
});

await check("CONTROL hop 2: an owner who already connected the app is not asked", async () => {
  const r = rig();
  await seedDueOwner(r);
  seedConnection(r, "ca_chain_1", APP.slug);
  await runCron(r.env);
  assert.equal(sentTexts().length, 0, "somebody was asked to connect an app they hold");
  const stopped = await whereItStopped(r);
  assert.ok(stopped?.startsWith("hop 2"), `expected hop 2, got: ${stopped}`);
});

await check("CONTROL hop 3: no timezone is no ask, and it is named", async () => {
  const r = rig();
  seedOwner(r, OWNER_ID, PHONE, null);
  seedJob(r, "jobdonechain04", "done");
  await recordObservedHost(createD1Store(r.env), OWNER_ID, "halcyon.example", CATALOG, NOW - HOUR);
  await runCron(r.env);
  assert.equal(sentTexts().length, 0,
    "an owner whose local hour is unknown was texted; UTC is how Auckland gets 2am");
  const stopped = await whereItStopped(r);
  assert.ok(stopped?.startsWith("hop 3"), `expected hop 3, got: ${stopped}`);
});

await check("CONTROL hop 3: quiet hours hold the ask", async () => {
  const r = rig();
  seedOwner(r, OWNER_ID, PHONE, ASLEEP_TZ);
  seedJob(r, "jobdonechain05", "done");
  await recordObservedHost(createD1Store(r.env), OWNER_ID, "halcyon.example", CATALOG, NOW - HOUR);
  await runCron(r.env);
  assert.equal(sentTexts().length, 0, "a connect link went out at 3am owner-local");
  assert.equal(nudgeOf(r, APP.slug), undefined, "a held ask wrote a row anyway");
});

await check("CONTROL hop 3: mid-errand holds the ask", async () => {
  const r = rig();
  await seedDueOwner(r);
  seedJob(r, "jobrunchain01", "running", NOW - 10 * 60 * 1000);
  await runCron(r.env);
  assert.equal(sentTexts().length, 0, "somebody was interrupted mid-step");
});

await check("CONTROL hop 4: a refused draft sends nothing and flips nothing", async () => {
  const r = rig();
  await seedDueOwner(r);
  // A draft with a second link in it. words.ts refuses `extra-link`, the writer
  // retries once, and the retry gets the same thing.
  socket.ask = (body) => JSON.stringify({
    message: `Connect your ${APP.name}: ${linkIn(body)} or ${linkIn(body)}`,
  });
  await runCron(r.env);
  assert.equal(sentTexts().length, 0, "a draft the judge refused was sent anyway");
  const row = nudgeOf(r, APP.slug);
  assert.ok(!row || row.state !== "asked",
    "a refused draft flipped the row to asked, so this owner is now silenced for a week "
      + "over a message they never received");
});

await check("CONTROL hop 5: a dead messaging provider does not lose the ask silently",
  async () => {
    const r = rig();
    await seedDueOwner(r);
    socket.sendStatus = 502;
    await runCron(r.env);
    // `sentTexts` counts what was HANDED to the provider, so the attempt is
    // visible; what must not happen is the failure passing for a send.
    assert.equal(sentTexts().length, 1, "the ask was never even attempted");
    assert.ok(LOGS.some((l) => /connect ask|messaging/.test(l)),
      "nothing in the log says the send failed, so the outage is invisible");
    assert.ok(LOGS.some((l) => l.includes("not sent") || l.includes("send")),
      `the log does not report a failed send: ${LOGS.join(" | ")}`);
  });

await check("CONTROL hop 0: a Worker missing one secret asks nobody, and says which",
  async () => {
    for (const [over, named] of [
      [{ COMPOSIO_API_KEY: "" }, "COMPOSIO_API_KEY"],
      [{ OPENROUTER_API_KEY: "" }, "OPENROUTER_API_KEY"],
      [{ SENDBLUE_API_KEY_ID: "", SENDBLUE_API_SECRET_KEY: "" }, "messaging provider"],
    ] as [Record<string, unknown>, string][]) {
      const r = rig(over);
      await seedDueOwner(r);
      await runCron(r.env);
      assert.equal(sentTexts().length, 0, `${named} was unset and a text went out anyway`);
      assert.ok(LOGS.some((l) => l.includes(named)),
        `nothing in the log names ${named}, so an operator cannot tell why it is quiet`);
      const stopped = await whereItStopped(r);
      assert.ok(stopped?.startsWith("hop 0"), `expected hop 0, got: ${stopped}`);
    }
  });

await check("CONTROL: two owners, and neither one's ask is written from the other's data",
  async () => {
    const r = rig();
    await seedDueOwner(r);
    seedOwner(r, SECOND_OWNER, SECOND_PHONE, AWAKE_TZ);
    seedJob(r, "jobdonechain06", "done", NOW - 2 * HOUR, SECOND_OWNER);
    await recordObservedHost(
      createD1Store(r.env), SECOND_OWNER, "marrowfat.example", CATALOG, NOW - HOUR);
    await runCron(r.env);
    const texts = sentTexts();
    assert.equal(texts.length, 2, `both owners were due; ${texts.length} text(s) went out`);
    const forFirst = texts.find((t) => t.includes(APP.name));
    const forSecond = texts.find((t) => t.includes(OTHER_APP.name));
    assert.ok(forFirst && forSecond, "the two owners were not asked about their own apps");
    assert.ok(!forFirst!.includes(OTHER_APP.name) && !forSecond!.includes(APP.name),
      "one owner's text named the other owner's app");
    assert.equal(nudgeOf(r, APP.slug, OWNER_ID)!.state, "asked");
    assert.equal(nudgeOf(r, OTHER_APP.slug, SECOND_OWNER)!.state, "asked");
  });

// ===========================================================================
// 3. THE NIGHTLY LEG — connections become evidence
// ===========================================================================

await check("THE NIGHTLY LEG: `17 4 * * *` turns a connected account into evidence",
  async () => {
    const r = rig();
    seedOwner(r);
    seedConnection(r, "ca_chain_night_1", APP.slug, OWNER_ID, "connected", "work");
    assert.equal(signalRows(r).length, 0, "the fixture started with evidence");

    await runCron(r.env, "17 4 * * *");

    const rows = signalRows(r);
    assert.equal(rows.length, 1, "the nightly sweep wrote no evidence row");
    assert.equal(rows[0].source, "connected");
    assert.equal(rows[0].toolkit, APP.slug);
    assert.equal(rows[0].alias, "work",
      "the alias did not ride into the row, so an ask could not name the account");
    assert.equal(sentTexts().length, 0,
      "the nightly leg sent a text; it writes evidence and must interrupt nobody");
  });

await check("THE NIGHTLY LEG: it is idempotent, and it is not the five-minute leg",
  async () => {
    const r = rig();
    seedOwner(r);
    seedConnection(r, "ca_chain_night_2", APP.slug);
    await runCron(r.env, "17 4 * * *");
    const first = signalRows(r)[0];
    await runCron(r.env, "17 4 * * *");
    await runCron(r.env, "17 4 * * *");
    const rows = signalRows(r);
    assert.equal(rows.length, 1, "three nightly sweeps wrote three rows");
    assert.equal(Number(rows[0].weight), Number(first.weight),
      "a certainty accumulated across sweeps, so the sweep's own schedule became the "
        + "strongest signal this owner has");
  });

await check("THE NIGHTLY LEG is registered, and so is the one the ask lives on", () => {
  // wrangler.jsonc is the routing key: src/cron.ts dispatches on the literal
  // string, so a schedule missing here is a leg dispatched by code production
  // never invokes. Both are asserted because BOTH are now load-bearing.
  const crons = /"crons"\s*:\s*\[([^\]]*)\]/.exec(WRANGLER)?.[1] ?? "";
  assert.ok(crons.includes('"*/5 * * * *"'),
    "wrangler.jsonc does not register the five-minute tick, so the connect ask is "
      + "dispatched by code production never invokes");
  assert.ok(crons.includes('"17 4 * * *"'),
    "wrangler.jsonc does not register the nightly tick");
  assert.equal(CRON_SOURCE.split("await sweepConnectedSignals(env, Date.now())").length - 1, 1,
    "src/cron.ts must call sweepConnectedSignals exactly once, on the nightly leg");
  const nightly = CRON_SOURCE.slice(CRON_SOURCE.indexOf('case "17 4 * * *"'));
  assert.ok(nightly.slice(0, nightly.indexOf("return;")).includes("connectedSignals(env)"),
    "the evidence sweep is not on the nightly leg — an ask at 04:17 UTC is the 3am text "
      + "the policy exists to prevent, and this is the leg that must NOT send");
  assert.ok(CRON_SOURCE.includes("installNudgeWiring(nudgeWiring)"),
    "nothing installs the nudge wiring, so connectNudgeSweep asks nobody");
});

// ===========================================================================
// 4. THE TEXT TWIN — an inbound message reaches somebody who understands it
// ===========================================================================

/** One inbound Sendblue message, through the SHIPPED route. */
async function inbound(r: Rig, text: string, from = PHONE, handle = "sb-1"): Promise<Response> {
  const waited: Promise<unknown>[] = [];
  const ctx = { waitUntil: (p: Promise<unknown>) => { waited.push(p); }, passThroughOnException() {} };
  const res = await sendblueInbound(
    new Request("https://api.anticipy.ai/sms/sendblue", {
      method: "POST",
      headers: { "content-type": "application/json", "sb-signing-secret": "sb-webhook-secret" },
      body: JSON.stringify({
        is_outbound: false, status: "RECEIVED", message_handle: handle,
        from_number: from, to_number: OUR_NUMBER, sendblue_number: OUR_NUMBER,
        content: text,
      }),
    }),
    r.env as never,
    ctx as unknown as ExecutionContext,
  );
  await Promise.allSettled(waited);
  return res;
}

await check("THE TEXT TWIN: an inbound message reaches the planner at all", async () => {
  const r = rig();
  seedOwner(r);
  socket.command = () => JSON.stringify({ kind: "command", command: "list_connected" });
  const res = await inbound(r, "what have I got set up with you");
  assert.equal(res.status, 200, "the carrier was not answered 200");

  const texts = sentTexts();
  assert.equal(texts.length, 1,
    "nothing was said back. Until 2026-09-06 nothing in this Worker read an inbound "
      + "message for a connections command at all, which is the gap this closes");
  assert.equal(forbiddenTermIn(saidWords(texts[0])), null,
    "the reply carried a forbidden term");

  // AND THE ROW STILL LANDED. The twin runs AFTER the event is written and adds
  // a reply; it never takes the message away from the brain.
  const events = r.d1.rows<Record<string, unknown>>(
    `SELECT * FROM events WHERE owner_ref = ? AND kind = 'sms_reply'`, OWNER_ID);
  assert.equal(events.length, 1, "the inbound message did not land as an event row");
});

await check("THE TEXT TWIN: `connect X` sends OUR link and nobody else's", async () => {
  const r = rig();
  seedOwner(r);
  socket.command = () => JSON.stringify({ kind: "command", command: "connect_app" });
  socket.match = () => JSON.stringify({ kind: "toolkit", slug: APP.slug });
  await inbound(r, "can you set up my notes app");

  const texts = sentTexts();
  assert.equal(texts.length, 1, `one reply expected, ${texts.length} sent`);
  assert.ok(texts[0].includes(CONNECT_URL_BASE),
    "the reply carried no connect link, so there is nothing to tap");
  assert.ok(!texts[0].includes("composio") && !texts[0].includes("backend."),
    "a vendor URL reached a phone");
  assert.ok(texts[0].includes(APP.name), "the reply did not name the app");
  const links = r.d1.rows<Record<string, unknown>>(
    `SELECT * FROM connect_links WHERE user_id = ?`, OWNER_ID);
  assert.equal(links.length, 1, "the reply's link is not in connect_links, so it cannot redeem");
  assert.equal(links[0].toolkit, APP.slug);
});

await check("THE TEXT TWIN: a message it answered is not answered a SECOND time",
  async () => {
    // brain/worker.py `fetch_unprocessed` polls `kind="sms_reply" && decision=""`.
    // Without this stamp the brain — which knows nothing about connections —
    // answers the same text again in its own words, and the person gets two
    // replies to one message from one number.
    const r = rig();
    seedOwner(r);
    socket.command = () => JSON.stringify({ kind: "command", command: "list_connected" });
    await inbound(r, "what have I got set up");
    assert.equal(sentTexts().length, 1, "the twin did not answer at all");
    const row = r.d1.rows<Record<string, unknown>>(
      `SELECT * FROM events WHERE owner_ref = ? AND kind = 'sms_reply'`, OWNER_ID)[0];
    assert.ok(row, "the message did not land");
    assert.equal(row.decision, "ignore",
      "the twin answered the message and left it unclaimed, so the brain will answer "
        + "it too");
  });

await check("THE TEXT TWIN: a message it did NOT answer is left for the brain",
  async () => {
    // THE CONTROL, and it is the one that matters more: losing somebody's
    // message is far worse than answering it twice, so nothing may be claimed
    // unless a reply actually went.
    const r = rig();
    seedOwner(r);
    socket.command = () => JSON.stringify({ kind: "none" });
    await inbound(r, "book me a table somewhere on thursday");
    assert.equal(sentTexts().length, 0);
    const row = r.d1.rows<Record<string, unknown>>(
      `SELECT * FROM events WHERE owner_ref = ? AND kind = 'sms_reply'`, OWNER_ID)[0];
    assert.equal(row.decision, "",
      "an ordinary message was marked handled by a surface that did not handle it — "
        + "the brain will never see it, and the person's request is gone");
  });

await check("THE TEXT TWIN: a decision the brain already made is never overwritten",
  async () => {
    const r = rig();
    seedOwner(r);
    socket.command = () => JSON.stringify({ kind: "command", command: "list_connected" });
    const res = await inbound(r, "what is connected");
    assert.equal(res.status, 200);
    r.d1.db.prepare(`UPDATE events SET decision = 'act' WHERE owner_ref = ?`).run(OWNER_ID);
    LOGS.length = 0;
    await handleInboundText(r.env, OWNER_ID, "what is connected",
      String(r.d1.rows<Record<string, unknown>>(
        `SELECT id FROM events WHERE owner_ref = ?`, OWNER_ID)[0].id));
    const row = r.d1.rows<Record<string, unknown>>(
      `SELECT * FROM events WHERE owner_ref = ?`, OWNER_ID)[0];
    assert.equal(row.decision, "act", "the twin overwrote a decision the brain had made");
    assert.ok(LOGS.some((l) => l.includes("already carried a decision")),
      "losing that race is silent, so nobody can tell a duplicate answer from a bug");
  });

await check("THE TEXT TWIN: an ordinary message is left completely alone", async () => {
  const r = rig();
  seedOwner(r);
  socket.command = () => JSON.stringify({ kind: "none" });
  await inbound(r, "running ten minutes late, tell them for me");
  assert.equal(sentTexts().length, 0,
    "an ordinary message was answered by the connections surface, which takes it away "
      + "from everything else that would have handled it");
  assert.equal(
    r.d1.rows(`SELECT * FROM events WHERE owner_ref = ?`, OWNER_ID).length, 1,
    "the message did not land for the brain");
});

await check("THE TEXT TWIN: a judge that is down claims nothing", async () => {
  const r = rig();
  seedOwner(r);
  socket.modelStatus = 503;
  await inbound(r, "disconnect my notes app");
  assert.equal(sentTexts().length, 0,
    "a module whose judge is down grabbed the message anyway — a listener that claims "
      + "every message when its model is down eats the product");
});

await check("THE TEXT TWIN: `disconnect X` revokes before it deletes, and says what happened",
  async () => {
    const r = rig();
    seedOwner(r);
    seedConnection(r, "ca_chain_tw_1", APP.slug);
    socket.command = () => JSON.stringify({ kind: "command", command: "disconnect_app" });
    socket.match = () => JSON.stringify({ kind: "toolkit", slug: APP.slug });
    socket.rowProbe = () => r.d1.rows(
      `SELECT * FROM connections WHERE connected_account_id = 'ca_chain_tw_1'`).length > 0;
    await inbound(r, "stop using my notes app please");

    // THE ORDER, observed rather than assumed. Delete-then-revoke leaves a live
    // token at the far end with nothing pointing at it, and both calls return
    // 200 either way — so the only way to see it is to look while the revoke is
    // in flight. The spec's words are "revoke THEN delete".
    assert.equal(socket.revokeSawOurRow, true,
      "our connections row was already gone when the revoke was sent, so a failed "
        + "revoke would have left a live token nobody can ever reach again");
    assert.equal(
      r.d1.rows(`SELECT * FROM connections WHERE connected_account_id = 'ca_chain_tw_1'`).length,
      0, "the row survived a disconnect");
    const texts = sentTexts();
    assert.equal(texts.length, 1);
    assert.ok(texts[0].includes(APP.name), "the confirmation did not name the app");
    assert.equal(forbiddenTermIn(saidWords(texts[0])), null);
  });

await check("THE TEXT TWIN: a revoke the vendor could not do is not reported as done",
  async () => {
    const r = rig();
    seedOwner(r);
    seedConnection(r, "ca_chain_tw_2", APP.slug);
    socket.command = () => JSON.stringify({ kind: "command", command: "disconnect_app" });
    socket.match = () => JSON.stringify({ kind: "toolkit", slug: APP.slug });
    socket.disconnectRevokeUnavailable = true;
    await inbound(r, "remove my notes app");
    const texts = sentTexts();
    assert.equal(texts.length, 1);
    assert.ok(texts[0].includes("own settings"),
      "the reply claimed a clean disconnect over a token the vendor said it could not "
        + `revoke: ${texts[0]}`);
  });

await check("THE TEXT TWIN: an app this owner was never offered asks, it does not act",
  async () => {
    const r = rig();
    seedOwner(r);
    seedConnection(r, "ca_chain_tw_3", APP.slug);
    socket.command = () => JSON.stringify({ kind: "command", command: "disconnect_app" });
    // The judge names a plausible app that is not in the list it was handed.
    socket.match = () => JSON.stringify({ kind: "toolkit", slug: "zznotoffered" });
    await inbound(r, "disconnect the other one");
    assert.equal(
      r.d1.rows(`SELECT * FROM connections WHERE connected_account_id = 'ca_chain_tw_3'`).length,
      1, "an app the judge invented was acted on");
    const texts = sentTexts();
    assert.equal(texts.length, 1);
    assert.ok(texts[0].includes("Which app"),
      `an off-catalog answer should ask, not act: ${texts[0]}`);
  });

await check("THE TEXT TWIN: the reply goes to the ACCOUNT's number, never the handset's",
  async () => {
    const r = rig();
    // The account's own number differs from the profile number the inbound
    // message was routed by. The reply must go to the account's.
    seedOwner(r, OWNER_ID, PHONE, AWAKE_TZ);
    socket.command = () => JSON.stringify({ kind: "command", command: "list_connected" });
    await inbound(r, "what is connected", PHONE);
    const sent = socket.calls.filter((c) => c.url.startsWith(SENDBLUE_BASE));
    assert.equal(sent.length, 1);
    const to = String((JSON.parse(sent[0].body) as { number?: unknown }).number ?? "");
    assert.equal(to, PHONE, "the reply went somewhere other than this owner's own number");
  });

await check("THE TEXT TWIN: every sentence it can send clears words.ts", () => {
  const lines = textReplySentences(APP.name, `${CONNECT_URL_BASE}/${"a".repeat(TOKEN_CHARS)}`);
  assert.ok(lines.length >= 10, "the audit list is suspiciously short");
  for (const line of lines) {
    assert.equal(forbiddenTermIn(saidWords(line)), null,
      `a reply carries a forbidden term: ${line}`);
    assert.ok(!line.includes("!"), `a reply shouts: ${line}`);
    assert.ok(line.length <= ASK_MESSAGE_MAX_CHARS, `a reply is too long for one text: ${line}`);
  }
  // THE CONTROL, so the scan above is not a decoration: the same scan over a
  // sentence that DOES carry one must find it.
  assert.ok(forbiddenTermIn(`We need your permission to do that.`) !== null,
    "forbiddenTermIn found nothing in a sentence built to trip it");
  assert.ok(FORBIDDEN_TERMS.length > 5, "FORBIDDEN_TERMS is not the shipped list");
});

await check("THE TEXT TWIN: a vendor name carrying a forbidden term never reaches a phone",
  async () => {
    const r = rig();
    seedOwner(r);
    // A catalog row whose NAME breaks the register rule. Ours is the sentence;
    // theirs is the noun, and the containment is on our side.
    const hostile: ToolkitMeta = { ...APP, name: "Halcyon Integration" };
    socket.catalog = new Map([[hostile.slug, hostile]]);
    socket.searchAnswers = [hostile];
    socket.command = () => JSON.stringify({ kind: "command", command: "connect_app" });
    socket.match = () => JSON.stringify({ kind: "toolkit", slug: hostile.slug });
    await inbound(r, "set up my notes app");
    const texts = sentTexts();
    assert.equal(texts.length, 1);
    assert.equal(forbiddenTermIn(saidWords(texts[0])), null,
      `a catalog name put a forbidden word in a text we signed: ${texts[0]}`);
    assert.ok(texts[0].includes(CONNECT_URL_BASE),
      "the containment cost the person their link; it must only cost the name");
  });

await check("THE TEXT TWIN: the two carriers and the entry point are wired the same", () => {
  for (const [name, source] of [["sms.ts", SMS_SOURCE], ["sendblue.ts", SENDBLUE_SOURCE]] as const) {
    assert.equal(source.split("handleInboundText(").length - 1, 1,
      `${name} must call the twin exactly once`);
    assert.ok(/landed\.kind === "written"/.test(source),
      `${name} must only run the twin for a message that actually landed`);
    assert.ok(/ctx\?: ExecutionContext/.test(source),
      `${name} must take a ctx, or a Worker cancels the twin the moment it answers`);
  }
  assert.equal(INDEX_SOURCE.split("smsInbound(request, env as unknown as SmsEnv, ctx)").length - 1, 1,
    "src/index.ts does not pass ctx to smsInbound");
  assert.equal(
    INDEX_SOURCE.split("sendblueInbound(request, env as unknown as SendblueEnv, ctx)").length - 1, 1,
    "src/index.ts does not pass ctx to sendblueInbound");
});

await check("THE TEXT TWIN: no pre-filter stands in front of the judge", async () => {
  // A length or shape test in front of `handleInboundText` would be
  // `shard_too_thin()` again — a word count deciding a line is too thin to
  // mean anything — and that guard is registered tape in HARNESS-LAWS. An
  // EMPTY-ish message must still cost exactly one model call.
  const r = rig();
  seedOwner(r);
  socket.command = () => JSON.stringify({ kind: "none" });
  await handleInboundText(r.env, OWNER_ID, "hm");
  const asked = socket.calls.filter((c) => !c.url.startsWith(COMPOSIO_BASE_URL)
    && !c.url.startsWith(SENDBLUE_BASE));
  assert.equal(asked.length, 1,
    `a two-character message should still be asked about exactly once; ${asked.length} calls`);
});

await check("THE TEXT TWIN: an unconfigured Worker spends nothing and says which piece",
  async () => {
    // ASKED BEFORE THE MODEL CALL, not after. The twin runs on EVERY inbound
    // text, so a Worker missing one secret would otherwise spend a model call
    // per message in order to discover it cannot answer any of them — and say
    // nothing about why in the log.
    const r = rig({ COMPOSIO_API_KEY: "" });
    seedOwner(r);
    socket.command = () => JSON.stringify({ kind: "command", command: "list_connected" });
    const outcome = await handleInboundText(r.env, OWNER_ID, "what is connected");
    assert.equal(outcome.kind, "not_for_us", "an unwired twin claimed the message anyway");
    assert.equal(socket.calls.length, 0,
      `an unwired twin spent ${socket.calls.length} call(s) before refusing`);
    assert.ok(LOGS.some((l) => l.includes("COMPOSIO_API_KEY")),
      "nothing in the log names the missing piece, so an operator cannot tell why "
        + "every text about an app is being ignored");
    // THE CONTROL: the same message on a configured Worker DOES cost a call.
    const good = rig();
    seedOwner(good);
    socket.command = () => JSON.stringify({ kind: "command", command: "list_connected" });
    await handleInboundText(good.env, OWNER_ID, "what is connected");
    assert.ok(socket.calls.length > 0, "the configured control spent nothing either, so "
      + "the check above is measuring the rig and not the refusal");
  });

await check("THE TEXT TWIN: the catalog it offers is bounded and per owner", async () => {
  const r = rig();
  seedOwner(r);
  const many: ToolkitMeta[] = [];
  for (let i = 0; i < TEXT_CATALOG_LIMIT + 15; i++) {
    many.push({ ...APP, slug: `zzfiller${i}`, name: `Filler ${i}` });
  }
  socket.searchAnswers = many;
  const deps = textCommandDeps(r.env, "anything");
  const offered = await deps.catalog(ownerId(OWNER_ID));
  assert.ok(offered.length <= TEXT_CATALOG_LIMIT + 5,
    `${offered.length} rows were put in front of the judge; the ceiling is `
      + `${TEXT_CATALOG_LIMIT} from the search plus this owner's own rows`);
  assert.ok(offered.length > 0, "the catalog port returned nothing at all");
});

await check("THE TEXT TWIN: a plan is a decision, and the executor is what acts", async () => {
  // The split the module argues for, made behavioural: planning writes nothing
  // and sends nothing, even for the most destructive plan there is.
  const r = rig();
  seedOwner(r);
  seedConnection(r, "ca_chain_tw_4", APP.slug);
  socket.command = () => JSON.stringify({ kind: "command", command: "disconnect_app" });
  socket.match = () => JSON.stringify({ kind: "toolkit", slug: APP.slug });
  const plan = await planTextCommand(
    ownerId(OWNER_ID), "get rid of my notes app", textCommandDeps(r.env, "get rid of my notes app"));
  assert.equal(plan.kind, "disconnect");
  assert.equal(sentTexts().length, 0, "planning sent a text");
  assert.equal(
    r.d1.rows(`SELECT * FROM connections WHERE connected_account_id = 'ca_chain_tw_4'`).length,
    1, "planning deleted a connection");

  const outcome = await runTextCommandPlan(plan, r.env);
  assert.equal(outcome.replied, true, `the executor did not reply: ${outcome.detail}`);
  assert.equal(
    r.d1.rows(`SELECT * FROM connections WHERE connected_account_id = 'ca_chain_tw_4'`).length,
    0, "the executor did not carry the plan out");
});

await check("LAW 1: the text twin's own wiring decides no meaning, and names no app",
  () => {
    const src = readFileSync(join(here, "..", "src", "connections", "wiring.ts"), "utf8");
    const start = src.indexOf("// THE TEXT TWIN — the ports src/connections/text_commands.ts");
    assert.ok(start > 0, "the text-twin region of wiring.ts could not be found — this "
      + "scan would have passed over nothing, which is how an instrument lies");
    const region = src.slice(start)
      + src.slice(src.indexOf("async function ownerPhrasing"),
                  src.indexOf("async function ownerPhrasing") + 2500);

    // NO SUBSTRING TEST OVER WHAT ANYBODY SAID. The message reaches exactly two
    // places — the vendor's own catalog search and the two judge calls — and is
    // never read a character at a time by us.
    const readsThem = /\b(said|phrase|content|body)\s*\.\s*(includes|startsWith|endsWith|match|indexOf|toLowerCase|split)\s*\(/
      .exec(region);
    assert.equal(readsThem, null,
      `the wiring reads the owner's own words: ${readsThem?.[0]}`);
    // CONTROL: the same scan over a planted violation must find it.
    assert.ok(/\b(said|phrase|content|body)\s*\.\s*(includes|startsWith|endsWith|match|indexOf|toLowerCase|split)\s*\(/
      .test(region + '\nif (said.includes("x")) {}'),
      "the scan cannot see a violation it was shown, so it proves nothing");

    // NO APP IS HARDCODED. Names, logos and slugs come from the catalog at run
    // time; a fixture may name a fictional app, production source may not name
    // a real one.
    const REAL = ["notion", "slack", "gmail", "github", "linear", "asana", "trello",
                  "dropbox", "jira", "stripe", "hubspot", "salesforce", "outlook",
                  "zoom", "figma", "airtable", "shopify", "discord", "spotify"];
    const named = REAL.filter((n) => new RegExp(`(?<![a-z])${n}(?![a-z])`, "i").test(region));
    assert.deepEqual(named, [], `the wiring names real apps: ${named.join(", ")}`);
    assert.ok(REAL.some((n) => new RegExp(`(?<![a-z])${n}(?![a-z])`, "i")
      .test(region + " notion ")), "the app-name scan is blind");

    // EXACTLY TWO REGEX LITERALS in the region, and both strip a MODEL's own
    // code fence — transport on a reply we are about to JSON.parse, which is
    // the same thing `parseSentences` does eight hundred lines above. A third
    // one is a conversation rather than a commit.
    const fences = (region.match(/\/\^?```/g) ?? []).length;
    assert.equal(fences, 2, `${fences} fence-stripping expressions; expected 2`);
  });

// ===========================================================================
// 5. THE THIRD WRITER INPUT — the owner's own words reach the prompt
// ===========================================================================

await check("PHRASING: the owner's own lines reach the ask writer, from their own rows",
  async () => {
    const r = rig();
    await seedDueOwner(r);
    seedSaidLine(r, "evchain0000001", "yeah just chuck it in there when you get a sec");
    seedSaidLine(r, "evchain0000002", "no worries either way honestly");

    const moment = await nudgeMomentFor(r.env)(ownerId(OWNER_ID), APP.slug, "in_task", NOW);
    assert.ok(moment, "the moment could not be established");
    assert.deepEqual(
      [...(moment!.phrasing ?? [])].sort(),
      ["no worries either way honestly", "yeah just chuck it in there when you get a sec"],
      "the moment did not carry this owner's own lines");

    await runCron(r.env);
    const askPrompts = socket.calls.filter((c) => promptKind(c.body) === "ask");
    assert.equal(askPrompts.length >= 1, true, "the writer was never asked");
    assert.ok(askPrompts[0].body.includes("chuck it in there"),
      "the owner's own words did not reach the prompt the ask was written from");
    assert.ok(askPrompts[0].body.includes("HOW THEY TALK"),
      "the phrasing section was not rendered");
  });

await check("PHRASING: one owner's words never reach another owner's text", async () => {
  const r = rig();
  await seedDueOwner(r);
  seedOwner(r, SECOND_OWNER, SECOND_PHONE, AWAKE_TZ);
  seedSaidLine(r, "evchain0000003", "a sentence only the second owner ever said", NOW - HOUR,
    SECOND_OWNER);
  // AND one the FIRST owner said out loud in front of the pendant, addressed to
  // another human being. It is theirs, it is in their own row, and it still
  // must not reach a prompt: `speaker = 'owner'` alone is half of every private
  // conversation they have had this week.
  seedSaidLine(r, "evchain0000004", "tell your mother I said the thing about the will",
    NOW - HOUR, OWNER_ID, "transcript", "person");

  const moment = await nudgeMomentFor(r.env)(ownerId(OWNER_ID), APP.slug, "in_task", NOW);
  assert.ok(moment, "the moment could not be established");
  assert.deepEqual(moment!.phrasing ?? [], [],
    "another owner's transcript, or this owner's ambient speech to a third party, "
      + "reached this owner's ask. The first is the single worst failure this product "
      + "has and has happened once already; the second is a pendant's whole privacy "
      + "model spent to make one text sound friendlier");
});

await check("PHRASING: an unreadable events table costs a voice, never an ask", async () => {
  const r = rig();
  await seedDueOwner(r);
  r.d1.failOn = (sql) => sql.includes('FROM "events"');
  await runCron(r.env);
  r.d1.failOn = null;
  assert.equal(sentTexts().length, 1,
    "an owner lost their ask because a register input could not be read; every OTHER "
      + "input to the moment is a floor, and this one deliberately is not");
});

// ===========================================================================
// 6. THE SUITE ITSELF, AND THE LAW-3 SEAM
// ===========================================================================

await check("this suite is in package.json's test script", () => {
  assert.ok(PACKAGE_JSON.includes("test/connections-endtoend.test.ts"),
    "connections-endtoend is not in CI. Five suites were written and left out this week; "
      + "each time hundreds of checks silently did not run");
  // AND IT RUNS LAST, so a break anywhere upstream is reported by the suite
  // that owns it rather than by this one.
  const script = /"test":\s*"([^"]*)"/.exec(PACKAGE_JSON)?.[1] ?? "";
  assert.ok(script.trim().endsWith("test/connections-endtoend.test.ts"),
    "the end-to-end suite should be the last leg of the chain");
});

await check("LAW 3: the live gate has a leg for the ask, and it knows the four states", () => {
  // This suite proves the chain is CONNECTED. It cannot prove production runs
  // it — no deploy has been verified, and `app_usage_signals` was empty on
  // api.anticipy.ai when this was written. The instrument that will say so is
  // overnight/is_connect_live.py leg 11, and these two are pinned to each other
  // so neither can be deleted quietly.
  assert.ok(GATE_SOURCE.includes("def leg_ask("),
    "overnight/is_connect_live.py has no leg for the ask, so nothing measures on "
      + "production what this suite measures in the repo");
  for (const state of ["cron-unregistered", "unwired", "nobody-due", "asking"]) {
    assert.ok(GATE_SOURCE.includes(state),
      `leg 11 cannot report the state ${state}, and those four are different facts`);
  }
});

// ===========================================================================
// MUTATIONS RUN AGAINST THIS CHAIN, 2026-09-06. 26 run, 26 RED, 0 survivors.
//
// Every anchor is a string that occurs EXACTLY ONCE in the file it mutates, and
// the runner refuses to apply one whose count is not 1 — a regex that silently
// matched nothing has produced several false "it is tested" readings in this
// repo. Mutation 17's first form was rejected on that rule and rewritten rather
// than loosened.
//
//   1  src/cron.ts          installNudgeWiring deleted                14 checks
//   2  src/cron.ts          the nightly evidence sweep dropped         3
//   3  src/cron.ts          the evidence sweep moved onto */5          3
//   4  wrangler.jsonc       the five-minute tick removed               1
//   5  src/routes/sms.ts    the text twin call deleted                 1
//   6  src/routes/sendblue  the text twin call deleted                 8
//   7  src/index.ts         ctx not threaded into smsInbound           1
//   8  wiring.ts            sayable stops containing a vendor name     1
//   9  wiring.ts            sayable scans our OWN link too             1
//   10 wiring.ts            revokeUnavailable ignored                  1
//   11 wiring.ts            disconnect DELETES before it revokes       1
//   12 wiring.ts            the phrasing read loses its owner filter   1
//   13 wiring.ts            an unreadable events table becomes a floor 1
//   14 nudge.ts             the moment's phrasing is not carried       1
//   15 wiring.ts            the judge's catalog is unbounded           1
//   16 wiring.ts            the reply goes to the handset, not the row 1
//   17 wiring.ts            a missing config no longer refuses         1
//   23 wiring.ts            an answered message is not claimed         2
//   24 wiring.ts            EVERY message claimed, answered or not     1
//   25 wiring.ts            the claim overwrites the brain's decision  1
//   26 wiring.ts            the phrasing read drops the addressee line 1
//   18-22 overnight/is_connect_live.py — leg 11's four states, its
//        config-can-never-be-green rule, and the mirrored due query.
//
// TWO SURVIVED THE FIRST PASS, and both are worth keeping in view because each
// one was a check that read as evidence and was not:
//
//   11 (revoke THEN delete) survived because both vendor calls answer 200
//      whichever order they are made in, and the row is gone either way at the
//      end. Nothing outside could see the order. `socket.rowProbe` was added —
//      the vendor stub looks at our own table AT REVOKE TIME — and the
//      mutation now goes red. Delete-first leaves a live token at the far end
//      with nothing pointing at it, and that is the failure provider.ts spends
//      forty lines of comment on.
//
//   21 (an uncountable connect_nudges read as zero) survived because
//      `nobody-due` and `unreadable` are BOTH UNPROVEN and both print the same
//      mark — so a check on the mark alone could not tell "a quiet night" from
//      "the database did not answer", which are opposite facts. The check now
//      reads the sentence as well.
// ===========================================================================

console.log = realLog;
console.log(`connections-endtoend: ${passes} checks passed, ${failures} failed`);
if (failures > 0) process.exit(1);
