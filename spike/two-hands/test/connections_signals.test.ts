// SIGNALS TESTS — decay as BEHAVIOUR, plus the two legs behaviour cannot catch.
//
// No network, no key, no account: every fixture below is a plain object built
// in this file. The catalog entries are deliberate nonsense — `kit-alpha` at
// `alpha.vendor-one.example` — so that a module which had quietly learned a
// real app's name or a real domain could not pass these tests even by accident,
// and so that renaming every slug in the catalog is a total substitution.
//
// THE LEGS THAT ARE NOT BEHAVIOUR TESTS are the last two: signals.ts is read
// back as text and fails if it contains a domain literal or an app name. Both
// are invisible to every behaviour test here — a module with one hardcoded
// domain passes all of them and is wrong for exactly one owner, on exactly one
// app, in production. HARNESS-LAWS law 1 permits pattern matching in "gates and
// evals", which is what those two legs are, and this file is the only place in
// this module's world where a list of app names or of domains may exist.

import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

import {
  DEFAULT_HALF_LIFE_MS,
  SOURCE_DECAYS,
  SOURCE_WEIGHT,
  createSignalTable,
  decayedWeight,
  hostToToolkit,
  observedHostSignal,
  rankRows,
  saidSignal,
} from "../src/connections/signals.ts";
import type { HostMatch, RankedApp, StoredSignal } from "../src/connections/signals.ts";
import { ownerId } from "../src/connections/contract.ts";
import type { ToolkitMeta, ToolkitVerdict } from "../src/connections/contract.ts";

// ---------------------------------------------------------------------------
// Fixtures.
// ---------------------------------------------------------------------------

// Two real owner-shaped ids. Fifteen lowercase alphanumerics, per the contract.
const OWNER = ownerId("sxkotd1h02qb6gw");
const OTHER_OWNER = ownerId("qeuy6sv1raof9rw");

const DAY = 24 * 60 * 60 * 1000;
const NOW = 1_757_000_000_000;

function meta(slug: string, appUrl: string | null): ToolkitMeta {
  return { slug, name: `${slug} (display name)`, logo: null, description: null, appUrl, scopes: [] };
}

// The catalog every host test reads. Nothing here is a real product:
//   - `kit-alpha` and `kit-beta` are two apps from ONE vendor, sharing a
//     registrable domain. That is the shape a host reduced to eTLD+1 cannot
//     tell apart, and it is the normal case, not an exotic one.
//   - `kit-gamma` is a one-app vendor whose url IS its registrable domain.
//   - `kit-delta` has no url at all, and `kit-epsilon`'s is not a url.
const CATALOG: ToolkitMeta[] = [
  meta("kit-alpha", "https://alpha.vendor-one.example/"),
  meta("kit-beta", "https://beta.vendor-one.example/product"),
  meta("kit-gamma", "https://vendor-two.example"),
  meta("kit-delta", null),
  meta("kit-epsilon", "not a url at all"),
];

function slugsOf(ranked: RankedApp[]): string[] {
  return ranked.map((r) => r.toolkit);
}

// ---------------------------------------------------------------------------
// DECAY — the property the whole table rests on.
// ---------------------------------------------------------------------------

test("decay: a fresh medium signal outranks a high one that went stale", () => {
  // The spec's promise in one assertion: an app they stopped using stops coming
  // up. Without decay the HIGH source wins forever and the top of the table is
  // a fossil of whatever they used first.
  const t = createSignalTable();
  t.record({ user_id: OWNER, toolkit: "kit-old", source: "observer", last_seen_at: NOW - 120 * DAY });
  t.record({ user_id: OWNER, toolkit: "kit-new", source: "link", last_seen_at: NOW - 1 * DAY });

  assert.deepEqual(slugsOf(t.rank(OWNER, NOW)), ["kit-new", "kit-old"]);
});

test("decay: the same two signals rank the other way round while the high one is fresh", () => {
  // The mirror of the test above, and the reason it means something: the order
  // flips because of the CLOCK, not because "link" is permanently worth more.
  // A module that had simply mis-ordered the weight bands would pass one of
  // these two tests and fail this one.
  const t = createSignalTable();
  t.record({ user_id: OWNER, toolkit: "kit-old", source: "observer", last_seen_at: NOW - 120 * DAY });
  t.record({ user_id: OWNER, toolkit: "kit-new", source: "link", last_seen_at: NOW - 1 * DAY });

  assert.deepEqual(slugsOf(t.rank(OWNER, NOW - 119 * DAY)), ["kit-old", "kit-new"]);
});

