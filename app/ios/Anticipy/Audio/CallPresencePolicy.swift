import Foundation

/// What the telephony stack is doing, what the listener should do about it, and
/// which conversation boundaries that produced.
///
/// WHY THIS FILE EXISTS. A call is a hole in the day where the ears go deaf, and
/// today that hole is indistinguishable from silence. `PhoneListener` learns the
/// microphone is gone — from `AVAudioSession.interruptionNotification`, or from
/// the 0 Hz guard at `configureAndStartEngine` refusing to tap an input that
/// reports no sample rate — and `suspended` says so honestly. What it never
/// learns is WHY, or WHEN it stopped, or WHEN it is over. Siri, a notification
/// chime, a route change and a forty-minute call are one undifferentiated
/// `suspended = true` to every line of code in this app.
///
/// CallKit closes that. `CXCallObserver` needs no entitlement — Apple's own
/// documentation for it says "any app can create a new CXCallObserver object to
/// be notified of any calls activity on the system" — and it is the one sense
/// that can say "a call is happening" and, more valuably, "the call is over"
/// even on the ticks where iOS never delivers an `.ended` notification at all.
///
/// WHAT IT CANNOT DO, SAID FIRST SO NOBODY BUILDS ON A HOPE. A third-party iOS
/// app cannot record the audio of a call. Not the far end, not the owner's own
/// side. That is refused by the operating system, it has been measured on this
/// repo's own hardware as the 0 Hz guard, and the whole argument with its
/// sources is `docs/superpowers/specs/2026-08-25-ios-call-recorder.md`. This
/// file is the part of that card which is legal, and it must never be described
/// as the recorder it is not.
///
/// WHAT `CXCall` ACTUALLY CARRIES, read from the CallKit headers in the
/// iPhoneOS 26.2 SDK rather than from memory: `UUID`, `isOutgoing`, `isOnHold`,
/// `hasConnected`, `hasEnded`. That is the entire surface. **No phone number,
/// no name, no handle, no start date, no duration.** So this sense can know
/// that an outgoing call was connected and is now over, and can know NOTHING
/// AT ALL about who was on it. That thinness is the feature: it is
/// `design/LOCAL-FIRST.md` rule 3's "smallest conclusion that works" arriving
/// for free, and a sense that has no identity cannot leak one.
///
/// HARNESS-LAWS.md LAW 1, stated before anyone objects. A `CXCall` callback is
/// a fact the operating system reports about its own telephony stack. It is not
/// a pattern over the owner's words, and nothing here decides what anything
/// MEANS — there is no regex, no word list, and deliberately no duration
/// threshold anywhere below. `run_call_presence_tests.sh` fails the build if a
/// duration constant appears in this file, because "a call longer than N
/// minutes deserves a message" is a threshold deciding meaning wearing a
/// sense's clothes. The boundary this file emits carries how long the call was
/// held; something with full context decides what that is worth.
///
/// AND WHETHER FaceTime IS IN THIS STREAM IS UNVERIFIED. The card that asked
/// for this names FaceTime explicitly. Apple's CallKit documentation does not
/// name FaceTime, and neither does any public header in the iPhoneOS 26.2 SDK —
/// `grep -ri facetime` over every framework header in that SDK returns nothing
/// at all. So there is no source that says FaceTime calls appear here and no
/// source that says they do not, and only a device can settle it. Nothing in
/// this file may be rendered to the owner as "a phone call": every name below
/// says `call`, meaning "whatever the telephony provider told us about", and
/// the runner fails the build if this file starts claiming otherwise.
///
/// Pure Foundation, like `TranscriptFlushPolicy`, `ListenJournal`,
/// `ListenTally`, `ListenResumePolicy`, `ListenWatchdogPolicy` and
/// `ListenControlPolicy`: a decision that can be shown to fail with `swiftc`
/// alone — no simulator, no signing, no network, and no device that has to
/// receive a real phone call before the answer can be checked. That last clause
/// is the entire reason this is a file and not four lines inside a delegate
/// method, because a delegate method for a phone call is a decision nothing in
/// this repo can prove wrong.
struct CallPresencePolicy {

