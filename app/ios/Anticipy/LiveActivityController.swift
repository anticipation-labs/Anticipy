import Combine
import Foundation
import SwiftUI
#if canImport(ActivityKit)
import ActivityKit
#endif

/// THE THING THAT PUTS THE CAPSULE ON THE LOCK SCREEN AND TAKES IT AWAY.
///
/// `LiveActivityPolicy` decides WHAT the lock screen may say; this decides
/// WHEN it says anything at all. The split is the usual one — the policy is
/// pure and walked by `run_live_activity_tests.sh`, this is the plumbing that
/// carries its answer to ActivityKit and can only be checked by holding a
/// phone.
///
/// Three properties this file is responsible for and the policy cannot be:
///
/// **It never starts an activity the owner did not cause.** The only inputs
/// are the owner's own listening switch and their own jobs. There is no
/// server push here and no timer that decides to appear.
///
/// **It ends rather than lingers.** When `LiveActivityPolicy.reason` returns
/// nil there is nothing happening, and a capsule for nothing happening is an
/// app that will not leave somebody's lock screen. It gets `lingerAfterEnding`
/// seconds so a finish is visible, then it goes.
///
/// **It pushes only when the face would change.** `heard` and the reason are
/// compared before every update, and the CLOCK IS NOT PUSHED AT ALL — the
/// widget runs `Text(started, style: .timer)` off `startedAt`. A Live Activity
/// updated once a second is a Live Activity iOS throttles and then stops
/// delivering, which is how these end up frozen on other people's phones.
@MainActor
final class LiveActivityController: ObservableObject {

    static let shared = LiveActivityController()

    /// What was last handed to ActivityKit, so an unchanged face costs nothing.
    private var lastReason: LiveActivityPolicy.Reason?
    private var lastHeard = -1
    private var lastAlive: Bool?
    private var lastPending = -1
    /// The line count when this listening run began. `heard` is the delta, so
    /// the capsule counts THIS session rather than everything the app has held
    /// since launch.
    private var heardBaseline: Int?
    private var startedAt: Date?
    private var endingTask: Task<Void, Never>?

    #if canImport(ActivityKit)
    @available(iOS 16.1, *)
    private var activity: Activity<ListeningActivityAttributes>? {
        get { _activity as? Activity<ListeningActivityAttributes> }
        set { _activity = newValue }
    }
    private var _activity: Any?
    #endif

    private init() {}

