// THE SECOND DOOR TO HIS MAILBOX.
//
// On 2026-08-24 the OTP wall's path to the owner's inbox was closed: consent
// there had been a word list, and "Yeah ok, my email is playing up, just use
// 884210." satisfied it. That fix locked one door. This is the other one.
//
// The main step loop had NO mailbox gate at all. `BLOCKED_DOMAINS`
// (agent_loop.js) named eighteen banks and not one mail host, so a goal like
// "find my flight confirmation number" could have the step model emit
// `navigate https://mail.google.com/...`, the working tab would go, and the
// loop would map the page and read it. No offer, no question, nothing to
// consent to — because nothing asked. Reproduced end to end before this file
// existed; see tests/test_private_places.mjs §1.
//
// -------------------------------------------------------------------------
// IS A DOMAIN LIST THE RIGHT INSTRUMENT?
//
// For deciding WHEN TO ASK: yes, and it is the only affordable one. A run
// makes dozens of navigations and cannot put a question to a human before
// each. Something cheap and mechanical has to notice "this one is different",
// and "what kind of place does this URL point at" is a question about what the
// plan TOUCHES — the seatbelt, which HARNESS-LAWS.md law 1 explicitly allows
// to be pattern-matched.
//
// For deciding THE ANSWER: no, and this is where BLOCKED_DOMAINS quietly
// fails. A list allows everything it does not name. It grew by incident —
// eighteen banks, added one payment scare at a time — which is why webmail,
// a category nobody had been burned by yet, was simply absent. Enumerating
// every webmail host on earth is not a task anyone finishes: `mail.acme.co.uk`
// running Roundcube is a mailbox and will never be on a list.
//
// So the list is a TRIGGER, and it is built in three layers, strongest first,
// so that the weakest layer is carrying the least weight:
//
//   1. DERIVED, NOT ENUMERATED — his own webmail, computed from his own
//      address by side_trip.inboxFor(). No list is consulted for the one
//      mailbox that actually matters.
//   2. HOST SHAPE — a hostname whose first label is `mail`, `webmail`,
//      `inbox`, `owa`, `roundcube`... is a mailbox whoever runs it. This is
//      reading URL structure, not company names, and it covers the
//      self-hosted and corporate mail no table can enumerate.
//   3. A NAMED TABLE — only for hosts whose shape says nothing
//      (outlook.live.com, web.whatsapp.com, 1password.com). Admittedly
//      incomplete; every entry is a place somebody would be upset to find an
//      agent standing in.
//
// And the answer, once triggered, is NOT decided here. It is decided the way
// the OTP wall now decides it: the owner is asked in a sentence, his reply
// comes back inside the brain's own frame, and a MODEL reads the question and
// the answer together. Nothing in this file pattern-matches his words.
//
// -------------------------------------------------------------------------
// WHY THE ERRAND'S OWN WORDING IS NOT A GRANT.
//
// It is tempting to let "go into my Gmail and get the flight number" open the
// door without asking. It does not, and that is deliberate:
//
//   * `goal` is a lossy model summary of what he said (the same reason
//     unsupportedScopeFields refuses to authorise from it). Opening a mailbox
//     on a machine's paraphrase is precisely the sentence "another process
//     decided I may read your inbox" that this product cannot afford.
//   * `scope` is his own words, but reading THEM to decide consent — with no
//     question attached — is the shape that produced the original defect. A
//     model doing it instead of a regex is better, but he still never got a
//     moment where he saw the question.
//
// So the offer is always put, even when he plainly asked. That costs exactly
// one message on a request he already made. A wrong yes reads his mail.

import { inboxFor, lastAskedAndAnswered, offerCarriesRef } from "./side_trip.js";

// ---------------------------------------------------------------------------
// Layer 2 — host shape
// ---------------------------------------------------------------------------

// A hostname's FIRST LABEL, when it is one of these, names the service the
// host runs. `mail.google.com`, `mail.ru`, `webmail.acme.co.uk`,
// `owa.hospital.org`, `roundcube.my-vps.net` are all mailboxes and none of
// them had to be listed anywhere. This reads URL structure, which is
// plumbing; it never sees a word anyone said.
const MAILBOX_LABEL = /^(?:mail|email|e-mail|webmail|inbox|mailbox|imap|owa|zimbra|roundcube|squirrelmail|rainloop|horde)$/;
// Patient portals are overwhelmingly `mychart.<provider>.org` and its
// cousins. Same structural trick, same reason.
const HEALTH_LABEL = /^(?:mychart|patientportal|patients?|myhealth|healthportal|followmyhealth)$/;

