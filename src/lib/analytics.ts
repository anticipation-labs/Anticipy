"use client";

import posthog from "posthog-js";

/**
 * The typed event spine for anticipy.ai.
 *
 * Two rules this file exists to enforce, both of which are cheap now and
 * impossible to retrofit once real data has accumulated:
 *
 *  1. FEW EVENT NAMES, MANY PROPERTIES. Every CTA on the site emits one
 *     `cta_clicked` differentiated by `cta_location`/`cta_type`, not eight
 *     separate event names. Dynamically-generated names produce thousands of
 *     unmaintainable event definitions and make funnels impossible to build.
 *
 *  2. NO EVENT NAME THAT ISN'T IN THIS UNION. `capture()` only accepts
 *     `AnticipyEvent`, so a typo is a compile error rather than a silent
 *     second event name that splits a funnel in half.
 *
 * Naming convention is `object_action`, snake_case, present tense.
 *
 * What is deliberately NOT here: scroll depth and time-on-page for
 * *reporting*. PostHog already puts `$prev_pageview_max_scroll_percentage`
 * and `$prev_pageview_duration` on every `$pageleave`. The custom milestone
 * events below exist only because we need them as discrete funnel steps and
 * as real-time triggers for the offer engine — not because the reporting
 * layer lacks them.
 */
export type AnticipyEvent =
  // ── Engagement ────────────────────────────────────────────────
  | "section_viewed"
  | "page_scroll_depth_reached"
  | "page_dwell_milestone_reached"
  // ── Interaction ───────────────────────────────────────────────
  | "cta_clicked"
  | "video_playback_progressed"
  | "faq_item_opened"
  | "outbound_link_clicked"
  // ── Checkout funnel ───────────────────────────────────────────
  | "checkout_started"
  | "checkout_form_field_completed"
  | "checkout_email_field_completed"
  | "checkout_validation_failed"
  | "checkout_email_submitted"
  | "checkout_redirected_to_stripe"
  | "checkout_abandoned"
  | "checkout_returned_canceled"
  // ── Offers ────────────────────────────────────────────────────
  | "offer_shown"
  | "offer_accepted"
  | "offer_dismissed"
  | "offer_suppressed"
  // ── Waitlist + consent ────────────────────────────────────────
  | "waitlist_submitted"
  | "consent_updated";

/** Enumerated so CTA data never degrades into free-form text. */
export type CtaLocation =
  | "nav"
  | "hero"
  | "sticky_bar"
  | "how_it_works"
  | "video"
  | "comparison"
  | "specs"
  | "faq"
  | "founder"
  | "final_cta"
  | "footer"
  | "offer_modal";

export type CtaType =
  | "preorder"
  | "waitlist"
  | "learn_more"
  | "video_play"
  | "anchor"
  | "contact";

export type SectionId =
  | "hero"
  | "wound"
  | "turn"
  | "chapters"
  | "live_demo"
  | "comparison"
  | "object"
  | "worn"
  | "trust"
  | "faq"
  | "close"
  | "footer";

type Props = Record<string, unknown>;

// ─── Engagement context ─────────────────────────────────────────
//
// "Engaged" time is not wall-clock time. A tab left open in a background
// window overnight is not twelve hours of attention, and treating it as such
// both corrupts the dwell metric and causes the offer engine to fire the
// moment someone returns to a stale tab. Time only accrues while the document
// is visible AND there has been real input within IDLE_TIMEOUT_MS.

const IDLE_TIMEOUT_MS = 30_000;
const TICK_MS = 1_000;

interface EngagementState {
  pageviewId: string;
  engagedMsOnPage: number;
  engagedMsOnSite: number;
  maxScrollDepthPct: number;
  sectionsViewed: Set<string>;
  lastInputAt: number;
  /** Milestones already emitted for the current pageview. */
  firedThisPageview: Set<string>;
  started: boolean;
}

