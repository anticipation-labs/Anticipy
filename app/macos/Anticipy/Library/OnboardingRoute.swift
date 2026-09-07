// OnboardingRoute — which screen a person sees when the window opens, and
// what the permission rows are allowed to say.
//
// Pure Foundation so it can be tested without a window, and so the sentences
// about macOS permissions exist ONCE. The window, the menu bar and the guide
// all read these; none of them phrases a permission for itself.
import Foundation

public enum OnboardingStep: Int, Equatable, Sendable, CaseIterable {
    case welcome
    case signIn
    case permissions
    case ready
    /// Onboarding is over; the library is the window.
    case done

    public var next: OnboardingStep {
        switch self {
        case .welcome: return .signIn
        case .signIn: return .permissions
        case .permissions: return .ready
        case .ready, .done: return .done
        }
    }

    /// The pager: four beats, the last of which ends onboarding.
    public static let beats: [OnboardingStep] = [.welcome, .signIn, .permissions, .ready]
}

/// What macOS has said about one permission. Three states, because "never
/// asked" and "asked and refused" call for different buttons: the first can
/// ask, the second can only send the person to System Settings.
public enum PermissionState: Equatable, Sendable {
    case notAsked
    case granted
    case denied
}

public enum OnboardingRoute {
    /// The UserDefaults key the window reads. Named once.
    public static let storageKey = "mac.hasOnboarded"

    /// ONBOARDING IS NOT A DOOR. Once it has been walked, the library opens
    /// whether or not the person is signed in: recordings work on this Mac
    /// alone, and a session the server dropped must not lock a person out of
    /// their own notes. Sign-in becomes a card in the library instead.
    public static func initial(hasOnboarded: Bool) -> OnboardingStep {
        hasOnboarded ? .done : .welcome
    }

    /// Whether the permissions beat may continue. System audio is not in this
    /// list on purpose: macOS has no way to ask for it ahead of time, so it is
    /// requested by the first recording and explained rather than gated.
    public static func canRecord(microphone: PermissionState,
                                 speech: PermissionState) -> Bool {
        microphone == .granted && speech == .granted
    }

    /// The one sentence under the permission rows, for the state they are in.
    public static func permissionSentence(microphone: PermissionState,
                                          speech: PermissionState) -> String {
        switch (microphone, speech) {
        case (.granted, .granted):
            return "Both are on. The first recording will also ask about system audio, which is how I hear the other side."
        case (.denied, _), (_, .denied):
            return "macOS has one of these switched off. I can't ask again from here; it's one switch in System Settings, under Privacy & Security."
        case (.notAsked, .notAsked):
            return "macOS asks twice, once for the microphone and once for speech recognition. Both are me."
        case (.notAsked, .granted):
            return "One more: the microphone."
        case (.granted, .notAsked):
            return "One more: speech recognition, so the words become text on this Mac."
        }
    }

    /// What the row's button says. A denied permission has no button that
    /// could work, so it points at the place that can.
    public static func buttonTitle(for state: PermissionState) -> String? {
        switch state {
        case .notAsked: return "Allow"
        case .granted: return nil
        case .denied: return "Open System Settings"
        }
    }
}
