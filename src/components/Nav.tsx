"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";

const navLinks = [
  { label: "Product", href: "#product" },
  { label: "How It Works", href: "#how-it-works" },
  { label: "Privacy", href: "#privacy" },
  { label: "Pricing", href: "#pricing" },
  { label: "Compare", href: "/compare" },
];

export function Nav() {
  const [isLight, setIsLight] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 50);

      const creamSections = document.querySelectorAll(".section-cream");
      const navHeight = 72;
      let overCream = false;

      creamSections.forEach((section) => {
        const rect = section.getBoundingClientRect();
        if (rect.top < navHeight && rect.bottom > navHeight) {
          overCream = true;
        }
      });

      setIsLight(overCream);
    };

    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const scrollToSection = (href: string) => {
    const el = document.querySelector(href);
    if (el) {
      el.scrollIntoView({ behavior: "smooth" });
      setMobileOpen(false);
    }
  };

  return (
    <nav
      className="fixed top-0 left-0 right-0 z-[100] transition-colors duration-300"
      style={{
        backgroundColor: isLight
          ? "rgba(245,240,235,0.85)"
          : "rgba(12,12,12,0.85)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        borderBottom: `1px solid ${isLight ? "rgba(0,0,0,0.06)" : "rgba(255,255,255,0.06)"}`,
      }}
    >
      <div className="max-w-container mx-auto flex items-center justify-between h-[72px] px-6 md:px-12">
        <a
          href="#"
          className="font-serif text-[22px] transition-colors duration-300"
          style={{ color: isLight ? "var(--text-on-light)" : "var(--text-on-dark)" }}
          onClick={(e) => {
            e.preventDefault();
            window.scrollTo({ top: 0, behavior: "smooth" });
          }}
        >
          Anticipy
        </a>

        {/* Desktop links */}
        <div className="hidden md:flex items-center gap-8">
          {navLinks.map((link) =>
            link.href.startsWith("/") ? (
              <a
                key={link.href}
                href={link.href}
                className="text-[14px] font-normal transition-colors duration-300 hover:opacity-80"
                style={{
                  color: isLight
                    ? "var(--text-on-light-muted)"
                    : "var(--text-on-dark-muted)",
                }}
              >
                {link.label}
              </a>
            ) : (
              <button
                key={link.href}
                onClick={() => scrollToSection(link.href)}
                className="text-[14px] font-normal transition-colors duration-300 hover:opacity-80"
                style={{
                  color: isLight
                    ? "var(--text-on-light-muted)"
                    : "var(--text-on-dark-muted)",
                }}
              >
                {link.label}
              </button>
            )
          )}
          <button
            onClick={() => scrollToSection("#waitlist")}
            className="text-[15px] font-medium px-6 py-2.5 rounded-pill transition-all duration-300"
            style={{
              backgroundColor: isLight ? "var(--text-on-light)" : "var(--text-on-dark)",
              color: isLight ? "var(--cream)" : "var(--dark)",
            }}
          >
            Join Waitlist
          </button>
        </div>

        {/* Mobile hamburger */}
        <button
          className="md:hidden flex flex-col gap-1.5 p-2"
          onClick={() => setMobileOpen(!mobileOpen)}
          aria-label="Toggle menu"
        >
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="block w-5 h-[1.5px] transition-all duration-300"
              style={{
                backgroundColor: isLight ? "var(--text-on-light)" : "var(--text-on-dark)",
                transform: mobileOpen
                  ? i === 0
                    ? "translateY(5px) rotate(45deg)"
                    : i === 2
                      ? "translateY(-5px) rotate(-45deg)"
                      : "none"
                  : "none",
                opacity: mobileOpen && i === 1 ? 0 : 1,
              }}
            />
          ))}
        </button>
      </div>

      {/* Mobile menu */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="md:hidden overflow-hidden"
            style={{
              backgroundColor: isLight
                ? "rgba(245,240,235,0.95)"
                : "rgba(12,12,12,0.95)",
            }}
          >
            <div className="px-6 py-6 flex flex-col gap-4">
              {navLinks.map((link) =>
                link.href.startsWith("/") ? (
                  <a
                    key={link.href}
                    href={link.href}
                    className="text-left text-[16px] transition-colors duration-300"
                    style={{
                      color: isLight
                        ? "var(--text-on-light)"
                        : "var(--text-on-dark)",
                    }}
                  >
                    {link.label}
                  </a>
                ) : (
                  <button
                    key={link.href}
                    onClick={() => scrollToSection(link.href)}
                    className="text-left text-[16px] transition-colors duration-300"
                    style={{
                      color: isLight
                        ? "var(--text-on-light)"
                        : "var(--text-on-dark)",
                    }}
                  >
                    {link.label}
                  </button>
                )
              )}
              <button
                onClick={() => scrollToSection("#waitlist")}
                className="mt-2 text-[15px] font-medium px-6 py-3 rounded-pill w-full transition-all duration-300"
                style={{
                  backgroundColor: isLight ? "var(--text-on-light)" : "var(--text-on-dark)",
                  color: isLight ? "var(--cream)" : "var(--dark)",
                }}
              >
                Join Waitlist
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </nav>
  );
}
