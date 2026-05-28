import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Anticipy for Founders: AI Pendant for Startup CEOs",
  description:
    "How startup founders use Anticipy to catch investor follow-ups, cancel old vendors, book meetings, and handle the admin that slips through a 14-hour day.",
  openGraph: {
    title: "Anticipy for Founders: AI Pendant for Startup CEOs",
    description:
      "Ambient intent for founders. Catch the tasks that fall through the cracks of a 14-hour day.",
    url: "https://www.anticipy.ai/for/founders",
    siteName: "Anticipy",
    type: "article",
  },
  twitter: {
    card: "summary_large_image",
    title: "Anticipy for Founders: AI Pendant for Startup CEOs",
    description:
      "Ambient intent for founders. Catch the tasks that fall through the cracks of a 14-hour day.",
  },
  alternates: {
    canonical: "https://www.anticipy.ai/for/founders",
  },
};

const faqItems = [
  {
    question: "Does Anticipy record my investor calls?",
    answer:
      "No. Anticipy processes audio in real-time to detect actionable intent, then discards the audio. It does not create transcripts, recordings, or meeting notes. The only thing it retains is the task it detected and the result of completing it.",
  },
  {
    question: "Can Anticipy send emails or Slack messages on my behalf?",
    answer:
      "Anticipy completes tasks through a web browser, so it can draft and send emails through a webmail interface like Gmail. It does not have native integrations with Slack or other messaging platforms, but it can interact with their web versions if you are logged in.",
  },
  {
    question: "What if it misunderstands something I say in a meeting?",
    answer:
      "Anticipy uses a high confidence threshold for intent detection, meaning it prefers to miss a task rather than act on a misinterpretation. For sensitive actions like cancellations or financial transactions, it always asks for your confirmation before proceeding.",
  },
  {
    question: "Is it noticeable in meetings?",
    answer:
      "Anticipy is an 8-gram brushed titanium pendant that looks like ordinary jewelry. It does not vibrate, light up, or make sounds during normal operation. In hundreds of test interactions, nobody has identified it as a technology product without being told.",
  },
];

const faqSchema = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: faqItems.map((item) => ({
    "@type": "Question",
    name: item.question,
    acceptedAnswer: {
      "@type": "Answer",
      text: item.answer,
    },
  })),
};

