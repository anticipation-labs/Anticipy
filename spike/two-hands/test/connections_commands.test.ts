// TEXT COMMANDS — the behaviour, plus the four legs behaviour cannot catch.
//
// Everything here runs with no network and no key: the judge, the provider and
// the connections table are local stubs written against the interfaces in
// `src/connections/contract.ts`. They are stubs and not imports on purpose —
// the rest of `src/connections/` is being written in parallel, and a test that
// leans on a file in flight tests two things and pins neither.
//
// THE LEGS THAT ARE NOT BEHAVIOUR TESTS read `commands.ts`'s own source back:
//
//   1. no app name, in code or in prose
//   2. no regex, and no expression that inspects the owner's words
//   3. every string literal in a comparison is one of the module's own closed
//      enum members
//   4. no string the module can SAY contains a word the spec forbids
//
// A hardcoded name or a smuggled keyword check is invisible to every behaviour
// test in this file: the module would keep passing all of them and be wrong for
// exactly one owner, on exactly one app, in production. HARNESS-LAWS law 1
// permits pattern matching in "gates and evals — deterministic tests of
// outcomes", which is what these four are, and each carries a planted negative
// control so a leg that has quietly stopped being able to go red fails instead
// of passing over nothing.
//
// THE APP NAMES BELOW ARE FIXTURES, NOT KNOWLEDGE. Every catalog in this file
// is invented ("app-zeta", "Zeta"), so a branch keyed on a real app could not
// be satisfied here even by accident — and the blindness leg re-runs the whole
// interpret battery against a second, disjoint set of invented slugs to prove
// the outcome came from the judge rather than from the strings.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import test from "node:test";
import assert from "node:assert/strict";

import {
  COMMAND_ACTIONS,
  combineResults,
  chooseAccountReply,
  connectReply,
  createCommands,
  disconnectReply,
  interpret,
  listReply,
  mayUse,
  settingsView,
  unclearReply,
  writesEnabled,
  writesReply,
  type CommandAction,
  type CommandIntent,
  type CommandJudge,
  type CommandVerdict,
  type ConnectionsTable,
  type DisconnectOutcome,
  type LinkMinter,
} from "../src/connections/commands.ts";
import { ownerId } from "../src/connections/contract.ts";
import type {
  AccountAlias,
  Connection,
  ConnectionProvider,
  DisconnectResult,
  OwnerId,
  Toolkit,
  ToolkitMeta,
  ToolkitVerdict,
} from "../src/connections/contract.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
const COMMANDS_SRC = readFileSync(resolve(HERE, "..", "src", "connections", "commands.ts"), "utf8");

// ---------------------------------------------------------------------------
// Fixtures.
// ---------------------------------------------------------------------------
// A real owner row id shape: fifteen lowercase alphanumerics. `ownerId` refuses
// anything else, and this file leans on that in the guard leg.
const OWNER = ownerId("sxkotd1h02qb6gw");
const OTHER_OWNER = ownerId("qeuy6sv1raof9rw");

function meta(slug: string, name: string, over: Partial<ToolkitMeta> = {}): ToolkitMeta {
  return { slug, name, logo: null, description: null, appUrl: null, scopes: [], ...over };
}

/** Two catalogs with nothing in common but their SHAPE. The blindness leg runs
 *  the same battery against each; identical results mean the strings were never
 *  the reason. */
const CATALOG_A: ToolkitMeta[] = [meta("app-zeta", "Zeta"), meta("app-theta", "Theta")];
const CATALOG_B: ToolkitMeta[] = [meta("wg-omicron", "Omicron"), meta("wg-kappa", "Kappa")];

function conn(over: Partial<Connection> = {}): Connection {
  return {
    user_id: OWNER,
    toolkit: "app-zeta",
    connected_account_id: "ca_1",
    alias: null,
    status: "connected",
    writes_enabled: false,
    last_used_at: null,
    ...over,
  };
}

// ---------------------------------------------------------------------------
// The judge stub. Both answers are handed in; nothing here reads the phrase,
// which is the point — the tests set the verdict and watch the intent move.
// ---------------------------------------------------------------------------
interface JudgeCalls {
  action: { phrase: string; actions: readonly CommandAction[] }[];
  match: { phrase: string; catalog: ToolkitMeta[] }[];
}

type Answer<T> = T | "throw";

function stubJudge(
  actionAnswer: Answer<unknown>,
  toolkitAnswer: Answer<unknown>,
): CommandJudge & { calls: JudgeCalls } {
  const calls: JudgeCalls = { action: [], match: [] };
  return {
    calls,
    async action(phrase: string, actions: readonly CommandAction[]): Promise<CommandVerdict> {
      calls.action.push({ phrase, actions });
      if (actionAnswer === "throw") throw new Error("judge unreachable");
      return actionAnswer as CommandVerdict;
    },
    async match(phrase: string, catalog: ToolkitMeta[]): Promise<ToolkitVerdict> {
      calls.match.push({ phrase, catalog });
      if (toolkitAnswer === "throw") throw new Error("judge unreachable");
      return toolkitAnswer as ToolkitVerdict;
    },
  };
}

const act = (action: CommandAction): CommandVerdict => ({ kind: "action", action });
const names = (slug: string): ToolkitVerdict => ({ kind: "toolkit", slug });

// ---------------------------------------------------------------------------
// The table and provider stubs.
// ---------------------------------------------------------------------------
function tableOf(rows: Connection[]): ConnectionsTable & { rows: Connection[] } {
  const store = rows.map((r) => ({ ...r }));
  return {
    rows: store,
    async forOwner(user: OwnerId): Promise<Connection[]> {
      return store.filter((r) => r.user_id === user).map((r) => ({ ...r }));
    },
    async put(row: Connection): Promise<void> {
      const at = store.findIndex(
        (r) =>
          r.user_id === row.user_id
          && r.toolkit === row.toolkit
          && r.connected_account_id === row.connected_account_id,
      );
      if (at === -1) store.push({ ...row });
      else store[at] = { ...row };
    },
  };
}

