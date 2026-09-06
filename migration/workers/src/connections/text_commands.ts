/**
 * text_commands.ts — THE TEXT TWIN. What somebody typed, turned into a plan,
 * and nothing else.
 *
 * The spec's rule for this whole area is one line: "Everything here has a text
 * twin" (Connections spec, page 27 of 31 / PDF page 47). The surface table on
 * page 21 names the four sentences it means — "connect notion", "what's
 * connected", "disconnect slack", "use my work Gmail for this" — and states,
 * in the column headed WHAT HAPPENS UNDERNEATH, the rule that governs this
 * file: "LLM maps the phrase to a catalog toolkit; no keyword list."
 *
 * WHAT THIS MODULE IS. A decision, not an action. It takes ONE inbound message
 * and the owner it came from, asks a model two questions about it, and returns
 * a PLAN describing what should happen. It reads no table, calls no vendor,
 * sends no text and writes nothing. The caller — the SMS route, which this file
 * deliberately does not know about — carries the plan out.
 *
 * That split is not tidiness. The route owns transport, signature checking and
 * the reply; this owns understanding. Written together they would be one
 * function nobody can test without a phone, and the understanding half is the
 * half that can disconnect the wrong person's mailbox.
 *
 * AND A PLAN IS WHAT THEY ASKED FOR, NOT WHAT IS POSSIBLE. A `disconnect` plan
 * for an app that was never connected, and a `connect` plan for one that
 * already is, are both correct outputs of this module: it reads no table and
 * cannot know. The caller reads `connections` and answers accordingly — and it
 * must, because "Done, disconnected" said over nothing is the same lie as
 * "revoked" said over a live token.
 *
 * ── HARNESS-LAWS LAW 1, WHICH IS THE WHOLE POINT OF THE FILE ─────────────
 *
 * TWO meaning questions have to be answered before a sentence becomes an
 * action, and both belong to a model:
 *
 *   1. WHICH OF OUR OPERATIONS is this, if any?
 *   2. WHICH APP is it about?
 *
 * Both are asked of the injected judge. They are asked SEPARATELY, one
 * question each, because a question that arrives as one more key in somebody
 * else's JSON reply loses (measured: seven cases, zero moved). Each comes back
 * in FOUR states, because "they were not talking to us", "they were and I
 * could not pin it down" and "nobody answered" are three different facts and a
 * bool holds two of them. The caller below compares the verdict and never
 * re-reads the sentence.
 *
 * The owner's words reach exactly TWO expressions in this file, both of them
 * the argument of a judge call, plus one `typeof` that reads their JavaScript
 * type and not their content. There is no regex here, no word list, no
 * substring test, no length test and no app name. `test/connections-text-
 * commands.test.ts` reads this source back and goes red if any of those
 * appears.
 *
 * NO LENGTH GATE, SAID OUT LOUD BECAUSE IT LOOKS FREE. An empty or two-word
 * message is asked about exactly like any other. Skipping the judge on a short
 * message would be `shard_too_thin()` again — a word count deciding a line is
 * too thin to mean anything — and that guard is registered TAPE in
 * HARNESS-LAWS for exactly this reason. The cost is real and is stated below.
 *
 * ── THE POLARITY, PER OPERATION ──────────────────────────────────────────
 *
 * Two different checks live here and they point opposite ways. Getting that
 * backwards is how a fence becomes a wall.
 *
 *   CLAIMING THE MESSAGE is a FLOOR on us. This module is one listener among
 *   several on an inbound text thread whose ordinary traffic is conversation.
 *   Treating a message as a connections command is an action — it takes the
 *   message away from everything else that would have answered it. So a
 *   `none`, an `unclear`, a judge that threw and a reply in a shape we did not
 *   define ALL fall through untouched. A module that grabs every message
 *   because its judge is down is worse than one nobody wired.
 *
 *   ACTING ON AN APP is a FLOOR too, and a harder one. Connecting an account
 *   and disconnecting one are privileges over somebody's real mailbox. So
 *   `connect`, `disconnect` and the account choice require an UNAMBIGUOUS yes
 *   on BOTH questions: a pinned operation AND a slug that is in this owner's
 *   own catalog. Anything else returns `ask_which_app`, which asks the person.
 *   Nothing here acts on a missing answer.
 *
 *   "WHAT'S CONNECTED" IS A READ, and it is the one operation that names no
 *   app at all. It is answered on an unclear toolkit because there is no
 *   toolkit to get wrong — and the second question is never even asked, which
 *   is also why a broken catalog cannot stop somebody seeing their own list.
 *
 * ── WHY THE CATALOG ARRIVES PER OWNER ────────────────────────────────────
 *
 * `TextCommandDeps.catalog` takes the owner. The slug that travels out in a
 * plan is always one this owner's own list contained, compared by identity
 * against that list — never the model's string, and never a slug from a list
 * fetched for somebody else. A judge that answers with a plausible app we
 * never handed it (its own memory of a vendor's names, or a cached reply from
 * the previous message on a shared Worker) resolves to nothing and asks.
 * `off-catalog` is the reason code, and it is kept distinct from `unclear` so
 * that a cross-owner leak shows up in a log as itself rather than as vagueness.
 *
 * ── WHAT THIS FILE LETS OUT OF THE CATALOG, AND WHY ONLY THAT ────────────
 *
 * The plan carries the slug (a machine identifier) and `appName` (the one
 * string from a vendor feed that reaches a person's phone). NO APP IS
 * HARDCODED here — there is not a name, a slug or a synonym in this file — so
 * every name a reply says is written by that feed, under our number, in a text
 * we signed. `appName` therefore contains it: one short line, no control
 * characters, and neither of the two characters that turn a string into an
 * address. A row named "Zeta — finish at <a vendor's connect link>" would
 * otherwise put that link into our own sentence, which is the defect the spike
 * recorded from the other direction. A refused name falls back to the slug,
 * then to a generic; it never throws, because one malformed row must not take
 * the surface down for every other app.
 *
 * The containment is a CHARACTER WALK rather than a regex or a substring test.
 * That is not superstition: this file's own law-1 legs refuse both outright and
 * cannot tell a check on a vendor's URL from a check on a human's sentence, and
 * that bluntness is worth more than the convenience.
 *
 * ── WHAT IT COSTS ────────────────────────────────────────────────────────
 *
 * One model call per inbound message, and a second only when the pinned
 * operation needs an app. `list_connected` never spends the second, and
 * neither does a message the first call disowns — which is most of them.
 *
 * ── WHAT IS DELIBERATELY NOT HERE ────────────────────────────────────────
 *
 *   THE WRITE OPT-IN. "let Anticipy edit notion" is on the spec's text-twin
 *   list and is NOT in this menu. It is the Two Hands ladder's rung-3 consent
 *   and it is owned beside the ladder, not here.
 *
 *   THE ALIAS ON A NEW CONNECTION. "connect my work Gmail" has no member here.
 *   The spec puts the alias on the connect page (`alias=chosen_alias`, page
 *   26), so a new connection chooses its account there; this menu's account
 *   members move an EXISTING choice. A message that asks for both is not
 *   pinned by question 1 and falls through, which is the honest outcome.
 *
 *   THE SCOPE OF "FOR THIS". The spec stores an account answer "against the
 *   context that caused it" (page 22). Which context is open is a fact the
 *   caller holds and this module cannot see, so the plan names the app and the
 *   account and the caller binds it.
 *
 * Spec: "Connections: how Anticipy asks, learns, and never says the vendor's
 * name", 2026-09-05, docs/spec-connections.txt pages 41-47.
 */

