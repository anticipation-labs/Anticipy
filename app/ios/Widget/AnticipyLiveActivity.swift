import SwiftUI
import WidgetKit
#if canImport(ActivityKit)
import ActivityKit
#endif
#if canImport(AppIntents)
import AppIntents
#endif

/// THE LOCK-SCREEN ACTIVITY.
///
/// The reference is Wispr Flow's: a soft-tinted capsule pinned above the torch
/// and camera, the app's mark and name on the left, one live number under it,
/// and controls on the right. Same anatomy here, in Anticipy's cream and
/// champagne rather than their lilac, and with the mark that is already the
/// product's — a capsule with a dot, which is also the pendant.
///
/// ── WHAT IT MAY NOT DO, DRAWN RATHER THAN DESCRIBED ───────────────────────
///
/// Every string on this surface comes from `LiveActivityPolicy` or is a fixed
/// word in this file. Nothing reaches it from a transcript, a goal, or anything
/// anybody said — the lock screen is readable over a shoulder on a train, and
/// `run_live_activity_tests.sh` fails if this file ever grows a path from
/// spoken text to a label.
///
/// There is one button and it stops the microphone. There is deliberately no
/// approve: an OK given from a lock screen is an OK given without the
/// consequence in front of you, by whoever is holding the phone.
#if canImport(ActivityKit)
@available(iOS 16.1, *)
struct AnticipyLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: ListeningActivityAttributes.self) { context in
            LockScreenActivityView(state: context.state)
                .activityBackgroundTint(ActivityPalette.ground)
                .activitySystemActionForegroundColor(ActivityPalette.ink)
        } dynamicIsland: { context in
            let face = face(context.state)
            return DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    ActivityMark(alive: context.state.alive)
                        .padding(.leading, 4)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    if #available(iOS 17.0, *), face.action == .stopListening {
                        StopButton(compact: true)
                    }
                }
                DynamicIslandExpandedRegion(.center) {
                    VStack(spacing: 3) {
                        Text(face.title)
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundStyle(ActivityPalette.ink)
                        Text(face.detail)
                            .font(.system(size: 13))
                            .foregroundStyle(ActivityPalette.text2)
                    }
                }
            } compactLeading: {
                ActivityMark(alive: context.state.alive, size: 15)
            } compactTrailing: {
                Text(LiveActivityPolicy.compact(reason(context.state), heard: context.state.heard))
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(ActivityPalette.champagne)
                    .monospacedDigit()
            } minimal: {
                ActivityMark(alive: context.state.alive, size: 14)
            }
            .widgetURL(URL(string: "anticipy://open"))
        }
    }

    private func reason(_ s: ListeningActivityAttributes.ContentState) -> LiveActivityPolicy.Reason {
        ActivityReason.from(s.reason)
    }

    private func face(_ s: ListeningActivityAttributes.ContentState) -> LiveActivityPolicy.Face {
        LiveActivityPolicy.face(reason(s), heard: s.heard,
                                elapsed: s.startedAt.map { -$0.timeIntervalSinceNow } ?? 0)
    }
}

/// The capsule itself. Mark and name left, the one live line under them,
/// controls right — the reference's anatomy exactly.
///
/// Not `private`, and that is deliberate: it is the only thing in this feature
/// whose LAYOUT can be looked at without a physical phone in a listening state,
/// so a harness has to be able to render it. Nothing in the app draws it.
@available(iOS 16.1, *)
struct LockScreenActivityView: View {
    let state: ListeningActivityAttributes.ContentState

    private var face: LiveActivityPolicy.Face {
        LiveActivityPolicy.face(ActivityReason.from(state.reason),
                                heard: state.heard,
                                elapsed: state.startedAt.map { -$0.timeIntervalSinceNow } ?? 0)
    }

