// THE OBSERVER — the extension side of the second hand.
//
// After a browser step it answers exactly two questions: WHICH APP was that,
// and WAS IT A WRITE. That is all the router needs in order to go and ask the
// catalog "was there an API for what just happened?", and it is deliberately
// far less than the extension could tell it. Everything else the browser hand
// sees — the page, its title, its text, request and response bodies, cookies,
// the rest of the address bar — is browsing activity about a person, and this
// module is the one place we promise never to keep it.
//
// THE PROMISE IS KEPT STRUCTURALLY, NOT BY A SCRUB ON THE WAY OUT. A URL is
// reduced to its registrable domain inside `observe()`, and the original string
// is dropped on the floor before anything is stored. There is no buffer of raw
// events for a later bug — a debug dump, a crash report, a new field on
// TraceSummary — to serialize. A redactor that runs on the way OUT is one
// forgotten field away from shipping a password-reset link to a server; a
// reducer that runs on the way IN cannot be, because by the time anything can
// read the store, the link does not exist any more.
//
// LAW 1: nothing in this file decides what anything MEANS. The HTTP method is
// an effect channel — the seatbelt exception in HARNESS-LAWS law 1 — and the
// public-suffix list below is string plumbing, parsing a host out of a name.
// Neither reads a human's words. "Is there an API for this app?" is asked
// later, of a model, by the router. The Observer only reports which domain and
// how many writes, and NOTHING routes on its numbers: they are evidence for
// learning, not a licence for a hand.
//
// Chrome Web Store Limited Use counts domains and URLs as browsing activity and
// requires a prominent in-UI disclosure plus an affirmative user action. We
// obey it while sideloaded too, because the day we stop being sideloaded is not
// the day to discover the copy was never written. `disclosureCopy()` at the
// bottom of this file is that text, and it is tested.

import type { Observer, TraceSummary } from "./contract.ts";

// ---------------------------------------------------------------------------
// WHAT THE OBSERVER IS ALLOWED TO BE TOLD.
// ---------------------------------------------------------------------------
// Injected plain objects, not chrome APIs: this is a spike module, and keeping
// the input a value rather than a global is what lets every test below run with
// no browser, no key and no network.

/** A top-level navigation or an SPA route change. */
export interface NavigationEvent {
  kind: "navigation";
  run_id: string;
  step_id: string;
  /** Absolute URL. Reduced to eTLD+1 inside `observe()` and then discarded —
   *  the Observer never stores this string. */
  url: string;
  /** Epoch ms. Used only to bound the step's wall clock. */
  at: number;
}

/** One observational request record, of the shape chrome.webRequest hands out. */
export interface RequestEvent {
  kind: "request";
  run_id: string;
  step_id: string;
  method: string;
  /** Absolute URL. Same treatment as above: reduced on arrival, never stored. */
  url: string;
  /** The individual HTTP status. Bucketed on arrival and never stored as a
   *  code, because "404 on accounts.google.com" is a fact about the owner's
   *  account and "one 4xx on google.com" is not. */
  status: number;
  at: number;
  /** How long the request took, if the caller measured it. */
  ms?: number;
  /** ACCEPTED AND IMMEDIATELY THROWN AWAY. The webRequest listener may already
   *  have computed a templated path ("/users/{id}/reset/{token}"), and it is
   *  cheaper to let it pass the field than to make every caller remember to
   *  strip it first. It is never stored: TraceSummary has no field for a path,
   *  and even a shape like "/password/reset/{token}" would tell a later reader
   *  which flow the owner was in. */
  path_shape?: string;
}

export type ObservedEvent = NavigationEvent | RequestEvent;

