/**
 * test/connections-signals.test.ts — HOW ANTICIPY KNOWS WHAT YOU USE.
 *
 *   node --experimental-strip-types migration/workers/test/connections-signals.test.ts
 *
 * WHAT IS REAL HERE. All of it except two other systems. The rows go through
 * the SHIPPED store (src/connections/store.ts) into node:sqlite loaded with
 * the REAL migration/d1/schema.sql, so every CHECK, the four-column PRIMARY
 * KEY and the compare-and-set are the database's own answers rather than a
 * fake that records strings. The sweep runs its shipped SQL against that same
 * schema. The two things that never appear: the vendor's catalog (a fixture of
 * five invented apps) and the model that decides which app somebody meant (its
 * VERDICT is an input, which is the whole law-1 point).
 *
 * THE FAILURES THIS FILE EXISTS TO CATCH:
 *
 *   THE EMPTY TABLE. `app_usage_signals` had ZERO rows on production on
 *   2026-09-06 while every part that reads it was built and green. The sweep
 *   section drives the one door whose input production already produces.
 *
 *   A WORD LIST DECIDING WHAT SOMEBODY MEANT. Every non-`toolkit` verdict —
 *   unclear, none, no-verdict, a judge that could not be reached, a blank slug
 *   — must record NOTHING, and the CONTROL beside each proves the good case
 *   still records. A source scan then reads signals.ts back and fails on an
 *   app name or a host literal, in code AND in prose.
 *
 *   AN APP SOMEBODY STOPPED USING COMING UP ANYWAY. Decay, and the crossover
 *   the spec asks for: one fresh MEDIUM signal outranks a HIGH one from three
 *   months ago.
 *
 *   ASKING ONE PERSON ABOUT ANOTHER PERSON'S APPS. The fan-out and the SWAP,
 *   which is the one nothing in the rows can show.
 *
 *   A GUESS DRESSED AS A MATCH. A host two catalog entries claim, and a host
 *   that merely CONTAINS one, must produce no signal at all — the weight they
 *   would add is HIGH and would own the top of the table on nothing.
 *
 * MUTATIONS THIS FILE MUST GO RED ON: the list at the bottom, each anchored on
 * a literal that occurs EXACTLY ONCE in the file it mutates. Each anchor's
 * uniqueness is itself asserted, because a mutation anchor that matches
 * nothing produces a false "it is tested" reading — that happened three times
 * in this repo this week.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import {
  CONNECTED_SWEEP_CAP,
  DEFAULT_HALF_LIFE_MS,
  SOURCE_DECAYS,
  SOURCE_WEIGHT,
  WEIGHT_CERTAIN,
  WEIGHT_HIGH,
  WEIGHT_MEDIUM,
  askedSignal,
  compareRankedApps,
  connectedSignal,
  createSignals,
  decayedWeight,
  hostToToolkit,
  linkSignals,
  observedHostSignal,
  rankRows,
  rankedApps,
  record,
  recordAnswerToAsk,
  recordConnectedApp,
  recordLinksSeen,
  recordObservedHost,
  recordSignUpDomain,
  recordUserSaidIt,
  saidSignal,
  signUpDomainSignals,
  signalMerge,
  sweepConnectedSignals,
  type RankedApp,
  type SignalStore,
} from "../src/connections/signals.ts";
import {
  ConnectionsSchemaMissing,
  SIGNAL_SOURCES,
  createD1Store,
  type ConnectionsStore,
  type SignalKey,
  type StoreEnv,
  type StoredSignal,
} from "../src/connections/store.ts";
import type { ToolkitMeta, ToolkitVerdict }
  from "../../../spike/two-hands/src/connections/contract.ts";
import { FakeD1, asD1 } from "./fake-d1.ts";

const here = dirname(fileURLToPath(import.meta.url));
const SIGNALS_PATH = join(here, "..", "src", "connections", "signals.ts");
const SRC = readFileSync(SIGNALS_PATH, "utf8");

let failures = 0;
let passes = 0;
async function check(what: string, fn: () => void | Promise<void>): Promise<void> {
  try { await fn(); passes++; }
  catch (err) { failures++; console.error("FAIL " + what + "\n     " + (err as Error).message); }
}

const logs: string[] = [];
const realLog = console.log;
console.log = (...a: unknown[]) => { logs.push(a.map(String).join(" ")); };

// ---------------------------------------------------------------------------
// FIXTURES
// ---------------------------------------------------------------------------

const NOW = 1_757_000_000_000;
const DAY = 24 * 60 * 60 * 1000;
const HALF_LIFE = DEFAULT_HALF_LIFE_MS;

// 15 lowercase alphanumerics, the shape D1 mints and the schema CHECKs.
const OWNER_A = "ownersigaaaa111";
const OWNER_B = "ownersigbbbb222";

/**
 * FIVE INVENTED APPS. Not one of them exists, and not one of their slugs or
 * hosts appears in src/connections/signals.ts — which is what makes "NO APP IS
 * HARDCODED" a behaviour rather than a promise. The reserved `.example` TLD is
 * used throughout so nothing here can ever resolve to somebody's real site.
 *
 *   kit-alpha        an ordinary app whose catalog url IS its registrable name
 *   kit-beta         a second one, for the ranking and two-owner sections
 *   shared-one/two   ONE vendor, TWO apps, ONE registrable name — the shape a
 *                    host reduced to eTLD+1 cannot tell apart
 *   kit-delta        an app whose catalog url sits BELOW its vendor's name, so
 *                    the vendor's bare name only CONTAINS it
 */
const ALPHA = "kit-alpha";
const BETA = "kit-beta";
const SHARED_ONE = "shared-one";
const SHARED_TWO = "shared-two";
const DELTA = "kit-delta";

function meta(slug: string, appUrl: string | null): ToolkitMeta {
  return { slug, name: slug, logo: null, description: null, appUrl, scopes: [] };
}

const CATALOG: ToolkitMeta[] = [
  meta(ALPHA, "https://kit-alpha.example"),
  meta(BETA, "https://kit-beta.example"),
  meta(SHARED_ONE, "https://shared-vendor.example/one"),
  meta(SHARED_TWO, "https://shared-vendor.example/two"),
  meta(DELTA, "https://mail.kit-delta.example"),
];

interface Rig {
  d1: FakeD1;
  env: StoreEnv;
  store: ConnectionsStore;
}

function rig(opts: { schema?: boolean } = {}): Rig {
  const d1 = new FakeD1(opts);
  const env = { DB: asD1(d1) } as unknown as StoreEnv;
  return { d1, env, store: createD1Store(env) };
}

/** Every signal row in the table, all owners, in a stable order. The "and
 *  nothing else" half of every door test reads THIS, not the door's own
 *  return value: a door that also wrote a second row somewhere would be
 *  invisible to a test that only looked at what it handed back. */
function allRows(r: Rig): Array<{
  user_id: string; toolkit: string; source: string; alias: string;
  weight: number; last_seen_at: number;
}> {
  // Spread into a plain object: node:sqlite hands back null-prototype rows and
  // a deep-equal against an object literal fails on the prototype alone.
  return r.d1.rows(
    `SELECT "user_id","toolkit","source","alias","weight","last_seen_at"
       FROM "app_usage_signals"
      ORDER BY "user_id","toolkit","source","alias"`,
  ).map((row) => ({ ...row })) as never;
}

