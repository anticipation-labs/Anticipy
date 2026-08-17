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

const AGREEMENT_VERSION = "v2-2026-05-28";
const EFFECTIVE_DATE = "May 28, 2026";

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
                Anticipation Labs Inc. It contains a <strong>binding
                arbitration clause and a class action waiver</strong> in
                Section 14 that affect your legal rights, and a{" "}
                <strong>limitation of liability</strong> in Section 11.
                By clicking the pre-order button and completing checkout, you
                agree to every term below. If you do not agree, do not
                pre-order.
              </p>
            </section>

            <Section title="1. The parties and your representations.">
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
                &ldquo;Customer&rdquo;).
              </p>
              <p>
                By placing this pre-order you represent and warrant that:
                (a) you are at least <Strong>eighteen (18) years of age</Strong>;
                (b) you have the full legal capacity to enter a binding
                contract in your jurisdiction; (c) the billing and shipping
                information you provide is accurate and is information you are
                authorized to use; (d) you are not on any United States
                Treasury OFAC, United States Department of State, Canadian
                consolidated sanctions list, EU sanctions list, or UK Treasury
                sanctions list, and you are not located in a jurisdiction
                under comprehensive United States or Canadian trade sanctions.
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
              <p>
                Statements such as &ldquo;vibes your life,&rdquo;
                &ldquo;anticipates what you need,&rdquo; and other forward
                looking or aspirational marketing language are{" "}
                <Strong>non-actionable puffery</Strong> and are not
                representations of measurable performance. AI outputs may be
                incorrect, incomplete, or unpredictable. Do not rely on AI
                output for any medical, financial, legal, safety-critical, or
                emergency decision.
              </p>
            </Section>

            <Section title="4. Estimated ship date.">
              <p>
                Our current good-faith estimate is that the Product will ship
                in <Strong>Q4 2026</Strong>. This is an estimate, not a
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

            <Section title="4A. British Columbia distance sales rights.">
              <p>
                Anticipation Labs Inc. is a British Columbia company and this
                pre-order is a <Strong>distance sales contract</Strong> under
                the British Columbia Business Practices and Consumer
                Protection Act, SBC 2004 c 2. That Act gives you the following
                rights, which apply regardless of anything else in this
                Agreement:
              </p>
              <p>
                <Strong>Supply date.</Strong> The supply date for this
                contract is the estimated ship date stated in section 4.
              </p>
              <p>
                <Strong>Cancellation for late delivery.</Strong> If we have
                not supplied the Product within <Strong>thirty (30) days</Strong>{" "}
                after that supply date, you may cancel this contract and
                receive a full refund. You do not need our agreement and you
                do not need to give a reason.
              </p>
              <p>
                <Strong>Refund timing.</Strong> If you cancel under the Act,
                we will refund you within <Strong>fifteen (15) days</Strong>{" "}
                of the cancellation, in the original form of payment, with no
                deductions — including all fees, charges and taxes you paid.
              </p>
              <p>
                <Strong>Your copy of this contract.</Strong> We will send you
                a copy of this Agreement and your order details by email
                within fifteen (15) days of your order. If we do not, the Act
                gives you a further right to cancel.
              </p>
              <p>
                To cancel, email{" "}
                <a
                  href="mailto:hello@anticipy.ai"
                  className="text-gold hover:underline"
                >
                  hello@anticipy.ai
                </a>{" "}
                from the address you ordered with and say you are cancelling.
                Nothing in section 5 below limits any of these rights.
              </p>
            </Section>

            <Section title="5. Refunds. Read carefully.">
              <p>
                <Strong>
                  You may cancel your pre-order and receive a full refund at
                  any time before your unit ships. No reason required.
                </Strong>{" "}
                Email us from the address you ordered with and we will refund
                the full amount you paid to your original payment method. This
                is the same promise made on our home page, and it is stated
                here so the two cannot disagree: if anything elsewhere in this
                Agreement appears to narrow it, this paragraph governs.
              </p>
              <p>
                Once your unit has shipped, this pre-order cancellation right
                ends and the return and warranty terms in the Terms of Service
                apply instead, along with any rights your local consumer
                protection law gives you.
              </p>
              <p>
                <Strong>
                  Your right to share an honest review is not affected by
                  this Agreement.
                </Strong>{" "}
                Nothing in this Agreement, and no refund decision by us, is
                conditioned on whether you publish reviews, social media
                posts, or other public statements about Anticipy. This
                provision is included to comply with the United States
                Consumer Review Fairness Act (15 U.S.C. &sect; 45b) and
                similar Canadian provincial consumer-protection statutes.
              </p>
              <p>
                <Strong>Statutory rights are preserved.</Strong> Nothing in
                this section limits any right granted to you by your local
                consumer protection statute, including without limitation:
                the U.S. FTC Mail-Order Rule (16 CFR Part 435); the
                Competition Act of Canada; the Quebec Consumer Protection
                Act, RSQ c P-40.1, sections 54.1 to 54.16 (which grants
                Quebec consumers a seven (7) day cancellation right from
                receipt of an internet-contract good); the British Columbia
                Business Practices and Consumer Protection Act, SBC 2004 c 2,
                sections 46 to 54 governing distance sales contracts
                (described in full in section 4A above); the Ontario Consumer Protection Act 2002, S.O.
                2002 c 30; the Alberta Consumer Protection Act, RSA 2000 c
                C-26.3; the EU Consumer Rights Directive 2011/83/EU and the
                UK Consumer Contracts Regulations 2013 (each granting a
                fourteen-day right of withdrawal); and any other mandatory
                consumer-protection law. You retain those rights and we will
                honour them.
              </p>
              <p>
                <Strong>How to request a refund.</Strong> Email{" "}
                <a
                  href="mailto:hello@anticipy.ai"
                  className="underline hover:text-[var(--gold)]"
                  style={{ color: "var(--text-on-dark)" }}
                >
                  hello@anticipy.ai
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
                refund request is under review, will be contested. This
                requirement does not limit your statutory rights under
                Section 75 of the United Kingdom Consumer Credit Act 1974 or
                similar mandatory chargeback statutes in your jurisdiction.
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
                ships to you.
              </p>
              <p>
                <Strong>
                  Year two and onward are optional and not automatically
                  renewed by this pre-order.
                </Strong>{" "}
                After the first year, continued use of the AI service
                requires you to affirmatively opt in to a new annual
                subscription at the then-current price, currently projected
                at USD 99 per year. We will email a renewal offer not less
                than thirty (30) days before the end of your first year. If
                you do not opt in, no charge is taken and the cloud features
                are deactivated. Hardware functions on a limited offline
                basis without the cloud service. This structure is intended
                to satisfy California Business and Professions Code Sections
                17600 to 17606 (Automatic Renewal Law) and the United States
                Restore Online Shoppers&apos; Confidence Act (15 U.S.C.
                Sections 8401 to 8405) by ensuring no automatic charge
                occurs without your express, informed, and recent consent.
              </p>
              <p>
                We are not obligated to maintain any specific AI feature,
                model, integration, or third-party connection for any period
                of time. AI models may be replaced, deprecated, or removed
                without notice.
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
                TRADE. WE DO NOT WARRANT THAT THE PRODUCT OR THE AI SERVICE
                WILL BE UNINTERRUPTED, ERROR-FREE, SECURE, OR FREE OF
                DEFECTS, OR THAT THE AI WILL PRODUCE ACCURATE, COMPLETE, OR
                RELIABLE OUTPUT.
              </p>
              <p>
                Nothing in this section limits any warranty that cannot be
                disclaimed under your local mandatory consumer protection
                law, including without limitation the Australian Consumer Law
                guarantees (where applicable), Canadian provincial implied
                warranties of merchantable quality, and the EU two-year
                conformity guarantee under Directive 2019/771.
              </p>
            </Section>

            <Section title="10. Indemnification by you.">
              <p>
                You agree to defend, indemnify, and hold harmless
                Anticipation Labs Inc., its officers, directors, employees,
                contractors, agents, affiliates, and licensors from and
                against any third-party claim, demand, loss, damage, fine,
                penalty, cost, or expense (including reasonable attorneys&apos;
                fees) arising out of or related to: (a) your misuse of the
                Product or AI service; (b) your violation of any law or
                regulation in connection with the Product, including without
                limitation wiretapping, recording-consent, privacy, or
                workplace-surveillance laws; (c) your infringement of any
                third party&apos;s right, including without limitation
                intellectual-property or privacy rights; (d) your breach of
                this Agreement; or (e) your reliance on AI output. This
                indemnification does not apply to the extent prohibited by
                applicable consumer-protection law.
              </p>
            </Section>

            <Section title="11. Limitation of liability.">
              <p>
                TO THE FULLEST EXTENT PERMITTED BY LAW, THE TOTAL CUMULATIVE
                LIABILITY OF ANTICIPATION LABS INC., ITS OFFICERS,
                DIRECTORS, EMPLOYEES, AGENTS, AFFILIATES, AND LICENSORS
                ARISING OUT OF OR RELATING TO THIS AGREEMENT OR THE PRE-ORDER
                SHALL NOT EXCEED <Strong>THE AMOUNT YOU PAID FOR THE
                PRE-ORDER</Strong>. IN NO EVENT SHALL WE BE LIABLE FOR ANY
                INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, PUNITIVE, OR
                EXEMPLARY DAMAGES, INCLUDING LOST PROFITS, LOST REVENUE,
                LOST DATA, LOSS OF GOODWILL, BUSINESS INTERRUPTION, OR ANY
                OTHER INTANGIBLE LOSS, REGARDLESS OF THE LEGAL THEORY AND
                EVEN IF WE HAVE BEEN ADVISED OF THE POSSIBILITY OF SUCH
                DAMAGES. THIS LIMITATION APPLIES TO ALL CAUSES OF ACTION IN
                THE AGGREGATE, INCLUDING WITHOUT LIMITATION BREACH OF
                CONTRACT, BREACH OF WARRANTY, NEGLIGENCE, STRICT LIABILITY,
                MISREPRESENTATION, AND ANY OTHER TORT.
              </p>
              <p>
                Some jurisdictions do not allow the exclusion of certain
                damages; if you are in one of those, our liability is limited
                to the maximum extent permitted by law. Nothing in this
                section limits liability for death or personal injury caused
                by our negligence, fraud, fraudulent misrepresentation, or
                any other liability that cannot be excluded under applicable
                law.
              </p>
            </Section>

            <Section title="12. Privacy and payment data.">
              <p>
                Your name, email address, shipping address, billing address,
                phone number (if you provide one), and IP address are
                collected to fulfill this pre-order. Payment is processed by{" "}
                <Strong>Stripe, Inc.</Strong> Stripe collects and handles your
                full payment card details under its own privacy policy. We
                receive a non-card identifier, the last four digits of the
                card, the card brand, the country, and a payment intent
                identifier. We never see your full card number and never
                store it. You may exercise data-access, correction, and
                deletion rights as described in our{" "}
                <Link
                  href="/privacy"
                  className="underline hover:text-[var(--gold)]"
                  style={{ color: "var(--text-on-dark)" }}
                >
                  Privacy Policy
                </Link>
                . Note that statutory tax-record-keeping laws may require us
                to retain certain transaction records for up to six (6) years
                after the transaction even after you request deletion.
              </p>
            </Section>

            <Section title="13. Transferability and assignment.">
              <p>
                Your pre-order is non-transferable. You may not resell,
                assign, or otherwise transfer your pre-order to a third party
                without our prior written consent. Any attempted transfer
                without consent is void. We may transfer or assign this
                Agreement, including in connection with a merger, acquisition,
                or sale of substantially all of our assets, without notice
                to you.
              </p>
            </Section>

            <Section title="14. Dispute resolution. Mandatory arbitration. Class action waiver. PLEASE READ.">
              <p>
                <Strong>
                  Please read this section carefully. It affects your legal
                  rights. It requires you to arbitrate disputes with us
                  individually rather than as a member of a class.
                </Strong>
              </p>
              <p>
                <Strong>14.1 Informal resolution first.</Strong> Before you
                file a claim against us, you agree to first email{" "}
                <a
                  href="mailto:hello@anticipy.ai"
                  className="underline hover:text-[var(--gold)]"
                  style={{ color: "var(--text-on-dark)" }}
                >
                  hello@anticipy.ai
                </a>{" "}
                with a written description of the claim, the relief you seek,
                and the email used at checkout. The parties will negotiate
                in good faith for sixty (60) days. The statute of limitations
                will be tolled during this period. Only after sixty (60) days
                may either party initiate arbitration.
              </p>
              <p>
                <Strong>14.2 Binding arbitration.</Strong> Any dispute,
                claim, or controversy arising out of or relating to this
                Agreement, the Product, the AI service, or the pre-order,
                whether in contract, tort, statute, or otherwise (a{" "}
                &ldquo;Dispute&rdquo;), that is not resolved through
                informal resolution will be settled by{" "}
                <Strong>binding individual arbitration</Strong>. For
                customers in the United States, arbitration will be
                administered by JAMS under its Comprehensive Arbitration
                Rules and Procedures or, if the amount in controversy is
                less than USD 250,000, its Streamlined Arbitration Rules
                and Procedures. For customers outside the United States,
                arbitration will be administered by the International Centre
                for Dispute Resolution under its International Arbitration
                Rules. The arbitration will take place in Vancouver, British
                Columbia, or, if you reside in the United States, in your
                county of residence, at your election. The arbitrator&apos;s
                decision is final and binding. Judgment on the award may be
                entered in any court of competent jurisdiction.
              </p>
              <p>
                <Strong>
                  14.3 Class action waiver. No class arbitration.
                </Strong>{" "}
                YOU AND ANTICIPATION LABS INC. AGREE THAT EACH MAY BRING
                CLAIMS AGAINST THE OTHER ONLY IN YOUR OR ITS INDIVIDUAL
                CAPACITY, AND NOT AS A PLAINTIFF OR CLASS MEMBER IN ANY
                PURPORTED CLASS, COLLECTIVE, REPRESENTATIVE, MULTIPLE
                PLAINTIFF, OR SIMILAR PROCEEDING. The arbitrator may not
                consolidate more than one person&apos;s claims and may not
                preside over any form of representative or class proceeding.
                If a court or arbitrator decides this class action waiver
                is unenforceable, the entirety of this Section 14 is void.
              </p>
              <p>
                <Strong>14.4 Jury trial waiver.</Strong> TO THE FULLEST
                EXTENT PERMITTED BY LAW, YOU AND WE EACH WAIVE ANY RIGHT TO
                A TRIAL BY JURY.
              </p>
              <p>
                <Strong>14.5 Thirty-day right to opt out of arbitration.</Strong>{" "}
                You may opt out of this Section 14 by emailing{" "}
                <a
                  href="mailto:hello@anticipy.ai"
                  className="underline hover:text-[var(--gold)]"
                  style={{ color: "var(--text-on-dark)" }}
                >
                  hello@anticipy.ai
                </a>{" "}
                with the subject line &ldquo;Arbitration Opt-Out&rdquo;
                within thirty (30) days of your pre-order being charged.
                Your opt-out notice must include your name, the email used
                at checkout, and your pre-order session id. Opting out does
                not affect any other provision of this Agreement.
              </p>
              <p>
                <Strong>14.6 Small claims carveout.</Strong> Either party
                may bring an individual claim in small claims court for
                disputes within that court&apos;s jurisdiction, in lieu of
                arbitration, so long as the action remains in small claims
                court and proceeds on an individual basis.
              </p>
              <p>
                <Strong>14.7 Severability of this section.</Strong> If any
                part of Sections 14.1, 14.2, or 14.4 through 14.6 is found
                unenforceable, the remainder of Section 14 will be enforced.
                The class action waiver in 14.3 is not severable; if it is
                unenforceable, all of Section 14 is void and the dispute
                proceeds in the courts identified in Section 15.
              </p>
              <p>
                <Strong>14.8 Mandatory consumer forum.</Strong> Nothing in
                this Section 14 prevents you from bringing a claim before a
                consumer-forum body that your jurisdiction provides as
                non-waivable, including the Quebec Office de la protection
                du consommateur, the Australian Competition and Consumer
                Commission, the European Online Dispute Resolution
                platform, or your provincial small-claims registry.
              </p>
            </Section>

            <Section title="15. Governing law and venue.">
              <p>
                This Agreement is governed by the laws of the Province of
                British Columbia, Canada, without regard to its conflict-of-
                laws principles. The federal laws of Canada applicable in
                British Columbia also apply. The United Nations Convention
                on Contracts for the International Sale of Goods does not
                apply. The exclusive venue for any Dispute that is not
                subject to mandatory consumer-forum law and that is not
                subject to arbitration under Section 14 is the courts
                located in Vancouver, British Columbia. If you are a
                consumer entitled to bring a claim in your local forum
                under your jurisdiction&apos;s mandatory consumer
                protection law, you retain that right.
              </p>
            </Section>

            <Section title="16. Force majeure.">
              <p>
                We are not liable for any delay, suspension, or failure to
                perform caused by events outside our reasonable control,
                including but not limited to: acts of God, fire, flood,
                pandemic, epidemic, government action, war, terrorism, civil
                unrest, labor disputes, supply chain failure, semiconductor
                or component shortage, raw materials shortage, port
                congestion, customs delay, carrier failure, internet or
                cloud-infrastructure outage, change in U.S. or Canadian
                tariff schedule, change in export-control or sanctions
                regime, currency restriction or hyperinflation in a
                supplier&apos;s country, regulatory action affecting
                wireless certification (FCC, IC, CE, or equivalent), and
                cybersecurity incident or ransomware attack. A force
                majeure event extends the time for performance for the
                duration of the event. If a force majeure event continues
                for more than one hundred and eighty (180) days, either
                party may terminate the affected pre-order with a full
                refund to you as your sole remedy.
              </p>
            </Section>

            <Section title="17. Entire agreement and amendments.">
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
                expressly accept the amended terms by clicking through on a
                renewal or new transaction.
              </p>
            </Section>

            <Section title="18. Severability.">
              <p>
                If any provision of this Agreement is held to be
                unenforceable under the law of your jurisdiction, that
                provision will be modified to the minimum extent necessary
                to make it enforceable, or, if modification is not
                possible, severed; the remainder of the Agreement remains in
                full force. The class-action waiver in Section 14.3 is not
                severable; see Section 14.7.
              </p>
            </Section>

            <Section title="19. Survival.">
              <p>
                The following provisions survive termination or expiration
                of this Agreement: Section 3 (preliminary specifications and
                puffery disclaimer), Section 5 (refund process), Section 9
                (warranty disclaimer), Section 10 (indemnification),
                Section 11 (limitation of liability), Section 12 (privacy
                and payment data), Section 14 (arbitration and class action
                waiver), Section 15 (governing law), Section 18
                (severability), and any other provision that by its nature
                should survive.
              </p>
            </Section>

            <Section title="20. Notices and contact for legal service.">
              <p>
                Notices to us must be sent to{" "}
                <a
                  href="mailto:hello@anticipy.ai"
                  className="underline hover:text-[var(--gold)]"
                  style={{ color: "var(--text-on-dark)" }}
                >
                  hello@anticipy.ai
                </a>{" "}
                with a copy by registered mail to: Anticipation Labs Inc.,
                West Vancouver, British Columbia, Canada. Notices to you may
                be sent to the email address on your pre-order. Each
                party&apos;s notice is deemed received one (1) business day
                after dispatch by email.
              </p>
            </Section>

            <Section title="21. Export controls and sanctions.">
              <p>
                You may not export, re-export, or transfer the Product, the
                AI service, or any technical data received from us to any
                country, person, or entity subject to United States or
                Canadian sanctions, including without limitation Cuba, Iran,
                North Korea, Syria, the Crimea region, the so-called
                Donetsk People&apos;s Republic and Luhansk People&apos;s
                Republic, or any person on a U.S. Treasury OFAC list or
                Canadian consolidated sanctions list. You represent that you
                are not such a person.
              </p>
            </Section>

            <Section title="22. Headings and interpretation.">
              <p>
                Headings are for convenience only and do not affect
                interpretation. &ldquo;Including&rdquo; means including
                without limitation. References to laws include any amendment
                or successor. This Agreement is in English; any translation
                is for convenience and the English version controls.
              </p>
            </Section>

            <Section title="23. Contact.">
              <p>
                Anticipation Labs Inc.
                <br />
                West Vancouver, British Columbia, Canada
                <br />
                Customer support:{" "}
                <a
                  href="mailto:hello@anticipy.ai"
                  className="underline hover:text-[var(--gold)]"
                  style={{ color: "var(--text-on-dark)" }}
                >
                  hello@anticipy.ai
                </a>
                <br />
                Legal notices:{" "}
                <a
                  href="mailto:hello@anticipy.ai"
                  className="underline hover:text-[var(--gold)]"
                  style={{ color: "var(--text-on-dark)" }}
                >
                  hello@anticipy.ai
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