const state: EngagementState = {
  pageviewId: "",
  engagedMsOnPage: 0,
  engagedMsOnSite: 0,
  maxScrollDepthPct: 0,
  sectionsViewed: new Set(),
  lastInputAt: 0,
  firedThisPageview: new Set(),
  started: false,
};

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `pv_${Date.now()}_${Math.floor(Math.random() * 1e9)}`;
}

function isEngaged(): boolean {
  if (typeof document === "undefined") return false;
  if (document.visibilityState !== "visible") return false;
  return Date.now() - state.lastInputAt < IDLE_TIMEOUT_MS;
}

/**
 * Starts the engagement clock and input listeners. Idempotent — safe to call
 * from a component that may remount.
 */
export function startEngagementTracking(): () => void {
  if (typeof window === "undefined" || state.started) return () => {};
  state.started = true;
  state.lastInputAt = Date.now();

  const markInput = () => {
    state.lastInputAt = Date.now();
  };

  // Passive listeners only — none of these may block scrolling or delay INP.
  const opts = { passive: true } as const;
  window.addEventListener("scroll", markInput, opts);
  window.addEventListener("pointerdown", markInput, opts);
  window.addEventListener("keydown", markInput, opts);
  window.addEventListener("touchstart", markInput, opts);

  const timer = window.setInterval(() => {
    if (!isEngaged()) return;
    state.engagedMsOnPage += TICK_MS;
    state.engagedMsOnSite += TICK_MS;
  }, TICK_MS);

  return () => {
    window.clearInterval(timer);
    window.removeEventListener("scroll", markInput);
    window.removeEventListener("pointerdown", markInput);
    window.removeEventListener("keydown", markInput);
    window.removeEventListener("touchstart", markInput);
    state.started = false;
  };
}

/**
 * Resets per-page counters on client navigation. Engaged-time-on-SITE and the
 * scroll maximum deliberately survive, because a visitor who read three pages
 * is more qualified than one who idled on a single page — and that
 * cross-page total is what the offer engine gates on.
 */
export function beginPageview(): string {
  state.pageviewId = newId();
  state.engagedMsOnPage = 0;
  state.maxScrollDepthPct = 0;
  state.firedThisPageview.clear();
  return state.pageviewId;
}

export function recordScrollDepth(pct: number): void {
  if (pct > state.maxScrollDepthPct) state.maxScrollDepthPct = Math.min(pct, 100);
}

export function recordSectionViewed(sectionId: string): boolean {
  const first = !state.sectionsViewed.has(sectionId);
  state.sectionsViewed.add(sectionId);
  return first;
}

/** Fire-once guard for milestone events, scoped to the current pageview. */
export function claimMilestone(key: string): boolean {
  if (state.firedThisPageview.has(key)) return false;
  state.firedThisPageview.add(key);
  return true;
}

/** Read-only snapshot for the offer engine's trigger evaluation. */
export function engagementSnapshot() {
  return {
    pageviewId: state.pageviewId,
    engagedSecondsOnPage: Math.round(state.engagedMsOnPage / 1000),
    engagedSecondsOnSite: Math.round(state.engagedMsOnSite / 1000),
    maxScrollDepthPct: state.maxScrollDepthPct,
    sectionsViewedCount: state.sectionsViewed.size,
  };
}

/**
 * Context merged into every custom event, so any event can be analysed
 * against how engaged the visitor was when it fired — without joining
 * across tables. `pageview_id` is what stitches section/scroll/dwell events
 * from one pageview back together.
 */
function withCtx(props?: Props): Props {
  const s = engagementSnapshot();
  return {
    pageview_id: s.pageviewId,
    engaged_seconds_on_page: s.engagedSecondsOnPage,
    engaged_seconds_on_site: s.engagedSecondsOnSite,
    max_scroll_depth_pct: s.maxScrollDepthPct,
    sections_viewed_count: s.sectionsViewedCount,
    ...props,
  };
}