function providerOf(opts: {
  catalog?: ToolkitMeta[];
  results?: Record<string, DisconnectResult>;
  throwOn?: string;
  throwToolkit?: boolean;
}): ConnectionProvider & { disconnected: string[] } {
  const catalog = opts.catalog ?? CATALOG_A;
  const disconnected: string[] = [];
  return {
    disconnected,
    async session(): Promise<{ sessionId: string }> {
      return { sessionId: "s_1" };
    },
    async authorize(): Promise<{ redirectUrl: string }> {
      return { redirectUrl: "https://example.invalid/never-used-in-a-text" };
    },
    async connections(): Promise<Connection[]> {
      return [];
    },
    async disconnect(_user: OwnerId, accountId: string): Promise<DisconnectResult> {
      disconnected.push(accountId);
      if (opts.throwOn === accountId) throw new Error("provider down");
      return (
        opts.results?.[accountId] ?? { revoked: true, deleted: true, revokeUnavailable: false }
      );
    },
    async toolkit(slug: Toolkit): Promise<ToolkitMeta> {
      if (opts.throwToolkit) throw new Error("catalog down");
      const found = catalog.find((m) => m.slug === slug);
      if (found === undefined) throw new Error(`no such toolkit: ${slug}`);
      return found;
    },
  };
}

function minterOf(url = "https://anticipy.ai/c/tok_abc"): LinkMinter & { minted: unknown[] } {
  const minted: unknown[] = [];
  return {
    minted,
    async mint(user: OwnerId, toolkit: Toolkit, alias: AccountAlias | null) {
      minted.push({ user, toolkit, alias });
      return { url };
    },
  };
}

// ===========================================================================
// 1. THE JUDGE DECIDES, NOT THE WORDS.
// ===========================================================================

test("the toolkit is whatever the judge said it was", async () => {
  const judge = stubJudge(act("connect"), names("app-theta"));
  assert.deepEqual(await interpret("connect the thing", CATALOG_A, judge), {
    kind: "connect",
    toolkit: "app-theta",
  });
});

test("same phrase, different verdict, different intent", async () => {
  // The whole Law-1 claim in one assertion: nothing about the sentence changed,
  // and the outcome moved anyway, because the outcome was never a reading of
  // the sentence.
  const phrase = "connect the thing";
  const first = await interpret(phrase, CATALOG_A, stubJudge(act("connect"), names("app-zeta")));
  const second = await interpret(phrase, CATALOG_A, stubJudge(act("connect"), names("app-theta")));
  assert.deepEqual(first, { kind: "connect", toolkit: "app-zeta" });
  assert.deepEqual(second, { kind: "connect", toolkit: "app-theta" });
  assert.notDeepEqual(first, second);
});

test("same phrase, different ACTION verdict, different intent", async () => {
  const phrase = "the usual thing with that app";
  const on = await interpret(phrase, CATALOG_A, stubJudge(act("allow_changes"), names("app-zeta")));
  const off = await interpret(phrase, CATALOG_A, stubJudge(act("stop_changes"), names("app-zeta")));
  assert.deepEqual(on, { kind: "set_writes", toolkit: "app-zeta", on: true });
  assert.deepEqual(off, { kind: "set_writes", toolkit: "app-zeta", on: false });
});

test("a phrase sharing no vocabulary with the app still resolves", async () => {
  // "use my work Gmail for this" is the easy case and it is not the case that
  // matters. This one has no overlap with the slug, the name, or any word a
  // synonym table could hold; the judge names the app and that is the whole
  // mechanism. A keyword layer would return unclear here.
  const judge = stubJudge(act("disconnect"), names("app-theta"));
  const intent = await interpret(
    "stop rummaging through the place where I keep the invoices",
    CATALOG_A,
    judge,
  );
  assert.deepEqual(intent, { kind: "disconnect", toolkit: "app-theta" });
});

test("the judge is handed the owner's words verbatim and the whole catalog", async () => {
  const judge = stubJudge(act("connect"), names("app-zeta"));
  const phrase = "  CONNECT the Thing, please  ";
  await interpret(phrase, CATALOG_A, judge);
  assert.equal(judge.calls.action[0]?.phrase, phrase);
  assert.equal(judge.calls.match[0]?.phrase, phrase);
  assert.deepEqual(judge.calls.match[0]?.catalog, CATALOG_A);
  // The action question is asked with the closed menu, so the model picks from
  // what this module can actually do rather than inventing an operation.
  assert.deepEqual([...(judge.calls.action[0]?.actions ?? [])], [...COMMAND_ACTIONS]);
});

test("every action maps to its own intent shape", async () => {
  const cases: [CommandAction, CommandIntent][] = [
    ["list", { kind: "list" }],
    ["connect", { kind: "connect", toolkit: "app-zeta" }],
    ["disconnect", { kind: "disconnect", toolkit: "app-zeta" }],
    ["allow_changes", { kind: "set_writes", toolkit: "app-zeta", on: true }],
    ["stop_changes", { kind: "set_writes", toolkit: "app-zeta", on: false }],
    ["use_work_account", { kind: "choose_account", toolkit: "app-zeta", alias: "work" }],
    ["use_personal_account", { kind: "choose_account", toolkit: "app-zeta", alias: "personal" }],
  ];
  for (const [action, expected] of cases) {
    const judge = stubJudge(act(action), names("app-zeta"));
    assert.deepEqual(await interpret("whatever", CATALOG_A, judge), expected, action);
  }
});

test("the app-wide question does not spend a second model call", async () => {
  // "what's connected" names no app. Asking which one would be a call whose
  // only possible useful answer is "none", and a `none` we then have to ignore
  // is a verdict waiting to be misread.
  const judge = stubJudge(act("list"), names("app-zeta"));
  assert.deepEqual(await interpret("what's connected", CATALOG_A, judge), { kind: "list" });
  assert.equal(judge.calls.match.length, 0);
});

// ===========================================================================
// 2. THE FLOOR: A MISSING ANSWER ASKS, IT DOES NOT ACT.
// ===========================================================================

test("an unclear toolkit asks rather than acting", async () => {
  for (const answer of [{ kind: "unclear" }, { kind: "no-verdict" }, { kind: "none" }]) {
    const judge = stubJudge(act("disconnect"), answer);
    assert.deepEqual(
      await interpret("get rid of it", CATALOG_A, judge),
      { kind: "unclear" },
      JSON.stringify(answer),
    );
  }
});

