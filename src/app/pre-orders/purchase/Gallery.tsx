"use client";

import { useState } from "react";
import Image from "next/image";
import { motion, AnimatePresence } from "motion/react";
import { ease } from "@/lib/animation";

const IMAGES = [
  {
    src: "/images/colorways.png",
    alt: "Anticipy pendant. Silver and gold colorways side by side.",
  },
  {
    src: "/images/macro.png",
    alt: "Anticipy pendant. Extreme close-up of the brushed titanium surface and single LED.",
  },
  {
    src: "/images/mirror.png",
    alt: "Anticipy pendant worn in front of a bathroom mirror.",
  },
  {
    src: "/images/flatlay.png",
    alt: "Anticipy pendant, chain, and wireless charging pad in flatlay.",
  },
];

export function Gallery() {
  const [index, setIndex] = useState(0);
  const active = IMAGES[index];

  return (
    <div>
      <div
        className="relative w-full aspect-[5/4] rounded-image overflow-hidden mb-4"
        style={{ background: "var(--cream-muted)" }}
      >
        <AnimatePresence mode="wait">
          <motion.div
            key={active.src}
            initial={{ opacity: 0, scale: 1.02 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.98 }}
            transition={{ duration: 0.4, ease }}
            className="absolute inset-0"
          >
            <Image
              src={active.src}
              alt={active.alt}
              fill
              priority={index === 0}
              sizes="(max-width: 768px) 100vw, 50vw"
              className="object-cover"
            />
          </motion.div>
        </AnimatePresence>
      </div>

      <div className="grid grid-cols-6 gap-2">
        {IMAGES.map((img, i) => (
          <button
            key={img.src}
            type="button"
            onClick={() => setIndex(i)}
            aria-label={`View image ${i + 1}`}
            className="relative aspect-square rounded-image overflow-hidden transition-all duration-200"
            style={{
              background: "var(--cream-muted)",
              outline:
                i === index
                  ? "2px solid var(--text-on-light)"
                  : "2px solid transparent",
              outlineOffset: "2px",
            }}
          >
            <Image
              src={img.src}
              alt={img.alt}
              fill
              sizes="120px"
              className="object-cover"
            />
          </button>
        ))}
      </div>
    </div>
  );
}
