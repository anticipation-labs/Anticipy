import SwiftUI

/// Everything this screen needs from the outside world to run ONE real read.
///
/// A value of async closures rather than the three `() -> Void` hooks that used
/// to live on `SupervisedRead`, for one concrete reason: `startSupervisedRead`
/// hands back a JOB ID, and both the narration poll and the watch-lease
/// heartbeat need it. A `() -> Void` cannot give one back, so the old hooks
/// could never have driven anything — they were a seam, not a reader.
///
/// `nil` is a real state, not a placeholder: previews and any caller without a
/// session get it, `SupervisedRead.hasReader` is false there, and the screen
/// offers no button it cannot honour.
struct SupervisedReader {
    /// Create the read job. `nil` means no job was created — offline, refused,
    /// or the write did not confirm. NEVER retried from here: a read nobody
    /// asked for a second time is not a read anybody is watching.
    let begin: () async -> String?

    /// Push `jobs.watching_until` out to now + 30s.
    ///
    /// THIS IS THE SUPERVISION, and it is why this type is a set of closures
    /// the VIEW drives rather than a service that runs somewhere. The extension
    /// re-reads the lease before every single action and aborts the instant it
    /// is in the past — `design/day-zero.md` §4 gate 5, "First read of a source
    /// requires the app in the foreground. This is the supervision, expressed
    /// as a precondition", built in the same shape as `agent_loop.js:5211`'s
    /// `stoppedNow()` re-check before anything irreversible. Stop calling this
    /// and the read stops itself within thirty seconds.
    ///
    /// Authorisation therefore comes from a lease the watcher is actively
    /// holding, never from a flag on the job. `extension/side_trip.js:190-260`
    /// states the rule this obeys: "another process decided I may read your
    /// inbox" is exactly the sentence this product cannot afford to be true.
    let hold: (String) async -> Void

    /// Read back what she has said and what she has concluded, in order.
    ///
    /// Distilled narration only. `design/LOCAL-FIRST.md:9-11` — conclusions
    /// travel, the stream never does — so there is deliberately no raw-page-text
    /// channel here for this screen to render by accident.
    let poll: (String) async -> (lines: [String], facts: [String])

    /// Is this job over? Answered from job status the app already polls, so the
    /// screen never decides for itself that a read has ended.
    let settled: (String) async -> Bool

    /// Put `watching_until` in the PAST, now.
    ///
    /// Simply quitting the heartbeat already ends a read, but it ends it up to
    /// thirty seconds later — and in that window she can keep acting and keep
    /// storing facts that never appear on this screen, which makes "I kept what
    /// you watched me find" a small lie. So a deliberate Stop, and this screen
    /// going away, say so out loud.
    ///
    /// It can only ever SHORTEN a read. That matters: it means calling this is
    /// never the escape hatch the heartbeat comment warns about, so it is safe
    /// in `onDisappear` where a heartbeat would not be.
    let drop: (String) async -> Void

    /// "Never derive this again." Fire-and-forget behind the instant local
    /// removal (`design/day-zero.md` §3: "A tap deletes it and marks it
    /// never-re-derive").
    let forget: (String, String) async -> Void
}

extension SupervisedReader {
    /// The real one. Every closure is a single existing session call, on
    /// purpose: the phone owns no read logic at all.
    ///
    /// `settled` is answered from `session.jobs` — the feed the app already
    /// polls every three seconds — rather than by a new server call or a
    /// stopwatch, because a screen that decides for itself when a read is over
    /// is a screen that can be confidently wrong about it.
    @MainActor
    static func live(_ session: AnticipySession, source: ContextSource) -> SupervisedReader {
        SupervisedReader(
            begin: { await session.startSupervisedRead(source: source) },
            hold: { await session.holdWatchLease(jobID: $0) },
            poll: { await session.supervisedLines(jobID: $0) },
            settled: { id in
                guard let job = session.jobs.first(where: { $0.id == id }) else { return false }
                return job.status == "done" || job.status == "failed" || job.status == "cancelled"
            },
            drop: { await session.dropWatchLease(jobID: $0) },
            forget: { await session.forgetSupervisedFact(jobID: $0, fact: $1) })
    }
}

