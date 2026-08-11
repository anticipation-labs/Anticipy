import type { Metadata } from "next";
import Link from "next/link";
import { Tm } from "@/components/Tm";
import { HIRE_THEME } from "@/components/apply/theme";
import { ApplyButton, APPLY_BUTTON_CSS } from "@/components/apply/ApplyButton";
import { PAY, PAY_LINES, LINK_BASE, AGREEMENTS } from "./program";

export const metadata: Metadata = {
  title: "Anticipy UGC Creator — get paid twice",
  description: `$${PAY.perVideo} a video past ${PAY.viewFloor.toLocaleString()} views, and ${PAY.purchaseSharePct}% of every order through your link.`,
  alternates: { canonical: "https://www.anticipy.ai/ugc" },
  openGraph: {
    title: "Anticipy UGC Creator",
    description: "Make videos. Get your own link. Get paid twice.",
    url: "https://www.anticipy.ai/ugc",
    type: "website",
  },
};

const RULES: { q: string; a: string }[] = [
  {
    q: "What counts as a video?",
    a: `Anything you post to your own channel that features the pendant and is labelled as an ad. There's no format, no script and no approval step. It has to pass ${PAY.viewFloor.toLocaleString()} views to earn the flat fee — that's the only bar.`,
  },
  {
    q: "When do I get paid?",
    a: "Send me the link once it clears the view floor and I'll pay it out. Your share of anything the link sells is tallied and paid at the end of each month.",
  },
  {
    q: "Do I have to say it's an ad?",
    a: "Yes, and this one isn't negotiable. We pay you, which makes it a material connection, and US and Canadian rules both require it to be obvious. The platform's paid-partnership toggle is enough on its own; #ad in the caption works too. Say it out loud in the first few seconds if you're talking to camera.",
  },
  {
    q: "Can you run my video as an ad?",
    a: "For 90 days from the day you send it, on Instagram, TikTok, YouTube, Facebook and our own site. After that it lapses unless we ask again and pay for it. We won't touch your ad account, and we won't run anything through your handle without a separate written agreement. You keep the video.",
  },
  {
    q: "What if nobody buys?",
    a: `You still get $${PAY.perVideo} for every video that clears the view floor. The ${PAY.purchaseSharePct}% is on top, not instead.`,
  },
  {
    q: "Can I be anywhere?",
    a: "Anywhere. The pendant ships from Vancouver but the videos don't have to.",
  },
];

/**
 * The UGC program, explained.
 *
 * A real page rather than a screen inside the funnel, because creators share
 * the terms with each other and a URL is what gets shared. Everything a
 * creator is promised is read from program.ts, so the page and the signup
 * confirmation email cannot end up quoting different rates.
 */
