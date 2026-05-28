"use client";

import { motion } from "motion/react";
import { StaggerContainer, staggerChild } from "./ScrollReveal";

const specs = [
  { value: "8g", label: "Weight" },
  { value: "IP67", label: "Water Resistant" },
  { value: "BLE 5.3", label: "Connectivity" },
  { value: "200mAh", label: "Battery" },
  { value: "nRF5340", label: "Processor" },
];

export function SpecsStrip() {
  return (
    <section className="section-dark px-6">
      <div
        className="max-w-container mx-auto py-16 border-y"
        style={{ borderColor: "var(--dark-border)" }}
      >
        <StaggerContainer
          className="grid grid-cols-2 md:grid-cols-5 gap-8 md:gap-4 text-center"
          stagger={0.1}
        >
          {specs.map((spec) => (
            <motion.div key={spec.label} variants={staggerChild}>
              <p className="font-serif text-[clamp(28px,4vw,36px)] text-[var(--text-on-dark)] leading-[1.2]">
                {spec.value}
              </p>
              <p className="text-[13px] uppercase tracking-[0.15em] text-[var(--text-on-dark-muted)] mt-2 font-medium">
                {spec.label}
              </p>
            </motion.div>
          ))}
        </StaggerContainer>
        <p className="text-[12px] text-[var(--text-on-dark-muted)] font-light text-center mt-6" style={{ opacity: 0.5 }}>
          Specifications are preliminary and subject to change before shipping.
        </p>
      </div>
    </section>
  );
}
