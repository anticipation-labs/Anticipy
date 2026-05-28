import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Anticipy for Lawyers: AI Pendant for Legal Professionals",
  description:
    "How lawyers use Anticipy to catch deadline reminders, book conference rooms, schedule client meetings, and handle admin tasks from ambient conversation.",
  openGraph: {
    title: "Anticipy for Lawyers: AI Pendant for Legal Professionals",
    description:
      "Ambient intent for legal professionals. Deadlines, bookings, and scheduling from conversation.",
    url: "https://www.anticipy.ai/for/lawyers",
    siteName: "Anticipy",
    type: "article",
  },
  twitter: {
    card: "summary_large_image",
    title: "Anticipy for Lawyers: AI Pendant for Legal Professionals",
    description:
      "Ambient intent for legal professionals. Deadlines, bookings, and scheduling from conversation.",
  },
  alternates: {
    canonical: "https://www.anticipy.ai/for/lawyers",
  },
};

const faqItems = [
  {
    question: "Does Anticipy store recordings of my client conversations?",
    answer:
      "No. Anticipy processes audio in real-time to detect actionable intent, then discards the audio immediately. It does not create transcripts, recordings, or any persistent copy of what was said. The only data it retains is the detected task (for example, \"book conference room B for Thursday 2pm\") and the outcome.",
  },
  {
    question: "Can Anticipy access my firm's internal systems like document management or billing?",
    answer:
      "Anticipy operates through a web browser. If your firm's systems are accessible via a web interface and you have logged-in sessions, Anticipy can interact with them in the same way you would. However, it does not have native integrations with legal-specific platforms like Clio, NetDocuments, or iManage. It navigates web pages, not desktop applications.",
  },
  {
    question: "What if Anticipy detects a task I did not actually intend?",
    answer:
      "Anticipy uses a high confidence threshold and always asks for confirmation before executing sensitive actions like cancellations, financial transactions, or sending communications. If it detects something you did not intend, you simply decline the confirmation and the action is not taken.",
  },
  {
    question: "Is the pendant appropriate to wear in court?",
    answer:
      "Anticipy is an 8-gram brushed titanium pendant that resembles ordinary jewelry. Whether it is appropriate in a specific courtroom depends on local rules regarding electronic devices. Many courtrooms prohibit recording devices, and while Anticipy does not record, it does contain a microphone. Check your jurisdiction's rules before wearing it in court settings.",
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

export default function ForLawyersPage() {
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
              For Lawyers
            </span>
          </div>
          <h1 className="font-serif text-[clamp(32px,5vw,48px)] text-[var(--text-on-dark)] leading-[1.15] mb-8">
            Ambient Intent for Legal Professionals
          </h1>

          {/* Opening */}
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy is an AI wearable pendant that listens to your conversations and completes tasks
            you mention. For lawyers, this means the logistical side of practice: scheduling client
            meetings, booking conference rooms, setting deadline reminders, and handling the
            administrative tasks that accumulate between substantive legal work. You mention something
            that needs to happen, and Anticipy handles it in the background.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Legal professionals operate under unique constraints around confidentiality and privilege.
            This page addresses those constraints directly. Anticipy does not record, store, or
            transcribe any audio. It processes conversations in real-time to detect actionable intent,
            then discards the audio entirely. The system is designed to retain only the task it detected
            and the result of executing it. Below is a detailed look at how this works in a lawyer&apos;s
            daily routine.
          </p>

          {/* Day walkthrough */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            A Lawyer&apos;s Day with Anticipy
          </h2>

          <div
            className="p-6 rounded-xl mb-6"
            style={{ background: "var(--dark-elevated)", border: "1px solid var(--dark-border)" }}
          >
            <p className="text-[13px] text-gold font-medium mb-2 uppercase tracking-wider">
              9:00 AM / Client Intake Call
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-3">
              You speak with a prospective client about a commercial lease dispute. Near the end of the
              call, you say: &quot;I will send over the engagement letter by end of day Friday. Let me
              also schedule a follow-up for next Tuesday so we can review the documents you are
              sending over.&quot;
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8]">
              <span className="text-gold">Anticipy detects two tasks:</span> (1) a deadline to send
              the engagement letter by Friday, and (2) a meeting to schedule for next Tuesday. It
              creates a calendar event for the follow-up and sets a reminder for the engagement letter
              deadline. You confirm both with a quick review.
            </p>
          </div>

          <div
            className="p-6 rounded-xl mb-6"
            style={{ background: "var(--dark-elevated)", border: "1px solid var(--dark-border)" }}
          >
            <p className="text-[13px] text-gold font-medium mb-2 uppercase tracking-wider">
              11:30 AM / Hallway Conversation with a Partner
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-3">
              On the way back from the kitchen, a senior partner stops you. &quot;The deposition for
              the Martinez matter is next Thursday. Make sure conference room B is booked for the full
              day, and order lunch for six people.&quot;
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8]">
              <span className="text-gold">Anticipy catches both requests.</span> It navigates to your
              firm&apos;s room booking system (if web-accessible) and reserves conference room B for
              the full day. It then searches catering options and presents you with a few choices for
              lunch delivery. You approve the room booking immediately and pick a catering option
              before your next meeting.
            </p>
          </div>

          <div
            className="p-6 rounded-xl mb-6"
            style={{ background: "var(--dark-elevated)", border: "1px solid var(--dark-border)" }}
          >
            <p className="text-[13px] text-gold font-medium mb-2 uppercase tracking-wider">
              2:00 PM / Phone Call with Opposing Counsel
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-3">
              During a call to negotiate discovery timelines, opposing counsel proposes: &quot;Let us
              set the document production deadline for April 30.&quot; You agree to the date.
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8]">
              <span className="text-gold">Anticipy detects a deadline.</span> It creates a calendar
              event for April 30 with a reminder set for one week before. Missed deadlines are among
              the most common sources of malpractice claims. Having an automated system catch deadline
              mentions in real-time adds a layer of safety beyond manual docketing.
            </p>
          </div>

          <div
            className="p-6 rounded-xl mb-6"
            style={{ background: "var(--dark-elevated)", border: "1px solid var(--dark-border)" }}
          >
            <p className="text-[13px] text-gold font-medium mb-2 uppercase tracking-wider">
              5:45 PM / Leaving the Office
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-3">
              You are on the phone with your spouse and mention: &quot;I need to renew my bar
              association membership before the end of the month. And we should book that restaurant
              for Saturday.&quot;
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8]">
              <span className="text-gold">Anticipy handles both.</span> It navigates to the bar
              association website to begin the renewal process and searches for restaurant availability
              on Saturday. Personal administrative tasks and professional ones are handled identically.
              Anticipy does not distinguish between work and life. It catches intent wherever it appears.
            </p>
          </div>

          {/* Privacy and Confidentiality */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            Privacy, Privilege, and Confidentiality
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Lawyers have professional obligations around client confidentiality that go beyond general
            privacy preferences. Attorney-client privilege and work product doctrine create specific
            requirements for how communications and work materials are handled. Any tool that processes
            audio in a legal context must be evaluated against these obligations.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy&apos;s architecture is designed around minimal data retention. Audio is processed
            in real-time through the intent detection pipeline and immediately discarded. No transcript
            is created. No recording exists. The only data retained is the structured task description
            (for example, &quot;book conference room B, Thursday, full day&quot;) and the outcome of
            that action. This means there is no stored communication content that could be subject to
            discovery, subpoena, or unauthorized access.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            That said, audio does pass through cloud processing during the intent detection phase. This
            means a third-party system (Anticipy&apos;s servers) briefly processes audio that may
            include privileged communications. Lawyers should evaluate whether this is acceptable under
            their jurisdiction&apos;s ethics rules and their firm&apos;s technology use policies. Many
            jurisdictions require only that attorneys take &quot;reasonable measures&quot; to protect
            client confidences, and the absence of any stored audio may satisfy that standard. However,
            this is a legal determination each attorney must make independently.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            For attorneys who prefer additional caution, Anticipy can be removed during privileged
            conversations and worn only during non-privileged interactions. The pendant is designed to
            be easy to put on and take off. Since it processes each conversation independently with no
            accumulated context, removing it for a specific conversation has no effect on its ability
            to function during other parts of the day.
          </p>

          {/* What Anticipy does NOT do */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            What Anticipy Does Not Do for Lawyers
          </h2>
          <ul className="space-y-4 mb-6">
            {[
              ["Legal research.", "Anticipy does not search case law, analyze statutes, or draft legal memoranda. It handles logistics, not substantive legal work."],
              ["Document review or drafting.", "It does not review contracts, redline documents, or generate legal filings. These tasks require specialized legal tools and professional judgment."],
              ["Case strategy.", "Anticipy does not advise on litigation strategy, negotiation tactics, or settlement decisions. It executes administrative tasks, not legal ones."],
              ["Billing and time tracking.", "It does not log billable hours, generate invoices, or interact with billing software. Time entry remains a manual process."],
              ["Court filings.", "Anticipy does not file documents with courts, serve papers, or interact with e-filing systems. These require specialized workflows with authentication and verification."],
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
              Let the logistics handle themselves.
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