export default function UgcPage() {
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
          <Link href="/" className="font-serif" style={{ fontSize: 19, color: "var(--ink)", textDecoration: "none", letterSpacing: "0.01em" }}>
            Anticipy<Tm />
          </Link>
          <Link href="/apply" style={{ fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--accent-ink)", textDecoration: "none" }}>
            Jobs
          </Link>
        </header>

        <section className="ugc-hero">
          <p style={{ fontFamily: "var(--mono)", fontSize: 10.5, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--accent-ink)", margin: "0 0 16px" }}>
            Anticipy UGC Creator
          </p>
          <h1
            className="font-serif"
            style={{ fontSize: "clamp(40px, 7.4vw, 84px)", lineHeight: 0.96, letterSpacing: "-0.035em", color: "var(--ink)", margin: 0 }}
          >
            Make videos.
            <br />
            Get paid twice.
          </h1>
          <p style={{ fontSize: "clamp(17px, 2vw, 20px)", lineHeight: 1.55, color: "var(--ink)", margin: "30px 0 0", maxWidth: "32em" }}>
            You get your own link, you post what you want, and you earn on the
            video whether or not anyone buys — then again if they do.
          </p>

          <ol className="pay-table">
            {PAY_LINES.map((l) => (
              <li key={l.label}>
                <span className="pay-amt font-serif">{l.amount}</span>
                <span className="pay-label">{l.label}</span>
                <span className="pay-detail">{l.detail}</span>
              </li>
            ))}
          </ol>

          <div className="ugc-cta">
            <ApplyButton href="/ugc/apply" label="Become a creator" id="ugc_hero_apply" location="hero" />
            <span style={{ fontSize: 14, color: "var(--ink-2)" }}>
              Five minutes. You&apos;ll have your link at the end.
            </span>
          </div>
        </section>

        <section className="ugc-how">
          <div style={{ width: 38, height: 2, background: "var(--accent)", marginBottom: 18 }} />
          <h2 className="font-serif" style={{ fontSize: "clamp(24px, 3vw, 30px)", letterSpacing: "-0.02em", color: "var(--ink)", margin: "0 0 24px" }}>
            How it works
          </h2>
          <ol className="how-list">
            <li><span className="how-num">01</span><span>Sign up and pick your link — <span style={{ fontFamily: "var(--mono)" }}>{LINK_BASE}yourname</span>. Put it in your bio.</span></li>
            <li><span className="how-num">02</span><span>Make a video. Post it on your own channel, tag <strong>@anticipy</strong>, label it as an ad.</span></li>
            <li><span className="how-num">03</span><span>Send me the link. Past {PAY.viewFloor.toLocaleString()} views, that&apos;s ${PAY.perVideo}.</span></li>
            <li><span className="how-num">04</span><span>Anything your link sells earns you {PAY.purchaseSharePct}% on top, paid at the end of the month.</span></li>
          </ol>
        </section>

        <section className="ugc-rules">
          <div style={{ width: 38, height: 2, background: "var(--accent)", marginBottom: 18 }} />
          <h2 className="font-serif" style={{ fontSize: "clamp(24px, 3vw, 30px)", letterSpacing: "-0.02em", color: "var(--ink)", margin: "0 0 6px" }}>
            The rules, in full
          </h2>
          <p style={{ fontSize: 15, color: "var(--ink-2)", margin: "0 0 30px", maxWidth: "34em" }}>
            There is no other contract. This is it.
          </p>
          <dl className="rule-list">
            {RULES.map((r) => (
              <div key={r.q}>
                <dt className="font-serif">{r.q}</dt>
                <dd>{r.a}</dd>
              </div>
            ))}
          </dl>

          <div style={{ marginTop: 44, paddingTop: 32, borderTop: "1px solid var(--rule)" }}>
            <ApplyButton href="/ugc/apply" label="Become a creator" id="ugc_footer_apply" />
            <p style={{ fontSize: 13.5, lineHeight: 1.7, color: "var(--ink-2)", margin: "20px 0 0", maxWidth: "34em" }}>
              You&apos;ll be asked to agree to two things: {AGREEMENTS.disclosure.label.toLowerCase().replace(/\.$/, "")}, and that{" "}
              {AGREEMENTS.rights.label.toLowerCase().replace(/\.$/, "")}. Both are spelled out in the form before you agree to them.
            </p>
          </div>
        </section>
      </div>

      <style dangerouslySetInnerHTML={{ __html: `
        ${APPLY_BUTTON_CSS}
        .ugc-hero { padding: 72px 0 64px; }
        .ugc-cta { display: flex; align-items: center; gap: 20px; flex-wrap: wrap; margin-top: 40px; }

        .pay-table { list-style: none; margin: 44px 0 0; padding: 0; border-top: 1px solid var(--rule); }
        .pay-table li {
          display: grid;
          grid-template-columns: 140px 200px 1fr;
          gap: 24px;
          align-items: baseline;
          padding: 22px 0;
          border-bottom: 1px solid var(--rule);
        }
        .pay-amt { font-size: clamp(30px, 4vw, 42px); letter-spacing: -0.03em; color: var(--ink); line-height: 1; }
        .pay-label { font-family: var(--mono); font-size: 12.5px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--accent-ink); }
        .pay-detail { font-size: 15.5px; line-height: 1.6; color: var(--ink-2); }

        .ugc-how { padding: 20px 0 64px; }
        .how-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 16px; max-width: 40em; }
        .how-list li { display: flex; gap: 18px; font-size: 16.5px; line-height: 1.65; color: var(--ink); }
        .how-num { font-family: var(--mono); font-size: 11.5px; color: var(--accent-ink); padding-top: 5px; flex-shrink: 0; }

        .ugc-rules { padding: 20px 0 110px; }
        .rule-list { margin: 0; padding: 0; display: grid; gap: 28px; max-width: 40em; }
        .rule-list dt { font-size: clamp(18px, 2vw, 21px); letter-spacing: -0.015em; color: var(--ink); margin-bottom: 8px; }
        .rule-list dd { margin: 0; font-size: 16px; line-height: 1.72; color: var(--ink-2); }

        @media (max-width: 820px) {
          .ugc-hero { padding: 48px 0 44px; }
          .pay-table li { grid-template-columns: 1fr; gap: 6px; padding: 20px 0; }
          .pay-amt { font-size: 34px; }
        }
      ` }} />
    </main>
  );
}
