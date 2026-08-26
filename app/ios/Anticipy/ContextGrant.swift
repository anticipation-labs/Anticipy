import Foundation

/// Which sources she has been let into, one at a time.
///
/// This is the deterministic half of consent. `CLAUDE-ONBOARDING.md:16-17`:
/// "that gate lives in deterministic code, never in the model." So no read of
/// any source is reachable without a grant recorded here first — a prompt
/// cannot talk its way past it, because the prompt never gets to run.
///
/// One grant, one source, revocable. There is deliberately no "grant
/// everything": `design/PREMIUM-FEEL.md:43-47` requires one toggle per source,
/// preselected off, and a bulk switch is the same thing wearing a disguise.
enum ContextSource: String, CaseIterable, Identifiable {
    /// `sheet(item:)` needs identity; the raw value already is one.
    var id: String { rawValue }

    /// On-device. Event titles and times for the next ~30 days — never bodies,
    /// never attendees' addresses, never past events.
    case calendar
    /// On-device. The names list only. Not numbers, not emails, not addresses.
    case contacts
    /// NOT on-device, and the only source that isn't. There is no mailbox on
    /// this phone to read: a mail read is a SUPERVISED READ in the browser you
    /// are already logged into — you open it, she reads it once in the
    /// foreground while you watch a narrated log, and a handful of distilled
    /// facts is the whole output (`design/day-zero.md` §2, §3).
    ///
    /// It is supervised rather than autonomous because three independent
    /// constraints say so, any one of which decides it: the architecture
    /// already forbids read-only work in the owner's browser
    /// (`backend/pb_hooks/research_lane.pb.js:70-73` answers 403, "research
    /// jobs run in the worker, never in a browser"); `gmail.readonly` is a
    /// Google *restricted* scope, so the API route is a subscription to a CASA
    /// audit re-certified every twelve months; and LinkedIn's User Agreement
    /// §8.2 makes automated access a contract breach whose penalty lands on
    /// the PAYING USER'S account, not on ours.
    ///
    /// Unreachable from the just-in-time ask on purpose. `ContextTrigger`
    /// returns only `.calendar` and `.contacts`, so `ContextAskSheet` can
    /// never present this; it is granted from `SupervisedReadView`, next to
    /// the read it authorises. Consenting to a capability somewhere far away
    /// from where it runs is the trap this ordering avoids.
    case mail

    /// Is this source read on the phone itself?
    ///
    /// The one distinction the rest of the code branches on, and it decides
    /// two different things: whether `LifeContext` has a reader for it at all,
    /// and whether an OS permission even exists to ask for. There is no iOS
    /// alert for "may she look at your mail in the browser", so false here
    /// means the grant is recorded with no OS round-trip.
    ///
    /// Expressed as a property rather than a scatter of `== .mail` checks,
    /// because the next off-device source (professional, work tools —
    /// `design/day-zero.md` §3) must inherit the behaviour by existing, not by
    /// somebody remembering to widen a comparison.
    var isOnDevice: Bool {
        switch self {
        case .calendar, .contacts: return true
        case .mail: return false
        }
    }

    /// A short human name, for a list. Not a sentence and not a title —
    /// "Your mail" is what she calls it out loud, and `design/day-zero.md` §3
    /// numbers the sources in exactly these words.
    var label: String {
        switch self {
        case .calendar: return "Your calendar"
        case .contacts: return "Your contacts"
        case .mail: return "Your mail"
        }
    }

    /// What she says she wants, in her voice. One question, and it NAMES THE
    /// SPECIFIC THING — `CLAUDE-ONBOARDING.md:19-20` and the voice law at
    /// `:28-29`: "the 7:30 at Cactus Club", not "your reservation". `subject`
    /// is the word from your own sentence that provoked the ask; without it
    /// this collapses into the generic form that law bans.
    func ask(subject: String? = nil) -> String {
        switch self {
        case .calendar:
            return "Want me to check your calendar?"
        case .contacts:
            guard let who = subject, !who.isEmpty else {
                return "Can I read the names in your contacts?"
            }
            return "Who's \(who)? I can read just the names in your contacts."
        case .mail:
            // One question, and the watching is IN the question — the whole
            // point of a supervised read is that it is a thing you see happen
            // (`design/day-zero.md` §2). `subject` is the thing from your own
            // sentence she would be looking for, which is what keeps this from
            // reading as a request for the mailbox in general.
            guard let what = subject, !what.isEmpty else {
                return "Want to open your mail and let me read it once while you watch?"
            }
            return "Want to open your mail so I can look for the \(what) thread while you watch?"
        }
    }

