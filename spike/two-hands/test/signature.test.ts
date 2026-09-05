// What these tests are actually defending.
//
// `signature_hash` is the ledger's primary key, so every assertion below is a
// statement about which two steps are allowed to share a track record. The two
// ways to get that wrong both cost real money:
//
//   too NARROW — the hash moves when it should not, every rung goes cold, and
//   shadow mode re-opens for a capability that has thirty successful runs
//   behind it. The API hand never finishes proving itself.
//
//   too WIDE — two different capabilities share a rung, and a promoted record
//   licenses a step nobody measured. That is the direction that sends an email.
//
// No network, no key, no account. `node --experimental-strip-types --test
// test/signature.test.ts`.

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  canonicalSignatureString,
  makeSignature,
  sameCapability,
  signatureHash,
  verbSideEffectFloor,
  verifySignatureHash,
  withInputs,
} from "../src/signature.ts";
import { type ToolCandidate, tightenSideEffect } from "../src/contract.ts";

// A complete, valid step, used as the base for the "one field changed" tests so
// that each test isolates exactly one variable.
function base(over: Record<string, unknown> = {}) {
  return makeSignature({
    app_hint: "gmail",
    verb: "send",
    object: "email",
    inputs: { to: "sam@example.com", subject: "the form", body: "attached" },
    expected_effect: "sam has one message from the owner with the form attached",
    side_effect: "irreversible",
    account_hint: "personal",
    ...over,
  } as never);
}

// ---------------------------------------------------------------------------
// WHAT IS IN THE HASH
// ---------------------------------------------------------------------------

test("key ORDER does not change the hash", () => {
  // The planner builds this object by filling a JSON reply; the order its keys
  // land in is the model's whim and changes between calls. If order were in the
  // hash, the same errand would open a new rung roughly at random.
  const a = signatureHash({
    verb: "send",
    object: "email",
    inputs: { to: "x", subject: "y", body: "z" },
  });
  const b = signatureHash({
    verb: "send",
    object: "email",
    inputs: { body: "z", to: "x", subject: "y" },
  });
  assert.equal(a, b);
});

test("a different VERB is a different capability", () => {
  const draft = signatureHash({ verb: "create", object: "email", inputs: { to: "x" } });
  const send = signatureHash({ verb: "send", object: "email", inputs: { to: "x" } });
  assert.notEqual(draft, send);
});

test("a different OBJECT is a different capability", () => {
  const mail = signatureHash({ verb: "create", object: "email_draft", inputs: { to: "x" } });
  const event = signatureHash({ verb: "create", object: "calendar_event", inputs: { to: "x" } });
  assert.notEqual(mail, event);
});

test("changing an input VALUE does not change the hash", () => {
  // The whole reason values are excluded: "email Sam" and "email Dana" are the
  // same capability. If they were not, every new recipient would arrive at rung
  // 0 and the API hand would be stuck in shadow mode forever, because there is
  // always another recipient.
  const sam = base().signature_hash;
  const dana = withInputs(base(), {
    to: "dana@example.com",
    subject: "completely different subject",
    body: "completely different body",
  }).signature_hash;
  assert.equal(sam, dana);
});

test("changing an input KEY does change the hash", () => {
  // A step that carries a cc needs a tool that can cc. Sharing a rung with the
  // no-cc version would let a record earned without the field license a call
  // that has to carry it.
  const plain = base().signature_hash;
  const withCc = withInputs(base(), {
    to: "sam@example.com",
    subject: "the form",
    body: "attached",
    cc: "dana@example.com",
  }).signature_hash;
  assert.notEqual(plain, withCc);
});

test("app_hint is not in the hash", () => {
  // contract.ts calls app_hint advisory. This is what advisory has to mean: the
  // planner guessing "google_mail" one day and "gmail" the next must not fork
  // the record of a capability that is in fact the same one.
  assert.equal(base({ app_hint: "gmail" }).signature_hash, base({ app_hint: "superhuman" }).signature_hash);
  assert.equal(base({ app_hint: null }).signature_hash, base({ app_hint: "gmail" }).signature_hash);
});

