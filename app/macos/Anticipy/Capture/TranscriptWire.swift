import Foundation

/// The row one Mac transcript line becomes on the wire.
///
/// It is the SAME row the phone posts — `AnticipyBackend.pushEvent` plus
/// `CaptureEnvelope.wireFields` in app/ios — built in one pure place so the
/// shape can be read by a test without a network, and so the Mac cannot
/// drift from the phone one column at a time. The Worker at api.anticipy.ai
/// refuses an unknown field with a 400 (migration/workers/src/pb/records.ts),
/// so every key here is one the `events` table has.
///
/// No audio and no meaning pass through this type: it is given text the
/// on-device transcriber already produced and two wall-clock instants.
public enum TranscriptWire {
    /// WHICH EAR heard the line. The phone stamps "phone_mic", the pendant
    /// "pendant", a typed line "typed" (app/ios CaptureSourcePolicy). The Mac
    /// is one more ear, "mac". Which SIDE of the call spoke is not the ear —
    /// it travels as `speaker`, which the brain reads to tell the owner's own
    /// words from what was overheard.
    ///
    /// overnight/are_the_ears_live.py counts this exact value on its "heard
    /// by the Mac" line; tests/test_ears_hear_the_mac.py pins the two
    /// together.
    public static let source = "mac"

    public static let kind = "transcript"

    /// The phone stamps "iphone-b<CFBundleVersion>" on every row it writes, so
    /// the ears gate can say which BUILD last spoke. The Mac does the same
    /// under its own prefix. "?" when the bundle has no number, as the phone
    /// does, rather than inventing one.
    public static let devicePrefix = "mac-b"

    public static func deviceID(build: String?) -> String {
        let number = (build ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return devicePrefix + (number.isEmpty ? "?" : number)
    }

    /// The microphone is the owner; the system tap is everyone else.
    public static func speaker(for channel: MeetingCaptureChannel) -> String {
        switch channel {
        case .owner: return "owner"
        case .system: return "other"
        }
    }

    /// The same clock the phone's CaptureEnvelope uses: fractional seconds,
    /// UTC. Two instants 300 ms apart must not render as the same string, or
    /// a genuinely bracketed line is indistinguishable from a collapsed one.
    public static let clock: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        f.timeZone = TimeZone(identifier: "UTC")
        return f
    }()

    /// Every column the row carries, and nothing else.
    ///
    /// `capture_started_at` is canonical and `spoken_at` is the older name for
    /// the SAME instant; `capture_ended_at` is when the words finished. Reads
    /// that came back out of order collapse onto the end, exactly as the
    /// phone's CaptureEnvelope does: a wall clock steps backwards for
    /// ordinary reasons, and two instants that do not bracket anything are
    /// one stale read and one fresh one.
    public static func body(text: String, speaker: String,
                            startedAt: Date, endedAt: Date,
                            ownerRef: String, deviceID: String) -> [String: String] {
        let start = endedAt > startedAt ? startedAt : endedAt
        return [
            "device_id": deviceID,
            "kind": kind,
            "text": text,
            "decision": "",
            "goal": "",
            "owner_ref": ownerRef,
            "source": source,
            "speaker": speaker,
            "capture_started_at": clock.string(from: start),
            "spoken_at": clock.string(from: start),
            "capture_ended_at": clock.string(from: endedAt),
        ]
    }
}
