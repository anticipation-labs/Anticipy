"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import {
  capture,
  beginPageview,
  startEngagementTracking,
  recordScrollDepth,
  recordSectionViewed,
  claimMilestone,
  engagementSnapshot,
  type CtaLocation,
  type CtaType,
} from "@/lib/analytics";

/**
 * Mounts the behavioural instrumentation that PostHog's autocapture cannot
 * provide: section visibility, scroll and dwell milestones, and a single
 * delegated CTA handler.
 *
 * Performance posture, because this runs on every page:
 *  - Every listener is `{ passive: true }`; none may delay scrolling or INP.
 *  - Scroll work is coalesced into one rAF frame, so a fast scroll does a
 *    handful of layout reads rather than one per event.
 *  - Milestones fire at most once per pageview, deduped through
 *    `claimMilestone`, which is what keeps a fully-engaged session at roughly
 *    25-40 events instead of hundreds.
 */

const SCROLL_MILESTONES = [25, 50, 75, 90] as const;
const DWELL_MILESTONES_S = [15, 30, 60, 120, 240] as const;

export function AnalyticsProvider() {
  const pathname = usePathname();

  // Engagement clock: mounted once for the life of the tab.
  useEffect(() => startEngagementTracking(), []);

  // Per-pageview counters reset on client navigation.
  useEffect(() => {
    beginPageview();
  }, [pathname]);

  // ─── Scroll depth ──────────────────────────────────────────────
  useEffect(() => {
    let frame = 0;

    const measure = () => {
      frame = 0;
      const doc = document.documentElement;
      const scrollable = doc.scrollHeight - window.innerHeight;
      // A page shorter than the viewport is 100% seen by definition;
      // dividing by zero here would otherwise produce Infinity.
      const pct =
        scrollable <= 0
          ? 100
          : Math.round(((window.scrollY || doc.scrollTop) / scrollable) * 100);

      recordScrollDepth(pct);

      for (const m of SCROLL_MILESTONES) {
        if (pct >= m && claimMilestone(`scroll:${m}`)) {
          capture("page_scroll_depth_reached", {
            depth_pct: m,
            path: window.location.pathname,
          });
        }
      }
    };

    const onScroll = () => {
      if (frame) return;
      frame = window.requestAnimationFrame(measure);
    };

    window.addEventListener("scroll", onScroll, { passive: true });
    measure();
    return () => {
      window.removeEventListener("scroll", onScroll);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [pathname]);

  // ─── Dwell milestones ──────────────────────────────────────────
  // Driven off engaged seconds, not wall clock, so a backgrounded tab does
  // not accumulate milestones it never earned.
  useEffect(() => {
    const timer = window.setInterval(() => {
      const { engagedSecondsOnPage } = engagementSnapshot();
      for (const s of DWELL_MILESTONES_S) {
        if (engagedSecondsOnPage >= s && claimMilestone(`dwell:${s}`)) {
          capture("page_dwell_milestone_reached", {
            seconds: s,
            path: window.location.pathname,
          });
        }
      }
    }, 5_000);
    return () => window.clearInterval(timer);
  }, [pathname]);

  // ─── Section visibility ────────────────────────────────────────
  // Any element carrying data-section-id is observed. A section counts as
  // viewed at >=50% visible for >=1s, which filters out sections that merely
  // flew past during a fast scroll to the footer.
  useEffect(() => {
    const nodes = document.querySelectorAll<HTMLElement>("[data-section-id]");
    if (!nodes.length) return;

    const pending = new Map<Element, number>();

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const el = entry.target as HTMLElement;
          const id = el.dataset.sectionId;
          if (!id) continue;

          if (entry.isIntersecting && entry.intersectionRatio >= 0.5) {
            if (pending.has(el)) continue;
            const t = window.setTimeout(() => {
              pending.delete(el);
              const isFirst = recordSectionViewed(id);
              if (!claimMilestone(`section:${id}`)) return;
              capture("section_viewed", {
                section_id: id,
                section_index: Number(el.dataset.sectionIndex ?? -1),
                is_first_view: isFirst,
                viewport_coverage_pct: Math.round(entry.intersectionRatio * 100),
              });
            }, 1000);
            pending.set(el, t);
          } else {
            const t = pending.get(el);
            if (t) {
              window.clearTimeout(t);
              pending.delete(el);
            }
          }
        }
      },
      { threshold: [0, 0.5, 1] }
    );

    nodes.forEach((n) => observer.observe(n));
    return () => {
      pending.forEach((t) => window.clearTimeout(t));
      observer.disconnect();
    };
  }, [pathname]);

  // ─── Delegated CTA + outbound clicks ───────────────────────────
  // One listener for the whole document. Adding a new CTA anywhere on the
  // site requires only data attributes on the markup, never a code change
  // here — which is what stops CTA instrumentation from rotting.
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement | null;
      if (!target) return;

      const cta = target.closest<HTMLElement>("[data-cta-id]");
      if (cta) {
        const { maxScrollDepthPct, engagedSecondsOnSite } = engagementSnapshot();
        capture("cta_clicked", {
          cta_id: cta.dataset.ctaId,
          cta_location: cta.dataset.ctaLocation as CtaLocation | undefined,
          cta_type: cta.dataset.ctaType as CtaType | undefined,
          cta_style: cta.dataset.ctaStyle,
          cta_label: (cta.dataset.ctaLabel ?? cta.textContent ?? "").trim().slice(0, 120),
          destination_url: cta.getAttribute("href") ?? null,
          scroll_depth_at_click_pct: maxScrollDepthPct,
          engaged_seconds_at_click: engagedSecondsOnSite,
        });
        return;
      }

      const link = target.closest<HTMLAnchorElement>("a[href]");
      if (!link) return;
      const href = link.getAttribute("href") || "";
      if (!/^https?:/i.test(href)) return;
      try {
        const url = new URL(href);
        if (url.host === window.location.host) return;
        capture("outbound_link_clicked", {
          destination_host: url.host,
          destination_url: url.href.slice(0, 300),
        });
      } catch {
        // Malformed href — nothing useful to record.
      }
    };

    document.addEventListener("click", onClick, { passive: true, capture: true });
    return () => document.removeEventListener("click", onClick, { capture: true });
  }, [pathname]);

  return null;
}
