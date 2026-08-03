"use client";

import { useEffect, useRef } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

const LIMITS: { limit: string; why: string }[] = [
  {
    limit: "It never acts on its own.",
    why: "Every email, message, and call is drafted first and sent only after you approve it. Slower than full autopilot \u2014 and the reason you can trust it with your name.",
  },
  {
    limit: "It isn\u2019t waterproof.",
    why: "Take it off before you swim or shower. We chose an 8-gram titanium body and all-day comfort over a sealed hull you\u2019d feel around your neck.",
  },
  {
    limit: "It needs your phone nearby.",
    why: "The pendant listens; your phone does the thinking, over Bluetooth 5.3. That\u2019s what keeps the pendant this small \u2014 and your audio under your control.",
  },
  {
    limit: "The battery is not infinite.",
    why: "It runs your day, then rests on its charging pad at night \u2014 the same rhythm you keep.",
  },
];

export function Honest() {
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.fromTo(
        ".honest-anim",
        { opacity: 0, y: 28 },
        {
          opacity: 1,
          y: 0,
          duration: 0.9,
          ease: "power3.out",
          stagger: 0.12,
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
    <section ref={rootRef} className="relative section-dark px-6 py-[120px]">
      <div className="max-w-2xl mx-auto">
        <p className="honest-anim text-[12px] uppercase tracking-[0.3em] text-gold text-center mb-4">
          Before you decide
        </p>
        <h2 className="honest-anim font-serif text-[clamp(28px,4vw,44px)] leading-[1.1] text-[var(--text-on-dark)] text-center">
          What it <span className="italic text-gold">doesn&apos;t</span> do.
        </h2>

        <div className="mt-14">
          {LIMITS.map((l) => (
            <div
              key={l.limit}
              className="honest-anim py-7 border-b"
              style={{ borderColor: "var(--dark-border)" }}
            >
              <p className="font-serif text-[clamp(18px,2.2vw,24px)] text-[var(--text-on-dark)]">
                {l.limit}
              </p>
              <p className="mt-2.5 text-[15px] leading-relaxed text-[var(--text-on-dark-muted)] max-w-xl">
                {l.why}
              </p>
            </div>
          ))}
        </div>

        <p className="honest-anim mt-10 text-[14px] text-center text-[var(--text-on-dark-muted)]">
          If any of these is a dealbreaker, Anticipy isn&apos;t for you &mdash;
          better to know now than in August.
        </p>
      </div>
    </section>
  );
}
