import Link from "next/link";
import { HIRE_THEME } from "./theme";
import { Tm } from "@/components/Tm";
import { ApplyButton, APPLY_BUTTON_CSS } from "./ApplyButton";
import type { Role } from "@/app/apply/roles";

/**
 * The shared layout for all four role pages.
 *
 * Set as a datasheet rather than a centred article: a fixed spec rail on the
 * left (pay, place, start — set in mono, the way a component's parameters are
 * listed) against a single column of prose on the right. The people these
 * pages are written for read datasheets all day; a spec rail is a form they
 * already trust, and it puts the three facts that decide whether to keep
 * reading where the eye lands first instead of three paragraphs down.
 *
 * Three voices, each doing one job: serif for headings, sans for prose, mono
 * for anything that is data. No motion — these pages render and sit still.
 */

export interface RoleSection {
  heading: string;
  /** Each string is its own paragraph. */
  body: string[];
}

export interface RolePageContent {
  /** The one-line thesis, set larger than the rest. */
  lede: string;
  /** Paragraphs after the lede. */
  intro: string[];
  sections: RoleSection[];
}

const railLabel: React.CSSProperties = {
  fontFamily: "var(--mono)",
  fontSize: 10,
  letterSpacing: "0.14em",
  textTransform: "uppercase",
  color: "var(--accent-ink)",
  display: "block",
  marginBottom: 6,
};

const railValue: React.CSSProperties = {
  fontFamily: "var(--mono)",
  fontSize: 13,
  lineHeight: 1.5,
  color: "var(--ink)",
};

