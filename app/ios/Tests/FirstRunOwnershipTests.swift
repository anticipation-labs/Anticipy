// Whose first run is this?
//
// `hasOnboarded` was one boolean for the whole PHONE and nothing in the account
// lifecycle ever touched it. Cable install is the only way onto a device today
// (research/2026-08-24-cold-stranger-walkthrough.md Step 0), so the phone having
// been opened by somebody else is the NORMAL case: the installer opens it once
// to check it, and the stranger's sign-up then lands straight on the feed. They
// never see the microphone primer, listening is never started, and she hears
// nothing all week.
//
// Run: sh app/ios/Tests/run_first_run_tests.sh
import Foundation

var failures = 0
func check(_ name: String, _ ok: Bool) {
    print("\(ok ? "PASS" : "FAIL"): \(name)")
    if !ok { failures += 1 }
}

let installer = "acc_installer_9x"
let stranger = "acc_stranger_2b"

// ================================================ THE STRANGER'S SIGN-UP
// The whole reason this file exists. A used phone, a fresh account.
check("a used phone hands the tour to the new account",
      FirstRunOwnership.arriving(account: stranger,
                                 onboardedAccount: installer,
                                 hasOnboarded: true) == .replay)

// The commonest shape of all: a phone somebody opened BEFORE accounts existed,
// or opened and toured without ever signing in. The flag is on and owned by
// nobody, so it cannot have been earned by the person now signing up.
check("a tour flag owned by nobody is not this stranger's",
      FirstRunOwnership.arriving(account: stranger,
                                 onboardedAccount: "",
                                 hasOnboarded: true) == .replay)

// ================================================ THE OWNER COMES BACK
check("signing back into your own account keeps your tour done",
      FirstRunOwnership.arriving(account: installer,
                                 onboardedAccount: installer,
                                 hasOnboarded: true) == .keep)
check("and a second sign-in does not re-run the tour",
      FirstRunOwnership.arriving(account: installer,
                                 onboardedAccount: installer,
                                 hasOnboarded: false) == .keep)

// ================================================ A FAILED SIGN-IN
// A sign-in that returned nothing must never clear anybody's flag. This is the
// one input that could turn a bug fix into a way to wipe the owner's state.
check("an empty account id changes nothing",
      FirstRunOwnership.arriving(account: "",
                                 onboardedAccount: installer,
                                 hasOnboarded: true) == .keep)
check("an empty account id changes nothing even with no owner recorded",
      FirstRunOwnership.arriving(account: "",
                                 onboardedAccount: "",
                                 hasOnboarded: true) == .keep)

// ================================================ THE STALE-OWNER TRAP
// Not "if hasOnboarded": an owner id left behind a CLEARED flag would then
// survive to be matched against later, and the next person to sign in under
// that id would silently inherit a tour they never saw.
check("a cleared flag with a stale owner still re-stamps for a new account",
      FirstRunOwnership.arriving(account: stranger,
                                 onboardedAccount: installer,
                                 hasOnboarded: false) == .replay)

// ================================================ THE UPGRADE PATH
// A phone updating to this build has hasOnboarded = true and no owner
// recorded, because the column did not exist when it was written. The tour can
// only be completed from BEHIND the sign-in door (AnticipyApp routes to
// AuthView first), so the only account that could have earned it is the one
// signed in right now. Stamping it is a fact, not a guess.
check("an existing owner is not made to redo first run",
      FirstRunOwnership.resuming(account: installer,
                                 onboardedAccount: "",
                                 hasOnboarded: true) == .adopt)
check("a resumed launch with the flag already owned leaves it alone",
      FirstRunOwnership.resuming(account: installer,
                                 onboardedAccount: installer,
                                 hasOnboarded: true) == .keep)

// Adoption must never be able to re-open the hole it closes: it only ever runs
// for the account signed in AT THAT MOMENT, and a flag that is OFF is not a
// fact to adopt.
check("there is nothing to adopt when the tour was never finished",
      FirstRunOwnership.resuming(account: installer,
                                 onboardedAccount: "",
                                 hasOnboarded: false) == .keep)
check("a resumed launch with no account adopts nothing",
      FirstRunOwnership.resuming(account: "",
                                 onboardedAccount: "",
                                 hasOnboarded: true) == .keep)

// Belt and braces: a flag owned by somebody ELSE surviving to a resumed launch
// means the arriving path was skipped, which is the bug this file exists for.
// The safe reading of "I cannot tell whose this is" is to show the tour.
check("somebody else's flag on a resumed launch is not kept",
      FirstRunOwnership.resuming(account: stranger,
                                 onboardedAccount: installer,
                                 hasOnboarded: true) == .replay)

// ================================================ THE KEYS
// One string, in one place. `swift_string_behind` in stranger_gate.py exists
// because moving "hasOnboarded" into a constant was the shape of an accident:
// a second copy of the key is a clear that silently clears nothing.
check("the flag key is the one the phone has always stored",
      FirstRunOwnership.flagKey == "hasOnboarded")
check("the owner is recorded under a key of its own",
      FirstRunOwnership.ownerKey != FirstRunOwnership.flagKey
        && !FirstRunOwnership.ownerKey.isEmpty)

// ================================================ THE WHOLE JOURNEY
// A used phone, start to finish, through the two entry points the app has.
var flag = true                     // the installer toured it
var owner = ""                      // before the owner column existed
switch FirstRunOwnership.resuming(account: installer,
                                  onboardedAccount: owner, hasOnboarded: flag) {
case .adopt: owner = installer
case .replay: flag = false; owner = installer
case .keep: break
}
check("the installer's own tour is stamped to the installer", owner == installer && flag)

switch FirstRunOwnership.arriving(account: stranger,
                                  onboardedAccount: owner, hasOnboarded: flag) {
case .adopt: owner = stranger
case .replay: flag = false; owner = stranger
case .keep: break
}
check("and the stranger who signs up next is shown the tour", !flag)
check("and the flag now belongs to the stranger", owner == stranger)

// And once she finishes it, it is hers and stays hers.
flag = true
switch FirstRunOwnership.arriving(account: stranger,
                                  onboardedAccount: owner, hasOnboarded: flag) {
case .adopt: owner = stranger
case .replay: flag = false
case .keep: break
}
check("her finished tour survives her next sign-in", flag)

print(failures == 0 ? "all first-run ownership checks passed" : "\(failures) FAILED")
exit(failures == 0 ? 0 : 1)
