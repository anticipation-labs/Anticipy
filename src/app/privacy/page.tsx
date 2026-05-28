import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Policy — Anticipy",
  description:
    "How Anticipy collects, uses, and protects your data. Our commitment to privacy-first AI wearable technology.",
  openGraph: {
    title: "Privacy Policy — Anticipy",
    description:
      "How Anticipy collects, uses, and protects your data.",
    url: "https://www.anticipy.ai/privacy",
    siteName: "Anticipy",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Privacy Policy — Anticipy",
    description:
      "How Anticipy collects, uses, and protects your data.",
  },
};

export default function PrivacyPolicy() {
  return (
    <div style={{ background: "var(--dark)" }} className="min-h-screen">
      {/* Header */}
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

      {/* Content */}
      <main className="px-6 py-16">
        <div className="max-w-3xl mx-auto">
          <h1 className="font-serif text-[clamp(32px,5vw,48px)] text-[var(--text-on-dark)] leading-[1.15] mb-4">
            Privacy Policy
          </h1>
          <p className="text-[15px] text-[var(--text-on-dark-muted)] font-light mb-12">
            Last updated: March 30, 2026
          </p>

          <div className="space-y-10 text-[15px] text-[var(--text-on-dark-muted)] font-light leading-[1.8]">
            {/* ───────────────────────────────────────────── 1 */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                1. Introduction &amp; Scope
              </h2>
              <p>
                This Privacy Policy (&ldquo;Policy&rdquo;) is issued by{" "}
                <strong className="text-[var(--text-on-dark)]">
                  Anticipation Labs Inc.
                </strong>
                (&ldquo;Anticipy,&rdquo; &ldquo;we,&rdquo; &ldquo;us,&rdquo; or
                &ldquo;our&rdquo;). It governs the collection, use, disclosure,
                retention, and protection of personal information in connection
                with our AI wearable pendant device (the &ldquo;Device&rdquo;),
                our companion mobile application (the &ldquo;App&rdquo;), our
                cloud-based action engine (the &ldquo;Service&rdquo;), and our
                website located at{" "}
                <a
                  href="https://www.anticipy.ai"
                  className="text-gold hover:underline"
                >
                  anticipy.ai
                </a>{" "}
                (the &ldquo;Site&rdquo;), collectively referred to as
                the &ldquo;Platform.&rdquo;
              </p>
              <p className="mt-4">
                This Policy applies to all individuals who interact with the
                Platform, including customers, prospective customers, waitlist
                registrants, website visitors, and any third parties whose
                information may be incidentally processed in connection with
                Device usage. By using or accessing the Platform, you acknowledge
                that you have read and understood this Policy. If you do not
                agree with this Policy, you must discontinue use of the Platform
                immediately.
              </p>
              <p className="mt-4">
                This Policy is designed to comply with applicable data protection
                and privacy laws across multiple jurisdictions, including but not
                limited to the California Consumer Privacy Act as amended by the
                California Privacy Rights Act (CCPA/CPRA, Cal. Civ. Code
                &sect;&sect;1798.100&ndash;199.100), the General Data Protection
                Regulation (GDPR, Regulation (EU) 2016/679), the UK General Data
                Protection Regulation (UK GDPR) and Data Protection Act 2018,
                Saudi Arabia&apos;s Personal Data Protection Law (PDPL, Royal
                Decree No. M/19), the UAE Personal Data Protection Law (Federal
                Decree-Law No. 45/2021), Japan&apos;s Act on Protection of
                Personal Information (APPI), South Korea&apos;s Personal
                Information Protection Act (PIPA), Singapore&apos;s Personal
                Data Protection Act 2012 (PDPA), India&apos;s Digital Personal
                Data Protection Act 2023 (DPDP Act), and the People&apos;s
                Republic of China&apos;s Personal Information Protection Law
                (PIPL).
              </p>
            </section>

            {/* ───────────────────────────────────────────── 2 */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                2. Our Privacy Architecture — On-Device Processing &amp; No Audio
                Storage
              </h2>
              <p>
                Anticipy was designed from the ground up with a{" "}
                <strong className="text-[var(--text-on-dark)]">
                  privacy-first architecture
                </strong>
                . Understanding how the Device processes information is essential
                to understanding the privacy protections we provide.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                2.1 How the Device Works
              </h3>
              <p>
                The Anticipy pendant captures ambient audio from the user&apos;s
                immediate environment via an integrated microphone. This audio
                is transmitted in real time over{" "}
                <strong className="text-[var(--text-on-dark)]">
                  encrypted Bluetooth Low Energy 5.3 (BLE 5.3)
                </strong>{" "}
                to the user&apos;s paired smartphone. The Bluetooth connection
                employs AES-CCM encryption as specified in the Bluetooth Core
                Specification v5.3, ensuring that audio data in transit between
                the Device and the smartphone is protected against interception.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                2.2 On-Device Audio Processing
              </h3>
              <p>
                Once the audio stream reaches the user&apos;s smartphone, it is
                processed{" "}
                <strong className="text-[var(--text-on-dark)]">
                  entirely on-device
                </strong>{" "}
                by our proprietary AI inference engine running locally on the
                phone&apos;s processor. The AI model analyzes the audio stream
                to extract actionable intent &mdash; that is, it determines
                whether the audio contains a request, task, reminder, or other
                actionable information that the user would want Anticipy to act
                upon.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                2.3 Immediate Audio Disposal
              </h3>
              <p>
                <strong className="text-[var(--text-on-dark)]">
                  Raw audio is discarded within seconds of processing.
                </strong>{" "}
                The audio stream exists only in volatile memory (RAM) for the
                brief duration required for the AI model to perform intent
                extraction. It is never written to persistent storage (disk,
                flash, or any other non-volatile medium) on the Device, the
                smartphone, or any server. There is no recording functionality,
                no audio buffer that persists beyond the processing window, and
                no mechanism by which audio can be retrieved after processing is
                complete.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                2.4 What Is Transmitted to the Cloud
              </h3>
              <p>
                After on-device processing, the{" "}
                <strong className="text-[var(--text-on-dark)]">
                  only data transmitted to our cloud action engine
                </strong>{" "}
                is a short, structured text instruction (e.g., &ldquo;Set a
                reminder for 3 PM tomorrow to call the dentist&rdquo; or
                &ldquo;Add milk to the grocery list&rdquo;). These text
                instructions contain no audio data, no voice biometrics, no
                ambient sound signatures, and no acoustic information of any
                kind. The cloud action engine receives only the minimal text
                payload necessary to execute the user&apos;s requested action.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                2.5 What We Do NOT Do
              </h3>
              <ul className="list-disc pl-6 space-y-2 mt-2">
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    We never store audio recordings.
                  </strong>{" "}
                  No audio file, audio stream, or audio fragment is ever saved to
                  any storage medium.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    We never transmit raw audio to the cloud.
                  </strong>{" "}
                  Audio never leaves the user&apos;s smartphone. Only derived text
                  instructions are sent to our servers.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    We never create voice profiles or biometric data.
                  </strong>{" "}
                  We do not perform speaker identification, voice recognition, or
                  any form of biometric processing.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    We never sell, share, or license audio data.
                  </strong>{" "}
                  Because we do not possess audio data, there is nothing to sell
                  or share.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    We never use audio for advertising or profiling.
                  </strong>{" "}
                  Anticipy has no advertising business model and does not build
                  behavioral profiles from audio content.
                </li>
              </ul>
            </section>

            {/* ───────────────────────────────────────────── 3 */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                3. Information We Collect
              </h2>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                3.1 Information You Provide Directly
              </h3>
              <ul className="list-disc pl-6 space-y-2 mt-2">
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Account Information:
                  </strong>{" "}
                  Name, email address, and password when you create an Anticipy
                  account.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Waitlist Information:
                  </strong>{" "}
                  Email address and optional name when you join the Anticipy
                  waitlist.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Payment Information:
                  </strong>{" "}
                  Billing address, payment card details (processed via our
                  PCI-DSS-compliant payment processor; we do not store full card
                  numbers on our servers), and transaction history.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Shipping Information:
                  </strong>{" "}
                  Delivery address, phone number (for courier notifications), and
                  recipient name.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Communications:
                  </strong>{" "}
                  Content of emails, support requests, or feedback you send to us.
                </li>
              </ul>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                3.2 Information Generated by Device Usage
              </h3>
              <ul className="list-disc pl-6 space-y-2 mt-2">
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Text Instructions:
                  </strong>{" "}
                  Short text commands derived from on-device audio processing
                  (as described in Section 2.4). These are the only
                  user-generated data transmitted to our cloud.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Action Logs:
                  </strong>{" "}
                  Records of actions executed by the cloud action engine on your
                  behalf (e.g., reminders set, tasks created, messages queued).
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Device Telemetry:
                  </strong>{" "}
                  Battery status, firmware version, Bluetooth connection quality
                  metrics, and crash reports from the Device and App. This data
                  does not contain audio or personally identifiable information.
                </li>
              </ul>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                3.3 Information Collected Automatically via the Site
              </h3>
              <ul className="list-disc pl-6 space-y-2 mt-2">
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Log Data:
                  </strong>{" "}
                  IP address, browser type and version, operating system,
                  referring URL, pages visited, timestamps, and session duration.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Device Information:
                  </strong>{" "}
                  Screen resolution, device type (mobile/desktop), and language
                  preferences.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Cookies &amp; Similar Technologies:
                  </strong>{" "}
                  As detailed in Section 14 of this Policy.
                </li>
              </ul>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                3.4 Information We Do NOT Collect
              </h3>
              <ul className="list-disc pl-6 space-y-2 mt-2">
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Audio recordings
                  </strong>{" "}
                  &mdash; We do not store, record, or retain ambient audio in any
                  form.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Voice biometrics
                  </strong>{" "}
                  &mdash; We do not create voiceprints, speaker models, or any
                  biometric identifiers.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Location data
                  </strong>{" "}
                  &mdash; The Device does not contain GPS hardware. The App does
                  not request or access location permissions.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Contacts, photos, or files
                  </strong>{" "}
                  &mdash; The App does not access your phone&apos;s contacts,
                  photo library, file system, or any other on-device data beyond
                  what is necessary for Bluetooth pairing and audio processing.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Third-party advertising identifiers
                  </strong>{" "}
                  &mdash; We do not collect or use IDFA, GAID, or any advertising
                  identifiers.
                </li>
              </ul>
            </section>

            {/* ───────────────────────────────────────────── 4 */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                4. Audio Capture Disclosure &amp; Recording Consent Laws
              </h2>
              <p>
                The Anticipy Device captures ambient audio from the user&apos;s
                environment to enable on-device AI processing. Although Anticipy
                does not record or store audio,{" "}
                <strong className="text-[var(--text-on-dark)]">
                  the act of capturing ambient audio may be subject to
                  wiretapping, eavesdropping, and recording consent laws
                </strong>{" "}
                in your jurisdiction. It is{" "}
                <strong className="text-[var(--text-on-dark)]">
                  solely your responsibility
                </strong>{" "}
                to understand and comply with all applicable laws governing audio
                capture in your location and any location in which you use the
                Device.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                4.1 United States — Two-Party and All-Party Consent States
              </h3>
              <p>
                The United States does not have a uniform federal standard for
                audio recording consent. While federal law (18 U.S.C. &sect;2511)
                permits one-party consent, many states impose stricter
                requirements. If you use the Device in any of the following
                states, you must obtain the consent of{" "}
                <strong className="text-[var(--text-on-dark)]">
                  all parties
                </strong>{" "}
                whose conversations may be captured:
              </p>
              <ul className="list-disc pl-6 space-y-2 mt-2">
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    California
                  </strong>{" "}
                  (Cal. Penal Code &sect;632) &mdash; All-party consent required.
                  Violation is a criminal offense and may carry civil liability
                  of up to $5,000 per violation.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Florida
                  </strong>{" "}
                  (Fla. Stat. &sect;934.03) &mdash; All-party consent required.
                  Violation is a third-degree felony.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Pennsylvania
                  </strong>{" "}
                  (18 Pa. Cons. Stat. &sect;5704) &mdash; All-party consent
                  required. Violation is a felony of the third degree.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Illinois
                  </strong>{" "}
                  (720 ILCS 5/14-2) &mdash; All-party consent required.
                  Additionally, the Illinois Biometric Information Privacy Act
                  (BIPA, 740 ILCS 14) may apply if any biometric data is
                  processed; however, Anticipy does not create biometric data.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Washington
                  </strong>{" "}
                  (RCW &sect;9.73.030) &mdash; All-party consent required for
                  private conversations.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Maryland
                  </strong>{" "}
                  (Md. Code, Cts. &amp; Jud. Proc. &sect;10-402) &mdash;
                  All-party consent required.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Massachusetts
                  </strong>{" "}
                  (Mass. Gen. Laws ch. 272, &sect;99) &mdash; All-party consent
                  required. One of the strictest recording statutes in the U.S.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Montana
                  </strong>{" "}
                  (Mont. Code Ann. &sect;45-8-213) &mdash; All-party consent
                  required.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    New Hampshire
                  </strong>{" "}
                  (N.H. Rev. Stat. Ann. &sect;570-A:2) &mdash; All-party consent
                  required.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Connecticut
                  </strong>{" "}
                  (Conn. Gen. Stat. &sect;52-570d) &mdash; All-party consent
                  required.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Michigan, Nevada, Oregon, Vermont, Hawaii
                  </strong>{" "}
                  &mdash; Various all-party or two-party consent requirements
                  apply. Consult local statutes for details.
                </li>
              </ul>
              <p className="mt-4">
                <strong className="text-[var(--text-on-dark)]">
                  Important:
                </strong>{" "}
                Even in one-party consent states, you must be a party to the
                conversation to lawfully capture it. Using the Device to capture
                conversations to which you are not a party may violate federal
                wiretapping laws regardless of state law.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                4.2 Canada
              </h3>
              <p>
                Under the Criminal Code of Canada (R.S.C., 1985, c. C-46,
                &sect;184), it is an offence to intercept a private
                communication unless one party to the communication consents.
                Canada is a{" "}
                <strong className="text-[var(--text-on-dark)]">
                  one-party consent
                </strong>{" "}
                jurisdiction at the federal level. However, you must be a party
                to the conversation, and the consent must be informed. Using the
                Device to capture conversations in which you are not a
                participant may constitute an offence under &sect;184.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                4.3 European Union &amp; United Kingdom
              </h3>
              <p>
                Recording laws vary significantly across EU member states. In
                general, the GDPR requires a lawful basis for processing personal
                data, including audio data. Key examples:
              </p>
              <ul className="list-disc pl-6 space-y-2 mt-2">
                <li>
                  <strong className="text-[var(--text-on-dark)]">Germany</strong>{" "}
                  &mdash; &sect;201 Strafgesetzbuch (StGB) criminalizes the
                  unauthorized recording of the spoken word. All-party consent is
                  required. Violations may result in imprisonment of up to three
                  years or a fine.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">France</strong>{" "}
                  &mdash; Article 226-1 of the Code p&eacute;nal prohibits the
                  recording of private conversations without consent.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">Spain</strong>{" "}
                  &mdash; One-party consent is generally permitted, but
                  dissemination of recordings may violate privacy rights under
                  Ley Org&aacute;nica 1/1982.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    United Kingdom
                  </strong>{" "}
                  &mdash; The Regulation of Investigatory Powers Act 2000 (RIPA)
                  and the Telecommunications (Lawful Business Practice)
                  (Interception of Communications) Regulations 2000 govern
                  interception. One-party consent generally applies for personal
                  use, but GDPR/UK GDPR compliance is also required.
                </li>
              </ul>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                4.4 Saudi Arabia
              </h3>
              <p>
                The Saudi Anti-Cybercrime Law (Royal Decree No. M/17, 2007)
                criminalizes the unauthorized interception of electronically
                transmitted data. Article 3(1) provides that unlawful
                interception may result in imprisonment for up to one year and/or
                a fine of up to SAR 500,000. The Personal Data Protection Law
                (PDPL, Royal Decree No. M/19) further requires explicit consent
                for the collection of personal data. Users in Saudi Arabia must
                ensure they have explicit consent from all parties before using
                the Device in any context where private conversations may be
                captured.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                4.5 United Arab Emirates
              </h3>
              <p>
                Federal Decree-Law No. 34/2021 on Combating Rumours and
                Cybercrime (replacing the earlier Federal Decree-Law No. 5/2012)
                criminalizes the unauthorized recording or disclosure of
                communications. Article 44 imposes penalties including
                imprisonment and fines of AED 150,000 to AED 500,000 for
                eavesdropping, recording, or disclosing private communications
                without consent. Users in the UAE must obtain explicit prior
                consent from all parties before using the Device.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                4.6 Asia-Pacific
              </h3>
              <ul className="list-disc pl-6 space-y-2 mt-2">
                <li>
                  <strong className="text-[var(--text-on-dark)]">Japan</strong>{" "}
                  &mdash; While Japan&apos;s Wiretapping Act (Act No. 137 of
                  1999) primarily targets law enforcement, unauthorized recording
                  may infringe privacy rights under the Japanese Constitution
                  (Article 13) and Civil Code tort provisions.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    South Korea
                  </strong>{" "}
                  &mdash; The Protection of Communications Secrets Act (Act No.
                  4650) requires one-party consent for recording but prohibits
                  recording of communications to which you are not a party.
                  Violation may result in imprisonment of up to ten years.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Singapore
                  </strong>{" "}
                  &mdash; While Singapore does not have a specific wiretapping
                  statute, unauthorized recording may constitute an offence under
                  the Computer Misuse Act or a tort of intrusion upon seclusion.
                  The PDPA also requires consent for the collection of personal
                  data including audio.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">India</strong>{" "}
                  &mdash; The Indian Telegraph Act, 1885 (&sect;26) and the
                  Information Technology Act, 2000 (&sect;69) govern
                  interception. One-party consent is generally accepted, but the
                  DPDP Act 2023 requires a lawful purpose and consent for
                  personal data processing.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">China</strong>{" "}
                  &mdash; Article 253(a) of the Criminal Law, the Cybersecurity
                  Law, and the Personal Information Protection Law (PIPL) all
                  impose strict requirements on the collection of personal
                  information, including audio data. Consent of the data subject
                  is required, and cross-border transfer restrictions apply.
                </li>
              </ul>

              <p className="mt-6">
                <strong className="text-[var(--text-on-dark)]">
                  Anticipy expressly disclaims all liability
                </strong>{" "}
                for any user&apos;s failure to comply with applicable recording
                consent laws. You are solely responsible for ensuring that your
                use of the Device complies with all laws in your jurisdiction.
                We strongly recommend consulting with a qualified legal
                professional if you are uncertain about the laws applicable to
                your use of the Device.
              </p>
            </section>

            {/* ───────────────────────────────────────────── 5 */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                5. Legal Bases for Processing
              </h2>
              <p>
                We process personal information only where we have a lawful basis
                to do so. Depending on the jurisdiction and the nature of the
                processing, our legal bases include:
              </p>
              <ul className="list-disc pl-6 space-y-2 mt-4">
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Consent (GDPR Art. 6(1)(a); UK GDPR Art. 6(1)(a); PIPEDA
                    Principle 3; PDPL Art. 6; PIPL Art. 13(1)):
                  </strong>{" "}
                  Where you have given clear, affirmative consent to the
                  processing of your personal data for specific purposes, such as
                  joining our waitlist, subscribing to communications, or using
                  the Device.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Contractual Necessity (GDPR Art. 6(1)(b); UK GDPR Art.
                    6(1)(b)):
                  </strong>{" "}
                  Processing necessary for the performance of a contract with
                  you, including providing the Device, App, and Service
                  functionality, processing payments, and fulfilling orders.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Legitimate Interests (GDPR Art. 6(1)(f); UK GDPR Art.
                    6(1)(f); PIPEDA &ldquo;Reasonable Purpose&rdquo;):
                  </strong>{" "}
                  Processing necessary for our legitimate interests, including
                  improving our products and services, ensuring network and
                  information security, preventing fraud, and conducting internal
                  analytics, provided such interests are not overridden by your
                  fundamental rights and freedoms.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Legal Obligation (GDPR Art. 6(1)(c); UK GDPR Art. 6(1)(c)):
                  </strong>{" "}
                  Processing necessary to comply with legal obligations to which
                  we are subject, including tax reporting, regulatory
                  requirements, and responding to lawful government requests.
                </li>
              </ul>
            </section>

            {/* ───────────────────────────────────────────── 6 */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                6. How We Use Your Information
              </h2>
              <p>We use the personal information we collect to:</p>
              <ul className="list-disc pl-6 space-y-2 mt-4">
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Provide and operate the Platform:
                  </strong>{" "}
                  Process text instructions through our cloud action engine,
                  execute requested actions, deliver the Device and related
                  services, and manage your account.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Process transactions:
                  </strong>{" "}
                  Handle payments, shipping, returns, and refunds in accordance
                  with our{" "}
                  <Link href="/refund" className="text-gold hover:underline">
                    Refund Policy
                  </Link>
                  .
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Communicate with you:
                  </strong>{" "}
                  Send order confirmations, shipping notifications, service
                  updates, security alerts, and (with your consent) marketing
                  communications.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Improve our products:
                  </strong>{" "}
                  Analyze aggregated, de-identified usage patterns (derived solely
                  from text instruction metadata, never from audio) to improve
                  the AI model, enhance accuracy, and develop new features.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Ensure security:
                  </strong>{" "}
                  Detect and prevent fraud, abuse, and unauthorized access to the
                  Platform.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Comply with legal obligations:
                  </strong>{" "}
                  Respond to lawful requests from government authorities, comply
                  with tax and financial regulations, and enforce our{" "}
                  <Link href="/terms" className="text-gold hover:underline">
                    Terms of Service
                  </Link>
                  .
                </li>
              </ul>
            </section>

            {/* ───────────────────────────────────────────── 7 */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                7. Data Sharing &amp; Disclosure
              </h2>
              <p>
                We do not sell your personal information. We do not share your
                personal information with third parties for their own marketing
                purposes. We may disclose personal information in the following
                limited circumstances:
              </p>
              <ul className="list-disc pl-6 space-y-2 mt-4">
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Service Providers:
                  </strong>{" "}
                  We engage trusted third-party service providers to perform
                  functions on our behalf, including payment processing, cloud
                  infrastructure hosting, email delivery, customer support
                  platforms, and analytics. These providers are contractually
                  bound to use personal information only as necessary to provide
                  services to us and in accordance with this Policy.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Legal Requirements:
                  </strong>{" "}
                  We may disclose personal information where required by law,
                  regulation, legal process, or governmental request, including
                  in response to court orders, subpoenas, or requests from law
                  enforcement or regulatory authorities.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Business Transfers:
                  </strong>{" "}
                  In the event of a merger, acquisition, reorganization,
                  bankruptcy, or other corporate transaction, personal
                  information may be transferred as part of the transaction. We
                  will provide notice and, where required by applicable law,
                  obtain consent before personal information is transferred to
                  a new entity under materially different privacy practices.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    With Your Consent:
                  </strong>{" "}
                  We may share personal information where you have provided
                  specific, informed consent.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Aggregated or De-Identified Data:
                  </strong>{" "}
                  We may share aggregated, anonymized, or de-identified data
                  that cannot reasonably be used to identify you. This data is
                  not considered personal information under applicable privacy
                  laws.
                </li>
              </ul>
            </section>

            {/* ───────────────────────────────────────────── 8 */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                8. Data Retention
              </h2>
              <p>
                We retain personal information only for as long as necessary to
                fulfill the purposes described in this Policy, unless a longer
                retention period is required or permitted by law. Our specific
                retention periods are as follows:
              </p>
              <ul className="list-disc pl-6 space-y-2 mt-4">
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Raw Audio:
                  </strong>{" "}
                  Zero retention. Audio is processed in volatile memory and
                  discarded within seconds. It is never stored on any persistent
                  medium.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Text Instructions:
                  </strong>{" "}
                  Retained for up to 90 days to enable action history, replay of
                  recent actions, and service improvement. After 90 days, text
                  instructions are permanently deleted or irreversibly
                  de-identified.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Action Logs:
                  </strong>{" "}
                  Retained for up to 12 months for service continuity, debugging,
                  and quality assurance. Thereafter, logs are deleted or
                  de-identified.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Account Information:
                  </strong>{" "}
                  Retained for the duration of your account plus 30 days after
                  account deletion to allow for account recovery. After this
                  period, account data is permanently deleted.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Payment &amp; Transaction Records:
                  </strong>{" "}
                  Retained for the period required by applicable tax and
                  financial regulations (typically 7 years in Canada under the
                  Income Tax Act, R.S.C. 1985, c. 1 (5th Supp.)).
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Waitlist Data:
                  </strong>{" "}
                  Retained until you unsubscribe or until 24 months after signup,
                  whichever comes first, unless you convert to a customer
                  account.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Device Telemetry:
                  </strong>{" "}
                  Retained for up to 6 months for quality assurance and debugging
                  purposes, then permanently deleted.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Website Analytics:
                  </strong>{" "}
                  Retained for up to 26 months, in accordance with standard
                  analytics data retention practices.
                </li>
              </ul>
              <p className="mt-4">
                Upon expiration of the applicable retention period, personal
                information is either permanently deleted using industry-standard
                secure deletion methods or irreversibly anonymized so that it can
                no longer be associated with any identifiable individual.
              </p>
            </section>

            {/* ───────────────────────────────────────────── 9 */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                9. Cross-Border Data Transfers
              </h2>
              <p>
                Your personal information may be processed and stored in
                the jurisdiction where Anticipation Labs Inc. operates and, to the
                extent necessary for the operation of the Platform, in other
                countries where our service providers operate. We take the
                following measures to ensure adequate protection of personal
                information during cross-border transfers:
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                9.1 Transfers from the European Union &amp; United Kingdom
              </h3>
              <p>
                For transfers to jurisdictions not covered
                by an adequacy decision, we rely on Standard Contractual Clauses
                (SCCs) as approved by the European Commission (Commission
                Implementing Decision (EU) 2021/914) and, where applicable, the
                UK International Data Transfer Agreement (IDTA) or the UK
                Addendum to the EU SCCs, as approved by the UK Information
                Commissioner&apos;s Office (ICO).
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                9.2 Transfers from Saudi Arabia
              </h3>
              <p>
                Under the PDPL, cross-border transfers of personal data are
                permitted where the receiving country provides an adequate level
                of protection, or where the transfer is necessary for the
                performance of a contract. We ensure that all transfers from
                Saudi Arabia comply with the requirements of the PDPL and its
                implementing regulations, including obtaining any necessary
                regulatory approvals and conducting transfer impact assessments
                where required.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                9.3 Transfers from the UAE
              </h3>
              <p>
                Under Federal Decree-Law No. 45/2021, cross-border data
                transfers require that the receiving jurisdiction provides
                adequate data protection or that appropriate safeguards are in
                place. We comply with UAE Data Office requirements for
                international transfers and implement contractual protections
                and data protection impact assessments where necessary.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                9.4 Transfers from Asia-Pacific Jurisdictions
              </h3>
              <ul className="list-disc pl-6 space-y-2 mt-2">
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Japan (APPI):
                  </strong>{" "}
                  We comply with the APPI&apos;s requirements for cross-border
                  transfers, including obtaining consent and ensuring the
                  receiving country has equivalent data protection standards or
                  that the recipient has implemented an appropriate system for
                  data protection pursuant to PPC rules.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    South Korea (PIPA):
                  </strong>{" "}
                  We obtain the data subject&apos;s consent for cross-border
                  transfers and notify the Personal Information Protection
                  Commission (PIPC) as required, disclosing the recipient
                  country, the recipient, and the purpose and items of
                  information transferred.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Singapore (PDPA):
                  </strong>{" "}
                  We ensure that recipients of personal data outside Singapore
                  are bound by legally enforceable obligations to provide a
                  standard of protection at least comparable to the PDPA.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    India (DPDP Act):
                  </strong>{" "}
                  We comply with any restrictions on cross-border transfer of
                  personal data as may be notified by the Central Government
                  under the DPDP Act 2023, and transfer data only to countries
                  not listed on any restricted jurisdictions list.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    China (PIPL):
                  </strong>{" "}
                  We comply with the PIPL&apos;s requirements for cross-border
                  transfers, including conducting personal information protection
                  impact assessments, obtaining separate consent from data
                  subjects, and (where applicable) passing the security
                  assessment administered by the Cyberspace Administration of
                  China (CAC) or obtaining certification from an accredited
                  institution.
                </li>
              </ul>
            </section>

            {/* ───────────────────────────────────────────── 10 */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                10. Canada — PIPEDA, BC PIPA &amp; CASL
              </h2>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                10.1 PIPEDA (S.C. 2000, c. 5)
              </h3>
              <p>
                If you are located in Canada, your personal information may be
                subject to the Personal Information Protection and Electronic
                Documents Act (PIPEDA), which governs the collection, use, and
                disclosure of personal information in the course of commercial
                activities. We adhere to the ten fair information principles set
                out in Schedule 1 of PIPEDA:
              </p>
              <ul className="list-disc pl-6 space-y-2 mt-2">
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Accountability:
                  </strong>{" "}
                  Our designated privacy officer is responsible for compliance
                  with this Policy and PIPEDA.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Identifying Purposes:
                  </strong>{" "}
                  The purposes for which personal information is collected are
                  identified in Sections 3 and 6 of this Policy.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Consent:
                  </strong>{" "}
                  We obtain meaningful consent for the collection, use, and
                  disclosure of personal information, except where exempted by
                  law.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Limiting Collection:
                  </strong>{" "}
                  We collect only the personal information necessary for the
                  identified purposes.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Limiting Use, Disclosure &amp; Retention:
                  </strong>{" "}
                  Personal information is used and disclosed only for the
                  identified purposes and retained only as described in Section 8.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Accuracy:
                  </strong>{" "}
                  We make reasonable efforts to ensure personal information is
                  accurate, complete, and up-to-date.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Safeguards:
                  </strong>{" "}
                  We protect personal information with security safeguards
                  appropriate to the sensitivity of the information (see
                  Section 13).
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Openness:
                  </strong>{" "}
                  This Policy constitutes our public statement of information
                  management policies and practices.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Individual Access:
                  </strong>{" "}
                  You may request access to your personal information held by us
                  (see Section 15).
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Challenging Compliance:
                  </strong>{" "}
                  You may challenge our compliance by contacting our
                  privacy officer or, for Canadian residents, filing a complaint
                  with the Office of the Privacy Commissioner of Canada (OPC).
                </li>
              </ul>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                10.2 British Columbia PIPA (SBC 2003, c. 63)
              </h3>
              <p>
                If you are located in British Columbia, your personal information
                may also be subject to BC&apos;s Personal Information Protection
                Act (PIPA). PIPA provides substantially similar protections to
                PIPEDA but includes additional provisions, including the
                requirement to notify the BC Information &amp; Privacy
                Commissioner in the event of a data breach that poses a real
                risk of significant harm to individuals.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                10.3 CASL (S.C. 2010, c. 23)
              </h3>
              <p>
                Where applicable, Canada&apos;s Anti-Spam Legislation (CASL)
                governs the sending of commercial electronic messages (CEMs). We
                comply with CASL by:
              </p>
              <ul className="list-disc pl-6 space-y-2 mt-2">
                <li>
                  Obtaining express or implied consent before sending CEMs.
                </li>
                <li>
                  Including our identity, contact information, and a clear
                  unsubscribe mechanism in every CEM.
                </li>
                <li>
                  Honoring unsubscribe requests within 10 business days.
                </li>
                <li>
                  Maintaining records of consent in accordance with CASL
                  requirements.
                </li>
              </ul>
            </section>

            {/* ───────────────────────────────────────────── 11 */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                11. United States — CCPA/CPRA &amp; State Privacy Laws
              </h2>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                11.1 California (CCPA/CPRA)
              </h3>
              <p>
                If you are a California resident, you have specific rights under
                the California Consumer Privacy Act as amended by the California
                Privacy Rights Act (Cal. Civ. Code &sect;&sect;1798.100&ndash;199.100).
                These include:
              </p>
              <ul className="list-disc pl-6 space-y-2 mt-2">
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Know:
                  </strong>{" "}
                  You have the right to request that we disclose the categories
                  and specific pieces of personal information we have collected
                  about you, the sources of that information, the business or
                  commercial purposes for collection, and the categories of third
                  parties with whom we share it.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Delete:
                  </strong>{" "}
                  You have the right to request the deletion of your personal
                  information, subject to certain exceptions.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Correct:
                  </strong>{" "}
                  You have the right to request correction of inaccurate personal
                  information.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Opt-Out of Sale/Sharing:
                  </strong>{" "}
                  We do not sell personal information and do not share personal
                  information for cross-context behavioral advertising. Therefore,
                  there is no need to opt out.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Limit Use of Sensitive Personal Information:
                  </strong>{" "}
                  We do not use or disclose sensitive personal information for
                  purposes other than those permitted under CPRA &sect;1798.121.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Non-Discrimination:
                  </strong>{" "}
                  We will not discriminate against you for exercising any of your
                  CCPA/CPRA rights.
                </li>
              </ul>
              <p className="mt-4">
                To exercise your CCPA/CPRA rights, contact us at{" "}
                <a
                  href="mailto:privacy@anticipy.ai"
                  className="text-gold hover:underline"
                >
                  privacy@anticipy.ai
                </a>
                . We will verify your identity before processing your request
                and respond within 45 days, with the option to extend by an
                additional 45 days where necessary.
              </p>
              <p className="mt-4">
                <strong className="text-[var(--text-on-dark)]">
                  CCPA Categories of Personal Information Collected:
                </strong>{" "}
                Identifiers (name, email, IP address); Commercial information
                (purchase history, transaction records); Internet or electronic
                network activity (browsing history, device information); Inferences
                drawn from the above categories to create a profile (limited to
                service improvement, not advertising).
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                11.2 Other U.S. State Privacy Laws
              </h3>
              <p>
                We also recognize and respect privacy rights afforded by other
                state laws, including but not limited to:
              </p>
              <ul className="list-disc pl-6 space-y-2 mt-2">
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Virginia Consumer Data Protection Act (VCDPA):
                  </strong>{" "}
                  Rights to access, correct, delete, obtain a copy, and opt out
                  of targeted advertising, sale of personal data, and profiling.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Colorado Privacy Act (CPA):
                  </strong>{" "}
                  Rights to access, correct, delete, data portability, and opt
                  out of targeted advertising, sale, and profiling.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Connecticut Data Privacy Act (CTDPA):
                  </strong>{" "}
                  Similar rights to the VCDPA including opt-out of targeted
                  advertising and sale.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Utah Consumer Privacy Act (UCPA):
                  </strong>{" "}
                  Rights to access, delete, and opt out of sale of personal data
                  and targeted advertising.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Texas Data Privacy and Security Act (TDPSA):
                  </strong>{" "}
                  Rights to access, correct, delete, data portability, and
                  opt out of sale and targeted advertising.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Oregon Consumer Privacy Act (OCPA):
                  </strong>{" "}
                  Rights to access, correct, delete, data portability, and
                  opt out of targeted advertising, sale, and profiling.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Montana Consumer Data Privacy Act (MCDPA):
                  </strong>{" "}
                  Similar protections and rights as the VCDPA and CPA.
                </li>
              </ul>
              <p className="mt-4">
                Residents of these states may exercise their rights by contacting
                us at{" "}
                <a
                  href="mailto:privacy@anticipy.ai"
                  className="text-gold hover:underline"
                >
                  privacy@anticipy.ai
                </a>
                . If we deny your request, you may appeal the decision by
                contacting us at the same address with the subject line
                &ldquo;Privacy Rights Appeal.&rdquo;
              </p>
            </section>

            {/* ───────────────────────────────────────────── 12 */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                12. European Union — GDPR &amp; ePrivacy Directive
              </h2>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                12.1 GDPR (Regulation (EU) 2016/679)
              </h3>
              <p>
                If you are located in the European Economic Area (EEA), your
                personal data is processed in accordance with the General Data
                Protection Regulation (GDPR). As a data controller, Anticipation
                Labs Inc. is responsible for determining the purposes and means
                of processing your personal data. Your rights under the GDPR
                include:
              </p>
              <ul className="list-disc pl-6 space-y-2 mt-2">
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right of Access (Art. 15):
                  </strong>{" "}
                  You have the right to obtain confirmation of whether we process
                  your personal data and, if so, to access that data along with
                  information about the processing.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Rectification (Art. 16):
                  </strong>{" "}
                  You have the right to obtain the rectification of inaccurate
                  personal data concerning you without undue delay.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Erasure (Art. 17):
                  </strong>{" "}
                  You have the right to obtain the erasure of your personal data
                  (&ldquo;right to be forgotten&rdquo;) under the conditions
                  specified in Art. 17.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Restriction of Processing (Art. 18):
                  </strong>{" "}
                  You have the right to restrict the processing of your personal
                  data under certain circumstances.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Data Portability (Art. 20):
                  </strong>{" "}
                  You have the right to receive your personal data in a
                  structured, commonly used, and machine-readable format and to
                  transmit it to another controller.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Object (Art. 21):
                  </strong>{" "}
                  You have the right to object to the processing of your personal
                  data based on legitimate interests or direct marketing.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right Not to Be Subject to Automated Decision-Making
                    (Art. 22):
                  </strong>{" "}
                  You have the right not to be subject to a decision based solely
                  on automated processing, including profiling, which produces
                  legal effects or similarly significantly affects you.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Withdraw Consent (Art. 7(3)):
                  </strong>{" "}
                  Where processing is based on consent, you have the right to
                  withdraw consent at any time without affecting the lawfulness
                  of processing based on consent before its withdrawal.
                </li>
              </ul>
              <p className="mt-4">
                To exercise your rights, contact our privacy team at{" "}
                <a
                  href="mailto:privacy@anticipy.ai"
                  className="text-gold hover:underline"
                >
                  privacy@anticipy.ai
                </a>
                . We will respond within 30 days. You also have the right to
                lodge a complaint with a supervisory authority in the EU member
                state of your habitual residence, place of work, or place of the
                alleged infringement.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                12.2 ePrivacy Directive (Directive 2002/58/EC)
              </h3>
              <p>
                We comply with the ePrivacy Directive as implemented in EU member
                states, including requirements governing the use of cookies and
                similar tracking technologies on our Site (see Section 14), the
                confidentiality of communications, and the processing of traffic
                data.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                12.3 Data Protection Officer
              </h3>
              <p>
                While we are not required to appoint a Data Protection Officer
                (DPO) under Art. 37 of the GDPR, we have designated a privacy
                lead who can be reached at{" "}
                <a
                  href="mailto:privacy@anticipy.ai"
                  className="text-gold hover:underline"
                >
                  privacy@anticipy.ai
                </a>{" "}
                for all data protection inquiries from EU and EEA data subjects.
              </p>
            </section>

            {/* ───────────────────────────────────────────── 12B */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                13. United Kingdom — UK GDPR, Data Protection Act 2018 &amp; PECR
              </h2>
              <p>
                If you are located in the United Kingdom, your personal data is
                processed in accordance with the UK General Data Protection
                Regulation (UK GDPR) as retained in UK law by the European Union
                (Withdrawal) Act 2018, and the Data Protection Act 2018 (DPA
                2018).
              </p>
              <p className="mt-4">
                Your rights under the UK GDPR mirror those under the EU GDPR as
                described in Section 12.1 above. You have the right to lodge a
                complaint with the Information Commissioner&apos;s Office (ICO)
                at{" "}
                <a
                  href="https://ico.org.uk"
                  className="text-gold hover:underline"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  ico.org.uk
                </a>
                .
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                13.1 Privacy and Electronic Communications Regulations (PECR)
              </h3>
              <p>
                We comply with PECR in relation to the use of cookies and similar
                technologies on our Site (see Section 14), the sending of
                marketing communications, and the security of our electronic
                communications services. We will only send you marketing
                communications with your prior consent and provide a clear
                mechanism to opt out at any time.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                13.2 International Transfers from the UK
              </h3>
              <p>
                For transfers of personal data from the UK, we rely on the UK
                adequacy regulations or the UK International Data Transfer
                Agreement (IDTA) or UK Addendum to the EU Standard Contractual
                Clauses, as approved by the ICO.
              </p>
            </section>

            {/* ───────────────────────────────────────────── 13 */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                14. Saudi Arabia — PDPL (Royal Decree No. M/19)
              </h2>
              <p>
                If you are located in the Kingdom of Saudi Arabia, your personal
                data is processed in accordance with the Personal Data Protection
                Law (PDPL) as issued by Royal Decree No. M/19 and its
                implementing regulations issued by the Saudi Data &amp; Artificial
                Intelligence Authority (SDAIA).
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                14.1 Your Rights Under the PDPL
              </h3>
              <ul className="list-disc pl-6 space-y-2 mt-2">
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to be Informed:
                  </strong>{" "}
                  You have the right to be informed about the collection and
                  processing of your personal data, including the legal basis,
                  purpose, and means of collection.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Access:
                  </strong>{" "}
                  You have the right to request access to the personal data we
                  hold about you.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Correction:
                  </strong>{" "}
                  You have the right to request correction of inaccurate or
                  incomplete personal data.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Destruction:
                  </strong>{" "}
                  You have the right to request the destruction of your personal
                  data when it is no longer necessary for the purpose for which
                  it was collected.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Withdraw Consent:
                  </strong>{" "}
                  Where processing is based on consent, you may withdraw consent
                  at any time.
                </li>
              </ul>
              <p className="mt-4">
                To exercise your rights under the PDPL, contact us at{" "}
                <a
                  href="mailto:privacy@anticipy.ai"
                  className="text-gold hover:underline"
                >
                  privacy@anticipy.ai
                </a>
                . You also have the right to submit complaints to SDAIA.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                14.2 Sensitive Data
              </h3>
              <p>
                The PDPL restricts the processing of sensitive personal data,
                including health data, genetic data, biometric data, and data
                revealing racial or ethnic origin, religious or philosophical
                beliefs, or criminal records. Anticipy does not collect or
                process any categories of sensitive personal data as defined
                under the PDPL.
              </p>
            </section>

            {/* ───────────────────────────────────────────── 14 */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                15. UAE &amp; Middle East — UAE PDPL (Federal Decree-Law No. 45/2021)
              </h2>
              <p>
                If you are located in the United Arab Emirates, your personal
                data is processed in accordance with Federal Decree-Law No.
                45/2021 on the Protection of Personal Data (UAE PDPL), as
                administered by the UAE Data Office.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                15.1 Your Rights Under the UAE PDPL
              </h3>
              <ul className="list-disc pl-6 space-y-2 mt-2">
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Access:
                  </strong>{" "}
                  Request access to your personal data and information about how
                  it is processed.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Correction:
                  </strong>{" "}
                  Request correction or updating of inaccurate or outdated
                  personal data.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Erasure:
                  </strong>{" "}
                  Request deletion of personal data that is no longer necessary
                  for the purpose of processing.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Restrict Processing:
                  </strong>{" "}
                  Request limitation of the processing of your personal data in
                  certain circumstances.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Data Portability:
                  </strong>{" "}
                  Receive your personal data in a structured, commonly used
                  format and transmit it to another controller.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Object:
                  </strong>{" "}
                  Object to the processing of your personal data for direct
                  marketing purposes.
                </li>
              </ul>
              <p className="mt-4">
                Contact us at{" "}
                <a
                  href="mailto:privacy@anticipy.ai"
                  className="text-gold hover:underline"
                >
                  privacy@anticipy.ai
                </a>{" "}
                to exercise your rights. You may also lodge complaints with the
                UAE Data Office.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                15.2 Free Zone Considerations
              </h3>
              <p>
                If you are located in or access the Platform from a UAE free zone
                that has its own data protection regime (e.g., the Dubai
                International Financial Centre under DIFC Law No. 5 of 2020 or
                the Abu Dhabi Global Market under its Data Protection Regulations
                2021), the specific provisions of that regime may also apply. We
                endeavor to comply with the data protection requirements of all
                UAE free zones from which our users may access the Platform.
              </p>
            </section>

            {/* ───────────────────────────────────────────── 15 */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                16. Asia-Pacific — APPI, PIPA, PDPA, DPDP Act &amp; PIPL
              </h2>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                16.1 Japan — Act on Protection of Personal Information (APPI)
              </h3>
              <p>
                If you are located in Japan, your personal information is
                processed in accordance with the Act on Protection of Personal
                Information (APPI, Act No. 57 of 2003, as amended). Your rights
                include the right to request disclosure, correction, suspension
                of use, and deletion of your retained personal data. You may
                also request that we cease providing your personal data to third
                parties. To exercise your rights, contact us at{" "}
                <a
                  href="mailto:privacy@anticipy.ai"
                  className="text-gold hover:underline"
                >
                  privacy@anticipy.ai
                </a>
                . You may also file complaints with the Personal Information
                Protection Commission (PPC) of Japan.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                16.2 South Korea — Personal Information Protection Act (PIPA)
              </h3>
              <p>
                If you are located in South Korea, your personal information is
                processed in accordance with the Personal Information Protection
                Act (PIPA, Act No. 10465). Your rights include the right to
                access, correct, suspend processing of, and delete your personal
                information. We will respond to requests within 10 days as
                required by PIPA. You may contact us at{" "}
                <a
                  href="mailto:privacy@anticipy.ai"
                  className="text-gold hover:underline"
                >
                  privacy@anticipy.ai
                </a>{" "}
                or file complaints with the Personal Information Protection
                Commission (PIPC).
              </p>
              <p className="mt-4">
                In accordance with Article 15(2) of PIPA, we provide the
                following information: the purpose of processing, items of
                personal information processed, retention and use periods, and
                the fact that cross-border transfer may occur (see Section 9.4).
                We have designated a personal information protection officer who
                can be reached at the contact information provided in Section 20.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                16.3 Singapore — Personal Data Protection Act 2012 (PDPA)
              </h3>
              <p>
                If you are located in Singapore, your personal data is processed
                in accordance with the Personal Data Protection Act 2012 (PDPA).
                Your rights include the right to access and correct your personal
                data. You may withdraw consent for the collection, use, or
                disclosure of your personal data at any time by contacting us,
                though this may affect our ability to provide the Service to you.
                You may also file complaints with the Personal Data Protection
                Commission (PDPC) of Singapore.
              </p>
              <p className="mt-4">
                Under the PDPA&apos;s Do Not Call (DNC) provisions, we will not
                send marketing messages to Singapore telephone numbers registered
                on the DNC registry without clear and unambiguous consent.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                16.4 India — Digital Personal Data Protection Act 2023 (DPDP Act)
              </h3>
              <p>
                If you are located in India, your personal data is processed in
                accordance with the Digital Personal Data Protection Act 2023
                (DPDP Act). As a &ldquo;Data Fiduciary&rdquo; under the DPDP
                Act, we process your personal data only for lawful purposes with
                your consent or for certain legitimate uses as specified in the
                Act. Your rights under the DPDP Act include:
              </p>
              <ul className="list-disc pl-6 space-y-2 mt-2">
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Access:
                  </strong>{" "}
                  Request a summary of your personal data being processed and
                  the processing activities undertaken.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Correction and Erasure:
                  </strong>{" "}
                  Request correction of inaccurate or misleading personal data,
                  completion of incomplete data, updating of personal data, and
                  erasure of personal data that is no longer necessary for the
                  purpose for which it was processed.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Grievance Redressal:
                  </strong>{" "}
                  You may contact our designated Grievance Officer for any
                  concerns regarding data processing (see Section 20).
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Nominate:
                  </strong>{" "}
                  You may nominate an individual to exercise your rights in the
                  event of your death or incapacity.
                </li>
              </ul>
              <p className="mt-4">
                You may exercise your rights by contacting us at{" "}
                <a
                  href="mailto:privacy@anticipy.ai"
                  className="text-gold hover:underline"
                >
                  privacy@anticipy.ai
                </a>
                . You may also file complaints with the Data Protection Board of
                India, once established and operational.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                16.5 China — Personal Information Protection Law (PIPL)
              </h3>
              <p>
                If you are located in the People&apos;s Republic of China, your
                personal information is processed in accordance with the Personal
                Information Protection Law (PIPL, effective November 1, 2021).
                Your rights under the PIPL include:
              </p>
              <ul className="list-disc pl-6 space-y-2 mt-2">
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Know and Decide:
                  </strong>{" "}
                  You have the right to know about and make decisions regarding
                  the processing of your personal information, and the right to
                  restrict or refuse processing.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Access and Copy:
                  </strong>{" "}
                  You have the right to access and obtain copies of your
                  personal information from us.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Transfer:
                  </strong>{" "}
                  You have the right to request the transfer of your personal
                  information to another handler under conditions specified by
                  the CAC.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Correction and Completion:
                  </strong>{" "}
                  You have the right to request correction or completion of
                  inaccurate or incomplete personal information.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Deletion:
                  </strong>{" "}
                  You have the right to request deletion of your personal
                  information where the processing purpose has been achieved, the
                  retention period has expired, consent has been withdrawn, or
                  processing violates applicable law.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Right to Explanation:
                  </strong>{" "}
                  You have the right to request an explanation of our processing
                  rules.
                </li>
              </ul>
              <p className="mt-4">
                For cross-border transfers involving personal information of PRC
                residents, we conduct a personal information protection impact
                assessment as required by Article 55 of the PIPL and comply with
                the cross-border transfer requirements set forth in Articles 38
                through 43, including (where applicable) passing the CAC
                security assessment, obtaining certification from an accredited
                professional institution, or entering into a standard contract
                as promulgated by the CAC.
              </p>
            </section>

            {/* ───────────────────────────────────────────── 16 */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                17. Data Security
              </h2>
              <p>
                We implement commercially reasonable administrative, technical,
                and physical safeguards to protect personal information from
                unauthorized access, disclosure, alteration, and destruction.
                These measures include but are not limited to:
              </p>
              <ul className="list-disc pl-6 space-y-2 mt-4">
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Encryption in Transit:
                  </strong>{" "}
                  All data transmitted between the Device and smartphone uses
                  AES-CCM encryption via BLE 5.3. All data transmitted between
                  the App and our cloud services uses TLS 1.3 encryption.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Encryption at Rest:
                  </strong>{" "}
                  All personal information stored on our servers is encrypted at
                  rest using AES-256 encryption.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Access Controls:
                  </strong>{" "}
                  We enforce role-based access controls (RBAC) and the principle
                  of least privilege for all personnel who handle personal
                  information.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Infrastructure Security:
                  </strong>{" "}
                  Our cloud infrastructure is hosted in SOC 2 Type II certified
                  data centers with physical security controls, intrusion
                  detection systems, and continuous monitoring.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Incident Response:
                  </strong>{" "}
                  We maintain a documented incident response plan and will notify
                  affected individuals and relevant supervisory authorities of
                  data breaches in accordance with applicable law, including
                  within 72 hours under GDPR Article 33, within the timeframe
                  prescribed by BC PIPA, and as required under the PDPL, UAE
                  PDPL, PIPL, and other applicable regimes.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Employee Training:
                  </strong>{" "}
                  All personnel with access to personal information receive
                  regular privacy and security training.
                </li>
              </ul>
              <p className="mt-4">
                While we take extensive measures to protect your personal
                information, no method of transmission over the Internet or
                electronic storage is 100% secure. We cannot guarantee absolute
                security but are committed to promptly addressing any security
                incidents in accordance with our incident response procedures.
              </p>
            </section>

            {/* ───────────────────────────────────────────── 17 */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                18. Cookie Policy
              </h2>
              <p>
                Our Site uses a minimal number of cookies and similar
                technologies. We do not use advertising cookies, tracking pixels
                for third-party advertisers, or cross-site tracking technologies.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                18.1 Cookies We Use
              </h3>
              <ul className="list-disc pl-6 space-y-2 mt-2">
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Strictly Necessary Cookies:
                  </strong>{" "}
                  These are essential for the Site to function and cannot be
                  switched off. They include session cookies for authentication,
                  security tokens (CSRF), and cookies necessary to remember your
                  cookie consent preferences. Legal basis: Legitimate interest /
                  not requiring consent under ePrivacy Directive Art. 5(3).
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Functional Cookies:
                  </strong>{" "}
                  These remember your preferences (such as language or region
                  settings) to provide a more personalized experience. These
                  cookies do not track you across third-party websites. Legal
                  basis: Consent (for EU/UK visitors) or legitimate interest.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Analytics Cookies:
                  </strong>{" "}
                  We may use privacy-focused analytics services to understand how
                  visitors interact with our Site. These analytics do not create
                  individual profiles, do not share data with third-party
                  advertisers, and process data in a manner compliant with GDPR,
                  UK GDPR, and other applicable privacy laws. Legal basis:
                  Consent (for EU/UK visitors).
                </li>
              </ul>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                18.2 Cookies We Do NOT Use
              </h3>
              <ul className="list-disc pl-6 space-y-2 mt-2">
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Advertising or Marketing Cookies:
                  </strong>{" "}
                  We do not place advertising cookies and do not participate in
                  ad networks or real-time bidding platforms.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Third-Party Tracking:
                  </strong>{" "}
                  We do not embed third-party tracking pixels, social media
                  widgets that set tracking cookies, or any technology designed
                  to follow users across the web.
                </li>
              </ul>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                18.3 Managing Cookies
              </h3>
              <p>
                You can manage cookie preferences through your browser settings.
                Most browsers allow you to refuse cookies, delete existing
                cookies, or be notified when a cookie is set. Please note that
                disabling strictly necessary cookies may impair the functionality
                of the Site. For EU and UK visitors, we provide a cookie consent
                banner upon your first visit, allowing you to accept or reject
                non-essential cookies in accordance with the ePrivacy Directive
                and PECR.
              </p>
            </section>

            {/* ───────────────────────────────────────────── 18 */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                19. Children&apos;s Privacy
              </h2>
              <p>
                The Platform is intended solely for users who are{" "}
                <strong className="text-[var(--text-on-dark)]">
                  18 years of age or older
                </strong>
                . We do not knowingly collect, use, or disclose personal
                information from individuals under the age of 18. This age
                restriction applies globally and satisfies the requirements of:
              </p>
              <ul className="list-disc pl-6 space-y-2 mt-4">
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    United States:
                  </strong>{" "}
                  The Children&apos;s Online Privacy Protection Act (COPPA, 15
                  U.S.C. &sect;&sect;6501&ndash;6506) prohibits the collection
                  of personal information from children under 13 without
                  verifiable parental consent. Our 18+ age restriction exceeds
                  this requirement.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    European Union &amp; United Kingdom:
                  </strong>{" "}
                  The GDPR (Art. 8) and UK GDPR require parental consent for
                  information society services offered to children under 16 (or
                  a lower age as set by member states, but not below 13). Our
                  18+ age restriction exceeds this requirement. We also comply
                  with the UK Age-Appropriate Design Code (Children&apos;s Code)
                  by not offering our services to children.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Canada:
                  </strong>{" "}
                  PIPEDA and BC PIPA require meaningful consent for the
                  collection of personal information from minors. Our 18+ age
                  restriction ensures we do not collect data from minors.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Saudi Arabia &amp; UAE:
                  </strong>{" "}
                  The PDPL and UAE PDPL provide enhanced protections for minors.
                  Our 18+ restriction ensures compliance.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    China:
                  </strong>{" "}
                  The PIPL (Art. 28) classifies personal information of minors
                  under 14 as sensitive personal information. Our 18+ age
                  restriction exceeds this threshold.
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    South Korea:
                  </strong>{" "}
                  PIPA requires consent from a legal representative for the
                  collection of personal information from individuals under 14.
                  Our 18+ restriction exceeds this requirement.
                </li>
              </ul>
              <p className="mt-4">
                If we discover that we have inadvertently collected personal
                information from an individual under 18, we will promptly delete
                that information and terminate the associated account. If you
                believe that we have collected personal information from a minor,
                please contact us immediately at{" "}
                <a
                  href="mailto:privacy@anticipy.ai"
                  className="text-gold hover:underline"
                >
                  privacy@anticipy.ai
                </a>
                .
              </p>
            </section>

            {/* ───────────────────────────────────────────── 19 */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                20. Your Rights — Summary by Jurisdiction
              </h2>
              <p>
                The following table summarizes your key privacy rights depending
                on your location. For detailed information, refer to the
                jurisdiction-specific sections of this Policy.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                20.1 Access to Your Data
              </h3>
              <p>
                All jurisdictions: You may request access to the personal
                information we hold about you. Contact{" "}
                <a
                  href="mailto:privacy@anticipy.ai"
                  className="text-gold hover:underline"
                >
                  privacy@anticipy.ai
                </a>
                .
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                20.2 Correction / Rectification
              </h3>
              <p>
                All jurisdictions: You may request correction of inaccurate
                personal information.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                20.3 Deletion / Erasure / Destruction
              </h3>
              <p>
                Available under: GDPR (Art. 17), UK GDPR, CCPA/CPRA, PIPEDA,
                BC PIPA, PDPL (Saudi Arabia), UAE PDPL, PIPL, APPI, PIPA
                (South Korea), PDPA (Singapore — via withdrawal of consent),
                and DPDP Act (India).
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                20.4 Data Portability
              </h3>
              <p>
                Available under: GDPR (Art. 20), UK GDPR, CCPA/CPRA, UAE PDPL,
                PIPL, and DPDP Act (India).
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                20.5 Restriction / Limitation of Processing
              </h3>
              <p>
                Available under: GDPR (Art. 18), UK GDPR, UAE PDPL, and PIPL.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                20.6 Objection to Processing
              </h3>
              <p>
                Available under: GDPR (Art. 21), UK GDPR, UAE PDPL, and PIPL.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                20.7 Withdrawal of Consent
              </h3>
              <p>
                All jurisdictions: Where processing is based on consent, you may
                withdraw your consent at any time. Withdrawal of consent does
                not affect the lawfulness of processing carried out prior to
                withdrawal.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                20.8 Opt-Out of Sale / Sharing
              </h3>
              <p>
                CCPA/CPRA and applicable U.S. state laws: We do not sell or share
                personal information for cross-context behavioral advertising.
                No opt-out action is required.
              </p>

              <h3 className="font-serif text-[18px] text-[var(--text-on-dark)] mb-2 mt-6">
                20.9 Complaint to Supervisory Authority
              </h3>
              <p>
                You may lodge a complaint with the relevant supervisory authority
                in your jurisdiction, including but not limited to: the Office
                of the Privacy Commissioner of Canada (OPC); the BC Office of
                the Information &amp; Privacy Commissioner (OIPC); the
                California Attorney General; the European Data Protection Board
                (EDPB) or relevant national supervisory authority; the UK
                Information Commissioner&apos;s Office (ICO); SDAIA (Saudi Arabia);
                the UAE Data Office; the Japanese PPC; the Korean PIPC; the
                Singapore PDPC; the Data Protection Board of India; or the
                Cyberspace Administration of China (CAC).
              </p>
            </section>

            {/* ───────────────────────────────────────────── 20 */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                21. Third-Party Links &amp; Services
              </h2>
              <p>
                The Platform may contain links to third-party websites, services,
                or applications. This Policy does not apply to any third-party
                services, and we are not responsible for the privacy practices
                of any third party. We encourage you to review the privacy
                policies of any third-party services you access through the
                Platform.
              </p>
            </section>

            {/* ───────────────────────────────────────────── 21 */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                22. Changes to This Policy
              </h2>
              <p>
                We may update this Policy from time to time to reflect changes
                in our practices, technologies, legal requirements, or other
                factors. When we make material changes, we will:
              </p>
              <ul className="list-disc pl-6 space-y-2 mt-4">
                <li>
                  Update the &ldquo;Last updated&rdquo; date at the top of this
                  Policy.
                </li>
                <li>
                  Provide prominent notice on our Site or through the App (e.g.,
                  a banner or push notification).
                </li>
                <li>
                  Where required by applicable law (including GDPR, PIPEDA, and
                  PDPL), obtain your consent to material changes that affect the
                  processing of your personal information.
                </li>
                <li>
                  Send an email notification to registered users for changes that
                  materially alter the scope of personal information processing
                  or the introduction of new categories of processing.
                </li>
              </ul>
              <p className="mt-4">
                Your continued use of the Platform after the effective date of
                any updated Policy constitutes your acceptance of the revised
                terms, to the extent permitted by applicable law. Where consent
                is required, we will not rely on continued use as a substitute
                for affirmative consent.
              </p>
            </section>

            {/* ───────────────────────────────────────────── 22 */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                23. Governing Law &amp; Dispute Resolution
              </h2>
              <p>
                This Policy is governed by and construed in accordance with the
                laws of the jurisdiction in which Anticipation Labs Inc. is
                incorporated, without regard to conflict of law principles.
                Any dispute arising out of or in connection with this Policy
                shall be subject to the exclusive jurisdiction of the courts in
                that jurisdiction, except where applicable privacy law provides
                otherwise (e.g., GDPR data subjects may bring proceedings in the
                member state of their habitual residence).
              </p>
              <p className="mt-4">
                Nothing in this Policy limits your rights under mandatory
                applicable data protection laws. Where this Policy conflicts
                with mandatory local law, the mandatory local law shall prevail
                to the extent of the conflict.
              </p>
            </section>

            {/* ───────────────────────────────────────────── 23 */}
            <section>
              <h2 className="font-serif text-[22px] text-[var(--text-on-dark)] mb-4">
                24. Contact Us
              </h2>
              <p>
                If you have any questions, concerns, or requests regarding this
                Privacy Policy or the processing of your personal information,
                please contact us:
              </p>
              <ul className="list-none pl-0 space-y-2 mt-4">
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Privacy Inquiries:
                  </strong>{" "}
                  <a
                    href="mailto:privacy@anticipy.ai"
                    className="text-gold hover:underline"
                  >
                    privacy@anticipy.ai
                  </a>
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    General Inquiries:
                  </strong>{" "}
                  <a
                    href="mailto:omar@anticipy.ai"
                    className="text-gold hover:underline"
                  >
                    omar@anticipy.ai
                  </a>
                </li>
                <li>
                  <strong className="text-[var(--text-on-dark)]">
                    Company:
                  </strong>
                  <br />
                  Anticipation Labs Inc.
                </li>
              </ul>
              <p className="mt-6">
                For GDPR, UK GDPR, and ePrivacy Directive inquiries, our
                designated privacy lead can be reached at{" "}
                <a
                  href="mailto:privacy@anticipy.ai"
                  className="text-gold hover:underline"
                >
                  privacy@anticipy.ai
                </a>
                .
              </p>
              <p className="mt-4">
                For DPDP Act (India) inquiries, our designated Grievance Officer
                can be reached at{" "}
                <a
                  href="mailto:privacy@anticipy.ai"
                  className="text-gold hover:underline"
                >
                  privacy@anticipy.ai
                </a>
                .
              </p>
              <p className="mt-4">
                For PIPL (China) inquiries, our designated personal information
                protection responsible person can be reached at{" "}
                <a
                  href="mailto:privacy@anticipy.ai"
                  className="text-gold hover:underline"
                >
                  privacy@anticipy.ai
                </a>
                .
              </p>
              <p className="mt-4">
                For PIPA (South Korea) inquiries, our designated personal
                information protection officer can be reached at{" "}
                <a
                  href="mailto:privacy@anticipy.ai"
                  className="text-gold hover:underline"
                >
                  privacy@anticipy.ai
                </a>
                .
              </p>
            </section>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer
        className="px-6 py-10 border-t"
        style={{ borderColor: "var(--dark-border)" }}
      >
        <div className="max-w-3xl mx-auto flex flex-col sm:flex-row justify-between items-center gap-4">
          <p className="text-[13px] text-[var(--text-on-dark-muted)]">
            &copy; 2026 Anticipation Labs Inc. All rights reserved.
          </p>
          <nav className="flex gap-4">
            <Link
              href="/terms"
              className="text-[13px] text-[var(--text-on-dark-muted)] hover:text-gold transition-colors"
            >
              Terms of Service
            </Link>
            <Link
              href="/refund"
              className="text-[13px] text-[var(--text-on-dark-muted)] hover:text-gold transition-colors"
            >
              Refund Policy
            </Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
