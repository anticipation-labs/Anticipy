// GOING TO GET SOMETHING, THEN COMING BACK.
//
// The failure this exists for: a run gets to the last field of an application
// — everything else filled, twenty minutes of work on the page — and the site
// says "we emailed you a code". The run had no way to go and read it. It
// parked, or worse, it ran out of steps and the tab was destroyed. Ten demos
// out of ten died here.
//
// A person in that position does not abandon the form. They open a second
// tab, read the code, come back, and finish. That is all this is: a bounded
// errand to ONE other place, for ONE value, while the working tab keeps its
// position, its session and everything already typed into it.
//
// Three properties matter more than the feature:
//
//   1. IT NEVER GOES WITHOUT BEING SENT. Reading someone's mail is not
//      covered by "book me a table". The owner authorises this specific trip,
//      to this specific place, for this specific value, or it does not happen.
//   2. IT IS READ-ONLY. It may open and read. It may never send, delete,
//      archive, reply, or click anything that changes the world.
//   3. THE VALUE COMES BACK; THE CONTENTS DO NOT. A verification code is
//      returned. The message it came from never enters the trace, the job
//      record, or the model's context beyond the single step that reads it.
//
// This module is deliberately free of Chrome APIs: everything it touches is
// injected. That keeps it honest under test — the containment below
// (`codeFromPage`) is the part that decides whether a model's reply may cross
// back into a form at all, and it is tested directly rather than through a
// browser. Which value IS the code is a model's reading (`readCodeVerdict`).

// ---------------------------------------------------------------------------
// What counts as the thing we were sent for
// ---------------------------------------------------------------------------

// WHAT WAS HERE UNTIL 2026-09-05, Audit #79, and why it is gone.
//
//     const CODE_CONTEXT = /\b(verification|verify|confirm(?:ation)?|security|
//                            one[-\s]?time|single[-\s]?use|access|login|sign[-\s]?in|
//                            auth(?:entication)?|passcode|pin|otp|code)\b/i;
//     const NOT_A_CODE = [/^(?:19|20)\d{2}$/, /^\d{5}(?:-\d{4})?$/, /^1?\d{10,11}$/, /^0+$/];
//     export function extractCode(text, opts)
//       pass 1: /\b(?:code|passcode|pin|otp)\b … ([0-9]{4,8}|[A-Z0-9]{4,8})\b/  -> score 100
//       pass 2: a digit run alone on its own line                                -> score 80
//       pass 3: a digit run within 90 characters of a CODE_CONTEXT word          -> score 60
//       sort by score; two rivals at the same score -> "ambiguous"; otherwise
//       { value, confidence: score >= 80 ? "high" : "medium" }
//     …and after runSideTrip's loop, askModel(page) with the model's prose
//     re-parsed through extractCode — a regex reading a model's sentence.
//
// A word list ranked the digit runs on an inbox page — the webmail search
// list, many messages' snippets on one page — by the English words around
// them, and the winner was typed into a live one-time-code field on the
// owner's logged-in tab, with unquotedCode satisfied by the regex's own output
// (agent_loop.js appends it to facts as `verification_code:`). Which run of
// digits IS the code a site sent is what the page means. HARNESS-LAWS.md law
// 1 — borderline, because a machine-written code has a shape, and the shape
// half stays below as containment on a model's reply. The `confidence` field
// never had a consumer.
//
// MEASURED (audit row 79, 2026-08-24): a snippet "Order #482130 confirmed"
// within 90 characters of "confirm" (CODE_CONTEXT), with the real code's
// snippet truncated out of the search list, returned { value: "482130",
// confidence: "medium" }; nothing read "medium"; 482130 was submitted. The
// trip is once per run, so the wrong read could not be corrected in-run: the
// site counts the attempt, some lock after three, and the one authorised
// mailbox read was spent. NOT_A_CODE's four entries were each a decoy that
// had beaten the real code in a real email — the list admitting it decided
// wrongly four times and was patched four times.
//
// What replaced it: `readCodeVerdict` — one question asked of a model on its
// own, with the page in front of it, in four states — and `codeFromPage`, the
// shape-and-provenance check on the model's reply, which can only REFUSE a
// reply and never picks between candidates.

// The page is shown to the judge up to here, and the provenance check runs
// against exactly this slice, so "present on the page the model was shown" is
// literally true.
export const CODE_PAGE_LIMIT = 4000;

