import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Anticipy vs Friend Pendant: Full Comparison",
  description:
    "Compare Anticipy and the Friend pendant. One is an AI companion that chats. The other is an AI agent that completes tasks. See the full breakdown.",
  openGraph: {
    title: "Anticipy vs Friend Pendant: Full Comparison",
    description:
      "AI companion vs AI agent. Full feature comparison of two wearable pendants.",
    url: "https://www.anticipy.ai/vs/friend",
    siteName: "Anticipy",
    type: "article",
  },
  twitter: {
    card: "summary_large_image",
    title: "Anticipy vs Friend Pendant: Full Comparison",
    description:
      "AI companion vs AI agent. Full feature comparison of two wearable pendants.",
  },
  alternates: {
    canonical: "https://www.anticipy.ai/vs/friend",
  },
};

const comparisonSchema = {
  "@context": "https://schema.org",
  "@type": "WebPage",
  name: "Anticipy vs Friend Pendant Comparison",
  description:
    "Detailed comparison of Anticipy and the Friend AI pendant.",
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
      name: "Friend",
      brand: { "@type": "Brand", name: "Friend" },
      description:
        "Always-on AI companion pendant that listens and provides conversational interaction.",
      category: "AI Wearable",
    },
  ],
};

const rows = [
  { feature: "Price", anticipy: "$149 (first year of service included)", competitor: "$99" },
  { feature: "Weight", anticipy: "8 grams", competitor: "Per public listing, lightweight pendant form factor" },
  { feature: "Material", anticipy: "Brushed titanium", competitor: "Per public listing, plastic housing" },
  { feature: "Core function", anticipy: "Detects intent, completes tasks autonomously", competitor: "AI companion: listens and responds conversationally" },
  { feature: "Intent model", anticipy: "Ambient intent (no commands needed)", competitor: "Always-on listening with personality-driven responses" },
  { feature: "Task execution", anticipy: "Yes, via autonomous browser agent", competitor: "No" },
  { feature: "Audio approach", anticipy: "Process for intent, then discard", competitor: "Listens continuously for conversational context" },
  { feature: "Output type", anticipy: "Completed real-world tasks", competitor: "Text and voice responses, emotional support" },
  { feature: "Charging", anticipy: "Wireless (up to 15 feet from pad)", competitor: "Per public listing, USB-C" },
  { feature: "Availability", anticipy: "Pre-order (waitlist open)", competitor: "Available for purchase" },
];

