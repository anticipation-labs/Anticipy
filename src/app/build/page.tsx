import type { Metadata } from "next";
import Link from "next/link";
import { BuildForm } from "./BuildForm";
import { Tm } from "@/components/Tm";
import { Reveal } from "./Reveal";

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
};

/**
 * The application page.
 *
 * Deliberately not a careers page: no team grid, no benefits list, no
 * gradient, no stock photography, no HR voice. The whole surface is one
 * question and one form, because the page is addressed to a person who has
 * built things and will judge it on whether it wastes their time.
 *
 * Chrome is reduced to a wordmark and a single footer line. The site's full
 * nav would give this page five ways to leave it.
 */
export default function BuildPage() {
  return (
    <main
      className="section-dark"
      style={{ minHeight: "100vh", paddingBottom: 120 }}
    >
      <div
        style={{
          maxWidth: 680,
          margin: "0 auto",
          padding: "0 24px",
        }}
      >
        {/* Wordmark — the only navigation. */}
        <div style={{ paddingTop: 40, paddingBottom: 72 }}>
          <Link
            href="/"
            className="font-serif"
            style={{
              fontSize: 21,
              color: "var(--gold)",
              textDecoration: "none",
              letterSpacing: "0.02em",
            }}
          >
            Anticipy
            <Tm />
          </Link>
        </div>

        <Reveal>
          <h1
            className="font-serif"
            style={{
              fontSize: "clamp(38px, 6.4vw, 68px)",
              lineHeight: 1.06,
              letterSpacing: "-0.03em",
              margin: 0,
              color: "var(--text-on-dark)",
            }}
          >
            Built something that shouldn&apos;t have worked?
          </h1>
        </Reveal>

        <Reveal delay={0.12}>
          <p
            style={{
              fontSize: "clamp(17px, 2.2vw, 21px)",
              lineHeight: 1.6,
              color: "var(--text-on-dark)",
              margin: "30px 0 0",
              maxWidth: 600,
            }}
          >
            Anticipy is looking for one hardware + software builder to own a
            tiny connected product from board to factory.
          </p>
        </Reveal>

        <Reveal delay={0.22}>
          <p
            style={{
              fontSize: 16,
              lineHeight: 1.75,
              color: "var(--text-on-dark-muted)",
              margin: "28px 0 0",
              maxWidth: 600,
            }}
          >
            You&apos;re probably right for this if you&apos;ve personally
            designed custom electronics, written embedded firmware, connected
            hardware to phones, and fixed the ugly problems that appear when a
            prototype becomes a manufactured product. We don&apos;t care about
            school or titles. We care about what you built and what was
            actually yours.
          </p>
        </Reveal>

        <Reveal delay={0.32}>
          <div style={{ marginTop: 64 }}>
            <BuildForm />
          </div>
        </Reveal>

        <Reveal delay={0.1}>
          <div
            style={{
              marginTop: 72,
              paddingTop: 26,
              borderTop: "1px solid var(--dark-border)",
            }}
          >
            <p
              style={{
                fontSize: 13,
                lineHeight: 1.7,
                color: "var(--text-on-dark-muted)",
                margin: 0,
              }}
            >
              Initial paid engagement: US$3,000–$4,000/month, depending on scope
              and availability. A longer-term founding-team position may include
              equity.
            </p>
            <p
              style={{
                fontSize: 12,
                color: "#5A5A5A",
                margin: "26px 0 0",
              }}
            >
              &copy; 2026 Anticipation Labs
              <Tm />. Résumés are stored privately and never published.
            </p>
          </div>
        </Reveal>
      </div>
    </main>
  );
}
