/**
 * test/connections-text-commands.test.ts — THE TEXT TWIN, judged.
 *
 *   node --experimental-strip-types migration/workers/test/connections-text-commands.test.ts
 *
 * WHAT IS REAL HERE. The module under test, entirely. What is faked is the
 * only thing that CAN be faked without lying: the model, and the catalog feed.
 * Both are the module's declared seams, and the point of every fixture below
 * is that the module never reads a word of the sentence for itself — so the
 * judge in these tests very often answers something the words do not support,
 * and the module obeys it. That is not a sloppy fixture. It IS the law-1
 * property, made behavioural: hand it "connect notion" and a judge that says
 * `wobblefish`, and the plan says wobblefish, because this file does not know
 * what "notion" is and must never learn.
 *
 * NO REAL APP IS NAMED IN A CATALOG HERE. `zzquixotic`, `wobblefish` and
 * `plinthworks` are in no catalog anybody has ever shipped. Real app names DO
 * appear as the human's own sentences, which is the other half of the same
 * proof: the words a person types are inert.
 *
 * THE FAILURES THIS FILE EXISTS TO CATCH:
 *
 *   THE MODULE THAT GRABS EVERY MESSAGE. An inbound text thread's ordinary
 *   traffic is conversation. A listener that claims a message when its judge
 *   says "not mine", says "I can't tell", or says nothing at all, silently
 *   eats the product. Section 2.
 *
 *   DISCONNECTING THE WRONG APP. An action taken on an unclear, absent or
 *   invented app. Section 3 drives every shape a judge can fail in, and
 *   section 5 drives the one that would leak somebody ELSE'S catalog into
 *   this owner's plan.
 *
 *   THE READ HELD HOSTAGE. "what's connected" names no app, so nothing about
 *   apps may stop it. Section 4 breaks the catalog and the toolkit judge and
 *   still expects an answer.
 *
 *   A VENDOR FEED WRITING OUR TEXT MESSAGES. Every app name a reply says comes
 *   from a catalog row at run time. Section 10 puts a link, a newline and a
 *   paragraph in that field.
 *
 *   A KEYWORD LIST GROWING BACK. Section 12 reads the module's own source.
 *
 * MUTATIONS THIS FILE MUST GO RED ON: the list at the bottom, each anchored on
 * a string the source contains EXACTLY ONCE — asserted, because a mutation
 * anchor that matches nothing has produced several false "it is tested"
 * readings in this repo this week.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import {
  MAX_APP_NAME_CHARS,
  TEXT_COMMANDS,
  displayName,
  planTextCommand,
  type TextCommandDeps,
  type TextCommandJudge,
  type TextCommandPlan,
} from "../src/connections/text_commands.ts";
import { FORBIDDEN_TERMS } from "../src/connections/words.ts";
import type { ToolkitMeta } from "../../../spike/two-hands/src/connections/contract.ts";

const here = dirname(fileURLToPath(import.meta.url));
const SRC_PATH = join(here, "..", "src", "connections", "text_commands.ts");
const SRC = readFileSync(SRC_PATH, "utf8");

let failures = 0;
let passes = 0;
async function check(what: string, fn: () => void | Promise<void>): Promise<void> {
  try { await fn(); passes++; }
  catch (err) { failures++; console.error("FAIL " + what + "\n     " + (err as Error).message); }
}

// ---------------------------------------------------------------------------
// FIXTURES
// ---------------------------------------------------------------------------

/** 15 lowercase alphanumerics, the shape D1 mints and the only shape the
 *  owner-id rule accepts. */
const OWNER_A = "ownertxtaaaa111";
const OWNER_B = "ownertxtbbbb222";

function meta(slug: string, name: string, over: Partial<ToolkitMeta> = {}): ToolkitMeta {
  return { slug, name, logo: null, description: null, appUrl: null, scopes: [], ...over };
}

/** Two invented apps for owner A, one for owner B. Nothing here is in any
 *  catalog, which is what makes "NO APP IS HARDCODED" a measurement. */
const QUIXOTIC = meta("zzquixotic", "Quixotic");
const WOBBLE = meta("wobblefish", "Wobblefish");
const PLINTH = meta("plinthworks", "Plinth Works");
const CATALOG_A: ToolkitMeta[] = [QUIXOTIC, WOBBLE];
const CATALOG_B: ToolkitMeta[] = [PLINTH];

const cmd = (command: string) => ({ kind: "command", command });
const tk = (slug: unknown) => ({ kind: "toolkit", slug });

type Answer = unknown | ((phrase: string) => unknown);

interface Rig {
  deps: TextCommandDeps;
  commandCalls: { phrase: string; menu: readonly string[] }[];
  matchCalls: { phrase: string; menu: ToolkitMeta[] }[];
  catalogCalls: string[];
}

function rig(opts: {
  command?: Answer;
  match?: Answer;
  catalog?: Record<string, readonly ToolkitMeta[]> | ((owner: string) => unknown);
} = {}): Rig {
  const commandCalls: { phrase: string; menu: readonly string[] }[] = [];
  const matchCalls: { phrase: string; menu: ToolkitMeta[] }[] = [];
  const catalogCalls: string[] = [];
  const answer = (a: Answer, phrase: string): unknown =>
    typeof a === "function" ? (a as (p: string) => unknown)(phrase) : a;

  const judge: TextCommandJudge = {
    async command(phrase, commands) {
      commandCalls.push({ phrase, menu: [...commands] });
      return answer(opts.command, phrase);
    },
    async match(phrase, catalog) {
      matchCalls.push({ phrase, menu: [...catalog] });
      // The scripted answer gets the array the module actually handed over, so
      // a leg can try to mutate it.
      return typeof opts.match === "function"
        ? (opts.match as (p: string, c: ToolkitMeta[]) => unknown)(phrase, catalog)
        : opts.match;
    },
  };
  const deps: TextCommandDeps = {
    async catalog(owner) {
      catalogCalls.push(owner);
      const c = opts.catalog;
      if (typeof c === "function") return c(owner) as readonly ToolkitMeta[];
      if (c === undefined) return CATALOG_A;
      return c[owner] ?? [];
    },
    judge,
  };
  return { deps, commandCalls, matchCalls, catalogCalls };
}