// TYPES ONLY. `import type` is erased before this file is bundled or run, so
// the deployed Worker carries no runtime edge into the spike tree — but the
// shapes are the contract's OWN declarations rather than a second copy. Same
// treatment store.ts, provider.ts and words.ts give theirs.
import type {
  AccountAlias,
  OwnerId,
  Toolkit,
  ToolkitMeta,
} from "../../../../spike/two-hands/src/connections/contract.ts";
// The ONE runtime import, and it is the owner-id rule. Re-declaring it here
// would be a second copy of the check that stops one operator's mailbox from
// serving everybody.
import { ownerId } from "./store.ts";

// ---------------------------------------------------------------------------
// THE MENU — a closed set of OUR operations, and why a closed set is not a
// word list.
// ---------------------------------------------------------------------------
// These are handed to the model as its options. No member is ever compared
// against anything a person typed; the model returns one, and `shapeOf` turns
// it into a plan. Replace every string below with a number and this module
// behaves identically, which is the test of whether a list is doing meaning's
// job or naming a menu.
//
// The account choice is TWO members rather than one member plus an `alias`
// field because `AccountAlias` is closed at exactly two values, and a flat
// pick leaves the caller a pure structural map with no second field to
// validate.
//
// FROZEN, because this array is HANDED TO THE JUDGE and then used as the
// membership test its answer has to pass. An implementation that appended to
// the list it was given — to add a house option, or by sorting in place with a
// helper that mutates — would widen what a message is allowed to mean, in the
// one place that decides it.
export const TEXT_COMMANDS = Object.freeze([
  "list_connected",
  "connect_app",
  "disconnect_app",
  "use_work_account",
  "use_personal_account",
] as const);