    /// The promises, as a rule list. Not cards — four evenly spaced
    /// symbol-and-card rows is the most recognisable AI-built layout there is
    /// (`design/CONSUMER-FEEL-DIRECTION-2026-08-03.md` §4 cut #3).
    ///
    /// EVERY LINE HERE MUST BE TRUE OF THE CODE. Two of them were not: this
    /// said "only what I conclude from it travels" while `LifeContext` uploads
    /// the verbatim event title, and "only the name travels" while it sends up
    /// to forty of them in one go, immediately. `CONSUMER-READINESS` §1 names
    /// that exact failure — "the app confidently asserts things that are not
    /// true" — and a consent screen is the worst possible place to reintroduce
    /// it. If the reader changes, these change with it.
    ///
    /// THE CAPS ARE PART OF THAT. "one line per event" and "the list of names"
    /// were both true and both unbounded, so the only two numbers a person
    /// would want before saying yes — fifteen events, forty names — were the
    /// two the screen did not say, while `LifeContext.maxEvents` and
    /// `maxNames` were already enforcing them. They are spelled here as words
    /// rather than digits because these are sentences, not measurements; the
    /// digits belong on the receipt, which reports what a phone actually
    /// counted. `run_context_receipt_tests.sh` spells both caps out of
    /// `LifeContext` and checks the promise contains them, so raising a cap
    /// fails a suite until the sentence catches up.
    var promises: [String] {
        switch self {
        case .calendar:
            return ["I read what's coming up for the next month: the title and the time.",
                    "I never read the notes, the invitees, or anything in the past.",
                    "I send myself one line per event, up to fifteen of them: that title and that time. Never the calendar itself.",
                    "Nothing goes in your calendar unless you tell me to put it there."]
        case .contacts:
            return ["I read the names, so I know who you mean when you say one.",
                    "I never read a number, an email, or an address.",
                    "I send myself at most forty names, once. Those three things never leave this phone.",
                    "I never message anyone in there on my own."]
        case .mail:
            // These describe what a supervised read IS — foreground, you
            // present, one pass, read-only, a handful of facts — and not one
            // of them claims a mailbox has been read. The read loop does not
            // exist yet, which is why `SupervisedReadView` says so on its face
            // instead of offering a button that does nothing.
            //
            // "I read. I never send. Ever." is the standing promise fixed at
            // `design/PREMIUM-FEEL.md:135`, and it is the second line because
            // it answers the thing somebody is actually frightened of.
            return ["You open it. I read it once, in the front window, while you watch.",
                    "I read. I never send, never reply, never delete. Ever.",
                    "I send myself a handful of lines: who you talk to, what's in flight.",
                    "Never the mailbox, never a message, never an attachment.",
                    "Anything I get wrong, tap it and it's gone."]
        }
    }

    /// The word on the button that says yes, per source.
    ///
    /// One button, three different things being handed over. The label was
    /// "Yes, go ahead" for all of them, which made the one control a thumb
    /// actually lands on the only line on the screen that did not name what it
    /// buys. An inline ternary at the call site would have been worse than a
    /// property: it would have left `mail` — the source whose yes buys a
    /// supervised read rather than a file read — on the generic string.
    ///
    /// Each names a LIMIT rather than a capability, because the limit is the
    /// part somebody is deciding about. "the next month" is deliberately not a
    /// fourth phrasing of `LifeContext.horizonDays`: promise `:116` and the
    /// shipped `NSCalendarsFullAccessUsageDescription` both say "the next
    /// month", and a button saying "the next 30 days" beside them is exactly
    /// the drift the standing order above exists to stop.
    var yesButton: String {
        switch self {
        case .calendar: return "Yes — the next month"
        case .contacts: return "Yes — names only"
        case .mail: return "Yes — one read, while you watch"
        }
    }

