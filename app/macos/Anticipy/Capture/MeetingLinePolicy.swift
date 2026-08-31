import Foundation

/// Which physical side of a Mac conversation produced a transcript line.
/// The microphone is the owner; the Core Audio process tap is everyone whose
/// voice the Mac is playing. This is capture provenance, not speaker identity.
public enum MeetingCaptureChannel: String, Codable, Equatable, Sendable {
    case owner
    case system
}

public struct MeetingTranscriptLine: Codable, Equatable, Sendable {
    public let text: String
    public let channel: MeetingCaptureChannel
    public let startedAt: Date
    public let endedAt: Date

    public init(text: String, channel: MeetingCaptureChannel,
                startedAt: Date, endedAt: Date) {
        self.text = text
        self.channel = channel
        self.startedAt = startedAt
        self.endedAt = endedAt
    }
}

/// Collects finalized SpeechTranscriber phrases into one bounded line.
///
/// Partial hypotheses are deliberately not emitted: a partial flushed just
/// before its final revision produces the same sentence twice. Final phrases
/// are the stable unit, and silence or an absolute ceiling groups them into
/// the envelope the server already understands.
public struct MeetingLinePolicy: Sendable {
    public let silenceSeconds: TimeInterval
    public let ceilingSeconds: TimeInterval

    private(set) var phrases: [String] = []
    private(set) var startedAt: Date?
    private(set) var lastPhraseAt: Date?

    public init(silenceSeconds: TimeInterval = 2.5,
                ceilingSeconds: TimeInterval = 15.0) {
        self.silenceSeconds = silenceSeconds
        self.ceilingSeconds = ceilingSeconds
    }

    public var hasFinalText: Bool { !phrases.isEmpty }

    public mutating func absorbFinal(_ text: String, at now: Date) {
        let clean = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { return }
        if startedAt == nil { startedAt = now }
        lastPhraseAt = now
        // SpeechTranscriber promises finalized phrases once, but retaining the
        // adjacent equality guard makes a restarted result task idempotent.
        if phrases.last != clean { phrases.append(clean) }
    }

    public func shouldFlush(at now: Date) -> Bool {
        guard hasFinalText, let start = startedAt, let last = lastPhraseAt else { return false }
        return now.timeIntervalSince(last) >= silenceSeconds
            || now.timeIntervalSince(start) >= ceilingSeconds
    }

    public mutating func take(channel: MeetingCaptureChannel,
                              at now: Date) -> MeetingTranscriptLine? {
        guard hasFinalText else { return nil }
        let text = phrases.joined(separator: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let start = startedAt ?? now
        let end = lastPhraseAt ?? now
        phrases.removeAll(keepingCapacity: true)
        startedAt = nil
        lastPhraseAt = nil
        guard !text.isEmpty else { return nil }
        return MeetingTranscriptLine(text: text, channel: channel,
                                     startedAt: start, endedAt: end)
    }
}
