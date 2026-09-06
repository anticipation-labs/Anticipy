import Foundation
#if canImport(ActivityKit)
import ActivityKit
#endif
#if canImport(AppIntents)
import AppIntents
#endif

/// THE SHAPE OF THE LOCK-SCREEN ACTIVITY, shared by the app and the widget.
///
/// This file is compiled into BOTH targets — see `project.yml`, where the
/// widget's sources list names it explicitly. It is the only file they share,
/// and it holds nothing but a shape and an intent, so the two can never drift
/// into disagreeing about what the activity carries.
///
/// Everything in the state is a COUNT, a FLAG or a DATE. There is deliberately
/// no field that could carry a sentence somebody spoke: a lock screen is
/// readable over a shoulder, and `LiveActivityPolicy`'s header argues that at
/// length. The absence of a `String` payload here is the enforceable half of
/// that argument.
#if canImport(ActivityKit)
@available(iOS 16.1, *)
struct ListeningActivityAttributes: ActivityAttributes {

    /// What changes while the activity is on screen.
    public struct ContentState: Codable, Hashable {
        /// Which of the policy's reasons is current, as its raw form. Kept as
        /// a small closed set of strings rather than the enum itself, because
        /// this type is the wire format between two processes and an enum's
        /// case order is not a wire contract.
        var reason: String
        /// How many things this listening session has produced. A COUNT. Never
        /// what any of them said.
        var heard: Int
        /// When listening began, so the widget can run its own clock without
        /// the app waking to push a tick every second.
        var startedAt: Date?
        /// Whether the microphone is actually hearing right now.
        var alive: Bool
    }

    /// Fixed for the life of the activity. Nothing identifying: the owner's
    /// name is not here, because a lock screen does not need it and a stranger
    /// holding the phone does not deserve it.
    var startedFor: String = "listening"
}
#endif

/// The stop button's intent.
///
/// `LiveActivityIntent` runs in the APP'S OWN PROCESS rather than the widget
/// extension's, which is the whole reason the button can exist here at all:
/// the widget target has no app group, no shared container and no way to reach
/// the app's state, and that impoverishment is deliberate — `project.yml`
/// records that it is what keeps provisioning from refusing on a fresh account.
/// An intent that runs in the app sidesteps that entirely.
///
/// It stops listening. It cannot approve anything; there is no intent here that
/// can, and `LiveActivityPolicy.Action` has no case for one.
#if canImport(AppIntents)
@available(iOS 17.0, *)
struct StopListeningIntent: LiveActivityIntent {
    static var title: LocalizedStringResource = "Stop listening"
    static var description = IntentDescription("Turns Anticipy's microphone off.")
    /// Never opens the app. Somebody on a lock screen who taps stop wants the
    /// microphone off, not a launch.
    static var openAppWhenRun: Bool = false

    init() {}

    @MainActor
    func perform() async throws -> some IntentResult {
        NotificationCenter.default.post(name: .anticipyStopListeningFromLockScreen, object: nil)
        return .result()
    }
}
#endif

extension Notification.Name {
    /// Posted by the lock-screen stop button, listened for by the session.
    ///
    /// A notification rather than a direct call because the intent is
    /// constructed by the system, not by the app, so it has no reference to
    /// anything — and the session is the only thing allowed to decide what
    /// stopping means.
    static let anticipyStopListeningFromLockScreen =
        Notification.Name("ai.anticipy.stopListeningFromLockScreen")
}
