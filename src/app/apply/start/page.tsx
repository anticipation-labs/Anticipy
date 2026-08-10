import type { Metadata, Viewport } from "next";
import { ApplyForm } from "./ApplyForm";
import { HIRE_THEME } from "@/components/apply/theme";

export const metadata: Metadata = {
  title: "Apply — Anticipy",
  description: "A few screens, no cover letter, no resume.",
  alternates: { canonical: "https://www.anticipy.ai/apply/start" },
  // The listings hub at /apply is the page worth indexing; this is the form.
  robots: { index: false, follow: true },
};

// Next 14 ignores a `viewport` key inside the metadata export — it must be its
// own export or it is silently dropped.
// `interactive-widget=resizes-content` shrinks the layout viewport when the
// on-screen keyboard opens, so a fixed-height screen keeps fitting. It works
// on Chrome and Firefox for Android with no JavaScript. WebKit has not
// implemented it, which is why useViewport() also drives the height from
// visualViewport — the two agree rather than conflict.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  interactiveWidget: "resizes-content",
};

/**
 * The application wizard.
 *
 * One question at a time, each screen sized to the viewport, the document
 * itself never scrolls. `?role=` skips the intro and role screens and lands
 * straight on name/email — one click from reading the job to typing your name
 * — with a "change role" link for anyone who followed the wrong link.
 */
export default function ApplyStartPage() {
  return (
    <main style={HIRE_THEME}>
      <ApplyForm />
    </main>
  );
}