    /// One call, carrying exactly what `CXCall` carries and nothing more.
    ///
    /// Deliberately a plain value rather than the framework type: it keeps this
    /// file free of CallKit so it compiles on macOS with `swiftc`, and it makes
    /// the property list above a thing a reader can check rather than trust.
    /// Anything a future maintainer wants to add here has to exist on `CXCall`
    /// first, and nothing else does.
    struct Call: Equatable {
        let id: UUID
        let isOutgoing: Bool
        let hasConnected: Bool
        let hasEnded: Bool
        let isOnHold: Bool

        init(id: UUID,
             isOutgoing: Bool,
             hasConnected: Bool,
             hasEnded: Bool,
             isOnHold: Bool) {
            self.id = id
            self.isOutgoing = isOutgoing
            self.hasConnected = hasConnected
            self.hasEnded = hasEnded
            self.isOnHold = isOnHold
        }
    }

    /// What the listener should do about the telephony stack this instant.
    ///
    /// NOT whether it should be listening at all. That is the owner's standing
    /// wish and `ListenResumePolicy` already owns it; asking it twice is how two
    /// right answers to different questions end up rendered on one control,
    /// which is the defect `ListenControlPolicy` was written about.
    enum Action: Equatable {
        /// A call is live and the microphone belongs to it. Do not rebuild the
        /// engine for it, do not mint a recognition task that can hear nothing.
        ///
        /// Fires on EVERY observation while a call is up, not only on the edge,
        /// and that is safe precisely because the instruction is to do nothing:
        /// an idempotent "stand still" cannot be carried out twice wrongly. Its
        /// opposite below costs a capture rebuild, so that one is edge-only.
        case standDownForCall

        /// The last call left the system. The microphone MAY be ours again —
        /// try it, and let the 0 Hz guard decide, because a call ending with the
        /// phone in a pocket still finds an input reporting nothing.
        ///
        /// EDGE ONLY. `PhoneListener`'s background assertion was taken on every
        /// write of `suspended` rather than on its edge, and a ten-minute call
        /// renewed a thirty-second grant a hundred and fifty times; the same
        /// shape here would be a capture rebuild per callback.
        case retakeMicrophone

        /// Nothing about the telephony stack changed that the listener cares
        /// about.
        case nothing
    }

    /// A ground-truth conversation boundary.
    ///
    /// `CAPTURE-ARCHITECTURE.md` Level 3 decides segment boundaries from
    /// capture-time silence, which is a heuristic over ambience. A call
    /// connecting and a call ending are not heuristics: they are the telephony
    /// stack reporting its own state, they cost no model call, and they are
    /// right in a noisy room and a quiet one alike.
    ///
    /// EVERY INSTANT HERE IS THIS DEVICE'S OBSERVATION, NOT THE CALL'S TRUTH,
    /// and the names say so rather than letting a consumer assume. The phone can
    /// be suspended across the moment a call connects — `UIBackgroundModes:
    /// audio` buys execution only while audio is flowing, and during a call none
    /// is — so what this file reports is always a bound it can defend, never a
    /// measurement it cannot.
    enum Boundary: Equatable {
        /// A call became connected: from here on, someone is being spoken to.
        ///
        /// `at` is the instant this device FIRST SAW it connected, which is at
        /// or after the real one. `sawItConnect` says which: true means the call
        /// was in view before it connected, so `at` is close; false means it was
        /// already up the first time this device looked, and the real connect
        /// was some unknown amount earlier.
        case callOpened(at: Date, outgoing: Bool, sawItConnect: Bool)

