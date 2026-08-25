import Foundation

// Checks for ListenResumePolicy — what happens when the owner opens the app
// again.
//
// The failure being closed, 2026-08-24. `resumeListeningIfWanted()` read:
//
//     if keepListening, !listener.isListening { listener.start() }
//
// A phone call sets `suspended` and leaves `isListening` alone — nothing in the
// app ever set it false for an interruption — so the guard was false and the
// function did nothing at all. Every route back to listening was closed except
// the owner reaching over and toggling the switch by hand, while the briefing
// on the same screen said "I'm listening." That is the day ending at 9am with
// nobody told.
//
// TWO FLAGS, TWO DIFFERENT FACTS, and collapsing them is the entire bug.
// `isListening` means THE OWNER WANTS ME LISTENING. `suspended` means THE
// MICROPHONE IS NOT OURS RIGHT NOW. The one state that needed action —
// wanted, nominally listening, microphone actually gone — is the one the old
// guard answered "nothing" to.
//
// Pure Foundation on purpose, like TranscriptFlushPolicy, ListenJournal,
// ListenTally and ListenWatchdogPolicy: swiftc alone. No simulator, no scheme,
// no signing, no network — and no device that has to receive a real phone call
// before the answer can be checked.

@main
struct ListenResumePolicyTests {
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

        // ------------------------------------------------- 1. the switch is off
        // Deliberately with the microphone taken as well, so this proves the
        // OWNER'S wish outranks the mic state rather than passing because every
        // other flag was quiet. Somebody who turned listening off during a call
        // must not have it turned back on for them by coming back to the app.
        check("the owner does not want listening, so nothing happens",
              ListenResumePolicy.decide(wantsListening: false,
                                        isListening: true,
                                        suspended: true) == .nothing)

        // ------------------------------------------------- 2. the ordinary open
        // Launch, or a return after the app was terminated: the process is
        // fresh, nothing is listening, and the standing wish says it should be.
        check("listening is off and wanted, so it starts",
              ListenResumePolicy.decide(wantsListening: true,
                                        isListening: false,
                                        suspended: false) == .start)

        // ------------------------------------------------- 3. nothing is wrong
        // The commonest case by far — the owner glances at the app while she is
        // already listening. Restarting capture here would flush a live sentence
        // across a swap seam for no reason at all.
        check("listening is on and healthy, so nothing happens",
              ListenResumePolicy.decide(wantsListening: true,
                                        isListening: true,
                                        suspended: false) == .nothing)

        // ------------------------------------------------------------ 4. THE BUG
        // Wanted, nominally listening, and the microphone belongs to a call.
        // The old guard returned nothing here, which is why the only thing in
        // the whole app that ever brought listening back was a human finger.
        check("listening is on but the mic was taken, so it is retaken",
              ListenResumePolicy.decide(wantsListening: true,
                                        isListening: true,
                                        suspended: true) == .retakeMicrophone)

        // ------------------------------------- 5. a state nothing reaches yet
        // This arm used to be justified as "iOS reclaimed the app mid-call and
        // the last state written said the microphone was gone". NOTHING WRITES
        // IT. `suspended` is a plain in-memory `@Published Bool` — no
        // `@AppStorage`, no `UserDefaults`, unlike `keepListening` — so a fresh
        // process always starts it false, and in-process every writer of
        // `suspended = true` runs only while `isListening` is true, with
        // `stop()` clearing both. This pair is unreachable today.
        //
        // It is checked anyway, because the ordering that produces it is
        // defensive and the failure it defends against is silent:
        // `retakeMicrophone()` guards on `isListening` and would return
        // immediately, so `.retakeMicrophone` here would be a no-op that looks
        // like a fix — the exact shape of the failure this file exists to
        // close. The day somebody persists `suspended`, this check is what says
        // the answer is still the one that does something.
        check("listening is off, so it starts even though the microphone was taken",
              ListenResumePolicy.decide(wantsListening: true,
                                        isListening: false,
                                        suspended: true) == .start)

        // ------------------------------------------------------------- result
        print("")
        if failures.isEmpty {
            print("ListenResumePolicy: all \(checks) checks passed")
        } else {
            print("ListenResumePolicy: \(failures.count)/\(checks) FAILED")
            for f in failures { print("  - \(f)") }
            exit(1)
        }
    }
}
