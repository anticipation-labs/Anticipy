// CaptureStreamHealth — decides whether a capture stream is actually carrying
// audio, or is a perfectly-shaped stream of zeros.
//
// THIS TYPE EXISTS BECAUSE OF A MEASUREMENT, and the measurement is the reason
// the Mac app must not trust `AudioDeviceStart` returning noErr. Measured on
// macOS 15.6.1 (24G90), 2026-08-25, full log in
// research/2026-08-25-macos-concurrent-capture.md:
//
//   Without the TCC grant, Core Audio does not fail. It succeeds.
//   `AudioHardwareCreateProcessTap` returned noErr, the aggregate device was
//   created, the IOProc was called 94 times a second with a well-formed buffer
//   list (1 buffer, 2 channels, 4096 bytes, non-null data) at exactly the right
//   sample rate — and every sample in it was 0.0, for fifteen seconds.
//   The same happened to the MICROPHONE when the app was launched through
//   LaunchServices without a microphone grant: 10 buffers/second, all zeros.
//   With the grant, the identical code read 0.0019-0.0111 peak in a quiet room.
//
// So "it started" and "it is recording" are different facts, and an app that
// conflates them records an hour of nothing and posts a note about silence.
// This type is what keeps them apart.
//
// LAW 1: this is not a rule about what words mean. It asks one question about
// plumbing — did any sample in this window differ from zero — and reports a
// state. It cannot measure meaning; it never sees a transcript.
import Foundation

/// What one capture stream did over one observation window. Counters only.
public struct CaptureStreamWindow: Equatable, Sendable {
    public let buffers: Int
    public let frames: Int64
    /// Largest absolute sample seen in the window. Exactly 0.0 means every
    /// sample was zero, which is the ungranted-TCC signature above.
    public let peakAmplitude: Float
    public let elapsedSeconds: Double
    public let expectedSampleRate: Double

    public init(buffers: Int, frames: Int64, peakAmplitude: Float,
                elapsedSeconds: Double, expectedSampleRate: Double) {
        self.buffers = buffers
        self.frames = frames
        self.peakAmplitude = peakAmplitude
        self.elapsedSeconds = elapsedSeconds
        self.expectedSampleRate = expectedSampleRate
    }
}

public enum CaptureStreamVerdict: Equatable, Sendable {
    /// Nothing arrived at all. The device stopped, was unplugged, or never ran.
    case notDelivering
    /// Buffers arrive, but far below the rate the format promised — an
    /// underrun, a dying aggregate, a `coreaudiod` restart in progress.
    case starved
    /// Buffers arrive at the right rate and every sample is zero. On macOS this
    /// is what a MISSING PRIVACY GRANT looks like; it is not an error code.
    /// The owner must be told, in these words, rather than left recording.
    case silentSinceStart
    case healthy

    /// Whether a meeting may honestly continue on this stream alone.
    public var isUsable: Bool { self == .healthy }
}

public struct CaptureStreamHealthPolicy: Sendable {
    /// A window shorter than this cannot distinguish a stall from a hiccup, and
    /// cannot distinguish a missing grant from a pause between words.
    public let minimumWindowSeconds: Double
    /// Below this fraction of the promised sample rate the stream is starved.
    public let starvedBelowRateFraction: Double

    public init(minimumWindowSeconds: Double = 3.0,
                starvedBelowRateFraction: Double = 0.5) {
        self.minimumWindowSeconds = minimumWindowSeconds
        self.starvedBelowRateFraction = starvedBelowRateFraction
    }

    public func verdict(_ w: CaptureStreamWindow) -> CaptureStreamVerdict {
        if w.buffers <= 0 || w.frames <= 0 { return .notDelivering }
        guard w.elapsedSeconds > 0, w.expectedSampleRate > 0 else { return .notDelivering }

        let observedRate = Double(w.frames) / w.elapsedSeconds
        if observedRate < w.expectedSampleRate * starvedBelowRateFraction { return .starved }

        // A window too short to judge is reported as flowing, not as silent.
        // Calling a two-second pause "your microphone is off" is the false
        // alarm that teaches an owner to ignore the warning.
        if w.elapsedSeconds < minimumWindowSeconds { return .healthy }

        // Exactly zero, not "quiet". A quiet room measured 0.0019; a stream
        // with no grant measured 0.0000. The test is identity with zero.
        if w.peakAmplitude == 0 { return .silentSinceStart }
        return .healthy
    }

    /// What the owner reads. No verdict about the ROOM — only about the wire.
    public func sentence(_ v: CaptureStreamVerdict, streamName: String) -> String {
        switch v {
        case .healthy:
            return "\(streamName) is carrying audio."
        case .notDelivering:
            return "\(streamName) has stopped delivering. The device may have changed or been unplugged."
        case .starved:
            return "\(streamName) is delivering far less audio than its format promises. Something is interrupting it."
        case .silentSinceStart:
            return "\(streamName) started, but every sample since has been silence. "
                 + "On macOS that is what a missing privacy permission looks like — "
                 + "the capture succeeds and records nothing. Check Privacy & Security "
                 + "before this meeting goes any further."
        }
    }
}
