"use client";

import { FormEvent, useEffect, useState } from "react";
import { motion } from "motion/react";
import { ease } from "@/lib/animation";
import {
  capture,
  identifyByEmail,
  attributionIds,
  emailDomainClass,
} from "@/lib/analytics";

type FormState = "idle" | "loading" | "error";

export function PurchaseForm({ canceled }: { canceled: boolean }) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [ageConfirmed, setAgeConfirmed] = useState(false);
  const [agreed, setAgreed] = useState(false);
  const [marketingOptIn, setMarketingOptIn] = useState(false);
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

  // Top of the checkout funnel. Emitted once on mount so the form-level
  // drop-off (reached the form -> submitted an email) is measurable
  // independently of the redirect to Stripe.
  useEffect(() => {
    capture("checkout_started", {
      entry_point: "purchase_page",
      price_shown_cents: 14999,
      returned_canceled: canceled,
    });
    if (canceled) {
      capture("checkout_returned_canceled", { entry_point: "purchase_page" });
    }
    // Intentionally mount-only: re-firing on `canceled` flips would
    // double-count a single visit to the form.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /**
   * Fires when the visitor leaves the email field with something in it.
   *
   * Deliberately carries NO address and NO local part — only whether it
   * parses and what class of domain it is. Capturing a typed-but-unsubmitted
   * address is the Popa v. Harriet Carter fact pattern, and under PostHog's
   * identified_only model a half-typed address would become a permanent
   * distinct_id that cannot be rewritten later. This gives the abandonment
   * signal without either problem.
   */
  const onEmailBlur = () => {
    const v = email.trim();
    if (!v) return;
    capture("checkout_email_field_completed", {
      form: "purchase",
      email_valid: /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v),
      email_domain_class: emailDomainClass(v),
      fields_completed_count: [name.trim(), v].filter(Boolean).length,
    });
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setShowCanceled(false);

    const trimmedEmail = email.trim();
    if (!trimmedEmail || !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(trimmedEmail)) {
      setError("Enter a valid email address.");
      capture("checkout_validation_failed", { field: "email", reason: "invalid_format" });
      return;
    }
    if (!ageConfirmed) {
      setError("You must confirm that you are at least 18 years old.");
      capture("checkout_validation_failed", { field: "age_confirmed", reason: "unchecked" });
      return;
    }
    if (!agreed) {
      setError("Accept the Pre-Order Agreement to continue.");
      capture("checkout_validation_failed", { field: "agreement", reason: "unchecked" });
      return;
    }

    setState("loading");

    // Identify on SUBMIT — never earlier. This is the moment the visitor
    // hands over the address of their own accord, and it is what collapses
    // every anonymous event they have generated so far onto a real person.
    await identifyByEmail(
      trimmedEmail,
      {
        marketing_consent: marketingOptIn === true,
        marketing_consent_at: new Date().toISOString(),
        marketing_consent_source: "purchase_form",
        marketing_consent_copy_version: "v1",
        lifecycle_stage: "checkout_started",
      },
      {
        first_seen_at: new Date().toISOString(),
        first_intent: "purchase",
      }
    );

    capture("checkout_email_submitted", {
      email_domain_class: emailDomainClass(trimmedEmail),
      has_name: Boolean(name.trim()),
      marketing_opt_in: marketingOptIn === true,
    });

    // Carried into Stripe metadata so the webhook can attribute the paid
    // order to this same person server-side. Client-side purchase events are
    // routinely blocked; the webhook is not.
    const { distinctId, sessionId } = attributionIds();

    try {
      const res = await fetch("/api/pre-orders/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: trimmedEmail,
          name: name.trim(),
          ageConfirmed: true,
          agreementAccepted: true,
          marketingOptIn,
          posthogDistinctId: distinctId,
          posthogSessionId: sessionId,
        }),
      });

      const data: { url?: string; error?: string } = await res.json();
      if (!res.ok || !data.url) {
        setState("error");
        setError(data.error || "Could not start checkout. Try again.");
        capture("checkout_validation_failed", {
          field: "server",
          reason: data.error?.slice(0, 120) || `http_${res.status}`,
        });
        return;
      }

      // Last event we control before the visitor leaves for Stripe's domain.
      // The gap between this and order_paid from the webhook is the true
      // hosted-checkout drop-off, which nothing client-side can observe.
      capture("checkout_redirected_to_stripe", {
        email_domain_class: emailDomainClass(trimmedEmail),
      });

      window.location.href = data.url;
    } catch {
      setState("error");
      setError("Network error. Try again.");
      capture("checkout_validation_failed", { field: "network", reason: "fetch_failed" });
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
          onBlur={onEmailBlur}
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
          checked={ageConfirmed}
          onChange={(e) => setAgeConfirmed(e.target.checked)}
          className="mt-1 w-4 h-4 accent-[var(--text-on-light)]"
        />
        <span>
          I confirm I am at least 18 years old and have the legal capacity to
          enter a binding contract in my jurisdiction.
        </span>
      </label>

      <label className="flex items-start gap-3 text-[14px] text-[var(--text-on-light-muted)] cursor-pointer">
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
          . I understand the estimated ship date is Q4 2026, that
          refunds are at Anticipation Labs Inc&apos;s sole discretion except
          where required by applicable law, and that the Pre-Order Agreement
          contains a binding arbitration clause and class action waiver in
          Section 14 that affect my legal rights (with a 30-day opt-out).
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
          (Optional) Send me product updates and shipping notifications. You
          can unsubscribe at any time using the link in every email.
        </span>
      </label>

      {error && (
        <p className="text-[14px] text-red-700">{error}</p>
      )}

      <button
        type="submit"
        disabled={state === "loading"}
        data-attr="preorder-submit"
        data-cta-id="preorder_submit"
        data-cta-location="hero"
        data-cta-type="preorder"
        data-cta-style="primary"
        data-cta-label="Continue to payment"
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
