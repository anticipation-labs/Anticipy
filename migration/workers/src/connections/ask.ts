/**
 * src/connections/ask.ts — THE SENTENCE. The model that actually writes the one
 * text message asking somebody to connect one of their own apps.
 *
 * WHY THIS FILE EXISTS, MEASURED. `AskWriter` (src/connections/words.ts:375) is
 * a TYPE. On 2026-09-06 nothing in this repository implemented it: the policy
 * could decide an ask was licensed, the link could be minted, the judge could
 * audit a draft, and there was no draft, because there was no writer. Every
 * other surface in the Connections spec — the consent page, the webhook, the
 * settings screen, the six live routes — is downstream of a text that was never
 * written. This is that text.
 *
 * THE THREE INPUTS, AND NO OTHERS. The spec (page 22, "The conversation") is
 * exact about them: "The policy engine decides if and when. The LLM writes the
 * words, from three inputs: the moment, the app's catalog entry, and the user's
 * own phrasing history." So:
 *
 *   the moment            `AskInput.moment`, a closed enum of things that
 *                         HAPPENED, plus whatever `evidence.whatHappened` the
 *                         caller established about it.
 *   the catalog entry     `AskInput.meta`, read from the vendor catalog at run
 *                         time. NO APP IS NAMED IN THIS FILE.
 *   the phrasing history  the owner's own words about their apps. See
 *                         `phrasingOf` — the seam does not carry it yet and
 *                         this file says so rather than pretending.
 *
 * HARNESS-LAWS LAW 1, and this file is the one that would be easiest to break
 * it in:
 *
 *   - NOTHING HERE DECIDES WHAT A HUMAN'S WORDS MEAN. There is no keyword table
 *     from a phrase to a toolkit; the toolkit arrives as a slug somebody else's
 *     model already resolved, and this file never compares it to a literal.
 *   - `MOMENT_SENTENCE` maps one CLOSED ENUM (`NudgeTrigger` — a step ran in a
 *     browser, a lid is shut) onto the system's own description of that event.
 *     Enum to prose, in that direction only. It never reads prose and it never
 *     produces a decision. A sixth trigger is a compile error, not a hole.
 *   - The retry loop reads OUR OWN DRAFT and the only outcome it can produce is
 *     "ask the model again, naming what broke". That is a ceiling on our own
 *     copy whose failure mode is silence, which is the argument words.ts makes
 *     at length in its own header.
 *   - THE JUDGE IS NOT RE-IMPLEMENTED HERE. `judgeDraft` calls
 *     `askMessage` from src/connections/nudge.ts — the same function
 *     `sendConnectAsk` will use — so there is exactly one set of rules about
 *     what may be sent, and this file cannot pass itself. A rule added to that
 *     judge tightens this writer in the same commit, with no edit here.
 *
 * A MODEL THAT WILL NOT WRITE IT SENDS NOTHING. Every failure below throws or
 * hands the bad draft on; nothing in this file substitutes a house sentence, a
 * template, or a repaired version of what the model said. `askMessage` turns a
 * throw into `no-verdict` and `sendConnectAsk` turns that into `refused-copy`,
 * which costs one unredeemable link and no interruption. A template would cost
 * the one interruption this product gets per owner per week, spent on words
 * nobody wrote.
 *
 * THE VOCABULARY IS words.ts's, IMPORTED. `FORBIDDEN_TERMS` and `STIFF_FORMS`
 * are read out of that module and pasted into the prompt, never re-typed: a
 * second copy of the forbidden list is a list that stops matching the judge,
 * and the day it does the writer starts producing drafts that are refused for
 * a rule it was never told about.
 *
 * Spec: "Connections: how Anticipy asks, learns, and never says Composio",
 * pages 22-23 (the register, the eight examples, the voice rules) and page 24
 * (the cadence, which is nudge.ts's and is not touched here).
 */

/// <reference types="@cloudflare/workers-types" />

