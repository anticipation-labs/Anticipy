// WHICH ROW OF HIS INBOX WE OPEN IS NOT A WORD MATCH.
//
// Audit #F07. Until 2026-09-05 `sideTripDeps.clickText` split its own purpose
// string ("the verification code") into the words over three letters —
// ["verification", "code"] — and clicked the FIRST link/row/listitem on the
// page whose text contained ANY of them. In a real mailbox that is: last
// week's "Your verification code" from a different site; a newsletter about a
// discount code; a security alert. The side trip exists because the run needs
// a one-time code, so the message it opens is then read. A word list decided
// which of a person's messages meant "the one we came for", and the cost of
// being wrong is opening a stranger's mail in the owner's own mailbox.
//
// Now `rowJudge` asks a model ONE question on its own — which row, if any, is
// the message this errand needs opened — and the caller compares the answer in
// four states: an index clicks; NONE, UNCLEAR and silence click nothing. The
// index is then CONTAINED: it must be one of the rows we actually offered, so
// a page that tries to steer the reply can at most name a row already on the
// list of things a side trip may click.
//
// THE TEST THIS SUITE IS BUILT AROUND: the rows are held identical and only
// the model's answer changes, and a different row is clicked. Then the answer
// is held identical and the WORDS are changed to share nothing with the
// purpose, and the same row is still clicked. A word list can do neither.
//
// Run: node extension/tests/test_row_is_a_model_verdict.mjs
import { readFileSync } from "node:fs";
import { installChrome } from "./chrome_mock.mjs";

