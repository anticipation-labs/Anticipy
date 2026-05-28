import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "What Is Ambient Intent? The AI Paradigm Beyond Voice Commands",
  description:
    "Ambient intent is AI that detects what you need from natural conversation, without wake words or commands. Learn how it works and why it matters.",
  openGraph: {
    title: "What Is Ambient Intent? The AI Paradigm Beyond Voice Commands",
    description:
      "AI that detects what you need from natural conversation. No wake words. No commands. Just life.",
    url: "https://www.anticipy.ai/ambient-intent",
    siteName: "Anticipy",
    type: "article",
  },
  twitter: {
    card: "summary_large_image",
    title: "What Is Ambient Intent? AI Beyond Voice Commands",
    description:
      "AI that detects what you need from natural conversation. No wake words. No commands. Just life.",
  },
  alternates: {
    canonical: "https://www.anticipy.ai/ambient-intent",
  },
};

const faqItems = [
  {
    question: "Is ambient intent the same as always-on recording?",
    answer:
      "No. Ambient intent systems process audio in real-time to detect actionable intent. They do not store or record conversations. Anticipy uses on-device voice activity detection to filter audio before any cloud processing occurs. Audio segments that contain no actionable content are discarded immediately.",
  },
  {
    question: "How does ambient intent differ from a voice assistant like Siri or Alexa?",
    answer:
      "Voice assistants require you to initiate a command with a wake word. Ambient intent detects your needs from natural conversation without any activation phrase or deliberate interaction. You do not talk to the device. It listens to your life and acts when it detects genuine intent.",
  },
  {
    question: "Can ambient intent systems misinterpret what I say?",
    answer:
      "Any AI system can make mistakes, which is why confirmation flows are essential. Anticipy asks for confirmation before executing sensitive actions like financial transactions or cancellations. The intent classifier also uses a high confidence threshold, meaning it prefers to miss an intent rather than act on a false positive.",
  },
  {
    question: "Does ambient intent work in noisy environments?",
    answer:
      "Anticipy's pendant includes a microphone array designed for voice isolation in conversational settings. It performs best in one-on-one and small group conversations. Very loud environments like concerts or construction sites will reduce accuracy, though the system is designed to recognize when conditions are too noisy and pause processing rather than produce errors.",
  },
  {
    question: "What types of tasks can ambient intent handle?",
    answer:
      "Any task that can be completed through a web browser: booking reservations, scheduling appointments, canceling subscriptions, disputing charges, filling out forms, comparing prices, and more. Anticipy's action engine navigates real websites autonomously, so it is not limited to a fixed set of integrations or partner platforms.",
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

export default function AmbientIntentPage() {
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
            href="/compare"
            className="text-[15px] text-[var(--text-on-dark-muted)] hover:text-gold transition-colors"
          >
            All Comparisons
          </Link>
        </div>
      </header>

      {/* Content */}
      <main className="px-6 py-16">
        <div className="max-w-3xl mx-auto">
          <h1 className="font-serif text-[clamp(32px,5vw,48px)] text-[var(--text-on-dark)] leading-[1.15] mb-8">
            What Is Ambient Intent?
            <br />
            <span className="text-gold">The AI Paradigm Beyond Voice Commands</span>
          </h1>

          {/* First 200 words: direct answer */}
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Ambient intent is the ability of an AI system to detect what a person needs from the
            natural flow of their conversation, without requiring an explicit command or activation
            phrase. Rather than asking a user to say &quot;Hey Siri, book a restaurant for Friday,&quot;
            an ambient intent system listens to a conversation where someone says &quot;we should get
            dinner on Friday, maybe Italian,&quot; and understands that a reservation needs to happen.
            The user never issues a command. They never open an app. They simply express a desire in the
            course of living their life, and the system recognizes it, interprets it, and acts on it.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            This concept represents a fundamental shift in how humans interact with AI. For three
            decades, the dominant paradigm has been explicit input: type a query, tap a button, speak
            a command. Ambient intent eliminates that friction entirely. The AI operates in the
            background, parsing natural language for signals of need, then completing the corresponding
            task autonomously.{" "}
            <Link href="/" className="text-gold hover:underline">
              Anticipy
            </Link>{" "}
            is the first consumer product built around ambient intent. It takes the form of an 8-gram
            titanium pendant that the wearer forgets is there, and it turns overheard intent into
            completed actions, no interaction required.
          </p>

          {/* Section: The Problem with Explicit Commands */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            The Problem with &quot;Hey Siri&quot;
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Voice assistants promised to make technology hands-free. In practice, they created a new
            kind of friction. To use Siri, Alexa, or Google Assistant, you must stop what you are
            doing, formulate a precise command, speak it clearly, and hope the system parses your
            intent correctly. That is not hands-free. That is voice-operated.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Consider a real scenario. You are on the phone with a friend, and they mention a restaurant
            they love. You think, &quot;I should try that place.&quot; With a voice assistant, you would need
            to end the conversation (or awkwardly pause it), invoke the assistant, and say something like
            &quot;Make a reservation at Trattoria Milano for two on Saturday at 7pm.&quot; You need to know
            the restaurant name, pick a time, specify the party size, and deliver all of that in a
            syntactically correct command.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            With ambient intent, none of that happens. The system heard your friend mention the
            restaurant. It detected your interest. It knows your typical dining preferences. It makes
            the reservation and confirms with you later. The cognitive load drops to zero.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            The failure of explicit voice commands is not a technology problem. It is a design problem.
            These systems were built on the assumption that humans should adapt to machines. Ambient
            intent inverts that assumption: the machine adapts to the human.
          </p>

          {/* Three failures of explicit model */}
          <h3 className="text-[20px] text-[var(--text-on-dark)] font-medium mt-10 mb-4">
            Three failures of the explicit command model
          </h3>
          <div className="space-y-6 mb-10">
            <div
              className="p-6 rounded-xl"
              style={{ background: "var(--dark-elevated)", border: "1px solid var(--dark-border)" }}
            >
              <p className="text-[15px] text-gold font-medium mb-2">1. Interruption cost</p>
              <p className="text-[15px] text-[var(--text-on-dark-muted)] font-light leading-[1.7]">
                Every command requires breaking your current context. If you are in a meeting, a
                conversation, or deep in thought, issuing a voice command forces a context switch. The
                mental cost of that switch often exceeds the value of the task, so you skip it.
              </p>
            </div>
            <div
              className="p-6 rounded-xl"
              style={{ background: "var(--dark-elevated)", border: "1px solid var(--dark-border)" }}
            >
              <p className="text-[15px] text-gold font-medium mb-2">2. Formulation cost</p>
              <p className="text-[15px] text-[var(--text-on-dark-muted)] font-light leading-[1.7]">
                You must translate a fuzzy need (&quot;I should deal with that parking ticket&quot;)
                into a precise instruction. Most people do not bother, which means most intents go
                unfulfilled. The gap between &quot;I should&quot; and a structured command is where
                most tasks die.
              </p>
            </div>
            <div
              className="p-6 rounded-xl"
              style={{ background: "var(--dark-elevated)", border: "1px solid var(--dark-border)" }}
            >
              <p className="text-[15px] text-gold font-medium mb-2">3. Memory cost</p>
              <p className="text-[15px] text-[var(--text-on-dark-muted)] font-light leading-[1.7]">
                If the moment passes and you forget to issue the command, the task never happens. Voice
                assistants require you to remember to use them. An assistant you have to remember to use
                is not much of an assistant.
              </p>
            </div>
          </div>

          {/* SVG Diagram: Explicit vs Ambient */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            Explicit Commands vs. Ambient Intent
          </h2>
          <div className="my-10 overflow-x-auto">
            <svg
              viewBox="0 0 800 420"
              xmlns="http://www.w3.org/2000/svg"
              className="w-full max-w-[800px] mx-auto"
              role="img"
              aria-label="Diagram comparing explicit command flow with ambient intent flow"
            >
              {/* Background */}
              <rect width="800" height="420" rx="16" fill="#141414" />

              {/* Top Label: Explicit Command Model */}
              <text x="400" y="40" textAnchor="middle" fill="#F5F0EB" fontSize="16" fontWeight="600">
                Explicit Command Model (Siri, Alexa)
              </text>

              {/* Explicit flow boxes */}
              <rect x="30" y="60" width="130" height="56" rx="8" fill="#1a1a1a" stroke="#333" strokeWidth="1" />
              <text x="95" y="84" textAnchor="middle" fill="#999" fontSize="11">You think of</text>
              <text x="95" y="100" textAnchor="middle" fill="#F5F0EB" fontSize="12" fontWeight="500">a need</text>

              <polygon points="168,88 180,88 180,82 192,90 180,98 180,92 168,92" fill="#555" />

              <rect x="200" y="60" width="130" height="56" rx="8" fill="#1a1a1a" stroke="#333" strokeWidth="1" />
              <text x="265" y="84" textAnchor="middle" fill="#999" fontSize="11">You formulate</text>
              <text x="265" y="100" textAnchor="middle" fill="#F5F0EB" fontSize="12" fontWeight="500">a command</text>

              <polygon points="338,88 350,88 350,82 362,90 350,98 350,92 338,92" fill="#555" />

              <rect x="370" y="60" width="130" height="56" rx="8" fill="#1a1a1a" stroke="#333" strokeWidth="1" />
              <text x="435" y="84" textAnchor="middle" fill="#999" fontSize="11">You say</text>
              <text x="435" y="100" textAnchor="middle" fill="#F5F0EB" fontSize="12" fontWeight="500">&quot;Hey Siri...&quot;</text>

              <polygon points="508,88 520,88 520,82 532,90 520,98 520,92 508,92" fill="#555" />

              <rect x="540" y="60" width="130" height="56" rx="8" fill="#1a1a1a" stroke="#333" strokeWidth="1" />
              <text x="605" y="84" textAnchor="middle" fill="#999" fontSize="11">AI processes</text>
              <text x="605" y="100" textAnchor="middle" fill="#F5F0EB" fontSize="12" fontWeight="500">your words</text>

              <polygon points="678,88 690,88 690,82 702,90 690,98 690,92 678,92" fill="#555" />

              <rect x="710" y="60" width="70" height="56" rx="8" fill="#1a1a1a" stroke="#C8A97E33" strokeWidth="1" />
              <text x="745" y="93" textAnchor="middle" fill="#C8A97E" fontSize="12" fontWeight="500">Result</text>

              {/* Effort indicator */}
              <text x="400" y="146" textAnchor="middle" fill="#ef4444" fontSize="12" fontWeight="500">
                ↑ Every step requires your effort and attention ↑
              </text>

              {/* Divider */}
              <line x1="40" y1="172" x2="760" y2="172" stroke="#333" strokeWidth="1" strokeDasharray="4,4" />

              {/* Bottom Label: Ambient Intent Model */}
              <text x="400" y="204" textAnchor="middle" fill="#F5F0EB" fontSize="16" fontWeight="600">
                Ambient Intent Model (Anticipy)
              </text>

              {/* Ambient flow boxes */}
              <rect x="40" y="224" width="160" height="72" rx="8" fill="#1a1a1a" stroke="#C8A97E44" strokeWidth="1" />
              <text x="120" y="252" textAnchor="middle" fill="#C8A97E" fontSize="12" fontWeight="500">You live your life</text>
              <text x="120" y="272" textAnchor="middle" fill="#999" fontSize="11">Talk, think, go about</text>
              <text x="120" y="286" textAnchor="middle" fill="#999" fontSize="11">your day normally</text>

              <polygon points="210,260 228,260 228,252 246,264 228,276 228,268 210,268" fill="#C8A97E55" />

              <rect x="260" y="224" width="160" height="72" rx="8" fill="#1a1a1a" stroke="#C8A97E44" strokeWidth="1" />
              <text x="340" y="252" textAnchor="middle" fill="#C8A97E" fontSize="12" fontWeight="500">AI listens passively</text>
              <text x="340" y="272" textAnchor="middle" fill="#999" fontSize="11">Continuous, background</text>
              <text x="340" y="286" textAnchor="middle" fill="#999" fontSize="11">audio processing</text>

              <polygon points="430,260 448,260 448,252 466,264 448,276 448,268 430,268" fill="#C8A97E55" />

              <rect x="480" y="224" width="140" height="72" rx="8" fill="#1a1a1a" stroke="#C8A97E88" strokeWidth="1.5" />
              <text x="550" y="252" textAnchor="middle" fill="#C8A97E" fontSize="12" fontWeight="500">Intent detected</text>
              <text x="550" y="272" textAnchor="middle" fill="#999" fontSize="11">&quot;We should book</text>
              <text x="550" y="286" textAnchor="middle" fill="#999" fontSize="11">dinner Friday&quot;</text>

              <polygon points="630,260 648,260 648,252 666,264 648,276 648,268 630,268" fill="#C8A97E55" />

              <rect x="680" y="224" width="100" height="72" rx="8" fill="#C8A97E22" stroke="#C8A97E" strokeWidth="1.5" />
              <text x="730" y="256" textAnchor="middle" fill="#C8A97E" fontSize="13" fontWeight="600">Task</text>
              <text x="730" y="274" textAnchor="middle" fill="#C8A97E" fontSize="13" fontWeight="600">completed</text>

              {/* Effort indicator */}
              <text x="400" y="328" textAnchor="middle" fill="#22c55e" fontSize="12" fontWeight="500">
                ↑ Only the first step involves you ↑
              </text>

              {/* Bottom summary */}
              <rect x="100" y="354" width="600" height="48" rx="8" fill="#C8A97E11" />
              <text x="400" y="382" textAnchor="middle" fill="#C8A97E" fontSize="13" fontWeight="500">
                Ambient intent closes the gap between thinking and doing.
              </text>
            </svg>
          </div>

          {/* Section: How It Works */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            How Ambient Intent Detection Works
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Ambient intent detection combines three technical capabilities: continuous audio processing,
            natural language understanding, and intent classification. Together, these systems turn
            ordinary conversation into actionable signals without any user effort.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            The process begins with audio capture. The wearable device (in Anticipy&apos;s case, a
            pendant with a microphone array) captures the audio environment around the wearer. This
            happens continuously, not in response to a wake word. On-device voice activity detection
            filters out silence, background noise, and music before anything leaves the device.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Next, the audio is processed through speech recognition and natural language understanding.
            The system transcribes relevant audio and analyzes it for semantic content. This is not
            keyword matching. The system understands context, relationships between speakers, and the
            pragmatic meaning behind statements. &quot;We should do Italian on Friday&quot; and &quot;I
            want to try that new pasta place this weekend&quot; both express the same underlying intent,
            even though they share almost no keywords.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Then, an intent classifier evaluates each segment for actionable meaning. &quot;We should
            get dinner Friday&quot; is flagged as a potential booking action. &quot;I need to cancel
            that subscription&quot; triggers a cancellation workflow. &quot;That charge on my card looks
            wrong&quot; initiates a dispute process. The classifier weighs factors like tone, repetition,
            specificity, and conversational context to separate genuine intent from idle conversation.
            Not every mention of dinner requires a reservation.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Once an intent is confirmed above the confidence threshold, the system&apos;s action engine
            takes over. In Anticipy, this is a browser-based AI agent that navigates real websites, fills
            real forms, and completes real transactions. It does not rely on APIs or partner integrations.
            It works on any website, the same way a human would.
          </p>

          {/* Section: Why It Matters */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            Why Ambient Intent Matters for Everyday Life
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            The average person has dozens of micro-intents every day that never get fulfilled. &quot;I
            should look into refinancing.&quot; &quot;I need to dispute that charge.&quot; &quot;We should
            plan something for Mom&apos;s birthday.&quot; These are real needs expressed in real
            conversations, and they evaporate because fulfilling them requires effort: opening an app,
            navigating a website, filling out a form, waiting on hold.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Ambient intent technology captures these moments. It turns passing thoughts into completed
            tasks. The impact compounds over time. A week of ambient intent fulfillment might mean a
            restaurant reservation you would have forgotten, a subscription you have been meaning to
            cancel for months, and a disputed charge that recovers money you would have written off.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            This is not about convenience for its own sake. It is about closing the gap between
            intention and action. Psychologists call this the &quot;intention-action gap,&quot; and it is
            one of the most studied phenomena in behavioral science. People consistently fail to act on
            their own stated goals, not because they lack motivation, but because the friction of
            execution is too high. Every additional step between wanting something and getting it reduces
            the probability that it happens.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Ambient intent reduces that friction to zero. You do not need to remember, plan, initiate,
            or follow through. You only need to live your life, and the system handles the rest.
          </p>

          {/* Section: Technology Stack */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            The Technology Behind Anticipy&apos;s Ambient Intent
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Building an ambient intent system requires solving several hard problems simultaneously.
            Each layer of the stack must work reliably for the overall experience to feel effortless.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Audio processing must be continuous, low-power, and privacy-respecting. Anticipy&apos;s
            pendant runs on-device voice activity detection, which means raw audio is processed locally.
            Only segments classified as potentially actionable are sent to the cloud for further
            analysis. Ambient noise, music, and background chatter are filtered at the hardware level.
            No raw audio is stored on any server.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Intent classification must be accurate enough to act on real conversations without generating
            false positives. A system that books a restaurant every time someone mentions food would be
            worse than no system at all. Anticipy&apos;s classifier uses a multi-stage pipeline: first
            detecting that a statement contains actionable content, then classifying the specific action
            type, then extracting the parameters needed to fulfill it (restaurant name, date, party
            size, and so on).
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            The action engine must be capable of completing tasks on arbitrary websites without
            pre-built integrations. This is perhaps the hardest technical problem. Anticipy&apos;s engine
            uses a browser-based AI agent that reads web pages the same way a human does: it navigates
            to URLs, reads page content, identifies form fields, clicks buttons, and enters information.
            This approach means it works on any website. There is no need to build and maintain
            integrations with thousands of services.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Finally, the whole system must be fast enough that the user does not need to think about
            timing. If someone mentions needing a restaurant reservation, the booking should be
            underway within seconds. Latency in any layer of the stack degrades the experience from
            &quot;magical&quot; to &quot;slow assistant.&quot;
          </p>

          {/* Section: The Future */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            The Future of Human-AI Interaction
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Ambient intent is not a feature. It is a paradigm shift in how humans and AI systems relate
            to each other. The progression has been clear over the past forty years: from typing
            commands, to clicking graphical interfaces, to speaking commands, and now to simply living
            while AI listens and acts.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Each transition has reduced the effort required from the human. Typing required formulating
            and entering text. Clicking required navigating visual interfaces. Speaking required
            formulating and vocalizing commands. Ambient intent requires nothing at all beyond living
            your normal life.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            This does not mean humans lose control. Anticipy includes confirmation flows for sensitive
            actions, spending limits, and blocked categories. The user sets boundaries, and the system
            operates within them. But within those boundaries, the system acts autonomously. That is the
            key difference from every previous generation of AI assistant: it does not wait to be asked.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-10">
            We believe ambient intent will become the dominant interaction model for personal AI within
            the next few years. The technology is ready. The hardware is small enough. The language
            models are accurate enough. The remaining question is which products will get the
            implementation right. That is what we are building at{" "}
            <Link href="/" className="text-gold hover:underline">
              Anticipy
            </Link>.
          </p>

          {/* FAQ Section */}
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
              Experience ambient intent firsthand.
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light mb-8">
              Anticipy is currently accepting waitlist signups.
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

      {/* JSON-LD FAQPage Schema */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(faqSchema) }}
      />
    </div>
  );
}