/**
 * The only way to emit a custom event. Never call `posthog.capture` directly
 * — doing so bypasses both the name union and the engagement context.
 */
export function capture(event: AnticipyEvent, props?: Props): void {
  if (typeof window === "undefined") return;
  try {
    posthog.capture(event, withCtx(props));
  } catch {
    // Analytics must never take the page down. A blocked or failed capture
    // is an acceptable loss; an exception thrown into a click handler is not.
  }
}

/**
 * Canonical person id: SHA-256 of the normalised email.
 *
 * Chosen so the browser, the Stripe webhook, the ESP and a future iOS client
 * can each derive the same id independently with no database round-trip, and
 * so the id itself is not a raw email sitting in analytics URLs. The raw
 * address is still set as a person property, where it can be edited or
 * deleted on request — unlike a distinct_id, which PostHog cannot rewrite.
 */
export async function emailHash(email: string): Promise<string> {
  const normalized = email.trim().toLowerCase();
  const bytes = new TextEncoder().encode(normalized);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** Coarse classification — never send the local part of an address. */
export function emailDomainClass(
  email: string
): "freemail" | "corporate" | "edu" | "gov" | "disposable" | "role" | "unknown" {
  const at = email.lastIndexOf("@");
  if (at < 0) return "unknown";
  const local = email.slice(0, at).toLowerCase();
  const domain = email.slice(at + 1).toLowerCase();

  const ROLE = new Set([
    "info",
    "admin",
    "support",
    "sales",
    "contact",
    "hello",
    "team",
    "billing",
    "noreply",
  ]);
  if (ROLE.has(local)) return "role";

  const FREE = new Set([
    "gmail.com",
    "yahoo.com",
    "hotmail.com",
    "outlook.com",
    "icloud.com",
    "me.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
    "live.com",
    "msn.com",
    "gmx.com",
    "yandex.com",
  ]);
  const DISPOSABLE = new Set([
    "mailinator.com",
    "guerrillamail.com",
    "10minutemail.com",
    "tempmail.com",
    "trashmail.com",
    "yopmail.com",
    "sharklasers.com",
  ]);

  if (DISPOSABLE.has(domain)) return "disposable";
  if (FREE.has(domain)) return "freemail";
  if (domain.endsWith(".edu") || domain.endsWith(".ac.uk")) return "edu";
  if (domain.endsWith(".gov") || domain.endsWith(".mil")) return "gov";
  if (domain.includes(".")) return "corporate";
  return "unknown";
}

/**
 * Identify on SUBMIT only.
 *
 * Never call this on blur or keystroke. Capturing an address the visitor
 * typed but never submitted is the Popa v. Harriet Carter fact pattern, and
 * a half-typed address becomes a permanent distinct_id that PostHog cannot
 * rewrite — it would poison the person graph for the life of the project.
 *
 * PostHog silently refuses to merge two already-identified persons: it
 * ingests the event, logs an ingestion warning, and does nothing. So a
 * second identify() with a different id LOOKS like it worked and did not.
 * Callers that may be re-identifying a different person must reset() first.
 */
export async function identifyByEmail(
  email: string,
  setProps: Props,
  setOnceProps?: Props
): Promise<string | null> {
  if (typeof window === "undefined") return null;
  try {
    const hash = await emailHash(email);
    posthog.identify(
      hash,
      { email: email.trim().toLowerCase(), email_domain_class: emailDomainClass(email), ...setProps },
      setOnceProps
    );
    return hash;
  } catch {
    return null;
  }
}

/** Distinct id + session id to stamp into Stripe metadata for server-side attribution. */
export function attributionIds(): { distinctId: string; sessionId: string } {
  try {
    return {
      distinctId: posthog.get_distinct_id?.() ?? "",
      sessionId: posthog.get_session_id?.() ?? "",
    };
  } catch {
    return { distinctId: "", sessionId: "" };
  }
}
