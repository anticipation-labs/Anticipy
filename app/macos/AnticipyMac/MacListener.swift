import AppKit
import AVFoundation
import Foundation
import Speech

/// Owns one two-sided meeting session: the owner's microphone, the Mac's
/// system output, one on-device transcriber per side, and a local archive.
@MainActor
@available(macOS 26.0, *)
final class MacListener: NSObject, ObservableObject {
    enum State: String {
        case idle, starting, recording, degraded, finishing, denied

        var isCapturing: Bool { self == .recording || self == .degraded }
    }

    enum StartReason: Equatable {
        case manual
        case detectedMeeting(bundleID: String?)
    }

    @Published private(set) var state: State = .idle
    @Published private(set) var lastLine = ""
    @Published private(set) var lines: [MeetingTranscriptLine] = []
    @Published private(set) var liveOwnerText = ""
    @Published private(set) var liveSystemText = ""
    @Published private(set) var healthSentence = ""
    @Published private(set) var currentArchiveURL: URL?
    @Published private(set) var lastArchiveURL: URL?

    private let audioEngine = AVAudioEngine()
    private var microphoneTapInstalled = false
    private var systemCapture: SystemAudioCapture?
    private var ownerSpeech: MacSpeechPipeline?
    private var systemSpeech: MacSpeechPipeline?
    private var archive: MeetingArchive?
    private var ownerLines = MeetingLinePolicy()
    private var systemLines = MeetingLinePolicy()
    private var ownerMeter = AudioCaptureMeter()
    private var systemMeter = AudioCaptureMeter()
    private var ownerSampleRate = 48_000.0
    private var systemSampleRate = 48_000.0
    private var flushTimer: Timer?
    private var healthTimer: Timer?
    private var routeObserver: NSObjectProtocol?
    private var systemEmptyWindows = 0
    private var systemRestartAttempts = 0
    private var stopCompletionsRemaining = 0
    private var startReason: StartReason = .manual
    private var sessionID: UUID?
    private var endingState: State = .idle
    private var endingSentence = "Recording saved on this Mac."

    var startedForDetectedMeeting: Bool {
        if case .detectedMeeting = startReason { return true }
        return false
    }

    static func isSupported() -> Bool { SpeechTranscriber.isAvailable }

    func start(reason: StartReason = .manual) {
        guard state == .idle || state == .denied else { return }
        state = .starting
        healthSentence = "Opening the microphone and system audio…"
        startReason = reason
        let requestedSessionID = UUID()
        sessionID = requestedSessionID

        Task { [weak self] in
            guard let self else { return }
            let speechAllowed = await Self.requestSpeechPermission()
            let microphoneAllowed = await AVCaptureDevice.requestAccess(for: .audio)
            guard self.sessionID == requestedSessionID,
                  self.state == .starting else { return }
            guard speechAllowed, microphoneAllowed else {
                self.sessionID = nil
                self.state = .denied
                self.healthSentence = "Anticipy needs Microphone and Speech Recognition permission in Privacy & Security."
                return
            }
            self.beginCapture()
        }
    }