/// The state of one supervised read, as the screen sees it.
///
/// Deliberately dumb, and deliberately timer-less: it holds what she has said,
/// what she has concluded, and whether she is still going. It starts no clock
/// and owns no task. The SCREEN drives, through `SupervisedReader`, so that
/// SwiftUI's own view lifecycle is the thing that kills a read — see
/// `SupervisedReadView.driveKey`. That is not a style preference, it is the
/// enforcement, and moving the loop in here would quietly destroy it.
///
/// Mutators `began/say/found/finished` are the seam the reader writes to.
/// Nothing in here invents a line, a fact, or a tick of progress.
@MainActor
final class SupervisedRead: ObservableObject {

    /// A line and a fact carry an IDENTITY rather than being bare strings.
    ///
    /// `ForEach(id: \.self)` over `[String]` collapses duplicates, and a
    /// narrated log repeats itself by nature — two "Nothing there." lines in
    /// one read is ordinary. Collapsed rows would drop her words and retrigger
    /// the typewriter on the survivor, which reads as a glitch in the one
    /// surface whose entire job is to be watchable.
    struct Line: Identifiable, Equatable { let id = UUID(); let text: String }
    struct Fact: Identifiable, Equatable { let id = UUID(); let text: String }

    /// What she is saying as she goes, oldest first.
    @Published private(set) var lines: [Line] = []
    /// What she has concluded. 5–15 per source, never a copy of the mailbox
    /// (`design/day-zero.md` §3: the store has no embeddings, so volume buries
    /// the facts that matter).
    @Published private(set) var facts: [Fact] = []
    /// Is a read running right now? Only ever set by `start()`/`began()` and
    /// cleared by `finished()`, `stop()`, `lapse()` or `failed()` — never
    /// inferred from having lines, because a finished read still has all of
    /// them.
    @Published private(set) var isReading = false
    /// Vetoed facts, kept as text so the screen can say how many. The
    /// never-re-derive half is sent in `forget(_:)`.
    @Published private(set) var forgotten: [String] = []
    /// She was stopped by hand rather than reaching the end. Kept distinct from
    /// `isReading == false` so the screen can say which happened.
    @Published private(set) var wasStopped = false

    /// The job this read IS. Nil until she has actually begun one.
    ///
    /// Published and owned here rather than held as view state because the
    /// narration poll and the lease heartbeat are two separate tasks that both
    /// need it — and a heartbeat pushing a stale id is a lease held open over
    /// the wrong read, which is the one bug this whole mechanism exists to make
    /// impossible.
    @Published private(set) var jobID: String?

    /// She stopped because you stopped watching.
    ///
    /// Kept apart from `wasStopped` (you pressed Stop) because the screen has
    /// to say which happened, and this one is not a failure — it is the
    /// mechanism working exactly as designed.
    @Published private(set) var lapsed = false

    /// Why a read cannot happen, or did not start, in her voice.
    ///
    /// Non-nil means SAY THIS. There is no state in which this screen shows a
    /// spinner and waits: an unreachable reader gets a sentence, because a
    /// consent surface is the worst place in the product to overstate what it
    /// can do (`CONSUMER-READINESS` §1, "the app confidently asserts things
    /// that are not true").
    @Published private(set) var trouble: String?

    /// The reader, or nothing at all. One optional value rather than a separate
    /// "available" flag, so it is structurally impossible for the surface to
    /// advertise a reader that cannot run.
    let reader: SupervisedReader?

    init(reader: SupervisedReader? = nil) {
        self.reader = reader
    }

    /// Can this screen actually start anything?
    var hasReader: Bool { reader != nil }

    // MARK: - Driven from outside

    /// She has the job and has begun. Clears the previous read's words: a
    /// second read is a second read, not an append to the first.
    func began(jobID: String) {
        self.jobID = jobID
        lines = []
        facts = []
        wasStopped = false
        lapsed = false
        trouble = nil
        isReading = true
    }

    func say(_ text: String) {
        lines.append(Line(text: text))
    }

    /// One distilled fact, as she finds it. The screen animates it in; nothing
    /// here decides how long that takes.
    func found(_ fact: String) {
        facts.append(Fact(text: fact))
    }

    /// One pass, done. A supervised read is a single pass by definition, so
    /// there is no "continue" here to be tempted by.
    func finished() {
        isReading = false
    }