    /// Why she is asking, right now — naming the gap, not hedging about it.
    /// "I can't be sure I've got it right" was filler; `design/day-zero.md`
    /// requires the ask to name its reason in the same breath.
    func because(_ heard: String, subject: String? = nil) -> String {
        switch self {
        case .calendar:
            return "You said \"\(heard)\". I don't know what else you've got on."
        case .contacts:
            let who = (subject?.isEmpty == false) ? subject! : "them"
            return "You said \"\(heard)\". I don't know a \(who) yet."
        case .mail:
            // The gap is specific: what is in flight lives in the thread, and
            // she has never seen the thread. Naming it in the same breath is
            // `design/day-zero.md` §2 — an unexplained request is denied about
            // twice as often as an explained one.
            let about = (subject?.isEmpty == false) ? subject! : "it"
            return "You said \"\(heard)\". Whatever's in flight about \(about) is in your mail, not in my head."
        }
    }

    var storageKey: String { "context.grant.\(rawValue)" }
    /// Asked and declined. Recorded so she never asks twice unprompted; a skip
    /// is a "no for now", never a fact about the person
    /// (`design/briefs/08-day-zero.md:30`).
    var declinedKey: String { "context.declined.\(rawValue)" }
}

/// The gate itself. A plain type over UserDefaults rather than a store object:
/// it is read from view code, from the ask sheet, and from the reader, and all
/// three must agree without an observation graph in between.
struct ContextGrants {
    private let defaults: UserDefaults
    init(defaults: UserDefaults = .standard) { self.defaults = defaults }

    func granted(_ source: ContextSource) -> Bool {
        defaults.bool(forKey: source.storageKey)
    }

    func declined(_ source: ContextSource) -> Bool {
        defaults.bool(forKey: source.declinedKey)
    }

    /// Granting clears any earlier decline, so "not now" is never permanent.
    func grant(_ source: ContextSource) {
        defaults.set(true, forKey: source.storageKey)
        defaults.set(false, forKey: source.declinedKey)
    }

    func decline(_ source: ContextSource) {
        defaults.set(false, forKey: source.storageKey)
        defaults.set(true, forKey: source.declinedKey)
    }

    /// Revoking must be as easy as granting, and it takes effect before the
    /// next read rather than at some later sync.
    func revoke(_ source: ContextSource) {
        defaults.set(false, forKey: source.storageKey)
    }

    /// Make her allowed to ASK again. Clears the decline and nothing else.
    ///
    /// `mayAsk`'s own comment has always promised this — "unless the person
    /// opens the door themselves in Settings" — while `decline` was in fact
    /// permanent, because only `grant` ever cleared `declinedKey`. One "not
    /// now" silenced the source forever, which is the recoverability failure
    /// `CONSUMER-READINESS` B1 exists to forbid.
    ///
    /// It deliberately does NOT grant. Reopening does not hand her the
    /// calendar; it restores her permission to ask the next time there is a
    /// real reason, so the ask keeps its just-in-time justification instead of
    /// collapsing into a context-free switch in Settings — the anti-pattern
    /// `CONSUMER-READINESS` T4 calls canonical.
    func reopen(_ source: ContextSource) {
        defaults.set(false, forKey: source.declinedKey)
    }

    /// May she ASK about this source right now?
    ///
    /// Not "may she read" — that is `granted`. She may ask when she has neither
    /// been let in nor turned away. This is what stops the just-in-time moment
    /// from becoming nagging: one ask per source, ever, unless the person opens
    /// the door themselves in Settings.
    func mayAsk(_ source: ContextSource) -> Bool {
        !granted(source) && !declined(source)
    }
}

/// What she just took, said back to the person who let her in.
///
/// The other half of a grant. Until now a yes closed the ask sheet the instant
/// iOS answered: she took the address book and the surface that asked for it
/// vanished, which is the shape of a thing that got what it came for.
/// `design/day-zero.md` §2-3 already pays this debt on the supervised read —
/// you watch the read happen and every fact it produces is on screen — and the
/// two sources read on the phone owe it just as much, precisely because they
/// are read in milliseconds with nothing to watch.
///
/// PURE, AND HERE, for the reason `ContextSource.promises` is here: these are
/// sentences that must stay true of the reader, and a sentence written in a
/// view is a sentence no test ever reads. Every decision below — how many
/// lines stand in for how many, what the remainder says, what "nothing" means
/// — is testable with no phone in the room.
enum ContextReceipt {
    /// The lead-in. It claims completeness, so nothing below it may show a
    /// part of a set without saying how big the set was — see `lines`.
    ///
    /// It survives the caps rather than colliding with them: "everything I've
    /// got" is a claim about what SHE holds, and `maxEvents`/`maxNames` are
    /// the reason she holds fifteen and forty rather than a diary and an
    /// address book. It would only become false if the screen showed part of
    /// what she holds and said nothing about the rest.
    static let heading = "Here's everything I've got, and it's all I've got:"