import type {
  NudgeTrigger,
  ToolkitMeta,
} from "../../../../spike/two-hands/src/connections/contract.ts";
import {
  FORBIDDEN_TERMS,
  MAX_ASK_CHARS_GSM7,
  MAX_ASK_SEGMENTS,
  STIFF_FORMS,
  forbiddenTermIn,
} from "./words.ts";
import type {
  AskInput,
  AskWriter,
  Refusal,
  WordsRefusalCause,
} from "./words.ts";
import { ASK_MESSAGE_MAX_CHARS, askMessage } from "./nudge.ts";
import { TOKEN_CHARS } from "../routes/connect.ts";
import {
  GOOGLE_BASE,
  MAX_REQUEST_CHARS,
  OPENROUTER_BASE,
  UPSTREAM_TIMEOUT_MS,
  boundMaxTokens,
  geminiGenerationConfig,
  providerBase,
  providerKeys,
  toGeminiContents,
  translateGemini,
  type ChatMessage,
  type LlmEnv,
} from "../llm.ts";

// ---------------------------------------------------------------------------
// THE MODEL
// ---------------------------------------------------------------------------

/**
 * The default model for the ask, and it is deliberately the SAME literal as
 * `DEFAULT_CONNECT_MODEL` in src/connections/wiring.ts, for the same measured
 * reason written there: OPENROUTER_API_KEY is the key this Worker actually
 * holds, and a default that needs a secret nobody set is a feature that does
 * not exist.
 *
 * IT IS DECLARED HERE RATHER THAN IMPORTED, and that is a real trade with a
 * real guard. Importing it would make this module depend on wiring.ts, which
 * depends on this module to build the writer — a cycle through the file the
 * Worker's bundler evaluates first. So the literal is repeated once, and
 * test/connections-ask.test.ts reads BOTH source files and goes red the day
 * they disagree. Two constants that must agree and a test that says so beats a
 * cycle that works until a bundler reorders it.
 */
export const DEFAULT_ASK_MODEL = "anthropic/claude-sonnet-4.6";

/** The same env var the connect page's sentences read, on purpose: one text
 *  surface, one model to point somewhere else, one secret to set. */
export interface AskEnv extends LlmEnv {
  ANTICIPY_CONNECT_MODEL?: string;
}

export function askModel(env: AskEnv): string {
  const named = typeof env?.ANTICIPY_CONNECT_MODEL === "string"
    ? env.ANTICIPY_CONNECT_MODEL.trim() : "";
  return named || DEFAULT_ASK_MODEL;
}

/**
 * How many tokens one ask may spend.
 *
 * The message itself is at most two SMS segments, which is well under a
 * hundred tokens — the floor exists because src/llm.ts `REPLY_FLOOR` is 512 for
 * a measured reason (a thinking model's reasoning counts against the cap and
 * its verdicts came back cut off mid-word at 64), and `boundMaxTokens` raises
 * anything smaller anyway. Stated rather than left implicit so a future reader
 * does not "optimise" it to 64 and get an empty string back.
 */
export const ASK_MAX_TOKENS = 512;

/**
 * How many times the writer will ask, counting the first.
 *
 * TWO, and the number is a budget rather than a taste. The connect page's
 * writer is allowed four because a person is standing in front of that page and
 * an app nobody can connect costs infinitely more than a retry. NOBODY IS
 * WAITING ON THIS ONE: it runs from a five-minute cron sweep that may send up
 * to `MAX_ASKS_PER_SWEEP` asks in one invocation, each model call is a
 * subrequest with a 95-second ceiling, and the leg beside it in the same
 * invocation carries reminders somebody IS waiting for (src/cron.ts, item 3).
 * A draft that is still wrong on the second attempt is refused, which costs one
 * dead link and no interruption, and the next real moment is five minutes away.
 *
 * ONE RETRY IS WORTH HAVING RATHER THAN ZERO for the reason wiring.ts measured
 * on 2026-09-06: a prompt that states a limit and a model that misses it is the
 * normal case, and asking again while SHOWING it the line it wrote and the rule
 * it broke is a different question from asking again identically.
 */
