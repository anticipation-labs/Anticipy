"use client";

import { useRef, useEffect, useState } from "react";
import { motion, useInView } from "motion/react";
import { ScrollReveal } from "./ScrollReveal";
import { ease } from "@/lib/animation";

export function Pricing() {
  const priceRef = useRef(null);
  const isInView = useInView(priceRef, { once: true, amount: 0.5 });
  const [count, setCount] = useState(0);

  useEffect(() => {
    if (!isInView) return;

    let start = 0;
    const end = 149;
    const duration = 1500;
    const startTime = performance.now();

    function animate(currentTime: number) {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setCount(Math.round(eased * end));
      if (progress < 1) {
        requestAnimationFrame(animate);
      }
    }

    requestAnimationFrame(animate);
  }, [isInView]);

  return (
    <section id="pricing" className="section-cream py-[120px] px-6">
      <div className="max-w-container mx-auto text-center">
        {/* Price headline */}
        <div ref={priceRef}>
          <ScrollReveal>
            <h2
              className="font-serif leading-[1.1]"
              style={{
                fontSize: "clamp(48px, 8vw, 80px)",
                color: "var(--text-on-light)",
              }}
            >
              ${count}.
            </h2>
          </ScrollReveal>
        </div>

        <ScrollReveal delay={0.1}>
          <p
            className="text-[17px] font-light mt-4 mb-16"
            style={{ color: "var(--text-on-light-muted)" }}
          >
            Pendant, chain, charging pad, and your first year. All included.
          </p>
        </ScrollReveal>

        {/* Comparison cards */}
        <div className="flex flex-col md:flex-row gap-6 max-w-2xl mx-auto mb-12">
          <motion.div
            initial={{ opacity: 0, x: -40 }}
            whileInView={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8, ease: ease }}
            viewport={{ once: true }}
            className="flex-1 p-8 rounded-card text-center"
            style={{
              background: "var(--cream-muted)",
            }}
          >
            <p
              className="text-[13px] uppercase tracking-[0.15em] font-medium mb-4"
              style={{ color: "var(--text-on-light-muted)" }}
            >
              Personal Assistant
            </p>
            <p
              className="font-serif text-[42px] leading-[1.1]"
              style={{ color: "var(--text-on-light)" }}
            >
              $45,000
            </p>
            <p
              className="text-[15px] font-light mt-2"
              style={{ color: "var(--text-on-light-muted)" }}
            >
              per year
            </p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, x: 40 }}
            whileInView={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8, ease: ease }}
            viewport={{ once: true }}
            className="flex-1 p-8 rounded-card text-center"
            style={{
              background: "var(--dark)",
              boxShadow: "0 20px 60px rgba(0,0,0,0.15)",
            }}
          >
            <p className="text-[13px] uppercase tracking-[0.15em] font-medium mb-4 text-gold">
              Anticipy
            </p>
            <p className="font-serif text-[42px] leading-[1.1] text-[var(--text-on-dark)]">
              $149
            </p>
            <p className="text-[15px] font-light mt-2 text-[var(--text-on-dark-muted)]">
              first year included, then $99/yr
            </p>
          </motion.div>
        </div>

        <ScrollReveal delay={0.3}>
          <p
            className="text-[17px] font-light"
            style={{ color: "var(--text-on-light-muted)" }}
          >
            You spend more on subscriptions you forget to cancel.
          </p>
          <p
            className="text-[12px] font-light mt-4"
            style={{ color: "var(--text-on-light-muted)", opacity: 0.5 }}
          >
            Pricing and features may change before shipping. Full refund available at any time before delivery.
          </p>
        </ScrollReveal>
      </div>
    </section>
  );
}