test("decay: one half-life halves a weight, and the half-life is a parameter", () => {
  assert.equal(decayedWeight(1, NOW - DEFAULT_HALF_LIFE_MS, NOW), 0.5);
  assert.equal(decayedWeight(1, NOW - 2 * DEFAULT_HALF_LIFE_MS, NOW), 0.25);
  assert.equal(decayedWeight(1, NOW - DAY, NOW, DAY), 0.5);
  assert.equal(decayedWeight(1, NOW, NOW), 1);
});

test("decay: a signal stamped in the future is not amplified", () => {
  // A phone with a wrong clock, or a backfill with a bad column. Amplification
  // is the dangerous direction: one row dated next week would otherwise own the
  // top of the table outright and every ask this owner ever gets.
  assert.equal(decayedWeight(1, NOW + 400 * DAY, NOW), 1);
});

test("decay: a broken half-life loses the freshness ordering, never the whole table", () => {
  // A zero would be a division by zero and a NaN in every row; a negative would
  // grow every weight without bound. Both turn a config mistake into an empty
  // or an insane table, which is far worse than an un-decayed one.
  for (const bad of [0, -1, Number.NaN, Number.POSITIVE_INFINITY]) {
    assert.equal(decayedWeight(3, NOW - 90 * DAY, NOW, bad), 3, `half-life ${bad}`);
  }
});

test("decay: the certain sources do not decay, so a connected app never sinks", () => {
  // `connected` and `asked` are facts about our own records, not observations
  // that go stale. If they decayed, an app connected a year ago would sink
  // under an app touched last week and the caller reading the top of the table
  // would text somebody asking them to connect a thing they already connected.
  assert.equal(SOURCE_DECAYS.connected, false);
  assert.equal(SOURCE_DECAYS.asked, false);

  const t = createSignalTable();
  t.record({ user_id: OWNER, toolkit: "kit-connected", source: "connected", last_seen_at: NOW - 365 * DAY });
  t.record({ user_id: OWNER, toolkit: "kit-fresh", source: "said", last_seen_at: NOW });

  assert.deepEqual(slugsOf(t.rank(OWNER, NOW)), ["kit-connected", "kit-fresh"]);
});

test("decay: the observational sources all decay", () => {
  for (const source of ["said", "observer", "mx", "link"] as const) {
    assert.equal(SOURCE_DECAYS[source], true, `${source} must decay`);
  }
});

// ---------------------------------------------------------------------------
// ACCUMULATION — "each signal ADDS weight".
// ---------------------------------------------------------------------------

test("record: repeated evidence accumulates instead of overwriting", () => {
  const t = createSignalTable();
  const once = t.record({ user_id: OWNER, toolkit: "kit-a", source: "observer", last_seen_at: NOW });
  assert.equal(once.weight, SOURCE_WEIGHT.observer);

  const twice = t.record({ user_id: OWNER, toolkit: "kit-a", source: "observer", last_seen_at: NOW });
  assert.equal(twice.weight, 2 * SOURCE_WEIGHT.observer);
  assert.equal(t.rows(OWNER).length, 1, "one row per (owner, toolkit, alias, source)");
});

test("record: a late-arriving signal lands where it belongs, not on top", () => {
  // Same two signals, opposite arrival order — a queued browser trace, a
  // backfill. If the second one simply overwrote the timestamp, an app's whole
  // history would collapse to whichever row happened to be written last.
  const early = createSignalTable();
  early.record({ user_id: OWNER, toolkit: "kit-a", source: "said", last_seen_at: NOW - 60 * DAY });
  const forwards = early.record({ user_id: OWNER, toolkit: "kit-a", source: "said", last_seen_at: NOW });

  const late = createSignalTable();
  late.record({ user_id: OWNER, toolkit: "kit-a", source: "said", last_seen_at: NOW });
  const backwards = late.record({ user_id: OWNER, toolkit: "kit-a", source: "said", last_seen_at: NOW - 60 * DAY });

  assert.equal(forwards.weight, backwards.weight);
  assert.equal(forwards.last_seen_at, backwards.last_seen_at);
  assert.equal(forwards.weight, SOURCE_WEIGHT.said * (1 + Math.pow(2, -2)));
});

