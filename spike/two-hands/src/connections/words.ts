// THE WORDS — the two pieces of copy a person reads before they connect an
// account, and neither of them is written in this file.
//
// A MODEL writes both: the three permission sentences the connect page shows
// (generated from the toolkit's OWN scopes, so a new app in the catalog is a
// new app in Anticipy with zero code here) and the one text message that asks.
// What this file owns is CONTAINMENT — the deterministic shape our own
// outgoing copy has to hold — and an honest refusal when the model hands back
// something we cannot send.
//
// WHY A REFUSAL AND NEVER A PATCH. Two failures, both already recorded:
//
//   * A CONNECT PAGE WITH A BLANK PERMISSION LIST. A person cannot consent to
//     nothing, so a page that renders `[]` has collected a consent that means
//     nothing — the worst outcome available on that screen, because it looks
//     like it worked. `permissionSentences` therefore never pads a short
//     reply, never truncates a long one, and never substitutes a house
//     sentence for a missing one. It refuses, and the caller decides what to
//     do about it.
//
//   * A MANGLED ASK. During the spike four raw `connect.composio.dev` links
//     were pasted into messages and every one of them was dead before it was
//     tapped (research/2026-09-05-composio-connections.md, items 3 and 4). An
//     ask is not free: it is one interruption of a product whose whole value is
//     trust under silence, and each app gets very few of them. A broken draft
//     spends that interruption for nothing, so it is dropped rather than
//     repaired into something the model did not write.
//
// LAW 1, AND WHY THE WORD LISTS BELOW ARE NOT A VIOLATION OF IT.
// HARNESS-LAWS law 1 forbids a regex or a word list DECIDING WHAT A HUMAN'S
// WORDS MEAN. Nothing in this file reads a human's words at all. The input to
// every check here is text WE are about to send, drafted by our own model, and
// the only outcome any check can produce is "do not send this draft". That is
// a style gate on our own copy — the same class of thing as a linter or a
// house style sheet — and its polarity is the safe one: it is a CEILING on our
// output whose failure mode is silence, never an action taken on somebody's
// behalf. The meaning questions in this area are real and they live elsewhere,
// with a model and four states: which toolkit did the person mean is
// `ToolkitJudge`, and is this a good moment to interrupt is `NudgePolicy`.
//
// Spec: "Connections: how Anticipy asks, learns, and never says Composio",
// 2026-09-05, pages 20-31.

import { TRIGGER_SCORE } from "./contract.ts";
import type { NudgeTrigger, PermissionWords, ToolkitMeta } from "./contract.ts";

// ---------------------------------------------------------------------------
// THE NUMBERS AND THE LISTS, IN ONE PLACE.
// ---------------------------------------------------------------------------

/** Exactly three, because the spec's connect page shows three plain sentences.
 *  Two is a permission the person was not shown; four is a page that stops
 *  being read. Neither is repaired here — see the header. */
export const SENTENCE_COUNT = 3;

/** About two lines on a phone at the connect page's body size. A permission
 *  line that wraps to four lines is not read, and an unread permission line is
 *  not consent — it is a checkbox with a paragraph behind it. */
export const MAX_SENTENCE_CHARS = 80;

/** Two GSM segments, and the last accepted length: 320 passes, 321 refuses.
 *  Past this a carrier splits the message, and the half that arrives second —
 *  or reordered, or not at all — is the half with the link in it. */
export const MAX_ASK_CHARS = 320;

/** OUR link, never the vendor's. Single use, ten minutes, bound to one owner
 *  (`ConnectLink` in the contract). The vendor's own link expires in ten
 *  minutes from the moment it is MINTED, so one pasted into a text is dead
 *  before it is tapped — measured, four out of four, 2026-09-05. */
export const CONNECT_LINK_PREFIX = "https://anticipy.ai/c/";

/** The register the spec fixes for every word Anticipy says about connecting.
 *  These are not concepts we are forbidden to express — they are the vocabulary
 *  of a consent screen written by a legal team, and the whole point of this
 *  surface is that it sounds like a person offering to help. "Connect your
 *  Notion", never "authorize the Notion integration".
 *
 *  Inflections are listed explicitly rather than stemmed, because a stemmer is
 *  a guess and this list has to be readable by the person who argues with it.
 *  Matching is whole-word (or whole-phrase) and case-insensitive, so "capital"
 *  does not trip "api" and "therapist" does not trip "api". */
