"use client";

import { useEffect, useRef } from "react";
import { gsap } from "gsap";

export function StoryHero() {
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.fromTo(
        ".hero-line",
        { opacity: 0, y: 24, filter: "blur(6px)" },
        {
          opacity: 1,
          y: 0,
          filter: "blur(0px)",
          duration: 1.4,
          ease: "power3.out",
          stagger: 0.35,
          delay: 0.6,
        }
      );
      gsap.fromTo(
        ".hero-cue",
        { opacity: 0 },
        { opacity: 1, duration: 1.2, delay: 2.2 }
      );
      // Slow fade of the video as you begin to scroll away
      gsap.to(".hero-video", {
        opacity: 0.25,
        scale: 1.06,
        ease: "none",
        scrollTrigger: {
          trigger: rootRef.current,
          start: "top top",
          end: "bottom top",
          scrub: true,
        },
      });
    }, rootRef);
    return () => ctx.revert();
  }, []);

  return (
    <section
      ref={rootRef}
      className="relative min-h-screen flex items-center justify-center overflow-hidden section-dark"
    >
      <video
        className="hero-video absolute inset-0 w-full h-full object-cover"
        src="/videos/hero-glint.mp4"
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
            "radial-gradient(ellipse at center, rgba(12,12,12,0) 30%, rgba(12,12,12,0.75) 100%)",
        }}
      />

      <div className="relative z-10 text-center px-6">
        <h1 className="hero-line font-serif text-[clamp(40px,7vw,88px)] leading-[1.05] tracking-tight text-[var(--text-on-dark)]">
          Say it once.
        </h1>
        <h1 className="hero-line font-serif italic text-[clamp(40px,7vw,88px)] leading-[1.05] tracking-tight text-gold">
          It&apos;s handled.
        </h1>
      </div>

      <div className="hero-cue absolute bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 opacity-0">
        <span className="text-[11px] uppercase tracking-[0.3em] text-[var(--text-on-dark-muted)]">
          Scroll
        </span>
        <span className="block w-[1px] h-10 bg-gradient-to-b from-[var(--gold)] to-transparent animate-pulse" />
      </div>
    </section>
  );
}