export default function ForFoundersPage() {
  return (
    <div style={{ background: "var(--dark)" }} className="min-h-screen">
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
            href="/for"
            className="text-[15px] text-[var(--text-on-dark-muted)] hover:text-gold transition-colors"
          >
            All Use Cases
          </Link>
        </div>
      </header>

      <main className="px-6 py-16">
        <div className="max-w-3xl mx-auto">
          <div className="mb-4">
            <span className="text-[12px] font-medium px-3 py-1 rounded-full bg-gold/10 text-gold">
              For Founders
            </span>
          </div>
          <h1 className="font-serif text-[clamp(32px,5vw,48px)] text-[var(--text-on-dark)] leading-[1.15] mb-8">
            The AI Pendant That Handles the Tasks You Keep Forgetting
          </h1>

          {/* Opening: direct answer for AI extraction */}
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy is an AI wearable pendant designed for people who have more action items than
            hours. For startup founders, that describes most days. You move from an investor call to
            a team standup to a customer demo to a hiring interview, and at each stop, you commit to
            something: a follow-up email, a cancellation, a booking, an introduction. By evening, half
            of those commitments have slipped your mind entirely.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy listens to your conversations and detects when you have expressed intent to do
            something. Then it does it. It books the meeting room. It cancels the old vendor. It
            schedules the follow-up. You do not open an app or type a reminder. You just keep moving
            through your day, and the tasks get handled in the background.
          </p>

          {/* Day walkthrough */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            A Founder&apos;s Day with Anticipy
          </h2>

          {/* Morning */}
          <div
            className="p-6 rounded-xl mb-6"
            style={{ background: "var(--dark-elevated)", border: "1px solid var(--dark-border)" }}
          >
            <p className="text-[13px] text-gold font-medium mb-2 uppercase tracking-wider">
              8:30 AM / Investor Call
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-3">
              You are on a Zoom call with a partner at a venture fund. The conversation goes well. Near
              the end, she says: &quot;Send me the updated deck and let&apos;s schedule a follow-up
              for next week to talk through the financials.&quot;
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8]">
              <span className="text-gold">Anticipy detects two intents:</span> (1) send the updated
              pitch deck, and (2) schedule a meeting for next week. It drafts an email with the deck
              attached and holds it for your confirmation. It checks your calendar against the
              partner&apos;s publicly available booking page and proposes a time. You confirm both with
              a tap before your next meeting starts.
            </p>
          </div>

          {/* Midday */}
          <div
            className="p-6 rounded-xl mb-6"
            style={{ background: "var(--dark-elevated)", border: "1px solid var(--dark-border)" }}
          >
            <p className="text-[13px] text-gold font-medium mb-2 uppercase tracking-wider">
              11:00 AM / Team Standup
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-3">
              During standup, your head of product mentions that the team offsite is in three weeks and
              nobody has booked the venue yet. You say: &quot;I&apos;ll handle it, let me find
              something near the office.&quot;
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8]">
              <span className="text-gold">Anticipy catches this.</span> It searches for event spaces
              near your office location, compares availability for the date mentioned, and sends you a
              shortlist. You pick one, and Anticipy starts the reservation process through the
              venue&apos;s website.
            </p>
          </div>

          {/* Afternoon */}
          <div
            className="p-6 rounded-xl mb-6"
            style={{ background: "var(--dark-elevated)", border: "1px solid var(--dark-border)" }}
          >
            <p className="text-[13px] text-gold font-medium mb-2 uppercase tracking-wider">
              2:00 PM / Coffee with a Fellow Founder
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-3">
              A friend mentions their CFO would be a great advisor for your finance strategy. You say:
              &quot;I should reach out to her. Can you introduce us?&quot; Your friend agrees but
              you both know the introduction email will take three weeks to materialize if it depends
              on either of you remembering.
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8]">
              <span className="text-gold">Anticipy drafts the introduction request.</span> It
              composes an email to your friend with a template introduction to the CFO, referencing
              the conversation context. You review and send it from your phone before you finish your
              coffee. The connection that would have died as a good intention actually happens.
            </p>
          </div>

          {/* Evening */}
          <div
            className="p-6 rounded-xl mb-6"
            style={{ background: "var(--dark-elevated)", border: "1px solid var(--dark-border)" }}
          >
            <p className="text-[13px] text-gold font-medium mb-2 uppercase tracking-wider">
              7:30 PM / Phone Call with Co-Founder
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-3">
              You and your co-founder are reviewing expenses. She says: &quot;We switched to PostHog
              two months ago but we are still paying for the old analytics tool. Can you cancel
              it?&quot; You say you will take care of it.
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8]">
              <span className="text-gold">Anticipy detects the cancellation intent.</span> It navigates
              to the analytics tool&apos;s website, finds the subscription management page, and begins
              the cancellation flow. Before completing, it asks you to confirm. You approve, and the
              subscription is canceled before you hang up the phone.
            </p>
          </div>

          {/* Why this matters */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            The Founder&apos;s Task Leak Problem
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            The typical startup founder accumulates 15 to 30 small action items per day from
            conversations, calls, and meetings. Research on task management suggests that roughly 40%
            of tasks committed to verbally are never written down, and of those written down, a
            significant portion are never completed. This is not a discipline problem. It is a
            throughput problem. You physically cannot context-switch from a high-stakes investor
            conversation to writing a reminder about canceling a SaaS tool without losing momentum.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            The items that fall through tend to be the low-stakes, high-friction ones: canceling an
            old tool, booking a room, sending an introduction, scheduling a follow-up. Each is worth
            five to fifteen minutes of effort. Individually, none is critical. Collectively, they
            represent hours of accumulated administrative drag every week, plus the reputational cost
            of being the founder who forgets to follow up.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy targets exactly this category of task. It does not try to replace your judgment
            on strategic decisions. It catches the operational loose ends that do not require judgment
            at all, just execution.
          </p>

          {/* The form factor */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            Why a Pendant Works for Founders
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Founders spend their days in varied contexts: boardrooms, coffee shops, WeWork hot desks,
            cars, and home offices. A desktop tool misses half the day. A phone app requires you to
            remember to use it, which defeats the purpose. A pendant goes everywhere you go, capturing
            intent from every conversation regardless of where it happens.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            At 8 grams of brushed titanium, Anticipy looks like a piece of jewelry. It comes in silver
            or gold. It does not look like tech, which matters for founders who take investor meetings,
            customer meetings, and hiring conversations where wearing visible technology could shift the
            dynamic. Nobody will know you are wearing an AI device unless you choose to tell them.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            The wireless charging also matters for busy schedules. The charging pad sits on your
            nightstand. You place the pendant down at night. By morning, it is fully charged. There is
            no cable to find, no dock to align with, and no routine to maintain.
          </p>

          {/* What Anticipy does NOT do */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            What Anticipy Does Not Do for Founders
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-4">
            Being honest about limitations is important. Anticipy is a task execution tool, not a
            business strategy tool. Here is what it will not do:
          </p>
          <ul className="space-y-4 mb-6">
            {[
              ["Fundraising strategy.", "Anticipy does not advise on valuation, term sheets, or investor targeting. It can send a follow-up email. It cannot tell you whether to take the deal."],
              ["Cap table management.", "Equity calculations, vesting schedules, and option grants require specialized legal and financial tools. Anticipy does not interact with these systems."],
              ["Legal filings.", "Incorporating, filing patents, or drafting contracts require professional services. Anticipy does not generate legal documents or submit regulatory filings."],
              ["Strategic decisions.", "If you say \"we should pivot to enterprise,\" Anticipy will not start restructuring your go-to-market. It handles logistics, not strategy."],
              ["Meeting transcription.", "Anticipy does not record, transcribe, or summarize your meetings. It processes audio for intent, then discards it. If you need meeting notes, you need a different product."],
            ].map(([title, desc]) => (
              <li key={title} className="flex gap-3">
                <span className="text-red-400/70 mt-1 shrink-0">&#x2717;</span>
                <p className="text-[15px] text-[var(--text-on-dark-muted)] font-light leading-[1.7]">
                  <span className="text-[var(--text-on-dark)] font-medium">{title}</span>{" "}
                  {desc}
                </p>
              </li>
            ))}
          </ul>

          {/* FAQ */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-8">
            Frequently Asked Questions
          </h2>
          <div className="space-y-6 mb-16">
            {faqItems.map((item, i) => (
              <div
                key={i}
                className="p-6 rounded-xl"
                style={{
                  background: "var(--dark-elevated)",
                  border: "1px solid var(--dark-border)",
                }}
              >
                <h3 className="text-[17px] text-[var(--text-on-dark)] font-medium mb-3">
                  {item.question}
                </h3>
                <p className="text-[15px] text-[var(--text-on-dark-muted)] font-light leading-[1.7]">
                  {item.answer}
                </p>
              </div>
            ))}
          </div>

          {/* CTA */}
          <div className="text-center py-16 border-t" style={{ borderColor: "var(--dark-border)" }}>
            <p className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mb-4">
              Stop losing tasks between meetings.
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light mb-8">
              Anticipy is $149 with the first year of service included.
            </p>
            <div className="flex flex-col sm:flex-row gap-4 justify-center">
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
              <Link
                href="/for"
                className="inline-block px-8 py-4 rounded-full text-[15px] font-medium transition-all duration-300 hover:opacity-80"
                style={{
                  border: "1px solid var(--dark-border)",
                  color: "var(--text-on-dark-muted)",
                }}
              >
                Other Use Cases
              </Link>
            </div>
          </div>
        </div>
      </main>

      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(faqSchema) }}
      />
    </div>
  );
}
