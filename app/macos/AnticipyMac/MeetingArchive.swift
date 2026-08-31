import AVFoundation
import Foundation

/// A local, inspectable record of one meeting. Microphone and system audio are
/// intentionally separate tracks: that keeps provenance truthful and lets a
/// future diarizer improve the transcript without pretending the mix already
/// knew who spoke. No audio path in this type has a network destination.
final class MeetingArchive: @unchecked Sendable {
    private struct Manifest: Codable {
        let id: UUID
        let startedAt: Date
        var endedAt: Date?
        let detectedBundleID: String?
        var ownerTracks: [String]
        var systemTracks: [String]
        var transcript: [MeetingTranscriptLine]
    }

    let directoryURL: URL
    private let queue = DispatchQueue(label: "ai.anticipy.mac.meeting-archive")
    private let manifestURL: URL
    private var manifest: Manifest
    private var ownerFile: AVAudioFile?
    private var systemFile: AVAudioFile?
    private var ownerPart = 0
    private var systemPart = 0
    private var finished = false

    init(detectedBundleID: String?, rootURL: URL? = nil) throws {
        let root = rootURL ?? FileManager.default.urls(
            for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Anticipy", isDirectory: true)
            .appendingPathComponent("Meetings", isDirectory: true)
        try FileManager.default.createDirectory(at: root,
                                                withIntermediateDirectories: true)

        let now = Date()
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyyMMdd-HHmmss"
        let id = UUID()
        directoryURL = root.appendingPathComponent(
            "\(formatter.string(from: now))-\(id.uuidString.prefix(8))",
            isDirectory: true)
        try FileManager.default.createDirectory(at: directoryURL,
                                                withIntermediateDirectories: true)
        manifestURL = directoryURL.appendingPathComponent("meeting.json")
        manifest = Manifest(id: id, startedAt: now, endedAt: nil,
                            detectedBundleID: detectedBundleID,
                            ownerTracks: [], systemTracks: [], transcript: [])
        try writeManifest()
    }

    func record(_ buffer: AVAudioPCMBuffer, channel: MeetingCaptureChannel) {
        queue.async { [weak self] in
            guard let self, !self.finished else { return }
            do {
                let file = try self.file(for: channel, format: buffer.format)
                try file.write(from: buffer)
            } catch {
                // The recorder remains usable if a local disk write fails;
                // stream health and on-device transcription continue.
            }
        }
    }

    func append(_ line: MeetingTranscriptLine) {
        queue.async { [weak self] in
            guard let self, !self.finished else { return }
            self.manifest.transcript.append(line)
            try? self.writeManifest()
        }
    }

    func finish(completion: @escaping @MainActor @Sendable (URL) -> Void) {
        queue.async { [weak self] in
            guard let self else { return }
            if !self.finished {
                self.finished = true
                self.ownerFile = nil
                self.systemFile = nil
                self.manifest.endedAt = Date()
                try? self.writeManifest()
            }
            let url = self.directoryURL
            Task { @MainActor in completion(url) }
        }
    }

    private func file(for channel: MeetingCaptureChannel,
                      format: AVAudioFormat) throws -> AVAudioFile {
        switch channel {
        case .owner:
            if let ownerFile, ownerFile.processingFormat == format { return ownerFile }
            ownerPart += 1
            let name = "owner-microphone-\(ownerPart).caf"
            let file = try AVAudioFile(forWriting: directoryURL.appendingPathComponent(name),
                                       settings: storageSettings(for: format),
                                       commonFormat: format.commonFormat,
                                       interleaved: format.isInterleaved)
            ownerFile = file
            manifest.ownerTracks.append(name)
            try? writeManifest()
            return file
        case .system:
            if let systemFile, systemFile.processingFormat == format { return systemFile }
            systemPart += 1
            let name = "system-audio-\(systemPart).caf"
            let file = try AVAudioFile(forWriting: directoryURL.appendingPathComponent(name),
                                       settings: storageSettings(for: format),
                                       commonFormat: format.commonFormat,
                                       interleaved: format.isInterleaved)
            systemFile = file
            manifest.systemTracks.append(name)
            try? writeManifest()
            return file
        }
    }

    /// A file is physically interleaved even when AVAudioFile exposes a
    /// non-interleaved processing buffer. Passing the processing-only flag in
    /// the file settings makes Core Audio ignore it noisily on every session.
    private func storageSettings(for format: AVAudioFormat) -> [String: Any] {
        var settings = format.settings
        settings.removeValue(forKey: AVLinearPCMIsNonInterleaved)
        return settings
    }

    private func writeManifest() throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        let data = try encoder.encode(manifest)
        try data.write(to: manifestURL, options: .atomic)
    }
}
