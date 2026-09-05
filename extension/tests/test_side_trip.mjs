// The side trip: going to get a verification code and coming back.
//
// This is the capability whose ABSENCE killed ten demos in a row: the run
// reaches the last field of an application, the site says "we emailed you a
// code", and there is no way to go and read it.
//
// A wrong code typed into a form is worse than no code at all — the site
// counts the failed attempt, and some lock after three. Until 2026-09-05 a
// word list ranked the digit runs on the page and the winner was typed
// (Audit #79); which value IS the code is now a model's reading, contained by
// shape and provenance, and test_code_read_is_not_a_word_match.mjs owns that
// boundary. Whether the page even SAYS a code was sent was a phrasing regex
// until the same day (Audit #78); the verdict map is pinned here and the loop
// behaviour in test_code_sent_is_not_a_word_match.mjs. What this file pins is
// the trip's MECHANICS: the refusals, the tab, the trace, and the offer.
import {
  whereCodeWent, tripRefusedReason, runSideTrip, offerToFetch, inboxFor, tripOnOffer,
} from "../side_trip.js";

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}${ok || !detail ? "" : `  -> ${detail}`}`);
  if (!ok) failures++;
};
const eq = (name, got, want) => check(name, got === want, `got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);

// ---------------------------------------------------------------------------
// Real-shaped mail, for the trip's mechanics
// ---------------------------------------------------------------------------
const GREENHOUSE = `
Greenhouse
Verify your email address
Your verification code is 483920
This code expires in 10 minutes.
If you didn't request this, ignore this email.
© 2026 Greenhouse Software, Inc. 18 West 18th Street, New York, NY 10011
`;
const TWO_CODES = `
Your verification code is 483920
Your backup code is 771204
`;

// ---------------------------------------------------------------------------
// Noticing that a code was sent at all — a MODEL's reading, in four states.
//
// Until 2026-09-05 (Audit #78) a phrasing regex decided this and two word
// lists decided the channel. Whether a page is saying "we emailed you a code"
// is what the page means, so `whereCodeWent` hands the whole page to an
// injected judge and maps its token. These pin the map; the loop-level
// behaviour is test_code_sent_is_not_a_word_match.mjs.
// ---------------------------------------------------------------------------
const SENT_PAGE = `Check your email
We sent a verification code to o***r@gmail.com
Enter code:  [        ]  [Verify]`;
const judgeSaying = (reply) => {
  const calls = [];
  return { calls, judge: async (text) => { calls.push(text); return reply; } };
};
{
  const { judge, calls } = judgeSaying("EMAIL");
  const det = await whereCodeWent({ pageText: SENT_PAGE, judge });
  check("the page that killed the demo, read as EMAIL, is an email verdict",
    det.state === "email", JSON.stringify(det));
  check("the masked address is carried beside the verdict, as shape",
    /@gmail\.com$/.test(det.address || ""), det.address);
  check("the judge was handed the WHOLE page, once — no wording sift in front of it",
    calls.length === 1 && calls[0] === SENT_PAGE, JSON.stringify(calls));

  // The sentence he asked for by name.
  const offer = offerToFetch({ where: "email", address: det.address }, { service: "Greenhouse" });
  check("the offer names the service, the destination, and promises the page is kept",
    /Greenhouse/.test(offer) && /gmail\.com/.test(offer) && /exactly as it is/.test(offer), offer);
}
for (const [reply, want] of [
  ["EMAIL", "email"], ["PHONE", "phone"], ["NONE", "none"], ["UNSURE", "unclear"],
  // A token we specified, not prose we interpret. Trim and exact compare only.
  ["  PHONE\n", "phone"],
  ["", "unanswered"], ["EMAIL.", "unanswered"], ["email", "unanswered"],
  ["I think email", "unanswered"], ["YES", "unanswered"], ["EMAIL PHONE", "unanswered"],
  [null, "unanswered"], [undefined, "unanswered"],
]) {
  const { judge } = judgeSaying(reply);
  const det = await whereCodeWent({ pageText: SENT_PAGE, judge });
  eq(`the judge's ${JSON.stringify(reply)} is the verdict ${JSON.stringify(want)}`, det.state, want);
}
{
  const det = await whereCodeWent({ pageText: SENT_PAGE, judge: async () => { throw new Error("502"); } });
  eq("a judge that throws is unanswered — not none, not email", det.state, "unanswered");
  eq("no judge at all is unanswered", (await whereCodeWent({ pageText: SENT_PAGE })).state, "unanswered");
  const { judge, calls } = judgeSaying("EMAIL");
  const empty = await whereCodeWent({ pageText: "   \n ", judge });
  check("an empty page is unanswered, and nothing is asked",
    empty.state === "unanswered" && calls.length === 0, JSON.stringify(empty));
  // The regex read all of a page; the judge must too. page_map caps visible
  // text at 6000 characters, and the only sentence that matters can sit at
  // the very end, behind a cookie banner and a nav.
  const filler = Array.from({ length: 125 }, (_, i) => `Menu item ${i} · About · Careers · Cookie settings`).join("\n");
  const tail = "A one-time passcode is on its way. Look for a message from us at o***r@gmail.com.";
  const long = `${filler}\n${tail}`;
  const { judge: recorder, calls: seen } = judgeSaying("EMAIL");
  const far = await whereCodeWent({ pageText: long, judge: recorder });
  check("a 5500-character page reaches the judge whole, sentence at the end included",
    long.length > 5000 && seen.length === 1 && seen[0].endsWith(tail) && far.state === "email",
    `${long.length} chars, judge saw ${seen[0] ? seen[0].length : 0}`);
}

