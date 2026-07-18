"use client";

import { useEffect, useRef } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

const CHAPTERS = [
  {
    k: "01",
    title: "You speak",
    body: "At dinner. On a walk. Mid-meeting. \u201CI\u2019ll send Marcus the notes tonight \u2014 actually, drop the budget slide.\u201D You just talk.",
    card: (
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-[var(--gold)] animate-pulse" />
          <span className="text-[11px] uppercase tracking-[0.2em] text-[var(--text-on-dark-muted)]">
            Listening
          </span>
        </div>
        <p className="text-[15px] leading-relaxed text-[var(--text-on-dark)]">
          &ldquo;I&rsquo;ll send Marcus the notes tonight &mdash;{" "}
          <span className="text-gold">actually, drop the budget slide.</span>&rdquo;
        </p>
      </div>
    ),
  },
  {
    k: "02",
    title: "It understands",
    body: "Not just the words \u2014 the correction. Who Marcus is. What \u201Ctonight\u201D means. What must never be in that email.",
    card: (
      <div className="space-y-2.5 text-[14px]">
        <div className="flex justify-between">
          <span className="text-[var(--text-on-dark-muted)]">To</span>
          <span className="text-[var(--text-on-dark)]">Marcus Chen</span>
        </div>
        <div className="flex justify-between">
          <span className="text-[var(--text-on-dark-muted)]">Deadline</span>
          <span className="text-[var(--text-on-dark)]">Tonight, 11:59 PM</span>
        </div>
        <div className="flex justify-between">
          <span className="text-[var(--text-on-dark-muted)]">Attachment</span>
          <span className="text-[var(--text-on-dark)]">Meeting notes</span>
        </div>
        <div className="flex justify-between">
          <span className="text-[var(--text-on-dark-muted)]">Excluded</span>
          <span className="text-gold">Budget slide</span>
        </div>
      </div>
    ),
  },
  {
    k: "03",
    title: "It executes",
    body: "The exact email, drafted and shown to you first. One tap to approve. Sent once, verified in your Sent folder. Receipt kept. Closed.",
    card: (
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-[14px] text-[var(--text-on-dark)]">
            Email to Marcus
          </span>
          <span className="text-[11px] px-2.5 py-1 rounded-full border border-[rgba(200,169,126,0.4)] text-gold">
            Approved by you
          </span>
        </div>
        <div className="h-[1px] bg-[var(--dark-border)]" />
        <div className="flex items-center gap-2.5">
          <span className="text-gold">&#10003;</span>
          <span className="text-[14px] text-[var(--text-on-dark)]">
            Sent &middot; verified in Sent &middot; 9:42 PM
          </span>
        </div>
      </div>
    ),
  },
];

export function Chapters() {
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      const panels = gsap.utils.toArray<HTMLElement>(".chapter-panel");
      panels.forEach((panel) => {
        gsap.fromTo(
          panel.querySelectorAll(".chapter-anim"),
          { opacity: 0, y: 50 },
          {
            opacity: 1,
            y: 0,
            duration: 1,
            ease: "power3.out",
            stagger: 0.15,
            scrollTrigger: {
              trigger: panel,
              start: "top 65%",
              toggleActions: "play none none reverse",
            },
          }
        );
      });
    }, rootRef);
    return () => ctx.revert();
  }, []);

  return (
    <section ref={rootRef} id="how-it-works" className="section-dark relative">
      <div className="max-w-container mx-auto px-6 md:px-12 pt-[140px] pb-10 text-center">
        <p className="text-[12px] uppercase tracking-[0.3em] text-gold mb-5">
          What it actually does
        </p>
        <h2 className="font-serif text-[clamp(32px,5vw,60px)] leading-[1.1] text-[var(--text-on-dark)]">
          One promise, followed
          <br />
          <span className="italic">all the way to done.</span>
        </h2>
      </div>

      <div className="max-w-container mx-auto px-6 md:px-12">
        {CHAPTERS.map((c, i) => (
          <div
            key={c.k}
            className={`chapter-panel py-[90px] grid md:grid-cols-2 gap-12 items-center ${
              i % 2 === 1 ? "md:[direction:rtl]" : ""
            }`}
          >
            <div className="md:[direction:ltr]">
              <span className="chapter-anim block font-serif text-[64px] leading-none text-[var(--dark-border)]">
                {c.k}
              </span>
              <h3 className="chapter-anim font-serif text-[clamp(26px,3.5vw,40px)] text-[var(--text-on-dark)] mt-4">
                {c.title}
              </h3>
              <p className="chapter-anim text-[16px] leading-relaxed text-[var(--text-on-dark-muted)] mt-5 max-w-md">
                {c.body}
              </p>
            </div>
            <div className="md:[direction:ltr]">
              <div
                className="chapter-anim rounded-2xl p-7 max-w-sm mx-auto"
                style={{
                  background: "var(--dark-elevated)",
                  border: "1px solid var(--dark-border)",
                  boxShadow: "0 30px 60px rgba(0,0,0,0.45)",
                }}
              >
                {c.card}
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="chapter-panel max-w-container mx-auto px-6 md:px-12 pb-[130px] text-center">
        <p className="chapter-anim font-serif italic text-[clamp(22px,3vw,32px)] text-[var(--text-on-dark)]">
          That&apos;s one promise. It does this with all of them.
        </p>
        <div className="chapter-anim mt-8">
          <a
            href="/pre-orders/purchase"
            className="inline-block rounded-pill text-[16px] font-medium transition-all duration-300 hover:scale-[1.02]"
            style={{
              background: "var(--text-on-dark)",
              color: "var(--dark)",
              padding: "16px 44px",
            }}
          >
            Pre-order &mdash; $149.99
          </a>
          <p className="text-[12px] uppercase tracking-[0.18em] text-[var(--text-on-dark-muted)] mt-4">
            Ships August 2026 &middot; Full refund anytime before shipping
          </p>
        </div>
      </div>
    </section>
  );
}
