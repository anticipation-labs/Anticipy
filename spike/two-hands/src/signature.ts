// CAPABILITY SIGNATURE — one step of a plan, described without naming a hand.
//
// This is the only object the router, the ledger and the judge all share, and
// the whole "no hardcoded app list" claim rests on it: the signature says WHAT
// the owner wants to have happened, never WHICH app or WHICH hand does it. If
// anything in this file ever starts deciding an outcome from the WORDS in
// `object` or `app_hint`, the spike has become the thing HARNESS-LAWS law 1
// forbids and this file is where a reviewer should look first.
//
// The hash is the ledger's primary key. Everything about how it is computed is
// therefore a promise about which two steps are allowed to share a track
// record — get it too narrow and shadow mode re-opens for every variation of
// the same errand; too wide and a promoted rung licenses a step nobody ever
// measured.

import { createHash } from "node:crypto";
import {
  type CapabilitySignature,
  type SideEffect,
  type Verb,
  tightenSideEffect,
} from "./contract.ts";

// ---------------------------------------------------------------------------
// The contract's closed enums, at runtime.
// ---------------------------------------------------------------------------
// `node --experimental-strip-types` DELETES the type annotations; it does not
// check them. So `sig.verb` being typed `Verb` stops exactly nobody at run
// time, and a planner that emits `{"verb": "purchase"}` would sail through and
// hash into a rung of its own. These two arrays exist so the guard is a real
// guard.
//
// This is NOT the word list law 1 forbids, and the distinction matters enough
// to write down: these are the members of a closed enum declared in
// contract.ts, checked for membership only. Nothing here reads a human's
// sentence, and nothing branches on WHICH member it is except the effect-channel
// floor below, which is the seatbelt law 1 explicitly permits.
const VERBS: readonly string[] = ["read", "create", "update", "send", "delete", "pay", "book"];
const SIDE_EFFECTS: readonly string[] = ["read", "write", "irreversible"];
const ACCOUNT_HINTS: readonly (string | null)[] = ["work", "personal", null];

// ---------------------------------------------------------------------------
// Orthographic normalisation — and the line it must not cross.
// ---------------------------------------------------------------------------
// LEGAL (this function): case, surrounding space, and which separator character
// a compound word was written with. `Calendar Event`, `calendar-event` and
// `calendar_event` are the same string typed three ways; no human reading them
// would say they mean different things, and no judgement is being made. This is
// the same class of pattern-matching as parsing a host out of a URL.
//
// ILLEGAL, and deliberately absent: a synonym table. There is no map turning
// `event` into `calendar_event`, or `message` into `email`. That would be a word
// list deciding that two planner words MEAN the same capability, which is the
// exact shape law 1 exists to keep out of this repo. The cost of leaving it out
// is real and is written up in
// research/2026-09-05-two-hands-signatures.md: a planner that renames its own
// object between releases silently orphans every rung it earned. The fix for
// that is a stable planner prompt (and, if it ever stops being enough, ONE
// question asked of a model in four states) — never a table here.
function normalizeToken(raw: unknown, field: string): string {
  if (typeof raw !== "string") {
    throw new TypeError(`signature.${field} must be a string, got ${typeof raw}`);
  }
  const t = raw.trim().toLowerCase().replace(/[\s_\-]+/g, "_");
  if (t === "") throw new TypeError(`signature.${field} must not be empty`);
  return t;
}

// The sorted, de-duplicated canonical names of the input keys.
//
// `sort()` with NO comparator, on purpose: it orders by UTF-16 code unit, which
// is the same on every machine. `localeCompare` would make the hash depend on
// the host's locale, so the same step would hash one way on the owner's laptop
// and another inside the Worker — and the ledger would look empty for a
// capability with thirty successful runs behind it.
//
// The de-dupe is there because normalisation can collide two written keys
// (`event-id` and `event_id`). Without it the canonical list would carry the
// same token twice and hash differently from the identical step written with
// one spelling. The hash is a function of the SET of keys the step needs.
function canonicalInputKeys(inputs: unknown): string[] {
  if (inputs === null || typeof inputs !== "object" || Array.isArray(inputs)) {
    throw new TypeError("signature.inputs must be a plain object");
  }
  const seen = new Set<string>();
  for (const k of Object.keys(inputs as Record<string, unknown>)) {
    seen.add(normalizeToken(k, `inputs["${k}"]`));
  }
  return [...seen].sort();
}

