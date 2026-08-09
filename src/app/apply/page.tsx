import type { Metadata, Viewport } from "next";
import { ApplyForm } from "./ApplyForm";

export const metadata: Metadata = {
  title: "Apply — Anticipy",
  description:
    "Four open roles at Anticipy: Founding Head of Content & Growth, Senior Software Engineer, Senior Hardware Engineer, and Senior Hardware & Software Engineer.",
  alternates: { canonical: "https://www.anticipy.ai/apply" },
  openGraph: {
    title: "Come build the thing. — Anticipy",
    description:
      "Four open roles. One application, a few screens, no cover letter.",
    url: "https://www.anticipy.ai/apply",
    type: "website",
  },
};

// Next 14 ignores a `viewport` key inside the metadata export — it must be its
// own export or it is silently dropped, which is what was happening here.
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
 * The shared application page for every open role.
 *
 * Same funnel as /build — one question at a time, each screen sized to the
 * viewport, the document itself never scrolls. `?role=` preselects, but the
 * role screen is always shown so somebody arriving cold can choose, and
 * somebody who followed the wrong link can correct it.
 */
export default function ApplyPage() {
  return (
    <main className="section-dark">
      <ApplyForm />
    </main>
  );
}