export default function VsFriendPage() {
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
            Anticipy vs Friend Pendant
          </h1>

          {/* First 200 words: direct answer */}
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy and the Friend pendant serve different purposes despite sharing a similar
            wearable form factor. The Friend pendant, created by Avi Schiffmann, is an always-listening
            AI companion. It provides conversational interaction, emotional support, and
            personality-driven responses. It is designed to feel like a friend who is always there,
            offering commentary, encouragement, and companionship throughout your day. Anticipy is not
            a companion. It does not chat with you, offer opinions, or attempt to form a relationship.
            It listens for moments when you need something done, and then it does it.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            The Friend pendant is about connection and presence. Anticipy is about execution and
            action. When you say &quot;I really need to cancel that gym membership,&quot; Friend might
            respond with encouragement or advice. Anticipy would navigate to the gym&apos;s website
            and cancel the membership. This is not a subtle difference. These are fundamentally
            different product categories that happen to share a wearable pendant form factor. Friend
            answers the question &quot;What if AI could be your companion?&quot; Anticipy answers the
            question &quot;What if AI could handle your to-do list without being asked?&quot;
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
                    Friend
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
            Companion vs. Agent: Two Visions for Wearable AI
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            The Friend pendant represents a bet on a specific human need: the desire for an
            always-available conversational partner. It listens to your day and responds with the
            personality of a supportive companion. If you share a frustration, it empathizes. If you
            share good news, it celebrates. The product is built on the thesis that many people want
            an AI that feels present, not one that disappears into the background.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy represents the opposite thesis. We believe the best AI assistant is one you
            forget is there until you notice that something you needed has already been handled. You
            do not interact with Anticipy. You do not talk to it or wait for it to respond. It operates
            entirely in the background, surfacing only when it needs confirmation before taking a
            significant action.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            These are both valid visions for what AI wearables can be. The question is which problem
            matters more to you: wanting a conversational presence throughout your day, or wanting
            the small tasks of life to happen without your involvement.
          </p>

          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            Output: Conversation vs. Completed Tasks
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            The simplest way to understand the difference is by looking at outputs. When Friend&apos;s
            microphone picks up your conversation, its output is text or speech directed back to you.
            It participates in your life by talking. When Anticipy&apos;s microphone picks up your
            conversation, its output is a completed task. A reservation made. A subscription canceled.
            An appointment scheduled.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Friend adds a layer of interaction to your day. Anticipy removes layers of effort from
            your day. If you ask &quot;should I cancel my streaming service I never use?&quot;,
            Friend might discuss the pros and cons with you. Anticipy would ask you to confirm, then
            navigate to the streaming service, log in, find the cancellation flow, and cancel it.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            This difference extends to how each product handles information. Friend synthesizes what
            it hears into conversational responses. Anticipy synthesizes what it hears into structured
            intents: a task type, a target, and the parameters needed to complete it. One is optimized
            for dialogue. The other is optimized for action.
          </p>

          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            Social Dynamics and Daily Use
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Friend is designed to be noticed. Part of its appeal is the novelty of having an AI
            companion that interacts with you throughout the day. It is a social product in the sense
            that it participates in your social life, reacting to conversations and offering input.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy is designed to be invisible. The titanium pendant looks like ordinary jewelry. It
            does not vibrate, light up, or make sounds during normal operation. It does not interject
            into conversations. The only sign that it is working is that tasks you mentioned get done
            in the background. People around you will not know you are wearing an AI device unless you
            tell them.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            This reflects a deeper design choice. Friend treats AI as a participant in your life.
            Anticipy treats AI as infrastructure that supports your life without demanding attention.
            Neither approach is inherently better. They serve different emotional and practical needs.
          </p>

          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            Privacy and Data Handling
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Friend processes audio to generate conversational context and responses. The specifics of
            its data retention policies are available on their website. Because the product needs to
            maintain conversational continuity (remembering what you talked about earlier), some amount
            of contextual data must persist between sessions.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy processes audio exclusively for intent detection. Once the system determines
            whether a segment contains actionable intent, the audio is discarded. There is no
            conversation history, no personality profile, and no continuity of dialogue. The system
            retains only the intent (for example, &quot;book dinner at Trattoria for two on Friday&quot;)
            and the outcome of the action it took. This minimal-retention approach is possible because
            Anticipy does not need to remember your conversations to function. It only needs to
            understand them in the moment.
          </p>

          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            Target User
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Friend appeals to people who want an AI that feels emotionally present. Early adopters have
            described it as having a persistent companion who remembers your day and engages with it.
            This has clear appeal for people who live alone, work remotely, or simply enjoy the idea of
            an AI that knows their context and converses with them about it.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy appeals to people who are busy. People who have a growing list of tasks they keep
            meaning to get to but never do. People who mention things in conversation and then forget
            to follow up. The value proposition is not emotional connection. It is time and effort saved.
            When something needs doing, it gets done, without you having to open your phone, navigate
            to a website, or remember to circle back later.
          </p>

          {/* Why We Built Differently */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            Why We Built Anticipy Differently
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            When we started building Anticipy, the obvious path was to build another chatbot in a
            new form factor. Conversational AI is well understood, and putting it in a pendant is
            primarily a hardware and UX challenge. But we asked a different question: what if the
            pendant did not talk at all?
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            We built Anticipy around the concept of{" "}
            <Link href="/ambient-intent" className="text-gold hover:underline">
              ambient intent
            </Link>:
            the idea that AI should detect what you need from the natural flow of your life, then
            handle it silently. No interaction. No conversation. No personality. Just results.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            The Friend pendant proves that people want AI closer to their daily lives. We agree with
            that premise. Where we differ is on what &quot;closer&quot; means. Friend brings AI closer
            by making it a conversational participant. Anticipy brings AI closer by making it disappear
            into the background, handling logistics so you can focus on the parts of life that actually
            matter.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-10">
            If you want an AI companion, Friend is built for that. If you want your to-do list to
            handle itself, that is what we are building.
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