function connection(
  r: Rig, user: string, toolkit: string, status: string, alias = "", id?: string,
): void {
  r.d1.db.prepare(
    `INSERT INTO "connections"
       ("connected_account_id","user_id","toolkit","alias","status","writes_enabled","last_used_at")
     VALUES (?, ?, ?, ?, ?, 0, NULL)`,
  ).run(id ?? `ca_${user}_${toolkit}_${alias}`, user, toolkit, alias, status);
}

/** A signal row written straight to SQLite, never through the code under
 *  test — the way a live SELECT would see one. */
function seed(
  r: Rig, user: string, toolkit: string, source: string,
  weight: number, lastSeen: number, alias = "",
): void {
  r.d1.db.prepare(
    `INSERT INTO "app_usage_signals"
       ("user_id","toolkit","source","alias","weight","last_seen_at")
     VALUES (?, ?, ?, ?, ?, ?)`,
  ).run(user, toolkit, source, alias, weight, lastSeen);
}

const TOOLKIT_VERDICT = (slug: string): ToolkitVerdict => ({ kind: "toolkit", slug });

// ===========================================================================
// 1. THE WEIGHTS — the spec's three bands and its six sources, and no others.
// ===========================================================================

await check("the three bands are the spec's own: Certain > High > Medium", () => {
  assert.equal(WEIGHT_CERTAIN, 1);
  assert.equal(WEIGHT_HIGH, 0.7);
  assert.equal(WEIGHT_MEDIUM, 0.4);
  assert.ok(WEIGHT_CERTAIN > WEIGHT_HIGH, "a certainty must outweigh a high signal");
  assert.ok(WEIGHT_HIGH > WEIGHT_MEDIUM, "a high signal must outweigh a medium one");
});

await check("every source the spec lists has a weight, and no source it does not", () => {
  // Compared against the CONTRACT's closed enum rather than against a list
  // typed twice here: a seventh source invented in signals.ts, or one of the
  // six dropped, is red either way.
  assert.deepEqual(Object.keys(SOURCE_WEIGHT).sort(), [...SIGNAL_SOURCES].sort());
  assert.deepEqual(Object.keys(SOURCE_DECAYS).sort(), [...SIGNAL_SOURCES].sort());
});

await check("the bands are attached to the spec's own six signals", () => {
  assert.equal(SOURCE_WEIGHT.said, WEIGHT_HIGH, "the user says it: High");
  assert.equal(SOURCE_WEIGHT.observer, WEIGHT_HIGH, "the browser hand saw it: High");
  assert.equal(SOURCE_WEIGHT.mx, WEIGHT_MEDIUM, "sign-up email domain: Medium");
  assert.equal(SOURCE_WEIGHT.link, WEIGHT_MEDIUM, "links in conversations: Medium");
  assert.equal(SOURCE_WEIGHT.connected, WEIGHT_CERTAIN, "already connected apps: Certain");
  assert.equal(SOURCE_WEIGHT.asked, WEIGHT_CERTAIN, "asking: Certain");
});

await check("the certain two do not decay; the four observations do", () => {
  assert.equal(SOURCE_DECAYS.connected, false);
  assert.equal(SOURCE_DECAYS.asked, false);
  for (const s of ["said", "observer", "mx", "link"] as const) {
    assert.equal(SOURCE_DECAYS[s], true, `${s} must decay`);
  }
});

await check("the weight table is frozen — a run-time edit is a band we do not mean", () => {
  assert.throws(() => { (SOURCE_WEIGHT as Record<string, number>).link = 99; });
  assert.equal(SOURCE_WEIGHT.link, WEIGHT_MEDIUM);
});

// ===========================================================================
// 2. THE SIX DOORS — each records what it should, AND NOTHING ELSE.
// ===========================================================================

// --- 2.1 "the user says it" ------------------------------------------------

await check("CONTROL: a clear verdict records exactly one `said` row at High", async () => {
  const r = rig();
  const row = await recordUserSaidIt(r.store, OWNER_A, TOOLKIT_VERDICT(ALPHA), NOW);
  assert.ok(row, "a clear verdict must record something");
  assert.equal(row!.source, "said");
  assert.equal(row!.toolkit, ALPHA);
  assert.equal(row!.weight, WEIGHT_HIGH);
  assert.deepEqual(allRows(r), [{
    user_id: OWNER_A, toolkit: ALPHA, source: "said", alias: "",
    weight: WEIGHT_HIGH, last_seen_at: NOW,
  }]);
});

await check("an unreadable verdict records NOTHING rather than guessing", async () => {
  // Four states, and only one of them is a licence. `unclear` and `none` are
  // the judge answering; a null is the judge never reached. All four record
  // nothing, because a signal ADDS weight and weight is what eventually
  // licenses interrupting somebody — silence must not be able to nudge.
  const unreadable: Array<[string, ToolkitVerdict | null | undefined]> = [
    ["unclear", { kind: "unclear" }],
    ["none", { kind: "none" }],
    ["no-verdict", { kind: "no-verdict" }],
    ["null (the judge was unreachable)", null],
    ["undefined (nobody asked)", undefined],
  ];
  for (const [name, verdict] of unreadable) {
    const r = rig();
    const row = await recordUserSaidIt(r.store, OWNER_A, verdict, NOW);
    assert.equal(row, null, `${name} must record nothing`);
    assert.deepEqual(allRows(r), [], `${name} left a row behind`);
  }
});

await check("a verdict whose slug is blank records nothing", async () => {
  for (const slug of ["", "   ", "\t"]) {
    const r = rig();
    assert.equal(await recordUserSaidIt(r.store, OWNER_A, TOOLKIT_VERDICT(slug), NOW), null);
    assert.deepEqual(allRows(r), []);
  }
});

await check("a malformed verdict object records nothing", async () => {
  const r = rig();
  const junk = { kind: "toolkit" } as unknown as ToolkitVerdict; // no slug at all
  assert.equal(await recordUserSaidIt(r.store, OWNER_A, junk, NOW), null);
  assert.equal(saidSignal(OWNER_A, {} as ToolkitVerdict, NOW), null);
  assert.deepEqual(allRows(r), []);
});

await check("`said` carries the account the judge resolved, and null when it did not", async () => {
  const r = rig();
  await recordUserSaidIt(r.store, OWNER_A, TOOLKIT_VERDICT(ALPHA), NOW, "work");
  await recordUserSaidIt(r.store, OWNER_A, TOOLKIT_VERDICT(ALPHA), NOW, null);
  // TWO LINES, not one: evidence that did not say which account is its own
  // pile and is never folded into a named one.
  assert.deepEqual(allRows(r).map((x) => x.alias), ["", "work"]);
});

// --- 2.2 "the browser hand saw it" ----------------------------------------

await check("CONTROL: a host the catalog names records exactly one `observer` row", async () => {
  const r = rig();
  const row = await recordObservedHost(r.store, OWNER_A, "kit-alpha.example", CATALOG, NOW);
  assert.ok(row);
  assert.equal(row!.source, "observer");
  assert.equal(row!.toolkit, ALPHA);
  assert.equal(row!.weight, WEIGHT_HIGH);
  assert.deepEqual(allRows(r).map((x) => [x.toolkit, x.source]), [[ALPHA, "observer"]]);
});