export const ASK_ATTEMPTS = 2;

// ---------------------------------------------------------------------------
// THE MOMENT, IN THE SYSTEM'S OWN WORDS
// ---------------------------------------------------------------------------

/**
 * What each moment IS, for the model to draw the why-sentence from.
 *
 * Typed `Record<NudgeTrigger, string>` against the contract's own union, so a
 * sixth trigger added there is a COMPILE error here rather than an ask that
 * opens on nothing. Every sentence describes an EVENT this system observed —
 * "never out of nowhere" is the spec's first rule about the ask, and a writer
 * given no moment has nothing to be honest about.
 *
 * These are inputs to a model, not templates. Nothing here is ever sent: the
 * model writes the message, and words.ts judges what it wrote.
 */
export const MOMENT_SENTENCE: Record<NudgeTrigger, string> = {
  laptop_closed:
    "their laptop is shut, so a job that needs this app is queued and waiting for it to wake",
  user_named_it:
    "they named this app themselves, in their own words, while asking for something",
  in_task:
    "a job of theirs just ran through this app in their browser instead of going straight there",
  onboarding:
    "they are finishing setting Anticipy up and this is the last step",
  repeated_use:
    "their jobs have gone through this app in the browser several times lately",
};

// ---------------------------------------------------------------------------
// THE THIRD INPUT
// ---------------------------------------------------------------------------

/**
 * The spec's third input: "the user's own phrasing history".
 *
 * WHAT IT IS FOR. The register is supposed to sound like the person it is
 * written to, and the eight examples on pages 22-23 are eight different voices
 * on purpose. Lines the owner actually said about their own apps are the only
 * honest source for that.
 *
 * THE SEAM DOES NOT CARRY IT TODAY, and this file will not pretend otherwise.
 * `AskWriter` is handed an `AskInput` — `{moment, meta, evidence}` — and
 * `sendConnectAsk` builds that `evidence` from five named fields, none of which
 * is the owner's words. Worse, `AskInput` carries no owner at all, so this
 * function CANNOT go and fetch them: the only code that knows whose ask this is
 * is `NudgeDeps.moment`, one call earlier and in another module.
 *
 * The alternative considered and REFUSED: caching "the owner we were last asked
 * about" on the deps and reading it here. Today's sweep awaits each
 * `sendConnectAsk` in turn so it would even work — until the day somebody
 * parallelises that loop, and then one person's words are used to write
 * another person's text. Binding one owner's data to another owner's message is
 * the single worst failure this product has, and it has happened once already.
 *
 * So this reads the field wherever it lands and supplies nothing when it is
 * absent. The one-line change that makes it real is named in
 * test/connections-ask.test.ts, in a check that goes RED the day words.ts
 * declares the field — so the wiring is not forgotten.
 */
/** Enough for a voice, short enough that a long day of transcripts cannot
 *  push the prompt over `MAX_REQUEST_CHARS`. */
export const MAX_PHRASING_LINES = 8;

export function phrasingOf(input: AskInput | null | undefined): string[] {
  const fromInput = (input as { phrasing?: unknown } | null | undefined)?.phrasing;
  const fromEvidence = (input?.evidence as { phrasing?: unknown } | undefined)?.phrasing;
  const raw = Array.isArray(fromInput) ? fromInput
    : Array.isArray(fromEvidence) ? fromEvidence
    : [];
  const out: string[] = [];
  for (const line of raw) {
    if (typeof line !== "string") continue;
    const tidied = line.replace(/\s+/g, " ").trim();
    if (tidied === "") continue;
    out.push(tidied);
    // A CEILING ON SOMEBODY ELSE'S DATA. These are transcript lines and their
    // length is not ours to assume; `callAskModel` refuses a prompt over
    // MAX_REQUEST_CHARS, and being refused by our own guard because a
    // transcript ran long is a good ask lost to plumbing.
    if (out.length >= MAX_PHRASING_LINES) break;
  }
  return out;
}

