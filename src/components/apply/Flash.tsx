"use client";

import { motion, AnimatePresence } from "motion/react";

/**
 * The cut between screens.
 *
 * Timing is measured, not chosen: a screen change should land in 240-300ms and
 * never exceed 320ms, because on a five-screen flow the person pays that cost
 * five times. The first version of this ran a 330ms flash and then swapped the
 * screen 150ms in — about 480ms of perceived latency, with the flash competing
 * against the screen change rather than covering it. That is what "not smooth"
 * was.
 *
 * Now the whole thing is 260ms and the swap happens at 90ms, under the second
 * beat, so the change is hidden inside the cut rather than racing it.
 *
 * `pointerEvents: none` so it never swallows a tap from someone moving fast,
 * and skipped entirely under reduced-motion, where rapid luminance changes are
 * exactly the pattern to avoid.
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
          animate={{ opacity: [0, 0.10, 0.02, 0.07, 0.01, 0.04, 0] }}
          exit={{ opacity: 0 }}
          transition={{
            duration: 0.26,
            times: [0, 0.14, 0.3, 0.46, 0.62, 0.78, 1],
            ease: "linear",
          }}
          style={{
            position: "fixed",
            inset: 0,
            background: "var(--ink)",
            mixBlendMode: "overlay",
            pointerEvents: "none",
            zIndex: 60,
          }}
        />
      )}
    </AnimatePresence>
  );
}
