import AVFoundation
import Foundation

// The scratch recorder, compiled against the REAL source rather than a copy.
// `ScratchRecorder.swift` imports AVFoundation, CryptoKit and Foundation, all
// three of which exist on macOS, so the runner hands swiftc the shipping file
// itself. Nothing here is a restatement of a rule that could drift from it.
//
// What these checks are FOR: this file is the input side of a measuring
// instrument. Every defect it can carry produces a plausible number rather than
// a visible failure — a mislabelled arm reverses the verdict, a dropped buffer
// reads as a starved microphone, a short read scores as a weak decoder. So the
// suite spends itself almost entirely on the recorder's refusals.

var passes = 0
var failures = 0
func check(_ name: String, _ ok: @autoclosure () -> Bool) {
    if ok() { passes += 1; print("  ok    \(name)") }
    else { failures += 1; print("  FAIL  \(name)") }
}

// ---------------------------------------------------------------- the arms

check("three arms, spelled the way the manifest spells them",
      ScratchRecorder.Arm.allCases.map(\.rawValue) == ["A", "B", "C"])

// The single most consequential fact in the file. proof/RECORDING-PROTOCOL.md
// gives arm B exactly one difference from arm A, and it is this one.
check("arm B is the only arm that wants voice processing",
      ScratchRecorder.Arm.b.wantsVoiceProcessing
      && !ScratchRecorder.Arm.a.wantsVoiceProcessing
      && !ScratchRecorder.Arm.c.wantsVoiceProcessing)

check("every arm tells the operator where to put the phone",
      ScratchRecorder.Arm.allCases.allSatisfy { !$0.instruction.isEmpty })

// C is the close-mic control that calibrates the reference decoder; A and B are
// the ones that must be from the same spot. If C ever picked up the "2 m" text
// the operator would record three of the same thing.
check("arm C is the close-mic control, not a third room recording",
      ScratchRecorder.Arm.c.instruction.contains("20 cm")
      && !ScratchRecorder.Arm.a.instruction.contains("20 cm"))
check("arm A names the distance and arm B is pinned to the same spot",
      ScratchRecorder.Arm.a.instruction.contains("2 m")
      && ScratchRecorder.Arm.b.instruction.contains("Same spot"))
// The protocol says screen up on BOTH A and B, because orientation selects
// which handset microphone dominates. A row that omitted it would make the
// A-vs-B difference partly the orientation and partly the setting, with no way
// afterwards to say which.
check("screen up is stated on both room arms, never only one",
      ScratchRecorder.Arm.a.instruction.contains("screen up")
      && ScratchRecorder.Arm.b.instruction.contains("screen up"))

// ------------------------------------------- the arm / engine agreement gate

ScratchRecorder.voiceProcessingActual = false
ScratchRecorder.voiceProcessingRefusal = nil
check("arm A may record while the node reports voice processing off",
      ScratchRecorder.armMatchesEngine(.a) == nil)
// THE FAILURE THAT REVERSES THE ANSWER. A wanted-but-refused toggle records a
// second arm A under the name B; the harness then reads two identical
// recordings as the strongest possible evidence that the setting does nothing.
check("arm B is REFUSED while the node reports voice processing off",
      ScratchRecorder.armMatchesEngine(.b) != nil)

ScratchRecorder.voiceProcessingActual = true
check("arm B may record once the node actually reports it on",
      ScratchRecorder.armMatchesEngine(.b) == nil)
check("arm A is refused while voice processing is still on",
      ScratchRecorder.armMatchesEngine(.a) != nil)
check("arm C is refused too — it is today's settings, like A",
      ScratchRecorder.armMatchesEngine(.c) != nil)

ScratchRecorder.voiceProcessingActual = false
ScratchRecorder.voiceProcessingRefusal = "the node said no"
check("a refusal reason reaches the operator's sentence",
      ScratchRecorder.armMatchesEngine(.b)?.contains("the node said no") == true)
ScratchRecorder.voiceProcessingRefusal = nil

// ------------------------------------------------------- what a take reports

func take(_ arm: ScratchRecorder.Arm, seconds: Double, dropped: Int,
          failure: String? = nil) -> ScratchRecorder.Take {
    ScratchRecorder.Take(arm: arm,
                         url: URL(fileURLWithPath: "/tmp/arm_a_x.wav"),
                         seconds: seconds, sampleRate: 48_000, channels: 1,
                         droppedBuffers: dropped,
                         sha256: String(repeating: "a", count: 64),
                         writeFailure: failure)
}

check("a clean three-minute take has nothing to report",
      take(.a, seconds: 190, dropped: 0).trouble == nil)
// A hole in the WAV and a starved microphone are the same shape to the scorer,
// and one of them is the finding the experiment exists to produce.
check("one dropped buffer is trouble, not a rounding error",
      take(.a, seconds: 190, dropped: 1).trouble != nil)
check("a write failure is trouble even with nothing dropped",
      take(.a, seconds: 190, dropped: 0, failure: "disk full").trouble != nil)
// proof/engine_or_audio.py refuses a transcript that covers less than 0.7 of
// the script. A short read produces exactly that and looks like a weak decoder.
check("a read far shorter than the script is trouble",
      take(.a, seconds: 20, dropped: 0).trouble != nil)