test("record: different sources for one app are separate rows that sum in the rank", () => {
  const t = createSignalTable();
  t.record({ user_id: OWNER, toolkit: "kit-a", source: "said", last_seen_at: NOW });
  t.record({ user_id: OWNER, toolkit: "kit-a", source: "mx", last_seen_at: NOW });

  assert.equal(t.rows(OWNER).length, 2);
  const [line] = t.rank(OWNER, NOW);
  assert.equal(line.weight, SOURCE_WEIGHT.said + SOURCE_WEIGHT.mx);
  assert.deepEqual(line.sources, ["mx", "said"], "sources are reported sorted, for the caller to filter on");
});

test("record: a slug is normalised, so one app cannot split into two rows", () => {
  const t = createSignalTable();
  t.record({ user_id: OWNER, toolkit: "kit-a", source: "said", last_seen_at: NOW });
  t.record({ user_id: OWNER, toolkit: "  KIT-A ", source: "said", last_seen_at: NOW });
  assert.equal(t.rows(OWNER).length, 1);
  assert.equal(t.rank(OWNER, NOW)[0].weight, 2 * SOURCE_WEIGHT.said);
});

test("record: a state source is set, not summed, so a sync loop cannot inflate it", () => {
  // Whatever job syncs connections from the provider records `connected` on
  // every pass. Summed, a hundred passes is a weight of a hundred and one
  // background schedule becomes the strongest signal this owner has.
  const t = createSignalTable();
  for (let i = 0; i < 100; i += 1) {
    t.record({ user_id: OWNER, toolkit: "kit-a", source: "connected", last_seen_at: NOW - i * DAY });
  }
  const [row] = t.rows(OWNER);
  assert.equal(row.weight, SOURCE_WEIGHT.connected);
  assert.equal(row.last_seen_at, NOW, "the newest sighting still moves the timestamp");
});

test("record: the half-life is configuration, not a constant in the code", () => {
  // The number is tuned from what converts. A table built with a one-day
  // half-life must actually decay in days.
  const fast = createSignalTable({ halfLifeMs: DAY });
  fast.record({ user_id: OWNER, toolkit: "kit-old", source: "observer", last_seen_at: NOW - 5 * DAY });
  fast.record({ user_id: OWNER, toolkit: "kit-new", source: "link", last_seen_at: NOW });
  assert.deepEqual(slugsOf(fast.rank(OWNER, NOW)), ["kit-new", "kit-old"]);

  const slow = createSignalTable({ halfLifeMs: 3650 * DAY });
  slow.record({ user_id: OWNER, toolkit: "kit-old", source: "observer", last_seen_at: NOW - 5 * DAY });
  slow.record({ user_id: OWNER, toolkit: "kit-new", source: "link", last_seen_at: NOW });
  assert.deepEqual(slugsOf(slow.rank(OWNER, NOW)), ["kit-old", "kit-new"]);
});

// ---------------------------------------------------------------------------
// RANK — deterministic, per-owner, and account-aware.
// ---------------------------------------------------------------------------

test("rank: the order does not depend on the order rows arrived", () => {
  // A rank that depends on storage order is a rank that changes under the owner
  // without anything about the owner changing.
  const rows: StoredSignal[] = [
    { user_id: OWNER, toolkit: "kit-c", source: "link", weight: 0.4, last_seen_at: NOW - 3 * DAY, alias: null },
    { user_id: OWNER, toolkit: "kit-a", source: "said", weight: 0.7, last_seen_at: NOW - DAY, alias: null },
    { user_id: OWNER, toolkit: "kit-b", source: "mx", weight: 0.4, last_seen_at: NOW - 3 * DAY, alias: null },
    { user_id: OWNER, toolkit: "kit-a", source: "observer", weight: 0.7, last_seen_at: NOW - 2 * DAY, alias: null },
  ];
  const forwards = rankRows(rows, NOW);
  const backwards = rankRows([...rows].reverse(), NOW);
  const shuffled = rankRows([rows[2], rows[0], rows[3], rows[1]], NOW);

  assert.deepEqual(forwards, backwards);
  assert.deepEqual(forwards, shuffled);
  assert.equal(forwards[0].toolkit, "kit-a");
});

test("rank: an exact tie is broken by name, never by arrival", () => {
  const rows: StoredSignal[] = [
    { user_id: OWNER, toolkit: "kit-z", source: "said", weight: 0.7, last_seen_at: NOW, alias: null },
    { user_id: OWNER, toolkit: "kit-a", source: "said", weight: 0.7, last_seen_at: NOW, alias: null },
    { user_id: OWNER, toolkit: "kit-m", source: "said", weight: 0.7, last_seen_at: NOW, alias: null },
  ];
  assert.deepEqual(slugsOf(rankRows(rows, NOW)), ["kit-a", "kit-m", "kit-z"]);
  assert.deepEqual(slugsOf(rankRows([...rows].reverse(), NOW)), ["kit-a", "kit-m", "kit-z"]);
});