    var body: some View {
        HStack(spacing: 12) {
            ActivityMark(alive: state.alive, size: 22)

            VStack(alignment: .leading, spacing: 2) {
                Text(face.title)
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(ActivityPalette.ink)
                // THE ONE LIVE LINE. When the microphone is running this is a
                // clock the widget ticks itself, so the app does not have to
                // wake once a second to push a number that a timer can derive.
                if state.alive, let started = state.startedAt {
                    HStack(spacing: 5) {
                        if state.heard > 0 {
                            Text(state.heard == 1 ? "1 thing heard" : "\(state.heard) things heard")
                            Text("·")
                        }
                        Text(started, style: .timer)
                            .monospacedDigit()
                    }
                    .font(.system(size: 15))
                    .foregroundStyle(ActivityPalette.text2)
                    .lineLimit(1)
                    // THE HALF THE CLOCK ONCE ATE, on its OWN LINE. Without it
                    // the offline capsule read "3 things heard · 2:12" on a
                    // phone with no signal — the reassuring lie `.offline`
                    // exists to refuse. It got a line of its own after the
                    // first render, where crammed onto the count line it
                    // truncated to "3 things h… · 2:07 · keeping it…", which is
                    // worse than saying nothing: it is the same omission plus
                    // visible damage.
                    if let tail = LiveActivityPolicy.qualifier(ActivityReason.from(state.reason)) {
                        Text(tail)
                            .font(.system(size: 13, weight: .medium))
                            .foregroundStyle(ActivityPalette.champagneInk)
                            .lineLimit(1)
                            .padding(.top, 1)
                    }
                } else {
                    Text(face.detail)
                        .font(.system(size: 15))
                        .foregroundStyle(ActivityPalette.text2)
                }
            }

            Spacer(minLength: 8)

            if #available(iOS 17.0, *), face.action == .stopListening {
                StopButton(compact: false)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
    }
}

/// The product's mark, breathing while the microphone is actually hearing.
/// Still otherwise, for the same reason the app's own indicators are.
@available(iOS 16.1, *)
private struct ActivityMark: View {
    var alive: Bool
    var size: CGFloat = 22

    var body: some View {
        ZStack {
            if alive {
                Circle()
                    .fill(ActivityPalette.champagne.opacity(0.22))
                    .frame(width: size * 1.9, height: size * 1.9)
            }
            RoundedRectangle(cornerRadius: size * 0.34, style: .continuous)
                .strokeBorder(ActivityPalette.ink, lineWidth: size * 0.11)
                .frame(width: size * 0.70, height: size)
            // The microphone hole, and the one warm thing on the capsule. It
            // is the same light the pendant renders carry in the onboarding —
            // see PendantArt — so the mark on the lock screen and the object
            // on the table are recognisably one product.
            Circle()
                .fill(ActivityPalette.champagne)
                .frame(width: size * 0.24, height: size * 0.24)
                .offset(y: size * 0.14)
                .shadow(color: alive ? ActivityPalette.champagne.opacity(0.9) : .clear,
                        radius: size * 0.16)
        }
        .frame(width: size * 1.9, height: size * 1.9)
    }
}

/// One button, and it stops the microphone.
///
/// `LiveActivityIntent` runs in the app's process, so this reaches the session
/// without the widget needing an app group — which it deliberately does not
/// have. iOS 16.1 to 16.x get no button at all and the capsule opens the app
/// instead; interactive controls arrived in 17.
@available(iOS 17.0, *)
private struct StopButton: View {
    var compact: Bool

    var body: some View {
        Button(intent: StopListeningIntent()) {
            Image(systemName: "stop.fill")
                .font(.system(size: compact ? 13 : 15, weight: .bold))
                .foregroundStyle(ActivityPalette.onInk)
                .frame(width: compact ? 34 : 44, height: compact ? 34 : 44)
                .background(Circle().fill(ActivityPalette.ink))
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Stop listening")
    }
}

/// The palette, spelled here because the widget target does not compile
/// `Theme.swift` and the theme contract's scan does not reach this tree. These
/// are the same values `OnboardTheme` carries; if those change, change these.
enum ActivityPalette {
    static let ground = Color(red: 0.949, green: 0.933, blue: 0.906)   // #F2EEE7
    static let ink = Color(red: 0.098, green: 0.082, blue: 0.071)      // #191512
    static let onInk = Color(red: 1, green: 1, blue: 1)
    static let text2 = Color(red: 0.357, green: 0.329, blue: 0.298)    // #5B544C
    static let champagne = Color(red: 0.722, green: 0.565, blue: 0.310) // #B8904F
    /// The same hue taken down until it passes as body text on cream. The
    /// champagne above is a MARK colour; used for a sentence it is unreadable
    /// on this ground, and this line is one somebody actually has to read.
    static let champagneInk = Color(red: 0.478, green: 0.353, blue: 0.157)  // #7A5A28
}
#endif