// ---------------------------------------------------------------------------
// THE PROMPT — ONE QUESTION, ASKED ON ITS OWN
// ---------------------------------------------------------------------------

/**
 * The ceiling stated to the model, in characters.
 *
 * COMPUTED, never typed. `MAX_ASK_CHARS_GSM7` is what two segments actually
 * hold (153 septets each) and `ASK_MESSAGE_MAX_CHARS` is the spec's own number;
 * the judge enforces both, so the number the model is told is the smaller. If
 * either constant moves, this moves with it and the prompt cannot rot into a
 * limit nothing enforces.
 */
export const ASK_CEILING_CHARS = Math.min(MAX_ASK_CHARS_GSM7, ASK_MESSAGE_MAX_CHARS - 1);

/**
 * ONE QUESTION, ASKED ON ITS OWN — HARNESS-LAWS law 1's worked shape. Not a
 * ninth key in some other reply, because a field among many loses (measured:
 * seven cases, zero moved).
 *
 * NO APP IS NAMED. Every concrete word about the app comes from the catalog row
 * that was passed in; the prompt itself would read identically for an app that
 * is invented tomorrow, which is what the test proves by running it on two
 * slugs that exist in no catalog.
 *
 * THE VENDOR'S DESCRIPTION IS DROPPED WHEN IT CARRIES A FORBIDDEN TERM, using
 * words.ts's own `forbiddenTermIn` and the measurement beside it: on 2026-09-06
 * four of eight live catalog descriptions carried "integration". Feeding one to
 * the model is asking it to echo the exact word the whole surface exists to
 * avoid, and then refusing the answer for doing so.
 */
export function askPrompt(input: AskInput, phrasing: readonly string[] = []): ChatMessage[] {
  const meta = (input?.meta ?? {}) as ToolkitMeta;
  const evidence = (input?.evidence ?? {}) as AskInput["evidence"];
  const link = typeof evidence?.link === "string" ? evidence.link.trim() : "";
  const moment = input?.moment as NudgeTrigger;
  const happened = Object.hasOwn(MOMENT_SENTENCE, moment as unknown as string)
    ? MOMENT_SENTENCE[moment] : "";

  const system = [
    "You write the ONE text message Anticipy sends when it offers to connect one of",
    "somebody's own apps. Anticipy is an assistant that quietly does small jobs for",
    "them. It can already do this job through their browser; connecting only makes it",
    "instant and makes it work while their laptop is shut.",
    "",
    "Answer with JSON only, in this exact shape:",
    '{"message": "..."}',
    "",
    "The message is three parts, in this order, and nothing else:",
    "  1. One sentence on what just happened and why connecting would help.",
    "  2. The link, copied character for character exactly as you are given it.",
    "  3. One short sentence saying it is optional.",
    "",
    "How it has to read:",
    `- At most ${ASK_CEILING_CHARS} characters in total, the link included. It has to`,
    "  arrive as one text.",
    "- Plain ASCII only: straight quotes, a plain hyphen, no dashes, no emoji, no",
    "  accents. One curly apostrophe more than halves how much fits in a text.",
    "- Contractions everywhere: you'll, it's, I'll, doesn't, won't, that's.",
    `  Never write any of these out in full: ${STIFF_FORMS.join(", ")}.`,
    "- No exclamation marks. This product does not raise its voice at anybody.",
    `- Never use any of these words: ${FORBIDDEN_TERMS.join(", ")}. Say what Anticipy`,
    "  can DO instead. It is \"connect your\" something, never the language of a",
    "  consent form.",
    "- Exactly one link, the one you are given, and no other web address of any kind",
    "  — not even a bare host with a path. Put a space or a full stop after it.",
    "- Say nothing about the app that the moment below did not show you.",
    "- Never say the word Anticipy twice, and never sign it.",
  ].join("\n");

  const description = typeof meta.description === "string" && meta.description.trim() !== ""
    && forbiddenTermIn(meta.description) === null
    ? meta.description.trim() : null;

  const user = [
    "THE MOMENT",
    happened ? `- What happened: ${happened}` : null,
    typeof evidence?.whatHappened === "string" && evidence.whatHappened.trim() !== ""
      ? `- In the system's own words: ${evidence.whatHappened.trim()}` : null,
    typeof evidence?.browserMs === "number" && Number.isFinite(evidence.browserMs)
      ? `- The browser took about ${Math.round(evidence.browserMs / 1000)} seconds` : null,
    typeof evidence?.tasksThatWouldHaveUsedIt === "number"
      && Number.isFinite(evidence.tasksThatWouldHaveUsedIt)
      ? `- Jobs of theirs that would have used it: ${evidence.tasksThatWouldHaveUsedIt}` : null,
    "",
    "THE APP, from our catalog",
    `- Name, use exactly this spelling: ${String(meta.name ?? "")}`,
    `- Id: ${String(meta.slug ?? "")}`,
    description ? `- What it is: ${description}` : null,
    "",
    "THE LINK, copy it exactly",
    link,
    ...(phrasing.length > 0
      ? [
        "",
        "HOW THEY TALK, in their own words. Match this voice; do not quote it.",
        ...phrasing.map((line) => `- ${line}`),
      ]
      : []),
  ].filter((line): line is string => line !== null).join("\n");

  return [{ role: "system", content: system }, { role: "user", content: user }];
}