// ---------------------------------------------------------------------------
// THE HASH
// ---------------------------------------------------------------------------
/**
 * The exact bytes that get hashed. Exported because a debugging session that
 * cannot see this string is reduced to guessing why two rungs did not merge.
 *
 * It is a JSON triple rather than a concatenation. Plain `verb + object + keys`
 * is ambiguous: `{verb:"send", object:"email"}` and a step whose verb ended one
 * character earlier would produce identical bytes, and two unrelated
 * capabilities would share a track record. JSON gives every field its own
 * delimited slot, so no re-split can collide.
 */
export function canonicalSignatureString(
  verb: unknown,
  object: unknown,
  inputs: unknown,
): string {
  const v = normalizeToken(verb, "verb");
  if (!VERBS.includes(v)) {
    throw new TypeError(`signature.verb ${JSON.stringify(verb)} is not one of ${VERBS.join("|")}`);
  }
  return JSON.stringify([v, normalizeToken(object, "object"), canonicalInputKeys(inputs)]);
}

/**
 * sha1(verb + object + sorted input KEY names). Three things are excluded, each
 * for a reason that costs money when it is got wrong:
 *
 * - INPUT VALUES. "email Sam" and "email Dana" are the same capability. If
 *   values were hashed, every new recipient would arrive as an unmeasured
 *   capability at rung 0 and re-open shadow mode — the API hand would never
 *   finish proving itself, because there is always another recipient.
 *
 * - `app_hint`. It is the planner's GUESS. Hashing it would make the ledger's
 *   key depend on that guess, so the day the planner starts writing "google
 *   calendar" instead of "googlecalendar" every rung it earned goes cold; worse,
 *   a wrong guess would fork the record of a capability that is in fact the
 *   same one. contract.ts calls it advisory; this is what advisory has to mean
 *   in code.
 *
 * - `expected_effect`, `side_effect` and `account_hint`. The first two are
 *   per-run judgements, not identity: "move the 2pm to 3pm" and "shorten the
 *   2pm" are the same tool call with the same arguments shape, and if the
 *   sentence were in the key the ledger's `n` would never leave 1. See the
 *   research note for the sharp edge this leaves — two steps that share a rung
 *   can differ in reversibility, so the ROUTER must gate on `sig.side_effect`
 *   as well as on the rung, never on the rung alone.
 */
export function signatureHash(
  sig: Pick<CapabilitySignature, "verb" | "object" | "inputs">,
): string {
  return createHash("sha1").update(canonicalSignatureString(sig.verb, sig.object, sig.inputs)).digest("hex");
}

// ---------------------------------------------------------------------------
// THE EFFECT-CHANNEL FLOOR
// ---------------------------------------------------------------------------
// This is a seatbelt, in law 1's sense: it reads what the step TOUCHES (the
// verb the planner chose from a closed set), never how a sentence was worded.
// It can only ever make a step STRICTER — it is applied through the contract's
// own `tightenSideEffect`, so a declaration can never be loosened by it.
//
// The failure it prevents, concretely: a planner emits
// `{verb: "pay", side_effect: "read"}` — a real class of mistake, since the
// model filling a JSON field is not the model that will be gated by it — and
// the router's read path, which is allowed to run unattended with the laptop
// shut, executes a payment. Moment 26 of the brief is one sentence long about
// this: "Money always waits for your word. Always."
//
// WHERE THE `irreversible` LINE IS DRAWN, and why it is not "how bad does this
// sound". A step floors at `irreversible` when UNDOING IT NEEDS SOMEBODY ELSE'S
// COOPERATION, OR A BACKUP — the payee's refund, the recipient's forgetting, a
// snapshot that may not exist. `create`, `update` and `book` all leave behind a
// record this same account still owns and can delete or cancel by itself, so
// the floor leaves them at `write` and the ladder plus the owner's write opt-in
// do the gating. That is a structural test of what the step TOUCHES, which is
// the seatbelt law 1 permits — it reads a member of a closed enum, never a
// human's sentence.
//
// `delete` moved here on 2026-09-05, and the bug it was hiding is the reason
// this comment is long. It used to floor at `write`. A delete built the
// INTENDED way — makeSignature with no `side_effect`, since answering an absent
// declaration is this function's whole job — came out `write`; the router's
// `effect === "irreversible"` test was therefore false; and no decision, on
// either hand, at any rung, ever carried `requiresConfirmation`. The only thing
// standing between the owner's mail and permanent destruction was the
// candidate's own `sideEffectHint` — which contract.ts calls untrusted per the
// MCP spec, and which the shipped fixture's GMAIL_DELETE_THREAD declares as a
// plain "write" on purpose, precisely to show that it saves nobody. A floor
// that defers to the vendor is not a floor.
//
// `send` moved here in the same pass, REVERSING a deliberate earlier decision,
// so the earlier reasoning is recorded rather than erased: whether a sent thing
// can be unsent is a property of the APP (a Slack message deletes; an email
// does not), so the verb alone cannot know. That premise is true and the
// conclusion drawn from it was backwards. A FLOOR is the answer given when
// nobody with context has spoken, and contract.ts's LAW1 note fixes its
// polarity — "a privilege needs something to license it rather than merely the
// absence of an objection". Flooring at `write` used the ABSENCE of context to
// pick the LOOSE end, which is the one move a floor exists to prevent. Three
// things settle it:
//   * docs/BRIEF.html states the seatbelt in one sentence and names sending
//     first: "anything that sends, buys, books, posts, or deletes waits for the
//     owner's tap."
//   * The browser hand already obeys that — `commitControl` in
//     extension/agent_loop.js carries `send` in its commit-verb set, so
//     pressing Send in a page goes through the authorization gate. With send
//     floored at `write` the API hand sent the same message with no tap: two
//     hands doing observably different things for one step, which is the exact
//     property this spike exists to hold.
//   * Slack's delete does not un-ring the notification, and this contract has
//     no state between `write` and `irreversible` in which to record
//     "recallable for thirty seconds".
// The price of being wrong strict is one tap. The price of being wrong loose is
// an unapproved message in a colleague's inbox. Note that the ratchet only goes
// up, so a planner CANNOT buy the loose end back by declaring `write` — that is
// deliberate: the model filling that field is the same kind of model that left
// it out in the first place.
export function verbSideEffectFloor(verb: Verb): SideEffect {
  if (verb === "read") return "read";
  if (verb === "pay" || verb === "delete" || verb === "send") return "irreversible";
  return "write";
}