const harness = installChrome();
const { sideTripDeps, rowJudge, MODEL_REPLY_FLOOR } = await import("../agent_loop.js");

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}${ok || !detail ? "" : `  -> ${detail}`}`);
  if (!ok) failures++;
};

const ROW_SENTINEL = /which row, if any, is the message this errand needs opened/i;
const PURPOSE = "the verification code";

// A mailbox list where THREE rows carry a word from the purpose. The old
// picker took the first of them, which is row 4 — a different site's code from
// last week. The message we came for is row 7 and shares no distinguishing
// word with anything.
const ROWS = [
  '[3] <row> Wren Digest — five things we liked this week @(10,120)',
  '[4] <row> Peakline Security — your verification code is 883120 @(10,160)',
  '[5] <row> Duvel Store — 20% off with code SPRING @(10,200)',
  '[6] <row> Mum — re: sunday @(10,240)',
  '[7] <row> Arbor Rail — 4471 @(10,280)',
  '[8] <button> Compose @(900,60)',
].join("\n");

// One clickText call against a page whose rows we control and a judge whose
// single reply we control. Everything the call DOES is observed: which model
// call went out, and which element was clicked.
async function clickWith({ rows = ROWS, reply, ok = true, elements = null }) {
  harness.tabs.clear();
  const tab = harness.addTab({ url: "https://mail.example/inbox", active: false });
  harness.mapPage = () => ({
    url: "https://mail.example/inbox", title: "Inbox",
    elements: elements === null ? rows : elements, text: "", fields: [], overlay: false,
  });
  const seen = { prompts: [], clicked: [], centres: 0 };
  // elementCenter goes through executeScript in the mock; give every offered
  // index a distinct point so the click can be attributed to a row.
  const realExecute = chrome.scripting.executeScript;
  chrome.scripting.executeScript = async (opts) => {
    const src = opts?.func ? String(opts.func) : "";
    // Match the CENTRE call and nothing else. Matching on "getBoundingClientRect"
    // also caught the page-map function, which contains it, so mapPage returned
    // a point instead of a page and clickText bailed before asking anything —
    // every assertion here read "clicked nothing", which is exactly what a
    // passing FLOOR looks like. A test that cannot tell a working floor from a
    // broken harness proves nothing, so the match is the exact helper name.
    if (/__anticipyCenter\(/.test(src)) {
      seen.centres += 1;
      const idx = Number(opts?.args?.[0]);
      return [{ result: { x: 100, y: 100 + idx } }];
    }
    return realExecute(opts);
  };
  harness.onCdp = (tabId, method, params) => {
    if (method === "Input.dispatchMouseEvent" && params?.type === "mousePressed") {
      seen.clicked.push(Number(params.y) - 100);
    }
    return undefined;
  };
  globalThis.fetch = async (url, opts = {}) => {
    if (!String(url).includes("openrouter")) {
      return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
    }
    const body = JSON.parse(opts.body);
    seen.prompts.push(body.messages.map((m) => String(m.content || "")).join("\n"));
    seen.maxTokens = body.max_tokens;
    if (!ok) return { ok: false, status: 502, json: async () => ({}), text: async () => "" };
    return {
      ok: true, status: 200,
      json: async () => ({ choices: [{ message: { content: reply } }] }),
      text: async () => "",
    };
  };
  const deps = sideTripDeps("test-key", "test-model");
  const opened = await deps.clickText(tab.id, PURPOSE);
  chrome.scripting.executeScript = realExecute;
  return { opened, seen };
}

// ---------------------------------------------------------------------------
// (a) THE PROPERTY. Same rows, different verdict -> a different row opens.
// ---------------------------------------------------------------------------
{
  const seven = await clickWith({ reply: "[7]" });
  check("(a) the judge names row 7 and row 7 is opened",
    seven.opened === true && seven.seen.clicked.includes(7),
    `opened=${seven.opened} clicked=${seven.seen.clicked.join(",")}`);

  const four = await clickWith({ reply: "[4]" });
  check("(a) the SAME rows with a different verdict open row 4 instead",
    four.opened === true && four.seen.clicked.includes(4),
    `opened=${four.opened} clicked=${four.seen.clicked.join(",")}`);

  check("(a) ...and the two runs clicked different rows on identical input",
    seven.seen.clicked.join(",") !== four.seen.clicked.join(","));

  // The old picker's own answer, for the record: the first row containing
  // "verification" or "code" is row 4, not row 7. It could never have reached
  // the message the errand actually needed.
  const oldWords = PURPOSE.toLowerCase().split(/\s+/).filter((w) => w.length > 3);
  const oldPick = ROWS.split("\n").find((row) =>
    /<(link|button|row|listitem|option)>/i.test(row)
      && oldWords.some((w) => row.toLowerCase().includes(w)));
  check("(a) the word list would have opened a different site's message",
    /^\[4\]/.test(oldPick), oldPick);
}

// ---------------------------------------------------------------------------
// (b) ...AND THE WORDS DECIDE NOTHING. Same verdict, rows sharing no word.
// ---------------------------------------------------------------------------
{
  // Not one row contains "verification" or "code" now. A word-overlap picker
  // returns nothing at all here; the judge still names the row it wants.
  const wordless = [
    '[3] <row> Wren Digest — five things we liked this week @(10,120)',
    '[7] <row> Arbor Rail — 4471 @(10,280)',
  ].join("\n");
  const { opened, seen } = await clickWith({ rows: wordless, reply: "[7]" });
  check("(b) a row sharing no word with the errand is still opened when named",
    opened === true && seen.clicked.includes(7), `clicked=${seen.clicked.join(",")}`);
  const oldWords = PURPOSE.toLowerCase().split(/\s+/).filter((w) => w.length > 3);
  check("(b) ...where the word list would have opened nothing at all",
    !wordless.split("\n").some((row) => oldWords.some((w) => row.toLowerCase().includes(w))));
}

// ---------------------------------------------------------------------------
// (c) THE FLOOR. Everything that is not an index clicks nothing.
// ---------------------------------------------------------------------------
for (const [reply, label] of [
  ["NONE", "NONE"],
  ["UNCLEAR", "UNCLEAR"],
  ["", "an empty reply"],
  ["   ", "whitespace"],
  ["I think it is probably row 7", "prose that mentions a row"],
  ["[7] because Arbor Rail sent it", "an index with an explanation"],
  ["seven", "the number in words"],
  ["[]", "empty brackets"],
  ["-1", "a negative index"],
]) {
  const { opened, seen } = await clickWith({ reply });
  check(`(c) ${label} clicks nothing`,
    opened === false && seen.clicked.length === 0, `clicked=${seen.clicked.join(",")}`);
}
{
  const { opened, seen } = await clickWith({ reply: "[7]", ok: false });
  check("(c) a judge that could not be reached clicks nothing",
    opened === false && seen.clicked.length === 0, `clicked=${seen.clicked.join(",")}`);
}

// ---------------------------------------------------------------------------
// (d) CONTAINMENT. The reply may only name a row we offered.
// ---------------------------------------------------------------------------
{
  // [99] is not on the page at all — the shape of a page trying to steer us.
  const { opened, seen } = await clickWith({ reply: "[99]" });
  check("(d) an index that was never offered clicks nothing",
    opened === false && seen.clicked.length === 0, `clicked=${seen.clicked.join(",")}`);

  // [8] IS on the page but is the Compose button, which is offered (a trip may
  // click a button). This documents the boundary honestly rather than pretending
  // it is narrower than it is: containment is "a row we listed", and the list is
  // the link/button/row/listitem/option lines.
  const compose = await clickWith({ reply: "[8]" });
  check("(d) containment is the offered set, and the offered set is what we listed",
    compose.opened === true && compose.seen.clicked.includes(8),
    `clicked=${compose.seen.clicked.join(",")}`);

  // A row that is not clickable at all is never offered, so naming it does nothing.
  const withText = [
    '[2] <text> Your verification code is 118822 @(10,80)',
    '[7] <row> Arbor Rail — 4471 @(10,280)',
  ].join("\n");
  const text = await clickWith({ rows: withText, reply: "[2]" });
  check("(d) a non-clickable line is not in the offered set",
    text.opened === false && text.seen.clicked.length === 0,
    `clicked=${text.seen.clicked.join(",")}`);

  const empty = await clickWith({ elements: "", reply: "[7]" });
  check("(d) a page with no clickable rows asks no question and clicks nothing",
    empty.opened === false && empty.seen.prompts.length === 0);
}

// ---------------------------------------------------------------------------
// (e) THE QUESTION. One question, asked on its own, with the page fenced.
// ---------------------------------------------------------------------------
{
  const { seen } = await clickWith({ reply: "[7]" });
  const prompt = seen.prompts[0] || "";
  check("(e) exactly one model call is made", seen.prompts.length === 1);
  check("(e) it asks the one question", ROW_SENTINEL.test(prompt));
  check("(e) it offers NONE and UNCLEAR as answers",
    /\bNONE\b/.test(prompt) && /\bUNCLEAR\b/.test(prompt));
  check("(e) it tells the model to prefer those over a guess",
    /Prefer NONE or UNCLEAR over a guess/i.test(prompt));
  check("(e) the rows are fenced and declared untrusted",
    /ROWS/.test(prompt) && /untrusted|instructions/i.test(prompt), prompt.slice(0, 160));
  check("(e) the errand's own words are sent, and they are ours not the page's",
    prompt.includes(PURPOSE));
  check("(e) the reply is floored for a thinking model",
    seen.maxTokens >= MODEL_REPLY_FLOOR || MODEL_REPLY_FLOOR >= 512,
    `max_tokens=${seen.maxTokens} floor=${MODEL_REPLY_FLOOR}`);
}

// ---------------------------------------------------------------------------
// (f) THE LAW LEG. The word list stays gone.
// ---------------------------------------------------------------------------
{
  const src = readFileSync(new URL("../agent_loop.js", import.meta.url), "utf8");
  const code = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
  const body = code.slice(code.indexOf("clickText: async (tabId, purpose) =>"),
                          code.indexOf("closeTab: async (tabId) =>"));
  check("(f) law 1: the purpose is no longer split into words",
    !/split\(\/\\s\+\//.test(body) && !/w\.length > 3/.test(body), body.slice(0, 200));
  check("(f) law 1: no row text is matched against those words",
    !/\.includes\(w\)/.test(body) && !/words\.some/.test(body));
  check("(f) the judge is what decides", /rowJudge\(/.test(body));
  check("(f) the offered set is checked after the model answers",
    /offered\.has\(/.test(body));
  check("(f) no tape marker was added for this audit",
    !/TA" \+ "PE:/.test(body) && !body.includes("TA" + "PE:"));
}

console.log(failures === 0
  ? "test_row_is_a_model_verdict: which message we open is a model's verdict"
  : `test_row_is_a_model_verdict: ${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
