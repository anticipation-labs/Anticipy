import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Refund Policy — Anticipy",
  description:
    "Refund and cancellation policy for Anticipy pre-orders and subscriptions. Clear terms, no surprises.",
  openGraph: {
    title: "Refund Policy — Anticipy",
    description:
      "Refund and cancellation policy for Anticipy pre-orders and subscriptions.",
    url: "https://www.anticipy.ai/refund",
    siteName: "Anticipy",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Refund Policy — Anticipy",
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
                At Anticipy, built by Anticipation Labs Inc., we believe you should love every product and service we offer. If for any reason you&apos;re not completely satisfied with your purchase, we&apos;re committed to making it right&mdash;whether that means a replacement, a credit, or a full refund.
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
                If you have placed a pre-order or joined our waitlist with a deposit, you may cancel and receive a <strong className="text-[var(--text-on-dark)]">full refund at any time before the product ships</strong>. No questions asked. No fees. No hoops.
              </p>
              <p className="mt-4">
                This right is guaranteed under the U.S. Federal Trade Commission&apos;s Mail, Internet, or Telephone Order Merchandise Rule (FTC Rule 16 CFR Part 435), which requires sellers to offer cancellation and a full refund if they are unable to ship within the timeframe stated at the time of order. Equivalent consumer protection statutes in the European Union, United Kingdom, Canada, and other jurisdictions provide similar or stronger protections.
              </p>
              <p className="mt-4">
                To cancel a pre-order or waitlist deposit, simply email{" "}
                <a
                  href="mailto:support@anticipy.ai"
                  className="text-gold hover:underline"
                >
                  support@anticipy.ai
                </a>{" "}
                with your order confirmation or email address. Your refund will be processed within 5 business days.
              </p>
            </section>

            {/* 3. Hardware Returns — 30-Day Satisfaction Guarantee */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                3. Hardware Returns &mdash; 30-Day Satisfaction Guarantee
              </h2>
              <p>
                We offer a <strong className="text-[var(--text-on-dark)]">30-day satisfaction guarantee</strong> on all Anticipy hardware. If you&apos;re not completely happy with your device, you may return it within 30 calendar days of the delivery date for a full refund of the purchase price.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                Requirements
              </h3>
              <ul className="list-disc pl-6 space-y-2">
                <li>
                  <strong className="text-[var(--text-on-dark)]">Original packaging:</strong> The device must be returned in its original packaging, including all boxes, inserts, and protective materials.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">All included items:</strong> All accessories, cables, documentation, and any bundled items must be included in the return.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Working condition:</strong> The device must be in working condition and free from physical damage beyond normal handling during the trial period.
                </li>
              </ul>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                Return Process
              </h3>
              <ol className="list-decimal pl-6 space-y-2">
                <li>
                  <strong className="text-[var(--text-on-dark)]">Initiate your return</strong> by emailing{" "}
                  <a
                    href="mailto:support@anticipy.ai"
                    className="text-gold hover:underline"
                  >
                    support@anticipy.ai
                  </a>{" "}
                  with your order number and reason for return. No justification is required&mdash;we simply appreciate the feedback.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Receive your prepaid return label.</strong> We will email you a prepaid shipping label within 2 business days of your request. <strong className="text-[var(--text-on-dark)]">We cover all return shipping costs.</strong>
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Ship the device back</strong> using the provided label. We recommend keeping the tracking number for your records.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Refund processed.</strong> Once we receive and inspect the returned device, your full refund will be processed within 5 business days.
                </li>
              </ol>
            </section>

            {/* 4. Defective Products */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                4. Defective Products
              </h2>
              <p>
                If your Anticipy device is defective or malfunctions, we will <strong className="text-[var(--text-on-dark)]">replace it or provide a full refund at any time during the 1-year limited warranty period</strong>, at your choice. Defective products are covered regardless of whether the 30-day return window has passed.
              </p>
              <p className="mt-4">
                To report a defect, contact us at{" "}
                <a
                  href="mailto:support@anticipy.ai"
                  className="text-gold hover:underline"
                >
                  support@anticipy.ai
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
                Your first year of Anticipy&apos;s AI service is <strong className="text-[var(--text-on-dark)]">included with your hardware purchase</strong> at no additional cost. If you return the hardware within the 30-day satisfaction guarantee period, the included service subscription is automatically cancelled.
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
                Under Japanese consumer protection law, consumers have an 8-day return right if no specific return policy was clearly stated at the time of purchase. As we do state our return policy, our 30-day satisfaction guarantee applies&mdash;which exceeds this statutory minimum.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                Canada
              </h3>
              <p>
                If you are located in Canada, you may benefit from protections under applicable provincial consumer protection legislation, including the <strong className="text-[var(--text-on-dark)]">Business Practices and Consumer Protection Act (BPCPA)</strong> in British Columbia and similar statutes in other provinces. Our 30-day satisfaction guarantee meets or exceeds these requirements.
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
                We may update this Refund Policy from time to time to reflect changes in our practices, legal requirements, or product offerings. Any changes will be posted on this page with an updated effective date. Changes to this policy <strong className="text-[var(--text-on-dark)]">will not apply retroactively</strong>&mdash;the policy in effect at the time of your purchase will govern your return and refund rights for that transaction.
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
                    href="mailto:support@anticipy.ai"
                    className="text-gold hover:underline"
                  >
                    support@anticipy.ai
                  </a>
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Founder:</strong>{" "}
                  <a
                    href="mailto:omar@anticipy.ai"
                    className="text-gold hover:underline"
                  >
                    omar@anticipy.ai
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