test("rank: floating-point dust does not reorder two equal lines", () => {
  // 0.1 + 0.2 is not 0.3, and the same evidence summed in two orders lands a
  // few ulps apart. Without the tie epsilon the table would flip between two
  // renderings of the same data.
  const rows: StoredSignal[] = [
    { user_id: OWNER, toolkit: "kit-z", source: "said", weight: 0.1, last_seen_at: NOW, alias: null },
    { user_id: OWNER, toolkit: "kit-z", source: "mx", weight: 0.2, last_seen_at: NOW, alias: null },
    { user_id: OWNER, toolkit: "kit-a", source: "link", weight: 0.3, last_seen_at: NOW, alias: null },
  ];
  const ranked = rankRows(rows, NOW);
  assert.notEqual(ranked[0].weight, ranked[1].weight, "the fixture must actually produce dust");
  assert.deepEqual(slugsOf(ranked), ["kit-a", "kit-z"]);
});

test("rank: work and personal are carried separately, and an unattributed signal is neither", () => {
  // The spec's normal case is one person holding the same app twice. Merging
  // them would produce an ask that cannot name the account; folding the
  // unattributed row into one of them would be this module INVENTING which
  // account somebody meant.
  const t = createSignalTable();
  t.record({ user_id: OWNER, toolkit: "kit-a", source: "said", last_seen_at: NOW, alias: "work" });
  t.record({ user_id: OWNER, toolkit: "kit-a", source: "said", last_seen_at: NOW, alias: "work" });
  t.record({ user_id: OWNER, toolkit: "kit-a", source: "said", last_seen_at: NOW, alias: "personal" });
  t.record({ user_id: OWNER, toolkit: "kit-a", source: "observer", last_seen_at: NOW });

  const ranked = t.rank(OWNER, NOW);
  assert.deepEqual(
    ranked.map((r) => [r.toolkit, r.alias, Number(r.weight.toFixed(6))]),
    [
      ["kit-a", "work", 2 * SOURCE_WEIGHT.said],
      ["kit-a", null, SOURCE_WEIGHT.observer],
      ["kit-a", "personal", SOURCE_WEIGHT.said],
    ],
  );
});

test("rank: one owner's evidence never reaches another owner's table", () => {
  // The worst failure available in this whole layer is binding a connection to
  // the wrong person. It starts one table earlier, here.
  const t = createSignalTable();
  t.record({ user_id: OWNER, toolkit: "kit-mine", source: "said", last_seen_at: NOW });
  t.record({ user_id: OTHER_OWNER, toolkit: "kit-theirs", source: "connected", last_seen_at: NOW });

  assert.deepEqual(slugsOf(t.rank(OWNER, NOW)), ["kit-mine"]);
  assert.deepEqual(slugsOf(t.rank(OTHER_OWNER, NOW)), ["kit-theirs"]);
  assert.deepEqual(t.rank(ownerId("aaaaaaaaaaaaaaa"), NOW), [], "an owner with no evidence has an empty table");
});

test("rank: two owners' rows in one call is refused, not summed", () => {
  // `rankRows` is exported and production feeds it a query result. A dropped
  // `WHERE user_id = ?` would arrive here as two people's evidence, and a
  // silent merge would ask one owner about another owner's apps.
  const mixed: StoredSignal[] = [
    { user_id: OWNER, toolkit: "kit-a", source: "said", weight: 0.7, last_seen_at: NOW, alias: null },
    { user_id: OTHER_OWNER, toolkit: "kit-b", source: "said", weight: 0.7, last_seen_at: NOW, alias: null },
  ];
  assert.throws(() => rankRows(mixed, NOW), /owners/i);
  assert.deepEqual(slugsOf(rankRows([mixed[0]], NOW)), ["kit-a"]);
  assert.deepEqual(rankRows([], NOW), []);
});

test("rank: a line reports its newest signal so a caller need not re-read the rows", () => {
  const t = createSignalTable();
  t.record({ user_id: OWNER, toolkit: "kit-a", source: "said", last_seen_at: NOW - 40 * DAY });
  t.record({ user_id: OWNER, toolkit: "kit-a", source: "mx", last_seen_at: NOW - 2 * DAY });
  assert.equal(t.rank(OWNER, NOW)[0].lastSeenAt, NOW - 2 * DAY);
});