export type TextCommand = (typeof TEXT_COMMANDS)[number];

/** Four states, the same shape and for the same reason as the contract's
 *  `ToolkitVerdict`. */
export type CommandVerdict =
  | { kind: "command"; command: TextCommand }
  | { kind: "none" }
  | { kind: "unclear" }
  | { kind: "no-verdict" };

/**
 * The two meaning questions, as two methods, so each is asked on its own.
 *
 * `match` is the contract's `ToolkitJudge` method, unchanged, so one
 * implementation serves this module and the signal writer. `command` is this
 * module's, and it is a separate call rather than a second key in `match`'s
 * reply — HARNESS-LAWS law 1's "ONE question, asked on its own".
 */
export interface TextCommandJudge {
  command(phrase: string, commands: readonly TextCommand[]): Promise<unknown>;
  match(phrase: string, catalog: ToolkitMeta[]): Promise<unknown>;
}

/**
 * What the caller must supply. `catalog` takes the owner because the answer is
 * per owner — see the header. It may throw or return nothing; both mean the
 * same thing to an action (ask) and neither can stop a read.
 */
export interface TextCommandDeps {
  catalog(owner: OwnerId): Promise<readonly ToolkitMeta[] | null | undefined>;
  judge: TextCommandJudge;
}

// ---------------------------------------------------------------------------
// THE PLAN
// ---------------------------------------------------------------------------

/**
 * Why a message was left alone. Every value is a verdict the judge itself
 * produced, so the log says which of the three happened rather than lumping
 * them together — a night of `no-verdict` is an outage, a night of `none` is a
 * thread nobody used for this.
 */
export type PassedOverBecause = "none" | "unclear" | "no-verdict";

/**
 * Why an action stopped and asked. The first three are the toolkit judge's own
 * verdicts; the last two are ours.
 *
 *   `off-catalog` — a slug this owner's catalog does not contain.
 *   `no-catalog`  — we could not read a catalog to ask about at all.
 */
export type RefusedBecause = PassedOverBecause | "off-catalog" | "no-catalog";

/** What should happen. The caller does it; this module already did all of the
 *  deciding there is. */
