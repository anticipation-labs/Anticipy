// CONNECTIONS: HOW EACH iOS USER CONNECTS THEIR OWN APPS.
//
// The Two Hands contract next door decides WHICH HAND runs a step. This one
// covers the only part a person ever sees: being asked to connect an app, in
// their own words, at a moment that makes sense, and connecting THEIR account —
// never ours.
//
// THE MISTAKE THIS FILE EXISTS TO PREVENT. During the spike, one operator's own
// Gmail and Calendar were connected by hand to prove the key worked. That is
// backwards and it was undone (revoked, then deleted). Anticipy is not an
// integration with the founder's mailbox; it is a per-user product where every
// owner connects their own accounts through the iOS app or a text. So:
//
//   THE USER ID IS THE OWNER ROW ID, ALWAYS, AND NEVER A NAME.
//
// `user_id` is the id of the owner using the app — `sxkotd1h02qb6gw`, not
// "omar", not an email. It is resolved per request from the signed-in session.
// A constant here would mean one person's tokens serving everybody, which is
// the worst failure this system can have. `OwnerId` is a distinct type so a
// display name cannot be passed where an id belongs.
//
// Spec: "Connections: how Anticipy asks, learns, and never says Composio",
// 2026-09-05, pages 20-31.

/** The owner's row id, as stored in D1's `owners` table. NOT an email, NOT a
 *  display name. Every Composio call is scoped by exactly this. */
export type OwnerId = string & { readonly __ownerId: unique symbol };

export function ownerId(raw: string): OwnerId {
  const id = String(raw ?? "").trim();
  // The ids this system mints are 15 lowercase alphanumerics. An email or a
  // human name reaching here means a caller has confused "who is this" with
  // "what do we call them", and the connection would bind to the wrong person.
  if (!/^[a-z0-9]{15}$/.test(id)) {
    throw new Error(
      `not an owner id: ${JSON.stringify(raw)} — connections bind to the owner ROW id, `
        + "never a name or an email",
    );
  }
  return id as OwnerId;
}

/** A Composio toolkit slug, lowercase: "gmail", "googlecalendar", "notion".
 *  Never hardcoded in policy — it arrives from the catalog or from a model
 *  matching the user's own words. */
export type Toolkit = string;

/** Which of the owner's accounts this connection is. The spec's normal case is
 *  two Google accounts, so these are real names on real connections. */
export type AccountAlias = "work" | "personal";

// ---------------------------------------------------------------------------
// THE FOUR TABLES
// ---------------------------------------------------------------------------

/** Weighted evidence that this owner uses this app. Signals decay, so an app
 *  they stopped using stops being asked about. */
export interface AppUsageSignal {
  user_id: OwnerId;
  toolkit: Toolkit;
  /** How we learned it. `said` and `observer` are high, `mx` and `link` are
   *  medium, `connected` and `asked` are certain. */
  source: "said" | "observer" | "mx" | "link" | "connected" | "asked";
  weight: number;
  last_seen_at: number;
}

export interface Connection {
  user_id: OwnerId;
  toolkit: Toolkit;
  connected_account_id: string;
  alias: AccountAlias | null;
  status: "connected" | "needs_reconnect" | "disconnected";
  /** THE WRITE OPT-IN, off by default. This is the Settings toggle "let
   *  Anticipy make changes", and the Two Hands ladder cannot reach rung 3
   *  without it. Reads never require it. */
  writes_enabled: boolean;
  last_used_at: number | null;
}