    /// Nothing arrived. Deliberately NOT "your calendar is empty": an empty
    /// read and a read that could not happen — iOS granted a moment ago and
    /// `calendarReadable` not yet true, or contacts limited to a selection
    /// with nothing in it — produce the identical empty array here, and this
    /// type cannot tell them apart. So it says the thing it knows (nothing
    /// came back) and makes no claim at all about what is on the phone. Same
    /// argument as `ListeningDiagnosticsView.batteryWording`, which keeps
    /// "Not recorded" and "Nothing to compare yet" apart from a real number.
    static let nothing = "Nothing came back."

    /// How many lines stand in for the rest. Three, because this sheet does
    /// not scroll and fifteen serif lines would push the buttons off a small
    /// phone — and because the fourth line is not what a person is deciding
    /// about, the shape of the first three is. The wording below says "three"
    /// in words; `ContextReceiptTests` fails if this number stops being 3.
    static let shown = 3

    /// The lines to show, for a source that was just granted and just read.
    ///
    /// `facts` is what `LifeContext.facts(for:)` produced — the exact strings
    /// the grant sent for, shown verbatim rather than summarised, because a
    /// summary of what left the phone is not a receipt for it. `names` is the
    /// contacts read, needed separately for the reason below.
    static func lines(for source: ContextSource,
                      facts: [String] = [], names: [String] = []) -> [String] {
        switch source {
        case .calendar:
            guard !facts.isEmpty else { return [nothing] }
            var out = Array(facts.prefix(shown))
            // THE HEADING SAYS "all I've got". Three of fifteen with nothing
            // said about the other twelve makes that sentence false, and a
            // false sentence on a consent screen is the exact failure
            // `promises` carries a standing order against. The remainder is
            // counted, and it names its own shape so the count cannot read as
            // twelve things of some other kind.
            //
            // It counts what she HAS, not what has landed. A grant taken
            // underground reads its calendar and queues the post
            // (`AnticipyApp.sendContextFacts` returns without marking
            // delivered, and the next foreground retries the set), so a
            // remainder worded as "went with them" would assert a delivery
            // that has not happened on the one screen that must not assert
            // things that are not true.
            let rest = facts.count - out.count
            if rest == 1 {
                out.append("And 1 more, a title and a time.")
            } else if rest > 1 {
                out.append("And \(rest) more, each one a title and a time.")
            }
            return out
        case .contacts:
            // ONE line, because one row is what she sends:
            // `LifeContext.facts(for: .contacts)` joins every name into a
            // single fact row, so forty separate lines here would report a
            // shape the server never receives.
            guard !names.isEmpty else { return [nothing] }
            return [nameLine(names)]
        case .mail:
            // Unreachable, and empty rather than absent by accident. Mail is
            // never granted from the ask sheet (`ContextSource.mail:38-42`),
            // and its facts are distilled in the browser while you watch —
            // they arrive by a different path entirely, so there is nothing
            // this type could honestly report at the moment of the grant.
            return []
        }
    }

    /// "40 names. The first three are …" — the count first, because the count
    /// is the promise being kept ("at most forty names, once") and the names
    /// are the proof of what kind of thing they are.
    private static func nameLine(_ names: [String]) -> String {
        let unit = names.count == 1 ? "name" : "names"
        guard names.count > shown else {
            return "\(names.count) \(unit): \(list(names))."
        }
        return "\(names.count) \(unit). The first three are \(list(Array(names.prefix(shown))))."
    }

    /// "A, B and C". No Oxford comma, matching every other list in her voice.
    private static func list(_ items: [String]) -> String {
        guard let last = items.last else { return "" }
        guard items.count > 1 else { return last }
        return items.dropLast().joined(separator: ", ") + " and " + last
    }
}