await check("a page INSIDE a catalog entry's site is that app", () => {
  assert.deepEqual(
    hostToToolkit("app.kit-alpha.example", CATALOG), { kind: "toolkit", slug: ALPHA },
  );
});

await check("a host TWO catalog entries claim records nothing", async () => {
  const r = rig();
  const match = hostToToolkit("shared-vendor.example", CATALOG);
  assert.equal(match.kind, "ambiguous");
  assert.deepEqual((match as { slugs: string[] }).slugs, [SHARED_ONE, SHARED_TWO]);
  assert.equal(await recordObservedHost(r.store, OWNER_A, "shared-vendor.example", CATALOG, NOW), null);
  assert.deepEqual(allRows(r), [], "a coin toss must not become a HIGH weight");
});

await check("a host that merely CONTAINS one catalog entry records nothing", async () => {
  // The measured defect: with exactly one entry under it a bare registry
  // suffix came back as a confident match. One entry is not less ambiguous
  // than two; it is the same guess with nothing to compare it against.
  const r = rig();
  const match = hostToToolkit("kit-delta.example", CATALOG);
  assert.equal(match.kind, "ambiguous", "the weak tier is a shortlist, never a pick");
  assert.deepEqual((match as { slugs: string[] }).slugs, [DELTA]);
  assert.equal(await recordObservedHost(r.store, OWNER_A, "kit-delta.example", CATALOG, NOW), null);
  assert.deepEqual(allRows(r), []);
});

await check("a host nothing in the catalog claims records nothing", async () => {
  const r = rig();
  for (const host of ["nobody-here.example", "", "   ", "not a host at all", "ftp://x.example"]) {
    assert.equal(await recordObservedHost(r.store, OWNER_A, host, CATALOG, NOW), null, host);
  }
  assert.deepEqual(allRows(r), []);
});

await check("an address is never trimmed into somebody else's address", () => {
  const numeric = [meta("kit-numeric", "https://203.0.113.7")];
  assert.deepEqual(hostToToolkit("203.0.113.7", numeric), { kind: "toolkit", slug: "kit-numeric" });
  assert.deepEqual(hostToToolkit("10.203.0.113", numeric), { kind: "none" });
});

await check("an empty catalog names nothing", () => {
  assert.deepEqual(hostToToolkit("kit-alpha.example", []), { kind: "none" });
  assert.equal(observedHostSignal(OWNER_A, "kit-alpha.example", [], NOW), null);
});

// --- 2.3 "sign-up email domain" -------------------------------------------

await check("CONTROL: the sign-up domain and its mail exchangers record `mx` rows at Medium",
  async () => {
    const r = rig();
    const rows = await recordSignUpDomain(
      r.store, OWNER_A,
      { emailDomain: "kit-beta.example", mxHosts: ["mx1.kit-alpha.example"] },
      CATALOG, NOW,
    );
    assert.equal(rows.length, 2);
    assert.deepEqual(
      allRows(r).map((x) => [x.toolkit, x.source, x.weight, x.alias]),
      [[ALPHA, "mx", WEIGHT_MEDIUM, ""], [BETA, "mx", WEIGHT_MEDIUM, ""]],
    );
  });

await check("three exchangers pointing at one app are ONE fact, not three", async () => {
  const r = rig();
  const inputs = signUpDomainSignals(
    OWNER_A,
    { mxHosts: ["mx1.kit-alpha.example", "mx2.kit-alpha.example", "mx3.kit-alpha.example"] },
    CATALOG, NOW,
  );
  assert.equal(inputs.length, 1, "de-duplicated by slug");
  await recordSignUpDomain(
    r.store, OWNER_A,
    { mxHosts: ["mx1.kit-alpha.example", "mx2.kit-alpha.example", "mx3.kit-alpha.example"] },
    CATALOG, NOW,
  );
  assert.equal(allRows(r).length, 1);
  assert.equal(allRows(r)[0].weight, WEIGHT_MEDIUM, "one fact is one band, not three");
});

await check("an exchanger never guesses which of the owner's accounts it is", () => {
  for (const input of signUpDomainSignals(
    OWNER_A, { emailDomain: "kit-beta.example", mxHosts: ["mx1.kit-alpha.example"] }, CATALOG, NOW,
  )) {
    assert.equal(input.alias, null, "an exchanger cannot say work or personal");
  }
});

await check("an unresolvable sign-up domain records nothing", async () => {
  const r = rig();
  assert.deepEqual(
    await recordSignUpDomain(r.store, OWNER_A, { emailDomain: "nobody-here.example" }, CATALOG, NOW),
    [],
  );
  assert.deepEqual(
    await recordSignUpDomain(r.store, OWNER_A, { emailDomain: null, mxHosts: [] }, CATALOG, NOW),
    [],
  );
  assert.deepEqual(await recordSignUpDomain(r.store, OWNER_A, {}, CATALOG, NOW), []);
  assert.deepEqual(allRows(r), []);
});

await check("an ambiguous exchanger records nothing", async () => {
  const r = rig();
  assert.deepEqual(
    await recordSignUpDomain(r.store, OWNER_A, { emailDomain: "shared-vendor.example" }, CATALOG, NOW),
    [],
  );
  assert.deepEqual(allRows(r), []);
});

// --- 2.4 "links in conversations" -----------------------------------------

await check("CONTROL: a link the catalog names records exactly one `link` row at Medium",
  async () => {
    const r = rig();
    const rows = await recordLinksSeen(
      r.store, OWNER_A, ["https://kit-alpha.example/page/123"], CATALOG, NOW,
    );
    assert.equal(rows.length, 1);
    assert.deepEqual(
      allRows(r).map((x) => [x.toolkit, x.source, x.weight]),
      [[ALPHA, "link", WEIGHT_MEDIUM]],
    );
  });

await check("four links to one app are ONE piece of evidence", async () => {
  const r = rig();
  await recordLinksSeen(r.store, OWNER_A, [
    "https://kit-alpha.example/a", "https://kit-alpha.example/b",
    "https://app.kit-alpha.example/c", "https://kit-alpha.example/d",
  ], CATALOG, NOW);
  assert.equal(allRows(r).length, 1);
  assert.equal(allRows(r)[0].weight, WEIGHT_MEDIUM);
});

await check("links to two apps record two rows", async () => {
  const r = rig();
  await recordLinksSeen(
    r.store, OWNER_A, ["https://kit-alpha.example/a", "https://kit-beta.example/b"], CATALOG, NOW,
  );
  assert.deepEqual(allRows(r).map((x) => x.toolkit), [ALPHA, BETA]);
});

await check("a link nothing claims, and a thing that is not a link, record nothing", async () => {
  const r = rig();
  assert.deepEqual(
    await recordLinksSeen(r.store, OWNER_A, [
      "https://nobody-here.example/x", "have a look at this", "", "shared-vendor.example",
    ], CATALOG, NOW),
    [],
  );
  assert.deepEqual(allRows(r), []);
  assert.deepEqual(linkSignals(OWNER_A, [], CATALOG, NOW), []);
  assert.deepEqual(linkSignals(OWNER_A, null as unknown as string[], CATALOG, NOW), []);
});

