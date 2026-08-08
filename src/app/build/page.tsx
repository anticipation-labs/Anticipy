import type { Metadata } from "next";
import { BuildForm } from "./BuildForm";

export const metadata: Metadata = {
  title: "Built something that shouldn't have worked? — Anticipy",
  description:
    "Anticipy is looking for one hardware + software builder to own a tiny connected product from board to factory.",
  alternates: { canonical: "https://www.anticipy.ai/build" },
  openGraph: {
    title: "Built something that shouldn't have worked?",
    description:
      "One hardware + software builder to own a tiny connected product from board to factory.",
    url: "https://www.anticipy.ai/build",
    type: "website",
  },
  // `interactive-widget=resizes-content` shrinks the layout viewport when the
  // on-screen keyboard opens, so a fixed-height screen keeps fitting. It works
  // on Chrome and Firefox for Android with no JavaScript. WebKit has not
  // implemented it, which is why useViewport() also drives the height from
  // visualViewport — the two agree rather than conflict.
  viewport: {
    width: "device-width",
    initialScale: 1,
    interactiveWidget: "resizes-content",
  },
};

/**
 * The application page.
 *
 * One screen at a time, each sized to the viewport, and the document itself
 * never scrolls — the intro, every question and the confirmation are all
 * panels rather than a long page. No nav, no footer, no team grid, no
 * benefits list. The whole surface is one question and a way to answer it.
 */
export default function BuildPage() {
  return (
    <main className="section-dark">
      <BuildForm />
    </main>
  );
}
