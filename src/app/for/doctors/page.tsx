import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Anticipy for Doctors: AI Pendant for Personal and Admin Tasks",
  description:
    "How doctors use Anticipy outside the clinical setting: CME sign-ups, personal scheduling, admin tasks. Includes clear discussion of HIPAA boundaries.",
  robots: { index: false, follow: true },
  openGraph: {
    title: "Anticipy for Doctors: AI Pendant for Personal and Admin Tasks",
    description:
      "Ambient intent for doctors outside the clinical setting. CME, scheduling, admin, with HIPAA boundaries discussed.",
    url: "https://www.anticipy.ai/for/doctors",
    siteName: "Anticipy",
    type: "article",
  },
  twitter: {
    card: "summary_large_image",
    title: "Anticipy for Doctors: AI Pendant for Personal and Admin Tasks",
    description:
      "Ambient intent for doctors outside the clinical setting. CME, scheduling, admin, with HIPAA boundaries discussed.",
  },
  alternates: {
    canonical: "https://www.anticipy.ai/for/doctors",
  },
};

const faqItems = [
  {
    question: "Can I wear Anticipy during patient consultations?",
    answer:
      "No. Anticipy is not HIPAA-compliant and should not be worn during patient encounters. Any audio processing of conversations that include Protected Health Information (PHI) would require a Business Associate Agreement and HIPAA-compliant data handling, which Anticipy does not currently provide. Anticipy is designed for use outside clinical settings: break rooms, personal calls, administrative meetings, and personal errands.",
  },
  {
    question: "Does Anticipy store any health-related data?",
    answer:
      "Anticipy does not store audio, transcripts, or recordings. It processes audio in real-time to detect actionable tasks, then discards the audio. The only data retained is the task description and its outcome. If you use Anticipy to schedule your own dentist appointment, for example, the system retains that a dentist appointment was booked, not the conversation that led to it.",
  },
  {
    question: "Could Anticipy eventually become HIPAA-compliant?",
    answer:
      "HIPAA compliance for an ambient audio processing system would require significant changes to Anticipy's data handling architecture, including encryption, access controls, audit logging, and a Business Associate Agreement framework. This is not on the current product roadmap. The scenarios on this page are specifically limited to non-clinical, non-PHI contexts.",
  },
  {
    question: "Is the pendant noticeable under scrubs or a white coat?",
    answer:
      "Anticipy is an 8-gram brushed titanium pendant on a chain. It can be worn under scrubs or a white coat and is not visible when tucked under a collar. However, it should be removed before entering clinical areas where patient conversations occur.",
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

export default function ForDoctorsPage() {
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
          <div className="mb-4 flex items-center gap-3">
            <span className="text-[12px] font-medium px-3 py-1 rounded-full bg-gold/10 text-gold">
              For Doctors
            </span>
            <span className="text-[12px] font-medium px-3 py-1 rounded-full bg-yellow-500/10 text-yellow-400">
              Draft: Under Review
            </span>
          </div>

          {/* HIPAA Notice */}
          <div
            className="p-6 rounded-xl mb-8"
            style={{ background: "rgba(234, 179, 8, 0.08)", border: "1px solid rgba(234, 179, 8, 0.2)" }}
          >
            <p className="text-[15px] text-yellow-300 font-medium mb-2">Important: HIPAA Boundaries</p>
            <p className="text-[14px] text-yellow-200/70 font-light leading-[1.7]">
              Anticipy is <strong>not HIPAA-compliant</strong> and must not be worn during patient
              encounters or in any setting where Protected Health Information (PHI) may be discussed.
              All scenarios on this page are limited to non-clinical contexts: personal scheduling,
              administrative tasks, and activities outside patient care areas.
            </p>
          </div>

          <h1 className="font-serif text-[clamp(32px,5vw,48px)] text-[var(--text-on-dark)] leading-[1.15] mb-8">
            AI Pendant for the Non-Clinical Side of Being a Doctor
          </h1>

          {/* Opening */}
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy is an AI wearable pendant that listens to your conversations and completes tasks
            you mention. For doctors, the relevant use cases are strictly outside the clinical
            setting. Anticipy is not a medical tool and does not handle patient data. What it does is
            catch the personal and administrative tasks that doctors accumulate during break room
            conversations, calls with colleagues about non-patient matters, personal phone calls, and
            the everyday logistics of a life that is chronically short on time.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Physicians work long, unpredictable hours. Personal tasks pile up because there is no
            natural break in the day to handle them. You mention needing to reschedule your dentist
            appointment while walking to the parking garage. You tell a colleague you want to sign up
            for a dermatology conference while grabbing coffee. You remind yourself to cancel a
            subscription while eating lunch. These are the tasks Anticipy catches and completes. The
            pendant goes on when you leave the clinical area and handles the rest of your life.
          </p>

          {/* Day walkthrough */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            A Doctor&apos;s Day with Anticipy (Non-Clinical Scenarios Only)
          </h2>

          <div
            className="p-6 rounded-xl mb-6"
            style={{ background: "var(--dark-elevated)", border: "1px solid var(--dark-border)" }}
          >
            <p className="text-[13px] text-gold font-medium mb-2 uppercase tracking-wider">
              7:15 AM / Commute
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-3">
              Driving to the hospital, you are on the phone with your spouse. They say: &quot;Your
              dentist called yesterday to remind you about the cleaning. Also, can you look into that
              summer camp for the kids? Registration closes next week.&quot;
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8]">
              <span className="text-gold">Anticipy catches both items.</span> It navigates to the
              dental office&apos;s online scheduling system and searches for available cleaning
              appointments. It also finds the summer camp registration page and starts the application.
              By the time you park, you have two items ready for review instead of two things to
              remember during a 12-hour shift.
            </p>
          </div>

          <div
            className="p-6 rounded-xl mb-6"
            style={{ background: "var(--dark-elevated)", border: "1px solid var(--dark-border)" }}
          >
            <p className="text-[13px] text-gold font-medium mb-2 uppercase tracking-wider">
              12:30 PM / Break Room
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-3">
              During lunch, a colleague mentions a dermatology conference in October that has a great
              speaker lineup. You say: &quot;That sounds useful. I should sign up before it fills up.
              I need the CME credits anyway.&quot;
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8]">
              <span className="text-gold">Anticipy detects the registration intent.</span> It finds
              the conference website, locates the registration page, and starts the sign-up process.
              You review and confirm the registration before the end of your break. The CME credit
              opportunity that would have been forgotten by afternoon rounds is now secured.
            </p>
          </div>

          <div
            className="p-6 rounded-xl mb-6"
            style={{ background: "var(--dark-elevated)", border: "1px solid var(--dark-border)" }}
          >
            <p className="text-[13px] text-gold font-medium mb-2 uppercase tracking-wider">
              4:00 PM / Administrative Meeting
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-3">
              In a department meeting (non-patient, administrative only), the department chief says:
              &quot;We need to book a restaurant for the year-end team dinner. Somewhere that can handle
              twenty people, ideally downtown.&quot; You volunteer to handle it.
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8]">
              <span className="text-gold">Anticipy catches the task.</span> It searches for restaurants
              downtown that accommodate groups of twenty, checks availability for the likely date range,
              and presents you with options. You pick one and confirm the reservation before the
              meeting ends.
            </p>
          </div>

          <div
            className="p-6 rounded-xl mb-6"
            style={{ background: "var(--dark-elevated)", border: "1px solid var(--dark-border)" }}
          >
            <p className="text-[13px] text-gold font-medium mb-2 uppercase tracking-wider">
              7:00 PM / Driving Home
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-3">
              On the phone with a friend, you say: &quot;I need to cancel that gym membership I have
              not used in three months. And I should book a flight to visit my parents next month.&quot;
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8]">
              <span className="text-gold">Anticipy handles both.</span> It navigates to the gym
              website and starts the cancellation process. It searches for flights to your
              parents&apos; city for next month and presents options by price and schedule. Two tasks
              that would have waited until a rare free evening are handled during the commute.
            </p>
          </div>

          {/* Why this matters for doctors */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            The Physician&apos;s Time Problem
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Doctors work some of the most unpredictable schedules in any profession. A planned lunch
            break becomes an emergency. An evening off becomes an on-call shift. The personal tasks
            that most people handle during downtime have no reliable window in a physician&apos;s day.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            The result is a growing backlog of personal and administrative tasks: dentist appointments
            that get pushed for months, CME credits that get handled at the last minute, subscriptions
            that keep charging long after they stopped being useful, and personal logistics that fall
            entirely to a spouse or partner because the doctor simply has no time.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy does not add time to your day. It eliminates the need for time in the first place.
            When you mention a task in conversation, it gets done. You do not need to find a free
            fifteen minutes to sit down, open a browser, and navigate a website. The task moves from
            &quot;mentioned&quot; to &quot;completed&quot; without any dedicated time investment from you.
          </p>

          {/* HIPAA and clinical boundaries */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            HIPAA and Clinical Boundaries
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy processes audio through a cloud-based pipeline. Any conversation involving
            Protected Health Information (PHI) processed through this pipeline would constitute
            unauthorized PHI disclosure under HIPAA regulations. Anticipy does not have a Business
            Associate Agreement (BAA), does not maintain HIPAA-compliant data handling procedures, and
            is not designed for clinical use.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            This means Anticipy must be removed before entering clinical areas where patient
            conversations occur. The recommended workflow is straightforward: wear the pendant during
            your commute, during breaks in non-clinical areas, and during personal time. Remove it
            before entering exam rooms, patient floors, or any area where PHI may be discussed.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            At 8 grams, the pendant is easy to put on and take off. Since Anticipy processes each
            conversation independently with no accumulated context, removing it for clinical hours has
            no impact on its functionality during other parts of the day. The pendant you put back on
            at 5 PM works just as well as if you had worn it all day.
          </p>

          {/* What Anticipy does NOT do */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            What Anticipy Does Not Do for Doctors
          </h2>
          <ul className="space-y-4 mb-6">
            {[
              ["Patient scheduling.", "Anticipy does not schedule patient appointments, manage patient calendars, or interact with electronic health record (EHR) systems. It handles your personal scheduling only."],
              ["Clinical documentation.", "It does not create clinical notes, dictate medical records, or interact with charting systems. Medical documentation requires HIPAA-compliant tools."],
              ["Medical orders.", "Anticipy does not place prescriptions, lab orders, or referrals. These require clinical judgment and authenticated access to medical systems."],
              ["Diagnosis or medical advice.", "It does not interpret symptoms, suggest diagnoses, or provide any form of medical guidance. It is a task execution tool, not a clinical decision support system."],
              ["Anything involving PHI.", "If a task requires accessing, creating, or transmitting Protected Health Information, Anticipy cannot and should not be used for it."],
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
              Reclaim the personal time your schedule took.
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
