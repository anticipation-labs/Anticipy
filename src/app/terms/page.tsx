import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Terms of Service — Anticipy",
  description:
    "Terms of service for Anticipy, the AI wearable pendant by Anticipation Labs Inc. Read before joining the waitlist.",
  openGraph: {
    title: "Terms of Service — Anticipy",
    description:
      "Terms of service for Anticipy by Anticipation Labs Inc.",
    url: "https://www.anticipy.ai/terms",
    siteName: "Anticipy",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Terms of Service — Anticipy",
    description:
      "Terms of service for Anticipy by Anticipation Labs Inc.",
  },
};

export default function TermsOfService() {
  return (
    <div style={{ background: "var(--dark)" }} className="min-h-screen">
      {/* Header */}
      <header
        className="px-6 py-6 border-b"
        style={{ borderColor: "var(--dark-border)" }}
      >
        <div className="flex items-center justify-between max-w-3xl mx-auto">
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
            &larr; Back
          </Link>
        </div>
      </header>

      {/* Content */}
      <main className="px-6 py-16">
        <div className="max-w-3xl mx-auto">
          <h1 className="font-serif text-[clamp(32px,5vw,48px)] text-[var(--text-on-dark)] leading-[1.15] mb-4">
            Terms of Service
          </h1>
          <p className="text-[15px] text-[var(--text-on-dark-muted)] font-light mb-12">
            Effective Date: March 30, 2026 &middot; Last Updated: March 30, 2026
          </p>

          <div className="space-y-10 text-[15px] text-[var(--text-on-dark-muted)] font-light leading-[1.8]">
            {/* ============================================================ */}
            {/* 1. INTRODUCTION & PRE-ORDER DISCLAIMERS */}
            {/* ============================================================ */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                1. Introduction &amp; Pre-Order / Waitlist Disclaimers
              </h2>
              <p>
                Welcome to Anticipy (<Link href="/" className="text-gold hover:underline">www.anticipy.ai</Link>),
                operated by <strong className="text-[var(--text-on-dark)]">Anticipation Labs Inc.</strong>
                (&ldquo;Company,&rdquo; &ldquo;we,&rdquo; &ldquo;us,&rdquo;
                or &ldquo;our&rdquo;). These Terms of Service (&ldquo;Terms&rdquo;) govern your access to
                and use of our website, waitlist, pre-order system, and&mdash;once available&mdash;the Anticipy
                hardware device, mobile application, cloud action engine, and all related services
                (collectively, the &ldquo;Service&rdquo;).
              </p>
              <p className="mt-4">
                By accessing this website, joining our waitlist, placing a pre-order, or using any part
                of the Service, you agree to be bound by these Terms. If you do not agree, do not use
                the Service.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                1.1 Product Development Status
              </h3>
              <p>
                <strong className="text-[var(--text-on-dark)]">The Anticipy device is currently in
                development and has not yet been manufactured or shipped.</strong> All specifications,
                features, capabilities, pricing, delivery timelines, and product descriptions displayed
                on our website, marketing materials, or communicated through any channel
                are <strong className="text-[var(--text-on-dark)]">preliminary, aspirational, and subject
                to change</strong> at our sole discretion without prior notice. No representation made
                during the pre-order or waitlist phase constitutes a guarantee, warranty, or binding
                commitment regarding the final product.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                1.2 Waitlist &amp; Pre-Order Nature
              </h3>
              <p>
                Joining the Anticipy waitlist is <strong className="text-[var(--text-on-dark)]">not a
                purchase</strong> and does not create a binding obligation on either party. A waitlist
                reservation does not guarantee availability, pricing, delivery priority, or any
                particular product configuration. We reserve the right to modify, suspend, or cancel
                the waitlist program at any time.
              </p>
              <p className="mt-4">
                If you place a pre-order and provide payment, you acknowledge that the product has not
                been manufactured and that the estimated delivery date is an approximation only. We will
                make commercially reasonable efforts to fulfill pre-orders within the stated timeframe;
                however, delays may occur due to supply chain constraints, regulatory approvals,
                engineering revisions, or other factors beyond our control.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                1.3 FTC Mail-Order Rule Compliance (16 CFR Part 435)
              </h3>
              <p>
                In accordance with the United States Federal Trade Commission&apos;s Mail, Internet, or
                Telephone Order Merchandise Rule (16 CFR Part 435), if we are unable to ship your
                pre-ordered product within the timeframe stated at the time of your order (or within
                30 days if no timeframe was stated), we will:
              </p>
              <ul className="list-disc pl-6 mt-3 space-y-2">
                <li>
                  Provide you with a revised shipping date and offer you the option to either
                  (a) consent to the delay or (b) cancel your order for
                  a <strong className="text-[var(--text-on-dark)]">full and prompt refund</strong>;
                </li>
                <li>
                  If you do not respond to our delay notice, we may treat your silence as consent
                  to the delay for the first delay only;
                </li>
                <li>
                  For any subsequent delays, your failure to respond will be treated as a cancellation,
                  and we will issue a full refund within seven (7) business days;
                </li>
                <li>
                  You may cancel at any time before the product ships and receive a full refund,
                  regardless of the number of delay notices issued.
                </li>
              </ul>
              <p className="mt-4">
                For complete details on our refund and cancellation policies, please see
                our <Link href="/refund" className="text-gold hover:underline">Refund Policy</Link>.
              </p>
            </section>

            {/* ============================================================ */}
            {/* 2. ELIGIBILITY */}
            {/* ============================================================ */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                2. Eligibility
              </h2>
              <p>
                You must be at least <strong className="text-[var(--text-on-dark)]">eighteen (18) years
                of age</strong> to use the Service, join the waitlist, place a pre-order, or operate
                the Anticipy device. This age requirement exists because the Anticipy device captures
                ambient audio, and the legal landscape surrounding audio recording&mdash;including
                wiretapping and eavesdropping statutes&mdash;is complex and varies significantly
                across jurisdictions. Minors may lack the legal capacity to understand and comply with
                the consent and disclosure obligations associated with audio recording.
              </p>
              <p className="mt-4">
                By using the Service, you represent and warrant that you are at least 18 years old,
                that you have the legal capacity to enter into these Terms, and that your use of the
                Service will comply with all applicable laws in your jurisdiction, including but not
                limited to laws governing audio recording, data protection, and electronic
                communications.
              </p>
            </section>

            {/* ============================================================ */}
            {/* 3. DESCRIPTION OF SERVICE */}
            {/* ============================================================ */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                3. Description of Service
              </h2>
              <p>
                Anticipy is an AI-powered wearable system designed to listen to your daily conversations,
                understand context and intent, and proactively execute actions on your behalf. The
                Service consists of the following components:
              </p>
              <ul className="list-disc pl-6 mt-3 space-y-2">
                <li>
                  <strong className="text-[var(--text-on-dark)]">Anticipy Pendant</strong> &mdash;
                  A wearable hardware device equipped with a microphone array and Bluetooth Low Energy
                  (BLE) connectivity. The pendant captures ambient audio in your environment and
                  transmits it to the companion mobile application. An LED indicator on the pendant
                  is active whenever audio recording is in progress.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Anticipy Mobile Application</strong> &mdash;
                  A companion app for iOS and Android that receives audio streams from the pendant,
                  performs on-device processing (including transcription and intent extraction), manages
                  device settings and preferences, and communicates with the cloud action engine.
                  Audio is processed locally on your phone to maximize privacy.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Anticipy Action Engine</strong> &mdash;
                  A cloud-based AI system that receives structured intent data from the mobile app,
                  interprets your needs, and executes actions on your behalf through integrations
                  with third-party services (e.g., calendar management, messaging, task creation,
                  online orders, and more).
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Charging Pad</strong> &mdash;
                  A wireless charging accessory included with each Anticipy pendant for convenient
                  daily charging.
                </li>
              </ul>
              <p className="mt-4">
                The specific features, integrations, and capabilities of the Service may change as
                the product evolves. We reserve the right to add, modify, or discontinue any
                feature at any time with reasonable notice.
              </p>
            </section>

            {/* ============================================================ */}
            {/* 4. PURCHASE AND PAYMENT */}
            {/* ============================================================ */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                4. Purchase and Payment
              </h2>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                4.1 Hardware Pricing
              </h3>
              <p>
                The Anticipy pendant (including charging pad) is available for a one-time purchase
                price of <strong className="text-[var(--text-on-dark)]">$149 USD</strong>. This price
                is subject to change prior to final product release. Any price change will be
                communicated to pre-order customers before their order is charged, and they will be
                given the option to cancel.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                4.2 Service Subscription
              </h3>
              <p>
                Your hardware purchase includes <strong className="text-[var(--text-on-dark)]">one (1)
                full year of the Anticipy Service</strong> at no additional charge, beginning on the
                date the device is activated. After the first year, continued access to the Anticipy
                Action Engine and cloud features requires an annual subscription
                of <strong className="text-[var(--text-on-dark)]">$99 USD per year</strong>.
              </p>
              <p className="mt-4">
                We will provide you with at least <strong className="text-[var(--text-on-dark)]">thirty
                (30) days&apos; written notice</strong> before your subscription renewal date. If you
                do not wish to renew, you must cancel before the renewal date to avoid being charged.
                Cancellation instructions will be provided in the renewal notice and are available in
                the mobile application.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                4.3 Taxes and Duties
              </h3>
              <p>
                All prices are exclusive of applicable taxes, duties, levies, and shipping charges.
                You are responsible for all sales tax, value-added tax (VAT), goods and services tax
                (GST), harmonized sales tax (HST), customs duties, and any other governmental charges
                imposed in connection with your purchase. The applicable tax amount will be calculated
                and displayed at checkout.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                4.4 Payment Processing
              </h3>
              <p>
                Payments are processed through third-party payment processors. By providing your
                payment information, you represent that you are authorized to use the designated
                payment method and authorize us (or our payment processor) to charge your payment
                method for the total amount of your purchase, including applicable taxes and fees.
                We do not store your full credit card or payment details on our servers.
              </p>
            </section>

            {/* ============================================================ */}
            {/* 5. AUDIO CAPTURE AND CONSENT */}
            {/* ============================================================ */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                5. Audio Capture, Recording Laws, and Consent
              </h2>
              <p>
                The Anticipy pendant is designed to capture ambient audio in your environment. This
                includes conversations you participate in as well as sounds and speech from other
                individuals who may be nearby. <strong className="text-[var(--text-on-dark)]">You, the
                user, are solely and exclusively responsible for ensuring that your use of the Anticipy
                device complies with all applicable federal, state, provincial, and local laws governing
                audio recording, wiretapping, eavesdropping, and surveillance in every jurisdiction
                where you operate the device.</strong>
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                5.1 LED Recording Indicator
              </h3>
              <p>
                The Anticipy pendant features a visible LED indicator that is illuminated whenever the
                device is actively recording audio. While this indicator serves as a visual cue to
                nearby individuals, it does <strong className="text-[var(--text-on-dark)]">not</strong> constitute
                legally sufficient notice or consent in all jurisdictions. You must independently ensure
                that your recording practices satisfy the legal requirements of your jurisdiction.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                5.2 United States &mdash; All-Party (Two-Party) Consent States
              </h3>
              <p>
                Several U.S. states require the consent of <strong className="text-[var(--text-on-dark)]">all
                parties</strong> to a conversation before recording is lawful. If you reside in or use
                the device in any of the following states, you must obtain explicit consent from every
                individual whose voice may be captured:
              </p>
              <ul className="list-disc pl-6 mt-3 space-y-2">
                <li>
                  <strong className="text-[var(--text-on-dark)]">California</strong> &mdash; Cal. Penal
                  Code &sect; 632. Violation is punishable as a misdemeanor or felony.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Connecticut</strong> &mdash; Conn. Gen.
                  Stat. &sect; 52-570d.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Delaware</strong> &mdash; Del. Code Ann.
                  tit. 11, &sect; 2402.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Florida</strong> &mdash; Fla. Stat.
                  &sect; 934.03. <strong className="text-[var(--text-on-dark)]">Violation is a
                  third-degree felony.</strong>
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Illinois</strong> &mdash; 720 ILCS
                  5/14-2 (Illinois Eavesdropping Act).
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Maryland</strong> &mdash; Md. Code Ann.,
                  Cts. &amp; Jud. Proc. &sect; 10-402.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Massachusetts</strong> &mdash; Mass. Gen.
                  Laws ch. 272, &sect; 99. One of the strictest wiretapping statutes in the U.S.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Montana</strong> &mdash; Mont. Code Ann.
                  &sect; 45-8-213.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Nevada</strong> &mdash; Nev. Rev. Stat.
                  &sect; 200.620.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">New Hampshire</strong> &mdash; N.H. Rev.
                  Stat. Ann. &sect; 570-A:2.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Pennsylvania</strong> &mdash; 18 Pa.
                  Cons. Stat. &sect; 5703. <strong className="text-[var(--text-on-dark)]">Violation is
                  a third-degree felony.</strong>
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Washington</strong> &mdash; Wash. Rev.
                  Code &sect; 9.73.030.
                </li>
              </ul>
              <p className="mt-4">
                This list may not be exhaustive and recording laws are subject to change. It is your
                responsibility to verify the current laws in your jurisdiction before using the device.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                5.3 International Recording Laws
              </h3>
              <p>
                Many countries impose strict requirements on audio recording. The following is a
                non-exhaustive overview of jurisdictions with notable restrictions:
              </p>
              <ul className="list-disc pl-6 mt-3 space-y-2">
                <li>
                  <strong className="text-[var(--text-on-dark)]">Germany</strong> &mdash; &sect;201 of
                  the German Criminal Code (Strafgesetzbuch, StGB) criminalizes the unauthorized
                  recording of private speech. Violations can result in imprisonment of up to three
                  years or a fine.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">European Union (GDPR)</strong> &mdash;
                  The General Data Protection Regulation imposes strict requirements on the processing
                  of personal data, including voice recordings. A lawful basis (such as explicit consent)
                  is required for any processing of audio data that can identify individuals.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Saudi Arabia</strong> &mdash; The
                  Anti-Cybercrime Law (Royal Decree No. M/17, 2007) prohibits unauthorized recording
                  of conversations. Violations may result in imprisonment of up to one year and/or
                  fines of up to 500,000 SAR.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">United Arab Emirates</strong> &mdash;
                  Federal Decree-Law No. 34 of 2021 on combating rumors and cybercrime prohibits
                  recording or disclosing conversations without consent. Violations carry significant
                  penalties including imprisonment and fines.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Canada</strong> &mdash; The Criminal
                  Code of Canada (&sect;184) allows one-party consent recording, meaning you may record
                  a conversation you are a party to. However, intercepting private communications to
                  which you are not a party is a criminal offense.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Australia</strong> &mdash; Recording
                  laws vary by state and territory. Some jurisdictions (e.g., Queensland, Victoria)
                  require all-party consent for recording private conversations.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Japan</strong> &mdash; While one-party
                  consent is generally recognized, recording without the knowledge of other parties may
                  have civil liability implications.
                </li>
              </ul>
              <p className="mt-4">
                <strong className="text-[var(--text-on-dark)]">Anticipation Labs Inc. is not a law firm
                and does not provide legal advice.</strong> The information above is provided for
                informational purposes only and may be incomplete or outdated. You should consult with
                a qualified attorney in your jurisdiction before using the Anticipy device to understand
                your legal obligations regarding audio recording.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                5.4 Your Responsibilities
              </h3>
              <p>
                You agree that you will:
              </p>
              <ul className="list-disc pl-6 mt-3 space-y-2">
                <li>
                  Obtain all necessary consents before recording any individual;
                </li>
                <li>
                  Inform people in your vicinity that the device is recording when required by law;
                </li>
                <li>
                  Not use the device to record conversations in which you are not a participant
                  (i.e., not use the device for eavesdropping or surveillance);
                </li>
                <li>
                  Not use the device in locations where recording is prohibited (e.g., certain
                  government buildings, medical facilities, courtrooms);
                </li>
                <li>
                  Disable recording in jurisdictions or situations where lawful recording is not
                  possible.
                </li>
              </ul>
            </section>

            {/* ============================================================ */}
            {/* 6. ACTIONS ON YOUR BEHALF */}
            {/* ============================================================ */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                6. Actions on Your Behalf
              </h2>
              <p>
                The Anticipy Action Engine uses artificial intelligence to interpret your intent from
                conversational context and execute actions on your behalf. You acknowledge and agree
                to the following:
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                6.1 AI Interpretation Limitations
              </h3>
              <p>
                AI interpretation of natural language is inherently imperfect. The Action Engine
                may <strong className="text-[var(--text-on-dark)]">misinterpret your intent</strong>,
                derive incorrect meaning from ambiguous statements, act on sarcasm or hypothetical
                statements as if they were genuine instructions, or fail to capture nuance and context.
                We make no guarantee that the system will correctly understand your intentions in
                every instance.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                6.2 High-Stakes Action Confirmations
              </h3>
              <p>
                For actions that the system classifies as high-stakes&mdash;including but not limited
                to financial transactions, sending messages to contacts, scheduling commitments,
                making purchases, or modifying important data&mdash;Anticipy will request your
                explicit confirmation via the mobile application before proceeding. You are
                responsible for reviewing and approving these confirmation requests carefully.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                6.3 User Responsibility
              </h3>
              <p>
                <strong className="text-[var(--text-on-dark)]">You are ultimately responsible for all
                actions taken by the Anticipy system on your behalf.</strong> Whether an action is
                executed automatically or after your confirmation, you bear full responsibility for
                the consequences. Anticipation Labs Inc. is not liable for any damages, losses, or
                obligations arising from actions the system takes based on its interpretation of
                your conversations, regardless of whether that interpretation was correct.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                6.4 Third-Party Services
              </h3>
              <p>
                The Action Engine may interact with third-party services and platforms to execute
                actions. Your use of these integrations is subject to the respective terms of
                service and privacy policies of those third parties. Anticipation Labs is not
                responsible for the availability, accuracy, or conduct of any third-party service.
              </p>
            </section>

            {/* ============================================================ */}
            {/* 7. INTELLECTUAL PROPERTY */}
            {/* ============================================================ */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                7. Intellectual Property
              </h2>
              <p>
                All intellectual property rights in the Anticipy device, mobile application, Action
                Engine, website, branding, logos, trade names, documentation, and all associated
                software, firmware, algorithms, models, and technology (collectively,
                &ldquo;Anticipy IP&rdquo;) are and shall remain the exclusive property of Anticipation
                Labs Inc. and its licensors. These Terms do not grant you any right, title, or interest
                in the Anticipy IP except for the limited license to use the Service as described
                herein.
              </p>
              <p className="mt-4">
                You are granted a limited, non-exclusive, non-transferable, revocable license to use
                the Anticipy mobile application and cloud services solely for personal,
                non-commercial use in connection with your Anticipy device, subject to these Terms.
              </p>
              <p className="mt-4">
                You may not reverse engineer, decompile, disassemble, or otherwise attempt to derive
                the source code of any Anticipy software or firmware. You may not copy, modify, create
                derivative works from, distribute, sell, lease, sublicense, or otherwise transfer any
                Anticipy IP. You may not remove, alter, or obscure any proprietary notices, labels,
                or marks on the device or software.
              </p>
              <p className="mt-4">
                Your audio data, transcripts, and personal information remain your property, subject
                to the licenses you grant us to process that data in order to provide the Service, as
                described in our <Link href="/privacy" className="text-gold hover:underline">Privacy
                Policy</Link>.
              </p>
            </section>

            {/* ============================================================ */}
            {/* 8. HARDWARE WARRANTY */}
            {/* ============================================================ */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                8. Hardware Warranty
              </h2>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                8.1 Limited Warranty
              </h3>
              <p>
                Anticipation Labs Inc. warrants that the Anticipy pendant and charging pad
                (&ldquo;Hardware&rdquo;) will be free from defects in materials and workmanship under
                normal use for a period of <strong className="text-[var(--text-on-dark)]">one (1)
                year</strong> from the date of original delivery to you (the &ldquo;Warranty
                Period&rdquo;). If a defect arises during the Warranty Period, and you submit a valid
                claim, Anticipation Labs will, at its sole discretion, either (a) repair the Hardware
                at no charge using new or refurbished parts, (b) replace the Hardware with a new or
                refurbished unit, or (c) refund the purchase price of the Hardware.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                8.2 Exclusions
              </h3>
              <p>
                This limited warranty does not cover:
              </p>
              <ul className="list-disc pl-6 mt-3 space-y-2">
                <li>Damage caused by accident, misuse, abuse, negligence, or unauthorized modification;</li>
                <li>Damage caused by operating the Hardware outside its intended use or contrary to provided instructions;</li>
                <li>Damage caused by exposure to liquids, extreme temperatures, or corrosive environments beyond the Hardware&apos;s rated specifications;</li>
                <li>Normal wear and tear, including but not limited to scratches, dents, and fading;</li>
                <li>Cosmetic damage that does not affect the functionality of the Hardware;</li>
                <li>Damage caused by use with non-Anticipy accessories or peripherals;</li>
                <li>Hardware that has been opened, tampered with, or repaired by anyone other than Anticipation Labs or its authorized service providers;</li>
                <li>Software, firmware, or service-related issues (which are governed by the software licensing terms).</li>
              </ul>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                8.3 Warranty Claims
              </h3>
              <p>
                To make a warranty claim, contact us
                at <a href="mailto:legal@anticipy.ai" className="text-gold hover:underline">legal@anticipy.ai</a> with
                your order number, a description of the defect, and photographic evidence if applicable.
                We will provide instructions for returning the Hardware. You are responsible for
                shipping costs to our service center; we will cover return shipping for valid
                warranty claims.
              </p>
            </section>

            {/* ============================================================ */}
            {/* 9. LIMITATION OF LIABILITY */}
            {/* ============================================================ */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                9. Limitation of Liability
              </h2>
              <p className="uppercase font-normal">
                TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, IN NO EVENT SHALL ANTICIPATION LABS
                INC., ITS DIRECTORS, OFFICERS, EMPLOYEES, AGENTS, AFFILIATES, SUCCESSORS, OR ASSIGNS
                BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, PUNITIVE, OR EXEMPLARY
                DAMAGES, INCLUDING BUT NOT LIMITED TO DAMAGES FOR LOSS OF PROFITS, GOODWILL, DATA,
                BUSINESS OPPORTUNITIES, OR OTHER INTANGIBLE LOSSES, ARISING OUT OF OR IN CONNECTION
                WITH YOUR USE OF OR INABILITY TO USE THE SERVICE, REGARDLESS OF THE THEORY OF LIABILITY
                (CONTRACT, TORT, STRICT LIABILITY, OR OTHERWISE) AND EVEN IF ANTICIPATION LABS HAS BEEN
                ADVISED OF THE POSSIBILITY OF SUCH DAMAGES.
              </p>
              <p className="uppercase font-normal mt-4">
                TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, THE TOTAL AGGREGATE LIABILITY OF
                ANTICIPATION LABS INC. FOR ALL CLAIMS ARISING OUT OF OR RELATING TO THESE TERMS OR THE
                SERVICE SHALL NOT EXCEED THE GREATER OF (A) THE AMOUNTS YOU HAVE PAID TO ANTICIPATION
                LABS IN THE TWELVE (12) MONTHS IMMEDIATELY PRECEDING THE EVENT GIVING RISE TO THE
                CLAIM, OR (B) ONE HUNDRED DOLLARS ($100 USD).
              </p>
              <p className="uppercase font-normal mt-4">
                THE FOREGOING LIMITATIONS SHALL APPLY NOTWITHSTANDING THE FAILURE OF THE ESSENTIAL
                PURPOSE OF ANY LIMITED REMEDY. SOME JURISDICTIONS DO NOT ALLOW THE EXCLUSION OR
                LIMITATION OF INCIDENTAL OR CONSEQUENTIAL DAMAGES, SO THE ABOVE LIMITATIONS MAY NOT
                APPLY TO YOU. IN SUCH JURISDICTIONS, OUR LIABILITY SHALL BE LIMITED TO THE GREATEST
                EXTENT PERMITTED BY LAW.
              </p>
              <p className="uppercase font-normal mt-4">
                ANTICIPATION LABS INC. SHALL NOT BE LIABLE FOR ANY DAMAGES, LOSSES, OR LEGAL
                CONSEQUENCES ARISING FROM YOUR USE OF THE ANTICIPY DEVICE TO RECORD AUDIO IN
                VIOLATION OF APPLICABLE RECORDING, WIRETAPPING, OR SURVEILLANCE LAWS. YOU ASSUME
                ALL RISK ASSOCIATED WITH YOUR USE OF THE AUDIO RECORDING FUNCTIONALITY.
              </p>
              <p className="uppercase font-normal mt-4">
                ANTICIPATION LABS INC. SHALL NOT BE LIABLE FOR ANY DAMAGES OR LOSSES ARISING FROM
                ACTIONS TAKEN BY THE ANTICIPY ACTION ENGINE BASED ON MISINTERPRETED, INCOMPLETE,
                OR INCORRECT UNDERSTANDING OF YOUR INTENT, REGARDLESS OF WHETHER SUCH ACTIONS WERE
                EXECUTED AUTOMATICALLY OR AFTER USER CONFIRMATION.
              </p>
            </section>

            {/* ============================================================ */}
            {/* 10. INDEMNIFICATION */}
            {/* ============================================================ */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                10. Indemnification
              </h2>
              <p>
                You agree to indemnify, defend, and hold harmless Anticipation Labs Inc., its
                directors, officers, employees, agents, affiliates, successors, and assigns from
                and against any and all claims, demands, actions, suits, proceedings, losses,
                damages, liabilities, costs, and expenses (including reasonable attorneys&apos; fees
                and court costs) arising out of or relating to:
              </p>
              <ul className="list-disc pl-6 mt-3 space-y-2">
                <li>Your use or misuse of the Service or the Anticipy device;</li>
                <li>Your violation of these Terms;</li>
                <li>Your violation of any applicable law, rule, or regulation, including but not limited to audio recording, wiretapping, eavesdropping, data protection, and privacy laws;</li>
                <li>Your failure to obtain required consents for audio recording;</li>
                <li>Any claim by a third party that their rights were violated by your use of the device (including but not limited to privacy rights, publicity rights, and intellectual property rights);</li>
                <li>Any action taken by the Anticipy Action Engine on your behalf, whether correctly or incorrectly interpreted;</li>
                <li>Any content, data, or information you provide through the Service.</li>
              </ul>
              <p className="mt-4">
                This indemnification obligation shall survive the termination of these Terms and
                your use of the Service.
              </p>
            </section>

            {/* ============================================================ */}
            {/* 11. TERMINATION */}
            {/* ============================================================ */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                11. Termination
              </h2>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                11.1 Termination by You
              </h3>
              <p>
                You may stop using the Service at any time. You may cancel your subscription through
                the mobile application or by contacting us
                at <a href="mailto:legal@anticipy.ai" className="text-gold hover:underline">legal@anticipy.ai</a>.
                Cancellation of your subscription does not entitle you to a refund of any prepaid
                fees unless required by applicable law.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                11.2 Termination by Us
              </h3>
              <p>
                Anticipation Labs may suspend or terminate your access to the Service, in whole or
                in part, at any time and for any reason, including but not limited to:
              </p>
              <ul className="list-disc pl-6 mt-3 space-y-2">
                <li>Breach of these Terms;</li>
                <li>Use of the device in violation of applicable laws;</li>
                <li>Conduct that we reasonably believe is harmful to other users, third parties, or our business;</li>
                <li>Extended periods of inactivity;</li>
                <li>Discontinuation of the Service.</li>
              </ul>
              <p className="mt-4">
                We will provide reasonable notice before termination where practicable, except in
                cases of serious breach or legal obligation.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                11.3 Effect of Termination
              </h3>
              <p>
                Upon termination of your account or subscription:
              </p>
              <ul className="list-disc pl-6 mt-3 space-y-2">
                <li>
                  Your access to cloud features and the Action Engine will be immediately revoked;
                </li>
                <li>
                  The Anticipy hardware remains your physical property. However, without an active
                  subscription, the device will operate with limited or no cloud-dependent
                  functionality;
                </li>
                <li>
                  Your personal data, audio recordings, transcripts, and account information will
                  be scheduled for deletion and permanently removed from our systems within
                  <strong className="text-[var(--text-on-dark)]"> thirty (30) days</strong> of
                  termination, unless retention is required by law or necessary for the resolution
                  of pending disputes;
                </li>
                <li>
                  Sections of these Terms that by their nature should survive termination shall
                  survive, including but not limited to Sections 7 (Intellectual Property),
                  9 (Limitation of Liability), 10 (Indemnification), 12 (Dispute Resolution),
                  and 13 (Governing Law).
                </li>
              </ul>
            </section>

            {/* ============================================================ */}
            {/* 12. DISPUTE RESOLUTION */}
            {/* ============================================================ */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                12. Dispute Resolution
              </h2>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                12.1 Informal Resolution
              </h3>
              <p>
                Before initiating any formal dispute resolution proceeding, you agree to first contact
                us at <a href="mailto:legal@anticipy.ai" className="text-gold hover:underline">legal@anticipy.ai</a> and
                attempt to resolve the dispute informally for a period of at least sixty (60) days.
                Most disputes can be resolved through good-faith discussion.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                12.2 Binding Arbitration
              </h3>
              <p>
                If the dispute cannot be resolved informally, you and Anticipation Labs agree that
                any dispute, claim, or controversy arising out of or relating to these Terms or the
                Service shall be resolved by <strong className="text-[var(--text-on-dark)]">binding
                arbitration</strong> administered in the jurisdiction in which the Company is incorporated,
                in accordance with the rules of a recognized commercial arbitration body mutually agreed
                upon by the parties. The arbitration shall be conducted in the
                English language by a single arbitrator. The arbitrator&apos;s decision shall be final
                and binding and may be entered as a judgment in any court of competent jurisdiction.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                12.3 Class Action Waiver
              </h3>
              <p>
                <strong className="text-[var(--text-on-dark)]">YOU AND ANTICIPATION LABS AGREE THAT
                EACH PARTY MAY BRING CLAIMS AGAINST THE OTHER ONLY IN YOUR OR ITS INDIVIDUAL CAPACITY,
                AND NOT AS A PLAINTIFF OR CLASS MEMBER IN ANY PURPORTED CLASS, CONSOLIDATED, OR
                REPRESENTATIVE ACTION.</strong> Unless both parties agree otherwise in writing, the
                arbitrator may not consolidate the claims of more than one person and may not otherwise
                preside over any form of class, consolidated, or representative proceeding.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                12.4 Exceptions
              </h3>
              <p>
                Notwithstanding the foregoing, either party may seek injunctive or other equitable
                relief in any court of competent jurisdiction to prevent the actual or threatened
                infringement, misappropriation, or violation of a party&apos;s intellectual property
                rights. Additionally, disputes relating to small claims may be brought in the
                applicable small claims court.
              </p>
            </section>

            {/* ============================================================ */}
            {/* 13. GOVERNING LAW */}
            {/* ============================================================ */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                13. Governing Law
              </h2>
              <p>
                These Terms and any dispute arising out of or relating to them or the Service shall be
                governed by and construed in accordance with the laws of the jurisdiction in which
                Anticipation Labs Inc. is incorporated, without regard to conflict of law principles.
                Subject to the arbitration provisions in Section 12, you irrevocably consent to the
                exclusive jurisdiction and venue of the courts in that jurisdiction for any action or
                proceeding arising out of or relating to these Terms.
              </p>
            </section>

            {/* ============================================================ */}
            {/* 14. JURISDICTION-SPECIFIC CONSUMER RIGHTS */}
            {/* ============================================================ */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                14. Jurisdiction-Specific Consumer Rights
              </h2>
              <p>
                Certain jurisdictions provide consumers with statutory rights that cannot be waived
                or limited by contract. <strong className="text-[var(--text-on-dark)]">Where the
                following rights provide greater protection than these Terms, they shall override
                our standard terms to the extent required by law.</strong>
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                14.1 European Union
              </h3>
              <p>
                If you are a consumer residing in the European Union, you are entitled to
                a <strong className="text-[var(--text-on-dark)]">fourteen (14) calendar day right of
                withdrawal</strong> from the date you receive the goods, pursuant to the Consumer
                Rights Directive 2011/83/EU. During this period, you may return the product for any
                reason or no reason and receive a full refund of the purchase price, including standard
                delivery costs. You are responsible for the cost of returning the goods unless we
                agree otherwise. To exercise your right of withdrawal, you must inform us of your
                decision by a clear statement (e.g., by email
                to <a href="mailto:legal@anticipy.ai" className="text-gold hover:underline">legal@anticipy.ai</a>)
                before the withdrawal period expires. Nothing in these Terms shall affect your
                statutory rights under applicable EU consumer protection legislation, including
                rights regarding non-conforming goods under Directive (EU) 2019/771.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                14.2 United Kingdom
              </h3>
              <p>
                If you are a consumer residing in the United Kingdom, you benefit from the Consumer
                Rights Act 2015, which provides:
              </p>
              <ul className="list-disc pl-6 mt-3 space-y-2">
                <li>
                  A <strong className="text-[var(--text-on-dark)]">fourteen (14) calendar day
                  cancellation period</strong> from the date you receive the goods (Consumer Contracts
                  Regulations 2013), during which you may cancel for any reason and receive a full
                  refund;
                </li>
                <li>
                  A <strong className="text-[var(--text-on-dark)]">thirty (30) day short-term right to
                  reject</strong> goods that are faulty or not as described and receive a full refund;
                </li>
                <li>
                  Beyond 30 days and up to six months, the right to request a repair or replacement,
                  and a refund if the repair or replacement is unsuccessful;
                </li>
                <li>
                  These rights are in addition to any warranty we provide and cannot be limited by
                  these Terms.
                </li>
              </ul>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                14.3 Saudi Arabia
              </h3>
              <p>
                If you are a consumer residing in the Kingdom of Saudi Arabia, you are entitled to a
                <strong className="text-[var(--text-on-dark)]"> seven (7) day return right</strong> from
                the date of receiving the product, in accordance with the E-Commerce Law (Royal Decree
                No. M/126, 2019) and its implementing regulations. The product must be in its original
                condition and packaging. This right exists in addition to your rights under the
                Saudi Consumer Protection Law.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                14.4 China
              </h3>
              <p>
                If you are a consumer residing in the People&apos;s Republic of China, you are entitled
                to a <strong className="text-[var(--text-on-dark)]">seven (7) day no-reason return
                right</strong> from the date of receiving the product, pursuant to Article 25 of the
                Consumer Rights Protection Law of the People&apos;s Republic of China. The product must
                be in its original condition. This right applies to products purchased through online
                channels.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                14.5 South Korea
              </h3>
              <p>
                If you are a consumer residing in the Republic of Korea, you are entitled to a
                <strong className="text-[var(--text-on-dark)]"> seven (7) day withdrawal right</strong> from
                the date of receiving the product, pursuant to the Act on Consumer Protection in
                Electronic Commerce. The product must be in its original condition. If the product
                is different from what was advertised or delivered in a defective condition, the
                withdrawal period is extended to thirty (30) days.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                14.6 Japan
              </h3>
              <p>
                If you are a consumer residing in Japan, you are entitled to an
                <strong className="text-[var(--text-on-dark)]"> eight (8) day return right</strong> from
                the date of receiving the product under the Act on Specified Commercial Transactions
                (Tokutei Sh&omacr;torihiki H&omacr;), unless the product listing clearly stated that
                returns are not accepted at the time of purchase. Where applicable, you may return the
                product and receive a full refund, minus return shipping costs unless the product was
                defective or not as described.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                14.7 General
              </h3>
              <p>
                If you reside in a jurisdiction that provides consumer protection rights not
                specifically addressed above, those rights shall apply to the extent they offer
                greater protection than these Terms. Nothing in these Terms is intended to exclude,
                restrict, or modify any mandatory statutory rights that apply to your purchase.
              </p>
            </section>

            {/* ============================================================ */}
            {/* 15. SEVERABILITY, ENTIRE AGREEMENT, AND CHANGES */}
            {/* ============================================================ */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                15. Severability, Entire Agreement, and Changes to Terms
              </h2>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                15.1 Severability
              </h3>
              <p>
                If any provision of these Terms is held to be invalid, illegal, or unenforceable by
                a court or arbitrator of competent jurisdiction, that provision shall be modified to
                the minimum extent necessary to make it valid, legal, and enforceable, or if
                modification is not possible, severed from these Terms. The invalidity or
                unenforceability of any provision shall not affect the validity or enforceability
                of the remaining provisions, which shall continue in full force and effect.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                15.2 Entire Agreement
              </h3>
              <p>
                These Terms, together with our <Link href="/privacy" className="text-gold hover:underline">Privacy
                Policy</Link> and <Link href="/refund" className="text-gold hover:underline">Refund
                Policy</Link>, constitute the entire agreement between you and Anticipation Labs Inc.
                regarding the Service and supersede all prior and contemporaneous agreements,
                proposals, representations, and understandings, whether written or oral, relating to
                the subject matter hereof. No waiver of any term or condition shall be deemed a
                further or continuing waiver of such term or any other term.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                15.3 Changes to These Terms
              </h3>
              <p>
                Anticipation Labs reserves the right to modify these Terms at any time. If we make
                material changes, we will provide you with at
                least <strong className="text-[var(--text-on-dark)]">thirty (30) days&apos;
                notice</strong> before the changes take effect, via email to the address associated
                with your account and/or a prominent notice on our website. Your continued use of the
                Service after the effective date of the revised Terms constitutes your acceptance of
                the changes. If you do not agree to the modified Terms, you must discontinue your use
                of the Service before the effective date.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                15.4 Assignment
              </h3>
              <p>
                You may not assign or transfer your rights or obligations under these Terms without
                our prior written consent. We may assign our rights and obligations under these Terms
                without restriction, including in connection with a merger, acquisition, sale of
                assets, or by operation of law.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                15.5 Waiver
              </h3>
              <p>
                Our failure to enforce any right or provision of these Terms shall not constitute a
                waiver of such right or provision. Any waiver of any provision of these Terms will be
                effective only if in writing and signed by Anticipation Labs.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                15.6 Force Majeure
              </h3>
              <p>
                Anticipation Labs shall not be liable for any failure or delay in performing its
                obligations under these Terms to the extent that such failure or delay results from
                circumstances beyond our reasonable control, including but not limited to acts of God,
                natural disasters, pandemics, epidemics, war, terrorism, riots, embargoes, acts of
                civil or military authorities, fire, floods, supply chain disruptions, semiconductor
                shortages, strikes, power outages, internet or telecommunications failures, or
                cyberattacks.
              </p>
            </section>

            {/* ============================================================ */}
            {/* 16. CONTACT INFORMATION */}
            {/* ============================================================ */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                16. Contact Information
              </h2>
              <p>
                If you have any questions, concerns, or requests regarding these Terms of Service,
                please contact us:
              </p>
              <ul className="list-none pl-0 mt-4 space-y-2">
                <li>
                  <strong className="text-[var(--text-on-dark)]">Anticipation Labs Inc.</strong>
                </li>
                <li>
                  Legal inquiries: <a href="mailto:legal@anticipy.ai" className="text-gold hover:underline">legal@anticipy.ai</a>
                </li>
                <li>
                  General inquiries: <a href="mailto:omar@anticipy.ai" className="text-gold hover:underline">omar@anticipy.ai</a>
                </li>
              </ul>
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
              href="/refund"
              className="text-[13px] text-[var(--text-on-dark-muted)] hover:text-gold transition-colors"
            >
              Refund Policy
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}