test("rank: the returned rows are copies, so a caller cannot edit the table by accident", () => {
  const t = createSignalTable();
  t.record({ user_id: OWNER, toolkit: "kit-a", source: "said", last_seen_at: NOW });
  const rows = t.rows(OWNER);
  rows[0].weight = 999;
  assert.equal(t.rank(OWNER, NOW)[0].weight, SOURCE_WEIGHT.said);
});

// ---------------------------------------------------------------------------
// RUNTIME GUARDS — types are stripped, so these must be real.
// ---------------------------------------------------------------------------

test("guard: a name or an email where an owner id belongs is refused", () => {
  // This is the spike's own recorded failure: `user_id` was `omar`, a name, and
  // one mailbox served everybody. A stripped type would have caught none of it.
  const t = createSignalTable();
  for (const bad of ["omar", "someone@an.address", "", "SXKOTD1H02QB6GW", "sxkotd1h02qb6g"]) {
    assert.throws(
      () => t.record({ user_id: bad as never, toolkit: "kit-a", source: "said", last_seen_at: NOW }),
      /owner/i,
      `accepted ${JSON.stringify(bad)} as an owner id`,
    );
  }
  assert.throws(() => t.rank("omar" as never, NOW), /owner/i);
  assert.throws(() => t.rows("omar" as never), /owner/i);
});

test("guard: an unknown source is refused rather than given a default weight", () => {
  // Defaulting would let the source nobody has weighed yet count as a
  // certainty. `constructor` is in the list because a prototype key is how a
  // membership check written with `in` lets exactly that through.
  const t = createSignalTable();
  for (const bad of ["guessed", "constructor", "toString", "", null, 7]) {
    assert.throws(
      () => t.record({ user_id: OWNER, toolkit: "kit-a", source: bad as never, last_seen_at: NOW }),
      /signal source/i,
      `accepted ${JSON.stringify(bad)} as a source`,
    );
  }
});

test("guard: a negative or zero weight is refused", () => {
  // A negative weight is a "never ask about this" reached through arithmetic —
  // invisible to the nudge state machine that is supposed to own that decision.
  const t = createSignalTable();
  for (const bad of [-1, 0, Number.NaN, Number.POSITIVE_INFINITY, "heavy"]) {
    assert.throws(
      () => t.record({ user_id: OWNER, toolkit: "kit-a", source: "said", last_seen_at: NOW, weight: bad as never }),
      /weight/i,
      `accepted ${JSON.stringify(bad)} as a weight`,
    );
  }
  const explicit = t.record({ user_id: OWNER, toolkit: "kit-a", source: "said", last_seen_at: NOW, weight: 0.05 });
  assert.equal(explicit.weight, 0.05, "an explicit weight is still allowed, for backfills");
});

test("guard: a missing timestamp, an empty slug and a made-up alias are refused", () => {
  const t = createSignalTable();
  assert.throws(
    () => t.record({ user_id: OWNER, toolkit: "kit-a", source: "said", last_seen_at: undefined as never }),
    /last_seen_at/,
  );
  assert.throws(() => t.record({ user_id: OWNER, toolkit: "   ", source: "said", last_seen_at: NOW }), /toolkit/);
  assert.throws(
    () => t.record({ user_id: OWNER, toolkit: "kit-a", source: "said", last_seen_at: NOW, alias: "wrok" as never }),
    /alias/,
  );
});

// ---------------------------------------------------------------------------
// HOSTS — matched through the catalog's own metadata, and nothing else.
// ---------------------------------------------------------------------------

test("host: an exact host match comes off the catalog entry's own url", () => {
  assert.deepEqual(hostToToolkit("alpha.vendor-one.example", CATALOG), { kind: "toolkit", slug: "kit-alpha" });
  assert.deepEqual(hostToToolkit("beta.vendor-one.example", CATALOG), { kind: "toolkit", slug: "kit-beta" });
  assert.deepEqual(hostToToolkit("vendor-two.example", CATALOG), { kind: "toolkit", slug: "kit-gamma" });
});

test("host: a page inside the catalog entry's site is that app", () => {
  assert.deepEqual(hostToToolkit("docs.vendor-two.example", CATALOG), { kind: "toolkit", slug: "kit-gamma" });
});

