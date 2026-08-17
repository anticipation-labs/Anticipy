"use client";

import { useEffect, useRef, useState } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

const FAQS: { q: string; a: string }[] = [
  {
    q: "What exactly do I get for $149.99?",
    a: "The titanium pendant, the chain, and the wireless charging pad. Free shipping in the US and Canada. $199 at launch — $149.99 if you claim it now.",
  },
  {
    q: "When does it ship?",
    a: "Q4 2026. You'll get your order number immediately, build updates as we go, and tracking the moment yours leaves the line.",
  },
  {
    q: "What if I change my mind?",
    a: "Full refund, any time before your unit ships, no questions asked. One email and the money is back on your card.",
  },
  {
    q: "Is it always listening? What about privacy?",
    a: "It hears you the way a good assistant does — and follows your rules. Your audio never leaves the device without a rule you set, every action is previewed before it happens, and every result is independently verified. You can see, export, or delete everything.",
  },
  {
    q: "What do I say when someone asks if it\u2019s recording them?",
    a: "The truth: Anticipy is there for your own promises, not other people\u2019s conversations. Your audio never leaves the device without a rule you set, nothing is ever posted or shared, and nothing happens without your explicit approval. And when you\u2019d rather it not listen at all, take it off \u2014 it\u2019s a pendant, not an implant.",
  },
  {
    q: "What happens right after I pay?",
    a: "Stripe processes the payment, you get a confirmation email with your order number, and you're locked in at $149.99 — $50 under the $199 retail price. Then we get back to building yours.",
  },
];

export function Faq() {
  const rootRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState<number | null>(0);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.fromTo(
        ".faq-anim",
        { opacity: 0, y: 32 },
        {
          opacity: 1,
          y: 0,
          duration: 0.9,
          ease: "power3.out",
          stagger: 0.1,
          scrollTrigger: {
            trigger: rootRef.current,
            start: "top 70%",
            toggleActions: "play none none reverse",
          },
        }
      );
    }, rootRef);
    return () => ctx.revert();
  }, []);

  return (
    <section ref={rootRef} className="relative section-cream px-6 py-[120px]">
      <div className="max-w-2xl mx-auto">
        <h2 className="faq-anim font-serif text-[clamp(28px,4vw,44px)] leading-[1.1] text-[var(--text-on-light)] text-center">
          The questions that
          <span className="italic"> matter.</span>
        </h2>

        <div className="mt-12">
          {FAQS.map((f, i) => (
            <div
              key={f.q}
              className="faq-anim border-b"
              style={{ borderColor: "var(--cream-border)" }}
            >
              <button
                type="button"
                onClick={() => setOpen(open === i ? null : i)}
                className="w-full flex items-center justify-between gap-6 py-6 text-left"
                aria-expanded={open === i}
              >
                <span className="text-[17px] text-[var(--text-on-light)]">
                  {f.q}
                </span>
                <span
                  className="text-bronze text-[20px] leading-none transition-transform duration-300"
                  style={{
                    transform: open === i ? "rotate(45deg)" : "rotate(0deg)",
                  }}
                >
                  +
                </span>
              </button>
              <div
                className="overflow-hidden transition-all duration-500 ease-out"
                style={{
                  maxHeight: open === i ? 320 : 0,
                  opacity: open === i ? 1 : 0,
                }}
              >
                <p className="pb-7 text-[15px] leading-relaxed text-[var(--text-on-light-muted)] max-w-xl">
                  {f.a}
                </p>
              </div>
            </div>
          ))}
        </div>

        <div
          className="faq-anim mt-16 rounded-2xl p-8 flex flex-col sm:flex-row items-center gap-7"
          style={{
            background: "#FFFFFF",
            border: "1px solid var(--cream-border)",
          }}
        >
          <div className="text-center sm:text-left">
            <p className="text-[15px] leading-relaxed text-[var(--text-on-light)]">
              &ldquo;I kept telling people I&apos;d send things &mdash; and kept
              finding those promises dead in my notes app three weeks later. So
              I built the thing I needed: something that hears the promise and
              walks it to done. A year of prototypes taught me the hard part
              isn&apos;t hearing you &mdash; it&apos;s proving the thing actually
              happened. If Anticipy isn&apos;t everything I&apos;m promising you
              here, email me and I&apos;ll refund you myself.&rdquo;
            </p>
            <p className="mt-3 text-[13px] uppercase tracking-[0.16em] text-[var(--text-on-light-muted)]">
              Omar &middot; Founder, Anticipy &middot;{" "}
              <a
                href="https://calendar.app.google/QnCVQxa9Aj3x8QKD7"
                target="_blank"
                rel="noopener noreferrer"
                className="underline underline-offset-4 decoration-[rgba(138,107,68,0.45)] hover:text-bronze transition-colors normal-case tracking-normal"
              >
                Book a call with me
              </a>
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