/** The four action members — every command that touches one app. */
const ACTION_COMMANDS = TEXT_COMMANDS.filter((c) => c !== "list_connected");

// ===========================================================================
// 1. THE FOUR INTENTS — the spec's own four sentences, and many it never wrote
// ===========================================================================

await check("the spec's own four sentences each produce their plan", async () => {
  // The judge answers; the words are inert. "connect notion" resolving to an
  // invented slug is the point, not an oversight.
  const a = rig({ command: cmd("connect_app"), match: tk("zzquixotic") });
  assert.deepEqual(await planTextCommand(OWNER_A as never, "connect notion", a.deps), {
    kind: "connect", owner: OWNER_A, toolkit: "zzquixotic", appName: "Quixotic",
  });

  const b = rig({ command: cmd("list_connected") });
  assert.deepEqual(await planTextCommand(OWNER_A as never, "what's connected", b.deps), {
    kind: "list_connections", owner: OWNER_A,
  });

  const c = rig({ command: cmd("disconnect_app"), match: tk("wobblefish") });
  assert.deepEqual(await planTextCommand(OWNER_A as never, "disconnect slack", c.deps), {
    kind: "disconnect", owner: OWNER_A, toolkit: "wobblefish", appName: "Wobblefish",
  });

  const d = rig({ command: cmd("use_work_account"), match: tk("zzquixotic") });
  assert.deepEqual(
    await planTextCommand(OWNER_A as never, "use my work Gmail for this", d.deps),
    {
      kind: "choose_account", owner: OWNER_A, toolkit: "zzquixotic",
      appName: "Quixotic", alias: "work",
    },
  );
});

await check("CONTROL: a plain 'connect notion' resolves", async () => {
  const r = rig({ command: cmd("connect_app"), match: tk("zzquixotic") });
  const plan = await planTextCommand(OWNER_A as never, "connect notion", r.deps);
  assert.equal(plan.kind, "connect");
  assert.equal((plan as { toolkit: string }).toolkit, "zzquixotic");
  assert.equal(r.commandCalls.length, 1);
  assert.equal(r.matchCalls.length, 1);
});

await check("the personal account member is the other half of the alias flow", async () => {
  const r = rig({ command: cmd("use_personal_account"), match: tk("wobblefish") });
  const plan = await planTextCommand(OWNER_A as never, "no, my own one", r.deps);
  assert.deepEqual(plan, {
    kind: "choose_account", owner: OWNER_A, toolkit: "wobblefish",
    appName: "Wobblefish", alias: "personal",
  });
});

await check("phrasings the spec never lists reach the same four plans", async () => {
  // Every sentence below is one the spec does not contain. The judge answers
  // the same thing for all of them, so what is being measured is that the
  // MODULE contributes nothing: no phrasing here is easier or harder for it.
  const connectish = [
    "hook me up with quixotic",
    "can you just get into it directly instead of the browser",
    "sign yourself in to quixotic so it's quicker",
    "stop doing this the slow way, take quixotic",
    "quixotic pls",
    "",
  ];
  for (const said of connectish) {
    const r = rig({ command: cmd("connect_app"), match: tk("zzquixotic") });
    const plan = await planTextCommand(OWNER_A as never, said, r.deps);
    assert.equal(plan.kind, "connect", said);
    assert.equal(r.commandCalls[0]?.phrase, said, "the phrase went to the judge verbatim");
  }

  const listish = [
    "which of my apps do you have",
    "remind me what i've hooked up",
    "what have i already given you",
    "status on my apps?",
  ];
  for (const said of listish) {
    const r = rig({ command: cmd("list_connected") });
    assert.equal((await planTextCommand(OWNER_A as never, said, r.deps)).kind,
      "list_connections", said);
  }

  const disconnectish = [
    "cut wobblefish loose",
    "i don't want you in there any more",
    "take yourself off that one",
    "undo the wobblefish thing",
  ];
  for (const said of disconnectish) {
    const r = rig({ command: cmd("disconnect_app"), match: tk("wobblefish") });
    assert.equal((await planTextCommand(OWNER_A as never, said, r.deps)).kind,
      "disconnect", said);
  }

  const accountish = [
    "the work one for this",
    "use my job account here",
    "not that inbox, the other one — work",
  ];
  for (const said of accountish) {
    const r = rig({ command: cmd("use_work_account"), match: tk("zzquixotic") });
    const plan = await planTextCommand(OWNER_A as never, said, r.deps);
    assert.equal(plan.kind, "choose_account", said);
    assert.equal((plan as { alias: string }).alias, "work", said);
  }
});

await check("the owner's words reach the judge byte for byte", async () => {
  const said = "  DISCONNECT   Wobblefish!!! \n\t🙂 zzz-secret-marker  ";
  const r = rig({ command: cmd("disconnect_app"), match: tk("wobblefish") });
  const plan = await planTextCommand(OWNER_A as never, said, r.deps);
  assert.equal(r.commandCalls[0]?.phrase, said);
  assert.equal(r.matchCalls[0]?.phrase, said);
  // ...and no further than the judge. The plan is a decision, not a copy of
  // somebody's text message travelling on to whatever logs the caller keeps.
  assert.equal(JSON.stringify(plan).includes("zzz-secret-marker"), false);
});

// ===========================================================================
// 2. ORDINARY CONVERSATION FALLS THROUGH, AND COSTS NOTHING
// ===========================================================================

const ORDINARY = [
  "can you move my 3pm to thursday",
  "tell priya i'm running late",
  "what's the weather like in london",
  "yes",
  "",
  "connect the dots for me on that pricing thing",
];

