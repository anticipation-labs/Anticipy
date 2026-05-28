"use client";

import { motion } from "motion/react";
import Image from "next/image";
import { ScrollReveal } from "./ScrollReveal";
import { ease } from "@/lib/animation";

export function SizeComparison() {
  return (
    <section className="section-cream py-[120px] md:py-[120px] px-6">
      <div className="max-w-container mx-auto text-center">
        <ScrollReveal>
          <h2
            className="font-serif text-section tracking-tight-section leading-[1.15]"
            style={{ color: "var(--text-on-light)" }}
          >
            Lighter than a house key.
          </h2>
        </ScrollReveal>

        <ScrollReveal delay={0.1}>
          <p
            className="text-[17px] leading-[1.7] font-light mt-4 mb-12"
            style={{ color: "var(--text-on-light-muted)" }}
          >
            People won&apos;t notice it. That&apos;s the point.
          </p>
        </ScrollReveal>

        <motion.div
          initial={{ opacity: 0, scale: 0.97 }}
          whileInView={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.8, delay: 0.2, ease: ease }}
          viewport={{ once: true, amount: 0.3 }}
          className="max-w-[800px] mx-auto"
        >
          <Image
            src="/images/size-compare.png"
            alt="Size comparison — pendant next to quarter, AirPod, and key"
            width={800}
            height={500}
            className="w-full h-auto rounded-image"
            loading="lazy"
          />
        </motion.div>
      </div>
    </section>
  );
}
