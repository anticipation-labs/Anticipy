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
// injected. That keeps it honest under test — the extraction rules below are
// the part that decides whether a real code or a street number gets typed
// into a form, and they are tested directly rather than through a browser.

// ---------------------------------------------------------------------------
// What counts as the thing we were sent for
// ---------------------------------------------------------------------------

// Words that appear next to a real one-time code, in the wild.
const CODE_CONTEXT = /\b(verification|verify|confirm(?:ation)?|security|one[-\s]?time|single[-\s]?use|access|login|sign[-\s]?in|auth(?:entication)?|passcode|pin|otp|code)\b/i;

// Things that are digit runs but are NEVER a verification code. Each of these
// is a real thing that appeared in a real email next to a real code, and any
// of them being picked instead would put the wrong value in the form.
const NOT_A_CODE = [
  /^(?:19|20)\d{2}$/,                    // a year
  /^\d{5}(?:-\d{4})?$/,                  // US zip
  /^1?\d{10,11}$/,                       // a phone number
  /^0+$/,                                // padding
];

/**
 * Pull a one-time code out of message text.
 *
 * ARITHMETIC FIRST, ON PURPOSE. A model asked "what is the code in this
 * email?" is right most of the time, and the times it is wrong it is
 * confidently wrong — it will happily return the year in the footer or the
 * last four of a card. A code has a shape, and shape is checkable. The model
 * is the fallback for genuinely odd formats, not the first resort.
 *
 * Returns { value, confidence, why } or null.
 */
export function extractCode(text, opts = {}) {
  const { minLen = 4, maxLen = 8 } = opts;
  const body = String(text || "");
  if (!body.trim()) return null;

  const candidates = [];

  // Pass 1: a labelled code. "Your verification code is 483920", "Code: 8813".
  // The label is the strongest possible evidence, so these outrank everything.
  // The filler between the label and the code matters more than it looks.
  // Requiring NON-alphanumeric filler meant "Your code is 483920" — the most
  // common phrasing there is — never matched as labelled at all. It fell
  // through to the weak proximity pass, where a number planted elsewhere in
  // the message could tie with it and the whole read came back "ambiguous".
  // A handful of connecting words are allowed; anything longer is prose, not
  // a label, and must not drag an unrelated number in with it.
  const labelled = /\b(?:code|passcode|pin|otp)\b(?:\s*(?:is|are|was|:|=|-|–|—)\s*){0,2}\s*([0-9]{4,8}|[A-Z0-9]{4,8})\b/gi;
  for (const m of body.matchAll(labelled)) {
    candidates.push({ value: m[1], score: 100, why: "labelled directly" });
  }

  // Pass 2: a standalone run of digits on a line of its own, or spaced out
  // the way services print them ("4 8 3 9 2 0"). Very common in real mail.
  for (const line of body.split(/\n+/)) {
    const bare = line.trim();
    const compact = bare.replace(/[\s-]/g, "");
    if (/^[0-9]{4,8}$/.test(compact) && /^[0-9\s-]+$/.test(bare)) {
      candidates.push({ value: compact, score: 80, why: "alone on its own line" });
    }
  }

  // Pass 3: a digit run near code words, within the same sentence-ish window.
  for (const m of body.matchAll(/\b([0-9]{4,8})\b/g)) {
    const at = m.index || 0;
    const around = body.slice(Math.max(0, at - 90), at + 40);
    if (CODE_CONTEXT.test(around)) {
      candidates.push({ value: m[1], score: 60, why: "next to code wording" });
    }
  }

  const seen = new Set();
  const kept = [];
  for (const c of candidates.sort((a, b) => b.score - a.score)) {
    const v = String(c.value).toUpperCase();
    if (seen.has(v)) continue;
    if (v.length < minLen || v.length > maxLen) continue;
    // A CODE CONTAINS A DIGIT. Without this the labelled pattern reads the
    // next word after "code" as the code itself: "This code expires in 10
    // minutes" yielded EXPIRES, and a model replying "I could not find a
    // code, sorry!" yielded SORRY — both scored as confidently as a real
    // one, and both would have been typed into the form.
    if (!/[0-9]/.test(v)) continue;
    // A purely-numeric candidate has to survive the not-a-code list. An
    // alphanumeric one (A3F9K2) cannot be a year or a zip, so it skips this.
    if (/^\d+$/.test(v) && NOT_A_CODE.some((re) => re.test(v))) continue;
    seen.add(v);
    kept.push({ ...c, value: v });
  }
  if (!kept.length) return null;

  // TWO DIFFERENT CANDIDATES WITH THE SAME STRENGTH IS NOT AN ANSWER.
  // Guessing between them is how the wrong code gets typed, the site locks
  // the attempt, and the run burns. Ambiguity goes back to the owner.
  const best = kept[0];
  const rival = kept.find((c) => c.value !== best.value && c.score === best.score);
  if (rival) {
    return { value: null, confidence: "ambiguous", why: `found both ${best.value} and ${rival.value}` };
  }
  return {
    value: best.value,
    confidence: best.score >= 80 ? "high" : "medium",
    why: best.why,
  };
}