test("expected_effect, side_effect and account_hint are not in the hash", () => {
  // Deliberate, and the sharp edge is documented rather than hidden: two steps
  // that share a rung can differ in reversibility, so the ROUTER must gate on
  // sig.side_effect as well as on the rung. If the sentence were in the key,
  // the ledger's n would never leave 1 and no capability would ever promote.
  const a = base({ expected_effect: "sam has the form", side_effect: "irreversible", account_hint: "personal" });
  const b = base({ expected_effect: "a wholly different sentence about the same call", side_effect: "irreversible", account_hint: "work" });
  assert.equal(a.signature_hash, b.signature_hash);
});

test("two different moments that are the same capability share one rung", () => {
  // The claim the ledger is built on, stated as a test: moment 27's landlord
  // draft and a draft to anybody else are one capability with one track record.
  const landlord = makeSignature({
    verb: "create", object: "email_draft",
    inputs: { to: "landlord@example.com", subject: "Heater still not working", body: "..." },
    expected_effect: "a draft to the landlord about the heater exists and nothing was sent",
  });
  const school = makeSignature({
    verb: "create", object: "email_draft",
    inputs: { to: "office@school.example", subject: "Permission slip", body: "..." },
    expected_effect: "a draft to the school about the slip exists and nothing was sent",
  });
  assert.ok(sameCapability(landlord, school));
});

// ---------------------------------------------------------------------------
// THE CANONICAL FORM
// ---------------------------------------------------------------------------

test("orthography is normalised; vocabulary is not", () => {
  // LEGAL: case, spacing, and which separator character a compound was typed
  // with. Nobody would say "Calendar Event" and "calendar_event" mean different
  // things, and no judgement is being made.
  assert.equal(
    signatureHash({ verb: "read", object: "Calendar Event", inputs: { Time_Min: 1 } }),
    signatureHash({ verb: "read", object: "calendar-event", inputs: { "time min": 2 } }),
  );
  // ILLEGAL, and its absence is the point: there is no synonym table, so
  // "event" and "calendar_event" stay different capabilities. Deciding they are
  // the same is a meaning judgement, and HARNESS-LAWS law 1 puts that with a
  // model, never with a lookup in this file.
  assert.notEqual(
    signatureHash({ verb: "read", object: "event", inputs: {} }),
    signatureHash({ verb: "read", object: "calendar_event", inputs: {} }),
  );
});

test("the canonical string is delimited, so no re-split can collide", () => {
  // Plain concatenation would let a longer object with fewer keys produce the
  // same bytes as a shorter object with an extra key, and two unrelated
  // capabilities would share a track record.
  assert.equal(canonicalSignatureString("Send", " Email ", { Subject: "y", to: "x", body: "z" }),
    '["send","email",["body","subject","to"]]');
  assert.notEqual(
    signatureHash({ verb: "read", object: "email", inputs: { x: 1 } }),
    signatureHash({ verb: "read", object: "emailx", inputs: {} }),
  );
});

test("keys that normalise together are counted once", () => {
  // Otherwise {event_id, "event-id"} would hash differently from {event_id}
  // even though the canonical key set is identical.
  assert.equal(
    signatureHash({ verb: "update", object: "calendar_event", inputs: { event_id: 1, "event-id": 2 } }),
    signatureHash({ verb: "update", object: "calendar_event", inputs: { event_id: 1 } }),
  );
});

test("the hash is stable across processes and locales", () => {
  // A pinned value. It goes red if the canonical encoding is ever changed, and
  // that is the point: changing it orphans every rung already stored against
  // the old key, so it must be a deliberate migration and never a refactor.
  // (sort() with no comparator is codepoint order; localeCompare would make
  // this value depend on the machine's locale.)
  assert.equal(
    signatureHash({ verb: "send", object: "email", inputs: { to: "x", subject: "y", body: "z" } }),
    "c393c75abb9dd3065b1ee2daaad6a756511326ea",
  );
});

test("the hash is 40 hex characters", () => {
  assert.match(base().signature_hash, /^[0-9a-f]{40}$/);
});

// ---------------------------------------------------------------------------
// CONSTRUCTION, DEFAULTS AND ROUND-TRIP
// ---------------------------------------------------------------------------

