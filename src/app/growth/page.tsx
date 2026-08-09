import type { Metadata } from "next";
import Link from "next/link";
import { Reveal } from "../build/Reveal";
import { Tm } from "@/components/Tm";

export const metadata: Metadata = {
  title: "Founding Head of Content & Growth — Anticipy",
  description:
    "One person to own everything Anticipy publishes — scripting, filming, editing and shipping content daily, and turning the best of it into paid growth.",
  alternates: { canonical: "https://www.anticipy.ai/growth" },
  openGraph: {
    title: "Founding Head of Content & Growth",
    description:
      "Own everything Anticipy publishes. Script it, film it, edit it, ship it daily — and turn the best of it into paid growth.",
    url: "https://www.anticipy.ai/growth",
    type: "website",
  },
};

const DOING = [
  "Script, film and edit short-form content — daily, not weekly.",
  "Own the accounts end to end: what goes out, when, and what it says.",
  "Turn whatever performs into a paid ad, then run and iterate on it.",
  "Film the founder, film the product, film the factory, film the mess.",
  "Appear in content yourself when that's the version that works.",
  "Read the numbers honestly and kill what isn't landing.",
];

const RIGHT = [
  "You've personally made content that people actually watched, and you can point at it.",
  "You can hold a camera, cut a video and write a hook without waiting for a brief.",
  "You think in formats and hooks, not in campaigns and decks.",
  "You'd rather publish five things this week than plan one thing for a month.",
  "You're comfortable on camera, or comfortable getting comfortable.",
];

/**
 * The Founding Head of Content & Growth listing.
 *
 * A page, not a funnel — it scrolls normally and its only job is to make the
 * right person click Apply. The application itself lives at /apply, which is
 * the fixed-height one-question-at-a-time flow shared by every role.
 */
export default function GrowthPage() {
  return (
    <main className="section-dark" style={{ minHeight: "100dvh", padding: "0 24px" }}>
      <div style={{ maxWidth: 680, margin: "0 auto", paddingTop: 64, paddingBottom: 96 }}>
        <Reveal>
          <Link
            href="/"
            className="font-serif"
            style={{ fontSize: 19, color: "var(--gold)", textDecoration: "none", letterSpacing: "0.02em" }}
          >
            Anticipy<Tm />
          </Link>
        </Reveal>

        <Reveal delay={0.1}>
          <p
            className="tracking-wide-label"
            style={{ fontSize: 10.5, textTransform: "uppercase", color: "var(--gold)", margin: "56px 0 14px" }}
          >
            Founding team · Vancouver
          </p>
          <h1
            className="font-serif"
            style={{
              fontSize: "clamp(34px, 6vw, 64px)",
              lineHeight: 1.04,
              letterSpacing: "-0.03em",
              margin: 0,
              color: "var(--text-on-dark)",
            }}
          >
            Founding Head of Content &amp; Growth
          </h1>
        </Reveal>

        <Reveal delay={0.2}>
          <p style={{ fontSize: "clamp(17px, 2.1vw, 21px)", lineHeight: 1.55, color: "var(--text-on-dark)", margin: "26px 0 0" }}>
            One person to own everything Anticipy puts into the world.
            You&apos;ll script it, film it, edit it and publish it — and then
            turn whatever works into paid growth.
          </p>
          <p style={{ fontSize: 16, lineHeight: 1.7, color: "var(--text-on-dark-muted)", margin: "20px 0 0" }}>
            We&apos;re a tiny team building a physical product. There is no
            marketing department to hand things to, no agency, and nobody above
            you deciding what to post. That&apos;s the job, and it&apos;s the
            reason it&apos;s worth taking.
          </p>
        </Reveal>

        <Reveal delay={0.3}>
          <div style={{ height: 1, background: "var(--dark-border)", margin: "48px 0 40px" }} />
          <h2 className="font-serif" style={{ fontSize: "clamp(22px, 2.8vw, 28px)", letterSpacing: "-0.02em", margin: "0 0 20px", color: "var(--text-on-dark)" }}>
            What you&apos;d actually do
          </h2>
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 14 }}>
            {DOING.map((d) => (
              <li key={d} style={{ display: "flex", gap: 14, fontSize: 16, lineHeight: 1.6, color: "var(--text-on-dark)" }}>
                <span aria-hidden style={{ color: "var(--gold)", flexShrink: 0 }}>—</span>
                <span>{d}</span>
              </li>
            ))}
          </ul>
        </Reveal>

        <Reveal delay={0.36}>
          <h2 className="font-serif" style={{ fontSize: "clamp(22px, 2.8vw, 28px)", letterSpacing: "-0.02em", margin: "48px 0 20px", color: "var(--text-on-dark)" }}>
            You&apos;re probably right for this if
          </h2>
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 14 }}>
            {RIGHT.map((d) => (
              <li key={d} style={{ display: "flex", gap: 14, fontSize: 16, lineHeight: 1.6, color: "var(--text-on-dark)" }}>
                <span aria-hidden style={{ color: "var(--gold)", flexShrink: 0 }}>—</span>
                <span>{d}</span>
              </li>
            ))}
          </ul>
          <p style={{ fontSize: 15, lineHeight: 1.7, color: "var(--text-on-dark-muted)", margin: "28px 0 0" }}>
            We don&apos;t care about school or titles. We care about what
            you&apos;ve made and what was actually yours. The role involves
            filming in Vancouver and travelling for launches and important
            shoots.
          </p>
        </Reveal>

        <Reveal delay={0.42}>
          <div style={{ height: 1, background: "var(--dark-border)", margin: "48px 0 36px" }} />
          <h2 className="font-serif" style={{ fontSize: "clamp(24px, 3vw, 32px)", letterSpacing: "-0.02em", margin: "0 0 14px", color: "var(--text-on-dark)" }}>
            The application is four questions.
          </h2>
          <p style={{ fontSize: 16, lineHeight: 1.7, color: "var(--text-on-dark-muted)", margin: "0 0 30px" }}>
            No cover letter. If it lands, you meet the founder directly — no
            recruiter, no screening round.
          </p>
          <Link
            href="/apply?role=growth"
            className="rounded-pill"
            data-cta-id="growth_apply"
            data-cta-location="final_cta"
            data-cta-type="contact"
            data-cta-style="primary"
            style={{
              display: "inline-block",
              background: "var(--gold)",
              color: "var(--dark)",
              padding: "14px 34px",
              fontSize: 15.5,
              fontWeight: 600,
              textDecoration: "none",
            }}
          >
            Apply for this role
          </Link>
          <p style={{ fontSize: 13, lineHeight: 1.7, color: "#5A5A5A", margin: "26px 0 0" }}>
            Also hiring engineers —{" "}
            <Link href="/apply" style={{ color: "var(--text-on-dark-muted)" }}>
              see all open roles
            </Link>
            .
          </p>
        </Reveal>
      </div>
    </main>
  );
}
