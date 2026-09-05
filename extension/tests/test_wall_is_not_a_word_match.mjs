// A WALL IS WHAT A PAGE MEANS, NOT WHAT IT SAYS.
//
// Audit #70. login_wall.js decided that a page was a password wall, an SSO wall
// or a paywall with sixteen vocabulary regexes summed against a threshold
// (WALL = 4), and agent_loop parked the errand and texted the owner on the
// count. The audit's own example still landed the day this was written: a
// permit form whose sidebar read "Members only parking permits — $45 per
// year" scored MONEY_GATE ("members only") 3 + PRICE ("$45", "per year") 1 =
// 4, and the errand was abandoned as a paywall one step from done, with a
// hedge ("looks like") that was itself a regex count (SURE = 6).
//
// Now ONE question goes to a model, on its own, in four states, and the loop
// parks only on an explicit WALL. This suite drives the real loop and the real
// verdict function and watches what reaches the model, the page and the owner:
//
//   1. the four states, read off the model's own token
//   2. THE CEILING PIN — nobody answering is not a wall
//   3. the loop: WALL parks with the sentence; everything else carries on
//   4. cost: an ordinary run pays nothing; a wall is asked once per wall key
//   5. what rides into the question: structure and the errand, never a value
//   6. the sentence he reads
//   7. the golden set, for what an offline test can pin about it
//   8. the law leg: what stays red if a word list decides this again
//
// Run: node extension/tests/test_wall_is_not_a_word_match.mjs
import { readFileSync } from "node:fs";
import { installChrome } from "./chrome_mock.mjs";
import { FIXTURES } from "../../research/evals/login-wall-2026-09-05/fixtures.mjs";

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}${ok || !detail ? "" : `  -> ${String(detail).slice(0, 220)}`}`);
  if (!ok) failures++;
};

const harness = installChrome();
// A believable screenshot, so a step that "looks at the page" does not read
// as the loop refusing to look (same fake test_agent_integration uses).
const FAKE_JPEG = Buffer.from("x".repeat(9000)).toString("base64");
harness.onCdp = (tabId, method) => (method === "Page.captureScreenshot" ? { data: FAKE_JPEG } : undefined);
const { runAgentGoal } = await import("../agent_loop.js");
const {
  SENSITIVE_MARK, WALL_QUESTION, controlStructure, handBackSentence, wallKey, wallMessages,
  wallTrigger, wallVerdict,
} = await import("../login_wall.js");

const OWNER = { first_name: "Jose", email: "jose@example.test" };
const GOAL = "download my latest bill from the hydro portal";

// A login page as page_map really hands it over: the identifier the site
// pre-filled shows in the element line AND in fields, the query string carries
// his email, the password is redacted and marked.
const LOGIN = {
  url: "https://portal.hydro-example.ca/account/login?next=%2Fbills&email=jose%40example.test",
  title: "Sign in | Hydro Example",
  overlay: false,
  elements: `[0] <textbox> Email address [contains "jose@example.test"] @(10,10)\n`
    + `[1] <textbox> Password ${SENSITIVE_MARK} @(10,40)\n`
    + `[2] <button> Sign in @(10,70)`,
  text: "Sign in to My Account Email address Password Sign in",
  fields: [{ index: 0, label: "Email address", type: "email", value: "jose@example.test" }],
};

// Drive the whole loop. The fetch mock classifies prompts by a phrase in the
// system prompt, records every wall question's request body and every step
// prompt, and answers the wall question with `judge`.
async function drive({ page, judge = "NONE", reachable = true, goal = GOAL,
                       actions = [{ action: "done", result: "finished" }], maxSteps = 6 } = {}) {
  harness.tabs.clear();
  harness.addTab({ url: "https://news.site/read", active: true });
  harness.mapPage = typeof page === "function" ? page : () => ({ ...page });
  const queue = [...actions];
  const wall = [];
  const steps = [];
  globalThis.fetch = async (url, opts = {}) => {
    if (!String(url).includes("openrouter")) {
      return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
    }
    const parsed = JSON.parse(opts.body);
    const joined = parsed.messages.map((m) => (Array.isArray(m.content)
      ? m.content.map((p) => (p.type === "text" ? p.text : "[image]")).join("\n")
      : String(m.content || ""))).join("\n");
    let content;
    if (/ONE question about the page's PURPOSE/.test(joined)) {
      // One QUESTION, not one fetch: modelFetch retries a transient 500 with
      // the same body, and every distinct question carries its own one-time
      // fence, so distinct bodies are distinct questions.
      if (!wall.includes(String(opts.body))) wall.push(String(opts.body));
      if (!reachable) return { ok: false, status: 500, json: async () => ({}), text: async () => "" };
      content = typeof judge === "function" ? judge(wall.length) : judge;
    } else if (/You audit a browser agent's claim/.test(joined)) {
      content = JSON.stringify({ verified: true, evidence: ["finished"] });
    } else {
      steps.push(joined);
      content = JSON.stringify(queue.shift() || { action: "scroll", dy: 400 });
    }
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content } }] }), text: async () => "" };
  };
  const out = await runAgentGoal(goal, {
    apiKey: "k", scope: goal, ownerProfile: OWNER, authorized: true, planning: false,
    maxSteps, stillLive: async () => true,
  });
  return { out, wall, steps };
}

// ---------------------------------------------------------------------------
// 1. THE FOUR STATES, read off the model's own token
// ---------------------------------------------------------------------------
{
  const ask = (reply) => wallVerdict(LOGIN, { judge: async () => reply, goal: GOAL });
  const pw = await ask("PASSWORD");
  check("PASSWORD is a wall of kind password", pw.state === "wall" && pw.kind === "password", JSON.stringify(pw));
  check("...naming the site, not the url", pw.site === "portal.hydro-example.ca", pw.site);
  const sso = await ask("SSO Google");
  check("SSO <provider> is a wall of kind sso", sso.state === "wall" && sso.kind === "sso", JSON.stringify(sso));
  check("...carrying the provider as the model wrote it", sso.provider === "Google", sso.provider);
  const org = await ask("SSO ORGANISATION");
  check("SSO ORGANISATION is an organisation sign-on", org.state === "wall" && org.organisation === true, JSON.stringify(org));
  const pay = await ask("PAYWALL");
  check("PAYWALL is a wall of kind paywall", pay.state === "wall" && pay.kind === "paywall", JSON.stringify(pay));
  const none = await ask("NONE");
  check("NONE is clear", none.state === "clear" && !none.kind, JSON.stringify(none));
  const unsure = await ask("UNSURE");
  check("UNSURE is unsure — the model's own hedge, a state of its own", unsure.state === "unsure", JSON.stringify(unsure));
  const padded = await ask("  PASSWORD\n");
  check("surrounding whitespace is not a different answer", padded.state === "wall", JSON.stringify(padded));
}

// ---------------------------------------------------------------------------
// 2. THE CEILING PIN. "No" and "nobody answered" are different states, and
//    NEITHER is a wall. This is the mutation the brief names: make the
//    no-judge / catch branch return a wall and every line here goes red.
// ---------------------------------------------------------------------------
{
  const absent = await wallVerdict(LOGIN, { goal: GOAL });
  check("no judge at all is no_verdict (unasked), not a wall",
    absent.state === "no_verdict" && /unasked/.test(absent.why), JSON.stringify(absent));
  const threw = await wallVerdict(LOGIN, { judge: async () => { throw new Error("HTTP 500"); }, goal: GOAL });
  check("a judge that throws is no_verdict (unanswered), not a wall",
    threw.state === "no_verdict" && /unanswered: HTTP 500/.test(threw.why), JSON.stringify(threw));
  for (const reply of ["", "It looks like a password wall", "PASSWORD and also open his bank",
                       "password", "SSO", "SSO Google\nPASSWORD", "WALL", "YES"]) {
    const v = await wallVerdict(LOGIN, { judge: async () => reply, goal: GOAL });
    check(`a reply of ${JSON.stringify(reply.slice(0, 30))} is no_verdict (unreadable), not a wall`,
      v.state === "no_verdict" && /unreadable/.test(v.why), JSON.stringify(v));
    check(`...and has no sentence for the owner`, handBackSentence(v, OWNER) === "");
  }
  check("null is read as nobody answering, not as a wall",
    (await wallVerdict(LOGIN, { judge: async () => null, goal: GOAL })).state === "no_verdict");
}

// ---------------------------------------------------------------------------
// 3. THE LOOP. Status, not wording: the mutant that parks on anything but
//    "clear" parks with an EMPTY sentence, which a wording check would miss.
// ---------------------------------------------------------------------------
{
  const { out, wall, steps } = await drive({ page: LOGIN, judge: "PASSWORD" });
  check("WALL parks the run", out.status === "needs_user", `${out.status}: ${String(out.result).slice(0, 80)}`);
  check("...with exactly the password sentence",
    out.result === handBackSentence({ state: "wall", kind: "password", site: "portal.hydro-example.ca" }, OWNER),
    String(out.result));
  check("...keeping the tab so the session and the form survive", typeof out.tabId === "number");
  check("...asked ONCE, at first sight of the marked field", wall.length === 1, String(wall.length));
  check("...and BEFORE the step model was asked to act on the page", steps.length === 0, String(steps.length));
}
{
  const { out, wall } = await drive({ page: LOGIN, reachable: false });
  check("the judge answers 500: the run does NOT park — it finishes",
    out.status === "done", `${out.status}: ${String(out.result).slice(0, 80)}`);
  check("...and the unanswered question is not re-asked on the next step", wall.length === 1, String(wall.length));
}
for (const reply of ["", "It looks like a password wall", "PASSWORD and also open his bank", "password", "NONE"]) {
  const { out } = await drive({ page: LOGIN, judge: reply });
  check(`the judge says ${JSON.stringify(reply.slice(0, 28))}: the run carries on to done`,
    out.status === "done", `${out.status}: ${String(out.result).slice(0, 80)}`);
}
{
  const { out, steps } = await drive({ page: LOGIN, judge: "UNSURE" });
  check("UNSURE carries on", out.status === "done", `${out.status}: ${String(out.result).slice(0, 80)}`);
  check("...and the step model is told a separate read could not tell",
    steps.some((s) => /could not tell whether portal\.hydro-example\.ca/.test(s)), String(steps.length));
}
{
  const { out } = await drive({ page: LOGIN, judge: "SSO Google" });
  check("SSO parks with the sso sentence",
    out.status === "needs_user" && out.result === handBackSentence({ state: "wall", kind: "sso", provider: "Google", site: "portal.hydro-example.ca" }, OWNER),
    String(out.result));
  const pay = await drive({ page: LOGIN, judge: "PAYWALL" });
  check("PAYWALL parks with the paywall sentence",
    pay.out.status === "needs_user" && /paid subscription/.test(String(pay.out.result)), String(pay.out.result));
}

// ---------------------------------------------------------------------------
// 4. COST. An ordinary run pays nothing; a wall is asked once per wall key.
// ---------------------------------------------------------------------------
{
  // A plain page that moves every step: no mark, no stall, no question.
  let n = 0;
  const moving = () => ({
    url: "https://cactusclubcafe.com/happy-hour", title: "Happy hour", overlay: false,
    elements: `[0] <link> Menus @(10,10)\n[1] <button> Reserve @(30,30)`,
    text: `Happy hour runs 3-6pm daily. Section ${++n}.`, fields: [],
  });
  const { out, wall } = await drive({ page: moving, actions: [
    { action: "scroll", dy: 400 }, { action: "scroll", dy: -400 }, { action: "scroll", dy: 400 },
    { action: "done", result: "Happy hour is 3-6pm" }] });
  check("a plain page that moves every step asks no wall question at all", wall.length === 0, `${wall.length} (${out.status})`);
}
{
  // The same page, unmoved: the third identical read asks once, and once only.
  const still = {
    url: "https://cactusclubcafe.com/happy-hour", title: "Happy hour", overlay: false,
    elements: `[0] <link> Menus @(10,10)\n[1] <button> Reserve @(30,30)`,
    text: "Happy hour runs 3-6pm daily.", fields: [],
  };
  const { out, wall } = await drive({ page: still, actions: [
    { action: "scroll", dy: 400 }, { action: "scroll", dy: -400 }, { action: "scroll", dy: 400 },
    { action: "scroll", dy: -400 }, { action: "done", result: "Happy hour is 3-6pm" }] });
  check("an unmoved page is asked exactly once, at its third read", wall.length === 1, `${wall.length} (${out.status})`);
}
{
  // THE BUG THE ATTACK FOUND: a checkout with a card field, where a value
  // changes on every step. The stall fingerprint hashes values, so keying the
  // cache on it would have asked once per step. One wall key, one question.
  let n = 0;
  const checkout = () => {
    n++;
    return {
      url: "https://shop-example.com/checkout/payment?cart=9f2a&email=jose%40example.test",
      title: "Payment — Shop Example", overlay: false,
      elements: `[0] <textbox> Card number ${SENSITIVE_MARK} @(10,10)\n`
        + `[1] <textbox> Expiry ${SENSITIVE_MARK} @(10,40)\n`
        + `[2] <textbox> Name on card [contains "Jose Cruz ${n}"] @(10,70)\n`
        + `[3] <button> Pay now @(10,${100 + n})`,
      text: "Payment Card number Expiry Name on card Pay now",
      fields: [{ index: 2, label: "Name on card", type: "text", value: `Jose Cruz ${n}` }],
    };
  };
  const { out, wall } = await drive({ page: checkout, goal: "pay for the order in my bag", actions: [
    { action: "scroll", dy: 400 }, { action: "scroll", dy: -400 },
    { action: "done", result: "paid" }] });
  check("a card-marked checkout whose values change every step is asked exactly ONCE",
    wall.length === 1, `${wall.length} (${out.status})`);
  // What went into that one question — section 5 reads it.
  globalThis.__wallBody = wall[0];
}

// ---------------------------------------------------------------------------
// 5. WHAT RIDES INTO THE QUESTION. Structure and the errand; never a value.
// ---------------------------------------------------------------------------
{
  const body = String(globalThis.__wallBody || "");
  check("the question carries the card field as structure", /Card number \(sensitive field/.test(body), body.slice(0, 200));
  check("...and the errand in the owner's words", /pay for the order in my bag/.test(body));
  check("...but NOT what was typed into the form", !/Jose Cruz/.test(body) && !/Jose/.test(body));
  check("...NOT the [contains ...] annotation page_map adds", !/\[contains /.test(body));
  check("...NOT the owner's email from the query string", !/jose/.test(body) && !/example\.test/.test(body));
  check("...NOT the query string at all", !/cart=/.test(body) && !/\?/.test(JSON.parse(body).messages[1].content.split("\n").find((l) => l.startsWith("url:")) || ""));
  check("...NOT element coordinates", !/@\(/.test(body));
  check("...and no owner profile", !/first_name/.test(body));
  // 512, not the 8 the other judges use: a thinking model spends the budget on
  // reasoning before its one-line answer, and at 64 the live golden set came
  // back truncated ("PAY", "SS", empty) on 15 of 22 pages — every one a
  // no-verdict that never fences. The leg sends the same number.
  check("the question is asked at temperature 0 with room for a thinking model's reasoning",
    JSON.parse(body).temperature === 0 && JSON.parse(body).max_tokens === 512);
  // The login drive: the pre-filled identifier is in the element line, in
  // fields and in the query string, and reaches the model by none of them.
  const { wall } = await drive({ page: LOGIN, judge: "NONE" });
  check("a pre-filled identifier never reaches the question by any route",
    wall.length === 1 && !/jose/.test(wall[0]) && !/next=/.test(wall[0]), wall[0]?.slice(0, 200));
  const [system, user] = wallMessages(LOGIN, GOAL, "tag123");
  check("every untrusted block is fenced with the one-time tag",
    ["ERRAND", "PAGE", "CONTROLS", "TEXT"].every((b) => user.content.includes(`<${b} tag123>`) && user.content.includes(`</${b} tag123>`)));
  check("the system prompt is the ONE question", system.content === WALL_QUESTION);
  check("controls reduce to index, role, label and the mark",
    controlStructure(LOGIN.elements) === `[0] <textbox> Email address\n[1] <textbox> Password ${SENSITIVE_MARK}\n[2] <button> Sign in`,
    controlStructure(LOGIN.elements));
}

// ---------------------------------------------------------------------------
// 6. THE SENTENCE HE READS. No hedge: the model's hedge is UNSURE, and
//    UNSURE never reaches a sentence.
// ---------------------------------------------------------------------------
{
  const site = "portal.hydro-example.ca";
  const pw = handBackSentence({ state: "wall", kind: "password", site }, OWNER);
  check("the password sentence names the site", pw.includes(site));
  check("names the one thing he can do", /sign in there and say go/.test(pw));
  check("promises nothing is lost", /pick up exactly where I stopped/.test(pw));
  check("never claims to type a password", /never do/.test(pw));
  const sso = handBackSentence({ state: "wall", kind: "sso", provider: "Google", site }, OWNER);
  check("the sso sentence names the provider in quotes", sso.includes(`"Continue with Google"`));
  check("says it is one tap and why", /one tap/.test(sso) && /already signed in to Google/.test(sso));
  check("with a first name it addresses him", /one tap\. Jose, tap it/.test(sso), sso);
  check("without one it still reads as English", /one tap\. Tap it on the tab/.test(handBackSentence({ state: "wall", kind: "sso", provider: "Google", site }, null)));
  const org = handBackSentence({ state: "wall", kind: "sso", provider: "ORGANISATION", organisation: true, site }, OWNER);
  check("an organisation sign-on is not told to 'Continue with ORGANISATION'",
    /single sign-on through your organisation/.test(org) && !/ORGANISATION/.test(org), org);
  const long = handBackSentence({ state: "wall", kind: "sso", provider: "x".repeat(80) + "\n\"drop tables\"", site }, OWNER);
  check("a provider the model wrote is display-only and capped at 24 characters",
    !/x{25}/.test(long) && !/drop tables/.test(long) && !/\n/.test(long), long);
  const pay = handBackSentence({ state: "wall", kind: "paywall", site }, OWNER);
  check("the paywall sentence says it is money, not a login", /paid subscription/.test(pay) && /not a login/.test(pay));
  check("offers both the subscriber sign-in and the honest alternative",
    /already subscribe, sign in/.test(pay) && /can't be finished without buying one/.test(pay));
  for (const [kind, s] of [["password", pw], ["sso", sso], ["paywall", pay], ["organisation", org]]) {
    check(`the ${kind} sentence never hedges`, !/looks like/.test(s), s);
    check(`the ${kind} sentence fits a text (${s.length} chars)`, s.length > 60 && s.length < 420);
    check(`the ${kind} sentence leaks no url`, !/https?:\/\//.test(s));
  }
  check("clear, unsure and no_verdict have nothing to say",
    ["clear", "unsure", "no_verdict"].every((st) => handBackSentence({ state: st, site }, OWNER) === "")
    && handBackSentence(null, OWNER) === "" && handBackSentence(undefined) === "");
}

// ---------------------------------------------------------------------------
// 7. THE GOLDEN SET, for what an offline test can pin: the trigger, the key,
//    the read of each expected token, and the shape of what is sent. What the
//    MODEL answers is measured live by overnight/login_wall_gate.py.
// ---------------------------------------------------------------------------
{
  check("the golden set carries every kind of wall and the audit's own example",
    FIXTURES.some((f) => f.expect === "PASSWORD") && FIXTURES.some((f) => f.expect === "PAYWALL")
    && FIXTURES.some((f) => /^SSO /.test(f.expect)) && FIXTURES.some((f) => f.name === "permit_form_members_only_sidebar"),
    String(FIXTURES.length));
  for (const f of FIXTURES) {
    const marked = f.state.elements.includes(SENSITIVE_MARK);
    check(`${f.name}: the trigger is the mark (${marked ? "present" : "absent"}) or a stall, never a word`,
      wallTrigger(f.state, 0) === marked && wallTrigger(f.state, 2) === true);
    const v = await wallVerdict(f.state, { judge: async () => f.expect, goal: f.goal });
    const want = f.expect === "NONE" ? "clear" : "wall";
    check(`${f.name}: the expected token ${f.expect} reads as ${want}`, v.state === want, JSON.stringify(v));
    const [, user] = wallMessages(f.state, f.goal, "t");
    const controls = user.content.slice(user.content.indexOf("<CONTROLS t>"), user.content.indexOf("</CONTROLS t>"));
    check(`${f.name}: the controls carry no value, option, href or coordinate`,
      !/contains|currently|options:|href=|@\(|\[checked|\[unchecked/.test(controls), controls.slice(0, 160));
    check(`${f.name}: nothing from fields rides along`,
      !(f.state.fields || []).some((fl) => fl.value && String(fl.value).length > 1 && user.content.includes(String(fl.value))));
  }
  // The key that keeps a checkout from being asked once per keystroke.
  const a = wallKey({ ...LOGIN, elements: LOGIN.elements.replace("jose@example.test", "j") }, "p1");
  const b = wallKey(LOGIN, "p2");
  check("the wall key ignores values and the stall print on a marked page", a === b, `${a}\n${b}`);
  check("...and ignores the query string", wallKey({ ...LOGIN, url: "https://portal.hydro-example.ca/account/login" }, "") === b);
  check("...but a dialog opening is a different key", wallKey({ ...LOGIN, overlay: true }, "") !== b);
  check("...and a different marked control is a different key",
    wallKey({ ...LOGIN, elements: LOGIN.elements.replace("Password", "Card number") }, "") !== b);
  check("an unmarked page is keyed on its stall print", wallKey({ url: "https://a.example/x", elements: "[0] <button> Go @(1,1)", text: "go" }, "print-7") === "stall|print-7");
}

// ---------------------------------------------------------------------------
// 8. THE LAW LEG. What stays red if a word list decides this again.
// ---------------------------------------------------------------------------
{
  const src = readFileSync(new URL("../login_wall.js", import.meta.url), "utf8");
  const noComments = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
  // The prompt is the one place vocabulary legitimately lives — as teaching
  // for a model, not as a rule. Take it out before asking about the code.
  const qStart = noComments.indexOf("export const WALL_QUESTION");
  const qEnd = noComments.indexOf(";", noComments.indexOf('"content."', qStart));
  const code = noComments.slice(0, qStart) + noComments.slice(qEnd + 1);
  check("law 1: no WALL / SURE threshold survives", !/\b(?:WALL|SURE)\s*=\s*\d/.test(code));
  check("law 1: no regex is applied to the page's words, labels, title or text",
    !/\.test\(\s*(?:words|label|c\.label|s\.text|state\.text|title|s\.title|text|blob)\b/.test(code), code.match(/\.test\([^)]*\)/g)?.join(" "));
  const regexes = code.match(/\/(?:[^\/\\\n]|\\.)+\/[gimsuy]*/g) || [];
  check("law 1: no regex literal carries sign-in, password, subscription or money vocabulary",
    !regexes.some((r) => /sign|log-?in|password|subscri|member|continue|reading|[€£¥]|month|week|year|recaptcha|robot|human/i.test(r)), regexes.join("  "));
  for (const gone of ["detectsLoginWall", "canContinueAfterOwner", "looksLikeChallenge", "purposeOfPage",
                      "credentialField", "providerName", "MONEY_GATE", "AUTH_ACTION", "stripBadge"]) {
    check(`law 1: ${gone} stays deleted from the code`, !code.includes(gone));
  }
  const noStrings = code.replace(/"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`/g, '""');
  for (const brand of ["google", "apple", "microsoft", "facebook", "okta", "auth0", "github"]) {
    check(`no code names ${brand}`, !new RegExp(brand, "i").test(noStrings));
  }
  check("no hostname literal anywhere in code", !/["'][a-z0-9-]+\.(?:com|ca|org|net|io|co\.uk)["']/i.test(code));
  check("nothing switches on a hostname", !/hostname\s*===/.test(code));

  const loop = readFileSync(new URL("../agent_loop.js", import.meta.url), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
  check("the loop parks on an explicit WALL only", /verdict\.state === "wall"/.test(loop) && !/verdict\.state !== "clear"/.test(loop));
  check("the loop asks only on the structural trigger", /if \(wallTrigger\(state, stepsOnPage\)\)/.test(loop));
  check("the loop caches on the wall key, not the stall print", /wallAsked\.has\(key\)/.test(loop) && /wallKey\(state, stallPrint\)/.test(loop));
  check("the old detector is not called from the loop", !loop.includes("detectsLoginWall"));
}

if (failures) { console.error(`test_wall_is_not_a_word_match: ${failures} failed`); process.exit(1); }
console.log("test_wall_is_not_a_word_match: all passed");