test("host: a registrable domain covering two of one vendor's apps is ambiguous, not a guess", () => {
  // This is what a host reduced to eTLD+1 looks like when the vendor ships
  // several apps. Picking one would be right half the time, and the wrong half
  // is a text asking somebody to connect an app they do not use.
  assert.deepEqual(hostToToolkit("vendor-one.example", CATALOG), {
    kind: "ambiguous",
    slugs: ["kit-alpha", "kit-beta"],
  });
});

test("host: the strongest reading wins outright, and only that reading is counted", () => {
  // A vendor-wide entry and a specific one both match `alpha.vendor-one.example`
  // — the specific one is an EXACT host, the vendor-wide one only contains it.
  // Without precedence this would be ambiguous forever and the observer signal
  // would be worthless for every vendor that has a marketing site.
  const withVendorWide = [...CATALOG, meta("kit-wide", "https://vendor-one.example")];
  assert.deepEqual(hostToToolkit("alpha.vendor-one.example", withVendorWide), {
    kind: "toolkit",
    slug: "kit-alpha",
  });
});

test("host: an unknown host returns no match rather than the nearest one", () => {
  // The failure this prevents: a fallback to "closest entry" turns every
  // browser run on any site into weight on whichever app happened to sort
  // first, and the table stops meaning anything.
  const unknown: HostMatch = { kind: "none" };
  assert.deepEqual(hostToToolkit("vendor-three.example", CATALOG), unknown);
  assert.deepEqual(hostToToolkit("vendor-one.example.co", CATALOG), unknown, "a longer name is not a subdomain");
  assert.deepEqual(hostToToolkit("notvendor-one.example", CATALOG), unknown, "a label suffix is not a label");
  assert.deepEqual(hostToToolkit("example", CATALOG), unknown, "a single label swallows nothing");
  assert.deepEqual(hostToToolkit("", CATALOG), unknown);
  assert.deepEqual(hostToToolkit("   ", CATALOG), unknown);
  assert.deepEqual(hostToToolkit("alpha.vendor-one.example", []), unknown, "an empty catalog knows no apps");
});

test("host: catalog entries with no usable url are skipped, not matched", () => {
  assert.deepEqual(hostToToolkit("kit-delta", CATALOG), { kind: "none" }, "a slug is not a host");
  assert.deepEqual(hostToToolkit("not a url at all", CATALOG), { kind: "none" });
  // A url this file cannot reduce to a host must not become a wildcard.
  const junk = [meta("kit-junk", "javascript:alert(1)"), meta("kit-blank", "https://"), meta("kit-noslug", null)];
  assert.deepEqual(hostToToolkit("alpha.vendor-one.example", junk), { kind: "none" });
  // A hole in the catalog is a bad row, never a crash in the middle of a
  // browser run's bookkeeping.
  const holed = [null as never, undefined as never, { slug: "  " } as never, ...CATALOG];
  assert.deepEqual(hostToToolkit("alpha.vendor-one.example", holed), { kind: "toolkit", slug: "kit-alpha" });
  assert.deepEqual(hostToToolkit("alpha.vendor-one.example", null as never), { kind: "none" });
});

test("host: an address is matched exactly or not at all", () => {
  // Trimming labels off a dotted quad produces another perfectly valid address
  // belonging to somebody else entirely.
  const byAddress = [meta("kit-addr", "https://192.0.2.10")];
  assert.deepEqual(hostToToolkit("192.0.2.10", byAddress), { kind: "toolkit", slug: "kit-addr" });
  assert.deepEqual(hostToToolkit("0.2.10", byAddress), { kind: "none" });
  assert.deepEqual(hostToToolkit("10.0.2.10", byAddress), { kind: "none" });
});

test("host: a url, a port, a trailing dot and a capital all reduce to the same host", () => {
  for (const spelling of [
    "ALPHA.Vendor-One.Example",
    "alpha.vendor-one.example.",
    "alpha.vendor-one.example:8443",
    "https://alpha.vendor-one.example/inbox?q=1#frag",
    "http://alpha.vendor-one.example",
  ]) {
    assert.deepEqual(
      hostToToolkit(spelling, CATALOG),
      { kind: "toolkit", slug: "kit-alpha" },
      `spelling ${spelling}`,
    );
  }
});

test("host: a credentialed string is refused instead of being read for a host", () => {
  // `someone@vendor-three.example` parsed as a url would hand back
  // `vendor-three.example` as the host, and an address book entry would become
  // a browsing habit.
  assert.deepEqual(hostToToolkit("someone@alpha.vendor-one.example", CATALOG), { kind: "none" });
});

