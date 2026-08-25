// Does first run offer to learn your voice — and does it stay honest when it
// cannot?
//
// `speaker` is 0% across 221 production events, cause recorded as "enrollment
// unreachable" (research/2026-08-24-engine-options.md:254). Enrollment had one
// presentation site in the entire app: a sheet three scrolls down in Settings.
// That is mechanical, not mysterious.
//
// It is also NOT the whole story, and this suite is where that gets written
// down: sherpa-onnx is unlinked (project.yml, commit d3ccb133), so
// SpeakerTagger.available is false and enrollment cannot enrol anybody today.
// Offering a twelve-second read that can never produce a profile is worse than
// not asking.
//
// Run: sh app/ios/Tests/run_enrollment_offer_tests.sh
import Foundation

var failures = 0
func check(_ name: String, _ ok: Bool) {
    print("\(ok ? "PASS" : "FAIL"): \(name)")
    if !ok { failures += 1 }
}

// ================================================ THE ONE THAT MATTERS
check("a working engine and no profile is an offer",
      EnrollmentOfferPolicy.firstRun(engineAvailable: true,
                                     hasOwnerProfile: false) == .offer)
check("and first run puts it on screen",
      EnrollmentOfferPolicy.presents(engineAvailable: true,
                                     hasOwnerProfile: false))

// ================================================ THE BUILD WE SHIP TODAY
// sherpa-onnx is out, so this is the live case. It must not dead-end anybody.
check("a build that cannot embed a voice does not offer to learn one",
      EnrollmentOfferPolicy.firstRun(engineAvailable: false,
                                     hasOwnerProfile: false) == .cannot)
check("and first run puts nothing on screen for it",
      !EnrollmentOfferPolicy.presents(engineAvailable: false,
                                      hasOwnerProfile: false))

// THE ORDER TRAP, and it is the reason `cannot` is checked first. A profile
// left behind by build 75 - which HAD the engine - survives on disk into build
// 82, which does not. Asked the other way round this would report "I know your
// voice" on a phone where every single tag comes back nil.
check("a stale profile on an engineless build is still cannot, not alreadyKnown",
      EnrollmentOfferPolicy.firstRun(engineAvailable: false,
                                     hasOwnerProfile: true) == .cannot)
check("and it is certainly not an offer",
      !EnrollmentOfferPolicy.presents(engineAvailable: false,
                                      hasOwnerProfile: true))

// ================================================ SHE ALREADY KNOWS YOU
// Not an offer, and not a failure either. Re-teaching stays in Settings, where
// somebody who wants it goes looking on purpose.
check("a voice already learned is not re-asked for during a tour",
      EnrollmentOfferPolicy.firstRun(engineAvailable: true,
                                     hasOwnerProfile: true) == .alreadyKnown)
check("and first run stays out of the way",
      !EnrollmentOfferPolicy.presents(engineAvailable: true,
                                      hasOwnerProfile: true))

// ================================================ THE THREE ARE DISTINCT
// A bool cannot carry this. "Don't ask because she knows you" and "don't ask
// because this build cannot learn anyone" are different facts about the
// product, and collapsing them is how a dead feature reads as a finished one.
check("cannot and alreadyKnown are not the same answer",
      EnrollmentOfferPolicy.firstRun(engineAvailable: false, hasOwnerProfile: true)
        != EnrollmentOfferPolicy.firstRun(engineAvailable: true, hasOwnerProfile: true))
check("offer is not either of them",
      EnrollmentOfferPolicy.firstRun(engineAvailable: true, hasOwnerProfile: false)
        != EnrollmentOfferPolicy.firstRun(engineAvailable: true, hasOwnerProfile: true)
        && EnrollmentOfferPolicy.firstRun(engineAvailable: true, hasOwnerProfile: false)
        != EnrollmentOfferPolicy.firstRun(engineAvailable: false, hasOwnerProfile: false))

// Exactly one of the four inputs may put a screen in front of a stranger.
var offered = 0
for engine in [true, false] {
    for profile in [true, false] {
        if EnrollmentOfferPolicy.presents(engineAvailable: engine,
                                          hasOwnerProfile: profile) { offered += 1 }
    }
}
check("exactly one of the four states is an offer", offered == 1)

print(failures == 0 ? "all enrollment offer checks passed" : "\(failures) FAILED")
exit(failures == 0 ? 0 : 1)