check("the dropped count is named in the sentence, not just implied",
      take(.a, seconds: 190, dropped: 7).trouble?.contains("7") == true)

// ------------------------------------------------------------- provenance

// proof/engine_or_audio.py:272 parses this line. It is the only thing standing
// between arm A's transcript filed under arm B and a reversed verdict.
let line = take(.b, seconds: 190, dropped: 0).provenance(decoder: "sf_ctx")
check("provenance starts with the prefix the scorer looks for",
      line.hasPrefix("#anticipy:"))
check("provenance names the arm", line.contains("arm=B"))
check("provenance names the decoder", line.contains("decoder=sf_ctx"))
check("provenance names the file", line.contains("wav=arm_a_x.wav"))
check("provenance carries a full sha256",
      line.contains("sha256=" + String(repeating: "a", count: 64)))
// Two cells that are subtracted from each other must be shown to come from
// different recordings. Same digest, different arm is the mislabel this catches.
check("the arm travels separately from the digest, so a relabel is visible",
      take(.a, seconds: 190, dropped: 0).provenance(decoder: "sf_ctx").contains("arm=A"))

// ------------------------------------------------------------ the deep copy

let format = AVAudioFormat(standardFormatWithSampleRate: 48_000, channels: 1)!
let source = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 512)!
source.frameLength = 512
source.floatChannelData![0][0] = 0.5
source.floatChannelData![0][511] = -0.25

let copied = ScratchRecorder.copy(source)
check("a buffer copy is produced", copied != nil)
check("the copy keeps the frame count", copied?.frameLength == 512)
check("the copy carries the samples", copied?.floatChannelData![0][0] == 0.5)
check("the copy carries the LAST sample too — a short memcpy loses the tail",
      copied?.floatChannelData![0][511] == -0.25)
// The tap reuses its buffer. A reference held past the callback records
// whatever arrived next, which is silence at the end of every recording.
source.floatChannelData![0][0] = 0.9
check("the copy is a real copy — mutating the source does not change it",
      copied?.floatChannelData![0][0] == 0.5)

let empty = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 512)!
empty.frameLength = 0
check("a zero-length buffer is refused rather than written", ScratchRecorder.copy(empty) == nil)

// ------------------------------------------------------- start / stop / digest

let recorder = ScratchRecorder.shared
check("the recorder starts idle", !recorder.isRecording)
check("an idle recorder has no arm", recorder.currentArm == nil)
check("stopping when nothing is recording returns nothing", recorder.stop() == nil)

let dead = AVAudioFormat(standardFormatWithSampleRate: 48_000, channels: 1)!
_ = dead
// A 0 Hz format is what the input node reports while a phone call owns the
// session. Opening a file with it is the exception PhoneListener guards.
check("a start with no usable format is refused with a sentence",
      recorder.start(arm: .a, format: AVAudioFormat()) != nil)
check("a refused start leaves the recorder idle", !recorder.isRecording)

if recorder.start(arm: .a, format: format) == nil {
    check("a started recorder says so", recorder.isRecording)
    check("a started recorder knows its arm", recorder.currentArm == .a)
    check("starting twice is refused", recorder.start(arm: .b, format: format) != nil)
    check("the second start did not change the arm", recorder.currentArm == .a)
    for _ in 0..<40 { recorder.accept(source) }
    let done = recorder.stop()
    check("stop returns a take", done != nil)
    check("the take names the arm that was recorded", done?.arm == .a)
    check("the take has audio in it", (done?.seconds ?? 0) > 0)
    check("the take lost nothing", done?.droppedBuffers == 0)
    check("the writer reported no failure", done?.writeFailure == nil)
    // The digest is computed over the closed file. A digest taken before the
    // writer drained would hash a partial recording, and two cells naming one
    // recording would then disagree about it.
    check("the take carries a real sha256", done?.sha256.count == 64)
    check("the file is on disk", FileManager.default.fileExists(atPath: done!.url.path))
    check("a file with audio in it is not empty",
          ((try? FileManager.default.attributesOfItem(atPath: done!.url.path)[.size] as? Int) ?? 0) > 44)
    check("the recorder is idle again", !recorder.isRecording)
    check("the same bytes hash the same twice",
          ScratchRecorder.digest(of: done!.url) == done!.sha256)
    ScratchRecorder.discard(done!.url)
    check("a discarded take is gone",
          !FileManager.default.fileExists(atPath: done!.url.path))
} else {
    failures += 1
    print("  FAIL  could not start a recording at all")
}

// A buffer offered to an idle recorder must be a no-op, not a crash and not a
// file. Every microphone buffer in the product goes through this call.
recorder.accept(source)
check("an idle recorder ignores audio", !recorder.isRecording)

check("the backlog ceiling is a real number, not zero",
      ScratchRecorder.maxPendingBuffers > 0)
check("a missing file digests to nothing rather than crashing",
      ScratchRecorder.digest(of: URL(fileURLWithPath: "/tmp/does-not-exist-\(UUID()).wav")).isEmpty)

print("ScratchRecorder: \(passes) checks passed, \(failures) failed")
if failures > 0 { exit(1) }
