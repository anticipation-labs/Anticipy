// A recipe is the agent acting with its eyes half closed, so these tests are
// about the four things that make that acceptable — and one of them is a real
// disaster we get exactly one chance to prevent.
//
// The disaster: a compiled booking that remembered "6 guests, July 4th" replays
// last month's dinner at ten times the speed and with total confidence, and the
// owner finds out when he arrives. So the central assertion here is STRUCTURAL,
// not behavioural: the stored step for a typing action has no `text` key on it
// at all, and the serialized recipe does not contain the owner's words anywhere
// — not in an action, not in a URL's query string, not even echoed inside a
// checkpoint sentence, which is where the page map's own `[contains "…"]` would
// have smuggled it in.
//
// The other three: two clean runs before anything compiles (one success can be
// luck), a checkpoint on every step that says in plain English what stopped
// being true, and a commit that is never replayed.
import assert from "node:assert";
import {
  actionSignature, compile, recall, remember, nextStep, checkpointFailed,
  RECIPE_TTL_MS, CLEAN_RUNS_REQUIRED, MAX_RECIPES,
} from "../recipes.js";
import { taskShape } from "../learn.js";

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}${ok || !detail ? "" : `  -> ${detail}`}`);
  if (!ok) failures++;
};

// --- the fixture: one booking, run twice with different answers -------------

const bookingPage = (party = "", notes = "") => ({
  url: "https://www.opentable.com/r/joes",
  title: "Joe's — reservations",
  elements: [
    "[0] <link> Sign in @(900,20)",
    `[1] <combobox> Party size (use select action; options: "1", "2", "6"${party ? "*" : ""}) @(120,300)`,
    "[2] <textbox> Date [readonly — click to open its picker] @(220,300)",
    "[3] <button> Find a table @(320,300)",
    // The mapper echoes what a field CURRENTLY holds. That echo is the most
    // likely way the owner's own sentence ends up inside a stored checkpoint.
    `[4] <textbox> Special request${notes ? ` [contains "${notes}"]` : ""} @(420,300)`,
  ].join("\n"),
  fields: [
    { index: 1, name: "partySize", label: "Party size", type: "select-one", value: party },
    { index: 4, name: "notes", label: "Special request", type: "text", value: notes },
  ],
});

const resultsPage = () => ({
  url: "https://www.opentable.com/r/joes/times",
  title: "Available times",
  elements: [
    "[0] <link> Sign in @(900,20)",
    "[1] <button> 6:30 PM @(120,400)",
    "[2] <button> Book now @(300,500)",
  ].join("\n"),
  fields: [],
});

const run = ({ party, notes, date }) => [
  // The query string is where this month's date and party size live.
  { decision: { action: "navigate", url: `https://www.opentable.com/r/joes?date=${date}&party=${party}` } },
  { decision: { action: "select", index: 1, option: party }, state: bookingPage("", "") },
  { decision: { action: "type", index: 4, text: notes, enter: false }, state: bookingPage(party, "") },
  { decision: { action: "wait" } },
  { decision: { action: "click", index: 3 }, state: bookingPage(party, notes) },
  { decision: { action: "click", index: 2 }, state: resultsPage() },
  { decision: { action: "done", result: "Booked" } },
];

const GOAL = "book a table at Joe's for July 4";
const OTHER_WORDING = "book us a table at Joe's on August 30";
const runA = run({ party: "6", notes: "Rumpelstiltskin party, July 4", date: "2026-07-04" });
const runB = run({ party: "2", notes: "Anniversary dinner", date: "2026-08-30" });
const SECRETS = ["Rumpelstiltskin", "July", "Anniversary", "2026-07-04", "2026-08-30", "party=6", "?date"];

// --- 1. one clean run is a coincidence, not a recipe -----------------------

check("a shape that succeeded ONCE does not compile", compile(runA, GOAL) === null);
check("neither does a single run wrapped as a run list", compile([{ goal: GOAL, trace: runA }], GOAL) === null);

