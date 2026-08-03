"use client";

import { useEffect, useRef } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

const SPECS = [
  { v: "8 g", k: "Titanium, brushed" },
  { v: "3 days", k: "On one charge" },
  { v: "15 ft", k: "Wireless charging" },
  { v: "1 LED", k: "Nothing else" },
];

export function ObjectSection() {
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.fromTo(
        ".object-anim",
        { opacity: 0, y: 50 },
        {
          opacity: 1,
          y: 0,
          duration: 1,
          ease: "power3.out",
          stagger: 0.12,
          scrollTrigger: {
            trigger: rootRef.current,
            start: "top 60%",
            toggleActions: "play none none reverse",
          },
        }
      );
      // Video parallax scale
      gsap.fromTo(
        ".object-video",
        { scale: 1.15 },
        {
          scale: 1,
          ease: "none",
          scrollTrigger: {
            trigger: rootRef.current,
            start: "top bottom",
            end: "bottom top",
            scrub: true,
          },
        }
      );
    }, rootRef);
    return () => ctx.revert();
  }, []);

  return (
    <section ref={rootRef} id="product" className="section-cream relative">
      <div className="relative overflow-hidden">
        <video
          className="object-video w-full h-[70vh] object-cover"
          src="/videos/glove-reveal.mp4"
          autoPlay
          muted
          loop
          playsInline
          aria-hidden
        />
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background:
              "linear-gradient(to bottom, rgba(12,12,12,0.4) 0%, rgba(12,12,12,0.1) 40%, rgba(12,12,12,0.65) 100%)",
          }}
        />
        <div className="absolute bottom-12 left-0 right-0 text-center px-6">
          <h2 className="object-anim font-serif text-[clamp(32px,5vw,60px)] text-[var(--text-on-dark)]">
            Jewelry first. <span className="italic">Then a computer.</span>
          </h2>
        </div>
      </div>

      <div className="max-w-container mx-auto px-6 md:px-12 py-[110px]">
        <p className="object-anim text-center text-[17px] leading-relaxed text-[var(--text-on-light-muted)] max-w-xl mx-auto">
          Machined titanium with a hand-brushed finish, on a chain that sits
          like any other necklace. Lighter than your house key. It charges from across
          the room while you sleep. Nobody will ask what it is &mdash; it just
          looks like something you&apos;d wear. Because it is.
        </p>

        <p className="object-anim text-center text-[13px] uppercase tracking-[0.18em] text-[var(--text-on-light-muted)] max-w-xl mx-auto mt-8">
          In the box: pendant &middot; chain &middot; wireless charging pad
          &middot; nothing else to buy
        </p>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-10 mt-[90px] text-center">
          {SPECS.map((s) => (
            <div key={s.k} className="object-anim">
              <div className="font-serif text-[clamp(30px,4vw,46px)] text-[var(--text-on-light)]">
                {s.v}
              </div>
              <div className="text-[13px] uppercase tracking-[0.18em] text-[var(--text-on-light-muted)] mt-2">
                {s.k}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