test("makeSignature round-trips: the stored hash describes the stored fields", () => {
  const sig = base();
  assert.equal(sig.signature_hash, signatureHash(sig));
  assert.ok(verifySignatureHash(sig));
});

test("the stored object is the normalised one, so a re-hash agrees with the stored key", () => {
  // If the record kept "Calendar Event" while the hash was computed from
  // "calendar_event", the ledger backfill — which re-hashes stored rows — would
  // produce a key that matches nothing, and every rung would be orphaned by a
  // job that was only supposed to read.
  const sig = makeSignature({
    verb: "read", object: "  Calendar Event ", inputs: {},
    expected_effect: "the owner is told tomorrow's events",
  });
  assert.equal(sig.object, "calendar_event");
  assert.equal(sig.signature_hash, signatureHash(sig));
});

test("defaults: absent app_hint, inputs and account_hint", () => {
  const sig = makeSignature({
    verb: "read", object: "calendar_event",
    expected_effect: "the owner is told tomorrow's events",
  });
  assert.equal(sig.app_hint, null);
  assert.deepEqual(sig.inputs, {});
  assert.equal(sig.account_hint, null);
  assert.equal(sig.side_effect, "read");
});

test("a blank app_hint becomes null rather than an empty string", () => {
  // An empty string is falsy in some places and truthy-ish in others; a router
  // that logs `app_hint || "unknown"` and a ledger that stores "" disagree
  // about the same step. One representation for absent.
  assert.equal(makeSignature({
    verb: "read", object: "calendar_event", app_hint: "   ",
    expected_effect: "the owner is told tomorrow's events",
  }).app_hint, null);
});

test("verifySignatureHash catches a swapped hash", () => {
  // Anything that crosses a process boundary carries a hash somebody else
  // computed. A step whose hash was replaced with a promoted one would inherit
  // a rung it never earned — an irreversible step executing on a read step's
  // track record.
  const good = base();
  const forged = { ...good, signature_hash: signatureHash({ verb: "read", object: "email", inputs: {} }) };
  assert.ok(verifySignatureHash(good));
  assert.equal(verifySignatureHash(forged as never), false);
  assert.equal(verifySignatureHash({ ...good, verb: "delete" } as never), false);
  assert.equal(verifySignatureHash(null as never), false);
  assert.equal(verifySignatureHash({ ...good, signature_hash: undefined } as never), false);
});

test("a returned signature cannot be edited into a lie", () => {
  // sig.inputs.cc = "..." would change which capability this is while leaving
  // signature_hash describing the old one, and the router would read a rung
  // earned by a step that never had the field. Frozen, so it throws at the line
  // that caused it.
  const sig = base();
  assert.throws(() => { (sig.inputs as Record<string, unknown>).cc = "x"; }, TypeError);
  assert.throws(() => { (sig as { object: string }).object = "calendar_event"; }, TypeError);
  // withInputs is the legal path, and it re-hashes.
  const changed = withInputs(sig, { to: "x", subject: "y", body: "z", cc: "d" });
  assert.notEqual(changed.signature_hash, sig.signature_hash);
  assert.ok(verifySignatureHash(changed));
});

// ---------------------------------------------------------------------------
// RUNTIME GUARDS — types are stripped, not checked
// ---------------------------------------------------------------------------

test("an unknown verb is rejected at run time", () => {
  // --experimental-strip-types deletes the annotation; a planner emitting
  // {"verb":"purchase"} would otherwise hash into a rung of its own and route
  // as if it were understood.
  assert.throws(() => makeSignature({ verb: "purchase", object: "ticket", expected_effect: "e" } as never), /verb/);
  assert.throws(() => signatureHash({ verb: "purchase", object: "ticket", inputs: {} } as never), /verb/);
  assert.throws(() => makeSignature({ verb: "", object: "ticket", expected_effect: "e" } as never), /verb/);
});

test("an unknown side_effect is rejected at run time", () => {
  assert.throws(() => makeSignature({
    verb: "send", object: "email", side_effect: "maybe", expected_effect: "e",
  } as never), /side_effect/);
});

