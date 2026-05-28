import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Who Is Anticipy For? Use Cases by Role",
  description:
    "See how founders, lawyers, parents, and doctors use Anticipy to turn ambient conversation into completed tasks. Real scenarios for real people.",
  openGraph: {
    title: "Who Is Anticipy For? Use Cases by Role",
    description:
      "Real use cases for the AI wearable that acts. See how different professionals use ambient intent.",
    url: "https://www.anticipy.ai/for",
    siteName: "Anticipy",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Who Is Anticipy For? Use Cases by Role",
    description:
      "Real use cases for the AI wearable that acts. See how different professionals use ambient intent.",
  },
  alternates: {
    canonical: "https://www.anticipy.ai/for",
  },
};

const audiences = [
  {
    href: "/for/founders",
    title: "Anticipy for Founders",
    description:
      "Investor follow-ups, vendor cancellations, team scheduling. Anticipy catches the action items that fall through the cracks of a 14-hour day.",
    tag: "Founders",
  },
  {
    href: "/for/lawyers",
    title: "Anticipy for Lawyers",
    description:
      "Deadline reminders, room bookings, client intake scheduling. Ambient intent for legal professionals, with a clear discussion of privacy and confidentiality.",
    tag: "Lawyers",
  },
  {
    href: "/for/parents",
    title: "Anticipy for Parents",
    description:
      "School deadlines, pediatrician appointments, activity sign-ups. Catching the logistics that get mentioned once and forgotten immediately.",
    tag: "Parents",
  },
  {
    href: "/for/doctors",
    title: "Anticipy for Doctors",
    description:
      "Personal scheduling, admin tasks, and CME sign-ups outside the clinical setting. Includes a clear discussion of HIPAA boundaries.",
    tag: "Doctors",
  },
];

export default function ForPage() {
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
            href="/"
            className="text-[15px] text-[var(--text-on-dark-muted)] hover:text-gold transition-colors"
          >
            Back to Home
          </Link>
        </div>
      </header>

      <main className="px-6 py-16">
        <div className="max-w-3xl mx-auto">
          <h1 className="font-serif text-[clamp(32px,5vw,48px)] text-[var(--text-on-dark)] leading-[1.15] mb-4">
            Who Is Anticipy For?
          </h1>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-4">
            Anticipy is an AI wearable pendant that listens to your day and completes tasks you
            mention in conversation. No commands. No apps. Just results.
          </p>
          <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light leading-[1.8] mb-12">
            Different people use it differently. Below are real use cases for specific roles, with
            honest discussion of what Anticipy does and does not do for each.
          </p>

          <div className="space-y-6 mb-16">
            {audiences.map((a) => (
              <Link
                key={a.href}
                href={a.href}
                className="block p-8 rounded-xl transition-all duration-300 hover:border-gold"
                style={{
                  background: "var(--dark-elevated)",
                  border: "1px solid var(--dark-border)",
                }}
              >
                <div className="flex items-center gap-3 mb-3">
                  <span className="text-[12px] font-medium px-3 py-1 rounded-full bg-gold/10 text-gold">
                    {a.tag}
                  </span>
                </div>
                <h2 className="text-[22px] text-[var(--text-on-dark)] font-medium mb-2">
                  {a.title}
                </h2>
                <p className="text-[15px] text-[var(--text-on-dark-muted)] font-light leading-[1.7]">
                  {a.description}
                </p>
              </Link>
            ))}
          </div>

          <div className="text-center py-16 border-t" style={{ borderColor: "var(--dark-border)" }}>
            <p className="font-serif text-[clamp(24px,4vw,32px)] text-[var(--text-on-dark)] leading-[1.2] mb-4">
              See yourself here?
            </p>
            <p className="text-[17px] text-[var(--text-on-dark-muted)] font-light mb-8">
              Anticipy is currently accepting waitlist signups. $149, first year included.
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
