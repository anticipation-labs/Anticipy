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
        ".hero-sub",
        { opacity: 0, y: 16 },
        { opacity: 1, y: 0, duration: 1.1, ease: "power3.out", delay: 1.5 }
      );
      gsap.fromTo(
        ".hero-cta",
        { opacity: 0, y: 16 },
        { opacity: 1, y: 0, duration: 1.1, ease: "power3.out", delay: 1.9 }
      );
      gsap.fromTo(
        ".hero-cue",
        { opacity: 0 },
        { opacity: 1, duration: 1.2, delay: 2.6 }
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
        src="/videos/hero-pendant.mp4?v=2"
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
            "linear-gradient(rgba(12,12,12,0.35), rgba(12,12,12,0.35)), radial-gradient(ellipse at center, rgba(12,12,12,0) 30%, rgba(12,12,12,0.8) 100%)",
        }}
      />

      <div className="relative z-10 text-center px-6">
        <h1 className="hero-line font-serif text-[clamp(40px,7vw,88px)] leading-[1.05] tracking-tight text-[var(--text-on-dark)]">
          Say it once.
        </h1>
        <h1 className="hero-line font-serif italic text-[clamp(40px,7vw,88px)] leading-[1.05] tracking-tight text-[var(--text-on-dark)]">
          It&apos;s handled.
        </h1>

        <p className="hero-sub mt-7 text-[clamp(15px,1.8vw,19px)] leading-relaxed text-[var(--text-on-dark)] max-w-xl mx-auto opacity-0">
          Anticipy is a titanium pendant that hears the promises you make out
          loud &mdash; and follows them all the way to done.
        </p>

        <div className="hero-cta mt-9 opacity-0">
          <a
            href="/pre-orders/purchase"
            className="inline-block rounded-pill text-[16px] font-medium transition-all duration-300 hover:scale-[1.02]"
            style={{
              background: "var(--text-on-dark)",
              color: "var(--dark)",
              padding: "16px 44px",
            }}
          >
            Claim yours &mdash; $149.99
          </a>
          <p className="text-[12px] uppercase tracking-[0.18em] text-[var(--text-on-dark-muted)] mt-4">
            $199 at launch &middot; Ships Q4 2026 &middot; Full refund
            anytime before shipping
          </p>
        </div>
      </div>

      <div className="hero-cue absolute bottom-6 left-1/2 -translate-x-1/2 opacity-0">
        <span className="block w-[1px] h-10 bg-gradient-to-b from-[rgba(245,240,235,0.7)] to-transparent animate-pulse" />
      </div>
    </section>
  );
}