// ---------------------------------------------------------------------------
// eTLD+1 — PLUMBING, NOT MEANING.
// ---------------------------------------------------------------------------
// This list decides where the boundary falls between the registrar's part of a
// name and the site's part of it: `example.co.uk` has three labels and
// `example.com` has two, and there is no algorithm for that — only the list.
// It never decides what a site IS, what an owner MEANT, or which hand runs a
// step, so it is the same kind of object as the code that splits a timestamp.
// HARNESS-LAWS law 1 forbids a word list that decides MEANING; a reader who
// mistakes this for one should re-read that sentence and then this comment.
//
// Two concrete failures without it, in opposite directions. Take the last two
// labels blindly and `news.bbc.co.uk` becomes `co.uk` — every British site
// collapses into one bucket and the router can never tell one app from another.
// Keep the whole hostname instead and `mail.google.com`, `calendar.google.com`
// and `drive.google.com` are three different apps that in fact share one API
// connection, so the ledger never accumulates enough runs on any of them to
// leave rung 0.
//
// ICANN suffixes only, on purpose: private suffixes (`myshopify.com`,
// `atlassian.net`, `zendesk.com`) are deliberately LEFT OUT so that
// `acme.atlassian.net` reduces to `atlassian.net`. The question is "which app",
// and the tenant label is the owner's employer's name — exactly the kind of
// thing this module exists in order not to keep.
//
// HOW THIS LIST IS MAINTAINED, AND WHAT HAPPENS WHILE IT IS BEHIND.
// It is a hand-cut copy of the ICANN DOMAINS section of
// https://publicsuffix.org/list/public_suffix_list.dat, taken 2026-09-05. To
// refresh it: take that section, keep the two-label entries, drop the wildcards
// and the exceptions, and re-run test/observer.test.ts.
//
// A copy is behind the day it is taken, and until 2026-09-05 being behind was
// SILENT: an omitted suffix made `registrableDomain` return the suffix itself
// as if it were a site, so a Greek bank and a Greek clinic both came back as
// "com.gr" and merged into one app — verbatim the failure this list exists to
// prevent, committed by the list's own gap. It is no longer silent:
// `looksLikeUnknownSuffix` below spots the SHAPE of a suffix this list has not
// heard of, and the Observer reports the host as unknown instead of guessing.
// Adding a suffix here turns an unknown back into a named app; forgetting to
// costs a name, never a wrong name.
const MULTI_LABEL_SUFFIXES: ReadonlySet<string> = new Set([
  // uk
  "co.uk", "org.uk", "ac.uk", "gov.uk", "me.uk", "net.uk", "sch.uk", "ltd.uk", "plc.uk",
  // au
  "com.au", "net.au", "org.au", "edu.au", "gov.au", "id.au", "asn.au",
  // nz
  "co.nz", "net.nz", "org.nz", "govt.nz", "ac.nz", "school.nz",
  // jp
  "co.jp", "or.jp", "ne.jp", "ac.jp", "go.jp", "ad.jp", "ed.jp", "gr.jp", "lg.jp",
  // br
  "com.br", "net.br", "org.br", "gov.br", "edu.br",
  // cn / hk / tw
  "com.cn", "net.cn", "org.cn", "gov.cn", "edu.cn", "ac.cn",
  "com.hk", "org.hk", "edu.hk", "gov.hk", "com.tw", "org.tw", "gov.tw",
  // in
  "co.in", "net.in", "org.in", "gen.in", "firm.in", "ind.in", "gov.in", "ac.in", "edu.in",
  // za
  "co.za", "org.za", "net.za", "gov.za", "ac.za",
  // europe, middle east
  "co.il", "org.il", "ac.il", "gov.il",
  "com.tr", "org.tr", "net.tr", "gov.tr", "edu.tr",
  "com.pl", "net.pl", "org.pl", "gov.pl", "edu.pl",
  "com.ua", "co.ua", "in.ua", "org.ua", "gov.ua",
  "com.ru", "org.ru", "net.ru",
  "com.es", "org.es", "gob.es", "com.pt", "gov.pt",
  "co.at", "or.at", "gv.at", "co.no", "co.dk", "co.hu",
  // americas
  "com.mx", "org.mx", "gob.mx", "com.ar", "net.ar", "org.ar", "gob.ar",
  "com.co", "gov.co", "com.pe", "com.ve", "com.ec", "com.uy",
  // asia-pacific, africa
  "com.sg", "edu.sg", "gov.sg", "com.my", "org.my", "gov.my",
  "co.th", "in.th", "go.th", "ac.th", "co.id", "or.id", "go.id", "web.id",
  "co.kr", "or.kr", "ne.kr", "go.kr", "re.kr", "com.ph", "gov.ph",
  "com.sa", "com.eg", "com.ng", "co.ke", "com.gh",
  // Added 2026-09-05, all for the same reason: every one of these TLDs is on
  // FLAT_TWO_LETTER_TLDS below, and a TLD may only be called flat once the
  // structured names its registry really does sell are carried here. Otherwise
  // "flat" would be a licence to merge the handful of sites that do sit under a
  // real suffix there.
  "com.io",
  "com.ai", "net.ai", "org.ai", "off.ai",
  "co.me", "net.me", "org.me", "edu.me", "ac.me", "gov.me",
  "net.co", "org.co", "edu.co", "mil.co", "nom.co",
  "com.sh", "net.sh", "org.sh", "gov.sh", "mil.sh",
  "co.gg", "net.gg", "org.gg",
  "com.ly", "net.ly", "org.ly", "gov.ly", "edu.ly", "sch.ly", "med.ly", "plc.ly", "id.ly",
  "com.fr", "asso.fr", "gouv.fr", "nom.fr", "prd.fr", "tm.fr",
  "ac.be",
]);

// TWO-LETTER TLDS WHOSE REGISTRY SELLS AT THE SECOND LEVEL.
//
// The other half of the shape rule, and the half it was missing. Under `.uk` a
// registrant buys `example.co.uk`, so a label like `co` sitting second-to-last
// really might be a suffix. Under `.de` a registrant buys `web.de` outright:
// there is nothing above it to be unsure about, and `looksLikeUnknownSuffix`
// firing there is not a cautious answer, it is a wrong one.
//
// This is the same kind of object as the suffix list — string plumbing about
// the shape of a NAME, never about meaning — and it has the same weakness: it
// is hand-cut against the ICANN section of publicsuffix.org, it is behind the
// day it was written (2026-09-05), and nothing in this session fetched it, so
// treat it as one reader's reading of that file rather than a copy of it. Two
// rules for editing it, because the two directions cost different things:
//   - LEAVING a flat TLD out costs a NAME. Every site under it whose own second
//     label happens to be a registry word is reported as unknown. That is the
//     safe direction and it is where the list starts.
//   - PUTTING a structured TLD in costs a WRONG name — every site under its
//     suffixes merges into one app, which is the failure the whole list exists
//     to prevent. So a TLD goes in only after the structured names its registry
//     does sell are carried in MULTI_LABEL_SUFFIXES above, in the same diff.
const FLAT_TWO_LETTER_TLDS: ReadonlySet<string> = new Set([
  // Sold worldwide as generic names, whatever country they were issued to. This
  // is the generation the apps this spike routes to actually live on, and the
  // shape rule was wrong about every one of them.
  "io", "ai", "tv", "me", "co", "sh", "gg", "ly",
  // Registries with no second level at all: a registrant buys the name itself.
  "de", "nl", "ch", "li", "cz", "sk", "si", "fi", "lu", "eu",
  // Sold at the second level, with a short structured list beside it that is
  // carried above. Canada's is its province codes (`ab.ca`, `gc.ca`), none of
  // which is a label this rule looks for, so it needed nothing added.
  "fr", "be", "ca",
]);

