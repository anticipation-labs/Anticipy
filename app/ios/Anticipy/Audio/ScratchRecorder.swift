import AVFoundation
import CryptoKit
import Foundation

/// THE MISSING FORTY LINES.
///
/// `proof/engine_or_audio.py` is a 1,400-line word-error-rate harness with a
/// pre-registered decision rule, a 370-word script, a written protocol and 57
/// tests. It has produced nothing since 2026-08-24, and
/// `research/2026-08-25-transcription-quality.md` §3.2 names the whole reason:
/// nothing in this app writes the microphone tap to a file. The harness's own
/// source says it at `proof/engine_or_audio.py:262` — *"The scratch recorder
/// DOES NOT EXIST YET."* This is that file.
///
/// WHAT IT IS FOR. Three recordings of one page, read aloud. Arm A is today's
/// configuration. Arm B is identical plus `setVoiceProcessingEnabled(true)`.
/// Arm C is a close-mic control that calibrates the reference decoder. The Mac
/// scores them and answers the one open question in the capture path: are words
/// lost because the recognizer is weak, or because the microphone is set up to
/// hear badly? Production says roughly a third of spoken words arrive
/// (`research/2026-08-24-engine-options.md` §4(b)). Nobody knows which half of
/// that is true, and no amount of reading the code settles it.
///
/// WHAT IT MUST NOT DO — and this is the whole design.
///
/// **It must not change what it measures.** A recorder that writes to disk on
/// the audio thread can stall the tap, drop buffers, and hand the harness a
/// recording of the recorder. So `accept(_:)` does exactly two things: copy the
/// buffer and hand it to a serial queue. Every file operation happens on that
/// queue. The copy is mandatory — the tap hands out a buffer it reuses, so
/// keeping a reference and writing it later writes whatever arrived next.
///
/// **It must not lie about a partial recording.** The backlog is bounded. If
/// the writer falls behind by more than `maxPendingBuffers`, buffers are
/// DROPPED and counted, and `stop()` reports the count. A WAV with a hole in it
/// scores as a starved microphone, which is one of the two answers the
/// experiment exists to distinguish — so an unreported drop does not just add
/// noise, it manufactures the finding. `proof/engine_or_audio.py:169-191`
/// records two headlines this repo has already printed off exactly that shape
/// of missing sample.
///
/// **It must not be on by accident.** `armed` is false until a person turns it
/// on, and every path back out of recording clears it. Nothing in the product
/// arms it; the only caller is the diagnostics screen.
///
/// **It writes the tap's own format, unconverted.** `AVAudioFile` created with
/// `format.settings` has a processing format identical to the tap's, so
/// `write(from:)` performs no sample-rate conversion and no requantisation.
/// The recording is what the microphone delivered, not a resampling of it. The
/// Mac downconverts for the reference decoder with `afconvert`, where the
/// conversion is visible and reversible. A converter here would be a silent
/// third arm nobody registered.
final class ScratchRecorder {
    static let shared = ScratchRecorder()

    /// The three arms of `proof/RECORDING-PROTOCOL.md`, spelled the way the
    /// manifest spells them, because the directory name is what tells the
    /// harness which arm a transcript belongs to (`reference_decode.arm_of`).
    enum Arm: String, CaseIterable {
        case a = "A", b = "B", c = "C"

        /// What the operator has to physically do differently. Shown on the
        /// screen so the phone itself carries the protocol.
        var instruction: String {
            switch self {
            case .a: return "On the tape, about 2 m away, screen up. Today's settings."
            case .b: return "Same spot, same distance, screen up. Voice processing ON."
            case .c: return "Held about 20 cm from your mouth. Today's settings."
            }
        }

        /// Arm B is the only one that changes the audio front end.
        var wantsVoiceProcessing: Bool { self == .b }
    }