    /// It could not happen, and here is the sentence to show for it. Ends the
    /// read in the same breath: a stated reason with a live breathing dot still
    /// going under it is worse than either alone.
    func failed(_ why: String) {
        trouble = why
        isReading = false
    }

    /// The watch lease lapsed because you stopped watching, which is the deal.
    func lapse() {
        guard isReading else { return }
        lapsed = true
        isReading = false
    }

    // MARK: - Driven by the person

    /// One tap, one job. `jobID` is cleared here rather than in `stop()`, so a
    /// veto tapped after she finishes still addresses the read it came from.
    func start() {
        guard hasReader else { return }
        jobID = nil
        trouble = nil
        lapsed = false
        wasStopped = false
        isReading = true
    }

    /// Stopping is not cancelling a download — it ends the read where it is and
    /// keeps what she already showed you, because the facts on screen are ones
    /// you watched her find.
    ///
    /// TWO things end it, and both are needed. The screen stops pushing
    /// `watching_until` (its `.task(id:)` re-keys the instant `isReading` goes
    /// false), and the lease is dropped INTO THE PAST right now. Without the
    /// drop, "stop" would mean "stop within thirty seconds", and anything she
    /// found in that window would land in the store having never appeared on
    /// this screen — which would make "I kept what you watched me find" false in
    /// exactly the direction that matters. Supervision is worth nothing if the
    /// person watching cannot intervene (`design/day-zero.md` §5, "skippable at
    /// every moment").
    func stop() {
        guard isReading else { return }
        isReading = false
        wasStopped = true
        release()
    }

    /// End the lease now, without touching what the screen is showing.
    ///
    /// Separate from `stop()` because the screen going away has to do this too,
    /// and it must NOT overwrite `lapsed`/`wasStopped` on the way out. The write
    /// can only ever shorten a read, so a fire-and-forget `Task` here is not the
    /// background-heartbeat defect the driver comment forbids — it is the
    /// opposite of it.
    func release() {
        guard let reader, let jobID else { return }
        Task { await reader.drop(jobID) }
    }

    /// A tap deletes it — here at once, and at the source behind you.
    ///
    /// The removal is synchronous and the write is not, on purpose: the tap has
    /// to feel instant, exactly as `AnticipySession.write` already treats a job
    /// action. The event is `kind: "read_veto"`, and the brain deletes every row
    /// stating the fact and marks it never-re-derive, so a second read cannot
    /// put it back (`design/day-zero.md` §3: "Every fact is vetoable. A tap
    /// deletes it and marks it never-re-derive").
    ///
    /// With no reader or no job — previews — the removal is still real and
    /// nothing is sent. It does not pretend to have sent one.
    func forget(_ fact: Fact) {
        facts.removeAll { $0.id == fact.id }
        forgotten.append(fact.text)
        guard let reader, let jobID else { return }
        Task { await reader.forget(jobID, fact.text) }
    }
}

/// Watching her read. The most interactive surface in the product, and the one
/// that explains what the product IS.
///
/// `design/day-zero.md` §2: "watching her open a tab, read subject lines, and
/// say 'you and Marcus have something in flight' teaches, in one gesture: she
/// reads your things, in your browser, in your accounts, and she asks first."
/// An autonomous scrape teaches nothing, because there is nothing to see — so
/// the read is supervised, and this screen is the supervision.
///
/// FOUR THINGS ARE LOAD-BEARING and none of them may be quietly dropped:
/// 1. the narrated log — her words, as she says them, typed;
/// 2. facts arriving one at a time, EACH VETOABLE BY A TAP (§3);
/// 3. the standing promise, visible the whole time
///    (`design/PREMIUM-FEEL.md:135`: "I read. I never send. Ever.");
/// 4. a stop that works mid-sentence.
///
/// TYPEWRITER RULES. `design/CONSUMER-FEEL-DIRECTION-2026-08-03.md` §2.7 bans
/// the typewriter on consent, permission and error copy — "where a companion
/// becomes twee". Her narrated lines ARE things she is saying, so they are
/// typed. The promise, the rule list, the empty state and anything explaining
/// why a read cannot happen are not, and must never become so.
///
/// NO ROUNDED-RECTANGLE GRID. The facts are ruled entries, not a fourth set of
/// evenly spaced symbol-and-card rows — §4 cut #3 names that layout as the most
/// recognisable AI-built thing there is, and this is the screen a stranger
/// judges the product by.
struct SupervisedReadView: View {
    /// Owned rather than observed, so the lines and facts survive the sheet's
    /// content closure being re-evaluated — which Home does every three
    /// seconds, on every poll. An `@ObservedObject` over a freshly built read
    /// would wipe her narration mid-sentence.
    /// MOTION SENSITIVITY. Read so the animations below can stand down; the
    /// beat is kept either way, so a flow under Reduce Motion takes the same
    /// time and simply shows its finished frame rather than travelling to it.
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @StateObject private var read: SupervisedRead
    @Environment(\.dismiss) private var dismiss
    /// Whether the app is FRONTMOST. Half of `driveKey`, and therefore half of
    /// the safety property — see the tasks at the bottom of `body`.
    @Environment(\.scenePhase) private var scenePhase

