import Link from "next/link";
import { PurchaseForm } from "./PurchaseForm";
import { Gallery } from "./Gallery";

const jsonLdProduct = {
  "@context": "https://schema.org",
  "@type": "Product",
  name: "Anticipy Pendant Pre-Order",
  description:
    "Pre-order the Anticipy AI wearable pendant. Brushed titanium, 8 grams. Wireless charging pad and chain included. $149.99 now, $199 at launch.",
  brand: { "@type": "Brand", name: "Anticipy" },
  image: [
    "https://www.anticipy.ai/images/colorways.png",
    "https://www.anticipy.ai/images/macro.png",
  ],
  offers: {
    "@type": "Offer",
    priceCurrency: "USD",
    price: "149.99",
    priceValidUntil: "2026-08-31",
    availability: "https://schema.org/PreOrder",
    url: "https://www.anticipy.ai/pre-orders/purchase",
    seller: {
      "@type": "Organization",
      name: "Anticipation Labs Inc.",
    },
    shippingDetails: {
      "@type": "OfferShippingDetails",
      shippingRate: { "@type": "MonetaryAmount", value: "0", currency: "USD" },
      shippingDestination: [
        { "@type": "DefinedRegion", addressCountry: "US" },
        { "@type": "DefinedRegion", addressCountry: "CA" },
      ],
    },
  },
};

