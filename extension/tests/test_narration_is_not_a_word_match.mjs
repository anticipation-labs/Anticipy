// THE NARRATION FILTER IS NOT A WORD MATCH — audit #77.
//
// A supervised read (`supervised_read.js`) reads one person's mail in their
// own browser, once, while they watch, and narrates CONCLUSIONS. A narration
// line is an EVENT: it leaves the device and is stored, so
// `design/LOCAL-FIRST.md:9-11` decides its contents absolutely — conclusions
// travel, the stream never does. Until 2026-09-05 the thing deciding whether
// a model-authored line was a conclusion or a quotation was a sentence count,
// a quote-mark list, a header word list and a furniture word list. Measured:
// "Marcus needs the proposal by Thursday for his board meeting" — a third
// party's words, paraphrased — sailed through to the wire; "Dr. Evans is
// waiting on your scan results" was refused as two sentences.
//
// Now: the seatbelt reads what a line CARRIES (bytes, an address, a link); a
// model with the pages in view answers ONE question on its own — is this line
// hers, or the page's? — in four states; and the loop compares the verdict as
// a FLOOR. Every test below drives the real loop and reads what reached the
// wire, the trace and the caller — never the source.
//
// Mutations that must turn this red (each done for real, see the commit):
//   1. in `say`, `verdict !== LINE_HERS` -> `verdict === LINE_PAGE`: the
//      floor lifts itself, UNASKED/UNANSWERED lines leave.        (§1)
//   2. `lineVerdict` returns LINE_HERS whenever `parsed.hers` is truthy:
//      {"hers":"yes"} becomes a yes.                              (§1, §7)
//   3. `say` never asks — the verdict is skipped and the old seatbelt-only
//      behaviour taken.                                           (§2, §4)
//   4. the lease re-read before each fact's judge+emit is removed. (§6)
//
// Run: node extension/tests/test_narration_is_not_a_word_match.mjs
import {
  DISTIL_SYSTEM, JUDGE_SYSTEM, LINE_HERS, LINE_PAGE, LINE_UNANSWERED, LINE_UNASKED,
  STEP_SYSTEM, lineVerdict, runSupervisedRead, vocabularyFor,
} from "../supervised_read.js";

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}${ok || !detail ? "" : `  -> ${detail}`}`);
  if (!ok) failures++;
};

// A thread, in the shape a thread reads. Marcus's sentence is what must never
// leave; the LINE below is that sentence paraphrased — the shape the old word
// lists could not see.
const THREAD = [
  "Q3 proposal — final draft",
  "Marcus Bell <marcus@bellworks.com>",
  "Need the proposal by Thursday for the board meeting, getting impatient here.",
].join("\n");
const LINE = "Marcus needs the proposal by Thursday for his board meeting";
const FACT = "Marcus Bell is a client and a proposal is in flight";
const SOURCE = "mail";
const VOCAB = vocabularyFor(SOURCE);

/**
 * One read, driven end to end. The fake model DISPATCHES ON THE REAL SYSTEM
 * PROMPTS, compared whole: the step prompt returns a scroll carrying LINE
 * and then done; the distil prompt returns FACT; the judge prompt returns
 * whatever this case says it should. A single fixed reply for every call
 * would starve the loop of moves and facts, and every floor pin below would
 * be green with the floor removed — the hole the attack on this design
 * named.
 */
async function read({
  judge, facts = [{ fact: FACT, importance: 3 }], say = LINE,
  lease = () => new Date(Date.now() + 30000).toISOString(),
  askModel = "dispatch",
} = {}) {
  const calls = [];
  const emitted = [];
  const notes = [];
  let leaseChecks = 0;
  let stepped = false;
  const dispatch = async (system, user) => {
    calls.push({ system, user });
    if (system === STEP_SYSTEM(SOURCE, VOCAB)) {
      if (stepped) return JSON.stringify({ action: "done" });
      stepped = true;
      return JSON.stringify(say ? { action: "scroll", say } : { action: "scroll" });
    }
    if (system === DISTIL_SYSTEM(SOURCE)) return JSON.stringify({ facts });
    if (system === JUDGE_SYSTEM(SOURCE)) return judge(user);
    throw new Error(`a prompt this test does not know: ${String(system).slice(0, 60)}`);
  };
  const deps = {
    openTab: async () => 77,
    readPage: async () => ({ text: THREAD, url: "https://mail.google.com/thread/1" }),
    scrollPage: async () => {},
    closeTab: async () => {},
    leaseUntil: async () => { leaseChecks++; return lease(leaseChecks); },
    emit: async (event) => { emitted.push(event); },
    note: (line) => { notes.push(line); },
  };
  if (askModel === "dispatch") deps.askModel = dispatch;
  const out = await runSupervisedRead({ source: SOURCE, startUrl: "https://mail.google.com/", deps });
  const judged = calls.filter((c) => c.system === JUDGE_SYSTEM(SOURCE));
  const lineEvents = emitted.filter((e) => e.kind === "read_line").map((e) => e.text);
  const factEvents = emitted.filter((e) => e.kind === "read_fact").map((e) => e.text);
  return { out, calls, judged, emitted, lineEvents, factEvents, notes, leaseChecks: () => leaseChecks };
}

// The line a judge call was asked about — the text between its own markers,
// after the fenced pages (which legitimately carry whatever the page did).
const judgedLine = (call) => (call.user.split("--- BEGIN THE LINE SHE WROTE ---\n")[1] || "").split("\n--- END")[0];

// Every floor pin asserts ALL THREE: the wire, the caller's arrays, and the
// trace — because a line can leak through any of them.
function nothingLeft(label, r) {
  check(`${label}: no read_line carried the model's line`, !r.lineEvents.includes(LINE), JSON.stringify(r.lineEvents));
  check(`${label}: no read_fact carried the fact`, !r.factEvents.includes(FACT), JSON.stringify(r.factEvents));
  check(`${label}: out.lines does not carry the line`, !r.out.lines.includes(LINE), JSON.stringify(r.out.lines));
  check(`${label}: out.facts does not carry the fact`, !r.out.facts.some((f) => f.fact === FACT), JSON.stringify(r.out.facts));
  const trace = r.out.refused.join("\n") + "\n" + r.notes.join("\n");
  check(`${label}: neither the line nor the fact appears in the trace`,
    !trace.includes(LINE) && !trace.includes(FACT), trace.slice(0, 200));
  check(`${label}: nothing on the page reached the wire`,
    !/getting impatient|bellworks|final draft/i.test(JSON.stringify(r.emitted)), JSON.stringify(r.emitted));
}

