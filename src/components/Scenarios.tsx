"use client";

import { motion } from "motion/react";
import Image from "next/image";
import { NotificationCard } from "./NotificationCard";
import { ScrollReveal, StaggerContainer, staggerChild } from "./ScrollReveal";

const scenarios = [
  {
    image: "/images/scenario-insurance.png",
    title: "Insurance denied your claim.",
    body: "You vented about it over dinner. Didn\u2019t ask anyone to do anything. Twenty minutes later, Anticipy had already filed the dispute, pulled the right policy clause, and emailed you a confirmation.",
    notification:
      "Dispute filed with Aetna. Confirmation sent to your email.",
  },
  {
    image: "/images/scenario-couch.png",
    title: "That free trial you forgot to cancel.",
    body: "You mentioned it to a friend on the couch \u2014 \u201CI keep meaning to cancel that.\u201D Anticipy caught it, logged in, navigated the cancellation maze, and handled it. You never opened the app.",
    notification:
      "Paramount+ canceled before billing. No charge will apply.",
  },
];

export function Scenarios() {
  return (
    <section className="section-dark py-[120px] px-6">
      <div className="max-w-container mx-auto">
        <ScrollReveal className="text-center mb-16">
          <h2 className="font-serif text-section tracking-tight-section leading-[1.15]">
            It heard you. It&apos;s handled.
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light mt-4">
            Two moments. Zero commands.
          </p>
        </ScrollReveal>

        <StaggerContainer
          className="grid grid-cols-1 md:grid-cols-2 gap-8"
          stagger={0.2}
        >
          {scenarios.map((scenario, i) => (
            <motion.div
              key={i}
              variants={staggerChild}
              className="relative rounded-card overflow-hidden aspect-[4/3] flex flex-col justify-end p-8"
            >
              {/* Background image */}
              <Image
                src={scenario.image}
                alt={scenario.title}
                fill
                className="object-cover"
                loading="lazy"
              />
              {/* Gradient overlay */}
              <div
                className="absolute inset-0"
                style={{
                  background:
                    "linear-gradient(to top, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.4) 50%, rgba(0,0,0,0.1) 100%)",
                }}
              />

              {/* Content */}
              <div className="relative z-10">
                <h3 className="font-serif text-[24px] text-white leading-[1.3] mb-3">
                  {scenario.title}
                </h3>
                <p className="text-[15px] text-[rgba(255,255,255,0.7)] font-light leading-[1.6] mb-6">
                  {scenario.body}
                </p>
                <NotificationCard
                  message={scenario.notification}
                  delay={0.5 + i * 0.2}
                />
              </div>
            </motion.div>
          ))}
        </StaggerContainer>
      </div>
    </section>
  );
}
