import Link from "next/link";
import type { Metadata } from "next";
import { stripe } from "@/lib/stripe";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Pre-order confirmed",
  description: "Your Anticipy pre-order is confirmed. Thank you for being early.",
  robots: { index: false, follow: false },
};

type Session = {
  email: string | null;
  amount: number;
  currency: string;
  name: string | null;
  city: string | null;
  state: string | null;
};

async function loadSession(sessionId: string | undefined): Promise<Session | null> {
  if (!sessionId || !sessionId.startsWith("cs_")) return null;
  try {
    const session = await stripe.checkout.sessions.retrieve(sessionId, {
      expand: ["customer_details"],
    });
    return {
      email: session.customer_details?.email ?? session.customer_email ?? null,
      amount: session.amount_total ?? 0,
      currency: session.currency ?? "usd",
      name:
        session.customer_details?.name ??
        session.collected_information?.shipping_details?.name ??
        null,
      city: session.collected_information?.shipping_details?.address?.city ?? null,
      state:
        session.collected_information?.shipping_details?.address?.state ?? null,
    };
  } catch {
    return null;
  }
}

export default async function PreOrderSuccessPage({
  searchParams,
}: {
  searchParams: { session_id?: string };
}) {
  const session = await loadSession(searchParams?.session_id);
  const amountDisplay = session ? (session.amount / 100).toFixed(2) : "149.99";
  const currencyDisplay = (session?.currency || "usd").toUpperCase();
  const firstName = session?.name?.split(" ")[0];

  return (
    <div
      className="min-h-screen flex flex-col"
      style={{ background: "var(--cream)", color: "var(--text-on-light)" }}
    >
      <header
        className="px-6 py-6 border-b"
        style={{ borderColor: "var(--cream-border)" }}
      >
        <div className="max-w-container mx-auto">
          <Link
            href="/"
            className="font-serif text-[22px] hover:text-[var(--gold)] transition-colors"
            style={{ color: "var(--text-on-light)" }}
          >
            Anticipy
          </Link>
        </div>
      </header>

      <main className="flex-1 flex items-center justify-center px-6 py-16">
        <div className="max-w-2xl text-center">
          <div
            className="w-20 h-20 rounded-full mx-auto mb-8 flex items-center justify-center"
            style={{ background: "var(--gold-dim)" }}
          >
            <svg
              className="w-10 h-10"
              fill="none"
              stroke="var(--gold)"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M5 13l4 4L19 7"
              />
            </svg>
          </div>

          <h1
            className="font-serif leading-[1.1] mb-6"
            style={{
              fontSize: "clamp(40px, 5.5vw, 64px)",
              color: "var(--text-on-light)",
            }}
          >
            {firstName ? `Thank you, ${firstName}.` : "Thank you."}
          </h1>

          <p
            className="text-[18px] font-light leading-[1.7] mb-10"
            style={{ color: "var(--text-on-light-muted)" }}
          >
            Your Anticipy pendant pre-order is confirmed at{" "}
            <strong style={{ color: "var(--text-on-light)" }}>
              ${amountDisplay} {currencyDisplay}
            </strong>
            . You locked in $50 off the $199 retail price.
          </p>

          <div
            className="rounded-card p-6 mb-10 text-left"
            style={{ background: "var(--cream-muted)" }}
          >
            <p className="text-[14px] font-light leading-[1.7]" style={{ color: "var(--text-on-light-muted)" }}>
              <strong style={{ color: "var(--text-on-light)" }}>What is next.</strong>
              {" "}
              We are targeting shipping for Q4 2026. As the date approaches we will email{" "}
              <strong style={{ color: "var(--text-on-light)" }}>
                {session?.email ?? "your inbox"}
              </strong>
              {" "}
              to confirm the shipping address and answer any questions. Stripe also emailed a receipt for your records.
            </p>
          </div>

          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              href="/"
              className="px-8 py-3.5 rounded-pill text-[15px] font-medium transition-colors"
              style={{
                background: "var(--dark)",
                color: "var(--cream)",
              }}
            >
              Back to anticipy.ai
            </Link>
            <Link
              href="/pre-orders/agreement"
              className="px-8 py-3.5 rounded-pill text-[15px] font-medium transition-colors"
              style={{
                background: "var(--cream-muted)",
                color: "var(--text-on-light)",
                border: "1px solid var(--cream-border)",
              }}
            >
              Read the Pre-Order Agreement
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}
