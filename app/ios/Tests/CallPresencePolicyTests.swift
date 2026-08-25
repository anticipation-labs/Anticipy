import Foundation

// Checks for CallPresencePolicy — what the telephony stack is doing, what the
// listener should do about it, and which conversation boundaries that produced.
//
// THE HOLE THIS CLOSES. A call is a hole in the day where the ears go deaf, and
// today it is indistinguishable from silence: `PhoneListener` learns only that
// the microphone is gone, never why, never when it stopped, never when it is
// over. Siri, a notification chime, a route change and a forty-minute call are
// one undifferentiated `suspended = true` to every line of code in the app.
//
// Every question this policy answers is a question about the call list and the
// clock, so all of them can be answered here — pure Foundation, like
// TranscriptFlushPolicy, ListenJournal, ListenTally, ListenResumePolicy,
// ListenWatchdogPolicy and ListenControlPolicy. No simulator, no scheme, no
// signing, no network, and — this is the entire point — no device that has to
// receive a real phone call before any of it can be checked.
//
// THE SWEEP AT THE BOTTOM IS THE REAL TEST. The named cases below it are the
// stories; the sweep is what makes them a contract, because the failures this
// sense can have are combinations — a second call arriving mid-call, a callback
// coalescing two transitions, an observation repeated — and a story per
// combination is a story nobody writes.

