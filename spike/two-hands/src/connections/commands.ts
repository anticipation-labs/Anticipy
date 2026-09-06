// TEXT COMMANDS AND THE SETTINGS SURFACE — one code path wearing two skins.
//
// The spec's rule is that everything in Settings has a text twin: the same
// owner can tap a toggle or type a sentence and get the same effect and the
// same words back. This file is the twin, and it is one file rather than two
// because a Settings screen and a text handler written separately drift, and
// the day they drift the toggle and the sentence disagree about whether we may
// change anything in somebody's account.
//
// WHAT THIS FILE IS NOT ALLOWED TO KNOW, AND THE TEST THAT PROVES IT.
// It does not know that any app exists. Not one name, not one slug, not one
// synonym, not one verb. Two questions have to be answered before a sentence
// becomes an action — WHICH OF OUR OPERATIONS is this, and WHICH TOOLKIT is it
// about — and both are meaning questions, so both belong to a model
// (HARNESS-LAWS law 1). They are asked SEPARATELY, one question each, because
// a question that arrives as one more key in somebody else's JSON reply loses;
// each comes back in FOUR states, because "they did not name an app" and "the
// judge never answered" are different facts and a bool holds two of them; and
// the caller below compares the verdict and never re-reads the sentence. The
// owner's words reach exactly two expressions in this file, both of them the
// argument of a judge call. `test/connections_commands.test.ts` reads this
// source back and goes red if a name, a regex, or a comparison against
// anything but our own closed enums appears.
//
// THE POLARITY IS A FLOOR, DELIBERATELY. Connecting an account, disconnecting
// one, and turning on our ability to change things inside somebody's account
// are all privileges. A privilege needs something to license it, not merely
// the absence of an objection — so an `unclear`, a `no-verdict`, a judge that
// throws, a judge that answers with a shape we did not define, and a slug that
// is not in the catalog we handed over ALL land on `unclear`, which ASKS the
// person. Nothing here acts on a missing answer.
//
// THE ONE SENTENCE THIS MODULE MUST NEVER SAY. `DisconnectResult.revoked` is
// the only licence for the word "revoked". About 5% of accounts cannot be
// revoked programmatically; telling somebody their access was revoked when the
// token is still live at the vendor is a quiet lie that this repo treats as a
// defect, and it is a lie the person cannot detect until it matters. So the
// honest branch says access was removed here and may need clearing in the
// app's own settings, and `combineResults` makes that the verdict for the whole
// app the moment ONE of the owner's accounts could not be revoked.
//
// Spec: "Connections: how Anticipy asks, learns, and never says Composio",
// 2026-09-05, pages 20-31.

import {
  ownerId,
  LINK_TTL_MS,
  type AccountAlias,
  type Connection,
  type ConnectionProvider,
  type DisconnectResult,
  type OwnerId,
  type Toolkit,
  type ToolkitJudge,
  type ToolkitMeta,
  type ToolkitVerdict,
} from "./contract.ts";

// ---------------------------------------------------------------------------
// WHAT A PERSON CAN ASK FOR — the closed set, and why a closed set is not a
// verb list.
// ---------------------------------------------------------------------------
// This is the menu of operations the module implements, handed to the model as
// its options. It is not a list of words and it never meets one: no member of
// it is ever compared against anything the owner typed. The model reads the
// sentence and returns ONE member; the mapping below turns that member into a
// shape. Swap every string here for a number and nothing about the behaviour
// changes, which is the test of whether a list is doing meaning's job.
//
// The account choice is two members rather than one member plus an `alias`
// field because `AccountAlias` in the contract is closed at exactly two values,
// and a flat pick keeps the caller's job a pure structural map with no second
// field to validate.
export const COMMAND_ACTIONS = [
  "list",
  "connect",
  "disconnect",
  "allow_changes",
  "stop_changes",
  "use_work_account",
  "use_personal_account",
] as const;

export type CommandAction = (typeof COMMAND_ACTIONS)[number];

/** Four states, same shape as the contract's `ToolkitVerdict`, for the same
 *  reason: "they asked for nothing", "they asked for something I could not
 *  pin down" and "I never answered" are three different facts. */
export type CommandVerdict =
  | { kind: "action"; action: CommandAction }
  | { kind: "none" }
  | { kind: "unclear" }
  | { kind: "no-verdict" };

/** The two meaning questions, kept as two methods so each is asked on its own.
 *  `match` is the contract's; `action` is this module's, and it is a separate
 *  call rather than a second key in `match`'s reply because a field among many
 *  loses (measured: seven cases, zero moved — HARNESS-LAWS law 1). */
