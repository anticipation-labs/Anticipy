"use client";

import { useEffect } from "react";

/**
 * Drives a real viewport height into `--app-h`, and the keyboard offset into
 * `--app-top`.
 *
 * `100dvh` is not enough on its own. The CSS spec explicitly allows a browser
 * to treat the on-screen keyboard as an overlay that does not affect
 * viewport-percentage units, and iOS Safari does exactly that — so when the
 * keyboard opens, `100dvh` stays full height, the screen no longer fits, and
 * the field the person is typing into can end up underneath the keyboard.
 *
 * `interactive-widget=resizes-content` in the viewport meta fixes this on
 * Chrome and Firefox for Android with no JavaScript at all, but WebKit has not
 * implemented it. So both are used: the meta tag handles Android, and
 * `visualViewport` is the authoritative override everywhere, including iOS.
 * They agree rather than fight.
 *
 * `--app-top` exists because WebKit lifts the visual viewport to reveal the
 * focused input; without compensating, the panel appears to slide off-screen.
 */
export function useViewport() {
  useEffect(() => {
    const root = document.documentElement;

    const apply = () => {
      const vv = window.visualViewport;
      const h = vv?.height ?? window.innerHeight;
      const top = vv?.offsetTop ?? 0;
      root.style.setProperty("--app-h", `${Math.round(h)}px`);
      root.style.setProperty("--app-top", `${Math.round(top)}px`);
    };

    apply();

    const vv = window.visualViewport;
    vv?.addEventListener("resize", apply);
    vv?.addEventListener("scroll", apply);
    window.addEventListener("orientationchange", apply);

    // The document itself never scrolls on this page — each screen is its own
    // scroll container. Restored on unmount so leaving /build does not leave
    // the rest of the site unscrollable.
    const prevBody = document.body.style.overflow;
    const prevHtml = root.style.overflow;
    document.body.style.overflow = "hidden";
    root.style.overflow = "hidden";

    return () => {
      vv?.removeEventListener("resize", apply);
      vv?.removeEventListener("scroll", apply);
      window.removeEventListener("orientationchange", apply);
      document.body.style.overflow = prevBody;
      root.style.overflow = prevHtml;
      root.style.removeProperty("--app-h");
      root.style.removeProperty("--app-top");
    };
  }, []);
}
