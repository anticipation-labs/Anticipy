import Foundation
import CallKit

/// The adapter that gives `CallPresencePolicy` something to see.
///
/// The policy has been correct and completely inert since it was written: 44
/// passing checks and zero call sites, with `run_all.sh` printing the fact on
/// every run — "nothing in the running app knows a call is happening yet." This
/// is the missing half. It owns a `CXCallObserver`, turns what CallKit reports
/// into the policy's `Call` values, and carries out the verdict.
///
/// NO ENTITLEMENT IS NEEDED and that is why this shape was chosen: Apple's own
/// documentation says any app may create a `CXCallObserver`. Nothing here reads
/// a phone number, a name, or any audio from the call — CallKit does not offer
/// those to an observer, and this file must never grow a way to want them.
///
/// WHAT IT IS FOR. A phone call is a hole in the day where the ears go deaf: iOS
/// takes the microphone and the interruption notification says only that
/// something happened, never what. Without a call sense, a forty-minute call and
/// a forty-minute silence are the same event in the journal, and the resume
/// policy has to guess. With it, the gap has a shape: a call opened, it lasted
/// at least this long, it closed.
///
/// THE WHOLE LIST, NEVER THE CHANGED CALL. `CXCallObserverDelegate` has exactly
/// one method and it hands over a single call — there is no "started" and no
/// "ended". Deriving transitions from one call at a time makes a missed or
/// coalesced callback a state the sense never leaves. `observer.calls` is
/// authoritative, cheap, and readable at any moment, so the policy is asked
/// about the whole list every time and the delegate argument is deliberately
/// ignored.
final class CallSense: NSObject, CXCallObserverDelegate {
    /// What to do when the policy says the microphone must go, or may come back.
    ///
    /// Closures rather than a reference to `PhoneListener`: this file is a
    /// sense, and a sense that can reach into the thing it informs is one
    /// refactor from deciding on its own. The listener wires itself in.
    private let standDown: () -> Void
    private let retake: () -> Void
    /// Where a boundary goes is the OWNER'S decision, not this file's.
    ///
    /// `ListenEvent` has no case that carries a call, and inventing one would
    /// mean changing what `ListenTally` folds and what the diagnostics screen
    /// reads back — a tested surface, on a commit whose subject is the
    /// microphone. So the sense hands the boundary up and the wiring site
    /// decides. Nothing is dropped, and nothing tested is disturbed.
    private let onBoundary: (CallPresencePolicy.Boundary) -> Void

    private let observer = CXCallObserver()
    private var state = CallPresencePolicy.State(callID: nil,
                                                 isOutgoing: false,
                                                 connectedSeenAt: nil,
                                                 sawItConnect: false,
                                                 seenLive: [])

    init(standDown: @escaping () -> Void,
         retake: @escaping () -> Void,
         onBoundary: @escaping (CallPresencePolicy.Boundary) -> Void = { _ in }) {
        self.standDown = standDown
        self.retake = retake
        self.onBoundary = onBoundary
        super.init()
        // Main queue on purpose. The verdict ends in starting or stopping audio
        // capture, and `PhoneListener` does that work on the main actor; a
        // background callback would hand it a decision on the wrong thread at
        // the one moment the microphone is changing hands.
        observer.setDelegate(self, queue: .main)
        // ASK ONCE AT BIRTH. A call can already be in progress when the app
        // launches or when listening is turned on, and the delegate only fires
        // on a CHANGE — so without this the sense would sit idle through a call
        // that started before it existed, which is exactly the case a person
        // hits by opening the app to check whether she heard something.
        evaluate()
    }

    func callObserver(_ observer: CXCallObserver, callChanged call: CXCall) {
        evaluate()
    }

    /// Read the whole list, ask the policy, carry out the answer.
    private func evaluate() {
        let calls = observer.calls.map {
            CallPresencePolicy.Call(id: $0.uuid,
                                    isOutgoing: $0.isOutgoing,
                                    hasConnected: $0.hasConnected,
                                    hasEnded: $0.hasEnded,
                                    isOnHold: $0.isOnHold)
        }
        let verdict = CallPresencePolicy.decide(was: state, sees: calls, now: Date())
        state = verdict.state

        // BOUNDARIES BEFORE THE ACTION. The journal line that says a call opened
        // must be written before the line the microphone change will produce, or
        // the record reads as though the ears went down for no reason and a call
        // began afterwards.
        for boundary in verdict.boundaries {
            onBoundary(boundary)
        }

        switch verdict.action {
        case .standDownForCall:
            standDown()
        case .retakeMicrophone:
            retake()
        default:
            // Every other verdict is "nothing to do". Written as a default
            // rather than exhaustively so that a new action added to the policy
            // is a compile-time decision there and a no-op here, never a silent
            // microphone change nobody asked this file to make.
            break
        }
    }
}