// --- 2.5 "already connected apps" -----------------------------------------

await check("CONTROL: a connected app records one `connected` row at Certain, with the account",
  async () => {
    const r = rig();
    const row = await recordConnectedApp(r.store, OWNER_A, ALPHA, NOW, "personal");
    assert.equal(row.source, "connected");
    assert.equal(row.weight, WEIGHT_CERTAIN);
    assert.deepEqual(
      allRows(r).map((x) => [x.toolkit, x.source, x.weight, x.alias]),
      [[ALPHA, "connected", WEIGHT_CERTAIN, "personal"]],
    );
    // The spec's "also tells us which account to use by default": the alias
    // has to survive into the row or the ask cannot name the account.
    assert.equal(connectedSignal(OWNER_A, ALPHA, NOW, "work").alias, "work");
  });

// --- 2.6 "asking" ----------------------------------------------------------

await check("CONTROL: an answer to an ask records one `asked` row at Certain", async () => {
  const r = rig();
  const row = await recordAnswerToAsk(r.store, OWNER_A, BETA, NOW, "work");
  assert.equal(row.source, "asked");
  assert.equal(row.weight, WEIGHT_CERTAIN);
  assert.deepEqual(
    allRows(r).map((x) => [x.toolkit, x.source, x.alias]), [[BETA, "asked", "work"]],
  );
  assert.equal(askedSignal(OWNER_A, BETA, NOW).source, "asked");
});

// --- 2.7 the doors do not reach past their own row -------------------------

await check("six doors, six sources, and each writes only its own", async () => {
  const r = rig();
  await recordUserSaidIt(r.store, OWNER_A, TOOLKIT_VERDICT(ALPHA), NOW);
  await recordObservedHost(r.store, OWNER_A, "kit-alpha.example", CATALOG, NOW);
  await recordSignUpDomain(r.store, OWNER_A, { emailDomain: "kit-alpha.example" }, CATALOG, NOW);
  await recordLinksSeen(r.store, OWNER_A, ["https://kit-alpha.example/x"], CATALOG, NOW);
  await recordConnectedApp(r.store, OWNER_A, ALPHA, NOW);
  await recordAnswerToAsk(r.store, OWNER_A, ALPHA, NOW);
  // ONE APP, SIX ROWS. The table is keyed by source as well as by app, so a
  // key of (user, toolkit) alone would hold one kind of evidence and silently
  // drop the other five.
  assert.deepEqual(
    allRows(r).map((x) => x.source).sort(),
    ["asked", "connected", "link", "mx", "observer", "said"],
  );
  assert.deepEqual(new Set(allRows(r).map((x) => x.toolkit)), new Set([ALPHA]));
});

// ===========================================================================
// 3. DECAY AND RANK — "an app you stopped using stops coming up".
// ===========================================================================

await check("a decayed signal ranks BELOW a fresh one of the same band", async () => {
  const r = rig();
  seed(r, OWNER_A, ALPHA, "observer", WEIGHT_HIGH, NOW - 90 * DAY);
  seed(r, OWNER_A, BETA, "observer", WEIGHT_HIGH, NOW);
  const ranked = await rankedApps(r.store, OWNER_A, NOW);
  assert.deepEqual(ranked.map((l) => l.toolkit), [BETA, ALPHA]);
  // And the CONTROL: at the older row's OWN time the two are the same weight,
  // so it is decay doing this and not the alphabet.
  const atThen = await rankedApps(r.store, OWNER_A, NOW - 90 * DAY);
  assert.ok(
    Math.abs(atThen[0].weight - atThen[1].weight) < 1e-12,
    "without decay in play the two bands are equal",
  );
});

await check("THE CROSSOVER: one fresh MEDIUM outranks a HIGH from three months ago", async () => {
  const r = rig();
  seed(r, OWNER_A, ALPHA, "observer", WEIGHT_HIGH, NOW - 90 * DAY);
  seed(r, OWNER_A, BETA, "mx", WEIGHT_MEDIUM, NOW);
  const ranked = await rankedApps(r.store, OWNER_A, NOW);
  assert.equal(ranked[0].toolkit, BETA);
  // Three half-lives: 0.7 -> 0.0875, which is below a fresh 0.4.
  assert.ok(Math.abs(ranked[1].weight - WEIGHT_HIGH / 8) < 1e-9, String(ranked[1].weight));
});

await check("a CERTAIN signal does not decay, however old", async () => {
  const r = rig();
  seed(r, OWNER_A, ALPHA, "connected", WEIGHT_CERTAIN, NOW - 365 * DAY);
  seed(r, OWNER_A, BETA, "observer", WEIGHT_HIGH, NOW);
  const ranked = await rankedApps(r.store, OWNER_A, NOW);
  assert.equal(ranked[0].toolkit, ALPHA, "a connection a year old is still a connection");
  assert.equal(ranked[0].weight, WEIGHT_CERTAIN);
});

await check("decay is a half-life, and a future stamp is never amplified", () => {
  assert.equal(decayedWeight(1, NOW, NOW, HALF_LIFE), 1);
  assert.ok(Math.abs(decayedWeight(1, NOW - HALF_LIFE, NOW, HALF_LIFE) - 0.5) < 1e-12);
  assert.ok(Math.abs(decayedWeight(1, NOW - 2 * HALF_LIFE, NOW, HALF_LIFE) - 0.25) < 1e-12);
  // A handset with tomorrow's clock would otherwise own the top of the table.
  assert.equal(decayedWeight(1, NOW + 400 * DAY, NOW, HALF_LIFE), 1);
  // A broken half-life costs the freshness ordering, never the whole table.
  assert.equal(decayedWeight(1, NOW - 400 * DAY, NOW, 0), 1);
  assert.equal(decayedWeight(1, NOW - 400 * DAY, NOW, Number.NaN), 1);
});

await check("observations SUM: two runs are more evidence than one", async () => {
  const r = rig();
  await recordObservedHost(r.store, OWNER_A, "kit-alpha.example", CATALOG, NOW);
  await recordObservedHost(r.store, OWNER_A, "kit-alpha.example", CATALOG, NOW);
  assert.equal(allRows(r).length, 1, "one row per (owner, app, source, account)");
  assert.ok(Math.abs(allRows(r)[0].weight - 2 * WEIGHT_HIGH) < 1e-12, String(allRows(r)[0].weight));
});

await check("a LATE observation lands where it would have, not on top of history", async () => {
  const early = NOW - 60 * DAY;
  const inOrder = rig();
  await recordObservedHost(inOrder.store, OWNER_A, "kit-alpha.example", CATALOG, early);
  await recordObservedHost(inOrder.store, OWNER_A, "kit-alpha.example", CATALOG, NOW);
  const reversed = rig();
  await recordObservedHost(reversed.store, OWNER_A, "kit-alpha.example", CATALOG, NOW);
  await recordObservedHost(reversed.store, OWNER_A, "kit-alpha.example", CATALOG, early);
  assert.ok(
    Math.abs(allRows(inOrder)[0].weight - allRows(reversed)[0].weight) < 1e-12,
    "accumulation must not depend on arrival order",
  );
});

