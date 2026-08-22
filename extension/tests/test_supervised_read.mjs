// THE SUPERVISED READ — the mechanism behind five promises that had none.
//
// `ContextSource.mail.promises` has been on screen since the consent surface
// shipped, and until `supervised_read.js` existed not one of those sentences
// was enforced by anything. These tests are the enforcement, stated as
// failures: each one is a way somebody's mailbox gets read when it should not,
// or leaves the device when it should not.
//
// The dangerous parts, in order of how bad the failure is:
//   1. an action outside the whitelist reaching the page — that is a reply, a
//      delete, a send, from a thing that promised it never would;
//   2. a read continuing after the person stopped watching;
//   3. page text — a subject line, a body — travelling as an event, which
//      `design/LOCAL-FIRST.md:9-11` forbids absolutely;
//   4. an unbounded pass, which is a scrape wearing a read's name.
import {
  FACT_CEILING, MAX_LINE_CHARS, MAX_PASS_CHARS, MAX_READ_IMPORTANCE,
  MAX_SLICE_CHARS, MAX_STEPS, READ_VOCABULARY, actionRefusedReason, cleanFacts,
  eventSourceFor, leaseLapsed, lineRefusedReason, runSupervisedRead,
  vocabularyFor,
} from "../supervised_read.js";

