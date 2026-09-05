// SEVENTEEN WORDS DECIDED WHETHER HIS NAME WAS COMPLETE.
//
// F10. `completeNamedValue` asks whether a value stops short of a capitalised
// run in the owner's own sentence — "Coast Dental" inside "West Coast Dental" —
// and it settled that with a hard-coded set:
//
//     const boundaries = new Set(["anticipy","at","book","cancel","contact",
//       "for","from","give","in","open","register","request","schedule",
//       "send","to","use","with"]);
//
// A capitalised word in front of the value counted as a MISSING NAME PART
// unless it was one of those seventeen. The brain writes authority text as
// `Task: {goal}. They said: "..."`, so the word in front of the first name in
// the sentence is the goal's own leading verb, capitalised because it starts
// the sentence. Email, Text, Call, Ask, Renew, Order — none of them on the
// list — all read as a missing name part.
//
// MEASURED on the shipped guards (kind NAME, field "Recipient", no matching
// fact): "Task: Email Coast Dental and ask for a Friday slot." holding "Coast
// Dental" came back a DECIDED refusal — not floor-only — so the run logged
// PRE-SUBMIT BLOCK, incremented stuckStreak and told the step model to replace
// or clear a value that was right; an optional field was WIPED first.
//
// HARNESS-LAWS law 1: a word list deciding what a sentence means. The fix is
// the shape this repo already built four times: the ORTHOGRAPHY stays here (is
// there a capitalised word in front of it?) and the MEANING goes to a model —
// one question on its own, four states, the caller comparing. The question
// carries his sentence and one word out of it: no field value, no page text,
// no profile, because this ambiguity lives entirely in his words.
//
// Polarity is a FLOOR — "does anything say this value is the whole thing he
// named?" — so no verdict means flagged floor-only: never cleared, never
// retyped, the owner asked.
//
// Run: node extension/tests/test_name_completeness_is_not_a_word_list.mjs
import { readFileSync } from "node:fs";
import { installChrome } from "./chrome_mock.mjs";

