"use client";

import { useState, FormEvent } from "react";
import { motion } from "motion/react";
import { ease } from "@/lib/animation";
import Link from "next/link";

type FormState = "idle" | "loading" | "success" | "duplicate" | "error";

export default function WaitlistPage() {
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
        body: JSON.stringify({ email }),
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
    <div
      className="min-h-screen flex flex-col items-center justify-center px-6"
      style={{ background: "var(--dark)" }}
    >
      <motion.div
        className="max-w-lg w-full text-center"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, ease }}
      >
        {/* Logo */}
        <Link href="/" className="inline-block mb-12">
          <span className="font-serif text-[28px] text-[var(--text-on-dark)] hover:text-gold transition-colors">
            Anticipy
          </span>
        </Link>

        {state === "success" ? (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.5, ease }}
          >
            <div className="w-16 h-16 rounded-full mx-auto mb-6 flex items-center justify-center" style={{ background: "var(--gold-dim)" }}>
              <svg
                className="w-8 h-8 text-gold"
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
            </div>
            <h1 className="font-serif text-[clamp(32px,5vw,48px)] text-[var(--text-on-dark)] leading-[1.15] mb-4">
              You&apos;re on the list.
            </h1>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.7] mb-8">
              We&apos;ll reach out when Anticipy is ready to ship. In the meantime,
              you can close this tab and go live your life — that&apos;s kind of the whole point.
            </p>
            <Link
              href="/"
              className="text-gold text-[15px] hover:underline"
            >
              Back to anticipy.ai
            </Link>
          </motion.div>
        ) : (
          <>
            <h1 className="font-serif italic text-[clamp(36px,6vw,56px)] text-[var(--text-on-dark)] leading-[1.1] mb-4">
              Vibe your life.
            </h1>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.7] mb-3">
              Anticipy is an AI wearable that listens to your day and handles
              what needs handling — booking, canceling, disputing, scheduling — without
              you lifting a finger.
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.7] mb-10">
              We&apos;re building it now. Leave your email and we&apos;ll let you know
              the moment it&apos;s ready.
            </p>

            {state === "duplicate" ? (
              <div className="text-[var(--text-on-dark-muted)] text-[17px] mb-6">
                <p>You&apos;re already on the list — we&apos;ve got your email.</p>
                <Link
                  href="/"
                  className="text-gold text-[15px] hover:underline mt-4 inline-block"
                >
                  Learn more about Anticipy
                </Link>
              </div>
            ) : (
              <form
                onSubmit={handleSubmit}
                className="flex flex-col sm:flex-row gap-3 mb-6"
              >
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="your@email.com"
                  required
                  className="flex-1 px-6 py-4 rounded-pill text-[15px] font-light outline-none transition-colors duration-300 focus:border-gold"
                  style={{
                    background: "var(--dark-elevated)",
                    border: "1px solid var(--dark-border)",
                    color: "var(--text-on-dark)",
                  }}
                />
                <button
                  type="submit"
                  disabled={state === "loading"}
                  className="px-8 py-4 rounded-pill text-[15px] font-medium transition-all duration-300 hover:bg-gold disabled:opacity-60"
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
              </form>
            )}

            {state === "error" && (
              <p className="text-red-400/70 text-[15px] mb-4">
                Something went wrong. Give it another try.
              </p>
            )}

            <p className="text-[13px] text-[var(--text-on-dark-muted)] font-light mt-8">
              $149 · Brushed titanium · 8 grams · First year of service included · Specifications subject to change
            </p>
          </>
        )}
      </motion.div>

      {/* Footer */}
      <div className="absolute bottom-8 text-center">
        <p className="text-[13px] text-[var(--text-on-dark-muted)]">
          &copy; 2026 Anticipy
        </p>
      </div>
    </div>
  );
}
