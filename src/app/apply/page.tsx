import type { Metadata } from "next";
import Link from "next/link";
import { Tm } from "@/components/Tm";
import { HIRE_THEME } from "@/components/apply/theme";
import { ApplyButton, APPLY_BUTTON_CSS } from "@/components/apply/ApplyButton";
import { ROLES } from "./roles";
import { PAY } from "@/app/ugc/program";

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
 * Every row carries its own Apply button straight into the form, and the page
 * opens with one. Previously the only way in was an arrow glyph at the end of
 * a row, which nobody reads as a button — the application was the thing this
 * page exists for and the hardest thing on it to find.
 *
 * The row splits into two separate links rather than one nested pair: the
 * title area goes to the role page to be read, the pill goes straight to the
 * form for somebody who already knows which job they want.
 *
 * No motion beyond hover. The page renders and sits still.
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

        <section className="hub-hero">
          <h1
            className="font-serif"
            style={{
              fontSize: "clamp(44px, 9vw, 104px)",
              lineHeight: 0.94,
              letterSpacing: "-0.035em",
              color: "var(--ink)",
              margin: 0,
            }}
          >
            Come build the thing.
          </h1>

          <div className="hub-hero-body">
            <p style={{ fontSize: "clamp(17px, 2vw, 20px)", lineHeight: 1.55, color: "var(--ink)", margin: 0 }}>
              Anticipy is a pendant that listens while you talk and does the
              things you mention. No wake word, no &ldquo;hey pendant.&rdquo;
              You say it to whoever you&apos;re with, and an agent on your
              computer quietly handles it.
            </p>
            <p style={{ fontSize: 16, lineHeight: 1.7, color: "var(--ink-2)", margin: "16px 0 0" }}>
              I&apos;m hiring four people to build it with me. No cover letter,
              no resume. I read every application myself and reply to the ones
              I want to talk to.
            </p>

            <div className="hub-cta">
              <ApplyButton
                href="/apply/start"
                label="Start your application"
                id="hub_primary_apply"
                location="hero"
              />
              <span style={{ fontSize: 14, color: "var(--ink-2)" }}>
                Takes a few minutes. Your answers save as you go.
              </span>
            </div>
          </div>
        </section>

        <section className="who">
          <h2 className="font-serif">Who I actually need</h2>
          <p>
            <strong>Hardware and software people first.</strong> The pendant is
            real hardware with a real factory problem, and the agent that makes
            it useful is real software. Those are the two things holding the
            product back. If you do both, you&apos;re the one I want most.
          </p>
          <p>
            I care about what you&apos;ve built, not where you&apos;ve worked.
            The person I&apos;m looking for has been tinkering since before
            anyone paid them to, ships without waiting for permission, and is
            better than their job title says they are.
          </p>
          <p>
            If you&apos;ve been passed over for being young, self-taught, or
            short on the right logos — that counts for you here, not against
            you. I&apos;m 15. I&apos;m not going to hold your CV against you.
          </p>
          <p className="who-note">
            Growth is open too, but engineering is what I&apos;d drop
            everything to fill. Vancouver helps for hardware because the units
            are physically here; everything else can be remote.
          </p>
        </section>

        <ol className="role-table">
          {ROLES.map((r) => (
            <li key={r.key} className="role-row">
              <Link href={`/${r.slug}`} className="role-main">
                <span className="role-name font-serif">{r.label}</span>
                <span className="role-line">{r.tagline}</span>
                <span className="role-read">Read the role →</span>
              </Link>
              <ApplyButton
                href={`/apply/start?role=${r.slug}`}
                label="Apply"
                size="md"
                id={`hub_apply_${r.slug}`}
                location="mid_page"
              />
            </li>
          ))}
        </ol>

        {/* Not a job. Kept visually distinct from the four salaried roles so
            nobody applies to one thinking it is the other. */}
        <section className="ugc-block">
          <div>
            <p style={{ fontFamily: "var(--mono)", fontSize: 10.5, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--accent-ink)", margin: "0 0 12px" }}>
              Not a job — anyone can do this
            </p>
            <h2 className="font-serif" style={{ fontSize: "clamp(26px, 3.4vw, 36px)", letterSpacing: "-0.025em", color: "var(--ink)", margin: "0 0 12px" }}>
              Anticipy UGC Creator
            </h2>
            <p style={{ fontSize: 16.5, lineHeight: 1.65, color: "var(--ink-2)", margin: "0 0 18px", maxWidth: "30em" }}>
              Make videos, get your own link, get paid twice — ${PAY.perVideo} a
              video past {PAY.viewFloor.toLocaleString()} views, and{" "}
              {PAY.purchaseSharePct}% of every order through your link.
            </p>
            <ApplyButton href="/ugc" label="See how it works" id="hub_ugc" location="mid_page" />
          </div>
        </section>

        <section style={{ padding: "76px 0 110px" }}>
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
        ${APPLY_BUTTON_CSS}

        .hub-hero { padding: 76px 0 72px; }
        .hub-hero-body { max-width: 34em; margin-top: 34px; }
        .hub-cta { display: flex; align-items: center; gap: 20px; flex-wrap: wrap; margin-top: 34px; }

        .who { padding: 8px 0 40px; max-width: 40em; }
        .who h2 { font-size: clamp(22px, 2.8vw, 28px); letter-spacing: -0.02em; color: var(--ink); margin: 0 0 16px; }
        .who p { font-size: 16.5px; line-height: 1.7; color: var(--ink); margin: 0 0 14px; }
        .who strong { font-weight: 600; }
        .who-note { font-size: 15px !important; color: var(--ink-2) !important; }

        .role-table { list-style: none; margin: 0; padding: 0; border-top: 1px solid var(--rule); }
        .role-row {
          display: grid;
          grid-template-columns: minmax(0, 1fr) auto;
          gap: 32px;
          align-items: center;
          border-bottom: 1px solid var(--rule);
          padding: 22px 4px;
          transition: background 160ms ease;
        }
        .role-row:hover { background: var(--paper-2); }
        .role-main { display: block; text-decoration: none; }
        .role-name { display: block; font-size: clamp(19px, 2.1vw, 24px); letter-spacing: -0.02em; color: var(--ink); }
        .role-line { display: block; font-size: 15.5px; line-height: 1.5; color: var(--ink-2); margin-top: 5px; }
        .role-read {
          display: inline-block; margin-top: 9px;
          font-family: var(--mono); font-size: 11px; letter-spacing: 0.1em;
          text-transform: uppercase; color: var(--accent-ink);
        }
        .role-main:hover .role-read { text-decoration: underline; text-underline-offset: 3px; }

        .ugc-block {
          margin-top: 56px;
          padding: 34px;
          border: 1px solid var(--rule);
          border-radius: 14px;
          background: var(--paper-2);
        }
        @media (max-width: 620px) { .ugc-block { padding: 24px; margin-top: 40px; } }

        .how-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 16px; max-width: 34em; }
        .how-list li { display: flex; gap: 18px; font-size: 16.5px; line-height: 1.65; color: var(--ink); }
        .how-num {
          font-family: var(--mono);
          font-size: 11.5px; color: var(--accent-ink); padding-top: 5px; flex-shrink: 0;
        }

        @media (max-width: 820px) {
          .hub-hero { padding: 52px 0 48px; }
          .role-row { grid-template-columns: 1fr auto; gap: 14px 18px; padding: 20px 4px; }
          .role-main { grid-column: 1 / -1; }
        }
      ` }} />
    </main>
  );
}