// THE SHAPE OF A SUFFIX WE HAVE NOT HEARD OF.
//
// Every entry in the suffix list is one of these labels followed by a
// two-letter country code. So when a hostname's last two labels have that same
// shape, are NOT in the list, and sit under a TLD whose registry organises a
// second level at all, the honest reading is "this is probably a public suffix
// the copy is missing", not "this is the site". Reporting it as the site is the
// merge-everything-together failure; reporting it as unknown costs a name.
//
// This is plumbing about the shape of a NAME, not about meaning: it never reads
// a word a human wrote and never decides which hand runs anything.
//
// THE COST, RESTATED 2026-09-05 BECAUSE THE OLD PARAGRAPH UNDERSOLD IT BADLY.
// It claimed the price was "one host lost on an unusual name" and named
// `www.example.co.it` as that host. Both halves were wrong. `co.it` is Como
// province and IS in the real public suffix list, so that example is the rule
// being RIGHT; and the price was never one host. Until the FLAT_TWO_LETTER_TLDS
// gate below, the rule fired on ANY of the labels above under ANY two-letter
// TLD, so `web.de`, `id.me`, `store.io` and `web.tv` — real sites on registries
// that have no second level to be unsure about — were all refused, and on those
// TLDs the rule was wrong every single time it fired.
//
// WHAT IS STILL PAID, honestly, because it is not nothing. A ccTLD can organise
// a second level AND sell directly at it: `.uk` has done both since 2014, and
// so do `.jp`, `.pl`, `.ru` and `.es`. Under those, a company whose own name is
// a registry word — `store.uk`, `web.pl` — is indistinguishable from a suffix
// this copy has not heard of, and it still loses its name. That is one real
// company per registry word per structured ccTLD, and it is still the right
// trade: a lost name costs a missed API suggestion, a guessed one merges a bank
// and a clinic into a single app. Pinned by the test named "the rule's own
// cost, written down rather than discovered", which asserts all three cases.
const SUFFIX_HEAD_LABELS: ReadonlySet<string> = new Set([
  "ac", "ad", "asn", "biz", "co", "com", "ed", "edu", "firm", "gen", "go", "gob",
  "gouv", "gov", "govt", "gr", "gv", "id", "in", "ind", "info", "lg", "ltd", "me",
  "mil", "name", "ne", "net", "nhs", "nom", "or", "org", "plc", "police", "pp",
  "pro", "re", "sch", "school", "store", "tm", "web",
]);

const TWO_LETTER_TLD = /^[a-z]{2}$/;

function looksLikeUnknownSuffix(labels: readonly string[]): boolean {
  const tld = labels[labels.length - 1] ?? "";
  const head = labels[labels.length - 2] ?? "";
  if (!TWO_LETTER_TLD.test(tld)) return false;
  // Nothing sits between a name and this registry, so there is no boundary to
  // be unsure about and no reason to withhold the name. Without this line the
  // rule refused `web.de` and `id.me` — whole sites, on registries with no
  // second level — and did it every time it fired on those TLDs.
  if (FLAT_TWO_LETTER_TLDS.has(tld)) return false;
  return SUFFIX_HEAD_LABELS.has(head);
}

// A dotted quad is a host, not a name with a registrar inside it, so the suffix
// walk must not run over it: `192.168.1.10` would otherwise reduce to `1.10`,
// which is not a thing, and every LAN address in the house would merge into one
// bucket. String plumbing, same as the list above.
const IPV4 = /^(?:\d{1,3}\.){3}\d{1,3}$/;

/**
 * What the Observer could make of a URL. THREE states, not two, because
 * "there is no site here" and "there is a site and I cannot name it" get
 * different treatment at ingest, and a single `null` hid the difference.
 *
 * - `none`    — a `chrome-extension://`, `data:` or `blob:` URL is the
 *               extension's own plumbing rather than a site the owner visited,
 *               and an unparseable string is not evidence of anything. The
 *               whole event is dropped, counts included: there was no request
 *               to a site for a count to be about.
 * - `unnamed` — a real http(s) request under a public suffix this file's copy
 *               does not carry. The request HAPPENED, so its read/write/status
 *               counts are kept; only the name is withheld. Guessing here is
 *               what merged unrelated sites into one app.
 * - `named`   — the registrable domain.
 *
 * A made-up host is worse than a missing one either way: the router would go
 * shopping for an API for an app that was never touched.
 */