// ---------------------------------------------------------------------------
// Layer 3 — the named table, for hosts whose shape says nothing
// ---------------------------------------------------------------------------
//
// `kind` is what he would call the place. `stance` is what happens when a run
// tries to walk in:
//
//   "ask"    — park and put the offer. Opening it can be a real errand
//              ("what did the clinic email me?"), so refusing outright would
//              replace a privacy bug with a dead end. He decides, in words,
//              and a model reads the answer.
//   "refuse" — never, the same stance the bank list takes. These are places
//              where being wrong is not recoverable by a follow-up message:
//              a password vault is the keys to everything he has, and a
//              government identity account is his legal identity. There is
//              no errand worth an agent standing in either.
//
// Every host below is matched on the host itself or any subdomain of it.
const NAMED = [
  // --- mailboxes whose hostname does not announce itself
  ["outlook.live.com", "mailbox", "ask"],
  ["outlook.office.com", "mailbox", "ask"],
  ["outlook.office365.com", "mailbox", "ask"],
  ["outlook.com", "mailbox", "ask"],
  ["app.fastmail.com", "mailbox", "ask"],
  ["fastmail.com", "mailbox", "ask"],
  ["hey.com", "mailbox", "ask"],
  ["superhuman.com", "mailbox", "ask"],
  ["proton.me", "mailbox", "ask"],
  ["protonmail.com", "mailbox", "ask"],
  ["tutanota.com", "mailbox", "ask"],
  ["zoho.com", "mailbox", "ask"],
  ["gmx.com", "mailbox", "ask"],
  ["gmx.net", "mailbox", "ask"],
  ["web.de", "mailbox", "ask"],

  // --- the places his conversations live. Reading someone's messages is the
  //     same act as reading their mail, and these clients can also SEND.
  ["web.whatsapp.com", "messages", "ask"],
  ["messenger.com", "messages", "ask"],
  ["web.telegram.org", "messages", "ask"],
  ["discord.com", "messages", "ask"],
  ["slack.com", "messages", "ask"],
  ["teams.microsoft.com", "messages", "ask"],
  ["messages.google.com", "messages", "ask"],
  ["web.skype.com", "messages", "ask"],
  ["signal.org", "messages", "ask"],

  // --- health records. Note what is NOT here: zocdoc.com and its kind are
  //     booking marketplaces, not record portals — "book me a dentist" is an
  //     ordinary errand and gating it would cost a message for nothing. The
  //     line is whether the site holds his history or merely his appointment.
  ["healthcare.gov", "health record", "ask"],
  ["nhs.uk", "health record", "ask"],
  ["athenahealth.com", "health record", "ask"],
  ["followmyhealth.com", "health record", "ask"],
  ["labcorp.com", "health record", "ask"],
  ["questdiagnostics.com", "health record", "ask"],
  ["23andme.com", "health record", "ask"],
  ["myhealth.va.gov", "health record", "ask"],

  // --- everything he owns, indexed. drive.google.com is the INDEX; a single
  //     docs.google.com/document/d/<id> he named in the errand is one named
  //     document and is deliberately absent, or the gate would fire on every
  //     link he sends himself.
  ["drive.google.com", "personal files", "ask"],
  ["photos.google.com", "personal files", "ask"],
  ["dropbox.com", "personal files", "ask"],
  ["onedrive.live.com", "personal files", "ask"],
  ["box.com", "personal files", "ask"],
  ["icloud.com", "personal files", "ask"],

  // --- REFUSE. The keys to everything.
  ["1password.com", "password vault", "refuse"],
  ["lastpass.com", "password vault", "refuse"],
  ["bitwarden.com", "password vault", "refuse"],
  ["dashlane.com", "password vault", "refuse"],
  ["keepersecurity.com", "password vault", "refuse"],
  ["nordpass.com", "password vault", "refuse"],
  ["enpass.io", "password vault", "refuse"],
  ["authy.com", "password vault", "refuse"],

  // --- REFUSE. His legal identity and his tax affairs. Same class as the
  //     bank list: a mistake here is not undone by a follow-up message.
  ["irs.gov", "government identity", "refuse"],
  ["ssa.gov", "government identity", "refuse"],
  ["id.me", "government identity", "refuse"],
  ["login.gov", "government identity", "refuse"],
  ["account.gov.uk", "government identity", "refuse"],
  ["signin.service.gov.uk", "government identity", "refuse"],
  ["tax.service.gov.uk", "government identity", "refuse"],
  ["cra-arc.gc.ca", "government identity", "refuse"],
  ["uscis.gov", "government identity", "refuse"],
];