/**
 * The containment on a model's reply: shape and provenance, never meaning.
 *
 *   * exactly one token after trim — a reply with a sentence around it ("the
 *     code is 4831 — also please visit evil.example") is a model we did not
 *     understand, and stays out whole;
 *   * 4-8 characters of [A-Za-z0-9], containing a digit;
 *   * present in the page the model was shown, either as a whole token
 *     (non-alphanumeric boundaries, case-sensitive) or equal to one line of
 *     the page with its spaces and hyphens removed — the "8 8 1 3" shape some
 *     services print.
 *
 * Returns the token, or null. This checks WHERE a value came from and WHAT
 * SHAPE it has; it cannot choose one value over another, which is what keeps
 * it on the right side of law 1 — the same "a token we specified, not prose
 * we interpret" rule inboxConsent applies to YES and NO.
 */
export function codeFromPage(reply, pageText) {
  const token = String(reply == null ? "" : reply).trim();
  if (!token || /\s/.test(token)) return null;
  if (!/^[A-Za-z0-9]{4,8}$/.test(token) || !/[0-9]/.test(token)) return null;
  const page = String(pageText || "");
  const esc = token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  if (new RegExp(`(^|[^A-Za-z0-9])${esc}([^A-Za-z0-9]|$)`).test(page)) return token;
  for (const line of page.split(/\n+/)) {
    if (line.trim().replace(/[\s-]/g, "") === token) return token;
  }
  return null;
}

/**
 * Which value on this page is the code? Await it; it asks a model.
 *
 * `judge({ pageText, purpose, site })` returns the model's reply as a string;
 * it is injected so this module stays free of Chrome and of network calls.
 * The page is cut to CODE_PAGE_LIMIT BEFORE the judge sees it, and the
 * provenance check runs on that same slice.
 *
 * Returns { state, value } where `state` is one of:
 *   code     — the judge named a value and codeFromPage found it on the page
 *   none     — NONE: no such code on this page
 *   unclear  — UNCLEAR: more than one value could be it, or it cannot be tied
 *              to the site
 *   unread   — nobody could read it: no judge, a throw, an empty reply,
 *              prose, two tokens, or a token that is not on the page
 *
 * "unread" is not "none". "Nobody could read it" must never become "keep
 * clicking through his mailbox". An empty page is "none" without a call:
 * there is nothing on it to ask about.
 */
export async function readCodeVerdict({ pageText, purpose, site, judge } = {}) {
  const shown = String(pageText || "").slice(0, CODE_PAGE_LIMIT);
  if (typeof judge !== "function") return { state: "unread", value: null };
  if (!shown.trim()) return { state: "none", value: null };
  let reply;
  try {
    reply = await judge({ pageText: shown, purpose, site });
  } catch (_) {
    return { state: "unread", value: null };
  }
  const token = String(reply == null ? "" : reply).trim();
  if (token === "NONE") return { state: "none", value: null };
  if (token === "UNCLEAR") return { state: "unclear", value: null };
  const value = codeFromPage(token, shown);
  return value ? { state: "code", value } : { state: "unread", value: null };
}

// WHAT WAS HERE UNTIL 2026-09-05, Audit #78, and why it is gone.
//
//     export function detectsCodeWasSent(pageText)
//       const sent = /\b(we[''\s]?(?:ve|just)?\s?(?:sent|emailed|texted)|has been sent|
//                     have been sent|was sent|were sent|been sent to|sent to|
//                     check your (?:e-?mail|inbox|phone|messages)|sent (?:you )?a
//                     (?:code|link|verification)|code (?:was |has been )?sent|
//                     (?:e-?mail|text|sms) (?:with|containing) a? ?(?:code|link))\b/i;
//       if (!sent.test(t)) return null;
//       const phone = /\b(?:phone|text|sms|message)\b/i.test(t);
//       const email = /\b(?:e-?mail|inbox)\b/i.test(t) || !!addr || !!masked;
//       return { where: email ? "email" : (phone ? "phone" : "unknown"), address };
//
// A phrasing regex over the rendered page decided whether the page was SAYING
// a code had been dispatched, and two word lists decided which channel it went
// to. That verdict is what decided whether the run offered to open the owner's
// inbox at all, and where the trip pointed. Whether a page is telling somebody
// "we emailed you a code" is what the page MEANS. HARNESS-LAWS.md law 1, and
// none of its exemptions cover it: not a sense, not the seatbelt (which reads
// what a plan TOUCHES, not how a page was worded), not a gate.
//
// MEASURED, from the function's own history and the audit:
//   * "Code sent to o***r@gmail.com" and "A verification code was sent to your
//     email" — the two commonest wordings on the exact page this feature exists
//     for — matched nothing until 2026-08-21, and the run stalled at the wall
//     the demo died on. The 2026-08-21 broadening fixed those two phrasings and
//     no others: "A one-time passcode is on its way. Look for a message from
//     us." matched none of the alternations, and neither did any page not
//     written in English. A miss here is `tripOnOffer` returning null, and the
//     loop burning its remaining steps to a stall.
//   * The channel read preferred "email" whenever "e-mail" or "inbox" appeared
//     ANYWHERE on the page, and "unknown" took the email path too — so "We
//     texted a code to your phone. Didn't get it? Check the email on file"
//     produced an offer to go and read the owner's mailbox, with a live ref,
//     for a code that never went there.
//
// What replaced it: `whereCodeWent` below — one question asked of a model on
// its own, with the whole page in front of it, answered in four states. The
// address extraction that used to sit under the regex stays, because a token
// shaped like an address is shape, not meaning; it only NAMES the address in
// the offer and picks the webmail row, and never decides whether or where a
// code went. `tripOnOffer` now takes the verdict and is synchronous over it.