test("a missing or empty expected_effect is rejected", () => {
  // Parity between the hands is judged on this sentence and nothing else. An
  // empty one makes the verifier vacuous, and a vacuous verifier collapses
  // parity back to "did both hands return the same bytes" — which is exactly
  // how a wrong browser run certifies a wrong API run.
  assert.throws(() => makeSignature({ verb: "send", object: "email" } as never), /expected_effect/);
  assert.throws(() => makeSignature({ verb: "send", object: "email", expected_effect: "   " } as never), /expected_effect/);
});

test("a malformed object, inputs or account_hint is rejected", () => {
  assert.throws(() => makeSignature({ verb: "send", object: "", expected_effect: "e" } as never), /object/);
  assert.throws(() => makeSignature({ verb: "send", object: 7, expected_effect: "e" } as never), /object/);
  // An array has keys "0","1" — it would hash as a capability with numeric
  // input names, which is silently wrong rather than loudly wrong.
  assert.throws(() => makeSignature({ verb: "send", object: "email", inputs: ["to"], expected_effect: "e" } as never), /inputs/);
  assert.throws(() => makeSignature({ verb: "send", object: "email", inputs: null, expected_effect: "e" } as never), /inputs/);
  assert.throws(() => makeSignature({ verb: "send", object: "email", account_hint: "school", expected_effect: "e" } as never), /account_hint/);
});

// ---------------------------------------------------------------------------
// THE EFFECT-CHANNEL FLOOR — the seatbelt, and only the seatbelt
// ---------------------------------------------------------------------------

test("the floor only ever tightens; a declaration is never loosened", () => {
  // A read step that the planner says is a write (reading a message marks it
  // read) stays a write. The floor is a minimum, not an opinion.
  assert.equal(makeSignature({
    verb: "read", object: "email", side_effect: "write",
    expected_effect: "the thread is summarised for the owner",
  }).side_effect, "write");
  assert.equal(makeSignature({
    verb: "create", object: "calendar_event", side_effect: "irreversible",
    expected_effect: "one event exists with the other three invited",
  }).side_effect, "irreversible");
});

test("a pay step cannot be declared read-only", () => {
  // The concrete failure: a planner emits {verb:"pay", side_effect:"read"} —
  // a real class of mistake, since the model filling a JSON field is not the
  // model that will be gated by it — and the router's read path, which may run
  // unattended with the laptop shut, executes a payment. Moment 26 of the brief
  // is one sentence about this: money always waits for your word.
  assert.equal(makeSignature({
    verb: "pay", object: "invoice", side_effect: "read",
    expected_effect: "the invoice shows paid and the amount left the account",
  }).side_effect, "irreversible");
  assert.equal(verbSideEffectFloor("pay"), "irreversible");
});

test("a delete confirms even when nobody declared it irreversible", () => {
  // THE DEFECT THIS PINS, found twice independently in the 2026-09-05 audit:
  // `delete` used to floor at "write". So a delete built the INTENDED way —
  // makeSignature with no side_effect, because answering an absent declaration
  // is the floor's entire job — came out "write"; the router's `irreversible`
  // test was false; and no decision, on either hand, at any rung, carried
  // requiresConfirmation. The only thing left between the owner's mail and
  // permanent destruction was the candidate's own `sideEffectHint`, which the
  // MCP spec calls untrusted and which the shipped fixture's
  // GMAIL_DELETE_THREAD declares as a plain "write" ON PURPOSE. A floor that
  // defers to the vendor is not a floor.
  assert.equal(verbSideEffectFloor("delete"), "irreversible");
  assert.equal(makeSignature({
    verb: "delete", object: "email", expected_effect: "the thread is gone from all mail",
  }).side_effect, "irreversible");
  // And a planner that says "write" — the likelier mistake, since the model
  // filling the field is not the model that will be gated by it — is ratcheted
  // up rather than believed.
  assert.equal(makeSignature({
    verb: "delete", object: "email", side_effect: "write",
    expected_effect: "the thread is gone from all mail",
  }).side_effect, "irreversible");
});

