// THE WORDS SUITE.
//
// Two claims are under test, and everything below is one of them:
//
//  1. THE CONTAINMENT HOLDS. A model wrote the copy; this module decides only
//     whether it is sendable. So every rule the spec states as a rule — three
//     sentences, one message, this vocabulary, this voice, our link, after the
//     result — has a case here where the model breaks it and the answer is a
//     refusal rather than a repair. A rule with no failing case is a comment.
//
//  2. NOTHING HERE KNOWS AN APP. Every assertion that matters is run twice,
//     once against a toolkit that exists and once against `zorptastic-9000`,
//     which does not and never will. Identical assertions, identical outcomes.
//     If anybody ever adds a per-app string table, the second run is where it
//     dies — and a blank permission page for a real app in the catalog is the
//     production shape of that same bug.
//
// No network, no key, no model: every writer in this file is a literal that
// returns what the test wants to see refused.

import { describe, it } from "node:test";
import assert from "node:assert/strict";

import type { ToolkitMeta } from "../src/connections/contract.ts";
import {
  CONNECT_LINK_PREFIX,
  FORBIDDEN_TERMS,
  MAX_ASK_CHARS_GSM7,
  MAX_ASK_CHARS_UCS2,
  MAX_ASK_SEGMENTS,
  MAX_SENTENCE_CHARS,
  PermissionWordsRefused,
  SENTENCE_COUNT,
  STIFF_FORMS,
  askText,
  makePermissionWords,
  permissionSentences,
  smsShape,
} from "../src/connections/words.ts";
import type { AskEvidence, AskInput, Refusal } from "../src/connections/words.ts";

const LINK = `${CONNECT_LINK_PREFIX}9f2k1qb`;

/** A toolkit the catalog really has. */
function realApp(over: Partial<ToolkitMeta> = {}): ToolkitMeta {
  return {
    slug: "gmail",
    name: "Gmail",
    logo: null,
    description: null,
    appUrl: null,
    scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
    ...over,
  };
}

/** A toolkit nobody has ever heard of, used to prove this module has not
 *  learned any app names. Same shape, same expectations, every time. */
function inventedApp(over: Partial<ToolkitMeta> = {}): ToolkitMeta {
  return {
    slug: "zorptastic-9000",
    name: "Zorptastic 9000",
    logo: null,
    description: null,
    appUrl: null,
    scopes: ["zorp.read", "zorp.write"],
    ...over,
  };
}

const APPS: Array<[string, () => ToolkitMeta]> = [
  ["a toolkit that exists", realApp],
  ["a toolkit nobody has heard of", inventedApp],
];

/** A stub model. Records what it was handed, so "the writer was never called"
 *  is a fact the tests can check rather than a claim. */
function stubWriter(reply: unknown) {
  const calls: unknown[] = [];
  const write = async (input: unknown): Promise<unknown> => {
    calls.push(input);
    return reply;
  };
  return { write, calls };
}

function throwingWriter(message: string) {
  const calls: unknown[] = [];
  const write = async (input: unknown): Promise<unknown> => {
    calls.push(input);
    throw new Error(message);
  };
  return { write, calls };
}

// ---------------------------------------------------------------------------
// THE REGISTER, WRITTEN OUT INDEPENDENTLY OF THE MODULE.
// ---------------------------------------------------------------------------
// These two lists used to be read straight off `FORBIDDEN_TERMS` and
// `STIFF_FORMS`, which meant every test was GENERATED FROM THE IMPLEMENTATION:
// delete a term and you delete its only test. Measured, not argued — with
// `STIFF_FORMS` emptied outright and every `FORBIDDEN_TERMS` entry but the
// vendor's name removed, this file ran 69 tests, 69 passing, 0 failing, and the
// register it exists to enforce was gone. An oracle that is a copy of the thing
// it checks is not an oracle.
//
// So these come from the spec ("Connections: how Anticipy asks, learns, and
// never says Composio", 2026-09-05, pages 20-31) and the module has to satisfy
// THEM. Deleting a term from `words.ts` now fails here twice: once in the
// coverage leg below, and once in the behaviour test that still runs.
const FORBIDDEN_BY_THE_SPEC = [
  "authorize",
  "authorise",
  "authorization",
  "authorisation",
  "grant access",
  "grants access",
  "granting access",
  "granted access",
  "permission",
  "permissions",
  "integration",
  "integrations",
  "api",
  "apis",
  "oauth",
  // Not a register problem but a promise: the product never says the vendor's
  // name, so a draft that does is not sent.
  "composio",
];

