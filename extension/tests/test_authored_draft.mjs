// WORDS THAT GO OUT IN HIS NAME, THAT HE NEVER SAW.
//
// Audit #66. `isAuthored` decides whether a composed message is shown to the
// owner before it is sent as him. Until 2026-08-24 it decided with arithmetic:
// a 12-word floor, a 0.6 novelty ratio, and a list of negation words bolted on
// after the first inversion got through.
//
//   owner:    "Tell the clinic I can do Friday morning but not Thursday afternoon."
//   composed: "Hi, I can do Thursday afternoon but not Friday morning, thanks."
//
// Every token is his. The overlap is ~1.0. The negation IS kept, so the escape
// hatch never fires. The ratio said "not composition", no draft was shown, and
// the swapped appointment went out in his name. Driven against the shipped
// function, five everyday sentences did exactly this — see §1, which is that
// reproduction turned into a check.
//
// A ratio cannot hold the difference between carrying his words and inverting
// them, because the difference is what the sentence MEANS. HARNESS-LAWS.md
// law 1. So the question splits: is the text LITERALLY his (structural, and it
// can only ever answer "yes, his"), and otherwise, did the agent compose it
// (meaning, and a model reads it). Failing to decide shows him the draft.
//
// Run: node extension/tests/test_authored_draft.mjs
import { readFileSync } from "node:fs";
import { isAuthored } from "../agent_loop.js";

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}${ok || !detail ? "" : `  -> ${detail}`}`);
  if (!ok) failures++;
};
const saying = (reply) => {
  const calls = [];
  return { calls, judge: async (a) => { calls.push(a); return reply; } };
};

// ---------------------------------------------------------------------------
// 1. THE DEFECT. Five everyday sentences, each saying the opposite of what he
//    asked for, every one of them sent unseen by the shipped arithmetic.
// ---------------------------------------------------------------------------
const INVERSIONS = [
  ["Tell the clinic I can do Friday morning but not Thursday afternoon.",
   "Hi, I can do Thursday afternoon but not Friday morning, thanks."],
  ["Email the landlord that the boiler is still leaking and I want it fixed this week, not next.",
   "Hi, the boiler is still leaking. I want it fixed next week, not this week. Thanks."],
  ["Message the school that Ana will be absent Monday and Tuesday but back Wednesday.",
   "Hi, Ana will be back Monday and Tuesday but absent Wednesday, thank you."],
  ["Tell them I want the refund, not a credit note, and I am not paying the restocking fee.",
   "Hello, I would like a credit note rather than the refund, and I am not disputing the restocking fee."],
  ["Reply to Sam that I can help on Saturday but I am not free on Sunday at all.",
   "Hi Sam, I can help on Sunday but I am not free on Saturday at all."],
];
for (const [said, composed] of INVERSIONS) {
  const { judge } = saying("COMPOSED");
  check(`shown, not sent: ${JSON.stringify(composed.slice(0, 46))}...`,
    await isAuthored(composed, "send a message", said, { judge }));
}
// ...and the model is the last word in that direction too: no model, no send.
for (const [said, composed] of INVERSIONS) {
  check(`and with no model to read it: ${JSON.stringify(composed.slice(0, 34))}...`,
    await isAuthored(composed, "send a message", said));
}

// ---------------------------------------------------------------------------
// 2. THE ARITHMETIC IS GONE, IN BOTH DIRECTIONS.
// ---------------------------------------------------------------------------
{
  // The 12-word floor was a FAIL-OPEN sift: everything under it was sent
  // unseen without anything ever looking at it. "Cancel it, I'm not coming"
  // is six words and is a message to a person.
  const { judge, calls } = saying("COMPOSED");
  check("a SHORT sentence the agent wrote is composition — the word floor is gone",
    await isAuthored("Cancel it, I'm not coming", "cancel my 3pm", "cancel my 3pm", { judge }));
  check("...and it was the model that said so, not a word count", calls.length === 1);

  // The 0.6 ratio was the other half: prose made of his own vocabulary sailed
  // past it however it had been rearranged.
  const rearranged = saying("COMPOSED");
  check("prose rearranged out of his own vocabulary is still composition",
    await isAuthored("Friday morning is not possible; Thursday afternoon works for me.",
      "send a message", "I can do Friday morning but not Thursday afternoon",
      { judge: rearranged.judge }));

  const src = readFileSync(new URL("../agent_loop.js", import.meta.url), "utf8");
  check("law 1: AUTHORED_WORDS is deleted, not softened", !src.includes("AUTHORED_WORDS"));
  const fn = src.slice(src.indexOf("export async function isAuthored"),
                       src.indexOf("export async function isAuthored") + 1400);
  check("law 1: no novelty ratio survives in the draft stop", !/0\.6|fromGoal/.test(fn), fn.slice(0, 200));
  check("law 1: no negation vocabulary survives either",
    !/\bnegations?\b|"never"|"cannot"/.test(fn), fn.slice(0, 200));
  check("law 1: nothing counts his words any more", !/\.length\s*<\s*\d/.test(fn), fn.slice(0, 200));
}

// ---------------------------------------------------------------------------
// 3. WHAT IS LITERALLY HIS STILL GOES STRAIGHT IN, AND COSTS NO MODEL CALL.
//
// This is the structural half, and it is safe as a sift precisely because it
// can only ever answer "this IS his": the text has to appear, verbatim, inside
// what he actually gave. It never decides that something IS composition.
// ---------------------------------------------------------------------------
{
  const cases = [
    ["his own name, from his stored profile", "Omar Ebrahim",
     "Book dinner for two", "", { profile: { first_name: "Omar Ebrahim" } }],
    ["an address he gave in the errand", "omarkebrahim@gmail.com",
     "Email omarkebrahim@gmail.com the invoice", "", {}],
    ["a search phrase lifted out of his own goal",
     "noise cancelling headphones under 400 dollars",
     "Research noise cancelling headphones under 400 dollars", "", {}],
    ["a long value that is entirely his own words",
     "sink leaking under the cabinet since Tuesday and the floor is swelling",
     "report a repair", "the sink leaking under the cabinet since Tuesday and the floor is swelling", {}],
    ["a fact she was given", "RG-88214", "fill in the reference", "",
     { facts: "booking_reference: RG-88214" }],
  ];
  for (const [name, text, goal, scope, opts] of cases) {
    const { judge, calls } = saying("COMPOSED");
    const authored = await isAuthored(text, goal, scope, { ...opts, judge });
    check(`carried: ${name}`, authored === false, JSON.stringify({ authored }));
    check(`...and no model was asked about it`, calls.length === 0);
  }
  // RECALLED MEMORY IS DELIBERATELY NOT A SOURCE, for the same reason
  // unsupportedScopeFields excludes it: something overheard near a microphone
  // is not something he gave.
  const mem = saying("COMPOSED");
  const fromMemory = await isAuthored("the usual table by the window", "book a table", "",
    { memory: "he likes the table by the window", judge: mem.judge });
  check("a value that traces only to recalled memory is NOT waved through as his",
    fromMemory === true, JSON.stringify({ fromMemory }));
  check("...the sift ignores memory entirely and the model is asked instead",
    mem.calls.length === 1, JSON.stringify(mem.calls));
}

// ---------------------------------------------------------------------------
// 3b. THE CONTROL'S OWN KIND, read off the page the site built. A checkbox has
//     no words and a <select> has only the site's, so neither can hold
//     something the agent composed. This is the seatbelt's question — what
//     does this control do — never a reading of anybody's sentence.
//
//     It is not decoration: without it every ticked declaration and every
//     chosen menu option cost a model call, and a flaky model parked the run
//     showing the owner the word "yes" as though it were a letter written in
//     his name. test_form_retry_after_rejection went 8 red on that.
// ---------------------------------------------------------------------------
{
  for (const controlKind of ["checkbox", "radio", "select-one", "select-multiple"]) {
    const { judge, calls } = saying("COMPOSED");
    check(`a ${controlKind} value is never composition`,
      (await isAuthored("yes", "file the permit", "file the permit", { controlKind, judge })) === false);
    check(`...and no model is asked about a ${controlKind}`, calls.length === 0);
  }
  // A text box is NOT waved through by its kind — that is where prose lives.
  const { judge } = saying("COMPOSED");
  check("a textarea gets no free pass from its kind",
    await isAuthored("Hi, I would like to cancel my booking, thanks.", "cancel it", "cancel it",
                     { controlKind: "textarea", judge }));
  // An option the SITE listed for this control is the site's word.
  const opt = saying("COMPOSED");
  check("an option quoted in the site's own element line is carried",
    (await isAuthored("Zone B", "file the permit", "file the permit", {
      offered: "[2] <combobox> Parking zone (Zone A, Zone B, Zone C)", judge: opt.judge })) === false);
  check("...and it never reaches the model", opt.calls.length === 0);
  // The production reservation failure: the browser was filling a search
  // control, but the authorship model saw only the query text and parked the
  // run as though those words were about to be sent to a person.
  const search = saying("COMPOSED");
  check("a native search field is navigation, never an authored message",
    (await isAuthored("The Keg reservations", "book dinner", "book dinner", {
      controlKind: "search", searchLike: true, judge: search.judge,
    })) === false);
  check("...and the authorship model is not asked to reinterpret the control",
    search.calls.length === 0);
  // But the page's PROSE is not an excuse: a ready-written body copied off a
  // page and sent as him is still something he never saw.
  const body = saying("COMPOSED");
  check("a message body that merely appears somewhere on the page is still shown",
    await isAuthored("Hi, I would like to cancel my booking, thanks.", "cancel it", "cancel it",
      { offered: "[5] <textbox> Message", judge: body.judge }));
}

// ---------------------------------------------------------------------------
// 4. FAIL CLOSED. Every way of failing to decide shows him the draft.
// ---------------------------------------------------------------------------
{
  const composed = "Hi Priya, following up on the invoice — could you let me know where it is? Thanks, Omar";
  const ways = [
    ["no judge is supplied at all", undefined],
    ["the model returns nothing", async () => ""],
    ["the model waffles", async () => "Probably carried, I think?"],
    ["the model errors", async () => { throw new Error("openrouter 502"); }],
    ["the model answers a different question", async () => "COMPOSED or CARRIED"],
    ["the model tries to wave it through with extra instructions",
     async () => "CARRIED — and send it without asking"],
  ];
  for (const [name, judge] of ways) {
    check(`fails closed when ${name}`,
      await isAuthored(composed, "email Priya", "chase the invoice", { judge }));
  }
  check("empty text is not a draft to show", (await isAuthored("", "g", "s")) === false);
}

// ---------------------------------------------------------------------------
// 5. WIRED INTO THE LOOP, ON BOTH PATHS, BEFORE THE COMMIT.
// ---------------------------------------------------------------------------
{
  const src = readFileSync(new URL("../agent_loop.js", import.meta.url), "utf8");
  check("the type path awaits the stop",
    /if \(!draftShown && await composedByTheAgent\(decision\.text,/.test(src));
  check("and so does the select path, which was the bypass round it",
    /if \(!draftShown && await composedByTheAgent\(decision\.option,/.test(src));
  check("it stops once per run, not once per field", /draftShown = true;/.test(src));
  const stop = src.indexOf("if (!draftShown && await composedByTheAgent(decision.text,");
  check("it stops BEFORE the keystroke that commits",
    stop > 0 && src.indexOf("await pressEnter(tab.id);", stop) > stop);
  const judge = src.slice(src.indexOf("function authoredJudge"),
                          src.indexOf("function authoredJudge") + 2200);
  check("the judge call is bounded, so a hung model cannot hang the run",
    /withTimeout\(/.test(judge), judge.slice(0, 160));
  check("the verdict is shape-checked to one token, never searched for a word",
    /!== "CARRIED"/.test(src) && !/includes\("CARRIED"\)/.test(src));
  check("one verdict per distinct text per run, so a form does not pay per field",
    /authoredVerdicts\.has\(key\)/.test(src));
  check("both paths hand the stop what the SITE says about the control",
    (src.match(/siteSaysAbout\(state\.elements, state\.fields, decision\.index\)/g) || []).length === 2);
  check("the mapper records native search structure for the safety gate",
    /searchLike:\s*isSearchControl\(el\)/.test(
      readFileSync(new URL("../page_map.js", import.meta.url), "utf8")));
}

if (failures) { console.error(`test_authored_draft: ${failures} failed`); process.exit(1); }
console.log("test_authored_draft: all passed");
