"use client";

import { useRef, useEffect, useState } from "react";
import Link from "next/link";
import { motion, useInView } from "motion/react";
import { ScrollReveal } from "./ScrollReveal";
import { ease } from "@/lib/animation";

const TARGET_DOLLARS = 149;
const TARGET_CENTS = 99;
const RETAIL_PRICE = 199;

export function Pricing() {
  const priceRef = useRef(null);
  const isInView = useInView(priceRef, { once: true, amount: 0.5 });
  const [count, setCount] = useState(0);

  useEffect(() => {
    if (!isInView) return;

    const duration = 1500;
    const startTime = performance.now();

    function animate(currentTime: number) {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setCount(Math.round(eased * TARGET_DOLLARS));
      if (progress < 1) {
        requestAnimationFrame(animate);
      }
    }

    requestAnimationFrame(animate);
  }, [isInView]);

  return (
    <section id="pricing" className="section-cream py-[120px] px-6">
      <div className="max-w-container mx-auto text-center">
        <ScrollReveal>
          <span
            className="inline-flex items-center gap-2 px-3 py-1 rounded-pill text-[11px] uppercase tracking-[0.15em] font-medium mb-6"
            style={{
              background: "var(--gold-dim)",
              color: "var(--gold)",
            }}
          >
            Pre-order &middot; $50 off retail
          </span>
        </ScrollReveal>

        <div ref={priceRef}>
          <ScrollReveal>
            <div className="flex items-baseline justify-center gap-4 flex-wrap">
              <h2
                className="font-serif leading-[1.05]"
                style={{
                  fontSize: "clamp(56px, 9vw, 96px)",
                  color: "var(--text-on-light)",
                }}
              >
                ${count}
                <span style={{ fontSize: "0.5em" }}>
                  .{count === TARGET_DOLLARS ? TARGET_CENTS : "00"}
                </span>
              </h2>
              <span
                className="text-[15px] md:text-[17px]"
                style={{ color: "var(--text-on-light-muted)" }}
              >
                ${RETAIL_PRICE} at launch
              </span>
            </div>
          </ScrollReveal>
        </div>

        <ScrollReveal delay={0.1}>
          <p
            className="text-[17px] font-light mt-4 mb-12"
            style={{ color: "var(--text-on-light-muted)" }}
          >
            Pendant, chain, and charging pad. All included. Free shipping in the US and Canada.
          </p>
        </ScrollReveal>

        <ScrollReveal delay={0.2}>
          <div className="flex flex-col sm:flex-row gap-3 justify-center mb-12">
            <Link
              href="/pre-orders/purchase"
              className="px-8 py-4 rounded-pill text-[15px] font-medium transition-colors duration-300 hover:bg-gold"
              style={{
                background: "var(--dark)",
                color: "var(--cream)",
              }}
            >
              Pre-order for $149.99
            </Link>
            <Link
              href="/waitlist"
              className="px-8 py-4 rounded-pill text-[15px] font-medium transition-colors duration-300"
              style={{
                background: "var(--cream-muted)",
                color: "var(--text-on-light)",
                border: "1px solid var(--cream-border)",
              }}
            >
              Or join the free waitlist
            </Link>
          </div>
        </ScrollReveal>

        <div className="flex flex-col md:flex-row gap-6 max-w-2xl mx-auto mb-12">
          <motion.div
            initial={{ opacity: 0, x: -40 }}
            whileInView={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8, ease: ease }}
            viewport={{ once: true }}
            className="flex-1 p-8 rounded-card text-center"
            style={{ background: "var(--cream-muted)" }}
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
              Anticipy pre-order
            </p>
            <p className="font-serif text-[42px] leading-[1.1] text-[var(--text-on-dark)]">
              $149.99
            </p>
            <p className="text-[15px] font-light mt-2 text-[var(--text-on-dark-muted)]">
              $149.99 now, $199 at launch
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
            style={{
              color: "var(--text-on-light-muted)",
              opacity: 0.5,
            }}
          >
            Pricing and specifications are preliminary and may change before shipping. Estimated ship date Q4 2026. Refunds at Anticipation Labs Inc&apos;s sole discretion except where required by applicable law.{" "}
            <Link
              href="/pre-orders/agreement"
              className="underline hover:opacity-100"
            >
              Read the Pre-Order Agreement
            </Link>
            .
          </p>
        </ScrollReveal>
      </div>
    </section>
  );
}
