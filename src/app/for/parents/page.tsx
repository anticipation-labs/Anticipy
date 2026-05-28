import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Anticipy for Parents: AI Pendant That Catches Family Logistics",
  description:
    "How parents use Anticipy to catch school deadlines, book pediatrician visits, sign up for activities, and handle the logistics mentioned once and forgotten.",
  openGraph: {
    title: "Anticipy for Parents: AI Pendant for Family Logistics",
    description:
      "School deadlines, doctor appointments, activity sign-ups. Anticipy catches what gets mentioned once and forgotten.",
    url: "https://www.anticipy.ai/for/parents",
    siteName: "Anticipy",
    type: "article",
  },
  twitter: {
    card: "summary_large_image",
    title: "Anticipy for Parents: AI Pendant for Family Logistics",
    description:
      "School deadlines, doctor appointments, activity sign-ups. Anticipy catches what gets mentioned once and forgotten.",
  },
  alternates: {
    canonical: "https://www.anticipy.ai/for/parents",
  },
};

const faqItems = [
  {
    question: "Does Anticipy record my children's conversations?",
    answer:
      "No. Anticipy does not record anyone's conversations. It processes audio in real-time to detect actionable tasks, then discards the audio immediately. It does not build profiles of family members, store recordings of children, or retain any audio data. The only thing it keeps is the task it detected and the result.",
  },
  {
    question: "What if my child says something that sounds like a task but isn't?",
    answer:
      "Anticipy uses a high confidence threshold for intent detection and focuses on statements made by the wearer or directed at the wearer. A child saying \"I want pizza\" in the background would not trigger a restaurant booking. The system is tuned to detect genuine, actionable intent from conversational context, not to act on every statement it overhears.",
  },
  {
    question: "Can I use Anticipy to monitor or track my kids?",
    answer:
      "No, and it is not designed for that. Anticipy does not record, transcribe, or store conversations. It does not track location. It does not build behavioral profiles. It is a task execution tool: it catches logistics you mention and completes them. It is not a surveillance or monitoring product.",
  },
  {
    question: "Does it work with school portals and parent apps?",
    answer:
      "Anticipy operates through a web browser. If your school's parent portal is accessible via the web and you have an active login session, Anticipy can navigate it to complete tasks like signing permission slips or registering for events. It cannot interact with native mobile apps directly.",
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

export default function ForParentsPage() {
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
              For Parents
            </span>
          </div>
          <h1 className="font-serif text-[clamp(32px,5vw,48px)] text-[var(--text-on-dark)] leading-[1.15] mb-8">
            The AI Pendant That Catches the Things You&apos;ll Forget by Dinner
          </h1>

          {/* Opening */}
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy is an AI wearable pendant that listens to your conversations and completes the
            tasks you mention. For parents, this means catching the constant stream of logistics that
            gets mentioned once, in passing, and then lost in the noise of managing a family. The
            teacher says picture day is Tuesday. Your spouse mentions the pediatrician needs to be
            scheduled. A neighbor tells you soccer sign-ups close Friday. Each of these is a five-minute
            task, and each one gets buried under the next demand on your attention.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Anticipy catches these moments. It detects that you need to do something, and it does it.
            It does not record your family. It does not build profiles of your children. It does not
            monitor anyone. It listens for logistics, acts on them, and discards the audio. Below is
            what that looks like in a parent&apos;s actual day.
          </p>

          {/* Day walkthrough */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            A Parent&apos;s Day with Anticipy
          </h2>

          <div
            className="p-6 rounded-xl mb-6"
            style={{ background: "var(--dark-elevated)", border: "1px solid var(--dark-border)" }}
          >
            <p className="text-[13px] text-gold font-medium mb-2 uppercase tracking-wider">
              8:15 AM / School Drop-Off
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-3">
              You are walking your daughter to her classroom. The teacher catches you at the door:
              &quot;Just a reminder, picture day is next Tuesday. There is an order form on the parent
              portal. And we still need two volunteers for the bake sale on the 15th.&quot;
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8]">
              <span className="text-gold">Anticipy detects two items.</span> It creates a calendar
              reminder for picture day on Tuesday with a note about the order form. It also sets a
              reminder about the bake sale volunteer sign-up. If the parent portal is web-accessible,
              it can navigate to the photo order form and start filling it in for you to review.
            </p>
          </div>

          <div
            className="p-6 rounded-xl mb-6"
            style={{ background: "var(--dark-elevated)", border: "1px solid var(--dark-border)" }}
          >
            <p className="text-[13px] text-gold font-medium mb-2 uppercase tracking-wider">
              10:30 AM / Phone Call with Your Spouse
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-3">
              Midmorning, your spouse calls. Between work updates, they mention: &quot;We need to
              schedule Ethan&apos;s annual checkup. The pediatrician said to come in before the end of
              the month. And can you look into that swim class at the community center? Registration
              opened this week.&quot;
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8]">
              <span className="text-gold">Anticipy picks up both.</span> It navigates to the
              pediatrician&apos;s online booking system and looks for available appointments before
              month&apos;s end, presenting you with options. Separately, it finds the community
              center&apos;s swim class registration page and starts the sign-up process. You get two
              confirmations to review instead of two items on a mental to-do list you will forget by
              lunch.
            </p>
          </div>

          <div
            className="p-6 rounded-xl mb-6"
            style={{ background: "var(--dark-elevated)", border: "1px solid var(--dark-border)" }}
          >
            <p className="text-[13px] text-gold font-medium mb-2 uppercase tracking-wider">
              3:30 PM / Playground Conversation
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-3">
              At after-school pickup, another parent says: &quot;Soccer sign-ups for spring close this
              Friday. I almost missed it last year. The link is on the league website.&quot; You
              reply: &quot;Thanks, I need to get my son signed up before I forget.&quot;
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8]">
              <span className="text-gold">Anticipy detects the registration intent.</span> It
              searches for the local youth soccer league website, finds the spring registration page,
              and begins the process. It fills in what it can from your prior interactions and holds
              the form for you to review and submit. The sign-up that would have been a Friday night
              panic is handled Tuesday afternoon.
            </p>
          </div>

          <div
            className="p-6 rounded-xl mb-6"
            style={{ background: "var(--dark-elevated)", border: "1px solid var(--dark-border)" }}
          >
            <p className="text-[13px] text-gold font-medium mb-2 uppercase tracking-wider">
              8:45 PM / After Bedtime
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-3">
              The kids are in bed. You are on the phone with your sister and say: &quot;I really need
              to cancel that streaming service the kids do not watch anymore. And I should book a
              table for Mom&apos;s birthday dinner this Saturday.&quot;
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8]">
              <span className="text-gold">Anticipy handles both.</span> It navigates to the streaming
              service, finds the cancellation flow, and walks through it. It then searches for
              restaurant availability for Saturday and presents options. You confirm the cancellation
              and pick a restaurant, all without opening your laptop or pulling up a browser.
            </p>
          </div>

          {/* Why this matters */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            The Parent&apos;s Logistics Problem
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Parents are unique among Anticipy&apos;s users because their action items come from
            everywhere: teachers, coaches, other parents, spouses, their own observations, school
            newsletters, doctor&apos;s offices, and the kids themselves. The information arrives at
            unpredictable times in unpredictable contexts. At drop-off. On the phone while cooking.
            In passing at the playground.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            The common thread is that these tasks are mentioned once, briefly, in the middle of
            something else. There is no natural moment to stop and write a reminder. The teacher is
            talking to you while thirty other parents are trying to get through the door. Your spouse
            mentions it between two other topics on a five-minute call. The other parent drops it
            casually while the kids are running around.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Each task is small. Picture day is a five-minute errand. Soccer sign-up takes ten minutes.
            But parents typically juggle ten to twenty of these per week, and the penalty for missing
            one ranges from mild inconvenience (no pictures) to genuine stress (missed medical
            appointment). Anticipy catches them at the moment they are mentioned, before they can be
            lost.
          </p>

          {/* Privacy for families */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            Privacy and Children
          </h2>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            Parents should know exactly how Anticipy handles audio in a household with children.
            Anticipy does not record, store, or transcribe any audio, including children&apos;s
            voices. It processes audio in real-time to detect actionable intent from the wearer&apos;s
            conversations, then discards the audio completely. There is no voice profile of your child.
            There is no stored conversation. There is no behavioral analysis.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-6">
            The system is designed to detect intent expressed by or directed at the wearer. A child
            saying &quot;I want juice&quot; in the background does not generate a task. Anticipy
            focuses on conversational context that includes clear, actionable statements: &quot;we need
            to schedule the checkup,&quot; &quot;sign up for soccer before Friday,&quot; &quot;cancel
            that subscription.&quot; Background noise, children playing, and general household audio
            are filtered out at the processing level.
          </p>

          {/* What Anticipy does NOT do */}
          <h2 className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mt-16 mb-6">
            What Anticipy Does Not Do for Parents
          </h2>
          <ul className="space-y-4 mb-6">
            {[
              ["Child monitoring.", "Anticipy does not track, record, or monitor children. It is not a parental control tool, a baby monitor, or a safety tracker."],
              ["Family calendar management.", "Anticipy can create individual calendar events from detected intent, but it does not manage or sync shared family calendars. It does not resolve scheduling conflicts between family members."],
              ["Homework help.", "If your child says \"I need help with my math,\" Anticipy will not provide tutoring. It detects logistical tasks, not educational ones."],
              ["Medical advice.", "Anticipy can schedule a pediatrician appointment. It cannot assess symptoms, recommend treatment, or make medical decisions."],
              ["School communication.", "It does not read or respond to school emails, apps, or newsletters on your behalf. It catches tasks mentioned verbally in your conversations."],
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
              Stop losing track of the little things.
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
