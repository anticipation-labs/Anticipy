import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Anticipy vs Limitless Pendant: Full Comparison",
  description:
    "Compare Anticipy and Limitless Pendant on price, privacy, intent model, task execution, and wearability. One records conversations. The other acts on them.",
  openGraph: {
    title: "Anticipy vs Limitless Pendant: Full Comparison",
    description:
      "One records conversations. The other acts on them. Full feature comparison.",
    url: "https://www.anticipy.ai/vs/limitless",
    siteName: "Anticipy",
    type: "article",
  },
  twitter: {
    card: "summary_large_image",
    title: "Anticipy vs Limitless Pendant: Full Comparison",
    description:
      "One records conversations. The other acts on them. Full feature comparison.",
  },
  alternates: {
    canonical: "https://www.anticipy.ai/vs/limitless",
  },
};

const comparisonSchema = {
  "@context": "https://schema.org",
  "@type": "WebPage",
  name: "Anticipy vs Limitless Pendant Comparison",
  description:
    "Detailed comparison of Anticipy and Limitless Pendant AI wearables.",
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
      name: "Limitless Pendant",
      brand: { "@type": "Brand", name: "Limitless AI" },
      description:
        "AI wearable that records conversations and provides searchable transcripts and summaries.",
      category: "AI Wearable",
    },
  ],
};

const rows = [
  { feature: "Price", anticipy: "$149 (first year of service included)", competitor: "$99 (subscription plans for AI features)" },
  { feature: "Weight", anticipy: "8 grams", competitor: "Per public listing, approximately 10 grams" },
  { feature: "Material", anticipy: "Brushed titanium", competitor: "Composite materials with multiple finish options" },
  { feature: "Core function", anticipy: "Detects intent, completes tasks autonomously", competitor: "Records, transcribes, and summarizes conversations" },
  { feature: "Intent model", anticipy: "Ambient intent (no wake word, no commands)", competitor: "Passive recording with AI recall" },
  { feature: "Task execution", anticipy: "Yes, via autonomous browser agent", competitor: "No" },
  { feature: "Audio storage", anticipy: "No audio stored. Real-time processing, then discarded.", competitor: "Stores recordings for search and recall" },
  { feature: "Charging", anticipy: "Wireless (up to 15 feet from pad)", competitor: "Per public listing, magnetic/USB-C" },
  { feature: "Availability", anticipy: "Pre-order (waitlist open)", competitor: "Available for purchase" },
];