export interface CommandJudge extends ToolkitJudge {
  action(phrase: string, actions: readonly CommandAction[]): Promise<CommandVerdict>;
}

/** What a sentence turned into. `unclear` is a question to the person, `none`
 *  means this was not a connections command at all and belongs to whatever
 *  else is listening. */
export type CommandIntent =
  | { kind: "list" }
  | { kind: "connect"; toolkit: Toolkit }
  | { kind: "disconnect"; toolkit: Toolkit }
  | { kind: "set_writes"; toolkit: Toolkit; on: boolean }
  | { kind: "choose_account"; toolkit: Toolkit; alias: AccountAlias }
  | { kind: "unclear" }
  | { kind: "none" };

const UNCLEAR: CommandIntent = { kind: "unclear" };
const NONE: CommandIntent = { kind: "none" };

// ---------------------------------------------------------------------------
// INTERPRET — the whole of this module's contact with a human sentence.
// ---------------------------------------------------------------------------

/**
 * Turn what somebody typed into an intent, using the injected judge for both
 * meaning questions and using nothing else for either.
 *
 * The order matters and is not an optimisation: the operation is asked first
 * because one of the operations names no app at all, and asking "which toolkit
 * is this about" of a sentence that is about all of them invites a verdict
 * nobody wanted. When the operation needs a toolkit and none can be pinned
 * down, the answer is a question, never a guess — picking the owner's only
 * connected account because it was the only candidate is how a disconnect
 * lands on the wrong one the week they connect a second.
 */
export async function interpret(
  phrase: string,
  catalog: readonly ToolkitMeta[],
  judge: CommandJudge,
): Promise<CommandIntent> {
  // Types are stripped at run time, so a caller handing us a non-string is a
  // live possibility rather than a compile error. This is the ONLY expression
  // in the file that touches the owner's words other than the two judge calls,
  // and it reads their JavaScript type, never their content.
  const said = typeof phrase === "string" ? phrase : String(phrase ?? "");
  const menu = usableCatalog(catalog);

  const verdict = await askAction(judge, said);
  if (verdict.kind === "none") return NONE;
  if (verdict.kind !== "action") return UNCLEAR;

  // The one operation that names no app. Asking the second question here would
  // spend a model call to be told "none" and then have to ignore it.
  if (verdict.action === "list") return { kind: "list" };

  const toolkit = await askToolkit(judge, said, menu);
  return shapeOf(verdict.action, toolkit);
}

/** The structural map: a member of our closed menu plus an optional toolkit
 *  becomes an intent. No words are read here; swapping the enum for integers
 *  would leave this function's behaviour identical. */
function shapeOf(action: CommandAction, toolkit: Toolkit | null): CommandIntent {
  if (action === "list") return { kind: "list" };
  // Every remaining operation acts on one app. Without one there is nothing to
  // act on and nothing to guess from.
  if (toolkit === null) return UNCLEAR;
  switch (action) {
    case "connect":
      return { kind: "connect", toolkit };
    case "disconnect":
      return { kind: "disconnect", toolkit };
    case "allow_changes":
      return { kind: "set_writes", toolkit, on: true };
    case "stop_changes":
      return { kind: "set_writes", toolkit, on: false };
    case "use_work_account":
      return { kind: "choose_account", toolkit, alias: "work" };
    case "use_personal_account":
      return { kind: "choose_account", toolkit, alias: "personal" };
    default:
      // Unreachable through `askAction`, which already refused anything outside
      // the menu. It is here because "unreachable" is a claim about a compiler
      // that is not running: this file ships with its types stripped.
      return UNCLEAR;
  }
}

async function askAction(judge: CommandJudge, said: string): Promise<CommandVerdict> {
  let answered: unknown;
  try {
    answered = await judge.action(said, COMMAND_ACTIONS);
  } catch {
    // A judge that is down has not said no. It has said nothing, and this check
    // is a floor, so nothing means ask.
    return { kind: "no-verdict" };
  }
  return normalizeAction(answered);
}

/** Everything a model hands back is untrusted shape as well as untrusted
 *  content. A reply we did not define is a missing answer, not a licence. */
function normalizeAction(answered: unknown): CommandVerdict {
  if (!isRecord(answered)) return { kind: "no-verdict" };
  const kind = answered["kind"];
  if (kind === "none") return { kind: "none" };
  if (kind === "unclear") return { kind: "unclear" };
  if (kind === "no-verdict") return { kind: "no-verdict" };
  if (kind !== "action") return { kind: "no-verdict" };
  const action = answered["action"];
  for (const known of COMMAND_ACTIONS) {
    if (action === known) return { kind: "action", action: known };
  }
  return { kind: "no-verdict" };
}