// ---------------------------------------------------------------------------
// READING WHAT CAME BACK
// ---------------------------------------------------------------------------

/** The model's text, or null when it produced none. Same reader as
 *  src/connections/wiring.ts, over the same chat-completions shape. */
function replyText(clientJson: unknown): string | null {
  const j = (clientJson ?? {}) as Record<string, unknown>;
  const choices = Array.isArray(j.choices) ? j.choices : [];
  const first = choices[0] as { message?: { content?: unknown } } | undefined;
  const text = first?.message?.content;
  return typeof text === "string" && text.trim() !== "" ? text : null;
}

/**
 * What the model said, turned into something the judge can audit — and NOTHING
 * else. It never repairs, pads, trims or rewrites: a reply this cannot read is
 * handed back as the raw string, which words.ts classifies as `malformed-reply`
 * and a person can act on, rather than as a message somebody's code made up.
 *
 * Three wrappers are accepted — `{"message": "..."}`, `{"text": "..."}` and a
 * bare JSON string — because which one a model picks is a coin toss and
 * refusing the others would be refusing a good answer over its packaging.
 * Fenced code blocks are unwrapped for the same reason: the fence is transport.
 */
export function parseAsk(text: string): unknown {
  const fenced = /^\s*```(?:json)?\s*([\s\S]*?)\s*```\s*$/i.exec(text);
  const body = fenced ? (fenced[1] as string) : text;
  let parsed: unknown;
  try {
    parsed = JSON.parse(body);
  } catch {
    return text;
  }
  if (typeof parsed === "string") return parsed;
  if (parsed !== null && typeof parsed === "object") {
    const message = (parsed as { message?: unknown }).message;
    if (typeof message === "string") return message;
    const alt = (parsed as { text?: unknown }).text;
    if (typeof alt === "string") return alt;
  }
  return text;
}

// ---------------------------------------------------------------------------
// THE SELF-CHECK — the real judge, not a second one
// ---------------------------------------------------------------------------

/**
 * The base the link was minted on, recovered from the link itself.
 *
 * ONLY EVER USED FOR THE WRITER'S OWN RETRY. `sendConnectAsk` judges the final
 * draft against the base the mint ACTUALLY used, which is the check that
 * matters; deriving it here would make that check tautological and is the one
 * thing this must not be used for. What the retry needs is every OTHER rule —
 * the count, the vocabulary, the length, the sentence on each side of the link
 * — and those do not depend on the base at all.
 */