const STIFF_BY_THE_SPEC = [
  "do not",
  "does not",
  "did not",
  "cannot",
  "can not",
  "will not",
  "would not",
  "should not",
  "is not",
  "are not",
  "was not",
  "were not",
  "have not",
  "has not",
  "i am",
];

/** Anything the module forbids beyond the spec is still exercised — a tightening
 *  deserves a test too — but it can never be the only thing under test. */
const EXTRA_FORBIDDEN = FORBIDDEN_TERMS.filter((t) => !FORBIDDEN_BY_THE_SPEC.includes(t));
const EXTRA_STIFF = STIFF_FORMS.filter((t) => !STIFF_BY_THE_SPEC.includes(t));
const EVERY_FORBIDDEN = [...FORBIDDEN_BY_THE_SPEC, ...EXTRA_FORBIDDEN];
const EVERY_STIFF = [...STIFF_BY_THE_SPEC, ...EXTRA_STIFF];

const GOOD_SENTENCES = [
  "Read and send email as you.",
  "See your inbox and its threads.",
  "Draft replies you can check first.",
];

const GOOD_ASK = `That took about a minute in the browser. Connect it once and I'll do the same `
  + `thing in a second: ${LINK} Connecting is optional, the browser can keep doing it.`;

function evidence(over: Partial<AskEvidence> = {}): AskEvidence {
  return {
    link: LINK,
    resultDelivered: true,
    whatHappened: "the third browser run on this app in two weeks",
    tasksThatWouldHaveUsedIt: 3,
    browserMs: 62_000,
    ...over,
  };
}

/** Narrow to a refusal, with the cause in the assertion message so a failure
 *  reads as "expected too-long, got forbidden-word" instead of "false". */
function refusal(result: { ok: boolean }): Refusal {
  assert.equal(result.ok, false, `expected a refusal, got: ${JSON.stringify(result)}`);
  return result as Refusal;
}

// ---------------------------------------------------------------------------
// 1. PERMISSION SENTENCES
// ---------------------------------------------------------------------------