let failures = 0;
const check = (name, ok, detail = "") => {
  if (ok) return;
  failures++;
  console.error(`  FAIL ${name}${detail ? ` — ${detail}` : ""}`);
};
const eq = (name, got, want) =>
  check(name, got === want, `got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);

// ---------------------------------------------------------------------------
// The vocabulary, per source
//
// TWO LISTS, AND THE DIFFERENCE IS LEGAL. LinkedIn's UA §8.2 prohibits
// automated access and hiQ lost on breach of contract, with the penalty landing
// on the paying user's account — and the question that decides it is WHO
// NAVIGATES. So mail may move inside a mailbox the person opened, and a
// professional page may only be read exactly as it sits.
// ---------------------------------------------------------------------------
eq("mail may navigate", actionRefusedReason("mail", "navigate"), null);
eq("mail may scroll", actionRefusedReason("mail", "scroll"), null);
eq("mail may extract", actionRefusedReason("mail", "extract"), null);

check("a professional page may NOT be navigated — §8.2 turns on who navigates",
  /may only extract/.test(actionRefusedReason("professional", "navigate") || ""),
  actionRefusedReason("professional", "navigate"));
check("a professional page may not be scrolled either",
  actionRefusedReason("professional", "scroll") !== null);
eq("a professional page may be read as it sits",
  actionRefusedReason("professional", "extract"), null);

// The whole point of a whitelist: the interesting cases are the ones nobody
// listed. Each of these is a real Chrome capability the browser arm has.
for (const verb of ["click", "type", "select", "press", "download", "submit",
                    "reply", "delete", "archive", "send", "wait", ""]) {
  check(`mail refuses "${verb}" — it is not in the vocabulary`,
    actionRefusedReason("mail", verb) !== null,
    `refusal was ${JSON.stringify(actionRefusedReason("mail", verb))}`);
}

// DEFAULT DENY. A new source that has not stated its vocabulary reads nothing;
// it does not inherit mail's.
check("an unknown source gets nothing at all", vocabularyFor("gmail_api").length === 0);
check("an unknown source is refused by name, not silently widened",
  /no read vocabulary/.test(actionRefusedReason("calendar", "extract") || ""),
  actionRefusedReason("calendar", "extract"));
check("a missing source is refused", actionRefusedReason("", "extract") !== null);
check("a missing source is refused even for a listed verb",
  actionRefusedReason(null, "navigate") !== null);

// The table itself cannot be widened by a caller holding a reference to it.
try { READ_VOCABULARY.professional.push("navigate"); } catch (_) { /* frozen */ }
eq("the vocabulary table cannot be widened in place",
  READ_VOCABULARY.professional.includes("navigate"), false);
try { READ_VOCABULARY.linkedin = ["navigate", "scroll", "extract"]; } catch (_) { /* frozen */ }
eq("a source cannot be added to the table at runtime",
  vocabularyFor("linkedin").length, 0);

// ---------------------------------------------------------------------------
// The lease — the only thing that authorises any of this
//
// `jobs.watching_until` is pushed forward every ten seconds by
// `SupervisedReadView`, and ONLY while it is on screen with the scene active.
// Everything below is the arithmetic that turns "while you watch" into a fact.
// ---------------------------------------------------------------------------
const T = Date.parse("2026-08-21T12:00:00Z");
eq("a lease 30s in the future is live", leaseLapsed(new Date(T + 30000).toISOString(), T), false);
eq("a lease one second in the past has lapsed", leaseLapsed(new Date(T - 1000).toISOString(), T), true);
eq("a lease expiring exactly now has lapsed", leaseLapsed(new Date(T).toISOString(), T), true);
eq("a Date works as well as a string", leaseLapsed(new Date(T + 5000), T), false);
// FAIL CLOSED, and these are the cases that matter: an app build that never
// writes the column, a cleared field, a mangled value. None of them is consent.
eq("a missing lease is nobody watching", leaseLapsed(null, T), true);
eq("an empty lease is nobody watching", leaseLapsed("", T), true);
eq("undefined is nobody watching", leaseLapsed(undefined, T), true);
eq("an unparseable lease is nobody watching", leaseLapsed("soon", T), true);
eq("a zero is nobody watching", leaseLapsed(0, T), true);

// ---------------------------------------------------------------------------
// Narration hygiene: what she concluded, never what she saw
//
// A read_line is an EVENT. It leaves the phone and it is stored, so
// `design/LOCAL-FIRST.md:9-11` decides its contents absolutely: conclusions
// travel, the stream never does.
// ---------------------------------------------------------------------------
eq("a short conclusion in her voice is fine",
  lineRefusedReason("You and Marcus have something in flight."), null);
eq("a contraction is fine", lineRefusedReason("I'm reading your inbox now."), null);
eq("the professional finding is sayable",
  lineRefusedReason("I'm on your feed, not your connections - open the page you want me to read"), null);

check("an empty line is refused", lineRefusedReason("") !== null);
check("whitespace is refused", lineRefusedReason("   \n ") !== null);
check("null is refused", lineRefusedReason(null) !== null);

// RAW PAGE TEXT. Each of these is a real shape of "the model summarised by
// quoting", and each one is a subject line or a body escaping onto the wire.
const RAW_QUOTED = 'Marcus wrote: "Can you get me the proposal by Thursday, I need it for the board"';
check("a quoted message body is refused", lineRefusedReason(RAW_QUOTED) !== null,
  lineRefusedReason(RAW_QUOTED));
check("a subject header is refused",
  lineRefusedReason("Subject: Q3 proposal — final draft") !== null);
check("a From header is refused",
  lineRefusedReason("From: marcus@bellworks.com") !== null);
check("a Re: line is refused", lineRefusedReason("Re: dinner Thursday") !== null);
check("an email address never travels",
  lineRefusedReason("Marcus at marcus@bellworks.com is waiting on you") !== null);
check("a link is page content",
  lineRefusedReason("Your proposal is at https://docs.example.com/x9") !== null);
check("mail-client furniture is refused",
  lineRefusedReason("Unsubscribe from these emails at any time") !== null);
check("a quote marker is refused", lineRefusedReason("> I need it for the board") !== null);
// LENGTH IS THE MOST RELIABLE SIGNAL that a conclusion is actually an excerpt.
const EXCERPT = "Hi there, following up on the thread from last week about the "
  + "proposal timeline and the revised scope, we should probably get on a call "
  + "before Thursday so the board has something to look at";
check("an excerpt-length line is refused", lineRefusedReason(EXCERPT) !== null,
  lineRefusedReason(EXCERPT));
check(`the cap is ${MAX_LINE_CHARS} characters`,
  lineRefusedReason("a".repeat(MAX_LINE_CHARS)) === null
    && lineRefusedReason("a".repeat(MAX_LINE_CHARS + 1)) !== null);
check("more than one sentence is refused",
  lineRefusedReason("You have three threads open. Marcus is waiting.") !== null);
check("a trailing full stop is still one sentence",
  lineRefusedReason("Marcus is waiting on you.") === null);

// ---------------------------------------------------------------------------
// Facts: 5-15 for the whole pass, importance never above 4
// ---------------------------------------------------------------------------
{
  const many = Array.from({ length: 40 }, (_, i) => ({ fact: `Fact number ${i} about you`, importance: 3 }));
  eq(`no more than ${FACT_CEILING} facts survive a whole read`,
    cleanFacts(many).length, FACT_CEILING);
}
{
  // IMPORTANCE 5 IS RESERVED for a boundary the owner stated in their own
  // words ("never touch anything to do with my bank"). Recall is ranked and a
  // briefing takes the top ten, so a fact nobody typed must never outrank one
  // they did.
  const clamped = cleanFacts([
    { fact: "Marcus Bell is a client and a proposal is in flight", importance: 5 },
    { fact: "Priya runs payroll", importance: 9 },
    { fact: "The board meets on Thursdays", importance: 1 },
    { fact: "Dana is a recruiter", importance: 0 },
    { fact: "Sam owns the vendor contract" },
  ]);
  check("nothing a read derives is ever importance 5",
    clamped.every((f) => f.importance <= MAX_READ_IMPORTANCE),
    JSON.stringify(clamped.map((f) => f.importance)));
  check("importance is never below 1", clamped.every((f) => f.importance >= 1));
  eq("a fact with no stated importance still carries one",
    typeof clamped[4].importance, "number");
}
{
  // The same hygiene as narration, because a fact is stored FOREVER and a line
  // is only shown once. This is the stricter of the two paths, not the looser.
  const dirty = cleanFacts([
    { fact: 'Subject: "the proposal" — Marcus', importance: 3 },
    { fact: "marcus@bellworks.com is the client", importance: 3 },
    { fact: "Marcus Bell is a client and a proposal is in flight", importance: 4 },
    { fact: "marcus bell IS A CLIENT and a proposal is in flight", importance: 4 },
  ]);
  eq("quoted and address-bearing facts are dropped, restatements merged",
    dirty.length, 1);
  eq("the surviving fact is the distilled one", dirty[0].fact,
    "Marcus Bell is a client and a proposal is in flight");
}
eq("junk in, nothing out", cleanFacts(null).length, 0);
eq("a list of empty strings yields nothing", cleanFacts(["", "  ", null]).length, 0);

// THE FENCE. Mail is written by other people, so a read-derived fact is
// attacker-controlled text and must be fenced exactly like an imported
// calendar title. These strings are keyed on in `brain/anticipy_core.py`
// `_UNTRUSTED_SOURCES`; if one is renamed on either side, this fails.
eq("mail facts carry the mail fence tag", eventSourceFor("mail"), "supervised_mail");
eq("professional facts carry their own fence tag",
  eventSourceFor("professional"), "supervised_professional");
eq("an unknown source has no fence tag, so it can emit no fact",
  eventSourceFor("gmail_api"), null);

// ---------------------------------------------------------------------------
// The pass itself, with Chrome faked out
// ---------------------------------------------------------------------------

// A mailbox, in the shape a mailbox actually reads: a list, then a thread.
const INBOX_PAGE = [
  "Inbox (14)",
  "Marcus Bell — Q3 proposal, final draft — 9:14",
  "Priya Raman — payroll cutoff moved to the 28th — Tue",
  "Dana Whitlock — following up on that intro — Mon",
].join("\n");
const THREAD_PAGE = [
  "Q3 proposal — final draft",
  "Marcus Bell <marcus@bellworks.com>",
  "Sending the final draft ahead of the board on Thursday. Need your sign-off.",
].join("\n");

/**
 * Everything Chrome would do, faked, plus a ledger of what was attempted.
 *
 * `moves` is the script the model "returns", one per step. That is the honest
 * way to test a whitelist: the model is the adversary here, not the page.
 */
function fakeDeps({
  moves = [],
  lease = () => new Date(Date.now() + 30000).toISOString(),
  pages = { "https://mail.google.com/": INBOX_PAGE },
  facts = [{ fact: "Marcus Bell is a client and a proposal is in flight", importance: 4 }],
  throwOnRead = false,
} = {}) {
  const log = {
    opened: [], closed: [], navigated: [], scrolled: [], reads: 0,
    emitted: [], leaseChecks: 0, modelCalls: [],
  };
  let currentUrl = Object.keys(pages)[0];
  let move = 0;
  const deps = {
    openTab: async (url) => { log.opened.push(url); currentUrl = url; return 77; },
    currentTab: async () => 77,
    readPage: async () => {
      log.reads++;
      if (throwOnRead) throw new Error("the tab went away mid-read");
      return { text: pages[currentUrl] ?? "", url: currentUrl };
    },
    navigate: async (_tabId, url) => { log.navigated.push(url); currentUrl = url; },
    scrollPage: async () => { log.scrolled.push(true); },
    closeTab: async (tabId) => { log.closed.push(tabId); },
    leaseUntil: async () => { log.leaseChecks++; return lease(log.leaseChecks); },
    askModel: async (system, user) => {
      log.modelCalls.push({ system, user });
      if (/Write down what you now know/.test(system)) return JSON.stringify({ facts });
      const next = moves[move++] || { action: "done" };
      return JSON.stringify(next);
    },
    emit: async (event) => { log.emitted.push(event); },
    note: () => {},
  };
  return { deps, log };
}

// --- the happy path: list, then one thread, then facts ---------------------
{
  const { deps, log } = fakeDeps({
    pages: { "https://mail.google.com/": INBOX_PAGE, "https://mail.google.com/thread/1": THREAD_PAGE },
    moves: [{ action: "navigate", url: "https://mail.google.com/thread/1", say: "Opening the thread with Marcus." }],
    facts: [
      { fact: "Marcus Bell is a client and a proposal is in flight", importance: 4 },
      { fact: "Priya Raman handles payroll", importance: 3 },
    ],
  });
  const out = await runSupervisedRead({
    source: "mail", startUrl: "https://mail.google.com/", deps,
  });
  check("a supervised read of mail completes", out.ok, JSON.stringify(out));
  eq("it opened its own tab", log.opened.length, 1);
  eq("and closed it", log.closed[0], 77);
  eq("it moved once, inside the mailbox", log.navigated.length, 1);
  eq("two facts came back", out.facts.length, 2);
  check("facts went out as read_fact events with the fence tag",
    log.emitted.filter((e) => e.kind === "read_fact")
      .every((e) => e.source === "supervised_mail" && e.importance <= MAX_READ_IMPORTANCE),
    JSON.stringify(log.emitted.filter((e) => e.kind === "read_fact")));
  check("narration went out as read_line events",
    log.emitted.some((e) => e.kind === "read_line"));
  check("nothing but read_line and read_fact was ever emitted",
    log.emitted.every((e) => e.kind === "read_line" || e.kind === "read_fact"),
    JSON.stringify(log.emitted.map((e) => e.kind)));
  // THE PROPERTY THIS WHOLE FILE EXISTS FOR: nothing that was on the page is
  // in anything that left.
  const wire = JSON.stringify(log.emitted);
  check("no message body reached the wire", !/sign-off|final draft/i.test(wire), wire);
  check("no address reached the wire", !/marcus@bellworks\.com/.test(wire), wire);
  check("the page text WAS shown to the model, fenced",
    log.modelCalls.some((c) => /BEGIN UNTRUSTED PAGE/.test(c.user) && /sign-off/.test(c.user)));
}

// --- an action outside the whitelist ---------------------------------------
{
  // The model asks to click. This is the failure the promise "I never send,
  // never reply, never delete" is about, and it is refused by code that never
  // consults a model to decide.
  const { deps, log } = fakeDeps({
    moves: [{ action: "click", url: "", say: "Opening that message." }],
  });
  const out = await runSupervisedRead({ source: "mail", startUrl: "https://mail.google.com/", deps });
  eq("a click ends the pass", out.stopped, "refused");
  check("the refusal is recorded", out.refused.some((r) => /not click/.test(r)),
    JSON.stringify(out.refused));
  eq("nothing was clicked, because there is no way to click", log.navigated.length, 0);
  eq("the tab still closed", log.closed[0], 77);
}
{
  // Under `professional` the SAME move that mail is allowed is refused, and
  // that asymmetry is the §8.2 argument expressed as code.
  const { deps, log } = fakeDeps({
    pages: { "https://www.linkedin.com/in/me": "Your profile — Head of Ops at Bellworks" },
    moves: [{ action: "navigate", url: "https://www.linkedin.com/mynetwork", say: "Checking your connections." }],
  });
  const out = await runSupervisedRead({ source: "professional", deps });
  eq("navigate under professional ends the pass", out.stopped, "refused");
  eq("the page was never moved", log.navigated.length, 0);
  eq("and no tab was opened for it — the person's own page is read in place",
    log.opened.length, 0);
  eq("a tab we did not open is never closed", log.closed.length, 0);
}
{
  // The identical move, under mail, is allowed. One assertion, and it is the
  // whole reason there are two lists.
  const { deps, log } = fakeDeps({
    pages: { "https://mail.google.com/": INBOX_PAGE, "https://mail.google.com/thread/1": THREAD_PAGE },
    moves: [{ action: "navigate", url: "https://mail.google.com/thread/1", say: "Opening that thread." }],
  });
  const out = await runSupervisedRead({ source: "mail", startUrl: "https://mail.google.com/", deps });
  eq("navigate under mail is allowed", log.navigated.length, 1);
  check("and the pass is not a refusal", out.stopped !== "refused", out.stopped);
}
{
  // An unknown source reads NOTHING — no tab, no model call, no event.
  const { deps, log } = fakeDeps({});
  const out = await runSupervisedRead({ source: "work_tools", startUrl: "https://example.com/", deps });
  eq("an unknown source refuses outright", out.ok, false);
  eq("it never opened a page", log.opened.length + log.reads, 0);
  eq("it never called a model", log.modelCalls.length, 0);
  eq("it emitted nothing", log.emitted.length, 0);
}

// --- the lease ------------------------------------------------------------
{
  // ALREADY LAPSED WHEN THE JOB IS PICKED UP. Nothing happens at all: no tab,
  // no read, no model call. The person put the phone down.
  const { deps, log } = fakeDeps({ lease: () => new Date(Date.now() - 1000).toISOString() });
  const out = await runSupervisedRead({ source: "mail", startUrl: "https://mail.google.com/", deps });
  eq("a lapsed lease is a clean stop, not a failure", out.ok, true);
  eq("and it says so", out.stopped, "lease");
  eq("no tab was ever opened", log.opened.length, 0);
  eq("nothing was read", log.reads, 0);
  eq("no model was asked anything", log.modelCalls.length, 0);
  eq("no fact was emitted", log.emitted.filter((e) => e.kind === "read_fact").length, 0);
}
{
  // THE ABORT PATH, MID-PASS: the lease is live for the first check and dead
  // afterwards — the app went to the background while she was reading. The tab
  // must close and nothing may be kept.
  let checks = 0;
  const { deps, log } = fakeDeps({
    lease: () => {
      checks++;
      return new Date(Date.now() + (checks <= 1 ? 30000 : -1000)).toISOString();
    },
    moves: [{ action: "scroll", say: "Reading further down." }],
  });
  const out = await runSupervisedRead({ source: "mail", startUrl: "https://mail.google.com/", deps });
  eq("the pass stops on the lease", out.stopped, "lease");
  eq("THE TAB IS CLOSED ON THE ABORT PATH", log.closed[0], 77);
  eq("not one fact is kept from an unwatched read", out.facts.length, 0);
  eq("and no read_fact event was sent", log.emitted.filter((e) => e.kind === "read_fact").length, 0);
  check("she says why she stopped",
    log.emitted.some((e) => e.kind === "read_line" && /looked away/.test(e.text)),
    JSON.stringify(log.emitted));
}
{
  // A lease that lapses only at the very END — after everything was read while
  // she was being watched. Still nothing kept: facts that arrive after the
  // surface is gone arrive unwatched and unvetoable, which is exactly what
  // supervision exists to prevent.
  let checks = 0;
  const { deps, log } = fakeDeps({
    lease: () => { checks++; return new Date(Date.now() + (checks <= 2 ? 30000 : -1000)).toISOString(); },
    moves: [{ action: "done" }],
  });
  const out = await runSupervisedRead({ source: "mail", startUrl: "https://mail.google.com/", deps });
  eq("a lease that dies before the distillation keeps nothing", out.facts.length, 0);
  eq("it is still a clean stop", out.ok, true);
  eq("the tab closed", log.closed[0], 77);
}
{
  // THE LEASE IS RE-READ, NOT CACHED. It is checked before the first action
  // and again before every one after it — the same shape as `stoppedNow()`
  // before an irreversible action in `agent_loop.js:5211`.
  const { deps, log } = fakeDeps({
    moves: [{ action: "scroll", say: "Reading on." }, { action: "done" }],
  });
  await runSupervisedRead({ source: "mail", startUrl: "https://mail.google.com/", deps });
  check("the lease is re-read several times in one pass", log.leaseChecks >= 4,
    `only ${log.leaseChecks} checks`);
}
{
  // NO LEASE READER AT ALL is a refusal, not an assumption. This is the
  // `side_trip.js:189-198` rule: authorisation may not come from a flag, and
  // the absence of proof is not proof.
  const { deps, log } = fakeDeps({});
  delete deps.leaseUntil;
  const out = await runSupervisedRead({ source: "mail", startUrl: "https://mail.google.com/", deps });
  eq("a read with no way to prove supervision refuses", out.ok, false);
  eq("and reads nothing", log.reads, 0);
}
{
  // A lease reader that THROWS (the row was deleted, the network died) is the
  // same answer: nobody is watching.
  const { deps, log } = fakeDeps({});
  deps.leaseUntil = async () => { throw new Error("job gone"); };
  const out = await runSupervisedRead({ source: "mail", startUrl: "https://mail.google.com/", deps });
  eq("a lease that cannot be read is a lapsed lease", out.stopped, "lease");
  eq("nothing was opened", log.opened.length, 0);
}

// --- the throw path -------------------------------------------------------
{
  const { deps, log } = fakeDeps({ throwOnRead: true });
  const out = await runSupervisedRead({ source: "mail", startUrl: "https://mail.google.com/", deps });
  eq("a thrown read fails honestly", out.ok, false);
  eq("THE TAB IS CLOSED ON THE THROW PATH", log.closed[0], 77);
  check("the failure reason is truncated, because an error can carry page text",
    out.reason.length <= 160, out.reason);
}
{
  // The tab closes even when closing is the thing that fails — a read must not
  // be able to leave an exception escaping out of its own cleanup.
  const { deps } = fakeDeps({});
  deps.closeTab = async () => { throw new Error("tab already gone"); };
  const out = await runSupervisedRead({ source: "mail", startUrl: "https://mail.google.com/", deps });
  check("a failed close does not break the read", out.ok, JSON.stringify(out));
}

// --- the bounds: this cannot become a crawl -------------------------------
{
  // A MODEL THAT WANTS TO KEEP GOING FOREVER. Every move is legal; the caps
  // are what stop it.
  const pages = {};
  for (let i = 0; i < 50; i++) pages[`https://mail.google.com/thread/${i}`] = `Thread ${i}\n${INBOX_PAGE}`;
  const moves = Array.from({ length: 50 }, (_, i) =>
    ({ action: "navigate", url: `https://mail.google.com/thread/${i + 1}`, say: "Reading on." }));
  const { deps, log } = fakeDeps({ pages, moves });
  const out = await runSupervisedRead({
    source: "mail", startUrl: "https://mail.google.com/thread/0", deps,
  });
  check(`the pass cannot exceed ${MAX_STEPS} steps`, out.steps <= MAX_STEPS,
    `ran ${out.steps}`);
  check(`it read at most ${MAX_STEPS} pages`, log.reads <= MAX_STEPS, `read ${log.reads}`);
  eq("and it ended on the step cap", out.stopped, "steps");
}
{
  // NO REVISITING. A model that keeps proposing a page already read ends the
  // pass rather than looping — an agent that re-reads is an agent with an
  // unbounded budget.
  const { deps, log } = fakeDeps({
    pages: { "https://mail.google.com/": INBOX_PAGE },
    moves: Array.from({ length: 6 },
      () => ({ action: "navigate", url: "https://mail.google.com/", say: "Back to the list." })),
  });
  await runSupervisedRead({ source: "mail", startUrl: "https://mail.google.com/", deps });
  eq("a page already read is never navigated to again", log.navigated.length, 0);
}
{
  // OFF-SITE IS NOT A PLACE A READ GOES. The model proposes a different host,
  // which is the shape of both a crawl and a phishing click.
  const { deps, log } = fakeDeps({
    moves: [{ action: "navigate", url: "https://tracker.example.com/pixel", say: "Following that up." }],
  });
  await runSupervisedRead({ source: "mail", startUrl: "https://mail.google.com/", deps });
  eq("a read never leaves the site the person opened", log.navigated.length, 0);
}
{
  // THE SLICE CAP. A page holding a novel contributes at most one slice's
  // worth to the prompt, on the same ~5,000-character bound `page_map.js`
  // already enforces.
  const huge = "Marcus Bell wrote something. ".repeat(4000);
  const { deps, log } = fakeDeps({ pages: { "https://mail.google.com/": huge } });
  await runSupervisedRead({ source: "mail", startUrl: "https://mail.google.com/", deps });
  const shown = log.modelCalls[0]?.user || "";
  check(`no more than ${MAX_SLICE_CHARS} characters of one page reach the model`,
    shown.length <= MAX_SLICE_CHARS + 200, `${shown.length} characters`);
  check(`the whole pass is bounded at ${MAX_PASS_CHARS} characters`,
    log.modelCalls.every((c) => c.user.length <= MAX_PASS_CHARS + 1000));
}
{
  // A BANK IS NOT READ, EVER — not even opened. Stricter than the main loop's
  // block list on purpose, and the same refusal a side trip gets, from the
  // same function.
  const { deps, log } = fakeDeps({});
  const out = await runSupervisedRead({ source: "mail", startUrl: "https://www.chase.com/messages", deps });
  eq("a read refuses to open a bank", out.ok, false);
  eq("and does not open a tab to find out", log.opened.length, 0);
}
{
  // Nothing readable on the page is a FINDING, not a reason to go looking —
  // which is the professional case the design names by name.
  const { deps, log } = fakeDeps({ pages: { "https://www.linkedin.com/feed": "" } });
  const out = await runSupervisedRead({ source: "professional", deps });
  eq("an empty page yields no facts", out.facts.length, 0);
  eq("and moves nothing looking for a better one", log.navigated.length + log.scrolled.length, 0);
  check("she names the page she needs instead of going to find it",
    log.emitted.some((e) => e.kind === "read_line" && /open the one you want me to read/.test(e.text)),
    JSON.stringify(log.emitted));
}