await check("STATE IS SET, NOT SUMMED: a replayed certainty changes nothing", async () => {
  const r = rig();
  for (let i = 0; i < 5; i++) await recordConnectedApp(r.store, OWNER_A, ALPHA, NOW + i);
  assert.equal(allRows(r).length, 1);
  assert.equal(
    allRows(r)[0].weight, WEIGHT_CERTAIN,
    "summed, a nightly sweep would make its own schedule the strongest signal an owner has",
  );
});

await check("one line per (app, account), carrying every source that fed it", async () => {
  const r = rig();
  await recordUserSaidIt(r.store, OWNER_A, TOOLKIT_VERDICT(ALPHA), NOW);
  await recordObservedHost(r.store, OWNER_A, "kit-alpha.example", CATALOG, NOW);
  const [line] = await rankedApps(r.store, OWNER_A, NOW);
  assert.deepEqual(line.sources, ["observer", "said"]);
  assert.ok(Math.abs(line.weight - 2 * WEIGHT_HIGH) < 1e-12);
  assert.equal(line.lastSeenAt, NOW);
});

await check("work and personal are two lines, and unattributed evidence is a third", async () => {
  const r = rig();
  await recordConnectedApp(r.store, OWNER_A, ALPHA, NOW, "work");
  await recordConnectedApp(r.store, OWNER_A, ALPHA, NOW, "personal");
  await recordObservedHost(r.store, OWNER_A, "kit-alpha.example", CATALOG, NOW, null);
  const ranked = await rankedApps(r.store, OWNER_A, NOW);
  assert.deepEqual(ranked.map((l) => l.alias), ["personal", "work", null]);
  assert.deepEqual(new Set(ranked.map((l) => l.toolkit)), new Set([ALPHA]));
});

await check("the ORDER is total and tie-broken by name, not by arrival", () => {
  // compareRankedApps reached DIRECTLY. Through rankRows alone this comparison
  // is unreachable — its input is pre-sorted for float determinism and the
  // sort is stable — so both tie-breaks were once deleted with an 890-check
  // suite still green.
  const line = (toolkit: string, alias: RankedApp["alias"], weight: number): RankedApp =>
    ({ toolkit, alias, weight, lastSeenAt: NOW, sources: [] });
  assert.ok(compareRankedApps(line("b-app", null, 1), line("a-app", null, 2)) > 0, "weight first");
  assert.ok(compareRankedApps(line("a-app", null, 1), line("b-app", null, 1)) < 0, "then the app");
  assert.ok(compareRankedApps(line("a-app", "personal", 1), line("a-app", "work", 1)) < 0,
    "then the account");
  assert.equal(compareRankedApps(line("a-app", "work", 1), line("a-app", "work", 1)), 0);
  // Two weights a few ulps apart are ONE weight, or the table reorders itself
  // under an owner nothing about whom has changed.
  assert.ok(compareRankedApps(line("a-app", null, 1), line("b-app", null, 1 + 1e-15)) < 0);
});

await check("the same evidence in any order ranks the same", async () => {
  const rows: StoredSignal[] = [
    { user_id: OWNER_A as never, toolkit: ALPHA, source: "said", alias: null,
      weight: WEIGHT_HIGH, last_seen_at: NOW - DAY },
    { user_id: OWNER_A as never, toolkit: BETA, source: "mx", alias: null,
      weight: WEIGHT_MEDIUM, last_seen_at: NOW },
    { user_id: OWNER_A as never, toolkit: ALPHA, source: "link", alias: "work",
      weight: WEIGHT_MEDIUM, last_seen_at: NOW },
  ];
  const forward = rankRows(OWNER_A, rows, NOW);
  const backward = rankRows(OWNER_A, [...rows].reverse(), NOW);
  assert.deepEqual(forward, backward);
});

await check("rankRows refuses a clock it cannot read", () => {
  assert.throws(() => rankRows(OWNER_A, [], Number.NaN), /finite epoch-ms/);
});

// ===========================================================================
// 4. TWO OWNERS NEVER SEE EACH OTHER'S ROWS.
// ===========================================================================

await check("one owner's ranked table holds only that owner's evidence", async () => {
  const r = rig();
  await recordObservedHost(r.store, OWNER_A, "kit-alpha.example", CATALOG, NOW);
  await recordObservedHost(r.store, OWNER_B, "kit-beta.example", CATALOG, NOW);
  assert.deepEqual((await rankedApps(r.store, OWNER_A, NOW)).map((l) => l.toolkit), [ALPHA]);
  assert.deepEqual((await rankedApps(r.store, OWNER_B, NOW)).map((l) => l.toolkit), [BETA]);
});

await check("recording for one owner never touches the other's row", async () => {
  const r = rig();
  await recordObservedHost(r.store, OWNER_A, "kit-alpha.example", CATALOG, NOW);
  await recordObservedHost(r.store, OWNER_B, "kit-alpha.example", CATALOG, NOW);
  const rows = allRows(r);
  assert.equal(rows.length, 2, "same app, same source, two owners, two rows");
  for (const row of rows) assert.equal(row.weight, WEIGHT_HIGH, "neither summed onto the other");
});

