// Checks for the Mac capture core: what makes the app OFFER to record, and
// whether what it then captures is real audio or a stream of zeros.
//
// Every constant these checks are built on was MEASURED on this machine on
// 2026-08-25 (macOS 15.6.1, 24G90) and written up in
// research/2026-08-25-macos-concurrent-capture.md. Nothing here is invented.
//
// Run: sh app/macos/Tests/run_capture_core_tests.sh
import Foundation

var failures = 0
func check(_ name: String, _ ok: Bool) {
    print("\(ok ? "PASS" : "FAIL"): \(name)")
    if !ok { failures += 1 }
}

// ===================================================================
// MeetingOfferPolicy — the offer, never the recording
// ===================================================================

// These four rows are the real `audioprocs` output from the experiment.
let vpioHolder = ProcessAudioObservation(pid: 46157, bundleID: nil,
                                         isRunningInput: true, isRunningOutput: true)
let playbackOnly = ProcessAudioObservation(pid: 47610, bundleID: "com.apple.afplay",
                                           isRunningInput: false, isRunningOutput: true)
let dictation = ProcessAudioObservation(pid: 2698, bundleID: "com.apple.CoreSpeech",
                                        isRunningInput: true, isRunningOutput: false)
let us = ProcessAudioObservation(pid: 99999, bundleID: "ai.anticipy.mac",
                                 isRunningInput: true, isRunningOutput: true)

let policy = MeetingOfferPolicy(sustainedReadings: 3)
let selfPID: Int32 = 99999

// A conversation is two-way. Each half alone is not.
check("a voice-processing process running input AND output is two-way", vpioHolder.isTwoWay)
check("a process that only plays audio is not a conversation", !playbackOnly.isTwoWay)
check("macOS dictation, which only listens, is not a conversation", !dictation.isTwoWay)

let meetingSweep = [dictation, vpioHolder, playbackOnly, us]
let sustained = [meetingSweep, meetingSweep, meetingSweep]
check("a sustained two-way process is offered",
      policy.offer(history: sustained, selfPID: selfPID) == .offer(pid: 46157, bundleID: nil))

// THE OFFER IS NOT A RECORDING. There is no code path in this type that starts
// capture, and this check is here so that stays true: the whole return type is
// an offer or nothing.
check("the policy can only ever return an offer, never a start",
      policy.offer(history: sustained, selfPID: selfPID).isOffer)

// WE ARE NOT A MEETING. The app itself runs input and output the moment it
// starts capturing; without this it would offer to record itself, forever.
let onlyUs = [[us], [us], [us]]
check("the app never offers to record itself",
      policy.offer(history: onlyUs, selfPID: selfPID) == .none)

// A PLAYER AND A LISTENER ARE NOT A MEETING, even together. This is the case
// that a bundle-ID list would get wrong in both directions, and the reason
// §6.2 refuses one: music playing while dictation is open is two processes,
// not one conversation.
let musicAndDictation = [[dictation, playbackOnly], [dictation, playbackOnly],
                         [dictation, playbackOnly]]
check("a listener and a player in separate processes are not a meeting",
      policy.offer(history: musicAndDictation, selfPID: selfPID) == .none)

// THE BANNER MUST NOT FLICKER. One reading fires on anything that momentarily
// touches both streams.
let flicker = [[dictation], meetingSweep, [dictation]]
check("a single stray reading does not raise the offer",
      policy.offer(history: flicker, selfPID: selfPID) == .none)
check("a history shorter than the sustain window offers nothing",
      policy.offer(history: [meetingSweep], selfPID: selfPID) == .none)

// THE NEVER-OFFER LIST IS THE OWNER'S, and it is the ONLY thing bundle
// identifiers decide. They label the banner; they never decide what a meeting
// is, and they never decide what was said.
let zoomSweep = [ProcessAudioObservation(pid: 79315, bundleID: "us.zoom.xos",
                                         isRunningInput: true, isRunningOutput: true)]
let zoomHistory = [zoomSweep, zoomSweep, zoomSweep]
check("a two-way process with a bundle id is offered by default",
      policy.offer(history: zoomHistory, selfPID: selfPID)
        == .offer(pid: 79315, bundleID: "us.zoom.xos"))
check("and the owner's never-offer list silences it",
      policy.offer(history: zoomHistory, selfPID: selfPID,
                   neverOffer: ["us.zoom.xos"]) == .none)
check("the never-offer list does not silence a different app",
      policy.offer(history: zoomHistory, selfPID: selfPID,
                   neverOffer: ["com.hnc.Discord"]).isOffer)

// The same input must always produce the same offer, or the banner names a
// different app each second when two meetings overlap.
let twoMeetings = [ProcessAudioObservation(pid: 500, bundleID: "b", isRunningInput: true, isRunningOutput: true),
                   ProcessAudioObservation(pid: 100, bundleID: "a", isRunningInput: true, isRunningOutput: true)]
