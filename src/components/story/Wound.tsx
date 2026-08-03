"use client";

import { useEffect, useRef } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

const PROMISES = [
  { said: "\u201CI\u2019ll send it tonight.\u201D", truth: "You didn\u2019t." },
  { said: "\u201CI\u2019ll book it tomorrow.\u201D", truth: "You forgot." },
  { said: "\u201CRemind me to call him back.\u201D", truth: "You never did." },
];

export function Wound() {
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      const tl = gsap.timeline({
        scrollTrigger: {
          trigger: rootRef.current,
          start: "top top",
          end: "+=2300",
          scrub: 0.6,
          pin: true,
        },
      });

      PROMISES.forEach((_, i) => {
        const said = `.wound-said-${i}`;
        const truth = `.wound-truth-${i}`;
        tl.fromTo(
          said,
          { opacity: 0, y: 30, filter: "blur(8px)" },
          { opacity: 1, y: 0, filter: "blur(0px)", duration: 1 }
        )
          .fromTo(
            truth,
            { opacity: 0 },
            { opacity: 1, duration: 0.6 },
            "+=0.4"
          )
          .to(
            [said, truth],
            {
              opacity: 0,
              y: -40,
              filter: "blur(10px)",
              letterSpacing: "0.08em",
              duration: 1,
            },
            "+=0.8"
          );
      });

      tl.fromTo(
        ".wound-closer-1",
        { opacity: 0, y: 30 },
        { opacity: 1, y: 0, duration: 1 }
      ).fromTo(
        ".wound-closer-2",
        { opacity: 0, filter: "blur(10px)" },
        { opacity: 1, filter: "blur(0px)", duration: 1.2 },
        "+=0.3"
      );
    }, rootRef);
    return () => ctx.revert();
  }, []);

  return (
    <section
      ref={rootRef}
      className="relative min-h-screen overflow-hidden section-cream"
    >
      <div className="relative z-10 min-h-screen flex items-center justify-center px-6">
        <div className="text-center max-w-3xl">
          {PROMISES.map((p, i) => (
            <div key={i} className="absolute inset-0 flex flex-col items-center justify-center px-6">
              <p
                className={`wound-said-${i} font-serif text-[clamp(28px,4.5vw,54px)] leading-tight text-[var(--text-on-light)] opacity-0`}
              >
                {p.said}
              </p>
              <p
                className={`wound-truth-${i} mt-6 text-[15px] uppercase tracking-[0.3em] text-[var(--text-on-light-muted)] opacity-0`}
              >
                {p.truth}
              </p>
            </div>
          ))}
          <div className="absolute inset-0 flex flex-col items-center justify-center px-6">
            <p className="wound-closer-1 text-[15px] uppercase tracking-[0.3em] text-[var(--text-on-light-muted)] opacity-0">
              Everything you say you&apos;ll do
            </p>
            <p className="wound-closer-2 font-serif italic text-[clamp(36px,6vw,72px)] text-[var(--text-on-light)] mt-4 opacity-0">
              disappears.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