export default function VsLimitlessPage() {
  return (
    <div style={{ background: "var(--dark)" }} className="min-h-screen">
      {/* Header */}
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
            Anticipy vs Limitless Pendant
          </h1>

          {/* First 200 words: direct comparison answer */}
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy and the Limitless Pendant take fundamentally different approaches to AI wearable
            technology. The Limitless Pendant, made by Limitless AI (formerly Rewind AI), is a
            recording and memory device. It captures conversations and meetings, transcribes them,
            and provides AI-powered summaries, search, and recall. It helps you remember what was said.
            Anticipy is an action device. It listens to your conversations not to record them, but to
            detect when you need something done, and then it does it. It books the restaurant, cancels
            the subscription, files the dispute.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            The core distinction is between passive recall and active execution. Limitless answers
            &quot;what did we talk about?&quot; Anticipy answers &quot;what needs to happen next?&quot;
            Both devices are worn as pendants. Both use ambient audio. But what they do with that audio
            is completely different. Limitless stores it for later retrieval. Anticipy processes it in
            real-time, discards the audio, and acts on the intent it detected. If you need a better
            memory, Limitless is designed for that. If you need an assistant that turns conversations
            into completed tasks without you lifting a finger, that is what Anticipy was built to do.
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
                    Limitless Pendant
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

          {/* Detailed Comparison Prose */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            Recording vs. Acting: The Core Difference
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            The most important distinction between these two products is what happens after the
            microphone captures audio. Limitless builds a searchable archive of everything you heard
            and said. It excels at post-meeting recall: &quot;What did Sarah say about the budget?&quot;
            or &quot;When is the project deadline we discussed last Tuesday?&quot; This is genuinely
            useful for knowledge workers who sit in hours of meetings daily and need reliable notes.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy does something fundamentally different. It does not archive. It does not build
            a transcript library. Instead, it processes audio in real-time, looking for moments where
            someone expresses a need that can be fulfilled through action. When it finds one, it hands
            that intent to its action engine, which navigates the web and completes the task. The audio
            itself is discarded after processing. There is nothing to search later because the system
            already did what needed doing.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Think of it this way: if you are in a meeting and someone says &quot;we need to book the
            conference room for next Wednesday,&quot; Limitless will note that as a highlight in your
            transcript. You can find it later when reviewing your notes. Anticipy will book the
            conference room. The task is done before the meeting ends.
          </p>

          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            Privacy Models
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            The two products take opposite approaches to audio data. Limitless, by design, stores your
            recordings. That is its core value proposition: everything you hear is saved and searchable.
            The company provides encryption and access controls, but the fundamental architecture
            requires retaining audio data on servers for recall to work.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy&apos;s architecture is the inverse. Because the product&apos;s value comes from
            acting on intent, not from storing audio, there is no reason to keep recordings. Audio is
            processed through the intent detection pipeline and then discarded. The only data retained
            is the detected intent and the result of the action taken. If someone is uncomfortable with
            the idea of an always-on microphone, this distinction matters: one product builds a
            permanent audio archive, and the other is designed to forget.
          </p>

          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            Hardware and Wearability
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Both products ship as pendants, but the industrial design reflects their different
            philosophies. Anticipy is built from brushed titanium and weighs 8 grams. It is designed
            to look like jewelry, not technology. It hangs on a chain and sits against clothing the
            way any necklace would. The goal is invisibility: nobody should know you are wearing an
            AI device unless you tell them.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Limitless offers multiple form factors, including a pendant and a clip-on design. Their
            approach is more utilitarian, reflecting the product&apos;s focus on workplace productivity
            rather than all-day personal use. Both are lightweight. Both can be worn throughout the
            day. The choice between them depends on whether you prioritize blending in (Anticipy) or
            flexibility of attachment (Limitless).
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy charges wirelessly from up to 15 feet away using a charging pad that sits on a
            nightstand. You never plug anything in. You place the pad once, and the pendant charges
            overnight, every night, without any action on your part. Per public listing, Limitless uses
            a magnetic or USB-C charging approach.
          </p>

          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            Target User
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Limitless is designed for people who want better recall of their conversations, especially
            in professional contexts. If you sit in three hours of meetings a day and need searchable
            transcripts, Limitless solves a real problem. Its strongest use case is post-meeting review:
            catching details you missed, generating action item lists, and creating summaries to share
            with colleagues who were not present.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy is designed for people who want their conversations to result in action, not just
            documentation. The target user is someone who has dozens of small tasks per week that they
            either forget about or procrastinate on because the execution effort is too high. Booking
            a dinner, canceling a free trial before it charges, disputing an incorrect bill, scheduling
            a doctor&apos;s appointment. These are the tasks that ambient intent captures and the action
            engine completes.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            There is some overlap. Both products listen to conversations. Both use AI to extract
            meaning. But the output is different: Limitless gives you better notes, while Anticipy
            gives you fewer tasks on your to-do list because they are already done.
          </p>

          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            Pricing and Availability
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Limitless prices the hardware at $99 with tiered subscription plans for AI features. The
            free tier offers basic functionality, while premium plans unlock advanced summarization,
            unlimited history, and priority processing.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy prices the pendant at $149, which includes the first year of AI service. After
            the first year, there is a service fee to cover the ongoing costs of the action engine
            (running a browser agent that completes tasks on real websites requires compute resources).
            Anticipy is currently in pre-order, with a waitlist open on the website.
          </p>

          {/* Why We Built Differently */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            Why We Built Anticipy Differently
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            We respect what Limitless has built. Better memory is a real and valuable product category.
            But when we looked at the problems most people face daily, we saw something different from
            a recall problem. We saw an action problem.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            People do not fail to do things because they forgot what was discussed. They fail because
            executing on what was discussed requires too many steps. You remember that you need to
            cancel that subscription. You just have not gotten around to navigating the website, finding
            the cancellation flow, and clicking through five confirmation screens. That is the problem
            Anticipy solves. Not better memory. Better follow-through.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            We also made a deliberate choice about audio data. We believe that for a product people
            wear every day, in every conversation, the default should be to retain as little as
            possible. Since our product&apos;s value comes from action rather than recall, we had the
            luxury of building a system that processes and forgets. Every piece of audio is transient.
            The only lasting artifact is the completed task.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-10">
            Both approaches have merit. The right choice depends on what you need: a better record of
            your conversations, or a system that turns those conversations into results.
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
