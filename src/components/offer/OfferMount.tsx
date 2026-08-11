"use client";

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { usePathname } from "next/navigation";
import { capture, engagementSnapshot } from "@/lib/analytics";
import type { Offer } from "./OfferDialog";

// Not in the initial bundle. The chunk is only fetched once a trigger has
// armed, so it cannot compete for bandwidth during LCP.
const OfferDialog = dynamic(
  () => import("./OfferDialog").then((m) => m.OfferDialog),
  { ssr: false }
);

/**
 * Routes where an offer would be an interruption rather than an offer.
 *
 * Two categories, and the second is the one that is easy to get wrong:
 *  - Pages where the visitor is already transacting or reading legal terms.
 *  - Pages addressed to someone who is NOT a shopper. A pendant discount
 *    shown to a job applicant or an investor is not a missed sale, it is a
 *    signal that nobody is minding the site. This was caught live: the wheel
 *    fired on /build while an engineer was mid-application.
 *
 * Adding a page that is not a purchase funnel? Add it here at the same time.
 */
const SUPPRESSED = [
  "/pre-orders/purchase",
  "/pre-orders/success",
  "/pre-orders/agreement",
  // Hiring. Job applicants are not shoppers — a discount wheel must never
  // fire on top of a job application.
  "/apply", // the listings hub and the wizard at /apply/start
  "/grow",
  "/ship",
  "/build",
  "/sync",
  "/ugc", // creator program — also not shoppers
  "/growth", // legacy, redirects to /grow
  "/jobs",
  "/join",
  "/funded", // investor page
  "/privacy",
  "/terms",
  "/refund",
  "/admin",
  "/crm",
  "/engine",
  "/analytics",
  "/internal",
  "/app",
];

const K = {
  session: "ap_offer_v1_session_shown",
  shownAt: "ap_offer_v1_shown_at",
  dismissCount: "ap_offer_v1_dismiss_count",
  optout: "ap_offer_v1_optout",
};

const DAY = 86_400_000;

/** Every storage read is wrapped: Safari private mode throws on access. */
function read(store: Storage, key: string): string | null {
  try {
    return store.getItem(key);
  } catch {
    return null;
  }
}
function write(store: Storage, key: string, value: string): void {
  try {
    store.setItem(key, value);
  } catch {
    /* storage disabled — degrade to showing at most once per page load */
  }
}

/**
 * Decides whether an offer may be shown at all, before any network call.
 *
 * Escalating cooldowns matter more than trigger tuning: session-capped
 * campaigns hold multiple times the conversion of uncapped ones, and a
 * documented four-popups-per-session build produced a 79% bounce rate.
 */
function eligibleByFrequency(): boolean {
  if (typeof window === "undefined") return false;

  if (read(localStorage, K.optout) === "1") return false;
  if (read(sessionStorage, K.session) === "1") return false;

  const dismissals = Number(read(localStorage, K.dismissCount) || "0");
  if (dismissals >= 3) return false;

  const shownAt = Number(read(localStorage, K.shownAt) || "0");
  if (shownAt) {
    const cooldown = dismissals >= 2 ? 30 * DAY : dismissals >= 1 ? 7 * DAY : DAY;
    if (Date.now() - shownAt < cooldown) return false;
  }
  return true;
}

function isBot(): boolean {
  if (typeof navigator === "undefined") return true;
  if (navigator.webdriver) return true;
  return /Lighthouse|Chrome-Lighthouse|GTmetrix|PageSpeed|HeadlessChrome/i.test(
    navigator.userAgent
  );
}

