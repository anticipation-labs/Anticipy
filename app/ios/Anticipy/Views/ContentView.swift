import SwiftUI

/// "41207s" is a number, not an answer. Anyone who opens the phone before the
/// laptop saw the raw seconds since the browser last checked in — found by
/// the demo-readiness audit, 2026-08-17.
func humanGap(_ seconds: Int) -> String {
    if seconds < 60 { return "just now" }
    if seconds < 3600 { return "\(seconds / 60)m ago" }
    if seconds < 86400 { return "\(seconds / 3600)h ago" }
    return "\(seconds / 86400)d ago"
}

extension AgentJob {
    /// Goals are free-form model strings ("prepare Devon invoice email").
    /// Show them as a sentence — capitalize the first word, leave the rest
    /// human — instead of Title Casing Every Single Word.
    var humanGoal: String {
        let s = goal.replacingOccurrences(of: "_", with: " ")
        guard let first = s.first else { return s }
        return first.uppercased() + s.dropFirst()
    }

    /// The exact owner-authored words bound into this plan's approval. The
    /// concise goal is model-written; this is shown whenever the model left
    /// anything out, so “Send it” never approves invisible context.
    var approvalSource: String? {
        guard let root = try? JSONSerialization.jsonObject(with: Data(params.utf8))
                as? [String: Any] else { return nil }
        let workflow = root["_workflow"] as? [String: Any]
        let raw = (workflow?["authority_text"] as? String)
            ?? (root["source"] as? String) ?? ""
        let source = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !source.isEmpty else { return nil }
        let normalize: (String) -> String = { value in
            value.lowercased().split(whereSeparator: { !$0.isLetter && !$0.isNumber })
                .joined(separator: " ")
        }
        return normalize(source) == normalize(goal) ? nil : source
    }

    /// docs ex 78's middle answer - is my stuff safe - delegated to a policy
    /// that can be tested without SwiftUI. `effect_uncertain` is the engine's
    /// own admission that it could not confirm whether the submit landed.
    var safetyLine: String {
        JobReceiptPolicy.safetyLine(effectUncertain: effect_uncertain)
    }

    /// What actually went wrong, said the way a person would say it.
    ///
    /// A failed job used to render one fixed shrug ("Couldn't finish this
    /// one") followed by `result` printed verbatim — and what lands in there
    /// is a raw JavaScript exception from the extension. The raw string still
    /// exists, behind a disclosure, for the one person in a hundred who wants
    /// it; everyone else gets a sentence and a way forward.
    var failureLine: String {
        let r = (result ?? "").lowercased()
        if r.isEmpty { return "I couldn't finish this one, and nothing came back to tell me why." }
        if r.contains("captcha") || r.contains("not a robot") || r.contains("verify you are human") {
            return "The site asked me to prove I'm a person. That part has to be you."
        }
        if r.contains("login") || r.contains("log in") || r.contains("sign in") || r.contains("signin") || r.contains("password") || r.contains("401") || r.contains("403") {
            return "It wanted a login I don't have. Sign in to that site in Chrome and I can pick this straight back up."
        }
        if r.contains("timeout") || r.contains("timed out") || r.contains("deadline") {
            return "The page took too long to answer, so I stopped waiting rather than sit there forever."
        }
        if r.contains("net::") || r.contains("failed to fetch") || r.contains("networkerror") || r.contains("err_") || r.contains("offline") {
            return "The page wouldn't load. That's usually the connection on your computer."
        }
        if r.contains("debugger") || r.contains("detached") || r.contains("cancel") {
            return "Chrome cut me off partway through. If you clicked Cancel on the yellow bar, that's what did it."
        }
        if r.contains("closed") || r.contains("no tab") {
            return "The tab I was working in closed before I finished."
        }
        if r.contains("not found") || r.contains("404") || r.contains("no such element") || r.contains("selector") {
            return "The page wasn't laid out the way I expected, so I couldn't find what I needed."
        }
        return "I couldn't finish this one."
    }
}

/// Home = the proactive feed: what Anticipy heard, what it's handling,
/// what needs your OK, and what's done — plus live connection health.
struct HomeView: View {
    @EnvironmentObject var pendant: PendantManager
    @EnvironmentObject var session: AnticipySession
    @Environment(\.scenePhase) private var scenePhase
    @State private var typedLine = ""
    /// The sentence the typewriter is committed to, captured ONCE. See
    /// `briefingView` — the poll runs every 3 seconds and used to wipe and
    /// re-type her whole briefing, with a haptic, every time a job count moved.
    @State private var briefingShown = ""
    @State private var briefingTyped = false
    /// Plain-English explanation of whichever status pill was last tapped.
    @State private var pillNote: String?
    /// Which connection she is asking for right now, and the sentence that
    /// provoked it. Transient: a dismissed ask is recorded in ContextGrants,
    /// never here, so it survives the view going away.
    @State private var contextAsk: ContextSource?
    @State private var heardForAsk = ""
    /// The word from your own sentence that provoked the ask, so the question
    /// can name it instead of being generic.
    @State private var askSubject: String?
    /// The newest line already considered. Nil until the first poll populates
    /// the feed, which is what stops a cold launch asking about yesterday.
    @State private var lastSeenLineID: String?
    /// Which source the open sheet is about, so a swipe-dismiss can be recorded
    /// as a decline. `contextAsk` is already nil by the time onDismiss runs.
    @State private var lastAskedSource: ContextSource?
    @State private var showInterview = false
    /// "I'll do this later", remembered. The browser ask below is the one
    /// page first run no longer has, and an offer that returns every time the
    /// feed refreshes is nagging, not offering — so a decline is written down,
    /// exactly as the interview's is. Settings still pairs whenever he wants.
    @AppStorage("browserOfferDeferred") private var browserOfferDeferred = false
    /// The supervised read screen, presented.
    @State private var showMailRead = false
    /// "Not now" on the mail offer, remembered.
    ///
    /// `@AppStorage` on the CANONICAL `ContextGrants` key rather than a private
    /// flag of this view's own, for two reasons. It is the same "no" that
    /// Settings can reopen (`ContextGrants.reopen`, which exists because one
    /// "not now" silencing a source forever is the recoverability failure
    /// `CONSUMER-READINESS` B1 forbids). And it is observed, so the card leaves
    /// the screen on the tap instead of three seconds later when the next poll
    /// happens to redraw the feed.
    @AppStorage(ContextSource.mail.declinedKey) private var mailDeclined = false
    /// May she offer to get to know you?
    ///
    /// "After she has demonstrated value" is the rule
    /// (`design/PREMIUM-FEEL.md:43-47`), and the first version of this read that
    /// as "after a completed job". That made the product's ONLY conversation
    /// about somebody's life contingent on pairing a browser — which onboarding
    /// explicitly invites you to skip ("I'll do this later"). Decline the mic as
    /// well, also a first-class skip, and there is no transcript either, so the
    /// just-in-time asks never fire. A person taking both offered exits was
    /// never asked a single thing about themselves, forever.
    ///
    /// So value OR patience: a finished errand still counts, and failing that,
    /// simply having come back the next day. Both mean she is no longer a
    /// stranger asking on first launch, which is the thing the rule protects
    /// against.
    private var showInterviewOffer: Bool {
        guard !UserDefaults.standard.bool(forKey: "interview.declined") else { return false }
        guard !InterviewProgress().isComplete else { return false }
        // An ERRAND she finished. A supervised read is also a `done` job, and
        // "she has demonstrated value" cannot be satisfied by the read this
        // very gate is meant to lead up to. See `isErrand`.
        if session.jobs.contains(where: { isErrand($0) && $0.status == "done" }) { return true }
        return hasSettledIn
    }

    /// A day since the app was first opened. Recorded on first read rather than
    /// at install, because there is no install hook — and a nil marker means
    /// "today is day zero", so a brand-new install can never satisfy it.
    private var hasSettledIn: Bool {
        let key = "firstOpenedAt"
        let stored = UserDefaults.standard.double(forKey: key)
        if stored == 0 {
            UserDefaults.standard.set(Date().timeIntervalSince1970, forKey: key)
            return false
        }
        return Date().timeIntervalSince1970 - stored > 24 * 60 * 60
    }

