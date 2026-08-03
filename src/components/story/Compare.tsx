"use client";

import { useEffect, useRef } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

const ROWS: {
  feature: string;
  anticipy: string;
  others: string;
}[] = [
  {
    feature: "What you get back",
    anticipy: "The task, done and verified",
    others: "A transcript or a summary",
  },
  {
    feature: "After you speak",
    anticipy: "It drafts, you approve, it executes",
    others: "You still do everything yourself",
  },
  {
    feature: "Proof",
    anticipy: "Independent receipt for every action",
    others: "Trust the notification",
  },
  {
    feature: "Price",
    anticipy: "$149.99 now, $199 at launch",
    others: "Hardware plus a subscription on top",
  },
];

const LINKS = [
  { href: "/vs/limitless", label: "vs Limitless" },
  { href: "/vs/bee", label: "vs Bee" },
  { href: "/vs/friend", label: "vs Friend" },
];

export function Compare() {
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.fromTo(
        ".cmp-anim",
        { opacity: 0, y: 28 },
        {
          opacity: 1,
          y: 0,
          duration: 0.9,
          ease: "power3.out",
          stagger: 0.1,
          scrollTrigger: {
            trigger: rootRef.current,
            start: "top 70%",
            toggleActions: "play none none reverse",
          },
        }
      );
    }, rootRef);
    return () => ctx.revert();
  }, []);

  return (
    <section ref={rootRef} className="section-cream px-6 py-[110px]">
      <div className="max-w-3xl mx-auto">
        <p className="cmp-anim text-[12px] uppercase tracking-[0.3em] text-bronze text-center mb-5">
          Recorders remember. Anticipy finishes.
        </p>
        <h2 className="cmp-anim font-serif text-[clamp(28px,4vw,44px)] leading-[1.1] text-[var(--text-on-light)] text-center">
          Every other pendant hands the work
          <span className="italic"> back to you.</span>
        </h2>

        <div
          className="cmp-anim mt-12 rounded-2xl overflow-hidden"
          style={{ border: "1px solid var(--cream-border)", background: "#FFFFFF" }}
        >
          <div
            className="grid grid-cols-[1fr_1.2fr_1.2fr] text-[11px] uppercase tracking-[0.15em] px-6 py-4"
            style={{ background: "var(--cream-muted)", color: "var(--text-on-light-muted)" }}
          >
            <span />
            <span className="text-bronze">Anticipy</span>
            <span>AI recorders</span>
          </div>
          {ROWS.map((r) => (
            <div
              key={r.feature}
              className="grid grid-cols-[1fr_1.2fr_1.2fr] gap-3 px-6 py-5 text-[14px] border-t"
              style={{ borderColor: "var(--cream-border)" }}
            >
              <span className="text-[var(--text-on-light-muted)]">{r.feature}</span>
              <span className="text-[var(--text-on-light)]">{r.anticipy}</span>
              <span className="text-[var(--text-on-light-muted)]">{r.others}</span>
            </div>
          ))}
        </div>

        <div className="cmp-anim flex items-center justify-center gap-7 mt-8 text-[14px]">
          {LINKS.map((l) => (
            <a
              key={l.href}
              href={l.href}
              className="text-[var(--text-on-light)] underline underline-offset-4 decoration-[rgba(138,107,68,0.45)] hover:text-bronze transition-colors"
            >
              {l.label}
            </a>
          ))}
        </div>
      </div>
    </section>
  );
}
