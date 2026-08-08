"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export interface Offer {
  tierKey: string;
  headline: string;
  subhead: string | null;
  listPriceCents: number;
  priceCents: number;
  amountOffCents: number;
}

interface Props {
  offer: Offer;
  triggerType: string;
  onClose: (accepted: boolean) => void;
}

const GOLD = "#C8A97E";

/**
 * The offer dialog.
 *
 * Built on a native <dialog> opened with showModal(), which is what makes it
 * structurally incapable of hurting Core Web Vitals:
 *
 *  - CLS: the top layer sits outside normal document flow, so the dialog
 *    cannot displace any element on the page. The only residual shift risk is
 *    the scrollbar vanishing when the body is locked, which the injected rule
 *    below neutralises by adding a stable gutter in the same style rule that
 *    removes the scrollbar — both change in the same frame, so net width is
 *    unchanged.
 *  - INP: focus trapping, ESC handling, background inerting and focus restore
 *    are all implemented natively in the browser. No focus-trap library, no
 *    keydown loop, no MutationObserver.
 *  - LCP: nothing renders until a real user interaction has already occurred,
 *    and the browser stops reporting LCP candidates at the first scroll or
 *    tap, so this is outside the measurement window by construction.
 *
 * The wheel is a REVEAL, not a lottery. It animates to the tier the visitor
 * already earned through their behaviour. It never claims chance, and no copy
 * here implies a random outcome — the segment it lands on was decided by the
 * server before this component mounted.
 */