test("send is floored at irreversible, and the reasoning is the floor's polarity", () => {
  // REVERSED on 2026-09-05. The previous floor was "write", reasoned as:
  // whether a sent thing can be unsent is a property of the APP (a Slack
  // message deletes, an email does not), so the verb alone cannot decide it.
  // The premise is true and the conclusion is backwards. A FLOOR is the answer
  // given when nobody with context has spoken; contract.ts's LAW1 note fixes
  // its polarity — "a privilege needs something to license it rather than
  // merely the absence of an objection" — so an absent fact must resolve to
  // the STRICT end. Flooring at "write" used the lack of context to pick the
  // loose end, which is the one shape of mistake a floor exists to prevent.
  //
  // Three concrete things it costs, none hypothetical:
  //   * docs/BRIEF.html states the seatbelt in one sentence and names sending
  //     first: "anything that sends, buys, books, posts, or deletes waits for
  //     the owner's tap."
  //   * The browser hand already obeys that. `commitControl` in
  //     extension/agent_loop.js has `send` in its commit-verb set, so pressing
  //     Send in a page goes through the authorization gate. With send floored
  //     at "write" the API hand sent the same message with no tap — the two
  //     hands doing observably different things for one step, which is the
  //     exact property this spike exists to hold.
  //   * A send cannot be undone by the hand that did it. Slack's delete does
  //     not un-ring the notification, and there is no state between "write" and
  //     "irreversible" in which to record "recallable for thirty seconds".
  //
  // The price of being wrong in this direction is one tap. The price of being
  // wrong in the other is an unapproved message in a colleague's inbox.
  assert.equal(verbSideEffectFloor("send"), "irreversible");
  assert.equal(makeSignature({
    verb: "send", object: "email", expected_effect: "sam has the message",
  }).side_effect, "irreversible");
  // A declaration cannot buy the loose end back, because tightenSideEffect
  // only ratchets. That is deliberate: the planner is the same kind of model
  // that produced the missing declaration in the first place.
  assert.equal(makeSignature({
    verb: "send", object: "email", side_effect: "write",
    expected_effect: "sam has the message",
  }).side_effect, "irreversible");
});

test("verbs the same hand can undo stay at write", () => {
  // The line the three irreversible verbs are on, stated so the next person
  // adding a verb has a rule instead of a precedent: a step is floored at
  // `irreversible` when undoing it needs somebody ELSE'S cooperation or a
  // backup — the payee's refund, the recipient's forgetting, a snapshot that
  // may not exist. `create`, `update` and `book` all produce a record this
  // same account still owns and can delete or cancel by itself, so the floor
  // leaves them at "write" and the ladder plus the opt-in do the gating.
  //
  // `book` is the uncomfortable one and is left deliberately, not by
  // oversight: the brief's seatbelt sentence names booking, but a booking is
  // cancellable by the actor and the case that is not — a non-refundable
  // ticket — is a `pay`. If that turns out to be the wrong call it should be
  // changed here with a receipt, not worked around at a call site.
  assert.equal(verbSideEffectFloor("read"), "read");
  assert.equal(verbSideEffectFloor("create"), "write");
  assert.equal(verbSideEffectFloor("update"), "write");
  assert.equal(verbSideEffectFloor("book"), "write");
});

test("a tool's own hint composes on top of the floor, and only tightens", () => {
  // The order the router applies these in: planner declaration, then the verb
  // floor (inside makeSignature), then the candidate's untrusted self-report
  // via the contract's tightenSideEffect. A tool that calls itself read-only
  // cannot turn a write into a read.
  const honest: ToolCandidate = {
    toolSlug: "GMAIL_DELETE_MESSAGE", app: "gmail", score: 0.9,
    sideEffectHint: "irreversible", schema: {}, description: "permanently deletes",
  };
  const liar: ToolCandidate = {
    toolSlug: "GMAIL_TRASH_MESSAGE", app: "gmail", score: 0.9,
    sideEffectHint: "read", schema: {}, description: "claims to be read-only",
  };
  // UPWARDS, on a verb whose floor leaves room above it. An `update` is a
  // write; a tool that reports it destroys is believed, because that direction
  // is the only one a self-report is allowed to move a step in.
  const update = makeSignature({
    verb: "update", object: "email", expected_effect: "the thread no longer carries the label",
  });
  assert.equal(update.side_effect, "write");
  assert.equal(tightenSideEffect(update.side_effect, honest.sideEffectHint), "irreversible");

  // DOWNWARDS, never. Since the delete floor moved, the liar cannot even buy
  // "write" — which is the point of putting the floor under the hint rather
  // than beside it: the guard holds with the vendor field deleted entirely.
  const del = makeSignature({
    verb: "delete", object: "email", expected_effect: "the thread is gone from the mailbox",
  });
  assert.equal(del.side_effect, "irreversible");
  assert.equal(tightenSideEffect(del.side_effect, liar.sideEffectHint), "irreversible");
});

