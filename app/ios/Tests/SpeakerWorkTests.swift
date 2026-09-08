import Foundation
import AVFoundation

final class SlowEmbedder: VoiceEmbedder {
    var ranOnMain = false
    var calls = 0
    func embed(_ samples: [Float]) -> [Float]? {
        ranOnMain = ranOnMain || Thread.isMainThread
        calls += 1
        Thread.sleep(forTimeInterval: 0.15)
        return [1, 0, 0]
    }
}

let model = SlowEmbedder()
let rosterFilename = "speaker-test-" + UUID().uuidString + ".json"
let roster = VoiceRoster(filename: rosterFilename)
defer {
    let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
    try? FileManager.default.removeItem(at: support.appendingPathComponent(rosterFilename))
}
let tagger = SpeakerTagger(roster: roster, modelAvailable: true, makeEmbedder: { model })
let format = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: 16000,
                          channels: 1, interleaved: false)!
func feed(_ receiver: SpeakerTagger = tagger) {
    let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 32000)!
    buffer.frameLength = 32000
    buffer.floatChannelData![0].initialize(repeating: 0.2, count: 32000)
    receiver.accept(buffer)
}
var delivered: [Int] = []
var mainThreadTicks = 0
let timer = Timer.scheduledTimer(withTimeInterval: 0.01, repeats: true) { _ in mainThreadTicks += 1 }
let start = Date()
feed()
tagger.tagForLatestUtterance { _ in delivered.append(1) }
feed()
tagger.tagForLatestUtterance { _ in delivered.append(2) }
assert(Date().timeIntervalSince(start) < 0.1, "inference must not block the caller")
while delivered.count < 2 && Date().timeIntervalSince(start) < 3 {
    RunLoop.main.run(until: Date().addingTimeInterval(0.01))
}
assert(delivered == [1, 2], "slow speaker work must preserve utterance order")
assert(!model.ranOnMain && mainThreadTicks >= 10, "the UI run loop must keep working during inference")

feed()
tagger.tagForLatestUtterance { _ in delivered.append(99) }
tagger.invalidatePendingDeliveries()
feed()
tagger.tagForLatestUtterance { _ in delivered.append(3) }
let end = Date().addingTimeInterval(3)
while !delivered.contains(3) && Date() < end { RunLoop.main.run(until: Date().addingTimeInterval(0.01)) }
assert(delivered == [1, 2, 3], "an account boundary must discard the old result and retain the new one")
timer.invalidate()
print("Speaker work: ordered delivery, responsive main loop, and account invalidation passed; ticks=\(mainThreadTicks)")

/// Block the FIRST real embedding until the test has crossed the account
/// boundary. A timed sleep alone could pass without ever putting the old work
/// in flight; started/release prove the ordering the report is about.
final class ControlledEmbedder: VoiceEmbedder {
    let started = DispatchSemaphore(value: 0)
    let release = DispatchSemaphore(value: 0)
    let result: [Float]?
    private var calls = 0 // only SpeakerTagger's serial embedding queue touches it
    init(result: [Float]?) { self.result = result }
    func embed(_ samples: [Float]) -> [Float]? {
        calls += 1
        if calls == 1 {
            started.signal()
            guard release.wait(timeout: .now() + 3) == .success else { return nil }
        }
        return result
    }
}

for result: [Float]? in [[1, 0, 0], nil] {
    let controlled = ControlledEmbedder(result: result)
    let crossing = SpeakerTagger(roster: roster, modelAvailable: true,
                                 makeEmbedder: { controlled })
    var currentAccount = "A"
    var captured: [(owner: String, words: String)] = []
    // Like PhoneListener.deliver: capture the line BEFORE asynchronous tagging,
    // and let the session callback read its current owner only when invoked.
    let onSpeaker: (String) -> Void = { words in captured.append((currentAccount, words)) }
    feed(crossing)
    crossing.tagForLatestUtterance { _ in onSpeaker("A-private-audio") }
    assert(controlled.started.wait(timeout: .now() + 1) == .success,
           "A's embedding must actually start before the account changes")
    currentAccount = "" // signOut/expireSession clear credentials first
    crossing.invalidatePendingDeliveries() // clearSignedInSurface's actual first action
    currentAccount = "B"
    feed(crossing)
    crossing.tagForLatestUtterance { _ in onSpeaker("B-audio") }
    controlled.release.signal()
    let deadline = Date().addingTimeInterval(3)
    while !captured.contains(where: { $0.words == "B-audio" }) && Date() < deadline {
        RunLoop.main.run(until: Date().addingTimeInterval(0.01))
    }
    assert(captured.count == 1 && captured.first?.owner == "B"
           && captured.first?.words == "B-audio",
           "delayed A audio must never call onSpeaker after B signs in, including nil-tag fallback")
    print("PASS: pre-tagging account epoch rejects delayed A audio (\(result == nil ? "nil" : "valid") tag), preserves B")
}

// A normal Stop has no account invalidation. PhoneListener.stop sends its final
// tail through this SAME serial tag queue (pinned by the runner), so the tail
// must remain behind the earlier delayed utterance and both must be delivered.
let stopModel = ControlledEmbedder(result: [1, 0, 0])
let stopping = SpeakerTagger(roster: roster, modelAvailable: true, makeEmbedder: { stopModel })
var stopWords: [String] = []
feed(stopping)
stopping.tagForLatestUtterance { _ in stopWords.append("before-stop") }
assert(stopModel.started.wait(timeout: .now() + 1) == .success)
feed(stopping)
stopping.tagForLatestUtterance { _ in stopWords.append("final-stop-tail") }
stopModel.release.signal()
let stopDeadline = Date().addingTimeInterval(3)
while stopWords.count < 2 && Date() < stopDeadline {
    RunLoop.main.run(until: Date().addingTimeInterval(0.01))
}
assert(stopWords == ["before-stop", "final-stop-tail"],
       "ordinary Stop must preserve both the delayed utterance and its ordered tail")
print("PASS: normal Stop preserves delayed utterance and final tail in order")