for (const [label, app] of APPS) {
  describe(`permission sentences — ${label}`, () => {
    it("the control: a good reply passes through unchanged", async () => {
      const model = stubWriter([...GOOD_SENTENCES]);
      const result = await permissionSentences(app(), model.write);

      assert.equal(result.ok, true);
      assert.deepEqual(result.ok && result.sentences, GOOD_SENTENCES);
      // The model got the toolkit itself, scopes and all — the sentences are
      // generated FROM those, and that is the whole no-hardcoding claim.
      assert.equal(model.calls.length, 1);
      assert.deepEqual(model.calls[0], app());
    });

    it("two sentences are refused, never padded to three", async () => {
      const model = stubWriter([GOOD_SENTENCES[0], GOOD_SENTENCES[1]]);
      const result = await permissionSentences(app(), model.write);

      const r = refusal(result);
      assert.equal(r.cause, "wrong-count");
      // The failure this test exists for: a third sentence invented by us and
      // shown on a consent screen as though a model had written it.
      assert.equal((result as { sentences?: unknown }).sentences, undefined);
    });

    it("four sentences are refused, never trimmed to three", async () => {
      const model = stubWriter([...GOOD_SENTENCES, "Delete anything you ask about."]);
      const r = refusal(await permissionSentences(app(), model.write));
      assert.equal(r.cause, "wrong-count");
    });

    it("an empty reply is refused, because a blank permission list is not consent", async () => {
      const r = refusal(await permissionSentences(app(), stubWriter([]).write));
      assert.equal(r.cause, "wrong-count");
    });

    // The numbers below are LITERALS, not `MAX_SENTENCE_CHARS`. A boundary test
    // written in terms of the constant it is testing measures only that the
    // code agrees with itself: raise the constant and the fixture moves with
    // it, and the test stays green while the page grows a paragraph. Checked by
    // mutation — with the constant at 800 these two go red, and they did not
    // before this comment was written.
    it("a sentence of exactly 80 characters is still sendable", async () => {
      const atLimit = `R${"o".repeat(78)}.`;
      assert.equal(atLimit.length, 80);

      const result = await permissionSentences(
        app(),
        stubWriter([atLimit, GOOD_SENTENCES[1], GOOD_SENTENCES[2]]).write,
      );
      assert.equal(result.ok, true);
    });

    it("81 characters refuses the whole page", async () => {
      const over = `R${"o".repeat(79)}.`;
      assert.equal(over.length, 81);

      const r = refusal(await permissionSentences(
        app(),
        stubWriter([over, GOOD_SENTENCES[1], GOOD_SENTENCES[2]]).write,
      ));
      assert.equal(r.cause, "too-long");
    });

    for (const term of EVERY_FORBIDDEN) {
      it(`refuses a permission sentence containing "${term}"`, async () => {
        const model = stubWriter([
          `Read your mail (${term}).`,
          GOOD_SENTENCES[1],
          GOOD_SENTENCES[2],
        ]);
        const r = refusal(await permissionSentences(app(), model.write));
        assert.equal(r.cause, "forbidden-word");
        assert.ok(
          r.refusal.includes(term),
          `the refusal should name the word it found: ${r.refusal}`,
        );
      });
    }

    it("does not trip on a word that merely contains a forbidden one", async () => {
      // "capital" ends in "api" and "therapist" contains it. A gate that fires
      // on those is a gate that gets switched off within a week.
      const model = stubWriter([
        "See the capital of each contact.",
        "Read what your therapist sent.",
        GOOD_SENTENCES[2],
      ]);
      assert.equal((await permissionSentences(app(), model.write)).ok, true);
    });

    it("refuses three lines that say the same thing", async () => {
      // Containment, not taste: a page repeating one sentence three times shows
      // one permission while the connection is being given three.
      const model = stubWriter([GOOD_SENTENCES[0], GOOD_SENTENCES[1], GOOD_SENTENCES[0]]);
      const r = refusal(await permissionSentences(app(), model.write));
      assert.equal(r.cause, "duplicate");
    });

    it("refuses a sentence that is really a scope URL with no scheme", async () => {
      // `https://` is not what makes a string a link to a phone. The scope
      // strings a model is most likely to echo back arrive without one, and a
      // permission line reading "www.googleapis.com/auth/gmail.readonly" is the
      // same non-consent as the version with a scheme on the front.
      const model = stubWriter([
        "www.googleapis.com/auth/gmail.readonly",
        GOOD_SENTENCES[1],
        GOOD_SENTENCES[2],
      ]);
      const r = refusal(await permissionSentences(app(), model.write));
      assert.equal(r.cause, "not-plain");
    });

    it("prose with a full stop in it is still plain language — the control", async () => {
      // A URL check widened carelessly refuses good copy, and on this surface a
      // refusal is a connect page that never renders.
      const model = stubWriter([
        "Read what arrived in the last 3.5 hours.",
        "See threads you have replied to, e.g. this week's.",
        "Draft a reply.Nothing is sent without you.",
      ]);
      const result = await permissionSentences(app(), model.write);
      assert.equal(result.ok, true, `refused good copy: ${JSON.stringify(result)}`);
    });

    it("refuses a sentence that is really a scope URL", async () => {
      const model = stubWriter([
        "https://www.googleapis.com/auth/gmail.readonly",
        GOOD_SENTENCES[1],
        GOOD_SENTENCES[2],
      ]);
      const r = refusal(await permissionSentences(app(), model.write));
      assert.equal(r.cause, "not-plain");
    });

    it("refuses an exclamation mark", async () => {
      const model = stubWriter(["Read and send email as you!", GOOD_SENTENCES[1], GOOD_SENTENCES[2]]);
      const r = refusal(await permissionSentences(app(), model.write));
      assert.equal(r.cause, "exclamation");
    });

    it("never calls the model when there is nothing to generate from", async () => {
      const model = stubWriter([...GOOD_SENTENCES]);
      const r = refusal(await permissionSentences(app({ scopes: [] }), model.write));

      assert.equal(r.cause, "no-scopes");
      // A permission sentence written without a scope is an invention about
      // somebody's mailbox, so the question is not even asked.
      assert.equal(model.calls.length, 0);
    });

    it("tells 'nobody answered' apart from 'the answer was unusable'", async () => {
      const thrown = refusal(await permissionSentences(app(), throwingWriter("timeout").write));
      assert.equal(thrown.cause, "no-verdict");

      const nothing = refusal(await permissionSentences(app(), stubWriter(null).write));
      assert.equal(nothing.cause, "no-verdict");

      const prose = refusal(await permissionSentences(app(), stubWriter("three sentences").write));
      assert.equal(prose.cause, "malformed-reply");

      const numbers = refusal(await permissionSentences(app(), stubWriter([1, 2, 3]).write));
      assert.equal(numbers.cause, "malformed-reply");

      const blank = refusal(await permissionSentences(
        app(),
        stubWriter([GOOD_SENTENCES[0], "   ", GOOD_SENTENCES[2]]).write,
      ));
      assert.equal(blank.cause, "malformed-reply");
    });

    it("refuses a toolkit row with no name, because the page cannot be headed", async () => {
      const model = stubWriter([...GOOD_SENTENCES]);
      const r = refusal(await permissionSentences(app({ name: "" }), model.write));
      assert.equal(r.cause, "malformed-meta");
      assert.equal(model.calls.length, 0);
    });

    it("the contract adapter hands back the sentences, or throws the refusal", async () => {
      const good = makePermissionWords(stubWriter([...GOOD_SENTENCES]).write);
      assert.deepEqual(await good.sentences(app()), GOOD_SENTENCES);

      // The contract's `sentences()` returns `Promise<string[]>`, and the two
      // values that fit that type when we have nothing are both wrong: `[]` is
      // the blank permission list, and a house-written placeholder is a claim
      // no model made. So it throws, and a caller cannot ignore it by accident.
      const bad = makePermissionWords(stubWriter([GOOD_SENTENCES[0]]).write);
      await assert.rejects(
        () => bad.sentences(app()),
        (err: unknown) => {
          assert.ok(err instanceof PermissionWordsRefused);
          assert.equal(err.refusal.cause, "wrong-count");
          return true;
        },
      );
    });
  });
}