let twoHistory = [twoMeetings, twoMeetings, twoMeetings]
check("two overlapping meetings resolve to one stable offer",
      policy.offer(history: twoHistory, selfPID: selfPID) == .offer(pid: 100, bundleID: "a"))

// ===================================================================
// CaptureStreamHealth — the measurement that made this type exist
// ===================================================================

let health = CaptureStreamHealthPolicy()

// THE EXPERIMENT'S OWN NUMBERS, both halves.
//
// RUN D, FAR channel, ungranted: 1410 buffers / 721920 frames over 15 s at
// 48000 Hz, peak exactly 0.0000. Core Audio returned noErr the whole way.
let ungrantedTap = CaptureStreamWindow(buffers: 1410, frames: 721_920,
                                       peakAmplitude: 0.0, elapsedSeconds: 15.0,
                                       expectedSampleRate: 48_000)
check("a tap with no privacy grant is reported as silent, not as healthy",
      health.verdict(ungrantedTap) == .silentSinceStart)

// RUN B, NEAR channel, granted, quiet room while another process held the mic:
// 80 buffers / 384000 frames over 8 s, peak 0.0021.
let grantedQuietRoom = CaptureStreamWindow(buffers: 80, frames: 384_000,
                                           peakAmplitude: 0.0021, elapsedSeconds: 8.0,
                                           expectedSampleRate: 48_000)
check("a granted microphone in a quiet room is healthy, not silent",
      health.verdict(grantedQuietRoom) == .healthy)

// THIS IS THE WHOLE POINT. The two windows above differ by 0.0021 and by
// nothing else — same rate, same shape, same success codes. If the policy
// cannot separate them the app records an hour of nothing and posts a note
// about it.
check("the granted and ungranted windows reach different verdicts",
      health.verdict(ungrantedTap) != health.verdict(grantedQuietRoom))

// RUN D again, launched through LaunchServices without a microphone grant:
// 10 buffers a second, all zeros. The microphone fails the same way the tap does.
let ungrantedMic = CaptureStreamWindow(buffers: 60, frames: 288_000,
                                       peakAmplitude: 0.0, elapsedSeconds: 6.0,
                                       expectedSampleRate: 48_000)
check("an ungranted microphone is caught by the same rule as the tap",
      health.verdict(ungrantedMic) == .silentSinceStart)

check("a stream delivering nothing at all is not confused with a silent one",
      health.verdict(CaptureStreamWindow(buffers: 0, frames: 0, peakAmplitude: 0,
                                         elapsedSeconds: 5, expectedSampleRate: 48_000))
        == .notDelivering)
check("a stream running far under its promised rate is starved",
      health.verdict(CaptureStreamWindow(buffers: 20, frames: 40_000, peakAmplitude: 0.3,
                                         elapsedSeconds: 5, expectedSampleRate: 48_000))
        == .starved)

// A SHORT WINDOW MUST NOT ACCUSE. Two seconds of silence is a pause between
// sentences. An alarm that fires on those is an alarm nobody reads.
check("a window too short to judge is not called silent",
      health.verdict(CaptureStreamWindow(buffers: 20, frames: 96_000, peakAmplitude: 0.0,
                                         elapsedSeconds: 2.0, expectedSampleRate: 48_000))
        == .healthy)

check("only a healthy stream is usable", CaptureStreamVerdict.healthy.isUsable)
check("a silent stream is not usable", !CaptureStreamVerdict.silentSinceStart.isUsable)
check("a starved stream is not usable", !CaptureStreamVerdict.starved.isUsable)

// THE SENTENCE THE OWNER READS must name the permission, because the owner
// cannot see an OSStatus and the OS gave them no error to see.
let said = health.sentence(.silentSinceStart, streamName: "The microphone")
check("the silence sentence names the stream", said.contains("The microphone"))
check("the silence sentence names the real cause, which is a permission",
      said.lowercased().contains("permission"))
check("and it tells the owner where to look",
      said.contains("Privacy & Security"))

// NO VERDICT ABOUT THE ROOM. "Silent" here is a fact about the wire. The app
// must never tell an owner their meeting was quiet, boring, or unproductive —
// that is meaning, and this type cannot see meaning.
for v: CaptureStreamVerdict in [.healthy, .notDelivering, .starved, .silentSinceStart] {
    let s = health.sentence(v, streamName: "The microphone").lowercased()
    check("the \(v) sentence judges the wire, not the conversation",
          !s.contains("boring") && !s.contains("unproductive")
            && !s.contains("nobody spoke") && !s.contains("no one was talking"))
}

print(failures == 0 ? "all capture-core checks passed" : "\(failures) FAILED")
exit(failures == 0 ? 0 : 1)