export type HostReading =
  | { kind: "named"; host: string }
  | { kind: "unnamed" }
  | { kind: "none" };

const NO_SITE: HostReading = { kind: "none" };
const UNNAMEABLE: HostReading = { kind: "unnamed" };

export function readHost(url: string): HostReading {
  if (typeof url !== "string" || url.length === 0) return NO_SITE;

  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return NO_SITE;
  }

  // Only the web. See the doc comment above for why the rest is dropped whole.
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return NO_SITE;

  // NOTE what is read here and what is not: `hostname` alone. Not `pathname`,
  // not `search`, not `hash`, and not `href` or `host` — a URL of the form
  // https://user:token@example.com/ carries a credential in the authority, and
  // `hostname` leaves it behind where `href` would carry it straight through.
  let host = parsed.hostname.toLowerCase();
  // A fully qualified "google.com." is the same site as "google.com"; keeping
  // both would split one app's evidence across two rows in the ledger.
  if (host.endsWith(".")) host = host.slice(0, -1);
  if (host.length === 0) return NO_SITE;

  // IPv6 arrives from `hostname` already bracketed ("[::1]"). Keep the literal:
  // it names the host as precisely as anything can, and dropping it would hide
  // requests from the counts rather than anonymise them.
  if (host.startsWith("[") || IPV4.test(host)) return { kind: "named", host };

  const labels = host.split(".");
  // Two labels is the whole name the browser was given and no boundary is being
  // chosen, so there is nothing to be unsure about. "localhost" lands here too.
  if (labels.length <= 2) return { kind: "named", host };

  const lastTwo = labels.slice(-2).join(".");
  if (MULTI_LABEL_SUFFIXES.has(lastTwo)) return { kind: "named", host: labels.slice(-3).join(".") };
  if (looksLikeUnknownSuffix(labels)) return UNNAMEABLE;
  return { kind: "named", host: lastTwo };
}

/**
 * The registrable domain of an absolute URL, or `null` if there is not one.
 *
 * `null` folds the two "cannot name it" readings together for callers that only
 * want a name. Anything that must act differently on them — `observe()` does,
 * because an unnameable request still has to be COUNTED — reads `readHost`.
 */
export function registrableDomain(url: string): string | null {
  const reading = readHost(url);
  return reading.kind === "named" ? reading.host : null;
}

// ---------------------------------------------------------------------------
// WRITE vs READ — an effect channel, which is the one thing pattern matching is
// allowed to look at.
// ---------------------------------------------------------------------------
// The contract's rule, verbatim: a write is a mutating method that came back
// 2xx during the step; reads are the rest. "The rest" genuinely includes a POST
// that 403'd — nothing was written, so calling that a write would teach the
// router that an app it cannot reach is an app it is succeeding at, and the
// first API suggestion the owner ever saw would be for a login he does not
// have.
//
// An unrecognised method (a custom verb, a WebDAV MKCOL) lands in `reads`. That
// under-claims writes, and under-claiming is the safe direction HERE for a
// reason worth stating out loud: these counts feed LEARNING — "there was an API
// for that" — and never licensing. A step's side effect comes from the
// planner's CapabilitySignature and the judge's verdict, not from this file, so
// a miscount here costs a missed API suggestion and can never cost a wrong
// action.
const MUTATING_METHODS: ReadonlySet<string> = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/** Buckets, never codes, and always in this order so two identical traces
 *  serialize to identical bytes. `other` catches the status-less request — a
 *  DNS failure or an aborted fetch arrives as 0 — which still has to be
 *  counted: dropping it would make a step that died on the network look like a
 *  step where nothing happened, and a silence that reads as calm is how the
 *  ears stayed deaf for thirty hours. */
const STATUS_BUCKETS = ["1xx", "2xx", "3xx", "4xx", "5xx", "other"] as const;

function statusBucket(status: unknown): string {
  const n = Number(status);
  if (!Number.isFinite(n) || n < 100 || n >= 600) return "other";
  return `${Math.floor(n / 100)}xx`;
}

// ---------------------------------------------------------------------------
// THE STORE — counters, never events.
// ---------------------------------------------------------------------------
// One accumulator per (run, step), and inside it one counter row per DISTINCT
// registrable domain the step touched.
//
// WHAT THAT DOES AND DOES NOT GROW WITH, said precisely, because the previous
// version of this comment claimed the store did not grow at all and that was
// false. It does not grow with the number of REQUESTS: a step that fires ten
// thousand XHRs costs the same as one that fires two. It DOES grow with the
// number of distinct domains one step touched — a page's third parties, tens at
// worst. Those rows are working memory for `principalHost` and they never leave
// the class: `summarize` reduces them to ONE host, and the whole tally is
// released when the step is forgotten or falls off MAX_RETAINED_STEPS.
interface HostTally {
  /** Top-level navigations. The strongest evidence of which document the step
   *  was actually in — a third-party subresource is never one. */
  navs: number;
  /** Mutating requests that came back 2xx. The effect the router is asking
   *  about. */
  writes: number;
  /** Every request, whatever it did. The last resort, and only that. */
  requests: number;
}