// ---------------------------------------------------------------------------
// CONSTRUCTION
// ---------------------------------------------------------------------------
export interface PartialSignature {
  verb: Verb | string;
  object: string;
  inputs?: Record<string, unknown>;
  expected_effect: string;
  side_effect?: SideEffect | string;
  app_hint?: string | null;
  account_hint?: "work" | "personal" | null;
}

/**
 * Fill the defaults, validate at RUN time, apply the effect-channel floor, and
 * compute the hash.
 *
 * The returned object is frozen, inputs included. A downstream module that does
 * `sig.inputs.cc = "..."` has changed which capability this is while leaving
 * `signature_hash` describing the old one — the router would then read a rung
 * earned by a step that never had a cc field, and shadow mode would be skipped
 * for a variant nobody measured. Freezing turns that into a loud TypeError at
 * the line that caused it. `withInputs` below is the legal way to change them.
 */
export function makeSignature(partial: PartialSignature): CapabilitySignature {
  if (partial === null || typeof partial !== "object") {
    throw new TypeError("makeSignature needs an object");
  }

  const verb = normalizeToken(partial.verb, "verb");
  if (!VERBS.includes(verb)) {
    throw new TypeError(`signature.verb ${JSON.stringify(partial.verb)} is not one of ${VERBS.join("|")}`);
  }
  const object = normalizeToken(partial.object, "object");

  // The stored `inputs` keep the planner's original spelling — the executor has
  // to hand them to a tool schema that never heard of our normalisation. Only
  // the HASH sees canonical names. What must never happen is the reverse: a
  // stored signature whose `object` is raw while its hash was computed from the
  // normalised form, because the ledger backfill re-hashes stored rows and every
  // rung would be orphaned by a re-hash that disagrees with the stored key.
  const inputs = partial.inputs === undefined ? {} : partial.inputs;
  canonicalInputKeys(inputs); // throws now, rather than at hash time three frames away

  // Parity between the two hands is judged on this sentence and nothing else
  // (contract.ts, ShadowRun.parity). An empty one makes the verifier vacuous,
  // and a vacuous verifier means parity collapses back to "did the two hands
  // return the same bytes" — which is exactly how a wrong browser run certifies
  // a wrong API run.
  if (typeof partial.expected_effect !== "string" || partial.expected_effect.trim() === "") {
    throw new TypeError("signature.expected_effect must be a non-empty sentence: the verifier has nothing to check without it");
  }

  let side_effect: SideEffect;
  if (partial.side_effect === undefined || partial.side_effect === null) {
    // Absent is not "read". A missing declaration is answered by the floor, in
    // the strict direction, because the API hand is a privilege and a privilege
    // needs something to license it rather than merely the absence of an
    // objection (contract.ts LAW1, same polarity).
    side_effect = verbSideEffectFloor(verb as Verb);
  } else {
    const declared = normalizeToken(partial.side_effect, "side_effect");
    if (!SIDE_EFFECTS.includes(declared)) {
      throw new TypeError(`signature.side_effect ${JSON.stringify(partial.side_effect)} is not one of ${SIDE_EFFECTS.join("|")}`);
    }
    side_effect = tightenSideEffect(declared as SideEffect, verbSideEffectFloor(verb as Verb));
  }

  const account_hint = partial.account_hint === undefined ? null : partial.account_hint;
  if (!ACCOUNT_HINTS.includes(account_hint)) {
    throw new TypeError(`signature.account_hint ${JSON.stringify(account_hint)} is not work|personal|null`);
  }

  // Trimmed, and otherwise left exactly as the planner wrote it. It is not
  // normalised because nothing is allowed to route on it, so there is nothing
  // for a canonical form to make comparable — and normalising it would invite a
  // later reader to think comparing it is fair game.
  let app_hint: string | null = null;
  if (partial.app_hint !== undefined && partial.app_hint !== null) {
    if (typeof partial.app_hint !== "string") {
      throw new TypeError("signature.app_hint must be a string or null");
    }
    const a = partial.app_hint.trim();
    app_hint = a === "" ? null : a;
  }

  const sig: CapabilitySignature = {
    app_hint,
    verb: verb as Verb,
    object,
    inputs: Object.freeze({ ...inputs }) as Record<string, unknown>,
    expected_effect: partial.expected_effect.trim(),
    side_effect,
    account_hint,
    signature_hash: signatureHash({ verb: verb as Verb, object, inputs }),
  };
  return Object.freeze(sig);
}