export type TextCommandPlan =
  /** Not ours. Hand the message on untouched. */
  | { kind: "not_for_us"; because: PassedOverBecause }
  /** Read this owner's connections and tell them. Names no app on purpose. */
  | { kind: "list_connections"; owner: OwnerId }
  /** Mint a connect link for this app and send it. */
  | { kind: "connect"; owner: OwnerId; toolkit: Toolkit; appName: string }
  /** Revoke, then delete. In that order — the spec's own words. */
  | { kind: "disconnect"; owner: OwnerId; toolkit: Toolkit; appName: string }
  /** Use this owner's `work` or `personal` account for this app. */
  | {
      kind: "choose_account";
      owner: OwnerId;
      toolkit: Toolkit;
      appName: string;
      alias: AccountAlias;
    }
  /** The operation was pinned and the app was not. Ask; never guess. `wanted`
   *  is what they asked for, so the question can name it. */
  | { kind: "ask_which_app"; owner: OwnerId; wanted: TextCommand; because: RefusedBecause };

// ---------------------------------------------------------------------------
// THE ENTRY POINT
// ---------------------------------------------------------------------------

/**
 * One inbound message in, one plan out.
 *
 * `owner` is re-checked at run time and not merely typed, because every
 * annotation above is stripped before this file executes and a plan bound to
 * the wrong id would act on the wrong person's account. It THROWS rather than
 * falling through: a bad owner is our wiring being wrong, not somebody's
 * sentence being unclear, and a silent no-op there would hide it forever.
 *
 * The order of the two questions is not an optimisation. The operation is
 * asked first because one of the operations names no app at all, and asking
 * "which app is this about" of a sentence that is about all of them invites a
 * verdict nobody wanted.
 */
export async function planTextCommand(
  owner: OwnerId,
  text: string,
  deps: TextCommandDeps,
): Promise<TextCommandPlan> {
  const who = ownerId(String(owner ?? ""));

  // The ONLY expression in this file that touches the owner's words other than
  // the two judge calls. It reads their JavaScript type, never their content.
  const said = typeof text === "string" ? text : String(text ?? "");

  const verdict = await askCommand(deps.judge, said);
  if (verdict.kind !== "command") return { kind: "not_for_us", because: verdict.kind };

  // The read. No second question, so a silent catalog cannot stop it.
  if (verdict.command === "list_connected") return { kind: "list_connections", owner: who };

  const offered = await ownersCatalog(deps, who);
  if (offered.length === 0) {
    return { kind: "ask_which_app", owner: who, wanted: verdict.command, because: "no-catalog" };
  }

  const found = await askToolkit(deps.judge, said, offered);
  if (found.slug === null) {
    return {
      kind: "ask_which_app",
      owner: who,
      wanted: verdict.command,
      because: found.because,
    };
  }
  return shapeOf(verdict.command, who, found.slug, found.meta);
}

/**
 * The structural map: a member of our closed menu plus a resolved catalog row
 * becomes a plan. No words are read here — swapping the menu for integers
 * would leave this function's behaviour identical.
 */
function shapeOf(
  command: TextCommand,
  owner: OwnerId,
  toolkit: Toolkit,
  meta: ToolkitMeta,
): TextCommandPlan {
  const appName = displayName(meta, toolkit);
  switch (command) {
    case "connect_app":
      return { kind: "connect", owner, toolkit, appName };
    case "disconnect_app":
      return { kind: "disconnect", owner, toolkit, appName };
    case "use_work_account":
      return { kind: "choose_account", owner, toolkit, appName, alias: "work" };
    case "use_personal_account":
      return { kind: "choose_account", owner, toolkit, appName, alias: "personal" };
    default:
      // Unreachable through `askCommand`, which already refused anything
      // outside the menu, and `list_connected` returned above. It is here
      // because "unreachable" is a claim about a compiler that is not running:
      // this file ships with its types stripped. An unknown member asks.
      return { kind: "ask_which_app", owner, wanted: command, because: "unclear" };
  }
}

// ---------------------------------------------------------------------------
// QUESTION 1 — which of our operations is this?
// ---------------------------------------------------------------------------