interface StepTally {
  hosts: Map<string, HostTally>;
  writes: number;
  reads: number;
  status: Map<string, number>;
  firstAt: number;
  lastEnd: number;
  timed: boolean;
}

/**
 * How many (run, step) tallies the Observer will hold at once.
 *
 * WHY THERE IS A CAP AT ALL. `forget()` is a request to a caller, and until
 * 2026-09-05 no caller made it: the extension's service worker lives for hours
 * across dozens of runs, so the Map was an unbounded accumulation of where the
 * owner has been — the one thing this module promises not to keep. A cap keeps
 * that promise without depending on anybody remembering, the same way the
 * reduce-on-ingest rule keeps the URL promise without depending on a scrubber.
 *
 * THE COST, AND WHY IT IS NO LONGER SILENT. A step evicted before anyone
 * summarized it comes back empty, and an empty summary is byte-identical to a
 * step where nothing happened: `browserOutcome` reads `duration_ms` 0 off it
 * and files a ledger row saying the browser hand did the work instantly. A hand
 * that looks instant is the hand rule 5 prefers, so a silent eviction does not
 * merely lose a row — it tilts the comparison the whole ladder exists to
 * settle, in the direction of the hand that failed to report. So the cap now
 * leaves a mark: `wasEvicted()` separates the two empty summaries and
 * `evictions` counts them. A caller filing a duration is expected to ask.
 *
 * Eviction is least-recently-OBSERVED, so the step currently receiving events
 * can never be the one evicted, and 64 is several times the length of any agent
 * run this spike has driven. A caller that knows a step is finished should use
 * `summarizeAndForget` and never meet the cap at all.
 */
export const MAX_RETAINED_STEPS = 64;

/**
 * How many eviction marks are kept.
 *
 * The marks are run and step ids — the caller's own labels, never a host, a
 * count or a clock — so they are not the record of where the owner has been
 * that the cap exists to prevent. They are still held state, though, and this
 * module's rule is that held state has an end: an unbounded set of them would
 * be the same leak one field narrower. When a mark falls off, `evictions` still
 * counts the eviction, so a caller can always learn that the Observer dropped
 * SOMETHING even once it can no longer say which step.
 */
const MAX_EVICTION_MARKS = MAX_RETAINED_STEPS;

// NUL cannot occur in either id, so this cannot collide the way a ":" join
// would: run "a:b" step "c" and run "a" step "b:c" are different steps and must
// stay different rows. Written as a char code rather than an escape so the
// separator cannot be mistaken for a printable character by a later reader.
const KEY_SEP = String.fromCharCode(0);

function tallyKey(runId: string, stepId: string): string {
  return `${runId}${KEY_SEP}${stepId}`;
}

// THE ROW AN UNNAMEABLE SITE COMPETES AS.
//
// A host under a suffix this file's copy does not carry cannot sit the contest
// out. If it did, a step that ran in a Greek bank whose every third party IS
// nameable would be reported as having happened in the CDN — a bystander named
// as the app, which sends the router shopping for an API the owner never
// touched. So the unnameable site gets a counter row like any other and wins on
// the same precedence. If it wins, `summarize` reports no host at all.
//
// NUL, because a hostname can never contain one, so this key can never collide
// with a real site. It also sorts before every real host, which means rule 4
// gives a dead tie to "unknown" — the safe direction: not knowing which app it
// was beats naming the wrong one.
const UNNAMED_HOST_KEY = String.fromCharCode(0);

function emptyTally(): StepTally {
  return {
    hosts: new Map<string, HostTally>(),
    writes: 0,
    reads: 0,
    status: new Map<string, number>(),
    firstAt: 0,
    lastEnd: 0,
    timed: false,
  };
}

/**
 * WHICH APP WAS THIS STEP IN — one answer, chosen by a stated precedence.
 *
 * The old summary listed every registrable domain the step touched. On a modern
 * page that is the app plus its CDN, its fonts, its analytics, its error
 * reporter and whoever bought the ad slot: a description of the PAGE, and
 * through it of the person, when the router asked one question and needs one
 * answer. `TraceSummary.hosts` stays an array because contract.ts was fixed
 * before the parts were built and is not ours to change; what goes into it is
 * at most one element.
 *
 * The precedence, most decisive first:
 *   1. the most TOP-LEVEL NAVIGATIONS — the document the step ran in, which a
 *      third-party subresource structurally cannot be;
 *   2. the most WRITES — a mutating 2xx is the app acting, and it is the effect
 *      the router is about to go shopping for an API for;
 *   3. the most REQUESTS — volume, and only when nothing better exists;
 *   4. the lexicographically first host — so a tie breaks the same way every
 *      time. The ledger hashes what it is given, and a tie broken by whichever
 *      XHR finished first would make two identical traces two different rows.
 *
 * A site the suffix list cannot name COMPETES in that contest under
 * UNNAMED_HOST_KEY rather than sitting it out, and winning it means the summary
 * carries no host. Sitting it out is how a step that ran in an unnameable app
 * would have been reported as having happened in the CDN that app loads.
 *
 * WHAT IT COSTS, IN FULL, BECAUSE THE DISCLOSURE IS WRITTEN FROM THIS
 * PARAGRAPH. A step that genuinely touched two apps reports one, and the other
 * app's evidence is lost. And rule 1 is the ONLY rule that cannot name a
 * bystander — a company whose font or advert a page loads never becomes the
 * document. Each of the other three can, and all three are ordinary traces,
 * not edge cases:
 *   - rule 2 — a traffic-counting beacon is a POST that comes back 2xx, so on a
 *     step that only READ a page (all GETs) the counter has the only write and
 *     takes the slot;
 *   - rule 3 — with no navigation and no write, the font or advert host that
 *     made twelve requests beats the app that made one;
 *   - rule 4 — a dead tie sorts alphabetically, and "adnxs.com" comes before
 *     "notion.so".
 * All of it is affordable because NOTHING ROUTES ON THIS: `browserOutcome`
 * takes the app from its caller and is forbidden by name from deriving it from
 * here (src/index.ts). The hosts field is evidence for learning, and the
 * smallest footprint that still answers "which app" beats a complete list of
 * everything the owner's page loaded.
 *
 * WHAT IT DOES NOT LET YOU SAY. `disclosureCopy()` may not promise the one name
 * is always the site the step was working in. It did, twice, and both times the
 * sentence was read off this function's INTENT. The three rules above are
 * driven by tests in test/observer.test.ts that the copy is pinned against.
 */
