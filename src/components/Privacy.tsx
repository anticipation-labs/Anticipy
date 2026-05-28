"use client";

import { motion } from "motion/react";
import { ScrollReveal, StaggerContainer, staggerChild } from "./ScrollReveal";

const cards = [
  {
    title: "Encrypted Bluetooth",
    body: "Audio goes from the pendant to your phone over encrypted Bluetooth. It never touches the internet. Not even for a second.",
  },
  {
    title: "On-Device Only",
    body: "Your phone figures out what you need and throws away the audio within seconds. No recording is created. Nothing is stored.",
  },
  {
    title: "Text Only",
    body: "The only thing that leaves your phone is a short text instruction. Never audio. Never a transcript. Never anything you actually said.",
  },
];

export function Privacy() {
  return (
    <section id="privacy" className="section-dark py-[120px] px-6">
      <div className="max-w-container mx-auto">
        <ScrollReveal className="text-center mb-16">
          <h2 className="font-serif text-section tracking-tight-section leading-[1.15]">
            Privacy isn&apos;t a feature.
          </h2>
          <p className="font-serif italic text-subsection text-gold mt-3">
            It&apos;s the architecture.
          </p>
        </ScrollReveal>

        <StaggerContainer
          className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-16"
          stagger={0.15}
        >
          {cards.map((card) => (
            <motion.div
              key={card.title}
              variants={staggerChild}
              className="p-8 rounded-card transition-colors duration-300"
              style={{
                background: "var(--dark-elevated)",
                border: "1px solid var(--dark-border)",
              }}
              whileHover={{
                borderColor: "rgba(200, 169, 126, 0.3)",
              }}
            >
              <h3 className="font-serif text-[22px] text-[var(--text-on-dark)] leading-[1.3] mb-3">
                {card.title}
              </h3>
              <p className="text-[15px] text-[var(--text-on-dark-muted)] font-light leading-[1.6]">
                {card.body}
              </p>
            </motion.div>
          ))}
        </StaggerContainer>

        <ScrollReveal delay={0.3} className="text-center">
          <p className="font-serif italic text-[clamp(20px,3vw,28px)] text-gold">
            Don&apos;t trust us. Test us.
          </p>
        </ScrollReveal>
      </div>
    </section>
  );
}
