"use client";

import { useEffect, useRef } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

const FALLING = ["send it", "book it", "call him back", "the notes", "tonight"];

export function Turn() {
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      const tl = gsap.timeline({
        scrollTrigger: {
          trigger: rootRef.current,
          start: "top top",
          end: "+=2000",
          scrub: 0.6,
          pin: true,
        },
      });

      // Pendant video fades in
      tl.fromTo(
        ".turn-video",
        { opacity: 0, scale: 1.08 },
        { opacity: 1, scale: 1, duration: 1.4 }
      );

      // Words fall into the pendant
      FALLING.forEach((_, i) => {
        tl.fromTo(
          `.turn-word-${i}`,
          { opacity: 0, y: -160 - i * 20, x: (i - 2) * 60 },
          { opacity: 0.9, y: 40, x: 0, duration: 0.8 },
          i === 0 ? "-=0.4" : "-=0.55"
        ).to(
          `.turn-word-${i}`,
          { opacity: 0, scale: 0.4, y: 90, duration: 0.4 },
          "-=0.25"
        );
      });

      // LED response + handled card
      tl.fromTo(
        ".turn-led",
        { opacity: 0, scale: 0.4 },
        { opacity: 1, scale: 1, duration: 0.6 }
      )
        .fromTo(
          ".turn-card",
          { opacity: 0, y: 40, scale: 0.96 },
          { opacity: 1, y: 0, scale: 1, duration: 1 },
          "+=0.2"
        )
        .fromTo(
          ".turn-caption",
          { opacity: 0 },
          { opacity: 1, duration: 0.8 },
          "-=0.3"
        );
    }, rootRef);
    return () => ctx.revert();
  }, []);

  return (
    <section
      ref={rootRef}
      className="relative min-h-screen overflow-hidden section-dark"
    >
      <video
        className="turn-video absolute inset-0 w-full h-full object-cover opacity-0"
        src="/videos/speak-wave.mp4"
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
            "radial-gradient(ellipse at center, rgba(12,12,12,0.1) 20%, rgba(12,12,12,0.85) 100%)",
        }}
      />

      <div className="relative z-10 min-h-screen flex flex-col items-center justify-center px-6">
        {/* falling words */}
        <div className="relative h-0 w-full max-w-md">
          {FALLING.map((w, i) => (
            <span
              key={w}
              className={`turn-word-${i} absolute left-1/2 -translate-x-1/2 whitespace-nowrap font-serif italic text-[20px] text-[var(--text-on-dark-muted)] opacity-0`}
            >
              {w}
            </span>
          ))}
        </div>

        <span
          className="turn-led block w-2 h-2 rounded-full opacity-0"
          style={{
            background: "var(--text-on-dark)",
            boxShadow: "0 0 18px 4px rgba(245,240,235,0.35)",
          }}
        />

        <div
          className="turn-card mt-10 px-7 py-5 rounded-2xl opacity-0 backdrop-blur-md"
          style={{
            background: "rgba(22,22,22,0.82)",
            border: "1px solid rgba(245,240,235,0.18)",
          }}
        >
          <div className="flex items-center gap-3">
            <span className="text-[var(--text-on-dark)] text-[18px]">&#10003;</span>
            <span className="text-[16px] text-[var(--text-on-dark)]">
              Handled. Receipt saved.
            </span>
          </div>
        </div>

        <p className="turn-caption mt-12 font-serif text-[clamp(28px,4.5vw,52px)] text-center text-[var(--text-on-dark)] opacity-0">
          You heard it. <span className="italic">It&apos;s handled.</span>
        </p>
      </div>
    </section>
  );
}