@main
struct CallPresencePolicyTests {
    static func main() {
        var checks = 0
        var failures: [String] = []

        func check(_ name: String, _ ok: Bool) {
            checks += 1
            if ok {
                print("  ok    \(name)")
            } else {
                failures.append(name)
                print("  FAIL  \(name)")
            }
        }

        typealias Policy = CallPresencePolicy
        typealias Call = Policy.Call
        typealias Boundary = Policy.Boundary

        let a = UUID(uuidString: "00000000-0000-0000-0000-0000000000AA")!
        let b = UUID(uuidString: "00000000-0000-0000-0000-0000000000BB")!

        let t0 = Date(timeIntervalSince1970: 1_756_000_000)
        func at(_ seconds: TimeInterval) -> Date { t0.addingTimeInterval(seconds) }

        func call(_ id: UUID,
                  outgoing: Bool = false,
                  connected: Bool = false,
                  ended: Bool = false,
                  onHold: Bool = false) -> Call {
            Call(id: id, isOutgoing: outgoing, hasConnected: connected,
                 hasEnded: ended, isOnHold: onHold)
        }

        // Replays a sequence of (call list, instant) through the policy the way
        // the sense will, carrying the state forward. Returns every verdict, so
        // a story can be asserted at whichever step it is about.
        func replay(_ steps: [(calls: [Call], now: Date)]) -> [Policy.Verdict] {
            var state = Policy.State.clear
            var out: [Policy.Verdict] = []
            for step in steps {
                let v = Policy.decide(was: state, sees: step.calls, now: step.now)
                state = v.state
                out.append(v)
            }
            return out
        }

        // ------------------------------------------------ 1. nothing at all
        let quiet = Policy.decide(was: .clear, sees: [], now: t0)
        check("no calls and none remembered is nothing to do",
              quiet.action == .nothing && quiet.boundaries.isEmpty
                  && quiet.state == .clear)

        // -------------------------------------- 2. a ring takes the mic early
        // An incoming call takes the audio session with the RINGTONE, before
        // anyone answers and whether or not anyone ever does. Standing down at
        // the connect instead would spend the whole ring minting recognition
        // tasks over an input that has already gone.
        let ringing = Policy.decide(was: .clear, sees: [call(a)], now: t0)
        check("a call that is only ringing already takes the microphone",
              ringing.action == .standDownForCall)
        check("...and a ring is not yet a conversation, so nothing is recorded",
              ringing.boundaries.isEmpty)

        // ------------------------------------------- 3. the declined ring
        // The mic went and came back and nobody said anything. The listener has
        // to be told; the day must not be.
        let declined = replay([(calls: [call(a)], now: t0),
                               (calls: [], now: at(9))])
        check("a declined ring hands the microphone back",
              declined[1].action == .retakeMicrophone)
        check("...and records no conversation, because there was none",
              declined[1].boundaries.isEmpty)
        check("...and forgets the call entirely",
              declined[1].state == .clear)

        // --------------------------------------- 4. the call that was watched
        let watched = replay([
            (calls: [call(a)], now: t0),                              // ringing
            (calls: [call(a, connected: true)], now: at(6)),          // answered
            (calls: [call(a, connected: true)], now: at(300)),        // still up
            (calls: [], now: at(2_406)),                              // hung up
        ])
        check("answering a watched ring opens a conversation at that instant",
              watched[1].boundaries == [.callOpened(at: at(6), outgoing: false,
                                                    sawItConnect: true)])
        check("a call already up produces no second opening",
              watched[2].boundaries.isEmpty)
        check("hanging up closes it, held for at least the time it was watched",
              watched[3].boundaries == [.callClosed(at: at(2_406), outgoing: false,
                                                    heldForAtLeast: 2_400,
                                                    sawItConnect: true)])

        // ------------------------------- 5. the call discovered in progress
        // The phone was suspended for the first thirty-nine minutes of a forty
        // minute call — `UIBackgroundModes: audio` buys execution only while
        // audio is flowing, and during a call none is. What comes back is a
        // FLOOR, and `sawItConnect: false` is the only thing standing between
        // this sense and a confident wrong number.
        let late = replay([
            (calls: [call(a, outgoing: true, connected: true)], now: at(2_340)),
            (calls: [], now: at(2_400)),
        ])
        check("a call first seen already up opens where it was seen, not where it began",
              late[0].boundaries == [.callOpened(at: at(2_340), outgoing: true,
                                                 sawItConnect: false)])
        check("...and closes carrying a floor, flagged as a floor",
              late[1].boundaries == [.callClosed(at: at(2_400), outgoing: true,
                                                 heldForAtLeast: 60,
                                                 sawItConnect: false)])
        check("...and the floor is honestly short rather than confidently wrong",
              {
                  guard case .callClosed(_, _, let held, let saw)? =
                      late[1].boundaries.first else { return false }
                  return held == 60 && saw == false
              }())

        // ------------------------------------------------------- 6. on hold
        // Hold is a pause in one conversation, not the end of it and the start
        // of another. Emitting boundaries for it would cut a single call into
        // segments at exactly the moments least likely to matter.
        let held = replay([
            (calls: [call(a)], now: t0),
            (calls: [call(a, connected: true)], now: at(5)),
            (calls: [call(a, connected: true, onHold: true)], now: at(60)),
            (calls: [call(a, connected: true)], now: at(90)),
            (calls: [], now: at(120)),
        ])
        check("going on hold is not a boundary", held[2].boundaries.isEmpty)
        check("coming off hold is not a boundary", held[3].boundaries.isEmpty)
        check("the microphone stays gone across a hold",
              held[2].action == .standDownForCall && held[3].action == .standDownForCall)
        check("and the whole thing closes as ONE call, measured from the answer",
              held[4].boundaries == [.callClosed(at: at(120), outgoing: false,
                                                 heldForAtLeast: 115,
                                                 sawItConnect: true)])

        // ------------------------------------------------- 7. call waiting
        // Two live calls. The one that matters is the one being spoken on, and a
        // second call arriving must not silently steal the presence and report a
        // conversation ending that did not end.
        let waiting = replay([
            (calls: [call(a)], now: t0),
            (calls: [call(a, connected: true)], now: at(5)),
            (calls: [call(a, connected: true), call(b)], now: at(200)),
        ])
        check("a second call ringing does not end the one being spoken on",
              waiting[2].boundaries.isEmpty && waiting[2].state.callID == a)

        // ...and the swap, which arrives as ONE callback: A ends, B connects.
        let swapped = Policy.decide(
            was: waiting[2].state,
            sees: [call(a, connected: true, ended: true),
                   call(b, connected: true)],
            now: at(260))
        check("swapping calls closes the first and opens the second, in that order",
              swapped.boundaries == [
                  .callClosed(at: at(260), outgoing: false,
                              heldForAtLeast: 255, sawItConnect: true),
                  .callOpened(at: at(260), outgoing: false, sawItConnect: true),
              ])
        check("...and the presence moves to the call now being spoken on",
              swapped.state.callID == b)

        // THE SECOND CALL WAS WATCHED EVERY SECOND OF, AND THE FLAG SAYS SO.
        // This is what the leading-call-only version of `State` got wrong: it
        // remembered one call, so a call that rang through somebody else's
        // conversation lost the fact that it had been watched arriving, and its
        // opening claimed `sawItConnect: false` about a call seen from its first
        // ring. The floor stayed correct — it is the epistemic flag itself that
        // lied, in the safe direction, which is still the one field it exists to
        // get right being wrong.
        check("a call that rang through another conversation is still watched",
              {
                  guard case .callOpened(_, _, let saw)? =
                      swapped.boundaries.last else { return false }
                  return saw == true
              }())
        // ...whereas one that was never seen ringing still under-claims, which
        // is the behaviour that must survive the fix above.
        let barged = Policy.decide(
            was: Policy.State(callID: a, isOutgoing: false,
                              connectedSeenAt: at(-30), sawItConnect: true),
            sees: [call(b, connected: true)],
            now: at(400))
        check("a call that appeared already connected is still honestly unvouched",
              barged.boundaries.contains(.callOpened(at: at(400), outgoing: false,
                                                     sawItConnect: false)))

        // A call that was already remembered and is on hold loses to the active
        // one, and that is a promotion rather than an ending of the held call.
        let promoted = Policy.decide(
            was: swapped.state,
            sees: [call(b, connected: true, onHold: true),
                   call(a, connected: true)],
            now: at(300))
        check("an active call outranks a held one",
              promoted.state.callID == a)

        // A DISPLACED CALL CLOSES, AND THE ACTION IS WHAT SAYS THE PHONE IS
        // STILL BUSY. The owner stopped talking to B at that instant, so the
        // stretch is over and pretending it ran on through A would be the lie.
        // But B has not ended, and a post-call prompt keyed on the close alone
        // would interrupt somebody in the middle of their second call. The
        // `Action` in the same verdict is what stops that, which is the whole
        // argument for one value over three functions.
        check("displacing a call closes its stretch of conversation",
              promoted.boundaries.contains { if case .callClosed = $0 { return true }
                                             else { return false } })
        check("...but the listener is told the phone is still busy, not free",
              promoted.action == .standDownForCall)
        check("...and a real hang-up is the one that hands the microphone back",
              watched[3].action == .retakeMicrophone)

        // Resuming the displaced call opens it again, and this device watched
        // every second of that too — the ringing-only version of `seenLive`
        // could say so about neither this nor the call-waiting arrival above.
        let resumed = Policy.decide(
            was: promoted.state,
            sees: [call(b, connected: true),
                   call(a, connected: true, onHold: true)],
            now: at(360))
        check("resuming a displaced call re-opens it as a watched conversation",
              resumed.boundaries.contains(.callOpened(at: at(360), outgoing: false,
                                                      sawItConnect: true)))

        // -------------------------------------------- 8. an ended call lingers
        // `hasEnded` is delivered as a change before the call leaves the list.
        // A sense that read `calls.isEmpty` would stand down for an extra beat.
        let lingering = replay([
            (calls: [call(a)], now: t0),
            (calls: [call(a, connected: true)], now: at(4)),
            (calls: [call(a, connected: true, ended: true)], now: at(64)),
        ])
        check("a call marked ended is not live, whatever the list still contains",
              lingering[2].action == .retakeMicrophone
                  && lingering[2].state == .clear)
        check("...and it closes on that tick rather than the next one",
              lingering[2].boundaries == [.callClosed(at: at(64), outgoing: false,
                                                      heldForAtLeast: 60,
                                                      sawItConnect: true)])

        // ---------------------------------------------- 9. the clock moved back
        // A timezone crossing or an NTP correction between two observations
        // would otherwise report a call that lasted a negative number of
        // seconds, and a consumer that formats that has been handed nonsense by
        // its senses.
        let backwards = Policy.decide(
            was: Policy.State(callID: a, isOutgoing: false,
                              connectedSeenAt: at(500), sawItConnect: true),
            sees: [], now: at(200))
        check("a clock that moved backwards cannot produce a negative call",
              backwards.boundaries == [.callClosed(at: at(200), outgoing: false,
                                                   heldForAtLeast: 0,
                                                   sawItConnect: true)])

        // --------------------------------------------- 10. the outgoing call
        let outgoing = replay([
            (calls: [call(a, outgoing: true)], now: t0),
            (calls: [call(a, outgoing: true, connected: true)], now: at(11)),
            (calls: [], now: at(71)),
        ])
        check("the direction survives to the close, when the call cannot be asked any more",
              outgoing[2].boundaries == [.callClosed(at: at(71), outgoing: true,
                                                     heldForAtLeast: 60,
                                                     sawItConnect: true)])

        // ------------------------------------ 11. retake is an EDGE, not a state
        // `PhoneListener`'s background assertion was taken on every write of
        // `suspended` rather than on its edge, and a ten-minute call renewed a
        // thirty-second grant a hundred and fifty times. The same shape here is
        // a capture rebuild per callback, forever, over a microphone that is
        // already back.
        let after = replay([
            (calls: [call(a, connected: true)], now: t0),
            (calls: [], now: at(60)),
            (calls: [], now: at(64)),
            (calls: [], now: at(68)),
        ])
        check("the microphone is retaken once when the call goes",
              after[1].action == .retakeMicrophone)
        check("...and not again on every observation after it",
              after[2].action == .nothing && after[3].action == .nothing)

        // ------------------------------------------- 12. the floor never shrinks
        // The instant is stamped once and never re-stamped. Re-stamping on each
        // callback would make a long call report a duration that shrinks toward
        // zero the more often the sense is asked.
        var floorState = Policy.State.clear
        var floors: [TimeInterval] = []
        for tick in stride(from: 0.0, through: 600.0, by: 30.0) {
            let v = Policy.decide(was: floorState,
                                  sees: [call(a, connected: true)],
                                  now: at(tick))
            floorState = v.state
            let close = Policy.decide(was: floorState, sees: [], now: at(tick))
            if case .callClosed(_, _, let held, _)? = close.boundaries.first {
                floors.append(held)
            }
        }
        check("the held-for floor only ever grows as a call goes on",
              floors.count == 21 && floors == floors.sorted() && floors.last == 600)

        // ================================================== THE SWEEP
        // Every prior state against every call list this sense can be handed,
        // asserting the invariants that make the stories above a contract
        // rather than twelve anecdotes.
        let priors: [Policy.State] = [
            .clear,
            Policy.State(callID: a, isOutgoing: false, connectedSeenAt: nil,
                         sawItConnect: false),
            Policy.State(callID: a, isOutgoing: true, connectedSeenAt: at(-60),
                         sawItConnect: true),
            Policy.State(callID: a, isOutgoing: false, connectedSeenAt: at(-60),
                         sawItConnect: false),
            Policy.State(callID: b, isOutgoing: true, connectedSeenAt: nil,
                         sawItConnect: false),
            Policy.State(callID: b, isOutgoing: false, connectedSeenAt: at(-5),
                         sawItConnect: true),
        ]

        // All sixteen flag combinations of one call, for each of two identities.
        func variants(_ id: UUID) -> [Call] {
            var out: [Call] = []
            for outgoing in [false, true] {
                for connected in [false, true] {
                    for ended in [false, true] {
                        for onHold in [false, true] {
                            out.append(call(id, outgoing: outgoing,
                                            connected: connected,
                                            ended: ended, onHold: onHold))
                        }
                    }
                }
            }
            return out
        }
        var lists: [[Call]] = [[]]
        for v in variants(a) { lists.append([v]) }
        for va in variants(a) {
            for vb in variants(b) { lists.append([va, vb]) }
        }

        var sweep = 0
        var wrongAction = 0
        var tooManyBoundaries = 0
        var outOfOrder = 0
        var negativeHeld = 0
        var strandedInstant = 0
        var unboundedSet = 0
        var closeMisreadsTheMic = 0
        var notIdempotent = 0
        var notDeterministic = 0
        var openedWithoutConnection = 0
        var closedWithoutConnection = 0

        for was in priors {
            for calls in lists {
                let now = at(1_000)
                let v = Policy.decide(was: was, sees: calls, now: now)
                sweep += 1

                let live = calls.filter { !$0.hasEnded }

                // 1. THE MICROPHONE. Any live call at all — ringing included —
                //    and the listener stands down. None, and it retakes only if
                //    something was there to give it back.
                let expected: Policy.Action = live.isEmpty
                    ? (was.callID == nil ? .nothing : .retakeMicrophone)
                    : .standDownForCall
                if v.action != expected { wrongAction += 1 }

                // 2. At most two boundaries, and a close always precedes an
                //    open. One callback can end one call and connect another;
                //    it can never do more than that.
                if v.boundaries.count > 2 { tooManyBoundaries += 1 }
                if v.boundaries.count == 2 {
                    if case .callClosed = v.boundaries[0] {} else { outOfOrder += 1 }
                    if case .callOpened = v.boundaries[1] {} else { outOfOrder += 1 }
                }

                // 3. No conversation ever lasted a negative length of time.
                for boundary in v.boundaries {
                    if case .callClosed(_, _, let held, _) = boundary, held < 0 {
                        negativeHeld += 1
                    }
                }

                // 4. A remembered instant with no call to belong to is a floor
                //    that will be measured against the wrong conversation. And
                //    the set of calls this device had in view IS the live list,
                //    which is what bounds it: one that only ever grew would be a
                //    leak with a sense's name on it, kept alive for the whole
                //    life of the process.
                if v.state.callID == nil && v.state.connectedSeenAt != nil {
                    strandedInstant += 1
                }
                if v.state.seenLive != Set(live.map { $0.id }) {
                    unboundedSet += 1
                }

                // 5. NOTHING IS OPENED THAT IS NOT CONNECTED, and nothing is
                //    closed that was never connected. A declined ring is not a
                //    conversation, and neither is a call that is still ringing.
                for boundary in v.boundaries {
                    switch boundary {
                    case .callOpened:
                        if v.state.connectedSeenAt == nil { openedWithoutConnection += 1 }
                    case .callClosed:
                        if was.connectedSeenAt == nil { closedWithoutConnection += 1 }
                    }
                }

                // 6. IDEMPOTENT. The same list observed again changes nothing
                //    and records nothing. Without this a sense polled once a
                //    second writes a conversation boundary once a second.
                let again = Policy.decide(was: v.state, sees: calls,
                                          now: now.addingTimeInterval(4))
                if !again.boundaries.isEmpty || again.state != v.state {
                    notIdempotent += 1
                }

                // 7. And the same question twice gets the same answer.
                let repeated = Policy.decide(was: was, sees: calls, now: now)
                if repeated != v { notDeterministic += 1 }

                // 8. A CLOSE NEVER IMPLIES A FREE MICROPHONE ON ITS OWN. The
                //    action beside it is the only thing that says so, and a
                //    consumer that reads the close alone would interrupt
                //    somebody in the middle of the call they just switched to.
                let closed = v.boundaries.contains {
                    if case .callClosed = $0 { return true } else { return false }
                }
                if closed && ((v.action == .retakeMicrophone) != live.isEmpty) {
                    closeMisreadsTheMic += 1
                }
            }
        }

        check("the sweep covers every prior state against every call list",
              sweep == 6 * (1 + 16 + 256))
        check("the microphone is stood down for every live call and retaken exactly on the edge",
              wrongAction == 0)
        check("no observation ever produces more than a close and an open, in that order",
              tooManyBoundaries == 0 && outOfOrder == 0)
        check("no conversation ever lasted a negative length of time",
              negativeHeld == 0)
        check("no remembered instant is left without a call to belong to",
              strandedInstant == 0)
        check("the remembered set of calls in view is exactly the live ones",
              unboundedSet == 0)
        check("nothing is opened that never connected, and nothing closed that never did",
              openedWithoutConnection == 0 && closedWithoutConnection == 0)
        check("observing the same call list again records nothing and changes nothing",
              notIdempotent == 0)
        check("the same facts always produce the same verdict",
              notDeterministic == 0)
        check("a close hands the microphone back only when nothing is left on the line",
              closeMisreadsTheMic == 0)

        // AND NOTHING IN HERE KNOWS WHO WAS ON THE CALL, because `CXCall` does
        // not carry it. Asserted as a fact about the type rather than left as a
        // sentence in a comment: a `Call` is built from exactly the five things
        // Apple exposes, so if a maintainer ever adds a handle to it, they have
        // to add it here first and this test is where they will notice they
        // cannot get one.
        let mirrored = Mirror(reflecting: call(a)).children.compactMap { $0.label }
        check("a call carries the five things CXCall carries, and no identity",
              mirrored == ["id", "isOutgoing", "hasConnected", "hasEnded", "isOnHold"])

        // ------------------------------------------------------------ result
        print("")
        if failures.isEmpty {
            print("CallPresencePolicy: all \(checks) checks passed")
        } else {
            print("CallPresencePolicy: \(failures.count)/\(checks) FAILED")
            for f in failures { print("  - \(f)") }
            exit(1)
        }
    }
}
