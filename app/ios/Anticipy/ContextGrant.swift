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
    var promises: [String] {
        switch self {
        case .calendar:
            return ["I read what's coming up for the next month: the title and the time.",
                    "I never read the notes, the invitees, or anything in the past.",
                    "I send myself one line per event: that title and that time. Never the calendar itself.",
                    "Nothing goes in your calendar unless you tell me to put it there."]
        case .contacts:
            return ["I read the names, so I know who you mean when you say one.",
                    "I never read a number, an email, or an address.",
                    "I send myself the list of names, once. Those three things never leave this phone.",
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