/**
 * Does this page actually say a code was sent, and where to?
 *
 * Used to decide whether to OFFER the trip at all. Being wrong in the
 * permissive direction here is cheap (we ask a question the owner declines);
 * being wrong in the restrictive direction is what killed the demo.
 */
export function detectsCodeWasSent(pageText) {
  const t = String(pageText || "");
  if (!t.trim()) return null;
  // Real pages overwhelmingly say "Code sent to o***r@gmail.com" or "A
  // verification code was sent to your email" — and NEITHER matched, because the
  // pattern only knew first-person constructions ("we sent", "check your
  // email"). So the most common wording on the exact page this feature exists for
  // detected nothing and offered nothing. Broadened to include the passive and
  // the bare "sent to".
  //
  // Deliberately still requires evidence of SENDING, not merely of a code being
  // expected: a bare "enter the code" is also true of an authenticator app, and
  // offering to read somebody's inbox for a code that never went there is a
  // question that makes the product look like it is guessing.
  const sent = /\b(we[''\s]?(?:ve|just)?\s?(?:sent|emailed|texted)|has been sent|have been sent|was sent|were sent|been sent to|sent to|check your (?:e-?mail|inbox|phone|messages)|sent (?:you )?a (?:code|link|verification)|code (?:was |has been )?sent|(?:e-?mail|text|sms) (?:with|containing) a? ?(?:code|link))\b/i;
  if (!sent.test(t)) return null;

  // Where did it go? An address in the text is the best evidence; failing
  // that, the words "email" or "phone" near the sentence.
  const addr = t.match(/\b([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b/);
  const masked = t.match(/\b([a-z]\*+[a-z0-9]*@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b/i);
  const phone = /\b(?:phone|text|sms|message)\b/i.test(t);
  const email = /\b(?:e-?mail|inbox)\b/i.test(t) || !!addr || !!masked;

  return {
    where: email ? "email" : (phone ? "phone" : "unknown"),
    address: (addr && addr[1]) || (masked && masked[1]) || null,
  };
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
// product cannot afford to be true.
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
//   1. WAS THE OFFER PUT TO HIM? Structural, and answerable from our own
//      machine-written frame. When he answers a parked question the brain
//      writes `You stopped and asked: "<our sentence>". They answered:
//      "<his words>"` into approved_scope (brain/conversation.py:1576-1580).
//      Recognising a sentence THIS MODULE WROTE is parsing our own format.
//   2. DID HIS ANSWER MEAN YES? Handed whole — with the question it answers —
//      to a model. Nothing here reads his words.
//
// Both must hold. Either one failing is a refusal, and so is every way of
// failing to decide: no model, a model that errors, a model that waffles.
// Failing closed costs one message asking him to paste the code. Failing open
// reads somebody's mail without being asked.

// The mark of our own offer, defined once and used both to BUILD the sentence
// he sees (offerToFetch) and to RECOGNISE it coming back in the frame. Two
// copies would let somebody reword the question while the recogniser kept
// matching the old wording, and every yes he gave would be silently thrown
// away — the failure mode that is invisible because it only ever refuses.
export const INBOX_OFFER_MARK = "Want me to go and read it?";

// The brain's frame, verbatim. The only regex on this path, and it reads our
// format, never his vocabulary.
const ASKED_AND_ANSWERED =
  /You stopped and asked:\s*"([\s\S]*?)"\.\s*They answered:\s*"([\s\S]*?)"/g;

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
 */
export function inboxOfferAnswered(scope) {
  const pair = lastAskedAndAnswered(scope);
  if (!pair || !pair.asked.includes(INBOX_OFFER_MARK)) return null;
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
 */
export async function inboxConsent({ scope, judge } = {}) {
  const pair = inboxOfferAnswered(scope);
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
 *   askModel(prompt) -> string       fallback extraction only
 *   note(line)                       trace line; MUST NOT be given message text
 *
 * The working tab is never passed in and never touched. That is the point:
 * the run's position survives the trip.
 */
export async function runSideTrip({
  url, purpose, authorized = false, deps, budget = {},
} = {}) {
  const { steps: maxSteps = 6 } = budget;
  const refusal = tripRefusedReason(url, { authorized, purpose });
  if (refusal) return { ok: false, reason: refusal, value: null };

  const { openTab, readTab, clickText, closeTab, askModel, note } = deps || {};
  if (!openTab || !readTab || !closeTab) {
    return { ok: false, reason: "the trip has no way to open a page", value: null };
  }

  let tabId = null;
  try {
    tabId = await openTab(url);
    if (note) note(`side trip: opened ${safeHost(url)} to get ${purpose}`);

    for (let step = 0; step < maxSteps; step++) {
      const page = await readTab(tabId);
      const text = String(page?.text || "");

      const found = extractCode(text);
      if (found && found.value) {
        // ONLY THE VALUE CROSSES BACK. Not the message, not the subject, not
        // the sender. The trace gets the shape of what was found, never the
        // thing itself — a code in a log is a code that outlived its minute.
        if (note) note(`side trip: found a ${found.value.length}-character code (${found.why})`);
        return { ok: true, value: found.value, confidence: found.confidence, steps: step + 1 };
      }
      if (found && found.confidence === "ambiguous") {
        if (note) note(`side trip: stopped — ${found.why}`);
        return { ok: false, reason: `I found more than one code and won't guess between them`, value: null, ambiguous: true };
      }

      // Nothing on this page. The only navigation a side trip is allowed is
      // opening the newest thing that looks like the message we came for —
      // it may not wander, and it may not act.
      if (!clickText) break;
      const opened = await clickText(tabId, purpose);
      if (!opened) break;
      if (note) note(`side trip: opened the newest matching message`);
    }

    // Arithmetic found nothing. THIS is where a model earns its place: an
    // unusual format ("your code: four-eight-three") that no regex will hold.
    // It sees the page once, for one question, and its answer is still
    // shape-checked before it is believed.
    if (askModel) {
      const page = await readTab(tabId);
      const raw = await askModel(String(page?.text || "").slice(0, 4000));
      const checked = extractCode(String(raw || ""), { minLen: 4, maxLen: 8 })
        || extractCode(`code: ${String(raw || "").trim()}`);
      if (checked && checked.value) {
        if (note) note(`side trip: found a ${checked.value.length}-character code (read from an unusual format)`);
        return { ok: true, value: checked.value, confidence: "medium", steps: maxSteps };
      }
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
 */
export function tripOnOffer(pageText, ownerProfile, service) {
  const sent = detectsCodeWasSent(pageText);
  if (!sent) return null;
  if (sent.where === "phone") {
    // His phone is not ours to read, and it is already the channel we text
    // him on. Ask; never pretend we can go and look.
    return { offer: `${service ? service + "'s" : "The"} code went to your phone. `
      + `Send it to me and I'll finish this off — the page is exactly where I left it.`,
      url: null, purpose: null };
  }
  // Prefer the address the SITE says it used; fall back to the one he gave us.
  // A MASKED ADDRESS IS NOT AN ADDRESS. Sites print "o***r@gmail.com", and
  // the plain-address pattern happily matches the tail — "r@gmail.com" —
  // which looks unmasked, resolves to a real provider, and would send the
  // trip somewhere chosen by a fragment. Only an address with a local part
  // that survives intact counts; otherwise fall back to the one HE gave us.
  const raw = String(sent.address || "");
  const local = raw.split("@")[0] || "";
  const looksReal = raw.includes("@") && !/[*•]/.test(raw)
    && local.length >= 2 && !/^[a-z]$/i.test(local);
  const addr = looksReal ? raw : ((ownerProfile && ownerProfile.email) || "");
  const url = inboxFor(addr);
  if (!url) {
    return { offer: `${service ? service + "'s" : "The"} code just went to `
      + `${sent.address || "your email"}. I can go and read it if you tell me where `
      + `that inbox is — or paste the code and I'll carry on from where I am.`,
      url: null, purpose: null };
  }
  return {
    offer: offerToFetch(sent, { service }),
    url,
    purpose: `${service || "the"} verification code`,
  };
}