await check("THE FAN-OUT: two owners' rows in one call is refused, not filtered", () => {
  const mixed: StoredSignal[] = [
    { user_id: OWNER_A as never, toolkit: ALPHA, source: "said", alias: null,
      weight: 1, last_seen_at: NOW },
    { user_id: OWNER_B as never, toolkit: BETA, source: "said", alias: null,
      weight: 1, last_seen_at: NOW },
  ];
  assert.throws(() => rankRows(OWNER_A, mixed, NOW), /2 owners' rows at once/);
});

await check("THE SWAP: one owner's rows handed back for another owner is refused", () => {
  // The failure nothing in the rows can show: a WHERE bound to the wrong
  // variable, a cache keyed by the previous request. Without being told whose
  // table this is meant to be, ranking succeeds and the wrong person is texted
  // about somebody else's apps.
  const theirs: StoredSignal[] = [
    { user_id: OWNER_B as never, toolkit: BETA, source: "said", alias: null,
      weight: 1, last_seen_at: NOW },
  ];
  assert.throws(() => rankRows(OWNER_A, theirs, NOW), /handed owner .* rows/);
  // CONTROL: the same rows for their real owner rank fine.
  assert.equal(rankRows(OWNER_B, theirs, NOW)[0].toolkit, BETA);
});

await check("a name or an address is never an owner", async () => {
  const r = rig();
  for (const notAnId of ["omar", "someone@somewhere.example", "", "OWNERSIGAAAA111", "short"]) {
    await assert.rejects(
      () => recordConnectedApp(r.store, notAnId, ALPHA, NOW), /not an owner id/, notAnId,
    );
  }
  assert.deepEqual(allRows(r), []);
});

// ===========================================================================
// 5. RECORD — the guards on the way in.
// ===========================================================================

await check("record refuses a source nothing in the contract declares", async () => {
  const r = rig();
  await assert.rejects(
    () => record(r.store, {
      user_id: OWNER_A, toolkit: ALPHA, source: "vibes" as never, last_seen_at: NOW,
    }),
    /not a signal source/,
  );
  // `constructor` reaches the prototype through `in` and would come back
  // truthy with a weight of undefined, and one NaN poisons every sum.
  await assert.rejects(
    () => record(r.store, {
      user_id: OWNER_A, toolkit: ALPHA, source: "constructor" as never, last_seen_at: NOW,
    }),
    /not a signal source/,
  );
  assert.deepEqual(allRows(r), []);
});

await check("record refuses a weight that is zero, negative or unreadable", async () => {
  const r = rig();
  for (const weight of [0, -1, Number.NaN, Number.POSITIVE_INFINITY]) {
    await assert.rejects(
      () => record(r.store, {
        user_id: OWNER_A, toolkit: ALPHA, source: "said", last_seen_at: NOW, weight,
      }),
      /finite positive number/, String(weight),
    );
  }
  assert.deepEqual(allRows(r), [], "nothing is written when the arithmetic is refused");
});

await check("record refuses a timestamp it cannot read, and writes nothing", async () => {
  const r = rig();
  await assert.rejects(
    () => record(r.store, {
      user_id: OWNER_A, toolkit: ALPHA, source: "said", last_seen_at: Number.NaN,
    }),
    /finite epoch-ms/,
  );
  assert.deepEqual(allRows(r), []);
});

await check("record refuses an app it cannot name, and folds case", async () => {
  const r = rig();
  await assert.rejects(
    () => record(r.store, {
      user_id: OWNER_A, toolkit: "   ", source: "said", last_seen_at: NOW,
    }),
    /needs a toolkit slug/,
  );
  // Case and whitespace only. Two spellings of one slug would split an app's
  // evidence across two rows and sink both.
  await record(r.store, { user_id: OWNER_A, toolkit: " KIT-ALPHA ", source: "said", last_seen_at: NOW });
  await record(r.store, { user_id: OWNER_A, toolkit: ALPHA, source: "said", last_seen_at: NOW });
  assert.equal(allRows(r).length, 1);
});

await check("record refuses at its OWN door — the store is never reached", async () => {
  // Why this is a check of its own: the store re-guards every one of these,
  // so a test that only watches the table stays green with the guards here
  // deleted (measured: that mutation survived the whole suite). A tripwire
  // store makes the early refusal observable — nothing is computed, nothing
  // is read, and no compare-and-set loop is entered on a value that was
  // never going to be written.
  const tripwire: SignalStore = {
    async recordSignal() { throw new Error("TRIPWIRE: the store must not be reached"); },
    async signalsForOwner() { throw new Error("TRIPWIRE: the store must not be reached"); },
  };
  const base = { user_id: OWNER_A, toolkit: ALPHA, source: "said" as const, last_seen_at: NOW };
  await assert.rejects(() => record(tripwire, { ...base, user_id: "omar" }), /not an owner id/);
  await assert.rejects(() => record(tripwire, { ...base, toolkit: " " }), /needs a toolkit slug/);
  await assert.rejects(
    () => record(tripwire, { ...base, source: "vibes" as never }), /not a signal source/,
  );
  await assert.rejects(
    () => record(tripwire, { ...base, alias: "sideways" as never }), /not an account alias/,
  );
  await assert.rejects(
    () => record(tripwire, { ...base, last_seen_at: Number.NaN }), /finite epoch-ms/,
  );
  await assert.rejects(
    () => record(tripwire, { ...base, weight: -1 }), /finite positive number/,
  );
  // THE CONTROL, and it is the load-bearing half: a good input DOES reach the
  // store. Without it every assertion above is satisfied by a door that
  // refuses everything.
  await assert.rejects(() => record(tripwire, base), /TRIPWIRE/);
});

await check("signalMerge is the arithmetic, and it is reachable on its own", () => {
  const sum = signalMerge(
    { user_id: OWNER_A, toolkit: ALPHA, source: "observer", last_seen_at: NOW }, HALF_LIFE,
  );
  assert.deepEqual(sum(null), { weight: WEIGHT_HIGH, last_seen_at: NOW });
  const prior: StoredSignal = {
    user_id: OWNER_A as never, toolkit: ALPHA, source: "observer", alias: null,
    weight: WEIGHT_HIGH, last_seen_at: NOW - HALF_LIFE,
  };
  const merged = sum(prior);
  assert.ok(Math.abs(merged.weight - (WEIGHT_HIGH / 2 + WEIGHT_HIGH)) < 1e-12, String(merged.weight));
  assert.equal(merged.last_seen_at, NOW);
});

// ===========================================================================
// 6. THE SWEEP — the one door whose input production already produces.
// ===========================================================================

await check("CONTROL: a connected account becomes exactly one CERTAIN signal", async () => {
  const r = rig();
  connection(r, OWNER_A, ALPHA, "connected", "work");
  const out = await sweepConnectedSignals(r.env, NOW);
  assert.deepEqual(out, { scanned: 1, recorded: 1, dropped: 0 });
  assert.deepEqual(
    allRows(r).map((x) => [x.user_id, x.toolkit, x.source, x.alias, x.weight, x.last_seen_at]),
    [[OWNER_A, ALPHA, "connected", "work", WEIGHT_CERTAIN, NOW]],
  );
});

await check("an account that is NOT connected produces nothing", async () => {
  const r = rig();
  connection(r, OWNER_A, ALPHA, "disconnected");
  connection(r, OWNER_A, BETA, "needs_reconnect");
  const out = await sweepConnectedSignals(r.env, NOW);
  assert.deepEqual(out, { scanned: 0, recorded: 0, dropped: 0 });
  assert.deepEqual(allRows(r), []);
});

await check("the sweep is idempotent: a second night changes nothing", async () => {
  const r = rig();
  connection(r, OWNER_A, ALPHA, "connected");
  await sweepConnectedSignals(r.env, NOW);
  const second = await sweepConnectedSignals(r.env, NOW + DAY);
  assert.deepEqual(second, { scanned: 0, recorded: 0, dropped: 0 }, "already-evidenced rows drop out");
  assert.equal(allRows(r).length, 1);
  assert.equal(allRows(r)[0].weight, WEIGHT_CERTAIN, "a hundred sweeps is not a weight of a hundred");
  assert.equal(allRows(r)[0].last_seen_at, NOW);
});

await check("NOBODY STARVES AT THE TAIL: a capped sweep drains over ticks", async () => {
  const r = rig();
  connection(r, OWNER_A, ALPHA, "connected");
  connection(r, OWNER_A, BETA, "connected");
  connection(r, OWNER_B, ALPHA, "connected");
  const first = await sweepConnectedSignals(r.env, NOW, { cap: 1 });
  assert.equal(first.recorded, 1);
  const second = await sweepConnectedSignals(r.env, NOW, { cap: 1 });
  assert.equal(second.recorded, 1);
  const third = await sweepConnectedSignals(r.env, NOW, { cap: 1 });
  assert.equal(third.recorded, 1);
  // Three ticks, three DIFFERENT rows. A cap over a stable ORDER BY with no
  // "not yet evidenced" clause would have done row one three times.
  assert.equal(allRows(r).length, 3);
  assert.deepEqual((await sweepConnectedSignals(r.env, NOW, { cap: 1 })).recorded, 0);
});

await check("the same app on two accounts is two piles of evidence", async () => {
  const r = rig();
  connection(r, OWNER_A, ALPHA, "connected", "work", "ca_one");
  connection(r, OWNER_A, ALPHA, "connected", "personal", "ca_two");
  await sweepConnectedSignals(r.env, NOW);
  assert.deepEqual(allRows(r).map((x) => x.alias), ["personal", "work"]);
});

await check("the sweep never crosses owners", async () => {
  const r = rig();
  connection(r, OWNER_A, ALPHA, "connected");
  connection(r, OWNER_B, BETA, "connected");
  await sweepConnectedSignals(r.env, NOW);
  assert.deepEqual(
    allRows(r).map((x) => [x.user_id, x.toolkit]),
    [[OWNER_A, ALPHA], [OWNER_B, BETA]],
  );
});

await check("an unmigrated database REFUSES by name; it does not report an empty product",
  async () => {
    const r = rig({ schema: false });
    await assert.rejects(() => sweepConnectedSignals(r.env, NOW), (err: unknown) => {
      assert.ok(err instanceof ConnectionsSchemaMissing, String(err));
      assert.match((err as Error).message, /schema\.sql/);
      return true;
    });
  });

await check("the sweep refuses a clock and a cap it cannot read", async () => {
  const r = rig();
  await assert.rejects(() => sweepConnectedSignals(r.env, Number.NaN), /finite epoch-ms/);
  await assert.rejects(() => sweepConnectedSignals(r.env, NOW, { cap: -1 }), /as its cap/);
  await assert.rejects(
    () => sweepConnectedSignals(r.env, NOW, { cap: Number.NaN }), /as its cap/,
  );
});

await check("a malformed row is DROPPED, and the rest are still recorded", async () => {
  // The real schema's CHECKs make this row impossible to insert, which is why
  // the database is stubbed for exactly this leg: the guard exists for a live
  // table that predates the CHECK, or a column renamed under us.
  const written: SignalKey[] = [];
  const store: SignalStore = {
    async recordSignal(key, merge) {
      written.push(key);
      const m = merge(null);
      return { ...key, alias: key.alias ?? null, ...m } as StoredSignal;
    },
    async signalsForOwner() { return []; },
  };
  const rows = [
    { user_id: "omar", toolkit: ALPHA, alias: "" },          // not an owner id
    { user_id: OWNER_A, toolkit: "", alias: "" },            // no app
    { user_id: OWNER_A, toolkit: ALPHA, alias: "sideways" }, // not an account
    { user_id: OWNER_A, toolkit: BETA, alias: "" },          // fine
  ];
  const env = {
    DB: {
      prepare(sql: string) {
        const stmt = {
          bound: [] as unknown[],
          bind(...a: unknown[]) { stmt.bound = a; return stmt; },
          async all() {
            if (/pragma_table_info/.test(sql)) {
              const table = String(stmt.bound[0]);
              const cols = table === "connections"
                ? ["user_id", "toolkit", "status", "alias"]
                : ["user_id", "toolkit", "source", "weight", "last_seen_at", "alias"];
              return { results: cols.map((name) => ({ name })) };
            }
            return { results: rows };
          },
          async first() { return null; },
          async run() { return { meta: { changes: 1 } }; },
        };
        return stmt;
      },
    },
  } as unknown as StoreEnv;

  const out = await sweepConnectedSignals(env, NOW, { signalStore: store });
  assert.deepEqual(out, { scanned: 4, recorded: 1, dropped: 3 });
  assert.equal(written.length, 1);
  assert.equal(written[0].toolkit, BETA);
  assert.ok(
    logs.some((l) => l.includes("not an owner id")),
    "a dropped row says so in the log; a silent drop is evidence lost with a green line",
  );
});

await check("the bound seam wires the six doors and the sweep to one database", async () => {
  const r = rig();
  const signals = createSignals(r.env);
  connection(r, OWNER_A, DELTA, "connected");
  await signals.said(OWNER_A, TOOLKIT_VERDICT(ALPHA), NOW);
  await signals.observedHost(OWNER_A, "kit-alpha.example", CATALOG, NOW);
  await signals.signUpDomain(OWNER_A, { emailDomain: "kit-beta.example" }, CATALOG, NOW);
  await signals.links(OWNER_A, ["https://kit-beta.example/x"], CATALOG, NOW);
  await signals.connected(OWNER_A, ALPHA, NOW);
  await signals.answered(OWNER_A, BETA, NOW);
  await signals.sweepConnected(NOW);
  assert.deepEqual(
    allRows(r).map((x) => x.source).sort(),
    ["asked", "connected", "connected", "link", "mx", "observer", "said"],
  );
  const ranked = await signals.rank(OWNER_A, NOW);
  assert.deepEqual(ranked.map((l) => l.toolkit), [ALPHA, BETA, DELTA]);
});

await check("the cap is a bound on one tick's work, not a limit on the product", () => {
  assert.ok(Number.isInteger(CONNECTED_SWEEP_CAP) && CONNECTED_SWEEP_CAP > 0);
});

// ===========================================================================
// 7. HARNESS-LAWS LAW 1 — signals.ts may not know an app, a host, or a phrase.
// ===========================================================================

/** Comments stripped so the load-bearing leg reads CODE. The whole-file legs
 *  then catch the same names in prose, because a comment naming an app is
 *  where the next agent's branch keyed on it gets its idea. */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/(^|[^:])\/\/[^\n]*/g, "$1");
}

