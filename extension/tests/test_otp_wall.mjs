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
import { inboxAuthorized, tripOnOffer } from "../side_trip.js";

let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}`);
  if (!ok) failures++;
};

// ------------------------------------- 1. who may open somebody else's mail
// Only that somebody, in their own words. The permission is derived from the
// approved scope and never from a params flag, because "another process decided
// I may read your inbox" is a sentence this product cannot afford to be true.
{
  // Imperatives are permission on their own — there is no separate yes to find.
  for (const yes of [
    "go read my email",
    "go and read my email",
    "yes, go read my inbox",
    "check my inbox",
    "open my gmail and get it",
    "grab it from my email",
    "look in my inbox",
    "fetch it from my email",
  ]) check(`permission: ${JSON.stringify(yes)}`, inboxAuthorized(yes));

  // An affirmative and the inbox, together, in one sentence.
  check("an answered yes about the inbox is permission",
    inboxAuthorized("They answered: yes go ahead and read the email"));

  // THE NEGATIVES ARE THE POINT. A false positive here reads somebody's mail
  // without being asked.
  for (const no of [
    "",
    "book a table for two at seven",
    "I'll email you the code",                    // mentions email, not permission
    "the code went to my email",                  // a statement of fact
    "yes",                                        // yes to WHAT?
    "yes, book it",                               // a yes about something else
    "no, don't go into my email, the code is 1234",
    "do not read my inbox",
    "never touch my email",
    "stay out of my mail",
  ]) check(`refused: ${JSON.stringify(no)}`, !inboxAuthorized(no));

  // The two halves must be in the SAME sentence, or a stray yes early in a long
  // approved scope lends its consent to an unrelated mention of email later.
  check("a yes in one sentence does not authorise an inbox mentioned in another",
    !inboxAuthorized("Yes, book the table. The confirmation goes to my email."));

  check("nothing is not permission", !inboxAuthorized(null) && !inboxAuthorized(undefined));
}

// --------------------------------------------- 2. what the offer actually says
{
  const owner = { email: "omar@gmail.com" };
  const emailed = tripOnOffer("We just sent a verification code to your email.", owner, "Anker");
  check("an emailed code produces an offer and somewhere to go",
    !!emailed && !!emailed.url && /Want me to go and read it/.test(emailed.offer));
  check("the destination comes from HIS address, never the errand",
    emailed.url.includes("mail.google.com"));

  // His phone is not ours to read, and it is already the channel we text him on.
  const texted = tripOnOffer("We sent a code by SMS to your phone.", owner, "Anker");
  check("a texted code asks him for it and offers no trip",
    !!texted && texted.url === null && /Send it to me/.test(texted.offer));

  // A masked address is not an address: the plain-address pattern happily
  // matches the tail of "o***r@gmail.com" and would send a trip to a fragment.
  const masked = tripOnOffer("Code sent to o***r@outlook.com", { email: "omar@gmail.com" }, "X");
  check("a masked address falls back to the address HE gave us",
    !!masked && masked.url.includes("mail.google.com"));

  check("a page with no code notice offers nothing",
    tripOnOffer("Welcome to our homepage.", owner, "X") === null);

  const unknownHost = tripOnOffer("Code sent to me@my-own-company.example", { email: "me@my-own-company.example" }, "X");
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
  harness.onInject = (src) => (src.includes("tagName !== \"INPUT\"")
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
      } else if (/find ONE verification code/.test(joined)) {
        content = "483920";
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
    if (!src.includes("tagName !== \"INPUT\"")) return undefined;
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
    } else if (/find ONE verification code/.test(joined)) {
      content = "483920";
    } else {
      seen.push(all[all.length - 1]);
      content = JSON.stringify(a.shift() || { action: "wait" });
    }
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content } }] }), text: async () => "" };
  };

  const out = await runAgentGoal("finish signing up for the shop account", {
    apiKey: "test-key",
    // HIS OWN WORDS are the authorization.
    scope: 'sign me up for the shop account. They answered: "yes, go read my email"',
    ownerProfile: { email: "omar@gmail.com", first_name: "Omar" },
    authorized: true,
    planning: true,
    stillLive: async () => true,
  });

  check("an authorised run finishes instead of parking", out.status === "done");
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
  const wall = loop.slice(loop.indexOf("THE OTP WALL"), loop.indexOf("THE OTP WALL") + 3000);
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