function principalHost(hosts: ReadonlyMap<string, HostTally>): string | null {
  let bestHost: string | null = null;
  let best: HostTally | null = null;
  for (const [host, tally] of hosts) {
    if (best === null || outranks(host, tally, bestHost as string, best)) {
      bestHost = host;
      best = tally;
    }
  }
  return bestHost === UNNAMED_HOST_KEY ? null : bestHost;
}

function outranks(host: string, a: HostTally, otherHost: string, b: HostTally): boolean {
  if (a.navs !== b.navs) return a.navs > b.navs;
  if (a.writes !== b.writes) return a.writes > b.writes;
  if (a.requests !== b.requests) return a.requests > b.requests;
  return host < otherHost;
}

export class TraceObserver implements Observer {
  #steps = new Map<string, StepTally>();
  #paused = false;
  /** Steps the cap threw away before anybody read them. Ids only. */
  #evictionMarks = new Set<string>();
  #evictions = 0;

  /** The pause switch the disclosure copy promises. It drops events at INGEST,
   *  not at summarize: a pause that quietly keeps recording and hides the
   *  result later is not a pause, it is a lie with a checkbox, and the whole
   *  Limited Use disclosure rests on this one being true. */
  pause(): void {
    this.#paused = true;
  }

  resume(): void {
    this.#paused = false;
  }

  get paused(): boolean {
    return this.#paused;
  }