export const FORBIDDEN_TERMS: readonly string[] = [
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
  // The vendor's name is the one word in this list that is not a register
  // problem but a promise: the product never says it, so a draft that does is
  // not sent. Bare `connect.composio.dev/...` links with no scheme are caught
  // here too, which is why this entry earns its place twice.
  "composio",
];

/** The voice rule is contractions, and this is the half of it that can be
 *  checked by looking. Only the NEGATION expansions are listed: each has an
 *  obvious contraction and each is what makes copy read like a terms page.
 *  Positive expansions ("it is", "you are") are deliberately absent, because
 *  they appear inside sentences where no contraction is idiomatic and refusing
 *  good copy also costs an ask. */
export const STIFF_FORMS: readonly string[] = [
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

/** Every ask is tied to a real moment; "never out of nowhere" is a rule with a
 *  leg only if an absent or invented moment refuses. The set is DERIVED from
 *  the contract's own trigger table rather than retyped, so a sixth trigger
 *  cannot silently fail to be a real moment here. */
const REAL_MOMENTS: ReadonlySet<string> = new Set(Object.keys(TRIGGER_SCORE));

// ---------------------------------------------------------------------------
// THE RESULTS. A refusal carries a CAUSE that callers may branch on and a
// SENTENCE that they may not.
// ---------------------------------------------------------------------------

export type WordsRefusalCause =
  /** Nobody answered: the writer threw, or returned null/undefined. Different
   *  from a bad answer, and kept different — a retry is reasonable for one and
   *  pointless for the other. */
  | "no-verdict"
  /** An answer arrived in a shape we cannot read (not an array, not a string,
   *  an empty line). */
  | "malformed-reply"
  /** Not exactly three sentences. Never padded, never truncated. */
  | "wrong-count"
  | "too-long"
  | "forbidden-word"
  | "stiff"
  | "exclamation"
  /** A permission sentence that is a scope URL rather than plain language. */
  | "not-plain"
  /** The same permission said more than once, which shows one permission while
   *  three are being given. */
  | "duplicate"
  /** The toolkit row itself is unusable — no slug, no name. */
  | "malformed-meta"
  /** The ask has no evidence behind it, so there is nothing to say why. */
  | "malformed-evidence"
  /** No scopes to generate from. A permission sentence not derived from a
   *  scope is a guess about what the connection gets. */
  | "no-scopes"
  /** The ask was not tied to one of the contract's real moments. */
  | "no-moment"
  /** The task's own answer has not been delivered yet. The ask comes AFTER the
   *  result, never instead of it. */
  | "result-not-delivered"
  /** The link we were handed is not our single-use link. */
  | "bad-link"
  | "no-link"
  | "extra-link"
  /** The link in the message is not the link we handed over — a token with
   *  characters welded onto it is a 404, and a 404 is a decline. */
  | "mangled-link"
  /** Nothing but the link — the why line or the it-is-optional line is gone. */
  | "nothing-before-link"
  | "nothing-after-link";

export interface Refusal {
  ok: false;
  /** An enumerated structural fact. Callers and gates MAY branch on this. */
  cause: WordsRefusalCause;
  /** Plain English for the log and for the caller's own fallback decision.
   *  NOTHING branches on these words, and they are never shown to the owner —
   *  which is why a refusal is allowed to quote the forbidden term it found. */
  refusal: string;
}

export interface SentencesOk {
  ok: true;
  /** Exactly `SENTENCE_COUNT` of them, in the model's own words. */
  sentences: string[];
}

export interface AskOk {
  ok: true;
  text: string;
}

export type SentencesResult = SentencesOk | Refusal;
export type AskResult = AskOk | Refusal;

// ---------------------------------------------------------------------------
// THE MODEL SEAM. Two writers, injected, each asked ONE question on its own.
// ---------------------------------------------------------------------------
// Separate rather than one object with two methods, so a caller can wire a
// different tier to each: the connect page's sentences are read by a person
// deciding whether to hand over their mailbox, and are worth a frontier model;
// the SMS is worth less. HARNESS-LAWS law 5, step 4, applied at the seam
// instead of argued about later.
//
// Both are typed as returning `unknown` on purpose. Types are STRIPPED at run
// time in this spike, so the declared return type of an injected function is a
// comment — every reply is checked as if it came off a wire, because it did.

/** "Given this toolkit's scopes, what are the three sentences?" */
export type SentenceWriter = (meta: ToolkitMeta) => Promise<unknown> | unknown;

/** What the ask writer is given. Everything here is a fact this system already
 *  holds; none of it is pattern-matched by anything in this file. */
export interface AskInput {
  moment: NudgeTrigger;
  meta: ToolkitMeta;
  evidence: AskEvidence;
}

export interface AskEvidence {
  /** OUR single-use link — `https://anticipy.ai/c/{token}`. */
  link: string;
  /** True once the task's own answer has already gone out. An ask that arrives
   *  INSTEAD of the result spends the trust the result was about to earn. */
  resultDelivered: boolean;
  /** What just happened, in the system's own words, for the model to draw the
   *  why-sentence from. */
  whatHappened?: string;
  /** How many of this owner's tasks would have used the connection. */
  tasksThatWouldHaveUsedIt?: number;
  /** What the browser hand cost, in ms. */
  browserMs?: number;
}

/** "Write the one text that asks." */
export type AskWriter = (input: AskInput) => Promise<unknown> | unknown;

// ---------------------------------------------------------------------------
// PLUMBING. String handling on text we wrote; no verdict below reads a human.
// ---------------------------------------------------------------------------

function refuse(cause: WordsRefusalCause, refusal: string): Refusal {
  return { ok: false, cause, refusal };
}

function isNonEmptyString(v: unknown): v is string {
  return typeof v === "string" && v.trim() !== "";
}

/** Collapse runs of whitespace and trim. Display plumbing on a string we are
 *  about to render — it changes no verdict and no wording. */
function tidy(s: string): string {
  return s.replace(/\s+/g, " ").trim();
}

/** A copy for scanning only: lowercased, curly apostrophes folded to straight
 *  ones so "doesn’t" and "doesn't" are the same string to the checks below. */
function forScan(s: string): string {
  return tidy(s).toLowerCase().replace(/[‘’ʼ]/g, "'");
}

function escapeForRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Whole-word / whole-phrase containment. The boundary is "not a letter or a
 *  digit" rather than `\b`, so "API-key" trips "api" (a hyphen is a boundary)
 *  while "capital" does not (a letter is not). */
function firstTermIn(text: string, terms: readonly string[]): string | null {
  const hay = forScan(text);
  for (const term of terms) {
    const re = new RegExp(`(?<![a-z0-9])${escapeForRegExp(term)}(?![a-z0-9])`, "i");
    if (re.test(hay)) return term;
  }
  return null;
}

const URL_LIKE = /https?:\/\/\S+/gi;

function urlCount(text: string): number {
  return (text.match(URL_LIKE) ?? []).length;
}

function countOccurrences(hay: string, needle: string): number {
  if (needle === "") return 0;
  let n = 0;
  let i = 0;
  for (;;) {
    const j = hay.indexOf(needle, i);
    if (j < 0) return n;
    n += 1;
    i = j + needle.length;
  }
}

/** Does this side of the link contain a letter — in ANY script? Used to ask
 *  "is there really a sentence here", where a stray "." is not one. `\p{L}`
 *  rather than `[a-z]` because the first ask written in a language that is not
 *  English must not be refused for being unreadable to a character class. */
function hasWords(s: string): boolean {
  return /\p{L}/u.test(s);
}

/** The toolkit row has to be usable before any of its words are. A connect page
 *  headed "Connect your undefined" is, to the person reading it, indistinguish-
 *  able from a phishing page — so it is never rendered. */
function metaProblem(meta: ToolkitMeta): Refusal | null {
  if (meta === null || typeof meta !== "object") {
    return refuse("malformed-meta", "no toolkit metadata: there is nothing to name on the page");
  }
  if (!isNonEmptyString(meta.slug) || !isNonEmptyString(meta.name)) {
    return refuse(
      "malformed-meta",
      "the toolkit row has no slug or no name, so the page cannot say which app this is",
    );
  }
  return null;
}

/** Shared by both surfaces: the house style every string we send has to hold.
 *  Returns the refusal, or null when the line is sendable. */
function styleProblem(line: string, where: string): Refusal | null {
  if (line.includes("!")) {
    return refuse(
      "exclamation",
      `${where} used an exclamation mark; this product does not raise its voice at anybody`,
    );
  }
  const forbidden = firstTermIn(line, FORBIDDEN_TERMS);
  if (forbidden !== null) {
    return refuse(
      "forbidden-word",
      `${where} used "${forbidden}", which is exactly the register the spec forbids`,
    );
  }
  return null;
}

// ---------------------------------------------------------------------------
// 1. THE PERMISSION SENTENCES.
// ---------------------------------------------------------------------------

/**
 * Three plain sentences for the connect page, generated by a model FROM THE
 * TOOLKIT'S OWN SCOPES — "read and send email as you", "see and create calendar
 * events", "read and write pages".
 *
 * One generator for every app. There is no per-app string table here and there
 * must never be one: the day a table exists, a toolkit the catalog knows about
 * renders a page with nothing on it, and the person is asked to consent to a
 * blank list. That is the same failure as an empty reply, arriving through the
 * front door.
 *
 * The writer is NOT called when there is nothing to generate from. A permission
 * sentence written without a scope is an invention about what the connection
 * gets, and an invention on a consent screen is a lie with a button under it.
 */
export async function permissionSentences(
  meta: ToolkitMeta,
  write: SentenceWriter,
): Promise<SentencesResult> {
  const bad = metaProblem(meta);
  if (bad !== null) return bad;

  const scopes = Array.isArray(meta.scopes) ? meta.scopes.filter(isNonEmptyString) : [];
  if (scopes.length === 0) {
    return refuse(
      "no-scopes",
      `${meta.name} declares no scopes, so anything we wrote about what it gets would be a guess`,
    );
  }

  let reply: unknown;
  try {
    reply = await write(meta);
  } catch (err) {
    // Nobody answered. This is a FLOOR — showing a person what they are about
    // to hand over is a privilege that needs a verdict, and the absence of one
    // is not permission to make three sentences up.
    return refuse(
      "no-verdict",
      `nothing wrote the permission sentences for ${meta.name}: ${String((err as Error)?.message ?? err)}`,
    );
  }

  if (reply === null || reply === undefined) {
    return refuse("no-verdict", `nothing wrote the permission sentences for ${meta.name}`);
  }
  if (!Array.isArray(reply)) {
    return refuse(
      "malformed-reply",
      `the permission sentences for ${meta.name} came back as ${typeof reply}, not a list of sentences`,
    );
  }
  if (reply.some((line) => typeof line !== "string")) {
    return refuse(
      "malformed-reply",
      `one of the permission sentences for ${meta.name} is not a string`,
    );
  }

  const lines = (reply as string[]).map(tidy);
  if (lines.some((line) => line === "")) {
    return refuse("malformed-reply", `one of the permission sentences for ${meta.name} is blank`);
  }

  // NOT padded to three, NOT cut down to three. Padding invents a permission;
  // cutting hides one the person is about to give. Both are worse than telling
  // the caller we have nothing to show.
  if (lines.length !== SENTENCE_COUNT) {
    return refuse(
      "wrong-count",
      `${lines.length} permission sentences for ${meta.name}, and the page shows exactly `
        + `${SENTENCE_COUNT}; padding would invent a permission and trimming would hide one`,
    );
  }

  // Three lines saying the same thing show ONE permission on a page that is
  // handing over three. The same reasoning the nudge copy already uses for
  // collapsed scope labels: a list that reads as one permission while two are
  // being given is worse than no list at all.
  const distinct = new Set(lines.map((line) => line.toLowerCase()));
  if (distinct.size !== lines.length) {
    return refuse(
      "duplicate",
      `the permission sentences for ${meta.name} repeat themselves, so the page would show `
        + "fewer permissions than the connection actually gets",
    );
  }

  for (const line of lines) {
    if (line.length > MAX_SENTENCE_CHARS) {
      return refuse(
        "too-long",
        `a permission sentence for ${meta.name} is ${line.length} characters, over the `
          + `${MAX_SENTENCE_CHARS} a person actually reads`,
      );
    }
    const style = styleProblem(line, "a permission sentence");
    if (style !== null) return style;
    if (urlCount(line) > 0) {
      // The laziest possible failure: the model echoes the scope strings back.
      // "https://mail.google.com/" is not a sentence and nobody consents to it.
      return refuse(
        "not-plain",
        `a permission sentence for ${meta.name} is a URL; the page shows plain language, `
          + "not the scope strings it was generated from",
      );
    }
  }

  return { ok: true, sentences: lines };
}

/** Thrown by the `PermissionWords` adapter below. Carries the whole refusal so
 *  a caller can branch on `err.refusal.cause` exactly as it would on a returned
 *  one. */
export class PermissionWordsRefused extends Error {
  readonly refusal: Refusal;
  constructor(refusal: Refusal) {
    super(refusal.refusal);
    this.name = "PermissionWordsRefused";
    this.refusal = refusal;
  }
}

/**
 * The contract's `PermissionWords`, implemented.
 *
 * WHY THIS THROWS. `sentences()` is declared `Promise<string[]>` and a string
 * array has no way to say "I have nothing for you". The two things that fit in
 * that type are both wrong: `[]` renders the blank permission list this whole
 * module exists to prevent, and a house-written placeholder is a claim about
 * somebody's mailbox that no model made. So the refusal is raised where a
 * caller cannot ignore it by accident, and `permissionSentences` above stays
 * available for callers that would rather have the value than the exception.
 *
 * (The contract is fixed and was not edited. This is the one place its shape
 * costs something — noted for whoever revises it.)
 */
export function makePermissionWords(write: SentenceWriter): PermissionWords {
  return {
    async sentences(meta: ToolkitMeta): Promise<string[]> {
      const result = await permissionSentences(meta, write);
      if (result.ok) return result.sentences;
      throw new PermissionWordsRefused(result);
    },
  };
}

// ---------------------------------------------------------------------------
// 2. THE ASK.
// ---------------------------------------------------------------------------

/**
 * The one text message. One sentence on why, one link, one sentence saying it
 * is optional, under two segments, in this product's voice.
 *
 * The four preconditions are checked BEFORE the writer is called, because none
 * of them can be argued out of by good copy: a beautiful ask at the wrong
 * moment is still the wrong moment, and a beautiful ask carrying a vendor link
 * is the failure of 2026-09-05 with better grammar.
 *
 * WHAT THIS FUNCTION HONESTLY CANNOT CHECK, said plainly so nobody later
 * mistakes silence for coverage: whether a sentence MEANS "this is optional".
 * That is meaning, and law 1 reserves it for the model that wrote it. What can
 * be checked is that the model left room for one — the shape is why → link →
 * optional, so a draft that ends on the link has dropped a line the spec
 * requires in every single ask, and that much is structural.
 */
export async function askText(
  moment: NudgeTrigger,
  meta: ToolkitMeta,
  evidence: AskEvidence,
  write: AskWriter,
): Promise<AskResult> {
  const bad = metaProblem(meta);
  if (bad !== null) return bad;

  if (!REAL_MOMENTS.has(moment as unknown as string)) {
    return refuse(
      "no-moment",
      `"${String(moment)}" is not one of the moments an ask may come from; every ask is tied `
        + "to something that actually happened, never out of nowhere",
    );
  }

  if (evidence === null || typeof evidence !== "object") {
    // A distinct cause from `malformed-meta`: this sends the caller to look at
    // the run that produced the ask, not at the catalog row.
    return refuse(
      "malformed-evidence",
      "no evidence for the ask, so there is nothing for it to say why about",
    );
  }

  if (evidence.resultDelivered !== true) {
    return refuse(
      "result-not-delivered",
      "the task's own answer has not gone out yet; the ask comes after the result, never "
        + "instead of it",
    );
  }

  const link = typeof evidence.link === "string" ? evidence.link.trim() : "";
  if (
    !link.startsWith(CONNECT_LINK_PREFIX)
    || link.length <= CONNECT_LINK_PREFIX.length
    || /\s/.test(link)
  ) {
    // Our link, never the vendor's. The vendor's expires ten minutes after it
    // is minted, so a text carrying one is a dead link by the time it is read —
    // four for four on 2026-09-05.
    return refuse(
      "bad-link",
      `"${link}" is not a single-use ${CONNECT_LINK_PREFIX}{token} link`,
    );
  }

  let reply: unknown;
  try {
    reply = await write({ moment, meta, evidence });
  } catch (err) {
    return refuse(
      "no-verdict",
      `nothing wrote the ask for ${meta.name}: ${String((err as Error)?.message ?? err)}`,
    );
  }

  if (reply === null || reply === undefined) {
    return refuse("no-verdict", `nothing wrote the ask for ${meta.name}`);
  }
  if (typeof reply !== "string") {
    return refuse(
      "malformed-reply",
      `the ask for ${meta.name} came back as ${typeof reply}, not a message`,
    );
  }

  // Ends trimmed only. Interior line breaks are the model's formatting and are
  // left alone; collapsing them would be this module rewriting copy, which is
  // the thing it does not do.
  const text = reply.trim();
  if (text === "") {
    return refuse("malformed-reply", `the ask for ${meta.name} is empty`);
  }

  if (text.length > MAX_ASK_CHARS) {
    return refuse(
      "too-long",
      `the ask is ${text.length} characters, over the ${MAX_ASK_CHARS} that stay in one `
        + "message; past that a carrier splits it and the half with the link can arrive second",
    );
  }

  // The vocabulary checks run over the WORDS, with the link lifted out. A
  // token is machine-issued and nobody reads it: `.../c/x-api-7` is not the ask
  // saying "API", and refusing that ask would drop a perfectly good message
  // because of nine random characters.
  const words = text.split(link).join(" ");

  const style = styleProblem(words, "the ask");
  if (style !== null) return style;

  const stiff = firstTermIn(words, STIFF_FORMS);
  if (stiff !== null) {
    return refuse(
      "stiff",
      `the ask wrote "${stiff}" where this product would contract it; the voice is a person `
        + "offering to help, not a consent form",
    );
  }

  const links = countOccurrences(text, link);
  if (links === 0) {
    return refuse("no-link", "the ask does not carry the connect link, so there is nothing to tap");
  }
  if (links > 1) {
    return refuse("extra-link", "the ask carries the connect link more than once");
  }
  const urls = text.match(URL_LIKE) ?? [];
  if (urls.length !== 1) {
    // A second URL in a connect text is, in every recorded case, the vendor's
    // own link riding along beside ours — which is both the wrong link and a
    // dead one.
    return refuse(
      "extra-link",
      "the ask carries a second link; the only URL in a connect text is ours",
    );
  }

  // The one URL has to BE our link, not merely contain it. `…/c/{token}-x.com`
  // contains the token, passes every count above, and resolves to nothing: the
  // owner taps, gets a 404, and reads it as "this is broken". Sentence-ending
  // punctuation is stripped before the comparison because the model is writing
  // prose and a full stop belongs to the sentence, not the URL.
  const only = urls[0].replace(/[).,;:'"”’»]+$/, "");
  if (only !== link) {
    return refuse(
      "mangled-link",
      `the message carries "${only}", not the single-use link it was given`,
    );
  }

  const at = text.indexOf(link);
  if (!hasWords(text.slice(0, at))) {
    return refuse(
      "nothing-before-link",
      "the ask opens on the link with no sentence saying why it is being sent",
    );
  }
  if (!hasWords(text.slice(at + link.length))) {
    return refuse(
      "nothing-after-link",
      "the ask ends on the link, so the line telling them this is optional is missing",
    );
  }

  return { ok: true, text };
}