function baseOfLink(link: string): string {
  return link.length > TOKEN_CHARS ? link.slice(0, link.length - (TOKEN_CHARS + 1)) : link;
}

/**
 * The causes a SECOND ATTEMPT could plausibly fix, because the model owns them.
 *
 * The others — a link that is not ours, a catalog row with no name, a moment
 * that is not a moment, a result that has not gone out — belong to the caller,
 * and asking the model again about any of them spends a subrequest to be told
 * the same thing. `no-verdict` is on neither list: it means nothing answered,
 * and this loop only runs once something did.
 */
export const MODEL_FIXABLE: readonly WordsRefusalCause[] = Object.freeze([
  "malformed-reply",
  "too-long",
  "forbidden-word",
  "stiff",
  "exclamation",
  "no-link",
  "extra-link",
  "mangled-link",
  "nothing-before-link",
  "nothing-after-link",
]);

/**
 * Run OUR OWN DRAFT past the shipped judge, and hand back its refusal.
 *
 * THIS IS THE POINT OF THE FILE'S LAW-1 ARGUMENT. There is no second set of
 * rules here: `askMessage` is the exact function `sendConnectAsk` will use on
 * the final draft, driven with a writer that returns the draft we already have.
 * A rule added to that judge tightens this writer with no edit here, and this
 * writer can never be tuned to pass a judge it does not share.
 */
export async function judgeDraft(draft: unknown, input: AskInput): Promise<Refusal | null> {
  const link = typeof input?.evidence?.link === "string" ? input.evidence.link.trim() : "";
  const verdict = await askMessage(
    input?.moment as NudgeTrigger,
    input?.meta as ToolkitMeta,
    input?.evidence as AskInput["evidence"],
    () => draft,
    { base: baseOfLink(link) },
  );
  return verdict.ok ? null : verdict;
}

/**
 * The second question: the draft it wrote, and the rule it broke.
 *
 * The judge's `refusal` sentence is written for a log and names the offence in
 * plain English — "the ask used \"permission\", which is exactly the register
 * the spec forbids". That sentence is the whole complaint; restating it here in
 * other words would be this file inventing a second explanation of somebody
 * else's rule.
 */
export function complaintText(refusal: Refusal): string {
  return [
    `That message can't go out: ${refusal.refusal}`,
    "",
    "Write the whole message again. Same three parts, same voice, same link copied",
    "exactly. Fix only what is named above; do not pad it and do not explain yourself.",
    'JSON only: {"message": "..."}',
  ].join("\n");
}

// ---------------------------------------------------------------------------
// THE CALL
// ---------------------------------------------------------------------------

/**
 * One model call, over the Worker's own LLM path.
 *
 * IT REUSES src/llm.ts RATHER THAN COPYING IT, exactly as wiring.ts does and
 * for the reasons written there: the provider split (rule 8 — a `google/` model
 * goes to Google directly, everything else to OpenRouter, never "whichever key
 * exists"), the reply cap, the loopback-only base override and the request-size
 * ceiling are that file's exported decisions. A second provider client in this
 * repo would be a second set of those decisions, and they would diverge.
 *
 * IT THROWS ON EVERY FAILURE. The polarity is the ask's: sending somebody an
 * interruption is a privilege that needs a verdict, and the absence of one is
 * not permission to send a sentence this file made up. `askMessage` turns the
 * throw into `no-verdict`, `sendConnectAsk` turns that into `refused-copy`, and
 * nobody is texted.
 */