        /// A connected call left the system.
        ///
        /// `heldForAtLeast` is a FLOOR and never a duration: it is measured from
        /// the first instant this device was certain the call was connected, so
        /// a forty-minute call the phone only noticed at minute thirty-nine
        /// reports "at least one minute" — true, and honestly useless. That is
        /// the correct failure. `sawItConnect` is how a consumer tells the two
        /// apart, and it is the only thing standing between this sense and a
        /// confident wrong number.
        ///
        /// NO BOUNDARY IS EMITTED FOR A CALL THAT NEVER CONNECTED. A ring that
        /// was declined, or an outgoing call nobody picked up, took the
        /// microphone and gave it back — the listener is told about that through
        /// `Action` — but nothing was said, so there is no conversation to bound.
        ///
        /// AND THIS ALSO FIRES WHEN A CALL IS DISPLACED RATHER THAN ENDED. Call
        /// waiting: the owner puts the first call on hold and speaks on the
        /// second, so the first stretch of conversation is over even though that
        /// call is still live. It is the same boundary — the owner stopped
        /// talking to that person at that instant — and pretending the first
        /// call ran continuously through the second would be the lie.
        ///
        /// SO A CONSUMER MUST NOT READ THIS AS "THE PHONE IS FREE NOW", and it
        /// does not have to: the `Action` in the same `Verdict` says which it
        /// is. `.retakeMicrophone` beside a close means the last call left and
        /// the microphone may be back; `.standDownForCall` beside a close means
        /// the owner simply moved to another call and is still on the phone.
        /// This is precisely why the three answers ride in one value instead of
        /// being three functions a caller can ask separately — a post-call
        /// prompt keyed on the close alone would interrupt somebody in the
        /// middle of their second call.
        case callClosed(at: Date,
                        outgoing: Bool,
                        heldForAtLeast: TimeInterval,
                        sawItConnect: Bool)
    }

    /// Everything the sense has to remember between observations. All of it.
    ///
    /// Small on purpose: a sense that accumulates is a sense that can be wrong
    /// about the past, and this one is asked to be right about the present.
    struct State: Equatable {
        /// The call this presence is about — the most engaged live one.
        var callID: UUID?
        /// Carried so the CLOSE can name the direction of a call that has
        /// already left `calls` and cannot be asked any more.
        var isOutgoing: Bool
        /// The earliest instant this device was certain that call was
        /// connected. Nil while it is only ringing, and nil when there is no
        /// call.
        var connectedSeenAt: Date?
        /// Did this device have the call in view BEFORE it connected?
        ///
        /// Not a claim that the process was awake for every second afterwards —
        /// it can be frozen across the connect and set this true while
        /// `connectedSeenAt` lands late. It is the weaker, checkable claim:
        /// this device watched the call arrive rather than discovering it
        /// already in progress.
        var sawItConnect: Bool

        /// Every call that was live the last time this device looked — not only
        /// the one in front.
        ///
        /// THE FIELD EXISTS BECAUSE CALL WAITING BREAKS THE ONE-CALL VERSION.
        /// A second call rings while the first is being spoken on, so it is
        /// live and watched but it is not the presence; when the first ends and
        /// the second connects in the same callback, a state that remembered
        /// only the leading call has lost the fact that it watched the second
        /// one arrive, and reports `sawItConnect: false` about a call it saw
        /// every second of. The floor stays correct either way, so this is not
        /// a wrong number — it is the epistemic flag itself lying, in the safe
        /// direction, which is still the field being wrong about the one thing
        /// it exists to say.
        ///
        /// EVERY LIVE CALL, NOT ONLY THE RINGING ONES, and the wider set is the
        /// simpler one as well as the more correct. `sawItConnect` asks whether
        /// this device had the call in view BEFORE the instant it is now
        /// reporting — and a call displaced by call waiting and later resumed is
        /// one this device watched every second of too, which the ringing-only
        /// version could not say either.
        ///
        /// BOUNDED BY CONSTRUCTION: it IS the live call list, so it cannot
        /// outgrow it. A set that only ever grew would be a leak with a sense's
        /// name on it.
        var seenLive: Set<UUID>

