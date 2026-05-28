"use client";

import { motion } from "motion/react";
import Image from "next/image";
import { ScrollReveal } from "./ScrollReveal";
import { ease } from "@/lib/animation";

export function Colorways() {
  return (
    <section className="section-dark py-[120px] px-6">
      <div className="max-w-container mx-auto text-center">
        <ScrollReveal>
          <h2 className="font-serif text-section tracking-tight-section leading-[1.15]">
            Two finishes. One intention.
          </h2>
        </ScrollReveal>

        <ScrollReveal delay={0.1}>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light mt-4 mb-12">
            Pick the one that matches what you already wear.
          </p>
        </ScrollReveal>

        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          whileInView={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.8, delay: 0.2, ease: ease }}
          viewport={{ once: true, amount: 0.3 }}
          className="max-w-[1000px] mx-auto"
        >
          <Image
            src="/images/colorways.png"
            alt="Anticipy pendant in silver and gold finishes"
            width={1000}
            height={500}
            className="w-full h-auto rounded-image"
            loading="lazy"
          />
        </motion.div>
      </div>
    </section>
  );
}