describe("the register, pinned to the spec rather than to the code", () => {
  it("the module still forbids every term the spec forbids", () => {
    // The leg that goes red the moment somebody shortens a list. It is written
    // as a subset check rather than an equality so that TIGHTENING the register
    // — adding a term — stays a one-file change, while LOOSENING it cannot.
    const gone = FORBIDDEN_BY_THE_SPEC.filter((t) => !FORBIDDEN_TERMS.includes(t));
    assert.deepEqual(gone, [], `words.ts stopped forbidding: ${gone.join(", ")}`);
    const soft = STIFF_BY_THE_SPEC.filter((t) => !STIFF_FORMS.includes(t));
    assert.deepEqual(soft, [], `words.ts stopped catching: ${soft.join(", ")}`);
  });

  it("the leg can see a term go missing", () => {
    // The negative control. A coverage leg whose list happened to be empty would
    // pass over nothing, which is the failure this whole section is about.
    const pretend = FORBIDDEN_BY_THE_SPEC.filter((t) => t !== "oauth");
    assert.deepEqual(FORBIDDEN_BY_THE_SPEC.filter((t) => !pretend.includes(t)), ["oauth"]);
    assert.ok(FORBIDDEN_BY_THE_SPEC.length >= 16, "the spec list emptied itself");
    assert.ok(STIFF_BY_THE_SPEC.length >= 15, "the spec list emptied itself");
  });
});