test("the only candidate in the catalog is still not an answer", async () => {
  // Found by mutation: swapping `askToolkit` for "if there is exactly one
  // toolkit, it must be that one" passed all fifty-five other tests. It is the
  // same guess the module's own header forbids, wearing a structural costume —
  // and it is wrong on the day somebody with one connected app types something
  // about a second one, which is the day they are most likely to be watching.
  const only = [meta("app-zeta", "Zeta")];
  for (const answer of [{ kind: "unclear" }, { kind: "no-verdict" }, { kind: "none" }]) {
    const judge = stubJudge(act("disconnect"), answer);
    assert.deepEqual(
      await interpret("get rid of it", only, judge),
      { kind: "unclear" },
      JSON.stringify(answer),
    );
    assert.equal(judge.calls.match.length, 1, "the judge was not asked");
  }
  // An empty catalog is not an answer either, and it must still be ASKED — the
  // judge is the thing that knows whether the person named an app at all.
  const empty = stubJudge(act("connect"), { kind: "none" });
  assert.deepEqual(await interpret("connect it", [], empty), { kind: "unclear" });
  assert.equal(empty.calls.match.length, 1);
});

test("an unclear action asks; 'none' hands the sentence back", async () => {
  const unclear = stubJudge({ kind: "unclear" }, names("app-zeta"));
  assert.deepEqual(await interpret("hm", CATALOG_A, unclear), { kind: "unclear" });

  const noVerdict = stubJudge({ kind: "no-verdict" }, names("app-zeta"));
  assert.deepEqual(await interpret("hm", CATALOG_A, noVerdict), { kind: "unclear" });

  // `none` is not a failure. It means this was somebody else's sentence, and a
  // connections module that answered it would be interrupting a conversation
  // it was not part of.
  const none = stubJudge({ kind: "none" }, names("app-zeta"));
  assert.deepEqual(await interpret("what's the weather", CATALOG_A, none), { kind: "none" });
});

test("a judge that throws is a missing answer, not a licence", async () => {
  const deadAction = stubJudge("throw", names("app-zeta"));
  assert.deepEqual(await interpret("disconnect it", CATALOG_A, deadAction), { kind: "unclear" });

  const deadToolkit = stubJudge(act("disconnect"), "throw");
  assert.deepEqual(await interpret("disconnect it", CATALOG_A, deadToolkit), { kind: "unclear" });
});

test("a bare ToolkitJudge with no action method asks rather than acting", async () => {
  // Types are stripped at run time, so "the caller passed the wrong judge" is a
  // thing that happens in production rather than a thing the compiler stops.
  const halfJudge = { async match() { return names("app-zeta"); } } as unknown as CommandJudge;
  assert.deepEqual(await interpret("connect it", CATALOG_A, halfJudge), { kind: "unclear" });
  assert.deepEqual(
    await interpret("connect it", CATALOG_A, null as unknown as CommandJudge),
    { kind: "unclear" },
  );
});

test("a verdict shape we never defined is refused", async () => {
  const malformed: unknown[] = [
    null,
    "connect",
    {},
    { kind: "connect" },
    { kind: "action" },
    { kind: "action", action: "delete_everything" },
    { kind: "action", action: 3 },
  ];
  for (const answer of malformed) {
    const judge = stubJudge(answer, names("app-zeta"));
    assert.deepEqual(
      await interpret("do the thing", CATALOG_A, judge),
      { kind: "unclear" },
      JSON.stringify(answer),
    );
  }
});

test("a slug the catalog never offered is refused", async () => {
  // A model asked to pick from a list can return something plausible that is
  // not on it. Acting would mint a link for a toolkit this owner was never
  // offered, or run a disconnect that silently matches nothing while the reply
  // says "done".
  const judge = stubJudge(act("connect"), names("app-invented"));
  assert.deepEqual(await interpret("connect it", CATALOG_A, judge), { kind: "unclear" });
});

test("a malformed slug is refused, and a mis-cased one resolves to the catalog's own", async () => {
  for (const bad of [null, 42, "", "   ", {}]) {
    const judge = stubJudge(act("connect"), { kind: "toolkit", slug: bad });
    assert.deepEqual(
      await interpret("connect it", CATALOG_A, judge),
      { kind: "unclear" },
      JSON.stringify(bad),
    );
  }
  // Case is a property of an identifier we minted, not of anybody's words: a
  // judge that answered with the right app in the wrong case has identified the
  // app, and the string that travels onward is still the catalog's.
  const judge = stubJudge(act("connect"), names("  APP-Zeta "));
  assert.deepEqual(await interpret("connect it", CATALOG_A, judge), {
    kind: "connect",
    toolkit: "app-zeta",
  });
});

test("a malformed catalog cannot become a toolkit", async () => {
  const junk = [null, { name: "no slug" }, { slug: 7 }, { slug: "" }] as unknown as ToolkitMeta[];
  const judge = stubJudge(act("connect"), names("app-zeta"));
  assert.deepEqual(await interpret("connect it", junk, judge), { kind: "unclear" });
  const judge2 = stubJudge(act("connect"), names("app-zeta"));
  assert.deepEqual(
    await interpret("connect it", null as unknown as ToolkitMeta[], judge2),
    { kind: "unclear" },
  );
});

test("a non-string phrase does not crash the surface", async () => {
  const judge = stubJudge({ kind: "none" }, { kind: "none" });
  assert.deepEqual(
    await interpret(null as unknown as string, CATALOG_A, judge),
    { kind: "none" },
  );
  assert.equal(judge.calls.action[0]?.phrase, "");
});

// ===========================================================================
// 3. APP BLINDNESS — the same battery, a disjoint catalog.
// ===========================================================================

test("the whole surface behaves identically against an unrelated catalog", async () => {
  async function battery(catalog: ToolkitMeta[], first: string, second: string) {
    const out: unknown[] = [];
    for (const action of COMMAND_ACTIONS) {
      out.push(await interpret("x", catalog, stubJudge(act(action), names(first))));
      out.push(await interpret("x", catalog, stubJudge(act(action), names(second))));
      out.push(await interpret("x", catalog, stubJudge(act(action), { kind: "unclear" })));
      out.push(await interpret("x", catalog, stubJudge(act(action), names("not-in-catalog"))));
    }
    return out;
  }
  const a = await battery(CATALOG_A, "app-zeta", "app-theta");
  const b = await battery(CATALOG_B, "wg-omicron", "wg-kappa");
  // Substituting every slug substitutes every answer and changes nothing else.
  const rewritten = JSON.parse(
    JSON.stringify(a).split("app-zeta").join("wg-omicron").split("app-theta").join("wg-kappa"),
  );
  assert.deepEqual(rewritten, b);
});