    private func beginCapture() {
        do {
            let bundleID: String?
            if case .detectedMeeting(let detected) = startReason { bundleID = detected }
            else { bundleID = nil }
            let archive = try MeetingArchive(detectedBundleID: bundleID)
            self.archive = archive
            currentArchiveURL = archive.directoryURL
        } catch {
            sessionID = nil
            state = .denied
            healthSentence = "Anticipy could not create a local meeting folder: \(error.localizedDescription)"
            return
        }

        lines = []
        lastLine = ""
        liveOwnerText = ""
        liveSystemText = ""
        ownerLines = MeetingLinePolicy()
        systemLines = MeetingLinePolicy()
        ownerMeter = AudioCaptureMeter()
        systemMeter = AudioCaptureMeter()
        systemEmptyWindows = 0
        systemRestartAttempts = 0

        let ownerSpeech = makeSpeechPipeline(label: "owner", channel: .owner)
        let systemSpeech = makeSpeechPipeline(label: "system", channel: .system)
        self.ownerSpeech = ownerSpeech
        self.systemSpeech = systemSpeech
        ownerSpeech.begin()
        systemSpeech.begin()

        do {
            try openMicrophone()
        } catch {
            let sentence = "The microphone could not start: \(error.localizedDescription)"
            tearDownAudio()
            finishSession(endingIn: .denied, sentence: sentence)
            return
        }

        do {
            try openSystemAudio()
            state = .recording
            healthSentence = "Microphone is recording. Waiting for sound from the meeting."
        } catch {
            state = .degraded
            healthSentence = error.localizedDescription
        }

        flushTimer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) {
            [weak self] _ in Task { @MainActor in self?.flushReadyLines() }
        }
        healthTimer = Timer.scheduledTimer(withTimeInterval: 4.0, repeats: true) {
            [weak self] _ in Task { @MainActor in self?.checkStreamHealth() }
        }
        routeObserver = NotificationCenter.default.addObserver(
            forName: .AVAudioEngineConfigurationChange,
            object: audioEngine, queue: .main) { [weak self] _ in
                Task { @MainActor in self?.restoreMicrophoneAfterRouteChange() }
            }
    }

    private func makeSpeechPipeline(label: String,
                                    channel: MeetingCaptureChannel) -> MacSpeechPipeline {
        let speech = MacSpeechPipeline(label: label)
        speech.onResult = { [weak self] text, isFinal in
            guard let self else { return }
            if channel == .owner { self.liveOwnerText = text }
            else { self.liveSystemText = text }
            self.lastLine = text
            guard isFinal else { return }
            if channel == .owner { self.ownerLines.absorbFinal(text, at: Date()) }
            else { self.systemLines.absorbFinal(text, at: Date()) }
        }
        speech.onError = { [weak self] in
            guard let self, self.state.isCapturing else { return }
            self.state = .degraded
            self.healthSentence = "One on-device transcript lane stopped. Audio is still being saved locally."
        }
        return speech
    }

    private func openMicrophone() throws {
        if microphoneTapInstalled {
            audioEngine.inputNode.removeTap(onBus: 0)
            microphoneTapInstalled = false
        }
        audioEngine.stop()
        let input = audioEngine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0 else {
            throw NSError(domain: "ai.anticipy.mac.microphone", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "The selected microphone has no readable format."])
        }
        ownerSampleRate = format.sampleRate
        let meter = ownerMeter
        let archive = archive
        let speech = ownerSpeech
        input.installTap(onBus: 0, bufferSize: 2_048, format: format) { buffer, _ in
            guard let owned = buffer.anticipyCopy() else { return }
            meter.record(owned)
            archive?.record(owned, channel: .owner)
            speech?.append(owned)
        }
        microphoneTapInstalled = true
        audioEngine.prepare()
        try audioEngine.start()
    }

    private func openSystemAudio() throws {
        systemCapture?.stop()
        let capture = SystemAudioCapture()
        let meter = systemMeter
        let archive = archive
        let speech = systemSpeech
        let format = try capture.start { buffer in
            meter.record(buffer)
            archive?.record(buffer, channel: .system)
            speech?.append(buffer)
        }
        systemSampleRate = format.sampleRate
        systemCapture = capture
    }

    private func restoreMicrophoneAfterRouteChange() {
        guard state.isCapturing else { return }
        do {
            try openMicrophone()
            healthSentence = "The microphone route changed and Anticipy reconnected it."
        } catch {
            state = .degraded
            healthSentence = "The microphone changed and could not be reopened: \(error.localizedDescription)"
        }
    }

    private func flushReadyLines() {
        let now = Date()
        if ownerLines.shouldFlush(at: now) { flush(channel: .owner, at: now) }
        if systemLines.shouldFlush(at: now) { flush(channel: .system, at: now) }
    }

    private func flush(channel: MeetingCaptureChannel, at now: Date = Date()) {
        let line: MeetingTranscriptLine?
        if channel == .owner { line = ownerLines.take(channel: channel, at: now) }
        else { line = systemLines.take(channel: channel, at: now) }
        guard let line else { return }
        lines.append(line)
        lastLine = line.text
        archive?.append(line)
    }

    private func checkStreamHealth() {
        guard state.isCapturing else { return }
        let policy = CaptureStreamHealthPolicy()
        var ownerVerdict = policy.verdict(ownerMeter.takeWindow(
            elapsedSeconds: 4, expectedSampleRate: ownerSampleRate))
        if ownerVerdict == .silentSinceStart, ownerMeter.hasEverCarriedSignal {
            ownerVerdict = .healthy
        }

        let systemWindow = systemMeter.takeWindow(elapsedSeconds: 4,
                                                  expectedSampleRate: systemSampleRate)
        var systemVerdict = policy.verdict(systemWindow)
        if systemVerdict == .silentSinceStart, systemMeter.hasEverCarriedSignal {
            systemVerdict = .healthy
        }

        if !ownerVerdict.isUsable {
            state = .degraded
            healthSentence = policy.sentence(ownerVerdict, streamName: "The microphone")
            return
        }

        if !systemMeter.hasEverDelivered {
            healthSentence = "Microphone is carrying audio. Waiting for sound from the meeting."
            return
        }

        if systemVerdict == .notDelivering || systemVerdict == .starved {
            systemEmptyWindows += 1
            if systemEmptyWindows >= 3 { restartSystemAudio() }
            else {
                healthSentence = "Microphone is carrying audio. System audio paused; Anticipy is watching the connection."
            }
            return
        }

        systemEmptyWindows = 0
        if systemVerdict == .silentSinceStart {
            state = .degraded
            healthSentence = policy.sentence(systemVerdict, streamName: "System audio")
        } else {
            state = .recording
            systemRestartAttempts = 0
            healthSentence = "Microphone and meeting audio are both carrying sound."
        }
    }

    private func restartSystemAudio() {
        guard systemRestartAttempts < 5 else {
            state = .degraded
            healthSentence = "System audio stopped after it had worked. Microphone audio is still being saved."
            return
        }
        systemRestartAttempts += 1
        systemEmptyWindows = 0
        do {
            try openSystemAudio()
            healthSentence = "Chrome or the audio route changed; Anticipy rebuilt the system-audio connection."
        } catch {
            state = .degraded
            healthSentence = "System audio could not reconnect: \(error.localizedDescription)"
        }
    }

    func stop() {
        guard state != .idle, state != .finishing else { return }
        sessionID = nil
        if state == .starting, ownerSpeech == nil, systemSpeech == nil,
           archive == nil {
            state = .idle
            healthSentence = "Recording start cancelled."
            return
        }
        flushTimer?.invalidate(); flushTimer = nil
        healthTimer?.invalidate(); healthTimer = nil
        if let routeObserver { NotificationCenter.default.removeObserver(routeObserver) }
        routeObserver = nil
        tearDownAudio()
        finishSession(endingIn: .idle,
                      sentence: "Recording saved on this Mac.")
    }

    private func finishSession(endingIn finalState: State, sentence: String) {
        sessionID = nil
        state = .finishing
        healthSentence = "Finishing the local transcript…"
        endingState = finalState
        endingSentence = sentence
        let lanes = [ownerSpeech, systemSpeech].compactMap { $0 }
        stopCompletionsRemaining = lanes.count
        guard !lanes.isEmpty else {
            finishArchive()
            return
        }
        for lane in lanes {
            lane.finish { [weak self] in self?.speechLaneFinished() }
        }
    }

    private func speechLaneFinished() {
        stopCompletionsRemaining -= 1
        guard stopCompletionsRemaining <= 0 else { return }
        flush(channel: .owner)
        flush(channel: .system)
        ownerSpeech = nil
        systemSpeech = nil
        finishArchive()
    }

    private func finishArchive() {
        let archive = archive
        self.archive = nil
        currentArchiveURL = nil
        guard let archive else {
            state = endingState
            healthSentence = endingSentence
            return
        }
        archive.finish { [weak self] url in
            guard let self else { return }
            self.lastArchiveURL = url
            self.healthSentence = self.endingSentence
            self.state = self.endingState
        }
    }

    private func tearDownAudio() {
        if microphoneTapInstalled {
            audioEngine.inputNode.removeTap(onBus: 0)
            microphoneTapInstalled = false
        }
        audioEngine.stop()
        systemCapture?.stop()
        systemCapture = nil
    }

    func revealLastRecording() {
        guard let url = lastArchiveURL ?? currentArchiveURL else { return }
        NSWorkspace.shared.activateFileViewerSelecting([url])
    }

    private static func requestSpeechPermission() async -> Bool {
        switch SFSpeechRecognizer.authorizationStatus() {
        case .authorized:
            return true
        case .denied, .restricted:
            return false
        case .notDetermined:
            return await withCheckedContinuation { continuation in
                SFSpeechRecognizer.requestAuthorization { status in
                    continuation.resume(returning: status == .authorized)
                }
            }
        @unknown default:
            return false
        }
    }

}
