"use client";

import { FormEvent, useEffect, useState } from "react";
import { motion } from "motion/react";
import { ease } from "@/lib/animation";

type FormState = "idle" | "loading" | "error";

export function PurchaseForm({ canceled }: { canceled: boolean }) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [marketingOptIn, setMarketingOptIn] = useState(true);
  const [state, setState] = useState<FormState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [showCanceled, setShowCanceled] = useState(canceled);

  useEffect(() => {
    if (canceled) {
      setShowCanceled(true);
      const timer = setTimeout(() => setShowCanceled(false), 8000);
      return () => clearTimeout(timer);
    }
  }, [canceled]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setShowCanceled(false);

    const trimmedEmail = email.trim();
    if (!trimmedEmail || !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(trimmedEmail)) {
      setError("Enter a valid email address.");
      return;
    }
    if (!agreed) {
      setError("Accept the Pre-Order Agreement to continue.");
      return;
    }

    setState("loading");
    try {
      const res = await fetch("/api/pre-orders/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: trimmedEmail,
          name: name.trim(),
          agreementAccepted: true,
          marketingOptIn,
        }),
      });

      const data: { url?: string; error?: string } = await res.json();
      if (!res.ok || !data.url) {
        setState("error");
        setError(data.error || "Could not start checkout. Try again.");
        return;
      }

      window.location.href = data.url;
    } catch {
      setState("error");
      setError("Network error. Try again.");
    }
  };

  return (
    <form
      onSubmit={onSubmit}
      className="flex flex-col gap-4"
      noValidate
    >
      {showCanceled && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease }}
          className="px-4 py-3 rounded-card text-[14px]"
          style={{
            background: "var(--gold-dim)",
            color: "var(--gold)",
            border: "1px solid rgba(200,169,126,0.3)",
          }}
        >
          Checkout canceled. Your card was not charged. You can complete your
          pre-order any time before manufacturing finishes.
        </motion.div>
      )}

      <label className="flex flex-col gap-2">
        <span className="text-[13px] uppercase tracking-[0.12em] font-medium text-[var(--text-on-light-muted)]">
          Name
        </span>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Full name"
          autoComplete="name"
          className="px-5 py-3.5 rounded-pill text-[15px] font-light outline-none transition-colors duration-300 bg-white"
          style={{
            border: "1px solid var(--cream-border)",
            color: "var(--text-on-light)",
          }}
        />
      </label>

      <label className="flex flex-col gap-2">
        <span className="text-[13px] uppercase tracking-[0.12em] font-medium text-[var(--text-on-light-muted)]">
          Email
        </span>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          required
          autoComplete="email"
          className="px-5 py-3.5 rounded-pill text-[15px] font-light outline-none transition-colors duration-300 bg-white"
          style={{
            border: "1px solid var(--cream-border)",
            color: "var(--text-on-light)",
          }}
        />
      </label>

      <label className="flex items-start gap-3 mt-2 text-[14px] text-[var(--text-on-light-muted)] cursor-pointer">
        <input
          type="checkbox"
          checked={agreed}
          onChange={(e) => setAgreed(e.target.checked)}
          className="mt-1 w-4 h-4 accent-[var(--text-on-light)]"
        />
        <span>
          I have read and accept the{" "}
          <a
            href="/pre-orders/agreement"
            target="_blank"
            rel="noopener"
            className="underline hover:text-[var(--text-on-light)]"
          >
            Pre-Order Agreement
          </a>
          , the{" "}
          <a
            href="/terms"
            target="_blank"
            rel="noopener"
            className="underline hover:text-[var(--text-on-light)]"
          >
            Terms of Service
          </a>
          , and the{" "}
          <a
            href="/privacy"
            target="_blank"
            rel="noopener"
            className="underline hover:text-[var(--text-on-light)]"
          >
            Privacy Policy
          </a>
          . I understand the estimated ship date is August 2026 and that pre-order refunds are at Anticipation Labs Inc&apos;s sole discretion except where required by applicable law.
        </span>
      </label>

      <label className="flex items-start gap-3 text-[14px] text-[var(--text-on-light-muted)] cursor-pointer">
        <input
          type="checkbox"
          checked={marketingOptIn}
          onChange={(e) => setMarketingOptIn(e.target.checked)}
          className="mt-1 w-4 h-4 accent-[var(--text-on-light)]"
        />
        <span>
          Send me product updates and shipping notifications. (You can opt out
          at any time.)
        </span>
      </label>

      {error && (
        <p className="text-[14px] text-red-700">{error}</p>
      )}

      <button
        type="submit"
        disabled={state === "loading"}
        className="mt-2 px-8 py-4 rounded-pill text-[16px] font-medium transition-all duration-300 disabled:opacity-60"
        style={{
          background: "var(--dark)",
          color: "var(--cream)",
        }}
      >
        {state === "loading" ? (
          <span className="inline-flex items-center gap-2 justify-center">
            <span className="inline-block w-4 h-4 border-2 border-cream border-t-transparent rounded-full animate-spin" />
            Redirecting to secure checkout
          </span>
        ) : (
          "Pre-order for $149.99"
        )}
      </button>

      <p className="text-[12px] text-[var(--text-on-light-muted)] mt-1 text-center">
        Secured by Stripe. Payment is charged today and locks in $50 off the
        $199 retail price. Free shipping in the US and Canada.
      </p>
    </form>
  );
}