/** The toolkit question. Returns the CATALOG's own slug or null; null covers
 *  every one of "they named none", "unclear", "no verdict", "the judge threw",
 *  and "the judge named something we never offered it". */
async function askToolkit(
  judge: CommandJudge,
  said: string,
  catalog: ToolkitMeta[],
): Promise<Toolkit | null> {
  let answered: unknown;
  try {
    answered = await judge.match(said, catalog);
  } catch {
    return null;
  }
  if (!isRecord(answered)) return null;
  if (answered["kind"] !== "toolkit") return null;
  return resolveSlug(answered["slug"], catalog);
}

/**
 * The judge's answer has to name something we actually handed it.
 *
 * A model asked to pick from a catalog can return a plausible slug that is not
 * in it — the vendor's name for an app we do not carry, or one it remembers
 * from training. Acting on that would mint a connect link for a toolkit this
 * owner was never offered, and a disconnect would silently match nothing while
 * the reply said "done". So membership is checked, and the string that travels
 * onward is the CATALOG's, never the model's.
 *
 * Case folding here compares two machine identifiers we minted, not two human
 * words: a judge that answers with the right app in the wrong case has
 * identified the app, and refusing it would be pedantry that costs the owner a
 * question.
 */
function resolveSlug(raw: unknown, catalog: ToolkitMeta[]): Toolkit | null {
  if (typeof raw !== "string") return null;
  const want = raw.trim();
  if (want === "") return null;
  for (const meta of catalog) {
    if (meta.slug === want) return meta.slug;
  }
  const folded = want.toLowerCase();
  for (const meta of catalog) {
    if (meta.slug.toLowerCase() === folded) return meta.slug;
  }
  return null;
}

/** Drops catalog entries that cannot be reasoned about, so a malformed row
 *  cannot become a toolkit nobody offered. */