test("host: the answer comes from the catalog, so renaming every slug renames every answer", () => {
  // App-blindness, the way the router proves it. If any of these answers
  // survived the substitution, the module would be reaching for a name it had
  // learned somewhere other than the catalog it was handed.
  const renamed = CATALOG.map((m) => meta(`renamed-${m.slug}`, m.appUrl));
  assert.deepEqual(hostToToolkit("alpha.vendor-one.example", renamed), {
    kind: "toolkit",
    slug: "renamed-kit-alpha",
  });
  assert.deepEqual(hostToToolkit("vendor-one.example", renamed), {
    kind: "ambiguous",
    slugs: ["renamed-kit-alpha", "renamed-kit-beta"],
  });
  // And a catalog whose hosts move takes the answers with it.
  const moved = [meta("kit-alpha", "https://alpha.vendor-nine.example")];
  assert.deepEqual(hostToToolkit("alpha.vendor-one.example", moved), { kind: "none" });
  assert.deepEqual(hostToToolkit("alpha.vendor-nine.example", moved), { kind: "toolkit", slug: "kit-alpha" });
});

// ---------------------------------------------------------------------------
// THE TWO EVIDENCE DOORS — both floors.
// ---------------------------------------------------------------------------

test("door: an observed host becomes a high signal only when exactly one app claims it", () => {
  const signal = observedHostSignal(OWNER, "alpha.vendor-one.example", CATALOG, NOW);
  assert.deepEqual(signal, {
    user_id: OWNER,
    toolkit: "kit-alpha",
    source: "observer",
    last_seen_at: NOW,
    alias: null,
  });
  assert.equal(observedHostSignal(OWNER, "vendor-one.example", CATALOG, NOW), null, "ambiguous adds nothing");
  assert.equal(observedHostSignal(OWNER, "vendor-three.example", CATALOG, NOW), null, "unknown adds nothing");
});

test("door: only the judge's positive verdict becomes a `said` signal", () => {
  // LAW 1. Deciding that "my work email" means a particular toolkit is a
  // model's job; this module reads the four-state verdict and treats exactly
  // one state as a licence. `unclear` and `no-verdict` are not weak yeses, and
  // an unreachable judge (null) is not a yes at all.
  const yes: ToolkitVerdict = { kind: "toolkit", slug: "kit-alpha" };
  assert.deepEqual(saidSignal(OWNER, yes, NOW, "work"), {
    user_id: OWNER,
    toolkit: "kit-alpha",
    source: "said",
    last_seen_at: NOW,
    alias: "work",
  });
  for (const verdict of [
    { kind: "none" } as ToolkitVerdict,
    { kind: "unclear" } as ToolkitVerdict,
    { kind: "no-verdict" } as ToolkitVerdict,
    null,
    undefined,
  ]) {
    assert.equal(saidSignal(OWNER, verdict, NOW), null, `verdict ${JSON.stringify(verdict)} licensed a signal`);
  }
  assert.equal(saidSignal(OWNER, { kind: "toolkit", slug: "  " } as ToolkitVerdict, NOW), null);
});

test("door: a signal from either door is recordable as-is", () => {
  const t = createSignalTable();
  const fromHost = observedHostSignal(OWNER, "vendor-two.example", CATALOG, NOW);
  const fromWords = saidSignal(OWNER, { kind: "toolkit", slug: "kit-gamma" }, NOW);
  assert.ok(fromHost && fromWords);
  t.record(fromHost);
  t.record(fromWords);
  const [line] = t.rank(OWNER, NOW);
  assert.equal(line.toolkit, "kit-gamma");
  assert.deepEqual(line.sources, ["observer", "said"]);
});

// ===========================================================================
// LAW 1 — signals.ts may not know an app, a domain, or a name.
// ===========================================================================
const SRC = readFileSync(new URL("../src/connections/signals.ts", import.meta.url), "utf8");

/** Comments stripped so the load-bearing leg reads CODE. The whole-file legs
 *  then catch the same names in prose, because a comment naming an app is where
 *  the next branch keyed on it gets its idea. */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/(^|[^:])\/\/[^\n]*/g, "$1");
}

