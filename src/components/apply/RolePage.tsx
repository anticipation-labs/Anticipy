import Link from "next/link";
import { Reveal } from "./Reveal";
import { Photo } from "./Photo";
import { Tm } from "@/components/Tm";
import type { Role } from "@/app/apply/roles";

/**
 * The shared layout for all four role pages.
 *
 * One component rather than four hand-built pages, so the chips, section
 * rhythm and CTA cannot drift apart as the copy gets edited — and so the comp
 * chip is rendered from the role record, which is the only place equity is
 * allowed to appear.
 */

export interface RoleSection {
  heading: string;
  /** Each string is its own paragraph. */
  body: string[];
}

export interface RolePageContent {
  /** Hero shot description. Renders as an empty 16:9 slot until a photo lands. */
  heroPhoto: string;
  /** Set this and the slot becomes the photo; heroPhoto stays as the alt text. */
  heroPhotoSrc?: string;
  /** Paragraphs between the hero photo and the first section. */
  intro: string[];
  sections: RoleSection[];
  /** Optional inline 4:3 slot, dropped in after the section at this index. */
  inlinePhoto?: { afterSection: number; caption: string; src?: string };
}

export function RolePage({ role, content }: { role: Role; content: RolePageContent }) {
  const chips = [role.comp, role.place, "Start when you can"];

  return (
    <main className="section-dark" style={{ minHeight: "100dvh", padding: "0 24px" }}>
      <div style={{ maxWidth: 680, margin: "0 auto", paddingTop: 56, paddingBottom: 96 }}>
        <Reveal>
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 16 }}>
            <Link
              href="/"
              className="font-serif"
              style={{ fontSize: 19, color: "var(--gold)", textDecoration: "none", letterSpacing: "0.02em" }}
            >
              Anticipy<Tm />
            </Link>
            <Link
              href="/apply"
              style={{ fontSize: 13, color: "var(--text-on-dark-muted)", textDecoration: "none" }}
            >
              All roles
            </Link>
          </div>
        </Reveal>

        <Reveal delay={0.08}>
          <h1
            className="font-serif"
            style={{
              fontSize: "clamp(32px, 5.4vw, 58px)",
              lineHeight: 1.05,
              letterSpacing: "-0.03em",
              margin: "46px 0 0",
              color: "var(--text-on-dark)",
            }}
          >
            {role.label}
          </h1>

          <ul style={{ listStyle: "none", padding: 0, margin: "22px 0 0", display: "flex", flexWrap: "wrap", gap: 8 }}>
            {chips.map((c) => (
              <li
                key={c}
                className="rounded-pill"
                style={{
                  fontSize: 12.5,
                  padding: "6px 14px",
                  color: "var(--gold)",
                  border: "1px solid var(--dark-border)",
                  background: "var(--gold-dim)",
                  whiteSpace: "nowrap",
                }}
              >
                {c}
              </li>
            ))}
          </ul>
        </Reveal>

        <Reveal delay={0.16}>
          <Photo caption={content.heroPhoto} src={content.heroPhotoSrc} priority />
        </Reveal>

        <Reveal delay={0.22}>
          {content.intro.map((p, i) => (
            <p
              key={i}
              style={{
                fontSize: i === 0 ? "clamp(17px, 2.1vw, 21px)" : 16,
                lineHeight: i === 0 ? 1.55 : 1.75,
                color: i === 0 ? "var(--text-on-dark)" : "var(--text-on-dark-muted)",
                margin: i === 0 ? "0 0 20px" : "0 0 18px",
              }}
            >
              {p}
            </p>
          ))}
        </Reveal>

        {content.sections.map((s, i) => (
          <div key={s.heading}>
            <Reveal delay={0.26}>
              <div style={{ height: 1, background: "var(--dark-border)", margin: "42px 0 34px" }} />
              <h2
                className="font-serif"
                style={{
                  fontSize: "clamp(22px, 2.8vw, 28px)",
                  letterSpacing: "-0.02em",
                  margin: "0 0 18px",
                  color: "var(--text-on-dark)",
                }}
              >
                {s.heading}
              </h2>
              {s.body.map((p, j) => (
                <p
                  key={j}
                  style={{ fontSize: 16, lineHeight: 1.75, color: "var(--text-on-dark)", margin: "0 0 16px" }}
                >
                  {p}
                </p>
              ))}
            </Reveal>

            {content.inlinePhoto?.afterSection === i && (
              <Reveal delay={0.26}>
                <Photo ratio="4:3" caption={content.inlinePhoto.caption} src={content.inlinePhoto.src} />
              </Reveal>
            )}
          </div>
        ))}

        <Reveal delay={0.3}>
          <div style={{ height: 1, background: "var(--dark-border)", margin: "46px 0 34px" }} />
          <Link
            href={`/apply/start?role=${role.slug}`}
            className="rounded-pill"
            data-cta-id={`role_apply_${role.slug}`}
            data-cta-location="final_cta"
            data-cta-type="contact"
            data-cta-style="primary"
            style={{
              display: "inline-block",
              background: "var(--gold)",
              color: "var(--dark)",
              padding: "15px 36px",
              fontSize: 15.5,
              fontWeight: 600,
              textDecoration: "none",
            }}
          >
            Apply for this role →
          </Link>
          <p style={{ fontSize: 13, lineHeight: 1.7, color: "#5A5A5A", margin: "22px 0 0" }}>
            No cover letter, no resume required. Omar reads every application himself.
          </p>
        </Reveal>
      </div>
    </main>
  );
}