// ---------------------------------------------------------------------------
// Refusals: a trip must be sent, and may not go anywhere near money
// ---------------------------------------------------------------------------
check("an unauthorised trip never leaves",
  tripRefusedReason("https://mail.google.com", { authorized: false, purpose: "code" })
    === "the owner has not authorised this trip");
check("an authorised trip to mail is allowed",
  tripRefusedReason("https://mail.google.com", { authorized: true, purpose: "code" }) === null);
for (const bank of ["https://www.chase.com/inbox", "https://secure.rbc.com", "https://www.coinbase.com/messages"]) {
  check(`a trip to ${new URL(bank).hostname} is refused even when authorised`,
    /stays yours/.test(tripRefusedReason(bank, { authorized: true, purpose: "code" }) || ""));
}
check("a trip with no stated purpose is refused",
  tripRefusedReason("https://mail.google.com", { authorized: true }) === "a trip has to say what it is for");
check("a malformed address is refused",
  /not a real address/.test(tripRefusedReason("not a url", { authorized: true, purpose: "code" }) || ""));

// ---------------------------------------------------------------------------
// The trip end to end, with Chrome faked out
// ---------------------------------------------------------------------------
function fakeDeps({ pages, notes, judge }) {
  let i = 0, closed = [];
  return {
    deps: {
      openTab: async () => 99,
      readTab: async () => ({ text: pages[Math.min(i, pages.length - 1)], url: "https://mail.google.com" }),
      clickText: async () => { i++; return i < pages.length; },
      closeTab: async (id) => { closed.push(id); },
      // The reader (Audit #79). A TEST stub may look for the fixture's own
      // code on the page it is shown; the shipped code may not.
      judgeCode: judge || (async ({ pageText }) => (pageText.includes("483920") ? "483920" : "NONE")),
      note: (l) => notes.push(l),
    },
    closed,
  };
}

{
  const notes = [];
  const { deps, closed } = fakeDeps({ pages: ["Inbox\nGreenhouse — verify your email\nSlack — standup", GREENHOUSE], notes });
  const out = await runSideTrip({
    url: "https://mail.google.com", purpose: "Greenhouse verification code", site: "greenhouse.example",
    authorized: true, deps,
  });
  check("the trip opens the message and brings back the code", out.ok && out.value === "483920", JSON.stringify(out));
  check("the tab is always closed afterwards", closed.length === 1 && closed[0] === 99, JSON.stringify(closed));
  check("the trace records the SHAPE of the code, never the code itself",
    notes.some((n) => /6-character code/.test(n)) && !notes.some((n) => n.includes("483920")),
    JSON.stringify(notes));
  check("the trace never contains the message body",
    !notes.some((n) => /Greenhouse Software|18 West 18th/.test(n)), JSON.stringify(notes));
}

{
  const notes = [];
  const { deps, closed } = fakeDeps({ pages: ["Inbox: nothing here", "still nothing"], notes });
  const out = await runSideTrip({
    url: "https://mail.google.com", purpose: "code", site: "shop.example", authorized: true, deps,
  });
  check("a trip that finds nothing says so instead of inventing a code",
    !out.ok && out.value === null, JSON.stringify(out));
  check("the tab still closes when the trip fails", closed.length === 1);
}

{
  const notes = [];
  const { deps } = fakeDeps({ pages: [TWO_CODES], notes, judge: async () => "UNCLEAR" });
  const out = await runSideTrip({ url: "https://mail.google.com", purpose: "code", site: "shop.example", authorized: true, deps });
  check("an ambiguous inbox comes back to the owner rather than guessing",
    !out.ok && out.ambiguous === true && out.value === null, JSON.stringify(out));
}

