"use client";

import { useEffect, useState } from "react";

const SCHEDULE_URL =
  "https://calendar.google.com/calendar/appointments/schedules/AcZssZ30VqtLax0yLxRLrPymbks4JOmA39jo2X42gUw6FC_9O5BgpgkH5ch_fHDgSPp7YPHcVNg85McP?gv=true";

const FALLBACK_URL = "https://calendar.app.google/s97HJuvexjobnwgu9";

/**
 * Omar's appointment schedule, embedded in place.
 *
 * WHY THE PLAIN IFRAME AND NOT GOOGLE'S SCHEDULING-BUTTON SCRIPT.
 * The button script was inspected rather than assumed. It does not open a
 * native popup — it injects a fixed overlay with a hardcoded `padding: 72px`
 * and NO media queries, which leaves a ~246px-wide booking frame on a 390px
 * phone. It also pulls two render-blocking stylesheets from
 * fonts.googleapis.com, and ships no Escape handler, no role="dialog" and no
 * focus trap. On a page whose whole point is that someone books, that script
 * is the version most likely to lose the booking.
 *
 * The booking page itself carries no X-Frame-Options and no CSP
 * frame-ancestors, so it embeds cross-origin, and its slot RPCs authenticate
 * with a referrer-locked API key rather than cookies — which is why Safari's
 * tracking prevention does not break it. A signed-out or cookie-blocked
 * visitor simply types their name and email instead of having it prefilled.
 *
 * Mounted on idle rather than immediately: the payload is ~285 KB and this
 * screen should paint the confirmation first. No click-to-load facade
 * though — on a post-submission screen, every extra click costs bookings,
 * and Core Web Vitals barely apply after a form POST.
 *
 * The Google UI is permanently light (its dark styles exist only under
 * forced-colors), so it is framed as a white card rather than fought.
 */
export function CalendarEmbed() {
  const [mounted, setMounted] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const start = () => setMounted(true);
    type IdleWindow = Window & {
      requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number;
    };
    const w = window as IdleWindow;
    if (typeof w.requestIdleCallback === "function") {
      const id = w.requestIdleCallback(start, { timeout: 1200 });
      return () => window.cancelIdleCallback?.(id);
    }
    const t = window.setTimeout(start, 400);
    return () => window.clearTimeout(t);
  }, []);

  // If the frame has not reported load in a few seconds, assume something
  // upstream is blocking it and surface a link rather than a blank rectangle.
  useEffect(() => {
    if (!mounted) return;
    const t = window.setTimeout(() => {
      setFailed((f) => f || !document.querySelector<HTMLIFrameElement>("[data-cal-frame]")?.dataset.loaded);
    }, 6000);
    return () => window.clearTimeout(t);
  }, [mounted]);

  return (
    <div style={{ marginTop: 34 }}>
      <div
        style={{
          background: "#FFFFFF",
          borderRadius: 16,
          overflow: "hidden",
          border: "1px solid var(--rule)",
          minHeight: 560,
        }}
      >
        {mounted && !failed ? (
          <iframe
            data-cal-frame
            src={SCHEDULE_URL}
            title="Book a call with Omar"
            onLoad={(e) => {
              e.currentTarget.dataset.loaded = "true";
            }}
            style={{
              border: 0,
              width: "100%",
              height: 620,
              display: "block",
            }}
          />
        ) : (
          <div
            style={{
              minHeight: 560,
              display: "grid",
              placeItems: "center",
              padding: 28,
              textAlign: "center",
            }}
          >
            {failed ? (
              <a
                href={FALLBACK_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-pill"
                style={{
                  background: "var(--accent)",
                  color: "var(--paper)",
                  padding: "14px 32px",
                  fontSize: 15,
                  fontWeight: 600,
                  textDecoration: "none",
                }}
              >
                Open Omar&apos;s calendar
              </a>
            ) : (
              <span style={{ color: "var(--ink-2)", fontSize: 14 }}>
                Loading available times…
              </span>
            )}
          </div>
        )}
      </div>

      <p
        style={{
          fontSize: 12,
          color: "var(--ink-2)",
          margin: "14px 0 0",
        }}
      >
        Trouble booking here?{" "}
        <a
          href={FALLBACK_URL}
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: "var(--ink-2)", textDecoration: "underline" }}
        >
          Open the calendar in a new tab
        </a>
        .
      </p>
    </div>
  );
}