/**
 * A new signature with different inputs and a hash that matches them. The legal
 * alternative to mutating a frozen `inputs`; without it, the freeze above would
 * push callers into rebuilding signatures by hand and getting a field wrong.
 */
export function withInputs(
  sig: CapabilitySignature,
  inputs: Record<string, unknown>,
): CapabilitySignature {
  return makeSignature({
    verb: sig.verb,
    object: sig.object,
    inputs,
    expected_effect: sig.expected_effect,
    side_effect: sig.side_effect,
    app_hint: sig.app_hint,
    account_hint: sig.account_hint,
  });
}

/**
 * Does this signature's hash actually describe this signature?
 *
 * Anything that arrives from outside this process — a queued step reloaded from
 * D1, a plan handed back by a model, a step that crossed the extension boundary
 * — carries a hash somebody else computed. A step whose hash was swapped for a
 * promoted one would inherit a rung it never earned, which is how an
 * `irreversible` step gets executed on the strength of a `read` step's track
 * record. Moment 48 of the brief is the same principle one layer out: content
 * that arrives from the world is quoted, never obeyed.
 *
 * Honest limit: sha1 is the contract's choice and this is a WIRING check — it
 * catches a stale, forged-by-hand or mismatched hash, not a determined
 * collision attack. If this hash ever becomes a real trust boundary it has to
 * move to sha256, and that is a contract change, not a change here.
 *
 * NOTHING SHIPPED CALLS THIS YET, and the paragraph above is therefore a
 * promise the system does not keep. `src/router.ts` reads `sig.signature_hash`
 * to look up a rung and `sig.side_effect` to decide confirmation, both straight
 * off an object it did not build. Until it verifies first, a step whose hash
 * was swapped for a promoted read pair's inherits that pair's rung, and the
 * ladder — the whole apparatus for not doing dangerous things until they are
 * earned — is bypassed by editing one string.
 *
 * That gap is a RED LEG, not a comment: `test/signature.test.ts`,
 * "verifySignatureHash is called by shipped code, not only by this file", scans
 * src/ and tasks/ with comments and string literals stripped, so a note like
 * this one cannot satisfy it. It closes by WIRING the call at the router's
 * entry point. Deleting or relaxing the leg is the failure HARNESS-LAWS law 2
 * names one layer out — a marker that "reads as compliant and enforces
 * nothing".
 */
export function verifySignatureHash(sig: CapabilitySignature): boolean {
  if (sig === null || typeof sig !== "object") return false;
  if (typeof sig.signature_hash !== "string") return false;
  try {
    return signatureHash(sig) === sig.signature_hash;
  } catch {
    // A malformed signature has no valid hash by definition. Returning false
    // rather than rethrowing keeps the router's guard a one-liner; the caller
    // that wants the reason calls signatureHash directly.
    return false;
  }
}

/**
 * Do these two steps share a ledger rung? Exported so no caller has to know
 * that the answer is "compare the hashes" — the day the key gains a field, this
 * is the one line that changes.
 */
export function sameCapability(a: CapabilitySignature, b: CapabilitySignature): boolean {
  return signatureHash(a) === signatureHash(b);
}