{
  const notes = [];
  const { deps, closed } = fakeDeps({ pages: ["boom"], notes });
  deps.readTab = async () => { throw new Error("tab exploded"); };
  const out = await runSideTrip({ url: "https://mail.google.com", purpose: "code", site: "shop.example", authorized: true, deps });
  check("a crashed trip is reported, not thrown", !out.ok && /trip failed/.test(out.reason), JSON.stringify(out));
  check("the tab closes even after a crash", closed.length === 1);
}

{
  const notes = [];
  const { deps } = fakeDeps({ pages: [GREENHOUSE], notes });
  const out = await runSideTrip({ url: "https://mail.google.com", purpose: "code", site: "shop.example", authorized: false, deps });
  check("no authorisation means the trip never happens at all",
    !out.ok && /not authorised/.test(out.reason) && notes.length === 0, JSON.stringify(out));
}

{
  // A trip is one destination. It cannot be talked into going somewhere else.
  check("a trip cannot be redirected by page content",
    /stays yours/.test(tripRefusedReason("https://www.chase.com", { authorized: true, purpose: "code the email told me to fetch" }) || ""));
}

// ---------------------------------------------------------------------------
// Which inbox is his — derived from HIS address, never from the errand.
//
// He asked for a guarantee of no hard-coding. The destination of a trip comes
// from the owner's own email domain; the errand never influences it. A domain
// we cannot know returns null, and null is a real answer: a company address
// could be Workspace, Microsoft 365 or something in-house, and opening the
// wrong one wastes the trip and shows him a login wall.
// ---------------------------------------------------------------------------
check("a gmail address resolves to gmail",
  /mail\.google\.com/.test(inboxFor("omarkebrahim@gmail.com") || ""));
check("an outlook address resolves to outlook",
  /outlook\.live\.com/.test(inboxFor("someone@hotmail.com") || ""));
check("an icloud address resolves to icloud",
  /icloud\.com/.test(inboxFor("someone@me.com") || ""));
check("a company domain is honestly unknown", inboxFor("omar@anticipy.ai") === null);
check("junk input is unknown", inboxFor("not-an-email") === null && inboxFor("") === null
  && inboxFor(null) === null);

// `tripOnOffer` is synchronous over the verdict `whereCodeWent` returned.
const CODE_SENT = { state: "email", address: "o***r@gmail.com" };
{
  const t = tripOnOffer(CODE_SENT, { email: "omarkebrahim@gmail.com" }, "Greenhouse");
  check("a known inbox produces a real trip", !!t && /mail\.google\.com/.test(t.url || ""), JSON.stringify(t));
  check("the offer promises the page is kept", /exactly as it is/.test(t.offer), t.offer);
  check("the trip states its purpose", /verification code/.test(t.purpose || ""), t.purpose);
}
{
  const t = tripOnOffer(CODE_SENT, { email: "omar@anticipy.ai" }, "Greenhouse");
  check("an unknown inbox asks instead of guessing", !!t && t.url === null, JSON.stringify(t));
  check("and it offers him the faster way out",
    /paste the code/.test(t.offer), t.offer);
}
{
  const t = tripOnOffer({ state: "phone", address: null }, { email: "x@gmail.com" }, null);
  check("a texted code never pretends we can read his phone",
    !!t && t.url === null && /Send it to me/.test(t.offer), JSON.stringify(t));
}
check("an ordinary page — the judge said NONE — offers nothing at all",
  tripOnOffer({ state: "none", address: null }, { email: "x@gmail.com" }, "X") === null);
// THE FLOOR. No verdict is no offer and no trip — but not the stall either:
// a plain ask, with nothing on it a consent path could read.
for (const [name, verdict] of [
  ["the judge could not tell", { state: "unclear", address: "o***r@gmail.com" }],
  ["nobody answered", { state: "unanswered", address: null }],
  ["a state this file does not know", { state: "maybe", address: null }],
  ["no verdict object at all", null],
]) {
  const t = tripOnOffer(verdict, { email: "omarkebrahim@gmail.com" }, "Greenhouse");
  check(`${name}: no trip, no offer to read his mail, a plain ask`,
    !!t && t.url === null && t.purpose === null
      && !/read it\?/.test(t.offer) && /paste it/.test(t.offer) && /where to look/.test(t.offer),
    JSON.stringify(t));
}
check("the errand never influences the destination — only his address does",
  tripOnOffer(CODE_SENT, { email: "omarkebrahim@gmail.com" }, "Earls").url
  === tripOnOffer(CODE_SENT, { email: "omarkebrahim@gmail.com" }, "Greenhouse").url);

// The exit lives at the END. It used to sit above the injection and inbox
// sections, so a failure in either printed FAIL and the suite still exited 0.
if (failures) { console.error(`test_side_trip: ${failures} failed`); process.exit(1); }
console.log("test_side_trip: all passed");