    /// What a finished recording knows about itself. Everything the harness's
    /// provenance line needs, computed once, at stop.
    struct Take {
        let arm: Arm
        let url: URL
        let seconds: Double
        let sampleRate: Double
        let channels: UInt32
        let droppedBuffers: Int
        let sha256: String
        let writeFailure: String?

        /// The line `proof/engine_or_audio.py` parses (PROVENANCE_PREFIX at
        /// :272). It is the only thing standing between a run and arm A's
        /// transcript filed under arm B — which, per
        /// `proof/reference_decode.py:182`, reverses the answer about the audio
        /// session line.
        func provenance(decoder: String) -> String {
            "#anticipy: arm=\(arm.rawValue) decoder=\(decoder) "
                + "wav=\(url.lastPathComponent) sha256=\(sha256)"
        }

        /// A take with a hole in it is not a measurement. The screen refuses to
        /// call it done and says which of the two reasons applies.
        var trouble: String? {
            if let writeFailure { return "The writer failed: \(writeFailure)" }
            if droppedBuffers > 0 {
                return "\(droppedBuffers) buffer(s) never reached the file. "
                    + "This recording has gaps in it — record the arm again."
            }
            if seconds < 60 {
                return "Only \(Int(seconds))s of audio. The script takes about "
                    + "three minutes; a short read is not the page."
            }
            return nil
        }
    }

    /// The backlog ceiling. At 1024 frames per buffer and 48 kHz that is about
    /// 5.5 seconds of audio in flight, which a disk write will never need. The
    /// number exists so that a stalled writer is a COUNTED failure rather than
    /// unbounded memory growth on the audio thread's back.
    static let maxPendingBuffers = 256

    // ---------------------------------------------------------- arm B state
    //
    // Three separate facts, deliberately not one Bool: what the operator asked
    // for, what the audio node actually became, and why it refused. Arm B's
    // entire meaning is "this recording differs from arm A by one setting", so
    // a wanted-but-not-applied toggle produces two identical recordings that
    // the harness would read as the strongest possible evidence that the
    // setting does nothing.

    /// What the operator asked for. Read by `PhoneListener` when it builds the
    /// capture engine. UserDefaults-backed so it survives the engine rebuild
    /// that applying it forces.
    static var voiceProcessingWanted: Bool {
        get { UserDefaults.standard.bool(forKey: "scratchVoiceProcessing") }
        set { UserDefaults.standard.set(newValue, forKey: "scratchVoiceProcessing") }
    }

    /// What the input node actually reports after the attempt. The screen shows
    /// this, never `voiceProcessingWanted`.
    static var voiceProcessingActual = false

    /// Why the node refused, if it did. `nil` is not "fine" — read it with
    /// `voiceProcessingActual`.
    static var voiceProcessingRefusal: String?

    /// The arm the current audio configuration can honestly record.
    ///
    /// This is the guard that stops arm B being recorded by an engine that
    /// never took the setting, and arm A being recorded by one that did.
    static func armMatchesEngine(_ arm: Arm) -> String? {
        if arm.wantsVoiceProcessing && !voiceProcessingActual {
            let why = voiceProcessingRefusal.map { ": \($0)" } ?? ""
            return "Voice processing is not on, so this would be a second arm A"
                + why + ". Turn it on, wait for listening to restart, try again."
        }
        if !arm.wantsVoiceProcessing && voiceProcessingActual {
            return "Voice processing is still ON. Arm \(arm.rawValue) is "
                + "today's settings — turn it off and wait for listening to restart."
        }
        return nil
    }

    private let writer = DispatchQueue(label: "ai.anticipy.scratch-recorder",
                                       qos: .utility)
    private let lock = NSLock()

    // Guarded by `lock`. `armed` is read on the audio thread on every buffer,
    // so it stays a plain Bool behind the lock rather than anything that can
    // allocate.
    private var armed = false
    private var arm: Arm = .a
    private var file: AVAudioFile?
    private var url: URL?
    private var framesWritten: AVAudioFramePosition = 0
    private var sampleRate: Double = 0
    private var channels: UInt32 = 0
    private var pending = 0
    private var dropped = 0
    private var failure: String?