// ---------------------------------------------------------------------------
// IS THE GUARD ACTUALLY WIRED? — a red leg, not a paragraph
// ---------------------------------------------------------------------------
// The second finding of the 2026-09-05 audit, and the reason it is a test and
// not a note: `verifySignatureHash` is exported, documented as THE defence
// against a hash somebody else computed, tested six ways above — and called by
// nobody. The router reads `sig.signature_hash` and `sig.side_effect`
// wholesale. Tested-in-isolation-and-unwired is the most expensive shape a
// guard can have, because every reader after this one sees green tests beside
// a confident docstring and concludes the hole is closed.
//
// So the wiring itself gets a leg. It is RED until some other file in the
// spike calls the function, and it must stay red rather than be softened:
// HARNESS-LAWS law 2 names the same failure one layer out — "a TAPE: comment
// pointing at a leg that tracks something else reads as compliant and enforces
// nothing".

/** The spike's own shipped source — src/ and tasks/, never test/. Being called
 *  by a test is precisely the state this leg exists to reject. */
function shippedSources(): string[] {
  const out: string[] = [];
  for (const dir of ["src", "tasks"]) {
    const base = fileURLToPath(new URL(`../${dir}/`, import.meta.url));
    for (const name of readdirSync(base)) {
      if (name.endsWith(".ts")) out.push(base + name);
    }
  }
  return out;
}

/**
 * Comments and string literals replaced with spaces.
 *
 * Without this the leg passes on a source file that merely MENTIONS the
 * function — "the router should call verifySignatureHash one day" in a comment,
 * or the name inside an audit `reason` string — which is exactly the
 * documentation-reads-as-compliance failure the leg was added to catch. Spaces
 * rather than deletion so offsets stay put.
 *
 * It over-blanks in two places — the inside of a `${...}` interpolation, and a
 * regex literal containing a quote character — and that is the direction to be
 * wrong in. Over-blanking can only HIDE a call, which leaves this leg red and
 * sends somebody to look; under-blanking would let a comment close it. A leg
 * that fails safe fails toward being read.
 */
function codeOnly(source: string): string {
  const out: string[] = [];
  let quote: string | null = null;
  let comment: "line" | "block" | null = null;
  for (let i = 0; i < source.length; i++) {
    const ch = source[i];
    const next = source[i + 1];
    if (comment === "line") {
      if (ch === "\n") { comment = null; out.push(ch); } else out.push(" ");
      continue;
    }
    if (comment === "block") {
      if (ch === "*" && next === "/") { comment = null; out.push("  "); i++; }
      else out.push(ch === "\n" ? ch : " ");
      continue;
    }
    if (quote !== null) {
      // A backslash escapes the next character, closing quote included.
      if (ch === "\\") { out.push("  "); i++; continue; }
      if (ch === quote) { quote = null; out.push(ch); continue; }
      out.push(ch === "\n" ? ch : " ");
      continue;
    }
    if (ch === '"' || ch === "'" || ch === "`") { quote = ch; out.push(ch); continue; }
    if (ch === "/" && next === "/") { comment = "line"; out.push(" "); continue; }
    if (ch === "/" && next === "*") { comment = "block"; out.push(" "); continue; }
    out.push(ch);
  }
  return out.join("");
}

