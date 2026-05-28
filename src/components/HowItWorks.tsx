"use client";

import { useRef } from "react";
import { motion, useInView } from "motion/react";
import { ScrollReveal, StaggerContainer, staggerChild } from "./ScrollReveal";
import { ease } from "@/lib/animation";

const steps = [
  {
    number: "01",
    title: "Ears",
    body: "The pendant picks up conversation around you and sends it to your phone over encrypted Bluetooth. Nothing goes to the cloud.",
  },
  {
    number: "02",
    title: "Brain",
    body: "Your phone figures out what matters \u2014 a task, a reminder, an annoyance that needs fixing \u2014 and throws away the audio. Gone in seconds. No transcript, no recording.",
  },
  {
    number: "03",
    title: "Hands",
    body: "Our action engine takes it from there. It books, cancels, schedules, disputes, follows up. If something\u2019s high-stakes, it checks with you first. Everything else just gets done.",
  },
];

export function HowItWorks() {
  const headlineRef = useRef(null);
  const headlineInView = useInView(headlineRef, { once: true, amount: 0.5 });

  const headlineWords = "Ears. Brain. Hands.".split(" ");

  return (
    <section id="how-it-works" className="section-cream py-[120px] px-6">
      <div className="max-w-container mx-auto">
        {/* Headline with word-by-word reveal */}
        <div ref={headlineRef} className="text-center mb-20">
          <h2 className="font-serif text-section tracking-tight-section leading-[1.15]">
            {headlineWords.map((word, i) => (
              <motion.span
                key={i}
                className="inline-block mr-[0.25em]"
                initial={{ opacity: 0, y: 40 }}
                animate={headlineInView ? { opacity: 1, y: 0 } : {}}
                transition={{
                  duration: 0.5,
                  delay: i * 0.08,
                  ease: ease,
                }}
                style={{ color: "var(--text-on-light)" }}
              >
                {word}
              </motion.span>
            ))}
          </h2>
        </div>

        {/* Steps */}
        <StaggerContainer
          className="grid grid-cols-1 md:grid-cols-3 gap-12 md:gap-8 relative"
          stagger={0.2}
        >
          {steps.map((step, i) => (
            <motion.div key={step.number} variants={staggerChild}>
              <p
                className="font-serif text-[64px] leading-[1] mb-4"
                style={{ color: "rgba(200, 169, 126, 0.3)" }}
              >
                {step.number}
              </p>
              <h3
                className="font-serif text-[28px] leading-[1.3] mb-4"
                style={{ color: "var(--text-on-light)" }}
              >
                {step.title}
              </h3>
              <p
                className="text-[15px] font-light leading-[1.6]"
                style={{ color: "var(--text-on-light-muted)" }}
              >
                {step.body}
              </p>

              {/* Connector line (hidden on mobile, between steps) */}
              {i < steps.length - 1 && (
                <div className="hidden md:block absolute top-[40px]" style={{
                  left: `${((i + 1) * 100) / 3}%`,
                  transform: "translateX(-50%)",
                  width: "calc(100% / 3 - 60px)",
                  height: "1px",
                  background: "var(--cream-border)",
                }} />
              )}
            </motion.div>
          ))}
        </StaggerContainer>
      </div>
    </section>
  );
}
