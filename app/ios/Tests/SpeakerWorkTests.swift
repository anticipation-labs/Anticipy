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
func feed() {
    let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 32000)!
    buffer.frameLength = 32000
    buffer.floatChannelData![0].initialize(repeating: 0.2, count: 32000)
    tagger.accept(buffer)
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