// Both directions were run against planted sources before this shipped, the way
// no_production_imports.test.ts proves its own fence: a real `import
// { verifySignatureHash }` plus call in a copy of src/router.ts turns it GREEN,
// and the name planted in a line comment, a block comment and all three quote
// forms leaves it RED. A leg that can never go green is a wall, not a fence.
test("verifySignatureHash is called by shipped code, not only by this file", () => {
  // WHAT GOES WRONG WHILE THIS IS RED, stated concretely so nobody closes it by
  // deleting the leg: a step that crossed a process boundary — reloaded from
  // D1, handed back by a model, returned across the extension boundary —
  // carries a `signature_hash` this process did not compute. Swap it for the
  // hash of a promoted read pair and the router reads a rung the step never
  // earned, on a `side_effect` from the same untrusted object. That is a delete
  // executing on a read's track record, which is the one outcome the whole
  // ladder exists to make impossible.
  const callers = shippedSources().filter((f) => {
    if (f.endsWith("/signature.ts")) return false; // the definition is not a call site
    return codeOnly(readFileSync(f, "utf8")).includes("verifySignatureHash");
  });
  assert.ok(
    callers.length > 0,
    "verifySignatureHash is exported, documented as the guard against a swapped hash, "
      + "and called by nothing the spike ships. src/router.ts is the site: a signature "
      + "that arrives from outside this process must be verified before its hash is used "
      + "to read a rung or its side_effect is used to decide confirmation. This leg is "
      + "RED on purpose and closes by WIRING it, never by relaxing this assertion.",
  );
});

// ---------------------------------------------------------------------------
// THE FIVE RECIPES — the file is checked, not just written
// ---------------------------------------------------------------------------

const RECIPES = JSON.parse(readFileSync(
  fileURLToPath(new URL("../tasks/five_recipe_signatures.json", import.meta.url)), "utf8",
));

test("five recipe signatures, each hashing to the value stored beside it", () => {
  // A hand-written hash in a fixture is a lie waiting to happen: it is copied
  // once, the shape changes, and the file goes on claiming a key nothing
  // produces. This recomputes all five from the same function the router uses.
  assert.equal(RECIPES.length, 5);
  const seen = new Set<string>();
  for (const r of RECIPES) {
    assert.equal(typeof r.moment, "number", "each recipe names its moment in the brief");
    assert.ok(typeof r.scene === "string" && r.scene.trim().length > 0);
    assert.ok(typeof r.why_api_shaped === "string" && r.why_api_shaped.trim().length > 0);
    assert.ok(
      typeof r.browser_fallback_when === "string" && r.browser_fallback_when.trim().length > 0,
      `moment ${r.moment} must say when it falls back — a capability with no fallback is a capability that strands the owner`,
    );
    assert.ok(verifySignatureHash(r.signature), `moment ${r.moment} hash does not match its own fields`);
    assert.equal(r.signature.signature_hash, makeSignature(r.signature).signature_hash);
    seen.add(r.signature.signature_hash);
  }
  // Five distinct capabilities, not one capability written five ways — the
  // point of picking five different moments before touching the planner.
  assert.equal(seen.size, 5);
});

test("the recipes exercise both ends of the effect channel", () => {
  // If all five were reads the exercise would prove nothing about the part that
  // can hurt: the router's rules only differ once a step writes.
  const effects = new Set(RECIPES.map((r: { signature: { side_effect: string } }) => r.signature.side_effect));
  assert.ok(effects.has("read"));
  assert.ok(effects.has("write"));
  assert.ok(effects.has("irreversible"));
});

test("the recipe scenes are verbatim from the brief", () => {
  // The recipes are the bridge between the fifty moments and the code. A scene
  // paraphrased here is a requirement quietly rewritten, and nobody would ever
  // catch it — so the file is checked against docs/BRIEF.html itself.
  const brief = readFileSync(
    fileURLToPath(new URL("../../../docs/BRIEF.html", import.meta.url)), "utf8",
  );
  for (const r of RECIPES) {
    const m = brief.match(new RegExp(`<span class="n">${r.moment}</span><span class="scene">([\\s\\S]*?)</span>`));
    assert.ok(m, `moment ${r.moment} is not in the brief`);
    assert.equal(r.scene, m![1], `moment ${r.moment}'s scene has drifted from the brief`);
  }
});
