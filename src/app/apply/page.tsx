import type { Metadata } from "next";
import Link from "next/link";
import { Reveal } from "@/components/apply/Reveal";
import { Photo } from "@/components/apply/Photo";
import { Tm } from "@/components/Tm";
import { ROLES } from "./roles";

export const metadata: Metadata = {
  title: "Come build the thing. — Anticipy",
  description:
    "Four open roles at Anticipy: content and growth, software, hardware, and the layer in between. No cover letter, no resume.",
  alternates: { canonical: "https://www.anticipy.ai/apply" },
  openGraph: {
    title: "Come build the thing. — Anticipy",
    description: "Four roles. No cover letter, no resume. Omar reads every application.",
    url: "https://www.anticipy.ai/apply",
    type: "website",
  },
};

const HOW = [
  "You apply. I read it — not a filter, not a recruiter.",
  "One 30-minute call with me.",
  "A fast, clear yes or no. If it's a no, I'll tell you why.",
];

/**
 * The listings hub.
 *
 * A normal scrolling page — the fixed-height, one-question-at-a-time funnel
 * starts at /apply/start. Cards link to the role pages rather than straight
 * into the wizard, because the job description is what makes somebody decide
 * to apply, and skipping it costs more than the extra click.
 */
export default function ApplyHubPage() {
  return (
    <main className="section-dark" style={{ minHeight: "100dvh", padding: "0 24px" }}>
      <div style={{ maxWidth: 680, margin: "0 auto", paddingTop: 56, paddingBottom: 96 }}>
        <Reveal>
          <Link
            href="/"
            className="font-serif"
            style={{ fontSize: 19, color: "var(--gold)", textDecoration: "none", letterSpacing: "0.02em" }}
          >
            Anticipy<Tm />
          </Link>
        </Reveal>

        <Reveal delay={0.08}>
          <h1
            className="font-serif"
            style={{
              fontSize: "clamp(34px, 6vw, 62px)",
              lineHeight: 1.04,
              letterSpacing: "-0.03em",
              margin: "46px 0 0",
              color: "var(--text-on-dark)",
            }}
          >
            Come build the thing.
          </h1>
        </Reveal>

        <Reveal delay={0.16}>
          <p style={{ fontSize: "clamp(17px, 2.1vw, 21px)", lineHeight: 1.55, color: "var(--text-on-dark)", margin: "26px 0 18px" }}>
            Anticipy is a pendant that listens while you talk and does the
            things you mention. No wake word, no &ldquo;hey pendant.&rdquo; You
            say it to whoever you&apos;re with, and an agent on your computer
            quietly handles it.
          </p>
          <p style={{ fontSize: 16, lineHeight: 1.75, color: "var(--text-on-dark-muted)", margin: 0 }}>
            I&apos;m hiring four people to build it with me. No cover letter, no
            resume. I read every application myself.
          </p>
        </Reveal>

        <Reveal delay={0.22}>
          <Photo
            priority
            caption="Hero, 16:9 — the pendant on a person, close crop at collarbone height, plain sweater or tee, daylight from a window on one side, no logos."
          />
        </Reveal>

        <div style={{ display: "grid", gap: 12 }}>
          {ROLES.map((r, i) => (
            <Reveal key={r.key} delay={0.26 + i * 0.05}>
              <Link
                href={`/${r.slug}`}
                data-cta-id={`hub_role_${r.slug}`}
                data-cta-location="mid_page"
                data-cta-type="contact"
                data-cta-style="secondary"
                className="apply-card"
                style={{
                  display: "block",
                  textDecoration: "none",
                  padding: "22px 24px",
                  borderRadius: 12,
                  border: "1px solid var(--dark-border)",
                  background: "var(--dark-elevated)",
                }}
              >
                <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 14 }}>
                  <h2
                    className="font-serif"
                    style={{ fontSize: "clamp(19px, 2.4vw, 23px)", letterSpacing: "-0.02em", margin: 0, color: "var(--text-on-dark)" }}
                  >
                    {r.label}
                  </h2>
                  <span aria-hidden style={{ color: "var(--gold)", fontSize: 17, flexShrink: 0 }}>
                    →
                  </span>
                </div>
                <p style={{ fontSize: 15.5, lineHeight: 1.6, color: "var(--text-on-dark-muted)", margin: "8px 0 14px" }}>
                  {r.tagline}
                </p>
                <span
                  className="rounded-pill"
                  style={{
                    display: "inline-block",
                    fontSize: 12.5,
                    padding: "5px 13px",
                    color: "var(--gold)",
                    border: "1px solid var(--dark-border)",
                    background: "var(--gold-dim)",
                  }}
                >
                  {r.comp}
                </span>
              </Link>
            </Reveal>
          ))}
        </div>

        <Reveal delay={0.3}>
          <div style={{ height: 1, background: "var(--dark-border)", margin: "48px 0 34px" }} />
          <h2
            className="font-serif"
            style={{ fontSize: "clamp(22px, 2.8vw, 28px)", letterSpacing: "-0.02em", margin: "0 0 22px", color: "var(--text-on-dark)" }}
          >
            How hiring works
          </h2>
          <ol style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 16, counterReset: "step" }}>
            {HOW.map((h, i) => (
              <li key={h} style={{ display: "flex", gap: 16, fontSize: 16, lineHeight: 1.65, color: "var(--text-on-dark)" }}>
                <span
                  aria-hidden
                  style={{ color: "var(--gold)", flexShrink: 0, fontVariantNumeric: "tabular-nums", opacity: 0.75 }}
                >
                  {i + 1}.
                </span>
                <span>{h}</span>
              </li>
            ))}
          </ol>
        </Reveal>
      </div>

      <style>{`
        .apply-card { transition: border-color 220ms ease, background 220ms ease; }
        .apply-card:hover { border-color: var(--gold); background: var(--dark-hover); }
      `}</style>
    </main>
  );
}