  observe(event: ObservedEvent): void {
    if (this.#paused) return;
    // Types are stripped, not checked, so every field a caller could get wrong
    // is guarded at runtime. The extension feeds this from a chrome.webRequest
    // listener whose payload shape changes between Chrome versions; a thrown
    // TypeError inside a listener kills the listener, and the Observer would go
    // silently deaf for the rest of the browser session.
    if (event === null || typeof event !== "object") return;

    const runId = typeof event.run_id === "string" ? event.run_id : "";
    const stepId = typeof event.step_id === "string" ? event.step_id : "";
    // An event with no run or no step happened outside an agent run, or the
    // caller lost track of which step it belongs to. Either way there is no
    // honest place to put it, and attributing it to "the last step we saw"
    // would fold the owner's own browsing into an agent trace — breaking the
    // exact sentence the disclosure makes. Drop it.
    if (runId === "" || stepId === "") return;

    const reading = readHost((event as { url?: unknown }).url as string);
    // No site at all: extension plumbing, or a broken URL. Nothing happened
    // that a count could be about. See `HostReading` — `unnamed` is the other
    // case and it is NOT dropped, because that request really was made.
    if (reading.kind === "none") return;

    const tally = this.#touch(tallyKey(runId, stepId));
    const row = hostRow(tally, reading.kind === "named" ? reading.host : UNNAMED_HOST_KEY);

    // The step's wall clock is the span from the first thing observed to the
    // last thing that finished, so a slow request that started early and
    // returned late still counts for its whole length. Events can arrive out of
    // order — chrome.webRequest fires onCompleted in completion order, not
    // start order — so both ends are min/max rather than first/last seen.
    const at = Number((event as { at?: unknown }).at);
    if (Number.isFinite(at)) {
      const ms = Number((event as { ms?: unknown }).ms);
      const end = at + (Number.isFinite(ms) && ms > 0 ? ms : 0);
      if (!tally.timed) {
        tally.firstAt = at;
        tally.lastEnd = end;
        tally.timed = true;
      } else {
        if (at < tally.firstAt) tally.firstAt = at;
        if (end > tally.lastEnd) tally.lastEnd = end;
      }
    }

    // A navigation contributes its host and its clock and NOTHING to the
    // read/write counts. The page load it starts arrives separately as a
    // request event; counting both would double every top-level GET and make
    // every step look busier than it was. It does count toward WHICH host the
    // step was in, and decisively — see `principalHost`.
    if (event.kind !== "request") {
      if (event.kind === "navigation") row.navs += 1;
      return;
    }

    const method = String((event as RequestEvent).method ?? "").trim().toUpperCase();
    const bucket = statusBucket((event as RequestEvent).status);
    tally.status.set(bucket, (tally.status.get(bucket) ?? 0) + 1);

    const isWrite = MUTATING_METHODS.has(method) && bucket === "2xx";
    if (isWrite) tally.writes += 1;
    else tally.reads += 1;

    row.requests += 1;
    if (isWrite) row.writes += 1;
  }

  /** Convenience for a caller that already holds a batch, and for tests. */
  observeAll(events: readonly ObservedEvent[]): void {
    for (const event of events) this.observe(event);
  }

  summarize(runId: string, stepId: string): TraceSummary {
    const tally = this.#steps.get(tallyKey(runId, stepId));

    // An unknown step is an EMPTY summary, never a throw. The router asks after
    // every browser step, including ones where the page made no request at all
    // — a click that only moved the DOM, or a step the pause switch swallowed.
    // Throwing there would turn "nothing happened" into a failed task in front
    // of the owner.
    if (!tally) {
      return {
        run_id: runId,
        step_id: stepId,
        hosts: [],
        writes: 0,
        reads: 0,
        status: {},
        duration_ms: 0,
      };
    }

    // ONE host, or none. See `principalHost` for the precedence and its cost.
    // An empty list is the honest answer when the step's own document sits
    // under a public suffix this file's copy does not carry: unknown, not
    // guessed, and not quietly replaced by whichever CDN it happened to load.
    const principal = principalHost(tally.hosts);

    const status: Record<string, number> = {};
    for (const bucket of STATUS_BUCKETS) {
      const n = tally.status.get(bucket);
      if (n !== undefined) status[bucket] = n;
    }

    return {
      run_id: runId,
      step_id: stepId,
      hosts: principal === null ? [] : [principal],
      writes: tally.writes,
      reads: tally.reads,
      status,
      duration_ms: tally.timed ? Math.max(0, tally.lastEnd - tally.firstAt) : 0,
    };
  }

  /** Read a finished step and release it in the same breath.
   *
   *  THIS IS THE CALL A FINISHED STEP SHOULD USE. `summarize` stays a plain
   *  read because the router may summarize the same step twice when a retry
   *  lands, but the last reader of a finished step is holding the only thing
   *  keeping its trace alive, and a trace nobody will read again is exactly the
   *  accumulation this module promises not to have. */
  summarizeAndForget(runId: string, stepId: string): TraceSummary {
    const summary = this.summarize(runId, stepId);
    this.#steps.delete(tallyKey(runId, stepId));
    return summary;
  }

  /** Drop everything held for a finished run. The extension's service worker
   *  can live for hours across dozens of runs; without this the Map is a leak
   *  that also happens to be a slowly growing record of where the owner has
   *  been — the one thing this module promises not to accumulate. */
  forget(runId: string): void {
    const prefix = `${runId}${KEY_SEP}`;
    for (const key of this.#steps.keys()) {
      if (key.startsWith(prefix)) this.#steps.delete(key);
    }
    // The marks are held state too, and held state has an end. `evictions`
    // deliberately does not move: a run being forgotten does not un-happen the
    // eviction, and a counter that could go down would let a leak hide behind
    // a tidy-up.
    for (const key of this.#evictionMarks) {
      if (key.startsWith(prefix)) this.#evictionMarks.delete(key);
    }
  }

  /**
   * Was this step's trace thrown away by the cap before anybody read it?
   *
   * THE QUESTION A CALLER FILING A DURATION HAS TO ASK. An evicted step and a
   * step where nothing happened summarize identically — no hosts, no counts,
   * `duration_ms` 0 — and `browserOutcome` turns the second one into a ledger
   * row claiming the browser hand finished instantly. That is not a missing
   * row, it is a fast one, and rule 5 promotes hands that look fast.
   *
   * `false` is not proof of the opposite: the marks are capped
   * (MAX_EVICTION_MARKS), so a very old eviction can itself have fallen off.
   * `evictions` is the total that never falls off.
   */
  wasEvicted(runId: string, stepId: string): boolean {
    return this.#evictionMarks.has(tallyKey(runId, stepId));
  }

  /** How many steps this Observer has dropped, ever. Monotonic on purpose —
   *  see `forget`. */
  get evictions(): number {
    return this.#evictions;
  }

  /** How many evictions can still be named. Lower than `evictions` once the
   *  marks have wrapped; exposed so a test can prove the marks are bounded
   *  rather than trusting the constant. */
  get markedEvictions(): number {
    return this.#evictionMarks.size;
  }

  /** Which steps are currently held, for a caller summarizing a whole run.
   *  Ids only — the tallies never leave the class except through summarize. */
  steps(): Array<{ run_id: string; step_id: string }> {
    return [...this.#steps.keys()].map((key) => {
      const cut = key.indexOf(KEY_SEP);
      return { run_id: key.slice(0, cut), step_id: key.slice(cut + 1) };
    });
  }