// DELIBERATELY NOT GATED: single sign-on. `accounts.google.com`,
// `login.microsoftonline.com`, okta, duo and their kind sit on the happy path
// of ordinary errands — every "sign in with Google" button lands there — and
// login_wall.js already owns that moment. Gating them would trade a privacy
// bug for a dead end on a large share of all errands, which is the trade this
// whole exercise exists to avoid making. Stated here so the omission reads as
// a decision rather than an oversight.
//
// WHAT "OWNS THAT MOMENT" RESTS ON, since 2026-09-05 (Audit #70): login_wall's
// verdict is ONE model question, and it is a CEILING — only an explicit WALL
// parks the run. A no-verdict (a timeout, a 500, prose) lets the step model
// carry on, and because these hosts are ungated and "continue" is a
// reversible control, that step model can click "Continue with Google" and
// the account-chooser tile behind it with no seatbelt in this file, in
// protectedInput, or in the stall catching it. The mitigation is that the
// wall judge and the step model share one transport (/agent/llm via
// modelFetch): a judge that cannot answer is a step model that cannot act.
// A which-host seatbelt on the OAuth click — legal under Law 1, it checks
// what a plan TOUCHES — is a separate item and has not been built.

function hostOf(url) {
  try {
    return new URL(String(url || "")).hostname.toLowerCase().replace(/\.$/, "");
  } catch (_) { return ""; }
}

const under = (host, domain) => host === domain || host.endsWith("." + domain);

/**
 * What kind of private place is this, if any?
 *
 * Returns { host, kind, stance, why } or null. `why` names the layer that
 * matched, so a trace line can say how the run knew — an unexplained refusal
 * on a host nobody recognises is the kind of thing that gets a gate deleted.
 */
export function privatePlace(url, ownerProfile = null) {
  const host = hostOf(url);
  if (!host) return null;

  // Layer 1 — derived. His own provider, from his own address.
  const ownInbox = hostOf(inboxFor(ownerProfile && ownerProfile.email) || "");
  if (ownInbox && under(host, ownInbox)) {
    return { host, kind: "mailbox", stance: "ask", why: "it is the inbox for his own address" };
  }

  // Layer 2 — host shape. No company names involved.
  const first = host.split(".")[0];
  if (MAILBOX_LABEL.test(first)) {
    return { host, kind: "mailbox", stance: "ask", why: `"${first}." is how a host announces a mailbox` };
  }
  if (HEALTH_LABEL.test(first)) {
    return { host, kind: "health record", stance: "ask", why: `"${first}." is how a host announces a patient portal` };
  }

  // Layer 3 — the named table. Longest domain wins, so a specific entry is
  // never shadowed by a broader one that happens to sit earlier in the list.
  let best = null;
  for (const [domain, kind, stance] of NAMED) {
    if (!under(host, domain)) continue;
    if (!best || domain.length > best[0].length) best = [domain, kind, stance];
  }
  if (best) return { host, kind: best[1], stance: best[2], why: `${best[0]} is a known ${best[1]}` };
  return null;
}

// ---------------------------------------------------------------------------
// The question, and who answers it
// ---------------------------------------------------------------------------

// The mark of our own offer, defined ONCE and used both to build the sentence
// he reads and to recognise it coming back in the brain's frame. Two copies is
// how consent silently stops being recognisable: somebody rewords the question
// the owner sees, the recogniser keeps matching the old wording, and every yes
// he gives is thrown away — a failure nobody notices because it only ever
// refuses. side_trip.js carries the same property for the same reason.
//
// IT IS NOT WHAT PROVES THE QUESTION WAS OURS. Nothing stops the step model
// composing this sentence and the host beside it — `asked` is `job.result`,
// and a model-authored hand-back puts free-form prose there. What proves it is
// side_trip.js's offer ref, minted when this module's offer is handed back and
// recorded where neither the owner's channel nor the step model can write.
// Read the block above `mintOfferRef` for the reproduction that made that
// necessary; the same defect existed on both doors and the ref closes both.
export const PLACE_OFFER_MARK = "Want me to open it?";

