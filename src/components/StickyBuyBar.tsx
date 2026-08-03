"use client";

import { useEffect, useState } from "react";

export function StickyBuyBar() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const onScroll = () => {
      const past = window.scrollY > window.innerHeight * 1.2;
      const nearEnd =
        window.scrollY + window.innerHeight >
        document.documentElement.scrollHeight - 900;
      const covered = Array.from(
        document.querySelectorAll("[data-hide-sticky]")
      ).some((el) => {
        const r = el.getBoundingClientRect();
        return r.top < window.innerHeight * 0.6 && r.bottom > window.innerHeight * 0.6;
      });
      setVisible(past && !nearEnd && !covered);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div
      className="fixed bottom-0 inset-x-0 z-40 transition-all duration-500"
      style={{
        transform: visible ? "translateY(0)" : "translateY(110%)",
        opacity: visible ? 1 : 0,
        pointerEvents: "none",
      }}
    >
      <div
        className="mx-auto max-w-xl mb-4 px-5 py-3 rounded-pill flex items-center justify-between gap-4 backdrop-blur-md"
        style={{
          pointerEvents: visible ? "auto" : "none",
          background: "rgba(18,18,18,0.88)",
          border: "1px solid var(--dark-border)",
          boxShadow: "0 16px 40px rgba(0,0,0,0.5)",
        }}
      >
        <div className="pl-2">
          <p className="text-[14px] text-[var(--text-on-dark)] leading-tight">
            Anticipy pendant &middot; $149.99
          </p>
          <p className="text-[11px] text-[var(--text-on-dark-muted)] leading-tight mt-0.5">
            $199 at launch &middot; Full refund before shipping
          </p>
        </div>
        <a
          href="/pre-orders/purchase"
          className="shrink-0 rounded-pill text-[14px] font-medium transition-all duration-300 hover:scale-[1.03]"
          style={{
            background: "var(--text-on-dark)",
            color: "var(--dark)",
            padding: "11px 26px",
          }}
        >
          Claim yours
        </a>
      </div>
    </div>
  );
}