// ===========================================================================
// 4. DISCONNECT HONESTY — "revoked" is a claim, not a formality.
// ===========================================================================

function outcome(result: DisconnectResult, attempted = 1): DisconnectOutcome {
  return { toolkit: "app-zeta", attempted, result };
}

test("a clean disconnect says revoked", () => {
  const reply = disconnectReply(
    meta("app-zeta", "Zeta"),
    outcome({ revoked: true, deleted: true, revokeUnavailable: false }),
  );
  assert.equal(reply, "Done. Zeta disconnected and access revoked.");
});

test("a revoke that could not happen never claims it did", () => {
  // The defect this whole module was written around: about 5% of accounts
  // cannot be revoked programmatically, and a person told "access revoked" has
  // no way to find out otherwise until it matters.
  const reply = disconnectReply(
    meta("app-zeta", "Zeta"),
    outcome({ revoked: false, deleted: true, revokeUnavailable: true }),
  );
  assert.equal(/revok/i.test(reply), false, `claimed a revoke that did not happen: ${reply}`);
  assert.ok(reply.includes("Zeta"));
  // And it has to say what the person must do about it, or the honesty is
  // just an omission.
  assert.ok(/own settings/i.test(reply), reply);
});

test("a revoke that simply failed is treated the same way", () => {
  // `revokeUnavailable: false` with `revoked: false` is "we tried and it did
  // not work", which is not a state the vendor distinguishes for the person.
  // What must not vary is the word.
  const reply = disconnectReply(
    meta("app-zeta", "Zeta"),
    outcome({ revoked: false, deleted: true, revokeUnavailable: false }),
  );
  assert.equal(/revok/i.test(reply), false, reply);
});

test("nothing deleted and nothing revoked does not report success", () => {
  const reply = disconnectReply(
    meta("app-zeta", "Zeta"),
    outcome({ revoked: false, deleted: false, revokeUnavailable: false }),
  );
  assert.equal(/^Done/.test(reply), false, reply);
  assert.equal(/revok/i.test(reply), false, reply);
  assert.ok(/nothing has changed/i.test(reply), reply);
});

test("a revoke without a delete says both halves", () => {
  const reply = disconnectReply(
    meta("app-zeta", "Zeta"),
    outcome({ revoked: true, deleted: false, revokeUnavailable: false }),
  );
  assert.ok(/revoked/.test(reply), reply);
  assert.ok(/still on file/i.test(reply), reply);
});