await check("a message about none of the four is left alone", async () => {
  for (const said of ORDINARY) {
    const r = rig({ command: { kind: "none" }, match: tk("zzquixotic") });
    assert.deepEqual(await planTextCommand(OWNER_A as never, said, r.deps),
      { kind: "not_for_us", because: "none" }, said);
    assert.equal(r.matchCalls.length, 0, "the second question was asked anyway: " + said);
    assert.equal(r.catalogCalls.length, 0, "the catalog was fetched anyway: " + said);
  }
});

await check("an unclear first answer falls through rather than grabbing the message", async () => {
  const r = rig({ command: { kind: "unclear" }, match: tk("zzquixotic") });
  assert.deepEqual(await planTextCommand(OWNER_A as never, "sort out my slack thing", r.deps),
    { kind: "not_for_us", because: "unclear" });
  assert.equal(r.matchCalls.length, 0);
});

await check("no verdict on the first question falls through, and says which", async () => {
  const shapes: [string, Answer][] = [
    ["the judge said so", { kind: "no-verdict" }],
    ["the judge threw", () => { throw new Error("model down"); }],
    ["a rejected promise", () => Promise.reject(new Error("upstream 502"))],
    ["null", null],
    ["undefined", undefined],
    ["a bare string", "connect_app"],
    ["a number", 7],
    ["an array", ["connect_app"]],
    ["a kind we never defined", { kind: "do_it" }],
    ["a command key with no kind", { command: "connect_app" }],
    ["a member outside the menu", cmd("delete_everything")],
    ["a member in the wrong case", cmd("CONNECT_APP")],
    ["kind command with no command", { kind: "command" }],
    ["kind command with a numeric command", { kind: "command", command: 1 }],
  ];
  for (const [what, command] of shapes) {
    const r = rig({ command, match: tk("zzquixotic") });
    assert.deepEqual(await planTextCommand(OWNER_A as never, "hello", r.deps),
      { kind: "not_for_us", because: "no-verdict" }, what);
    assert.equal(r.matchCalls.length, 0, "acted on junk: " + what);
  }
});

await check("CONTROL: the same rig with a good answer does claim the message", async () => {
  const r = rig({ command: cmd("connect_app"), match: tk("zzquixotic") });
  assert.equal((await planTextCommand(OWNER_A as never, "hello", r.deps)).kind, "connect");
});

// ===========================================================================
// 3. AN AMBIGUOUS APP REFUSES AN ACTION AND SAYS SO
// ===========================================================================

await check("every action refuses on an app the judge could not pin down", async () => {
  const shapes: [string, Answer, string][] = [
    ["they named no app", { kind: "none" }, "none"],
    ["the judge could not tell", { kind: "unclear" }, "unclear"],
    ["the judge abstained", { kind: "no-verdict" }, "no-verdict"],
    ["the judge threw", () => { throw new Error("model down"); }, "no-verdict"],
    ["a rejected promise", () => Promise.reject(new Error("502")), "no-verdict"],
    ["null", null, "no-verdict"],
    ["a bare slug string", "zzquixotic", "no-verdict"],
    ["a kind we never defined", { kind: "app", slug: "zzquixotic" }, "no-verdict"],
    ["kind toolkit with no slug", { kind: "toolkit" }, "no-verdict"],
    ["kind toolkit with a numeric slug", tk(42), "no-verdict"],
    ["kind toolkit with an empty slug", tk("   "), "no-verdict"],
    ["an app we never offered", tk("dropbox"), "off-catalog"],
  ];
  for (const command of ACTION_COMMANDS) {
    for (const [what, match, because] of shapes) {
      const r = rig({ command: cmd(command), match });
      const plan = await planTextCommand(OWNER_A as never, "do the thing", r.deps);
      assert.deepEqual(plan, { kind: "ask_which_app", owner: OWNER_A, wanted: command, because },
        `${command} / ${what}`);
    }
  }
});

await check("CONTROL: each action still resolves when the app is unambiguous", async () => {
  const expected: Record<string, string> = {
    connect_app: "connect",
    disconnect_app: "disconnect",
    use_work_account: "choose_account",
    use_personal_account: "choose_account",
  };
  for (const command of ACTION_COMMANDS) {
    const r = rig({ command: cmd(command), match: tk("zzquixotic") });
    const plan = await planTextCommand(OWNER_A as never, "do the thing", r.deps);
    assert.equal(plan.kind, expected[command], command);
    assert.equal((plan as { toolkit: string }).toolkit, "zzquixotic", command);
  }
});

await check("a refusal names what they asked for, so the question can too", async () => {
  for (const command of ACTION_COMMANDS) {
    const r = rig({ command: cmd(command), match: { kind: "unclear" } });
    const plan = await planTextCommand(OWNER_A as never, "that one", r.deps);
    assert.equal((plan as { wanted: string }).wanted, command);
  }
});

// ===========================================================================
// 4. THE READ IS NEVER HELD HOSTAGE BY AN APP
// ===========================================================================

await check("'what's connected' answers with the catalog down and the app judge broken", async () => {
  const r = rig({
    command: cmd("list_connected"),
    match: () => { throw new Error("this must never be called"); },
    catalog: () => { throw new Error("catalog feed is down"); },
  });
  assert.deepEqual(await planTextCommand(OWNER_A as never, "what's connected", r.deps),
    { kind: "list_connections", owner: OWNER_A });
  assert.equal(r.matchCalls.length, 0, "the read asked which app");
  assert.equal(r.catalogCalls.length, 0, "the read fetched a catalog it cannot use");
});

await check("the read costs exactly one model call", async () => {
  const r = rig({ command: cmd("list_connected") });
  await planTextCommand(OWNER_A as never, "what have you got", r.deps);
  assert.equal(r.commandCalls.length, 1);
  assert.equal(r.matchCalls.length, 0);
});

// ===========================================================================
// 5. TWO OWNERS' CATALOGS NEVER CROSS
// ===========================================================================

