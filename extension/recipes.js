// DO IT AGAIN WITHOUT THINKING ABOUT IT.
//
// The first time a task shape runs, the whole agent reasons through it: a model
// call per step, a page map per step, forty seconds of somebody's evening. The
// second time it does the identical thing for the identical money. That is the
// margin and, month three, it is also the product — an errand that costs three
// cents and takes fifteen seconds is a different thing from one that costs
// thirty and takes four minutes.
//
// So a shape that has run cleanly twice compiles into a script: the same clicks,
// in the same order, with no model in the loop. MVP spec section 04.
//
// FOUR RULES, AND EVERY ONE OF THEM EXISTS BECAUSE THE CHEAP PATH IS THE
// DANGEROUS PATH. A replay is an agent acting with its eyes half closed; what
// makes that acceptable is only what follows.
//
// 1. TWO CLEAN RUNS, NEVER ONE. One success can be luck: a site that happened
//    to be logged in, a cookie banner that happened not to appear, a page that
//    happened to load in the order the model guessed. Compiling from a single
//    run mints a script out of a coincidence. So `compile` returns null until it
//    has seen the same action sequence succeed twice, and `runs` says how many.
//
// 2. EVERY STEP CARRIES A CHECKPOINT. A recipe replays a remembered click
//    against a page that changed under it overnight. Each step therefore states
//    what must be TRUE before it may fire — this URL, this labelled control at
//    this slot, this field still in this form — and `checkpointFailed` says in
//    plain English what stopped being true. On any failure the caller abandons
//    the replay entirely and reasons live. Abandoning is cheap; a half-replayed
//    form is not, so there is no partial mode and never will be.
//
// 3. A RECIPE MAY NEVER CARRY A VALUE THE OWNER DID NOT GIVE THIS TIME. This is
//    the one that would have shipped a real disaster. A compiled booking that
//    remembered "4 guests, July 3rd, 7:30pm" replays last month's dinner at full
//    speed and with total confidence, and the owner finds out when he arrives.
//    So a typing step stores WHICH FIELD and nothing else: there is no `text`
//    key on it to put a stale value in. Same for a dropdown's option, and same
//    for a URL's query string, which is where sites keep dates and party sizes.
//    The live run supplies values from its own approved scope, as it always did.
//    Structurally impossible beats carefully avoided — see `stepFrom`, which
//    builds each action key by key and never spreads a recorded decision.
//
// 4. THE COMMIT IS NEVER REPLAYED. Submitting, paying, booking, sending: replay
//    gets the agent to the ready-to-commit state for almost nothing, and then
//    stops. The last click goes back through the live gates — approval, the
//    exact-fact audit, at-most-once — because those gates are the reason this
//    product is allowed near a checkout. A recipe that could submit would be a
//    way to route around all of them at 10x speed.
//
// Bounded and expiring, like the researched procedures in learn.js: a site
// redesign must age a recipe out on its own, and a cache that cannot write must
// never break a run.

// The shape key comes from learn.js on purpose. A recipe and a researched
// procedure MUST key the same way — same task, same normalisation — and a second
// copy of that function would drift within a month of somebody fixing one of
// them. Everything about which words identify a shape lives there.
import { taskShape } from "./learn.js";

// Two weeks, where a procedure gets a month. A procedure is knowledge ("the
// claim goes through the warranty portal, you need the serial") and ages slowly.
// A recipe is a script bolted to one vendor's current DOM, and vendors ship
// redesigns. Long enough to compound across a fortnight of daily errands, short
// enough that a dead route cannot become folklore.
export const RECIPE_TTL_MS = 14 * 24 * 60 * 60 * 1000;
export const CLEAN_RUNS_REQUIRED = 2;
// A run longer than this was flailing, not working. Compiling a flail bakes the
// flail in and replays it at speed.
export const MAX_RECIPE_STEPS = 30;
export const MAX_RECIPES = 40;