export type NudgeState =
  | "never_asked"
  | "asked"
  /**
   * THE SETUP CARD SHRUG, and it is a sixth state because the spec asks for one
   * by name — twice. Page 21: "Skip records `declined_soft` with a 7-day
   * snooze, not a real decline." Page 25: "Skipping in onboarding is a 7-day
   * snooze, not a decline."
   *
   * WHY IT CANNOT BE `declined` WITH A SHORTER CLOCK, which is what shipped
   * until 2026-09-06. `recordDecline` advanced the ladder to level 1 on an
   * onboarding skip, and `LEVEL_THRESHOLD[1]` is 0.80 against a STRICT
   * comparison — so in_task (0.80), onboarding (0.70) and repeated_use (0.60)
   * never clear it again. The three triggers that can name a task which
   * already cost this person real time were silenced for good by one tap on a
   * card during setup. That is the opposite of "not a real decline".
   *
   * WHY IT CANNOT BE `declined` AT LEVEL 0 EITHER. `whatIsMissing` refuses
   * that row by name ("the ladder was not advanced, so the decline cannot be
   * honoured"), which turns every future verdict about that app into
   * `no-verdict` — worse than level 1, because nothing ever re-opens it.
   *
   * WHY IT CANNOT BE `never_asked` WITH A SNOOZE. It would read as a lie: the
   * person WAS asked, on the glass, and `acted_at` on the row says so. A state
   * that disagrees with a stamped `acted_at` is how the next reader concludes
   * the column is unreliable.
   *
   * SO: its own state, LEVEL 0, snoozed `ONBOARDING_SKIP_SNOOZE_DAYS`. The
   * snooze is honoured like any other (policy step 5 checks every state), and
   * when it runs out the owner is back at threshold 0.5 — askable by anything.
   * A shrug costs seven days of quiet and nothing else.
   */
  | "declined_soft"
  | "declined"
  | "connected"
  | "needs_reconnect";

/** Which real moment produced the ask. Never "out of nowhere" — every value
 *  here is a thing that actually happened, and the log is keyed by it so the
 *  timers can be tuned from what converts. */
export type NudgeTrigger =
  | "in_task"        // a step routed to browser and the catalog has a match
  | "repeated_use"   // third browser run on the same app inside 14 days
  | "laptop_closed"  // a task is queued because the Mac is shut
  | "user_named_it"  // they said "my Notion"
  | "onboarding";

export interface ConnectNudge {
  user_id: OwnerId;
  toolkit: Toolkit;
  state: NudgeState;
  /** 0 while never declined; 1, 2, 3 as declines accumulate. Level 3 stops. */
  level: 0 | 1 | 2 | 3;
  snooze_until: number | null;
  trigger: NudgeTrigger | null;
  sent_at: number | null;
  acted_at: number | null;
  channel: "sms" | "ios" | null;
}

/** OUR link, not Composio's. Single use, ten minutes, bound to one owner and
 *  one toolkit. The raw Composio link is generated only when this token is
 *  redeemed, because Composio's own link also expires in ten minutes — sending
 *  one in a text guarantees it is dead before it is tapped. Measured: four
 *  links generated and handed over on 2026-09-05 all expired unused. */
export interface ConnectLink {
  token: string;
  user_id: OwnerId;
  toolkit: Toolkit;
  alias: AccountAlias | null;
  expires_at: number;
  used_at: number | null;
}

// ---------------------------------------------------------------------------
// THE PROVIDER SEAM
// ---------------------------------------------------------------------------

export interface ConnectionProvider {
  /** One session per owner, restored by stored session_id.
   *  MUST be created with manage_connections disabled: otherwise Composio
   *  gives the model a tool that pastes a raw vendor link into a text, and the
   *  spec's first rule is that we own the ask. */
  session(user: OwnerId): Promise<{ sessionId: string }>;
  /** The vendor's connect URL. Called at REDEEM time, never at send time. */
  authorize(
    user: OwnerId,
    toolkit: Toolkit,
    opts: { callbackUrl: string; alias?: AccountAlias | null },
  ): Promise<{ redirectUrl: string }>;
  connections(user: OwnerId): Promise<Connection[]>;
  /** Revoke THEN delete. Delete alone leaves the token live at the provider —
   *  the user was told their access was revoked, so it must actually be. About
   *  5% cannot be revoked programmatically; say so honestly rather than
   *  claiming a revoke that did not happen. */
  disconnect(user: OwnerId, connectedAccountId: string): Promise<DisconnectResult>;
  /** Name, logo, description and required scopes, so the connect page and the
   *  permission sentences are generic. No app is hardcoded. */
  toolkit(slug: Toolkit): Promise<ToolkitMeta>;
}

