"use client";

import { useEffect, useRef, useState, FormEvent } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

type FormState = "idle" | "loading" | "success" | "duplicate" | "error";

export function Close() {
  const rootRef = useRef<HTMLDivElement>(null);
  const [email, setEmail] = useState("");
  const [state, setState] = useState<FormState>("idle");

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.fromTo(
        ".close-anim",
        { opacity: 0, y: 40 },
        {
          opacity: 1,
          y: 0,
          duration: 1,
          ease: "power3.out",
          stagger: 0.14,
          scrollTrigger: {
            trigger: rootRef.current,
            start: "top 60%",
            toggleActions: "play none none reverse",
          },
        }
      );
    }, rootRef);
    return () => ctx.revert();
  }, []);

  const handleWaitlist = async (e: FormEvent) => {
    e.preventDefault();
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return;
    setState("loading");
    try {
      const res = await fetch("/api/waitlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      if (res.ok) setState("success");
      else if (res.status === 409) setState("duplicate");
      else setState("error");
    } catch {
      setState("error");
    }
  };

  return (
    <section
      ref={rootRef}
      id="waitlist"
      className="relative section-dark overflow-hidden"
    >
      <video
        className="absolute inset-0 w-full h-full object-cover opacity-40"
        src="/videos/night-charge.mp4"
        autoPlay
        muted
        loop
        playsInline
        aria-hidden
      />
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(12,12,12,0.35) 0%, rgba(12,12,12,0.95) 100%)",
        }}
      />

      <div className="relative z-10 max-w-2xl mx-auto text-center px-6 py-[160px]">
        <h2 className="close-anim font-serif text-[clamp(34px,5.5vw,64px)] leading-[1.08] text-[var(--text-on-dark)]">
          Stop carrying
          <br />
          <span className="italic">everything alone.</span>
        </h2>

        <div className="close-anim mt-12">
          <a
            href="/pre-orders/purchase"
            className="inline-block w-full sm:w-auto px-14 py-4.5 rounded-pill text-[17px] font-medium transition-all duration-300 hover:scale-[1.02]"
            style={{
              background: "var(--text-on-dark)",
              color: "var(--dark)",
              padding: "18px 56px",
            }}
          >
            Claim yours &mdash; $149.99
          </a>
        </div>

        <p className="close-anim text-[13px] text-[var(--text-on-dark-muted)] mt-5">
          $149.99 now, $199 at launch &middot; Free shipping (US &amp; Canada) &middot;
          Ships Q4 2026 &middot; Change your mind? One email, full refund
        </p>

        <div className="close-anim flex items-center justify-center gap-8 mt-10">
          <a
            href="/book"
            className="text-[15px] text-[var(--text-on-dark)] underline underline-offset-4 decoration-[rgba(245,240,235,0.4)] hover:opacity-80 transition-opacity"
          >
            Book a call with us
          </a>
          <span className="text-[var(--dark-border)]">&middot;</span>
          <a
            href="#join-waitlist"
            className="text-[15px] text-[var(--text-on-dark)] underline underline-offset-4 decoration-[rgba(245,240,235,0.4)] hover:opacity-80 transition-opacity"
          >
            Join the waitlist
          </a>
        </div>

        <div id="join-waitlist" className="close-anim mt-14">
          {state === "success" ? (
            <p className="text-[var(--text-on-dark)] text-[16px]">You&apos;re on the list.</p>
          ) : state === "duplicate" ? (
            <p className="text-[var(--text-on-dark-muted)] text-[16px]">
              You&apos;re already on the list.
            </p>
          ) : (
            <form
              onSubmit={handleWaitlist}
              className="flex flex-col sm:flex-row gap-3 max-w-md mx-auto"
            >
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Your email"
                required
                className="flex-1 px-6 py-3.5 rounded-pill text-[15px] font-light outline-none"
                style={{
                  background: "rgba(22,22,22,0.85)",
                  border: "1px solid var(--dark-border)",
                  color: "var(--text-on-dark)",
                }}
              />
              <button
                type="submit"
                disabled={state === "loading"}
                className="px-8 py-3.5 rounded-pill text-[15px] font-medium disabled:opacity-60 transition-opacity duration-300 hover:opacity-85"
                style={{
                  background: "rgba(245,240,235,0.12)",
                  border: "1px solid var(--dark-border)",
                  color: "var(--text-on-dark)",
                }}
              >
                {state === "loading" ? "\u2026" : "Join"}
              </button>
            </form>
          )}
          {state === "error" && (
            <p className="text-[var(--text-on-dark-muted)] text-[14px] mt-3">
              Something went wrong. Try again.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