// The only list of app names this module's world is allowed to contain, and it
// lives in a test because HARNESS-LAWS law 1 permits pattern matching in gates.
const APP_NAMES = [
  "gmail", "googlecalendar", "google", "outlook", "slack", "notion", "github",
  "gitlab", "linear", "asana", "trello", "jira", "confluence", "salesforce",
  "hubspot", "stripe", "shopify", "twilio", "sendgrid", "airtable", "dropbox",
  "box", "zoom", "discord", "figma", "intercom", "zendesk", "quickbooks",
  "xero", "calendly", "docusign", "mailchimp", "clickup", "monday", "chrome",
  "whatsapp", "telegram", "instagram", "facebook", "twitter", "linkedin",
  "amazon", "uber", "doordash", "opentable", "spotify", "apple", "microsoft",
];

// Likewise the only list of top-level domains. A domain literal in this module
// is the hardcoding the spec forbids, said in the one dialect that looks
// harmless: not `if (app === "…")` but `host.endsWith("…")`, which is the same
// branch wearing a hostname.
const TLDS = [
  "com", "net", "org", "io", "ai", "co", "so", "dev", "app", "xyz", "me", "tv",
  "us", "uk", "ca", "de", "fr", "jp", "cn", "ru", "br", "au", "nl", "se", "es",
  "pl", "ch", "info", "biz", "cloud", "site", "online", "store", "shop", "tech",
  "space", "website", "live", "link", "email", "chat", "team", "works", "gov",
  "edu", "eu", "asia", "mobi", "example",
];
const DOMAIN_SHAPED = new RegExp(String.raw`\b[a-z0-9][a-z0-9-]*\.(?:${TLDS.join("|")})\b`, "gi");

test("law 1: signals.ts contains no domain literal", () => {
  const hits = [...SRC.matchAll(DOMAIN_SHAPED)].map((m) => m[0]);
  assert.deepEqual(hits, [], `signals.ts contains domain literals: ${hits.join(", ")}`);
  // A gate that cannot go red is a decoration. The red-check builds its own
  // copy of the pattern: a global regex carries `lastIndex` between calls, and
  // a leg whose second use starts mid-string is a leg that passes by accident.
  const scan = new RegExp(DOMAIN_SHAPED.source, "i");
  assert.ok(scan.test('if (host.endsWith("mail.example.com")) return "kit";'), "the domain scan is blind");
});

test("law 1: signals.ts names no app, in code or in prose", () => {
  const code = stripComments(SRC).toLowerCase();
  const inCode = APP_NAMES.filter((n) => new RegExp(`\\b${n}\\b`).test(code));
  assert.deepEqual(inCode, [], `signals.ts names apps in code: ${inCode.join(", ")}`);

  const anywhere = APP_NAMES.filter((n) => new RegExp(`\\b${n}\\b`).test(SRC.toLowerCase()));
  assert.deepEqual(anywhere, [], `signals.ts names apps: ${anywhere.join(", ")}`);

  // Stripping comments is the step most likely to quietly eat the whole file
  // and turn the first assertion green over nothing.
  const planted = stripComments('// a comment\nif (row.toolkit === "slack") return 1;').toLowerCase();
  assert.ok(APP_NAMES.some((n) => new RegExp(`\\b${n}\\b`).test(planted)));
});

test("law 1: no string literal is compared against a toolkit or a host", () => {
  const code = stripComments(SRC);
  // `typeof meta?.slug === "string"` is exempt, and only that shape: it is a
  // runtime guard on a value the catalog supplied, and it cannot express "this
  // app in particular" because the only strings it can compare against are
  // JavaScript's type names.
  const shapes = [
    /(?<!typeof\s)\b[A-Za-z_$][\w$?.]*\.(toolkit|slug|host|hostname)\s*[=!]==?\s*["'`][^"'`]/,
    /["'`][^"'`][^"'`]*["'`]\s*[=!]==?\s*[A-Za-z_$][\w$?.]*\.(toolkit|slug|host|hostname)/,
    /\.(toolkit|slug|hostname)\s*\.\s*(includes|startsWith|endsWith|match|search|indexOf)\s*\(/,
  ];
  for (const re of shapes) {
    assert.equal(re.test(code), false, `signals.ts branches on an app string: ${re}`);
  }
  // Each shape must be able to fire.
  const planted = [
    'if (row.toolkit === "kit-a") return 1;',
    'if ("kit-a" === row.toolkit) return 1;',
    'if (url.hostname.endsWith("suffix")) return 1;',
  ];
  shapes.forEach((re, i) => assert.ok(re.test(planted[i]), `shape ${i} cannot go red`));
});
