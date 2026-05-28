"use client";

import { motion, useInView } from "motion/react";
import { useRef, useState, useEffect } from "react";
import Link from "next/link";
import Image from "next/image";
import { ease, defaultTransition } from "@/lib/animation";
import { ScrollReveal } from "@/components/ScrollReveal";

// ─── CONFIGURATION ─────────────────────────────────────────────
// Update these values as the raise progresses
const FUNDING_CONFIG = {
  goal: 1500000,
  valuationCap: 15000000,
  equity: "~10%",
  instrument: "SAFE (post-money)",
  projectedReturn: "92x",
  projectedYear: 2031,
  minInvestment: 1000,
};

const CAL_LINK = "https://cal.com/omar-anticipy"; // Profile page — investors pick 15/30/60 min
const CAL_LINK_30 = "https://cal.com/omar-anticipy/anticipyfundraising30"; // Direct 30-min for emails
const DECK_URL = ""; // Deck removed — investors get it after signing up
const CONTACT_EMAIL = "omar@anticipy.ai";

// ─── HELPERS ───────────────────────────────────────────────────
function formatCurrency(n: number) {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toLocaleString()}`;
}

// ─── NAV ───────────────────────────────────────────────────────
function FundedNav() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 50);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <nav
      className="fixed top-0 left-0 right-0 z-[100] transition-all duration-300"
      style={{
        backgroundColor: scrolled ? "rgba(12,12,12,0.85)" : "transparent",
        backdropFilter: scrolled ? "blur(20px)" : "none",
        WebkitBackdropFilter: scrolled ? "blur(20px)" : "none",
        borderBottom: scrolled ? "1px solid rgba(255,255,255,0.06)" : "1px solid transparent",
      }}
    >
      <div className="max-w-container mx-auto flex items-center justify-between h-[72px] px-6 md:px-12">
        <Link
          href="/"
          className="font-serif text-[22px] text-[var(--text-on-dark)] transition-colors duration-300"
        >
          Anticipy
        </Link>
        <Link
          href="/"
          className="text-[14px] text-[var(--text-on-dark-muted)] hover:text-[var(--text-on-dark)] transition-colors duration-300"
        >
          Back to Home
        </Link>
      </div>
    </nav>
  );
}

// ─── HERO ──────────────────────────────────────────────────────
function HeroSection() {
  const containerVariants = {
    hidden: {},
    visible: { transition: { staggerChildren: 0.15 } },
  };
  const child = {
    hidden: { opacity: 0, y: 30 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.9, ease } },
  };

  const deckAction = DECK_URL
    ? { label: "Download Deck", href: DECK_URL, external: true }
    : { label: "Get Early Access", href: "#investor-interest", external: false };

  return (
    <section className="section-dark min-h-screen flex items-center justify-center pt-[72px]">
      <motion.div
        className="max-w-container mx-auto px-6 md:px-12 py-24 md:py-32 text-center"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        <motion.h1
          variants={child}
          className="font-serif text-hero text-[var(--text-on-dark)] leading-[1.05] mb-6"
        >
          Invest in Anticipy
        </motion.h1>

        <motion.p
          variants={child}
          className="text-[clamp(18px,2.5vw,24px)] text-[var(--text-on-dark-muted)] font-light max-w-[640px] mx-auto mb-4"
        >
          The AI wearable that acts — not advises.
        </motion.p>

        <motion.p
          variants={child}
          className="text-[clamp(14px,1.8vw,16px)] text-[var(--text-on-dark-muted)] font-light max-w-[540px] mx-auto mb-10 opacity-70"
        >
          Apple is entering this market in 2027. This is your window to invest before the category exists.
        </motion.p>

        <motion.div variants={child} className="flex flex-wrap justify-center gap-4 mb-10">
          {[
            `${formatCurrency(FUNDING_CONFIG.goal)} Raise`,
            `${formatCurrency(FUNDING_CONFIG.valuationCap)} Cap`,
            "Pre-Seed SAFE",
          ].map((label) => (
            <span
              key={label}
              className="px-5 py-2.5 rounded-pill text-[14px] font-medium border"
              style={{
                color: "var(--gold)",
                borderColor: "rgba(200,169,126,0.35)",
                backgroundColor: "rgba(200,169,126,0.08)",
              }}
            >
              {label}
            </span>
          ))}
        </motion.div>

        <motion.div variants={child} className="flex flex-wrap justify-center gap-4 mb-8">
          <a
            href="#book-a-call"
            className="px-8 py-3.5 rounded-pill text-[15px] font-semibold transition-all duration-200"
            style={{
              backgroundColor: "#C9A227",
              color: "var(--dark)",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "#D4AF37")}
            onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "#C9A227")}
          >
            Book a Call
          </a>
          {deckAction.external ? (
            <a
              href={deckAction.href}
              target="_blank"
              rel="noopener noreferrer"
              className="px-8 py-3.5 rounded-pill text-[15px] font-medium border transition-all duration-200"
              style={{
                color: "var(--text-on-dark)",
                borderColor: "rgba(255,255,255,0.2)",
              }}
            >
              {deckAction.label}
            </a>
          ) : (
            <a
              href={deckAction.href}
              className="px-8 py-3.5 rounded-pill text-[15px] font-medium border transition-all duration-200"
              style={{
                color: "var(--text-on-dark)",
                borderColor: "rgba(255,255,255,0.2)",
              }}
            >
              {deckAction.label}
            </a>
          )}
        </motion.div>

        <motion.p variants={child} className="text-[13px] text-[var(--text-on-dark-muted)]">
          {CONTACT_EMAIL}
        </motion.p>
      </motion.div>
    </section>
  );
}

// ─── OPPORTUNITY ───────────────────────────────────────────────
function ComparisonChart() {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, amount: 0.4 });

  const companies = ["Anticipy", "Halo", "Omi", "Limitless"];
  const capabilities = ["Records", "Transcribes", "Acts Autonomously"];

  return (
    <div ref={ref} className="mt-12 max-w-[600px] mx-auto">
      <div className="grid grid-cols-5 gap-0 text-center">
        {/* Header row */}
        <div />
        {companies.map((c) => (
          <div
            key={c}
            className="text-[13px] font-semibold pb-4"
            style={{ color: c === "Anticipy" ? "var(--gold)" : "var(--text-on-light-muted)" }}
          >
            {c}
          </div>
        ))}

        {/* Capability rows */}
        {capabilities.map((cap, ri) => (
          <>
            <div
              key={`label-${cap}`}
              className="text-[13px] text-left py-3 pr-4 border-t"
              style={{
                color: "var(--text-on-light)",
                borderColor: "var(--cream-border)",
              }}
            >
              {cap}
            </div>
            {companies.map((company, ci) => {
              const hasIt = cap !== "Acts Autonomously" || company === "Anticipy";
              return (
                <div
                  key={`${cap}-${company}`}
                  className="flex items-center justify-center py-3 border-t"
                  style={{ borderColor: "var(--cream-border)" }}
                >
                  <motion.svg
                    width="20"
                    height="20"
                    viewBox="0 0 20 20"
                    initial={{ pathLength: 0, opacity: 0 }}
                    animate={inView ? { pathLength: 1, opacity: 1 } : {}}
                    transition={{ duration: 0.5, delay: ri * 0.15 + ci * 0.08 }}
                  >
                    {hasIt ? (
                      <motion.path
                        d="M4 10 L8 14 L16 6"
                        fill="none"
                        stroke={company === "Anticipy" ? "#C9A227" : "#8A8A8A"}
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        initial={{ pathLength: 0 }}
                        animate={inView ? { pathLength: 1 } : {}}
                        transition={{ duration: 0.5, delay: ri * 0.15 + ci * 0.08 }}
                      />
                    ) : (
                      <>
                        <motion.path
                          d="M6 6 L14 14"
                          fill="none"
                          stroke="#ccc"
                          strokeWidth="1.5"
                          strokeLinecap="round"
                          initial={{ pathLength: 0 }}
                          animate={inView ? { pathLength: 1 } : {}}
                          transition={{ duration: 0.4, delay: ri * 0.15 + ci * 0.08 }}
                        />
                        <motion.path
                          d="M14 6 L6 14"
                          fill="none"
                          stroke="#ccc"
                          strokeWidth="1.5"
                          strokeLinecap="round"
                          initial={{ pathLength: 0 }}
                          animate={inView ? { pathLength: 1 } : {}}
                          transition={{ duration: 0.4, delay: ri * 0.15 + ci * 0.08 + 0.1 }}
                        />
                      </>
                    )}
                  </motion.svg>
                </div>
              );
            })}
          </>
        ))}
      </div>
    </div>
  );
}

function OpportunitySection() {
  return (
    <section className="section-cream" style={{ padding: "clamp(80px,12vh,160px) 0" }}>
      <div className="max-w-container mx-auto px-6 md:px-12">
        <ScrollReveal>
          <h2 className="font-serif text-section text-[var(--text-on-light)] text-center mb-10">
            The $90B Wearable Market Is Missing a Brain
          </h2>
        </ScrollReveal>

        <ScrollReveal delay={0.1}>
          <div className="max-w-[720px] mx-auto space-y-6 text-[16px] leading-[1.75] text-[var(--text-on-light-muted)]">
            <p>
              The wearable market is projected to exceed $90 billion, with AI wearables carving out a $48 billion
              segment growing at 25% CAGR. Every major tech company is watching. Apple is quietly developing a
              recording pendant. The infrastructure moment is here.
            </p>
            <p>
              Yet every competitor on the market does the same thing: record, transcribe, summarize. They give you
              more information to process. None of them act on your behalf. The gap between capturing intent and
              executing on it is the entire opportunity.
            </p>
          </div>
        </ScrollReveal>

        <ScrollReveal delay={0.2}>
          <ComparisonChart />
        </ScrollReveal>

        <ScrollReveal delay={0.3}>
          <p
            className="font-serif text-[clamp(20px,3vw,28px)] text-center mt-14 italic"
            style={{ color: "var(--text-on-light)" }}
          >
            &ldquo;Every competitor records. None of them act.&rdquo;
          </p>
        </ScrollReveal>
      </div>
    </section>
  );
}

// ─── WHY NOW ───────────────────────────────────────────────────
function WhyNowSection() {
  return (
    <section className="section-dark" style={{ padding: "clamp(80px,12vh,160px) 0" }}>
      <div className="max-w-container mx-auto px-6 md:px-12">
        <ScrollReveal>
          <h2 className="font-serif text-section text-[var(--text-on-dark)] text-center mb-14">
            Why This Moment Matters
          </h2>
        </ScrollReveal>

        <div className="max-w-[720px] mx-auto space-y-8">
          <ScrollReveal delay={0.1}>
            <p className="text-[16px] leading-[1.75] text-[var(--text-on-dark-muted)]">
              Apple is targeting 2027 with a recording pendant — a device that listens and transcribes. But the
              action layer, the capability to autonomously execute tasks from ambient conversation, puts Apple&apos;s
              full vision at 2029 or 2030. We are building that layer now, years ahead of the incumbents.
            </p>
          </ScrollReveal>

          <ScrollReveal delay={0.2}>
            <p className="text-[16px] leading-[1.75] text-[var(--text-on-dark-muted)]">
              The window for a startup to own this space is narrow. Once Apple ships a recording device, consumer
              awareness explodes — but the company that already has the action layer built wins the upgrade cycle.
              We intend to be that company.
            </p>
          </ScrollReveal>

          <ScrollReveal delay={0.3}>
            <p className="text-[16px] leading-[1.75] text-[var(--text-on-dark-muted)]">
              At a $199 consumer price point, Anticipy is not a niche gadget for early adopters. It is a mass-market
              product priced for mainstream adoption from day one — the same strategy that made AirPods a $30 billion
              category.
            </p>
          </ScrollReveal>
        </div>

        <ScrollReveal delay={0.35}>
          <div
            className="max-w-[680px] mx-auto mt-14 py-8 px-8 rounded-card text-center"
            style={{ backgroundColor: "var(--dark-elevated)", border: "1px solid var(--dark-border)" }}
          >
            <p className="font-serif text-[clamp(18px,2.5vw,22px)] text-[var(--text-on-dark)] leading-[1.6] mb-4">
              This is getting into Apple before it was Apple.
              Bitcoin before it was Bitcoin. The best investments are
              obvious in hindsight — invisible in the moment.
            </p>
            <p className="text-[14px] text-[var(--text-on-dark-muted)] opacity-70">
              At a $15M cap, you&apos;re investing at the stage where legends are made.
            </p>
          </div>
        </ScrollReveal>

        <ScrollReveal delay={0.4}>
          <div className="mt-16 max-w-[800px] mx-auto rounded-image overflow-hidden relative">
            <Image
              src="/images/macro.png"
              alt="Anticipy pendant close-up"
              width={800}
              height={500}
              className="w-full h-auto object-cover"
              priority={false}
            />
          </div>
        </ScrollReveal>
      </div>
    </section>
  );
}

// ─── TRACTION TIMELINE ─────────────────────────────────────────
function TimelineSection() {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, amount: 0.3 });

  const milestones = [
    { label: "Software MVP", status: "done" },
    { label: "Action Engine", status: "done" },
    { label: "Working Prototype", sub: "Sep 2026", status: "upcoming" },
    { label: "Limited Launch", sub: "Nov 2026", status: "upcoming" },
    { label: "Scale Production", sub: "Q1 2027", status: "upcoming" },
    { label: "Seed Raise $3-5M", sub: "Q2 2027", status: "upcoming" },
  ];

  return (
    <section className="section-cream" style={{ padding: "clamp(80px,12vh,160px) 0" }}>
      <div className="max-w-container mx-auto px-6 md:px-12">
        <ScrollReveal>
          <h2 className="font-serif text-section text-[var(--text-on-light)] text-center mb-16">
            Where We Are
          </h2>
        </ScrollReveal>

        <div ref={ref} className="relative max-w-[900px] mx-auto">
          {/* Horizontal line - desktop */}
          <div className="hidden md:block absolute top-[18px] left-[10%] right-[10%] h-[2px] bg-[var(--cream-border)]">
            <motion.div
              className="h-full origin-left"
              style={{ backgroundColor: "#C9A227" }}
              initial={{ scaleX: 0 }}
              animate={inView ? { scaleX: 1 } : {}}
              transition={{ duration: 1.5, ease }}
            />
          </div>

          {/* Desktop timeline */}
          <div className="hidden md:flex justify-between relative">
            {milestones.map((m, i) => (
              <motion.div
                key={m.label}
                className="flex flex-col items-center text-center w-[15%]"
                initial={{ opacity: 0, y: 20 }}
                animate={inView ? { opacity: 1, y: 0 } : {}}
                transition={{ duration: 0.6, delay: i * 0.2, ease }}
              >
                <motion.div
                  className="w-[36px] h-[36px] rounded-full flex items-center justify-center relative z-10"
                  style={{
                    backgroundColor: m.status === "done" ? "#C9A227" : "var(--cream)",
                    border: m.status === "done" ? "none" : "2px solid var(--cream-border)",
                  }}
                  animate={
                    inView && m.status === "done"
                      ? { boxShadow: ["0 0 0 0 rgba(201,162,39,0)", "0 0 0 8px rgba(201,162,39,0.2)", "0 0 0 0 rgba(201,162,39,0)"] }
                      : {}
                  }
                  transition={{ duration: 1.5, delay: i * 0.2 + 0.5 }}
                >
                  {m.status === "done" && (
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                      <path d="M3 7 L6 10 L11 4" stroke="#0C0C0C" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </motion.div>
                <p
                  className="text-[13px] font-medium mt-4"
                  style={{ color: m.status === "done" ? "var(--text-on-light)" : "var(--text-on-light-muted)" }}
                >
                  {m.label}
                </p>
                {m.sub && (
                  <p className="text-[12px] text-[var(--text-on-light-muted)] mt-1">{m.sub}</p>
                )}
              </motion.div>
            ))}
          </div>

          {/* Mobile timeline - vertical */}
          <div className="md:hidden space-y-6">
            {milestones.map((m, i) => (
              <motion.div
                key={m.label}
                className="flex items-center gap-4"
                initial={{ opacity: 0, x: -20 }}
                animate={inView ? { opacity: 1, x: 0 } : {}}
                transition={{ duration: 0.5, delay: i * 0.15, ease }}
              >
                <div
                  className="w-[32px] h-[32px] rounded-full flex items-center justify-center flex-shrink-0"
                  style={{
                    backgroundColor: m.status === "done" ? "#C9A227" : "transparent",
                    border: m.status === "done" ? "none" : "2px solid var(--cream-border)",
                  }}
                >
                  {m.status === "done" && (
                    <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
                      <path d="M3 7 L6 10 L11 4" stroke="#0C0C0C" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </div>
                <div>
                  <p
                    className="text-[14px] font-medium"
                    style={{ color: m.status === "done" ? "var(--text-on-light)" : "var(--text-on-light-muted)" }}
                  >
                    {m.label}
                  </p>
                  {m.sub && <p className="text-[12px] text-[var(--text-on-light-muted)]">{m.sub}</p>}
                </div>
              </motion.div>
            ))}
          </div>
        </div>

        <ScrollReveal delay={0.5}>
          <p className="text-[15px] text-[var(--text-on-light-muted)] text-center mt-14">
            Funded by believers. Built for everyone.
          </p>
        </ScrollReveal>
      </div>
    </section>
  );
}

// ─── TERMS ─────────────────────────────────────────────────────
function TermsSection() {
  const terms = [
    { label: "Raising", value: formatCurrency(FUNDING_CONFIG.goal) },
    { label: "Valuation Cap", value: formatCurrency(FUNDING_CONFIG.valuationCap) },
    { label: "Instrument", value: FUNDING_CONFIG.instrument },
    { label: "Equity", value: FUNDING_CONFIG.equity },
    { label: "Use of Funds", value: "Team, manufacturing, marketing, ops" },
  ];

  return (
    <section className="section-dark" style={{ padding: "clamp(80px,12vh,160px) 0" }}>
      <div className="max-w-container mx-auto px-6 md:px-12">
        <ScrollReveal>
          <h2 className="font-serif text-section text-[var(--text-on-dark)] text-center mb-14">
            The Terms
          </h2>
        </ScrollReveal>

        <div className="max-w-[600px] mx-auto">
          <ScrollReveal delay={0.1}>
            <div className="grid grid-cols-2 gap-y-6 gap-x-8">
              {terms.map((t) => (
                <div key={t.label}>
                  <p className="text-[12px] uppercase tracking-[0.1em] text-[var(--text-on-dark-muted)] mb-1">
                    {t.label}
                  </p>
                  <p className="text-[18px] font-medium text-[var(--text-on-dark)]">{t.value}</p>
                </div>
              ))}
            </div>
          </ScrollReveal>

          <ScrollReveal delay={0.2}>
            <p className="text-[14px] italic text-[var(--text-on-dark-muted)] mt-10">
              Projected return: {FUNDING_CONFIG.projectedReturn} by {FUNDING_CONFIG.projectedYear} based on
              market capture model.
            </p>
          </ScrollReveal>
        </div>
      </div>
    </section>
  );
}

// ─── TEAM ──────────────────────────────────────────────────────
function TeamSection() {
  return (
    <section className="section-cream" style={{ padding: "clamp(80px,12vh,160px) 0" }}>
      <div className="max-w-container mx-auto px-6 md:px-12">
        <ScrollReveal>
          <h2 className="font-serif text-section text-[var(--text-on-light)] text-center mb-14">
            Who&apos;s Building This
          </h2>
        </ScrollReveal>

        <ScrollReveal delay={0.1}>
          <div className="flex flex-col items-center text-center max-w-[520px] mx-auto">
            <div className="w-[120px] h-[120px] rounded-full overflow-hidden mb-6 border-2" style={{ borderColor: "rgba(201,162,39,0.3)" }}>
              <Image
                src="/images/omar.jpg"
                alt="Omar Ebrahim"
                width={120}
                height={120}
                className="w-full h-full object-cover"
              />
            </div>
            <h3 className="font-serif text-[24px] text-[var(--text-on-light)]">Omar Ebrahim</h3>
            <p className="text-[14px] text-[var(--text-on-light-muted)] mt-1 mb-4">Founder & CEO &middot; 15 &middot; West Vancouver</p>
            <p className="text-[15px] leading-[1.7] text-[var(--text-on-light-muted)]">
              Started coding at 8. First production app at 13. At 15, built the AI that turns
              ambient conversations into completed tasks. Solo. Zero funding. The software runs today.
            </p>
            <p className="text-[14px] italic text-[var(--text-on-light-muted)] mt-4 opacity-70">
              &ldquo;I&apos;m just getting started.&rdquo;
            </p>
          </div>
        </ScrollReveal>
      </div>
    </section>
  );
}

// ─── BOOK A CALL ───────────────────────────────────────────────
function BookCallSection() {
  return (
    <section id="book-a-call" className="section-dark" style={{ padding: "clamp(80px,12vh,160px) 0" }}>
      <div className="max-w-container mx-auto px-6 md:px-12 text-center">
        <ScrollReveal>
          <h2 className="font-serif text-section text-[var(--text-on-dark)] mb-4">
            Let&apos;s Talk
          </h2>
        </ScrollReveal>

        <ScrollReveal delay={0.1}>
          <p className="text-[18px] text-[var(--text-on-dark-muted)] mb-3">
            30 minutes. No pitch. Just conversation.
          </p>
          <p className="text-[14px] text-[var(--text-on-dark-muted)] opacity-60 mb-10">
            The round is filling. The earlier you move, the more favorable your position.
          </p>
        </ScrollReveal>

        <ScrollReveal delay={0.2}>
          <div className="max-w-[700px] mx-auto rounded-card overflow-hidden" style={{ backgroundColor: "var(--dark-elevated)" }}>
            <iframe
              src={`${CAL_LINK}?embed=true&layout=month_view&theme=dark`}
              width="100%"
              height="700"
              frameBorder="0"
              className="border-0"
              title="Book an investor call"
            />
          </div>
        </ScrollReveal>

        <ScrollReveal delay={0.3}>
          <p className="text-[14px] text-[var(--text-on-dark-muted)] mt-8">
            Or email directly:{" "}
            <a
              href={`mailto:${CONTACT_EMAIL}`}
              className="text-gold hover:underline transition-colors"
            >
              {CONTACT_EMAIL}
            </a>
          </p>
        </ScrollReveal>
      </div>
    </section>
  );
}

// ─── EMAIL CAPTURE / INVESTOR INTEREST ─────────────────────────
function InvestorInterestSection() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error" | "duplicate">("idle");
  const [errorMsg, setErrorMsg] = useState("");

  const firstName = name.trim().split(" ")[0];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || status === "loading") return;

    setStatus("loading");
    try {
      const res = await fetch("/api/waitlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, name: name.trim(), source: "funded" }),
      });

      if (res.status === 201) {
        setStatus("success");
      } else if (res.status === 409) {
        setStatus("duplicate");
      } else {
        const data = await res.json();
        setErrorMsg(data.error || "Something went wrong.");
        setStatus("error");
      }
    } catch {
      setErrorMsg("Something went wrong.");
      setStatus("error");
    }
  };

  return (
    <section id="investor-interest" className="section-cream" style={{ padding: "clamp(80px,12vh,160px) 0" }}>
      <div className="max-w-container mx-auto px-6 md:px-12 text-center">
        <ScrollReveal>
          <h2 className="font-serif text-section text-[var(--text-on-light)] mb-4">
            Get In Early
          </h2>
        </ScrollReveal>

        <ScrollReveal delay={0.1}>
          <p className="text-[15px] leading-[1.7] text-[var(--text-on-light-muted)] max-w-[520px] mx-auto mb-3">
            Leave your name and email. We&apos;ll personally send you the deck, terms, and
            next steps — and a link to book time with Omar directly.
          </p>
          <p className="text-[13px] text-[var(--text-on-light-muted)] opacity-60 mb-8">
            Minimum investment: {formatCurrency(FUNDING_CONFIG.minInvestment)}
          </p>
        </ScrollReveal>

        <ScrollReveal delay={0.2}>
          {status === "success" ? (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="max-w-[500px] mx-auto text-left"
            >
              <div className="flex items-center gap-3 mb-6">
                <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
                  <circle cx="14" cy="14" r="14" fill="#C9A227" />
                  <path d="M8 14 L12 18 L20 10" stroke="#0C0C0C" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <p className="font-serif text-[22px] text-[var(--text-on-light)]">
                  {firstName ? `Welcome, ${firstName}.` : "You\u2019re in."}
                </p>
              </div>

              <div className="space-y-4 text-[15px] leading-[1.7] text-[var(--text-on-light-muted)]">
                <p>
                  {firstName ? `Hey ${firstName}` : "Hey"} — really glad you&apos;re interested.
                  This isn&apos;t a mass email situation. Omar will personally reach out
                  within the next 24 hours with your investor packet.
                </p>
                <p>
                  In the meantime, if you&apos;d rather skip the wait and talk now:
                </p>
              </div>

              <a
                href={CAL_LINK}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-block mt-6 px-8 py-3.5 rounded-pill text-[15px] font-semibold transition-all duration-200"
                style={{ backgroundColor: "#C9A227", color: "var(--dark)" }}
              >
                Book a Call with Omar
              </a>

              <p className="text-[13px] text-[var(--text-on-light-muted)] mt-6">
                Or email directly:{" "}
                <a href={`mailto:${CONTACT_EMAIL}`} className="text-gold hover:underline">
                  {CONTACT_EMAIL}
                </a>
              </p>
            </motion.div>
          ) : status === "duplicate" ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="max-w-[440px] mx-auto"
            >
              <p className="text-[15px] text-[var(--text-on-light)] mb-4">
                You&apos;re already on the list — we haven&apos;t forgotten about you.
              </p>
              <p className="text-[14px] text-[var(--text-on-light-muted)] mb-6">
                If you haven&apos;t heard from us yet, book a call directly:
              </p>
              <a
                href={CAL_LINK}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-block px-8 py-3.5 rounded-pill text-[15px] font-semibold transition-all duration-200"
                style={{ backgroundColor: "#C9A227", color: "var(--dark)" }}
              >
                Book a Call with Omar
              </a>
            </motion.div>
          ) : (
            <form onSubmit={handleSubmit} className="max-w-[440px] mx-auto">
              <div className="flex flex-col gap-3">
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Your name"
                  required
                  className="w-full px-5 py-3.5 rounded-pill text-[15px] outline-none transition-all duration-200"
                  style={{
                    backgroundColor: "var(--cream-muted)",
                    color: "var(--text-on-light)",
                    border: "1px solid var(--cream-border)",
                  }}
                  onFocus={(e) => (e.currentTarget.style.borderColor = "#C9A227")}
                  onBlur={(e) => (e.currentTarget.style.borderColor = "var(--cream-border)")}
                />
                <div className="flex gap-3">
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="your@email.com"
                    required
                    className="flex-1 px-5 py-3.5 rounded-pill text-[15px] outline-none transition-all duration-200"
                    style={{
                      backgroundColor: "var(--cream-muted)",
                      color: "var(--text-on-light)",
                      border: "1px solid var(--cream-border)",
                    }}
                    onFocus={(e) => (e.currentTarget.style.borderColor = "#C9A227")}
                    onBlur={(e) => (e.currentTarget.style.borderColor = "var(--cream-border)")}
                  />
                  <button
                    type="submit"
                    disabled={status === "loading"}
                    className="px-6 py-3.5 rounded-pill text-[15px] font-semibold transition-all duration-200 flex-shrink-0"
                    style={{
                      backgroundColor: "#C9A227",
                      color: "var(--dark)",
                      opacity: status === "loading" ? 0.7 : 1,
                    }}
                  >
                    {status === "loading" ? "..." : "I\u2019m In"}
                  </button>
                </div>
              </div>
              {status === "error" && (
                <p className="text-[13px] mt-3" style={{ color: "#c44" }}>{errorMsg}</p>
              )}
            </form>
          )}
        </ScrollReveal>
      </div>
    </section>
  );
}

// ─── FAQ ───────────────────────────────────────────────────────
function FAQItem({ q, a, index }: { q: string; a: string; index: number }) {
  const [open, setOpen] = useState(false);

  return (
    <ScrollReveal delay={index * 0.08}>
      <div
        className="border-b py-5 cursor-pointer"
        style={{ borderColor: "var(--dark-border)" }}
        onClick={() => setOpen(!open)}
      >
        <div className="flex justify-between items-center gap-4">
          <h3 className="text-[16px] font-medium text-[var(--text-on-dark)]">{q}</h3>
          <motion.span
            className="text-[var(--text-on-dark-muted)] text-[20px] flex-shrink-0 select-none"
            animate={{ rotate: open ? 45 : 0 }}
            transition={{ duration: 0.2 }}
          >
            +
          </motion.span>
        </div>
        <motion.div
          initial={false}
          animate={{ height: open ? "auto" : 0, opacity: open ? 1 : 0 }}
          transition={{ duration: 0.3, ease }}
          className="overflow-hidden"
        >
          <p className="text-[15px] leading-[1.7] text-[var(--text-on-dark-muted)] pt-4">{a}</p>
        </motion.div>
      </div>
    </ScrollReveal>
  );
}

function FAQSection() {
  const faqs = [
    {
      q: "What stage is the company?",
      a: "Pre-seed. Software MVP complete. Action engine prototype functional. Working hardware prototype targeting September 2026. Limited launch November 2026.",
    },
    {
      q: "What's the use of funds?",
      a: "Team (firmware engineer, software engineer, head of growth) $380K. Manufacturing (10,000 units, charging bases, MIM tooling, Shenzhen sourcing) $450K. Marketing and distribution $150K. Legal, IP, and certifications $80K. Operations and infrastructure $140K. Working capital and contingency $300K.",
    },
    {
      q: "Who else has invested?",
      a: "Currently raising first institutional round. Friends and family committed. Lead investor in discussions.",
    },
    {
      q: "What's the competitive moat?",
      a: "Privacy-first architecture creates a structural moat. Competitors store and transmit audio to the cloud — their architecture cannot support autonomous action without rebuilding from scratch. We have provisional patents covering ambient intent detection and on-device ephemeral audio processing. PCT international filing covering US, Canada, EU, UK, China, GCC, South Africa.",
    },
    {
      q: "How do I invest if I'm not in the US?",
      a: "We accept international investors via SAFE agreements. Book a call and we handle the paperwork.",
    },
  ];

  return (
    <section className="section-dark" style={{ padding: "clamp(80px,12vh,160px) 0" }}>
      <div className="max-w-container mx-auto px-6 md:px-12">
        <ScrollReveal>
          <h2 className="font-serif text-section text-[var(--text-on-dark)] text-center mb-14">
            Questions
          </h2>
        </ScrollReveal>

        <div className="max-w-[640px] mx-auto">
          {faqs.map((faq, i) => (
            <FAQItem key={faq.q} q={faq.q} a={faq.a} index={i} />
          ))}
        </div>
      </div>
    </section>
  );
}

// ─── FOOTER ────────────────────────────────────────────────────
function FundedFooter() {
  return (
    <footer
      className="px-6 py-10 border-t"
      style={{ background: "var(--dark)", borderColor: "var(--dark-border)" }}
    >
      <div className="max-w-container mx-auto">
        <div className="flex flex-col md:flex-row justify-between items-center gap-6">
          <p className="text-[13px] text-[var(--text-on-dark-muted)]">
            &copy; 2026 Anticipation Labs.
          </p>
          <nav className="flex gap-4">
            <Link href="/privacy" className="text-[13px] text-[var(--text-on-dark-muted)] hover:text-gold transition-colors">
              Privacy Policy
            </Link>
            <Link href="/terms" className="text-[13px] text-[var(--text-on-dark-muted)] hover:text-gold transition-colors">
              Terms of Service
            </Link>
          </nav>
          <a href={`mailto:${CONTACT_EMAIL}`} className="text-[13px] text-[var(--text-on-dark-muted)] hover:text-gold transition-colors">
            {CONTACT_EMAIL}
          </a>
        </div>
      </div>
    </footer>
  );
}

// ─── PAGE ──────────────────────────────────────────────────────
export default function FundedPage() {
  return (
    <>
      <FundedNav />
      <HeroSection />
      <div className="transition-dark-to-cream" />
      <OpportunitySection />
      <div className="transition-cream-to-dark" />
      <WhyNowSection />
      <div className="transition-dark-to-cream" />
      <TimelineSection />
      <div className="transition-cream-to-dark" />
      <TermsSection />
      <div className="transition-dark-to-cream" />
      <TeamSection />
      <div className="transition-cream-to-dark" />
      <BookCallSection />
      <div className="transition-dark-to-cream" />
      <InvestorInterestSection />
      <div className="transition-cream-to-dark" />
      <FAQSection />
      <FundedFooter />
    </>
  );
}
