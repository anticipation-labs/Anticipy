import Link from "next/link";

export default function CompetitivePage() {
  return (
    <div className="min-h-screen" style={{ background: "#0C0C0C", color: "#F5F0EB" }}>
      <div className="max-w-4xl mx-auto px-4 py-8">

        <Link href="/internal" className="inline-flex items-center gap-2 text-sm mb-8 hover:opacity-80 transition-opacity" style={{ color: "#8A8A8A" }}>
          ← Internal Dashboard
        </Link>

        <div className="mb-10">
          <div className="flex items-center gap-3 mb-3">
            <span style={{ color: "#C8A97E" }}>◎</span>
            <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: "rgba(200,169,126,0.15)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.3)" }}>Research</span>
          </div>
          <h1 className="text-3xl font-semibold tracking-tight mb-2">Competitive Market Analysis</h1>
          <p style={{ color: "#8A8A8A" }}>April 2026 — Sources: TechCrunch, CNBC, Grand View Research, Fortune</p>
        </div>

        {/* Market size */}
        <section className="mb-10">
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: "Market size 2025", value: "$43.64B", sub: "AI wearables globally" },
              { label: "Market size 2033", value: "$310B+", sub: "projected" },
              { label: "CAGR", value: "27.8%", sub: "2025–2033" },
            ].map((s) => (
              <div key={s.label} className="p-5 rounded-xl text-center" style={{ background: "#161616", border: "1px solid #252525" }}>
                <div className="text-2xl font-bold mb-1" style={{ color: "#C8A97E" }}>{s.value}</div>
                <div className="text-xs font-medium mb-1" style={{ color: "#F5F0EB" }}>{s.label}</div>
                <div className="text-xs" style={{ color: "#5A5A5A" }}>{s.sub}</div>
              </div>
            ))}
          </div>
        </section>

        {/* Competitors */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-6" style={{ color: "#C8A97E" }}>Competitor Analysis — All 8</h2>
          <div className="space-y-4">

            {/* Humane AI Pin */}
            <div className="p-5 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
              <div className="flex items-start justify-between gap-4 mb-3">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold" style={{ color: "#F5F0EB" }}>Humane AI Pin</span>
                    <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{ background: "rgba(239,68,68,0.15)", color: "#ef4444", border: "1px solid rgba(239,68,68,0.3)" }}>DEAD</span>
                  </div>
                  <div className="text-xs" style={{ color: "#5A5A5A" }}>HP acquired Feb 2025 for $116M in assets</div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-medium" style={{ color: "#C8A97E" }}>$699</div>
                  <div className="text-xs" style={{ color: "#5A5A5A" }}>+ $24/mo</div>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="text-xs font-medium mb-1" style={{ color: "#8A8A8A" }}>What happened</div>
                  <p className="text-xs leading-relaxed" style={{ color: "#A0A0A0" }}>
                    Only ~10,000 units shipped. Returns exceeded sales within weeks of launch. Projector UI was laggy and impractical.
                    High price + buggy execution = catastrophic failure. HP acquired the assets at bankruptcy prices.
                  </p>
                </div>
                <div>
                  <div className="text-xs font-medium mb-1" style={{ color: "#8A8A8A" }}>Lesson for Anticipy</div>
                  <p className="text-xs leading-relaxed" style={{ color: "#A0A0A0" }}>
                    Never ship before the product works. High price raises expectations astronomically.
                    A projector on your chest is a party trick, not a product. Anticipy: no projector, no screen, no gimmick.
                  </p>
                </div>
              </div>
            </div>

            {/* Rabbit R1 */}
            <div className="p-5 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
              <div className="flex items-start justify-between gap-4 mb-3">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold" style={{ color: "#F5F0EB" }}>Rabbit R1</span>
                    <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{ background: "rgba(234,179,8,0.15)", color: "#eab308", border: "1px solid rgba(234,179,8,0.3)" }}>RECOVERING</span>
                  </div>
                  <div className="text-xs" style={{ color: "#5A5A5A" }}>Standalone AI device; Rabbit OS 2 released Q1 2026</div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-medium" style={{ color: "#C8A97E" }}>$199</div>
                  <div className="text-xs" style={{ color: "#5A5A5A" }}>one-time</div>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="text-xs font-medium mb-1" style={{ color: "#8A8A8A" }}>Status</div>
                  <p className="text-xs leading-relaxed" style={{ color: "#A0A0A0" }}>
                    50,000+ units sold. RabbitOS 2.0 dramatically improved reliability and response speed.
                    Still requires carrying a separate device. LAM (Large Action Model) is improving but slow.
                  </p>
                </div>
                <div>
                  <div className="text-xs font-medium mb-1" style={{ color: "#8A8A8A" }}>Lesson for Anticipy</div>
                  <p className="text-xs leading-relaxed" style={{ color: "#A0A0A0" }}>
                    Iterate fast + low price = survival. Users forgive bugs if you ship fixes.
                    But nobody wants to carry a third device — Anticipy is a pendant, no new form factor burden.
                  </p>
                </div>
              </div>
            </div>

            {/* Meta Ray-Ban */}
            <div className="p-5 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
              <div className="flex items-start justify-between gap-4 mb-3">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold" style={{ color: "#F5F0EB" }}>Meta Ray-Ban Smart Glasses</span>
                    <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{ background: "rgba(34,197,94,0.15)", color: "#22c55e", border: "1px solid rgba(34,197,94,0.3)" }}>MARKET LEADER</span>
                  </div>
                  <div className="text-xs" style={{ color: "#5A5A5A" }}>7M+ units shipped in 2025, 3× YoY growth</div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-medium" style={{ color: "#C8A97E" }}>$299–$799</div>
                  <div className="text-xs" style={{ color: "#5A5A5A" }}>40%+ market share</div>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="text-xs font-medium mb-1" style={{ color: "#8A8A8A" }}>Why winning</div>
                  <p className="text-xs leading-relaxed" style={{ color: "#A0A0A0" }}>
                    Form factor is familiar (glasses). Camera + Meta AI integration. Works as actual glasses.
                    Meta&apos;s distribution, marketing, and brand. Not primarily a &quot;AI assistant&quot; device — it&apos;s glasses that also do AI.
                  </p>
                </div>
                <div>
                  <div className="text-xs font-medium mb-1" style={{ color: "#8A8A8A" }}>Anticipy positioning</div>
                  <p className="text-xs leading-relaxed" style={{ color: "#A0A0A0" }}>
                    Orthogonal category — audio vs visual. Meta Ray-Ban is for seeing; Anticipy is for doing.
                    No overlap in use case. Not a competitor — different workflow. Glasses users may also wear Anticipy.
                  </p>
                </div>
              </div>
            </div>

            {/* Plaud NotePin */}
            <div className="p-5 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
              <div className="flex items-start justify-between gap-4 mb-3">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold" style={{ color: "#F5F0EB" }}>Plaud NotePin</span>
                    <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{ background: "rgba(59,130,246,0.15)", color: "#3b82f6", border: "1px solid rgba(59,130,246,0.3)" }}>ACTIVE (NICHE)</span>
                  </div>
                  <div className="text-xs" style={{ color: "#5A5A5A" }}>HIPAA-compliant transcription for professionals</div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-medium" style={{ color: "#C8A97E" }}>$159</div>
                  <div className="text-xs" style={{ color: "#5A5A5A" }}>+ $8/mo Pro</div>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="text-xs font-medium mb-1" style={{ color: "#8A8A8A" }}>What it does</div>
                  <p className="text-xs leading-relaxed" style={{ color: "#A0A0A0" }}>
                    Magnetic clip that attaches to your phone. Records meetings + conversations.
                    Produces HIPAA-compliant transcripts for doctors, lawyers, therapists.
                    Smart summaries. No autonomous task execution whatsoever.
                  </p>
                </div>
                <div>
                  <div className="text-xs font-medium mb-1" style={{ color: "#8A8A8A" }}>Anticipy advantage</div>
                  <p className="text-xs leading-relaxed" style={{ color: "#A0A0A0" }}>
                    Plaud transcribes. Anticipy acts. If you say &quot;book a meeting with Sarah for Thursday&quot;,
                    Plaud gives you a transcript. Anticipy books the meeting.
                    That&apos;s a fundamentally different value proposition.
                  </p>
                </div>
              </div>
            </div>

            {/* Limitless Pendant */}
            <div className="p-5 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
              <div className="flex items-start justify-between gap-4 mb-3">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold" style={{ color: "#F5F0EB" }}>Limitless Pendant</span>
                    <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{ background: "rgba(239,68,68,0.15)", color: "#ef4444", border: "1px solid rgba(239,68,68,0.3)" }}>ACQUIRED</span>
                  </div>
                  <div className="text-xs" style={{ color: "#5A5A5A" }}>Meta acquired December 2025</div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-medium" style={{ color: "#C8A97E" }}>$99</div>
                  <div className="text-xs" style={{ color: "#5A5A5A" }}>~5,000 units shipped</div>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="text-xs font-medium mb-1" style={{ color: "#8A8A8A" }}>What happened</div>
                  <p className="text-xs leading-relaxed" style={{ color: "#A0A0A0" }}>
                    Raised $8M, shipped ~5K pendant wearables. Good form factor, decent UX.
                    Meta saw strategic value in the AI wearable space and acquired it as a defensive play
                    against Apple&apos;s rumored AI wearable.
                  </p>
                </div>
                <div>
                  <div className="text-xs font-medium mb-1" style={{ color: "#8A8A8A" }}>Lesson for Anticipy</div>
                  <p className="text-xs leading-relaxed" style={{ color: "#A0A0A0" }}>
                    Indie players in AI wearables are acquisition targets. This is an exit path.
                    Build something that would embarrass a big company not to own.
                    At $149–$299, you don&apos;t need to beat Meta — you need to be worth buying.
                  </p>
                </div>
              </div>
            </div>

            {/* Friend */}
            <div className="p-5 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
              <div className="flex items-start justify-between gap-4 mb-3">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold" style={{ color: "#F5F0EB" }}>Friend (Avi Schiffmann)</span>
                    <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{ background: "rgba(239,68,68,0.15)", color: "#ef4444", border: "1px solid rgba(239,68,68,0.3)" }}>BACKLASH</span>
                  </div>
                  <div className="text-xs" style={{ color: "#5A5A5A" }}>Museum of Failure. Always-listening AI companion pendant.</div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-medium" style={{ color: "#C8A97E" }}>$129</div>
                  <div className="text-xs" style={{ color: "#5A5A5A" }}>preorder + $4/mo</div>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="text-xs font-medium mb-1" style={{ color: "#8A8A8A" }}>What went wrong</div>
                  <p className="text-xs leading-relaxed" style={{ color: "#A0A0A0" }}>
                    Promoted as an &quot;AI friend&quot; that listens to you all day.
                    Massive privacy backlash — people don&apos;t want an always-on AI companion watching them.
                    Zero utility value beyond emotional companionship. Branded as dystopian.
                  </p>
                </div>
                <div>
                  <div className="text-xs font-medium mb-1" style={{ color: "#8A8A8A" }}>Lesson for Anticipy</div>
                  <p className="text-xs leading-relaxed" style={{ color: "#A0A0A0" }}>
                    Always-listening = reputational disaster without clear value. Anticipy: on-device VAD
                    never sends audio until speech is detected. Utility-first positioning —
                    &quot;it does your tasks&quot; not &quot;it&apos;s your friend&quot;. Publish privacy policy before launch.
                  </p>
                </div>
              </div>
            </div>

            {/* Bee AI */}
            <div className="p-5 rounded-xl" style={{ background: "#161616", border: "2px solid rgba(200,169,126,0.3)" }}>
              <div className="flex items-start justify-between gap-4 mb-3">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold" style={{ color: "#F5F0EB" }}>Bee AI</span>
                    <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{ background: "rgba(200,169,126,0.15)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.4)" }}>CLOSEST COMPETITOR</span>
                    <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{ background: "rgba(59,130,246,0.15)", color: "#3b82f6", border: "1px solid rgba(59,130,246,0.3)" }}>AMAZON ACQUIRED Jan 2026</span>
                  </div>
                  <div className="text-xs" style={{ color: "#5A5A5A" }}>AI pendant that automates email and calendar tasks</div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-medium" style={{ color: "#C8A97E" }}>$49.99</div>
                  <div className="text-xs" style={{ color: "#5A5A5A" }}>+ $19/mo</div>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="text-xs font-medium mb-1" style={{ color: "#8A8A8A" }}>What it does</div>
                  <p className="text-xs leading-relaxed" style={{ color: "#A0A0A0" }}>
                    Records ambient conversation. Integrates with Gmail, Google Calendar, Outlook.
                    Can draft emails, schedule meetings, set reminders. Amazon acquired it for
                    integration with Alexa ecosystem in January 2026.
                  </p>
                </div>
                <div>
                  <div className="text-xs font-medium mb-1" style={{ color: "#8A8A8A" }}>Anticipy critical advantage</div>
                  <p className="text-xs leading-relaxed" style={{ color: "#A0A0A0" }}>
                    <strong className="font-semibold" style={{ color: "#F5F0EB" }}>Bee does email + calendar. Anticipy does any web task via browser agent.</strong>{" "}
                    Book a flight. Order dinner. Fill a form. Apply for a job. No API integration needed —
                    Anticipy operates the browser directly, like a human would.
                  </p>
                </div>
              </div>
            </div>

            {/* OM1 */}
            <div className="p-5 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
              <div className="flex items-start justify-between gap-4 mb-3">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold" style={{ color: "#F5F0EB" }}>OM1 / ResMed Health AI</span>
                    <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{ background: "rgba(59,130,246,0.15)", color: "#3b82f6", border: "1px solid rgba(59,130,246,0.3)" }}>ACTIVE (B2B)</span>
                  </div>
                  <div className="text-xs" style={{ color: "#5A5A5A" }}>Enterprise health AI wearables for clinical settings</div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-medium" style={{ color: "#C8A97E" }}>Enterprise</div>
                  <div className="text-xs" style={{ color: "#5A5A5A" }}>B2B only</div>
                </div>
              </div>
              <div className="text-xs leading-relaxed" style={{ color: "#A0A0A0" }}>
                Not a direct competitor — different market (healthcare enterprise), different use case (clinical documentation),
                different buyer (hospital procurement). Validates that the &quot;ambient audio → AI action&quot; concept
                has institutional buyers. Anticipy targets consumer + SMB.
              </div>
            </div>

          </div>
        </section>

        {/* Anticipy differentiation */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Anticipy Differentiation</h2>
          <div className="grid grid-cols-2 gap-4">
            {[
              {
                title: "1. Autonomous browser execution",
                body: "Any web task, not just transcription. Bee AI does email/calendar via API. Anticipy operates any website via browser agent — no integration required. Book flights, fill forms, order food, apply for jobs.",
              },
              {
                title: "2. Under $100 hardware",
                body: "~$77 CAD BOM for a single prototype. 1,000-unit production target: ~$26 CAD. Competitors charge $99–$799. Anticipy can retail at $149–$299 with healthy margins.",
              },
              {
                title: "3. Privacy-first architecture",
                body: "On-device Voice Activity Detection (VAD) — audio never leaves the device until speech is detected. No always-on streaming. Local VAD means zero data transmitted in silence. Directly addresses Friend/Bee backlash.",
              },
              {
                title: "4. Learns from failures",
                body: "Humane: high price + bad UX. Friend: creepy positioning. Limitless: acquired. Bee: API-limited. Rabbit: carries a new device. Anticipy: low price, pendant form, browser-native, utility-first, wear what you already wear.",
              },
            ].map((d) => (
              <div key={d.title} className="p-5 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
                <div className="font-semibold text-sm mb-2" style={{ color: "#F5F0EB" }}>{d.title}</div>
                <p className="text-xs leading-relaxed" style={{ color: "#A0A0A0" }}>{d.body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Recommendations */}
        <section>
          <h2 className="text-lg font-semibold mb-4" style={{ color: "#C8A97E" }}>Recommendations</h2>
          <div className="space-y-3">
            {[
              { n: "1", title: "Position: \"Listens. Understands. Does.\"", body: "Contrast with transcription-only competitors. The word \"does\" is the differentiator. Marketing should show actual web tasks completing in real-time, not abstract AI bubbles." },
              { n: "2", title: "Start B2B before consumer", body: "Enterprise buyers (HR teams, recruiters, ops managers) will pay $299/device + $49/mo for autonomous web tasks. Lower CAC, longer LTV, lower support burden. Build case studies before consumer launch." },
              { n: "3", title: "Price at $149–$299 consumer", body: "Below Plaud ($159) and Humane ($699). Above Bee ($49.99) — justifiable because Anticipy does more. At $199 with $19/mo you match Rabbit R1 pricing at 3× the utility." },
              { n: "4", title: "Publish privacy policy before launch", body: "Friend and Bee had massive backlash around always-on recording. Publish a clear, plain-English privacy policy before any press. Explain on-device VAD, what data is sent, retention policy. This is a competitive advantage if done right." },
            ].map((r) => (
              <div key={r.n} className="flex gap-4 p-5 rounded-xl" style={{ background: "#161616", border: "1px solid #252525" }}>
                <div className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold" style={{ background: "rgba(200,169,126,0.15)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.3)" }}>{r.n}</div>
                <div>
                  <div className="font-semibold text-sm mb-1" style={{ color: "#F5F0EB" }}>{r.title}</div>
                  <p className="text-xs leading-relaxed" style={{ color: "#A0A0A0" }}>{r.body}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

      </div>
    </div>
  );
}