async function askCommand(judge: TextCommandJudge, said: string): Promise<CommandVerdict> {
  let answered: unknown;
  try {
    answered = await judge.command(said, TEXT_COMMANDS);
  } catch {
    // A judge that is down has not said no. It has said nothing, and claiming
    // the message is the action here, so nothing means leave it alone.
    return { kind: "no-verdict" };
  }
  return readCommand(answered);
}

/** Everything a model hands back is an untrusted SHAPE as well as untrusted
 *  content. A reply we did not define is a missing answer, never a licence. */
function readCommand(answered: unknown): CommandVerdict {
  if (!isRecord(answered)) return { kind: "no-verdict" };
  const kind = answered["kind"];
  if (kind === "none") return { kind: "none" };
  if (kind === "unclear") return { kind: "unclear" };
  if (kind === "no-verdict") return { kind: "no-verdict" };
  if (kind !== "command") return { kind: "no-verdict" };
  const command = answered["command"];
  for (const known of TEXT_COMMANDS) {
    if (command === known) return { kind: "command", command: known };
  }
  return { kind: "no-verdict" };
}

// ---------------------------------------------------------------------------
// QUESTION 2 — which app is it about?
// ---------------------------------------------------------------------------

/** A resolved row, or the reason there is not one. `slug` is null exactly when
 *  no row was resolved, and `because` then says which of the five happened. */
interface Resolved {
  slug: Toolkit | null;
  meta: ToolkitMeta;
  because: RefusedBecause;
}

const NOTHING_RESOLVED = (because: RefusedBecause): Resolved =>
  ({ slug: null, meta: EMPTY_META, because });

/**
 * The second question. Every failure carries its OWN reason rather than being
 * folded into one: the person is asked the same thing either way, but a night
 * of `no-verdict` in the log is an outage and a night of `unclear` is a model
 * that cannot tell these apps apart, and those get fixed differently.
 */
async function askToolkit(
  judge: TextCommandJudge,
  said: string,
  offered: ToolkitMeta[],
): Promise<Resolved> {
  let answered: unknown;
  try {
    // A COPY goes to the judge and `offered` is what the answer is checked
    // against, so a judge that appends to the list it was handed — a house
    // option, an in-place sort by a helper that mutates — cannot make an app
    // this owner was never offered pass the membership test below.
    answered = await judge.match(said, [...offered]);
  } catch {
    return NOTHING_RESOLVED("no-verdict");
  }
  if (!isRecord(answered)) return NOTHING_RESOLVED("no-verdict");
  const kind = answered["kind"];
  if (kind === "none") return NOTHING_RESOLVED("none");
  if (kind === "unclear") return NOTHING_RESOLVED("unclear");
  if (kind === "no-verdict") return NOTHING_RESOLVED("no-verdict");
  // A reply in a shape we did not define is a missing answer, never a licence.
  if (kind !== "toolkit") return NOTHING_RESOLVED("no-verdict");
  const raw = answered["slug"];
  // "It says toolkit and names nothing" is a MALFORMED reply, not an app we do
  // not carry. The two are kept apart because they get fixed differently: one
  // is our prompt, the other is our catalog.
  if (typeof raw !== "string" || raw.trim() === "") return NOTHING_RESOLVED("no-verdict");
  const row = rowFor(raw.trim(), offered);
  if (row === null) return NOTHING_RESOLVED("off-catalog");
  return { slug: row.slug, meta: row, because: "none" };
}

/**
 * The judge's answer has to name something we actually handed it, and the
 * string that travels onward is the CATALOG's, never the model's.
 *
 * A model asked to pick from a list can return a plausible slug that is not in
 * it — the vendor's name for an app we do not carry, or one it remembers from
 * training. Acting on that would mint a connect link for an app this owner was
 * never offered, and a disconnect would silently match nothing while the reply
 * said "done".
 *
 * Case folding compares two machine identifiers we minted, not two human
 * words: a judge that answers with the right app in the wrong case has
 * identified the app, and refusing it would be pedantry that costs a question.
 */
