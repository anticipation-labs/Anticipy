import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Book a call — Anticipy",
  description:
    "Book a quick call with the Anticipy team. Questions about the pendant, pre-orders, or privacy — pick a time that works for you.",
};

const CAL_LINK = "https://calendar.app.google/QnCVQxa9Aj3x8QKD7";
const CAL_EMBED =
  "https://calendar.google.com/calendar/appointments/schedules/AcZssZ30VqtLax0yLxRLrPymbks4JOmA39jo2X42gUw6FC_9O5BgpgkH5ch_fHDgSPp7YPHcVNg85McP?gv=true";

export default function BookPage() {
  return (
    <div className="min-h-screen section-cream">
      <header
        className="px-6 py-6 border-b"
        style={{ borderColor: "var(--cream-border)" }}
      >
        <div className="max-w-3xl mx-auto flex justify-between items-center">
          <Link
            href="/"
            className="font-serif text-[22px] text-[var(--text-on-light)] hover:text-bronze transition-colors"
          >
            Anticipy
          </Link>
          <Link
            href="/pre-orders/purchase"
            className="text-[14px] text-[var(--text-on-light-muted)] hover:text-bronze transition-colors"
          >
            Pre-order
          </Link>
        </div>
      </header>

      <main className="px-6 py-14">
        <div className="max-w-3xl mx-auto">
          <h1 className="font-serif text-[clamp(30px,4.5vw,48px)] leading-[1.1] text-[var(--text-on-light)]">
            Book a quick call.
          </h1>
          <p className="mt-4 text-[16px] leading-relaxed text-[var(--text-on-light-muted)] max-w-xl">
            Questions about the pendant, your pre-order, or privacy? Pick a
            time below and we&apos;ll talk. If the calendar doesn&apos;t load,{" "}
            <a
              href={CAL_LINK}
              target="_blank"
              rel="noopener noreferrer"
              className="underline underline-offset-4 text-[var(--text-on-light)] hover:text-bronze transition-colors"
            >
              open the booking page directly
            </a>
            .
          </p>

          <div
            className="mt-10 rounded-2xl overflow-hidden"
            style={{ border: "1px solid var(--cream-border)", background: "#FFFFFF" }}
          >
            <iframe
              src={CAL_EMBED}
              style={{ border: 0 }}
              width="100%"
              height="720"
              title="Book an Anticipy call"
            />
          </div>
        </div>
      </main>
    </div>
  );
}
