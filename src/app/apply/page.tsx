import type { Metadata } from "next";
import Link from "next/link";
import { Tm } from "@/components/Tm";
import { HIRE_THEME } from "@/components/apply/theme";
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
 * The product is the argument for the job, so the pendant opens the page and
 * is the only dark thing on it. Roles are a table, not cards: four rows of
 * title / what it is / what it pays is the shape an engineer scans in one
 * pass, and a card grid would pad the same four facts into four boxes.
 *
 * No motion. The page renders and sits still.
 */
export default function ApplyHubPage() {
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
          <span
            style={{
              fontFamily: "var(--mono)",
              fontSize: 11,
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              color: "var(--accent-ink)",
            }}
          >
            Four open roles
          </span>
        </header>

        <div className="hub-top">
          <div>
            <h1
              className="font-serif"
              style={{
                fontSize: "clamp(40px, 7vw, 76px)",
                lineHeight: 0.98,
                letterSpacing: "-0.03em",
                color: "var(--ink)",
                margin: 0,
              }}
            >
              Come build
              <br />
              the thing.
            </h1>
            <p style={{ fontSize: "clamp(17px, 2vw, 20px)", lineHeight: 1.55, color: "var(--ink)", margin: "30px 0 0", maxWidth: "30em" }}>
              Anticipy is a pendant that listens while you talk and does the
              things you mention. No wake word, no &ldquo;hey pendant.&rdquo;
              You say it to whoever you&apos;re with, and an agent on your
              computer quietly handles it.
            </p>
            <p style={{ fontSize: 16, lineHeight: 1.7, color: "var(--ink-2)", margin: "18px 0 0", maxWidth: "30em" }}>
              I&apos;m hiring four people to build it with me. No cover letter,
              no resume. I read every application myself.
            </p>
          </div>

          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/media/hiring/pendant.jpg"
            alt="The Anticipy pendant, chain coiled around it, on black slate."
            className="hub-shot"
            width={1632}
            height={918}
          />
        </div>

        <ol className="role-table">
          {ROLES.map((r) => (
            <li key={r.key}>
              <Link
                href={`/${r.slug}`}
                className="role-row"
                data-cta-id={`hub_role_${r.slug}`}
                data-cta-location="mid_page"
                data-cta-type="contact"
                data-cta-style="secondary"
              >
                <span className="role-name font-serif">{r.label}</span>
                <span className="role-line">{r.tagline}</span>
                <span className="role-pay">{r.comp}</span>
                <span className="role-arrow" aria-hidden>
                  →
                </span>
              </Link>
            </li>
          ))}
        </ol>

        <section style={{ padding: "80px 0 110px" }}>
          <div style={{ width: 38, height: 2, background: "var(--accent)", marginBottom: 18 }} />
          <h2
            className="font-serif"
            style={{ fontSize: "clamp(24px, 3vw, 30px)", letterSpacing: "-0.02em", color: "var(--ink)", margin: "0 0 26px" }}
          >
            How hiring works
          </h2>
          <ol className="how-list">
            {HOW.map((h, i) => (
              <li key={h}>
                <span className="how-num">{String(i + 1).padStart(2, "0")}</span>
                <span>{h}</span>
              </li>
            ))}
          </ol>
        </section>
      </div>

      <style dangerouslySetInnerHTML={{ __html: `
        .hub-top { display: grid; grid-template-columns: 1fr 1fr; gap: 56px; align-items: center; padding: 72px 0 76px; }
        .hub-shot { width: 100%; height: auto; display: block; border-radius: 3px; }

        .role-table { list-style: none; margin: 0; padding: 0; border-top: 1px solid var(--rule); }
        .role-table li { border-bottom: 1px solid var(--rule); }
        .role-row {
          display: grid;
          grid-template-columns: minmax(0, 1.55fr) minmax(0, 0.95fr) auto 22px;
          gap: 28px;
          align-items: baseline;
          padding: 26px 4px;
          text-decoration: none;
          transition: background 180ms ease, padding-left 180ms ease;
        }
        .role-row:hover { background: var(--paper-2); padding-left: 14px; }
        .role-name { font-size: clamp(18px, 1.9vw, 22px); letter-spacing: -0.02em; color: var(--ink); }
        .role-line { font-size: 15.5px; line-height: 1.5; color: var(--ink-2); }
        .role-pay {
          font-family: var(--mono);
          font-size: 12.5px; color: var(--accent-ink); white-space: nowrap;
        }
        .role-arrow { font-size: 17px; color: var(--accent); justify-self: end; transition: transform 180ms ease; }
        .role-row:hover .role-arrow { transform: translateX(4px); }

        .how-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 16px; max-width: 34em; }
        .how-list li { display: flex; gap: 18px; font-size: 16.5px; line-height: 1.65; color: var(--ink); }
        .how-num {
          font-family: var(--mono);
          font-size: 11.5px; color: var(--accent-ink); padding-top: 5px; flex-shrink: 0;
        }

        @media (max-width: 900px) {
          .hub-top { grid-template-columns: 1fr; gap: 40px; padding: 48px 0 56px; }
          .role-row { grid-template-columns: 1fr auto; gap: 8px 20px; padding: 22px 4px; }
          .role-line { grid-column: 1 / -1; }
          .role-pay { grid-column: 1; }
          .role-arrow { grid-column: 2; grid-row: 1; }
        }
      ` }} />
    </main>
  );
}