const recipe = compile([runA, runB], GOAL);
check("two clean runs of the same route compile", !!recipe);
check("and `runs` records how many", recipe?.runs === CLEAN_RUNS_REQUIRED, String(recipe?.runs));
check("the shape key is learn.js's, not a second copy",
  recipe?.shape === taskShape(GOAL) && taskShape(GOAL) === taskShape(OTHER_WORDING), recipe?.shape);

// A different route is a different task, however similar the words.
const detour = runB.slice();
detour.splice(1, 0, { decision: { action: "click", index: 0 }, state: bookingPage("", "") });
check("two runs that took different routes do not compile", compile([runA, detour], GOAL) === null);
check("a run containing an action the module cannot model refuses the whole run",
  compile([runA, [...runB.slice(0, 2), { decision: { action: "teleport" } }, ...runB.slice(2)]], GOAL) === null);
// runA has a `wait` in it and runB does not, yet they agree — a step with
// nothing to replay must not fork the route.
check("waiting and finishing are skipped rather than forking the route", !!recipe);

// --- 2. the commit is never replayed --------------------------------------

const commitStep = recipe.steps[recipe.steps.length - 1];
check("the recipe ends AT the commit and stores nothing past it",
  recipe.steps.length === 5 && commitStep.commits === true && /book now/.test(commitStep.checkpoint),
  `${recipe.steps.length} steps, last = ${commitStep?.checkpoint}`);
check("the commit's signature says so in the string itself",
  commitStep.sig.startsWith("commit:"), commitStep.sig);
check("the live page still matches the commit step's checkpoint",
  checkpointFailed(recipe, resultsPage(), 4) === null);
check("and nextStep refuses it anyway — the last click goes through the live gates",
  nextStep(recipe, resultsPage(), 4) === null);
check("a submit-by-Enter is a commit too",
  actionSignature({ action: "type", index: 2, label: "Search", enter: true }).startsWith("commit:"));
check("an action-shaped GET is a commit",
  actionSignature({ action: "navigate", url: "https://shop.example.com/cart/checkout" }).startsWith("commit:"));
check("but ordinary navigation is not",
  actionSignature({ action: "navigate", url: "https://shop.example.com/shoes" }) === "navigate|shop.example.com/shoes");
check("and neither is a reversible control that happens to read like one",
  !actionSignature({ action: "click", index: 3, label: "Find a table" }).startsWith("commit:")
  && !actionSignature({ action: "click", index: 3, label: "Apply filters" }).startsWith("commit:"));

// --- 3. a stale value can never be replayed. structurally. ----------------

const serialized = JSON.stringify(recipe);
for (const secret of SECRETS) {
  check(`no part of the recipe carries ${JSON.stringify(secret)}`, !serialized.includes(secret));
}
check("and the recipe's own name for itself is the shape, not his sentence",
  recipe.goal === "book joe table" && !/july|4/.test(recipe.goal), recipe.goal);
const typeStep = recipe.steps[2];
check("a typing step has NO text key at all — not empty, absent",
  !("text" in typeStep.action) && !("value" in typeStep.action), JSON.stringify(typeStep.action));
check("it stores which FIELD, and says it needs a value",
  typeStep.action.field === "special request" && typeStep.action.needsValue === true);
check("a dropdown step carries no option either",
  !("option" in recipe.steps[1].action) && recipe.steps[1].action.field === "party size",
  JSON.stringify(recipe.steps[1].action));
check("a navigate step keeps the route and drops the query",
  recipe.steps[0].action.url === "https://www.opentable.com/r/joes");
check("the page's echo of the typed value never reaches the checkpoint sentence",
  typeStep.checkpoint === 'on opentable.com/r/joes, the "special request" field at slot 4',
  typeStep.checkpoint);
check("a typed value cannot change a step's identity",
  actionSignature({ action: "type", index: 4, field: "Special request", text: "one thing" })
  === actionSignature({ action: "type", index: 4, field: "Special request", text: "something else" }));