// ---------------------------------------------------------------------------
// §1 THE FLOOR. No verdict is not a yes. A judge that throws, answers prose,
// or answers with a token we did not specify leaves the line on the device.
// ---------------------------------------------------------------------------
for (const [label, judge] of [
  ["judge throws", () => { throw new Error("proxy 502"); }],
  ["judge answers prose", () => "I'd say that one is fine to keep."],
  ['judge answers {"hers":"yes"}', () => JSON.stringify({ hers: "yes" })],
  ['judge answers {"hers":1}', () => JSON.stringify({ hers: 1 })],
  ['judge answers {"hers":"true"}', () => JSON.stringify({ hers: "true" })],
  ["judge answers an empty object", () => "{}"],
  ["judge answers a bare array", () => "[true]"],
]) {
  const r = await read({ judge });
  nothingLeft(label, r);
  check(`${label}: the read itself is not a failure`, r.out.ok === true, JSON.stringify(r.out));
  check(`${label}: the trace says the judge did not answer, for the line and for the fact`,
    r.out.refused.filter((x) => /the judge did not answer/.test(x)).length === 2,
    JSON.stringify(r.out.refused));
  check(`${label}: the closing line says she could not check, not that there was nothing`,
    r.lineEvents.some((t) => /couldn't check/.test(t)) && !r.lineEvents.some((t) => /nothing in there worth keeping/.test(t)),
    JSON.stringify(r.lineEvents));
}
{
  // The "judge absent" case restated honestly: the judge rides the same
  // injected askModel as the step and distil calls, so no askModel means no
  // moves, no facts, nothing to judge — zero calls, zero facts, and only the
  // module's own lines.
  const r = await read({ askModel: null });
  check("no askModel: zero model calls of any kind", r.calls.length === 0, String(r.calls.length));
  check("no askModel: zero facts", r.out.facts.length === 0);
  check("no askModel: only module-authored lines were said",
    r.lineEvents.length > 0 && r.lineEvents.every((t) => /Opening your mail now|nothing in there worth keeping/.test(t)),
    JSON.stringify(r.lineEvents));
}

// ---------------------------------------------------------------------------
// §2 PAGE. The judge, with the thread in view, says the paraphrase is the
// page's. It does not leave, and the trace says why without saying what.
// ---------------------------------------------------------------------------
{
  const r = await read({ judge: () => JSON.stringify({ hers: false }) });
  nothingLeft("hers:false", r);
  check("hers:false: the trace names page text as the reason, for the line and for the fact",
    r.out.refused.filter((x) => /the judge read it as page text/.test(x)).length === 2,
    JSON.stringify(r.out.refused));
  check("hers:false: the closing line is 'nothing worth keeping' — the judge DID answer",
    r.lineEvents.some((t) => /nothing in there worth keeping/.test(t)) && !r.lineEvents.some((t) => /couldn't check/.test(t)),
    JSON.stringify(r.lineEvents));
}

// ---------------------------------------------------------------------------
// §3 HERS. A live yes is the only thing that lets a line leave.
// ---------------------------------------------------------------------------
{
  const r = await read({ judge: () => JSON.stringify({ hers: true }) });
  check("hers:true: the line went out as a read_line with the mail fence tag",
    r.emitted.some((e) => e.kind === "read_line" && e.text === LINE && e.source === "supervised_mail"),
    JSON.stringify(r.emitted));
  check("hers:true: the fact went out as a read_fact with its importance",
    r.emitted.some((e) => e.kind === "read_fact" && e.text === FACT && e.source === "supervised_mail" && e.importance === 3),
    JSON.stringify(r.emitted));
  check("hers:true: the caller sees the line and the fact",
    r.out.lines.includes(LINE) && r.out.facts.some((f) => f.fact === FACT));
  check("hers:true: nothing was refused", r.out.refused.length === 0, JSON.stringify(r.out.refused));
  check("hers:true: the closing line counts one thing",
    r.lineEvents.some((t) => /Done — 1 thing I didn't know about you/.test(t)), JSON.stringify(r.lineEvents));
}

// ---------------------------------------------------------------------------
// §4 ON ITS OWN. One question, its own prompt, the pages and the line fenced
// in front of it — never a ninth key in the step or distil reply.
// ---------------------------------------------------------------------------
{
  const r = await read({ judge: () => JSON.stringify({ hers: true }) });
  check("exactly one judge call per model-authored line: the say and the fact",
    r.judged.length === 2, `${r.judged.length} judge calls`);
  check("the judge's prompt is neither the step prompt nor the distil prompt",
    r.judged.every((c) => c.system !== STEP_SYSTEM(SOURCE, VOCAB) && c.system !== DISTIL_SYSTEM(SOURCE)));
  check("the step and distil prompts never ask for a verdict — no `hers` anywhere in them",
    !/hers/.test(STEP_SYSTEM(SOURCE, VOCAB)) && !/hers/.test(DISTIL_SYSTEM(SOURCE)));
  check("the judge sees the fenced pages",
    r.judged.every((c) => /--- BEGIN UNTRUSTED PAGE 1 \(mail\.google\.com\) ---/.test(c.user) && /getting impatient/.test(c.user)));
  check("the judge sees the fenced line, and the fenced fact, one per call",
    /--- BEGIN THE LINE SHE WROTE ---\n.*\n--- END THE LINE SHE WROTE ---/.test(r.judged[0].user)
      && judgedLine(r.judged[0]) === LINE && judgedLine(r.judged[1]) === FACT,
    r.judged.map((c) => c.user.slice(-120)).join(" | "));
  check("the judge's system prompt fences the line as untrusted alongside the pages",
    /UNTRUSTED/.test(JUDGE_SYSTEM(SOURCE)) && /answer false/.test(JUDGE_SYSTEM(SOURCE)));
  const order = r.calls.map((c) =>
    c.system === STEP_SYSTEM(SOURCE, VOCAB) ? "step"
      : c.system === DISTIL_SYSTEM(SOURCE) ? "distil"
        : c.system === JUDGE_SYSTEM(SOURCE) ? "judge" : "?");
  check("the judge is asked right after the line exists, and right after the fact exists",
    order.join(",") === "step,judge,step,distil,judge", order.join(","));
}

// ---------------------------------------------------------------------------
// §5 sayOwn. Lines THIS FILE wrote pass the seatbelt and skip the judge, so a
// dead judge cannot mute supervision's own voice.
// ---------------------------------------------------------------------------
{
  // Lease dies at the first step: "You looked away" must still be said, with
  // no judge in the loop at all.
  let n = 0;
  const r = await read({
    judge: () => { throw new Error("dead"); },
    lease: () => { n++; return new Date(Date.now() + (n <= 1 ? 30000 : -1000)).toISOString(); },
  });
  check("a lapsed lease is announced with zero judge calls",
    r.out.stopped === "lease" && r.lineEvents.some((t) => /looked away/.test(t)) && r.judged.length === 0,
    JSON.stringify({ stopped: r.out.stopped, lines: r.lineEvents, judged: r.judged.length }));
}
{
  // A judge that is dead for the whole read: the opening and closing lines
  // still reach the phone; the model's line and fact do not.
  const r = await read({ judge: () => { throw new Error("dead"); } });
  check("with a dead judge the module's own opening line still goes out",
    r.lineEvents.some((t) => t === "Opening your mail now."), JSON.stringify(r.lineEvents));
  check("with a dead judge the module's own closing line still goes out",
    r.lineEvents.some((t) => /couldn't check/.test(t)), JSON.stringify(r.lineEvents));
  check("with a dead judge the judge was still asked — once per model-authored line — and refused",
    r.judged.length === 2 && !r.lineEvents.includes(LINE) && r.factEvents.length === 0);
}

// ---------------------------------------------------------------------------
// §6 THE LEASE IS RE-READ BEFORE EVERY JUDGE+EMIT. Fifteen facts are fifteen
// judge round-trips; the unwatched window may not stretch across them.
// ---------------------------------------------------------------------------
{
  const three = [
    { fact: "Marcus Bell is a client and a proposal is in flight", importance: 3 },
    { fact: "Priya Raman runs payroll", importance: 3 },
    { fact: "Dana Whitlock is a recruiter", importance: 2 },
  ];
  // Lease reads, in order: 1 before the tab; 2 at the step top; 3 before the
  // scroll; 4 before the say judge; 5 at the next step top; 6 before distil;
  // 7 before fact 1's judge; 8 before fact 2's judge. Live through 7, dead
  // from 8.
  let n = 0;
  const r = await read({
    facts: three,
    judge: () => JSON.stringify({ hers: true }),
    lease: () => { n++; return new Date(Date.now() + (n <= 7 ? 30000 : -1000)).toISOString(); },
  });
  const factJudgeCalls = r.judged.filter((c) => judgedLine(c) !== LINE).length;
  check("the lease lapsing between two facts stops the loop", r.out.stopped === "lease", r.out.stopped);
  check("exactly one fact was judged and kept before the lapse",
    factJudgeCalls === 1 && r.out.facts.length === 1 && r.factEvents.length === 1,
    JSON.stringify({ factJudgeCalls, facts: r.out.facts.length, events: r.factEvents.length }));
  check("the second and third facts were never judged and never sent",
    !r.judged.some((c) => /Priya|Dana/.test(judgedLine(c))) && !r.emitted.some((e) => /Priya|Dana/.test(e.text)),
    JSON.stringify(r.emitted));
  check("and she says why she stopped", r.lineEvents.some((t) => /looked away/.test(t)), JSON.stringify(r.lineEvents));
}
{
  // The same property on the say path: reads 1-3 (tab, step top, before the
  // scroll) are live and read 4 — the one immediately before the say judge —
  // is dead. The line is never judged and never sent. Without that fourth
  // read the line would be judged, sent, and only the NEXT step would stop.
  let n = 0;
  const r = await read({
    judge: () => JSON.stringify({ hers: true }),
    lease: () => { n++; return new Date(Date.now() + (n <= 3 ? 30000 : -1000)).toISOString(); },
  });
  check("a lease that dies before the say judge means the line is never judged and never sent",
    r.out.stopped === "lease" && r.judged.length === 0 && !r.lineEvents.includes(LINE),
    JSON.stringify({ stopped: r.out.stopped, judged: r.judged.length, lines: r.lineEvents }));
}

// ---------------------------------------------------------------------------
// §7 lineVerdict on its own: the four states, and what each input maps to.
// ---------------------------------------------------------------------------
{
  const slices = [{ where: "mail.google.com", text: THREAD }];
  const v = (reply) => lineVerdict({
    askModel: async () => (typeof reply === "function" ? reply() : reply), source: SOURCE, line: LINE, slices,
  });
  check("no askModel -> UNASKED", (await lineVerdict({ source: SOURCE, line: LINE, slices })) === LINE_UNASKED);
  check("a throw -> UNANSWERED", (await v(() => { throw new Error("x"); })) === LINE_UNANSWERED);
  check("prose -> UNANSWERED", (await v("no idea")) === LINE_UNANSWERED);
  check('{"hers":"yes"} -> UNANSWERED, never HERS', (await v('{"hers":"yes"}')) === LINE_UNANSWERED);
  check('{"hers":true} in prose wrapping -> HERS (the last object is read)', (await v('Sure: {"hers":true}')) === LINE_HERS);
  check('{"hers":false} -> PAGE', (await v('{"hers":false}')) === LINE_PAGE);
  check('{"hers":true} -> HERS', (await v('{"hers":true}')) === LINE_HERS);
  check("the four states are distinct strings",
    new Set([LINE_HERS, LINE_PAGE, LINE_UNASKED, LINE_UNANSWERED]).size === 4);
  let seen = null;
  await lineVerdict({ askModel: async (system, user) => { seen = { system, user }; return '{"hers":true}'; }, source: SOURCE, line: LINE, slices });
  check("the judge is asked with its own system prompt, the fenced pages and the fenced line",
    seen && seen.system === JUDGE_SYSTEM(SOURCE)
      && /BEGIN UNTRUSTED PAGE 1 \(mail\.google\.com\)/.test(seen.user)
      && seen.user.endsWith(`--- BEGIN THE LINE SHE WROTE ---\n${LINE}\n--- END THE LINE SHE WROTE ---`),
    JSON.stringify(seen).slice(0, 200));
}

// ---------------------------------------------------------------------------
// §8 COST. The judge fires only where a model-authored line exists. A read
// whose step says done with nothing to say, and whose distil finds nothing,
// asks it zero times.
// ---------------------------------------------------------------------------
{
  const r = await read({ say: "", facts: [], judge: () => JSON.stringify({ hers: true }) });
  check("no model-authored line, no judge call", r.judged.length === 0, `${r.judged.length} judge calls`);
  check("and the read still closes honestly", r.out.ok && r.lineEvents.some((t) => /nothing in there worth keeping/.test(t)),
    JSON.stringify(r.lineEvents));
}
{
  // The seatbelt runs BEFORE the judge: a fact carrying an address is dropped
  // by what it carries, and is never the line a judge is asked about. (The
  // fenced PAGES carry the address, as they already do in the step call —
  // the pin is on the fenced line.)
  const r = await read({
    say: "",
    facts: [{ fact: "Reach Marcus at marcus@bellworks.com about the proposal", importance: 3 }],
    judge: () => JSON.stringify({ hers: true }),
  });
  check("an address-bearing fact is never put to the judge, and never leaves, even with a judge saying yes",
    r.judged.length === 0 && r.factEvents.length === 0 && r.out.facts.length === 0,
    JSON.stringify({ judged: r.judged.length, facts: r.out.facts }));
}

if (failures) { console.error(`test_narration_is_not_a_word_match: ${failures} failed`); process.exit(1); }
console.log("test_narration_is_not_a_word_match: all passed");