        static let clear = State(callID: nil,
                                 isOutgoing: false,
                                 connectedSeenAt: nil,
                                 sawItConnect: false,
                                 seenLive: [])

        init(callID: UUID?,
             isOutgoing: Bool,
             connectedSeenAt: Date?,
             sawItConnect: Bool,
             seenLive: Set<UUID> = []) {
            self.callID = callID
            self.isOutgoing = isOutgoing
            self.connectedSeenAt = connectedSeenAt
            self.sawItConnect = sawItConnect
            self.seenLive = seenLive
        }
    }

    /// One answer, carrying all three things this instant decided.
    ///
    /// ONE VALUE RATHER THAN THREE FUNCTIONS, and that is the lesson
    /// `ListenControlPolicy` paid for: the label, the tap and the glyph were
    /// three right answers to three questions about one control, and they
    /// drifted. What to remember, what the listener does, and what the day
    /// records are decided from the same facts at the same instant, so a caller
    /// that could ask for one without the others would eventually record a call
    /// ending it never told the listener about.
    struct Verdict: Equatable {
        let state: State
        let action: Action
        /// Ordered, and CLOSE COMES BEFORE OPEN. Call waiting ends one call and
        /// connects another in a single callback, so an answer that could carry
        /// only one boundary would drop a whole conversation's ending on the
        /// commonest reason two calls ever exist at once. At most two.
        let boundaries: [Boundary]
    }