async function callAskModel(env: AskEnv, messages: ChatMessage[]): Promise<string> {
  const model = askModel(env);
  const keys = providerKeys(env);
  const bounded = boundMaxTokens(ASK_MAX_TOKENS);
  // src/llm.ts rule 8, applied identically.
  const geminiModel = model.startsWith("google/") ? model.slice("google/".length) : "";

  let url: string;
  let headers: Record<string, string>;
  let serialized: string;
  if (geminiModel) {
    if (!keys.gemini) throw new Error("no GEMINI_API_KEY for the connect ask");
    const { systemText, contents } = toGeminiContents(messages);
    if (!contents.length) throw new Error("the ask prompt has no usable content");
    const payload: Record<string, unknown> = {
      contents,
      generationConfig: geminiGenerationConfig(geminiModel, bounded, true),
    };
    if (systemText) payload.systemInstruction = { parts: [{ text: systemText }] };
    url = providerBase(env, GOOGLE_BASE) + "/v1beta/models/"
      + encodeURIComponent(geminiModel) + ":generateContent";
    headers = { "x-goog-api-key": keys.gemini };
    serialized = JSON.stringify(payload);
  } else {
    if (!keys.openrouter) throw new Error("no OPENROUTER_API_KEY for the connect ask");
    url = providerBase(env, OPENROUTER_BASE) + "/api/v1/chat/completions";
    headers = {
      "Authorization": "Bearer " + keys.openrouter,
      "HTTP-Referer": "https://anticipy.ai",
      "X-Title": "Anticipy",
    };
    serialized = JSON.stringify({
      model, messages, temperature: 0, max_tokens: bounded,
      response_format: { type: "json_object" },
    });
  }

  // A catalog row and a transcript line are somebody else's data and their
  // length is not ours to assume. Refusing here beats being refused by the
  // provider with a 400 the log reads as "the model is down".
  if (serialized.length > MAX_REQUEST_CHARS) {
    throw new Error("the ask prompt is larger than the model will take");
  }

  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: serialized,
    signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
  });
  let json: unknown = null;
  try { json = await res.json(); } catch { json = null; }
  if (!json) throw new Error(`the model returned no JSON (${res.status})`);
  if (res.status < 200 || res.status >= 300) {
    // The provider's own error text is theirs and may name a vendor. The status
    // is the whole of what this log line is allowed to carry.
    throw new Error(`the model provider refused the request (${res.status})`);
  }

  const text = replyText(geminiModel ? translateGemini(json, geminiModel) : json);
  if (text === null) throw new Error("the model returned no text");
  return text;
}

// ---------------------------------------------------------------------------
// THE WRITER
// ---------------------------------------------------------------------------

/**
 * The `AskWriter` src/connections/words.ts declares and nothing implemented.
 *
 * Exported so the suite can drive the REAL one against a stubbed provider
 * rather than a stub of its own — the same discipline as `makeSentenceWriter`,
 * and the reason the retry in that file was found to have never fired once.
 *
 * WHAT IT RETURNS. Whatever the last attempt said, unrepaired, for the judge to
 * refuse or pass. The loop exists to give the model its failure, not to give up
 * on the rule, and not to hand back something the model did not write.
 */
export function makeAskWriter(env: AskEnv): AskWriter {
  return async (input: AskInput): Promise<unknown> => {
    const messages = askPrompt(input, phrasingOf(input));
    let draft = parseAsk(await callAskModel(env, messages));

    for (let attempt = 1; attempt < ASK_ATTEMPTS; attempt++) {
      const refusal = await judgeDraft(draft, input);
      if (refusal === null) return draft;
      if (!MODEL_FIXABLE.includes(refusal.cause)) {
        // The caller's fault, not the model's. Asking again spends a
        // subrequest to be told the same thing, and the judge will say it
        // again for real in a moment.
        return draft;
      }
      messages.push({ role: "assistant", content: JSON.stringify({ message: draft }) });
      messages.push({ role: "user", content: complaintText(refusal) });
      draft = parseAsk(await callAskModel(env, messages));
    }
    return draft;
  };
}

/** For a gate leg and for a caller that wants the two segment ceilings in one
 *  place: what the writer was told, and what the judge will enforce. */
export const ASK_LIMITS = Object.freeze({
  ceilingChars: ASK_CEILING_CHARS,
  segments: MAX_ASK_SEGMENTS,
  attempts: ASK_ATTEMPTS,
});