export function OfferMount() {
  const pathname = usePathname();
  const [offer, setOffer] = useState<Offer | null>(null);
  const [trigger, setTrigger] = useState<string>("");
  const armed = useRef(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (armed.current) return;
    if (SUPPRESSED.some((p) => pathname?.startsWith(p))) return;
    if (isBot() && !window.location.search.includes("popup=force")) return;
    if (!eligibleByFrequency()) return;

    // A visitor who arrived on a link that already carries an offer should
    // not be shown a second one.
    const qs = new URLSearchParams(window.location.search);
    if (qs.has("promo") || qs.has("discount") || qs.has("coupon")) return;

    let cancelled = false;

    const fire = async (triggerType: string) => {
      if (armed.current || cancelled) return;
      armed.current = true;

      const snap = engagementSnapshot();
      try {
        const res = await fetch("/api/offers/evaluate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            engagedSeconds: snap.engagedSecondsOnSite,
            maxScrollPct: snap.maxScrollDepthPct,
            sectionsSeen: [],
            pagesSeen: [window.location.pathname],
            referrer: document.referrer || null,
            utmSource: qs.get("utm_source"),
            utmMedium: qs.get("utm_medium"),
            utmCampaign: qs.get("utm_campaign"),
            landingPath: window.location.pathname,
            newSession: read(sessionStorage, "ap_seen") !== "1",
          }),
        });
        write(sessionStorage, "ap_seen", "1");
        if (!res.ok) return;
        const data = await res.json();
        if (cancelled || !data?.eligible) {
          capture("offer_suppressed", {
            reason: data?.reason ?? "not_eligible",
            arm: data?.arm ?? null,
          });
          return;
        }

        setTrigger(triggerType);
        setOffer({
          tierKey: data.tierKey,
          headline: data.headline,
          subhead: data.subhead,
          listPriceCents: data.listPriceCents,
          priceCents: data.priceCents,
          amountOffCents: data.amountOffCents,
        });

        // Burn the session slot at ARM time, not close time, so a 200ms
        // dismissal still counts as the one impression for this session.
        write(sessionStorage, K.session, "1");
        write(localStorage, K.shownAt, String(Date.now()));

        capture("offer_shown", {
          tier_key: data.tierKey,
          trigger_type: triggerType,
          price_before_cents: data.listPriceCents,
          price_after_cents: data.priceCents,
          arm: data.arm,
        });
        void fetch("/api/offers/evaluate", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            event: "shown",
            tierKey: data.tierKey,
            triggerType,
            priceAfterCents: data.priceCents,
          }),
        });
      } catch {
        armed.current = false;
      }
    };

    // ── Triggers ───────────────────────────────────────────────
    // Depth beats time: the popup data shows scroll-qualified and
    // repeat-visit triggers convert far better than exit intent, and dwell
    // past ~20s converts worse than dwell at 11-15s.
    const poll = window.setInterval(() => {
      const s = engagementSnapshot();
      if (s.maxScrollDepthPct >= 40 && s.engagedSecondsOnSite >= 25) {
        void fire("scroll_dwell");
      }
    }, 2_000);

    // Desktop exit intent, as a secondary. Ignored for the first 5s because
    // a cursor commonly starts near the URL bar on a fresh tab.
    const startedAt = Date.now();
    const onLeave = (e: MouseEvent) => {
      if (Date.now() - startedAt < 5_000) return;
      if (e.relatedTarget !== null || e.clientY > 8) return;
      const s = engagementSnapshot();
      if (s.engagedSecondsOnSite < 20 && s.maxScrollDepthPct < 35) return;
      void fire("exit_intent");
    };
    const isDesktop =
      window.matchMedia?.("(pointer: fine)").matches && window.innerWidth >= 1024;
    if (isDesktop) document.addEventListener("mouseleave", onLeave);

    return () => {
      cancelled = true;
      window.clearInterval(poll);
      document.removeEventListener("mouseleave", onLeave);
    };
  }, [pathname]);

  if (!offer) return null;

  return (
    <OfferDialog
      offer={offer}
      triggerType={trigger}
      onClose={(accepted) => {
        setOffer(null);
        if (accepted) {
          capture("offer_accepted", { tier_key: offer.tierKey, trigger_type: trigger });
          void fetch("/api/offers/evaluate", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ event: "accepted", tierKey: offer.tierKey }),
          });
          window.location.href = "/pre-orders/purchase";
          return;
        }
        const n = Number(read(localStorage, K.dismissCount) || "0") + 1;
        write(localStorage, K.dismissCount, String(n));
        if (n >= 3) write(localStorage, K.optout, "1");
        capture("offer_dismissed", {
          tier_key: offer.tierKey,
          trigger_type: trigger,
          dismiss_count: n,
        });
        void fetch("/api/offers/evaluate", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ event: "dismissed", tierKey: offer.tierKey }),
        });
      }}
    />
  );
}