test("nothing connected is said plainly, not as a success", () => {
  const reply = disconnectReply(
    meta("app-zeta", "Zeta"),
    outcome({ revoked: false, deleted: false, revokeUnavailable: false }, 0),
  );
  assert.ok(/isn't connected/.test(reply), reply);
  assert.equal(/revok/i.test(reply), false, reply);
});

test("one account out of two failing to revoke sinks the whole claim", () => {
  // Two accounts on one app is the spec's normal case. Being told "access
  // revoked" when only the personal one came back is a false statement about
  // the work one, and it is the dangerous half that would be wrong.
  const combined = combineResults([
    { revoked: true, deleted: true, revokeUnavailable: false },
    { revoked: false, deleted: true, revokeUnavailable: true },
  ]);
  assert.deepEqual(combined, { revoked: false, deleted: true, revokeUnavailable: true });
  const reply = disconnectReply(meta("app-zeta", "Zeta"), outcome(combined, 2));
  assert.equal(/revok/i.test(reply), false, reply);
});

test("combining nothing is not a revoke", () => {
  assert.deepEqual(combineResults([]), {
    revoked: false,
    deleted: false,
    revokeUnavailable: false,
  });
  assert.deepEqual(combineResults(null as unknown as DisconnectResult[]), {
    revoked: false,
    deleted: false,
    revokeUnavailable: false,
  });
  // Truthy-but-not-true is not a yes. A provider that answers `1` has not been
  // read as a revoke by anything downstream, so it must not be here either.
  assert.equal(
    combineResults([{ revoked: 1, deleted: 1, revokeUnavailable: false } as unknown as DisconnectResult])
      .revoked,
    false,
  );
});

test("the app's name comes from the catalog, never from this module", () => {
  const renamed = disconnectReply(
    meta("app-zeta", "Something Else Entirely"),
    outcome({ revoked: true, deleted: true, revokeUnavailable: false }),
  );
  assert.equal(renamed, "Done. Something Else Entirely disconnected and access revoked.");
  // And with no catalog entry at all the slug stands in — a blank renders as
  // "Done.  disconnected" and reads to the person as a broken product.
  const nameless = disconnectReply(
    null,
    outcome({ revoked: true, deleted: true, revokeUnavailable: false }),
  );
  assert.ok(nameless.includes("app-zeta"), nameless);
});

// ===========================================================================
// 5. THE WRITE OPT-IN.
// ===========================================================================

test("writes are off by default and reads are not", () => {
  const rows = [conn()];
  assert.equal(mayUse(rows, "app-zeta", "read"), true);
  assert.equal(mayUse(rows, "app-zeta", "write"), false);
  assert.equal(writesEnabled(rows, "app-zeta"), false);
});

test("a row with the opt-in column missing reads as off, and reads still work", () => {
  // Rows arrive from storage, where a column can be absent or null and where
  // booleans are integers. Every unreadable shape has to land on OFF: this is
  // a floor, and an unreadable consent is not a consent.
  const shapes: unknown[] = [undefined, null, 0, "", "true", "1", {}];
  for (const value of shapes) {
    const rows = [conn({ writes_enabled: value as boolean })];
    assert.equal(mayUse(rows, "app-zeta", "write"), false, JSON.stringify(value));
    assert.equal(mayUse(rows, "app-zeta", "read"), true, JSON.stringify(value));
  }
  // The two shapes storage actually uses for a yes.
  for (const value of [true, 1]) {
    assert.equal(mayUse([conn({ writes_enabled: value as boolean })], "app-zeta", "write"), true);
  }
});

test("an app that is not connected licenses nothing, read or write", () => {
  const rows = [conn({ status: "needs_reconnect", writes_enabled: true })];
  assert.equal(mayUse(rows, "app-zeta", "read"), false);
  assert.equal(mayUse(rows, "app-zeta", "write"), false);
  assert.equal(mayUse([], "app-zeta", "read"), false);
  assert.equal(mayUse(rows, "app-theta", "read"), false);
});

test("two accounts, one opted in, is not an opt-in", () => {
  // Under "any account will do", opting in for a personal account would license
  // a write to a work one that was never offered the choice.
  const rows = [
    conn({ connected_account_id: "ca_1", alias: "personal", writes_enabled: true }),
    conn({ connected_account_id: "ca_2", alias: "work", writes_enabled: false }),
  ];
  assert.equal(mayUse(rows, "app-zeta", "write"), false);
  assert.equal(mayUse(rows, "app-zeta", "read"), true);
});

test("setWrites moves every account on the app, and reads are untouched", async () => {
  const table = tableOf([
    conn({ connected_account_id: "ca_1", alias: "personal" }),
    conn({ connected_account_id: "ca_2", alias: "work" }),
  ]);
  const cmds = createCommands({ table, provider: providerOf({}), links: minterOf() });

  assert.equal(mayUse(await table.forOwner(OWNER), "app-zeta", "read"), true);
  const on = await cmds.setWrites(OWNER, "app-zeta", true);
  assert.deepEqual(on, { toolkit: "app-zeta", enabled: true, applied: true, accounts: 2 });
  assert.equal(mayUse(await table.forOwner(OWNER), "app-zeta", "write"), true);
  // The read half never moved. If it ever did, the toggle would stop being a
  // consent control and become an on/off switch for the product.
  assert.equal(mayUse(await table.forOwner(OWNER), "app-zeta", "read"), true);

  const off = await cmds.setWrites(OWNER, "app-zeta", false);
  assert.equal(off.enabled, false);
  assert.equal(mayUse(await table.forOwner(OWNER), "app-zeta", "write"), false);
  assert.equal(mayUse(await table.forOwner(OWNER), "app-zeta", "read"), true);
});

test("setWrites on an app that is not connected changes nothing and says so", async () => {
  const table = tableOf([]);
  const cmds = createCommands({ table, provider: providerOf({}), links: minterOf() });
  const result = await cmds.setWrites(OWNER, "app-zeta", true);
  assert.deepEqual(result, { toolkit: "app-zeta", enabled: false, applied: false, accounts: 0 });
  assert.equal(table.rows.length, 0);
  assert.ok(/isn't connected yet/.test(writesReply(meta("app-zeta", "Zeta"), result)));
});

test("setWrites accepts only a real boolean as a yes", async () => {
  const table = tableOf([conn()]);
  const cmds = createCommands({ table, provider: providerOf({}), links: minterOf() });
  await cmds.setWrites(OWNER, "app-zeta", "yes" as unknown as boolean);
  assert.equal(mayUse(await table.forOwner(OWNER), "app-zeta", "write"), false);
});

test("a disconnect drops the opt-in with the row", async () => {
  // Otherwise a reconnect a month later inherits a write licence the owner gave
  // to a connection that no longer exists.
  const table = tableOf([conn({ writes_enabled: true })]);
  const cmds = createCommands({ table, provider: providerOf({}), links: minterOf() });
  await cmds.disconnect(OWNER, "app-zeta");
  assert.equal(table.rows[0]?.status, "disconnected");
  assert.equal(table.rows[0]?.writes_enabled, false);
});

// ===========================================================================
// 6. THE OWNER ID IS THE OWNER ROW ID.
// ===========================================================================

test("every entry point re-checks the owner id at run time", async () => {
  // The distinct `OwnerId` type is erased before this code runs, so the check
  // has to be a call. One operator's mailbox serving everybody is the worst
  // failure this system has and it has already happened once.
  const cmds = createCommands({ table: tableOf([]), provider: providerOf({}), links: minterOf() });
  const bad = "omar" as unknown as OwnerId;
  await assert.rejects(() => cmds.settings(bad), /owner id/);
  await assert.rejects(() => cmds.setWrites(bad, "app-zeta", true), /owner id/);
  await assert.rejects(() => cmds.disconnect(bad, "app-zeta"), /owner id/);
  await assert.rejects(() => cmds.chooseAccount(bad, "app-zeta", "work"), /owner id/);
  await assert.rejects(() => cmds.connect(bad, "app-zeta"), /owner id/);
  await assert.rejects(() => cmds.handle(bad, { kind: "list" }), /owner id/);
  await assert.rejects(
    () => cmds.settings("someone@example.com" as unknown as OwnerId),
    /owner id/,
  );
});

test("a store that leaks another owner's rows still cannot touch them", async () => {
  // Belt and braces, and it stays: a `forOwner` that forgot its WHERE clause is
  // one missing line away from a revoke on a stranger's mailbox, through code
  // that looks correct everywhere it is read.
  const leaky = tableOf([
    conn({ user_id: OWNER, connected_account_id: "ca_mine" }),
    conn({ user_id: OTHER_OWNER, connected_account_id: "ca_theirs", writes_enabled: false }),
  ]);
  leaky.forOwner = async () => leaky.rows.map((r) => ({ ...r }));
  const provider = providerOf({});
  const cmds = createCommands({ table: leaky, provider, links: minterOf() });

  const view = await cmds.settings(OWNER);
  assert.equal(view.apps[0]?.accounts, 1);

  await cmds.setWrites(OWNER, "app-zeta", true);
  assert.equal(leaky.rows.find((r) => r.connected_account_id === "ca_theirs")?.writes_enabled, false);

  await cmds.disconnect(OWNER, "app-zeta");
  assert.deepEqual(provider.disconnected, ["ca_mine"]);
  assert.equal(leaky.rows.find((r) => r.connected_account_id === "ca_theirs")?.status, "connected");
});

test("one owner's rows never reach another owner", async () => {
  const table = tableOf([
    conn({ user_id: OWNER, toolkit: "app-zeta" }),
    conn({ user_id: OTHER_OWNER, toolkit: "app-theta", connected_account_id: "ca_9" }),
  ]);
  const cmds = createCommands({ table, provider: providerOf({}), links: minterOf() });
  const view = await cmds.settings(OWNER);
  assert.deepEqual(view.apps.map((a) => a.toolkit), ["app-zeta"]);
  const link = minterOf();
  const cmds2 = createCommands({ table, provider: providerOf({}), links: link });
  await cmds2.connect(OWNER, "app-zeta");
  assert.deepEqual(link.minted, [{ user: OWNER, toolkit: "app-zeta", alias: null }]);
});

// ===========================================================================
// 7. THE SETTINGS SURFACE AND ITS TEXT TWIN.
// ===========================================================================

test("the view is built from the catalog, and one app is one row", () => {
  const view = settingsView(
    [
      conn({ connected_account_id: "ca_1", alias: "work", last_used_at: 5 }),
      conn({ connected_account_id: "ca_2", alias: "personal", last_used_at: 9 }),
      conn({ toolkit: "app-theta", connected_account_id: "ca_3", status: "needs_reconnect" }),
      conn({ toolkit: "app-gone", connected_account_id: "ca_4", status: "disconnected" }),
    ],
    CATALOG_A,
  );
  assert.deepEqual(view.apps.map((a) => a.name), ["Theta", "Zeta"]);
  const zeta = view.apps.find((a) => a.toolkit === "app-zeta");
  assert.equal(zeta?.accounts, 2);
  assert.deepEqual(zeta?.aliases, ["work", "personal"]);
  assert.equal(zeta?.lastUsedAt, 9);
  // A row the owner already disconnected is history. Showing it reads as "you
  // are still connected".
  assert.equal(view.apps.some((a) => a.toolkit === "app-gone"), false);
});

test("the screen never shows a licence a write would refuse", () => {
  const view = settingsView(
    [
      conn({ connected_account_id: "ca_1", writes_enabled: true }),
      conn({ connected_account_id: "ca_2", writes_enabled: false }),
    ],
    CATALOG_A,
  );
  assert.equal(view.apps[0]?.writesEnabled, false);
  assert.equal(
    view.apps[0]?.writesEnabled,
    mayUse(
      [conn({ connected_account_id: "ca_1", writes_enabled: true }), conn({ connected_account_id: "ca_2" })],
      "app-zeta",
      "write",
    ),
  );
});

test("the text twin renders the same view the screen does", () => {
  const rows = [
    conn({ alias: "work", writes_enabled: true }),
    conn({ toolkit: "app-theta", connected_account_id: "ca_3", status: "needs_reconnect" }),
  ];
  const text = listReply(settingsView(rows, CATALOG_A));
  assert.ok(text.includes("Zeta"), text);
  assert.ok(text.includes("(work)"), text);
  assert.ok(text.includes("I can make changes"), text);
  assert.ok(/Theta has stopped working/.test(text), text);

  // Rename the app in the catalog and the sentence follows. Nothing in the
  // module holds a second copy of the name.
  const renamed = listReply(settingsView(rows, [meta("app-zeta", "Renamed"), meta("app-theta", "T2")]));
  assert.ok(renamed.includes("Renamed"), renamed);
  assert.equal(renamed.includes("Zeta"), false, renamed);
});

test("an empty list says connecting is optional", () => {
  // The spec's rule, and the reason for it: the browser does the same work
  // either way, so an owner who feels cornered is being cornered over nothing.
  const text = listReply(settingsView([], CATALOG_A));
  assert.ok(/browser/.test(text), text);
  assert.ok(/optional|up to you|just makes it quicker/i.test(text), text);
  assert.equal(listReply(null as unknown as { apps: [] }), text);
});

test("the connect reply carries our own link and says it is optional", () => {
  const reply = connectReply(meta("app-zeta", "Zeta"), { url: "https://anticipy.ai/c/tok_abc" });
  assert.ok(reply.includes("https://anticipy.ai/c/tok_abc"), reply);
  assert.ok(reply.includes("10 minutes"), reply);
  assert.ok(/up to you|browser either way/i.test(reply), reply);
});

test("no link means no link sentence", () => {
  // "Here's your link to connect Zeta:  — it opens once" is a text somebody
  // taps at and finds nothing in, and they conclude the product is broken.
  for (const bad of [{ url: "" }, { url: "   " }, {}, null]) {
    const reply = connectReply(meta("app-zeta", "Zeta"), bad as { url: string });
    assert.ok(/couldn't make you a link/.test(reply), JSON.stringify(bad));
  }
});

test("a status nobody can name vanishes from both skins, not one", () => {
  // `listReply` groups by status. A fourth value would sit in the view the
  // screen renders and in neither of the text's two groups, and the twin claim
  // would be false for exactly the row that was already wrong.
  const rows = [
    conn(),
    conn({ toolkit: "app-theta", connected_account_id: "ca_7", status: "pending" as never }),
  ];
  const view = settingsView(rows, CATALOG_A);
  assert.deepEqual(view.apps.map((a) => a.toolkit), ["app-zeta"]);
  assert.equal(listReply(view).includes("Theta"), false);
});

test("the unclear reply asks and offers, and never guesses", () => {
  const reply = unclearReply();
  assert.ok(reply.trim().endsWith("?"), reply);
  assert.ok(/connect/.test(reply) && /disconnect/.test(reply), reply);
});

test("choosing an account that is not connected says so instead of pretending", () => {
  assert.ok(
    /don't have a work Zeta connected/.test(
      chooseAccountReply(meta("app-zeta", "Zeta"), {
        toolkit: "app-zeta",
        alias: "work",
        chosen: false,
      }),
    ),
  );
  assert.equal(
    chooseAccountReply(meta("app-zeta", "Zeta"), {
      toolkit: "app-zeta",
      alias: "work",
      chosen: true,
    }),
    "Got it — I'll use your work Zeta.",
  );
});

// ===========================================================================
// 8. END TO END, INTENT TO SENTENCE.
// ===========================================================================

test("handle runs each intent and returns the sentence the person reads", async () => {
  const table = tableOf([conn({ alias: "work" })]);
  const provider = providerOf({
    results: { ca_1: { revoked: true, deleted: true, revokeUnavailable: false } },
  });
  const cmds = createCommands({ table, provider, links: minterOf() });

  assert.ok((await cmds.handle(OWNER, { kind: "list" })).includes("Zeta"));
  assert.ok((await cmds.handle(OWNER, { kind: "connect", toolkit: "app-zeta" })).includes("tok_abc"));
  assert.ok(
    (await cmds.handle(OWNER, { kind: "set_writes", toolkit: "app-zeta", on: true })).includes(
      "make changes in Zeta",
    ),
  );
  assert.equal(
    await cmds.handle(OWNER, { kind: "choose_account", toolkit: "app-zeta", alias: "work" }),
    "Got it — I'll use your work Zeta.",
  );
  assert.equal(
    await cmds.handle(OWNER, { kind: "disconnect", toolkit: "app-zeta" }),
    "Done. Zeta disconnected and access revoked.",
  );
  assert.equal(await cmds.handle(OWNER, { kind: "unclear" }), unclearReply());
  // `none` was not ours to answer. Saying anything is how a connections module
  // starts replying to the rest of the product's conversations.
  assert.equal(await cmds.handle(OWNER, { kind: "none" }), "");
  assert.equal(await cmds.handle(OWNER, null as unknown as CommandIntent), unclearReply());
});

test("a provider that throws mid-disconnect does not produce a success sentence", async () => {
  const table = tableOf([
    conn({ connected_account_id: "ca_1" }),
    conn({ connected_account_id: "ca_2" }),
  ]);
  const provider = providerOf({ throwOn: "ca_2" });
  const cmds = createCommands({ table, provider, links: minterOf() });
  const reply = await cmds.handle(OWNER, { kind: "disconnect", toolkit: "app-zeta" });
  assert.equal(/revok/i.test(reply), false, reply);
  // The one that DID delete still leaves; the one that did not is still there
  // to retry, which is the only shape a retry can be built on.
  assert.equal(table.rows.find((r) => r.connected_account_id === "ca_1")?.status, "disconnected");
  assert.equal(table.rows.find((r) => r.connected_account_id === "ca_2")?.status, "connected");
});

test("a catalog lookup that fails still tells the person what happened", async () => {
  const table = tableOf([conn()]);
  const cmds = createCommands({
    table,
    provider: providerOf({ throwToolkit: true }),
    links: minterOf(),
  });
  const reply = await cmds.handle(OWNER, { kind: "disconnect", toolkit: "app-zeta" });
  assert.ok(reply.includes("app-zeta"), reply);
  assert.ok(reply.startsWith("Done."), reply);
});

test("a provider answering with something that is not a result is not a revoke", async () => {
  const table = tableOf([conn()]);
  const provider = providerOf({});
  provider.disconnect = async () => "ok" as unknown as DisconnectResult;
  const cmds = createCommands({ table, provider, links: minterOf() });
  const reply = await cmds.handle(OWNER, { kind: "disconnect", toolkit: "app-zeta" });
  assert.equal(/revok/i.test(reply), false, reply);
  assert.equal(table.rows[0]?.status, "connected");
});

// ===========================================================================
// 9. THE FOUR SOURCE LEGS.
// ===========================================================================

function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/(^|[^:])\/\/[^\n]*/g, "$1");
}