await check("an app from the other owner's catalog is not an app for this one", async () => {
  const byOwner = { [OWNER_A]: CATALOG_A, [OWNER_B]: CATALOG_B };
  // One judge, one answer, two owners: the ONLY difference is whose catalog
  // was fetched.
  const a = rig({ command: cmd("disconnect_app"), match: tk("plinthworks"), catalog: byOwner });
  assert.deepEqual(await planTextCommand(OWNER_A as never, "disconnect plinth", a.deps),
    { kind: "ask_which_app", owner: OWNER_A, wanted: "disconnect_app", because: "off-catalog" });

  // CONTROL: the owner who actually has it gets the plan.
  const b = rig({ command: cmd("disconnect_app"), match: tk("plinthworks"), catalog: byOwner });
  assert.deepEqual(await planTextCommand(OWNER_B as never, "disconnect plinth", b.deps),
    { kind: "disconnect", owner: OWNER_B, toolkit: "plinthworks", appName: "Plinth Works" });

  // And the other direction, so the leg is not passing on alphabetical luck.
  const c = rig({ command: cmd("connect_app"), match: tk("zzquixotic"), catalog: byOwner });
  assert.equal((await planTextCommand(OWNER_B as never, "connect quixotic", c.deps)).kind,
    "ask_which_app");
});

await check("the app judge is handed this owner's rows and no others", async () => {
  const byOwner = { [OWNER_A]: CATALOG_A, [OWNER_B]: CATALOG_B };
  const r = rig({ command: cmd("connect_app"), match: tk("zzquixotic"), catalog: byOwner });
  await planTextCommand(OWNER_A as never, "connect it", r.deps);
  assert.deepEqual(r.catalogCalls, [OWNER_A]);
  assert.deepEqual(r.matchCalls[0]?.menu.map((m) => m.slug), ["zzquixotic", "wobblefish"]);

  const s = rig({ command: cmd("connect_app"), match: tk("plinthworks"), catalog: byOwner });
  await planTextCommand(OWNER_B as never, "connect it", s.deps);
  assert.deepEqual(s.catalogCalls, [OWNER_B]);
  assert.deepEqual(s.matchCalls[0]?.menu.map((m) => m.slug), ["plinthworks"]);
});

// ===========================================================================
// 6. THE SLUG THAT TRAVELS IS THE CATALOG'S, NEVER THE MODEL'S
// ===========================================================================

await check("a slug in the wrong case identifies the app and the catalog's string travels", async () => {
  const r = rig({ command: cmd("connect_app"), match: tk("ZZQuixotic") });
  const plan = await planTextCommand(OWNER_A as never, "connect it", r.deps);
  assert.equal((plan as { toolkit: string }).toolkit, "zzquixotic");
});

await check("a padded slug identifies the app, and the padding does not travel", async () => {
  const r = rig({ command: cmd("connect_app"), match: tk("  wobblefish  ") });
  const plan = await planTextCommand(OWNER_A as never, "connect it", r.deps);
  assert.equal((plan as { toolkit: string }).toolkit, "wobblefish");
});

await check("a slug that only prefixes a real one is not that app", async () => {
  const r = rig({ command: cmd("disconnect_app"), match: tk("wobble") });
  assert.equal((await planTextCommand(OWNER_A as never, "x", r.deps) as { because: string }).because,
    "off-catalog");
});

// ===========================================================================
// 7. NO CATALOG IS ITS OWN ANSWER, AND IT NEVER BECOMES A THROW
// ===========================================================================

await check("an unreadable catalog refuses the action by name and spends no model call", async () => {
  const shapes: [string, Record<string, readonly ToolkitMeta[]> | ((o: string) => unknown)][] = [
    ["the feed threw", () => { throw new Error("feed down"); }],
    ["a rejected promise", () => Promise.reject(new Error("feed 500"))],
    ["null", () => null],
    ["undefined", () => undefined],
    ["not an array", () => ({ items: CATALOG_A })],
    ["empty", () => []],
    ["only rows with no slug", () => [{ name: "Nameless" }, { slug: "   ", name: "Blank" }]],
  ];
  for (const [what, catalog] of shapes) {
    const r = rig({ command: cmd("connect_app"), match: tk("zzquixotic"), catalog });
    assert.deepEqual(await planTextCommand(OWNER_A as never, "connect it", r.deps),
      { kind: "ask_which_app", owner: OWNER_A, wanted: "connect_app", because: "no-catalog" },
      what);
    assert.equal(r.matchCalls.length, 0, "asked a model to pick from nothing: " + what);
  }
});

await check("one malformed row does not cost the rest of the catalog", async () => {
  const r = rig({
    command: cmd("connect_app"),
    match: tk("wobblefish"),
    catalog: () => [{ name: "Nameless" }, WOBBLE, { slug: "", name: "Blank" }],
  });
  const plan = await planTextCommand(OWNER_A as never, "connect it", r.deps);
  assert.equal(plan.kind, "connect");
  assert.deepEqual(r.matchCalls[0]?.menu.map((m) => m.slug), ["wobblefish"]);
});

// ===========================================================================
// 8. THE OWNER COMES FROM THE CALLER'S AUTH, AND IS CHECKED AT RUN TIME
// ===========================================================================

await check("a name, an email or an empty owner throws rather than planning", async () => {
  const bad = ["", "omar", "omar@anticipy.ai", "OWNERTXTAAAA111", "short", "ownertxtaaaa1111",
    "owner txtaaa111", null, undefined, 12345];
  for (const who of bad) {
    const r = rig({ command: cmd("list_connected") });
    await assert.rejects(
      () => planTextCommand(who as never, "what's connected", r.deps),
      /not an owner id/,
      String(who),
    );
    assert.equal(r.commandCalls.length, 0, "asked a model about a bad owner: " + String(who));
  }
});

