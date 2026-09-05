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

    /// Which execution surface owns the stored lane. This reads a typed lane
    /// value; it never infers an action from the goal's prose. Calendar work
    /// runs in the phone's contained EventKit hand and must not be presented as
    /// Chrome work merely because it is not a research row.
    var executionSurfaceLabel: String {
        switch CalendarHandPolicy.normalizedLane(lane) {
        case "research": return "Hand 2 · Research service"
        case CalendarHandPolicy.lane: return "This iPhone · Calendar"
        default: return "Hand 1 · Browser"
        }
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

// ANCHOR: home feed placement

/// Where a job belongs on Home, and what a called-off card leads with.
///
/// THE SECTION A JOB LANDS IN USED TO BE THREE SEPARATE `filter` CLOSURES, and
/// between them they named five of the six statuses a row can hold.
/// `cancelled` — the status BOTH `session.decline` and `session.stopRunning`
/// write (`AnticipyApp.swift`) — matched none of them. So a job the owner
/// stopped left the screen entirely the moment the write landed, which reads
/// exactly like the tap having worked. What it actually did was delete the only
/// account of what happened from the only place a person reads.
///
/// That mattered most in the one case this product exists to get right. A stop
/// on a run that may already have committed something writes "It may already
/// have gone through before I stopped. Worth a check." into `result` — and the
/// same PATCH writes `effect_uncertain: false` (`cancellationFields`), so
/// `JobReceiptPolicy.safetyLine` answers the reassuring "Nothing you told me
/// was lost." `result` is the ONLY surviving carrier of that warning, and it
/// was being carried to a card that rendered nowhere at all. docs ex 36 / ex
/// 50: the duplicate booking nobody checks for is the cardinal sin here.
///
/// Pure Foundation, and anchored so `Tests/run_home_feed_tests.sh` compiles the
/// REAL source rather than a copy of it. A copy is honest only until somebody
/// edits one side.
enum HomeFeedPolicy {
    /// The four places a row can be on Home. `hidden` is an answer, not a
    /// default: a supervised read is a job the person is sitting there
    /// watching, and it must never also appear under "Waiting for your browser"
    /// as though it were stalled.
    enum Placement {
        case needsYou
        case handling
        case done
        case hidden
    }

    /// ATTENTION IS DECIDED BEFORE THE LANE IS, and that ordering is the
    /// shipping behaviour rather than a preference. `needsOK` never consulted
    /// `isErrand`, so a supervised read that stopped and asked for something
    /// has always been given a card here. Testing the lane first would take
    /// that card away from the two statuses that cannot afford to lose it.
    static func placement(status: String, lane: String?) -> Placement {
        switch status {
        case "awaiting_confirm", "needs_user": return .needsYou
        default: break
        }
        if lane == "supervised_read" { return .hidden }
        switch status {
        case "queued", "running": return .handling
        // `cancelled` files with `done` and `failed` because it is TERMINAL,
        // not because it succeeded. That section has meant "finished with, one
        // way or another" since failures started rendering under it, and the
        // card says which of the three this one was.
        case "done", "failed", "cancelled": return .done
        // A status nobody here has heard of. Silence beats filing it under a
        // heading that would then be claiming something about it.
        default: return .hidden
        }
    }

    /// It was stopped before it finished. NOT "the owner stopped it" — see
    /// `calledOffKicker`: the brain writes this status too, on cards he was
    /// never shown. One answer, here, because three places now ask it: the card
    /// that draws it, the cap that must not cut it, and the runner that checks
    /// both.
    static func wasCalledOff(status: String) -> Bool { status == "cancelled" }

    /// Whether Done's cap is allowed to cut this card.
    ///
    /// "Done" is drawn newest-CREATED first and capped, and both of those are
    /// about when a job STARTED. Nothing on the row says when it ENDED —
    /// `AgentJob` decodes `created` and no other timestamp — so an errand begun
    /// this morning and stopped this evening sorts below every job that began
    /// and finished in between, and the cap cuts it. While cancellations
    /// rendered nowhere at all that cost nothing. Now the cap is the last thing
    /// standing between "it may already have gone through" and the person who
    /// needs to read it: the same silence the section fix was written to end,
    /// arriving one step later through the display instead of the filter.
    ///
    /// So the cap counts SETTLED cards, and a card still asking the reader to
    /// go and check something out in the world is drawn however old it is.
    /// There are two shapes of that, both read off the row's own fields and
    /// never off its words:
    ///
    ///   * a cancellation — because this card can never tell a decline of a
    ///     plan that never ran from a decline of a run that stopped partway.
    ///     `decline` clears `effect_uncertain` on its way out and writes no
    ///     `result`, so the two arrive here indistinguishable and the card is
    ///     not entitled to assume the harmless one; and
    ///   * a failure the row ITSELF still marks uncertain, where
    ///     `JobReceiptPolicy.safetyLine` answers "It may already have gone
    ///     through … so you don't end up with two." That one was droppable
    ///     before any of this and is the same defect wearing a different
    ///     status, which is why it is named here rather than left for the next
    ///     reviewer to find.
    ///
    /// This is a cap rule and nothing else. It can only ever ADD a card that
    /// would have been dropped, it draws it in the same newest-first position
    /// it would have held anyway, and it grades, counts and colours nothing.
    static func settled(status: String, effectUncertain: Bool?) -> Bool {
        if wasCalledOff(status: status) { return false }
        return effectUncertain != true
    }

    /// WHICH OF DONE'S ROWS ARE ACTUALLY DRAWN, by index, in the order given.
    ///
    /// The walk lives here and not in the view, and that is not tidiness.
    /// `settled` is a predicate about ONE row; the defect it guards is about a
    /// walk over many, and the one-word version of that walk going wrong —
    /// leaving the scan at the shelf's edge instead of stepping past it —
    /// drops the exact card the rule exists to keep while every predicate in
    /// the file still answers correctly. That mutation survived this suite
    /// until the walk became a function with cases behind it. A rule nothing
    /// can prove wrong is not a rule.
    ///
    /// `rows` arrives newest-CREATED first and the answer keeps that order:
    /// everything past the shelf is older than everything on it, so a survivor
    /// lands exactly where newest-first would have put it, at the bottom.
    /// The shelf counts SETTLED rows only. Nothing is promoted, reordered,
    /// marked or counted out loud.
    static func shelved(_ rows: [(status: String, effectUncertain: Bool?)],
                        shelf: Int) -> [Int] {
        var drawn: [Int] = []
        var used = 0
        for (i, row) in rows.enumerated() {
            if settled(status: row.status, effectUncertain: row.effectUncertain) {
                // SKIP, NEVER STOP. What is being looked for past the shelf's
                // edge is precisely the old cancellation nothing else on this
                // screen will mention, and it is down there because it is old,
                // which is the same reason a stop would never reach it.
                if used >= shelf { continue }
                used += 1
            }
            drawn.append(i)
        }
        return drawn
    }

    /// THE CARD'S OWN IDENTITY, said by the card and not by the server.
    ///
    /// The card used to be identified only by what `result` happened to hold,
    /// and on the "Don't do it" path `result` holds whatever the ENGINE wrote
    /// before the tap — `decline` (`AnticipyApp.swift`) writes the cancellation
    /// fields and never touches `result`. So a stuck job carrying "I may have
    /// already sent that … check the site before I try again" was cancelled and
    /// then rendered under "Done" still leading with an offer to try again,
    /// with no sentence anywhere saying the owner had stopped it. Now the card
    /// says what it is first, in the same caption treatment `ConfirmJobCard`
    /// uses for "Your exact words", and the server's words follow it verbatim.
    ///
    /// IT NAMES NO ACTOR, and that is the whole of the wording. The obvious
    /// line here is "You called this off", and it is false on rows the owner
    /// never touched. `cancelled` is not the owner's word: `_cancel_job`
    /// (`brain/anticipy_core.py`) writes it to take a card off the desk that he
    /// was NEVER TOLD ABOUT — "I picked this up from the room rather than from
    /// you, so I've dropped it", "she was not allowed to raise this" — and the
    /// extension writes it when a run spends its last attempt. Telling somebody
    /// they cancelled a thing they were never shown is the same false claim as
    /// telling them nothing happened when it might have, printed the other way
    /// round.
    ///
    /// "Stopped" is true of every one of them: the phone's "Don't do it", Stop
    /// on a running job, the two endings `AnswerRoutePolicy` routes here, the
    /// stop from the Chrome popup, the brain's own drop, and a run out of
    /// attempts. It says the card's state and leaves WHO to the sentence
    /// underneath, which is the one place that actually knows. It never
    /// overrides what came back; it sits above it.
    static let calledOffKicker = "Stopped"

    /// What a called-off card leads with, under that kicker.
    ///
    /// THE ENGINE'S OWN WORDS FIRST, never a sentence composed here about them.
    /// ex 126 forbids paraphrasing what came back, and on this card the words
    /// that came back are the warning: "You stopped this. It may already have
    /// gone through before I stopped. Worth a check."
    ///
    /// The fallback is reachable only when the server wrote nothing — the
    /// "Don't do it" path again, where `decline` writes no result at all.
    ///
    /// IT USED TO READ "You called this off. I didn't do it." AND THAT IS A
    /// SENTENCE THIS CARD CANNOT SAY. "Don't do it" is offered on two statuses,
    /// and they are not the same event. `awaiting_confirm` is a plan waiting
    /// for a yes, where nothing has run. `needs_user` is a run that STOPPED
    /// PARTWAY and asked for something, and it can carry `effect_uncertain`:
    /// `extension/background.js` promotes exactly that combination, and
    /// `ConfirmJobCard` prints "Only continue if the action did not happen."
    /// over it. Tapping "Don't do it" there PATCHes `effect_uncertain: false`
    /// with no result and no reconciliation record, so by the time this card
    /// renders the row has lost the one field that said the effect was in
    /// doubt — and the two statuses are indistinguishable, both now `cancelled`.
    /// A flat "I didn't do it" over that is the duplicate booking of ex 36 with
    /// a denial printed on it.
    ///
    /// So the fallback claims only what this app can still see: after your tap,
    /// it did nothing more. That is the house's own sentence for this act —
    /// `AnticipyApp.swift` already ends an errand with "I did nothing further."
    /// — and it neither denies nor invents a warning the phone never measured,
    /// which is the standing rule for naming a loss on this screen.
    ///
    /// The real repair is one line up the stack and is NOT in this file:
    /// `decline` should write a `result` the way `stopRunning` already does,
    /// branching on `job.effect_uncertain` BEFORE it clears it. Until it does,
    /// this is the most the card is entitled to say.
    static func calledOffLead(result: String?) -> String {
        let said = (result ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return said.isEmpty ? "I did nothing further." : said
    }

    /// Whether Home says out loud that there is no way to reach this person.
    ///
    /// The sentence itself is old; where it was said is the defect. It lived
    /// inside `if !handling.isEmpty`, so it reached only people who ALREADY had
    /// errands stuck — while the comment sitting above it argued the opposite
    /// case in capitals: an unreachable customer never finds out they are
    /// unreachable. An account with no number gets asked nothing, ever, so it
    /// never accumulates the stuck work that was the condition for being told.
    ///
    /// THE ACCOUNT ANSWERS THIS, NOT THE MIRROR. `PhoneState` is unknown until a
    /// canonical owner read succeeds, then distinguishes an absent number from
    /// a malformed one and from one that passed the same E.164 rule used when
    /// saving. Home speaks only for the explicit `.none` answer.
    static func sayUnreachable(phoneState: OwnerMirror.PhoneState) -> Bool {
        phoneState == .none
    }

    /// Whether a completed brain event deserves its own recap card. A worker
    /// emits `job-result:<job id>` after completing an ordinary job; when that
    /// exact terminal job is already in the visible Done deck, rendering both
    /// records makes one outcome look like two pieces of work.
    ///
    /// Only the exact namespace is interpreted. Older events without an id,
    /// unrelated external ids, and job results whose terminal card is not on
    /// the current shelf all remain visible.
    static func showsDoneEvent(externalEventID: String?,
                               visibleTerminalJobIDs: Set<String>) -> Bool {
        let prefix = "job-result:"
        guard let externalEventID,
              externalEventID.hasPrefix(prefix) else { return true }
        let jobID = String(externalEventID.dropFirst(prefix.count))
        guard !jobID.isEmpty else { return true }
        return !visibleTerminalJobIDs.contains(jobID)
    }
}

// END ANCHOR: home feed placement

// ANCHOR: home card copy

/// The sentences on Home whose truth depends on a COUNT or on a MEASUREMENT.
///
/// They were written inline in three view bodies until two of them were caught
/// saying the wrong number out loud. The browser card asked for two minutes of
/// somebody's afternoon and never named what was waiting on the other side of
/// it. The interview card opened "Six questions" — the numeral typed into the
/// prose — so a person who had already answered three was told there were six,
/// and nothing on the phone could tell it otherwise. A sentence with a number
/// in it is a claim, and a claim belongs where a test can call it.
///
/// Pure Foundation, and anchored so `Tests/run_home_copy_tests.sh` compiles
/// THIS source rather than a copy of these strings — a copy is honest only
/// until somebody edits one side. The counts arrive as arguments instead of
/// being read from `InterviewProgress` or `session.jobs` here, for the same
/// reason `PlainDuration` takes an `Int`: the numbers stay the caller's, the
/// wording stays here, and the runner needs neither a simulator nor a defaults
/// database to ask what a card will say.
///
/// NO THRESHOLD LIVES HERE, AND NONE MAY. Nothing on this page decides that a
/// queue is long or a silence has gone on too far; every sentence names what
/// the phone counted and stops. `ListeningDiagnosticsView.swift:38-43` is the
/// argument these sit inside — "a phone that has heard nothing for eleven hours
/// and a phone that has heard nothing for four minutes both say so, and the
/// reader judges" — and it is why there is no badge, no meter, no percentage
/// and no colour anywhere below.
enum HomeCopy {

    // MARK: The browser ask

    /// Whose Chrome, and how many things are standing in it.
    ///
    /// `waiting` cannot be zero: the card renders only under
    /// `!browserHandling.isEmpty`, which is also `browserOffer`'s own condition.
    static func browserHeadline(waiting: Int) -> String {
        waiting == 1 ? "This one needs your Chrome" : "These need your Chrome"
    }

    /// The cost and the payoff in one breath.
    ///
    /// The cost half is kept from the onboarding step this card replaces,
    /// because it was the honest version: no password, a computer, one setting,
    /// two minutes. Naming what she will NOT do is the rule
    /// (`design/PREMIUM-FEEL.md:43-47`), so "I never ask for a password"
    /// survives verbatim.
    ///
    /// What it lacked was the other side of the trade. Four costs and no payoff
    /// reads as a chore, and the thing being bought was sitting three inches
    /// below the card the whole time — so the queue joins the sentence that
    /// asks for the two minutes. QUEUE DEPTH AND NOTHING ELSE: no elapsed time,
    /// no "stalled", no countdown, no urgency the phone did not measure.
    static func browserBody(waiting: Int) -> String {
        // Singular gets its own tail rather than a spliced-in noun. "The thing
        // below starts moving on their own" is what one shared ending produces,
        // and a sentence that does not parse is a sentence nobody trusts.
        let payoff = waiting == 1
            ? "the thing below starts moving on its own"
            : "the \(waiting) things below start moving on their own"
        return "I work inside your own Chrome, using the accounts you're already signed in to. "
            + "I never ask for a password. Two minutes on a computer, once — and \(payoff). "
            + "There's one Chrome setting to flip; the guide shows you where."
    }

    /// What the tap buys, still legible with a thumb over the card.
    ///
    /// "Set it up" alone is a chore with no object. The count is the same one
    /// the headline and the body branch on, from the same argument, so the
    /// three cannot disagree.
    static func browserButton(waiting: Int) -> String {
        "Set it up — \(waiting) waiting"
    }

    // MARK: The interview ask

    /// Whether she is asking to start or asking to finish.
    static func interviewTitle(answered: Int) -> String {
        answered == 0 ? "Want me to actually know you?" : "Want me to know the rest?"
    }

    /// What she already holds, said before what she still wants.
    ///
    /// Home used to gate on `!isComplete` alone and then describe the whole
    /// script, so somebody who had sat through three answers was told there
    /// were six questions — the work counted for nothing on the one screen that
    /// asks for more of it. Settings had the sentence right at
    /// `SettingsView.swift:893` ("You've answered 4 of 6") and Home ignored it.
    ///
    /// A COUNT OF REAL WORK, NOT OF ATTEMPTS. A skip records nothing at all
    /// (`Interview.swift:113-118`), so a skipped question is simply still open
    /// and cannot inflate this. No percentage, no meter, no bar: two counts and
    /// the sentence they belong to.
    static func interviewBody(answered: Int, total: Int) -> String {
        guard answered > 0 else {
            // Character-for-character what this card has always opened with,
            // save for where the numeral comes from — see `spelledOut`.
            return "\(spelledOut(total)) questions, in your words. I ask, you answer or skip. "
                + "I never send anything on your behalf without your yes."
        }
        return "You've answered \(answered) of \(total). I've kept them. The rest are still open — "
            + "I ask, you answer or skip. I never send anything on your behalf without your yes."
    }

    /// How much is left, on the button that spends it.
    static func interviewButton(answered: Int, total: Int) -> String {
        answered == 0 ? "Ask me" : "Ask me — \(max(0, total - answered)) left"
    }

    /// A count at the head of a sentence, in words.
    ///
    /// "Six questions, in your words" was typed, so the day a seventh question
    /// ships the card goes on saying six at a script that no longer holds six.
    /// Spelling it from `InterviewQuestion.script.count` leaves the sentence
    /// identical to the character today and wrong on no day after.
    ///
    /// Words here and digits everywhere else on this card is not an
    /// inconsistency: "You've answered 4 of 6" is a measurement of two counts
    /// against each other, and this is prose opening a sentence. Digits past
    /// twelve, where English stops being the shorter way to say it.
    static func spelledOut(_ n: Int) -> String {
        let words = ["Zero", "One", "Two", "Three", "Four", "Five", "Six",
                     "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve"]
        return n >= 0 && n < words.count ? words[n] : "\(n)"
    }

    // MARK: The microphone, taken away

    /// "Taking it back" — and, when the phone measured it, how long it has
    /// heard nothing.
    ///
    /// When iOS takes the microphone and the watchdog never gets it back,
    /// `suspended` stays true and `isListening` stays true
    /// (`PhoneListener.swift:86`, `:457-460`), so this line claimed a recovery
    /// in the present tense for the rest of the day and read the same at four
    /// seconds as at four hours. Something the phone measured belongs in it,
    /// and there is exactly one such number to hand: `ListenTally.unheardForSeconds`.
    ///
    /// IT IS NOT THE AGE OF THE INTERRUPTION, and that is why the wording this
    /// audit prescribed — "Mic interrupted 6 hr 20 min ago, still trying to
    /// take it back. I've missed that stretch." — is refused here rather than
    /// shipped. `ListenTally` folds the number as `end - lastHeardAt`
    /// (`ListenTally.swift:318`), and `lastHeardAt` moves on a FLUSH, never on
    /// a non-owner stop: `:231-237` leaves it deliberately where it was, "AND
    /// THE CLOCK KEEPS RUNNING… Moving `lastHeardAt` here is what answered
    /// '58 min' for a day that heard nothing after nine". So on a night that
    /// started at ten, last heard a word at eleven and lost the microphone at
    /// eight the next morning, this arrives as 9 hr 2 min TWO MINUTES after the
    /// interruption. "Interrupted 9 hr 2 min ago" is wrong by nine hours, and
    /// "I've missed that stretch" bills a loss for eight hours that were heard
    /// and merely silent. The error has one direction — the value is always at
    /// least the interruption's age and unbounded above it — so the sentence
    /// could only ever overstate. A loss the phone did not measure is the one
    /// thing this audit's own "What NOT to do" forbids outright, and an
    /// overstatement is not made honest by being a caption.
    ///
    /// SO THE NUMBER IS SAID UNDER ITS TRUE LABEL, which the house already
    /// owns: `UnheardLine.words` under the Settings listening row, and the
    /// "Nothing heard for" row on the diagnostics screen. Not house style for
    /// its own sake — both of those rest their whole refusal to give a verdict
    /// on the screens "wording the same seconds the same way", and this card is
    /// the third screen reading the same field. Cited by SYMBOL and not by line
    /// because the Settings half moved into a type the same week this was
    /// written; the fragment "Nothing heard for " + `PlainDuration.words` is
    /// what the three of them actually share, and `HomeCopyTests` pins this
    /// side of it so a rewording here cannot pass unseen.
    ///
    /// NOT YET ONE CALL, and that is a choice with a cost. Home could ask
    /// `UnheardLine.words` outright, which would make drift impossible rather
    /// than merely visible. It does not, because `UnheardLine` lives inside
    /// SettingsView.swift and this suite lifts `HomeCopy` out and compiles it
    /// against Foundation and `PlainDuration` alone — reaching into a second
    /// screen's file would couple Home's green to edits nobody here can see.
    /// Worth unifying once both sides have settled.
    ///
    /// The recovery clause keeps the words it always had, because "taking it
    /// back…" is the one thing on this line that is true of what the app is
    /// doing at the moment it is read.
    ///
    /// NIL IS AN ANSWER, and it is the common one. The caller passes a gap only
    /// when the journal ends in an interruption with time on it; `.unknown` is
    /// a record with no session line in it at all, and a duration invented for
    /// that case would be a number about nothing. So the sentence that ships
    /// today survives verbatim as the thing said whenever the phone cannot say
    /// more.
    ///
    /// NO THRESHOLD AND NO VERDICT: "4 min" and "6 hr 20 min" are the same
    /// sentence with a different measurement in it, and neither is coloured,
    /// ranked or called too long. `PlainDuration` is asked for the words so the
    /// three screens now reporting this same stretch cannot word it three ways.
    static func micInterrupted(unheardForSeconds seconds: Int?) -> String {
        guard let seconds = seconds, seconds > 0 else { return "Mic interrupted, taking it back…" }
        return "Mic interrupted, taking it back… Nothing heard for \(PlainDuration.words(seconds))."
    }

    // MARK: The empty state's examples

    /// The two fixture strings the day-zero screen draws, and the one sentence
    /// that reads them back.
    ///
    /// The example pair was `accessibilityHidden(true)`, so a first-timer using
    /// VoiceOver got the promise — what she listens for — and no sample at all
    /// of what arrives. The label is built FROM the fixtures rather than
    /// alongside them: a hand-written copy of these two sentences would go
    /// stale the first time somebody edited the cards, and a VoiceOver user
    /// would then be read a screen that is not on the screen.
    static let exampleHeard = "I'll get that invoice over to you tonight"
    static let exampleGoal = "Draft the invoice email to Devon"
    static var exampleCardsLabel: String {
        "Example. When I catch something it looks like this. "
            + "Heard: \(exampleHeard). Ready: \(exampleGoal)."
    }
}

// END ANCHOR: home card copy

/// Home = the proactive feed: what Anticipy heard, what it's handling,
/// what needs your OK, and what's done — plus live connection health.
struct HomeView: View {
    @EnvironmentObject var pendant: PendantManager
    @EnvironmentObject var session: AnticipySession
    @Environment(\.scenePhase) private var scenePhase
    @State private var typedLine = ""
    /// Reachability is owned by the session's canonical account read. A cached
    /// phone string cannot distinguish not-yet-read, absent, malformed, and
    /// valid, and must not make notification promises on its own.
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
    /// WHEN the phone last heard anything, if the record ends in an
    /// interruption and only then — an instant, not a count of seconds, and
    /// that difference is the whole of it.
    ///
    /// This held the elapsed seconds, read once and then drawn unchanged for as
    /// long as the screen stayed up. `readInterruptionGap` is keyed on
    /// `"\(suspended)|\(scenePhase)"`, and through an outage both halves are
    /// constant, so nothing re-ran it: somebody on speakerphone with Anticipy
    /// open read the same "4 min" at minute forty. A duration captured once and
    /// then stated as now is the exact defect this line was rewritten to end,
    /// and it does not stop being that defect because it is the caption rather
    /// than the headline.
    ///
    /// AN INSTANT CANNOT GO STALE. The subtraction happens in `interruptedGap`,
    /// where the label is drawn, against `Date()` — so every redraw re-reads it
    /// for one subtraction and NO DISK AT ALL, and `AnticipyApp.startPolling`
    /// republishes `backendReachable` every three seconds whether or not it
    /// changed. That is how the number keeps moving while
    /// `readInterruptionGap`'s "never on the poll" rule stays exactly as
    /// strict as it was.
    ///
    /// Nil is the ordinary value and the honest one: nothing measured, nothing
    /// said — see `readInterruptionGap` for why this is `@State` filled by a
    /// task rather than read where it is drawn.
    @State private var heardNothingSince: Date?
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
        // WHAT SHE ALREADY HOLDS, read once for the whole card. The gate above
        // asks only whether anything is left (`!isComplete`), so this card
        // described the entire script to somebody who had already sat through
        // half of it. Three separate reads — one per sentence — is how a title
        // and a button come to disagree about the same defaults key.
        let answered = InterviewProgress().answeredCount
        let total = InterviewQuestion.script.count
        return VStack(alignment: .leading, spacing: Theme.Space.snug) {
            Text(HomeCopy.interviewTitle(answered: answered))
                .font(Theme.display(24))
                .foregroundStyle(Theme.text)
                .fixedSize(horizontal: false, vertical: true)
            Text(HomeCopy.interviewBody(answered: answered, total: total))
                .font(Theme.aside)
                .foregroundStyle(Theme.text2)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: Theme.Space.snug) {
                Button {
                    Haptics.engage()
                    showInterview = true
                } label: {
                    Text(HomeCopy.interviewButton(answered: answered, total: total))
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
        verified && !session.agentPaired && !browserOfferDeferred
            && !browserHandling.isEmpty
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
        // The queue this card is standing over, counted once. Three sentences
        // branch on it — the headline's grammar, the body's payoff and the
        // button's label — and they are one question, so they ask it once and
        // in one place (`HomeCopy`).
        let waiting = browserHandling.count
        return VStack(alignment: .leading, spacing: Theme.Space.snug) {
            Text(HomeCopy.browserHeadline(waiting: waiting))
                .font(Theme.display(24))
                .foregroundStyle(Theme.text)
                .fixedSize(horizontal: false, vertical: true)
            // The costs are kept from the onboarding step this replaces,
            // because that was the honest version: no password, a computer,
            // one setting, two minutes. Naming what she will NOT do is the
            // rule (`design/PREMIUM-FEEL.md:43-47`). What the sentence lacked
            // was the other side of the trade — see `HomeCopy.browserBody`.
            Text(HomeCopy.browserBody(waiting: waiting))
                .font(Theme.aside)
                .foregroundStyle(Theme.text2)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: Theme.Space.snug) {
                NavigationLink { SettingsHomeView() } label: {
                    Text(HomeCopy.browserButton(waiting: waiting))
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
    private var needsOK: [AgentJob] {
        session.jobs.filter { HomeFeedPolicy.placement(status: $0.status, lane: $0.lane) == .needsYou }
    }
    /// Finished quiet work — anticipy_says events the brain marked done.
    /// Newest first, capped so the desk never becomes a landfill.
    private var foundForYou: [BrainEvent] {
        let visibleTerminalJobIDs = Set(finishedShown.map(\.id))
        let done = session.anticipySays.filter { ev in
            ev.kind == "anticipy_says" && ev.decision == "done"
                && (ev.text?.isEmpty == false)
                && HomeFeedPolicy.showsDoneEvent(
                    externalEventID: ev.external_event_id,
                    visibleTerminalJobIDs: visibleTerminalJobIDs)
        }
        return Array(done.prefix(5))
    }

    /// The briefing's newest conversational line. Job-result events already
    /// represented by a visible Done card are filtered by the same policy as
    /// Found for You, so the top briefing cannot become a second copy.
    private var freshAnticipyLine: String? {
        guard let event = session.freshAnticipyEvent,
              HomeFeedPolicy.showsDoneEvent(
                externalEventID: event.external_event_id,
                visibleTerminalJobIDs: Set(finishedShown.map(\.id))) else { return nil }
        return event.text
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
    private var handling: [AgentJob] {
        session.jobs.filter { HomeFeedPolicy.placement(status: $0.status, lane: $0.lane) == .handling }
    }
    /// Only these rows actually depend on Chrome. Research and the contained
    /// calendar executor are also handling rows, but telling either of them to
    /// open Chrome would be a false recovery path.
    private var browserHandling: [AgentJob] {
        handling.filter {
            let lane = CalendarHandPolicy.normalizedLane($0.lane)
            return lane != "research" && lane != CalendarHandPolicy.lane
        }
    }
    /// Terminal work: done, failed, AND called off.
    ///
    /// This read `done || failed` and nothing else, so every cancellation fell
    /// through all three sections and rendered nowhere — including the one
    /// carrying "it may already have gone through, worth a check". No backend
    /// work was needed to fix it: `fetchJobs` applies no status filter, so those
    /// rows have been sitting in `session.jobs` the whole time, matching
    /// nothing. One question, one answer, in `HomeFeedPolicy` — three closures
    /// naming statuses by hand is how a status came to match none of them.
    private var finished: [AgentJob] {
        session.jobs
            .filter { HomeFeedPolicy.placement(status: $0.status, lane: $0.lane) == .done }
            .sorted { ($0.updated ?? $0.created) > ($1.updated ?? $1.created) }
    }
    /// How much of Done is a shelf. Eight is what this section has always
    /// drawn; naming it is the only change to the number.
    private static let doneShelf = 8
    /// Done as it is actually drawn — the shelf, plus every card the shelf is
    /// not allowed to swallow.
    ///
    /// `finished` is newest-UPDATED first. PocketBase's update timestamp moves
    /// when a job settles, so the shelf now follows when work ended; legacy
    /// rows fall back to their creation time. The policy below still preserves
    /// every unsettled terminal result even beyond the ordinary shelf.
    ///
    /// The order is untouched: everything past the shelf is older than
    /// everything on it, so what survives lands exactly where newest-first
    /// would have put it, at the bottom. Nothing is promoted, nothing is
    /// marked, and a person with no unsettled work sees the same eight cards
    /// they saw before.
    /// Bound once, because `finished` recomputes off `session.jobs` on every
    /// read and the answer below is a list of INDEXES into the list it was
    /// asked about.
    private var finishedShown: [AgentJob] {
        let rows = finished
        let keep = HomeFeedPolicy.shelved(
            rows.map { (status: $0.status, effectUncertain: $0.effect_uncertain) },
            shelf: Self.doneShelf)
        return keep.map { rows[$0] }
    }

    /// A recap may use only meaning the brain explicitly stamped. The person's
    /// raw words stay in Settings; Home gets at most three goal titles from
    /// conversations that were actually classified as asking or acting.
    private var recentConversationInsights: [HomeConversationInsight] {
        var seen = Set<String>()
        var rows: [HomeConversationInsight] = []
        for group in HeardGroup.build(session.transcript).reversed()
            where group.weight >= .acting {
            guard let title = group.latestGoalTitle else { continue }
            let key = title.lowercased()
            guard seen.insert(key).inserted else { continue }
            rows.append(HomeConversationInsight(
                id: group.id,
                title: title,
                state: "Recent conversation"))
            if rows.count == 3 { break }
        }
        return rows
    }

    /// Nothing to show at all. WHY there's nothing is a separate question, and
    /// the answer decides which of four very different screens you get.
    private var feedIsEmpty: Bool {
        needsOK.isEmpty && openQuestions.isEmpty && handling.isEmpty
            && finished.isEmpty && foundForYou.isEmpty
            && recentConversationInsights.isEmpty
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
                        if verified && !recentConversationInsights.isEmpty {
                            sectionHeader("Insights")
                                .padding(.top, Theme.Space.section)
                                .padding(.bottom, Theme.Space.tight)
                            HomeInsightsCard(
                                items: recentConversationInsights,
                                needsYou: needsOK.count + openQuestions.count,
                                working: handling.count,
                                done: finished.count)
                        }
                        // AN UNREACHABLE CUSTOMER NEVER FINDS OUT THEY ARE
                        // UNREACHABLE. Those were this file's own capitals,
                        // written above a sentence nested inside
                        // `if !handling.isEmpty` — so it could only reach
                        // someone who already had work stuck, and an account
                        // with no number gets asked nothing and never
                        // accumulates any. Said here instead, once, under the
                        // control, on the screen everybody opens. The nested
                        // copy is gone rather than kept: this one already
                        // carries the parked-queue consequence in its own
                        // words, and that one asked the device-local mirror
                        // with no guard on it at all.
                        if HomeFeedPolicy.sayUnreachable(
                            phoneState: session.canonicalOwnerPhoneState) {
                            unreachableNotice.padding(.top, Theme.Space.tight)
                        }
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
                                        ConfirmJobCard(
                                            job: job,
                                            canonicalPhoneState: session.canonicalOwnerPhoneState)
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
                                // A handling section can contain three different
                                // hands at once. Each card names its own hand;
                                // the shared heading therefore stays neutral.
                                sectionHeader("In progress")
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
                                if !browserHandling.isEmpty {
                                    if browserOffer {
                                        browserOfferCard
                                            .padding(.bottom, Theme.Space.base)
                                    } else if !session.agentOnline {
                                        Text(session.agentPaired
                                             ? "Open Chrome and your browser work picks up on its own."
                                             : "Link Chrome in Settings and your browser work picks up on its own.")
                                            .font(.system(size: 15))
                                            .foregroundStyle(Theme.text2)
                                            .padding(.bottom, Theme.Space.tight)
                                    }
                                }
                                // He has had to ASK whether his extension was
                                // current — twice — and once a whole retest
                                // ran against a stale one while everybody
                                // believed the fixes were live. Chrome already
                                // reports its version on every heartbeat, so
                                // the answer was always here to be shown.
                                // THE SECOND COPY OF THE UNREACHABLE SENTENCE
                                // IS GONE FROM HERE, and both halves of that
                                // are deliberate. It was the same fact as
                                // `unreachableNotice` above — which already
                                // carries the parked-queue consequence in its
                                // own words ("anything I prepare will just sit
                                // here until you open the app") — so with the
                                // hoist landed the two said one thing twice on
                                // one scroll, in two different voices. And this
                                // one asked `session.ownerPhone.isEmpty` with NO
                                // guard at all: the device-local mirror is empty
                                // in exactly the same way whether the account
                                // has no number or this launch has not read it
                                // yet, so on a reinstall-and-sign-in whose owner
                                // read failed it printed "I have no number for
                                // you" in the app's one accent colour at
                                // somebody whose number was sitting on the
                                // server. See `HomeFeedPolicy.sayUnreachable`.
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
                            if !finished.isEmpty {
                                sectionHeader("Done")
                                    .padding(.top, Theme.Space.section)
                                    .padding(.bottom, Theme.Space.tight)
                                DoneDeck(jobs: finishedShown)
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
                    NavigationLink { SettingsHomeView() } label: {
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
            // Ask after this server has answered at least one authenticated
            // read, and re-arm at an account boundary. The session owns the
            // explicit unknown/none/invalid/valid result and ignores any reply
            // that comes back after the account changed.
            .task(id: "\(verified)|\(session.accountID)") {
                await refreshCanonicalOwnerForReachability()
            }
            // WHEN THE PHONE LAST HEARD ANYTHING, asked on the three moments
            // that can change that answer and on no others: the view appearing,
            // `suspended` flipping, and the app coming back to the foreground.
            // Never on the poll — see `readInterruptionGap`. The DURATION on
            // the card moves without this running again, because what is stored
            // is the instant and the subtraction happens at the draw — see
            // `heardNothingSince`.
            .task(id: "\(session.listener.suspended)|\(scenePhase)") {
                await readInterruptionGap()
            }
            .onChange(of: scenePhase) { phase in
                if phase == .active {
                    Haptics.warmUp()
                    session.resumeListeningIfWanted()
                    // Profile reachability is not part of the three-second
                    // feed poll. A foreground transition is the bounded retry
                    // point after a launch or sign-in that began offline.
                    Task { await refreshCanonicalOwnerForReachability() }
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
            // NOT "starting transcription". Nothing is starting: the pendant
            // has no way to turn sound into words until an on-device
            // transcriber exists, and a label promising one that never
            // arrives is the same lie as a Listening label over silence.
            return "Pendant · can't hear yet"
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
            // BOTH halves of this used to be false. One said the pendant's
            // sound was going to a speech vendor; the other promised a stream
            // that was "opening". design/LOCAL-FIRST.md rule 1 closed that
            // lane - "RAW AUDIO NEVER LEAVES A DEVICE" - and a privacy promise
            // left standing after the thing it described is gone is worse than
            // the violation: it tells someone their audio goes somewhere it
            // does not, and nothing about where it actually went.
            return "Your pendant is connected, but I can't turn its sound into words yet - that has to happen on this phone, and I don't have that piece. Nothing from the pendant is recorded or sent anywhere. Your phone's microphone is the ear that works."
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
            //
            // AND HOW LONG IT HAS HEARD NOTHING, when the phone measured it.
            // Recovery in the present tense reads the same at four seconds as
            // at four hours, and the four-hour version of this line is the
            // 30-hour-deaf case `CLAUDE.md` records. The number is NOT the age
            // of the interruption and is not worded as one — see
            // `HomeCopy.micInterrupted` for the measurement it actually is and
            // why claiming the other would have overstated the loss. It comes
            // from `interruptedGap`, nil unless the journal ends in an
            // interruption with time on it, so nothing is invented here.
            if session.listener.suspended {
                Label(HomeCopy.micInterrupted(unheardForSeconds: interruptedGap),
                      systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(Theme.muted)
                    // It wraps now — the same treatment the pending-lines
                    // sentence below already needs for the same reason.
                    .fixedSize(horizontal: false, vertical: true)
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
            // Capture stays visible; the person's words do not. Showing every
            // partial and final line made Home a scrolling speech console and
            // forced the owner to watch recognition mistakes in real time.
            // The complete record remains available under Privacy & Data.
            if session.listener.capturing {
                Label("Listening quietly. I'll bring forward only what matters.",
                      systemImage: "waveform")
                    .font(.caption)
                    .foregroundStyle(Theme.muted)
                    .fixedSize(horizontal: false, vertical: true)
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

    /// No number on file, said on Home instead of only under a stuck queue.
    ///
    /// QUIET ON PURPOSE, and the choice is argued rather than defaulted. This
    /// is a STANDING state: for an account with no number it is true on every
    /// launch, for as long as that stays true. A permanent sentence in the
    /// app's one accent colour, sitting under the control that turns the whole
    /// product on, is a nag — and an app that asks for a microphone all day
    /// cannot afford to nag. So it takes `Theme.text2` at the same 15pt the
    /// Chrome sentence further down already uses for a standing fact.
    /// Placement was the defect; loudness never was — which is also why the
    /// accent-coloured second copy that used to sit inside the stuck-queue
    /// block is not still there saying the same thing louder.
    private var unreachableNotice: some View {
        Text("I don't have a number for you, so there's no SMS backstop. "
             + "Local alerts can reach you while Anticipy is running or listening "
             + "in the background if notifications are allowed. Otherwise, open "
             + "the app to see what needs you. Add a number in Settings if you want text updates.")
            .font(.system(size: 15))
            .foregroundStyle(Theme.text2)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// The one canonical read behind both the standing Home notice and every
    /// approval card's delivery promise. A failed read leaves the state unknown;
    /// only a successful server answer can move it to none/invalid/valid.
    private func refreshCanonicalOwnerForReachability() async {
        guard verified, !session.accountID.isEmpty else { return }
        let account = session.accountID
        for attempt in 0..<3 {
            guard !Task.isCancelled, session.accountID == account else { return }
            if await session.refreshCanonicalOwner() { return }
            // A known value remains the last successful canonical answer. Only
            // unknown needs the short retry; foregrounding will refresh known
            // values once without turning this into another poll.
            guard session.canonicalOwnerPhoneState == .unknown,
                  attempt < 2 else { return }
            try? await Task.sleep(nanoseconds: UInt64(attempt + 1) * 500_000_000)
        }
    }

    /// How long the microphone has been gone, read off the journal — never on
    /// the poll.
    ///
    /// THREADING IS THE WHOLE SHAPE OF THIS FUNCTION. `persistedEvents` is a
    /// synchronous `queue.sync` over the journal's two files plus a parse of
    /// every line in them (`Audio/ListenJournal.swift`), and this screen
    /// redraws every three seconds — so the same read wired into a view body
    /// would put disk I/O on the main thread twenty times a minute to move a
    /// number by three seconds. It runs on the moments that can change the
    /// answer instead: the view appearing, `suspended` flipping, and the scene
    /// coming back to `.active`, which is the one that matters most — the
    /// reader this sentence was written for is somebody opening the app an
    /// hour after a call took the microphone.
    ///
    /// IT READS NOTHING WHILE THE MICROPHONE IS FINE. The guard is first, so on
    /// an ordinary day this costs one comparison and touches no disk at all.
    ///
    /// SILENT UNLESS THE PHONE MEASURED IT, which is the rule the whole card
    /// sits under. `.unknown` is a record with no session line in it — both
    /// ends rotated away, or a phone that has never listened — and a gap
    /// invented there would be a number about nothing. `.stoppedByOwner` zeroes
    /// the gap deliberately (`ListenTally.swift:58-60`: quiet after you turn it
    /// off is the ordinary state of a phone nobody is talking to, not a
    /// finding), and `.listening` has no gap to name. Each of those leaves
    /// `heardNothingSince` nil, so `interruptedGap` is nil and the sentence is
    /// exactly the one that shipped before any of this.
    @MainActor
    private func readInterruptionGap() async {
        guard session.listener.suspended else {
            heardNothingSince = nil
            return
        }
        // Detached for the same reason Settings' listening row is
        // (`SettingsView.unheardSeconds`), and passing `now:` for the same
        // reason both of them do: a fold that can only measure to the
        // journal's own last line answers "58 min" for a phone that has been
        // deaf since breakfast, because on that day the last line IS the
        // failure.
        let tally = await Task.detached(priority: .utility) {
            ListenTally.of(ListenJournal.shared.persistedEvents, now: Date())
        }.value
        guard case .stoppedByOther = tally.ending, tally.unheardForSeconds > 0 else {
            heardNothingSince = nil
            return
        }
        // THE INSTANT, RECONSTRUCTED, rather than the seconds kept as they came
        // — see `heardNothingSince` for why a stored count of seconds is a
        // number that freezes and then goes on being stated as now. `Date()` is
        // read HERE, after `.value` has returned, so the anchor can only land
        // at or after the fold's own `lastHeardAt` and the duration drawn from
        // it is never larger than what the phone measured. That is
        // `PlainDuration`'s truncate-never-round rule held across the one
        // subtraction that happens outside `PlainDuration`.
        heardNothingSince = Date().addingTimeInterval(-Double(tally.unheardForSeconds))
    }

    /// How long the phone has heard nothing, as of this draw.
    ///
    /// Reads no disk and folds nothing: `heardNothingSince` is already the
    /// answer, and this is the subtraction that turns it back into the number
    /// the sentence wants. Nil in, nil out — and `HomeCopy.micInterrupted`
    /// takes zero and below as "nothing measured", so a clock that moved
    /// backwards under us falls back to the sentence with no number in it
    /// rather than printing a negative.
    private var interruptedGap: Int? {
        guard let since = heardNothingSince else { return nil }
        return Int(Date().timeIntervalSince(since))
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
            if let says = freshAnticipyLine {
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
            // AND NEITHER SENTENCE WHILE A CALL HAS THE MICROPHONE, which the
            // two arms above manage between them. `idleLine` is "All quiet on
            // my end. I've got the watch." — a claim to be covering something,
            // stacked on the sentence that has just admitted she is not — so it
            // is gated on `capturing` and not on the wish. `offLine` is the
            // other arm, and it cannot be reached from here at all: it sits
            // behind `!isListening`, and a listener that is merely suspended is
            // still listening. So the suspended case falls out of both and says
            // nothing more, which is the whole intent. The first sentence
            // already said the truth, and a briefing may be one sentence long.
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
            Text("Turn on listening during a conversation. Anticipy keeps track of follow-ups, names, dates, and messages that need a response.")
                .font(.system(size: 17))
                .lineSpacing(3)
                .foregroundStyle(Theme.text2)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: 300)
            VStack(alignment: .leading, spacing: Theme.Space.snug) {
                manifestRow("Commitments and follow-ups")
                manifestRow("People, dates, and details")
                manifestRow("Messages that need a response")
            }
            .padding(.top, Theme.Space.tight)
            Rectangle().fill(Theme.edge).frame(height: 0.5)
                .padding(.vertical, Theme.Space.snug)
            Text("EXAMPLE")
                .font(.system(size: 12, weight: .semibold))
                .tracking(1.2)
                .foregroundStyle(Theme.muted)
                .frame(maxWidth: .infinity, alignment: .leading)
            // The REAL components, fed fixtures — using the actual views
            // guarantees the promise matches the delivery.
            VStack(spacing: Theme.Space.snug) {
                TranscriptRow(line: AnticipySession.TranscriptLine(
                    id: "demo-1",
                    text: HomeCopy.exampleHeard,
                    decision: "act"))
                ConfirmJobCard(job: AgentJob(
                    id: "demo-2", goal: HomeCopy.exampleGoal,
                    params: "", status: "awaiting_confirm", result: nil, created: ""))
            }
            // 0.42 was faint enough that the sample was hard to read at all on
            // the one screen whose whole job is showing what arrives. NOT full
            // strength: the caption above plus a visibly quieter pair is what
            // says "example", and a first-timer reading a fixture as a real job
            // is a worse failure than a faint one.
            .opacity(0.62)
            .blur(radius: 0.4)
            .allowsHitTesting(false)
            // SAID OUT LOUD, rather than hidden. This was
            // `accessibilityHidden(true)`, so a first-timer using VoiceOver got
            // the promise — the three things she listens for — and no sample at
            // all of what a caught thing looks like when it lands. The label
            // reads the fixtures back verbatim (`HomeCopy.exampleCardsLabel`),
            // and it opens with "Example." because the caption that carries
            // that word for a sighted reader is a separate element.
            //
            // `.ignore` AND NOT `.contain`: contain leaves the children
            // individually focusable, so VoiceOver would walk into the fixture
            // card's inert "Send it" and "Not now" buttons — a decision to
            // make about somebody's invoice, on a screen with no invoice and
            // no working buttons. `.allowsHitTesting(false)` above stops the
            // finger; this is the same refusal for the other pointer.
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(HomeCopy.exampleCardsLabel)
        }
        .frame(maxWidth: .infinity)
    }

    private func manifestRow(_ text: String) -> some View {
        HStack(spacing: Theme.Space.snug) {
            Image(systemName: "checkmark")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(Theme.accent)
                .frame(width: 12)
                .accessibilityHidden(true)
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

// MARK: - Recaps and result deck

private struct HomeConversationInsight: Identifiable, Equatable {
    let id: String
    let title: String
    let state: String
}

/// A bounded recap, grounded only in decisions and jobs already on the phone.
/// It borrows the one-idea-at-a-time clarity of a story card without turning
/// Home into an autoplaying slideshow or inventing a personality from one day.
private struct HomeInsightsCard: View {
    let items: [HomeConversationInsight]
    let needsYou: Int
    let working: Int
    let done: Int

    private var headline: String {
        if needsYou > 0 {
            return needsYou == 1
                ? "One thing from your conversations still needs your word."
                : "\(needsYou) things from your conversations still need your word."
        }
        if working > 0 {
            return working == 1
                ? "One thing you mentioned is moving now."
                : "\(working) things you mentioned are moving now."
        }
        if done > 0 {
            return done == 1
                ? "One result is ready for you."
                : "\(done) results are ready for you."
        }
        return "Here is what Anticipy picked up."
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Space.snug) {
            Text(headline)
                .font(Theme.display(23))
                .tracking(-0.2)
                .foregroundStyle(Theme.text)
                .fixedSize(horizontal: false, vertical: true)
            ForEach(items) { item in
                HStack(alignment: .firstTextBaseline, spacing: Theme.Space.tight) {
                    Text(item.title)
                        .font(.callout.weight(.medium))
                        .foregroundStyle(Theme.text)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: Theme.Space.tight)
                    Text(item.state)
                        .font(.caption)
                        .foregroundStyle(Theme.muted)
                        .multilineTextAlignment(.trailing)
                }
                .accessibilityElement(children: .combine)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .anticipyCard()
    }
}

/// One result at a time, selected by stable job id so a three-second poll
/// cannot move somebody to a different card while they are reading it.
private struct DoneDeck: View {
    let jobs: [AgentJob]
    @State private var selectedID: String?

    private var index: Int {
        guard let selectedID,
              let found = jobs.firstIndex(where: { $0.id == selectedID })
        else { return 0 }
        return found
    }

    private var selected: AgentJob? {
        guard !jobs.isEmpty else { return nil }
        return jobs[min(index, jobs.count - 1)]
    }

    var body: some View {
        VStack(spacing: Theme.Space.tight) {
            if let job = selected {
                DoneCard(job: job)
                    .id(job.id)
                    .anticipyCard()
                    .transition(.asymmetric(
                        insertion: .move(edge: .trailing).combined(with: .opacity),
                        removal: .move(edge: .leading).combined(with: .opacity)))
                    .simultaneousGesture(
                        DragGesture(minimumDistance: 20)
                            .onEnded { value in
                                let horizontal = abs(value.translation.width)
                                let vertical = abs(value.translation.height)
                                guard horizontal > 44, horizontal > vertical * 1.2 else { return }
                                move(by: value.translation.width < 0 ? 1 : -1)
                            })
            }
            if jobs.count > 1 {
                HStack(spacing: Theme.Space.tight) {
                    Button("Previous") { move(by: -1) }
                        .buttonStyle(.ghost)
                        .disabled(index == 0)
                    Spacer()
                    Text("\(index + 1) of \(jobs.count)")
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(Theme.muted)
                        .accessibilityLabel("Result \(index + 1) of \(jobs.count)")
                    Spacer()
                    Button("Next") { move(by: 1) }
                        .buttonStyle(.ghost)
                        .disabled(index >= jobs.count - 1)
                }
            }
        }
        .onAppear { repairSelection() }
        .onChange(of: jobs.map(\.id)) { _ in repairSelection() }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Done results")
        .accessibilityValue("Result \(index + 1) of \(jobs.count)")
        .accessibilityAdjustableAction { direction in
            switch direction {
            case .increment: move(by: 1)
            case .decrement: move(by: -1)
            @unknown default: break
            }
        }
    }

    private func repairSelection() {
        guard !jobs.isEmpty else { selectedID = nil; return }
        if selectedID == nil || !jobs.contains(where: { $0.id == selectedID }) {
            selectedID = jobs[0].id
        }
    }

    private func move(by amount: Int) {
        guard !jobs.isEmpty else { return }
        let destination = min(max(0, index + amount), jobs.count - 1)
        guard destination != index else { return }
        Haptics.tap()
        withAnimation(Theme.spring) { selectedID = jobs[destination].id }
    }
}

// MARK: - Cards

/// A job the agent prepared and is holding for your explicit go-ahead.
struct ConfirmJobCard: View {
    let job: AgentJob
    /// This comes only from the canonical account read (or a confirmed save),
    /// never from the device-local phone mirror.
    let canonicalPhoneState: OwnerMirror.PhoneState
    @EnvironmentObject var session: AnticipySession
    @State private var answer = ""

    init(job: AgentJob,
         canonicalPhoneState: OwnerMirror.PhoneState = .unknown) {
        self.job = job
        self.canonicalPhoneState = canonicalPhoneState
    }

    private var stuck: Bool {
        job.status == "needs_user" || job.workflow_state == "draft"
    }
    private var uncertain: Bool { job.effect_uncertain == true }
    /// What the extension found when it looked at the surviving page after a
    /// crash, read off `params._reconciliation`. Audit #90 (E): the caption
    /// and the button below are decided by this row, never by the tap alone.
    private var reconciliation: RetryReconciliationPolicy.Reading {
        RetryReconciliationPolicy.read(
            (try? JSONSerialization.jsonObject(with: Data(job.params.utf8)))
                as? [String: Any] ?? [:])
    }
    /// The floor, as the card sees it: an uncertain row may be retried only
    /// on a positive not_applied. `approvalFields` refuses the same thing on
    /// the write, so a bypassed button still sends nothing.
    private var retryable: Bool {
        !uncertain || RetryReconciliationPolicy.mayRetry(reconciliation)
    }
    private var sending: Bool { session.inFlight.contains(job.id) }
    private var failed: Bool { session.failedWrites.contains(job.id) }
    private var unverified: Bool { session.unverifiedWrites.contains(job.id) }
    private enum NotificationRoute {
        case textAndApp, appOnly, checking, phoneNeedsAttention
    }
    private var notificationRoute: NotificationRoute {
        switch canonicalPhoneState {
        case .valid: return .textAndApp
        case .none: return .appOnly
        case .invalid: return .phoneNeedsAttention
        case .unknown: return .checking
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(stuck ? "I need one detail" : "Ready for approval",
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
                // What the page showed, or why nothing could be said — six
                // sentences for six states, from the row rather than a
                // standing instruction to go and check. The old constant here
                // told him to check and then let the tap assert that he had.
                Text(RetryReconciliationPolicy.explanation(reconciliation))
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
                Label("I checked the job after the request failed. It did not change, so it is safe to try again.", systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(Theme.text2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if unverified {
                Label("I couldn't verify whether that went through. I won't send it again until the job itself gives us an answer.", systemImage: "questionmark.circle")
                    .font(.caption)
                    .foregroundStyle(Theme.text2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            VStack(alignment: .leading, spacing: 3) {
                Label(notificationLabel, systemImage: "bell")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Theme.text2)
                switch notificationRoute {
                case .appOnly:
                    Text("This account has no phone number. Add one in Settings → Profile if you want text updates.")
                        .font(.caption2)
                        .foregroundStyle(Theme.muted)
                        .fixedSize(horizontal: false, vertical: true)
                case .checking:
                    Text("I haven't finished checking this account's text-message setup. The result will still appear in the app.")
                        .font(.caption2)
                        .foregroundStyle(Theme.muted)
                        .fixedSize(horizontal: false, vertical: true)
                case .phoneNeedsAttention:
                    Text("The saved number cannot receive a text as written. Fix it in Settings → Profile; the result will still appear in the app.")
                        .font(.caption2)
                        .foregroundStyle(Theme.muted)
                        .fixedSize(horizontal: false, vertical: true)
                case .textAndApp:
                    Text("The result is saved in the app first. I'll also try your saved number; carrier delivery can still fail.")
                        .font(.caption2)
                        .foregroundStyle(Theme.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            HStack(spacing: 10) {
                Button {
                    // No haptic here: confirm() buzzes only after the server
                    // has actually accepted it. This one used to buzz success
                    // before the request had even left the phone.
                    if unverified {
                        Task { await session.reconcileWrite(job) }
                    } else {
                        Task { await session.confirm(job, ownerAnswer: answer) }
                    }
                } label: {
                    Group {
                        if sending {
                            HStack(spacing: 8) {
                                BreathingDot(size: 6)
                                Text("Sending…")
                            }
                        } else {
                            Text(unverified ? "Check outcome"
                                 : (uncertain ? "I checked, try again"
                                    : (failed ? "Try again" : (stuck ? "Send answer" : "Approve"))))
                        }
                    }
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.glass)
                .disabled(sending || !retryable
                          || (stuck && !uncertain && !unverified
                              && answer.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty))
                Button {
                    Task { await session.decline(job) }
                } label: {
                    // NOT AN ESCAPE HATCH, A CANCELLATION — and the label now
                    // says which. `session.decline` writes `status=cancelled`
                    // and nulls approval, lease and receipt, and the backend
                    // comment on `setJobFields` calls it "cancel it". "Not now"
                    // promises a later that does not exist: the plan is gone,
                    // and getting it back means saying the whole thing again.
                    //
                    // This is deliberately NOT the same edit as the two real
                    // "Not now"s on this screen. Those defer an OFFER — the
                    // mail read, the interview — and every escape hatch in this
                    // app is full-width, real size and unguilty. They keep
                    // their words. This one is not an offer being deferred.
                    Text("Don't do it")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.ghost)
                .disabled(sending || unverified)
            }
            // No opacity on the row: each control dims itself when it is
            // disabled, so a send in flight no longer greys out the sentence
            // the person is still reading.
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .anticipyCard()
    }

    private var notificationLabel: String {
        switch notificationRoute {
        case .textAndApp: return "Updates: In app · I'll also try text"
        case .appOnly: return "Updates: In app"
        case .checking: return "Updates: In app · checking text setup"
        case .phoneNeedsAttention: return "Updates: In app"
        }
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
    private var unverified: Bool { session.unverifiedWrites.contains(event.id) }
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
                Label("That answer is not on Anticipy, so it is safe to try again.",
                      systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(Theme.text2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if unverified {
                Label("I couldn't verify whether she received that answer. Tap Check outcome; it looks for this exact answer without sending it again.",
                      systemImage: "questionmark.circle")
                    .font(.caption)
                    .foregroundStyle(Theme.text2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Button {
                // No haptic here. `answer` buzzes only once the server has
                // taken it, which is the same rule every other write follows.
                Task {
                    if unverified {
                        await session.reconcileAnswer(event)
                    } else {
                        await session.answer(event, text: answer)
                    }
                }
            } label: {
                Group {
                    if sending {
                        HStack(spacing: 8) {
                            BreathingDot(size: 6)
                            Text(unverified ? "Checking…" : "Sending…")
                        }
                    } else {
                        Text(unverified ? "Check outcome" : (failed ? "Try again" : "Send"))
                    }
                }
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.glass)
            // Check needs no answer text, which is what makes an unknown write
            // recoverable after a process restart.
            .disabled(sending || (!unverified && empty))
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
    private var stopping: Bool { session.inFlight.contains(job.id) }
    private var stopUnverified: Bool { session.unverifiedWrites.contains(job.id) }

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

    private var normalizedLane: String {
        CalendarHandPolicy.normalizedLane(job.lane)
    }
    private var usesResearchHand: Bool { normalizedLane == "research" }
    private var usesCalendarHand: Bool { normalizedLane == CalendarHandPolicy.lane }

    private var stageTitle: String {
        if usesResearchHand {
            return job.status == "running" ? "Research is working" : "Research is queued"
        }
        if usesCalendarHand {
            return job.status == "running"
                ? "Updating your calendar"
                : "Queued on this iPhone"
        }
        if job.status == "running" { return "Working in Chrome" }
        return session.agentOnline ? "Sent to your browser agent" : "Waiting for your browser agent"
    }

    private var stageDetail: String? {
        if let doingNow { return doingNow }
        if usesResearchHand {
            return job.status == "running"
                ? "The research service accepted this task."
                : "It will start when the research service reaches it."
        }
        if usesCalendarHand {
            return job.status == "running"
                ? "This iPhone accepted the calendar change."
                : "This iPhone will pick up the calendar change from its queue."
        }
        if job.status == "running" { return "Chrome accepted this task." }
        if session.agentOnline { return "Chrome is connected and this task is in its queue." }
        if session.agentPaired, let seconds = session.agentLastSeenSeconds {
            return "Chrome is linked but offline. Last seen \(PlainDuration.words(seconds)) ago."
        }
        return session.agentPaired
            ? "Chrome is linked but offline. Open it and this picks up on its own."
            : "Link Chrome in Settings before this can start."
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
                Text(job.executionSurfaceLabel.uppercased())
                    .font(.system(size: 10, weight: .semibold))
                    .tracking(0.8)
                    .foregroundStyle(Theme.muted)
                Text(stageTitle)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.accent)
                Text(job.humanGoal)
                    .font(.system(size: 17))
                    .lineSpacing(3)
                    .foregroundStyle(Theme.text)
                if let stageDetail {
                    Text(stageDetail)
                        .font(.system(size: 13))
                        .foregroundStyle(Theme.text2)
                        .lineLimit(2)
                        .transition(.opacity)
                        .animation(Theme.spring, value: stageDetail)
                        .accessibilityLabel(stageDetail)
                }
            }
            Spacer()
            // THE ONLY STOP IN THIS PRODUCT WAS ON HIS LAPTOP.
            // HandlingCard carried no controls at all, so away from the desk,
            // watching a run head somewhere wrong, he could do nothing about
            // it. Same cancellation path as "Don't do it", so a stop from here
            // and a stop from Chrome mean one thing to the rest of the
            // system; the browser loop re-reads liveness immediately before
            // every irreversible action, so this lands before a submit.
            if job.status == "running" || job.status == "queued" {
                VStack(alignment: .trailing, spacing: 4) {
                    Button {
                        if stopUnverified {
                            Task { await session.reconcileWrite(job) }
                        } else {
                            Task { _ = await session.stopRunning(job) }
                        }
                    } label: {
                        Text(stopping ? "Checking…" : (stopUnverified ? "Check stop" : "Stop"))
                    }
                    .buttonStyle(.ghost)
                    .disabled(stopping)
                    .accessibilityLabel(stopping ? "Checking stop outcome"
                                        : (stopUnverified ? "Check stop outcome" : "Stop this task"))
                    if stopUnverified {
                        Text("Outcome unverified")
                            .font(.caption2)
                            .foregroundStyle(Theme.muted)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, Theme.Space.base)
    }
}

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

/// Terminal work, in the three ways it can end.
///
/// A completed job leads with its receipt. A failed one gets a plain sentence
/// and a way forward instead of a shrug and a stack trace. A CALLED-OFF one
/// gets a card at all, which it did not have: `cancelled` matched none of
/// Home's three filters, so a job the owner stopped left the screen the instant
/// the write landed — taking with it the only sentence saying it might have
/// gone through anyway. See `HomeFeedPolicy`.
///
/// The first two paragraphs of this comment spent some time attached to
/// `FoundCard` instead, which is where they were found.
struct DoneCard: View {
    let job: AgentJob
    @EnvironmentObject var session: AnticipySession
    @State private var expanded = false
    @State private var showRaw = false
    @AppStorage(AppPreferences.developerModeKey) private var developerMode = false

    private var succeeded: Bool { job.status == "done" }
    /// Stopped before it finished — from "Don't do it" on the card above, from
    /// Stop on a running one, from an answer that ended the errand, from the
    /// Chrome popup, or from the brain dropping a card he was never shown. All
    /// of them write `cancelled`, and until this branch existed all of them
    /// vanished off the screen without leaving a card behind.
    ///
    /// Asked of the policy rather than of the string, because Home's Done cap
    /// asks the same question a few hundred lines up and two spellings of one
    /// question is how `cancelled` came to match nothing in the first place.
    private var calledOff: Bool { HomeFeedPolicy.wasCalledOff(status: job.status) }
    private var retrying: Bool { session.inFlight.contains(job.id) }
    private var retryFailed: Bool { session.failedWrites.contains(job.id) }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            // Three outcomes, two colours. A cancellation is neither a
            // success nor a failure, so it takes the same muted grey a failure
            // does and is told apart by the glyph and the sentence — not by a
            // third colour grading it. Nobody is being scored for stopping
            // something.
            Image(systemName: succeeded ? "checkmark.circle.fill"
                  : (calledOff ? "slash.circle" : "exclamationmark.circle"))
                .foregroundStyle(succeeded ? Theme.accent : Theme.muted)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 8) {
                Text(job.executionSurfaceLabel.uppercased())
                    .font(.system(size: 10, weight: .semibold))
                    .tracking(0.8)
                    .foregroundStyle(Theme.muted)
                if succeeded {
                    // docs ex 77: the receipt leads. This used to lead with the
                    // goal in callout weight and put the confirmation number
                    // underneath in grey footnote with a three-line clamp - the
                    // one thing the person opened the app for, rendered as the
                    // small print under a restated question.
                    let card = JobReceiptPolicy.doneCard(goal: job.humanGoal,
                                                        result: job.result,
                                                        receipt: job.receipt,
                                                        effectKey: job.effect_key)
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
                            // Every other multi-line Text on this card carries
                            // this and the goal did not, so a goal longer than
                            // the row clipped to one line with an ellipsis —
                            // the restated question, cut in half, under its own
                            // answer. It wraps now.
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    // THE PROOF, not the claim. The server refuses to mark any
                    // job done without a verified receipt naming non-empty
                    // evidence, and until now the app decoded none of it: the
                    // card led with whatever sentence the browser composed
                    // about its own success while the checked thing sat unread
                    // in the same row. Moment 31: done without proof doesn't
                    // exist - so the card either shows the proof or says it
                    // hasn't got any.
                    if let proof = card.proof {
                        ReceiptProof(proof: proof)
                    }
                    if let unproven = card.unproven {
                        Label(unproven, systemImage: "questionmark.circle")
                            .font(.caption)
                            .foregroundStyle(Theme.muted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                } else if calledOff {
                    // THE RESULT LEADS, and this is the load-bearing half of
                    // the whole card. When a stop lands on a run that may
                    // already have committed something, `stopRunning` writes
                    // "You stopped this. It may already have gone through
                    // before I stopped. Worth a check." into `result` — and the
                    // SAME patch writes `effect_uncertain: false`, because
                    // `cancellationFields` clears the workflow. So `result` is
                    // the only surviving carrier of that warning, and until
                    // this branch existed it was carried to a card that
                    // rendered nowhere: the person watched the run head
                    // somewhere wrong, tapped Stop, and the row left the
                    // screen. ex 36 / ex 50 — the duplicate booking nobody
                    // checks for.
                    //
                    // AND `job.safetyLine` IS DELIBERATELY NOT HERE. It reads
                    // `effect_uncertain`, which the cancellation just set
                    // false, so on this card it returns "Nothing you told me
                    // was lost." — the reassuring sentence, printed directly
                    // under the warning that contradicts it, and the
                    // reassuring one is the one people act on. It stays on the
                    // failed branch below, where the field still means what it
                    // says.
                    //
                    // THE CARD SAYS WHAT IT IS BEFORE THE SERVER DOES, and
                    // that line is the repair. `decline` never writes `result`,
                    // so on the "Don't do it" path the sentence below is
                    // whatever the ENGINE last said — for a stuck job, "I may
                    // have already sent that … check the site before I try
                    // again, so you don't end up with two." Led with, under a
                    // heading reading "Done", that is a terminal card promising
                    // a retry that will never come, with nothing anywhere on it
                    // saying the owner stopped it. The kicker is the same
                    // caption treatment `ConfirmJobCard` gives "Your exact
                    // words", it costs one line, and it makes the card's
                    // identity independent of what the server happened to
                    // write. It names WHAT, never WHO — the brain cancels cards
                    // he was never shown, so an actor in the kicker would be a
                    // fresh false claim; see `HomeFeedPolicy.calledOffKicker`.
                    // Succeeded and failed do not need one: their leads are
                    // composed here and say what they are.
                    //
                    // BOUND TO THE SENTENCE IT LABELS, at the same spacing 4
                    // `ConfirmJobCard` binds "Your exact words" to the words —
                    // loose in this card's outer stack the kicker sat exactly
                    // as far from its own sentence as the goal sits from it,
                    // and a label the same distance from everything is not
                    // reading as a label of anything. Combined for VoiceOver
                    // for the same reason: the glyph beside this card is
                    // `accessibilityHidden`, so the kicker is the only thing
                    // that says what the card is, and two stray elements read
                    // out one after another do not make one statement.
                    VStack(alignment: .leading, spacing: 4) {
                        Text(HomeFeedPolicy.calledOffKicker)
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(Theme.muted)
                        Text(HomeFeedPolicy.calledOffLead(result: job.result))
                            .font(.callout.weight(.medium))
                            .foregroundStyle(Theme.text)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .accessibilityElement(children: .combine)
                    // The goal underneath, in the same lead-then-context order
                    // the succeeded branch uses a few lines up: what happened
                    // first, what it was about second.
                    Text(job.humanGoal)
                        .font(.footnote)
                        .foregroundStyle(Theme.muted)
                        .fixedSize(horizontal: false, vertical: true)
                    // NO RETRY BUTTON, and that is the point rather than an
                    // omission. The failed branch offers one because nothing
                    // happened and the person wants it to. Here they just said
                    // stop — and in the exact case this branch exists for, they
                    // stopped because it may already have gone through. A
                    // one-tap "Start a fresh attempt" sitting beside "worth a
                    // check" is the duplicate booking with a button on it.
                    // Asking again out loud queues it again, through the brain,
                    // which is where deciding what was meant belongs.
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
                    if developerMode, let r = job.result, !r.isEmpty {
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

/// WHAT WAS CHECKED, under the sentence that claims it.
///
/// The backend refuses to move any job to `done` without a receipt carrying
/// `verified: true` and a non-empty `evidence` array, and the phone decoded
/// none of it until now - so the promise of this card ("done requires
/// evidence tied to the exact effect", ex 44) was kept entirely on the server
/// and shown to nobody.
///
/// One quiet line by default: where it was checked, and whether there is a
/// photograph. The full proof index is one tap behind that, verbatim and
/// unedited - ex 126 forbids paraphrasing what the engine came back with, and
/// evidence is held to the same rule. A person who wants to audit a booking
/// six weeks later needs the entries as they were written, not a summary of
/// them.
private struct ReceiptProof: View {
    let proof: JobReceiptPolicy.Proof
    @State private var showing = false

    /// The site, not the URL. A confirmation URL is a 300-character query
    /// string; the host is the part that answers "where did this happen".
    /// The whole URL is still one tap away in the list below.
    private var host: String? {
        guard let url = proof.url, let parsed = URL(string: url),
              let host = parsed.host else { return nil }
        return host.hasPrefix("www.") ? String(host.dropFirst(4)) : host
    }

    /// Where the claim was checked, in the receipt's own words. Never
    /// composed from anything but what the row holds.
    private var checkedOn: String? {
        let where_ = proof.title ?? host
        guard let where_ else { return nil }
        return "Checked on \(where_)"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Image(systemName: "checkmark.seal")
                    .font(.caption)
                    .foregroundStyle(Theme.accent)
                    .accessibilityHidden(true)
                Text(checkedOn ?? "Checked before I called it done")
                    .font(.caption)
                    .foregroundStyle(Theme.text2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if proof.photographed {
                // The one entry nothing else in the product can reconstruct.
                Label("There's a photo of the finished page",
                      systemImage: "photo")
                    .font(.caption2)
                    .foregroundStyle(Theme.muted)
            }
            Button {
                Haptics.tap()
                withAnimation(.easeInOut(duration: 0.2)) { showing.toggle() }
            } label: {
                Label(showing ? "Hide the proof" : "Show me the proof",
                      systemImage: showing ? "chevron.up" : "chevron.down")
            }
            .buttonStyle(.ghost)
            if showing {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(proof.items, id: \.self) { item in
                        Text(item)
                            .font(.caption2.monospaced())
                            .foregroundStyle(Theme.muted)
                            .textSelection(.enabled)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    if let at = proof.recordedAt {
                        Text("Recorded \(at)")
                            .font(.caption2)
                            .foregroundStyle(Theme.muted)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(10)
                .background(RoundedRectangle(cornerRadius: Theme.Radius.small,
                                             style: .continuous)
                    .fill(Theme.surface))
            }
        }
        .accessibilityElement(children: .contain)
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
                        Text("Looking into it. I'll bring the result back here.")
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
