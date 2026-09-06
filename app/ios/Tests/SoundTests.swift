import Foundation

// WHEN ANTICIPY IS ALLOWED TO MAKE A SOUND, walked. Compiled by
// run_sound_tests.sh against the production policy; this file is that suite's
// main.swift, so it may hold top-level code.

var failures = 0
func check(_ ok: Bool, _ name: String, _ detail: @autoclosure () -> String = "") {
    if ok { print("PASS: \(name)") } else { failures += 1; print("FAIL: \(name) \(detail())") }
}

typealias S = SoundPolicy
let every = S.Cue.allCases

// ============================================ FIVE CUES, AND THE NUMBER IS THE RULE
// A product that makes six noises is a product somebody turns off.
check(every.count == 5, "five cues, no more", "\(every.count)")
check(Set(every.map(\.rawValue)).count == 5, "and no two share a file")

// ================================================================ THE ECHO RULE
// The one that decides the shape of the whole file. The capture session is
// .measurement (no echo cancellation) pointed at .defaultToSpeaker, so a
// PITCHED cue played while the engine runs can be transcribed — and a
// transcribed cue becomes a line in somebody's transcript that they never said.
check(S.isTonal(.listenOpen) && S.isTonal(.listenClose) && S.isTonal(.done),
      "the two breaths and the warm cue carry pitch")
check(!S.isTonal(.heard) && !S.isTonal(.needsYou),
      "the tick and the knock are transients, and can be heard over a live mic")

let listening = S.World(microphoneRunning: true, outputIsSpeaker: true)
for cue in every where S.isTonal(cue) {
    check(S.decide(cue, in: listening) == .refuse(.theMicrophoneWouldHearIt),
          "a tonal cue is refused over a live microphone on the speaker", "\(cue)")
}
for cue in every where !S.isTonal(cue) {
    check(S.decide(cue, in: listening) == .play(cue),
          "a transient is allowed over a live microphone", "\(cue)")
}
// Headphones break the acoustic path, and then everything is allowed.
let headphones = S.World(microphoneRunning: true, outputIsSpeaker: false)
for cue in every {
    check(S.decide(cue, in: headphones) == .play(cue),
          "on headphones there is no path back into the mic", "\(cue)")
}
// A microphone that is not running cannot hear anything.
let quiet = S.World(microphoneRunning: false, outputIsSpeaker: true)
for cue in every {
    check(S.decide(cue, in: quiet) == .play(cue), "a stopped engine hears nothing", "\(cue)")
}

// ================================================== THE BREATHS BRACKET THE ENGINE
// listen-open is played BEFORE listener.start() and listen-close AFTER
// listener.stop(), which is what keeps them out of the echo rule's way. If
// somebody moves either call inside the running window the cue silently stops
// existing on every phone without headphones, and nobody notices a missing sound.
check(S.mustBracketTheEngine(.listenOpen) && S.mustBracketTheEngine(.listenClose),
      "the two breaths are marked as needing to bracket the engine")
check(!S.mustBracketTheEngine(.heard) && !S.mustBracketTheEngine(.needsYou)
        && !S.mustBracketTheEngine(.done),
      "and nothing else is")

// ========================================================= THE OWNER'S SWITCH FIRST
for cue in every {
    check(S.decide(cue, in: S.World(soundOn: false)) == .refuse(.soundIsOff),
          "sound off silences everything", "\(cue)")
}
// It outranks even the reasons we would not have played anyway.
check(S.decide(.heard, in: S.World(soundOn: false, screenIsOn: false, inFront: false,
                                   onACall: true, pastFirstRun: false))
        == .refuse(.soundIsOff),
      "and it is the FIRST reason given, because it is the only one the owner chose")

// ======================================================== A DARK PHONE MAKES NO NOISE
// Same doctrine as the Live Activity: a phone whose screen is off belongs to
// whoever is holding it, and a noise out of a pocket is not a cue.
for cue in every {
    check(S.decide(cue, in: S.World(screenIsOn: false)) == .refuse(.screenIsDark),
          "nothing plays while the screen is dark", "\(cue)")
    check(S.decide(cue, in: S.World(inFront: false)) == .refuse(.notInFront),
          "nothing plays from the background — Notifier is that channel", "\(cue)")
    check(S.decide(cue, in: S.World(onACall: true)) == .refuse(.onACall),
          "nothing plays into somebody's call", "\(cue)")
    check(S.decide(cue, in: S.World(pastFirstRun: false)) == .refuse(.beforeFirstRun),
          "and nothing at all happens before there is an owner", "\(cue)")
}

// ==================================================== THE TICK IS NOT A METRONOME
// Somebody in a meeting produces a line every few seconds. A cue on each one is
// a woodpecker in their pocket.
check(S.heardMinimumGap >= 10, "the tick's gap is long", "\(S.heardMinimumGap)")
check(S.minimumGap > 0 && S.minimumGap < 1, "and everything shares a short floor")

var recent = S.World(lastPlayed: ["heard": 100], now: 104)
if case .refuse(.tooSoon(let left)) = S.decide(.heard, in: recent) {
    check(abs(left - 8) < 0.001, "the refusal says how long is left", "\(left)")
} else { check(false, "a tick four seconds after the last one is refused") }

recent.now = 113
check(S.decide(.heard, in: recent) == .play(.heard), "and allowed once the gap has passed")

// A different cue is not blocked by the tick's long gap.
check(S.decide(.needsYou, in: S.World(lastPlayed: ["heard": 100], now: 104)) == .play(.needsYou),
      "one cue's rate limit is not another's")

// A CLOCK THAT WENT BACKWARDS is not evidence a cue is due. A timezone change or
// a manual set would otherwise fire every cue at once.
check(S.decide(.heard, in: S.World(lastPlayed: ["heard": 500], now: 100))
        != .play(.heard),
      "a backwards clock does not unlock a cue")

// ================================================================= THE VOCABULARY
// The raw value IS the filename, so a rename here is a missing asset there.
check(S.Cue.listenOpen.rawValue == "listen-open", "listen-open")
check(S.Cue.heard.rawValue == "heard", "heard")
check(S.Cue.listenClose.rawValue == "listen-close", "listen-close")
check(S.Cue.needsYou.rawValue == "needs-you", "needs-you")
check(S.Cue.done.rawValue == "done", "done")
for cue in every {
    check(!cue.rawValue.isEmpty && cue.rawValue == cue.rawValue.lowercased(),
          "every cue names a real lowercase file", cue.rawValue)
}

// ===================================================== EVERY REFUSAL HAS WORDS
for cue in every {
    check(!S.words(S.decide(cue, in: S.World())).isEmpty, "a play has words")
}
for world in [S.World(soundOn: false), S.World(screenIsOn: false), S.World(inFront: false),
              S.World(onACall: true), S.World(pastFirstRun: false),
              S.World(microphoneRunning: true, outputIsSpeaker: true),
              S.World(lastPlayed: ["heard": 0], now: 1)] {
    let said = S.words(S.decide(.heard, in: world))
    check(!said.isEmpty, "every refusal can be printed in Developer Diagnostics", said)
}

print(failures == 0 ? "\nAll sound checks passed."
                    : "\n\(failures) sound check(s) failed.")
exit(failures == 0 ? 0 : 1)