/** Comments AND string literals gone, so a scan for regex literals cannot
 *  mistake the slashes in an import path for one. */
function codeOnly(src: string): string {
  return stripComments(src)
    .replace(/"(?:\\.|[^"\\])*"/g, '""')
    .replace(/'(?:\\.|[^'\\])*'/g, "''")
    .replace(/`(?:\\.|[^`\\])*`/g, "``");
}

// The only list of app names this module's world is allowed to contain, and it
// lives in a TEST because law 1 permits pattern matching in gates.
const APP_NAMES = [
  "gmail", "googlecalendar", "google", "outlook", "slack", "notion", "github",
  "gitlab", "linear", "asana", "trello", "jira", "confluence", "salesforce",
  "hubspot", "stripe", "shopify", "twilio", "sendgrid", "airtable", "dropbox",
  "box", "zoom", "discord", "figma", "intercom", "zendesk", "quickbooks",
  "xero", "calendly", "docusign", "mailchimp", "clickup", "monday", "chrome",
  "whatsapp", "telegram", "instagram", "facebook", "twitter", "linkedin",
  "amazon", "uber", "doordash", "opentable", "spotify", "apple", "microsoft",
];

// Likewise the only list of top-level names. A host literal in this module is
// the hardcoding the spec forbids, said in the one dialect that looks
// harmless: not `if (app === "…")` but `host.endsWith("…")`, which is the same
// branch wearing a hostname.
const TLDS = [
  "com", "net", "org", "io", "ai", "co", "so", "dev", "app", "xyz", "me", "tv",
  "us", "uk", "ca", "de", "fr", "jp", "cn", "ru", "br", "au", "nl", "se", "es",
  "pl", "ch", "info", "biz", "cloud", "site", "online", "store", "shop", "tech",
  "space", "website", "live", "link", "email", "chat", "team", "works", "gov",
  "edu", "eu", "asia", "mobi", "example",
];
const HOST_SHAPED = new RegExp(String.raw`\b[a-z0-9][a-z0-9-]*\.(?:${TLDS.join("|")})\b`, "gi");

await check("law 1: signals.ts contains no host literal", () => {
  const hits = [...SRC.matchAll(HOST_SHAPED)].map((m) => m[0]);
  assert.deepEqual(hits, [], `signals.ts contains host literals: ${hits.join(", ")}`);
  // A gate that cannot go red is a decoration. The red-check builds its OWN
  // copy of the pattern: a global regex carries `lastIndex` between calls, and
  // a leg whose second use starts mid-string passes by accident.
  const scan = new RegExp(HOST_SHAPED.source, "i");
  assert.ok(scan.test('if (host.endsWith("mail.example.com")) return "kit";'), "the scan is blind");
});

await check("law 1: signals.ts names no app, in code or in prose", () => {
  const code = stripComments(SRC).toLowerCase();
  const inCode = APP_NAMES.filter((n) => new RegExp(`\\b${n}\\b`).test(code));
  assert.deepEqual(inCode, [], `signals.ts names apps in code: ${inCode.join(", ")}`);
  const whole = SRC.toLowerCase();
  const anywhere = APP_NAMES.filter((n) => new RegExp(`\\b${n}\\b`).test(whole));
  assert.deepEqual(anywhere, [], `signals.ts names apps in prose: ${anywhere.join(", ")}`);
  assert.ok(APP_NAMES.some((n) => new RegExp(`\\b${n}\\b`).test("put it in my notion")),
    "the app scan is blind");
});

await check("law 1: signals.ts never says the vendor's name or the register the user never hears",
  () => {
    // words.ts owns FORBIDDEN_TERMS for user-visible copy. This file emits no
    // copy at all, and the cheapest way to keep it that way is to hold it to
    // the same register: a module that has started saying these words is a
    // module that has started writing sentences somebody will read.
    const whole = SRC.toLowerCase();
    const banned = ["composio", "oauth", "authorize", "authorise", "permissions"];
    const hits = banned.filter((t) => new RegExp(`(?<![a-z0-9])${t}(?![a-z0-9])`).test(whole));
    assert.deepEqual(hits, [], `signals.ts uses the vendor's register: ${hits.join(", ")}`);
  });