check("nor can a query string",
  actionSignature({ action: "navigate", url: "https://x.example/a?date=2026-07-04" })
  === actionSignature({ action: "navigate", url: "https://x.example/a?date=2026-08-30" }));
check("a route that names a date does not compile at all",
  compile([runA, runB].map((r) => [{ decision: { action: "navigate", url: "https://x.example/book/2026-07-04" } }, ...r.slice(1)]), GOAL) === null);

// The value the caller fills in must not land on the stored recipe.
const handed = nextStep(recipe, bookingPage("", ""), 2);
handed.action.text = "this run's answer";
check("nextStep hands out a COPY, so filling it in cannot poison the recipe",
  !("text" in recipe.steps[2].action));
check("an unfilled slot still names its field for the live run",
  handed.action.field === "special request" && /special request/.test(handed.checkpoint));

// --- 4. checkpoints: what stopped being true, in words ---------------------

check("an unchanged page passes every checkpoint",
  recipe.steps.every((_, i) => checkpointFailed(recipe, i === 0 ? {} : i === 4 ? resultsPage() : bookingPage("6", ""), i) === null));

const shifted = {
  ...bookingPage("", ""),
  // A banner shifted every index below it. This is the silent mis-click.
  elements: bookingPage("", "").elements.replace("[3] <button> Find a table", "[3] <link> Gift cards"),
};
const shiftReason = checkpointFailed(recipe, shifted, 3);
check("a changed page fails its checkpoint",
  typeof shiftReason === "string" && shiftReason.length > 10, String(shiftReason));
