import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Refund Policy. Anticipy",
  description:
    "Refund and cancellation policy for Anticipy pre-orders and subscriptions. Clear terms, no surprises.",
  openGraph: {
    title: "Refund Policy. Anticipy",
    description:
      "Refund and cancellation policy for Anticipy pre-orders and subscriptions.",
    url: "https://www.anticipy.ai/refund",
    siteName: "Anticipy",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Refund Policy. Anticipy",
    description:
      "Refund and cancellation policy for Anticipy pre-orders and subscriptions.",
  },
};

export default function RefundPolicy() {
  return (
    <div style={{ background: "var(--dark)" }} className="min-h-screen">
      {/* Header */}
      <header
        className="px-6 py-6 border-b"
        style={{ borderColor: "var(--dark-border)" }}
      >
        <div className="flex items-center justify-between">
          <Link
            href="/"
            className="font-serif text-[22px] text-[var(--text-on-dark)] hover:text-gold transition-colors"
          >
            Anticipy
          </Link>
          <Link
            href="/"
            className="text-[13px] text-[var(--text-on-dark-muted)] hover:text-gold transition-colors"
          >
            &larr; Back to Home
          </Link>
        </div>
      </header>

      {/* Content */}
      <main className="px-6 py-16">
        <div className="max-w-3xl mx-auto">
          <h1 className="font-serif text-[clamp(32px,5vw,48px)] text-[var(--text-on-dark)] leading-[1.15] mb-4">
            Refund Policy
          </h1>
          <p className="text-[15px] text-[var(--text-on-dark-muted)] font-light mb-12">
            Effective Date: March 30, 2026
          </p>

          <div className="space-y-10 text-[15px] text-[var(--text-on-dark-muted)] font-light leading-[1.8]">
            {/* 1. Our Commitment */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                1. Our Commitment
              </h2>
              <p>
                At Anticipy, built by Anticipation Labs Inc., we believe you should love every product and service we offer. If for any reason you&apos;re not completely satisfied with your purchase, we&apos;re committed to making it right, whether that means a replacement, a credit, or a full refund.
              </p>
              <p className="mt-4">
                This Refund Policy outlines your rights and the process for returns, cancellations, and refunds. Where local consumer protection laws provide greater rights than those described here, those laws take precedence. We will always honour the option most favourable to you.
              </p>
            </section>

            {/* 2. Pre-Order / Waitlist Cancellations */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                2. Pre-Order &amp; Waitlist Cancellations
              </h2>
              <p>
                Pre-order refunds are governed by the{" "}
                <Link href="/pre-orders/agreement" className="text-gold hover:underline">
                  Pre-Order Agreement
                </Link>
                . <strong className="text-[var(--text-on-dark)]">You may cancel your pre-order
                and receive a full refund at any time before your unit ships, no reason
                required.</strong> Email us from the address you ordered with and we will
                refund the full amount to your original payment method.
              </p>
              <p className="mt-4">
                <strong className="text-[var(--text-on-dark)]">If you are in British Columbia,
                you have rights that are not discretionary.</strong> Anticipation Labs Inc. is a
                BC company and a pre-order placed online is a distance sales contract under the
                Business Practices and Consumer Protection Act, SBC 2004 c 2. If we have not
                shipped within <strong className="text-[var(--text-on-dark)]">30 days</strong> of
                the estimated ship date shown at checkout, you may cancel and receive a full
                refund — no reason required and no agreement from us needed. We will refund you
                within <strong className="text-[var(--text-on-dark)]">15 days</strong>, in your
                original payment method, with no deductions, including all fees and taxes.
              </p>
              <p className="mt-4">
                Where the U.S. Federal Trade Commission&apos;s Mail, Internet, or Telephone Order
                Merchandise Rule (FTC Rule 16 CFR Part 435) applies, sellers must offer
                cancellation and a full refund if they are unable to ship within the timeframe
                stated at the time of order. The Competition Act of Canada and provincial
                consumer protection statutes, the EU Consumer Rights Directive, the UK
                Consumer Rights Act, and other mandatory consumer-protection laws may grant
                similar or stronger statutory rights. Those rights are preserved in full.
              </p>
              <p className="mt-4">
                Joining the free waitlist is not a purchase and does not require a deposit.
                Removing yourself from the waitlist creates no obligation on either side and
                no refund is needed.
              </p>
              <p className="mt-4">
                To request consideration of a pre-order refund, email{" "}
                <a
                  href="mailto:hello@anticipy.ai"
                  className="text-gold hover:underline"
                >
                  hello@anticipy.ai
                </a>{" "}
                with the email used at checkout and the reason for the request. We respond
                within seven business days. If approved, refunds are issued through Stripe
                to the original payment method and can take up to ten business days to clear.
              </p>
            </section>

            {/* 3. Hardware Returns . Final sale after delivery */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                3. Hardware Returns &mdash; All Sales Final After Delivery
              </h2>
              <p>
                <strong className="text-[var(--text-on-dark)]">Once your pendant has been
                delivered, the sale is final.</strong> We do not accept change-of-mind returns,
                and we do not offer a trial period. Anticipy is made in small runs by a small
                team, each unit is built and tested individually, and a returned unit cannot be
                resold as new.
              </p>
              <p className="mt-4">
                You have a full and unconditional right to change your mind{" "}
                <strong className="text-[var(--text-on-dark)]">before your unit ships</strong> —
                one email and we refund you in full, no reason required. That window closes when
                the unit is handed to the carrier. Please use it if you are unsure.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                What is still covered, always
              </h3>
              <p>
                &ldquo;Final sale&rdquo; means we will not take a working pendant back because
                you changed your mind. It does not, and legally cannot, take away any of the
                following:
              </p>
              <ul className="list-disc pl-6 space-y-2 mt-4">
                <li>
                  <strong className="text-[var(--text-on-dark)]">A pendant that is faulty.</strong>{" "}
                  Covered by the 1-year limited warranty in section 4 below, at your choice of
                  replacement or refund.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">A pendant that is not what we
                  described,</strong> is not of merchantable quality, or is not fit for the
                  purpose we sold it for. In British Columbia these are implied conditions under
                  the Sale of Goods Act, RSBC 1996 c 410, and section 20(3) makes any attempt to
                  waive them in a consumer sale void. We are not attempting to.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Anything that arrives damaged
                  or never arrives at all.</strong> Tell us and we will make it right.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Every right your own consumer
                  protection law gives you,</strong> including the British Columbia Business
                  Practices and Consumer Protection Act and the statutes listed in section 6. A
                  waiver of rights under that Act is void by operation of section 187 of the Act.
                  Where your local law gives you more than this policy does, your local law wins.
                </li>
              </ul>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                Making a claim
              </h3>
              <p>
                Email{" "}
                <a
                  href="mailto:hello@anticipy.ai"
                  className="text-gold hover:underline"
                >
                  hello@anticipy.ai
                </a>{" "}
                with your order number and what went wrong. We respond within 2 business days,
                we pay return shipping on anything faulty, and we do not require the original
                packaging for a warranty claim.
              </p>
            </section>

            {/* 4. Defective Products */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                4. Defective Products
              </h2>
              <p>
                If your Anticipy device is defective or malfunctions, we will <strong className="text-[var(--text-on-dark)]">replace it or provide a full refund at any time during the 1-year limited warranty period</strong>, at your choice. Defects are covered for the full warranty period. The final-sale rule in section 3 applies only to change-of-mind returns and never to a faulty unit.
              </p>
              <p className="mt-4">
                To report a defect, contact us at{" "}
                <a
                  href="mailto:hello@anticipy.ai"
                  className="text-gold hover:underline"
                >
                  hello@anticipy.ai
                </a>{" "}
                with:
              </p>
              <ul className="list-disc pl-6 space-y-2 mt-2">
                <li>Your order number</li>
                <li>A description of the issue</li>
                <li>Photos or a short video showing the defect</li>
              </ul>
              <p className="mt-4">
                Our team will review your claim within 2 business days and arrange a replacement shipment or full refund. We cover all shipping costs for defective product returns.
              </p>
            </section>

            {/* 5. Service Subscription Refunds */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                5. Service Subscription Refunds
              </h2>
              <p>
                Anticipy&apos;s AI service subscription works as follows:
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                First Year Included
              </h3>
              <p>
                Your first year of Anticipy&apos;s AI service is <strong className="text-[var(--text-on-dark)]">included with your hardware purchase</strong> at no additional cost. If your order is cancelled before shipping, or if we refund a faulty unit under the warranty, the included service subscription is cancelled with it.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                Annual Renewals
              </h3>
              <ul className="list-disc pl-6 space-y-2">
                <li>
                  <strong className="text-[var(--text-on-dark)]">Within 14 days of renewal:</strong> You may request a full refund of the renewal charge. No questions asked.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">After 14 days:</strong> Renewal charges are non-refundable. However, your service will remain fully active until the end of the current billing period.
                </li>
              </ul>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                Cancellation
              </h3>
              <p>
                You may cancel your subscription at any time. Upon cancellation, your service will <strong className="text-[var(--text-on-dark)]">remain active until the end of your current billing period</strong>. We do not prorate partial months or years, but you will never lose access before your paid period expires.
              </p>
            </section>

            {/* 6. Jurisdiction-Specific Return Rights */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                6. Jurisdiction-Specific Return Rights
              </h2>
              <p>
                Consumer protection laws vary by country and region. Where your local laws provide greater return or refund rights than our standard policy, <strong className="text-[var(--text-on-dark)]">those laws override our policy and we will honour the more favourable terms</strong>. Below is a summary of key jurisdictions:
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                European Union
              </h3>
              <p>
                Under the <strong className="text-[var(--text-on-dark)]">Consumer Rights Directive 2011/83/EU</strong>, you have a 14-day right of withdrawal from the date of delivery. No reason is required. You are entitled to a full refund, including standard delivery charges, within 14 days of us receiving the returned goods or proof of return shipment. This right applies to all EU member states.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                United Kingdom
              </h3>
              <p>
                Under the <strong className="text-[var(--text-on-dark)]">Consumer Contracts (Information, Cancellation and Additional Charges) Regulations 2013</strong>, you have a 14-day cancellation period from the date of delivery. Additionally, the <strong className="text-[var(--text-on-dark)]">Consumer Rights Act 2015</strong> provides a 30-day short-term right to reject goods if they do not match the description, are not of satisfactory quality, or are not fit for purpose.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                Saudi Arabia
              </h3>
              <p>
                Under the <strong className="text-[var(--text-on-dark)]">E-Commerce Law (2019)</strong>, consumers have the right to return products within 7 days from the date of the contract, provided the product is unused and in its original condition.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                China
              </h3>
              <p>
                Under the <strong className="text-[var(--text-on-dark)]">Consumer Rights Protection Law</strong>, consumers purchasing goods online have a 7-day no-reason return right from the date of receipt, provided the goods are in their original condition.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                South Korea
              </h3>
              <p>
                Under the <strong className="text-[var(--text-on-dark)]">Act on Consumer Protection in Electronic Commerce</strong>, consumers have a 7-day withdrawal right from the date of receipt of goods or the date the supply of goods becomes available.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                Japan
              </h3>
              <p>
                Under Japanese consumer protection law, consumers have an 8-day return right if no specific return policy was clearly stated at the time of purchase. Our return policy is stated clearly in section 3 above. We currently ship only to the United States and Canada.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                Canada
              </h3>
              <p>
                If you are located in Canada, you may benefit from protections under applicable provincial consumer protection legislation, including the <strong className="text-[var(--text-on-dark)]">Business Practices and Consumer Protection Act (BPCPA)</strong> in British Columbia and similar statutes in other provinces. You also benefit from the implied conditions in provincial sale-of-goods legislation. None of those rights are waivable, and the final-sale rule in section 3 does not attempt to waive them — it applies only to change-of-mind returns of a working pendant.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                United States
              </h3>
              <p>
                Under the <strong className="text-[var(--text-on-dark)]">FTC Rule 16 CFR Part 435</strong> (the Mail, Internet, or Telephone Order Merchandise Rule), sellers must ship goods within the timeframe stated at the time of order, or offer the consumer a cancellation and full refund. All pre-orders and waitlist deposits are fully refundable at any time before shipment, in compliance with this rule. Individual state laws may provide additional protections.
              </p>
            </section>

            {/* 7. Exceptions */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                7. Exceptions
              </h2>
              <p>
                We reserve the right to decline a return or refund in the following circumstances:
              </p>
              <ul className="list-disc pl-6 space-y-2 mt-4">
                <li>
                  <strong className="text-[var(--text-on-dark)]">Intentional damage:</strong> Products that have been deliberately damaged, destroyed, or rendered non-functional through misuse.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Unauthorized modification:</strong> Devices that have been disassembled, tampered with, or modified beyond normal use, including hardware or firmware alterations not authorized by Anticipy.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Unauthorized resellers:</strong> Products purchased from unauthorized third-party resellers or secondary markets are not eligible for returns or warranty coverage through Anticipy.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Fraudulent claims:</strong> Return requests that are found to be fraudulent, including serial return abuse, empty-box claims, or misrepresentation of product condition.
                </li>
              </ul>
              <p className="mt-4">
                These exceptions do not limit any mandatory rights you may have under applicable consumer protection laws in your jurisdiction.
              </p>
            </section>

            {/* 8. Refund Processing */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                8. Refund Processing
              </h2>
              <ul className="list-disc pl-6 space-y-2">
                <li>
                  <strong className="text-[var(--text-on-dark)]">Payment method:</strong> All refunds are issued to the original payment method used at the time of purchase.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Processing time:</strong> Refunds are processed within 5 business days of receiving the returned product or approving the refund request. Please allow an additional 5&ndash;10 business days for the refund to appear on your statement, depending on your bank or payment provider.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Currency:</strong> Refunds are issued in the original currency of the transaction. Any exchange rate differences between the time of purchase and refund are determined by your bank and are outside our control.
                </li>
              </ul>
            </section>

            {/* 9. Changes to This Policy */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                9. Changes to This Policy
              </h2>
              <p>
                We may update this Refund Policy from time to time to reflect changes in our practices, legal requirements, or product offerings. Any changes will be posted on this page with an updated effective date. Changes to this policy <strong className="text-[var(--text-on-dark)]">will not apply retroactively</strong>, the policy in effect at the time of your purchase will govern your return and refund rights for that transaction.
              </p>
            </section>

            {/* 10. Contact */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                10. Contact Us
              </h2>
              <p>
                If you have any questions about this Refund Policy, need to initiate a return, or require assistance with a refund, please don&apos;t hesitate to reach out:
              </p>
              <ul className="list-disc pl-6 space-y-2 mt-4">
                <li>
                  <strong className="text-[var(--text-on-dark)]">Customer Support:</strong>{" "}
                  <a
                    href="mailto:hello@anticipy.ai"
                    className="text-gold hover:underline"
                  >
                    hello@anticipy.ai
                  </a>
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Founder:</strong>{" "}
                  <a
                    href="mailto:hello@anticipy.ai"
                    className="text-gold hover:underline"
                  >
                    hello@anticipy.ai
                  </a>
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Company:</strong> Anticipation Labs Inc.
                </li>
              </ul>
              <p className="mt-4">
                We aim to respond to all inquiries within <strong className="text-[var(--text-on-dark)]">1 business day</strong>.
              </p>
            </section>
          </div>

          {/* Footer Links */}
          <div
            className="mt-16 pt-8 border-t flex flex-wrap gap-6"
            style={{ borderColor: "var(--dark-border)" }}
          >
            <Link
              href="/privacy"
              className="text-[13px] text-[var(--text-on-dark-muted)] hover:text-gold transition-colors"
            >
              Privacy Policy
            </Link>
            <Link
              href="/terms"
              className="text-[13px] text-[var(--text-on-dark-muted)] hover:text-gold transition-colors"
            >
              Terms of Service
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}