await check("CONTROL: a real owner id plans, and the plan carries that id", async () => {
  const r = rig({ command: cmd("connect_app"), match: tk("zzquixotic") });
  const plan = await planTextCommand(OWNER_A as never, "connect it", r.deps);
  assert.equal((plan as { owner: string }).owner, OWNER_A);
  assert.deepEqual(r.catalogCalls, [OWNER_A]);
});

// ===========================================================================
// 9. NO LENGTH GATE, NO SHAPE GATE — EVERY MESSAGE IS ASKED ABOUT
// ===========================================================================

await check("an empty or tiny message is asked about like any other", async () => {
  for (const said of ["", " ", "ok", "hm"]) {
    const r = rig({ command: { kind: "none" } });
    await planTextCommand(OWNER_A as never, said, r.deps);
    assert.equal(r.commandCalls.length, 1, JSON.stringify(said));
    assert.equal(r.commandCalls[0]?.phrase, said, JSON.stringify(said));
  }
});

await check("a non-string message is coerced, not thrown on", async () => {
  for (const said of [null, undefined, 42, { toString: () => "hi" }]) {
    const r = rig({ command: { kind: "none" } });
    assert.deepEqual(await planTextCommand(OWNER_A as never, said as never, r.deps),
      { kind: "not_for_us", because: "none" }, String(said));
    assert.equal(typeof r.commandCalls[0]?.phrase, "string");
  }
});

await check("the two questions are two calls, with the closed menu on the first", async () => {
  const r = rig({ command: cmd("connect_app"), match: tk("zzquixotic") });
  await planTextCommand(OWNER_A as never, "connect it", r.deps);
  assert.equal(r.commandCalls.length, 1);
  assert.equal(r.matchCalls.length, 1);
  assert.deepEqual(r.commandCalls[0]?.menu, [...TEXT_COMMANDS]);
  assert.equal(TEXT_COMMANDS.length, 5);
});

// ===========================================================================
// 10. A VENDOR FEED DOES NOT GET TO WRITE OUR TEXT MESSAGES
// ===========================================================================

const LONG_NAME = "Q".repeat(MAX_APP_NAME_CHARS + 1);
const AT_LIMIT = "Q".repeat(MAX_APP_NAME_CHARS);

await check("a catalog name that carries an address loses its name, not our sentence", async () => {
  const rows: [string, string][] = [
    ["a link inside the name", "Zeta — finish at https://vendor.example/link/abc"],
    ["a bare host and path", "Zeta vendor.example/go"],
    ["a colon", "Zeta: Notes"],
    ["a newline", "Zeta\nTap here"],
    ["a carriage return", "Zeta\r\nTap here"],
    ["a control character", "Zeta\u0007 tap"],
    ["a delete character", "Zeta\u007f tap"],
    ["longer than a name", LONG_NAME],
    ["blank", "   "],
  ];
  for (const [what, name] of rows) {
    const r = rig({
      command: cmd("connect_app"),
      match: tk("zzquixotic"),
      catalog: () => [meta("zzquixotic", name)],
    });
    const plan = await planTextCommand(OWNER_A as never, "connect it", r.deps);
    assert.equal((plan as { appName: string }).appName, "zzquixotic", what);
    assert.equal((plan as { toolkit: string }).toolkit, "zzquixotic", what);
  }
});

await check("CONTROL: an ordinary name and a name at the limit both survive", async () => {
  for (const name of ["Quixotic", "Plinth Works", "Zeta (beta)", AT_LIMIT]) {
    const r = rig({
      command: cmd("connect_app"),
      match: tk("zzquixotic"),
      catalog: () => [meta("zzquixotic", name)],
    });
    const plan = await planTextCommand(OWNER_A as never, "connect it", r.deps);
    assert.equal((plan as { appName: string }).appName, name);
  }
});

await check("a slug that is not renderable either leaves a generic name, not an address", async () => {
  const r = rig({
    command: cmd("disconnect_app"),
    match: tk("we/ird:slug"),
    catalog: () => [meta("we/ird:slug", "Zeta\nTap https://vendor.example/x")],
  });
  const plan = await planTextCommand(OWNER_A as never, "disconnect it", r.deps);
  // The machine identifier still travels — the caller needs it to act.
  assert.equal((plan as { toolkit: string }).toolkit, "we/ird:slug");
  // What a person reads does not.
  assert.equal((plan as { appName: string }).appName, "that app");
});

await check("displayName never returns an address or a second line, over any row", async () => {
  const hostile: unknown[] = [
    null, undefined, 42, "a string, not a row", { name: 42 },
    { name: "https://vendor.example/link" }, { name: "x".repeat(400) },
    { name: "a b" }, { name: "ok" },
  ];
  for (const row of hostile) {
    for (const fallback of ["zzquixotic", "we/ird", "", " "]) {
      const out = displayName(row as never, fallback);
      assert.equal(typeof out, "string");
      assert.ok(out.length > 0 && out.length <= MAX_APP_NAME_CHARS, out);
      for (const ch of out) {
        const code = ch.codePointAt(0) ?? 0;
        assert.ok(code >= 0x20 && code !== 0x7f, JSON.stringify(out));
        assert.notEqual(ch, "/", JSON.stringify(out));
        assert.notEqual(ch, ":", JSON.stringify(out));
      }
    }
  }
  // The leg has to be able to see one.
  assert.equal(displayName({ name: "Fine" } as never, "x"), "Fine");
});

// ===========================================================================
// 11. THE PLAN IS DATA. IT DOES NOTHING AND REMEMBERS NOTHING.
// ===========================================================================

