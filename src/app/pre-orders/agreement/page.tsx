import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Pre-Order Agreement",
  description:
    "The binding agreement between you and Anticipation Labs Inc. when you pre-order the Anticipy pendant. Read before purchase.",
  alternates: {
    canonical: "https://www.anticipy.ai/pre-orders/agreement",
  },
  robots: { index: true, follow: true },
};

const AGREEMENT_VERSION = "v1-2026-05-27";
const EFFECTIVE_DATE = "May 27, 2026";

export default function PreOrderAgreementPage() {
  return (
    <div
      className="min-h-screen"
      style={{ background: "var(--dark)", color: "var(--text-on-dark)" }}
    >
      <header
        className="px-6 py-6 border-b"
        style={{ borderColor: "var(--dark-border)" }}
      >
        <div className="max-w-3xl mx-auto flex justify-between items-center">
          <Link
            href="/"
            className="font-serif text-[22px] hover:text-[var(--gold)] transition-colors"
            style={{ color: "var(--text-on-dark)" }}
          >
            Anticipy
          </Link>
          <Link
            href="/pre-orders/purchase"
            className="text-[13px] hover:text-[var(--gold)] transition-colors"
            style={{ color: "var(--text-on-dark-muted)" }}
          >
            &larr; Back to pre-order
          </Link>
        </div>
      </header>

      <main className="px-6 py-16">
        <div className="max-w-3xl mx-auto">
          <h1
            className="font-serif leading-[1.15] mb-3"
            style={{
              fontSize: "clamp(32px, 5vw, 48px)",
              color: "var(--text-on-dark)",
            }}
          >
            Pre-Order Agreement.
          </h1>
          <p
            className="text-[14px] font-light mb-12"
            style={{ color: "var(--text-on-dark-muted)" }}
          >
            Version {AGREEMENT_VERSION} &middot; Effective {EFFECTIVE_DATE}
          </p>

          <div
            className="space-y-10 text-[15px] font-light leading-[1.85]"
            style={{ color: "var(--text-on-dark-muted)" }}
          >
            <section>
              <p
                className="px-5 py-4 rounded-card"
                style={{
                  background: "var(--dark-elevated)",
                  border: "1px solid var(--dark-border)",
                  color: "var(--text-on-dark)",
                }}
              >
                <strong>Read this before you click pre-order.</strong> This
                Pre-Order Agreement is a binding contract between you and
                Anticipation Labs Inc. By clicking the pre-order button and
                completing checkout, you agree to every term below. If you do
                not agree, do not pre-order.
              </p>
            </section>

            <Section title="1. The parties.">
              <p>
                This Pre-Order Agreement (the &ldquo;Agreement&rdquo;) is
                between <Strong>Anticipation Labs Inc.</Strong>, a corporation
                organized in British Columbia, Canada, doing business as
                Anticipy and operating the website{" "}
                <a
                  href="https://www.anticipy.ai"
                  className="underline hover:text-[var(--gold)]"
                  style={{ color: "var(--text-on-dark)" }}
                >
                  anticipy.ai
                </a>{" "}
                (collectively, &ldquo;Company,&rdquo; &ldquo;we,&rdquo;
                &ldquo;us,&rdquo; or &ldquo;our&rdquo;), and the individual
                placing the pre-order (&ldquo;you&rdquo; or
                &ldquo;Customer&rdquo;). You confirm that you are at least
                eighteen years of age and have the legal capacity to enter
                this Agreement.
              </p>
            </Section>

            <Section title="2. What you are pre-ordering.">
              <p>
                The pre-order covers one (1) <Strong>Anticipy Pendant</Strong>{" "}
                in brushed titanium, a matching chain, one (1) wireless
                charging pad, and one (1) year of the Anticipy AI cloud
                service starting on the date your pendant ships to you (the
                &ldquo;Product&rdquo;). The price for this pre-order is{" "}
                <Strong>USD 149.99</Strong>, charged in full at the time you
                complete checkout, which is fifty United States dollars and
                one cent (USD 50.01) less than the projected retail price of
                USD 199.00. Free shipping is included to physical addresses
                in the United States and Canada. Shipping to any other
                country is not currently offered. If you select an address
                outside those countries, we will cancel the order and refund
                the full purchase price.
              </p>
            </Section>

            <Section title="3. Specifications are preliminary.">
              <p>
                The Product is in active development. The materials,
                appearance, dimensions, weight, battery life, microphone
                count, on-device storage, supported features, color options,
                packaging, included accessories, and AI capabilities described
                on our website, in our marketing, in this Agreement, or in any
                other communication are <Strong>preliminary, aspirational,
                and subject to change at our sole discretion</Strong> without
                prior notice. We may substitute components, redesign the
                enclosure, alter colors, change finishes, modify firmware
                features, or otherwise depart from what is shown today. The
                final Product you receive may differ from the renderings,
                photos, prototypes, or descriptions you saw at the time of
                pre-order. Nothing on our website or in any sales channel is
                a warranty, guarantee, or binding specification.
              </p>
            </Section>

            <Section title="4. Estimated ship date.">
              <p>
                Our current good-faith estimate is that the Product will ship
                in <Strong>August 2026</Strong>. This is an estimate, not a
                guarantee. Hardware schedules slip. Suppliers miss dates.
                Certifications take longer than expected. By placing a
                pre-order, you acknowledge that the date can move and that
                you accept that risk in exchange for the pre-order discount.
              </p>
              <p>
                Where the United States Federal Trade Commission&apos;s Mail,
                Internet, or Telephone Order Merchandise Rule (16 CFR Part
                435) applies, we will offer you the option to consent to a
                delay or to receive a full refund if we determine we cannot
                ship within thirty (30) days of the date stated at the time
                of order. Customers in Canada are protected by the Competition
                Act and provincial consumer protection statutes; Canadian
                customers retain whatever rights those statutes grant. Where
                local law is more favourable to you than the terms of this
                Agreement, local law controls.
              </p>
            </Section>

            <Section title="5. Refunds. Read carefully.">
              <p>
                <Strong>
                  Refunds on pre-orders are at the sole discretion of
                  Anticipation Labs Inc., except where applicable law
                  requires us to issue one.
                </Strong>{" "}
                We do not offer no-questions-asked refunds during the
                pre-order period. We may, in our sole discretion, grant a
                refund in cases such as confirmed inability to ship,
                substantial change in specifications materially adverse to
                you, hardship, or duplicate orders. We are equally entitled,
                in our sole discretion, to decline a refund request that does
                not fall within an applicable legal requirement. Examples
                where we may decline include but are not limited to: change
                of mind, change in financial circumstance, finding a
                competing product, dissatisfaction with the appearance or
                feature set in late-stage marketing, public commentary
                about the project, or any other reason not protected by
                consumer law in your jurisdiction.
              </p>
              <p>
                <Strong>Statutory rights are preserved.</Strong> Nothing in
                this section limits any right granted to you by your local
                consumer protection statute. If you are a consumer protected
                by the FTC Mail-Order Rule, the Competition Act of Canada,
                the consumer-protection statutes of any Canadian province,
                the EU Consumer Rights Directive, the UK Consumer Rights
                Act, or any other mandatory consumer-protection law, you
                retain those rights and we will honour them.
              </p>
              <p>
                <Strong>How to request a refund.</Strong> Email{" "}
                <a
                  href="mailto:support@anticipy.ai"
                  className="underline hover:text-[var(--gold)]"
                  style={{ color: "var(--text-on-dark)" }}
                >
                  support@anticipy.ai
                </a>{" "}
                with the email you used at checkout and the reason for the
                request. We will respond within seven (7) business days. If
                approved, refunds are issued to the original payment method
                through Stripe and may take up to ten (10) business days to
                appear on your statement.
              </p>
              <p>
                <Strong>No chargeback bypass.</Strong> You agree to contact
                us first and give us a reasonable opportunity to resolve any
                concern before initiating a chargeback or payment dispute. A
                chargeback initiated without first contacting us, or while a
                refund request is under review, will be contested.
              </p>
            </Section>

            <Section title="6. Cancellation by us.">
              <p>
                We may cancel your pre-order at any time, with or without
                cause, by issuing a full refund of the amount you paid. We
                may cancel in cases including but not limited to: project
                discontinuation, supplier failure, regulatory blocker,
                shipping address ineligibility, suspected fraud, suspected
                resale, or suspected violation of these terms or any other
                Anticipy policy. A refund issued upon cancellation by us is
                your sole remedy and is the full extent of our liability for
                the cancellation.
              </p>
            </Section>

            <Section title="7. Shipping and risk of loss.">
              <p>
                When manufacturing concludes, we will email the address on
                file to confirm or update the shipping address. You are
                responsible for keeping a current shipping address on file
                with us. Risk of loss passes to you upon delivery to the
                carrier. Carrier damage, theft after delivery, or refusal of
                delivery are not our responsibility, although we will assist
                in good faith with carrier claims where reasonable.
              </p>
              <p>
                If a shipment is returned to us because of an incorrect or
                outdated address that you provided, we may, at our option,
                hold the Product for thirty (30) days awaiting corrected
                instructions, attempt redelivery at your expense, or cancel
                and refund the order net of reasonable shipping costs we
                incurred.
              </p>
            </Section>

            <Section title="8. Service component and ongoing fees.">
              <p>
                The first year of the Anticipy AI cloud service is included
                in the pre-order price and begins on the date the Product
                ships to you. After the first year, continued use of the AI
                service is offered at our then-current annual fee, currently
                projected at USD 99 per year. The fee is subject to change.
                Hardware functions on a limited offline basis without the
                cloud service. We are not obligated to maintain any specific
                AI feature, model, integration, or third-party connection
                for any period of time.
              </p>
            </Section>

            <Section title="9. No warranties. Express disclaimer.">
              <p>
                THE PRE-ORDER IS PROVIDED ON AN <Strong>&ldquo;AS-IS&rdquo;
                AND &ldquo;AS-AVAILABLE&rdquo;</Strong> BASIS. TO THE FULLEST
                EXTENT PERMITTED BY LAW, WE DISCLAIM ALL WARRANTIES, EXPRESS
                OR IMPLIED, INCLUDING IMPLIED WARRANTIES OF MERCHANTABILITY,
                FITNESS FOR A PARTICULAR PURPOSE, NON-INFRINGEMENT, TITLE,
                AND ANY WARRANTY ARISING FROM COURSE OF DEALING OR USAGE OF
                TRADE. WE DO NOT WARRANT THAT THE PRODUCT WILL BE
                UNINTERRUPTED, ERROR-FREE, SECURE, OR FREE OF DEFECTS.
              </p>
              <p>
                Nothing in this section limits any warranty that cannot be
                disclaimed under your local mandatory consumer protection law.
              </p>
            </Section>

            <Section title="10. Limitation of liability.">
              <p>
                TO THE FULLEST EXTENT PERMITTED BY LAW, THE TOTAL CUMULATIVE
                LIABILITY OF ANTICIPATION LABS INC., ITS OFFICERS,
                DIRECTORS, EMPLOYEES, AGENTS, AFFILIATES, AND LICENSORS
                ARISING OUT OF OR RELATING TO THIS AGREEMENT OR THE PRE-ORDER
                SHALL NOT EXCEED THE AMOUNT YOU PAID FOR THE PRE-ORDER.
                IN NO EVENT SHALL WE BE LIABLE FOR ANY INDIRECT, INCIDENTAL,
                SPECIAL, CONSEQUENTIAL, OR EXEMPLARY DAMAGES, INCLUDING LOST
                PROFITS, LOST DATA, LOSS OF GOODWILL, BUSINESS INTERRUPTION,
                OR OTHER INTANGIBLE LOSSES, REGARDLESS OF THE LEGAL THEORY
                AND EVEN IF WE HAVE BEEN ADVISED OF THE POSSIBILITY OF SUCH
                DAMAGES. Some jurisdictions do not allow the exclusion of
                certain damages; if you are in one of those, our liability is
                limited to the maximum extent permitted by law.
              </p>
            </Section>

            <Section title="11. Privacy and payment data.">
              <p>
                Your name, email address, shipping address, billing address,
                phone number (if you provide one), and IP address are
                collected to fulfill this pre-order. Payment is processed by{" "}
                <Strong>Stripe, Inc.</Strong> Stripe collects and handles your
                full payment card details under its own privacy policy. We
                receive a non-card identifier, the last four digits of the
                card, the card brand, the country, and a payment intent
                identifier. We never see your full card number and never
                store it. Read our{" "}
                <Link
                  href="/privacy"
                  className="underline hover:text-[var(--gold)]"
                  style={{ color: "var(--text-on-dark)" }}
                >
                  Privacy Policy
                </Link>{" "}
                for full details.
              </p>
            </Section>

            <Section title="12. Transferability.">
              <p>
                Your pre-order is non-transferable. You may not resell,
                assign, or otherwise transfer your pre-order to a third party
                without our prior written consent. Any attempted transfer
                without consent is void. We may transfer or assign this
                Agreement, including in connection with a merger, acquisition,
                or sale of substantially all of our assets.
              </p>
            </Section>

            <Section title="13. Governing law and venue.">
              <p>
                This Agreement is governed by the laws of the Province of
                British Columbia, Canada, without regard to its conflict-of-
                laws principles. The federal laws of Canada applicable in
                British Columbia also apply. The exclusive venue for any
                dispute that is not subject to mandatory consumer-forum law
                is the courts located in Vancouver, British Columbia. If you
                are a consumer entitled to bring a claim in your local
                forum under your jurisdiction&apos;s mandatory consumer
                protection law, you retain that right.
              </p>
            </Section>

            <Section title="14. Force majeure.">
              <p>
                We are not liable for any delay, suspension, or failure to
                perform caused by events outside our reasonable control,
                including but not limited to: acts of God, fire, flood,
                pandemic, epidemic, government action, war, terrorism, civil
                unrest, labor disputes, supply chain failure, semiconductor
                shortage, port congestion, customs delay, or carrier failure.
                A force majeure event extends the time for performance for
                the duration of the event.
              </p>
            </Section>

            <Section title="15. Entire agreement and amendments.">
              <p>
                This Agreement together with our{" "}
                <Link
                  href="/terms"
                  className="underline hover:text-[var(--gold)]"
                  style={{ color: "var(--text-on-dark)" }}
                >
                  Terms of Service
                </Link>
                {" "}and{" "}
                <Link
                  href="/privacy"
                  className="underline hover:text-[var(--gold)]"
                  style={{ color: "var(--text-on-dark)" }}
                >
                  Privacy Policy
                </Link>{" "}
                constitutes the entire agreement between you and Anticipation
                Labs Inc. regarding your pre-order. It supersedes prior
                discussions, communications, and proposals. We may amend this
                Agreement going forward; the version in effect at the time of
                your pre-order applies to your pre-order. Amendments do not
                retroactively apply to completed pre-orders unless you
                expressly accept the amended terms.
              </p>
            </Section>

            <Section title="16. Severability.">
              <p>
                If any provision of this Agreement is held to be unenforceable
                under the law of your jurisdiction, that provision will be
                modified to the minimum extent necessary to make it
                enforceable, or, if modification is not possible, severed;
                the remainder of the Agreement remains in full force.
              </p>
            </Section>

            <Section title="17. Contact.">
              <p>
                Anticipation Labs Inc.
                <br />
                West Vancouver, British Columbia, Canada
                <br />
                <a
                  href="mailto:support@anticipy.ai"
                  className="underline hover:text-[var(--gold)]"
                  style={{ color: "var(--text-on-dark)" }}
                >
                  support@anticipy.ai
                </a>
              </p>
            </Section>

            <section className="pt-6 border-t" style={{ borderColor: "var(--dark-border)" }}>
              <p
                className="text-[13px]"
                style={{ color: "var(--text-on-dark-muted)" }}
              >
                Acknowledged version: {AGREEMENT_VERSION}. The version stored
                against your pre-order record at the moment of checkout is the
                version that governs your transaction.
              </p>
            </section>
          </div>
        </div>
      </main>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2
        className="font-serif text-[22px] mb-4"
        style={{ color: "var(--text-on-dark)" }}
      >
        {title}
      </h2>
      <div className="space-y-4">{children}</div>
    </section>
  );
}

function Strong({ children }: { children: React.ReactNode }) {
  return (
    <strong style={{ color: "var(--text-on-dark)", fontWeight: 500 }}>
      {children}
    </strong>
  );
}
