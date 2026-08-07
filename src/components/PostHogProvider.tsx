"use client";

import { useEffect } from "react";
import posthog from "posthog-js";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense } from "react";

const POSTHOG_KEY = process.env.NEXT_PUBLIC_POSTHOG_KEY;
// Defaults to the first-party proxy path. Kept overridable by env so a
// preview deploy or a local run can point straight at PostHog if the rewrite
// is ever suspected of being the problem.
const POSTHOG_HOST = process.env.NEXT_PUBLIC_POSTHOG_HOST || "/ingest";

function PostHogInit() {
  useEffect(() => {
    if (!POSTHOG_KEY) return;
    if (typeof window === "undefined") return;
    if ((posthog as unknown as { __loaded?: boolean }).__loaded) return;

    posthog.init(POSTHOG_KEY, {
      // First-party path — see the /ingest rewrite in next.config.mjs.
      api_host: POSTHOG_HOST,
      ui_host: "https://us.posthog.com",
      autocapture: true,
      capture_pageview: false,
      capture_pageleave: true,
      // $pageleave carries $prev_pageview_max_scroll_percentage and
      // $prev_pageview_duration, which is the reporting layer for scroll and
      // dwell. The custom milestone events in AnalyticsProvider exist only to
      // serve funnels and real-time offer triggers, not to duplicate this.

      // Clickmaps and scrollmaps. Billed with ordinary events rather than
      // separately, so there is no cost argument against enabling them.
      enable_heatmaps: true,

      // Frustration signals. Repeated deliberate clicks on the FAQ accordion
      // and the video scrubber are not rage, so those carry .ph-no-rageclick.
      rageclick: true,

      // Field data for Core Web Vitals, judged at p90 rather than mean.
      capture_performance: { web_vitals: true },

      session_recording: {
        maskAllInputs: true,
        maskInputOptions: {
          password: true,
          // Was false, which meant email addresses were legible in replays.
          // The address is already captured deliberately on submit as a person
          // property; having it additionally sitting in replay video is pure
          // liability with no analytical gain.
          email: true,
        },
      },
      // No person profile exists until identify() fires on form SUBMIT, so
      // anonymous browsing stays anonymous and is billed as such. When
      // identify() does fire, PostHog merges the anonymous person into the
      // identified one and repoints all prior events at the survivor — which
      // is what makes the full pre-signup history resolve retroactively.
      person_profiles: "identified_only",
      loaded: (ph) => {
        if (process.env.NODE_ENV === "development") {
          ph.debug();
        }
      },
    });
  }, []);

  return null;
}

function PostHogPageView() {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  useEffect(() => {
    if (!POSTHOG_KEY) return;
    if (!pathname) return;
    let url = window.origin + pathname;
    const q = searchParams?.toString();
    if (q) url += "?" + q;
    posthog.capture("$pageview", { $current_url: url });
  }, [pathname, searchParams]);

  return null;
}

export function PostHogProvider() {
  return (
    <>
      <PostHogInit />
      <Suspense fallback={null}>
        <PostHogPageView />
      </Suspense>
    </>
  );
}
// bust build cache 2026-05-29T01:07:06Z
