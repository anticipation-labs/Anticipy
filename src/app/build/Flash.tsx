"use client";

import { motion, AnimatePresence } from "motion/react";

/**
 * The transition between screens.
 *
 * Three fast beats rather than a fade. A cross-fade reads as "loading"; a
 * rhythmic flash reads as a deliberate cut, which is the difference between
 * feeling like a form and feeling like something was made. The whole sequence
 * is 330ms — long enough to register as intentional, short enough that a
 * person filling in seven screens never waits on it.
 *
 * `pointerEvents: none` throughout: the flash must never eat a tap from
 * someone moving quickly. And it is skipped entirely under reduced-motion,
 * where three rapid luminance changes are exactly the pattern to avoid.
 */
export function Flash({ active }: { active: boolean }) {
  const reduced =
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

  if (reduced) return null;

  return (
    <AnimatePresence>
      {active && (
        <motion.div
          aria-hidden="true"
          initial={{ opacity: 0 }}
          animate={{ opacity: [0, 0.5, 0, 0.32, 0, 0.16, 0] }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.33, times: [0, 0.12, 0.24, 0.42, 0.56, 0.74, 1], ease: "linear" }}
          style={{
            position: "fixed",
            inset: 0,
            background: "var(--gold)",
            pointerEvents: "none",
            zIndex: 60,
            mixBlendMode: "overlay",
          }}
        />
      )}
    </AnimatePresence>
  );
}