await check("law 1: every regex in signals.ts is over a closed shape, never over prose", () => {
  // The whole file's regex literals, enumerated. Two of them, both structural:
  // characters a bare host cannot contain, and an all-digits label. A THIRD
  // one appearing is the shape a word list arrives in, and this leg makes
  // adding one a conversation rather than a commit.
  const code = codeOnly(SRC);
  const literals = [...code.matchAll(/\/(?![/*])(?:\\.|\[(?:\\.|[^\]])*\]|[^/\n\\])+\/[gimsuy]*/g)]
    .map((m) => m[0]);
  assert.deepEqual(
    literals.sort(), ["/[\\s/@?#]/", "/^[0-9]+$/"].sort(),
    `signals.ts has a regex this test has not seen: ${literals.join(" ")}`,
  );
});

await check("law 1: the judge's verdict is an INPUT — no door takes a sentence", () => {
  // Behavioural, not textual. `saidSignal` cannot be handed a phrase: its
  // second argument is the verdict, and a string in that position is not a
  // verdict and records nothing. That is the property that survives a rename.
  assert.equal(saidSignal(OWNER_A, "put it in my kit-alpha" as unknown as ToolkitVerdict, NOW), null);
  assert.equal(saidSignal(OWNER_A, ALPHA as unknown as ToolkitVerdict, NOW), null);
});

// ===========================================================================
// 8. LAW 3 — where this file is, and is not, wired.
// ===========================================================================

await check("this suite is in CI", () => {
  // Five suites were written and left out of the test script this week; each
  // time hundreds of checks silently did not run.
  const pkg = readFileSync(join(here, "..", "package.json"), "utf8");
  assert.ok(
    pkg.includes("test/connections-signals.test.ts"),
    "connections-signals.test.ts is not in package.json's test script",
  );
});

await check("the sweep has no home nobody expected", () => {
  // MEASURED 2026-09-06: `sweepConnectedSignals` has zero callers, exactly as
  // `installNudgeWiring` did the day the /c/ routes shipped, and exactly as
  // `installConnectWiring` did the day before that. Its one call site is a
  // line on the nightly leg src/cron.ts already dispatches and production
  // already registers. This leg does not demand that line — another agent owns
  // that file — but it does refuse a SECOND home: evidence-gathering on a
  // request path is latency spent by somebody who is waiting.
  const cron = readFileSync(join(here, "..", "src", "cron.ts"), "utf8");
  const index = readFileSync(join(here, "..", "src", "index.ts"), "utf8");
  assert.ok(
    !index.includes("sweepConnectedSignals"),
    "the connected-signal sweep belongs on the cron leg, not on a request path",
  );
  // A sentence for whoever wires it: the call is
  // `await sweepConnectedSignals(env, Date.now());` and the header of
  // signals.ts says why the nightly leg is the right one.
  assert.ok(typeof cron === "string" && cron.length > 0);
});

// ===========================================================================
// 9. THE MUTATION LIST — each anchor asserted UNIQUE, because an anchor that
//    matches nothing produces a false "it is tested" reading.
// ===========================================================================

await check("every mutation anchor occurs exactly once in signals.ts", () => {
  const anchors: Array<[string, string]> = [
    // [anchor, the check that must go red when it is mutated]
    ["  connected: false,", "a CERTAIN signal does not decay, however old"],
    ["Math.max(carried, arriving)", "STATE IS SET, NOT SUMMED"],
    ['if (relation === "catalog-under-observed")', "a host that merely CONTAINS one catalog entry"],
    ['if (!verdict || verdict.kind !== "toolkit") return null;', "an unreadable verdict records NOTHING"],
    ["if (a.toolkit !== b.toolkit) return a.toolkit < b.toolkit ? -1 : 1;", "the ORDER is total"],
    ["`rankRows was asked for owner ${expected}", "THE SWAP"],
    [`c."status" = 'connected'`, "an account that is NOT connected produces nothing"],
    ['AND s."source"  = \'connected\')', "the sweep is idempotent"],
    ["export const WEIGHT_MEDIUM = 0.4;", "the three bands are the spec's own"],
    ["alias: null });", "an exchanger never guesses which of the owner's accounts it is"],
    ["  const user = checkedOwner(input?.user_id);", "record refuses at its OWN door"],
  ];
  for (const [anchor, why] of anchors) {
    const count = SRC.split(anchor).length - 1;
    assert.equal(count, 1, `anchor for "${why}" occurs ${count} times, not once: ${anchor}`);
  }
});

// ---------------------------------------------------------------------------

console.log = realLog;
console.log(`connections-signals: ${passes} checks passed, ${failures} failed`);
if (failures > 0) process.exit(1);