export function RolePage({ role, content }: { role: Role; content: RolePageContent }) {
  const spec: [string, string][] = [
    ["Location", role.place],
    ["Start", "When you can"],
  ];

  return (
    <main style={{ ...HIRE_THEME, minHeight: "100dvh" }}>
      <div style={{ maxWidth: 1000, margin: "0 auto", padding: "0 28px" }}>
        <header
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            gap: 16,
            padding: "26px 0",
            borderBottom: "1px solid var(--rule)",
          }}
        >
          <Link
            href="/"
            className="font-serif"
            style={{ fontSize: 19, color: "var(--ink)", textDecoration: "none", letterSpacing: "0.01em" }}
          >
            Anticipy<Tm />
          </Link>
          <Link
            href="/apply"
            className="rp-mono"
            style={{ fontSize: 11, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--accent-ink)", textDecoration: "none" }}
          >
            All roles
          </Link>
        </header>

        <div className="rp-grid">
          <div className="rp-intro">
            <h1
              className="font-serif"
              style={{
                fontSize: "clamp(36px, 5.6vw, 62px)",
                lineHeight: 1.02,
                letterSpacing: "-0.025em",
                color: "var(--ink)",
                margin: 0,
              }}
            >
              {role.label}
            </h1>

            <p
              style={{
                fontSize: "clamp(19px, 2.3vw, 24px)",
                lineHeight: 1.45,
                color: "var(--ink)",
                margin: "28px 0 0",
                maxWidth: "26em",
              }}
            >
              {content.lede}
            </p>

            {content.intro.map((p, i) => (
              <p
                key={i}
                style={{ fontSize: 16.5, lineHeight: 1.72, color: "var(--ink)", margin: "20px 0 0", maxWidth: "34em" }}
              >
                {p}
              </p>
            ))}
          </div>

          {/* Spec rail. Sticky on desktop so the pay band stays in view while
              somebody reads three screens of prose deciding whether to apply. */}
          <aside className="rp-rail">
            <div className="rp-rail-inner">
              <div className="rp-rail-cta">
                <ApplyButton
                  href={`/apply/start?role=${role.slug}`}
                  label="Apply"
                  size="md"
                  block
                  id={`role_rail_apply_${role.slug}`}
                  location="sidebar"
                />
              </div>
              {spec.map(([label, value]) => (
                <div key={label} className="rp-spec">
                  <span style={railLabel}>{label}</span>
                  <span style={railValue}>{value}</span>
                </div>
              ))}
            </div>
          </aside>

          <article className="rp-body">
            {content.sections.map((s) => (
              <section key={s.heading} style={{ marginTop: 52 }}>
                <div style={{ width: 38, height: 2, background: "var(--accent)", marginBottom: 18 }} />
                <h2
                  className="font-serif"
                  style={{
                    fontSize: "clamp(22px, 2.6vw, 27px)",
                    lineHeight: 1.2,
                    letterSpacing: "-0.015em",
                    color: "var(--ink)",
                    margin: "0 0 16px",
                  }}
                >
                  {s.heading}
                </h2>
                {s.body.map((p, j) => (
                  <p
                    key={j}
                    style={{ fontSize: 16.5, lineHeight: 1.72, color: "var(--ink)", margin: "0 0 14px", maxWidth: "34em" }}
                  >
                    {p}
                  </p>
                ))}
              </section>
            ))}

            <div style={{ marginTop: 60, paddingTop: 36, borderTop: "1px solid var(--rule)" }}>
              <ApplyButton
                href={`/apply/start?role=${role.slug}`}
                label="Apply for this role"
                id={`role_apply_${role.slug}`}
              />
              <p style={{ fontSize: 13.5, lineHeight: 1.7, color: "var(--ink-2)", margin: "20px 0 0" }}>
                No cover letter, no resume required. Omar reads every application himself.
              </p>
            </div>
          </article>
        </div>
      </div>

      <div className="rp-sticky">
        <span className="rp-sticky-pay">{role.label}</span>
        <ApplyButton
          href={`/apply/start?role=${role.slug}`}
          label="Apply"
          size="md"
          id={`role_sticky_apply_${role.slug}`}
          location="sticky_bar"
        />
      </div>

      <style dangerouslySetInnerHTML={{ __html: `
        ${APPLY_BUTTON_CSS}

        .rp-rail-cta { margin-bottom: 4px; }
        /* The fixed bar is mobile-only; on desktop the rail CTA is always in
           view already and a second one would be noise. */
        .rp-sticky { display: none; }

        .rp-grid {
          display: grid;
          grid-template-columns: 176px 1fr;
          grid-template-areas: 'rail intro' 'rail body';
          column-gap: 64px;
          padding: 64px 0 110px;
          align-items: start;
        }
        /* The grid sets align-items:start, which collapses this cell to its
           own height — and a sticky child needs a taller containing block to
           have anywhere to travel. Stretching it across both rows is what
           actually makes the Apply button follow the read. */
        .rp-rail { grid-area: rail; align-self: stretch; }
        .rp-intro { grid-area: intro; }
        .rp-body { grid-area: body; }
        .rp-rail-inner { position: sticky; top: 48px; display: grid; gap: 26px; }
        .rp-spec { border-top: 1px solid var(--rule); padding-top: 12px; }
        .rp-cta { transition: opacity 180ms ease; }
        .rp-cta:hover { opacity: 0.82; }

        /* Stacked, the pay band belongs directly under the lede — it is the
           first thing anyone checks, and at the foot of the page it would sit
           below four sections of prose. */
        @media (max-width: 860px) {
          .rp-grid {
            grid-template-columns: 1fr;
            grid-template-areas: 'intro' 'rail' 'body';
            padding: 40px 0 116px;
          }
          .rp-rail { margin: 34px 0 8px; }
          .rp-rail-inner { position: static; grid-template-columns: repeat(3, 1fr); gap: 16px; }
          .rp-rail-cta { display: none; }

          .rp-sticky {
            display: flex;
            position: fixed;
            left: 0; right: 0; bottom: 0;
            z-index: 30;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            padding: 12px 20px calc(12px + env(safe-area-inset-bottom));
            background: var(--paper);
            border-top: 1px solid var(--rule);
            box-shadow: 0 -8px 24px rgba(23, 21, 18, 0.06);
          }
          .rp-sticky-pay {
            font-family: var(--mono); font-size: 12px;
            color: var(--accent-ink); line-height: 1.35;
          }
        }
        @media (max-width: 460px) {
          .rp-rail-inner { grid-template-columns: 1fr; gap: 0; }
          .rp-spec { padding-top: 10px; margin-top: 10px; }
        }
      ` }} />
    </main>
  );
}