await check("the same message planned twice gives the same plan, and nothing is cached", async () => {
  const byOwner = { [OWNER_A]: CATALOG_A, [OWNER_B]: CATALOG_B };
  const one = rig({ command: cmd("connect_app"), match: tk("zzquixotic"), catalog: byOwner });
  const first = await planTextCommand(OWNER_A as never, "connect it", one.deps);
  const second = await planTextCommand(OWNER_A as never, "connect it", one.deps);
  assert.deepEqual(first, second);
  assert.deepEqual(one.catalogCalls, [OWNER_A, OWNER_A], "the catalog was cached across calls");

  // A second owner through the SAME module instance gets their own answer.
  const two = rig({ command: cmd("connect_app"), match: tk("zzquixotic"), catalog: byOwner });
  assert.equal((await planTextCommand(OWNER_B as never, "connect it", two.deps)).kind,
    "ask_which_app");
});

await check("every plan kind is one of the six declared, with no extra keys", async () => {
  const kinds = new Set<string>();
  const seen: TextCommandPlan[] = [];
  const cases: { command: unknown; match?: unknown; catalog?: () => unknown }[] = [
    { command: { kind: "none" } },
    { command: { kind: "unclear" } },
    { command: { kind: "no-verdict" } },
    { command: cmd("list_connected") },
    { command: cmd("connect_app"), match: tk("zzquixotic") },
    { command: cmd("disconnect_app"), match: tk("zzquixotic") },
    { command: cmd("use_work_account"), match: tk("zzquixotic") },
    { command: cmd("use_personal_account"), match: tk("zzquixotic") },
    { command: cmd("connect_app"), match: { kind: "unclear" } },
  ];
  for (const c of cases) {
    const r = rig(c as never);
    const plan = await planTextCommand(OWNER_A as never, "x", r.deps);
    kinds.add(plan.kind);
    seen.push(plan);
  }
  assert.deepEqual([...kinds].sort(), [
    "ask_which_app", "choose_account", "connect", "disconnect",
    "list_connections", "not_for_us",
  ]);
  const allowed = new Set(["kind", "because", "owner", "toolkit", "appName", "alias", "wanted"]);
  for (const plan of seen) {
    for (const key of Object.keys(plan)) assert.ok(allowed.has(key), key);
  }
});

await check("a judge cannot widen the menu it was handed", async () => {
  // The list of operations is handed to the model and is then the membership
  // test its answer has to pass. If it were mutable, an implementation that
  // appended to it — a house option, an in-place sort by a mutating helper —
  // would be writing the module's own closed set at run time.
  assert.ok(Object.isFrozen(TEXT_COMMANDS));
  const r = rig({
    command: () => {
      try { (TEXT_COMMANDS as unknown as string[]).push("delete_everything"); } catch { /* frozen */ }
      return cmd("delete_everything");
    },
    match: tk("zzquixotic"),
  });
  assert.deepEqual(await planTextCommand(OWNER_A as never, "x", r.deps),
    { kind: "not_for_us", because: "no-verdict" });
  assert.equal(TEXT_COMMANDS.length, 5, "the menu grew");
  assert.equal(TEXT_COMMANDS.includes("delete_everything" as never), false);
});

await check("a judge cannot invent an app by appending to the list it was handed", async () => {
  const r = rig({
    command: cmd("disconnect_app"),
    // The judge appends a row to the very array it was handed, then names it.
    // The membership test runs against the rows the CATALOG returned, so this
    // must not become an app.
    match: ((_p: string, given: ToolkitMeta[]) => {
      given.push(meta("invented", "Invented"));
      return tk("invented");
    }) as never,
  });
  assert.deepEqual(await planTextCommand(OWNER_A as never, "disconnect it", r.deps),
    { kind: "ask_which_app", owner: OWNER_A, wanted: "disconnect_app", because: "off-catalog" });
  // CONTROL: the same rig answering with a row that WAS on the list resolves.
  const ok = rig({ command: cmd("disconnect_app"), match: tk("wobblefish") });
  assert.equal((await planTextCommand(OWNER_A as never, "disconnect it", ok.deps)).kind,
    "disconnect");
});

// ===========================================================================
// 12. THE SOURCE LEGS — law 1, the register, and what may be imported.
// ===========================================================================

function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/(^|[^:])\/\/[^\n]*/g, "$1");
}
const CODE = stripComments(SRC);

// The only list of app names this file is allowed to be near, and it lives in
// a TEST because HARNESS-LAWS law 1 permits pattern matching in gates.
const APP_NAMES = [
  "gmail", "googlecalendar", "outlook", "slack", "notion", "github", "gitlab",
  "linear", "asana", "trello", "jira", "confluence", "salesforce", "hubspot",
  "stripe", "shopify", "twilio", "sendgrid", "airtable", "dropbox", "box",
  "zoom", "discord", "figma", "intercom", "zendesk", "quickbooks", "xero",
  "calendly", "docusign", "mailchimp", "clickup", "monday", "whatsapp",
  "telegram", "instagram", "facebook", "linkedin", "spotify", "microsoft",
  "google", "apple",
];

await check("law 1: no app is named in the module's CODE", async () => {
  // Prose is exempt and the exemption is deliberate: the header quotes the
  // spec's own four example sentences, and a header that cannot quote its
  // spec drifts from it (law 4). A comment cannot make an app special at run
  // time; a branch can, and every branch is in `CODE`.
  const hits = APP_NAMES.filter((n) => new RegExp(`\\b${n}\\b`).test(CODE.toLowerCase()));
  assert.deepEqual(hits, [], `text_commands.ts branches on apps: ${hits.join(", ")}`);
  // A leg that cannot go red is a decoration. Comment stripping is the step
  // most likely to eat the file and turn this green over nothing.
  const planted = stripComments('// c\nif (t === "slack") return 1;').toLowerCase();
  assert.ok(APP_NAMES.some((n) => new RegExp(`\\b${n}\\b`).test(planted)));
  assert.ok(CODE.includes("planTextCommand"), "comment stripping ate the file");
});

await check("law 1: the vendor's name appears nowhere in the file at all", async () => {
  assert.equal(/composio/i.test(SRC), false, "text_commands.ts names the vendor");
  assert.ok(/composio/i.test("Composio wants access"), "the leg cannot see one");
});

