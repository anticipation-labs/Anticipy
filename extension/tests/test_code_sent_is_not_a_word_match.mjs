// WHERE THE CODE WENT IS NOT A WORD MATCH.
//
// Audit #78. Until 2026-09-05 `detectsCodeWasSent` (side_trip.js) was a
// phrasing regex and two word lists over the rendered page, and its verdict
// decided whether the run offered to open the owner's inbox at all and where
// the trip pointed. Its own comment records the live failure of that shape:
// the two commonest wordings on the exact page this feature exists for
// matched nothing until they were added by hand, and every wording not on the
// list — "a one-time passcode is on its way", any page not in English — was
// a silent null and a run burning its steps to a stall. HARNESS-LAWS.md law 1.
//
// Now a model reads the whole page (`codeSentJudge` in agent_loop.js), the
// reply is mapped in four states (`whereCodeWent`), and `tripOnOffer` is a
// FLOOR over the verdict: EMAIL offers and mints a ref; PHONE asks him to send
// it; NONE returns null (the page does not say a code was sent); UNSURE and
// no-verdict hand back with a plain ask and NO ref — never the offer, never
// the stall.
//
// These are BEHAVIOURAL: the real loop is driven through the real wall and
// what reaches the model, the owner and the job's params is observed.
//
// Run: node extension/tests/test_code_sent_is_not_a_word_match.mjs
import { installChrome } from "./chrome_mock.mjs";
import { INBOX_OFFER_MARK, whereCodeWent } from "../side_trip.js";

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}${ok || !detail ? "" : `  -> ${detail}`}`);
  if (!ok) failures++;
};

const harness = installChrome();
const { runAgentGoal, codeSentJudge, CODE_SENT_PAGE_LIMIT } = await import("../agent_loop.js");

// The wall page, worded the way the deleted regex could not read: no "sent",
// no "check your email", no "code was sent".
const ON_ITS_WAY = "A one-time passcode is on its way. Look for a message from us at o***r@gmail.com.";

function wallPage(text) {
  harness.mapPage = (tabId) => ({
    url: harness.tabs.get(tabId)?.url || "https://shop.example.com/verify",
    title: "Verify your email",
    elements: '[0] <textbox> Verification code (type="text" name="code")',
    text,
    fields: [{ index: 0, label: "Verification code", value: "" }],
  });
}
// The field's DECLARED kind is what opens the wall (unquotedCode) — structure,
// and the only gate in front of the judge.
const OTP_FIELD = { type: "text", autocomplete: "one-time-code", attrs: "code verification code" };
harness.onInject = (src) => (src.includes("readDeclaredKind") ? OTP_FIELD : undefined);
function freshTab() {
  harness.tabs.clear();
  delete harness.storageData.agentTabs;
  harness.addTab({ url: "https://news.site/read", active: true });
}

// A scripted step model plus a scripted code-sent judge. Every request the
// judge receives is recorded whole, so a case can say how often it was asked
// and exactly what it was shown; every step prompt is recorded so the trace
// line can be read back.
function scripted(actions, { judgeReply = "EMAIL" } = {}) {
  const a = [...actions];
  const judgeCalls = [];
  const stepPrompts = [];
  globalThis.fetch = async (url, opts = {}) => {
    if (!String(url).includes("openrouter")) {
      return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
    }
    const body = JSON.parse(opts.body);
    const all = body.messages.map((m) => (Array.isArray(m.content)
      ? m.content.map((p) => (p.type === "text" ? p.text : "")).join("\n")
      : String(m.content || "")));
    const joined = all.join("\n");
    let content;
    if (/You plan a task/.test(joined)) {
      content = JSON.stringify({ start_url: "https://shop.example.com/verify", why: "the site", steps: [], unfamiliar: false });
    } else if (/You audit a browser agent's claim/.test(joined)) {
      content = JSON.stringify({ verified: true });
    } else if (/JUST BEEN SENT to this person/.test(joined)) {
      judgeCalls.push(body);
      content = judgeReply;
    } else if (/did this person agree to let/.test(joined)) {
      content = "NO";
    } else {
      stepPrompts.push(all[all.length - 1]);
      content = JSON.stringify(a.shift() || { action: "wait" });
    }
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content } }] }), text: async () => "" };
  };
  return { judgeCalls, stepPrompts };
}
const run = (goal = "finish signing up for the shop account", scope = "sign me up for the shop account") =>
  runAgentGoal(goal, {
    apiKey: "test-key", scope,
    ownerProfile: { email: "omar@gmail.com", first_name: "Omar" },
    authorized: true, planning: true, stillLive: async () => true,
  });

// ---------------------------------------------------------------------------
// 1. THE DEMO-KILLER WORDING. The regex returned null here; the model reads
//    it, and the offer goes out with a live ref.
// ---------------------------------------------------------------------------
{
  freshTab();
  wallPage(ON_ITS_WAY);
  const { judgeCalls } = scripted([{ action: "type", index: 0, text: "123456" }], { judgeReply: "EMAIL" });
  const out = await run();
  check("wording the old regex could not read: the run hands back instead of stalling",
    out.status === "needs_user", `${out.status}: ${String(out.result)}`);
  check("...with the offer to read his mail", String(out.result).includes(INBOX_OFFER_MARK), String(out.result));
  check("...stamped with a live ref that the run reports for params",
    /\[ref [0-9a-f]{32}\]$/.test(String(out.result).trim())
      && typeof out.offerRef === "string" && String(out.result).includes(`[ref ${out.offerRef}]`),
    String(out.result));
  check("...and the model was asked exactly once", judgeCalls.length === 1, String(judgeCalls.length));

  // What the judge was shown. The page is DATA, in the user turn, fenced with
  // a one-time tag; the system turn is the question and the rule, never text
  // from the page.
  const body = judgeCalls[0] || { messages: [] };
  const system = String(body.messages?.[0]?.content || "");
  const user = String(body.messages?.[1]?.content || "");
  const fence = (user.match(/<PAGE ([0-9a-f]{32})>/) || [])[1] || "";
  check("the page sits inside a one-time fenced block in the USER turn",
    !!fence && user.includes(`<PAGE ${fence}>\n`) && user.includes(`\n</PAGE ${fence}>`)
      && user.indexOf(ON_ITS_WAY) > user.indexOf(`<PAGE ${fence}>`)
      && user.indexOf(ON_ITS_WAY) < user.indexOf(`</PAGE ${fence}>`), user);
  check("the system turn carries the question and the rule, and no page text",
    /JUST BEEN SENT/.test(system) && /answer UNSURE/.test(system) && !system.includes("on its way"), system);
  check("one question on its own, temperature 0",
    body.temperature === 0 && Array.isArray(body.messages) && body.messages.length === 2);
  check("the site is named to the judge — a hostname, which is structure",
    user.includes("shop.example.com"), user);
}

// ---------------------------------------------------------------------------
// 2. YES WITH ITS FACT: PHONE. His phone is not ours to read — a sentence
//    asking him to send it, with no ref, and no mailbox offer.
// ---------------------------------------------------------------------------
{
  freshTab();
  wallPage("A passcode is on its way to the number ending 4471.");
  const { judgeCalls } = scripted([{ action: "type", index: 0, text: "123456" }], { judgeReply: "PHONE" });
  const out = await run();
  check("PHONE: he is asked to send it", out.status === "needs_user" && /Send it to me/.test(String(out.result)),
    String(out.result));
  check("PHONE: no mailbox offer, no ref on the sentence, none in params",
    !String(out.result).includes(INBOX_OFFER_MARK) && !String(out.result).includes("[ref") && !out.offerRef,
    String(out.result));
  check("PHONE: asked once", judgeCalls.length === 1);
}

// ---------------------------------------------------------------------------
// 3. THE FLOOR. No verdict is no offer and no ref — and NOT the stall either.
//    The demo died of the stall; failing closed here costs one message.
// ---------------------------------------------------------------------------
for (const [name, reply] of [
  ["an empty reply", ""],
  ["prose", "I think email"],
  ["the token with a period", "EMAIL."],
  ["the model's own cannot-tell", "UNSURE"],
]) {
  freshTab();
  wallPage(ON_ITS_WAY);
  const { judgeCalls } = scripted([{ action: "type", index: 0, text: "123456" }], { judgeReply: reply });
  const out = await run();
  check(`${name}: the run still hands back — the floor is not the stall`,
    out.status === "needs_user", `${out.status}: ${String(out.result)}`);
  check(`${name}: ...with no offer to read his mail`,
    !String(out.result).includes(INBOX_OFFER_MARK), String(out.result));
  check(`${name}: ...no ref on the sentence and none in params`,
    !String(out.result).includes("[ref") && !out.offerRef, `${String(out.result)} / ${String(out.offerRef)}`);
  check(`${name}: ...and a plain ask — paste it, or say where to look`,
    /paste it/.test(String(out.result)) && /where to look/.test(String(out.result)), String(out.result));
  check(`${name}: the model was asked`, judgeCalls.length === 1, String(judgeCalls.length));
}

// ---------------------------------------------------------------------------
// 4. NONE, and the memo. The page does not say a code was sent (an
//    authenticator app): no offer, the step model carries on — and one page
//    state is judged ONCE however many times the wall is hit. The trace names
//    the verdict and the memo hit, never the page.
// ---------------------------------------------------------------------------
{
  freshTab();
  wallPage("Enter the 6-digit code from your authenticator app.");
  const { judgeCalls, stepPrompts } = scripted([
    { action: "type", index: 0, text: "123456" },
    { action: "type", index: 0, text: "654321" },
    { action: "needs_user", reason: "I need the code from your authenticator app." },
  ], { judgeReply: "NONE" });
  const out = await run();
  check("NONE: no offer about his mail, no ref",
    !String(out.result).includes(INBOX_OFFER_MARK) && !out.offerRef, String(out.result));
  check("NONE: the step model carried on and the run ended on its own hand-back",
    out.status === "needs_user" && /authenticator/.test(String(out.result)), `${out.status}: ${String(out.result)}`);
  check("one page state is judged ONCE per run, however many times the wall is hit",
    judgeCalls.length === 1, String(judgeCalls.length));
  check("the trace records the verdict and the memo hit",
    stepPrompts.some((p) => /read where the code went — none$/m.test(p))
      && stepPrompts.some((p) => /read where the code went — none \(remembered for this page\)/.test(p)),
    stepPrompts.map((p) => (p.match(/read where the code went[^\n]*/g) || []).join(" | ")).join(" || "));
  check("...and never the page text or a fence", !stepPrompts.some((p) => p.includes("<PAGE ")));
}

// ---------------------------------------------------------------------------
// 5. THE COST PIN. An ordinary field is not the wall; the model is never
//    asked where a code went on a page that has no code box.
// ---------------------------------------------------------------------------
{
  freshTab();
  harness.mapPage = (tabId) => ({
    url: harness.tabs.get(tabId)?.url || "https://shop.example.com/apply",
    title: "Apply",
    elements: '[0] <textbox> First name (type="text" name="first")',
    // Wording the old regex WOULD have matched, on a page with no code box.
    text: "Tell us about yourself. We sent you a welcome email. First name Last name Resume Submit application",
    fields: [{ index: 0, label: "First name", value: "" }],
  });
  const wasInject = harness.onInject;
  harness.onInject = (src) => (src.includes("readDeclaredKind")
    ? { type: "text", autocomplete: "given-name", attrs: "first name" } : undefined);
  const { judgeCalls, stepPrompts } = scripted([
    { action: "type", index: 0, text: "Omar" },
    { action: "needs_user", reason: "Which resume should I attach?" },
  ]);
  const out = await run("apply for the job as Omar", "apply for the job as Omar");
  harness.onInject = wasInject;
  check("an ordinary form never asks the model where a code went", judgeCalls.length === 0, String(judgeCalls.length));
  check("...and the run went on as it always did", stepPrompts.length >= 2 && out.status === "needs_user",
    `${stepPrompts.length} steps, ${out.status}`);
}

// ---------------------------------------------------------------------------
// 6. THE WIRING, through the real judge factory and a captured fetch.
// ---------------------------------------------------------------------------
{
  // (a) The judge sees the SAME text the run has. page_map caps visible text
  // at 6000 characters; a 4000-character fence would have hidden a sentence
  // sitting behind a cookie banner and a nav — the regex miss with a
  // different face.
  const lines = [];
  while (lines.join("\n").length < 5000) lines.push(`Menu item ${lines.length} · About · Careers · Cookie settings`);
  const long = `${lines.join("\n")}\n${ON_ITS_WAY}`;
  check("the fixture is a page longer than 5000 characters and under the map's cap",
    long.length > 5000 && long.length <= 6000, String(long.length));
  const sent = [];
  globalThis.fetch = async (url, opts = {}) => {
    sent.push(JSON.parse(opts.body));
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content: "EMAIL" } }] }), text: async () => "" };
  };
  const verdict = await whereCodeWent({ pageText: long, judge: codeSentJudge("test-key", "test-model", "shop.example.com") });
  check("EMAIL from the model, through the real factory, is an email verdict",
    verdict.state === "email" && /@gmail\.com$/.test(verdict.address || ""), JSON.stringify(verdict));
  const user = String(sent[0]?.messages?.[1]?.content || "");
  const system = String(sent[0]?.messages?.[0]?.content || "");
  const fence = (user.match(/<PAGE ([0-9a-f]{32})>/) || [])[1] || "";
  check("a sentence 5000 characters into the page reaches the judge, inside the fence",
    !!fence && user.includes(ON_ITS_WAY)
      && user.indexOf(ON_ITS_WAY) > user.indexOf(`<PAGE ${fence}>`)
      && user.indexOf(ON_ITS_WAY) < user.indexOf(`</PAGE ${fence}>`),
    `fence=${fence} user=${user.length} chars`);
  check("the limit is the page map's own cap, never lower", CODE_SENT_PAGE_LIMIT >= 6000, String(CODE_SENT_PAGE_LIMIT));
  check("the system turn carries no page text", !system.includes("Menu item") && !system.includes("on its way"));
  check("max_tokens is asked small; modelFetch floors it at 64 and the token compare is the real bound",
    Number(sent[0]?.max_tokens) === 64, String(sent[0]?.max_tokens));

  // (b) A HUNG MODEL CANNOT HANG THE RUN, and is read as unanswered — not
  // none. The clock is shrunk rather than the code.
  const savedTimeout = globalThis.setTimeout;
  globalThis.fetch = () => new Promise(() => { /* never */ });
  globalThis.setTimeout = (fn, ms, ...rest) => savedTimeout(fn, ms > 1000 ? 5 : ms, ...rest);
  const decided = await Promise.race([
    whereCodeWent({ pageText: ON_ITS_WAY, judge: codeSentJudge("test-key", "test-model", "shop.example.com") }),
    new Promise((resolve) => savedTimeout(() => resolve("HUNG"), 3000)),
  ]);
  globalThis.setTimeout = savedTimeout;
  check("a model that never answers is bounded, not waited on forever", decided !== "HUNG", JSON.stringify(decided));
  check("...and read as unanswered, so no offer and no ref follow",
    decided !== "HUNG" && decided.state === "unanswered", JSON.stringify(decided));

  // (c) An HTTP failure is unanswered too — never none, never email.
  globalThis.fetch = async () => ({ ok: false, status: 400, json: async () => ({}), text: async () => "" });
  const failed = await whereCodeWent({ pageText: ON_ITS_WAY, judge: codeSentJudge("test-key", "test-model", "shop.example.com") });
  check("an HTTP failure is unanswered", failed.state === "unanswered", JSON.stringify(failed));
}

if (failures) { console.error(`test_code_sent_is_not_a_word_match: ${failures} failed`); process.exit(1); }
console.log("test_code_sent_is_not_a_word_match: all passed");
