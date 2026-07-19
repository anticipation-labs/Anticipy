"use client";

import { useEffect, useRef } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

const LINES = [
  "Your audio never leaves without your rule.",
  "Every action is previewed before it happens.",
  "Every result is independently verified.",
];

export function Trust() {
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.fromTo(
        ".trust-line",
        { opacity: 0, y: 26 },
        {
          opacity: 1,
          y: 0,
          duration: 0.9,
          ease: "power3.out",
          stagger: 0.25,
          scrollTrigger: {
            trigger: rootRef.current,
            start: "top 65%",
            toggleActions: "play none none reverse",
          },
        }
      );
    }, rootRef);
    return () => ctx.revert();
  }, []);

  return (
    <section
      ref={rootRef}
      id="privacy"
      className="relative section-dark py-[140px] px-6 overflow-hidden"
    >
      <video
        className="absolute inset-0 w-full h-full object-cover opacity-[0.16]"
        src="/videos/macro-listen.mp4"
        autoPlay
        muted
        loop
        playsInline
        aria-hidden
      />
      <div
        className="absolute inset-0"
        style={{
          background:
            "linear-gradient(to bottom, var(--dark) 0%, rgba(12,12,12,0.35) 50%, var(--dark) 100%)",
        }}
      />
      <div className="relative max-w-xl mx-auto text-center">
        <p className="trust-line text-[12px] uppercase tracking-[0.3em] text-gold mb-10">
          Three rules, engraved
        </p>
        {LINES.map((l, i) => (
          <p
            key={l}
            className="trust-line font-serif text-[clamp(20px,2.6vw,28px)] text-[var(--text-on-dark)] py-5"
            style={{
              borderBottom:
                i < LINES.length - 1 ? "1px solid var(--dark-border)" : "none",
            }}
          >
            {l}
          </p>
        ))}
      </div>
    </section>
  );
}