    private init() {}

    var isRecording: Bool {
        lock.lock(); defer { lock.unlock() }
        return armed
    }

    /// The arm currently being recorded, for the screen.
    var currentArm: Arm? {
        lock.lock(); defer { lock.unlock() }
        return armed ? arm : nil
    }

    /// Where takes live. `Documents/scratch/` so the operator can pull the WAVs
    /// off the phone with the Files app — `UIFileSharingEnabled` and
    /// `LSSupportsOpeningDocumentsInPlace` in Info.plist are what make that
    /// directory visible, and without them these files can only be reached by
    /// unpacking a container from Xcode.
    static var directory: URL {
        let docs = FileManager.default.urls(for: .documentDirectory,
                                            in: .userDomainMask)[0]
        return docs.appendingPathComponent("scratch", isDirectory: true)
    }

    /// Every take on disk, newest first. The screen lists these so the operator
    /// can see all three arms before walking to the Mac.
    static func takesOnDisk() -> [URL] {
        let fm = FileManager.default
        let found = (try? fm.contentsOfDirectory(at: directory,
                                                 includingPropertiesForKeys: [.contentModificationDateKey],
                                                 options: [.skipsHiddenFiles])) ?? []
        return found.filter { $0.pathExtension.lowercased() == "wav" }
            .sorted { a, b in
                let da = (try? a.resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate ?? .distantPast
                let db = (try? b.resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate ?? .distantPast
                return da > db
            }
    }

    /// Open a file for `arm` in the tap's own format.
    ///
    /// Returns the reason on failure rather than throwing, because every caller
    /// is a button and the operator needs the sentence, not a crash. A failure
    /// here leaves `armed` false, so `accept(_:)` stays a no-op.
    @discardableResult
    func start(arm: Arm, format: AVAudioFormat) -> String? {
        lock.lock()
        if armed {
            lock.unlock()
            return "Already recording arm \(self.arm.rawValue)."
        }
        lock.unlock()

        guard format.sampleRate > 0, format.channelCount > 0 else {
            return "The microphone is reporting 0 Hz. Something else owns the "
                + "audio session — end the call and try again."
        }
        let fm = FileManager.default
        do {
            try fm.createDirectory(at: Self.directory, withIntermediateDirectories: true)
        } catch {
            return "Could not make the scratch directory: \(error.localizedDescription)"
        }
        // The name carries the arm and the wall clock. The arm is duplicated in
        // the provenance line and in the directory the operator drops it into;
        // three independent statements of the same fact is the point, because
        // the one failure this experiment cannot survive is a mislabelled arm.
        let stamp = ISO8601DateFormatter().string(from: Date())
            .replacingOccurrences(of: ":", with: "")
        let target = Self.directory.appendingPathComponent("arm_\(arm.rawValue.lowercased())_\(stamp).wav")

        let made: AVAudioFile
        do {
            made = try AVAudioFile(forWriting: target,
                                   settings: format.settings,
                                   commonFormat: format.commonFormat,
                                   interleaved: format.isInterleaved)
        } catch {
            return "Could not open the file: \(error.localizedDescription)"
        }

        lock.lock()
        self.arm = arm
        self.file = made
        self.url = target
        self.framesWritten = 0
        self.sampleRate = format.sampleRate
        self.channels = format.channelCount
        self.pending = 0
        self.dropped = 0
        self.failure = nil
        self.armed = true
        lock.unlock()
        return nil
    }

    /// Called from the microphone tap, on the audio thread.
    ///
    /// Two operations and no file I/O: a bounded-backlog check and a copy. The
    /// copy is not optional — `installTap` reuses its buffer, so a reference
    /// held past this call writes whatever arrived next.
    func accept(_ buffer: AVAudioPCMBuffer) {
        lock.lock()
        guard armed, file != nil else { lock.unlock(); return }
        if pending >= Self.maxPendingBuffers {
            // Counted, never silent. A hole in the WAV and a starved microphone
            // are the same shape to the scorer, and one of them is the finding.
            dropped &+= 1
            lock.unlock()
            return
        }
        pending &+= 1
        lock.unlock()

        guard let copy = Self.copy(buffer) else {
            lock.lock()
            pending -= 1
            dropped &+= 1
            lock.unlock()
            return
        }
        writer.async { [weak self] in
            guard let self else { return }
            self.lock.lock()
            let target = self.file
            self.lock.unlock()
            var wrote: String?
            if let target {
                do { try target.write(from: copy) }
                catch { wrote = error.localizedDescription }
            }
            self.lock.lock()
            self.pending -= 1
            if let wrote, self.failure == nil { self.failure = wrote }
            if wrote == nil { self.framesWritten += AVAudioFramePosition(copy.frameLength) }
            self.lock.unlock()
        }
    }

    /// Close the file and describe what was recorded.
    ///
    /// Drains the writer first: `stop()` returning before the last buffers land
    /// would hash a file still being written, and the digest is the one thing
    /// that stops two cells naming the same recording.
    func stop() -> Take? {
        lock.lock()
        guard armed else { lock.unlock(); return nil }
        armed = false
        let takenArm = arm
        let takenURL = url
        let rate = sampleRate
        let chans = channels
        lock.unlock()

        writer.sync {}          // drain

        lock.lock()
        file = nil              // closes the file
        url = nil
        let frames = framesWritten
        let lost = dropped
        let why = failure
        lock.unlock()

        guard let takenURL else { return nil }
        let seconds = rate > 0 ? Double(frames) / rate : 0
        return Take(arm: takenArm, url: takenURL, seconds: seconds,
                    sampleRate: rate, channels: chans, droppedBuffers: lost,
                    sha256: Self.digest(of: takenURL), writeFailure: why)
    }

    /// Delete one take. The operator will make bad ones — a cough, a phone
    /// ringing, losing their place in the script — and a directory full of
    /// discarded reads is how the wrong WAV gets scored.
    static func discard(_ url: URL) {
        try? FileManager.default.removeItem(at: url)
    }

    // ------------------------------------------------------------ internals

    /// A real deep copy, format-agnostic: memcpy over the audio buffer list
    /// rather than reaching for `floatChannelData`, which is nil for every
    /// integer format and would silently record nothing on a device whose tap
    /// is not float32.
    static func copy(_ buffer: AVAudioPCMBuffer) -> AVAudioPCMBuffer? {
        guard buffer.frameLength > 0,
              let out = AVAudioPCMBuffer(pcmFormat: buffer.format,
                                         frameCapacity: buffer.frameLength)
        else { return nil }
        out.frameLength = buffer.frameLength
        let src = UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: buffer.audioBufferList))
        let dst = UnsafeMutableAudioBufferListPointer(out.mutableAudioBufferList)
        guard src.count == dst.count else { return nil }
        for i in 0..<src.count {
            guard let from = src[i].mData, let to = dst[i].mData else { return nil }
            let bytes = Int(min(src[i].mDataByteSize, dst[i].mDataByteSize))
            memcpy(to, from, bytes)
            dst[i].mDataByteSize = UInt32(bytes)
        }
        return out
    }

    /// Streaming sha256, so a three-minute 48 kHz float recording is not read
    /// into memory whole on a phone.
    static func digest(of url: URL) -> String {
        guard let handle = try? FileHandle(forReadingFrom: url) else { return "" }
        defer { try? handle.close() }
        var hasher = SHA256()
        while true {
            let chunk = (try? handle.read(upToCount: 1 << 20)) ?? Data()
            if chunk.isEmpty { break }
            hasher.update(data: chunk)
        }
        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }
}