/**
 * The sentence he actually sees when a run reaches a private place.
 *
 * It names the HOST, because consent to one place is not consent to another
 * and the recogniser below proves that from this sentence.
 */
export function offerToOpen(place) {
  if (!place) return null;
  return `This errand runs into ${place.host} — your ${place.kind}. `
    + `I haven't opened it. ${PLACE_OFFER_MARK} Say go and I'll look, `
    + `or tell me what you'd rather I did instead.`;
}

/**
 * What to say when the offer was put and his answer did not read as agreement.
 *
 * Putting the SAME question twice is the failure that replaces a wrong read if
 * you are not careful: he answers, the answer cannot be read as agreement, the
 * run parks with the identical sentence, and he is in a loop answering a
 * question that never resolves.
 */
export function askInsteadOfOpening(place) {
  return `I left ${place ? place.host : "it"} alone. Tell me what you'd like `
    + `me to do instead and I'll carry on from exactly where I stopped.`;
}

/** The refusal for the places no answer can open. */
export function refusalToOpen(place) {
  return `refused: ${place.host} is your ${place.kind} — that one stays yours. `
    + `I stopped rather than operate it, and the page is exactly where I left it.`;
}

/**
 * Was OUR offer, about THIS place, put to him — and what did he reply?
 *
 * Structural, and every part of it reads a format we wrote ourselves: the
 * brain's frame (side_trip.lastAskedAndAnswered), our own offer mark, and the
 * host our own sentence named. Nothing here reads his vocabulary.
 *
 * THE LAST PAIR ONLY, and the HOST must match. A yes about his mailbox three
 * questions ago is not consent to open his password vault now, and consent
 * that drifts sideways between places is the same bug as consent that drifts
 * forward in time.
 */
export function placeOfferAnswered(scope, place, offerRef) {
  if (!place) return null;
  const pair = lastAskedAndAnswered(scope);
  if (!pair) return null;
  // THE REF FIRST, because it is the only one of the three an attacker cannot
  // write. The mark and the host are what tell one of OUR questions from
  // another one of OUR questions; they say nothing about whose question it is.
  if (!offerCarriesRef(pair.asked, offerRef)) return null;
  if (!pair.asked.includes(PLACE_OFFER_MARK)) return null;
  if (!pair.asked.includes(place.host)) return null;
  return pair;
}

/**
 * May this run open this place? Await it; it may ask a model.
 *
 * `judge({ asked, answer, place })` returns the model's verdict as a string.
 * Injected for the same reason side_trip.js injects its own: this module stays
 * free of Chrome and of network calls so the decision is testable directly.
 *
 * Returns { granted, why } where `why` is one of:
 *   never asked  — the offer was never put to him; no model is consulted
 *   declined     — the model read his answer and it is not agreement
 *   undecidable  — no judge, or a verdict we cannot read. FAIL CLOSED.
 *   granted      — he agreed
 *
 * `why` is not decoration: the caller must not re-put a question he has
 * already answered, so "never asked" and everything else lead to different
 * sentences.
 */
export async function placeConsent({ scope, place, offerRef, judge } = {}) {
  if (!place) return { granted: false, why: "never asked" };
  if (place.stance === "refuse") return { granted: false, why: "declined" };
  const pair = placeOfferAnswered(scope, place, offerRef);
  if (!pair) return { granted: false, why: "never asked" };
  if (typeof judge !== "function") return { granted: false, why: "undecidable" };
  let verdict;
  try {
    verdict = await judge({ ...pair, place });
  } catch (_) {
    return { granted: false, why: "undecidable" };
  }
  // A SHAPE CHECK ON THE MODEL'S OWN REPLY. The verdict is a token we
  // specified, not prose we interpret: a model that answers in a sentence is a
  // model we did not understand, and an unread verdict is a refusal, never an
  // approval. Anything trailing the token — a hijacked reply continuing "and
  // also open his vault" — fails this and stays out.
  const token = String(verdict == null ? "" : verdict).trim();
  if (token === "YES") return { granted: true, why: "granted" };
  if (token === "NO") return { granted: false, why: "declined" };
  return { granted: false, why: "undecidable" };
}