  /** Fetch a step's tally, creating it if new, and move it to the young end of
   *  the Map so eviction is least-recently-OBSERVED. A Map iterates in
   *  insertion order, so delete-then-set is the whole of the bookkeeping — and
   *  it is what guarantees the live step, the one receiving events right now,
   *  is never the one thrown away. */
  #touch(key: string): StepTally {
    const existing = this.#steps.get(key);
    if (existing !== undefined) {
      this.#steps.delete(key);
      this.#steps.set(key, existing);
      return existing;
    }
    const fresh = emptyTally();
    this.#steps.set(key, fresh);
    while (this.#steps.size > MAX_RETAINED_STEPS) {
      const oldest = this.#steps.keys().next();
      if (oldest.done === true) break;
      this.#steps.delete(oldest.value);
      this.#mark(oldest.value);
    }
    return fresh;
  }

  /** Record that a step was dropped by the cap rather than read. Oldest mark
   *  out first, so the marks cannot become the accumulation the cap prevents. */
  #mark(key: string): void {
    this.#evictions += 1;
    this.#evictionMarks.add(key);
    while (this.#evictionMarks.size > MAX_EVICTION_MARKS) {
      const oldest = this.#evictionMarks.values().next();
      if (oldest.done === true) break;
      this.#evictionMarks.delete(oldest.value);
    }
  }
}

function hostRow(tally: StepTally, host: string): HostTally {
  const existing = tally.hosts.get(host);
  if (existing !== undefined) return existing;
  const fresh: HostTally = { navs: 0, writes: 0, requests: 0 };
  tally.hosts.set(host, fresh);
  return fresh;
}

export function createObserver(): TraceObserver {
  return new TraceObserver();
}

// ---------------------------------------------------------------------------
// THE DISCLOSURE.
// ---------------------------------------------------------------------------
// Chrome Web Store's Limited Use policy counts domains and URLs as browsing
// activity: collecting them requires a prominent in-UI disclosure and an
// affirmative user action, separate from the privacy policy. We write it now,
// while sideloaded, because the day a review rejects the listing is not the day
// to start drafting copy — and because the owner deserves to be told in the
// same words either way.
//
// The register is the owner's, not a lawyer's. "Request body" means nothing to
// him; "what you typed, what was sent, what came back" means exactly the same
// thing and he can check it against what he sees. Every clause below is a
// promise the code above actually keeps, and test/observer.test.ts walks the
// list one clause at a time — so a future edit that quietly drops the pause
// sentence, or the sentence about page text, fails a test instead of shipping.
//
// WHY THE SECOND PARAGRAPH IS UNCOMFORTABLE, AND STAYS. This copy has been
// wrong twice, both times by describing what `principalHost` is FOR instead of
// what it DOES. The first version implied every site a page touched; the
// replacement swore the one name was never one of the page's own advert, font
// or traffic-counting companies. `principalHost` has four rules and only the
// first — the most top-level navigations — structurally cannot name a
// bystander. Rule 2 hands the slot to whoever made a mutating 2xx, and a
// tracking beacon is a POST; rule 3 hands it to whoever made the most requests,
// which on a read-only step is the font host; rule 4 breaks a tie
// alphabetically, and "adnxs.com" sorts before "notion.so".
//
// Naming the app is what the whole Observer is for, and the three rules below
// rule 1 are the only thing that names it on a single-page app, where a step
// fires XHRs and never navigates — which is most agent steps in the tools this
// spike is about. Deleting them to make the simpler sentence true would leave
// the Observer able to answer "which app" only for full page loads: a guard
// that refuses everything, and an outage in the one feature the module exists
// for. Nothing routes on this field either, so a bystander's name costs a
// missed API suggestion and can never cost an action. So the code keeps its
// four rules and the COPY tells the truth about them — because a Limited Use
// disclosure that under-states what is collected is not a rough disclosure, it
// is a false one, and that is the direction the store and the owner both
// read as a lie. `test/observer.test.ts` drives all three rules and fails if
// this copy claims what they can break.
export function disclosureCopy(): string {
  return [
    "Anticipy keeps a short note of where it went in your browser.",
    "",
    "WHAT IT KEEPS. One site name for each thing it does - google.com,",
    "amazon.co.uk - plus a count of how many requests just looked at something",
    "and how many changed something, and whether they came back fine, refused,",
    "or broken. One name, never a list of every company a page talks to.",
    "",
    "THAT ONE NAME IS A BEST GUESS. Usually it is the site you would see in the",
    "address bar. But a page also talks to advert, font, hosting and",
    "visitor-counting companies while you are on it, and when one of those does",
    "more of the talking than the site itself, the name Anticipy keeps can be",
    "that company instead of the site. Sometimes it keeps no name at all. It is",
    "one name either way.",
    "",
    "WHAT IT NEVER KEEPS. What was on the page, the page title, the text on it,",
    "what you typed, what was sent, what came back, your cookies, and everything",
    "in the address bar after the site name. No full links. No search terms. A",
    "password reset link is a link, and it is never kept.",
    "",
    "WHEN IT RUNS. Only while Anticipy is running a task you asked for. When it",
    "is not working for you it is not looking, and it never watches your own",
    "browsing.",
    "",
    "WHY. So that after Anticipy has clicked its way through a site for you, it",
    "can notice the site has a proper connection available, and ask you once",
    "whether to use that instead. It is faster and it breaks less often.",
    "",
    "YOUR SWITCH. You can pause this in Settings and it stops the same second.",
    "Pausing does not stop Anticipy doing your tasks - it only stops the note.",
  ].join("\n");
}
