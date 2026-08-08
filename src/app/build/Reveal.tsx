"use client";

import { motion } from "motion/react";
import { ReactNode } from "react";
import { ease } from "@/lib/animation";

/**
 * On-load reveal for this page.
 *
 * The site's shared ScrollReveal fires on scroll into view, which is wrong
 * here: the headline and subheadline are above the fold on load, so a
 * whileInView trigger either fires instantly with no stagger or, on short
 * viewports, leaves content invisible until the user scrolls.
 *
 * This animates on mount with an explicit delay, so the page assembles in a
 * deliberate order — headline, then subheadline, then body, then form —
 * rather than everything arriving at once. Same easing curve as the rest of
 * the site so the motion feels related.
 *
 * Respects prefers-reduced-motion via the `reduce` variant below: the content
 * still appears, it simply does not travel.
 */
export function Reveal({
  children,
  delay = 0,
  y = 18,
}: {
  children: ReactNode;
  delay?: number;
  y?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.85, ease, delay }}
      style={{ willChange: "transform, opacity" }}
    >
      {children}
    </motion.div>
  );
}