function rowFor(want: string, offered: ToolkitMeta[]): ToolkitMeta | null {
  for (const meta of offered) {
    if (meta.slug === want) return meta;
  }
  const folded = want.toLowerCase();
  for (const meta of offered) {
    if (meta.slug.toLowerCase() === folded) return meta;
  }
  return null;
}

/**
 * This owner's catalog, or an empty list.
 *
 * A dep that throws and a dep that returns nothing are the same fact to an
 * action — there is no list to pin an app against — and neither may become an
 * exception the SMS route has to catch, because an unhandled throw there costs
 * the person their whole message rather than one app.
 */
async function ownersCatalog(deps: TextCommandDeps, owner: OwnerId): Promise<ToolkitMeta[]> {
  let rows: readonly ToolkitMeta[] | null | undefined;
  try {
    rows = await deps.catalog(owner);
  } catch {
    return [];
  }
  if (!Array.isArray(rows)) return [];
  // A row with no slug cannot be reasoned about and must not become an app
  // nobody was offered.
  return rows.filter(
    (meta): meta is ToolkitMeta =>
      isRecord(meta) && typeof meta["slug"] === "string" && meta["slug"].trim() !== "",
  );
}

// ---------------------------------------------------------------------------
// CONTAINING THE CATALOG — the one vendor string that reaches a phone.
// ---------------------------------------------------------------------------

/** The longest a display name may be: room for the longest real app name, and
 *  short enough that a sentence cannot arrive inside one. */
export const MAX_APP_NAME_CHARS = 64;

/** The two characters that turn a name into an ADDRESS. Walked, never used in
 *  a substring test — see the header on why this file has no such test. */
const ADDRESS_CHARS = ":/";

/** Stands in when neither the name nor the slug can be rendered. Generic on
 *  purpose: a caller that says this is telling the truth about what it knows. */
const NAMELESS = "that app";

/** A row with nothing in it, so `Resolved.meta` is never null and no caller has
 *  to check. Never rendered: `slug` is null beside it in every case that uses
 *  it. */
const EMPTY_META: ToolkitMeta = Object.freeze({
  slug: "",
  name: "",
  logo: null,
  description: null,
  appUrl: null,
  scopes: [] as string[],
});

/** Is this safe to put in a sentence somebody reads on a phone? */
function isRenderableName(value: string): boolean {
  if (value === "") return false;
  if (value.length > MAX_APP_NAME_CHARS) return false;
  for (const ch of value) {
    // A control character or a line break is a second sentence in somebody's
    // text message, written by a vendor feed rather than by us. A newline
    // inside "Here's your link to connect X" splits our promise from our link.
    const code = ch.codePointAt(0) ?? 0;
    if (code < 0x20 || code === 0x7f) return false;
    for (const bad of ADDRESS_CHARS) {
      if (ch === bad) return false;
    }
  }
  return true;
}

/**
 * The name a reply may say.
 *
 * The slug is vendor metadata too — it arrives through the same feed — so it
 * is contained by the same rule rather than trusted because it is shorter. A
 * refusal falls back; it never throws. The cost is stated plainly: a row named
 * "Something: Notes" loses its display name and shows its slug, because `:` is
 * not needed to spot a link and the rule is deliberately blunter than the
 * failure requires. A name wrongly refused is a slug on a screen; a name
 * wrongly allowed is somebody else's address in a text message we signed.
 */
export function displayName(meta: ToolkitMeta | null | undefined, fallback: string): string {
  const given = isRecord(meta) && typeof meta["name"] === "string" ? meta["name"].trim() : "";
  if (isRenderableName(given)) return given;
  const slug = typeof fallback === "string" ? fallback.trim() : "";
  return isRenderableName(slug) ? slug : NAMELESS;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
