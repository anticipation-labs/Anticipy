"use client";

import { useEffect, useRef } from "react";
import Image from "next/image";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

const FRAMES: (
  | { type: "video"; src: string; caption: string }
  | { type: "image"; src: string; caption: string }
)[] = [
  { type: "video", src: "/videos/on-body.mp4", caption: "Worn all day" },
  { type: "video", src: "/videos/night-charge.mp4", caption: "Charging by the bed" },
  { type: "video", src: "/videos/flatlay-done.mp4", caption: "At rest" },
];

export function Worn() {
  const rootRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      const track = trackRef.current;
      if (!track) return;
      const scrollWidth = track.scrollWidth - window.innerWidth;
      gsap.to(track, {
        x: -scrollWidth,
        ease: "none",
        scrollTrigger: {
          trigger: rootRef.current,
          start: "top top",
          end: `+=${scrollWidth}`,
          scrub: 0.5,
          pin: true,
          invalidateOnRefresh: true,
        },
      });
    }, rootRef);
    return () => ctx.revert();
  }, []);

  return (
    <section ref={rootRef} className="section-cream relative overflow-hidden">
      <div className="pt-[110px] pb-8 px-6 md:px-12">
        <p className="text-[12px] uppercase tracking-[0.3em] text-bronze mb-4">
          Worn, not noticed
        </p>
        <h2 className="font-serif text-[clamp(30px,4.5vw,54px)] text-[var(--text-on-light)] max-w-2xl">
          Nobody asks about it.
          <br />
          <span className="italic">Everything gets done.</span>
        </h2>
      </div>

      <div ref={trackRef} className="flex gap-6 px-6 md:px-12 pb-[110px] w-max">
        {FRAMES.map((f) => (
          <figure key={f.src} className="w-[70vw] md:w-[44vw] lg:w-[36vw] shrink-0">
            <div
              className="rounded-2xl overflow-hidden"
              style={{ border: "1px solid var(--cream-border)" }}
            >
              {f.type === "video" ? (
                <video
                  className="w-full aspect-[4/3] object-cover"
                  src={f.src}
                  autoPlay
                  muted
                  loop
                  playsInline
                />
              ) : (
                <Image
                  src={f.src}
                  alt={f.caption}
                  width={900}
                  height={675}
                  className="w-full aspect-[4/3] object-cover"
                />
              )}
            </div>
            <figcaption className="mt-3 text-[13px] uppercase tracking-[0.18em] text-[var(--text-on-light-muted)]">
              {f.caption}
            </figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}
