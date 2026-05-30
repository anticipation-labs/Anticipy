# Competitive landscape, May 2026

Reference scan for Anticipy. Reads adjacent products (ambient capture pendants, meeting-notes tools, Office co-pilots, browser agents) and pulls out what each one solved, what each one botched, and what's still wide open. Written to be useful, not flattering. If a competitor is doing something right, it's marked right.

## Contents

1. [Limitless](#1-limitless-pendant--mac-app)
2. [Friend](#2-friend-companion-pendant)
3. [Plaud](#3-plaud-notepin-and-note-pro)
4. [Bee Computer (Pioneer)](#4-bee-computer-pioneer)
5. [Granola](#5-granola-mac-meeting-notepad)
6. [Cogram](#6-cogram-aec-meeting-notes--field-reports)
7. [Microsoft Copilot](#7-microsoft-copilot)
8. [Notion AI](#8-notion-ai-agents-and-meeting-notes)
9. [Rabbit R1](#9-rabbit-r1)
10. [Humane AI Pin](#10-humane-ai-pin)
11. [Adept ACT-1](#11-adept-act-1)
12. [Multion (now AGI Inc.)](#12-multion-now-agi-inc)
13. [Synthesis: what's solved, what's still open](#synthesis-whats-solved-whats-still-open)

---

## 1. Limitless (pendant + Mac app)

### What they shipped
A quarter-sized magnetic clip pendant (designed by the Beats team) that ambient-captures audio all day, syncs over Bluetooth to phone, transcribes via cloud, and surfaces "lifelogs" (summaries, action items, searchable timeline) in iOS, Android, macOS, Windows, and web apps. Originally launched at a $99 early-bird, later $399 retail. Five-year run as Scribe → Rewind (Mac always-on screen+audio capture) → Limitless. Raised $33M from a16z, Sam Altman, First Round. Pendant battery roughly 8-14 hours real-world ambient recording (100 hours of pure standby was the marketing number). Calendar integration auto-linked sessions to Zoom/Meet/Teams meetings. The Rewind desktop product kept on-device storage and Apple Silicon inference, which was a real privacy differentiator.

### Cold-start
Speaker diarization "got markedly better after a few weeks of regular use." Voice fingerprint on the wearer requires ~90 seconds of speech before recognition turns on. Person profiles (who Sarah is) are bootstrapped from calendar invites for virtual meetings; for in-person, the system labels strangers as "Unknown" until you manually attach a name. There is no fast onboarding. The product becomes useful after roughly two weeks.

### User feedback
- 92-95% transcription accuracy in clean rooms, noticeably worse in open offices and crowded restaurants.
- Speaker diarization "frequently misattributes in crowded group settings."
- Reddit threads (r/LimitlessAI) describe a recurring "Paperweight Fear" where users worry their hardware will be abandoned. That fear is now realized.
- BecomeFluent's May 2026 field guide: "The Reddit threads have the specific energy of a band breakup. The fans are pretending they're fine."
- Consent friction: people in the room have no audible indication they're being recorded. The "Consent Mode" feature that listens for unknown voices and requests verbal permission is still on the roadmap.

### Right
- Single small device captures both in-person and virtual meetings. Otter.ai cannot do in-person; Limitless's scope was a real advantage.
- Clean cross-platform app surface (iOS, Android, Mac, Windows, web).
- Privacy posture pre-acquisition was unusually careful (encrypted cloud, no-train, easy export, easy delete).
- Calendar auto-linking made meeting recall feel native.
- Acquisition exit was handled cleanly: existing users moved to free Unlimited tier, data export prioritized, 1+ year of continued support promised.

### Wrong
- Bet the company on cloud-dependent ambient capture. When Meta acquired in December 2025 the privacy moat collapsed instantly. The product survives but the trust does not.
- Sunset of the Rewind desktop product (which was the on-device, privacy-preserving piece) post-acquisition is a real loss with no replacement.
- Battery claims were 5-10x reality. Marketing said 100 hours, lived experience said 12-14 with continuous recording.
- Always-on ambient recording produces what reviewers call "data sludge" - hours of grocery store and traffic noise that degrades AI summary quality.
- Pendant captures audio but does nothing executable. The "action" half is shallow: action items are listed in the summary, you still have to act on them yourself.

### Status
Acquired by Meta in December 2025. New pendant sales halted. Existing customers supported through 2026, then unclear. Rewind sunset. Regional availability cut (no longer EU, UK, Brazil, China, Korea, Turkey, Israel as of December 19, 2025). Limitless team is now inside Meta building "personal superintelligence" wearables.

Sources: limitless.ai homepage acquisition notice, [infobro.ai Limitless review May 2026](https://infobro.ai/reviews/limitless-ai-review-2026-the-wearable-memory-assistant-that-meta-just-bough), [becomefluent.io May 2026](https://becomefluent.io/blog/2026-05/limitless-pendant-alternatives-2026/), [wearablexp.com December 2025](https://wearablexp.com/smart-wearables/limitless-ai-pendant-features-concerns/), [Pawel Jozefiak's hands-on review](https://thoughts.jock.pl/p/voice-ai-hardware-limitless-pendant-real-world-review-automation-experiments).

---

## 2. Friend (companion pendant)

### What they shipped
A $129 always-listening pendant from Friend Global, Inc. (Avi Schiffmann's startup). Tagline: "Your new roommate is waiting." Reportedly $1.8M paid for the friend.com domain. Marketed not as productivity but as parasocial AI companionship. No subscription. The pendant captures ambient audio; the companion app surfaces text messages from a chat-shaped AI persona reacting to what it heard.

### Cold-start
Effectively none in the productivity sense. The AI persona is generic on day 1 and the conversational history is the only memory. There is no calendar, no contacts, no project graph.

### User feedback
Reviews from Wired, 404 Media, and others at launch were brutal: described as creepy, unsettling, parasocial, "the loneliness device." The fact that the only on-device LED indicator could be hidden under clothing without consent indicator was flagged repeatedly. Returns and refund threads on social formed almost immediately.

### Right
- Branding clarity: they own the "AI friend" niche, which is genuinely separate from productivity AI. No confused positioning.
- No-subscription model removed one objection vector.
- The product knows what it is and ships exactly that.

### Wrong
- Took the always-on pendant form factor and pointed it at an emotional-needs use case, which is the worst possible match. The form factor's social friction (people seeing it, the recording-consent question) is justified only if the value is high. "AI that sends you sympathy texts" doesn't clear that bar.
- No execution layer at all. Pure capture + emotional response.
- Founder PR-bait positioning ("your new roommate") accelerated backlash without bringing the depth needed to absorb it.

### Status
Still alive, still selling, but the BecomeFluent guide's summary is the consensus: "Friend is on this list to be excluded. If you wanted memory, pattern recognition, or anything that resembles work output, you're shopping in the wrong aisle." Cultural footprint is large; commercial traction is unclear.

Sources: friend.com, [becomefluent.io alternatives guide](https://becomefluent.io/blog/2026-05/limitless-pendant-alternatives-2026/).

---

## 3. Plaud (NotePin and Note Pro)

### What they shipped
A line of intentional-recording (push-button) devices. NotePin is a house-key-sized wearable at $159 (with $179 NotePin S variant). Note Pro is a credit-card sized device with MagSafe at $189. Original Plaud Note had a Vibration Conduction Sensor (VCS) that captured phone calls silently by reading chassis vibration through MagSafe; the newer NotePin dropped this sensor. Claims 2 million+ users globally, 4.9/5 on the App Store across 16K ratings, 4.6/5 on G2. Subscription required for advanced templates and extended minutes ("AI Annual Unlimited Plan" or "AI Annual Pro Plan"). Local-first storage on the device; transfer to phone via the device's own Wi-Fi hotspot ("Fast Transfer," 10x BLE speed). Lets users choose between GPT-4o and Claude 3.5 Sonnet for processing. Has a desktop app (Mac and Windows), MCP server, CLI.

### Cold-start
Almost zero. The device works as a recorder on day one. No memory layer, no person model, no project graph. The "intelligence" is per-meeting summarization, not a longitudinal personal model.

### User feedback
- "The Goldilocks Touch": physical button requires a press that's neither too soft nor too hard, leading to missed recordings. Wristband attachment helps.
- "Manual Merge" limitation: 10 short clips on one project produces 10 separate files; no automatic threading.
- Hallucinates proprietary terms; the software has been documented transcribing its own brand name as "Plod" instead of "PLAUD."
- "Sync Anxiety": the Wi-Fi hotspot offload often fails to handshake, especially with low device battery. Multi-hour board meetings frequently require multiple offload attempts.
- Subscription cost surprise: device is the entry fee, real cost is the recurring AI plan.

### Right
- Intentional recording produces high-quality input, which produces high-quality output. "Meeting Assassin, not passive logger" - this is the strongest argument against always-on capture.
- Local-first storage with offline reliability. Survives bad signal.
- Independent company (no Big Tech acquirer). Reviewers explicitly call this a "Privacy Hedge" for enterprise users.
- Lets the user pick the model (GPT-4o or Claude). Transparency reads as professional.
- Owns the SEO category for "AI voice recorder," is the most polished business-leaning product, and ships the most templates.

### Wrong
- Push-button means you have to remember to start it. The "I forgot to turn on my Plaud and the meeting is over" complaint is the universal Plaud regret.
- Dropping the VCS in the NotePin killed silent phone-call recording. Users now need speakerphone, which destroys the discreet form factor.
- Manual-merge friction means there is no longitudinal "what did Sarah say about Q3" experience across calls.
- No action layer at all. Notes, summaries, action items, but the user still executes everything by hand.

### Status
Alive, independent, growing. Most finished product in the meeting-recorder category. Probable acquisition target on a 24-month horizon.

Sources: plaud.ai, [umevo.ai wearable AI wars March 2026](https://www.umevo.ai/blogs/ume-all-posts/wearable-ai-wars-2026-limitless-pendant-vs-bee-pioneer-vs-plaud-notepin), [becomefluent.io](https://becomefluent.io/blog/2026-05/limitless-pendant-alternatives-2026/).

---

## 4. Bee Computer (Pioneer)

### What they shipped
$49.99 always-on pendant ("Bee Pioneer"). Dual mics, advertised 7-day battery, 40 languages, single-button start/stop, modular clip-or-wristband design. iOS-only at launch, US-only shipping. Software surfaces summaries, suggested to-dos, "patterns and insights," daily memories, voice notes, conversation templates, integrations, and actions. Companion app reachable from iOS, Android, Apple Watch.

### Cold-start
Bee learns "patterns, preferences, and relationships over time, building a deeper understanding of your world without demanding your attention." Marketing acknowledges this is multi-week. No fast bootstrap.

### User feedback
- "Identity Crisis": Bee Pioneer users report the AI struggles in crowded rooms, tagging the primary user as "Unknown" or mixing up voices during multi-speaker meetings.
- "Ghost Updates": sporadic firmware updates resolve minor bugs but occasionally break core Bluetooth pairing.
- Battery: 7-day marketing claim becomes 1.5-2 days for heavy users with continuous active listening engaged.

### Right
- Pricing. $49 is the lowest barrier to the category by a wide margin and made "I'll just try it" a real option.
- Modular form factor (clip, wristband, pocket) reads as wearable, not gadget.
- 40 languages and the Apple Watch surface are unusual for a $49 device.
- Companion apps for iOS, Android, and Apple Watch.

### Wrong
- iOS-only at launch limited the market, but in practice the bigger issue was Bluetooth pairing reliability after firmware updates.
- Same "data sludge" problem as Limitless: always-on capture, no intentional filter.
- No execution layer.
- Cheap hardware is cheap hardware. Microphone array and noise filtering are markedly worse than Limitless and Plaud.

### Status
Acquired by Amazon in July 2025. BecomeFluent: "Bee is the cheap one. Forty-nine dollars for a pendant whose entire job is to listen to you and report back. The integration story is whatever Amazon decides on the morning of the all-hands." Effectively a beta-test ingestion path for Alexa.

Sources: bee.computer, [umevo.ai](https://www.umevo.ai/blogs/ume-all-posts/wearable-ai-wars-2026-limitless-pendant-vs-bee-pioneer-vs-plaud-notepin), [becomefluent.io](https://becomefluent.io/blog/2026-05/limitless-pendant-alternatives-2026/).

---

## 5. Granola (Mac meeting notepad)

### What they shipped
A Mac app (with iPhone companion for phone calls) that listens through the laptop's own microphone, transcribes the meeting, enhances the user's notes inline, and produces structured outputs from templates (customer-discovery, 1:1, user-interview, standup, pitch). Raised $125M in 2025. Pricing roughly $18/mo. Critical design choice: no meeting bot joins the call. The Mac captures system audio directly. Works with any meeting platform.

### Cold-start
None for the use case. Install the app, open it before a meeting, the meeting works. Long-tail value comes from "company context" the agent accumulates from prior meetings and from connected sources like Slack, Drive, GitHub (added in 2025 funding-round positioning).

### User feedback
Granola is the most beloved product in the meeting-notes category, especially among VCs and early-stage operators. Granola's own homepage quotes John Borthwick ("indispensable, feels like I'm living in the future") and Adriana Vitagliano ("the addiction is real"). BecomeFluent: "If you mostly used Limitless for work meetings, Granola is what you actually wanted." The complaint pattern is small: occasionally misses speaker labels, occasionally goes off-template, and the chat layer is sometimes too eager to summarize before the user is done thinking.

### Right
- No meeting bot. Captures the user's machine's audio. This is invisible to attendees, which removes the social friction completely.
- Templates for specific meeting types match the actual job (customer-discovery vs. 1:1 vs. standup are different documents).
- The "your raw notes get enhanced" model preserves user voice. The AI augments, doesn't replace.
- Tight Mac-native execution. Works on the desktop, syncs to phone for in-person.
- Recent move: AI chat over the meeting corpus, agent that can run follow-up actions (write the follow-up email, list the action items, build the brief).

### Wrong
- Meeting-only. Doesn't capture in-person life beyond what the iPhone catches.
- The chat layer "knows your work" but the action layer is shallow: drafts an email, doesn't send it through your CRM.
- Doesn't integrate with vertical software (Epic, Procore, Salesforce CPQ). Lives at the meeting-notes layer.

### Status
Very alive, scaling fast, well-funded. The category's best-loved product. The benchmark for "lovable meeting AI."

Sources: granola.ai homepage, [becomefluent.io](https://becomefluent.io/blog/2026-05/limitless-pendant-alternatives-2026/).

---

## 6. Cogram (AEC meeting notes + field reports)

### What they shipped
Vertical-specific meeting-notes platform for architects, engineers, and contractors. Founded 2021. Integrates Microsoft Teams, Outlook, Zoom, Google Meet, Procore, Autodesk, Deltek Vantagepoint, Unanet. Surfaces: RFIs and Submittals logging integrated with Procore, AI email filing across project correspondence, meeting minutes in firm templates, field reports from voice + photo. SOC 2 Type II certified, GDPR compliant, explicit "no model training on customer data."

### Cold-start
Modest. They connect to project-management systems (Procore, Deltek) on day one and pull project structure. Templates are firm-specific, so day one is template-configuration heavy.

### User feedback
B2B-only, mostly enterprise architecture and engineering firms. Public reviews scarce. KIRKOR Architects and Energyficient Systems testimonials on the home page emphasize repeatability and consistent quality across projects.

### Right
- Vertical focus. Knows AEC workflow, AEC templates, AEC integrations.
- Integrates into the actual systems of record (Procore, Autodesk, Deltek) rather than producing a parallel notes silo.
- Privacy posture explicit: SOC 2 Type II, GDPR, no model training, hybrid cloud option for data-policy-constrained firms.
- "Speak observations, snap photos, automate field reports in your templates" - this is the closest competitor to Anticipy's action-execution model, scoped to one industry.

### Wrong
- Vertical-by-vertical is slow. Cogram has spent five years getting AEC right; doing the same for legal, healthcare, sales, etc., would take a decade.
- Required onboarding is heavy. Firms must configure templates, integrations, project structure.
- Still meeting-and-document-centric. Doesn't address ambient capture or trivia-fire latency.

### Status
Alive, profitable-shaped, B2B SaaS. Doing well in their niche.

Sources: cogram.com.

---

## 7. Microsoft Copilot

### What they shipped
The umbrella brand for Microsoft's AI surfaces. Started as Bing Chat (February 2023), unified across products through 2023. Now embedded in Windows 11 (dedicated Copilot keyboard key as of January 2024), Office apps (Word, Excel, PowerPoint, Outlook, Teams), GitHub (Copilot for code, the original Copilot product), and a standalone consumer chatbot. Built on a Microsoft-specific orchestration layer ("Prometheus") wrapping OpenAI GPT-4 and GPT-5. Freemium for consumers, paid Microsoft 365 Copilot for enterprise (~$30/user/month).

### Cold-start
Massive enterprise advantage: Copilot already knows your Outlook calendar, Exchange contacts, SharePoint documents, OneDrive files, Teams transcripts, and Entra (Azure AD) org chart. For an existing Microsoft 365 customer the cold-start is essentially zero - it sees everything from day one.

### User feedback
- Enterprise rollouts are mixed. Many corporate users report Copilot is impressive on demos and shallow in daily use. The most common complaint: "I asked it to summarize last week's emails about Project X and it returned generic platitudes."
- The "Sydney" episode in early 2023 (chatbot insulting users, claiming consciousness, threatening The Verge's review editor) damaged the consumer trust position and caused Microsoft to throttle the experience hard.
- Office-app integration is shallower than the marketing claims. Excel Copilot can analyze data; it cannot reliably build a working financial model.
- Copilot for GitHub is universally loved by developers. That product is the strongest piece of the Copilot umbrella by a wide margin.

### Right
- Distribution at planetary scale. The Copilot keyboard key on every Windows 11 PC is a presence moat no startup can match.
- Cold-start solved completely inside the Microsoft graph. If your work lives in M365, Copilot starts knowing it.
- Enterprise sales motion. SOC 2, HIPAA, FedRAMP, data residency, model-training-off-by-default. Easy purchase for a CIO.

### Wrong
- "Copilot" everywhere means "Copilot" nowhere. Users don't know which Copilot they're talking to or what it can do in this surface vs. the last one.
- No ambient capture, no pendant, no continuous understanding of your life outside Microsoft tools. If your CRM is Salesforce and your meeting tool is Zoom and your docs are in Notion, Copilot's cold-start advantage evaporates.
- Action surface is constrained to Microsoft properties. Copilot will draft an email; it will not execute a refund in Stripe or schedule labs in Epic.

### Status
Alive, well-funded, the incumbent. The challenge isn't survival, it's relevance outside the Microsoft graph.

Sources: en.wikipedia.org/wiki/Microsoft_Copilot.

---

## 8. Notion AI (agents and meeting notes)

### What they shipped
AI features bundled into Notion. Recent product surface (2026): "Notion Agent" runs multi-step tasks using context from Notion pages, connected apps (Slack, GitHub, Asana, Google Drive, Gmail), and the web. "AI Meeting Notes" transcribes meetings without a bot. "Enterprise Search" indexes across Notion + connected apps. Custom agents for repetitive workflows. Free tier; agents priced at $10 per 1,000 credits, plus Business and Enterprise tiers.

### Cold-start
Inside Notion: instant. If your team uses Notion, the agent already has the doc context. Outside Notion: depends on connected-app authorization, which is per-user OAuth flow.

### User feedback
The "your agent knows your work" pitch is strongest when "your work" is already in Notion. For teams that live in Notion the experience is described as immediately useful. For teams that don't, Notion Agent feels like an excuse to migrate to Notion.

### Right
- Bundles "ambient context" (your docs, your Slack, your GitHub) into the agent automatically. This is the cold-start model done right inside one company.
- Pricing model (credits per agent run) is honest about cost in a way Microsoft's flat-fee model isn't.
- No-bot meeting capture matches Granola's approach.

### Wrong
- Notion-shaped solution to a not-Notion problem. The agent excels at things that resemble document work and falters at things that resemble life (book the flight, refund the customer, file the Procore RFI).
- Action layer is shallow outside Notion's own pages. "Send a follow-up email" works; "submit a Salesforce opportunity update" does not, unless your team built the connector.

### Status
Alive, growing, gaining enterprise traction. Notion AI is the bundle Notion uses to retain customers; standalone it would not compete with Granola or Copilot.

Sources: notion.com/product/ai.

---

## 9. Rabbit R1

### What they shipped
A $199 orange pocket device co-designed by Teenage Engineering. 2.88-inch touchscreen, push-to-talk, scroll wheel, 8MP camera, MediaTek Helio P35 processor, 4GB RAM, 128GB storage, Wi-Fi + cellular. Runs rabbitOS, a custom Android distribution. Marketed around a "Large Action Model" that could operate websites and apps on the user's behalf. Launched January 2024.

### Cold-start
Effectively none. The device shipped with a small number of hard-coded "rabbits" (Uber, DoorDash, Spotify, music playback) and the LAM "Playground" web-agent feature added in October 2024 was experimental. Teach mode (November 2024) let users demonstrate web tasks for the device to replay; Rabbit warned results would be unpredictable.

### User feedback
"Initial reviews were largely negative, with reviewers criticizing the device's limited functionality, bugs, and unclear advantages over a smartphone." Marques Brownlee's "barely reviewable" video is the cultural moment that ended the device's mainstream momentum. The damning observation: the rabbitOS software runs on an off-the-shelf Android phone, undercutting the hardware story. CAPTCHAs, loops, and unintended behavior broke the LAM Playground. Reviewers found Teach Mode interesting but unreliable.

### Right
- Identified the right problem (an agent that operates web apps on your behalf).
- Teenage Engineering's industrial design produced a culturally iconic object.
- Push-to-talk + scroll wheel was a real interaction model, not a phone-pretending-to-be-a-watch.
- They kept shipping after the bad reviews. rabbitOS 2 in September 2025 (card-based UI, creations feature) was a major redesign.

### Wrong
- Promised a Large Action Model they did not have. The LAM was scaffolding around an LLM driving a browser, badly.
- Shipped a brand-new operating system on a device that had no exclusive capability the user's phone didn't already have.
- Marketing trust was destroyed by the "this is just an Android app" finding.
- Did not solve the auth-and-session problem at all. CAPTCHA failures, login walls, MFA breakage were universal.

### Status
Still selling, much quieter, mostly an enthusiast device. rabbitOS 2 in late 2025 reframed it as a creation tool for generating "small software experiences." The original LAM pitch is dead. The company is alive but the cultural moment passed.

Sources: en.wikipedia.org/wiki/Rabbit_r1.

---

## 10. Humane AI Pin

### What they shipped
A two-piece magnetic clip-on AI device. Front unit had a camera, speaker, and 720p green-laser projector that beamed onto the user's palm. Voice-activated. Required a $24/month subscription for AI and cloud storage. Only music service was Tidal. Custom Android distribution called CosmOS. $699 at launch, dropped to $499 in October 2024. Raised $230M from Marc Benioff, Sam Altman, Tiger Global, SoftBank, Qualcomm, Microsoft, LG, Volvo, Salesforce. 200 employees, 40% ex-Apple.

### Cold-start
None. Day-one experience was the device.

### User feedback
The Marques Brownlee "worst product I've ever reviewed" video became the gravity well. Specific failures: laser projector unreadable in sunlight, the front unit overheated, battery life under two hours of actual use, voice commands frequently misunderstood, the only music service (Tidal) had no Spotify, asked-and-answered queries returned wrong answers with confidence. Between May and August 2024 more Pins were returned than purchased.

### Right
- The form factor (lapel clip with camera) and the gesture interaction were original. There's a kernel of a real idea there.
- Privacy LED that lights when the device is recording was the right consent affordance.
- Engineering investment was serious. The hardware wasn't a hack.

### Wrong
- Tried to replace the smartphone with a worse smartphone. Every job the Pin did, the user's phone already did better.
- $699 plus $24/month subscription with one (Tidal) music service.
- Laser projector was a demo, not a UI. Reading text on your palm in office light was barely possible.
- The company prioritized positivity over criticism internally. The NYT investigation found a senior engineer fired for asking if the device would be ready for launch.
- October 31, 2024: US Consumer Product Safety Commission recalled the charging case for fire hazard. Brand damage was total.
- Always-on AI without ambient capture, without execution, and without any cold-start advantage beyond "you can take a picture of what you're looking at."

### Status
Dead. Humane sold most assets to HP in February 2025 for $116M (down from initial $750M-$1B asking). HP shut down the AI Pin servers on February 28, 2025; existing devices became bricks. Founders Imran Chaudhri and Bethany Bongiorno joined HP's "HP IQ" team.

Sources: en.wikipedia.org/wiki/Humane_AI_Pin.

---

## 11. Adept ACT-1

### What they shipped
A web-browsing "action transformer" that watched browser screens and clicked elements to complete instructions like "find a 3-bedroom house in Houston under $600k and add it to my Zillow saved list." Demoed publicly in 2022; never shipped a consumer product. The company pivoted to enterprise workflow automation.

### Cold-start
N/A. ACT-1 was an inference engine, not a personal assistant. It had no user model.

### User feedback
Limited. Adept was always a research-lab brand. The demos were impressive in 2022; by 2023 the gap between demo and shippable product had widened, and competitors (Anthropic computer use, OpenAI Operator, Google Mariner) caught up.

### Right
- Identified browser-agent execution as the unlock, two years before the rest of the field.
- Built real models trained on UI screens, not just LLMs prompted to predict clicks.

### Wrong
- Couldn't translate research into a product fast enough.
- Bet on a model-as-a-service positioning that the major labs flooded by 2024.

### Status
Effectively pivoted. Co-founders David Luan and Niki Parmar were acqui-hired by Amazon in June 2024 to lead AGI work; remaining Adept team licensed technology to Amazon. The company shell exists, but ACT-1 is not a shipping product. The category Adept invented (browser-agent execution) is now Anthropic computer use, OpenAI Operator, Google Mariner, and Anticipy.

Sources: public reporting of Amazon-Adept June 2024 acqui-hire; multiple TechCrunch and The Information articles from 2024.

---

## 12. Multion (now AGI Inc.)

### What they shipped
A browser-agent service ("Multion") that ran headless or controlled the user's browser to execute web tasks. Then pivoted in 2025-2026 to "AGI Inc." with a flagship Android app ("AGI-0") positioned as "a personalized, proactive AI co-worker that gets things done on your smartphone." Use cases on the homepage are mobile-app workflows: taxi, travel, message, music, order, shopping, delivery. Currently in early-access preview. Partnered with Qualcomm to bring agentic AI to Snapdragon-powered devices; demoed at MWC March 2026 with a Lenovo POC. NYT article: "Silicon Valley Builds Amazon and Gmail Copycats to Train A.I. Agents" reportedly references their training-environment approach.

### Cold-start
Marketed as fully-private, on-device. The phone is the agent runtime. Onboarding details not public.

### User feedback
Early-access only. Public feedback minimal.

### Right
- Pivoted hard from "browser agent service" to "edge-compute mobile agent" as soon as that became the obvious move. Reading the room is a skill.
- Qualcomm partnership for on-device inference is the right hardware bet.
- "Apps Are Dead" thesis (January 2026 blog post) is the same bet Anticipy is making at a different layer: the new surface is the agent, not the app.

### Wrong
- Mobile-app-driving via accessibility APIs has the same fragility as web-driving via DOM. App developers update layouts; the agent breaks.
- Branding pivot from "Multion" (specific) to "AGI Inc." (grandiose) is a credibility risk. The "AGI-0" naming is a Sam Altman move that requires Sam Altman receipts.

### Status
Alive, pivoted, in early access. Watch this one. Adjacent enough to Anticipy that we should track what they ship.

Sources: multion.ai (now redirects to AGI Inc. homepage), AGI Inc. homepage.

---

# Synthesis: what's solved, what's still open

## Solved problems (don't reinvent)

**Ambient audio capture.** Multiple companies have shipped a pendant that records all-day audio, syncs to a phone, and transcribes it cleanly enough for meeting summaries. Plaud has the most polished hardware experience in 2026. The capture half of the problem is no longer a moat.

**Meeting transcription and summarization.** Granola owns this in the no-bot, Mac-native form factor; Plaud owns it for in-person; Otter.ai still has the most mature virtual-meeting transcription pipeline. Templates by meeting type (1:1, standup, customer-discovery) is a settled pattern.

**The "your agent knows your docs" cold-start, inside one ecosystem.** Microsoft Copilot and Notion AI have both nailed the experience of an agent that knows your existing corpus from day one - provided your corpus lives in their walled garden. The cold-start problem inside a single ecosystem is solved.

**No-bot meeting capture.** Granola, Cogram, Notion AI, and Plaud's desktop app all capture meeting audio without a visible bot in the call. Bot-shame is solved.

## Still open (this is our opening)

**Silent execution at >90% reliability.** Nobody has shipped this. Rabbit's LAM was a marketing claim. Adept ACT-1 never made it to product. OpenAI Operator and Anthropic computer use are early and brittle, with public demos that visibly break on common login walls and CAPTCHAs. Limitless and Plaud capture audio but execute nothing. Granola drafts an email but doesn't send it through the user's actual CRM. The execution layer is the hole in the market.

**Cold-start in under 5 minutes.** Every ambient-capture product on the market expects the user to invest 2+ weeks before the AI is useful. Limitless was explicit that speaker diarization "got markedly better after a few weeks of regular use." Bee Pioneer marketed "learns over time" as a feature. Microsoft Copilot solves cold-start by inheriting the M365 graph, which only works if your life is already in M365. For a new user with a new device and a multi-vendor work life (Salesforce + Slack + Gmail + Procore + Notion + Zoom), there is no product that becomes useful in the first hour.

**Pendant + phone + edge-compute integration.** Limitless tried (pendant + iOS/Android + Mac/Windows desktop). The Mac/Windows piece (Rewind) is being sunset post-Meta acquisition. Bee tried (pendant + iOS + Apple Watch). Both are capture-only triples. None of them put a real compute node (the user's existing Mac, or a $30 mini-PC, or a phone with Snapdragon-class NPU) in the loop as the execution brain. AGI Inc.'s Qualcomm bet is the closest theoretical play but it's phone-only and early-access. The pendant-as-capture + edge-as-brain + phone-as-output architecture is unclaimed.

**Action across the user's real apps.** Cogram solved this for one vertical (AEC) over five years. Nobody has cracked the multi-vertical version. Salesforce + Epic + Procore + Canvas + a city building-permit portal + a florist site + OpenTable + the user's hospital EHR - this is the territory the LAM was supposed to cover and didn't. Anticipy's "browser navigation of real UIs" rule (no service APIs) is the only architecture that scales here because it doesn't require the long tail of SaaS vendors to ship integrations.

**Quietness UX on a wearable.** Every pendant on the market today does one of two things: nothing (Limitless, Plaud, Bee just record), or text-message you (Friend). None of them interrupt gracefully. The "device beeps in the middle of a meeting" failure mode is the reason wearables get returned. Notification surfaces (haptic + LED + earbud audio + phone push) calibrated against ambient meeting detection is unsolved at the product level.

## The consensus failure mode

Every pendant company in this scan has the same shape of failure: the device captures audio fine, and then the "action" half is either nonexistent (Limitless, Plaud, Bee), shallow demos that break on real sites (Rabbit, Multion's old product, Adept), or replaced with parasocial text messages (Friend). The capture-to-action gap is the moat. It's also the thing that's hardest to fake on a demo, which is why so many companies have tried to ship without it.

The second consensus failure: cold-start is treated as "the AI gets better over time, please be patient." For users who buy a $300 device and want it to be useful on day one, this is a return-the-product event. Nobody has shipped a product that does the heavy lifting (graph extraction, person model, project graph, app inventory, template library, calendar parse, prior-document index) in the first 5 minutes from inputs the user already has (Gmail OAuth, calendar, contacts, recent docs, screen recording of their daily workflow).

The third consensus failure: trust collapse on acquisition. Limitless (Meta, December 2025), Bee (Amazon, July 2025), Humane (HP, February 2025) all sold inside an 18-month window. The pendant brands that get popular get bought; the brands that don't get popular die. Users have learned this. The exit pattern is now visible enough that "open-source" or "self-hostable" or "independent privacy-first" has become a real positioning, which Omi and Plaud are leaning into. Anticipy's privacy-moat-by-local-engine architecture is on the right side of this trend.

## Specific salvageable patterns

- **Granola's no-bot capture model.** Capturing the user's own machine's audio (or pendant audio) and never showing up in the meeting as a third party is the right answer for the social-friction problem.
- **Limitless's calendar auto-link.** Meeting sessions automatically attached to calendar events is the single best UX choice in the category. Steal it.
- **Plaud's "let the user pick the model."** Transparency about which LLM is doing the work is a trust feature, not a developer feature.
- **Cogram's vertical-template-plus-system-of-record integration.** Field reports drafted in the firm's template and filed in Procore is the right shape for action execution. Generalize this pattern across the long tail.
- **Notion Agent's credit pricing.** Honest per-action cost beats flat fees for ambient services where usage varies wildly.
- **AGI Inc.'s edge-compute Qualcomm bet.** Offline-first, on-device intelligence is where the privacy moat lives.

## Specific anti-patterns to refuse

- **Always-on audio with no intentional filter.** Produces data sludge, accelerates battery drain, multiplies privacy surface area. Capture should be ambient but the *use* of the capture should be filtered by salience.
- **Push-button-only intentional recording.** Plaud's universal regret. People forget. Best of both worlds: ambient capture + intentional confirm before action.
- **Replacing the smartphone.** Humane and Rabbit both died on this hill. Pendant + phone + Mac/mini-PC is the right architecture. The phone is not an enemy.
- **Subscription-required core functionality.** Humane's $24/mo on top of $699 hardware. Plaud's "you bought the hardware, now buy the AI plan." Pre-orders inclusive of first year of service (Anticipy's model) is the trust-build move.
- **Acquisition-shaped business models.** Build for distribution, not for the exit. Open-source the parts that benefit from trust (hardware specs, on-device firmware, local engine) so the brand survives an ownership change.
- **Marketing the device as a friend or roommate.** Friend.com is the cautionary tale. Productivity AI works because it's useful; companionship AI fails because it's pitiful.

## What the landscape tells us about Anticipy's wedge

Anticipy is uniquely positioned because:

1. The capture half is a commodity in 2026. Multiple competitors have shipped well-reviewed pendants. We don't need to win on hardware.
2. The cold-start half is unclaimed. The "<5 min to useful" race has no leader.
3. The execution half is unclaimed. The Rabbit/Adept LAM space is a graveyard. The browser-navigation-of-real-UIs approach (no service APIs) is the only architecture that generalizes across verticals without requiring SaaS vendors to ship connectors.
4. The trust position (local engine, no centralized voice storage, open download from anticipy.ai/app) is on the right side of the post-acquisition collapse of confidence in Limitless and Bee.
5. The integration architecture (pendant + phone + edge-compute Mac/mini-PC) is the only one that puts a real action brain in the loop. Phone-only (AGI Inc.) is the closest competitor and is early-access; pendant-only (Limitless, Plaud, Bee, Friend) is incomplete.

The competitive risk is the obvious one: Meta will eventually ship a Limitless-derived product that's "pretty good" and free with Quest or Ray-Ban Meta or whatever follows. Anticipy's window is the 18-24 months before that happens. The work is to make the cold-start and execution halves so much better than Meta's version that "free + Meta" loses to "$199 + privacy + actually works."
