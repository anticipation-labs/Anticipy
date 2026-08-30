import Foundation

/// Which recognizer listens, and how a hole in the audio is spoken about.
/// Foundation on purpose: the shell test runners compile this file directly
/// with no simulator, no signing, and no Speech framework.
enum ListenEnginePolicy {

    /// The operator's escape hatch. iOS 26's SpeechTranscriber is the default
    /// ears on every device that has it; this flag is the way back to the
    /// pre-26 recognizer without a rebuild. A hatch that loses to the OS
    /// check is decoration, so the flag wins over everything.
    static let legacyFlagKey = "useLegacySpeech"

    static var prefersLegacy: Bool {
        UserDefaults.standard.object(forKey: legacyFlagKey) as? Bool == true
    }

    /// The decision, with the OS version injected so a test can stand on a
    /// phone it does not have. `version` is (major, minor, patch) — what
    /// ProcessInfo.processInfo.operatingSystemVersion reports in the field.
    static func usesAnalyzer(on version: (major: Int, minor: Int, patch: Int)) -> Bool {
        if prefersLegacy { return false }
        return version.major > 26 || (version.major == 26 && version.minor >= 0)
    }

    /// The runtime form the app calls — the real OS version, not a test's.
    static var usesAnalyzerNow: Bool {
        let v = ProcessInfo.processInfo.operatingSystemVersion
        return usesAnalyzer(on: (v.majorVersion, v.minorVersion, v.patchVersion))
    }
}

/// The one honest way to talk about audio nobody captured.
///
/// A BLE gap is not silence, and silence is not speech. Splicing quiet audio
/// across a hole invites the recognizer to speak through it — a model asked
/// to decode dead air will invent a sentence rather than return nothing.
/// So a hole becomes a MARK: a line in the feed that says how long nobody
/// was listening, in the same voice the rest of the transcript uses. It is
/// never pushed as a transcript row, so the brain can never triage a hole
/// into an errand.
enum GapMarker {

    static let prefix = "[unavailable "

    static func text(_ seconds: TimeInterval) -> String {
        let total = Int(seconds.rounded())
        guard total > 0 else { return prefix + "under 1s]" }
        let h = total / 3600
        let m = (total % 3600) / 60
        let s = total % 60
        if h > 0 { return prefix + "\(h)h \(m)m \(s)s]" }
        if m > 0 { return prefix + "\(m)m \(s)s]" }
        return prefix + "\(s)s]"
    }
}
