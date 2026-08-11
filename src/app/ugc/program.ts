/**
 * The Anticipy UGC Creator program, in one place.
 *
 * Every number a creator is shown — on the page, in the wizard, in both
 * emails — is read from here, so changing what the program pays is a one-line
 * edit and cannot end up saying two different things in two places. A creator
 * program whose posted rate disagrees with its confirmation email is a
 * dispute waiting to happen.
 */

export const PAY = {
  /** Paid once per approved video, after it clears the view floor. */
  perVideo: 25,
  /** A video below this does not earn the flat fee. */
  viewFloor: 1000,
  /** Share of each pre-order attributed to a creator's link. */
  purchaseSharePct: 15,
} as const;

/** The list price a creator's share is calculated against, in dollars. */
export const LIST_PRICE = 149.99;

export const PAY_LINES: { amount: string; label: string; detail: string }[] = [
  {
    amount: `$${PAY.perVideo}`,
    label: "per video",
    detail: `Once it passes ${PAY.viewFloor.toLocaleString()} views. Post it, tag us, send us the link.`,
  },
  {
    amount: `${PAY.purchaseSharePct}%`,
    label: "of every order",
    detail: `Anyone who buys through your link. About $${((LIST_PRICE * PAY.purchaseSharePct) / 100).toFixed(2)} at today's price.`,
  },
];

/**
 * What a creator is agreeing to. Both are affirmative checkboxes rather than
 * fine print — one is a legal obligation on them, the other is a licence they
 * are granting us, and neither should be something they discover later.
 */
export const AGREEMENTS = {
  disclosure: {
    id: "disclosure",
    label: "I'll label every paid video as an ad.",
    detail:
      "We pay you, so this is a material connection and US and Canadian rules both require it to be obvious. Use the platform's own paid-partnership label, or #ad in the caption — and say it out loud in the first few seconds if the video is spoken. This one is not optional and it protects you as much as us.",
  },
  rights: {
    id: "rights",
    label: "Anticipy can run my video as an ad for 90 days.",
    detail:
      "On Instagram, TikTok, YouTube, Facebook and our own site. Ninety days from the day you send it, then it lapses unless we ask you again and pay for it. We are not asking for access to your ad account, and we will not run anything through your handle without a separate written agreement. You keep the video and can post it anywhere you like.",
  },
} as const;

/** Where a creator's link points, and what they get to choose. */
export const LINK_BASE = "anticipy.ai/c/";

export const HANDLE_RULES = {
  min: 3,
  max: 24,
  /** Lowercase letters, digits and single inner hyphens. */
  pattern: /^[a-z0-9](?:[a-z0-9-]{1,22}[a-z0-9])$/,
  help: "Lowercase letters, numbers and hyphens. 3–24 characters.",
};

/**
 * Handles that must never belong to a creator: they either collide with a
 * real route or would let somebody impersonate the company.
 */
export const RESERVED_HANDLES = new Set([
  "anticipy", "anticipylabs", "anticipationlabs", "admin", "api", "app",
  "apply", "build", "grow", "ship", "sync", "ugc", "c", "waitlist", "funded",
  "internal", "crm", "engine", "analytics", "support", "help", "team",
  "official", "hq", "shop", "store", "buy", "order", "preorder", "pre-orders",
  "login", "signup", "account", "settings", "privacy", "terms", "refund",
  "omar", "founder", "ceo", "press", "media", "careers", "jobs", "join",
]);

export function normalizeHandle(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/^[@/]+/, "")
    .replace(/[\s_.]+/g, "-")
    .replace(/[^a-z0-9-]/g, "")
    .replace(/-{2,}/g, "-")
    .slice(0, HANDLE_RULES.max);
}

/** Returns an error string, or null when the handle is usable. */
export function validateHandle(handle: string): string | null {
  if (handle.length < HANDLE_RULES.min) return `At least ${HANDLE_RULES.min} characters.`;
  if (handle.length > HANDLE_RULES.max) return `At most ${HANDLE_RULES.max} characters.`;
  if (!HANDLE_RULES.pattern.test(handle)) return HANDLE_RULES.help;
  if (RESERVED_HANDLES.has(handle)) return "That one's taken.";
  return null;
}

export interface UgcQuestion {
  id: string;
  q: string;
  hint?: string;
  placeholder: string;
}

/**
 * Four questions, chosen to predict whether somebody can actually make a
 * video that holds attention — not to measure follower count, which is the
 * number most creator forms ask for and the one least connected to whether a
 * video sells anything.
 */
export const UGC_QUESTIONS: UgcQuestion[] = [
  {
    id: "u1",
    q: "Link the best thing you've made.",
    hint: "Whatever you're proudest of, or whatever performed best — they're often not the same video.",
    placeholder:
      "Paste the link, then tell me in a line or two why that one worked when others didn't.",
  },
  {
    id: "u2",
    q: "Who actually watches you?",
    hint: "Roughly how many, and more usefully — who are they and why do they stay?",
    placeholder:
      "Rough numbers are fine. What I care about is who they are and what they come to you for.",
  },
  {
    id: "u3",
    q: "You've just put the pendant on. What's your first video?",
    hint: "A pendant that hears what you said and gets it done. No wake word.",
    placeholder:
      "One idea, described the way you'd describe it to a friend. The hook matters more than the plot.",
  },
  {
    id: "u4",
    q: "Anything else I should know?",
    hint: "Optional. Skip it if there's nothing.",
    placeholder: "Or leave it empty and go make the video.",
  },
];

export const SOCIALS: { id: string; label: string; prefix: string; placeholder: string }[] = [
  { id: "instagram", label: "Instagram", prefix: "@", placeholder: "yourhandle" },
  { id: "tiktok", label: "TikTok", prefix: "@", placeholder: "yourhandle" },
  { id: "x", label: "X", prefix: "@", placeholder: "yourhandle" },
  { id: "linkedin", label: "LinkedIn", prefix: "", placeholder: "linkedin.com/in/you" },
];

export const PAYOUT_METHODS = ["PayPal", "Interac e-Transfer", "Wise"] as const;