    /// Not a card among cards. `design/CONSUMER-FEEL-DIRECTION-2026-08-03.md`
    /// §6 asks for hero moments to get bespoke layouts rather than the fourth
    /// identical rounded rectangle — so this is her voice against the page in
    /// serif and space. It stood behind an accent rule until the golden bars
    /// came out of the product; nothing replaced it, and nothing should: a
    /// border or a fill here is the card §6 forbids. The leading inset went
    /// with the rule, because an indent clearing a rule that is gone reads as
    /// a misaligned section against everything else in this scroll view.
    private var interviewOfferCard: some View {
        VStack(alignment: .leading, spacing: Theme.Space.snug) {
            Text("Want me to actually know you?")
                .font(Theme.display(24))
                .foregroundStyle(Theme.text)
                .fixedSize(horizontal: false, vertical: true)
            Text("Six questions, in your words. I ask, you answer or skip. I never send anything on your behalf without your yes.")
                .font(Theme.aside)
                .foregroundStyle(Theme.text2)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: Theme.Space.snug) {
                Button {
                    Haptics.engage()
                    showInterview = true
                } label: {
                    Text("Ask me")
                }
                .buttonStyle(.glass)
                // Equal weight, and it means it: declined once, never offered
                // again unprompted. Settings still opens it. The touch haptic
                // is the style's, so this action no longer fires its own.
                Button {
                    UserDefaults.standard.set(true, forKey: "interview.declined")
                } label: {
                    Text("Not now")
                }
                .buttonStyle(.ghost)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .animation(Theme.springSlow, value: showInterviewOffer)
    }

    /// May she ask for the browser yet?
    ///
    /// Only with an errand genuinely parked for want of hands: queued and
    /// running jobs are jobs the extension is meant to execute, and with no
    /// browser linked they sit there until one is. That is the "when an errand
    /// actually needs hands" that `design/day-zero.md:237-239` moved this ask
    /// out of first run for — never on day zero, never before she has anything
    /// to show for it.
    ///
    /// `verified` matters as much as the rest: a server she cannot reach
    /// reports `agentPaired` as false (`AnticipyApp.swift:473`), so without it
    /// a dropped connection would tell someone who paired months ago to go and
    /// pair.
    private var browserOffer: Bool {
        verified && !session.agentPaired && !browserOfferDeferred && !handling.isEmpty
    }

    /// The browser ask, asked here instead of in first run.
    ///
    /// `design/day-zero.md:237-239` took it out of onboarding — "It is asked
    /// just-in-time, when an errand actually needs hands" — so this is where
    /// that page went. It sits directly over the work that is waiting for it,
    /// which is the only thing that makes it an answer rather than a chore.
    ///
    /// Bespoke like `interviewOfferCard` and for the same reason
    /// (`CONSUMER-FEEL-DIRECTION-2026-08-03.md` §6): her voice against the
    /// page in serif and space, not the fourth identical rounded rectangle. The
    /// ceremony itself — the step-by-step guide and the six-digit code — is
    /// already in Settings, so this routes there rather than growing a second
    /// copy of pairing that can drift from the first.
    private var browserOfferCard: some View {
        VStack(alignment: .leading, spacing: Theme.Space.snug) {
            Text(handling.count == 1 ? "This one needs your Chrome" : "These need your Chrome")
                .font(Theme.display(24))
                .foregroundStyle(Theme.text)
                .fixedSize(horizontal: false, vertical: true)
            // Kept from the onboarding step this replaces, because it was the
            // honest version: no password, a computer, one setting, two
            // minutes. Naming what she will NOT do is the rule
            // (`design/PREMIUM-FEEL.md:43-47`).
            Text("I work inside your own Chrome, using the accounts you're already signed in to. I never ask for a password. It takes about two minutes, it has to happen on a computer, and there's one Chrome setting to flip. The guide shows you where.")
                .font(Theme.aside)
                .foregroundStyle(Theme.text2)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: Theme.Space.snug) {
                NavigationLink { SettingsView() } label: {
                    Text("Set it up")
                }
                .buttonStyle(.glass)
                // A NavigationLink runs no action closure of its own, and this
                // is the one tap on the card that commits to something.
                .simultaneousGesture(TapGesture().onEnded { Haptics.engage() })
                // The same escape the onboarding step offered, in the same
                // words, and it means it: taken once, she stops asking. The
                // sentence under the header still explains why nothing is
                // moving, so declining costs him no honesty.
                Button {
                    browserOfferDeferred = true
                } label: {
                    Text("I'll do this later")
                }
                .buttonStyle(.ghost)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .animation(Theme.springSlow, value: browserOffer)
    }

    /// May she offer to read your mail yet?
    ///
    /// The trigger is that SHE HAS BEEN TOLD what you live in all day —
    /// interview question 3 (`Interview.swift:56-65`), the one no scrape can
    /// answer. That is a much better provocation than a clock: it puts this ask
    /// in the same register as the just-in-time calendar and contacts asks,
    /// where the ask follows something the person themselves said, rather than
    /// following our schedule. `PREMIUM-FEEL.md:43-47` wants value demonstrated
    /// before the ask, and her having sat and listened to six answers is a far
    /// better demonstration than twenty-four hours having elapsed.
    ///
    /// WHAT SHE CANNOT DO, and it is worth stating so nobody tries: this card
    /// cannot QUOTE the answer. "You said you live in Gmail" is unavailable
    /// from the phone. Interview answers travel out as `kind:"profile"` events
    /// and land in the brain's per-owner SQLite `profile_facts`
    /// (`brain/memory.py:60`); there is no route back, and `upsertOwner` is the
    /// only `owner_profile` call the app makes — a write. `InterviewProgress`
    /// deliberately records WHICH questions were answered and never the
    /// answers, because a second local copy is exactly the split-brain
    /// `design/day-zero.md` §3 already names as a known defect. So the gate
    /// reads the question id and the copy says only what is true of it: that
    /// she was told, not what she was told.
    ///
    /// `design/day-zero.md` §1 phase 3's own trigger was "one errand completed
    /// with a visible result, AND at least one overnight". The finished errand
    /// is kept verbatim. The overnight is dropped, and the interview answer
    /// stands in its place, because the overnight was only ever a proxy for
    /// "she is not a stranger asking on first launch" — and the interview is
    /// itself gated on a finished errand or an overnight
    /// (`showInterviewOffer`), so having been through it proves the same thing
    /// the clock was guessing at, plus the person actually talking to her.
    ///
    /// Then three conditions the interview offer does not need:
    ///
    /// - `agentPaired && agentOnline` — the read happens in HER Chrome, in the
    ///   accounts she is already signed into. Offering a screen whose only
    ///   button cannot work is the "confidently asserts things that are not
    ///   true" failure `CONSUMER-READINESS` §1 names.
    /// - not already granted — one ask, ever, unless the door is reopened in
    ///   Settings. Supervision is required for the FIRST read of a source and
    ///   refreshes afterwards are quiet (§2), so this card is not the way you
    ///   read again; it is the way you let her in the first time.
    /// - not while the interview offer is up. Two asks stacked on one screen is
    ///   the six-step wall wearing a different hat, and `PREMIUM-FEEL.md:43-47`
    ///   allows exactly one at a time.
    private var mailReadOffer: Bool {
        guard verified, session.agentPaired, session.agentOnline else { return false }
        guard !mailDeclined, !ContextGrants().granted(.mail) else { return false }
        guard !showInterviewOffer else { return false }
        guard InterviewProgress().isAnswered("tools") else { return false }
        // A finished ERRAND, never a finished read: otherwise a first read
        // would qualify a person for the offer to do their first read.
        return session.jobs.contains(where: { isErrand($0) && $0.status == "done" })
    }

    /// The mail ask. Bespoke for the same reason as its two siblings
    /// (`CONSUMER-FEEL-DIRECTION-2026-08-03.md` §6): her voice against the page
    /// in serif and space, NOT a fourth identical rounded rectangle.
    ///
    /// The question comes from `ContextSource.mail.ask()` rather than being
    /// retyped here. That string and the promise list on the read screen are
    /// the consent copy, and a second copy of consent wording is a second copy
    /// that can drift from what the code actually does — which is exactly how
    /// two of those promises came to be untrue once already.
    private var mailReadCard: some View {
        VStack(alignment: .leading, spacing: Theme.Space.snug) {
            Text(ContextSource.mail.ask())
                .font(Theme.display(24))
                .foregroundStyle(Theme.text)
                .fixedSize(horizontal: false, vertical: true)
            // The provocation, said in the only way that is TRUE from here.
            // She was told what you live in all day (that is the gate); she
            // cannot read back WHAT you said, so she does not pretend to —
            // see `mailReadOffer`. "The one part of it I still can't see" holds
            // whether or not you named a mail app, because she genuinely
            // cannot see any of it.
            //
            // Then `design/day-zero.md` §1 phase 3, in her words: read and
            // only read, you are there for the first one, and the veto is
            // named up front rather than discovered.
            Text("You've told me what you live in all day. Your mail's the one part of it I still can't see. I'll read, only read, never send, never reply, never delete. You watch the whole thing, and anything I get wrong you tap and it's gone.")
                .font(Theme.aside)
                .foregroundStyle(Theme.text2)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: Theme.Space.snug) {
                Button {
                    Haptics.engage()
                    showMailRead = true
                } label: {
                    Text("Watch me read")
                }
                .buttonStyle(.glass)
                // Equal weight, and it means it. Recorded through
                // `declineContext` so it is the one canonical "no" — the same
                // one the just-in-time asks write and the same one Settings can
                // reopen. Nothing about the person is recorded either way: a
                // skip is never a fact (`design/briefs/08-day-zero.md:30`).
                Button {
                    session.declineContext(.mail)
                } label: {
                    Text("Not now")
                }
                .buttonStyle(.ghost)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .animation(Theme.springSlow, value: mailReadOffer)
    }
    /// Names she has already been told, so a familiar one is not a reason to
    /// ask for the address book.
    private var knownNames: Set<String> {
        Set([session.ownerFirstName, session.ownerLastName]
            .filter { !$0.isEmpty })
    }

    // needs_user (login wall, CAPTCHA, refused site) used to render in NO
    // section at all — the job silently disappeared while the card said
    // "Nothing needs you right now". It belongs in the attention section.
    private var needsOK: [AgentJob] { session.jobs.filter { $0.status == "awaiting_confirm" || $0.status == "needs_user" } }
    /// Finished quiet work — anticipy_says events the brain marked done.
    /// Newest first, capped so the desk never becomes a landfill.
    private var foundForYou: [BrainEvent] {
        let done = session.anticipySays.filter { ev in
            ev.kind == "anticipy_says" && ev.decision == "done"
                && (ev.text?.isEmpty == false)
        }
        return Array(done.prefix(5))
    }
    /// Questions she asked that have NO task behind them, and that he has not
    /// answered yet.
    ///
    /// `needs_user` and `act` always carry a job, so `ConfirmJobCard` already
    /// gives them a box. The two lanes that do not are `clock` (her own
    /// proactive check-in: "Want me to book a table at Earls tonight?") and
    /// `ask` ("what is 'it' in this case?"). Production holds 17 of them and
    /// they rendered as prose he could not reply to, so the only way to answer
    /// the phone that heard him was to leave the app and send a text.
    ///
    /// Still-open is decided by comparing against his newest reply rather than
    /// by remembering locally what he answered. PocketBase `created` is a fixed
    /// ISO shape, so string order IS time order here.
    private var openQuestions: [BrainEvent] {
        let newestReply = session.ownerReplies
            .map(\.created).max() ?? ""
        let goalsWithCards = Set(needsOK.map(\.goal))
        return session.anticipySays.filter { ev in
            guard ev.kind == "anticipy_says",
                  ev.decision == "clock" || ev.decision == "ask",
                  let text = ev.text, !text.isEmpty,
                  ev.created > newestReply else { return false }
            // Belt and braces: a `clock` line normally carries no goal, but if
            // one ever does and that task is already on screen, the card there
            // is the place to answer it.
            let goal = ev.goal ?? ""
            return goal.isEmpty || !goalsWithCards.contains(goal)
        }
        // Two at most. She is allowed to be curious, not to fill the desk with
        // interrogation while the work he actually asked for scrolls away.
        .prefix(2)
        .map { $0 }
    }
    /// A supervised read is a job, but it is NOT an errand, so it stays out of
    /// both feed sections.
    ///
    /// Left in, a read the person is sitting there watching also renders on
    /// Home under "Waiting for your browser" — with `browserOfferCard` possibly
    /// stacked over it telling them to go and pair the Chrome they are watching
    /// her work in. And once it lands it would file under "Done" as an errand
    /// nobody asked for. `lane` is the server's own word for this
    /// (`AgentJob.lane`), which is why this reads the field rather than
    /// sniffing goals or params.
    private func isErrand(_ job: AgentJob) -> Bool { job.lane != "supervised_read" }
    private var handling: [AgentJob] { session.jobs.filter { isErrand($0) && ($0.status == "queued" || $0.status == "running") } }
    private var finished: [AgentJob] { session.jobs.filter { isErrand($0) && ($0.status == "done" || $0.status == "failed") } }

    /// What she heard, as conversations rather than as a wall of lines.
    ///
    /// The window is the same newest-30 lines the feed has always shown; only
    /// the grouping is new, and it groups on the one field that exists —
    /// `events.segment`. A line the segmenter never stamped is a conversation
    /// of one, so with no segments at all this renders the identical list of
    /// rows it renders today. Newest conversation first, the way "Heard" has
    /// always been chronological.
    private var heardGroups: [HeardGroup] {
        Array(HeardGroup.build(Array(session.transcript.suffix(30))).reversed())
    }

    /// Nothing to show at all. WHY there's nothing is a separate question, and
    /// the answer decides which of four very different screens you get.
    private var feedIsEmpty: Bool {
        needsOK.isEmpty && handling.isEmpty && finished.isEmpty && session.transcript.isEmpty
    }

    /// A read actually succeeded. Everything the app claims about your day
    /// hangs off this — reachability alone means nothing, because /api/health
    /// isn't behind the same guard the data API is.
    private var verified: Bool { session.connection == .ready }

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.bg.ignoresSafeArea()
                // Was a hand-rolled copy of the grain with .plusLighter
                // hard-coded — a white haze over a white page once light mode
                // existed. GrainLayer reads the scheme.
                GrainLayer()
                ScrollView {
                    // Rhythm is driven explicitly: space BETWEEN groups is
                    // 2.5–3x space WITHIN one, which is what makes this read
                    // as a layout instead of a list.
                    VStack(alignment: .leading, spacing: 0) {
                        if micNeedsHelp { micRecoveryCard.padding(.top, Theme.Space.tight) }
                        // "Want me to actually know you?" — the graduation.
                        //
                        // Gated on her having FINISHED something visible, not
                        // on a step count. design/PREMIUM-FEEL.md:43-47: ask
                        // AFTER demonstrating value, framed as her curiosity
                        // rather than data collection. Asking on day one, before
                        // she has done a single thing, is the version people
                        // decline.
                        if verified && showInterviewOffer {
                            interviewOfferCard.padding(.top, Theme.Space.snug)
                        }
                        // "Want to open your mail and let me read it once while
                        // you watch?" — the graduation's second half, and the
                        // one that needs her to have earned it most, because it
                        // is the only source that is not on this phone.
                        if mailReadOffer {
                            mailReadCard.padding(.top, Theme.Space.snug)
                        }
                        // Her briefing only appears over a verified read. She
                        // does not get to say "I've got the watch" from an app
                        // that has never once reached its own server — and on
                        // day one the empty state carries the whole screen.
                        if verified && !feedIsEmpty {
                            anticipyCardView.padding(.top, Theme.Space.snug)
                        }
                        // What she found — the quiet work, delivered. Lives
                        // at the top because Omar's words were exact: "it
                        // should text you the results and pull it up at the
                        // top of the app." Before this section existed her
                        // finished research sat in the database and nowhere
                        // else a human looks.
                        if verified && !foundForYou.isEmpty {
                            foundHeader
                                .padding(.top, Theme.Space.section)
                                .padding(.bottom, Theme.Space.tight)
                            VStack(spacing: Theme.Space.snug) {
                                ForEach(foundForYou, id: \.id) { ev in
                                    FoundCard(event: ev)
                                        .transition(.asymmetric(
                                            insertion: .move(edge: .top).combined(with: .opacity),
                                            removal: .opacity))
                                }
                            }
                        }
                        listenCard.padding(.top, feedIsEmpty ? Theme.Space.tight : Theme.Space.roomy)
                        if feedIsEmpty {
                            switch session.connection {
                            case .loading:          loadingState
                            case .offline:          offlineState
                            case .refused(let s):   refusedState(s)
                            case .ready:            emptyState
                            }
                        } else {
                            if !verified { staleNotice.padding(.top, Theme.Space.section) }
                            if !needsOK.isEmpty {
                                needsOKHeader
                                    .padding(.top, Theme.Space.section)
                                    .padding(.bottom, Theme.Space.tight)
                                VStack(spacing: Theme.Space.snug) {
                                    ForEach(Array(needsOK.enumerated()), id: \.element.id) { i, job in
                                        ConfirmJobCard(job: job)
                                            .transition(.asymmetric(
                                                insertion: .move(edge: .top).combined(with: .opacity),
                                                removal: .opacity.combined(with: .scale(scale: 0.96))))
                                            .animation(Theme.spring.delay(min(Double(i) * 0.05, 0.25)), value: session.jobs)
                                    }
                                }
                            }
                            if !openQuestions.isEmpty {
                                askHeader
                                    .padding(.top, Theme.Space.section)
                                    .padding(.bottom, Theme.Space.tight)
                                VStack(spacing: Theme.Space.snug) {
                                    ForEach(openQuestions, id: \.id) { ev in
                                        AskCard(event: ev)
                                            .transition(.asymmetric(
                                                insertion: .move(edge: .top).combined(with: .opacity),
                                                removal: .opacity.combined(with: .scale(scale: 0.96))))
                                    }
                                }
                            }
                            if !handling.isEmpty {
                                // Honest about WHY nothing is moving: with Chrome
                                // shut there are no hands, and saying "Handling"
                                // over a stalled queue is a small daily lie.
                                sectionHeader(session.agentOnline ? "Handling" : "Waiting for your browser")
                                    .padding(.top, Theme.Space.section)
                                    .padding(.bottom, Theme.Space.tight)
                                // Unpaired used to be one grey sentence
                                // pointing at a screen with nothing to tap —
                                // and it is now all that is left of first
                                // run's browser page. So where there is real
                                // work waiting, the ask itself goes here,
                                // once. The sentence stays for the two cases
                                // the card does not cover: paired but shut,
                                // and anyone who already said "later".
                                if browserOffer {
                                    browserOfferCard
                                        .padding(.bottom, Theme.Space.base)
                                } else if !session.agentOnline {
                                    Text(session.agentPaired
                                         ? "Open Chrome and these pick up on their own."
                                         : "Link Chrome in Settings and these pick up on their own.")
                                        .font(.system(size: 15))
                                        .foregroundStyle(Theme.text2)
                                        .padding(.bottom, Theme.Space.tight)
                                }
                                // He has had to ASK whether his extension was
                                // current — twice — and once a whole retest
                                // ran against a stale one while everybody
                                // believed the fixes were live. Chrome already
                                // reports its version on every heartbeat, so
                                // the answer was always here to be shown.
                                // AN UNREACHABLE CUSTOMER NEVER FINDS OUT
                                // THEY ARE UNREACHABLE. Sign-up never
                                // required a number, this app has no
                                // notifications at all, and a text is the
                                // only channel there is — so an account with
                                // no number on file gets asked nothing, ever,
                                // and its work parks forever in silence.
                                // Anyone who signed up before the sign-up
                                // gate is in exactly that state right now.
                                if session.ownerPhone.isEmpty {
                                    Text("I have no number for you, so I can't tell you when "
                                         + "something needs your word. These will just wait. "
                                         + "Add it in Settings and I'll start reaching you.")
                                        .font(.system(size: 15))
                                        .foregroundStyle(Theme.accent)
                                        .padding(.bottom, Theme.Space.tight)
                                }
                                if let stale = session.staleExtensionVersion {
                                    // These three fragments shipped fused: the version
                                    // interpolation ran straight into the next sentence, so the
                                    // banner read "press Reload to get 0.11.0until then it's
                                    // working from old instructions." Nobody saw it for three
                                    // minor versions because the version pin had rotted shut
                                    // (AnticipyApp.swift:104) and a banner that can never fire
                                    // can never be proofread by using the product -- fixing the
                                    // pin on 2026-08-24 is what exposed it. Every fragment but
                                    // the last must end in a space;
                                    // tests/test_extension_version_pin.py holds that seam now.
                                    Text("Chrome is running the old extension (\(stale)). "
                                         + "Open chrome://extensions and press Reload to get \(AnticipySession.expectedExtensionVersion). "
                                         + "Until then it's working from old instructions.")
                                        .font(.system(size: 15))
                                        .foregroundStyle(Theme.accent)
                                        .padding(.bottom, Theme.Space.tight)
                                }
                                VStack(spacing: 0) {
                                    ForEach(Array(handling.enumerated()), id: \.element.id) { i, job in
                                        if i > 0 { Rectangle().fill(Theme.edge).frame(height: 0.5) }
                                        HandlingCard(job: job)
                                            .transition(.asymmetric(
                                                insertion: .move(edge: .top).combined(with: .opacity),
                                                removal: .opacity.combined(with: .scale(scale: 0.96))))
                                            .animation(Theme.spring.delay(min(Double(i) * 0.05, 0.25)), value: session.jobs)
                                    }
                                }
                            }
                            heardSection
                            if !finished.isEmpty {
                                sectionHeader("Done")
                                    .padding(.top, Theme.Space.section)
                                    .padding(.bottom, Theme.Space.tight)
                                VStack(spacing: 0) {
                                    ForEach(Array(finished.prefix(8).enumerated()), id: \.element.id) { i, job in
                                        if i > 0 { Rectangle().fill(Theme.edge).frame(height: 0.5) }
                                        DoneCard(job: job)
                                            .transition(.asymmetric(
                                                insertion: .move(edge: .top).combined(with: .opacity),
                                                removal: .opacity))
                                            .animation(Theme.spring.delay(min(Double(i) * 0.05, 0.25)), value: session.jobs)
                                    }
                                }
                            }
                        }
                        // Diagnostics belong at the foot, not as the opening
                        // statement of the whole product.
                        statusStrip.padding(.top, Theme.Space.wide)
                    }
                    .padding(.horizontal)
                    .padding(.bottom, 30)
                }
                .refreshable { await session.refresh() }
            }
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    // THE MARK ALONE, AND THAT IS THE FIX. This was an HStack
                    // of the mark plus `Text("Anticipy")` at 24pt serif, and
                    // the wordmark never rendered: the leading slot is narrow
                    // once the trailing control has its share, so the system
                    // truncated the text to nothing — while the HStack's 10pt
                    // spacing before it SURVIVED.
                    //
                    // iOS gives a toolbar item its own glass backing and
                    // centres the item's content inside it. So the thing being
                    // centred was `[mark][10pt][nothing]`, which put the mark
                    // 5pt left of the circle's middle and read exactly as a
                    // logo sitting off-centre in its own button.
                    //
                    // Nothing visible is lost: the wordmark was already
                    // invisible, and the app it names is the one you are in.
                    LogoMark(size: 26)
                        .accessibilityLabel("Anticipy")
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    // NO PLATE OF ITS OWN, and that is the whole point.
                    //
                    // iOS draws a glass capsule behind EVERY toolbar item -
                    // it is what the mark on the left is sitting in. Giving
                    // this one `.icon` as well put the component's machined
                    // metal face INSIDE that capsule: two nested surfaces, a
                    // grey disc in a white one, which is what read as "there
                    // is still colour inside it". The leading item looks right
                    // for exactly the reason this one looked wrong - it brings
                    // no surface of its own.
                    //
                    // So `GlassyIconStyle` is for glyph buttons that have to
                    // supply their own affordance, like the send arrow on the
                    // compose line. In a toolbar the system already did it.
                    NavigationLink { SettingsView() } label: {
                        Image(systemName: "slider.horizontal.3")
                            // The colour it had before any of this: a muted
                            // dark, the same weight as the mark opposite it.
                            // Without it the glyph inherits the app's champagne
                            // `.tint`, which makes a gold gear - and a `Theme`
                            // role is not a view naming a colour, which is what
                            // the contract actually forbids.
                            .foregroundStyle(Theme.text2)
                    }
                    // An icon on its own is announced as "button" and nothing
                    // else. VoiceOver users got two unnamed controls on Home.
                    .accessibilityLabel("Settings")
                }
            }
            // The single clearest "this is a real, current iOS app" signal
            // available: content blurs as it passes under the header.
            .toolbarBackground(.ultraThinMaterial, for: .navigationBar)
            // NOT pinned to .dark. It was, which put white toolbar glyphs on a
            // white page the moment light mode existed. Omitted so it inherits
            // whatever AnticipyApp pinned.
            // If listening was on when the app closed or backgrounded, she
            // picks it back up herself — no button-press chore per open.
            .onAppear {
                Haptics.warmUp()
                session.resumeListeningIfWanted()
            }
            .onChange(of: scenePhase) { phase in
                if phase == .active {
                    Haptics.warmUp()
                    session.resumeListeningIfWanted()
                    // A granted source whose facts never made it out (offline,
                    // a dead connection) is retried here rather than lost.
                    Task { await session.flushPendingContext() }
                }
            }
            // The just-in-time ask. It is provoked by a line she actually
            // heard, decided by ContextTrigger (a rule, not the model), and it
            // asks at most once per source. Presented as a sheet rather than a
            // step, because it is a question about the sentence you just said —
            // not another page of a wizard.
            .onChange(of: session.transcript) { _ in
                // Only ever on a line that is genuinely NEW to this session.
                //
                // `transcript` starts empty and the first poll replaces it
                // wholesale, so without this the sheet opened on every cold
                // launch quoting a sentence from hours ago — the unexpected,
                // unexplained ask that CONSUMER-READINESS T4 exists to prevent.
                // It re-fired again every time the server filled in a
                // `decision` on an older line, because any element change makes
                // the array unequal while `last` is unchanged.
                guard let latest = session.transcript.last else { return }
                let firstLoad = lastSeenLineID == nil
                let alreadySeen = latest.id == lastSeenLineID
                lastSeenLineID = latest.id
                guard !firstLoad, !alreadySeen, contextAsk == nil,
                      let hit = ContextTrigger.ask(for: latest.text, knownNames: knownNames)
                else { return }
                heardForAsk = latest.text
                askSubject = hit.subject
                contextAsk = hit.source
            }
            // onDismiss catches the SWIPE. A sheet dismissed by gesture runs
            // neither button, so nothing was recorded and `mayAsk` stayed true —
            // and the next poll, three seconds later, presented it again. Swipe
            // it away twice and it came back twice. A swipe is a "not now", and
            // it is recorded as one.
            .sheet(isPresented: $showInterview) {
                InterviewView().environmentObject(session)
            }
            // The supervised read. A sheet rather than a push, because it is
            // one bounded thing you sit and watch — and it gets the live
            // session so it can create the job, hold the watch lease, and read
            // her narration back. NOT wrapped in a NavigationStack: the screen
            // carries its own header, and a nav bar over it would be a second
            // title saying the same thing.
            .sheet(isPresented: $showMailRead) {
                SupervisedReadView(session: session)
            }
            .sheet(item: $contextAsk, onDismiss: {
                if let asked = lastAskedSource, ContextGrants().mayAsk(asked) {
                    session.declineContext(asked)
                }
                lastAskedSource = nil
            }) { source in
                ContextAskSheet(source: source, heard: heardForAsk, subject: askSubject)
                    .environmentObject(session)
                    .onAppear { lastAskedSource = source }
            }
        }
    }

    // MARK: - Status

    private var statusStrip: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Long, honest labels don't fit two-across on a small phone, and
            // truncating "not capturing yet" back into "Listening" is exactly
            // the lie this is here to stop.
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 10) {
                    statusPill(
                        icon: "dot.radiowaves.left.and.right",
                        label: pendantLabel,
                        active: pendant.state == .connected,
                        // A percentage alone made the person work out what 12%
                        // means for hardware they have owned a week. The policy
                        // owns both the threshold and the words (docs ex 90).
                        detail: PendantBatteryPolicy.detail(percent: pendant.battery),
                        note: pendantNote
                    )
                    statusPill(
                        icon: "macbook",
                        label: agentLabel,
                        active: session.agentOnline,
                        detail: session.agentLastSeenSeconds.map(humanGap),
                        note: agentNote
                    )
                }
                .padding(.vertical, 1)
            }
            if let pillNote {
                Text(pillNote)
                    .font(.caption)
                    .foregroundStyle(Theme.text2)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.top, 6)
        .animation(Theme.spring, value: pillNote)
    }

    /// "Agent unpaired" means nothing to a stranger. This is the same state,
    /// said in words they already own.
    private var agentLabel: String {
        if !verified { return "Chrome, can't check" }
        if !session.agentPaired { return "Chrome not linked" }
        return session.agentOnline ? "Chrome ready" : "Chrome asleep"
    }

    private var agentNote: String {
        if !verified { return "I can't reach my own server, so I can't tell you what Chrome is doing right now." }
        if !session.agentPaired { return "Chrome isn't linked to your phone yet. Linking it in Settings is what lets me actually do things on the web for you." }
        if session.agentOnline { return "Chrome is open and linked. That's where I do the doing." }
        return "Chrome is linked, but it isn't open. Anything I've queued waits there until you open it."
    }

    private var pendantLabel: String {
        switch pendant.state {
        case .connected:
            return session.pendantCapturing
                ? "Pendant · listening"
                : "Pendant · starting transcription"
        case .connecting: return "Pendant connecting"
        case .reconnecting: return "Pendant reconnecting"
        case .warmingUp: return "Turning on Bluetooth"
        case .searching: return "Looking for pendant"
        case .unavailable: return "Bluetooth off"
        case .off: return pendant.hasPairedPendant ? "Pendant away" : "No pendant"
        }
    }

    private var pendantNote: String {
        switch pendant.state {
        case .connected:
            return session.pendantCapturing
                ? "Your pendant audio is being securely transcribed by Deepgram. Finalized words come back to Anticipy; the long-lived provider key never enters this phone."
                : "Your pendant is connected and I'm opening its secure transcription stream. If that service is unavailable, I say so here instead of dropping audio behind a Listening label."
        case .warmingUp: return "Bluetooth is still waking up. I'll start looking for your pendant the moment it's ready. Nothing for you to do."
        case .connecting, .reconnecting, .searching: return "I'm looking for your pendant. Listen with phone works right now either way."
        case .unavailable: return "Bluetooth is off, so I can't see the pendant."
        case .off: return pendant.hasPairedPendant
            ? "Your pendant is out of range or switched off."
            : "You don't have a pendant set up. You don't need one. Your phone is the microphone."
        }
    }

    /// A chip that explains itself when tapped. The `Theme.surface` capsule it
    /// used to be painted on is gone: at rest it is the dot, the icon and the
    /// words, and the frosted pill arrives under your finger.
    private func statusPill(icon: String, label: String, active: Bool, detail: String?, note: String) -> some View {
        Button {
            pillNote = (pillNote == note) ? nil : note
        } label: {
            HStack(spacing: 6) {
                Circle()
                    .fill(active ? Theme.accent : Theme.edge)
                    .frame(width: 7, height: 7)
                    // Pure decoration: the label right beside it says the
                    // same thing in words.
                    .accessibilityHidden(true)
                Image(systemName: icon).font(.caption)
                    .accessibilityHidden(true)
                Text(label).font(.caption.weight(.medium)).lineLimit(1)
                if let detail { Text(detail).font(.caption2).foregroundStyle(Theme.muted) }
            }
            // Kept over the ghost's own label token because here the colour
            // is STATE — this pill says whether the thing it names is on.
            .foregroundStyle(active ? Theme.text : Theme.muted)
        }
        .buttonStyle(.ghost)
        .accessibilityLabel(label)
        .accessibilityHint("Explains what this means.")
    }

    // MARK: - Microphone

    /// iOS has been told no, or told no earlier in this session. Either way
    /// the system alert will never appear again and only Settings can undo it.
    private var micNeedsHelp: Bool { session.micBlocked || !session.listener.authorized }

    /// The whole recovery route used to be one line of grey caption text with
    /// nothing to tap, in an app that contained no route to Settings at all —
    /// so a single "Don't Allow" was the end of the product.
    private var micRecoveryCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("I can't hear you", systemImage: "mic.slash")
                .font(.caption.weight(.semibold))
                .foregroundStyle(Theme.accent)
            Text("The microphone is switched off for Anticipy, so tapping Listen won't do anything. iOS only asks once. Turn it back on and I'll start the moment you come back.")
                .font(.callout)
                .foregroundStyle(Theme.text2)
                .fixedSize(horizontal: false, vertical: true)
            // Secondary: it is the card's way out, not the page's action.
            Button {
                session.openSystemSettings()
            } label: {
                Text("Open Settings")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.ghost)
            .accessibilityHint("Opens Anticipy's page in the iOS Settings app, where Microphone and Speech Recognition can be switched back on.")
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .anticipyCard()
    }

    /// Pendant-less listening: phone mic → on-device transcription → brain.
    private var listenCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 12) {
                Button {
                    Haptics.engage()
                    // The action and the words above it come from ONE answer,
                    // which is the finding: the label was made honest during an
                    // interruption ("Waiting for the microphone") while the tap
                    // stayed keyed on `isListening` — true for the whole of a
                    // call — so the biggest type on the screen became a status
                    // sentence on a control that ends the day.
                    switch listenFace.tap {
                    case .start: session.startListening()
                    case .stop: session.stopListening()
                    case .nothing: break
                    }
                } label: {
                    // The switch that turns the entire product on wears the
                    // same glass as every other primary. What says LISTENING
                    // is the breathing dot and the word — not a second fill
                    // colour. The champagne capsule was the last bespoke
                    // background on this screen.
                    HStack(spacing: Theme.Space.snug) {
                        switch listenFace.glyph {
                        case .breathingDot:
                            BreathingDot(size: 10)
                        case .symbol(let name):
                            Image(systemName: name)
                                .font(.system(size: 18, weight: .medium))
                        }
                        // THE ONE CONTROL THAT KEEPS ITS OWN TYPE. 14pt on the
                        // switch that turns the product on would read as a
                        // footnote, and a label that sets its own font wins
                        // over the style's default by design — see
                        // GlassCTAStyle. Everything else takes the 14/600.
                        Text(listenFace.label)
                            .font(Theme.display(22))
                            .tracking(-0.2)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .buttonStyle(.glass)
                // A tap that iOS will instantly refuse is worse than no
                // button: it reads as the app being broken. `.nothing` is the
                // policy saying exactly that, so the disable and the label it
                // wears cannot disagree.
                .disabled(listenFace.tap == .nothing)
                .accessibilityHint(micNeedsHelp ? "Unavailable until the microphone is switched back on in Settings." : "")
                Spacer()
                // A listening app shows a waveform, never a spinner — and only
                // while there is something to draw it from.
                if session.listener.capturing {
                    WaveBars()
                }
            }
            // Honesty over pretense: when iOS takes the mic (call, Siri,
            // route change), say so while recovery runs — never glow
            // "Listening" over a dead microphone.
            if session.listener.suspended {
                Label("Mic interrupted, taking it back…", systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(Theme.muted)
            }
            // Nothing you said is lost when the network is: say the count out
            // loud rather than let it look like she stopped hearing you.
            if session.pendingCount > 0 {
                Label(
                    session.pendingCount == 1
                        ? "One thing you said is waiting for a signal. I'll send it the moment there is one."
                        : "\(session.pendingCount) things you said are waiting for a signal. I'll send them the moment there is one.",
                    systemImage: "tray.and.arrow.up"
                )
                .font(.caption)
                .foregroundStyle(Theme.muted)
                .fixedSize(horizontal: false, vertical: true)
            }
            // The current session's spoken lines stay visible right here —
            // words move DOWN into this list when you pause, they are never
            // deleted. ✓ means Anticipy's brain has them.
            if session.listener.isListening && !session.sessionLines.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(session.sessionLines.suffix(4)) { line in
                        SessionLineRow(line: line)
                    }
                }
                .padding(10)
                .background(RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous).fill(Theme.surface.opacity(0.6)))
            }
            // Your own voice becoming text is the demo — it renders big,
            // above the settled record, never as fine print below it.
            if !session.listener.partial.isEmpty {
                Text(session.listener.partial)
                    .font(.system(size: 20))
                    .lineSpacing(3)
                    .foregroundStyle(Theme.text.opacity(0.55))
                    .fixedSize(horizontal: false, vertical: true)
                    .transition(.opacity)
            }
            HStack(spacing: 8) {
                TextField("Or tell Anticipy something…", text: $typedLine)
                    .font(.callout)
                    .foregroundStyle(Theme.text)
                    .textFieldStyle(.plain)
                    .onSubmit(submitTyped)
                // ONLY a glyph, so `.icon` — and the state colours go with it.
                // "Empty field versus ready" was `Theme.edge` versus
                // `Theme.accent` decided here, beside a `.disabled` that then
                // dimmed the whole thing again: two expressions of one fact,
                // neither of them the material's. The style says refusing now,
                // in the same voice the primary says it.
                //
                // `arrow.up`, not `arrow.up.circle.fill`: the control IS the
                // circle now, and a filled disc inside a 44pt round face is
                // two nested circles with a gap between them.
                Button(action: submitTyped) {
                    Image(systemName: "arrow.up")
                }
                .buttonStyle(.icon)
                .disabled(typedLine.isEmpty)
                .accessibilityLabel("Send")
            }
            .padding(.horizontal, 12)
            // The arrow brings its own 44pt, so the row adds the hair rather
            // than stacking two paddings into a 62pt compose bar.
            .padding(.vertical, Theme.Space.hair)
            .background(RoundedRectangle(cornerRadius: 12).fill(Theme.surface))
        }
    }

    /// What the control says, what tapping it does, and what sits beside the
    /// words — one answer, from `ListenControlPolicy`.
    ///
    /// The label and the icon were computed properties, the action and the dot
    /// were written into the button, and the label drifted onto a different
    /// question from the action: "Waiting for the microphone" is a true
    /// sentence about the moment, and the tap under it was `stopListening()`.
    /// What is happening is said by the banner below, the wave bars beside, and
    /// the briefing above — none of them a control.
    private var listenFace: ListenControlPolicy.Face {
        ListenControlPolicy.face(micBlocked: micNeedsHelp,
                                 isListening: session.listener.isListening,
                                 suspended: session.listener.suspended)
    }

    private func submitTyped() {
        let line = typedLine.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !line.isEmpty else { return }
        // heard() owns the haptic — a second tap here reads as a stutter-bug.
        typedLine = ""
        Task { await session.heard(line, explicit: true) }
    }

    /// Anticipy speaks first: a first-person briefing of what she heard and
    /// what she's handling, rebuilt live from the real job queue.
    private var anticipyCardView: some View {
        VStack(alignment: .leading, spacing: Theme.Space.tight) {
            // She OPENS with "Evening." in serif — the nav bar two inches
            // above already says Anticipy, so the wordmark row is gone and
            // the greeting takes the headline slot.
            HStack(spacing: Theme.Space.tight) {
                Text(greeting)
                    .font(Theme.display(30))
                    .tracking(-0.5)
                    .foregroundStyle(Theme.accent)
                // Breathing means "she is doing something right now". A
                // connected pendant is not that: it captures nothing. Neither
                // is a microphone a call is holding — this dot sat pulsing
                // directly above "Something else has the microphone right now."
                if session.listener.capturing || !handling.isEmpty {
                    BreathingDot(size: 7)
                }
            }
            briefingView
            if let says = session.freshAnticipySays {
                Rectangle()
                    .fill(Theme.accent.opacity(0.14))
                    .frame(height: 1)
                    .padding(.vertical, Theme.Space.snug)
                Text(says)
                    .font(.system(size: 15))
                    .lineSpacing(2)
                    .foregroundStyle(Theme.text2)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .cardSurface(elevated: true)
    }

    /// She types her opening line ONCE.
    ///
    /// `TypewriterText` restarts whenever its string changes, and the briefing
    /// is rebuilt from job counts that the 3-second poll moves all day — so
    /// the whole sentence wiped itself and re-typed, with a haptic, while you
    /// were reading it. The typewriter now gets a string captured on appear
    /// and never touched again; every later change lands as plain text.
    private var briefingView: some View {
        Group {
            if briefingTyped {
                Text(briefingText)
                    .font(.system(size: 17))
                    .lineSpacing(3)
                    .foregroundStyle(Theme.text)
                    .fixedSize(horizontal: false, vertical: true)
                    .animation(Theme.spring, value: briefingText)
            } else {
                TypewriterText(text: briefingShown) {
                    briefingTyped = true
                }
            }
        }
        .onAppear {
            if briefingShown.isEmpty { briefingShown = briefingText }
        }
    }

    private var briefingText: String {
        var parts: [String] = []
        // Only the phone mic actually hears anything today.
        //
        // `isListening` is the owner's standing wish, not a fact about the
        // microphone: a call, Siri or another app takes the input and sets
        // `suspended` while `isListening` stays true. Saying "I'm listening."
        // there is the same lie the status strip's own comment exists to stop,
        // in the FIRST line she speaks, over an input she does not have.
        if session.listener.isListening {
            parts.append(session.listener.suspended
                         ? "Something else has the microphone right now."
                         : "I'm listening.")
        }
        if !needsOK.isEmpty {
            parts.append("I've got \(needsOK.count) thing\(needsOK.count == 1 ? "" : "s") ready. Just say the word.")
        }
        if !handling.isEmpty {
            parts.append("I'm handling \(handling.count) task\(handling.count == 1 ? "" : "s") right now.")
        }
        if needsOK.isEmpty && handling.isEmpty {
            // EARS ARE EARS, WHICHEVER ONES THEY ARE. This asked only the
            // phone mic, so with the pendant live and the phone mic off the
            // screen said "I'm not listening yet — tap Listen with phone"
            // directly above a status bar reading "Pendant · listening".
            // Demoing the pendant, the product contradicted itself on one
            // screen and took the pendant's side away.
            if session.listener.capturing || session.pendantCapturing {
                parts.append(idleLine)
            } else if !session.listener.isListening {
                parts.append(offLine)
            }
            // AND NEITHER SENTENCE WHILE A CALL HAS THE MICROPHONE. `idleLine`
            // is "All quiet on my end. I've got the watch." — a claim to be
            // covering something, appended to the sentence that has just said
            // she is not. `offLine` is no better: it tells the owner to tap the
            // listening control, which is the one tap that would end the day.
            // The first sentence already said the whole truth, and a briefing
            // is allowed to be one sentence long.
        }
        return parts.joined(separator: " ")
    }

    /// She knows what time it is, and she doesn't say the same sentence
    /// every single time you look at her. Statements only — a question from
    /// an always-listening device reads wrong at night.
    private var greeting: String {
        switch Calendar.current.component(.hour, from: Date()) {
        case 5..<12: return "Morning."
        case 12..<17: return "Afternoon."
        case 17..<23: return "Evening."
        default: return "Late one."
        }
    }

    /// Time-neutral idle lines — "go live your day" belongs to the
    /// empty-state brand moment, and reads absurd at 2am.
    private var idleLine: String {
        let lines = [
            "Nothing needs you right now. I've got it covered.",
            "All quiet on my end. I've got the watch.",
            "Nothing waiting on you. I'll speak up when something matters.",
        ]
        let day = Calendar.current.ordinality(of: .day, in: .year, for: Date()) ?? 0
        return lines[day % lines.count]
    }

    /// With the mic off she is not covering anything, so she doesn't claim to.
    /// She points at the one control that starts her instead.
    private var offLine: String {
        micNeedsHelp
            ? "I can't hear anything until the microphone is back on."
            : "I'm not listening yet, tap Listen with phone, or wake your pendant, "
              + "and I'll start picking things up."
    }

    /// What she heard — one card per conversation, newest first.
    ///
    /// The groups are built ONCE here rather than per row: `heardGroups` is a
    /// computed property, and the separator rule below has to look at the
    /// previous sibling.
    @ViewBuilder private var heardSection: some View {
        let groups = heardGroups
        if !groups.isEmpty {
            sectionHeader("Heard")
                .padding(.top, Theme.Space.section)
                .padding(.bottom, Theme.Space.tight)
            VStack(spacing: 0) {
                ForEach(Array(groups.enumerated()), id: \.element.id) { i, group in
                    // A hairline belongs between two rows on the ink. It does
                    // not belong beside a card, which has its own edge already.
                    if i > 0, !group.isCarded, !groups[i - 1].isCarded {
                        Rectangle().fill(Theme.edge).frame(height: 0.5)
                    }
                    ConversationCard(group: group)
                        .transition(.asymmetric(
                            insertion: .move(edge: .top).combined(with: .opacity),
                            removal: .opacity))
                        .animation(Theme.spring.delay(min(Double(i) * 0.05, 0.25)),
                                   value: session.transcript)
                }
            }
        }
    }

    /// Chronology sections — a tracked uppercase micro-label beside the
    /// serif is an editorial move: it gives the big type something to be
    /// big against.
    private func sectionHeader(_ text: String) -> some View {
        Text(text.uppercased())
            .font(.system(size: 12, weight: .semibold))
            .tracking(1.2)
            .foregroundStyle(Theme.muted)
    }

    /// The one section that demands an action gets the display register and
    /// a count.
    private var needsOKHeader: some View {
        HStack(spacing: Theme.Space.tight) {
            Text("Needs your OK")
                .font(Theme.display(22))
                .tracking(-0.2)
                .foregroundStyle(Theme.text)
            Text("\(needsOK.count)")
                .font(.system(size: 12, weight: .bold))
                .padding(.horizontal, 7)
                .padding(.vertical, 3)
                .background(Capsule().fill(Theme.fill))
                .foregroundStyle(Theme.onFill)
        }
    }

    private var foundHeader: some View {
        HStack(spacing: Theme.Space.tight) {
            Text("Found for you")
                .font(Theme.display(22))
                .tracking(-0.2)
                .foregroundStyle(Theme.text)
            Text("\(foundForYou.count)")
                .font(.system(size: 12, weight: .bold))
                .padding(.horizontal, 7)
                .padding(.vertical, 3)
                .background(Capsule().fill(Theme.fill))
                .foregroundStyle(Theme.onFill)
        }
    }

    private var askHeader: some View {
        HStack(spacing: Theme.Space.tight) {
            Text("She asked you")
                .font(Theme.display(22))
                .tracking(-0.2)
                .foregroundStyle(Theme.text)
            Text("\(openQuestions.count)")
                .font(.system(size: 12, weight: .bold))
                .padding(.horizontal, 7)
                .padding(.vertical, 3)
                .background(Capsule().fill(Theme.fill))
                .foregroundStyle(Theme.onFill)
        }
    }

    // MARK: - The four empty screens

    /// Still asking. The first probe can take the full timeout, and this is
    /// the window in which the app used to paint the finished empty state.
    private var loadingState: some View {
        VStack(spacing: 14) {
            BreathingDot(size: 10)
                .padding(.top, Theme.Space.hero)
                .padding(.bottom, 4)
            Text("One moment.")
                .font(Theme.display(30))
                .tracking(-0.5)
                .foregroundStyle(Theme.text)
            Text("I'm catching up on your day. This takes a second.")
                .font(.system(size: 17))
                .lineSpacing(3)
                .foregroundStyle(Theme.text2)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: 300)
            retryButton("Check again")
        }
        .frame(maxWidth: .infinity)
    }

    /// The phone cannot get to Anticipy at all.
    private var offlineState: some View {
        VStack(spacing: 14) {
            Image(systemName: "wifi.slash")
                .font(.system(size: 34))
                .foregroundStyle(Theme.accent)
                .padding(.top, Theme.Space.hero)
                .accessibilityHidden(true)
            Text("I can't reach my side.")
                .font(Theme.display(30))
                .tracking(-0.5)
                .foregroundStyle(Theme.text)
                .multilineTextAlignment(.center)
            Text(offlineBody)
                .font(.system(size: 17))
                .lineSpacing(3)
                .foregroundStyle(Theme.text2)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: 300)
            retryButton("Try again")
        }
        .frame(maxWidth: .infinity)
    }

    private var offlineBody: String {
        let base = "Your phone can't get through to Anticipy right now. It's almost always the connection. You can keep talking to me either way."
        guard session.pendingCount > 0 else { return base }
        return base + " I'm holding \(session.pendingCount) thing\(session.pendingCount == 1 ? "" : "s") you said, and I'll send \(session.pendingCount == 1 ? "it" : "them") the moment we're back."
    }

    /// We reached the server and it said no. That is mine to fix, not yours —
    /// and it is a completely different problem from being offline.
    private func refusedState(_ status: Int) -> some View {
        VStack(spacing: 14) {
            Image(systemName: "lock")
                .font(.system(size: 34))
                .foregroundStyle(Theme.accent)
                .padding(.top, Theme.Space.hero)
                .accessibilityHidden(true)
            Text("Anticipy won't let me in.")
                .font(Theme.display(30))
                .tracking(-0.5)
                .foregroundStyle(Theme.text)
                .multilineTextAlignment(.center)
            Text("I reached my server and it turned me away. I'm sorting my own key out. This should clear itself in a moment.")
                .font(.system(size: 17))
                .lineSpacing(3)
                .foregroundStyle(Theme.text2)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: 300)
            Text("Error \(status)")
                .font(.system(size: 12))
                .foregroundStyle(Theme.muted)
            retryButton("Try again")
        }
        .frame(maxWidth: .infinity)
    }

    /// The finished, confident screen. It is only ever allowed to appear over
    /// a read that actually succeeded and came back with nothing.
    /// Day one: the ghost of tomorrow — a living manifest of what she is
    /// listening for, and the real components showing what a catch will look
    /// like. No "Check again": this branch is only reachable when the read
    /// SUCCEEDED, and offering a retry tells a first-timer something broke.
    private var emptyState: some View {
        VStack(spacing: 16) {
            LogoMark(size: 96)
                .frame(height: 120)
                .padding(.top, Theme.Space.wide)
                .accessibilityHidden(true)
            Text(greeting)
                .font(Theme.display(40))
                .tracking(-1.0)
                .foregroundStyle(Theme.text)
            Text("Live your day. I listen, I understand, and I handle the follow-through, asking before anything is sent.")
                .font(.system(size: 17))
                .lineSpacing(3)
                .foregroundStyle(Theme.text2)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: 300)
            // Motion is the only thing that distinguishes WAITING from
            // BROKEN: three dots pulsing in sequence beside what she's
            // listening for.
            VStack(alignment: .leading, spacing: Theme.Space.snug) {
                manifestRow("things you say you'll do", delay: 0)
                manifestRow("names and dates you mention", delay: 0.53)
                manifestRow("anything that needs a reply", delay: 1.07)
            }
            .padding(.top, Theme.Space.tight)
            Rectangle().fill(Theme.edge).frame(height: 0.5)
                .padding(.vertical, Theme.Space.snug)
            Text("WHEN I CATCH SOMETHING, IT LOOKS LIKE THIS")
                .font(.system(size: 12, weight: .semibold))
                .tracking(1.2)
                .foregroundStyle(Theme.muted)
                .frame(maxWidth: .infinity, alignment: .leading)
            // The REAL components, fed fixtures — using the actual views
            // guarantees the promise matches the delivery.
            VStack(spacing: Theme.Space.snug) {
                TranscriptRow(line: AnticipySession.TranscriptLine(
                    id: "demo-1",
                    text: "I'll get that invoice over to you tonight",
                    decision: "act"))
                ConfirmJobCard(job: AgentJob(
                    id: "demo-2", goal: "Draft the invoice email to Devon",
                    params: "", status: "awaiting_confirm", result: nil, created: ""))
            }
            .opacity(0.42)
            .blur(radius: 0.4)
            .allowsHitTesting(false)
            .accessibilityHidden(true)
        }
        .frame(maxWidth: .infinity)
    }

    private func manifestRow(_ text: String, delay: Double) -> some View {
        HStack(spacing: Theme.Space.snug) {
            PulseDot(delay: delay)
            Text(text)
                .font(.system(size: 17))
                .foregroundStyle(Theme.text2)
        }
    }

    /// Pull-to-refresh has always been here and nobody has ever found it.
    private func retryButton(_ title: String) -> some View {
        Button {
            Task { await session.refresh() }
        } label: {
            Label(title, systemImage: "arrow.clockwise")
        }
        .buttonStyle(.ghost)
        .padding(.top, 4)
    }

    /// There IS something on screen, but it's what we had before we lost
    /// touch. Say so rather than let it read as live.
    private var staleNotice: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: session.connection == .offline ? "wifi.slash" : "lock")
                .foregroundStyle(Theme.accent)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 8) {
                Text(session.connection == .offline
                     ? "I can't reach Anticipy right now, so this is what I had a moment ago."
                     : "Anticipy turned me away just now, so this is what I had a moment ago.")
                    .font(.footnote)
                    .foregroundStyle(Theme.text2)
                    .fixedSize(horizontal: false, vertical: true)
                Button {
                    Task { await session.refresh() }
                } label: {
                    Label("Try again", systemImage: "arrow.clockwise")
                }
                .buttonStyle(.ghost)
            }
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .anticipyCard()
    }
}