check("and the reason reads like a sentence a person could act on",
  /slot 3/.test(shiftReason) && /find a table/.test(shiftReason)
  && !/undefined|null|\[object|NaN/.test(shiftReason), shiftReason);
check("a failed checkpoint means no step, ever", nextStep(recipe, shifted, 3) === null);

const elsewhere = { ...bookingPage("", ""), url: "https://www.opentable.com/r/other" };
const urlReason = checkpointFailed(recipe, elsewhere, 1);
check("the wrong page is caught before the click, and named",
  /opentable\.com\/r\/other/.test(String(urlReason)) && /opentable\.com\/r\/joes/.test(String(urlReason)),
  String(urlReason));

const noField = {
  ...bookingPage("", ""),
  elements: bookingPage("", "").elements.split("\n").slice(0, 4).join("\n"),
  fields: [{ index: 1, name: "partySize", label: "Party size", type: "select-one", value: "" }],
};
const fieldReason = checkpointFailed(recipe, noField, 2);
check("a form that lost a field says which field",
  /special request/.test(String(fieldReason)) && /slot 4/.test(String(fieldReason)), String(fieldReason));
check("no page at all is a failure, not a pass",
  typeof checkpointFailed(recipe, null, 1) === "string");
check("a site that renamed a control is caught even at the right slot",
  /slot 1/.test(String(checkpointFailed(recipe, {
    ...bookingPage("", ""),
    fields: [{ index: 1, name: "guests", label: "How many guests", type: "select-one", value: "" }],
  }, 1))));
check("a control that changed KIND is caught",
  /combobox|textbox|link/.test(String(checkpointFailed(recipe, {
    ...bookingPage("", ""),
    elements: bookingPage("", "").elements.replace("[3] <button> Find a table", "[3] <link> Find a table"),
  }, 3))));
check("a recipe that has only been seen once can never step, whatever its steps say",
  nextStep({ ...recipe, runs: 1 }, bookingPage("", ""), 1) === null);
check("walking off the end of a recipe is not a checkpoint failure",
  nextStep(recipe, resultsPage(), 99) === null && checkpointFailed(recipe, resultsPage(), 99) === null);

// --- 5. storage: the two-run gate, expiry, bounds, and failure ------------

const fakeStorage = (seed = {}) => {
  const data = { ...seed };
  return { data, get: async (key) => ({ [key]: data[key] }), set: async (patch) => { Object.assign(data, patch); } };
};

const shape = taskShape(GOAL);
const store = fakeStorage();
await remember(shape, { goal: GOAL, trace: runA }, store);
check("one clean run is remembered but is not recallable",
  (await recall(shape, store)) === null && !!store.data.recipes[shape].witness);
check("and the witness on disk holds no raw trace and no owner value",
  !JSON.stringify(store.data.recipes).match(/Rumpelstiltskin|decision/),
  JSON.stringify(store.data.recipes).slice(0, 200));

await remember(shape, { goal: GOAL, trace: runB }, store);
const stored = await recall(shape, store);
check("the second clean run compiles it", stored?.runs === 2 && stored?.steps?.length === 5);
check("a differently worded ask hits the same recipe", (await recall(taskShape(OTHER_WORDING), store)) === stored);
check("passing the raw goal instead of the shape key does not fork the cache",
  (await recall(GOAL, store))?.runs === 2);

await remember(shape, { goal: GOAL, trace: run({ party: "4", notes: "quiet corner", date: "2026-09-01" }) }, store);
check("a third clean run of the same route counts up", (await recall(shape, store))?.runs === 3);

const failed = fakeStorage();
await remember(shape, { goal: GOAL, trace: runA, ok: false }, failed);
check("a run that did not finish clean witnesses nothing", !failed.data.recipes?.[shape]);

// Self-healing: one divergent run does not throw a working recipe away, two do.
await remember(shape, { goal: GOAL, trace: detour }, store);
check("one odd run leaves the recipe alone — that is what checkpoints are for",
  (await recall(shape, store))?.steps?.length === 5);
await remember(shape, { goal: GOAL, trace: detour }, store);
const healed = await recall(shape, store);
check("two runs of a new route replace the old one, back at two",
  healed?.steps?.length === 6 && healed?.runs === 2, `${healed?.steps?.length} steps, runs ${healed?.runs}`);

const aged = fakeStorage();
await remember(shape, recipe, aged);
const at = aged.data.recipes[shape].compiledAt;
check("a fresh recipe is recallable", !!(await recall(shape, aged, at + 1000)));
check("an expired one is not", (await recall(shape, aged, at + RECIPE_TTL_MS + 1)) === null);

// Bounded, oldest evicted first.
const base = Date.now();
const many = {};
for (let i = 0; i < MAX_RECIPES; i++) {
  many[`shape-${i}`] = { ...recipe, shape: `shape-${i}`, compiledAt: base - i * 1000 };
}
many["long-dead"] = { ...recipe, shape: "long-dead", compiledAt: base - RECIPE_TTL_MS - 1 };
const full = fakeStorage({ recipes: many });
await remember("brand-new", recipe, full);
const kept = Object.keys(full.data.recipes);
check("the cache stays bounded", kept.length === MAX_RECIPES, String(kept.length));
check("the oldest is the one evicted",
  !kept.includes(`shape-${MAX_RECIPES - 1}`) && kept.includes("shape-0") && kept.includes("brand-new"));
check("and an expired entry is swept on the way past", !kept.includes("long-dead"));

const broken = {
  get: async () => { throw new Error("storage unavailable"); },
  set: async () => { throw new Error("quota exceeded"); },
};
check("a cache that cannot read returns nothing rather than throwing",
  (await recall(shape, broken)) === null);
await assert.doesNotReject(() => remember(shape, recipe, broken));
await assert.doesNotReject(() => remember(shape, { goal: GOAL, trace: runA }, { get: async () => ({}), set: async () => { throw new Error("quota"); } }));
check("a cache that cannot write does not break the run", true);
check("a missing storage is simply no cache",
  (await recall(shape, null)) === null);
await assert.doesNotReject(() => remember(shape, recipe, null));

// The read door enforces rule 3 a second time: a hand-edited or downgraded
// entry that carries a value must die rather than replay it fast.
const poisoned = fakeStorage({
  recipes: {
    [shape]: {
      ...recipe,
      compiledAt: Date.now(),
      steps: recipe.steps.map((s, i) => (i === 2
        ? { ...s, action: { ...s.action, text: "6 guests, July 4" } }
        : s)),
    },
  },
});
check("a stored step carrying a value is refused at recall", (await recall(shape, poisoned)) === null);
const withQuery = fakeStorage({
  recipes: {
    [shape]: {
      ...recipe,
      compiledAt: Date.now(),
      steps: recipe.steps.map((s, i) => (i === 0
        ? { ...s, action: { ...s.action, url: "https://www.opentable.com/r/joes?date=2026-07-04" } }
        : s)),
    },
  },
});
check("so is a stored route that grew a query string", (await recall(shape, withQuery)) === null);
check("and remember refuses to write one",
  await (async () => {
    const s = fakeStorage();
    await remember(shape, poisoned.data.recipes[shape], s);
    return !s.data.recipes;
  })());

// --- 6. signatures ---------------------------------------------------------

check("an action with nothing to replay has no signature",
  actionSignature({ action: "done" }) === "" && actionSignature({ action: "needs_user" }) === ""
  && actionSignature(null) === "" && actionSignature({}) === "");
check("the model's synonyms are one verb",
  actionSignature({ action: "goto", url: "https://x.example/a" })
  === actionSignature({ action: "open", url: "https://x.example/a" }));
check("two scrolls in the same direction are one step",
  actionSignature({ action: "scroll", dy: 600 }) === actionSignature({ action: "scroll", dy: 900 })
  && actionSignature({ action: "scroll", dy: -600 }) !== actionSignature({ action: "scroll", dy: 600 }));
check("a different control at the same slot is a different step",
  actionSignature({ action: "click", index: 3, label: "Find a table" })
  !== actionSignature({ action: "click", index: 3, label: "Gift cards" }));

// --- 7. the whole thing, driven the way the loop will drive it ------------
//
// Every assertion above tests one property. This one is the actual errand: two
// clean runs recorded, a third ask arriving with DIFFERENT answers, and the
// replay walking the site until it reaches the commit and hands over. It is
// here because the properties can all hold while the pieces refuse to compose.

const live = fakeStorage();
await remember(shape, { goal: GOAL, trace: runA }, live);
await remember(shape, { goal: GOAL, trace: runB }, live);
const script = await recall(taskShape(OTHER_WORDING), live);

// What the owner asked for THIS time. Nothing below may come from anywhere else.
const thisTime = { "party size": "4", "special request": "window seat if you have one" };
// The replay starts in a fresh tab that has never seen this site.
const blankTab = { url: "about:blank", title: "", elements: "", fields: [] };
const pages = [blankTab, bookingPage("", ""), bookingPage("4", ""), bookingPage("4", "window seat if you have one"), resultsPage()];
const dispatched = [];
let cursor = 0;
let handedOver = null;
while (cursor < script.steps.length) {
  const page = pages[cursor];
  const step = nextStep(script, page, cursor);
  if (!step) {
    handedOver = checkpointFailed(script, page, cursor) || `commit: ${script.steps[cursor].checkpoint}`;
    break;
  }
  // The live run fills the slots. The recipe told it WHICH; it knows WHAT.
  if (step.action.needsValue) step.action.text = thisTime[step.action.field];
  dispatched.push(step.action);
  cursor++;
}
check("the replay walks the site with no model in the loop",
  dispatched.length === 4 && dispatched.map((a) => a.action).join(",") === "navigate,select,type,click",
  dispatched.map((a) => a.action).join(","));
check("and every value it typed is THIS run's answer",
  dispatched[1].text === "4" && dispatched[2].text === "window seat if you have one");
check("it stops at the commit and says so, rather than booking",
  /^commit: /.test(String(handedOver)) && /book now/.test(String(handedOver)), String(handedOver));
check("the recipe on disk is untouched by the run that used it",
  !JSON.stringify((await recall(shape, live)).steps).match(/window seat|"4"/));

if (failures) { console.error(`test_recipes: ${failures} failed`); process.exit(1); }
console.log("test_recipes: all passed");