export default function PreOrderPurchasePage({
  searchParams,
}: {
  searchParams: { canceled?: string };
}) {
  const canceled = searchParams?.canceled === "1";

  return (
    <div
      className="min-h-screen"
      style={{ background: "var(--cream)", color: "var(--text-on-light)" }}
    >
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLdProduct) }}
      />

      <header
        className="px-6 py-6 border-b sticky top-0 z-50"
        style={{
          borderColor: "var(--cream-border)",
          background: "rgba(245,240,235,0.85)",
          backdropFilter: "blur(20px)",
          WebkitBackdropFilter: "blur(20px)",
        }}
      >
        <div className="max-w-container mx-auto flex items-center justify-between">
          <Link
            href="/"
            className="font-serif text-[22px] hover:text-[var(--gold)] transition-colors"
            style={{ color: "var(--text-on-light)" }}
          >
            Anticipy
          </Link>
          <div className="flex items-center gap-4 text-[13px]">
            <Link
              href="/waitlist"
              className="hover:text-[var(--gold)] transition-colors"
              style={{ color: "var(--text-on-light-muted)" }}
            >
              Waitlist
            </Link>
            <Link
              href="/pre-orders/agreement"
              className="hover:text-[var(--gold)] transition-colors"
              style={{ color: "var(--text-on-light-muted)" }}
            >
              Pre-Order Terms
            </Link>
            <Link
              href="/"
              className="hover:text-[var(--gold)] transition-colors"
              style={{ color: "var(--text-on-light-muted)" }}
            >
              &larr; Back
            </Link>
          </div>
        </div>
      </header>

      <main className="px-6 py-12 md:py-16">
        <div className="max-w-container mx-auto grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-16">
          <div>
            <Gallery />
          </div>

          <div className="flex flex-col">
            <span
              className="inline-flex items-center self-start gap-2 px-3 py-1 rounded-pill text-[11px] uppercase tracking-[0.15em] font-medium mb-4"
              style={{
                background: "var(--gold-dim)",
                color: "var(--gold)",
              }}
            >
              Pre-order &middot; $50 off retail
            </span>

            <h1
              className="font-serif leading-[1.05] mb-4"
              style={{
                fontSize: "clamp(40px, 5.5vw, 64px)",
                color: "var(--text-on-light)",
              }}
            >
              Anticipy Pendant.
            </h1>

            <p
              className="text-[18px] font-light leading-[1.6] mb-8"
              style={{ color: "var(--text-on-light-muted)" }}
            >
              The ambient AI wearable that listens to your day and quietly
              handles what needs handling. Books, drafts, schedules, follows
              up. You wear it. You forget it is there. Things get done.
            </p>

            <div className="flex items-baseline gap-4 mb-3">
              <span
                className="font-serif"
                style={{
                  fontSize: "clamp(40px, 5vw, 56px)",
                  color: "var(--text-on-light)",
                }}
              >
                $149.99
              </span>
              <span
                className="text-[15px]"
                style={{ color: "var(--text-on-light-muted)" }}
              >
                $199 at launch
              </span>
            </div>

            <p
              className="text-[14px] font-light mb-8"
              style={{ color: "var(--text-on-light-muted)" }}
            >
              $149.99 now, $199 at launch. Free shipping to the US and Canada.
            </p>

            <div
              className="rounded-card p-6 mb-8"
              style={{ background: "var(--cream-muted)" }}
            >
              <h2 className="font-serif text-[18px] mb-3" style={{ color: "var(--text-on-light)" }}>
                What is included
              </h2>
              <ul className="space-y-2 text-[15px] font-light" style={{ color: "var(--text-on-light-muted)" }}>
                <li className="flex items-start gap-2">
                  <span style={{ color: "var(--gold)" }}>&bull;</span>
                  <span>Brushed titanium pendant. 8 grams. Silver finish.</span>
                </li>
                <li className="flex items-start gap-2">
                  <span style={{ color: "var(--gold)" }}>&bull;</span>
                  <span>Matching chain in your choice of length.</span>
                </li>
                <li className="flex items-start gap-2">
                  <span style={{ color: "var(--gold)" }}>&bull;</span>
                  <span>Wireless charging pad with 15-foot range.</span>
                </li>
                <li className="flex items-start gap-2">
                  <span style={{ color: "var(--gold)" }}>&bull;</span>
                  <span>Free shipping to the US and Canada.</span>
                </li>
              </ul>
            </div>

            <div className="grid grid-cols-3 gap-4 mb-8">
              <div className="text-center p-4 rounded-card" style={{ background: "var(--cream-muted)" }}>
                <div className="text-[11px] uppercase tracking-[0.12em] mb-1" style={{ color: "var(--text-on-light-muted)" }}>Ship date</div>
                <div className="font-serif text-[16px]" style={{ color: "var(--text-on-light)" }}>Q4 2026</div>
              </div>
              <div className="text-center p-4 rounded-card" style={{ background: "var(--cream-muted)" }}>
                <div className="text-[11px] uppercase tracking-[0.12em] mb-1" style={{ color: "var(--text-on-light-muted)" }}>Shipping</div>
                <div className="font-serif text-[16px]" style={{ color: "var(--text-on-light)" }}>Free</div>
              </div>
              <div className="text-center p-4 rounded-card" style={{ background: "var(--cream-muted)" }}>
                <div className="text-[11px] uppercase tracking-[0.12em] mb-1" style={{ color: "var(--text-on-light-muted)" }}>Weight</div>
                <div className="font-serif text-[16px]" style={{ color: "var(--text-on-light)" }}>8 g</div>
              </div>
            </div>

            <PurchaseForm canceled={canceled} />
          </div>
        </div>

        <section className="max-w-3xl mx-auto mt-24">
          <h2
            className="font-serif text-center mb-12"
            style={{
              fontSize: "clamp(32px, 4vw, 44px)",
              color: "var(--text-on-light)",
            }}
          >
            Common questions.
          </h2>
          <div className="space-y-8">
            <FAQ
              q="When will my pendant ship?"
              a="Our current estimate is Q4 2026. We are an early-stage hardware company, so dates can shift. If the date moves and you no longer want to wait, contact us and we will work with you. By US Federal Trade Commission Mail-Order Rule, if we cannot ship within thirty days of the originally promised date and you have not consented to a delay, you have the right to a full refund."
            />
            <FAQ
              q="Why is the pre-order price lower?"
              a="The retail price is $199. Pre-order customers help fund manufacturing tooling, supplier deposits, and the first production run. The $50 saving is our way of saying thank you for being early."
            />

            <FAQ
              q="What is your refund policy?"
              a={
                <>
                  Pre-order refunds are at Anticipation Labs Inc&apos;s sole
                  discretion except where required by applicable law including
                  the FTC Mail-Order Rule. We will always honour rights granted
                  to you by your local consumer protection statutes. For full
                  details see the{" "}
                  <Link
                    href="/pre-orders/agreement"
                    className="underline hover:text-[var(--gold)]"
                    style={{ color: "var(--text-on-light)" }}
                  >
                    Pre-Order Agreement
                  </Link>
                  .
                </>
              }
            />
            <FAQ
              q="Where do you ship?"
              a="Right now, the United States and Canada only. We will expand internationally as soon as customs and tax handling are in place. Pre-orders placed from outside the US and Canada will be canceled and refunded."
            />
            <FAQ
              q="Is my data private?"
              a={
                <>
                  Your audio is processed for the explicit purpose of running
                  the AI service, with on-device and ephemeral cloud
                  processing. We do not sell personal data, do not run
                  third-party ad networks, and do not train shared models on
                  your transcripts. Full details are in the{" "}
                  <Link
                    href="/privacy"
                    className="underline hover:text-[var(--gold)]"
                    style={{ color: "var(--text-on-light)" }}
                  >
                    Privacy Policy
                  </Link>
                  .
                </>
              }
            />
          </div>
        </section>

        <section className="max-w-3xl mx-auto mt-24 text-center">
          <p className="text-[15px] font-light mb-4" style={{ color: "var(--text-on-light-muted)" }}>
            Not ready to pre-order?
          </p>
          <Link
            href="/waitlist"
            className="inline-block px-8 py-3 rounded-pill text-[15px] font-medium transition-colors"
            style={{
              background: "var(--cream-muted)",
              color: "var(--text-on-light)",
              border: "1px solid var(--cream-border)",
            }}
          >
            Join the free waitlist instead
          </Link>
        </section>
      </main>

      <footer
        className="px-6 py-12 border-t mt-24"
        style={{ borderColor: "var(--cream-border)" }}
      >
        <div className="max-w-container mx-auto flex flex-col md:flex-row gap-4 items-center justify-between text-[13px]" style={{ color: "var(--text-on-light-muted)" }}>
          <div>&copy; 2026 Anticipation Labs Inc.</div>
          <div className="flex gap-6">
            <Link href="/privacy" className="hover:text-[var(--text-on-light)]">Privacy</Link>
            <Link href="/terms" className="hover:text-[var(--text-on-light)]">Terms</Link>
            <Link href="/refund" className="hover:text-[var(--text-on-light)]">Refund</Link>
            <Link href="/pre-orders/agreement" className="hover:text-[var(--text-on-light)]">Pre-Order Agreement</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}

function FAQ({ q, a }: { q: string; a: React.ReactNode }) {
  return (
    <div>
      <h3
        className="font-serif text-[20px] mb-2"
        style={{ color: "var(--text-on-light)" }}
      >
        {q}
      </h3>
      <p
        className="text-[15px] font-light leading-[1.7]"
        style={{ color: "var(--text-on-light-muted)" }}
      >
        {a}
      </p>
    </div>
  );
}