// MARK: - Cards

/// A job the agent prepared and is holding for your explicit go-ahead.
struct ConfirmJobCard: View {
    let job: AgentJob
    @EnvironmentObject var session: AnticipySession
    @State private var answer = ""

    private var stuck: Bool { job.status == "needs_user" }
    private var uncertain: Bool { job.effect_uncertain == true }
    private var sending: Bool { session.inFlight.contains(job.id) }
    private var failed: Bool { session.failedWrites.contains(job.id) }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(stuck ? "Stuck. I need you" : "Ready. Say the word",
                  systemImage: stuck ? "hand.raised" : "checkmark.seal")
                .font(.caption.weight(.semibold))
                .foregroundStyle(Theme.accent)
            Text(job.humanGoal)
                .font(.body.weight(.semibold))
                .foregroundStyle(Theme.text)
            if let source = job.approvalSource {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Your exact words")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(Theme.muted)
                    Text(source)
                        .font(.footnote)
                        .foregroundStyle(Theme.text2)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            if let r = job.result, !r.isEmpty {
                Text(r).font(.footnote).foregroundStyle(Theme.text2)
            }
            if uncertain {
                Text("First check the site or app where this was happening. Only continue if the action did not happen.")
                    .font(.caption)
                    .foregroundStyle(Theme.text2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if stuck && !uncertain {
                TextField("Type what I need, or say you handled it", text: $answer,
                          axis: .vertical)
                    .lineLimit(1...4)
                    .font(.callout)
                    .foregroundStyle(Theme.text)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 10)
                    .background(RoundedRectangle(cornerRadius: 10).fill(Theme.surface))
                    .accessibilityLabel("Your answer for this task")
            }
            // The write failed and the card is still sitting here. Without
            // this row that reads as a UI glitch, and the natural next move
            // is to tap Send again — which is how one email goes twice.
            if failed {
                Label("That didn't go through, I couldn't reach Anticipy. Nothing was sent.", systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(Theme.text2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack(spacing: 10) {
                Button {
                    // No haptic here: confirm() buzzes only after the server
                    // has actually accepted it. This one used to buzz success
                    // before the request had even left the phone.
                    Task { await session.confirm(job, ownerAnswer: answer) }
                } label: {
                    Group {
                        if sending {
                            HStack(spacing: 8) {
                                BreathingDot(size: 6)
                                Text("Sending…")
                            }
                        } else {
                            Text(uncertain ? "I checked, try again"
                                 : (failed ? "Try again" : (stuck ? "Send answer" : "Send it")))
                        }
                    }
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.glass)
                .disabled(sending || (stuck && !uncertain
                           && answer.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty))
                Button {
                    Task { await session.decline(job) }
                } label: {
                    Text("Not now")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.ghost)
                .disabled(sending)
            }
            // No opacity on the row: each control dims itself when it is
            // disabled, so a send in flight no longer greys out the sentence
            // the person is still reading.
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .anticipyCard()
    }
}

/// A question she asked with no task behind it, and a box to answer it in.
///
/// `ConfirmJobCard` answers questions that belong to a job. This answers the
/// other kind, and it deliberately looks quieter: nothing here is waiting on
/// consent, and a proactive check-in dressed up as an approval would teach him
/// to stop reading them.
///
/// The answer goes to the brain as one inbound turn, never onto a job. Which
/// task she meant, whether the answer covers what she asked, and what to keep
/// as a fact about him are all decisions the text lane already owns; a
/// card-local write would be a second, worse copy of that reasoning.
struct AskCard: View {
    let event: BrainEvent
    @EnvironmentObject var session: AnticipySession
    @State private var answer = ""

    private var sending: Bool { session.inFlight.contains(event.id) }
    private var failed: Bool { session.failedWrites.contains(event.id) }
    private var empty: Bool {
        answer.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("She asked", systemImage: "quote.bubble")
                .font(.caption.weight(.semibold))
                .foregroundStyle(Theme.accent)
            Text(event.text ?? "")
                .font(.callout)
                .foregroundStyle(Theme.text)
                .fixedSize(horizontal: false, vertical: true)
            TextField("Answer her", text: $answer, axis: .vertical)
                .lineLimit(1...4)
                .font(.callout)
                .foregroundStyle(Theme.text)
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
                .background(RoundedRectangle(cornerRadius: 10).fill(Theme.surface))
                .accessibilityLabel("Your answer to her question")
            // Same reason ConfirmJobCard carries this row: a write that failed
            // while the card stayed put reads as a UI glitch, and the natural
            // next move is to send again.
            if failed {
                Label("That didn't go through, I couldn't reach Anticipy. She hasn't heard it.",
                      systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(Theme.text2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Button {
                // No haptic here. `answer` buzzes only once the server has
                // taken it, which is the same rule every other write follows.
                Task { await session.answer(event, text: answer) }
            } label: {
                Group {
                    if sending {
                        HStack(spacing: 8) {
                            BreathingDot(size: 6)
                            Text("Sending…")
                        }
                    } else {
                        Text(failed ? "Try again" : "Send")
                    }
                }
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.glass)
            .disabled(sending || empty)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .anticipyCard()
    }
}

/// One line spoken in the current Listen session. Its own view so the
/// checkmark can spring and the hand can feel the promise being kept —
/// the moment "heard on the phone" becomes "held by her brain".
struct SessionLineRow: View {
    let line: AnticipySession.SessionLine
    @State private var celebrated = false

    var body: some View {
        HStack(alignment: .top, spacing: 6) {
            Image(systemName: line.received ? "checkmark.circle.fill" : "circle.dotted")
                .font(.caption)
                .foregroundStyle(line.received ? Theme.accent : Theme.muted)
                .scaleEffect(line.received ? 1.0 : 0.9)
                .animation(Theme.springJoy, value: line.received)
                .padding(.top, 2)
                .accessibilityHidden(true)
            Text(line.text)
                .font(.footnote)
                .foregroundStyle(Theme.text2)
            if line.decision == "act" {
                Image(systemName: "bolt.fill")
                    .font(.caption2)
                    .foregroundStyle(Theme.accent)
                    .padding(.top, 2)
                    .transition(.scale(scale: 0.8).combined(with: .opacity))
                    .accessibilityLabel("I'm acting on this")
            }
            Spacer(minLength: 0)
        }
        .animation(Theme.springJoy, value: line.decision)
        .onChange(of: line.received) { received in
            if received { Haptics.herMessage() }
        }
        .onChange(of: line.decision) { decision in
            // Guarded so the 3s poll can't re-fire the celebration.
            if decision == "act", !celebrated {
                celebrated = true
                Haptics.taskDone()
            }
        }
    }
}

/// A job the agent is working on right now. A row on the ink, not a card —
/// with real data the feed was 30 identical rectangles.
struct HandlingCard: View {
    let job: AgentJob
    @EnvironmentObject private var session: AnticipySession
    @State private var stopping = false

    /// What it is doing RIGHT NOW, in his words.
    ///
    /// The browser writes this to the job every four seconds while it works.
    /// Until it was shown here, a run that can last forty minutes displayed
    /// the words "I'm handling it" and nothing else — so a run going
    /// perfectly and a run that died twenty minutes ago looked exactly the
    /// same from the sofa. That is the whole "why is it always stalling?"
    /// feeling, and the information to answer it already existed.
    ///
    /// The browser guarantees this line names the site rather than the URL
    /// and the field rather than what was typed into it, so it is safe on a
    /// screen someone else can see.
    private var doingNow: String? {
        guard job.status == "running",
              let data = job.params.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let line = obj["_doing"] as? String else { return nil }
        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    var body: some View {
        HStack(spacing: 12) {
            if job.status == "running" {
                BreathingDot(size: 8)
            } else {
                Image(systemName: "hourglass")
                    .foregroundStyle(Theme.muted)
                    .accessibilityHidden(true)
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(job.status == "running" ? "I'm handling it" : "Queued for your browser")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.accent)
                Text(job.humanGoal)
                    .font(.system(size: 17))
                    .lineSpacing(3)
                    .foregroundStyle(Theme.text)
                if let doingNow {
                    Text(doingNow)
                        .font(.system(size: 13))
                        .foregroundStyle(Theme.text2)
                        .lineLimit(2)
                        .transition(.opacity)
                        .animation(Theme.spring, value: doingNow)
                        .accessibilityLabel("Currently \(doingNow)")
                }
            }
            Spacer()
            // THE ONLY STOP IN THIS PRODUCT WAS ON HIS LAPTOP.
            // HandlingCard carried no controls at all, so away from the desk,
            // watching a run head somewhere wrong, he could do nothing about
            // it. Same cancellation path as "Not now", so a stop from here
            // and a stop from Chrome mean one thing to the rest of the
            // system; the browser loop re-reads liveness immediately before
            // every irreversible action, so this lands before a submit.
            if job.status == "running" || job.status == "queued" {
                Button {
                    stopping = true
                    Task { _ = await session.stopRunning(job) }
                } label: {
                    Text(stopping ? "Stopping…" : "Stop")
                }
                .buttonStyle(.ghost)
                .disabled(stopping)
                .accessibilityLabel(stopping ? "Stopping" : "Stop this task")
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, Theme.Space.base)
    }
}

/// A completed job with its result — or a failed one, which gets a plain
/// sentence and a way forward instead of a shrug and a stack trace.
/// Something she quietly looked into, delivered. Her sentence leads —
/// the card IS her speaking, not a log row. Tap to read the whole thing
/// (sources and all); collapsed it stays a glanceable three lines.
struct FoundCard: View {
    let event: BrainEvent
    @State private var expanded = false

    private var headline: String {
        // The goal reads like machine shorthand ("research dinner spots in
        // Vancouver"); soften it into the thing itself. The softening moved to
        // Humanize.goal so this card and the conversation cards share ONE
        // implementation; the fallback below is this card's own and unchanged.
        let g = (event.goal ?? "").trimmingCharacters(in: .whitespaces)
        guard !g.isEmpty else { return "Something you mentioned" }
        return Humanize.goal(g)
    }

    var body: some View {
        // No leading glyph. The sparkle was decoration on a card that already
        // announces itself with `anticipyCard`'s surface and the section
        // heading above it; the headline carries the beat in semibold instead,
        // and the text starts at the card's own edge rather than behind an
        // indent nothing occupies.
        VStack(alignment: .leading, spacing: 8) {
            Text(headline)
                .font(.callout.weight(.semibold))
                .foregroundStyle(Theme.text)
            Text(event.text ?? "")
                .font(.footnote)
                .foregroundStyle(Theme.text2)
                .lineLimit(expanded ? nil : 3)
                .fixedSize(horizontal: false, vertical: expanded)
                .contentShape(Rectangle())
                .onTapGesture {
                    Haptics.tap()
                    withAnimation(.easeInOut(duration: 0.2)) { expanded.toggle() }
                }
            if !expanded {
                Text("tap for the full picture")
                    .font(.caption2)
                    .foregroundStyle(Theme.muted)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .anticipyCard()
    }
}

struct DoneCard: View {
    let job: AgentJob
    @EnvironmentObject var session: AnticipySession
    @State private var expanded = false
    @State private var showRaw = false

    private var succeeded: Bool { job.status == "done" }
    private var retrying: Bool { session.inFlight.contains(job.id) }
    private var retryFailed: Bool { session.failedWrites.contains(job.id) }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: succeeded ? "checkmark.circle.fill" : "exclamationmark.circle")
                .foregroundStyle(succeeded ? Theme.accent : Theme.muted)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 8) {
                if succeeded {
                    // docs ex 77: the receipt leads. This used to lead with the
                    // goal in callout weight and put the confirmation number
                    // underneath in grey footnote with a three-line clamp - the
                    // one thing the person opened the app for, rendered as the
                    // small print under a restated question.
                    let card = JobReceiptPolicy.doneCard(goal: job.humanGoal, result: job.result)
                    Text(card.lead)
                        .font(.callout.weight(.medium))
                        .foregroundStyle(card.hasReceipt ? Theme.text : Theme.text2)
                        .fixedSize(horizontal: false, vertical: true)
                        .lineLimit(expanded ? nil : 4)
                        .contentShape(Rectangle())
                        .onTapGesture {
                            Haptics.tap()
                            withAnimation(.easeInOut(duration: 0.2)) { expanded.toggle() }
                        }
                    if let context = card.context {
                        Text(context)
                            .font(.footnote)
                            .foregroundStyle(Theme.muted)
                    }
                } else {
                    Text(job.humanGoal)
                        .font(.callout.weight(.medium))
                        .foregroundStyle(Theme.text)
                    Text(job.failureLine)
                        .font(.footnote)
                        .foregroundStyle(Theme.text2)
                        .fixedSize(horizontal: false, vertical: true)
                    // docs ex 78: a failed card must answer THREE things -
                    // what happened, is my stuff safe, what do I do next.
                    // failureLine answers the first and the retry button the
                    // third; the middle one was simply absent, so a person
                    // reading "I couldn't finish this" had no idea whether
                    // twenty minutes of filled form was still there. Part 3:
                    // "Work is never destroyed" - which is worth nothing if
                    // the person cannot tell.
                    Text(job.safetyLine)
                        .font(.caption)
                        .foregroundStyle(Theme.muted)
                        .fixedSize(horizontal: false, vertical: true)
                    if retryFailed {
                        Text("I couldn't even queue it back up. I can't reach Anticipy.")
                            .font(.caption)
                            .foregroundStyle(Theme.muted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    VStack(alignment: .leading, spacing: 8) {
                        // A terminal attempt stays immutable. Retrying starts
                        // a new request rather than rewriting a failed record.
                        Button {
                            Task { await session.requestFreshRetry(job) }
                        } label: {
                            Group {
                                if retrying {
                                    HStack(spacing: 8) {
                                        BreathingDot(size: 6)
                                        Text("Queueing…")
                                    }
                                } else {
                                    Text("Start a fresh attempt")
                                }
                            }
                        }
                        .buttonStyle(.glass)
                        .disabled(retrying)
                        Text("This failed attempt stays in history; the retry gets its own approval and result.")
                            .font(.caption2)
                            .foregroundStyle(Theme.muted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    // The raw string is a JavaScript exception. It stays
                    // available and stops being the headline.
                    if let r = job.result, !r.isEmpty {
                        Button {
                            withAnimation(.easeInOut(duration: 0.2)) { showRaw.toggle() }
                        } label: {
                            Label(showRaw ? "Hide the details" : "Show me the details",
                                  systemImage: showRaw ? "chevron.up" : "chevron.down")
                        }
                        .buttonStyle(.ghost)
                        if showRaw {
                            Text(r)
                                .font(.caption2.monospaced())
                                .foregroundStyle(Theme.muted)
                                .textSelection(.enabled)
                                .fixedSize(horizontal: false, vertical: true)
                                .padding(10)
                                .background(RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous).fill(Theme.surface))
                        }
                    }
                }
            }
            Spacer()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, Theme.Space.base)
    }
}

struct TranscriptRow: View {
    let line: AnticipySession.TranscriptLine
    @EnvironmentObject var session: AnticipySession
    /// "Thinking…" used to sit on a line for hours if the worker stalled,
    /// with nothing to tap. After a minute and a half it stops pretending.
    @State private var waitedTooLong = false

    private var local: Bool { line.id.hasPrefix("local-") }

    /// The instant the product becomes real — a line flipping to "act" —
    /// arrives on the joy spring, once. A latch and nothing more now: it used
    /// to flash the row's champagne rule to full strength for 0.6s and settle
    /// back, and that rule went with every other golden bar. The moment is
    /// still carried twice — `Haptics.taskDone()` below, and "On it" springing
    /// in on `Theme.springJoy` — so the flash was the third telling of it.
    @State private var celebrated = false

    /// WHICH EARS caught this line, drawn small and grey. Which sources earn a
    /// badge — and which deliberately stay silent — is decided by
    /// CaptureSourcePolicy, where it is tested without a simulator.
    private var ear: CaptureSourcePolicy.Badge? {
        CaptureSourcePolicy.badge(for: line.source)
    }

    var body: some View {
        // Speech looks like speech: her words at voice size, no container and
        // no edge. The champagne rule that stood at the left is gone; nothing
        // took its place, because the row was never a container and a border
        // would make it one.
        VStack(alignment: .leading, spacing: 5) {
            Text(line.text)
                .font(.system(size: 17))
                .lineSpacing(3)
                .foregroundStyle(Theme.text)
            if let ear {
                HStack(spacing: 4) {
                    Image(systemName: ear.glyph).accessibilityHidden(true)
                    Text(ear.label)
                }
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(Theme.muted)
                .accessibilityLabel(CaptureSourcePolicy.accessibilityLabel(for: ear))
            }
            switch line.decision {
            case "act":
                HStack(spacing: 5) {
                    Image(systemName: "bolt.fill").accessibilityHidden(true)
                    Text("On it")
                }
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(Theme.accent)
                .transition(.scale(scale: 0.8).combined(with: .opacity))
            case "ask":
                HStack(spacing: 5) {
                    Image(systemName: "questionmark.circle").accessibilityHidden(true)
                    Text("Quick question for you")
                }
                .font(.caption.weight(.medium))
                .foregroundStyle(Theme.accent)
            case "ignore":
                // Two different silences, finally told apart. "Ignored with
                // a goal" means she quietly started work because of this
                // line — Omar watched her research Paris flights behind
                // "Noted — nothing needed" and reasonably concluded she was
                // dead. Truly-left-alone keeps the plain label.
                if line.goal?.isEmpty == false {
                    HStack(spacing: 5) {
                        Image(systemName: "magnifyingglass").accessibilityHidden(true)
                        Text("Looking into it. I'll text you what I find")
                    }
                    .font(.caption.weight(.medium))
                    .foregroundStyle(Theme.accent.opacity(0.85))
                } else {
                    Text("Noted. Nothing needed")
                        .font(.caption)
                        .foregroundStyle(Theme.muted)
                }
            default:
                if waitedTooLong {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(local
                             ? "This one is still on your phone, it hasn't reached me yet."
                             : "I have this, but I haven't come back with anything on it.")
                            .font(.caption)
                            .foregroundStyle(Theme.muted)
                            .fixedSize(horizontal: false, vertical: true)
                        Button {
                            Task { await session.refresh() }
                        } label: {
                            Label(local ? "Send it now" : "Check again", systemImage: "arrow.clockwise")
                        }
                        .buttonStyle(.ghost)
                    }
                } else {
                    // A line still on this phone hasn't reached the brain yet —
                    // saying "Thinking…" about it would be a lie the moment the
                    // network dropped it.
                    Text(local ? "Sending…" : "Thinking…")
                        .font(.caption)
                        .foregroundStyle(Theme.muted)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .animation(Theme.springJoy, value: line.decision)
        .onChange(of: line.decision) { decision in
            guard decision == "act", !celebrated else { return }
            celebrated = true
            Haptics.taskDone()
        }
        .task(id: line.id) {
            waitedTooLong = false
            guard line.decision == nil else { return }
            try? await Task.sleep(nanoseconds: 90_000_000_000)
            waitedTooLong = true
        }
    }
}