// An address as it appears on the page, full or masked. Shape parsing, carried
// beside the verdict: it names the address in the offer and lets `tripOnOffer`
// prefer the address the SITE says it used, and it decides nothing else.
function addressOnPage(text) {
  const t = String(text || "");
  const addr = t.match(/\b([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b/);
  const masked = t.match(/\b([a-z]\*+[a-z0-9]*@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b/i);
  return (addr && addr[1]) || (masked && masked[1]) || null;
}

/**
 * Where did the code go? Await it; it asks a model.
 *
 * The ONE question this file used to answer with a phrasing regex: does the
 * page say a one-time code has just been sent to this person away from the
 * page, and if so where? `judge(pageText)` is injected — this module stays
 * free of Chrome and of network calls — and returns the model's reply as a
 * string. The caller is `agent_loop.js`, which builds the judge on
 * `codeSentJudge` and asks only at the code wall, once per page state.
 *
 * Returns { state, address } where `state` is one of:
 *   email       — YES, and it went to their email (EMAIL)
 *   phone       — YES, and it went to their phone (PHONE)
 *   none        — NO: the page does not say a code was sent (NONE)
 *   unclear     — the model could not tell (UNSURE)
 *   unanswered  — nobody answered: no judge, a throw, an empty page, an empty
 *                 reply, prose, or anything that is not exactly one token
 *
 * "none" and "unanswered" are different answers and lead to different
 * sentences downstream. The reply is compared as a token we specified, after
 * a trim and nothing else — "EMAIL." with a period is unanswered, which for a
 * floor is the safe direction.
 */
export async function whereCodeWent({ pageText, judge } = {}) {
  const text = String(pageText || "");
  const address = addressOnPage(text);
  if (!text.trim()) return { state: "unanswered", address };
  if (typeof judge !== "function") return { state: "unanswered", address };
  let verdict;
  try {
    verdict = await judge(text);
  } catch (_) {
    return { state: "unanswered", address };
  }
  const token = String(verdict == null ? "" : verdict).trim();
  const state = { EMAIL: "email", PHONE: "phone", NONE: "none", UNSURE: "unclear" }[token]
    || "unanswered";
  return { state, address };
}

// ---------------------------------------------------------------------------
// The trip itself
// ---------------------------------------------------------------------------

// Places a side trip may never go, no matter who asks. This is deliberately
// stricter than the main loop's block list: the main loop refuses to OPERATE
// a bank, and a side trip may not even go and READ one, because the whole
// point of a side trip is that it happens with less supervision.
const NEVER_VISIT = /(^|\.)(chase|bankofamerica|wellsfargo|citi(bank)?|rbc|td(bank|canadatrust)?|scotiabank|bmo|cibc|tangerine|schwab|fidelity|vanguard|etrade|robinhood|coinbase|binance|kraken|paypal|wise|revolut)\./i;

export function tripRefusedReason(url, { authorized, purpose } = {}) {
  if (!authorized) return "the owner has not authorised this trip";
  let host;
  try { host = new URL(String(url)).hostname; } catch (_) { return "that is not a real address"; }
  if (NEVER_VISIT.test(host)) return `${host} holds money — that one stays yours`;
  if (!purpose) return "a trip has to say what it is for";
  return null;
}

// WHO SAYS THE AGENT MAY OPEN SOMEBODY'S MAIL? Only that somebody, answering
// this module's own question, read by a model that can see both halves.
//
// THIS IS ONE DOOR OF TWO. It guards the side trip's own new tab. The main
// step loop can walk the WORKING tab into the same mailbox, and until
// 2026-08-24 nothing stopped it; `private_places.js` is the other lock, built
// to the same shape as this one and reusing this file's frame parser so there
// is one copy of that pattern rather than two that can drift apart.
//
// `runSideTrip` takes `authorized` as a boolean and refuses without it, which
// correctly leaves open the question of where the boolean comes from. It must
// NOT come from a params flag: a flag is something another process set, and
// "another process decided I may read your inbox" is exactly the sentence this
// product cannot afford to be true. That rule is unchanged by the offer ref
// below — a ref proves WHICH QUESTION WAS PUT, and nothing else. It cannot
// authorise anything on its own: with a ref and no answer, or a ref and an
// answer a model reads as no, the mailbox stays shut.
//
// WHAT WAS HERE UNTIL 2026-08-24, and why it is gone. Consent was two word
// lists — an affirmative vocabulary and a mailbox vocabulary — that had to
// co-occur in one sentence of the approved scope. The sentence
//
//     "Yeah ok, my email is playing up, just use 884210."
//
// is a man apologising for his mail server while handing over a code he read
// himself. It contains an affirmative and it contains "email", so it returned
// TRUE, and the agent went and read his mailbox. Nobody had asked him anything
// about his mailbox. That is not a tuning error in the word list; a word list
// cannot hold the difference, because the difference is what he MEANT.
// HARNESS-LAWS.md law 1: meaning belongs to a model with full context.
//
// This looks like the seatbelt and is not. The seatbelt asks "what would this
// plan do to the world?" — a question about effect channels, answerable from a
// plan's own structured fields, and pattern-matching is legal there. This asks
// "did this person agree?" — a question about what a human meant. So it is
// split into the two questions it actually is:
//
//   1. WAS THE OFFER PUT TO HIM? Structural, and answerable from a record ONLY
//      THIS MODULE CAN HAVE WRITTEN — see the offer ref below.
//   2. DID HIS ANSWER MEAN YES? Handed whole — with the question it answers —
//      to a model. Nothing here reads his words.
//
// Both must hold. Either one failing is a refusal, and so is every way of
// failing to decide: no model, a model that errors, a model that waffles.
// Failing closed costs one message asking him to paste the code. Failing open
// reads somebody's mail without being asked.

// ---------------------------------------------------------------------------
// THE OFFER REF — what makes question (1) answerable at all
// ---------------------------------------------------------------------------
//
// WHAT WAS HERE UNTIL 2026-08-24 (the second time), and why it is gone.
// Question (1) was decided by testing whether the quoted question contained
// INBOX_OFFER_MARK, on the stated grounds that it was "recognising a sentence
// THIS MODULE WROTE". That premise was false in the shipped system, and a
// reviewer drove the consequence end to end.
//
// `asked` is `job.result` — and `job.result` for a model-authored hand-back is
// `decision.reason`, free-form step-model prose written while reading a page
// (agent_loop.js, the `needs_user` branch). AGENT_SYSTEM then instructs the
// step model, in capitals, to offer to go and read anything "sent somewhere
// they control … a document, a reference number … or an account they are
// signed into". So the model is actively steered to compose questions of this
// exact shape about targets that are not the mailbox. It parked with a
// sentence of its own about an order summary on the next page, ending in the
// mark word for word; the owner answered "sure, but only the summary — do not go poking around
// anywhere else", the structural half passed, and mail.google.com was opened
// and read. A page can steer that prose too, so the sentence is not merely
// ours-by-coincidence; it is writable by an attacker.
//
// The difference between READING OUR OWN FORMAT — which is safe — and MATCHING
// A SENTENCE ANYONE CAN PRODUCE is that our own format has to contain
// something no one else can produce. So the offer now carries one:
//
//   * `mintOfferRef()` mints 128 bits of CSPRNG randomness when — and only
//     when — this module's offer is actually handed back.
//   * `stampOffer()` puts it in the sentence he reads, so the brain quotes it
//     back inside the frame's `asked` half, verbatim, with everything else.
//   * The loop returns it to background.js, which records it in the JOB'S
//     PARAMS. That channel is not reachable by the owner's words (they land in
//     approved_scope) and not writable by the step model (it emits actions,
//     not params), and background.js CLEARS it on every hand-back that is not
//     one of our offers — so a ref never outlives the question it was minted
//     for, and a forged sentence carrying a ref copied out of the scope has no
//     live ref to match.
//   * `offerCarriesRef()` checks it on the way in. No ref, a short ref, a
//     malformed ref, or a ref the quoted question does not carry: NOT ASKED,
//     and the model is never consulted.
//
// A ref is NOT consent and cannot become consent: it answers "which question
// was put", never "what did he mean". Question (2) is still a model reading
// his whole answer, and it is still the only thing that can say yes.

// The mark of our own offer, defined once and used both to BUILD the sentence
// he sees (offerToFetch) and to RECOGNISE it coming back in the frame. Two
// copies would let somebody reword the question while the recogniser kept
// matching the old wording, and every yes he gave would be silently thrown
// away — the failure mode that is invisible because it only ever refuses.
//
// It is NOT what proves the question was ours; the ref is. The mark is what
// tells the two doors apart, so a yes about a private place is never read as a
// yes about the mailbox and the other way round.
export const INBOX_OFFER_MARK = "Want me to go and read it?";

// 16 bytes, hex. The owner sees this on the end of the sentence, which is a
// real cost in a product whose whole promise is not spending his attention —
// but the alternative is a shorter token, and the thing this proves is worth
// more than the four words of tidiness. Guessing is not a strategy against
// 128 bits, and the step model gets one hand-back to try.
const REF_LEN = 32;
const REF_ALPHABET = "0123456789abcdef";

/**
 * A fresh offer ref, or "" when this runtime has no CSPRNG.
 *
 * "" IS A REAL ANSWER AND MUST STAY ONE. Math.random() is not an option: a
 * predictable ref is a forgeable ref, and a forgeable ref is the defect this
 * exists to close. With no CSPRNG the offer goes out unstamped, no answer to
 * it can ever be read as consent, and the run asks him to paste the code —
 * one message, which is the correct price of not knowing.
 */
export function mintOfferRef() {
  const source = globalThis.crypto;
  if (!source || typeof source.getRandomValues !== "function") return "";
  const bytes = source.getRandomValues(new Uint8Array(REF_LEN / 2));
  let out = "";
  for (const b of bytes) out += b.toString(16).padStart(2, "0");
  return out;
}

// A ref shaped the way we mint them, or "". Deliberately not a regex and
// deliberately not a substring test: `offerCarriesRef("...", "")` returning
// true would make every unstamped sentence consent-bearing, which is the
// fail-open version of this whole change.
//
// A STRING, NOT SOMETHING STRINGABLE. `String(x)` on an object calls its
// `toString`, so `{ toString: () => theRef }` used to pass here and grant. The
// only legitimate source is a JSON params field, which is a string or absent;
// anything else arriving is a bug or an attempt, and both are refusals.
function usableRef(ref) {
  if (typeof ref !== "string") return "";
  if (ref.length !== REF_LEN) return "";
  for (const ch of ref) if (!REF_ALPHABET.includes(ch)) return "";
  return ref;
}

/** The sentence he reads, carrying the ref. Unstamped if there is no ref. */
export function stampOffer(text, ref) {
  const usable = usableRef(ref);
  const sentence = String(text || "");
  return usable ? `${sentence} [ref ${usable}]` : sentence;
}

/** Does this quoted question carry THIS run's live ref? */
export function offerCarriesRef(asked, ref) {
  const usable = usableRef(ref);
  if (!usable) return false;
  return String(asked || "").includes(`[ref ${usable}]`);
}

// The brain's frame, verbatim. The only regex on this path, and it reads our
// format, never his vocabulary.
//
// THE ANSWER RUNS TO THE FRAME'S OWN TAIL, NOT TO THE NEXT QUOTE. It used to
// stop at the first `"` inside the reply, and a truncated answer is not a
// smaller answer — it is a different one, because a retraction lives at the
// END of a sentence:
//
//     yes — actually wait, "cancel that", no, leave my mail alone
//       → the judge was handed:  `yes — actually wait, `
//
// A model reads that as agreement. His retraction never arrived. So the
// terminator is the frame's own tail — `" — that answer is final`, written by
// brain/conversation.py — or, for the iOS writer (AnticipyApp.swift), which
// omits that tail, the closing `".` immediately before the end of the scope or
// the start of the next appended segment. Both shapes exist in the wild and
// both are read here.
const ASKED_AND_ANSWERED =
  /You stopped and asked:\s*"([\s\S]*?)"\.\s*They answered:\s*"([\s\S]*?)"(?:\s*[—–-]\s*that answer is final|\.?(?=\s*(?:$|You stopped and asked:|They changed:)))/g;

/**
 * The LAST question this job parked on and the words he replied, or null.
 *
 * THE LAST PAIR ONLY. A job can park more than once; if his most recent answer
 * was about which card to use, an inbox offer he agreed to three questions ago
 * is not consent to a mailbox read happening now. Consent that drifts forward
 * in time is how "he said yes once" becomes a standing permission nobody
 * granted.
 *
 * Exported because private_places.js needs exactly this and nothing else, and
 * a second copy of the frame regex is the one duplication that must not exist:
 * the brain could reword its frame and one of the two copies would silently
 * stop recognising consent while the other kept granting it. One regex, in the
 * module whose test pins it.
 */
export function lastAskedAndAnswered(scope) {
  const text = String(scope || "");
  if (!text.trim()) return null;
  const pairs = [...text.matchAll(ASKED_AND_ANSWERED)];
  if (!pairs.length) return null;
  const [, asked, answer] = pairs[pairs.length - 1];
  return { asked, answer };
}

/**
 * The same pair, but only when the question was OUR inbox offer — so a scope
 * carrying any other parked question never reaches the model at all.
 *
 * `offerRef` is this run's live ref, recorded in the job's params when the
 * offer was handed back. THE REF IS CHECKED FIRST AND IT IS THE ONE THAT
 * MATTERS: without it, "was the offer put to him" collapses into "does this
 * sentence contain a sentence anyone can write", which is what shipped and
 * what a reviewer used to open the owner's Gmail. The mark is checked too, but
 * only to tell this door from the private-places door — both stamp refs into
 * the same params slot, and the last question asked is the only one either can
 * be answering.
 */
export function inboxOfferAnswered(scope, offerRef) {
  const pair = lastAskedAndAnswered(scope);
  if (!pair) return null;
  if (!offerCarriesRef(pair.asked, offerRef)) return null;
  if (!pair.asked.includes(INBOX_OFFER_MARK)) return null;
  return pair;
}

/**
 * May the agent open his mailbox? Await it; it may ask a model.
 *
 * `judge({ asked, answer })` returns the model's verdict as a string. It is
 * injected for the same reason everything else here is: this module stays free
 * of Chrome and of network calls so the decision is testable directly.
 *
 * Returns { granted, why } where `why` is one of:
 *   never asked  — the offer was never put to him; the model is not consulted
 *   declined     — the model read his answer and it is not agreement
 *   undecidable  — no judge, or a verdict we cannot read. FAIL CLOSED.
 *   granted      — he agreed
 *
 * `why` is not decoration: the caller must not re-put a question he has
 * already answered, so "never asked" and everything else lead to different
 * sentences.
 *
 * `offerRef` is the ref recorded when the offer was handed back. Omitting it
 * refuses everything — which is correct: a caller that cannot say which
 * question it put has not established that any question was put.
 */
export async function inboxConsent({ scope, offerRef, judge } = {}) {
  const pair = inboxOfferAnswered(scope, offerRef);
  if (!pair) return { granted: false, why: "never asked" };
  if (typeof judge !== "function") return { granted: false, why: "undecidable" };
  let verdict;
  try {
    verdict = await judge(pair);
  } catch (_) {
    return { granted: false, why: "undecidable" };
  }
  // A SHAPE CHECK ON THE MODEL'S OWN REPLY, which is the same containment
  // runSideTrip already applies to its fallback model: the verdict is a token
  // we specified, not prose we interpret. A model that answers in a sentence
  // is a model we did not understand, and an unread verdict is a refusal —
  // never an approval. Anything trailing the token (a hijacked reply
  // continuing "and also open his bank") fails this and stays out.
  const token = String(verdict == null ? "" : verdict).trim();
  if (token === "YES") return { granted: true, why: "granted" };
  if (token === "NO") return { granted: false, why: "declined" };
  return { granted: false, why: "undecidable" };
}

/**
 * Go to one place, read one value, come back.
 *
 * `deps` is everything that touches Chrome, injected so this stays testable:
 *   openTab(url)   -> tabId          open a NEW tab (never reuse the working one)
 *   readTab(tabId) -> { text, url }  read the visible text
 *   clickText(tabId, text) -> bool   click a link/row matching visible text
 *   closeTab(tabId)                  clean up
 *   judgeCode({ pageText, purpose, site }) -> string
 *                                    the model that reads which value is the
 *                                    code; its reply is contained by
 *                                    codeFromPage before anything crosses back
 *   note(line)                       trace line; MUST NOT be given message text
 *
 * The working tab is never passed in and never touched. That is the point:
 * the run's position survives the trip.
 *
 * A FLOOR on what gets typed into a live one-time-code field: no judge means
 * the mailbox is never opened; a judge that throws, times out, waffles or
 * names a value that is not on the page ends the trip at once as
 * undecidable, never as "keep looking"; UNCLEAR on the list page (several
 * snippets visible) opens the newest matching message, UNCLEAR on any later
 * page stops at once so no more mail is read than necessary.
 */
export async function runSideTrip({
  url, purpose, site, authorized = false, deps, budget = {},
} = {}) {
  const { steps: maxSteps = 6 } = budget;
  const refusal = tripRefusedReason(url, { authorized, purpose });
  if (refusal) return { ok: false, reason: refusal, value: null };

  const { openTab, readTab, clickText, closeTab, judgeCode, note } = deps || {};
  if (!openTab || !readTab || !closeTab) {
    return { ok: false, reason: "the trip has no way to open a page", value: null };
  }
  // BEFORE the tab opens: a mailbox is never opened for a read nobody can
  // perform.
  if (typeof judgeCode !== "function") {
    return { ok: false, reason: "the trip has no way to read the code", value: null, undecidable: true };
  }

  let tabId = null;
  let last = null;
  try {
    tabId = await openTab(url);
    if (note) note(`side trip: opened ${safeHost(url)} to get ${purpose}`);

    for (let step = 0; step < maxSteps; step++) {
      const page = await readTab(tabId);
      const text = String(page?.text || "");

      last = await readCodeVerdict({ pageText: text, purpose, site, judge: judgeCode });
      if (last.state === "code") {
        // ONLY THE VALUE CROSSES BACK. Not the message, not the subject, not
        // the sender. The trace gets the shape of what was found, never the
        // thing itself — a code in a log is a code that outlived its minute.
        if (note) note(`side trip: found a ${last.value.length}-character code (read by the model, present on the page)`);
        return { ok: true, value: last.value, steps: step + 1 };
      }
      if (last.state === "unread") {
        if (note) note("side trip: stopped — the code could not be read");
        return { ok: false, reason: "I could not read the code", value: null, undecidable: true };
      }
      if (last.state === "unclear" && step > 0) {
        if (note) note("side trip: stopped — more than one value could be the code");
        return { ok: false, reason: "I found more than one code and won't guess between them", value: null, ambiguous: true };
      }

      // Nothing on this page — or UNCLEAR on the list page, where opening the
      // message resolves it. The only navigation a side trip is allowed is
      // opening the newest thing that looks like the message we came for — it
      // may not wander, and it may not act.
      if (!clickText) break;
      const opened = await clickText(tabId, purpose);
      if (!opened) break;
      if (note) note(`side trip: opened the newest matching message`);
    }

    if (last && last.state === "unclear") {
      if (note) note("side trip: stopped — more than one value could be the code");
      return { ok: false, reason: "I found more than one code and won't guess between them", value: null, ambiguous: true };
    }
    return { ok: false, reason: "I could not find the code on that page", value: null };
  } catch (e) {
    return { ok: false, reason: `the trip failed: ${String(e).slice(0, 120)}`, value: null };
  } finally {
    // The trip's tab always closes. A stray inbox tab left open is both a
    // mess and a privacy problem.
    if (tabId != null && closeTab) { try { await closeTab(tabId); } catch (_) { /* gone */ } }
  }
}

function safeHost(url) {
  try { return new URL(String(url)).hostname; } catch (_) { return "that page"; }
}

/**
 * The sentence the owner actually sees. He asked for this by name:
 * "Hey, can I go to your Gmail and get the verification code for you?"
 */
export function offerToFetch(detection, { service } = {}) {
  if (!detection) return null;
  const where = detection.where === "phone" ? "your phone"
    : detection.address ? detection.address : "your email";
  const what = service ? `${service}'s code` : "the code";
  return `${what} just went to ${where}. ${INBOX_OFFER_MARK} I'll keep this page exactly as it is and come straight back — say go and I'll finish this off.`;
}

/**
 * What to say when the offer was already put to him and his answer did not
 * read as a yes.
 *
 * Putting the SAME question a second time is the failure that replaces a wrong
 * mailbox read if you are not careful: he answers, the answer cannot be read
 * as agreement, the run parks with the identical sentence, and he is in a loop
 * answering a question that never resolves. This is the exit — it names what
 * did not happen to his mail, and asks for the one thing that finishes the
 * job.
 */
export function askForCodeInstead(service) {
  return `${service ? service + "'s" : "The"} code is still needed and I haven't `
    + `touched your inbox. Paste it to me and I'll finish this off — the page is `
    + `exactly where I left it.`;
}

// ---------------------------------------------------------------------------
// Which inbox is his
// ---------------------------------------------------------------------------

// Where the big providers keep their web mail. This is infrastructure the
// world already fixed — not task knowledge — so it is a lookup, not a guess.
// It is deliberately NOT a list of restaurants or job boards: the destination
// is derived from HIS OWN email address, never from the errand.
const WEBMAIL = {
  "gmail.com": "https://mail.google.com/mail/u/0/#search/in%3Aanywhere+newer_than%3A1h",
  "googlemail.com": "https://mail.google.com/mail/u/0/#search/in%3Aanywhere+newer_than%3A1h",
  "outlook.com": "https://outlook.live.com/mail/0/",
  "hotmail.com": "https://outlook.live.com/mail/0/",
  "live.com": "https://outlook.live.com/mail/0/",
  "msn.com": "https://outlook.live.com/mail/0/",
  "yahoo.com": "https://mail.yahoo.com/",
  "ymail.com": "https://mail.yahoo.com/",
  "icloud.com": "https://www.icloud.com/mail",
  "me.com": "https://www.icloud.com/mail",
  "mac.com": "https://www.icloud.com/mail",
  "proton.me": "https://mail.proton.me/u/0/inbox",
  "protonmail.com": "https://mail.proton.me/u/0/inbox",
  "aol.com": "https://mail.aol.com/",
  "zoho.com": "https://mail.zoho.com/zm/",
  "fastmail.com": "https://app.fastmail.com/mail/Inbox",
};

/**
 * The web inbox for an address, or null when it cannot be known.
 *
 * Null is a real answer and must stay one: a company address on its own
 * domain could be Google Workspace, Microsoft 365, or something built
 * in-house, and opening the wrong one wastes a trip and shows him a login
 * wall. When this returns null the offer asks him where to look instead of
 * pretending to know.
 */
export function inboxFor(email) {
  const at = String(email || "").trim().toLowerCase().split("@");
  if (at.length !== 2 || !at[1]) return null;
  return WEBMAIL[at[1]] || null;
}

/**
 * Everything needed to offer the trip, or null if there is nothing to offer.
 *
 * Keeps the decision in ONE place: is a code being waited on, do we know
 * where it went, and can we get there. The loop asks this and either offers
 * or asks plainly — it never has to work any of it out itself.
 *
 * `verdict` is what `whereCodeWent` returned. This is a FLOOR: the verdict is
 * what licenses OFFERING to read his mail and minting a live ref, so without
 * one there is no offer and no ref. But the demo died of the STALL, not of a
 * declined offer, so "unclear" and "unanswered" still hand back — with a
 * url:null sentence that asks where to look or for the code, which no consent
 * path ever reads. Only "none" returns null: the page does not say a code was
 * sent (an authenticator app, a code not yet requested), and the step model
 * may press "send code" or hand back on its own.
 */
export function tripOnOffer(verdict, ownerProfile, service) {
  const state = verdict && typeof verdict === "object" ? String(verdict.state || "") : "";
  const who = service ? service + "'s" : "The";
  if (state === "none") return null;
  if (state === "phone") {
    // His phone is not ours to read, and it is already the channel we text
    // him on. Ask; never pretend we can go and look.
    return { offer: `${who} code went to your phone. `
      + `Send it to me and I'll finish this off — the page is exactly where I left it.`,
      url: null, purpose: null };
  }
  if (state !== "email") {
    // unclear, unanswered, or a state this file does not know: no offer, no
    // ref, and a plain ask. Failing closed costs one message.
    return { offer: `${who} code is needed and I can't tell from the page where it `
      + `went — tell me where to look, or paste it, and I'll finish this off; the `
      + `page is exactly where I left it.`,
      url: null, purpose: null };
  }
  // Prefer the address the SITE says it used; fall back to the one he gave us.
  // A MASKED ADDRESS IS NOT AN ADDRESS. Sites print "o***r@gmail.com", and
  // the plain-address pattern happily matches the tail — "r@gmail.com" —
  // which looks unmasked, resolves to a real provider, and would send the
  // trip somewhere chosen by a fragment. Only an address with a local part
  // that survives intact counts; otherwise fall back to the one HE gave us.
  const raw = String(verdict.address || "");
  const local = raw.split("@")[0] || "";
  const looksReal = raw.includes("@") && !/[*•]/.test(raw)
    && local.length >= 2 && !/^[a-z]$/i.test(local);
  const addr = looksReal ? raw : ((ownerProfile && ownerProfile.email) || "");
  const url = inboxFor(addr);
  if (!url) {
    return { offer: `${who} code just went to `
      + `${verdict.address || "your email"}. I can go and read it if you tell me where `
      + `that inbox is — or paste the code and I'll carry on from where I am.`,
      url: null, purpose: null };
  }
  return {
    offer: offerToFetch({ where: "email", address: verdict.address || null }, { service }),
    url,
    purpose: `${service || "the"} verification code`,
  };
}