const harness = installChrome();
const FAKE_JPEG = Buffer.from("x".repeat(9000)).toString("base64");
const {
  NAME_PART_SYSTEM, namePartMessages, namePartJudge, fieldKindsNeeded,
  unsupportedScopeFields, unsupportedScopeFieldsDetailed, unsupportedScopeVerdict,
  decidedUnsupportedNames, clearableUnsupportedFields, runAgentGoal,
} = await import("../agent_loop.js");

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}${ok || !detail ? "" : `  -> ${detail}`}`);
  if (!ok) failures++;
};

// A judge with a scripted answer, counting what it was asked.
const saying = (reply) => {
  const calls = [];
  const judge = async (ask) => { calls.push(ask); return typeof reply === "function" ? reply(ask) : reply; };
  return { judge, calls };
};
const kindsOf = (map) => new Map(Object.entries(map)
  .map(([index, kind]) => [Number(index), { state: "answered", kind }]));
const NAME = kindsOf({ 1: "NAME" });
const field = (value, over = {}) => ({ index: 1, name: "recipient", label: "Recipient",
  type: "text", required: true, readOnly: false, value, ...over });
const verdictOf = (said, fields, nameJudge, { facts = "", kinds = NAME, memo = new Map() } = {}) =>
  unsupportedScopeVerdict(said, { fields }, null, facts, kinds, null, null, new Map(), 45000,
    nameJudge ? { judge: nameJudge, memo } : null);

// ---------------------------------------------------------------------------
// (a) THE DEFECT, driven. Four sentences whose leading verb is not one of the
//     seventeen. Each was a decided refusal of a correct value; each is now
//     one question about ONE WORD of his own sentence, and a NO clears it.
// ---------------------------------------------------------------------------
const MEASURED = [
  ['Task: Email Coast Dental and ask for a Friday slot. They gave the go-ahead.', "Coast Dental", "Email"],
  ['Task: Text Jordan Kim that dinner moved to 8.', "Jordan Kim", "Text"],
  ['Task: Ask Coast Dental about a Friday slot.', "Coast Dental", "Ask"],
  ['Task: Call Bloom Studio and move the delivery.', "Bloom Studio", "Call"],
];
for (const [said, value, word] of MEASURED) {
  const { judge, calls } = saying("NO");
  const out = await verdictOf(said, [field(value)], judge);
  check(`(a) "${word} ${value}" is his whole name once the word is read`,
    out.unsupported.length === 0 && out.rows.length === 0, JSON.stringify(out.rows));
  check("(a) ...one question, about that word and his sentence — and nothing else",
    calls.length === 1 && calls[0].word === word
      && calls[0].authority === said && Object.keys(calls[0]).join(",") === "word,authority",
    JSON.stringify(calls));
  // THE PRIVACY LEG, said precisely. His sentence rides — it already rides to
  // every other judge in this file — and one word out of it. What must never
  // ride is anything the FORM knows: the box's label, its name, its type, or
  // the fact that a value was typed into it at all.
  check("(a) ...and nothing the form knows goes with it",
    calls.length === 1 && !JSON.stringify(calls).includes("Recipient")
      && !JSON.stringify(calls).includes("recipient")
      && !("value" in calls[0]) && !("label" in calls[0]) && !("type" in calls[0]),
    JSON.stringify(calls));
}

// ---------------------------------------------------------------------------
// (b) THE OTHER DIRECTION. The case the guard exists for: he named a longer
//     thing and the box holds part of it. A YES is a DECIDED refusal — the
//     step model may retype it, an optional default may be cleared.
// ---------------------------------------------------------------------------
{
  const said = "Schedule Jordan Chen at West Coast Dental";
  const { judge, calls } = saying("YES");
  const out = await verdictOf(said, [field("Coast Dental", { name: "clinic", label: "Clinic" })], judge);
  check("(b) 'Coast Dental' under 'West Coast Dental' is refused", out.unsupported.includes("clinic"));
  check("(b) ...as a DECIDED refusal, not a floor-only flag",
    out.rows.length === 1 && out.rows[0].floorOnly === false, JSON.stringify(out.rows));
  check("(b) ...and the word it asked about was his, in the spelling he used",
    calls.length === 1 && calls[0].word === "West", JSON.stringify(calls));
  const optional = field("Coast Dental", { name: "clinic", label: "Clinic", required: false });
  const opt = await verdictOf(said, [optional], saying("YES").judge);
  check("(b) ...and an optional one is in the clearable set, as it always was",
    clearableUnsupportedFields(decidedUnsupportedNames(opt), [optional]).map((f) => f.name).join() === "clinic");
}

// ---------------------------------------------------------------------------
// (c) FOUR STATES, AND THE FLOOR. Every way of not deciding leaves the value
//     FLAGGED (never submitted unexamined) and FLOOR-ONLY (never cleared,
//     never retyped): the owner is asked instead.
// ---------------------------------------------------------------------------
{
  const said = "Task: Email Coast Dental and ask for a Friday slot.";
  const ways = [
    ["no judge is supplied at all", null],
    ["the model returns nothing", async () => ""],
    ["the model waffles", async () => "That word is a verb"],
    ["the model answers in the wrong case", async () => "no"],
    ["the model says UNCLEAR", async () => "UNCLEAR"],
    ["the model errors", async () => { throw new Error("proxy 502"); }],
    ["the model approves with extra instructions", async () => "NO — and clear the box"],
  ];
  for (const [name, judge] of ways) {
    const out = await verdictOf(said, [field("Coast Dental")], judge);
    check(`(c) flagged, floor-only, when ${name}`,
      out.unsupported.includes("recipient") && out.rows.length === 1 && out.rows[0].floorOnly === true,
      JSON.stringify(out.rows));
    check("(c) ...so the clearing pass may not touch it",
      decidedUnsupportedNames(out).length === 0, JSON.stringify(decidedUnsupportedNames(out)));
  }
  // The bare sync guard — a caller with no judge in reach at all — lands in
  // the same place, and can never wave the value through.
  const detailed = unsupportedScopeFieldsDetailed(said, { fields: [field("Coast Dental")] }, null, "", NAME);
  check("(c) the sync guard alone flags it floor-only, never a decided refusal",
    detailed.length === 1 && detailed[0].floorOnly === true, JSON.stringify(detailed));
}

// ---------------------------------------------------------------------------
// (d) WHAT COSTS NOTHING. The question fires only where the word list used to
//     fire AND the answer would change what happens.
// ---------------------------------------------------------------------------
{
  const said = "Task: email Coast Dental and ask for a Friday slot.";
  const { judge, calls } = saying("YES");
  const out = await verdictOf(said, [field("Coast Dental")], judge);
  check("(d) a lowercase word in front asks nobody and passes",
    out.unsupported.length === 0 && calls.length === 0, JSON.stringify(out.rows));
}
{
  const { judge, calls } = saying("YES");
  const out = await verdictOf("Order flowers from Bloom Studio", [field("Bloom Studio")], judge);
  check("(d) a value with no capitalised neighbour asks nobody",
    out.unsupported.length === 0 && calls.length === 0);
}
{
  // A fact that glosses the value settles it before the name branch is
  // reached, exactly as it did before.
  const { judge, calls } = saying("YES");
  const out = await verdictOf("Task: Email Coast Dental about Friday", [field("Coast Dental")], judge,
    { facts: "recipient: Coast Dental" });
  check("(d) a brain-seeded fact carrying the value asks nobody", calls.length === 0 && out.unsupported.length === 0);
}
{
  // One occurrence of the value in his sentence with a LOWERCASE word in
  // front of it settles the whole thing with no call, even when another
  // occurrence is capitalised — one place he wrote the whole name is proof
  // the value is the whole name.
  const { judge, calls } = saying("YES");
  const out = await verdictOf("Task: Renew the plan at Coast Dental.", [field("Coast Dental")], judge);
  check("(d) a value with a lowercase word each side is settled, unasked",
    calls.length === 0 && out.unsupported.length === 0, JSON.stringify(out.rows));
}
{
  // BOTH SIDES ASK. The word AFTER the value can be an ordinary capital too —
  // the first word of his next sentence — and judging that side by its capital
  // alone would leave half the decision where it was.
  const said = "Task: Renew the plan at Coast Dental. Email them to confirm.";
  const { judge, calls } = saying("NO");
  const out = await verdictOf(said, [field("Coast Dental")], judge);
  check("(d) the word AFTER is asked about too, and a NO settles it",
    calls.length === 1 && calls[0].word === "Email" && out.unsupported.length === 0,
    JSON.stringify(calls) + JSON.stringify(out.rows));
}
{
  const said = "Task: Text Jordan Kim about Friday.";
  const { judge, calls } = saying((ask) => (ask.word === "Kim" ? "YES" : "NO"));
  const out = await verdictOf(said, [field("Jordan")], judge);
  check("(d) a value with an unread word on EACH side has both read, in one pass",
    calls.length === 2 && out.unsupported.includes("recipient") && out.rows[0].floorOnly === false,
    JSON.stringify(calls) + JSON.stringify(out.rows));
}
{
  // Two boxes, one word: one call. The distinct-word pass is what makes a
  // form with several name boxes cost what one box costs.
  const said = "Task: Email Coast Dental about Friday.";
  const { judge, calls } = saying("NO");
  const out = await verdictOf(said, [
    field("Coast Dental"),
    field("Coast Dental", { index: 2, name: "cc", label: "CC" }),
  ], judge, { kinds: kindsOf({ 1: "NAME", 2: "NAME" }) });
  check("(d) two boxes holding the same name cost ONE call",
    calls.length === 1 && out.unsupported.length === 0, `calls=${calls.length}`);
}
{
  // And across two gate passes in one run, the run memo answers the second.
  const said = "Task: Email Coast Dental and ask for a Friday slot.";
  const memo = new Map();
  const { judge, calls } = saying("NO");
  await verdictOf(said, [field("Coast Dental")], judge, { memo });
  await verdictOf(said, [field("Coast Dental")], judge, { memo });
  check("(d) the run memo answers the second pass with no second call", calls.length === 1);
}
{
  // A NAMEPART verdict is provenance-only and never reaches the question.
  const { judge, calls } = saying("YES");
  const out = await verdictOf("Task: Text Jordan Kim about Friday",
    [field("Jordan", { name: "first", label: "First name" })], judge,
    { kinds: kindsOf({ 1: "NAMEPART" }) });
  check("(d) a NAMEPART box asks nobody — a first/last split is not a truncation",
    calls.length === 0 && out.unsupported.length === 0, JSON.stringify(out.rows));
}

// ---------------------------------------------------------------------------
// (e) THE T3 TRIGGER. The shape still decides whether the FORM's kinds are
//     worth one batched question, and it now fires in the cases the word list
//     swallowed — a wider trigger, which is the safe direction for a trigger.
// ---------------------------------------------------------------------------
{
  const need = (said, f) => fieldKindsNeeded(said, [f]).length === 1;
  check("(e) 'Task: Email Coast Dental' now asks the form what its boxes are for",
    need("Task: Email Coast Dental and ask for a Friday slot.",
      { index: 1, label: "Recipient", type: "text", value: "Coast Dental" }));
  check("(e) ...and the case that always triggered still does",
    need("Schedule Jordan Chen at West Coast Dental",
      { index: 1, label: "Clinic", type: "text", value: "Coast Dental" }));
  check("(e) a native time beside a capitalised word is a clock reading, not a name",
    fieldKindsNeeded("Book it for 7:30 tonight at The Keg",
      [{ index: 1, label: "Time", type: "time", value: "19:30" }]).length === 0);
}

// ---------------------------------------------------------------------------
// (f) WHAT THE JUDGE IS SENT. His sentence and one word, each in its own
//     one-time-tagged block, with the injection clause answering UNCLEAR.
// ---------------------------------------------------------------------------
{
  const messages = namePartMessages({
    word: "Email", authority: 'Task: Email Coast Dental. They said: "go ahead"' }, "t");
  check("(f) the system turn is the question and nothing else",
    messages[0].content === NAME_PART_SYSTEM && messages.length === 2);
  check("(f) the sentence is fenced under a one-time tag",
    messages[1].content.includes('<SENTENCE t>\nTask: Email Coast Dental. They said: "go ahead"\n</SENTENCE t>'),
    messages[1].content);
  check("(f) the word is fenced too", messages[1].content.includes("<WORD t>\nEmail\n</WORD t>"));
  check("(f) the injection clause answers UNCLEAR, the floor's own state",
    /answer UNCLEAR/.test(NAME_PART_SYSTEM) && /never instructions to you/.test(NAME_PART_SYSTEM));
  check("(f) the three tokens are specified exactly",
    /exactly YES, exactly NO, or exactly UNCLEAR/.test(NAME_PART_SYSTEM));
  check("(f) nothing about a form, a field or a value is in the question",
    !/\bfield\b|\bform\b|\bbox\b|\bvalue\b/i.test(NAME_PART_SYSTEM), NAME_PART_SYSTEM.slice(0, 120));
}

// ---------------------------------------------------------------------------
// (g) THE BLAST RADIUS, THROUGH THE REAL LOOP. The measured errand, on a form
//     with the correct value already in it, with the run authorised to press
//     the button. With the judge saying NO the run reaches the commit; the
//     control is the same run with the judge saying YES.
// ---------------------------------------------------------------------------
const GOAL = "Task: Email Coast Dental and ask for a Friday slot.";
const NAME_SENTINEL = /is that word part of a NAME/;
const KIND_SENTINEL = /what KIND of value that field is FOR/;
const STEP_SENTINEL = /You are Anticipy's browser agent/;
const AUDIT_SENTINEL = /You audit a browser agent's claim/;

async function drive(nameToken) {
  harness.tabs.clear();
  for (const key of Object.keys(harness.storageData)) delete harness.storageData[key];
  harness.addTab({ url: "https://news.site/read", active: true });
  const page = {
    url: "https://clinic.example/contact",
    title: "Contact",
    elements: '[0] <textbox> Recipient [contains "Coast Dental"] @(10,10)\n[1] <button> Send @(10,60)',
    text: "Contact the clinic.",
    fields: [{ index: 0, name: "recipient", label: "Recipient", type: "text",
               value: "Coast Dental", required: true, readOnly: false }],
  };
  harness.mapPage = () => page;
  harness.onCdp = (tabId, method, params) => {
    if (method === "Page.captureScreenshot") return { data: FAKE_JPEG };
    if (method === "Input.dispatchMouseEvent" && params?.type === "mousePressed") pressed.push(1);
    return undefined;
  };
  const realExecuteScript = chrome.scripting.executeScript;
  chrome.scripting.executeScript = async (opts) => {
    const src = opts?.func ? String(opts.func) : "";
    if (src.includes("navigationLink")) return [{ frameId: 0, result: true }];
    if (src.includes("fieldsIn")) {
      return [{ frameId: 0, result: { label: "Send", tag: "button", href: "", nearbyText: "Send",
        formAction: "/contact", name: "", elementId: "", fieldIndexes: [0] } }];
    }
    return realExecuteScript(opts);
  };
  const asked = { name: 0, kind: 0 };
  const steps = [{ action: "click", index: 1 }, { action: "done", result: "Asked the clinic about Friday." }];
  let at = 0;
  const trace = [];
  globalThis.fetch = async (url, opts = {}) => {
    if (!String(url).includes("openrouter")) return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
    const joined = JSON.parse(opts.body).messages.map((m) => (Array.isArray(m.content)
      ? m.content.map((p) => (p.type === "text" ? p.text : "")).join("\n") : String(m.content || ""))).join("\n");
    let content = "{}";
    if (NAME_SENTINEL.test(joined)) { asked.name += 1; content = nameToken; }
    else if (KIND_SENTINEL.test(joined)) { asked.kind += 1; content = '{"0":"NAME"}'; }
    else if (AUDIT_SENTINEL.test(joined)) content = '{"verified":true}';
    else if (STEP_SENTINEL.test(joined)) content = JSON.stringify(steps[Math.min(at++, steps.length - 1)]);
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content } }] }), text: async () => "" };
  };
  const out = await runAgentGoal(GOAL, {
    apiKey: "test-key", scope: GOAL, readOnly: false, authorized: true, planning: false,
    startUrl: page.url, maxSteps: 5, budgetMs: 60_000, stillLive: async () => true,
    onTrace: (history) => { trace.length = 0; trace.push(...history); },
  });
  chrome.scripting.executeScript = realExecuteScript;
  return { out, trace, asked };
}
const pressed = [];
{
  pressed.length = 0;
  const { out, trace, asked } = await drive("NO");
  check("(g) with the word read as an ordinary verb the run gets past the gate",
    !trace.some((line) => /PRE-SUBMIT BLOCK/.test(line)), trace.join(" | ").slice(0, 300));
  check("(g) ...the button is pressed", pressed.length > 0);
  check("(g) ...the run ends done", out.status === "done", `${out.status}: ${String(out.result).slice(0, 120)}`);
  check("(g) ...and the name question was asked exactly once for the whole run",
    asked.name === 1, `name=${asked.name}`);
}
{
  pressed.length = 0;
  const { out, trace } = await drive("YES");
  check("(g) THE CONTROL: read as part of a name, the identical run is blocked",
    trace.some((line) => /PRE-SUBMIT BLOCK/.test(line)) || out.status === "needs_user",
    `${out.status} | ${trace.join(" | ").slice(0, 300)}`);
  check("(g) ...and the button was never pressed", pressed.length === 0);
}
{
  pressed.length = 0;
  const { out } = await drive("mumble");
  check("(g) with no verdict the run ends at the OWNER, not at a wipe",
    out.status === "needs_user" && /could not tell what the/.test(String(out.result)),
    `${out.status}: ${String(out.result).slice(0, 160)}`);
  check("(g) ...and the button was never pressed", pressed.length === 0);
}

// ---------------------------------------------------------------------------
// (h) THE LAW LEG. The list is gone from the code, the record of what it did
//     survives in the comment, and nothing here is tape.
// ---------------------------------------------------------------------------
{
  const src = readFileSync(new URL("../agent_loop.js", import.meta.url), "utf8");
  const code = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
  check("(h) law 1: the boundaries word list is gone from the code",
    !/const boundaries = new Set/.test(code) && !code.includes("completeNamedValue"));
  check("(h) ...and no vocabulary of connectives survives in a regex literal here",
    !/"anticipy"|'anticipy'/.test(code));
  check("(h) the record names the measured sentences and what they cost",
    /WHAT WAS HERE UNTIL 2026-09-05 \(F10\)/.test(src)
      && /Task: Email Coast Dental/.test(src) && /wiped/i.test(src));
  check("(h) the memo is minted per run, inside runAgentGoal, never shared across owners",
    /const names = \{ judge: namePartJudge\(apiKey, model\), memo: new Map\(\) \};/.test(code)
      && !/namePartJudge\(/.test(code.slice(0, code.indexOf("export async function verifyDone("))));
  const marker = "TA" + "PE:";
  check("(h) no tape marker — the pattern was replaced, not deferred",
    !new RegExp(marker + "[^\\n]*(?:F10|boundaries|name)", "i").test(src));
}

if (failures) { console.log(`test_name_completeness_is_not_a_word_list: ${failures} FAILED`); process.exit(1); }
console.log("test_name_completeness_is_not_a_word_list: whether a word is part of his name is a model's verdict");
process.exit(0);