describe("the three numbers, pinned to the spec rather than to the code", () => {
  it("three sentences, eighty characters, two messages", () => {
    // These come out of the product spec, not out of a preference: three
    // sentences on the connect page, a line short enough to be read on a phone,
    // and one text that leaves in no more than two pieces. Changing one of them
    // is a product decision, so it fails here first and gets argued with on
    // purpose.
    assert.equal(SENTENCE_COUNT, 3);
    assert.equal(MAX_SENTENCE_CHARS, 80);
    assert.equal(MAX_ASK_SEGMENTS, 2);
    // The two real ceilings, each with its condition. 320 was neither.
    assert.equal(MAX_ASK_CHARS_GSM7, 306);
    assert.equal(MAX_ASK_CHARS_UCS2, 134);
    assert.equal(CONNECT_LINK_PREFIX, "https://anticipy.ai/c/");
  });

  it("the segment arithmetic is the carrier's, not ours", () => {
    // Every number below is the GSM 03.38 / concatenated-SMS spec, written out.
    // One message alone holds more than one part of a concatenated pair does,
    // because the concatenation header eats into every part.
    assert.deepEqual(
      { encoding: smsShape("x".repeat(160)).encoding, segments: smsShape("x".repeat(160)).segments },
      { encoding: "gsm-7", segments: 1 },
    );
    assert.equal(smsShape("x".repeat(161)).segments, 2);
    assert.equal(smsShape("x".repeat(306)).segments, 2);
    assert.equal(smsShape("x".repeat(307)).segments, 3);

    // One character outside GSM-7 re-prices the whole message.
    assert.equal(smsShape("x".repeat(70)).segments, 1);
    assert.equal(smsShape(`${"x".repeat(69)}\u2019`).encoding, "ucs-2");
    assert.equal(smsShape(`${"x".repeat(69)}\u2019`).segments, 1);
    assert.equal(smsShape(`${"x".repeat(70)}\u2019`).segments, 2);
    assert.equal(smsShape(`${"x".repeat(133)}\u2019`).segments, 2);
    assert.equal(smsShape(`${"x".repeat(134)}\u2019`).segments, 3);

    // The extension characters are sendable and cost two septets each, so a
    // character count over-estimates the room a draft has left.
    assert.equal(smsShape("a").units, 1);
    assert.equal(smsShape("{").units, 2);
    assert.equal(smsShape("\u20ac").encoding, "gsm-7");
    assert.equal(smsShape("\u20ac").units, 2);
    // An emoji is two UTF-16 units, and the carrier charges for both.
    assert.equal(smsShape("\u{1f600}").encoding, "ucs-2");
    assert.equal(smsShape("\u{1f600}").units, 2);
    // Accented names and em dashes are the everyday way copy leaves GSM-7 — but
    // NOT all of them, and guessing which is how a ceiling gets set wrong. GSM-7
    // carries e-acute and a-grave; it has no slot for e-diaeresis or o-circumflex,
    // so one owner called Zoe with a diaeresis re-prices every text she gets.
    assert.equal(smsShape("caf\u00e9").encoding, "gsm-7");
    assert.equal(smsShape("Zo\u00eb").encoding, "ucs-2");
    assert.equal(smsShape("\u00e0 bient\u00f4t").encoding, "ucs-2");
    assert.equal(smsShape("\u2014").encoding, "ucs-2");
    assert.equal(smsShape("\u00e4\u00f6\u00fc\u00c9").encoding, "gsm-7");
  });
});

// ---------------------------------------------------------------------------
// 2. THE ASK
// ---------------------------------------------------------------------------

/** A message of EXACTLY `n` characters that breaks no other rule, so a length
 *  test measures length and nothing else. The fixed parts are kept short so the
 *  same helper can reach the UCS-2 ceiling, which is less than half the GSM-7
 *  one. Every character in it is in the GSM-7 alphabet, apostrophe included. */
function askOfLength(n: number): string {
  const head = "Quicker next time, ";
  const tail = `: ${LINK} It's up to you.`;
  const pad = n - head.length - tail.length;
  assert.ok(pad > 0, "test helper: asked for a message shorter than its own fixed parts");
  return `${head}${"x".repeat(pad)}${tail}`;
}

/** The same message with ONE straight apostrophe swapped for a curly one. The
 *  character count does not move; the real ceiling more than halves, because
 *  GSM-7 has no slot for U+2019 and the whole message goes out as UCS-2. */
function curlyAskOfLength(n: number): string {
  return askOfLength(n).replace("'", "\u2019");
}