// --- narration hygiene, in the emit path ---------------------------------
{
  // A MODEL THAT QUOTES. The prompt tells it not to; this is what happens when
  // it does anyway, which is the only version of this that matters.
  const { deps, log } = fakeDeps({
    moves: [{
      action: "scroll",
      say: 'Marcus wrote: "I need the final draft before the board on Thursday, can you send it"',
    }, { action: "done" }],
  });
  const out = await runSupervisedRead({ source: "mail", startUrl: "https://mail.google.com/", deps });
  const wire = JSON.stringify(log.emitted);
  check("A READ_LINE CARRYING RAW PAGE TEXT IS REFUSED",
    !/final draft/.test(wire) && !/Marcus wrote/.test(wire), wire);
  check("and the refusal is recorded rather than silently swallowed",
    out.refused.some((r) => /line refused/.test(r)), JSON.stringify(out.refused));
  check("the pass carries on — a bad line is not a bad read",
    out.ok, JSON.stringify(out));
}
{
  // A MODEL THAT RETURNS A SUBJECT LINE AS A FACT. Same wall, and it matters
  // more here because a fact is stored forever.
  const { deps, log } = fakeDeps({
    facts: [
      { fact: 'Subject: "Q3 proposal — final draft" from marcus@bellworks.com', importance: 4 },
      { fact: "Marcus Bell is a client and a proposal is in flight", importance: 4 },
    ],
  });
  const out = await runSupervisedRead({ source: "mail", startUrl: "https://mail.google.com/", deps });
  eq("the quoted fact is dropped and the distilled one kept", out.facts.length, 1);
  check("no subject line was ever stored",
    !/Q3 proposal/.test(JSON.stringify(log.emitted)), JSON.stringify(log.emitted));
}
{
  // A model returning nothing usable is an honest blank, never an invented
  // fact — `learn.js:308-313` takes the same position for the same reason.
  const { deps } = fakeDeps({ facts: [] });
  const out = await runSupervisedRead({ source: "mail", startUrl: "https://mail.google.com/", deps });
  eq("no facts is a real answer", out.facts.length, 0);
  check("and it is not a failure", out.ok);
}
{
  // A model that returns prose instead of JSON, or nothing at all, ends the
  // pass — it does not retry, because a retry is a second read of somebody's
  // mail to answer the same question.
  const { deps, log } = fakeDeps({});
  deps.askModel = async () => "I'm sorry, I can't help with that.";
  const out = await runSupervisedRead({ source: "mail", startUrl: "https://mail.google.com/", deps });
  check("unparseable model output is survivable", out.ok !== undefined);
  eq("the tab still closed", log.closed[0], 77);
}
{
  // A FAILING EMIT MUST NOT LOSE A READ THAT ALREADY HAPPENED. The narration
  // is still returned to the caller for the trace.
  const { deps } = fakeDeps({});
  deps.emit = async () => { throw new Error("narration refused (403)"); };
  const out = await runSupervisedRead({ source: "mail", startUrl: "https://mail.google.com/", deps });
  check("a refused POST does not fail the read", out.ok, JSON.stringify(out));
  check("the lines are still returned", out.lines.length > 0);
}