// Deliberately a copy of the commit/reversible vocabulary in agent_loop.js's
// commitControl(), NOT an import: this module is pure by contract (no chrome, no
// DOM, no network) and importing the loop would drag the whole extension in.
// The duplication is safe in one direction only — over-calling something a
// commit costs a slower live step, under-calling it hands a submit button to a
// replay. When these lists disagree, this one must be the stricter.
const COMMIT_VERB = /\b(submit|send|confirm|place\s+order|buy|purchase|book|schedule|request|apply|pay|delete|remove|save|renew|register|file|complete|finish|finalize|create|open\s+(?:a\s+)?claim)\b|^\s*cancel\s+\w+/i;
const REVERSIBLE_LABEL = /^\s*(?:(?:search|find|filter|look\s*up|next|continue|back|previous)(?:\b|\s)|(?:cancel|close|dismiss)\s*$|(?:see|show|view)\s+[0-9][0-9,.\s]*\s+results?\b|(?:apply|update)\s+(?:filters?|search|results?)\b)/i;
// An action-shaped GET: the URL itself names the mutation, so following it is
// the commit. Same test the loop applies to anchors.
const MUTATING_ROUTE = /(?:^|[/?#&=_-])(?:delete|remove|unsubscribe|logout|purchase|checkout|confirm|pay)(?:$|[/?#&=_-])/i;
// A date in a path is this month's instance, not the shape — rule 3 applies to
// routes as much as to fields, and there is nothing to strip, so the run simply
// does not compile.
const DATED_ROUTE = /\d{4}-\d{2}-\d{2}|\/\d{8}(?:\/|$)/;

// Verbs the loop actually dispatches, folded onto their canonical form. The
// model says "goto", "fill" and "choose" for the same three tools.
const VERBS = new Map(Object.entries({
  navigate: "navigate", goto: "navigate", open: "navigate",
  click: "click", press: "click",
  type: "type", fill: "type", set: "type",
  select: "select", choose: "select",
  enter: "enter", submit: "enter",
  scroll: "scroll",
}));
// Steps with nothing to replay. `wait` is a stall the fast path does not need,
// and `done`/`needs_user` are how a run ENDS — replaying either is meaningless.
// Anything not in this set and not in VERBS refuses the whole run: an action
// this module cannot model is an action it must not silently drop.
const SKIPPABLE = new Set(["wait", "done", "needs_user", "verify", ""]);

/**
 * The stable identity of one step: the verb and what it points at, never what
 * was written into it. Two runs of the same shape produce the same string here
 * or they are not the same route and nothing compiles.
 *
 * A signature that marks a commit says so in the string itself (`commit:`), so
 * the hard stop in nextStep cannot be reached by a code path that forgot to ask
 * a separate predicate.
 */
export function actionSignature(decision) {
  const d = decision || {};
  const verb = VERBS.get(String(d.action || "").toLowerCase());
  if (!verb) return "";
  // The label may arrive on the decision (the model sometimes names its target)
  // or be resolved from the page map at compile time. Either way it is page
  // text, not owner input.
  const label = cleanLabel(d.label || d.field || d.name || "");
  let target;
  if (verb === "navigate") {
    // The ROUTE, never the query: `?date=2026-07-04&party=6` is last month's
    // dinner, and letting it into an identity means the identity changes every
    // time the owner asks for something slightly different anyway.
    target = urlKey(d.url);
  } else if (verb === "scroll") {
    target = Number(d.dy) < 0 ? "up" : "down";
  } else {
    const index = Number(d.index);
    target = `${Number.isFinite(index) ? index : "?"}${label ? `:${label}` : ""}`;
  }
  return `${isCommit(verb, label, d) ? "commit:" : ""}${verb}|${target}`;
}

/**
 * Compile the recorded runs of one shape into a replayable script, or null.
 *
 * `trace` is either one run's entries or a list of runs; a run's entry is
 * `{ decision, state }` — the action the loop dispatched and the page map it was
 * decided against. The state is not optional decoration: it is where every
 * checkpoint comes from, so a run recorded without it cannot compile.
 *
 * Null is the normal, expected answer. One clean run gives null. Two runs that
 * took different routes give null. A run containing an action this module cannot
 * model gives null. In every one of those cases the agent simply thinks, which
 * is what it did last week.
 */
export function compile(trace, goal) {
  return compileSteps(normalizeRuns(trace).map(runToSteps).filter(Boolean), goal);
}

/**
 * The compiled recipe for a shape, if there is a live one. Keyed by task shape
 * so "book the usual table for Friday" and "book us a table Tuesday" are one
 * recipe, which is the entire point of the shape key.
 */
export async function recall(shape, storage, now = Date.now()) {
  if (!shape || !storage) return null;
  let all;
  try { all = (await storage.get("recipes"))?.recipes || {}; } catch (_) { return null; }
  const hit = all[keyOf(shape)];
  if (!hit || !Array.isArray(hit.steps) || hit.steps.length < 2) return null;
  // A witness that has only been seen once is stored under the same key. It is
  // not a recipe and must never be handed to a replay.
  if (Number(hit.runs) < CLEAN_RUNS_REQUIRED) return null;
  if (!hit.compiledAt || now - hit.compiledAt > RECIPE_TTL_MS) return null;
  // Rule 3, enforced again at the READ door. Storage is a file on a laptop; a
  // hand-edited, half-written or downgraded entry that carries a value must die
  // here rather than replay it. Cheap check, total consequence.
  if (hit.steps.some(unfitToReplay)) return null;
  return hit;
}

/**
 * Record a clean run, or store an already-compiled recipe.
 *
 * Given a run, this is the two-clean-runs gate: the first one is kept as a
 * WITNESS and nothing is replayable; a second run with the same signature
 * sequence compiles. A clean run matching the stored recipe bumps `runs` and
 * refreshes the clock — it just worked, so it has earned another fortnight. A
 * run that diverges becomes the new witness WITHOUT throwing the recipe away:
 * one odd run (a cookie banner, an interstitial) is what checkpoints are for,
 * and two odd runs are a redesign, at which point the new route wins. That is
 * the self-healing loop the spec asks for.
 *
 * Witnesses are stored as COMPILED STEPS, never as raw traces. A raw trace holds
 * the owner's typed values and page text; keeping one on disk to compare against
 * later would put back exactly what rule 3 takes out.
 */
export async function remember(shape, recipe, storage) {
  if (!shape || !recipe || !storage) return;
  const key = keyOf(shape);
  const now = Date.now();
  try {
    const all = (await storage.get("recipes"))?.recipes || {};
    const record = all[key] && typeof all[key] === "object" ? all[key] : null;
    const next = mergeRecord(record, recipe, key, now);
    if (!next) return;
    all[key] = next;
    prune(all, now);
    await storage.set({ recipes: all });
  } catch (_) { /* a cache that cannot write must not break a run */ }
}

/**
 * The next action to replay, or null.
 *
 * Null has three meanings and the caller can tell them apart without a second
 * return channel: `cursor >= recipe.steps.length` is a finished recipe;
 * `checkpointFailed()` non-null is a changed site (wake up, finish live,
 * re-record); otherwise `recipe.steps[cursor].commits` is true and the commit is
 * deliberately not replayable — hand it to the live gates.
 *
 * The action is returned as a COPY. The caller fills a typing step's value in
 * from this run's approved scope, and if that write landed on the stored object
 * the recipe would quietly acquire the value it exists to not have.
 */
export function nextStep(recipe, state, cursor) {
  if (!recipe || !Array.isArray(recipe.steps)) return null;
  if (Number(recipe.runs) < CLEAN_RUNS_REQUIRED) return null;
  const step = recipe.steps[Number(cursor)];
  if (!step || !step.action || !step.checkpoint) return null;
  if (step.commits || unfitToReplay(step)) return null;
  if (checkpointFailed(recipe, state, cursor)) return null;
  return { action: { ...step.action }, checkpoint: step.checkpoint };
}

/**
 * Why this step may not fire against this page, in words a person could read in
 * the feed — or null when the page still matches what was recorded.
 */
export function checkpointFailed(recipe, state, cursor) {
  const step = recipe?.steps?.[Number(cursor)];
  if (!step) return null;
  const expect = step.expect || {};
  // A step with nothing to check needs no page: the first step of a recipe is
  // usually a navigate, and a replay legitimately starts in a fresh tab that
  // has never been mapped. Demanding a snapshot here would have made every
  // recipe unreplayable at step one.
  if (!expect.url && !Number.isFinite(Number(expect.index))) return null;
  if (!state || typeof state !== "object") return "there is no page to check this step against";

  if (expect.url) {
    const live = urlKey(state.url);
    if (!live) return `the browser is not on a page this recipe knows (expected ${expect.url})`;
    if (live !== expect.url) return `the page is now ${live}, but this step was recorded on ${expect.url}`;
  }
  if (!Number.isFinite(Number(expect.index))) return null;

  const index = Number(expect.index);
  // The index is only meaningful against the map that produced it, so the
  // checkpoint is not "is there something at slot 12" but "is slot 12 still the
  // control I recorded". A page that inserted one banner shifts every index
  // below it, and that is precisely the silent mis-click this catches.
  const live = elementAt(state.elements, index);
  if (expect.field) {
    const field = fieldAt(state, index);
    const name = cleanLabel(field?.label || field?.name || live?.label || "");
    if (!name) return `the ${quoted(expect.field)} field is no longer at slot ${index} on ${expect.url || "this page"}`;
    if (!sameLabel(name, expect.field)) {
      return `slot ${index} is now the ${quoted(name)} field, not ${quoted(expect.field)}`;
    }
    return null;
  }
  if (!live) return `nothing is at slot ${index} on ${expect.url || "this page"} any more`;
  if (!sameLabel(live.label, expect.label)) {
    return `slot ${index} is now ${quoted(live.label) || "unlabelled"}, not the ${expect.role || "control"} labelled ${quoted(expect.label)}`;
  }
  if (expect.role && live.role && live.role !== expect.role) {
    return `${quoted(expect.label)} is now a ${live.role}, not a ${expect.role}`;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Compiling
// ---------------------------------------------------------------------------

// Shared by compile() and remember() so the two-clean-runs gate exists exactly
// once. Two call sites with their own copy of "is this good enough to replay"
// is how one of them ends up laxer than the other.
function compileSteps(runs, goal, now = Date.now()) {
  const clean = (runs || []).filter((r) => Array.isArray(r) && r.length >= 2);
  if (clean.length < CLEAN_RUNS_REQUIRED) return null;
  const latest = clean[clean.length - 1];
  const sig = sigsOf(latest);
  // Count only the CONSECUTIVE trailing runs that agree. Runs 1 and 3 matching
  // around a different run 2 is not two clean runs of one route; it is a flaky
  // page, which is the last thing to compile a script out of.
  let agreed = 0;
  for (let i = clean.length - 1; i >= 0 && sigsOf(clean[i]) === sig; i--) agreed++;
  if (agreed < CLEAN_RUNS_REQUIRED) return null;
  return {
    shape: taskShape(goal),
    // The same thing said in words, for the feed ("replaying: book joes table").
    //
    // NOT the owner's sentence. "book a table at Joe's for July 4" written here
    // would leave last month's dinner sitting in storage, in every backup, and
    // in the feed line of a run he actually asked for August — which is rule 3
    // wearing a different hat. The live run has the real ask; a recipe needs
    // only to be able to say which recipe it is. So: the shape's own tokens,
    // which by construction contain no date, amount, quantity or name-of-one.
    goal: taskShape(goal).replace(/-/g, " "),
    steps: latest,
    runs: agreed,
    compiledAt: now,
    sources: [...new Set(latest.map((s) => s.expect?.url || urlKey(s.action?.url)).filter(Boolean)
      .map((k) => k.split("/")[0]))].slice(0, 6),
  };
}

// One run of trace entries into replayable steps, or null if this run cannot be
// replayed at all. Refusing the whole run is the point: a run with one step
// missing is a run that does something else.
function runToSteps(entries) {
  if (!Array.isArray(entries) || !entries.length) return null;
  const steps = [];
  for (const raw of entries) {
    const entry = normalizeEntry(raw);
    if (!entry) return null;
    const verb = VERBS.get(String(entry.decision.action || "").toLowerCase());
    if (!verb) {
      if (SKIPPABLE.has(String(entry.decision.action || "").toLowerCase())) continue;
      return null;
    }
    const step = stepFrom(verb, entry);
    if (!step) return null;
    steps.push(step);
    // The recipe ENDS at the commit. Everything after it in the recorded run
    // happened on the far side of a submit the replay will never perform, so
    // storing it invites a caller to walk past the stop.
    if (step.commits) break;
    if (steps.length > MAX_RECIPE_STEPS) return null;
  }
  return steps.length >= 2 ? steps : null;
}

function normalizeEntry(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  if (raw.decision && typeof raw.decision === "object") {
    return { decision: raw.decision, state: raw.state || raw.page || null };
  }
  if (typeof raw.action === "string") return { decision: raw, state: raw.state || null };
  return null;
}

// RULE 3 LIVES HERE. Every action below is assembled key by key. There is no
// `{ ...decision }` in this function and there must never be one: a spread is
// how `text`, `value` and `option` would arrive without anybody deciding to
// bring them, and the resulting recipe would replay the owner's last answer
// forever. If you need another key, add it by name and say why.
function stepFrom(verb, { decision, state }) {
  const page = urlKey(state?.url);

  if (verb === "navigate") {
    const target = navTarget(decision.url);
    if (!target || DATED_ROUTE.test(target)) return null;
    const key = urlKey(target);
    return finish({
      // No expectation about where the replay currently is: a navigate is safe
      // from any page, and demanding the recorded starting page would fail every
      // replay that began in a fresh tab for no safety gained.
      action: { action: "navigate", url: target },
      expect: {},
      checkpoint: `opening ${key || "a page"}`,
      label: "",
    });
  }

  if (verb === "scroll") {
    if (!page) return null;
    const dy = Number(decision.dy);
    return finish({
      action: { action: "scroll", dy: Number.isFinite(dy) ? Math.max(-2000, Math.min(2000, Math.round(dy))) : 600 },
      expect: { url: page },
      checkpoint: `still on ${page}`,
      label: "",
    });
  }

  const index = Number(decision.index);
  if (!Number.isFinite(index) || index < 0 || !page) return null;

  if (verb === "type" || verb === "select") {
    const field = fieldAt(state, index);
    const name = cleanLabel(field?.label || field?.name || elementAt(state?.elements, index)?.label || "");
    if (!name) return null;
    return finish({
      // needsValue, and NO value. The caller must supply this run's own answer
      // from this run's approved scope; a step it cannot fill is a step it
      // reasons through live, which is correct and merely slower.
      action: verb === "type"
        // Explicitly false, never omitted: an Enter that submits is a commit
        // (below), so a replayable typing step is by construction one that does
        // not press it, and the loop's Enter gate reads this key literally.
        ? { action: "type", index, field: name, needsValue: true, enter: decision.enter === true }
        : { action: "select", index, field: name, needsValue: true },
      expect: { url: page, index, field: name, fieldType: field?.type || "" },
      checkpoint: `on ${page}, the ${quoted(name)} field at slot ${index}`,
      label: name,
    });
  }

  // click / enter: the identity is the control's own label, read off the map
  // that the decision's index refers to.
  const element = elementAt(state?.elements, index);
  if (!element || !element.label) return null;
  return finish({
    action: verb === "enter" ? { action: "enter", index } : { action: "click", index },
    expect: { url: page, index, role: element.role, label: element.label },
    checkpoint: `on ${page}, the ${element.role || "control"} labelled ${quoted(element.label)} at slot ${index}`,
    label: element.label,
  });
}

// The signature is computed from the STORED action plus the resolved label, so
// `sig` and `commits` can never disagree with the step they describe, and so a
// signature can be recomputed from a stored recipe later without the trace.
function finish(step) {
  const sig = actionSignature({ ...step.action, label: step.label });
  return { sig, commits: sig.startsWith("commit:"), action: step.action, checkpoint: step.checkpoint, expect: step.expect };
}

function isCommit(verb, label, decision) {
  if (verb === "enter") return true;
  // Typing that presses Enter IS a submit — the loop treats it as one, and a
  // replay that "only types" into a search-shaped booking form would commit it.
  if (verb === "type") return decision.enter === true;
  if (verb === "navigate") return MUTATING_ROUTE.test(String(decision.url || ""));
  if (verb !== "click") return false;
  if (!label) return false;
  if (REVERSIBLE_LABEL.test(label)) return false;
  return COMMIT_VERB.test(label);
}

// ---------------------------------------------------------------------------
// Storage
// ---------------------------------------------------------------------------

function mergeRecord(record, payload, key, now) {
  if (isCompiled(payload)) {
    if (payload.steps.some(unfitToReplay)) return null;
    const same = record?.steps && sigsOf(record.steps) === sigsOf(payload.steps);
    return {
      ...payload,
      shape: key,
      compiledAt: now,
      runs: same ? Number(record.runs || 0) + 1 : Math.max(CLEAN_RUNS_REQUIRED, Number(payload.runs) || 0),
      witness: null,
    };
  }

  const entries = Array.isArray(payload) ? payload
    : Array.isArray(payload.trace) ? payload.trace
      : Array.isArray(payload.entries) ? payload.entries
        : Array.isArray(payload.steps) ? payload.steps : null;
  // Only a run that actually finished clean may witness anything. A failed run's
  // route is the route that did not work.
  if (!entries || payload.ok === false || payload.clean === false) return null;
  const steps = runToSteps(entries);
  if (!steps) return null;
  const sig = sigsOf(steps);
  const goal = payload.goal || record?.goal || key;

  if (record?.steps && sigsOf(record.steps) === sig) {
    // It ran again and it worked. Another fortnight, and one more on the count.
    return { ...record, runs: Number(record.runs || 0) + 1, compiledAt: now, witness: null };
  }
  if (record?.witness?.sig === sig) {
    const compiled = compileSteps([record.witness.steps, steps], goal, now);
    if (!compiled) return null;
    return { ...compiled, shape: key, witness: null };
  }
  return {
    // Value-free here too: a witness lives on disk for a fortnight waiting for
    // its second run, and it may hold no more of the owner's wording than the
    // compiled recipe may.
    ...(record || { shape: key, goal: taskShape(goal).replace(/-/g, " ") }),
    witness: { sig, steps, at: now },
  };
}

function prune(all, now) {
  for (const key of Object.keys(all)) {
    const stamp = stampOf(all[key]);
    if (!stamp || now - stamp > RECIPE_TTL_MS) delete all[key];
  }
  const keys = Object.keys(all);
  if (keys.length <= MAX_RECIPES) return;
  // Oldest first. chrome.storage.local is not infinite, and the recipe nobody
  // has run in a fortnight is the one whose site has most likely moved anyway.
  keys.sort((a, b) => stampOf(all[a]) - stampOf(all[b]));
  for (const key of keys.slice(0, keys.length - MAX_RECIPES)) delete all[key];
}

function stampOf(record) {
  return Number(record?.compiledAt || record?.witness?.at || 0);
}

function isCompiled(payload) {
  return !!payload && !Array.isArray(payload) && Array.isArray(payload.steps)
    && payload.steps.length >= 2
    && payload.steps.every((s) => s && typeof s.sig === "string" && s.action && s.checkpoint);
}

// The read-side half of rule 3, and the reason a poisoned or downgraded cache
// entry cannot become a fast wrong booking.
function unfitToReplay(step) {
  const action = step?.action;
  if (!action || typeof action !== "object") return true;
  if ("text" in action || "value" in action || "option" in action || "code" in action) return true;
  // A query string is where dates, party sizes and search terms live. A stored
  // route that has one was not built by this module.
  return action.action === "navigate" && /[?#]/.test(String(action.url || ""));
}

function sigsOf(steps) {
  return (steps || []).map((s) => s?.sig || "").join(">");
}

// A shape key never contains whitespace, so a caller who passed a raw goal by
// mistake gets normalised here rather than silently forking the cache. Running
// taskShape over an already-shaped key would re-split and re-sort it into a
// DIFFERENT key, so the test is on the way in, once.
function keyOf(shape) {
  const s = String(shape || "").trim();
  return /\s/.test(s) ? taskShape(s) : s.slice(0, 120);
}

// ---------------------------------------------------------------------------
// Reading a page map
// ---------------------------------------------------------------------------

// `[12] <button> Book now [disabled] (…) @(300,400)` — page_map.js's line format.
function elementAt(elements, index) {
  if (typeof elements !== "string" || !elements) return null;
  const line = new RegExp(`^\\[${Number(index)}\\]\\s+<([^>]*)>\\s*([^\\n]*)$`, "m").exec(elements);
  if (!line) return null;
  return { role: line[1].trim().toLowerCase().slice(0, 24), label: cleanLabel(line[2]) };
}

function fieldAt(state, index) {
  const fields = state?.fields;
  if (!Array.isArray(fields)) return null;
  return fields.find((f) => Number(f?.index) === Number(index)) || null;
}

// Everything the mapper appends after a label is page STATE, not identity: the
// coordinates, the options list, `[disabled]`, and `[contains "…"]` — which is
// the field's CURRENT VALUE and would smuggle the owner's own typed answer into
// a stored checkpoint string. Cut at the first of them. A label with a real
// bracket in it ("Book now (2 guests)") loses its tail, which costs nothing:
// this is an identity, and the part that was cut was an instance value anyway.
function cleanLabel(raw) {
  const s = String(raw || "");
  let cut = s.length;
  for (const token of [" @(", " [", " ("]) {
    const at = s.indexOf(token);
    if (at >= 0 && at < cut) cut = at;
  }
  return s.slice(0, cut).replace(/\s+/g, " ").trim().toLowerCase().slice(0, 80);
}

// Sites append counts and badges to their own buttons ("Book now", "Book now
// (2)", "Cart 3"). A prefix match in either direction tolerates that without
// tolerating a different control; anything under three characters is too little
// to identify anything and fails closed.
function sameLabel(live, expected) {
  const a = cleanLabel(live);
  const b = cleanLabel(expected);
  if (!a || !b) return false;
  if (a === b) return true;
  if (a.length < 3 || b.length < 3) return false;
  return a.startsWith(b) || b.startsWith(a);
}

function quoted(text) {
  const s = String(text || "").trim();
  return s ? `"${s.slice(0, 80)}"` : "";
}

// host + path, lowercased, no query and no fragment: the identity of a PAGE,
// which is what a checkpoint is about. The query is this run's values.
function urlKey(url) {
  try {
    const u = new URL(String(url));
    if (u.protocol !== "https:" && u.protocol !== "http:") return "";
    return `${u.hostname.replace(/^www\./, "")}${u.pathname.replace(/\/+$/, "")}`.toLowerCase();
  } catch (_) { return ""; }
}

// What a navigate step is allowed to store. The query string is DROPPED, not
// preserved: rule 3. If the site genuinely needed those parameters, the next
// step's checkpoint fails and the agent finishes the job live — slower, correct,
// and self-healing — instead of quietly re-requesting last month's date.
function navTarget(url) {
  try {
    const u = new URL(String(url));
    if (u.protocol !== "https:" && u.protocol !== "http:") return "";
    return `${u.origin}${u.pathname}`;
  } catch (_) { return ""; }
}

function normalizeRuns(trace) {
  if (!Array.isArray(trace) || !trace.length) return [];
  const asRun = (item) => {
    if (Array.isArray(item)) return item;
    if (item && typeof item === "object") {
      if (Array.isArray(item.trace)) return item.trace;
      if (Array.isArray(item.entries)) return item.entries;
      // `{ steps: [...] }` only reads as a run when its members are trace
      // entries; a compiled recipe's steps are not runs.
      if (Array.isArray(item.steps) && item.steps.some((s) => s?.decision)) return item.steps;
    }
    return null;
  };
  const runs = trace.map(asRun);
  // Either this is a list of runs, or it is the entries of one run. Mixed input
  // is treated as one run, which then fails to compile — the safe direction.
  return runs.every(Boolean) ? runs : [trace];
}
