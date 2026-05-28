import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Compare Anticipy to Other AI Wearables",
  description:
    "See how Anticipy compares to Limitless, Friend, and Bee. Detailed feature comparisons covering price, privacy, intent model, and task execution.",
  openGraph: {
    title: "Compare Anticipy to Other AI Wearables",
    description:
      "Feature-by-feature comparisons of Anticipy vs Limitless, Friend, and Bee AI wearables.",
    url: "https://www.anticipy.ai/compare",
    siteName: "Anticipy",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Compare Anticipy to Other AI Wearables",
    description:
      "Feature-by-feature comparisons of Anticipy vs Limitless, Friend, and Bee AI wearables.",
  },
  alternates: {
    canonical: "https://www.anticipy.ai/compare",
  },
};

const comparisons = [
  {
    href: "/guide/ai-wearables-2026",
    name: "The Complete Guide to AI Wearables in 2026",
    description:
      "A landscape analysis of the AI wearables category after the 2025 consolidation. Categories, players, technology, privacy, and how to choose.",
    tag: "Industry Analysis",
  },
  {
    href: "/vs/limitless",
    name: "Anticipy vs Limitless Pendant",
    description:
      "Limitless records and summarizes your conversations. Anticipy listens for intent and completes tasks. See the full feature breakdown.",
    tag: "Memory vs Action",
  },
  {
    href: "/vs/friend",
    name: "Anticipy vs Friend Pendant",
    description:
      "Friend is an AI companion that talks back. Anticipy is an AI agent that acts on your behalf. Two very different visions for wearable AI.",
    tag: "Companion vs Agent",
  },
  {
    href: "/vs/bee",
    name: "Anticipy vs Bee AI",
    description:
      "Bee captures meeting notes and extracts action items. Anticipy skips the list and completes the actions directly. Compare the approaches.",
    tag: "Notes vs Execution",
  },
];

export default function ComparePage() {
  return (
    <div style={{ background: "var(--dark)" }} className="min-h-screen">
      {/* Header */}
      <header
        className="px-6 py-6 border-b"
        style={{ borderColor: "var(--dark-border)" }}
      >
        <div className="max-w-3xl mx-auto flex justify-between items-center">
          <Link
            href="/"
            className="font-serif text-[22px] text-[var(--text-on-dark)] hover:text-gold transition-colors"
          >
            Anticipy
          </Link>
          <Link
            href="/"
            className="text-[15px] text-[var(--text-on-dark-muted)] hover:text-gold transition-colors"
          >
            Back to Home
          </Link>
        </div>
      </header>

      {/* Content */}
      <main className="px-6 py-16">
        <div className="max-w-3xl mx-auto">
          <h1 className="font-serif text-[clamp(32px,5vw,48px)] text-[var(--text-on-dark)] leading-[1.15] mb-4">
            Compare Anticipy
          </h1>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-4">
            Several AI wearables are entering the market, each with a different thesis on what a
            pendant around your neck should do. Some record. Some chat. Some take notes.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-12">
            Anticipy is the only one that acts. It detects intent from your natural conversation
            and completes tasks on real websites, autonomously. No commands. No apps. No manual
            follow-through. Here is how it compares to the alternatives.
          </p>

          {/* Concept page link */}
          <div
            className="p-8 rounded-xl mb-8 transition-all duration-300 hover:border-gold"
            style={{
              background: "var(--dark-elevated)",
              border: "1px solid var(--dark-border)",
            }}
          >
            <div className="flex items-center gap-3 mb-3">
              <span className="text-[12px] font-medium px-3 py-1 rounded-full bg-gold/10 text-gold">
                Concept
              </span>
            </div>
            <Link href="/ambient-intent" className="group">
              <h2 className="text-[22px] text-[var(--text-on-dark)] font-medium mb-2 group-hover:text-gold transition-colors">
                What Is Ambient Intent?
              </h2>
              <p className="text-[15px] text-[var(--text-on-dark-muted)] font-light leading-[1.7]">
                The foundational concept behind Anticipy. Learn why detecting intent from natural
                conversation is a fundamentally different paradigm from voice commands, recording,
                or chatbots.
              </p>
            </Link>
          </div>

          {/* Comparison cards */}
          <div className="space-y-6 mb-16">
            {comparisons.map((comp) => (
              <Link
                key={comp.href}
                href={comp.href}
                className="block p-8 rounded-xl transition-all duration-300 hover:border-gold"
                style={{
                  background: "var(--dark-elevated)",
                  border: "1px solid var(--dark-border)",
                }}
              >
                <div className="flex items-center gap-3 mb-3">
                  <span className="text-[12px] font-medium px-3 py-1 rounded-full bg-gold/10 text-gold">
                    {comp.tag}
                  </span>
                </div>
                <h2 className="text-[22px] text-[var(--text-on-dark)] font-medium mb-2">
                  {comp.name}
                </h2>
                <p className="text-[15px] text-[var(--text-on-dark-muted)] font-light leading-[1.7]">
                  {comp.description}
                </p>
              </Link>
            ))}
          </div>

          {/* CTA */}
          <div className="text-center py-16 border-t" style={{ borderColor: "var(--dark-border)" }}>
            <p className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mb-4">
              Ready to skip the comparison?
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light mb-8">
              Join the waitlist for the AI wearable that acts.
            </p>
            <Link
              href="/waitlist"
              className="inline-block px-8 py-4 rounded-full text-[15px] font-medium transition-all duration-300 hover:opacity-90"
              style={{
                backgroundColor: "var(--text-on-dark)",
                color: "var(--dark)",
              }}
            >
              Join the Waitlist
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}