// ---------------------------------------------------------------------------
// The wiring in background.js, checked by reading it — the same style
// `check_never_foreground.mjs` uses, because these are static properties.
// ---------------------------------------------------------------------------
{
  const { readFileSync } = await import("node:fs");
  const { join, dirname } = await import("node:path");
  const { fileURLToPath } = await import("node:url");
  const ext = join(dirname(fileURLToPath(import.meta.url)), "..");
  const bg = readFileSync(join(ext, "background.js"), "utf8");

  // THE LANE MUST BE NAMED IN THE POLL. `research_lane.pb.js` hides
  // supervised reads from any queued poll that does not mention `lane`,
  // precisely so an old extension cannot claim one and run it through the full
  // action vocabulary.
  check("the supervised poll names its lane explicitly",
    /lane="supervised_read"/.test(bg));
  // AND THE DISPATCH MUST INTERCEPT BEFORE THE agent_goal REWRITE. If this
  // ordering ever inverts, a read becomes a click-and-type loop inside
  // somebody's mailbox.
  const guardAt = bg.indexOf('job.lane === "supervised_read"');
  const rewriteAt = bg.indexOf('goal: "agent_goal" }, { ...params, task }');
  check("a supervised read is intercepted before the agent_goal rewrite",
    guardAt > 0 && guardAt < rewriteAt, `guard ${guardAt}, rewrite ${rewriteAt}`);
  // NO DEBUGGER, so there is physically no path to a trusted click or
  // keystroke inside a read, whatever a model replies.
  const readBlock = bg.slice(bg.indexOf("function supervisedReadDeps"),
                             bg.indexOf("async function pushReadEvent"));
  check("the read is handed no debugger", !/chrome\.debugger/.test(readBlock), readBlock.slice(0, 80));
  check("the read is handed no way to click or type",
    !/trustedClick|typeText|dispatchKeyEvent/.test(readBlock));
  // EVERY NARRATION EVENT CARRIES THE JOB ID, because guard.pb.js requires it
  // and the phone filters on it.
  const emitBlock = bg.slice(bg.indexOf("async function pushReadEvent"),
                             bg.indexOf("async function runSupervisedReadJob"));
  check("narration events carry the job id in goal", /goal: job\.id/.test(emitBlock));
  check("narration events carry the owner", /owner_ref: ownerRef/.test(emitBlock));
  // THE TERMINAL WRITE MUST NOT LOOK LIKE A CLAIM. The backend's lease guard
  // treats the mere presence of a `claimed_by` key as a claim attempt and 403s
  // it once `watching_until` has lapsed — which is exactly when the abort path
  // writes its ending. Tidying this into the release shape used everywhere
  // else (`{status, claimed_by: "", claimed_at: null}`) would leave the row
  // stuck at `running` behind a 403 nobody reads.
  const runner = bg.slice(bg.indexOf("async function runSupervisedReadJob"),
                          bg.indexOf("async function runJob(job)"));
  const ends = runner.match(/updateJob\(job\.id, \{[^}]*\}/g) || [];
  check("every ending this runner writes claims nothing",
    ends.length > 0 && ends.every((w) => !/claimed_by|claimed_at/.test(w)),
    JSON.stringify(ends));
}

if (failures) { console.error(`test_supervised_read: ${failures} failed`); process.exit(1); }
console.log("test_supervised_read: all passed");