export interface DisconnectResult {
  revoked: boolean;
  deleted: boolean;
  /** True when the provider could not revoke programmatically. The
   *  confirmation copy must then say access was removed here but may need
   *  clearing in the app's own settings — never "access was revoked". */
  revokeUnavailable: boolean;
}

export interface ToolkitMeta {
  slug: Toolkit;
  name: string;
  logo: string | null;
  description: string | null;
  appUrl: string | null;
  scopes: string[];
}

// ---------------------------------------------------------------------------
// THE ASK
// ---------------------------------------------------------------------------

/** A four-state answer, because "should we interrupt this person" is exactly
 *  the kind of question that must be allowed to say "I don't know". */
export type NudgeDecision = "ask" | "hold" | "never-again" | "no-verdict";

export interface NudgeVerdict {
  decision: NudgeDecision;
  /** For the log, so the timers can be tuned from what converts. Nothing
   *  branches on these words. */
  reason: string;
}

export interface NudgeContext {
  now: number;
  trigger: NudgeTrigger;
  /** Owner-local hour, 0-23. Quiet hours are 22:00-08:00 and a connect link at
   *  2am is spam whatever the score says. */
  localHour: number;
  /** A nudge NEVER lands mid-step, and never before the task result. The whole
   *  product is trust under silence; an ask that arrives instead of an answer
   *  spends that trust. */
  taskInFlight: boolean;
  resultDelivered: boolean;
  /** Evidence. Zero means hold: we do not ask about an app on a hunch. */
  tasksThatWouldHaveUsedIt: number;
  /** Across ALL apps. One ask per owner per 7 days, so somebody who just ran
   *  three browser tasks does not get three connect texts. */
  lastAskAnyAppAt: number | null;
}

/** The right-time score per the spec. Values are config, not code. */
export const TRIGGER_SCORE: Record<NudgeTrigger, number> = {
  laptop_closed: 1.0,
  user_named_it: 0.9,
  in_task: 0.8,
  onboarding: 0.7,
  repeated_use: 0.6,
};

/** Ask only if the moment scores above the snooze level's threshold. */
export const LEVEL_THRESHOLD: Record<0 | 1 | 2 | 3, number> = {
  0: 0.5,
  1: 0.8,
  2: 0.95,
  3: Number.POSITIVE_INFINITY, // level 3 stops; only the user may reopen it
};

/** Snooze after each decline, in days. Level 3 never re-asks. */
export const SNOOZE_DAYS: Record<1 | 2 | 3, number> = { 1: 14, 2: 45, 3: 3650 };

export const GLOBAL_ASK_INTERVAL_DAYS = 7;
export const SILENCE_IS_A_SOFT_NO_HOURS = 72;
export const ONBOARDING_SKIP_SNOOZE_DAYS = 7;
export const LINK_TTL_MS = 10 * 60 * 1000;

export interface NudgePolicy {
  shouldAsk(nudge: ConnectNudge, ctx: NudgeContext): NudgeVerdict;
}

/** Turns a toolkit's own metadata into the three plain sentences the connect
 *  page shows. Generated from scopes, never a per-app string table — a new app
 *  in the catalog is a new app in Anticipy with zero code.
 *
 *  The register is fixed by the spec: never "authorize", "grant access",
 *  "permissions", "integration" or "API". It is "connect your Notion". */
export interface PermissionWords {
  sentences(meta: ToolkitMeta): Promise<string[]>;
}

/** Which toolkit did the user mean? "connect notion", "disconnect slack",
 *  "use my work Gmail for this". A MODEL answers this against the catalog —
 *  HARNESS-LAWS law 1: no keyword list decides what an app name means, because
 *  "my Outlook" and "office mail" and "my work email" are the same request and
 *  no list holds them all. */
export type ToolkitVerdict =
  | { kind: "toolkit"; slug: Toolkit }
  | { kind: "none" }
  | { kind: "unclear" }
  | { kind: "no-verdict" };

export interface ToolkitJudge {
  match(phrase: string, catalog: ToolkitMeta[]): Promise<ToolkitVerdict>;
}
