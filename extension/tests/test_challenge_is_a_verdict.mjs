// A HUMAN CHECK IS A VERDICT, NOT A PHRASE.
//
// Audit #71. `looksLikeCaptcha` ran an English phrase list ("just a moment",
// "checking your browser", "unusual traffic", "verify you are human", ...)
// over the page's own words and, on a hit, the loop POSTed a paid solve,
// declared the host unusable and navigated away, or parked the run and
// texted the owner. Live, 2026-08-16, it parked a real booking over a page
// that held an invisible reCAPTCHA badge and a date field, texted him four
// times in two hours about a CAPTCHA that did not exist, and scrapped the
// reservation. "Just a moment — we're holding your table for 5:00" is a
// table hold, and "just a moment" was in the list.
//
// Now: what the page RENDERS decides whether a question is asked at all
// (challengeFurniture — provider frames and widgets, by origin, that are
// painted and not declared invisible); a model answers ONE question in four
// states; the loop compares as a CEILING — only BLOCKED fences. And an
// executor seatbelt refuses any click, keystroke or select whose target sits
// inside a provider's frame, so "no verdict" can never mean "tick the box".
//
// Every case here drives the real loop through chrome_mock and watches what
// reaches the model, the page and the owner. HARNESS-LAWS.md law 1.
//
// Run: node extension/tests/test_challenge_is_a_verdict.mjs
import { readFileSync } from "node:fs";
import { installChrome } from "./chrome_mock.mjs";