function usableCatalog(catalog: readonly ToolkitMeta[] | null | undefined): ToolkitMeta[] {
  if (!Array.isArray(catalog)) return [];
  return catalog.filter(
    (meta): meta is ToolkitMeta =>
      isRecord(meta) && typeof meta["slug"] === "string" && meta["slug"].trim() !== "",
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

// ---------------------------------------------------------------------------
// THE WRITE OPT-IN — off until somebody says otherwise, and reads never wait
// for it.
// ---------------------------------------------------------------------------
// This is the Settings toggle, and it is the thing the Two Hands ladder needs
// before a step may change anything in the owner's account. Two properties are
// load-bearing and both have legs in the test file:
//
//   OFF BY DEFAULT. A row with the column absent, null, or any value we do not
//   recognise reads as off. The column arrives from storage where booleans are
//   integers, so `1` counts as on and everything else does not — and that
//   asymmetry points the safe way: an unreadable opt-in withholds a privilege
//   rather than granting one.
//
//   READS NEVER REQUIRE IT. Reading somebody's mail is what they connected the
//   app for. If a read ever waited on the write toggle, the toggle would stop
//   being a consent control and start being an on/off switch for the product,
//   and every owner would turn it on to make anything work at all — which is
//   the same as not having asked.

export type Access = "read" | "write";

function isOn(value: unknown): boolean {
  return value === true || value === 1;
}

function connectedRows(rows: readonly Connection[], toolkit: Toolkit): Connection[] {
  if (!Array.isArray(rows)) return [];
  return rows.filter(
    (row) => isRecord(row) && row["toolkit"] === toolkit && row["status"] === "connected",
  );
}

/**
 * May we do this to this app right now?
 *
 * Writes require EVERY connected account for the app to be opted in, not any.
 * The Settings toggle is per app, so in the normal case the two rules are the
 * same sentence; they diverge only when the rows have skewed — a second account
 * connected after the toggle was set, say — and there the floor is the honest
 * reading. Under "any", opting in for a personal account would license a write
 * to a work one that was never offered the choice.
 */
export function mayUse(
  rows: readonly Connection[],
  toolkit: Toolkit,
  access: Access,
): boolean {
  const live = connectedRows(rows, toolkit);
  if (live.length === 0) return false;
  if (access === "read") return true;
  return live.every((row) => isOn(row.writes_enabled));
}

/** The toggle's current position, as Settings renders it. Same predicate as
 *  `mayUse(..., "write")` so the screen cannot show ON while a write is
 *  refused. */
export function writesEnabled(rows: readonly Connection[], toolkit: Toolkit): boolean {
  return mayUse(rows, toolkit, "write");
}

// ---------------------------------------------------------------------------
// THE SETTINGS VIEW — the model both skins render.
// ---------------------------------------------------------------------------

export interface ConnectedAppView {
  toolkit: Toolkit;
  /** From the catalog at run time. Falls back to the slug when the catalog has
   *  nothing to say, because a blank where a name belongs renders as
   *  "Done.  disconnected" and reads as a bug to the person. */
  name: string;
  logo: string | null;
  status: Connection["status"];
  aliases: (AccountAlias | null)[];
  accounts: number;
  writesEnabled: boolean;
  lastUsedAt: number | null;
}

export interface SettingsView {
  apps: ConnectedAppView[];
}

/** One app per row even when the owner has two accounts on it, because the
 *  toggle is per app and a screen that showed two toggles for one app would be
 *  promising a per-account control this module does not implement. */
export function settingsView(
  rows: readonly Connection[],
  catalog: readonly ToolkitMeta[],
): SettingsView {
  const metas = new Map<Toolkit, ToolkitMeta>();
  for (const meta of usableCatalog(catalog)) metas.set(meta.slug, meta);

  const bySlug = new Map<Toolkit, ConnectedAppView>();
  for (const row of Array.isArray(rows) ? rows : []) {
    if (!isRecord(row)) continue;
    const slug = row["toolkit"];
    if (typeof slug !== "string" || slug === "") continue;
    // A row the owner already disconnected is not a connected app; it is
    // history, and history on this screen reads as "you are still connected".
    if (row.status === "disconnected") continue;
    // A status we cannot name is a connection we cannot honestly describe, and
    // it must vanish from BOTH skins or the twin claim is false: `listReply`
    // groups by status, so a row with a fourth value would sit in the view the
    // screen renders and in neither of the text's two groups.
    if (row.status !== "connected" && row.status !== "needs_reconnect") continue;

    const seen = bySlug.get(slug);
    if (seen === undefined) {
      bySlug.set(slug, {
        toolkit: slug,
        name: appName(metas.get(slug), slug),
        logo: metas.get(slug)?.logo ?? null,
        status: row.status,
        aliases: [row.alias ?? null],
        accounts: 1,
        writesEnabled: isOn(row.writes_enabled),
        lastUsedAt: row.last_used_at ?? null,
      });
      continue;
    }
    seen.accounts += 1;
    seen.aliases.push(row.alias ?? null);
    // Same floor as `mayUse`: one account without the opt-in turns the app's
    // toggle off, so the screen never claims a licence a write would refuse.
    seen.writesEnabled = seen.writesEnabled && isOn(row.writes_enabled);
    if (row.status === "needs_reconnect") seen.status = "needs_reconnect";
    if ((row.last_used_at ?? 0) > (seen.lastUsedAt ?? 0)) seen.lastUsedAt = row.last_used_at ?? null;
  }

  const apps = [...bySlug.values()];
  // Sorted by the rendered name so the screen and the text twin list the same
  // apps in the same order — the twin claim is only true if it survives a
  // reload.
  apps.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
  return { apps };
}

function appName(meta: ToolkitMeta | undefined | null, fallback: string): string {
  const given = meta && typeof meta.name === "string" ? meta.name.trim() : "";
  if (given !== "") return given;
  const slug = typeof fallback === "string" ? fallback.trim() : "";
  return slug !== "" ? slug : "that app";
}

// ---------------------------------------------------------------------------
// THE REPLIES.
// ---------------------------------------------------------------------------
// The register is fixed by the spec and enforced by a leg that scans every
// string literal in this file: the person never hears the vendor's name, and
// never hears the words a settings screen for developers would use. It is
// "connect your <app>", in the app's own name, taken from the catalog.

/** Minutes, from the contract's own TTL, so a change to the link's life cannot
 *  leave this sentence claiming the old one. */
const LINK_MINUTES = Math.round(LINK_TTL_MS / 60000);

export function unclearReply(): string {
  return (
    "I can show you what's connected, connect an app, disconnect one, or turn "
    + "changes on or off for one. Which did you mean?"
  );
}

/** OUR link and nobody else's, single use, ten minutes, bound to one owner.
 *
 *  Written out here rather than imported: this module imports nothing but the
 *  contract, deliberately, so that it cannot reach the vendor even by accident,
 *  and `words.ts` holds the same prefix for the same reason. The copy is guarded
 *  by each suite pinning the literal independently rather than reading it off
 *  the other module — an oracle that is a copy of the implementation catches
 *  nothing, which this layer has already measured once. */
const OUR_LINK_PREFIX = "https://anticipy.ai/c/";

/**
 * Is this the link WE minted?
 *
 * `slice` rather than `startsWith`, and a character walk rather than a regex,
 * because this file's own law-1 legs forbid substring tests and regexes
 * outright. The legs cannot tell a check on a URL we minted from a check on
 * somebody's sentence, and their being blunt is the property worth keeping.
 */
function isOurLink(url: string): boolean {
  if (url.length <= OUR_LINK_PREFIX.length) return false;
  if (url.slice(0, OUR_LINK_PREFIX.length) !== OUR_LINK_PREFIX) return false;
  for (const ch of url) {
    // Whitespace inside the string means a second address is riding along, and
    // a phone linkifies both of them.
    if (ch.trim() === "") return false;
  }
  return true;
}

/**
 * Raised when something hands this module a connect link that is not ours.
 *
 * It THROWS rather than returning a softer sentence, on the same reasoning as
 * `PermissionWordsRefused` next door: the empty-url branch below already covers
 * "the mint failed" with copy the owner can act on, so a url that is not ours is
 * not a failed mint — it is our own plumbing offering somebody else's address,
 * and a polite "want me to try again?" would bury that defect under an owner
 * retrying forever.
 */
export class ForeignConnectLink extends Error {
  readonly url: string;
  constructor(url: string) {
    super(`refusing to send a connect link that is not ours: ${JSON.stringify(url)}`);
    this.name = "ForeignConnectLink";
    this.url = url;
  }
}

export function connectReply(meta: ToolkitMeta | null, link: { url: string }): string {
  const app = appName(meta, meta?.slug ?? "");
  const url = link && typeof link.url === "string" ? link.url.trim() : "";
  // No link, no link sentence. "Here's your link to connect Zeta:  — it opens
  // once" is a text somebody would tap at and find nothing, and they would
  // reasonably conclude the product is broken rather than that a mint failed.
  if (url === "") {
    return `I couldn't make you a link for ${app} just now. Want me to try again?`;
  }
  // THE SPEC'S FIRST RULE, WITH A FLOOR UNDER IT. Until this check existed the
  // sentence below interpolated whatever the injected minter returned, so a raw
  // vendor link reached a person inside a promise that it lasts ten minutes —
  // false about anybody else's URL, because the vendor's own link dies ten
  // minutes after it is MINTED rather than after it is sent. Four were pasted
  // into messages on 2026-09-05 and all four were dead before they were tapped.
  if (!isOurLink(url)) throw new ForeignConnectLink(url);
  // The spec's unconditional rule: every ask that ends in a connect link says
  // in one sentence that it is optional, because the browser does the same
  // work either way and somebody who feels cornered by an app they like will
  // not tell us.
  return (
    `Here's your link to connect ${app}: ${url} — it opens once and lasts `
    + `${LINK_MINUTES} minutes. Entirely up to you; I can do ${app} in your `
    + "browser either way."
  );
}

export interface DisconnectOutcome {
  toolkit: Toolkit;
  /** How many of the owner's accounts on this app we tried to disconnect. Zero
   *  means there was nothing connected. */
  attempted: number;
  /** How many of them actually left our table, and how many actually had their
   *  token revoked at the vendor.
   *
   *  These exist because `result` CANNOT express a partial. `combineResults`
   *  folds two accounts with `every`, so one clean disconnect beside one failure
   *  collapses to `{revoked:false, deleted:false}` — byte-identical to a run
   *  where the provider refused everything. The reply built from that said
   *  "nothing has changed" while `settingsView` had already dropped the row that
   *  DID come off, and two surfaces contradicting each other about whether
   *  somebody's mailbox is still reachable is the trust failure this product
   *  cannot afford. */
  deletedCount: number;
  revokedCount: number;
  result: DisconnectResult;
}

/**
 * The sentence this module exists to get right.
 *
 * `revoked === true` is the ONLY thing that licenses the word. Not
 * `deleted`, not the absence of `revokeUnavailable`, not "it usually works".
 * Deleting our record while the token stays live at the vendor is precisely
 * the state a person would describe as "I disconnected it", so the honest copy
 * has to tell them the second half themselves.
 */
export function disconnectReply(meta: ToolkitMeta | null, outcome: DisconnectOutcome): string {
  const app = appName(meta, outcome?.toolkit ?? "");
  if (!outcome || outcome.attempted === 0) {
    return `${app} isn't connected, so there's nothing to disconnect.`;
  }
  const result = outcome.result;
  const revoked = result?.revoked === true;
  const deleted = result?.deleted === true;

  if (revoked && deleted) return `Done. ${app} disconnected and access revoked.`;
  if (revoked) {
    // Access is genuinely gone; our own record is not. Saying "done" here would
    // be true about the part they care about and false about the part that
    // makes the app vanish from Settings, so it says both.
    return (
      `${app} access is revoked — nothing can use it from here. Its entry is `
      + "still on file on my side and I'm clearing it."
    );
  }
  if (deleted) {
    return (
      `Done. ${app} is disconnected here. ${app} may still list Anticipy in its `
      + "own settings, so clear it there if you want it gone at both ends."
    );
  }

  // NEITHER ALL NOR NOTHING. Reaching here with a non-zero count means some of
  // this owner's accounts on this app came off and some did not, and the old
  // sentence — "nothing has changed" — was a lie the person could check: the
  // Settings screen has already lost the rows that were deleted. Say the two
  // numbers, because "which one is still connected" is the only thing they can
  // act on, and still do not say "revoked", which is EVERY and did not happen.
  const gone = countOf(outcome.deletedCount, deleted, outcome.attempted);
  if (gone > 0 && gone < outcome.attempted) {
    return partialLine(`I disconnected ${gone} of your ${outcome.attempted} ${app} accounts.`,
      outcome.attempted - gone);
  }
  const off = countOf(outcome.revokedCount, revoked, outcome.attempted);
  if (off > 0 && off < outcome.attempted) {
    // Rarer, and worse to get wrong: nothing left our table, so both accounts
    // still LOOK connected, while one of them has quietly stopped working.
    return partialLine(`${app} access is off for ${off} of your ${outcome.attempted} accounts.`,
      outcome.attempted - off);
  }

  return `I couldn't disconnect ${app} just now, so nothing has changed. Want me to try again?`;
}

function partialLine(head: string, left: number): string {
  return `${head} The other ${left} ${left === 1 ? "is" : "are"} still connected — want me to `
    + "try again?";
}

/** A count, or the all-or-nothing reading when a caller predates the counts.
 *  Types are stripped at run time, so "the field is there" is a claim to check
 *  rather than one the compiler makes — and falling back to the combined result
 *  keeps an older caller's sentence exactly as honest as it already was. */
function countOf(given: unknown, all: boolean, attempted: number): number {
  if (typeof given === "number" && given >= 0) return Math.min(given, attempted);
  return all ? attempted : 0;
}

export interface WritesOutcome {
  toolkit: Toolkit;
  /** The position of the toggle AFTER the call. */
  enabled: boolean;
  /** False when there was nothing to toggle because the app is not connected. */
  applied: boolean;
  accounts: number;
}

export function writesReply(meta: ToolkitMeta | null, outcome: WritesOutcome): string {
  const app = appName(meta, outcome?.toolkit ?? "");
  if (!outcome || !outcome.applied) {
    return `${app} isn't connected yet, so there's nothing to change there. Want a link?`;
  }
  if (outcome.enabled) {
    return `Done — I can make changes in ${app} now. I'll show you each one before it happens.`;
  }
  return `Done — I'll only read ${app} from now on, and won't change anything in it.`;
}

export interface AccountOutcome {
  toolkit: Toolkit;
  alias: AccountAlias;
  chosen: boolean;
}

export function chooseAccountReply(meta: ToolkitMeta | null, outcome: AccountOutcome): string {
  const app = appName(meta, outcome?.toolkit ?? "");
  if (outcome?.chosen) return `Got it — I'll use your ${outcome.alias} ${app}.`;
  return `You don't have a ${outcome?.alias} ${app} connected yet. Want a link for it?`;
}

/** The text twin of the Settings screen: the same view object, rendered. */
export function listReply(view: SettingsView): string {
  const apps = view && Array.isArray(view.apps) ? view.apps : [];
  if (apps.length === 0) {
    return (
      "Nothing's connected yet. I can still do all of this in your browser — "
      + "connecting an app just makes it quicker."
    );
  }
  const lines: string[] = [];
  const live = apps.filter((app) => app.status === "connected");
  const stale = apps.filter((app) => app.status === "needs_reconnect");

  if (live.length > 0) {
    lines.push("Connected right now:");
    for (const app of live) lines.push(`• ${app.name}${accountNote(app)} — ${changeNote(app)}`);
  }
  for (const app of stale) {
    lines.push(`${app.name} has stopped working and needs connecting again.`);
  }
  return lines.join("\n");
}

function accountNote(app: ConnectedAppView): string {
  const named = app.aliases.filter((alias): alias is AccountAlias => alias !== null);
  if (named.length === 0) return "";
  return ` (${named.join(" and ")})`;
}

function changeNote(app: ConnectedAppView): string {
  return app.writesEnabled ? "I can make changes" : "reading only";
}

// ---------------------------------------------------------------------------
// THE SEAMS. Two of them, both injected, neither imported.
// ---------------------------------------------------------------------------

/** Our four tables' `connections` row, as this module needs it. Week 2 puts
 *  this on D1; the methods are async now so that day is a new implementation
 *  rather than a rewrite of everything below. */
export interface ConnectionsTable {
  forOwner(user: OwnerId): Promise<Connection[]>;
  put(row: Connection): Promise<void>;
}

/** Mints OUR link — `anticipy.ai/c/{token}`, single use, ten minutes, bound to
 *  this owner. Injected rather than built here because the vendor's own link
 *  must be generated at redeem time, and a module that could reach the vendor
 *  directly is a module that will one day put a vendor URL in a text. */
export interface LinkMinter {
  mint(user: OwnerId, toolkit: Toolkit, alias: AccountAlias | null): Promise<{ url: string }>;
}

export interface CommandDeps {
  table: ConnectionsTable;
  provider: ConnectionProvider;
  links: LinkMinter;
}

export interface Commands {
  settings(user: OwnerId): Promise<SettingsView>;
  setWrites(user: OwnerId, toolkit: Toolkit, on: boolean): Promise<WritesOutcome>;
  disconnect(user: OwnerId, toolkit: Toolkit): Promise<DisconnectOutcome>;
  chooseAccount(user: OwnerId, toolkit: Toolkit, alias: AccountAlias): Promise<AccountOutcome>;
  connect(user: OwnerId, toolkit: Toolkit): Promise<{ url: string }>;
  /** Intent in, the sentence the person reads out. The text twin. */
  handle(user: OwnerId, intent: CommandIntent): Promise<string>;
}

/**
 * Combining several accounts' results into one answer for the app.
 *
 * `revoked` is EVERY, `revokeUnavailable` is ANY. Somebody with a work and a
 * personal account on the same app who is told "access revoked" when only one
 * of the two came back has been told something false about the account that
 * still works, and it is the more dangerous half of the sentence that would be
 * wrong.
 */
export function combineResults(results: readonly DisconnectResult[]): DisconnectResult {
  const seen = Array.isArray(results) ? results.filter(isRecord) : [];
  if (seen.length === 0) return { revoked: false, deleted: false, revokeUnavailable: false };
  return {
    revoked: seen.every((r) => r["revoked"] === true),
    deleted: seen.every((r) => r["deleted"] === true),
    revokeUnavailable: seen.some((r) => r["revokeUnavailable"] === true),
  };
}

export function createCommands(deps: CommandDeps): Commands {
  const { table, provider, links } = deps;

  // EVERY entry point re-checks the owner id at run time. The contract's whole
  // reason for a distinct `OwnerId` is that one operator's mailbox once served
  // everybody, and the type that prevents that is erased before this code runs
  // — so the check has to be a call, not a signature.
  const who = (user: OwnerId): OwnerId => ownerId(user as unknown as string);

  /**
   * The store is asked for one owner's rows and the answer is checked anyway.
   *
   * This is belt and braces and it stays. The single worst failure available in
   * this module is acting on somebody else's connection — it is why `OwnerId`
   * exists as a distinct type, and it has already happened once by hand. A
   * `forOwner` that forgets its WHERE clause, or a cache keyed one field too
   * loosely, would otherwise reach a revoke on a stranger's mailbox through
   * code that looks correct at every line.
   */
  async function rowsFor(id: OwnerId): Promise<Connection[]> {
    const rows = await table.forOwner(id);
    if (!Array.isArray(rows)) return [];
    return rows.filter((row) => isRecord(row) && row["user_id"] === id);
  }

  async function metaFor(toolkit: Toolkit): Promise<ToolkitMeta | null> {
    try {
      const meta = await provider.toolkit(toolkit);
      return isRecord(meta) ? (meta as ToolkitMeta) : null;
    } catch {
      // A catalog lookup that fails must not take the reply down with it: the
      // person still needs to be told what happened to their account, and the
      // slug is a worse name than the real one but a far better one than an
      // error page.
      return null;
    }
  }

  async function settings(user: OwnerId): Promise<SettingsView> {
    const id = who(user);
    const rows = await rowsFor(id);
    const catalog: ToolkitMeta[] = [];
    const wanted = new Set<Toolkit>();
    for (const row of Array.isArray(rows) ? rows : []) {
      if (isRecord(row) && typeof row["toolkit"] === "string") wanted.add(row["toolkit"]);
    }
    for (const slug of wanted) {
      const meta = await metaFor(slug);
      if (meta !== null) catalog.push(meta);
    }
    return settingsView(rows, catalog);
  }

  async function setWrites(
    user: OwnerId,
    toolkit: Toolkit,
    on: boolean,
  ): Promise<WritesOutcome> {
    const id = who(user);
    const rows = await rowsFor(id);
    const live = connectedRows(rows, toolkit);
    if (live.length === 0) {
      return { toolkit, enabled: false, applied: false, accounts: 0 };
    }
    // The toggle is per app, so it moves every account on that app. Leaving one
    // behind is exactly the skew `mayUse` refuses, and a toggle that reads ON
    // while writes are refused is worse than one that never moved.
    for (const row of live) await table.put({ ...row, writes_enabled: on === true });
    return { toolkit, enabled: on === true, applied: true, accounts: live.length };
  }

  async function disconnect(user: OwnerId, toolkit: Toolkit): Promise<DisconnectOutcome> {
    const id = who(user);
    const rows = await rowsFor(id);
    const live = connectedRows(rows, toolkit);
    if (live.length === 0) {
      return {
        toolkit,
        attempted: 0,
        deletedCount: 0,
        revokedCount: 0,
        result: { revoked: false, deleted: false, revokeUnavailable: false },
      };
    }
    const results: DisconnectResult[] = [];
    for (const row of live) {
      let result: DisconnectResult;
      try {
        const answered = await provider.disconnect(id, row.connected_account_id);
        result = isRecord(answered)
          ? (answered as DisconnectResult)
          : { revoked: false, deleted: false, revokeUnavailable: false };
      } catch {
        // A provider that threw did not revoke and did not delete. Recording it
        // as anything else is how the reply learns to claim a revoke nobody saw.
        result = { revoked: false, deleted: false, revokeUnavailable: false };
      }
      results.push(result);
      // Only a DELETED account leaves our table, and it leaves as
      // `disconnected` rather than vanishing, so the write opt-in it carried
      // cannot be inherited by a fresh connection later.
      if (result.deleted === true) {
        await table.put({ ...row, status: "disconnected", writes_enabled: false });
      }
    }
    // Counted per account, not folded. The fold is what loses a partial, and a
    // lost partial is the reply telling somebody nothing changed while their
    // mailbox has already come off the Settings screen.
    return {
      toolkit,
      attempted: live.length,
      deletedCount: results.filter((r) => r.deleted === true).length,
      revokedCount: results.filter((r) => r.revoked === true).length,
      result: combineResults(results),
    };
  }

  async function chooseAccount(
    user: OwnerId,
    toolkit: Toolkit,
    alias: AccountAlias,
  ): Promise<AccountOutcome> {
    const id = who(user);
    const rows = await rowsFor(id);
    const match = connectedRows(rows, toolkit).some((row) => row.alias === alias);
    return { toolkit, alias, chosen: match };
  }

  async function connect(user: OwnerId, toolkit: Toolkit): Promise<{ url: string }> {
    const id = who(user);
    return links.mint(id, toolkit, null);
  }

  async function handle(user: OwnerId, intent: CommandIntent): Promise<string> {
    const id = who(user);
    if (!isRecord(intent)) return unclearReply();
    switch (intent.kind) {
      case "list":
        return listReply(await settings(id));
      case "connect": {
        const [meta, link] = await Promise.all([
          metaFor(intent.toolkit),
          connect(id, intent.toolkit),
        ]);
        return connectReply(meta, link);
      }
      case "disconnect": {
        const outcome = await disconnect(id, intent.toolkit);
        return disconnectReply(await metaFor(intent.toolkit), outcome);
      }
      case "set_writes": {
        const outcome = await setWrites(id, intent.toolkit, intent.on);
        return writesReply(await metaFor(intent.toolkit), outcome);
      }
      case "choose_account": {
        const outcome = await chooseAccount(id, intent.toolkit, intent.alias);
        return chooseAccountReply(await metaFor(intent.toolkit), outcome);
      }
      case "unclear":
        return unclearReply();
      default:
        // `none` and anything the stripped types let through: this was not ours
        // to answer, and saying something anyway is how a connections module
        // starts replying to the rest of the product's conversations.
        return "";
    }
  }

  return { settings, setWrites, disconnect, chooseAccount, connect, handle };
}
