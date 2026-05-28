"use client";

import { motion } from "motion/react";
import Image from "next/image";
import { ease } from "@/lib/animation";

const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.18 } },
};

const childVariants = {
  hidden: { opacity: 0, y: 30 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.9, ease },
  },
};

export function Hero() {
  return (
    <section className="section-dark relative min-h-screen flex items-center justify-center overflow-hidden">
      <motion.div
        className="flex flex-col items-center text-center px-6 pt-[100px] pb-[80px] max-w-4xl mx-auto"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* Tag */}
        <motion.span
          variants={childVariants}
          className="text-gold text-[12px] uppercase tracking-[0.15em] font-medium mb-6"
        >
          By Anticipation Labs
        </motion.span>

        {/* Title */}
        <motion.h1
          variants={childVariants}
          className="font-serif text-hero tracking-tight-hero leading-[1.05] text-[var(--text-on-dark)]"
        >
          Anticipy
        </motion.h1>

        {/* Subtitle */}
        <motion.p
          variants={childVariants}
          className="font-serif italic text-subsection text-[var(--text-on-dark-muted)] mt-4"
        >
          Vibe your life.
        </motion.p>

        {/* Pendant image with floating animation */}
        <motion.div
          variants={childVariants}
          className="mt-12 mb-12 relative"
        >
          <Image
            src="/images/hero.png"
            alt="Anticipy pendant — brushed titanium AI wearable"
            width={640}
            height={480}
            priority
            className="w-full max-w-[640px] h-auto drop-shadow-[0_40px_80px_rgba(0,0,0,0.6)]"
          />
        </motion.div>

        {/* CTA buttons */}
        <motion.div
          variants={childVariants}
          className="flex flex-col sm:flex-row gap-4"
        >
          <a
            href="#waitlist"
            className="px-8 py-3.5 rounded-pill bg-[var(--text-on-dark)] text-[var(--dark)] text-[15px] font-medium hover:bg-gold transition-colors duration-300"
          >
            Join the Waitlist
          </a>
          <a
            href="#how-it-works"
            className="px-8 py-3.5 rounded-pill border border-[rgba(255,255,255,0.2)] text-[var(--text-on-dark)] text-[15px] font-medium hover:border-gold hover:text-gold transition-colors duration-300"
          >
            See How It Works
          </a>
        </motion.div>
      </motion.div>
    </section>
  );
}
