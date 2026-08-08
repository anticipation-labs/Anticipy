"use client";

import Image from "next/image";

const FRAMES: (
  | { type: "video"; src: string; caption: string }
  | { type: "image"; src: string; caption: string }
)[] = [
  { type: "video", src: "/videos/on-body.mp4", caption: "Worn all day" },
  { type: "video", src: "/videos/night-charge.mp4", caption: "Charging by the bed" },
  { type: "video", src: "/videos/flatlay-done.mp4", caption: "At rest" },
];

/**
 * The "worn, not noticed" strip.
 *
 * This was a GSAP-pinned horizontal scroll: the section locked the viewport
 * and translated vertical scroll into sideways movement. That is scroll-
 * jacking — the visitor pushes down, the page goes across, and they cannot
 * leave until the track finishes. It also meant the whole strip depended on
 * JavaScript and a layout measurement taken at mount, so it broke on resize
 * and did nothing sensible for anyone on reduced motion.
 *
 * It is now an ordinary horizontal scroll container. Touch swipe works
 * natively on mobile, trackpads scroll it sideways, keyboards can tab through
 * it, and vertical scrolling always moves the page vertically. Scroll-snap
 * keeps frames aligned without any script at all.
 */
export function Worn() {
  return (
    <section className="section-cream relative">
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

      <div
        className="flex gap-6 px-6 md:px-12 pb-[110px] overflow-x-auto"
        style={{
          scrollSnapType: "x mandatory",
          // The strip is a horizontal region; tell the browser so it does not
          // wait to decide whether a swipe was meant to scroll the page.
          touchAction: "pan-x",
          scrollbarWidth: "none",
          msOverflowStyle: "none",
        }}
      >
        {FRAMES.map((f) => (
          <figure
            key={f.src}
            className="w-[78vw] sm:w-[60vw] md:w-[44vw] lg:w-[34vw] shrink-0"
            style={{ scrollSnapAlign: "start" }}
          >
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
