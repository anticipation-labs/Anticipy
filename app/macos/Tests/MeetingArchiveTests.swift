import AVFoundation
import Foundation

var failures = 0
func check(_ name: String, _ condition: @autoclosure () -> Bool) {
    let passed = condition()
    print("\(passed ? "PASS" : "FAIL"): \(name)")
    if !passed { failures += 1 }
}

guard CommandLine.arguments.count == 2 else {
    print("expected a temporary output directory")
    exit(2)
}
let root = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
let archive = try MeetingArchive(detectedBundleID: "com.google.Chrome",
                                 rootURL: root)

func buffer(sampleRate: Double, channels: AVAudioChannelCount,
            value: Float) -> AVAudioPCMBuffer {
    let format = AVAudioFormat(standardFormatWithSampleRate: sampleRate,
                               channels: channels)!
    let pcm = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 4_800)!
    pcm.frameLength = 4_800
    for channel in 0..<Int(channels) {
        for frame in 0..<Int(pcm.frameLength) {
            pcm.floatChannelData![channel][frame] = value
        }
    }
    return pcm
}

archive.record(buffer(sampleRate: 48_000, channels: 1, value: 0.15),
               channel: .owner)
archive.record(buffer(sampleRate: 48_000, channels: 2, value: 0.25),
               channel: .system)
let start = Date(timeIntervalSince1970: 1_800_000_000)
archive.append(MeetingTranscriptLine(text: "The other side is present.",
                                     channel: .system, startedAt: start,
                                     endedAt: start.addingTimeInterval(1)))

var finishedURL: URL?
archive.finish { url in finishedURL = url }
let deadline = Date().addingTimeInterval(5)
while finishedURL == nil, RunLoop.current.run(mode: .default,
                                               before: Date().addingTimeInterval(0.05)),
      Date() < deadline {}

check("the archive completes", finishedURL != nil)
let directory = finishedURL ?? archive.directoryURL
let owner = directory.appendingPathComponent("owner-microphone-1.caf")
let system = directory.appendingPathComponent("system-audio-1.caf")
let manifest = directory.appendingPathComponent("meeting.json")
check("the microphone is written as its own non-empty track",
      (try? owner.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0) ?? 0 > 0)
check("system audio is written as its own non-empty track",
      (try? system.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0) ?? 0 > 0)
check("the meeting manifest is written", FileManager.default.fileExists(atPath: manifest.path))

let decoded = try JSONSerialization.jsonObject(with: Data(contentsOf: manifest)) as? [String: Any]
let transcript = decoded?["transcript"] as? [[String: Any]]
check("the manifest keeps the detected meeting app",
      decoded?["detectedBundleID"] as? String == "com.google.Chrome")
check("the transcript keeps system-audio provenance",
      transcript?.first?["channel"] as? String == "system")
check("the manifest records both physical track lists",
      (decoded?["ownerTracks"] as? [String]) == ["owner-microphone-1.caf"]
        && (decoded?["systemTracks"] as? [String]) == ["system-audio-1.caf"])

print(failures == 0 ? "all meeting-archive checks passed" : "\(failures) FAILED")
exit(failures == 0 ? 0 : 1)