    /// The deterministic half of consent (`design/day-zero.md` §4 gate 1: "A
    /// read refuses without a stored per-source grant"). Recorded here, next to
    /// the read it authorises, because mail is unreachable from the just-in-time
    /// ask on purpose — consenting to a capability somewhere far from where it
    /// runs is the trap.
    private let grants = ContextGrants()
    @State private var granted = ContextGrants().granted(ContextSource.mail)

    private let source = ContextSource.mail

    /// The live screen. ONE construction site for the reader, so the state
    /// object and the thing that can actually run a read cannot end up
    /// disagreeing about whether one is possible.
    init(session: AnticipySession) {
        _read = StateObject(wrappedValue: SupervisedRead(
            reader: .live(session, source: ContextSource.mail)))
    }

    /// A read handed in whole: previews, and any caller with no session. Its
    /// `reader` is nil, so `hasReader` is false and no start button appears.
    init(read: SupervisedRead) {
        _read = StateObject(wrappedValue: read)
    }

    var body: some View {
        ZStack {
            Theme.bg.ignoresSafeArea()
            // No eye-anchor behind the mark any more: the champagne haze is
            // gone from every surface in the product. `grainOverlay` below is
            // the paper texture and stays.

            VStack(alignment: .leading, spacing: Theme.Space.card) {
                header
                if granted { readingBody } else { consentBody }
                troubleNote
                Spacer(minLength: Theme.Space.snug)
                promiseBand
                actions
            }
            .padding(.horizontal, 28)
            .padding(.top, Theme.Space.roomy)
            .padding(.bottom, 18)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .grainOverlay()
        .navigationTitle("Watch me read")
        // THE HEARTBEAT AND THE NARRATION, BOTH KEYED THE SAME WAY. Read this
        // before touching either.
        //
        // `driveKey` folds in whether the app is frontmost. SwiftUI cancels a
        // `.task(id:)` when its id changes AND when the view leaves the
        // hierarchy — so backgrounding the app, locking the phone, or swiping
        // this screen away kills both of these, and there is no timer object
        // left anywhere that could keep either alive. `jobs.watching_until`
        // then runs out thirty seconds after the last beat, the extension
        // re-reads it before its next action, and the read ends itself.
        //
        // DO NOT "FIX" THIS INTO A BACKGROUND TASK, a BGTaskScheduler job, or a
        // Timer on `SupervisedRead`. Letting the lease lapse IS the safety
        // property — it is the whole difference between "I read it once, in the
        // front window, while you watch" being a fact about the code and being
        // a sentence in a promise list. A read that survives you looking away
        // is precisely the thing this product cannot afford: "I went through
        // your mail while you weren't looking" (`design/day-zero.md` §2, and §4
        // gate 5 — foreground and present, "the supervision, expressed as a
        // precondition").
        .task(id: driveKey) { await holdTheLease() }
        .task(id: driveKey) { await narrate() }
        // Swiped away mid-read. Cancelling the tasks alone would already end it
        // within thirty seconds; this ends it now, so nothing she finds after
        // you closed the screen can land somewhere you never saw it. The write
        // can only ever shorten a read — see `SupervisedRead.release()`.
        .onDisappear { read.release() }
        // BACKGROUNDING IS NOT LEAVING THE SCREEN, and SwiftUI does not call
        // `onDisappear` for it. Cancelling the heartbeat on the `driveKey`
        // change stops the lease being EXTENDED, but the last stamp it wrote is
        // still up to thirty seconds in the future - so locking the phone left a
        // half-minute window in which she could keep reading with nobody
        // watching. That is the exact sentence the lease exists to make
        // impossible. Found by audit, not by testing.
        //
        // `dropWatchLease` can only ever SHORTEN a read, which is why it is safe
        // to fire here on any phase change without checking which one.
        .onChange(of: scenePhase) { phase in
            if phase != .active { read.release() }
        }
    }

    // MARK: - The driver

    /// One key for both tasks: is a read running, and are you actually here.
    ///
    /// `jobID` is deliberately NOT folded in. It appears part-way through a
    /// drive, and re-keying on it would cancel the very task that had just
    /// created it.
    private var driveKey: String {
        "\(read.isReading)|\(scenePhase == .active)"
    }

    /// Push the watch lease every ten seconds, and ONLY while you are here.
    ///
    /// The guard is not belt-and-braces: `.task(id:)` restarts this closure
    /// with the NEW key whenever the phase moves off `.active`, and this is
    /// where that restart turns into a no-op instead of a background
    /// heartbeat.
    private func holdTheLease() async {
        guard read.isReading, scenePhase == .active, let reader = read.reader else { return }
        while !Task.isCancelled {
            if let id = read.jobID { await reader.hold(id) }
            // Ten seconds against a thirty-second lease: two beats may be lost
            // to a slow write before a read that is genuinely being watched
            // gets cut off.
            try? await Task.sleep(nanoseconds: 10_000_000_000)
        }
    }

    /// The read itself: create the job once, then follow her narration at the
    /// app's own three-second cadence (`AnticipyApp.swift:361`). One poll
    /// discipline for the whole product, not a second one invented here.
    private func narrate() async {
        guard read.isReading, let reader = read.reader else { return }

        // Not frontmost. If a read was running it is over — this screen stopped
        // pushing the lease the moment the phase left `.active`, so the
        // extension has already refused its next action or is about to. Coming
        // back does NOT resume it: you tap again, and she starts over in front
        // of you.
        guard scenePhase == .active else {
            read.lapse()
            return
        }

        if read.jobID == nil {
            guard let id = await reader.begin() else {
                // Plainly, in her voice, and never a spinner that waits
                // forever. It does not claim to know that Chrome is shut:
                // `agentOnline` is also false when the SERVER is unreachable,
                // so "I can't reach my end of this" is the only true version.
                read.failed("I couldn't get a read started. I can't reach my end of this right now. Give it a minute and ask me again.")
                return
            }
            read.began(jobID: id)
            // The lease must EXIST before the extension can claim the job: the
            // first thing it does is re-read `watching_until`, and with no
            // lease it refuses. So the first beat is pushed here rather than
            // waiting up to ten seconds for the heartbeat's first tick.
            await reader.hold(id)
        }
        guard let id = read.jobID else { return }

        // How much of her narration is already on screen. Append-only: she
        // narrates forward, and re-feeding a line would retype words already
        // sitting there.
        var shownLines = 0
        var shownFacts = 0
        // Polls that came back with nothing whatsoever. Chrome may never pick
        // the job up — shut, or running a stale extension — and a read that
        // silently never begins has to say so rather than breathe at you
        // forever.
        var silentPolls = 0

        while !Task.isCancelled && read.isReading {
            let (lines, facts) = await reader.poll(id)
            if lines.count > shownLines {
                for line in lines[shownLines...] { read.say(line) }
                shownLines = lines.count
            }
            if facts.count > shownFacts {
                for fact in facts[shownFacts...] {
                    withAnimation(reduceMotion ? nil : Theme.spring) { read.found(fact) }
                }
                shownFacts = facts.count
            }

            if shownLines == 0 && shownFacts == 0 {
                silentPolls += 1
                // Ten polls is thirty seconds of nothing at all coming back.
                if silentPolls >= 10 {
                    read.failed("Nothing's come back from your Chrome. Make sure it's open on your computer, then ask me again.")
                    return
                }
            }

            // The server says when a read is over, not a stopwatch here.
            if await reader.settled(id) {
                if shownLines == 0 {
                    read.failed("That never got off the ground: the read finished without reading anything. Ask me again and I'll have another go.")
                } else {
                    read.finished()
                }
                return
            }
            try? await Task.sleep(nanoseconds: 3_000_000_000)
        }
    }

    // MARK: - Header

    private var header: some View {
        HStack(alignment: .center, spacing: Theme.Space.snug) {
            LogoMark(size: 44)
                .accessibilityHidden(true)
            // The breath is the only thing that says "she is going" — a
            // listening app shows life, never a spinner.
            if read.isReading {
                // BreathingDot hides itself from VoiceOver — it is decoration
                // everywhere else. Here it is the ONLY thing saying she is
                // going, so the container carries the label instead of the
                // dot, which would otherwise be silence for a screen reader.
                BreathingDot()
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("Reading now")
            }
            Spacer()
        }
    }

    // MARK: - Before consent

    /// The ask, then the rules. A RULE LIST, never cards
    /// (`CONSUMER-FEEL-DIRECTION` §3d).
    private var consentBody: some View {
        VStack(alignment: .leading, spacing: Theme.Space.base) {
            // Not typed: this is consent copy.
            Text(source.ask())
                .font(Theme.display(28))
                .foregroundStyle(Theme.text)
                .fixedSize(horizontal: false, vertical: true)

            VStack(alignment: .leading, spacing: Theme.Space.snug) {
                ForEach(source.promises, id: \.self) { promise in
                    promiseLine(promise)
                }
            }

            if !read.hasReader {
                // No reader attached at all — the `init(read:)` path, which is
                // previews and nothing else in the shipped app. Said plainly
                // rather than shown as a dead button: a consent screen is the
                // worst place in the product to overstate what it can do
                // (`CONSUMER-READINESS` §1: "the app confidently asserts
                // things that are not true"). Not typed — it is not something
                // she is saying, it is the state of the machine.
                Text("Nothing's hooked up to this screen, so there's nothing here for me to read with.")
                    .font(Theme.aside)
                    .foregroundStyle(Theme.text2)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, Theme.Space.hair)
            }
        }
    }