const harness = installChrome();
const {
  runAgentGoal, challengeFurniture, challengeProvider, CHALLENGE_ASK_CAP,
} = await import("../agent_loop.js");

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}${ok || !detail ? "" : `  -> ${detail}`}`);
  if (!ok) failures++;
};

const FAKE_JPEG = Buffer.from("x".repeat(9000)).toString("base64");
// The question is recognised by a phrase of ITS OWN system prompt. If the
// prompt drifts, the stub answers a step decision to it instead, which is
// not a bare token, which is UNANSWERED — and the BLOCKED cases below go
// red rather than the CLEAR ones quietly passing.
const QUESTION = "standing between the assistant";
const STEP_CONTRACT = "You are Anticipy's browser agent";

// ---------------------------------------------------------------------------
// Pages. The booking page is the audit's page, in the shape a real v3 page
// has: the anchor iframe declares size=invisible and the bframe sits in a
// visibility:hidden div. Neither is furniture. The Turnstile frame is.
// ---------------------------------------------------------------------------
const BOOKING = "https://tablehold.example.com/book";
const WALL = "https://fastbite.example.com/browse";
const SEARCH = "https://search.test/";
const DOB = "1987-03-14";   // a form VALUE; the question must never carry it

const V3_ANCHOR = {
  src: "https://www.google.com/recaptcha/api2/anchor?ar=1&k=6LeKEY&co=aHR0&hl=en&v=abc&size=invisible&cb=xyz",
  x: 1020, y: 720, w: 256, h: 60, hidden: false, inViewport: true,
};
const V3_BFRAME = {
  src: "https://www.google.com/recaptcha/api2/bframe?hl=en&v=abc&k=6LeKEY",
  x: 0, y: 0, w: 400, h: 580, hidden: true, inViewport: true,
};
const TURNSTILE_SRC = "https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/b/turnstile/if/ov2/av0/rcv/abc/0x4AAAA/light/normal/";
const TURNSTILE = { src: TURNSTILE_SRC, x: 380, y: 420, w: 300, h: 65, hidden: false, inViewport: true };
const V3_ONLY = [V3_ANCHOR, V3_BFRAME];
const V3_PLUS_TURNSTILE = [V3_ANCHOR, V3_BFRAME, TURNSTILE];

function bookingPage(url, frames, revision = 0) {
  const extraLinks = Array.from({ length: revision }, (_, i) => `[${2 + i}] <link> Menu ${i} @(10,${500 + i})`);
  return {
    url,
    title: "Just a moment — we're holding your table for 5:00",
    text: "Just a moment — we're holding your table for 5:00. Checking your browser details. "
      + "Enter your date of birth to continue. This site is protected by reCAPTCHA and the "
      + "Google Privacy Policy and Terms of Service apply."
      + (revision ? ` Revision ${"x".repeat(revision)}.` : ""),
    elements: [
      `[0] <textbox> Date of birth (date field — use select action with option in the exact format YYYY-MM-DD; currently "${DOB}") @(400,300)`,
      "[1] <button> Continue @(400,360)",
      ...extraLinks,
    ].join("\n"),
    fields: [{ index: 0, name: "dob", label: "Date of birth", type: "date", required: true, readOnly: false, value: DOB }],
    frames,
    widgets: [],
  };
}
function wallPage(url) {
  return {
    url, title: "Just a moment...",
    text: "Verify you are human by completing the challenge below.",
    elements: "[0] <button> Verify you are human @(400,300)",
    fields: [], frames: [TURNSTILE], widgets: [],
  };
}
function searchPage(url) {
  return {
    url, title: "kid friendly delivery - Search",
    text: "Results for kid-friendly dinner delivery in Vancouver: Nook and Superbaba both deliver.",
    elements: "[0] <link> fastbite.example.com - Order food now @(10,10)\n[1] <link> Eater - kid-friendly delivery spots @(10,40)",
    fields: [], frames: [], widgets: [],
  };
}

const chat = (content) => ({
  ok: true, status: 200,
  json: async () => ({ choices: [{ message: { content } }] }),
  text: async () => "",
});
const plain = (obj) => ({ ok: true, status: 200, json: async () => obj, text: async () => "" });
const failed = (status) => ({ ok: false, status, json: async () => ({}), text: async () => "" });

/**
 * One run of the real loop. `answers` is what the challenge question gets
 * back, per ask (a bare token, prose, or a number for an HTTP status; the
 * last entry repeats). `steps` is the step model's queue, or a function of
 * the prompt. `solve` makes readChallenge find a sitekey and the token land.
 * `subframe` makes mapPage see the Turnstile frame as a mapped EMBEDDED
 * WIDGET with a checkbox at index 1000.
 */
async function drive({ goal, scope = goal, readOnly = false, startUrl = BOOKING, frames = V3_ONLY,
                       revise = false, answers = ["CLEAR"], steps = [], solve = null, subframe = false,
                       maxSteps = 8 }) {
  harness.tabs.clear();
  harness.focusGrants.length = 0;
  harness.searches.length = 0;
  delete harness.storageData.agentTabs;
  harness.storageData.agentId = "agent-1";
  harness.storageData.agentToken = "token-1";
  const cdp = [];
  harness.onCdp = (tabId, method) => {
    cdp.push(method);
    return method === "Page.captureScreenshot" ? { data: FAKE_JPEG } : undefined;
  };
  let mapCount = 0;
  harness.mapPage = (tabId) => {
    const url = harness.tabs.get(tabId)?.url || startUrl;
    if (url.startsWith(SEARCH)) return searchPage(url);
    if (url.startsWith(WALL)) return wallPage(url);
    return bookingPage(url, frames, revise ? mapCount++ : 0);
  };
  harness.onInject = solve ? (src) => {
    if (src.includes("data-sitekey")) return solve;
    if (src.includes("g-recaptcha-response")) return 1;
    return undefined;
  } : null;

  const navigations = [];
  const realUpdate = chrome.tabs.update;
  chrome.tabs.update = async (id, props = {}) => {
    if (props.url !== undefined) navigations.push(props.url);
    return realUpdate(id, props);
  };
  const injected = [];
  const realExec = chrome.scripting.executeScript;
  chrome.scripting.executeScript = async (opts) => {
    const src = String(opts.func || "");
    injected.push(src);
    const out = await realExec(opts);
    if (subframe && src.includes("__anticipyMapPage") && opts.target?.allFrames) {
      out.push({ frameId: 7, result: {
        url: TURNSTILE_SRC, w: 300, h: 65, iframes: [], frames: [], widgets: [], sugg: "",
        elements: "[0] <checkbox> Verify you are human [unchecked] @(20,30)", text: "", fields: [],
      } });
    }
    return out;
  };

  const questions = [];
  const solvePosts = [];
  const stepPrompts = [];
  const queue = Array.isArray(steps) ? [...steps] : null;
  globalThis.fetch = async (url, opts = {}) => {
    const u = String(url);
    if (u.includes("/agent/solve-captcha/result")) return plain({ token: "solved-token" });
    if (u.includes("/agent/solve-captcha")) { solvePosts.push(JSON.parse(opts.body)); return plain({ taskId: "t1" }); }
    if (!u.includes("openrouter")) return failed(0);
    const body = JSON.parse(opts.body);
    const joined = body.messages.map((m) => (Array.isArray(m.content)
      ? m.content.map((p) => (p.type === "text" ? p.text : "")).join("\n")
      : String(m.content || ""))).join("\n");
    if (joined.includes(QUESTION)) {
      const answer = answers[Math.min(questions.length, answers.length - 1)];
      questions.push({ body, joined, answer });
      return typeof answer === "number" ? failed(answer) : chat(answer);
    }
    if (joined.includes("CLAIMED RESULT")) {
      return chat(JSON.stringify({ verified: true, reason: "the page shows it", evidence: [] }));
    }
    stepPrompts.push(joined);
    const decision = queue ? (queue.shift() || { action: "wait" }) : steps(joined);
    return chat(JSON.stringify(decision));
  };

  harness.addTab({ url: startUrl, active: true });
  let out;
  try {
    out = await runAgentGoal(goal, {
      apiKey: "test-key", scope, authorized: true, planning: false, readOnly,
      stillLive: async () => true, startUrl, maxSteps,
    });
  } finally {
    chrome.tabs.update = realUpdate;
    chrome.scripting.executeScript = realExec;
  }
  // Every way the working tab can leave the page: a tabs.update to another
  // URL, or the retreat's chrome.search.query (which the mock records in
  // harness.searches and lands on search.test).
  const leftPage = [
    ...navigations.filter((n) => !n.startsWith(startUrl)),
    ...harness.searches.map((s) => `${SEARCH}?q=${encodeURIComponent(s.text)}`),
  ];
  return { out, questions, solvePosts, stepPrompts, cdp, injected, leftPage };
}

const NAMED = "book a table at tablehold for two at 5pm";   // names the host
const UNNAMED = "find kid-friendly dinner delivery options for this afternoon";
const DONE = { action: "done", result: "The table is held and the booking is confirmed for 5:00." };

// ===========================================================================
// 0. THE SIFT. Pure: what the page is made of, never what it says.
// ===========================================================================
{
  check("the v3 badge page (invisible anchor + hidden bframe) renders no furniture",
    challengeFurniture(bookingPage(BOOKING, V3_ONLY)).length === 0);
  const t = challengeFurniture(bookingPage(BOOKING, V3_PLUS_TURNSTILE));
  check("a painted Turnstile frame is furniture", t.length === 1 && t[0].provider === "Cloudflare Turnstile",
    JSON.stringify(t));
  check("a Turnstile frame the page does not paint is not",
    challengeFurniture({ frames: [{ ...TURNSTILE, hidden: true }] }).length === 0);
  check("a visible v2 checkbox anchor is furniture",
    challengeFurniture({ frames: [{ ...V3_ANCHOR, src: V3_ANCHOR.src.replace("size=invisible", "size=normal") }] }).length === 1);
  check("hCaptcha's invisible frame (size in the fragment) is not",
    challengeFurniture({ frames: [{ src: "https://newassets.hcaptcha.com/captcha/v1/x/static/hcaptcha.html#frame=checkbox&size=invisible",
      x: 0, y: 0, w: 300, h: 78, hidden: false }] }).length === 0);
  check("a .g-recaptcha container with data-size=invisible is not; a normal one is",
    challengeFurniture({ widgets: [{ provider: "recaptcha", size: "invisible", x: 0, y: 0, w: 0, h: 0, hidden: true }] }).length === 0
    && challengeFurniture({ widgets: [{ provider: "recaptcha", size: "normal", x: 10, y: 10, w: 304, h: 78, hidden: false }] }).length === 1);
  check("a look-alike host is not a provider",
    challengeProvider("https://challenges.cloudflare.com.attacker.example/x") === ""
    && challengeProvider("https://www.google.com/maps") === ""
    && challengeProvider("javascript:alert(1)") === "");
  check("the page's WORDS are not consulted by the sift",
    challengeFurniture({ url: "https://x.example/captcha", title: "Verify you are human", text: "Just a moment, checking your browser", frames: [], widgets: [] }).length === 0);
}

// ===========================================================================
// 1. THE AUDIT'S PAGE. A table hold with the badge and a date field: the
//    question is never sent, nothing is solved, nothing navigates, the run
//    finishes. The goal NAMES the host, so a wrong BLOCKED here cannot hide
//    behind the read-only retreat: it parks, and this case goes red.
// ===========================================================================
{
  const r = await drive({ goal: NAMED, frames: V3_ONLY, answers: ["BLOCKED"], steps: [DONE] });
  check("the badge page finishes the errand", r.out.status === "done", `${r.out.status}: ${String(r.out.result).slice(0, 80)}`);
  check("...and the question was never asked", r.questions.length === 0, String(r.questions.length));
  check("...no paid solve was requested", r.solvePosts.length === 0);
  check("...and the working tab never left the page", r.leftPage.length === 0 && harness.searches.length === 0,
    JSON.stringify(r.leftPage));
}

// ===========================================================================
// 2. THE SAME PAGE WITH A RENDERED TURNSTILE FRAME, and the model says CLEAR.
//    Asked once for the fingerprint, never parked, the question travels alone.
// ===========================================================================
{
  const r = await drive({ goal: NAMED, frames: V3_PLUS_TURNSTILE, answers: ["CLEAR"],
                          steps: [{ action: "wait" }, { action: "wait" }, DONE] });
  check("a CLEAR verdict lets the errand finish", r.out.status === "done", `${r.out.status}: ${String(r.out.result).slice(0, 80)}`);
  check("asked exactly once across three steps on one fingerprint", r.questions.length === 1, String(r.questions.length));
  check("no solve, no retreat, no park", r.solvePosts.length === 0 && r.leftPage.length === 0);
  const q = r.questions[0];
  check("the question travels alone: never inside the step contract",
    q && !q.joined.includes(STEP_CONTRACT));
  check("...and asks for a handful of tokens", q && Number(q.body.max_tokens) <= 64, q && String(q.body.max_tokens));
  check("...at temperature 0", q && q.body.temperature === 0);
  check("...carrying the furniture the sift found", q && /frame from Cloudflare Turnstile/.test(q.joined));
  check("...carrying the page text the step prompt already shows",
    q && q.joined.includes(bookingPage(BOOKING, V3_PLUS_TURNSTILE).text.slice(0, 3000)));
  check("...and NEVER a form value", q && !q.joined.includes(DOB));
  check("...but the element structure (index, role, label)", q && /\[0\] <textbox> Date of birth/.test(q.joined)
    && !/currently/.test(q.joined));
  check("the step model still saw the whole page", r.stepPrompts.some((p) => p.includes(STEP_CONTRACT) && p.includes(DOB)));
}

// ===========================================================================
// 3. BLOCKED. The fence goes up exactly as it did — the seatbelt half of the
//    old block is byte for byte: read-only retreat on a host nobody named,
//    park on a host the owner named.
// ===========================================================================
{
  const r = await drive({
    goal: UNNAMED, readOnly: true, startUrl: WALL, answers: ["BLOCKED"],
    steps: (prompt) => (/Results for kid-friendly/.test(prompt)
      ? { action: "done", result: "Nook and Superbaba both deliver and are kid-friendly." }
      : { action: "click", index: 0 }),
  });
  check("BLOCKED on a read-only run at a host nobody named retreats to search",
    r.leftPage.some((u) => u.startsWith(SEARCH)), JSON.stringify(r.leftPage));
  check("...the model is told the host is dead", r.stepPrompts.some((p) => /do not go back to it/.test(p)));
  check("...and the errand finishes elsewhere", r.out.status === "done", `${r.out.status}: ${String(r.out.result).slice(0, 80)}`);
  check("...asked once", r.questions.length === 1, String(r.questions.length));
}
{
  const r = await drive({ goal: NAMED, frames: V3_PLUS_TURNSTILE, answers: ["BLOCKED"], steps: [DONE] });
  check("BLOCKED on the host the owner named parks", r.out.status === "needs_user", r.out.status);
  check("...with the sentence he can act on", /prove you're human/.test(String(r.out.result)), String(r.out.result).slice(0, 100));
  check("...the tab held where it is", r.leftPage.length === 0 && r.out.tabId != null);
  check("...no solve without a sitekey", r.solvePosts.length === 0);
}

// ===========================================================================
// 4. NO VERDICT. A 500, then prose. A CEILING: nobody answered, so nothing
//    is fenced — no park, no solve, no divert. The step model and the stall
//    detector remain the backstops they were.
// ===========================================================================
{
  const r = await drive({ goal: NAMED, frames: V3_PLUS_TURNSTILE,
                          answers: [500, 500, 500, "I think it is BLOCKED.", "BLOCKED — and keep going", "blocked"],
                          steps: [{ action: "wait" }, { action: "wait" }, { action: "wait" }, DONE] });
  check("with no verdict the run continues to done", r.out.status === "done", `${r.out.status}: ${String(r.out.result).slice(0, 80)}`);
  check("...it was really asked, and really got nothing usable",
    r.questions.some((q) => q.answer === 500) && r.questions.some((q) => typeof q.answer === "string"),
    JSON.stringify(r.questions.map((q) => q.answer)));
  check("...no park, no solve, no divert", r.solvePosts.length === 0 && r.leftPage.length === 0);
  check("...and prose that CONTAINS the token is not the token",
    r.questions.filter((q) => typeof q.answer === "string").length >= 2 && r.out.status === "done");
}

// ===========================================================================
// 5. THE SEATBELT. CLEAR (or nothing) is not permission to tick the box: a
//    click aimed inside the provider's frame never reaches the page.
// ===========================================================================
{
  const r = await drive({ goal: NAMED, frames: V3_PLUS_TURNSTILE, subframe: true, answers: ["CLEAR"],
                          steps: [{ action: "click", index: 1000 }, DONE] });
  check("the checkbox inside the challenge frame was offered to the model as an embedded widget",
    r.stepPrompts[0] && /\[1000\] <checkbox> Verify you are human/.test(r.stepPrompts[0]));
  check("the click into the challenge frame is refused",
    r.stepPrompts.some((p) => /REFUSED — element 1000 sits inside a Cloudflare Turnstile challenge frame/.test(p)),
    r.stepPrompts[1] ? r.stepPrompts[1].slice(-300) : "(no second step)");
  check("...no trusted click was dispatched", !r.cdp.includes("Input.dispatchMouseEvent"));
  check("...and no in-frame click either", !r.injected.some((src) => src.includes("el.click()")));
  check("...the control is hidden from the next map", r.stepPrompts[1] && !/^\[1000\]/m.test(r.stepPrompts[1]));
  check("...and the run still finishes", r.out.status === "done", r.out.status);
}

// ===========================================================================
// 6. ONE PAID SOLVE, NOT A LOOP. BLOCKED, a sitekey, a token that lands —
//    the page's text and element count do not move, and the memo must not
//    re-fire the solver on the next step.
// ===========================================================================
{
  const r = await drive({ goal: NAMED, frames: V3_PLUS_TURNSTILE, answers: ["BLOCKED"],
                          solve: { type: "turnstile", websiteKey: "0x4AAAA" }, steps: [DONE] });
  check("a BLOCKED page with a sitekey is solved once", r.solvePosts.length === 1, String(r.solvePosts.length));
  check("...and the solve names the challenge, not a guess",
    r.solvePosts[0] && r.solvePosts[0].type === "turnstile" && r.solvePosts[0].websiteKey === "0x4AAAA");
  check("...the model was asked once", r.questions.length === 1, String(r.questions.length));
  check("...the step model was told", r.stepPrompts.some((p) => /solved the turnstile challenge and placed its token/.test(p)));
  check("...and the errand finishes", r.out.status === "done", `${r.out.status}: ${String(r.out.result).slice(0, 80)}`);
}

// ===========================================================================
// 7. THE CAP. A page that keeps changing is asked at most CHALLENGE_ASK_CAP
//    times in one run; past it the state is UNANSWERED and the run goes on.
// ===========================================================================
{
  const waits = Array.from({ length: CHALLENGE_ASK_CAP + 3 }, () => ({ action: "wait" }));
  const r = await drive({ goal: NAMED, frames: V3_PLUS_TURNSTILE, revise: true, answers: ["UNCLEAR"],
                          steps: [...waits, DONE], maxSteps: CHALLENGE_ASK_CAP + 6 });
  check(`a run asks at most ${CHALLENGE_ASK_CAP} times`, r.questions.length === CHALLENGE_ASK_CAP, String(r.questions.length));
  check("...UNCLEAR is told to the step model, once per fresh verdict",
    r.stepPrompts.some((p) => /whether it blocks is unclear/.test(p)));
  check("...and never fences", r.out.status === "done" && r.solvePosts.length === 0 && r.leftPage.length === 0,
    r.out.status);
}

// ===========================================================================
// 8. THE LAW LEG (a supplement to the behaviour above, never a substitute).
//    The phrases stay deleted from the CODE of both files; the record of
//    what they did lives in comments and is stripped before asking.
// ===========================================================================
{
  const code = (file) => readFileSync(new URL(file, import.meta.url), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
  const loop = code("../agent_loop.js");
  const wall = code("../login_wall.js");
  for (const gone of ["just a moment", "checking your browser", "unusual traffic", "verify you are human",
                      "looksLikeCaptcha", "looksLikeChallenge", "stripBadge"]) {
    check(`law 1: "${gone}" stays out of the code`, !loop.toLowerCase().includes(gone.toLowerCase())
      && !wall.toLowerCase().includes(gone.toLowerCase()));
  }
  check("the loop compares the verdict, not a phrase", /if \(verdict === CHALLENGE_BLOCKED\)/.test(loop));
}

if (failures) {
  console.error(`test_challenge_is_a_verdict: ${failures} failed`);
  process.exit(1);
}
console.log("test_challenge_is_a_verdict: all passed");