// The only list of app names this module is allowed to be near, and it lives in
// a test because HARNESS-LAWS law 1 permits pattern matching in gates.
const APP_NAMES = [
  "gmail", "googlecalendar", "google", "outlook", "slack", "notion", "github",
  "gitlab", "linear", "asana", "trello", "jira", "confluence", "salesforce",
  "hubspot", "stripe", "shopify", "twilio", "sendgrid", "airtable", "dropbox",
  "box", "zoom", "discord", "figma", "intercom", "zendesk", "quickbooks",
  "xero", "calendly", "docusign", "mailchimp", "clickup", "monday", "chrome",
  "whatsapp", "telegram", "instagram", "facebook", "twitter", "linkedin",
  "amazon", "uber", "doordash", "opentable", "spotify", "apple", "microsoft",
];

test("law 1: commands.ts names no app, in code or in prose", () => {
  const hits = APP_NAMES.filter((n) => new RegExp(`\\b${n}\\b`).test(COMMANDS_SRC.toLowerCase()));
  assert.deepEqual(hits, [], `commands.ts names apps: ${hits.join(", ")}`);
  // A leg that cannot go red is a decoration. Comment stripping is the step
  // most likely to eat the file and turn this green over nothing.
  const planted = stripComments('// c\nif (t === "slack") return 1;').toLowerCase();
  assert.ok(APP_NAMES.some((n) => new RegExp(`\\b${n}\\b`).test(planted)));
});