    /// Whether iOS will let us put anything on a lock screen at all. False on
    /// iOS 16.0, false when the owner has switched Live Activities off for
    /// Anticipy in Settings, and false in every simulator that has not enabled
    /// them. Every entry point checks it, because ActivityKit throws rather
    /// than no-ops when it is false.
    var available: Bool {
        #if canImport(ActivityKit)
        if #available(iOS 16.1, *) {
            return ActivityAuthorizationInfo().areActivitiesEnabled
        }
        #endif
        return false
    }

    /// The single entry point. Called with the facts; decides everything else.
    ///
    /// `lines` is the app's running count of spoken lines — a COUNT, and the
    /// only thing derived from what was said that ever reaches this file.
    func sync(listening: Bool,
              paused: Bool,
              reachable: Bool,
              jobs: [AgentJob],
              lines: Int,
              now: Date = Date()) {
        let workingCount = jobs.filter { $0.status == "running" || $0.status == "queued" }.count
        let waitingCount = jobs.filter { $0.status == "awaiting_confirm" }.count
        let reason = LiveActivityPolicy.reason(listening: listening,
                                               paused: paused,
                                               reachable: reachable,
                                               working: workingCount > 0,
                                               waiting: waitingCount > 0)

        guard let reason else { finish(); return }
        guard available else { return }

        // The baseline and the clock belong to a LISTENING RUN, not to the
        // activity: an activity that stays up because a job is still running
        // must not restart the count when the microphone comes back on.
        if listening {
            if heardBaseline == nil { heardBaseline = lines; startedAt = now }
        } else {
            heardBaseline = nil
            startedAt = nil
        }
        let heard = heardBaseline.map { max(0, lines - $0) } ?? 0
        // How many jobs are in the state this capsule is about. Counted here so
        // the one line can read "3 waiting on you" rather than "Waiting on you"
        // while two more sit unmentioned behind it.
        let pending = reason == .waiting ? waitingCount : (reason == .working ? workingCount : 0)
        let alive = LiveActivityPolicy.face(reason, heard: heard, elapsed: 0).alive

        #if canImport(ActivityKit)
        guard #available(iOS 16.1, *) else { return }
        let state = ListeningActivityAttributes.ContentState(
            reason: ActivityReason.wire(reason),
            heard: heard,
            startedAt: alive ? startedAt : nil,
            alive: alive,
            pending: pending)

        endingTask?.cancel()
        endingTask = nil

        // ONE CAPSULE, AND THIS IS WHERE THAT IS TRUE OR NOT.
        //
        // A Live Activity OUTLIVES THE PROCESS. iOS keeps it on the lock screen
        // after a force-quit, and it is still there when the app comes back —
        // but `activity` is an instance property and comes back nil. The first
        // version of this asked "is my handle nil?" and requested a new one, so
        // a force-quit and relaunch left TWO capsules stacked on the lock
        // screen, three after the next, and nothing in the app could see them.
        //
        // The question that is actually being asked is "does iOS already hold
        // one of mine?", so ask iOS. Adopt what it has; end anything past the
        // first, which nothing should ever produce and which is exactly the
        // pile this guard exists to make impossible.
        adoptExistingActivity()

        if activity == nil {
            do {
                activity = try Activity.request(
                    attributes: ListeningActivityAttributes(),
                    contentState: state,
                    pushType: nil)          // NO PUSH TOKEN. Nothing off this
                                            // phone updates this capsule.
            } catch {
                // A refusal is a refusal — the owner turned Live Activities
                // off, or iOS is holding too many. Nothing to retry and
                // nothing to tell them: the app itself is unaffected.
                return
            }
        } else if reason != lastReason || heard != lastHeard || alive != lastAlive
                    || pending != lastPending {
            let current = activity
            Task { await current?.update(using: state) }
        }
        lastReason = reason
        lastHeard = heard
        lastAlive = alive
        lastPending = pending
        #endif
    }

    /// THE ONE-CAPSULE RULE, enforced against iOS rather than against a local
    /// variable.
    ///
    /// Takes back the activity this app already has on screen — after a
    /// relaunch, a force-quit, a crash — and ends every extra beyond the first.
    /// Called before every request, so a second capsule cannot outlive one
    /// `sync`.
    private func adoptExistingActivity() {
        #if canImport(ActivityKit)
        guard #available(iOS 16.1, *) else { return }
        let live = Activity<ListeningActivityAttributes>.activities
        guard let first = live.first else { return }
        if activity == nil { activity = first }
        for extra in live where extra.id != activity?.id {
            Task { await extra.end(dismissalPolicy: .immediate) }
        }
        #endif
    }

    /// Nothing is happening any more. Show it for a moment, then leave.
    func finish() {
        heardBaseline = nil
        startedAt = nil
        #if canImport(ActivityKit)
        guard #available(iOS 16.1, *), let current = activity, endingTask == nil else { return }
        lastReason = nil
        lastHeard = -1
        lastAlive = nil
        lastPending = -1
        activity = nil
        endingTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds:
                UInt64(LiveActivityPolicy.lingerAfterEnding * 1_000_000_000))
            await current.end(dismissalPolicy: .immediate)
            await MainActor.run { self?.endingTask = nil }
        }
        #endif
    }

    /// Take everything down now, with no linger. For sign-out: the next person
    /// on this phone must not inherit a capsule that says somebody is being
    /// listened to.
    func tearDown() {
        endingTask?.cancel()
        endingTask = nil
        heardBaseline = nil
        startedAt = nil
        lastReason = nil
        lastHeard = -1
        lastAlive = nil
        lastPending = -1
        #if canImport(ActivityKit)
        guard #available(iOS 16.1, *) else { return }
        activity = nil
        // Everything iOS holds for this app, not merely the handle this
        // instance happens to have. A sign-out that left one capsule behind
        // would hand the next person on this phone a lock screen saying
        // somebody is being listened to.
        for live in Activity<ListeningActivityAttributes>.activities {
            Task { await live.end(dismissalPolicy: .immediate) }
        }
        #endif
    }
}

/// The driver, attached once at the root.
///
/// A modifier rather than logic inside `AnticipySession` because the facts it
/// needs live in three different objects, and because a session that reached
/// for ActivityKit could not be compiled by the pure test runners.
struct LiveActivityDriver: ViewModifier {
    @ObservedObject var session: AnticipySession
    @ObservedObject var listener: PhoneListener

    func body(content: Content) -> some View {
        content
            .onAppear { push() }
            .onChange(of: listener.isListening) { _ in push() }
            .onChange(of: listener.suspended) { _ in push() }
            .onChange(of: session.backendReachable) { _ in push() }
            .onChange(of: session.sessionLines.count) { _ in push() }
            .onChange(of: session.jobs) { _ in push() }
            // A sign-out takes the capsule with it, immediately.
            .onChange(of: session.accountID) { id in
                if id.isEmpty { LiveActivityController.shared.tearDown() } else { push() }
            }
            // THE BUTTON'S OTHER END. `StopListeningIntent` runs in this
            // process and posts this; the session is the only thing allowed to
            // decide what stopping means, so it is what gets called.
            .onReceive(NotificationCenter.default.publisher(
                for: .anticipyStopListeningFromLockScreen)) { _ in
                session.stopListening()
            }
    }

    private func push() {
        LiveActivityController.shared.sync(listening: listener.isListening,
                                           paused: listener.suspended,
                                           reachable: session.backendReachable,
                                           jobs: session.jobs,
                                           lines: session.sessionLines.count)
    }
}

extension View {
    func drivesLiveActivity(session: AnticipySession, listener: PhoneListener) -> some View {
        modifier(LiveActivityDriver(session: session, listener: listener))
    }
}