    /// Why a read cannot happen, when it cannot.
    ///
    /// The one thing this screen must never do is breathe at you indefinitely
    /// while nothing happens, so every dead end sets `read.trouble` and lands
    /// here. NOT typed: an error is not a thing she is saying, and §2.7 bans
    /// the typewriter on exactly this register.
    @ViewBuilder
    private var troubleNote: some View {
        if let trouble = read.trouble {
            HStack(alignment: .top, spacing: Theme.Space.snug) {
                Rectangle()
                    .fill(Theme.alarm)
                    .frame(width: 2)
                    .accessibilityHidden(true)
                Text(trouble)
                    .font(Theme.aside)
                    .foregroundStyle(Theme.text2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: - The read itself

    private var readingBody: some View {
        ScrollViewReader { proxy in
            ScrollView(.vertical, showsIndicators: false) {
                VStack(alignment: .leading, spacing: Theme.Space.base) {
                    if read.lines.isEmpty && read.facts.isEmpty {
                        emptyState
                    }
                    narratedLog
                    if !read.facts.isEmpty { factList }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            // Follow her own words down the page. The count, not the array, so
            // a veto on a fact does not yank the log.
            .onChange(of: read.lines.count) { _ in
                guard let last = read.lines.last else { return }
                withAnimation(reduceMotion ? nil : Theme.spring) { proxy.scrollTo(last.id, anchor: .bottom) }
            }
        }
    }

    /// Honest, and short. An empty state that promises activity it cannot
    /// deliver is the same lie as a fake progress bar.
    private var emptyState: some View {
        VStack(alignment: .leading, spacing: Theme.Space.hair) {
            Text("Nothing yet.")
                .font(Theme.display(24))
                .foregroundStyle(Theme.text)
            Text(read.isReading
                 ? "Every line I read shows up here as I read it."
                 : "When I read, every line shows up here as I read it.")
                .font(Theme.aside)
                .foregroundStyle(Theme.text2)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// Her voice, typed, with the live marker at the bottom —
    /// `design/day-zero.md` §5: "a rule list with a live marker, not wizard
    /// dots." The single continuous rule it ran down is gone with the rest of
    /// the golden bars, and the marker never was the rule: it is the wave that
    /// keeps moving while she is still reading.
    private var narratedLog: some View {
        VStack(alignment: .leading, spacing: Theme.Space.snug) {
            ForEach(read.lines) { line in
                // Typed, because she is SAYING it. The one place on this
                // screen where the typewriter is allowed (§2.7).
                TypewriterText(text: line.text, font: Theme.voice, color: Theme.text)
                    .fixedSize(horizontal: false, vertical: true)
                    .id(line.id)
            }
            if read.isReading {
                WaveBars()
                    .frame(height: 12)
                    .accessibilityHidden(true)
            }
        }
    }

    /// What she concluded. Ruled entries — a serif line, a hairline under it,
    /// and a real veto target. No rounded rectangles, on purpose.
    private var factList: some View {
        VStack(alignment: .leading, spacing: Theme.Space.snug) {
            Text("WHAT I'VE GOT")
                .font(Theme.meta)
                .foregroundStyle(Theme.muted)
                .padding(.top, Theme.Space.snug)

            ForEach(read.facts) { fact in
                VStack(alignment: .leading, spacing: Theme.Space.tight) {
                    Button {
                        Haptics.engage()
                        withAnimation(reduceMotion ? nil : Theme.spring) { read.forget(fact) }
                    } label: {
                        HStack(alignment: .top, spacing: Theme.Space.snug) {
                            // Serif and 19pt: this is a conclusion, not a log
                            // line, and the type says so without a card.
                            Text(fact.text)
                                .font(Theme.display(19))
                                .foregroundStyle(Theme.text)
                                .multilineTextAlignment(.leading)
                                .fixedSize(horizontal: false, vertical: true)
                            Spacer(minLength: Theme.Space.snug)
                            // Destructive, so the word keeps `alarm` — the
                            // geometry is the same glass as everything else.
                            Text("FORGET")
                                .font(Theme.meta)
                                .foregroundStyle(Theme.alarm)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    // A row, not a pill: `ghostRow` keeps the serif line on
                    // the column's own left edge.
                    .ghostRow()
                    .accessibilityLabel(fact.text)
                    .accessibilityHint("Wrong? Double tap and I'll forget it.")
                    // The rule lives OUTSIDE the control so it spans the
                    // column rather than the pill.
                    Rectangle()
                        .fill(Theme.edge)
                        .frame(height: 1)
                }
                .transition(.opacity)
            }

            if !read.forgotten.isEmpty {
                // Not an apology and not a toast that steals focus — a count,
                // in the register counts belong in.
                Text(read.forgotten.count == 1
                     ? "Forgot one."
                     : "Forgot \(read.forgotten.count).")
                    .font(Theme.meta)
                    .foregroundStyle(Theme.muted)
            }
        }
    }

    // MARK: - The standing promise

    /// Visible the whole time, in both states, and NEVER typed: it is consent
    /// copy, and somebody deciding whether to let her into their mail should not
    /// be made to wait for the sentence to finish appearing (§2.7).
    /// `design/PREMIUM-FEEL.md:135` fixes the words. It used to stand beside a
    /// 2px accent rule; with the golden bars out of the product the sentence
    /// carries itself, in her voice at full strength while everything around
    /// it is aside grey.
    private var promiseBand: some View {
        Text("I read. I never send. Ever.")
            .font(Theme.voice)
            .foregroundStyle(Theme.text)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: - Actions

    @ViewBuilder
    private var actions: some View {
        if read.isReading {
            // Stop is the primary control while she is going: the supervision
            // is only real if the person watching can end it mid-sentence.
            Button {
                read.stop()
            } label: {
                Text("Stop")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.glass)
        } else if granted {
            finishedActions
        } else if read.hasReader {
            Button {
                // The grant is recorded BEFORE anything reads — the gate is
                // deterministic code, not a prompt (`CLAUDE-ONBOARDING.md:19-20`).
                grants.grant(source)
                granted = true
                Haptics.engage()
                read.start()
            } label: {
                Text("Open my mail while I watch")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.glass)
            .accessibilityHint("Opens your mail in your browser and reads it once while you watch.")
            secondary("Not now") { dismiss() }
        } else {
            // No reader: there is nothing to press. Leaving is the only action,
            // and leaving records NOTHING — a skip is never a fact about the
            // person (`design/briefs/08-day-zero.md:30`).
            secondary("Close") { dismiss() }
        }
    }

    @ViewBuilder
    private var finishedActions: some View {
        // Granted, not running. FOUR different things end a read and the line
        // has to say which, because "done" over a read that lapsed, failed, or
        // was killed halfway is the app telling a small lie about what just
        // happened.
        //
        // `trouble` already has its own sentence in `troubleNote`, so this says
        // nothing on top of it — two explanations of one dead end read as the
        // app not knowing what happened either.
        if read.trouble == nil {
            Text(read.lapsed
                 ? "I stopped when you looked away. That's the deal. Tap again and I'll start over while you're here."
                 : read.wasStopped
                   ? "Stopped. I kept what you watched me find."
                   : read.facts.isEmpty
                     ? "Nothing read yet."
                     : "That's one pass. I'll keep it to that until you ask again.")
                .font(Theme.aside)
                .foregroundStyle(Theme.text2)
                .fixedSize(horizontal: false, vertical: true)
        }

        if read.hasReader {
            secondary("Read it again") {
                Haptics.engage()
                read.start()
            }
        }
        secondary("Done") { dismiss() }
    }

    /// A skip or a close at a real size (`design/PREMIUM-FEEL.md:45`). Full
    /// width, because it stacks under a full-width primary; the style owns the
    /// 44pt target and the frosted press.
    private func secondary(_ title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .frame(maxWidth: .infinity)
        }
        .buttonStyle(.ghost)
    }

    /// One promise, one line. It was a hairline in the accent with the sentence
    /// beside it, the gesture `ContextAskSheet` also used; the hairline is gone
    /// from both, so the list is held by space alone — still a rule list, never
    /// cards (`CONSUMER-FEEL-DIRECTION` §3d).
    private func promiseLine(_ text: String) -> some View {
        Text(text)
            .font(Theme.aside)
            .foregroundStyle(Theme.text2)
            .fixedSize(horizontal: false, vertical: true)
    }
}

#if DEBUG
/// Previewable with no extension, no server and no account. `PreviewProvider`
/// rather than the `#Preview` macro because the deployment floor is iOS 16.
struct SupervisedReadView_Previews: PreviewProvider {
    static var previews: some View {
        // 1. No reader attached: no start button, and the screen says why
        //    rather than offering a control that cannot work.
        SupervisedReadView(read: SupervisedRead())
            .previewDisplayName("No reader")

        // 2. What a read looks like, driven by hand. The lines and facts are
        //    written HERE, in a preview, and nowhere in shipping code — the
        //    view never invents either.
        SupervisedReadView(read: midRead())
            .previewDisplayName("Mid-read")

        // 3. The dead end. Every unreachable case ends up here, never as a
        //    spinner that waits forever.
        SupervisedReadView(read: unreachable())
            .previewDisplayName("Can't reach it")
    }

    /// `SupervisedRead` is main-actor isolated, like every other observable in
    /// this app, and `PreviewProvider` is itself `@MainActor` — so the helpers
    /// have to say so or they cannot touch the object they are building.
    @MainActor
    private static func midRead() -> SupervisedRead {
        let read = SupervisedRead(reader: inert())
        read.began(jobID: "preview")
        read.say("Opening your mail.")
        read.say("Reading the last few subject lines, not the messages.")
        read.found("Marcus Bell is a client; a proposal is in flight.")
        read.say("You and Priya have been going back and forth about Thursday.")
        return read
    }

    @MainActor
    private static func unreachable() -> SupervisedRead {
        let read = SupervisedRead(reader: inert())
        read.failed("Nothing's come back from your Chrome. Make sure it's open on your computer, then ask me again.")
        return read
    }

    /// A reader that exists and does nothing. Enough to make `hasReader` true
    /// so the previews show the buttons a real session shows; it reaches no
    /// network, which is what makes these previews run at all.
    private static func inert() -> SupervisedReader {
        SupervisedReader(begin: { nil },
                         hold: { _ in },
                         poll: { _ in ([], []) },
                         settled: { _ in false },
                         drop: { _ in },
                         forget: { _, _ in })
    }
}
#endif
