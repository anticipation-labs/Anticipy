import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Anticipy vs Bee AI Wearable: Full Comparison",
  description:
    "Compare Anticipy and Bee (acquired by Amazon). One captures meeting notes and action items. The other skips the list and completes tasks directly.",
  openGraph: {
    title: "Anticipy vs Bee AI Wearable: Full Comparison",
    description:
      "Meeting notes vs task execution. Full comparison of two AI wearable approaches.",
    url: "https://www.anticipy.ai/vs/bee",
    siteName: "Anticipy",
    type: "article",
  },
  twitter: {
    card: "summary_large_image",
    title: "Anticipy vs Bee AI Wearable: Full Comparison",
    description:
      "Meeting notes vs task execution. Full comparison of two AI wearable approaches.",
  },
  alternates: {
    canonical: "https://www.anticipy.ai/vs/bee",
  },
};

const comparisonSchema = {
  "@context": "https://schema.org",
  "@type": "WebPage",
  name: "Anticipy vs Bee AI Comparison",
  description: "Detailed comparison of Anticipy and Bee AI wearables.",
  mainEntity: [
    {
      "@type": "Product",
      name: "Anticipy",
      brand: { "@type": "Brand", name: "Anticipation Labs" },
      description:
        "AI wearable pendant that detects ambient intent and completes tasks autonomously.",
      category: "AI Wearable",
      offers: {
        "@type": "Offer",
        price: "149",
        priceCurrency: "USD",
        availability: "https://schema.org/PreOrder",
      },
    },
    {
      "@type": "Product",
      name: "Bee",
      brand: { "@type": "Brand", name: "Bee AI (acquired by Amazon)" },
      description:
        "AI wearable focused on meeting capture, personal knowledge management, and action item extraction.",
      category: "AI Wearable",
    },
  ],
};

const rows = [
  { feature: "Price", anticipy: "$149 (first year of service included)", competitor: "Pricing changed after Amazon acquisition; originally subscription-based" },
  { feature: "Weight", anticipy: "8 grams", competitor: "Per public listing, compact wearable form factor" },
  { feature: "Material", anticipy: "Brushed titanium", competitor: "Per public listing, lightweight housing" },
  { feature: "Core function", anticipy: "Detects intent, completes tasks autonomously", competitor: "Meeting capture, knowledge timeline, action item extraction" },
  { feature: "Intent model", anticipy: "Ambient intent (no commands needed)", competitor: "Passive listening with structured note extraction" },
  { feature: "Task execution", anticipy: "Yes, via autonomous browser agent", competitor: "No; extracts action items for user to complete" },
  { feature: "Audio approach", anticipy: "Process for intent, then discard", competitor: "Records and organizes into searchable timeline" },
  { feature: "Output type", anticipy: "Completed real-world tasks", competitor: "Meeting summaries, action item lists, searchable notes" },
  { feature: "Platform", anticipy: "Independent, works on any website", competitor: "Post-acquisition, likely integrating with Amazon ecosystem" },
  { feature: "Availability", anticipy: "Pre-order (waitlist open)", competitor: "Status evolving post-Amazon acquisition" },
];