test("law 1: commands.ts never inspects the owner's words", () => {
  const code = stripComments(COMMANDS_SRC);
  // The phrase reaches exactly two expressions — the two judge calls — plus one
  // `typeof` that reads its JavaScript type and not its content. Any member
  // access on it is a string method, and a string method on a human sentence is
  // the thing this repo spent three months undoing.
  const forbidden: [RegExp, string][] = [
    [/\bphrase\s*\./, "a member access on the phrase"],
    [/\bsaid\s*\./, "a member access on the phrase"],
    [/(?<!typeof\s)\b(phrase|said)\s*[=!]==?\s*["'`]/, "the phrase compared to a literal"],
    [/["'`]\s*[=!]==?\s*\b(phrase|said)\b/, "the phrase compared to a literal"],
    [/\/(?![/*])(?:[^/\n\\]|\\.)+\/[gimsuy]*\s*\.\s*test\s*\(/, "a regex over the words"],
    [/\bnew\s+RegExp\b/, "a regex over the words"],
    [/\.\s*(includes|startsWith|endsWith|search|indexOf)\s*\(/, "a substring test"],
    // `.match(` is banned everywhere EXCEPT on the judge, whose contract method
    // is called `match`. Exempting the whole name would have let
    // `said.match(...)` through, which is the exact shape this leg exists for.
    [/(?<!\bjudge)\.\s*match\s*\(/, "a substring test"],
  ];
  for (const [re, what] of forbidden) {
    assert.equal(re.test(code), false, `commands.ts has ${what}: ${re}`);
  }
  // The judge is asked, and asked twice, or the module is deciding for itself.
  assert.ok(/judge\s*\.\s*action\s*\(/.test(code), "commands.ts never asks which operation");
  assert.ok(/judge\s*\.\s*match\s*\(/.test(code), "commands.ts never asks which toolkit");

  // Negative controls, one per shape.
  const violations = [
    'if (phrase.includes("send")) return connect;',
    'if (said === "what is connected") return list;',
    'if (/^connect /.test(said)) return connect;',
    'if (new RegExp("^connect").test(said)) return connect;',
    'if (said.match(WORDS)) return connect;',
  ];
  for (const v of violations) {
    assert.ok(
      forbidden.some(([re]) => re.test(v)),
      `the leg cannot catch: ${v}`,
    );
  }
});

test("law 1: every literal in a comparison is one of the module's own enum members", () => {
  const code = stripComments(COMMANDS_SRC);
  // Everything this module is allowed to branch on: its own closed sets, the
  // contract's closed sets, JavaScript's type names, and the empty string. None
  // of them can express "this app in particular" or "this wording in
  // particular", which is the property the leg is protecting.
  const allowed = new Set<string>([
    ...COMMAND_ACTIONS,
    // CommandVerdict / ToolkitVerdict kinds
    "action", "none", "unclear", "no-verdict", "toolkit",
    // CommandIntent kinds
    "list", "connect", "disconnect", "set_writes", "choose_account",
    // Connection.status
    "connected", "needs_reconnect", "disconnected",
    // Access, AccountAlias
    "read", "write", "work", "personal",
    // typeof results, and the empty string
    "string", "object", "number", "boolean", "function", "undefined", "symbol", "bigint",
    "",
  ]);
  const patterns = [
    /(?:===|!==|==(?!=)|!=(?!=))\s*("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g,
    /("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')\s*(?:===|!==|==(?!=)|!=(?!=))/g,
    /\bcase\s+("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g,
  ];
  const compared = new Set<string>();
  for (const re of patterns) {
    for (const m of code.matchAll(re)) compared.add(m[1]!.slice(1, -1));
  }
  const strays = [...compared].filter((s) => !allowed.has(s));
  assert.deepEqual(strays, [], `commands.ts branches on strings it did not declare: ${strays}`);
  // The leg has to be able to see one.
  const plantedStrays = new Set<string>();
  for (const re of patterns) {
    for (const m of 'if (x === "some-vendor") y();'.matchAll(re)) {
      plantedStrays.add(m[1]!.slice(1, -1));
    }
  }
  assert.deepEqual([...plantedStrays].filter((s) => !allowed.has(s)), ["some-vendor"]);
});

test("the register: nothing this module can say uses a forbidden word", () => {
  // The spec's rule is that the person never hears the vendor's name and never
  // hears a developer's vocabulary for what is happening. This scans STRING
  // LITERALS rather than the whole file, because citing the spec by its title
  // in a comment is Law 4 working and is not something anybody reads aloud.
  const code = stripComments(COMMANDS_SRC);
  const literals = [
    ...code.matchAll(/"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`/g),
  ].map((m) => m[0]);
  const banned = [
    /\bcomposio\b/i,
    /\bauthoriz/i,
    /\bauthoris/i,
    /grant\s+access/i,
    /\bpermission/i,
    /\bintegration/i,
    /\bapi\b/i,
    /\boauth\b/i,
    /\bscopes?\b/i,
  ];
  const offenders = literals.filter((lit) => banned.some((re) => re.test(lit)));
  assert.deepEqual(offenders, [], `commands.ts can say: ${offenders.join(" | ")}`);

  // And the same scan over every sentence the tests above actually produced,
  // because a literal assembled from two halves would slip past the source
  // scan and still reach a person.
  const spoken = [
    unclearReply(),
    connectReply(meta("app-zeta", "Zeta"), { url: "https://anticipy.ai/c/t" }),
    disconnectReply(meta("app-zeta", "Zeta"), outcome({ revoked: true, deleted: true, revokeUnavailable: false })),
    disconnectReply(meta("app-zeta", "Zeta"), outcome({ revoked: false, deleted: true, revokeUnavailable: true })),
    disconnectReply(meta("app-zeta", "Zeta"), outcome({ revoked: true, deleted: false, revokeUnavailable: false })),
    disconnectReply(meta("app-zeta", "Zeta"), outcome({ revoked: false, deleted: false, revokeUnavailable: false })),
    disconnectReply(meta("app-zeta", "Zeta"), outcome({ revoked: false, deleted: false, revokeUnavailable: false }, 0)),
    writesReply(meta("app-zeta", "Zeta"), { toolkit: "app-zeta", enabled: true, applied: true, accounts: 1 }),
    writesReply(meta("app-zeta", "Zeta"), { toolkit: "app-zeta", enabled: false, applied: true, accounts: 1 }),
    writesReply(meta("app-zeta", "Zeta"), { toolkit: "app-zeta", enabled: false, applied: false, accounts: 0 }),
    chooseAccountReply(meta("app-zeta", "Zeta"), { toolkit: "app-zeta", alias: "work", chosen: true }),
    chooseAccountReply(meta("app-zeta", "Zeta"), { toolkit: "app-zeta", alias: "work", chosen: false }),
    listReply(settingsView([], CATALOG_A)),
    listReply(settingsView([conn({ alias: "work", writes_enabled: true })], CATALOG_A)),
  ];
  const said = spoken.filter((s) => banned.some((re) => re.test(s)));
  assert.deepEqual(said, [], `spoken: ${said.join(" | ")}`);
  assert.ok(banned.some((re) => re.test("we will authorize the integration")));
});

test("commands.ts imports nothing but its own contract", () => {
  // The rest of `src/connections/` is being written beside this file. An import
  // of one of those modules would make this suite green against a file that
  // does not exist yet and red the morning somebody renames it.
  const code = stripComments(COMMANDS_SRC);
  const specifiers = [...code.matchAll(/\bfrom\s+["']([^"']+)["']/g)].map((m) => m[1]!);
  assert.deepEqual(specifiers, ["./contract.ts"], `commands.ts imports: ${specifiers.join(", ")}`);
});