await check("law 1: the module never inspects the owner's words", async () => {
  // The phrase reaches exactly two expressions — the two judge calls — plus one
  // `typeof` that reads its JavaScript type and not its content. Any member
  // access on it is a string method, and a string method on a human sentence is
  // the thing this repo spent three months undoing.
  const forbidden: [RegExp, string][] = [
    [/\b(phrase|said|text)\s*\./, "a member access on the owner's words"],
    [/(?<!typeof\s)\b(phrase|said|text)\s*[=!]==?\s*["'`]/, "the words compared to a literal"],
    [/["'`]\s*[=!]==?\s*\b(phrase|said|text)\b/, "the words compared to a literal"],
    [/\/(?![/*])(?:[^/\n\\]|\\.)+\/[gimsuy]*\s*\.\s*test\s*\(/, "a regex over the words"],
    [/\bnew\s+RegExp\b/, "a regex built at run time"],
    [/\.\s*(includes|startsWith|endsWith|search|indexOf|split)\s*\(/, "a substring test"],
    // `.match(` is banned everywhere EXCEPT on the judge, whose contract method
    // is called `match`. Exempting the whole name would have let
    // `said.match(...)` through, which is the exact shape this leg exists for.
    [/(?<!\bjudge)\.\s*match\s*\(/, "a substring test"],
    [/\b(phrase|said|text)\s*\.\s*length\b/, "a length gate on the owner's words"],
  ];
  for (const [re, what] of forbidden) {
    assert.equal(re.test(CODE), false, `text_commands.ts has ${what}: ${re}`);
  }
  // The judge is asked, and asked twice, or the module is deciding for itself.
  assert.ok(/judge\s*\.\s*command\s*\(/.test(CODE), "it never asks which operation");
  assert.ok(/judge\s*\.\s*match\s*\(/.test(CODE), "it never asks which app");

  // Negative controls, one per shape, so no leg above is a decoration.
  const violations = [
    'if (said.includes("connect")) return connect;',
    'if (said === "what is connected") return list;',
    'if ("connect" === said) return connect;',
    'if (/^connect /.test(said)) return connect;',
    'if (new RegExp("^connect").test(said)) return connect;',
    'if (said.match(WORDS)) return connect;',
    'if (said.length < 3) return NONE;',
    'const first = text.split(" ")[0];',
  ];
  for (const v of violations) {
    assert.ok(forbidden.some(([re]) => re.test(v)), `the leg cannot catch: ${v}`);
  }
});

await check("law 1: every literal in a comparison is one of the module's own enums", async () => {
  const allowed = new Set<string>([
    ...TEXT_COMMANDS,
    // CommandVerdict / ToolkitVerdict kinds
    "command", "none", "unclear", "no-verdict", "toolkit",
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
    for (const m of CODE.matchAll(re)) compared.add(m[1]!.slice(1, -1));
  }
  const strays = [...compared].filter((s) => !allowed.has(s));
  assert.deepEqual(strays, [], `it branches on strings it did not declare: ${strays}`);
  assert.ok(compared.size >= 5, "the scan found nothing, so it proves nothing");
  // The leg has to be able to see one.
  const planted = new Set<string>();
  for (const re of patterns) {
    for (const m of 'if (x === "some-vendor") y();'.matchAll(re)) {
      planted.add(m[1]!.slice(1, -1));
    }
  }
  assert.deepEqual([...planted].filter((s) => !allowed.has(s)), ["some-vendor"]);
});

await check("the register: nothing this module can put in a message is forbidden copy", async () => {
  // FORBIDDEN_TERMS is words.ts's list, imported rather than copied — two
  // copies of a register drift, and the day they drift one surface says a word
  // the other refuses. Whole-word, case-insensitive, so "capital" does not
  // trip "api".
  const literals = [
    ...CODE.matchAll(/"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`/g),
  ].map((m) => m[0]);
  assert.ok(literals.length >= 5, "the literal scan found nothing, so it proves nothing");
  const banned = FORBIDDEN_TERMS.map((t) => new RegExp(`(^|[^a-z0-9])${t}([^a-z0-9]|$)`, "i"));
  const offenders = literals.filter((lit) => banned.some((re) => re.test(lit)));
  assert.deepEqual(offenders, [], `text_commands.ts can say: ${offenders.join(" | ")}`);
  assert.ok(banned.some((re) => re.test("we will authorize the integration")),
    "the register leg cannot see a violation");

  // And over the only strings the module ACTUALLY produced above, because a
  // literal assembled from two halves would slip past a source scan and still
  // reach a person's phone.
  const spoken = ["that app", displayName(null as never, ""), displayName(QUIXOTIC, "x")];
  const said = spoken.filter((s) => banned.some((re) => re.test(s)));
  assert.deepEqual(said, [], `spoken: ${said.join(" | ")}`);
});

await check("the module imports nothing that can act", async () => {
  const specifiers = [...CODE.matchAll(/\bfrom\s+["']([^"']+)["']/g)].map((m) => m[1]!);
  assert.deepEqual(specifiers.sort(), [
    "../../../../spike/two-hands/src/connections/contract.ts",
    "./store.ts",
  ], `text_commands.ts imports: ${specifiers.join(", ")}`);
  // The contract edge is TYPES ONLY, so the deployed Worker carries no runtime
  // dependency on the spike tree — the same rule store.ts, provider.ts and
  // words.ts state in their own headers.
  assert.ok(
    /import\s+type\s*\{[^}]*\}\s*from\s*["']\.\.\/\.\.\/\.\.\/\.\.\/spike/.test(CODE),
    "the spike import is not type-only",
  );
  // And nothing here reaches the world. A decision module that fetches is an
  // action module with a misleading name.
  for (const forbidden of ["fetch(", ".prepare(", "env.DB", "await sql", "crypto."]) {
    assert.equal(CODE.includes(forbidden), false, `text_commands.ts does: ${forbidden}`);
  }
});

// ===========================================================================
// 13. THE MUTATION ANCHORS ARE REAL
// ===========================================================================

/** Every anchor the mutation list at the bottom names. A regex that silently
 *  matched nothing has produced several false "it is tested" readings in this
 *  repo this week, so each one is asserted to occur EXACTLY once. */
const ANCHORS = [
  'if (verdict.kind !== "command") return { kind: "not_for_us", because: verdict.kind };',
  'if (verdict.command === "list_connected") return { kind: "list_connections", owner: who };',
  "if (offered.length === 0) {",
  "if (found.slug === null) {",
  'if (kind !== "command") return { kind: "no-verdict" };',
  "for (const known of TEXT_COMMANDS) {",
  'if (row === null) return NOTHING_RESOLVED("off-catalog");',
  'if (kind !== "toolkit") return NOTHING_RESOLVED("no-verdict");',
  "return { slug: row.slug, meta: row, because: \"none\" };",
  'const who = ownerId(String(owner ?? ""));',
  'const said = typeof text === "string" ? text : String(text ?? "");',
  "if (value.length > MAX_APP_NAME_CHARS) return false;",
  "if (code < 0x20 || code === 0x7f) return false;",
  "for (const bad of ADDRESS_CHARS) {",
  "return isRenderableName(slug) ? slug : NAMELESS;",
  'if (typeof raw !== "string" || raw.trim() === "") return NOTHING_RESOLVED("no-verdict");',
];

await check("every mutation anchor occurs exactly once in the source", async () => {
  for (const anchor of ANCHORS) {
    const n = SRC.split(anchor).length - 1;
    assert.equal(n, 1, `anchor occurs ${n} times: ${anchor}`);
  }
});

// ---------------------------------------------------------------------------
// MUTATIONS RUN AGAINST THIS SUITE. Thirty-one of them, every one RED against
// the final source, each reverted afterwards. Twenty change a decision; eleven
// plant the Law-1 violation this module exists in order not to have, so the
// source legs in section 12 are shown to be able to go red rather than
// asserted to be.
//
// DECISIONS (anchor -> the check that caught it):
//   1  `if (verdict.kind !== "command") …` inverted so a non-command acts
//      -> "a message about none of the four is left alone"
//   2  the `list_connected` early return deleted
//      -> "'what's connected' answers with the catalog down and the app judge broken"
//   3  `if (menu.length === 0) {` -> `if (false) {`
//      -> "an unreadable catalog refuses the action by name and spends no model call"
//   4  `if (found.slug === null) {` -> `if (false) {`
//      -> "every action refuses on an app the judge could not pin down"
//   5  `if (kind !== "command") return { kind: "no-verdict" };` -> `if (false) …`
//      -> "no verdict on the first question falls through, and says which"
//   6  the `for (const known of TEXT_COMMANDS)` membership loop bypassed by a cast
//      -> "no verdict on the first question falls through, and says which"
//   7  `if (row === null) return NOTHING_RESOLVED("off-catalog");` -> the model's
//      slug accepted anyway
//      -> "an app from the other owner's catalog is not an app for this one"
//   8  `if (kind !== "toolkit") …` -> `if (false) …`
//      -> "every action refuses on an app the judge could not pin down"
//   9  `slug: row.slug` -> `slug: raw` (the model's string, not the catalog's)
//      -> "a padded slug identifies the app, and the padding does not travel"
//  10  `const who = ownerId(String(owner ?? ""));` -> `const who = owner;`
//      -> "a name, an email or an empty owner throws rather than planning"
//  11  the phrase truncated to 8 characters before the judge sees it
//      -> "the owner's words reach the judge byte for byte"
//  12  `if (value.length > MAX_APP_NAME_CHARS) return false;` -> `if (false) …`
//      -> "a catalog name that carries an address loses its name, not our sentence"
//  13  `if (code < 0x20 || code === 0x7f) return false;` -> `if (false) …`
//      -> same
//  14  the `for (const bad of ADDRESS_CHARS)` walk deleted
//      -> same
//  15  `return isRenderableName(slug) ? slug : NAMELESS;` -> `return slug;`
//      -> "a slug that is not renderable either leaves a generic name, not an address"
//  16  the `rows.filter` slug guard -> `rows as ToolkitMeta[]`
//      -> "one malformed row does not cost the rest of the catalog"
//  17  `catch { return []; }` in `ownersCatalog` -> rethrow
//      -> "an unreadable catalog refuses the action by name and spends no model call"
//  18  `if (typeof raw !== "string" || raw.trim() === "") …` -> `if (false) …`
//      -> "every action refuses on an app the judge could not pin down"
//  19  `Object.freeze` dropped from TEXT_COMMANDS
//      -> "a judge cannot widen the menu it was handed"
//  20  `judge.match(said, [...offered])` -> `judge.match(said, offered)`
//      -> "a judge cannot invent an app by appending to the list it was handed"
//
// PLANTED LAW-1 VIOLATIONS (each one line added to the module):
//  L1  `said.includes("connect")`            -> "the module never inspects the owner's words"
//  L2  `/^connect /.test(said)`              -> same
//  L3  `new RegExp("^x").test(said)`         -> same
//  L4  `said === "what is connected"`        -> same, and the enum-literal leg
//  L5  `said.length < 3`                     -> same
//  L6  `const KNOWN = ["notion", "slack"];`  -> "no app is named in the module's CODE"
//  L7  the vendor's name in a comment        -> "the vendor's name appears nowhere"
//  L8  `x === "some-vendor"`                 -> "every literal in a comparison is one of
//                                               the module's own enums"
//  L9  `"authorize the integration"`         -> "the register: nothing this module can put
//                                               in a message is forbidden copy"
//  L10 `fetch("https://x.example")`          -> "the module imports nothing that can act"
//  L11 a runtime import of the D1 store      -> same
// ---------------------------------------------------------------------------

console.log(`connections-text-commands: ${passes} checks passed, ${failures} failed`);
if (failures) process.exit(1);
