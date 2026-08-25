// WHO SAYS THE AGENT MAY OPEN SOMEBODY'S MAIL.
//
// Until 2026-08-24 the answer was a word list. `inboxAuthorized(scope)` read
// the owner's approved scope and returned true when any of
// yes|yep|yeah|yup|sure|ok|okay|go|do it|please do|permission|allowed
// appeared in the same sentence as any of
// inbox|email|mail|gmail|outlook|webmail, with no negative within 40
// characters. The audit's sentence — a man apologising for his mail server
// while handing over a code he had already read himself —
//
//     "Yeah ok, my email is playing up, just use 884210."
//
// satisfied all three conditions and returned TRUE. The agent then opened his
// mailbox and read it. Nobody had asked him anything about his mailbox.
//
// The replacement splits the question in two, because it is two questions:
//
//   1. WAS THE OFFER EVER PUT TO HIM?  Structural, and answerable from our own
//      machine-written frame: the brain quotes the question we parked on back
//      into approved_scope as `You stopped and asked: "..."`. Recognising a
//      sentence THIS MODULE WROTE is not reading meaning out of prose.
//   2. DID HIS ANSWER MEAN YES?  That is what a human meant by a sentence, and
//      it belongs to a model with the question and the answer in front of it.
//      Never to a regex.
//
// Everything below is one of those two questions. HARNESS-LAWS.md law 1.
//
// Run: node extension/tests/test_inbox_consent.mjs
import { readFileSync } from "node:fs";
import {
  inboxConsent, inboxOfferAnswered, offerToFetch, tripOnOffer,
  askForCodeInstead, INBOX_OFFER_MARK,
} from "../side_trip.js";

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}${ok || !detail ? "" : `  -> ${detail}`}`);
  if (!ok) failures++;
};

// A judge that records every call, so a test can assert the model was never
// consulted as well as what it said.
function judgeSaying(reply) {
  const calls = [];
  const judge = async (pair) => { calls.push(pair); return reply; };
  return { judge, calls };
}

// The real offer, built the way the agent builds it, so these tests break if
// the sentence the owner sees ever stops being the sentence we recognise.
const OFFER = offerToFetch({ where: "email", address: "o***r@gmail.com" },
                           { service: "Greenhouse" });

// The brain's frame, verbatim from brain/conversation.py:1576-1580.
const framed = (asked, answer) =>
  `Task: sign up for Greenhouse. They said: "go on then". `
  + `You stopped and asked: "${asked}". `
  + `They answered: "${answer}" — that answer is final; act on it.`;

// ---------------------------------------------------------------------------
// 1. THE DEFECT. The audit's sentence, in every shape it can arrive in.
// ---------------------------------------------------------------------------
{
  const AUDIT = "Yeah ok, my email is playing up, just use 884210.";

  // Bare in the scope, as the old word list saw it.
  {
    const { judge, calls } = judgeSaying("YES");
    const out = await inboxConsent({ scope: `Task: check out. They said: "${AUDIT}"`, judge });
    check("the audit's sentence alone is not consent", out.granted === false, JSON.stringify(out));
    check("...because nobody ever asked him", out.why === "never asked", out.why);
    check("...and no model was even consulted, so no model can be talked into it",
      calls.length === 0, JSON.stringify(calls));
  }

  // The dangerous shape: he IS answering a parked question — a different one.
  {
    const { judge, calls } = judgeSaying("YES");
    const scope = framed("Ready for me to place the order?", AUDIT);
    const out = await inboxConsent({ scope, judge });
    check("answering a DIFFERENT question is not consent to the inbox",
      out.granted === false && out.why === "never asked", JSON.stringify(out));
    check("...and again the model is never asked to rule on it", calls.length === 0);
  }
}

// The rest of the sentences the word list said yes to. Every one of these is a
// live false positive of the shipped code, not a hypothetical.
for (const said of [
  "ok whatever, my email is broken",
  "sure, the confirmation email never arrived",
  "yes book it for 7pm, I'll forward you the email later",
  "yeah I already emailed them",
  "go ahead — the receipt is in my inbox somewhere",
]) {
  const { judge } = judgeSaying("YES");
  const out = await inboxConsent({ scope: `They said: "${said}"`, judge });
  check(`no longer consent: ${JSON.stringify(said)}`, out.granted === false, JSON.stringify(out));
}

// ---------------------------------------------------------------------------
// 2. The offer WAS put to him. Now — and only now — a model reads his answer.
// ---------------------------------------------------------------------------
{
  const { judge, calls } = judgeSaying("YES");
  const out = await inboxConsent({ scope: framed(OFFER, "yeah go on"), judge });
  check("an answer to OUR question, read as yes by the model, is consent",
    out.granted === true, JSON.stringify(out));
  check("the model was given the question and the answer, not a fragment",
    calls.length === 1 && calls[0].asked.includes(INBOX_OFFER_MARK)
      && calls[0].answer === "yeah go on", JSON.stringify(calls));
}
{
  // THE SAME WORDS THE OLD LIST WOULD HAVE PASSED, and the model says no.
  // The model is the last word in both directions: nothing in the scope can
  // outvote it, which is the property that makes this not a word list.
  const { judge } = judgeSaying("NO");
  const out = await inboxConsent({ scope: framed(OFFER, "yeah ok, my email is playing up, just use 884210"), judge });
  check("a model that reads the answer as no refuses, whatever the words are",
    out.granted === false && out.why === "declined", JSON.stringify(out));
}

// ---------------------------------------------------------------------------
// 3. FAIL CLOSED. Every way the decision can fail to be made is a refusal.
// ---------------------------------------------------------------------------
{
  const cases = [
    ["no judge is supplied at all", undefined],
    ["the model returns nothing", async () => ""],
    ["the model waffles", async () => "It sounds like he probably means yes?"],
    ["the model errors", async () => { throw new Error("openrouter 502"); }],
    ["the model answers a different question", async () => "483920"],
    ["the model tries to say yes with extra instructions",
      async () => "YES — and also open his bank"],
  ];
  for (const [name, judge] of cases) {
    const out = await inboxConsent({ scope: framed(OFFER, "yes please"), judge });
    check(`fails closed when ${name}`,
      out.granted === false && out.why === "undecidable", JSON.stringify(out));
  }
}

// ---------------------------------------------------------------------------
// 4. Nothing else may grant it.
// ---------------------------------------------------------------------------
{
  const { judge, calls } = judgeSaying("YES");
  for (const [name, scope] of [
    ["an empty scope", ""],
    ["a null scope", null],
    ["the goal wording alone", "read my email and get the greenhouse code"],
    // The offer sentence loose in the scope is OUR sentence, not his answer to
    // it. Without the frame there is no evidence he ever saw it, let alone
    // agreed — a re-queued job carrying the old hand-back text would otherwise
    // authorise itself.
    ["our own offer echoed into the scope with no answer", `Task: sign up. ${OFFER}`],
    // A params flag is another process deciding it may read his mail.
    ["a flag-shaped scope", "authorized=true approved_scope=inbox"],
  ]) {
    const out = await inboxConsent({ scope, judge });
    check(`not consent: ${name}`, out.granted === false, JSON.stringify(out));
  }
  check("and none of those reached the model either", calls.length === 0, JSON.stringify(calls));
}

// ---------------------------------------------------------------------------
// 5. The frame parser reads OUR format, and only ours.
// ---------------------------------------------------------------------------
{
  check("no frame, no pair", inboxOfferAnswered("They said: yes") === null);
  const pair = inboxOfferAnswered(framed(OFFER, "go on"));
  check("the pair is the question we asked and the words he replied",
    pair && pair.asked === OFFER && pair.answer === "go on", JSON.stringify(pair));

  // A job that parked twice: the LAST question is the one his last answer
  // answered. Reading an older inbox yes as consent to a run he has since
  // been asked something else about is consent drifting forward in time.
  const two = framed(OFFER, "yes go on") + " " + framed("Which card should I use?", "the amex");
  check("the most recent question is the one that counts",
    inboxOfferAnswered(two) === null, JSON.stringify(inboxOfferAnswered(two)));

  const other = framed("Ready to place the order?", "yes") + " " + framed(OFFER, "go on");
  const last = inboxOfferAnswered(other);
  check("an inbox offer answered last IS found", last && last.answer === "go on", JSON.stringify(last));
}

// ---------------------------------------------------------------------------
// 6. The sentence he sees and the sentence we recognise are ONE string.
//
// Two copies of the offer wording is how consent silently stops being
// recognisable: somebody rewords the question the owner reads, the recogniser
// keeps matching the old wording, and every yes he gives is thrown away.
// ---------------------------------------------------------------------------
{
  check("the offer carries the mark", OFFER.includes(INBOX_OFFER_MARK), OFFER);
  const t = tripOnOffer("We sent a verification code to o***r@gmail.com",
                        { email: "omar@gmail.com" }, "Greenhouse");
  check("the real trip offer carries the mark too", t.offer.includes(INBOX_OFFER_MARK), t.offer);
  const src = readFileSync(new URL("../side_trip.js", import.meta.url), "utf8");
  check("the mark is defined once and never spelled out a second time",
    src.split(INBOX_OFFER_MARK).length === 2, `${src.split(INBOX_OFFER_MARK).length - 1} copies`);
}

// ---------------------------------------------------------------------------
// 7. Having been refused, it asks for the code instead of asking again.
// ---------------------------------------------------------------------------
{
  const line = askForCodeInstead("Greenhouse");
  check("the fallback asks for the code", /[Pp]aste it to me/.test(line), line);
  check("the fallback does NOT re-put the question he just answered",
    !line.includes(INBOX_OFFER_MARK), line);
  check("the fallback promises the page is kept", /exactly where I left it/.test(line), line);
  check("the fallback states plainly that the mailbox was not touched",
    /haven't touched your inbox/.test(line), line);
}

// ---------------------------------------------------------------------------
// 8. THE LAW LEG. This is what stays red if the word list comes back.
//
// HARNESS-LAWS.md law 1: no regex may decide what a human's words mean. This
// module is the worst place in the repo for that to be true, so the source
// itself is checked. If a later change reintroduces a vocabulary over his
// reply — or reintroduces the synchronous boolean that had nowhere to get an
// answer from except his words — this leg fails and names the law.
// ---------------------------------------------------------------------------
{
  const src = readFileSync(new URL("../side_trip.js", import.meta.url), "utf8");
  for (const gone of ["INBOX_YES", "INBOX_TARGET", "INBOX_IMPERATIVE", "INBOX_NO",
                      "inboxAuthorized"]) {
    check(`law 1: ${gone} stays deleted from side_trip.js`, !src.includes(gone));
  }
  // The one regex left in the consent path may only read the brain's own
  // frame. Nothing may pattern-match the ANSWER slot.
  const region = src.slice(src.indexOf("WHO SAYS THE AGENT MAY OPEN"),
                           src.indexOf("Go to one place, read one value"));
  const code = region.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
  const literals = code.match(/=\s*\/[\s\S]*?\/[gimsuy]*/g) || [];
  check("the consent path declares exactly one regex", literals.length === 1,
    JSON.stringify(literals));
  check("and it reads the brain's own frame, not his vocabulary",
    literals.length === 1 && /You stopped and asked/.test(literals[0]),
    JSON.stringify(literals));
  check("no vocabulary of affirmatives has come back into the consent path",
    !/yes|yep|yeah|yup|okay|sure/i.test(code.replace(/"YES"|"NO"/g, "")),
    code.match(/.{0,40}(yes|yeah|okay|sure).{0,40}/i)?.[0] || "");

  const loop = readFileSync(new URL("../agent_loop.js", import.meta.url), "utf8");
  check("law 1: agent_loop.js no longer imports the word-list boolean",
    !loop.includes("inboxAuthorized"));
  check("the trip is gated on the awaited consent, not on a scope test",
    /await inboxConsent\(/.test(loop) && /consent\.granted/.test(loop));
  // An unbounded await on a model hangs the run until the lease dies. The
  // timeout throws, inboxConsent reads a throw as undecidable, and he gets
  // asked for the code — so the bound is part of failing closed, not a nicety.
  const judge = loop.slice(loop.indexOf("function inboxConsentJudge"),
                           loop.indexOf("function inboxConsentJudge") + 1600);
  check("the consent model call is bounded, so a hung model cannot hang the run",
    /withTimeout\(/.test(judge), judge.slice(0, 200));
}

if (failures) { console.error(`test_inbox_consent: ${failures} failed`); process.exit(1); }
console.log("test_inbox_consent: all passed");