    /// Fold what the observer can see into what is true, what to do, and what
    /// to record.
    ///
    /// TAKES THE WHOLE LIST, NOT THE CHANGED CALL. `CXCallObserverDelegate` has
    /// exactly one method — `callObserver(_:callChanged:)` — and it hands over a
    /// single call. There is no "started" callback and no "ended" callback;
    /// every transition in this product has to be derived. Deriving it from one
    /// call at a time means a missed or coalesced callback is a state this sense
    /// never leaves, whereas `CXCallObserver.calls` is authoritative, cheap and
    /// complete. So the caller passes the list, on every callback AND whenever
    /// the app comes back to the foreground, and this function is total over it:
    /// the same code path that handles a callback handles "what happened while
    /// we were suspended", which is the case a call sense exists for.
    ///
    /// THE ORDER IS THE BEHAVIOUR. Each step below is only meaningful because
    /// the ones above it have already run.
    static func decide(was: State, sees calls: [Call], now: Date) -> Verdict {
        // A call marked ended is not a live call, and it lingers in the list for
        // an instant after it stops. Filtering first is what makes "is anything
        // holding the microphone" a question about the present tense.
        let live = calls.filter { !$0.hasEnded }

        // THE MOST ENGAGED CALL WINS. During call waiting there are two, and the
        // one that matters is the one being spoken on — a call on hold is not
        // taking the microphone from the other one.
        //
        // Ties are broken toward the call already remembered, so a second call
        // arriving at equal rank cannot silently steal the presence and report a
        // conversation ending that did not end.
        let lead = live.max { a, b in
            let ra = engagement(a), rb = engagement(b)
            if ra != rb { return ra < rb }
            // Equal rank: the remembered call is "greater", so `max` keeps it.
            if b.id == was.callID { return true }
            return false
        }

        // WHICH CALLS THIS DEVICE HAD IN VIEW. Simply the live ones, carried to
        // the next observation so the question "was this call already in front
        // of us before now?" has an answer for every call rather than only for
        // the one that happened to be the presence. Call waiting is the reason
        // it has to be a set: the second call rings through the first
        // conversation, and the fact that it was watched has to survive until it
        // is promoted.
        let liveIDs = Set(live.map { $0.id })

        var boundaries: [Boundary] = []

        // ------------------------------------------------------ 1. the close
        // The remembered call is no longer the one in front of us: it ended, or
        // call waiting promoted another. Either way its ending is now, and it is
        // the last moment anything can be said about it — `calls` no longer
        // carries it and `CXCall` has no history to ask.
        if let previous = was.callID, lead?.id != previous {
            if let connectedAt = was.connectedSeenAt {
                boundaries.append(.callClosed(
                    at: now,
                    outgoing: was.isOutgoing,
                    // FLOORED AT ZERO. A clock that moved backwards between two
                    // observations — the owner crossing a timezone, an NTP
                    // correction — would otherwise report a call that lasted a
                    // negative number of seconds, and a consumer that formats
                    // that has been handed nonsense by its senses.
                    heldForAtLeast: max(0, now.timeIntervalSince(connectedAt)),
                    sawItConnect: was.sawItConnect))
            }
            // ...and if it never connected, nothing is recorded. A declined ring
            // is not a conversation. The microphone still went and came back,
            // and step 3 is what tells the listener so.
        }

        // ------------------------------------------------------- 2. the open
        guard let call = lead else {
            // Nothing live. `.retakeMicrophone` only if something WAS — the edge,
            // for the reason spelled out on the case.
            return Verdict(state: .clear,
                           action: was.callID == nil ? .nothing : .retakeMicrophone,
                           boundaries: boundaries)
        }

        var state = State(callID: call.id,
                          isOutgoing: call.isOutgoing,
                          connectedSeenAt: nil,
                          sawItConnect: false,
                          seenLive: liveIDs)

        if call.id == was.callID {
            // Same call as last time. Carry what was already established: the
            // instant is never re-stamped, because the earliest instant this
            // device was certain is the only one that keeps `heldForAtLeast` a
            // floor rather than a guess that shrinks on every callback.
            //
            // A call going on and off hold lands here and changes nothing, and
            // must not. Hold is a pause in one conversation, not the end of it
            // and the start of another, and emitting boundaries for it would cut
            // a single call into segments at exactly the moments least likely to
            // matter.
            state.connectedSeenAt = was.connectedSeenAt
            state.sawItConnect = was.sawItConnect
        }

        // THE OPENING, and it is one condition for both the call already in
        // front and the one just promoted, because it is one question: is this
        // the first instant this device is certain somebody is being spoken to?
        // Two branches asking it separately is how the call-waiting case came to
        // answer it differently from the ordinary one.
        if call.hasConnected, state.connectedSeenAt == nil {
            state.connectedSeenAt = now
            // Did this device have this particular call in view before now? Read
            // off the set rather than inferred from which branch we are in — a
            // call that rang through somebody else's conversation, and one
            // displaced by call waiting and later resumed, were both watched
            // every second of, and the leading-call-only version could say so
            // about neither.
            state.sawItConnect = was.seenLive.contains(call.id)
            boundaries.append(.callOpened(at: now,
                                          outgoing: call.isOutgoing,
                                          sawItConnect: state.sawItConnect))
        }
        // Not connected: ringing or dialling. Remembered so the connect can be
        // watched for, and no boundary — nobody is talking to anybody yet.

        // ------------------------------------------------- 3. the microphone
        // Any live call at all, ringing included. An incoming call takes the
        // audio session with the ringtone, before anyone answers and whether or
        // not anyone ever does, so the listener has to stand down from the ring
        // rather than from the connect.
        return Verdict(state: state, action: .standDownForCall, boundaries: boundaries)
    }

    /// How much of the microphone a call is holding, as an order rather than a
    /// meaning. Private because it is an implementation of "which call is the
    /// one being spoken on", not a fact about the world anything else should
    /// read.
    private static func engagement(_ call: Call) -> Int {
        if call.hasConnected && !call.isOnHold { return 3 }
        if call.hasConnected { return 2 }
        return 1
    }
}
