"use client";

import { motion } from "motion/react";
import Image from "next/image";
import { ScrollReveal } from "./ScrollReveal";
import { ease } from "@/lib/animation";

export function ChargingSection() {
  return (
    <section className="section-dark overflow-hidden">
      <div className="grid grid-cols-1 md:grid-cols-2 min-h-[600px]">
        {/* Text */}
        <div className="flex flex-col justify-center px-8 md:px-16 lg:px-20 py-16 md:py-20">
          <ScrollReveal>
            <h2
              className="font-serif text-section tracking-tight-section leading-[1.15] mb-6"
              style={{ color: "var(--text-on-dark)" }}
            >
              You sleep.
              <br />
              It charges.
            </h2>
          </ScrollReveal>

          <ScrollReveal delay={0.15}>
            <p className="text-[17px] leading-[1.7] font-light mb-4 text-[var(--text-on-dark-muted)]">
              No base. No cables. No alignment. The pendant charges wirelessly
              as long as you&apos;re within 15 feet of the charging pad — so it tops
              up while you sleep, watch TV, or sit at your desk.
            </p>
          </ScrollReveal>

          <ScrollReveal delay={0.3}>
            <p className="text-[15px] font-light text-[var(--text-on-dark-muted)]">
              Resonant wireless charging pad included.
            </p>
          </ScrollReveal>
        </div>

        {/* Image */}
        <motion.div
          initial={{ opacity: 0, x: 60 }}
          whileInView={{ opacity: 1, x: 0 }}
          transition={{ duration: 1, ease: ease }}
          viewport={{ once: true, amount: 0.3 }}
          className="relative h-[400px] md:h-auto"
        >
          <Image
            src="/images/nightstand.png"
            alt="Anticipy charging base on nightstand"
            fill
            className="object-cover"
            loading="lazy"
          />
          {/* LED glow on charging base */}
          <div
            className="absolute led-pulse pointer-events-none"
            style={{
              bottom: "35%",
              left: "40%",
              width: "30px",
              height: "30px",
              borderRadius: "50%",
              background:
                "radial-gradient(circle, rgba(255,220,180,0.5) 0%, rgba(255,220,180,0) 70%)",
            }}
          />
        </motion.div>
      </div>
    </section>
  );
}
