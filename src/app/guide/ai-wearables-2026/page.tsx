import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "The Complete Guide to AI Wearables in 2026",
  description:
    "A 2026 landscape analysis of AI wearables: who survived consolidation, the five product categories, real specs, privacy realities, and how to choose.",
  openGraph: {
    title: "The Complete Guide to AI Wearables in 2026",
    description:
      "Landscape analysis of AI wearables after the great 2025 consolidation. Categories, players, technology, privacy, and how to choose.",
    url: "https://www.anticipy.ai/guide/ai-wearables-2026",
    siteName: "Anticipy",
    type: "article",
  },
  twitter: {
    card: "summary_large_image",
    title: "The Complete Guide to AI Wearables in 2026",
    description:
      "Landscape analysis of AI wearables after the great 2025 consolidation. Categories, players, technology, privacy, and how to choose.",
  },
  alternates: {
    canonical: "https://www.anticipy.ai/guide/ai-wearables-2026",
  },
};

const faqItems = [
  {
    question: "What are AI wearables?",
    answer:
      "AI wearables are body-worn devices that use artificial intelligence to capture, process, or act on information from the user's environment. The current generation focuses on ambient audio, with most devices taking the form of pendants, clips, or small recorders. They differ from smartwatches in that AI is the primary product, not a feature added to a fitness tracker.",
  },
  {
    question: "What happened to Humane, Limitless, and Bee in 2025?",
    answer:
      "All three changed hands. Humane shut down its AI Pin in February 2025 and sold its assets to HP for $116 million. Bee was acquired by Amazon in July 2025. Limitless was acquired by Meta in December 2025, which halted new hardware sales. The category consolidated into big tech, with most independent players either acquired or shuttered.",
  },
  {
    question: "Which AI wearable has the best privacy model?",
    answer:
      "It depends on what you mean by privacy. Devices that record continuously (Bee, Omi) store the most data. Push-to-record devices (Plaud NotePin) only capture audio when activated. Action-focused devices (Anticipy) process audio in real-time and discard it. Always-on devices in two-party consent states like California raise additional legal questions about recording other people without their knowledge.",
  },
  {
    question: "Are AI wearables legal in two-party consent states?",
    answer:
      "The legality depends on what the device does with audio. Devices that record and store conversations may violate two-party consent laws if they capture other people without their knowledge. Devices that process audio in real-time without recording occupy a more ambiguous legal space. Users in California, Florida, Pennsylvania, and other two-party consent states should research applicable laws before using always-on audio devices in conversations.",
  },
  {
    question: "Are AI wearables a replacement for smartphones?",
    answer:
      "No. Humane proved this thesis wrong in 2024. AI wearables work as companion devices that augment a smartphone, not replace it. Most rely on a paired phone for connectivity, processing, or display. The successful products in 2026 do one specific thing well rather than trying to be a phone replacement.",
  },
  {
    question: "How much do AI wearables cost in 2026?",
    answer:
      "Prices range widely. Bee was $49.99 plus subscription before the Amazon acquisition. Plaud NotePin is $169. Anticipy is $149 with first year of service included. Friend is $99. Limitless was $99 before being discontinued. Subscription models are common, with most products requiring an ongoing fee for AI features.",
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

const articleSchema = {
  "@context": "https://schema.org",
  "@type": "Article",
  headline: "The Complete Guide to AI Wearables in 2026",
  description:
    "A landscape analysis of AI wearables in 2026 covering categories, players, technology, privacy, and how to choose.",
  author: {
    "@type": "Organization",
    name: "Anticipation Labs",
  },
  publisher: {
    "@type": "Organization",
    name: "Anticipation Labs",
    url: "https://www.anticipy.ai",
  },
  datePublished: "2026-04-22",
  dateModified: "2026-04-22",
  url: "https://www.anticipy.ai/guide/ai-wearables-2026",
};

const players = [
  {
    name: "Anticipy",
    company: "Anticipation Labs",
    category: "Action Agent",
    price: "$149 (first year incl.)",
    intentModel: "Ambient intent (no commands)",
    audioHandling: "Process and discard",
    status: "Pre-order",
  },
  {
    name: "Bee",
    company: "Amazon (acq. July 2025)",
    category: "Always-on Listener",
    price: "$49.99 + $19/mo",
    intentModel: "Continuous recording",
    audioHandling: "Stores transcripts",
    status: "Available, integration pending",
  },
  {
    name: "Limitless Pendant",
    company: "Meta (acq. Dec 2025)",
    category: "Always-on Listener",
    price: "$99 (discontinued)",
    intentModel: "Continuous recording",
    audioHandling: "Stored recordings, searchable",
    status: "Hardware sales halted",
  },
  {
    name: "Friend",
    company: "Friend Inc.",
    category: "Companion",
    price: "$99",
    intentModel: "Always-on conversational",
    audioHandling: "Processes for chat context",
    status: "Available",
  },
  {
    name: "Plaud NotePin",
    company: "Plaud",
    category: "Recorder",
    price: "$169",
    intentModel: "Push to record",
    audioHandling: "Records on demand",
    status: "Available",
  },
  {
    name: "Omi",
    company: "Omi AI",
    category: "Always-on Listener",
    price: "Per public listing",
    intentModel: "Continuous recording",
    audioHandling: "Transcripts, summaries",
    status: "Available",
  },
  {
    name: "Humane AI Pin",
    company: "HP (assets only)",
    category: "Phone Replacement",
    price: "Was $699",
    intentModel: "Voice command",
    audioHandling: "Servers shut down Feb 2025",
    status: "Discontinued",
  },
];

export default function GuidePage() {
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
          <div className="mb-4 flex items-center gap-3">
            <span className="text-[12px] font-medium px-3 py-1 rounded-full bg-gold/10 text-gold">
              Industry Analysis
            </span>
            <span className="text-[12px] text-[var(--text-on-dark-muted)]">
              Updated April 2026
            </span>
          </div>
          <h1 className="font-serif text-[clamp(32px,5vw,52px)] text-[var(--text-on-dark)] leading-[1.1] mb-8">
            The Complete Guide to AI Wearables in 2026
          </h1>

          {/* First 200 words */}
          <p className="text-[18px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            The AI wearables category looks fundamentally different in 2026 than it did eighteen
            months ago. The market has bifurcated into two paths: independent products built around
            specific use cases, and platform plays absorbed into big tech. Humane shut down its AI
            Pin in February 2025 and sold its assets to HP for $116 million. Amazon acquired Bee in
            July 2025. Meta acquired Limitless in December 2025 and immediately halted hardware
            sales. What was a crowded field of independent startups has become a small set of
            survivors and a growing list of subsidiaries.
          </p>
          <p className="text-[18px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            This guide covers what AI wearables actually are in 2026, the five product categories
            that have emerged, the major players that survived consolidation, the technology
            choices that distinguish them, the privacy realities buyers should understand, and a
            framework for deciding which device fits which use case. The dedicated AI wearables
            market reached an estimated $394.53 million in 2026 and is projected to roughly double
            by 2032. The shake-out is over. The remaining players are the products that will define
            how this category looks for the rest of the decade.
          </p>

          {/* Table of contents */}
          <div
            className="p-6 rounded-xl mb-12 mt-8"
            style={{ background: "var(--dark-elevated)", border: "1px solid var(--dark-border)" }}
          >
            <p className="text-[13px] text-gold font-medium mb-3 uppercase tracking-wider">
              In This Guide
            </p>
            <ol className="space-y-2 text-[15px] text-[var(--text-on-dark-muted)] font-light">
              <li>1. The 2025 Consolidation: How We Got Here</li>
              <li>2. The Five Categories of AI Wearables</li>
              <li>3. Major Players in 2026: Honest Reviews</li>
              <li>4. Side-by-Side Comparison</li>
              <li>5. Technology Architectures Compared</li>
              <li>6. Privacy and Legal Realities</li>
              <li>7. How to Choose an AI Wearable</li>
              <li>8. The Future of the Category</li>
              <li>9. Where Anticipy Fits</li>
              <li>10. Frequently Asked Questions</li>
            </ol>
          </div>

          {/* Section 1: 2025 Consolidation */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            1. The 2025 Consolidation: How We Got Here
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Three events in 2025 reshaped the AI wearables market more than the entire prior decade
            of product launches. In February, Humane shut down its AI Pin and sold its assets to HP
            for $116 million. The deal handed HP more than 300 patents and the Cosmos software
            platform, but the device itself was discontinued. Servers went offline at the end of
            February 2025, and existing customer data was permanently wiped. Refunds were limited to
            buyers from the prior 90 days, leaving most $699 customers with paperweights.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            In July, Amazon acquired Bee for an undisclosed sum. Bee made a $49.99 wristband and an
            Apple Watch app that recorded conversations and produced AI summaries. The acquisition
            signaled Amazon&apos;s intent to extend AI beyond the Echo line into wearable form
            factors. Bee continued operating post-acquisition with new features added, but the
            independent company is now an Amazon subsidiary subject to ecosystem decisions.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            In December, Meta acquired Limitless. The deal immediately halted new hardware sales of
            the $99 Limitless Pendant. Existing users were transitioned to a free unlimited plan,
            with the device on a path to obsolescence by late 2026 according to public reporting. No
            new features and no bug fixes are planned for the existing hardware. The acquisition
            terms were not disclosed.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Three major independent products. Three different exits within ten months. The
            implications are significant. First, the category has been validated by big tech.
            Second, the market is consolidating fast, with independent players increasingly rare.
            Third, customers face genuine continuity risk: the device you buy today may belong to a
            different company within twelve months, or be discontinued entirely.
          </p>

          {/* Section 2: Categories */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            2. The Five Categories of AI Wearables
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Despite surface similarities (small device, microphone, AI), today&apos;s AI wearables
            fall into five distinct categories with very different value propositions. Conflating
            them leads to bad purchase decisions.
          </p>

          {/* Category cards */}
          {[
            {
              num: "Category 1",
              name: "Recorders",
              examples: "Plaud NotePin",
              description:
                "Push-to-record devices that capture audio on demand and produce AI transcripts and summaries afterward. Privacy-friendlier because they only record when activated. Best for professionals who want better meeting notes without committing to always-on capture. Plaud NotePin sells at $169 with up to 20 hours of continuous recording capacity.",
            },
            {
              num: "Category 2",
              name: "Always-on Listeners",
              examples: "Bee, Omi, Limitless (discontinued)",
              description:
                "Continuously capture audio throughout the day, storing recordings and transcripts for later recall. Build searchable timelines of your conversations. Highest data accumulation. Most controversial from a privacy standpoint, especially in two-party consent states. Bee at $49.99 (now Amazon) is the affordability leader.",
            },
            {
              num: "Category 3",
              name: "Companions",
              examples: "Friend",
              description:
                "Always-on listeners that respond conversationally as an AI persona. The output is dialogue rather than transcripts or actions. Marketed around emotional connection. Friend has reportedly sold only a few thousand units in the United States, suggesting limited consumer demand for the companion thesis so far.",
            },
            {
              num: "Category 4",
              name: "Action Agents",
              examples: "Anticipy",
              description:
                "Detect actionable intent from natural conversation and execute the corresponding tasks autonomously. Audio is processed and discarded. The output is completed actions: bookings made, subscriptions canceled, appointments scheduled. The newest category, with Anticipy as the only consumer-facing example shipping in 2026.",
            },
            {
              num: "Category 5",
              name: "Phone Replacements",
              examples: "Humane AI Pin (failed)",
              description:
                "All-in-one devices intended to replace smartphones entirely. Tried to handle voice queries, projection displays, calls, messaging, and search in a single wearable. The category is effectively dead after Humane&apos;s shutdown. Industry consensus is that AI wearables succeed as phone companions, not replacements.",
            },
          ].map((cat) => (
            <div
              key={cat.name}
              className="p-6 rounded-xl mb-6"
              style={{ background: "var(--dark-elevated)", border: "1px solid var(--dark-border)" }}
            >
              <p className="text-[12px] text-gold font-medium mb-2 uppercase tracking-wider">
                {cat.num}
              </p>
              <h3 className="text-[20px] text-[var(--text-on-dark)] font-medium mb-2">
                {cat.name}
              </h3>
              <p className="text-[13px] text-gold/80 mb-3">
                Example products: {cat.examples}
              </p>
              <p className="text-[15px] text-[var(--text-on-dark-muted)] font-light leading-[1.7]">
                {cat.description}
              </p>
            </div>
          ))}

          {/* Section 3: Major Players */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            3. Major Players in 2026: Honest Reviews
          </h2>

          <h3 className="text-[20px] text-[var(--text-on-dark)] font-medium mt-8 mb-3">
            Bee (Amazon)
          </h3>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-4">
            Bee continues to operate at $49.99 hardware plus a $19 monthly subscription. It records
            audio continuously by default (with mute capability) and produces summaries, reminders,
            and to-do lists. Reviews have been generally positive on summary quality. Post
            acquisition, new features have been added, suggesting Amazon is investing in the
            product. The open question is integration depth with Alexa and the broader Amazon
            ecosystem, which could either strengthen the offering or homogenize it into a Prime
            commodity. Privacy policy states audio recordings are not saved or used for AI
            training, though users should review current terms after the acquisition.
          </p>

          <h3 className="text-[20px] text-[var(--text-on-dark)] font-medium mt-8 mb-3">
            Limitless Pendant (Meta)
          </h3>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-4">
            Limitless was the most polished of the always-on listener category. The pendant
            captured conversations and produced searchable, AI-summarized notes. Battery life with
            continuous Rewind features enabled was reportedly 12 to 14 hours, well below advertised
            standby times. Following Meta&apos;s December 2025 acquisition, the device is on a
            sunset path. Existing users get free unlimited plans through end of life, but no new
            features or bug fixes. New buyers are out of luck. The product&apos;s underlying
            technology may resurface in Meta&apos;s broader wearable strategy.
          </p>

          <h3 className="text-[20px] text-[var(--text-on-dark)] font-medium mt-8 mb-3">
            Friend
          </h3>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-4">
            Friend, founded by Avi Schiffmann, sells a $99 always-on listening pendant that
            communicates back via text messages on a paired phone. Designed as an AI companion with
            an evolving personality. Public reporting suggests only a few thousand units have sold
            in the United States, indicating either slow adoption or a deliberately niche launch.
            The product&apos;s thesis (an AI you talk to as a friend) is distinct from the
            productivity-focused alternatives but has yet to demonstrate broad market pull.
          </p>

          <h3 className="text-[20px] text-[var(--text-on-dark)] font-medium mt-8 mb-3">
            Plaud NotePin
          </h3>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-4">
            Plaud NotePin at $169 takes the opposite philosophical approach from always-on
            listeners: push-to-record only. Up to 20 hours of recording capacity, transcription in
            112 languages, speaker labels, and AI summaries. Reviewers generally praise the
            transcription quality but note the press-to-start interaction can be finicky during
            fast-moving conversations. For privacy-conscious users who want recording capability
            without continuous capture, Plaud is the leading option in 2026.
          </p>

          <h3 className="text-[20px] text-[var(--text-on-dark)] font-medium mt-8 mb-3">
            Omi
          </h3>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-4">
            Omi is an always-on AI assistant that records and transcribes throughout the day,
            producing summaries, reminders, and tasks reviewable through a companion app. Smaller
            profile than the original Limitless and Bee. Marketed as one of the few independent
            alternatives still standing in the always-on category. Has positioned itself partly
            around being a Limitless alternative for users displaced by the Meta acquisition.
          </p>

          <h3 className="text-[20px] text-[var(--text-on-dark)] font-medium mt-8 mb-3">
            Anticipy
          </h3>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-4">
            Anticipy at $149 (first year of service included) takes a different approach than every
            other product in this list. It is the only consumer device built around action
            execution rather than memory or companionship. Audio is processed in real-time for
            actionable intent and discarded. The output is completed tasks: bookings made,
            subscriptions canceled, appointments scheduled. Currently in pre-order. Independent and
            not part of any big tech acquisition. The newest category in the AI wearables landscape,
            with no direct competitors shipping the same product thesis.
          </p>

          {/* Section 4: Comparison Table */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            4. Side-by-Side Comparison
          </h2>
          <div
            className="overflow-x-auto mb-12 rounded-xl"
            style={{ border: "1px solid var(--dark-border)" }}
          >
            <table className="w-full text-left text-[13px]">
              <thead>
                <tr style={{ background: "var(--dark-elevated)" }}>
                  <th className="px-4 py-3 text-[var(--text-on-dark-muted)] font-medium uppercase tracking-wider">
                    Product
                  </th>
                  <th className="px-4 py-3 text-[var(--text-on-dark-muted)] font-medium uppercase tracking-wider">
                    Owner
                  </th>
                  <th className="px-4 py-3 text-[var(--text-on-dark-muted)] font-medium uppercase tracking-wider">
                    Category
                  </th>
                  <th className="px-4 py-3 text-[var(--text-on-dark-muted)] font-medium uppercase tracking-wider">
                    Price
                  </th>
                  <th className="px-4 py-3 text-[var(--text-on-dark-muted)] font-medium uppercase tracking-wider">
                    Intent Model
                  </th>
                  <th className="px-4 py-3 text-[var(--text-on-dark-muted)] font-medium uppercase tracking-wider">
                    Audio Handling
                  </th>
                  <th className="px-4 py-3 text-[var(--text-on-dark-muted)] font-medium uppercase tracking-wider">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody>
                {players.map((p, i) => (
                  <tr
                    key={p.name}
                    style={{
                      borderTop: "1px solid var(--dark-border)",
                      background:
                        p.name === "Anticipy"
                          ? "rgba(200,169,126,0.05)"
                          : i % 2 === 0
                            ? "transparent"
                            : "var(--dark-elevated)",
                    }}
                  >
                    <td
                      className={`px-4 py-3 font-medium ${
                        p.name === "Anticipy" ? "text-gold" : "text-[var(--text-on-dark)]"
                      }`}
                    >
                      {p.name}
                    </td>
                    <td className="px-4 py-3 text-[var(--text-on-dark-muted)] font-light">
                      {p.company}
                    </td>
                    <td className="px-4 py-3 text-[var(--text-on-dark-muted)] font-light">
                      {p.category}
                    </td>
                    <td className="px-4 py-3 text-[var(--text-on-dark-muted)] font-light">
                      {p.price}
                    </td>
                    <td className="px-4 py-3 text-[var(--text-on-dark-muted)] font-light">
                      {p.intentModel}
                    </td>
                    <td className="px-4 py-3 text-[var(--text-on-dark-muted)] font-light">
                      {p.audioHandling}
                    </td>
                    <td className="px-4 py-3 text-[var(--text-on-dark-muted)] font-light">
                      {p.status}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Section 5: Technology */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            5. Technology Architectures Compared
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Beneath the marketing, AI wearables differ along four technical axes that determine
            their behavior and trade-offs.
          </p>

          <h3 className="text-[18px] text-[var(--text-on-dark)] font-medium mt-6 mb-3">
            Activation: wake word vs. always-on vs. ambient intent
          </h3>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Wake-word systems require an explicit phrase before listening. Always-on systems capture
            continuously. Ambient intent systems are technically always-on but process audio for
            actionable signals rather than archiving it. The distinction matters legally and
            practically. Always-on archival creates a permanent record. Ambient intent processing
            does not.
          </p>

          <h3 className="text-[18px] text-[var(--text-on-dark)] font-medium mt-6 mb-3">
            Storage: store vs. process and discard
          </h3>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Bee, Omi, and the now-discontinued Limitless store audio (or transcripts derived from
            audio) for later retrieval. Plaud stores recordings only when explicitly captured.
            Anticipy processes audio in real-time and stores nothing. The right choice depends on
            whether you value the ability to recall past conversations or want to minimize stored
            data.
          </p>

          <h3 className="text-[18px] text-[var(--text-on-dark)] font-medium mt-6 mb-3">
            Output: text vs. dialogue vs. action
          </h3>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Recorders and listeners produce text artifacts: transcripts, summaries, action item
            lists. Companions produce dialogue. Action agents produce completed tasks. Most users
            asking &quot;which AI wearable should I buy&quot; have not first asked &quot;what
            output do I want?&quot; The output type should drive the category choice.
          </p>

          <h3 className="text-[18px] text-[var(--text-on-dark)] font-medium mt-6 mb-3">
            Integration: API/partnership vs. browser-based
          </h3>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Devices that complete tasks (or extract action items) can either rely on partner
            integrations (calendar APIs, booking platform APIs) or use browser automation. The
            former is faster and more reliable when integrations exist. The latter is broader,
            working on any website without pre-arranged access. Anticipy uses browser automation,
            which is why it can handle arbitrary websites without partnership deals.
          </p>

          {/* Section 6: Privacy */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            6. Privacy and Legal Realities
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Always-on audio capture raises legal and social questions that buyers should understand
            before purchasing. United States wiretap law splits states into one-party consent
            jurisdictions (where one participant&apos;s consent is sufficient to record) and
            two-party consent jurisdictions (where all parties must consent). California, Florida,
            Pennsylvania, Massachusetts, and several other states require all-party consent for
            recording. Devices that record continuously may create legal exposure for users in
            those states when the device captures conversations with non-consenting third parties.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Devices that process audio in real-time without storing it occupy a more ambiguous
            legal space. There is no permanent recording, which removes the most direct wiretap
            concern, but cloud processing of conversation audio may still raise privacy questions
            depending on jurisdiction and use case.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Beyond legal questions, social dynamics matter. People around you generally do not know
            you are wearing an AI device unless you tell them. Pendants are visible but often
            mistaken for jewelry. Clip-on devices may be more obvious. Best practice for any
            always-on device is to disclose to people you spend significant time with and to
            remove the device for sensitive conversations.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Data handling policies differ significantly across products. Bee&apos;s pre-acquisition
            policy stated that audio was not saved or used for AI training, with users able to
            delete data at any time. Limitless retained recordings to enable search. Anticipy
            discards audio after intent processing. Buyers should read current privacy policies
            (post-acquisition where applicable) before purchasing, and re-read them periodically
            as they may change.
          </p>

          {/* Section 7: How to Choose */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            7. How to Choose an AI Wearable
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            The right device depends on what you actually want it to do. The mistake most buyers
            make is choosing a category before knowing the answer to that question. Use the
            following framework.
          </p>

          <div
            className="p-6 rounded-xl mb-4"
            style={{ background: "var(--dark-elevated)", border: "1px solid var(--dark-border)" }}
          >
            <p className="text-[15px] text-gold font-medium mb-2">
              If you want better recall of meetings and conversations:
            </p>
            <p className="text-[15px] text-[var(--text-on-dark-muted)] font-light leading-[1.7]">
              Choose an always-on listener (Bee, Omi) or a recorder (Plaud NotePin) depending on
              how much continuous capture you want. Recorders are privacy-friendlier; listeners
              capture more.
            </p>
          </div>

          <div
            className="p-6 rounded-xl mb-4"
            style={{ background: "var(--dark-elevated)", border: "1px solid var(--dark-border)" }}
          >
            <p className="text-[15px] text-gold font-medium mb-2">
              If you want an AI companion to talk to:
            </p>
            <p className="text-[15px] text-[var(--text-on-dark-muted)] font-light leading-[1.7]">
              Friend is the only product in this category. Adoption has been limited, but if the
              concept appeals, no other current device targets the same use case.
            </p>
          </div>

          <div
            className="p-6 rounded-xl mb-4"
            style={{ background: "var(--dark-elevated)", border: "1px solid var(--dark-border)" }}
          >
            <p className="text-[15px] text-gold font-medium mb-2">
              If you want tasks completed automatically:
            </p>
            <p className="text-[15px] text-[var(--text-on-dark-muted)] font-light leading-[1.7]">
              Anticipy is the only consumer device built around action execution. Other products
              extract action items but require manual follow-through. If completion matters more
              than documentation, this is the category to evaluate.
            </p>
          </div>

          <div
            className="p-6 rounded-xl mb-4"
            style={{ background: "var(--dark-elevated)", border: "1px solid var(--dark-border)" }}
          >
            <p className="text-[15px] text-gold font-medium mb-2">
              If you want maximum privacy:
            </p>
            <p className="text-[15px] text-[var(--text-on-dark-muted)] font-light leading-[1.7]">
              Push-to-record (Plaud) gives you control over when audio is captured. Process-and
              discard architectures (Anticipy) avoid persistent storage entirely. Both reduce data
              accumulation compared to always-on listeners.
            </p>
          </div>

          <div
            className="p-6 rounded-xl mb-8"
            style={{ background: "var(--dark-elevated)", border: "1px solid var(--dark-border)" }}
          >
            <p className="text-[15px] text-gold font-medium mb-2">
              If you want long-term continuity:
            </p>
            <p className="text-[15px] text-[var(--text-on-dark-muted)] font-light leading-[1.7]">
              Independent companies carry continuity risk in a consolidating market. Big tech
              subsidiaries (Bee, Limitless) carry roadmap risk where the parent company may pivot
              or sunset the product. Both risks exist. Evaluate company stability and product
              roadmap commitments before buying.
            </p>
          </div>

          {/* Section 8: Future */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            8. The Future of the Category
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Several trends will shape AI wearables over the next two to three years. Apple and
            OpenAI are both reportedly working on AI hardware, with industry analysts pointing to
            late 2026 or 2027 launches. If either ships a wearable in the categories above, the
            independent players face existential pressure beyond what consolidation has already
            applied.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Edge processing is growing in importance. The current generation of products relies
            heavily on cloud inference. Latency, privacy, and battery considerations are pushing
            development toward more on-device processing. The first product to combine ambient
            audio capture with substantial on-device intelligence will likely set a new bar.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Action over recording is the directional trend. The recording category is mature
            (Plaud, Bee, Omi all do it well). The action category is nascent. Buyers and
            journalists are increasingly asking why they should pay for documentation when the same
            input could produce execution.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Form factor will diversify. Pendants dominate today, but clips, glasses, earbuds, and
            embedded fabric solutions are all in development. The pendant&apos;s advantage is that
            it does not change behavior; it sits where a necklace would. Glasses face social
            adoption hurdles after Google Glass. Earbuds compete with established categories.
          </p>

          {/* Section 9: Where Anticipy Fits */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            9. Where Anticipy Fits
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Full disclosure: this guide is published by Anticipation Labs, the maker of Anticipy.
            We have tried to describe competing products factually, including those in our
            category. Where claims are uncertain, we have qualified them or skipped them. We also
            think there is value in being explicit about where our product fits in the landscape we
            just described.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy is the only consumer AI wearable in the action agent category in 2026. It is
            independent. It is not built on or owned by any big tech platform. Its core thesis is
            that the highest-value thing an AI can do with ambient conversation is not to remember
            it but to act on it. The product processes audio for actionable intent, discards it,
            and completes tasks through a browser-based action engine.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            That positioning carries trade-offs. Anticipy does not give you a transcript of your
            meeting. It does not provide a personality to chat with. It does not summarize your day.
            What it does is take the things you mentioned needing to do and do them. If your problem
            is forgetting tasks, Anticipy is built for you. If your problem is remembering
            conversations, you should look at the recorder or always-on listener categories
            described above.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            For deeper comparisons, see our pages on{" "}
            <Link href="/vs/limitless" className="text-gold hover:underline">
              Anticipy vs Limitless
            </Link>
            ,{" "}
            <Link href="/vs/friend" className="text-gold hover:underline">
              Anticipy vs Friend
            </Link>
            , and{" "}
            <Link href="/vs/bee" className="text-gold hover:underline">
              Anticipy vs Bee
            </Link>
            . For the underlying concept, see our essay on{" "}
            <Link href="/ambient-intent" className="text-gold hover:underline">
              ambient intent
            </Link>
            .
          </p>

          {/* FAQ */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-8">
            10. Frequently Asked Questions
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

          {/* Methodology */}
          <h2 className="font-serif text-[clamp(20px,3vw,24px)] text-[var(--text-on-dark)] leading-[1.2] mt-12 mb-4">
            Methodology and Sources
          </h2>
          <p className="text-[14px] text-[var(--text-on-dark-muted)] font-light leading-[1.7] mb-3">
            This guide was compiled in April 2026 from public reporting on AI wearable acquisitions,
            product reviews, and company statements. Acquisition details for Humane, Bee, and
            Limitless are sourced from announcements covered by TechCrunch, Bloomberg, Axios,
            Fortune, GeekWire, and CNBC during 2025. Product specifications reflect publicly listed
            information at the time of writing. Where specifications were uncertain or unverifiable,
            we have noted &quot;per public listing&quot; or omitted the claim.
          </p>
          <p className="text-[14px] text-[var(--text-on-dark-muted)] font-light leading-[1.7] mb-12">
            Market sizing of $394.53 million in 2026 reflects industry analyst estimates of the
            dedicated AI wearables segment, distinct from the broader smart wearables market that
            includes fitness trackers and smartwatches. We will update this guide as the landscape
            evolves.
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
                Detailed Comparisons
              </Link>
            </div>
          </div>
        </div>
      </main>

      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(faqSchema) }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(articleSchema) }}
      />
    </div>
  );
}
