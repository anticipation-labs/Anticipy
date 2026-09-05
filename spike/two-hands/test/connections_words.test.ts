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
  MAX_ASK_CHARS,
  MAX_SENTENCE_CHARS,
  PermissionWordsRefused,
  SENTENCE_COUNT,
  STIFF_FORMS,
  askText,
  makePermissionWords,
  permissionSentences,
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

    for (const term of FORBIDDEN_TERMS) {
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

describe("the three numbers, pinned to the spec rather than to the code", () => {
  it("three sentences, eighty characters, one message", () => {
    // These come out of the product spec, not out of a preference: three
    // sentences on the connect page, a line short enough to be read on a phone,
    // and one text message. Changing one of them is a product decision, so it
    // fails here first and gets argued with on purpose.
    assert.equal(SENTENCE_COUNT, 3);
    assert.equal(MAX_SENTENCE_CHARS, 80);
    assert.equal(MAX_ASK_CHARS, 320);
    assert.equal(CONNECT_LINK_PREFIX, "https://anticipy.ai/c/");
  });
});

// ---------------------------------------------------------------------------
// 2. THE ASK
// ---------------------------------------------------------------------------

/** A message of EXACTLY `n` characters that breaks no other rule, so a length
 *  test measures length and nothing else. */
function askOfLength(n: number): string {
  const head = "That took a while in the browser, ";
  const tail = `. Connect it once and I'll be quicker: ${LINK} It's optional, the browser `
    + "can keep doing this.";
  const pad = n - head.length - tail.length;
  assert.ok(pad > 0, "test helper: asked for a message shorter than its own fixed parts");
  return `${head}${"x".repeat(pad)}${tail}`;
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

    // 320 and 321 are written out, not derived from `MAX_ASK_CHARS`. See the
    // note on the sentence boundary above: a test that imports the number it is
    // checking goes green for any number.
    it("exactly 320 characters is still one message", async () => {
      const text = askOfLength(320);
      assert.equal(text.length, 320);

      const result = await askText("in_task", app(), evidence(), stubWriter(text).write);
      assert.equal(result.ok, true, `expected the boundary to pass: ${JSON.stringify(result)}`);
    });

    it("321 characters is refused, not trimmed", async () => {
      const text = askOfLength(321);
      assert.equal(text.length, 321);

      const r = refusal(await askText("in_task", app(), evidence(), stubWriter(text).write));
      assert.equal(r.cause, "too-long");
      // Trimming to fit is how the link loses its last characters and the one
      // ask this app ever gets becomes a 404.
      assert.equal((r as { text?: unknown }).text, undefined);
    });

    for (const term of FORBIDDEN_TERMS) {
      it(`refuses an ask containing "${term}"`, async () => {
        const text = `That went through the browser, ${term}. Connect it once: ${LINK} `
          + "It's optional, the browser can keep doing it.";
        const r = refusal(await askText("in_task", app(), evidence(), stubWriter(text).write));
        assert.equal(r.cause, "forbidden-word");
        assert.ok(r.refusal.includes(term), `the refusal should name the word: ${r.refusal}`);
      });
    }

    for (const stiff of STIFF_FORMS) {
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
