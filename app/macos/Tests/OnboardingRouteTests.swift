import Foundation

var failures = 0
func check(_ name: String, _ condition: @autoclosure () -> Bool) {
    let passed = condition()
    print("\(passed ? "PASS" : "FAIL"): \(name)")
    if !passed { failures += 1 }
}

// The route: onboarding is walked once, and it is not a door.
check("a fresh install opens on welcome", OnboardingRoute.initial(hasOnboarded: false) == .welcome)
check("a walked onboarding opens the library", OnboardingRoute.initial(hasOnboarded: true) == .done)
check("the beats run welcome, sign in, permissions, ready",
      OnboardingStep.beats == [.welcome, .signIn, .permissions, .ready])
var step = OnboardingStep.welcome
var walked: [OnboardingStep] = [step]
while step != .done { step = step.next; walked.append(step) }
check("next walks every beat exactly once and ends",
      walked == [.welcome, .signIn, .permissions, .ready, .done])
check("done stays done", OnboardingStep.done.next == .done)

// Recording needs both grants; system audio is explained, never gated.
check("both granted can record", OnboardingRoute.canRecord(microphone: .granted, speech: .granted))
check("a missing microphone cannot", !OnboardingRoute.canRecord(microphone: .notAsked, speech: .granted))
check("a denied speech grant cannot", !OnboardingRoute.canRecord(microphone: .granted, speech: .denied))

// The sentences exist once, and each state has its own.
let sentences = [
    OnboardingRoute.permissionSentence(microphone: .notAsked, speech: .notAsked),
    OnboardingRoute.permissionSentence(microphone: .granted, speech: .notAsked),
    OnboardingRoute.permissionSentence(microphone: .notAsked, speech: .granted),
    OnboardingRoute.permissionSentence(microphone: .granted, speech: .granted),
    OnboardingRoute.permissionSentence(microphone: .denied, speech: .granted),
]
check("five states, five different sentences", Set(sentences).count == 5)
check("a denial names System Settings",
      OnboardingRoute.permissionSentence(microphone: .granted, speech: .denied).contains("System Settings"))
check("both granted mentions system audio, the one macOS asks for later",
      OnboardingRoute.permissionSentence(microphone: .granted, speech: .granted).contains("system audio"))
check("no sentence contains an em dash",
      sentences.allSatisfy { !$0.contains("\u{2014}") })

// The buttons: ask when we can, point at Settings when we cannot, nothing
// when there is nothing to do.
check("not asked offers Allow", OnboardingRoute.buttonTitle(for: .notAsked) == "Allow")
check("granted offers nothing", OnboardingRoute.buttonTitle(for: .granted) == nil)
check("denied points at System Settings", OnboardingRoute.buttonTitle(for: .denied) == "Open System Settings")
check("the storage key is named once", OnboardingRoute.storageKey == "mac.hasOnboarded")

print(failures == 0 ? "all onboarding-route checks passed" : "\(failures) onboarding-route check(s) failed")
exit(failures == 0 ? 0 : 1)
