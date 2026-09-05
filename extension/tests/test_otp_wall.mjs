// The verification-code wall was this product's most expensive dead end.
//
// The system prompt promises, in so many words, "want me to open your inbox and
// read it". side_trip.js implements exactly that in 358 careful lines — and was
// imported by nothing but its own test, and was not even listed in the shipped
// zip. So every signup, verification and password reset walked up to the code
// field, correctly refused to invent a code, and then burned the rest of its step
// budget to a stall that reported "got nowhere". An offer that cannot be kept is
// worse than no offer at all.
//
// Run: node extension/tests/test_otp_wall.mjs
import assert from "node:assert/strict";
import { installChrome } from "./chrome_mock.mjs";
import {
  inboxConsent, mintOfferRef, offerToFetch, stampOffer, tripOnOffer,
} from "../side_trip.js";

let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}`);
  if (!ok) failures++;
};

// ------------------------------------- 1. who may open somebody else's mail
// Only that somebody, answering the question we actually put to him, read by a
// model. Never a params flag ("another process decided I may read your inbox"
// is a sentence this product cannot afford to be true), and — since
// 2026-08-24 — never a word list either. `inboxAuthorized` used to match an
// affirmative vocabulary against a mailbox vocabulary, and on
// "Yeah ok, my email is playing up, just use 884210." it returned true and the
// agent read the man's mail. Consent from keyword proximity is not consent.
//
// test_inbox_consent.mjs owns that boundary in full; a second copy of it here
// is a second copy to drift. What this file checks is the property the two
// behavioural sections below stand on.
// STAMPED, because the sentence alone is not evidence the question was ours:
// the step model is instructed to compose questions of this shape and its
// prose reaches `job.result` unfiltered. The ref minted at hand-back is what
// separates our offer from a sentence anyone can write — §3c drives that.
const REF = mintOfferRef();
const OFFER = stampOffer(
  offerToFetch({ where: "email", address: "o***r@gmail.com" }, { service: "shop" }), REF);
const ANSWERED = (answer) =>
  `You stopped and asked: "${OFFER}". They answered: "${answer}" — that answer is final; act on it.`;
const ALWAYS_YES = async () => "YES";
{
  check("a scope with no parked question never authorises a mailbox read",
    !(await inboxConsent({ scope: "sign me up for the shop account", offerRef: REF, judge: ALWAYS_YES })).granted);
  check("...not even one worded the way the old word list wanted",
    !(await inboxConsent({
      scope: 'They said: "yeah ok, my email is playing up, just use 884210"',
      offerRef: REF, judge: ALWAYS_YES,
    })).granted);
  check("an answer to OUR offer, read as agreement, does authorise it",
    (await inboxConsent({ scope: ANSWERED("yes, go on"), offerRef: REF, judge: ALWAYS_YES })).granted);
  check("and with no model to read that same answer, it fails closed",
    !(await inboxConsent({ scope: ANSWERED("yes, go on"), offerRef: REF })).granted);
  check("...and with no ref, the same sentence and the same yes authorise nothing",
    !(await inboxConsent({ scope: ANSWERED("yes, go on"), judge: ALWAYS_YES })).granted);
}

// --------------------------------------------- 2. what the offer actually says
// `tripOnOffer` is synchronous over the verdict a model gave (`whereCodeWent`,
// Audit #78); the page's wording never reaches it.
{
  const owner = { email: "omar@gmail.com" };
  const emailed = tripOnOffer({ state: "email", address: null }, owner, "Anker");
  check("an emailed code produces an offer and somewhere to go",
    !!emailed && !!emailed.url && /Want me to go and read it/.test(emailed.offer));
  check("the destination comes from HIS address, never the errand",
    emailed.url.includes("mail.google.com"));

  // His phone is not ours to read, and it is already the channel we text him on.
  const texted = tripOnOffer({ state: "phone", address: null }, owner, "Anker");
  check("a texted code asks him for it and offers no trip",
    !!texted && texted.url === null && /Send it to me/.test(texted.offer));


  // A masked address is not an address: the plain-address pattern happily
  // matches the tail of "o***r@gmail.com" and would send a trip to a fragment.
  const masked = tripOnOffer({ state: "email", address: "o***r@outlook.com" }, { email: "omar@gmail.com" }, "X");
  check("a masked address falls back to the address HE gave us",
    !!masked && masked.url.includes("mail.google.com"));

  check("a page with no code notice offers nothing",
    tripOnOffer({ state: "none", address: null }, owner, "X") === null);

  const unknownHost = tripOnOffer({ state: "email", address: "me@my-own-company.example" },
                                  { email: "me@my-own-company.example" }, "X");
  check("an inbox we cannot locate asks WHERE instead of guessing",
    !!unknownHost && unknownHost.url === null && /tell me where/.test(unknownHost.offer));
}

// ------------------------ 3. BEHAVIOURAL: the wall, unauthorised -> it ASKS
{
  const harness = installChrome();
  const { runAgentGoal } = await import("../agent_loop.js");
  harness.tabs.clear();
  harness.mapPage = (tabId) => ({
    url: harness.tabs.get(tabId)?.url || "https://shop.example.com/verify",
    title: "Verify your email",
    elements: '[0] <textbox> Verification code (type="text" name="code")',
    text: "We just emailed a 6-digit verification code to your email. Enter it below.",
    fields: [{ index: 0, label: "Verification code", value: "" }],
  });
  harness.addTab({ url: "https://news.site/read", active: true });
  // The shape of the field the agent is about to type into. Without this the
  // injected read returns null (what the real API gives for a vanished frame),
  // unquotedCode sees no attrs, and the code wall this suite is about never
  // triggers at all — the test would pass by never reaching the thing it tests.
  harness.onInject = (src) => (src.includes("readDeclaredKind")
    ? { type: "text", autocomplete: "one-time-code", attrs: "code verification code" }
    : undefined);

  const scripted = (actions) => {
    const a = [...actions];
    globalThis.fetch = async (url, opts = {}) => {
      if (!String(url).includes("openrouter")) {
        return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
      }
      const body = JSON.parse(opts.body);
      const joined = body.messages.map((m) => (Array.isArray(m.content)
        ? m.content.map((p) => (p.type === "text" ? p.text : "")).join("\n")
        : String(m.content || ""))).join("\n");
      let content;
      if (/You plan a task/.test(joined)) {
        content = JSON.stringify({ start_url: "https://shop.example.com/verify", why: "the site", steps: [], unfamiliar: false });
      } else if (/You audit a browser agent's claim/.test(joined)) {
        content = JSON.stringify({ verified: true });
      } else if (/ONE page from a person's mailbox/.test(joined)) {
        // The code judge (Audit #79): the value it names must be on the page.
        content = "483920";
      } else if (/JUST BEEN SENT to this person/.test(joined)) {
        // The code-sent judge (Audit #78), answered from the page it was
        // shown — never a scripted step. A stub may pattern-match a fixture.
        const page = (joined.match(/<PAGE [^>]+>\n([\s\S]*?)\n<\/PAGE /) || [])[1] || "";
        content = /SMS|phone/i.test(page) ? "PHONE" : (/e-?mail|@/i.test(page) ? "EMAIL" : "NONE");
      } else {
        content = JSON.stringify(a.shift() || { action: "wait" });
      }
      return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content } }] }), text: async () => "" };
    };
  };

  // The model tries to type a code nobody gave it. unquotedCode refuses — and
  // now, instead of looping to a stall, the run ASKS.
  scripted([{ action: "type", index: 0, text: "123456" }]);
  const asked = await runAgentGoal("finish signing up for the shop account", {
    apiKey: "test-key",
    scope: "sign me up for the shop account",
    ownerProfile: { email: "omar@gmail.com", first_name: "Omar" },
    authorized: true,
    planning: true,
    stillLive: async () => true,
  });
  check("an unauthorised code wall hands back instead of stalling",
    asked.status === "needs_user");
  check("...and the hand-back is the CONCRETE offer, not a shrug",
    /Want me to go and read it/.test(String(asked.result)));
  check("...and it keeps the tab, so the session and the filled form survive",
    typeof asked.tabId === "number");
  check("the hand-back is not the old 'got nowhere' stall",
    !/without getting anywhere|got nowhere/i.test(String(asked.result)));
  check("the offer he is put carries a ref, and the run reports it",
    /\[ref [0-9a-f]{32}\]$/.test(String(asked.result).trim())
      && String(asked.result).includes(`[ref ${asked.offerRef}]`), String(asked.result));

  // A CODE THAT WENT TO HIS PHONE IS NOT A CONSENT OFFER. `tripOnOffer`
  // produces a sentence here too, but it has `url: null` and no consent path
  // ever reads it — so stamping it would put a reference number on a message
  // that just asks him to paste a code, and leave a live ref in params with no
  // question pending.
  {
    const wasMap = harness.mapPage;
    harness.mapPage = (tabId) => ({
      url: harness.tabs.get(tabId)?.url || "https://shop.example.com/verify",
      title: "Verify", elements: '[0] <textbox> Code (type="text" name="code")',
      text: "We sent a code by SMS to your phone. Enter it below.",
      fields: [{ index: 0, label: "Code", value: "" }],
    });
    scripted([{ action: "type", index: 0, text: "123456" }]);
    const texted = await runAgentGoal("finish signing up for the shop account", {
      apiKey: "test-key", scope: "sign me up for the shop account",
      ownerProfile: { email: "omar@gmail.com", first_name: "Omar" },
      authorized: true, planning: true, stillLive: async () => true,
    });
    harness.mapPage = wasMap;
    check("a code that went to his phone asks him for it, with no ref on it",
      texted.status === "needs_user" && /Send it to me/.test(String(texted.result))
        && !String(texted.result).includes("[ref"), String(texted.result));
    check("...and leaves no live ref in params either",
      !texted.offerRef, String(texted.offerRef));
  }

  // ------------------ 3b. THE DEFECT, END TO END, THROUGH THE WHOLE LOOP
  //
  // The audit's sentence, carried in the approved scope exactly as it would
  // arrive: a man approving a checkout, apologising for his mail server and
  // handing over a code he read himself.
  //
  //     "Yeah ok, my email is playing up, just use 884210."
  //
  // Until 2026-08-24 this opened his mailbox. It satisfied the affirmative
  // vocabulary ("yeah", "ok"), it satisfied the mailbox vocabulary ("email"),
  // no negative sat within 40 characters, so `inboxAuthorized` returned true
  // and the run navigated a fresh tab to mail.google.com and read it.
  //
  // Checked here at the level that matters — TABS, not return values. A unit
  // test on the consent function proves the function; this proves that no
  // other path in the loop reaches his mail.
  {
    const opened = [];
    const realCreate = chrome.tabs.create.bind(chrome.tabs);
    chrome.tabs.create = async (props) => { opened.push(String(props?.url || "")); return realCreate(props); };
    let judged = 0;
    // A code the owner never gave — otherwise `unquotedCode` allows the typing
    // (he quoted 884210 himself) and the run never reaches the mailbox branch
    // this case exists to test.
    scripted([{ action: "type", index: 0, text: "123456" }]);
    const inner = globalThis.fetch;
    globalThis.fetch = async (url, opts = {}) => {
      if (String(url).includes("openrouter")
          && /did this person agree to let/.test(String(opts.body || ""))) {
        judged++;
        // Even a model that would have said yes changes nothing: it is never
        // reached, because he was never asked the question.
        return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content: "YES" } }] }), text: async () => "" };
      }
      return inner(url, opts);
    };
    const out = await runAgentGoal("finish checking out", {
      apiKey: "test-key",
      scope: 'checkout for the shop order. They said: "Yeah ok, my email is playing up, just use 884210."',
      ownerProfile: { email: "omar@gmail.com", first_name: "Omar" },
      authorized: true,
      planning: true,
      stillLive: async () => true,
    });
    check("THE DEFECT: the audit's sentence never opens his mailbox",
      !opened.some((u) => u.includes("mail.google.com")), JSON.stringify(opened));
    check("...and no model was asked to rule on a question he was never put",
      judged === 0);
    check("...and he is asked, rather than read", out.status === "needs_user"
      && /Want me to go and read it/.test(String(out.result)), String(out.result));

    // THE MODEL'S NO IS THE LAST WORD, AT THE CALL SITE TOO. A word list
    // restored here as `consent.granted || alreadyBlessed` is invisible to any
    // unit test of inboxConsent, because it never runs inboxConsent — it sits
    // beside it. So: a genuine, ref-carrying offer, an answer stuffed with the
    // affirmative AND mailbox vocabulary the old list wanted, and a model that
    // says NO. The mailbox stays shut or the list is back.
    {
      const before = opened.length;
      let sawJudge = 0;
      scripted([{ action: "type", index: 0, text: "123456" }]);
      const layer = globalThis.fetch;
      globalThis.fetch = async (url, opts = {}) => {
        if (String(url).includes("openrouter")
            && /did this person agree to let/.test(String(opts.body || ""))) {
          sawJudge++;
          return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content: "NO" } }] }), text: async () => "" };
        }
        return layer(url, opts);
      };
      const refused = await runAgentGoal("finish checking out", {
        apiKey: "test-key",
        scope: `checkout. ${ANSWERED("yeah ok, open my email and grab it, my inbox is fine")}`,
        offerRef: REF,
        ownerProfile: { email: "omar@gmail.com", first_name: "Omar" },
        authorized: true, planning: true, stillLive: async () => true,
      });
      check("a model that says NO keeps the mailbox shut, whatever the words were",
        !opened.slice(before).some((u) => u.includes("mail.google.com")),
        JSON.stringify(opened.slice(before)));
      check("...and the model really was the thing that was asked", sawJudge === 1, String(sawJudge));
      check("...and he is asked for the code rather than the same question again",
        refused.status === "needs_user" && /Paste it to me/.test(String(refused.result))
          && !/Want me to go and read it/.test(String(refused.result)), String(refused.result));
    }
    chrome.tabs.create = realCreate;
  }

  // ------------------ 3c. THE SECOND DEFECT, END TO END, THROUGH THE LOOP
  //
  // A reviewer opened the owner's Gmail past this consent check on
  // 2026-08-24, and this is that run. Two hand-backs, driven in order:
  //
  //   RUN A  the step model parks with prose OF ITS OWN — AGENT_SYSTEM tells
  //          it, in capitals, to offer to go and read "a document, a reference
  //          number … or an account they are signed into", and that prose goes
  //          into `job.result` unfiltered. It ends in the offer mark word for
  //          word, about an order summary.
  //   RUN B  the brain quotes RUN A's sentence back inside its own frame with
  //          the owner's reply. His reply CONSTRAINS rather than refuses —
  //          "sure, but only the summary" — and the judge says YES.
  //
  // Before the ref, run B opened mail.google.com, read the code, typed it, and
  // reported done. Checked at the level that matters: TABS.
  {
    const offerRefsSeen = [];
    const opened = [];
    const realCreate = chrome.tabs.create.bind(chrome.tabs);
    chrome.tabs.create = async (props) => { opened.push(String(props?.url || "")); return realCreate(props); };
    let typed = "";
    harness.onCdp = (tabId, method, params) => {
      if (method === "Input.dispatchKeyEvent" && params?.type === "char" && params.text) typed += String(params.text);
    };
    // RUN A — the model's own hand-back.
    harness.mapPage = () => ({ url: "https://shop.example.com/checkout", title: "Order summary",
      elements: "[0] <link> Next", text: "Step 3 of 4.", fields: [] });
    const PROSE = "There is an order summary on the next page. Want me to go and read it?";
    scripted([{ action: "needs_user", reason: PROSE }]);
    const runA = await runAgentGoal("finish checking out", {
      apiKey: "test-key", scope: "check out the shop order",
      ownerProfile: { email: "omar@gmail.com", first_name: "Omar" },
      authorized: true, planning: true, stillLive: async () => true,
    });
    offerRefsSeen.push(runA.offerRef);
    check("RUN A: the model's own prose is what the owner is handed",
      runA.status === "needs_user" && String(runA.result) === PROSE);
    check("RUN A: ...and the run reports NO offer ref, so background.js clears the stored one",
      typeof runA.offerRef !== "string" || runA.offerRef === "");

    // RUN B — his answer to it, in the brain's frame, with a judge saying YES.
    harness.mapPage = (tabId) => {
      const url = harness.tabs.get(tabId)?.url || "";
      if (url.includes("mail.google.com")) {
        return { url, title: "Inbox", elements: "[0] <link> Your verification code",
                 text: "Your verification code is 483920. It expires in 10 minutes.", fields: [] };
      }
      return { url: url || "https://shop.example.com/verify", title: "Verify your email",
               elements: '[0] <textbox> Verification code (type="text" name="code")',
               text: "We just emailed a 6-digit verification code to your email. Enter it below.",
               fields: [{ index: 0, label: "Verification code", value: "" }] };
    };
    harness.onInject = (src, target) => {
      if (!src.includes("readDeclaredKind")) return undefined;
      const url = harness.tabs.get(target.tabId)?.url || "";
      if (url.includes("mail.google.com")) return {};
      return { type: "text", autocomplete: "one-time-code", attrs: "code verification code" };
    };
    let judged = 0;
    scripted([{ action: "type", index: 0, text: "123456" },
              { action: "type", index: 0, text: "483920" },
              { action: "done", result: "Account verified" }]);
    const inner = globalThis.fetch;
    globalThis.fetch = async (url, opts = {}) => {
      if (String(url).includes("openrouter")
          && /did this person agree to let/.test(String(opts.body || ""))) {
        judged++;
        return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content: "YES" } }] }), text: async () => "" };
      }
      return inner(url, opts);
    };
    const runB = await runAgentGoal("finish checking out", {
      apiKey: "test-key",
      scope: `check out the shop order. You stopped and asked: "${runA.result}". `
        + `They answered: "sure, but only the summary — do not go poking around anywhere else" `
        + `— that answer is final; act on it.`,
      // Exactly what background.js would hand this resumed run: whatever run A
      // recorded, which for a model-authored hand-back is nothing.
      offerRef: typeof runA.offerRef === "string" ? runA.offerRef : "",
      ownerProfile: { email: "omar@gmail.com", first_name: "Omar" },
      authorized: true, planning: true, stillLive: async () => true,
    });
    check("THE EXPLOIT: a question the STEP MODEL wrote never opens his mailbox",
      !opened.some((u) => u.includes("mail.google.com")), JSON.stringify(opened));
    check("...and the code was never read or typed", !typed.includes("483920"), typed);
    check("...and no model was asked to rule on a question this module never put",
      judged === 0, String(judged));
    check("...and he is put OUR question instead, carrying a ref of its own",
      runB.status === "needs_user" && /Want me to go and read it/.test(String(runB.result))
        && /\[ref [0-9a-f]{32}\]$/.test(String(runB.result).trim()), String(runB.result));
    check("...a fresh one, not the one the model's sentence could have quoted",
      typeof runB.offerRef === "string" && /^[0-9a-f]{32}$/.test(runB.offerRef)
        && !offerRefsSeen.includes(runB.offerRef), String(runB.offerRef));
    chrome.tabs.create = realCreate;
    harness.onCdp = null;
  }

  // ------------------ 3d. THE ROUND TRIP. Park, then resume with exactly what
  // background.js would have carried across.
  //
  // The refusals are only half the property. The other half is that the ref
  // SURVIVES the park — run A puts our offer and reports its ref,
  // `handBackParamsPatch` records it as `params._offer_ref`, the brain quotes
  // the sentence back with his answer, and run B, handed that ref, does the
  // trip. Without this leg a door that mints no ref at all reads as "safe":
  // every refusal check would still pass and the feature would be dead.
  {
    const opened = [];
    const realCreate = chrome.tabs.create.bind(chrome.tabs);
    chrome.tabs.create = async (props) => { opened.push(String(props?.url || "")); return realCreate(props); };
    let typed = "";
    harness.onCdp = (tabId, method, params) => {
      if (method === "Input.dispatchKeyEvent" && params?.type === "char" && params.text) typed += String(params.text);
    };
    harness.mapPage = (tabId) => {
      const url = harness.tabs.get(tabId)?.url || "";
      if (url.includes("mail.google.com")) {
        return { url, title: "Inbox", elements: "[0] <link> Your verification code",
                 text: "Your verification code is 483920. It expires in 10 minutes.", fields: [] };
      }
      return { url: url || "https://shop.example.com/verify", title: "Verify your email",
               elements: '[0] <textbox> Verification code (type="text" name="code")',
               text: "We just emailed a 6-digit verification code to your email. Enter it below.",
               fields: [{ index: 0, label: "Verification code", value: "" }] };
    };
    harness.onInject = (src, target) => {
      if (!src.includes("readDeclaredKind")) return undefined;
      const url = harness.tabs.get(target.tabId)?.url || "";
      if (url.includes("mail.google.com")) return {};
      return { type: "text", autocomplete: "one-time-code", attrs: "code verification code" };
    };

    // RUN A — the wall, nobody asked yet. This is where the ref is minted.
    scripted([{ action: "type", index: 0, text: "123456" }]);
    const parked = await runAgentGoal("finish signing up for the shop account", {
      apiKey: "test-key", scope: "sign me up for the shop account",
      ownerProfile: { email: "omar@gmail.com", first_name: "Omar" },
      authorized: true, planning: true, stillLive: async () => true,
    });
    check("RUN A: the park is our offer, and it carries a ref",
      parked.status === "needs_user" && /Want me to go and read it/.test(String(parked.result))
        && /\[ref [0-9a-f]{32}\]$/.test(String(parked.result).trim()), String(parked.result));
    check("RUN A: ...and the run reports that same ref for background.js to record",
      typeof parked.offerRef === "string" && /^[0-9a-f]{32}$/.test(parked.offerRef)
        && String(parked.result).includes(`[ref ${parked.offerRef}]`), String(parked.offerRef));

    // RUN B — his yes, in the brain's frame, with the ref carried in params.
    let judged = 0;
    scripted([{ action: "type", index: 0, text: "483920" },
              { action: "type", index: 0, text: "483920" },
              { action: "done", result: "Account verified" }]);
    const inner = globalThis.fetch;
    globalThis.fetch = async (url, opts = {}) => {
      if (String(url).includes("openrouter")
          && /did this person agree to let/.test(String(opts.body || ""))) {
        judged++;
        return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content: "YES" } }] }), text: async () => "" };
      }
      return inner(url, opts);
    };
    const resumed = await runAgentGoal("finish signing up for the shop account", {
      apiKey: "test-key",
      scope: `sign me up for the shop account. You stopped and asked: "${parked.result}". `
        + `They answered: "yeah go on" — that answer is final; act on it.`,
      offerRef: parked.offerRef,
      ownerProfile: { email: "omar@gmail.com", first_name: "Omar" },
      authorized: true, planning: true, stillLive: async () => true,
    });
    check("RUN B: the ref survives the park, so his yes actually opens the mailbox",
      opened.some((u) => u.includes("mail.google.com")), JSON.stringify(opened));
    check("RUN B: ...the code comes back and is typed", typed.includes("483920"), typed);
    check("RUN B: ...and the errand finishes instead of parking again",
      resumed.status === "done", `${resumed.status}: ${String(resumed.result)}`);
    check("RUN B: ...on one model call, not one per step", judged === 1, String(judged));
    chrome.tabs.create = realCreate;
    harness.onCdp = null;
  }
}

// ------------------- 4. BEHAVIOURAL: authorised -> it GOES, READS, CONTINUES
{
  const harness = installChrome();
  const { runAgentGoal } = await import("../agent_loop.js");
  harness.tabs.clear();
  const opened = [];
  const realCreate = chrome.tabs.create.bind(chrome.tabs);
  chrome.tabs.create = async (props) => { opened.push(String(props?.url || "")); return realCreate(props); };
  let typed = "";
  harness.onCdp = (tabId, method, params) => {
    // trustedType sends one `char` key event per character — rawKeyDown does not
    // insert text, and sending text on both once produced "TToorroonnttoo".
    // Accumulate the char events; anything else is not typing.
    if (method === "Input.dispatchKeyEvent" && params?.type === "char" && params.text) {
      typed += String(params.text);
    }
  };
  harness.mapPage = (tabId) => {
    const url = harness.tabs.get(tabId)?.url || "";
    if (url.includes("mail.google.com")) {
      return { url, title: "Inbox", elements: "[0] <link> Your verification code",
               text: "Your verification code is 483920. It expires in 10 minutes.", fields: [] };
    }
    return { url: url || "https://shop.example.com/verify", title: "Verify your email",
             elements: '[0] <textbox> Verification code (type="text" name="code")',
             text: "We just emailed a 6-digit verification code to your email. Enter it below.",
             fields: [{ index: 0, label: "Verification code", value: "" }] };
  };
  harness.addTab({ url: "https://news.site/read", active: true });
  // Only the verification page has a code field; the inbox has none, so the
  // shape is keyed on the tab's url. A blanket answer would make the inbox look
  // like a code field and the trip would refuse its own destination.
  harness.onInject = (src, target) => {
    if (!src.includes("readDeclaredKind")) return undefined;
    const url = harness.tabs.get(target.tabId)?.url || "";
    if (url.includes("mail.google.com")) return {};
    return { type: "text", autocomplete: "one-time-code", attrs: "code verification code" };
  };

  const a = [
    { action: "type", index: 0, text: "483920" },   // refused first time (no code known)
    { action: "type", index: 0, text: "483920" },   // allowed after the trip
    { action: "done", result: "Account verified" },
  ];
  const seen = [];
  const consentAsked = [];
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
      content = JSON.stringify({ start_url: "https://shop.example.com/verify", why: "site", steps: [], unfamiliar: false });
    } else if (/You audit a browser agent's claim/.test(joined)) {
      content = JSON.stringify({ verified: true });
    } else if (/ONE page from a person's mailbox/.test(joined)) {
      content = "483920";
    } else if (/JUST BEEN SENT to this person/.test(joined)) {
      const page = (joined.match(/<PAGE [^>]+>\n([\s\S]*?)\n<\/PAGE /) || [])[1] || "";
      content = /SMS|phone/i.test(page) ? "PHONE" : (/e-?mail|@/i.test(page) ? "EMAIL" : "NONE");
    } else if (/did this person agree to let/.test(joined)) {
      // The consent judge. It is asked the question we parked on and his reply,
      // and answers in one token. This is the ONLY thing in the run that may
      // conclude his mailbox may be opened.
      consentAsked.push(joined);
      content = "YES";
    } else {
      seen.push(all[all.length - 1]);
      content = JSON.stringify(a.shift() || { action: "wait" });
    }
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content } }] }), text: async () => "" };
  };

  const out = await runAgentGoal("finish signing up for the shop account", {
    apiKey: "test-key",
    // HIS OWN WORDS, ANSWERING OUR OWN QUESTION, are the authorization — in the
    // frame the brain actually writes (brain/conversation.py:1576-1580) when he
    // replies to a parked run. A loose "yes, go read my email" floating in the
    // scope is NOT this: nothing in it says he was ever asked.
    scope: `sign me up for the shop account. ${ANSWERED("yeah go on")}`,
    // What background.js reads out of `params._offer_ref` and hands to the run:
    // the ref minted when this job parked on our offer.
    offerRef: REF,
    ownerProfile: { email: "omar@gmail.com", first_name: "Omar" },
    authorized: true,
    planning: true,
    stillLive: async () => true,
  });

  check("an authorised run finishes instead of parking", out.status === "done");
  check("a model — not a word list — was what said his mailbox could be opened",
    consentAsked.length === 1 && consentAsked[0].includes("yeah go on"));
  check("the agent actually went to HIS inbox",
    opened.some((u) => u.includes("mail.google.com")));
  check("the working tab was never navigated away — a separate tab made the trip",
    opened.filter((u) => u.includes("mail.google.com")).length === 1);
  check("the code it read became a fact the model can see",
    seen.some((prompt) => prompt.includes("verification_code: 483920")));
  check("the code was actually typed into the field", typed.includes("483920"));
}

// ------------------------------------------- 5. the code never enters a trace
{
  // history is what gets written to the job's `trace` on the backend. A code in
  // a log is a code that outlived its minute.
  const { readFileSync } = await import("node:fs");
  const loop = readFileSync(new URL("../agent_loop.js", import.meta.url), "utf8");
  // The window has to reach the end of the wall's own branch. It was 3000
  // characters and the consent rewrite pushed the hand-back past it, which made
  // this leg red for the wrong reason — a source check that measures a byte
  // offset instead of the property it names.
  const wall = loop.slice(loop.indexOf("THE OTP WALL"), loop.indexOf("THE OTP WALL") + 5000);
  check("the history line records the code's LENGTH, never its value",
    /got\.value\.length/.test(wall) && !/history\.push\([^)]*\$\{got\.value\}/.test(wall));
  check("the trip is taken at most once per run", /inboxTripTaken/.test(wall));
  check("a failed trip hands back and names why, rather than looping",
    /I went to look for the code and could not read it/.test(wall));
}

if (failures) {
  console.error(`test_otp_wall: ${failures} failed`);
  process.exit(1);
}
console.log("test_otp_wall: all passed");