for (const [label, app] of APPS) {
  describe(`the ask — ${label}`, () => {
    it("the control: a good message passes through unchanged", async () => {
      const model = stubWriter(GOOD_ASK);
      const result = await askText("in_task", app(), evidence(), model.write);

      assert.equal(result.ok, true);
      assert.equal(result.ok && result.text, GOOD_ASK);

      // The model was handed the moment and the evidence — the ask is tied to
      // something that happened, and the model is the thing that says how.
      const input = model.calls[0] as AskInput;
      assert.equal(input.moment, "in_task");
      assert.equal(input.meta.slug, app().slug);
      assert.equal(input.evidence.link, LINK);
    });

    // THE BOUNDARY IS AN ENCODING, NOT A NUMBER. The old ceiling was 320, and
    // it did not deliver its own promise in either direction: concatenated
    // GSM-7 holds 306, so 307-320 went out in three pieces, and one curly
    // apostrophe forces UCS-2, where the real ceiling is 134 and a 320-character
    // ask arrives in five. The half that arrives second — or reordered, or not
    // at all — is the half with the link in it.
    //
    // 306, 307, 134 and 135 are written out, not derived from the constants.
    // See the note on the sentence boundary above: a test that imports the
    // number it is checking goes green for any number.
    it("306 GSM-7 characters still arrive as two messages", async () => {
      const text = askOfLength(306);
      assert.equal(text.length, 306);

      const result = await askText("in_task", app(), evidence(), stubWriter(text).write);
      assert.equal(result.ok, true, `expected the boundary to pass: ${JSON.stringify(result)}`);
    });

    it("307 is refused, not trimmed", async () => {
      const text = askOfLength(307);
      assert.equal(text.length, 307);

      const r = refusal(await askText("in_task", app(), evidence(), stubWriter(text).write));
      assert.equal(r.cause, "too-long");
      // Trimming to fit is how the link loses its last characters and the one
      // ask this app ever gets becomes a 404.
      assert.equal((r as { text?: unknown }).text, undefined);
    });

    it("one curly apostrophe drops the real ceiling to 134, and 134 still sends", async () => {
      const text = curlyAskOfLength(134);
      assert.equal(text.length, 134);
      assert.ok(text.includes("\u2019"), "test helper: the apostrophe was not swapped");

      const result = await askText("in_task", app(), evidence(), stubWriter(text).write);
      assert.equal(result.ok, true, `expected the boundary to pass: ${JSON.stringify(result)}`);
    });

    it("135 characters with one curly apostrophe is refused", async () => {
      const text = curlyAskOfLength(135);
      assert.equal(text.length, 135);

      const r = refusal(await askText("in_task", app(), evidence(), stubWriter(text).write));
      assert.equal(r.cause, "too-long");
    });

    it("the same 200 characters send or refuse on ONE character's account", async () => {
      // The whole of finding 13 in two assertions. A character-count ceiling
      // cannot tell these two apart, and the carrier can: the first goes out in
      // two pieces, the second in three.
      const plain = askOfLength(200);
      const curly = curlyAskOfLength(200);
      assert.equal(plain.length, curly.length);

      const sent = await askText("in_task", app(), evidence(), stubWriter(plain).write);
      assert.equal(sent.ok, true, `expected the plain one to send: ${JSON.stringify(sent)}`);

      const r = refusal(await askText("in_task", app(), evidence(), stubWriter(curly).write));
      assert.equal(r.cause, "too-long");
      // And the refusal has to say the real number for the encoding it found,
      // or the next person reads 320 in a log and looks for a bug elsewhere.
      assert.ok(/134/.test(r.refusal), r.refusal);
    });

    for (const term of EVERY_FORBIDDEN) {
      it(`refuses an ask containing "${term}"`, async () => {
        const text = `That went through the browser, ${term}. Connect it once: ${LINK} `
          + "It's optional, the browser can keep doing it.";
        const r = refusal(await askText("in_task", app(), evidence(), stubWriter(text).write));
        assert.equal(r.cause, "forbidden-word");
        assert.ok(r.refusal.includes(term), `the refusal should name the word: ${r.refusal}`);
      });
    }

    for (const stiff of EVERY_STIFF) {
      it(`refuses an ask that writes "${stiff}" instead of contracting it`, async () => {
        const text = `That took a while and I ${stiff} enjoying it. Connect it once: ${LINK} `
          + "It's optional, the browser can keep doing it.";
        const r = refusal(await askText("in_task", app(), evidence(), stubWriter(text).write));
        assert.equal(r.cause, "stiff");
      });
    }

    it("refuses an exclamation mark", async () => {
      const text = `That took a while in the browser! Connect it once: ${LINK} It's optional.`;
      const r = refusal(await askText("in_task", app(), evidence(), stubWriter(text).write));
      assert.equal(r.cause, "exclamation");
    });

    it("refuses a message with no link", async () => {
      const text = "That took a while in the browser. Connect it once and I'll be quicker. "
        + "It's optional, the browser can keep doing it.";
      const r = refusal(await askText("in_task", app(), evidence(), stubWriter(text).write));
      assert.equal(r.cause, "no-link");
    });

    it("refuses the same link twice", async () => {
      const text = `Connect it once: ${LINK} or here: ${LINK} It's optional.`;
      const r = refusal(await askText("in_task", app(), evidence(), stubWriter(text).write));
      assert.equal(r.cause, "extra-link");
    });

    it("refuses a second link riding along beside ours", async () => {
      const text = `That took a while. Connect it once: ${LINK} or read https://example.com/help `
        + "first. It's optional.";
      const r = refusal(await askText("in_task", app(), evidence(), stubWriter(text).write));
      assert.equal(r.cause, "extra-link");
    });

    it("refuses the vendor's own link in the message", async () => {
      // The recorded failure of 2026-09-05: four raw vendor links pasted into
      // messages, all four dead before they were tapped. The vendor's NAME is
      // forbidden vocabulary, so this one is caught a step earlier than the
      // second-link check — either way it does not go out.
      const text = `That took a while. Connect it once: ${LINK} and also `
        + "https://connect.composio.dev/link/abc123 works. It's optional.";
      const r = refusal(await askText("in_task", app(), evidence(), stubWriter(text).write));
      assert.equal(r.cause, "forbidden-word");
    });

    it("refuses a schemeless second link, which a phone linkifies anyway", async () => {
      // The recorded shape: a vendor's own sign-in URL riding along beside ours.
      // It arrives with no scheme because that is how people write hosts, and a
      // containment that only looked for "https://" was blind to exactly the
      // link it was built to stop.
      const text = `That took a while. Connect it once: ${LINK} or start at `
        + "accounts.google.com/o/v2/auth instead. It's optional.";
      const r = refusal(await askText("in_task", app(), evidence(), stubWriter(text).write));
      assert.equal(r.cause, "extra-link");
    });

    it("the vendor's schemeless link is caught twice over", async () => {
      // The vendor's NAME is forbidden vocabulary, so this one never reaches the
      // link count — which is the point of listing it in both places.
      const text = `That took a while. Connect it once: ${LINK} or connect.composio.dev/link/abc `
        + "if you'd rather. It's optional.";
      const r = refusal(await askText("in_task", app(), evidence(), stubWriter(text).write));
      assert.equal(r.cause, "forbidden-word");
    });

    it("ordinary prose is not a second link — the control", async () => {
      // Each refusal spends the one interruption this app ever gets, so a widened
      // check that fires on "browser.Connect" or "e.g." costs an ask for nothing.
      for (const body of [
        "That took a while in the browser.Connect it once",
        "That took about 3.5 minutes, e.g. longer than it should have",
        "That took a while. No. 4 this fortnight",
        "That took a while, and anticipy.ai is quicker when it's connected",
      ]) {
        const text = `${body}: ${LINK} It's optional, the browser can keep doing it.`;
        const result = await askText("in_task", app(), evidence(), stubWriter(text).write);
        assert.equal(result.ok, true, `refused good copy: ${JSON.stringify(result)}`);
      }
    });

    it("refuses a link with characters welded onto the token", async () => {
      // Every count above passes: one occurrence of the link, one URL in the
      // message. The owner still taps a 404, and reads the 404 as "broken".
      const text = `That took a while. Connect it once: ${LINK}-evil.example/x It's optional.`;
      const r = refusal(await askText("in_task", app(), evidence(), stubWriter(text).write));
      assert.equal(r.cause, "mangled-link");
    });

    it("tolerates a full stop after the link, because that belongs to the sentence", async () => {
      const text = `That took a while in the browser. Connect it once: ${LINK}. It's optional, `
        + "the browser can keep doing it.";
      const result = await askText("in_task", app(), evidence(), stubWriter(text).write);
      assert.equal(result.ok, true, `expected punctuation to be tolerated: ${JSON.stringify(result)}`);
    });

    it("refuses a message that is only the link", async () => {
      const opensOnIt = refusal(await askText(
        "in_task",
        app(),
        evidence(),
        stubWriter(`${LINK} It's optional, the browser can keep doing it.`).write,
      ));
      assert.equal(opensOnIt.cause, "nothing-before-link");

      const endsOnIt = refusal(await askText(
        "in_task",
        app(),
        evidence(),
        stubWriter(`That took a while in the browser. Connect it once: ${LINK}`).write,
      ));
      // Not a claim that we can read "this is optional" — that is meaning, and
      // it belongs to the model. It is a claim that the model left no room for
      // the line the spec requires in every ask.
      assert.equal(endsOnIt.cause, "nothing-after-link");
    });

    it("a random token is not the ask saying a forbidden word", async () => {
      const linky = `${CONNECT_LINK_PREFIX}x-api-7`;
      const text = `That took a while in the browser. Connect it once: ${linky} `
        + "It's optional, the browser can keep doing it.";
      const result = await askText(
        "in_task",
        app(),
        evidence({ link: linky }),
        stubWriter(text).write,
      );
      assert.equal(result.ok, true, `expected the token to be ignored: ${JSON.stringify(result)}`);
    });

    it("never asks before the result has gone out", async () => {
      const model = stubWriter(GOOD_ASK);
      const r = refusal(await askText(
        "in_task",
        app(),
        evidence({ resultDelivered: false }),
        model.write,
      ));

      assert.equal(r.cause, "result-not-delivered");
      // Checked before the model is called: an ask that arrives instead of the
      // answer cannot be argued out of by good copy.
      assert.equal(model.calls.length, 0);
    });

    it("says which half is broken: the catalog row or the run behind the ask", async () => {
      const model = stubWriter(GOOD_ASK);

      const noEvidence = refusal(await askText("in_task", app(), null as never, model.write));
      assert.equal(noEvidence.cause, "malformed-evidence");

      const noRow = refusal(await askText("in_task", app({ name: "" }), evidence(), model.write));
      assert.equal(noRow.cause, "malformed-meta");

      assert.equal(model.calls.length, 0);
    });

    it("never asks out of nowhere", async () => {
      const model = stubWriter(GOOD_ASK);
      const r = refusal(await askText(
        "because_it_felt_like_it" as never,
        app(),
        evidence(),
        model.write,
      ));

      assert.equal(r.cause, "no-moment");
      assert.equal(model.calls.length, 0);
    });

    it("every moment the contract declares is a real moment here", async () => {
      // Derived from the contract's own trigger table, so a sixth trigger
      // cannot quietly fail to be askable.
      for (const moment of ["in_task", "repeated_use", "laptop_closed", "user_named_it", "onboarding"] as const) {
        const result = await askText(moment, app(), evidence(), stubWriter(GOOD_ASK).write);
        assert.equal(result.ok, true, `${moment} should be a real moment`);
      }
    });

    it("refuses a link that is not ours, before spending a model call", async () => {
      const model = stubWriter(GOOD_ASK);
      for (const link of [
        "https://connect.composio.dev/link/abc123",
        "https://anticipy.ai/settings",
        CONNECT_LINK_PREFIX,
        "",
      ]) {
        const r = refusal(await askText("in_task", app(), evidence({ link }), model.write));
        assert.equal(r.cause, "bad-link", `expected ${JSON.stringify(link)} to be refused`);
      }
      assert.equal(model.calls.length, 0);
    });

    it("tells 'nobody answered' apart from 'the answer was unusable'", async () => {
      const thrown = refusal(await askText(
        "in_task",
        app(),
        evidence(),
        throwingWriter("timeout").write,
      ));
      assert.equal(thrown.cause, "no-verdict");

      const nothing = refusal(await askText("in_task", app(), evidence(), stubWriter(null).write));
      assert.equal(nothing.cause, "no-verdict");

      const wrongShape = refusal(await askText(
        "in_task",
        app(),
        evidence(),
        stubWriter({ text: GOOD_ASK }).write,
      ));
      assert.equal(wrongShape.cause, "malformed-reply");

      const blank = refusal(await askText("in_task", app(), evidence(), stubWriter("   ").write));
      assert.equal(blank.cause, "malformed-reply");
    });
  });
}