export default function VsBeePage() {
  return (
    <div style={{ background: "var(--dark)" }} className="min-h-screen">
      <header
        className="px-6 py-6 border-b"
        style={{ borderColor: "var(--dark-border)" }}
      >
        <div className="max-w-4xl mx-auto flex justify-between items-center">
          <Link
            href="/"
            className="font-serif text-[22px] text-[var(--text-on-dark)] hover:text-gold transition-colors"
          >
            Anticipy
          </Link>
          <Link
            href="/compare"
            className="text-[15px] text-[var(--text-on-dark-muted)] hover:text-gold transition-colors"
          >
            All Comparisons
          </Link>
        </div>
      </header>

      <main className="px-6 py-16">
        <div className="max-w-4xl mx-auto">
          <h1 className="font-serif text-[clamp(32px,5vw,48px)] text-[var(--text-on-dark)] leading-[1.15] mb-8">
            Anticipy vs Bee AI
          </h1>

          {/* First 200 words: direct answer */}
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy and Bee are both AI wearables that process ambient audio, but they target
            different problems and produce different outputs. Bee, originally developed by Bee AI and
            acquired by Amazon in early 2025, was designed primarily for meeting capture and personal
            knowledge management. It records conversations, organizes them into a searchable timeline,
            and uses AI to extract key points, decisions, and action items. The result is a structured
            set of notes: what was discussed, what was decided, and what needs to happen next.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy does not record or organize conversations. It listens for intent and acts on it
            autonomously. When Bee detects an action item in a meeting (&quot;let&apos;s schedule a
            follow-up for next week&quot;), it adds that to your action item list. When Anticipy
            detects the same statement, it opens a calendar, finds available slots, and sends the
            invite. Bee tells you what needs to be done. Anticipy does it. Both products demonstrate
            that the market recognizes the value of ambient audio AI. Where they differ is in what
            happens after the listening: documentation versus execution.
          </p>

          {/* Comparison Table */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            Feature Comparison
          </h2>
          <div className="overflow-x-auto mb-12 rounded-xl" style={{ border: "1px solid var(--dark-border)" }}>
            <table className="w-full text-left">
              <thead>
                <tr style={{ background: "var(--dark-elevated)" }}>
                  <th className="px-6 py-4 text-[13px] text-[var(--text-on-dark-muted)] font-medium uppercase tracking-wider">
                    Feature
                  </th>
                  <th className="px-6 py-4 text-[13px] text-gold font-medium uppercase tracking-wider">
                    Anticipy
                  </th>
                  <th className="px-6 py-4 text-[13px] text-[var(--text-on-dark-muted)] font-medium uppercase tracking-wider">
                    Bee
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr
                    key={row.feature}
                    style={{
                      borderTop: "1px solid var(--dark-border)",
                      background: i % 2 === 0 ? "transparent" : "var(--dark-elevated)",
                    }}
                  >
                    <td className="px-6 py-4 text-[14px] text-[var(--text-on-dark)] font-medium whitespace-nowrap">
                      {row.feature}
                    </td>
                    <td className="px-6 py-4 text-[14px] text-[var(--text-on-dark-muted)] font-light">
                      {row.anticipy}
                    </td>
                    <td className="px-6 py-4 text-[14px] text-[var(--text-on-dark-muted)] font-light">
                      {row.competitor}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Detailed Prose */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            Notes vs. Execution: The Core Difference
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Bee was built to solve a real problem for busy professionals: the difficulty of keeping
            track of everything discussed across multiple meetings and conversations in a day. It
            listens, transcribes, and organizes. After a meeting, you can review what was said, see
            extracted action items, and search across your conversation history. It is, in essence, a
            personal knowledge base powered by ambient audio.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy starts where Bee stops. Rather than presenting you with a list of things that need
            to happen, Anticipy skips the list and goes straight to execution. Its action engine
            navigates real websites, fills out real forms, and completes real transactions. You do not
            review action items after a meeting. You review completed actions.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Here is a concrete example. In a team meeting, someone says &quot;we need to book the
            offsite venue before spots fill up.&quot; Bee would capture that as an action item in your
            post-meeting summary. You would see it alongside other items, prioritize it, and eventually
            get around to searching for venues, comparing options, and making a booking. Anticipy would
            detect the intent in real-time, identify available venues matching your typical preferences,
            and present you with a confirmation before booking. The task moves from &quot;on a list&quot;
            to &quot;in progress&quot; within seconds of being mentioned.
          </p>

          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            The Amazon Acquisition and Ecosystem Effects
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Amazon&apos;s acquisition of Bee in early 2025 signals that major technology companies see
            value in ambient audio AI. The acquisition likely means Bee&apos;s technology will integrate
            with Amazon&apos;s ecosystem: Alexa, Ring, Echo, and AWS services. For users already invested
            in the Amazon ecosystem, this could mean deeper integration with their existing tools and
            services.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy operates independently. It does not rely on any specific platform or ecosystem.
            Its action engine works through a browser, which means it can interact with any website
            regardless of whether that website has an API, a partnership, or an integration. This
            independence is by design. We do not want our product&apos;s capabilities to be limited
            by which companies we have partnerships with. If a task can be done through a web browser,
            Anticipy can do it.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            The tradeoff is clear. Ecosystem integration offers seamless, deep connectivity with
            specific platforms. Platform independence offers breadth: the ability to act across any
            website, any service, any provider, without needing pre-arranged access. For a product
            whose core promise is &quot;we handle whatever needs handling,&quot; breadth is
            non-negotiable.
          </p>

          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            Knowledge Management vs. Task Completion
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Bee&apos;s strength is in building a personal knowledge graph from your conversations. Over
            time, it accumulates context about your work, your relationships, your decisions, and your
            commitments. It can answer questions like &quot;what did we decide about the pricing model
            last month?&quot; or &quot;when did I last talk to Jordan about the partnership?&quot; This
            kind of longitudinal memory has real value for people who operate in complex, information-rich
            environments.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy does not build a knowledge graph. It does not accumulate conversational context
            over time. Each moment of detected intent is processed independently. &quot;Book dinner at
            that place Sarah mentioned&quot; is understood and acted on using the context of the current
            conversation, not a months-long history. This is a deliberate constraint. We believe that
            for a device worn in every conversation, retaining the minimum necessary data is the
            responsible default.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            The practical implication: Bee gets more useful the longer you use it, because its knowledge
            base grows. Anticipy delivers its core value from day one, because every detected intent
            results in a completed task regardless of whether it has any prior context about you.
          </p>

          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            Action Items vs. Actions Completed
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            This difference deserves its own section because it captures the philosophical divide
            between the two products. An action item is a promise. It is a note that says &quot;this
            needs to happen.&quot; The problem with action items is that they require follow-through.
            Studies consistently show that people complete only a fraction of their action items from
            meetings. The items that survive tend to be the urgent and simple ones. Complex, multi-step
            tasks (researching options, navigating websites, filling out forms) are the first to be
            deferred and eventually forgotten.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy does not generate action items. It generates actions. The distinction is not
            semantic. When Anticipy detects that you need to schedule a follow-up meeting, it does not
            add &quot;schedule follow-up&quot; to a list. It checks calendars, finds a time that works,
            and drafts the invite. When it detects that you want to dispute a charge, it navigates to
            the bank&apos;s website and begins the dispute process. The output is not a reminder. It is
            a result.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Bee extracts the signal. Anticipy completes the circuit. For people who are diligent about
            reviewing and completing their action items, Bee provides genuine value. For people who have
            a growing backlog of things they keep meaning to do, Anticipy bypasses the backlog entirely.
          </p>

          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            Privacy and Data Retention
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Bee&apos;s value proposition requires storing conversation data. The searchable timeline,
            the knowledge graph, the ability to recall what was discussed months ago: all of these
            depend on retaining audio transcripts and derived metadata. Post-acquisition, this data
            now falls under Amazon&apos;s data handling policies, which users should review
            independently.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy&apos;s architecture requires no long-term audio storage. Audio is processed
            through the intent detection pipeline and discarded. The system retains only the intent
            itself (a structured description of the requested task) and the outcome. This is not a
            feature we added after the fact. It is a consequence of the product architecture:
            because our value comes from completing tasks rather than recalling conversations, there
            is nothing to gain from keeping the audio around.
          </p>

          {/* Why We Built Differently */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            Why We Built Anticipy Differently
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Bee and products like it proved that ambient audio capture has value. The market validated
            the idea that people want AI to listen and extract meaning from their conversations. That
            validation gave us confidence to pursue{" "}
            <Link href="/ambient-intent" className="text-gold hover:underline">
              ambient intent
            </Link>{" "}
            as a product concept.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            But we kept asking: what is the point of a perfect action item list if the items still
            require manual execution? The bottleneck in most people&apos;s productivity is not
            identifying what needs to be done. It is doing it. Most people already know they should
            cancel that unused subscription, dispute that incorrect charge, and schedule that overdue
            appointment. They do not need an AI to tell them. They need an AI to handle it.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            That insight is why Anticipy exists. We built an action engine, not a note-taking engine.
            We chose to process and discard audio rather than archive it. We chose browser-based task
            completion over structured summaries. Every design decision flows from a single question:
            does this help the user get things done without their involvement?
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-10">
            Bee captures what was said and identifies what should happen. Anticipy captures what was
            said and makes it happen. If your challenge is remembering and organizing, Bee solves
            a real problem. If your challenge is execution, that is the problem we built Anticipy
            to solve.
          </p>

          {/* CTA */}
          <div className="text-center py-16 border-t" style={{ borderColor: "var(--dark-border)" }}>
            <p className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mb-4">
              Want the AI wearable that acts?
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light mb-8">
              Anticipy is currently accepting waitlist signups.
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
                href="/compare"
                className="inline-block px-8 py-4 rounded-full text-[15px] font-medium transition-all duration-300 hover:opacity-80"
                style={{
                  border: "1px solid var(--dark-border)",
                  color: "var(--text-on-dark-muted)",
                }}
              >
                More Comparisons
              </Link>
            </div>
          </div>
        </div>
      </main>

      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(comparisonSchema) }}
      />
    </div>
  );
}
