"use client";

import { useRef } from "react";
import { motion, useInView } from "motion/react";
import { ease } from "@/lib/animation";

export function Hook() {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, amount: 0.5 });

  const line1 = "Every wearable listens.";
  const line2 = "Not one of them does anything about it.";

  const words1 = line1.split(" ");
  const words2 = line2.split(" ");
  const allWords = [...words1, ...words2];

  return (
    <section className="section-dark py-[160px] px-6" ref={ref}>
      <div className="max-w-container mx-auto text-center">
        <h2 className="font-serif text-section tracking-tight-section leading-[1.15]">
          {words1.map((word, i) => (
            <motion.span
              key={`w1-${i}`}
              className="inline-block mr-[0.3em]"
              initial={{ opacity: 0, y: 40 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{
                duration: 0.5,
                delay: i * 0.04,
                ease: ease,
              }}
            >
              {word}
            </motion.span>
          ))}
          <br />
          {words2.map((word, i) => (
            <motion.span
              key={`w2-${i}`}
              className="inline-block mr-[0.3em] italic text-gold"
              initial={{ opacity: 0, y: 40 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{
                duration: 0.5,
                delay: (words1.length + i) * 0.04,
                ease: ease,
              }}
            >
              {word}
            </motion.span>
          ))}
        </h2>
      </div>
    </section>
  );
}
