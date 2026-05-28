"use client";

import { useState, FormEvent } from "react";
import { motion } from "motion/react";
import { ScrollReveal } from "./ScrollReveal";
import { ease } from "@/lib/animation";

type FormState = "idle" | "loading" | "success" | "duplicate" | "error";

export function WaitlistCTA() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [state, setState] = useState<FormState>("idle");

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return;

    setState("loading");

    try {
      const res = await fetch("/api/waitlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, name: name.trim() || undefined }),
      });

      if (res.ok) {
        setState("success");
      } else if (res.status === 409) {
        setState("duplicate");
      } else {
        setState("error");
      }
    } catch {
      setState("error");
    }
  };

  return (
    <section id="waitlist" className="section-dark py-[120px] px-6">
      <div className="max-w-container mx-auto text-center">
        {/* Gold divider */}
        <ScrollReveal>
          <motion.div
            initial={{ width: 0 }}
            whileInView={{ width: 60 }}
            transition={{ duration: 0.8, ease: ease }}
            viewport={{ once: true }}
            className="h-[1px] mx-auto mb-12"
            style={{ background: "rgba(200, 169, 126, 0.4)" }}
          />
        </ScrollReveal>

        <ScrollReveal>
          <h2 className="font-serif italic text-hero tracking-tight-hero leading-[1.05] text-[var(--text-on-dark)]">
            Vibe your life.
          </h2>
        </ScrollReveal>

        <ScrollReveal delay={0.1}>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light mt-6 mb-10">
            We&apos;re building it now. Drop your email — we&apos;ll let you know the moment it&apos;s ready.
          </p>
        </ScrollReveal>

        <ScrollReveal delay={0.2}>
          {state === "success" ? (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="flex items-center justify-center gap-3"
            >
              <svg
                className="w-5 h-5 text-gold"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M5 13l4 4L19 7"
                />
              </svg>
              <span className="text-gold text-[17px]">
                You&apos;re on the list.
              </span>
            </motion.div>
          ) : state === "duplicate" ? (
            <p className="text-[var(--text-on-dark-muted)] text-[17px]">
              You&apos;re already on the list.
            </p>
          ) : (
            <form
              onSubmit={handleSubmit}
              className="flex flex-col gap-3 max-w-md mx-auto"
            >
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Your name"
                className="w-full px-6 py-3.5 rounded-pill text-[15px] font-light outline-none transition-colors duration-300"
                style={{
                  background: "var(--dark-elevated)",
                  border: "1px solid var(--dark-border)",
                  color: "var(--text-on-dark)",
                }}
              />
              <div className="flex flex-col sm:flex-row gap-3">
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Enter your email"
                required
                className="flex-1 px-6 py-3.5 rounded-pill text-[15px] font-light outline-none transition-colors duration-300"
                style={{
                  background: "var(--dark-elevated)",
                  border: "1px solid var(--dark-border)",
                  color: "var(--text-on-dark)",
                }}
              />
              <button
                type="submit"
                disabled={state === "loading"}
                className="px-8 py-3.5 rounded-pill text-[15px] font-medium transition-colors duration-300 disabled:opacity-60"
                style={{
                  background: "var(--text-on-dark)",
                  color: "var(--dark)",
                }}
              >
                {state === "loading" ? (
                  <span className="inline-block w-5 h-5 border-2 border-dark border-t-transparent rounded-full animate-spin" />
                ) : (
                  "Join Waitlist"
                )}
              </button>
              </div>
            </form>
          )}

          {state === "error" && (
            <p className="text-[var(--text-on-dark-muted)] text-[15px] mt-4">
              Something went wrong. Try again.
            </p>
          )}
        </ScrollReveal>

        <ScrollReveal delay={0.3}>
          <p className="text-[15px] text-[var(--text-on-dark-muted)] font-light mt-12">
            omar@anticipy.ai · anticipy.ai
          </p>
        </ScrollReveal>
      </div>
    </section>
  );
}