export function OfferDialog({ offer, triggerType, onClose }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [spun, setSpun] = useState(false);
  const [revealed, setRevealed] = useState(false);

  const SEGMENTS = 8;
  // Index of the earned tier, so the wheel decelerates onto it.
  const tierIndex = Math.max(
    0,
    Math.min(SEGMENTS - 1, Number(offer.tierKey.replace(/\D/g, "")) || 0)
  );

  const reducedMotion =
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (!el.open) el.showModal();
    // autofocus inside <dialog> is unreliable across browsers, so focus the
    // heading explicitly for screen-reader users.
    headingRef.current?.focus();
  }, []);

  const close = useCallback(
    (accepted: boolean) => {
      const el = ref.current;
      if (el?.open) el.close();
      onClose(accepted);
    },
    [onClose]
  );

  const spin = () => {
    if (spun) return;
    setSpun(true);
    if (reducedMotion) {
      setRevealed(true);
      return;
    }
    window.setTimeout(() => setRevealed(true), 3200);
  };

  const price = (offer.priceCents / 100).toFixed(2);
  const list = (offer.listPriceCents / 100).toFixed(2);
  const off = (offer.amountOffCents / 100).toFixed(2);

  const segmentAngle = 360 / SEGMENTS;
  // Five full turns, then land mid-segment on the earned tier.
  const finalRotation = 360 * 5 + (360 - tierIndex * segmentAngle - segmentAngle / 2);

  return (
    <>
      <style>{`
        :root:has(dialog[data-offer][open]) { overflow: hidden; scrollbar-gutter: stable; }
        dialog[data-offer]::backdrop { background: rgba(6,6,6,0.72); }
        dialog[data-offer] { border: none; padding: 0; background: transparent; max-width: 100vw; max-height: 100dvh; }
        @keyframes ap-fade { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
        .ap-wheel { transition: transform 3s cubic-bezier(0.17, 0.67, 0.16, 1); }
        @media (prefers-reduced-motion: reduce) { .ap-wheel { transition: none; } }
      `}</style>

      <dialog
        ref={ref}
        data-offer
        aria-labelledby="ap-offer-heading"
        aria-describedby="ap-offer-desc"
        onCancel={() => close(false)}
        onClose={() => onClose(false)}
      >
        <div
          style={{
            width: "min(440px, calc(100vw - 32px))",
            background: "#111111",
            border: "1px solid #1F1F1F",
            borderRadius: 18,
            padding: "30px 28px 26px",
            color: "#FAFAFA",
            fontFamily:
              "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif",
            textAlign: "center",
            animation: "ap-fade 240ms ease-out",
          }}
        >
          <button
            onClick={() => close(false)}
            aria-label="Close"
            data-cta-id="offer_close"
            data-cta-location="offer_modal"
            data-cta-type="anchor"
            style={{
              position: "absolute",
              top: 14,
              right: 16,
              width: 44,
              height: 44,
              background: "transparent",
              border: "none",
              color: "#8A8A8A",
              fontSize: 22,
              cursor: "pointer",
              lineHeight: 1,
            }}
          >
            ×
          </button>

          <p
            style={{
              fontFamily: "Georgia,'Times New Roman',serif",
              fontSize: 19,
              color: GOLD,
              margin: "0 0 20px",
            }}
          >
            Anticipy
          </p>

          {/* ── Wheel ─────────────────────────────────────────── */}
          <div
            style={{
              position: "relative",
              width: 200,
              height: 200,
              margin: "0 auto 22px",
            }}
          >
            <div
              className="ap-wheel"
              aria-hidden="true"
              style={{
                width: "100%",
                height: "100%",
                borderRadius: "50%",
                border: `2px solid ${GOLD}`,
                background: `conic-gradient(${Array.from({ length: SEGMENTS })
                  .map((_, i) => {
                    const c = i % 2 === 0 ? "#1A1A1A" : "#141414";
                    return `${c} ${(i * 360) / SEGMENTS}deg ${
                      ((i + 1) * 360) / SEGMENTS
                    }deg`;
                  })
                  .join(",")})`,
                transform: spun ? `rotate(${finalRotation}deg)` : "rotate(0deg)",
              }}
            />
            {/* Pointer */}
            <div
              aria-hidden="true"
              style={{
                position: "absolute",
                top: -6,
                left: "50%",
                transform: "translateX(-50%)",
                width: 0,
                height: 0,
                borderLeft: "8px solid transparent",
                borderRight: "8px solid transparent",
                borderTop: `14px solid ${GOLD}`,
              }}
            />
            {revealed && (
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  display: "grid",
                  placeItems: "center",
                  animation: "ap-fade 300ms ease-out",
                }}
              >
                <div
                  style={{
                    background: "#0C0C0C",
                    border: `2px solid ${GOLD}`,
                    borderRadius: "50%",
                    width: 132,
                    height: 132,
                    display: "grid",
                    placeItems: "center",
                  }}
                >
                  <span style={{ fontSize: 30, fontWeight: 700 }}>${price}</span>
                </div>
              </div>
            )}
          </div>

          <h2
            id="ap-offer-heading"
            ref={headingRef}
            tabIndex={-1}
            style={{
              fontSize: 21,
              lineHeight: 1.3,
              margin: "0 0 8px",
              outline: "none",
            }}
          >
            {revealed ? offer.headline : "Your price is already set."}
          </h2>

          <p
            id="ap-offer-desc"
            style={{ fontSize: 14, lineHeight: 1.6, color: "#B8B8B8", margin: "0 0 20px" }}
          >
            {revealed
              ? offer.subhead ?? ""
              : "Spin to reveal what your time on this page has earned you."}
          </p>

          {revealed && (
            <p style={{ fontSize: 13, color: "#8A8A8A", margin: "0 0 18px" }}>
              <span style={{ textDecoration: "line-through" }}>${list}</span>
              {"  "}
              <span style={{ color: GOLD }}>${off} off</span>
            </p>
          )}

          {!spun ? (
            <button
              onClick={spin}
              data-cta-id="offer_spin"
              data-cta-location="offer_modal"
              data-cta-type="preorder"
              data-cta-style="primary"
              style={{
                background: GOLD,
                color: "#0C0C0C",
                border: "none",
                borderRadius: 100,
                padding: "13px 34px",
                fontSize: 15,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Reveal my price
            </button>
          ) : (
            <button
              onClick={() => close(true)}
              disabled={!revealed}
              data-cta-id="offer_accept"
              data-cta-location="offer_modal"
              data-cta-type="preorder"
              data-cta-style="primary"
              style={{
                background: revealed ? GOLD : "#2A2A2A",
                color: revealed ? "#0C0C0C" : "#6A6A6A",
                border: "none",
                borderRadius: 100,
                padding: "13px 34px",
                fontSize: 15,
                fontWeight: 600,
                cursor: revealed ? "pointer" : "default",
                transition: "background 200ms",
              }}
            >
              {revealed ? `Claim $${price}` : "Revealing…"}
            </button>
          )}

          <p style={{ fontSize: 11, color: "#5A5A5A", margin: "16px 0 0" }}>
            Applied automatically at checkout. Nothing to type.
          </p>

          <span hidden data-trigger={triggerType} />
        </div>
      </dialog>
    </>
  );
}
