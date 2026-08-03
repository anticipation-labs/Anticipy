"use client";

import { useEffect, useRef } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

const SPOKEN =
  "\u201CI\u2019ll send Marcus the meeting notes tonight \u2014 actually, don\u2019t include the budget slide.\u201D";

const STAGE_LABELS = [
  "You said it out loud",
  "Anticipy caught it",
  "It drafted the email",
  "You approved with one tap",
  "Done \u2014 and proven",
];

export function LiveDemo() {
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      const tl = gsap.timeline({
        scrollTrigger: {
          trigger: rootRef.current,
          start: "top top",
          end: "+=3200",
          scrub: 0.4,
          pin: true,
        },
      });

      // Stage 0: spoken words appear over waveform
      tl.fromTo(
        ".ld-spoken",
        { opacity: 0, y: 16 },
        { opacity: 1, y: 0, duration: 1 }
      )
        .fromTo(".ld-wave span", { scaleY: 0.2 }, { scaleY: 1, stagger: 0.02, duration: 0.5 }, "<")
        .to(".ld-label-0", { opacity: 1, duration: 0.4 }, "<");

      // Stage 1: caught card
      tl.to(".ld-label-0", { opacity: 0.35, duration: 0.3 }, "+=0.4")
        .fromTo(".ld-caught", { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.8 })
        .to(".ld-label-1", { opacity: 1, duration: 0.4 }, "<");

      // Stage 2: draft email
      tl.to(".ld-label-1", { opacity: 0.35, duration: 0.3 }, "+=0.4")
        .fromTo(".ld-draft", { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.8 })
        .fromTo(
          ".ld-strike",
          { backgroundSize: "0% 1px" },
          { backgroundSize: "100% 1px", duration: 0.5 }
        )
        .to(".ld-label-2", { opacity: 1, duration: 0.4 }, "<");

      // Stage 3: approve tap
      tl.to(".ld-label-2", { opacity: 0.35, duration: 0.3 }, "+=0.4")
        .fromTo(".ld-approve", { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.5 })
        .to(".ld-approve-btn", {
          scale: 0.94,
          background: "var(--gold)",
          color: "var(--dark)",
          duration: 0.3,
        })
        .to(".ld-approve-btn", { scale: 1, duration: 0.2 })
        .to(".ld-label-3", { opacity: 1, duration: 0.4 }, "<");

      // Stage 4: receipt
      tl.to(".ld-label-3", { opacity: 0.35, duration: 0.3 }, "+=0.4")
        .to(".ld-caught", { opacity: 0.25, duration: 0.4 }, "<")
        .to(".ld-draft", { opacity: 0.25, duration: 0.4 }, "<")
        .to(".ld-approve", { opacity: 0.25, duration: 0.4 }, "<")
        .fromTo(".ld-receipt", { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.8 })
        .fromTo(
          ".ld-check",
          { strokeDashoffset: 48 },
          { strokeDashoffset: 0, duration: 0.6 }
        )
        .to(".ld-label-4", { opacity: 1, duration: 0.4 }, "<")
        .to({}, { duration: 0.8 });
    }, rootRef);
    return () => ctx.revert();
  }, []);

  return (
    <section
      ref={rootRef}
      data-hide-sticky
      className="section-cream relative overflow-hidden"
    >
      <div className="min-h-screen flex flex-col items-center justify-center px-6 py-[90px]">
        <p className="text-[12px] uppercase tracking-[0.3em] text-bronze mb-4 text-center">
          Watch one promise get kept
        </p>
        <h2 className="font-serif text-[clamp(26px,3.6vw,40px)] leading-[1.1] text-[var(--text-on-light)] text-center max-w-2xl">
          This is what happens on your phone
          <span className="italic"> while you keep talking.</span>
        </h2>

        <div className="mt-10 w-full max-w-md md:max-w-lg grid md:grid-cols-[150px_1fr] gap-6 items-start">
          {/* stage rail */}
          <ol className="hidden md:flex flex-col gap-5 pt-2">
            {STAGE_LABELS.map((l, i) => (
              <li
                key={l}
                className={`ld-label-${i} text-[12px] uppercase tracking-[0.14em] text-[var(--text-on-light-muted)] opacity-0 transition-none`}
              >
                <span className="text-bronze mr-2">{String(i + 1).padStart(2, "0")}</span>
                {l}
              </li>
            ))}
          </ol>

          {/* phone */}
          <div
            className="rounded-[28px] px-5 py-6 flex flex-col gap-4"
            style={{
              background: "var(--dark-elevated)",
              border: "1px solid var(--dark-border)",
              boxShadow: "0 30px 70px rgba(23,21,18,0.3)",
            }}
          >
            {/* spoken */}
            <div className="ld-spoken opacity-0">
              <div className="ld-wave flex items-end gap-[3px] h-6 mb-3" aria-hidden>
                {Array.from({ length: 28 }).map((_, i) => (
                  <span
                    key={i}
                    className="w-[3px] rounded-full"
                    style={{
                      height: `${6 + ((i * 7) % 18)}px`,
                      background: "var(--gold)",
                      opacity: 0.85,
                      transformOrigin: "bottom",
                    }}
                  />
                ))}
              </div>
              <p className="font-serif italic text-[16px] leading-snug text-[var(--text-on-dark)]">
                {SPOKEN}
              </p>
            </div>

            {/* caught */}
            <div
              className="ld-caught opacity-0 rounded-xl px-4 py-3"
              style={{ border: "1px solid rgba(200,169,126,0.4)" }}
            >
              <p className="text-[11px] uppercase tracking-[0.18em] text-gold mb-1">
                Commitment caught
              </p>
              <p className="text-[13px] text-[var(--text-on-dark)]">
                Send meeting notes to <strong>Marcus</strong> &middot; tonight
                &middot; leave out the budget slide
              </p>
            </div>

            {/* draft */}
            <div
              className="ld-draft opacity-0 rounded-xl px-4 py-3"
              style={{
                background: "rgba(255,255,255,0.03)",
                border: "1px solid var(--dark-border)",
              }}
            >
              <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-on-dark-muted)] mb-2">
                Draft ready &middot; 9:41 PM
              </p>
              <p className="text-[13px] text-[var(--text-on-dark)]">
                To: Marcus &middot; &ldquo;Notes from today&rdquo;
              </p>
              <p className="text-[13px] text-[var(--text-on-dark-muted)] mt-1">
                meeting-notes.pdf &middot;{" "}
                <span
                  className="ld-strike"
                  style={{
                    backgroundImage:
                      "linear-gradient(var(--gold), var(--gold))",
                    backgroundRepeat: "no-repeat",
                    backgroundPosition: "0 55%",
                    backgroundSize: "0% 1px",
                  }}
                >
                  budget slide
                </span>{" "}
                removed
              </p>
            </div>

            {/* approve */}
            <div className="ld-approve opacity-0 flex justify-end">
              <span
                className="ld-approve-btn inline-block rounded-pill text-[13px] font-medium px-6 py-2"
                style={{
                  background: "var(--text-on-dark)",
                  color: "var(--dark)",
                }}
              >
                Approve &amp; send
              </span>
            </div>

            {/* receipt */}
            <div
              className="ld-receipt opacity-0 rounded-xl px-4 py-3 flex items-center gap-3"
              style={{ border: "1px solid rgba(200,169,126,0.55)" }}
            >
              <svg width="26" height="26" viewBox="0 0 26 26" fill="none" aria-hidden>
                <circle cx="13" cy="13" r="12" stroke="var(--gold)" strokeWidth="1.5" />
                <path
                  className="ld-check"
                  d="M7.5 13.5l3.5 3.5 7-8"
                  stroke="var(--gold)"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeDasharray="48"
                  strokeDashoffset="48"
                />
              </svg>
              <div>
                <p className="text-[13px] text-[var(--text-on-dark)]">
                  Delivered &middot; independently verified
                </p>
                <p className="text-[12px] text-[var(--text-on-dark-muted)]">
                  Receipt saved. Commitment closed.
                </p>
              </div>
            </div>
          </div>
        </div>

        <p className="mt-8 text-[13px] text-[var(--text-on-light-muted)] text-center max-w-md">
          You never opened your laptop. You never wrote a reminder. You said it
          once, near your chest, and it happened.
        </p>
      </div>
    </section>
  );
}
